import hashlib
import json
import logging
import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.alpha.c3 import FIRST_DAY
from cli.data.manifest import build_manifest, series_entry
from cli.onchain.crosscheck import CM_SERIES, SPAN, crosscheck, ratios, summary
from cli.onchain.freeze import SNAPSHOT_RELPATH
from cli.onchain.series import COLUMNS, SCHEMA
from cli.vintage.table import derive_table
from tests.vintage_fixtures import BASE_TICK_START, body
from tests.vintage_stub import FakeClock, build_record, standard_record

MVRV, PRICE, SUPPLY = CM_SERIES
SET = "btc-onchain-20260401T000000Z"
NAS = Path("/mnt/zhao-crypto")
RUN_AT = BASE_TICK_START + timedelta(days=30, seconds=17)
_LOG_LINE = re.compile(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} (INFO|WARNING|ERROR) zcrypto\.onchain\.\w+ \[[^\]]*\] - (.*)")

# The span's two ends and the day either side of it, spelt here.
PRE, FIRST = date(2010, 12, 31), date(2011, 1, 1)
LAST, POST = date(2026, 3, 30), date(2026, 3, 31)
JANUARY = [date(2020, 1, 1) + timedelta(days=n) for n in range(28)]
GAP = date(2020, 1, 15)
CAP_MVRV, PRICE_USD, SPLY_CUR = 2.5, 40000.0, 18000000.0
TOKENS = {"CapMVRVCur": "2.5", "PriceUSD": "40000", "SplyCur": "18000000"}
SPAN_DAYS = [FIRST, *JANUARY, LAST]
SERVED = [PRE, *SPAN_DAYS, POST]
# Served on every day of SERVED but GAP, on which Coin Metrics serves no CapMVRVCur.
VENDOR = {day: {metric: token for metric, token in TOKENS.items() if (day, metric) != (GAP, "CapMVRVCur")} for day in SERVED}
# Served before and after the span alone.
UNSPANNED = {day: dict(TOKENS) for day in (PRE, POST)}
# A run's snapshot holds every calendar day of the span and the day either side of it.
CALENDAR = [FIRST + timedelta(days=n) for n in range((LAST - FIRST).days + 1)]
HELD = [PRE, *CALENDAR, POST]


def _snapshot(rows: dict[date, tuple[float | None, float | None, float | None]]) -> pl.DataFrame:
    """A snapshot of `rows`' days, each `(price, supply, realized_cap)`; every other valuation null."""
    days = sorted(rows)
    given = dict(zip(("price", "supply", "realized_cap"), zip(*(rows[day] for day in days), strict=True), strict=True))
    data = {
        "ts": [datetime.combine(day, time(), UTC) for day in days],
        "last_height": list(range(len(days))),
        "last_hash": [f"{n:064x}" for n in range(len(days))],
    } | {column: list(given.get(column, [None] * len(days))) for column in COLUMNS[3:]}
    return pl.DataFrame(data, schema=SCHEMA)


def _ours(days: list[date], r_mvrv: dict[date, float]) -> dict[date, tuple[float, float, float]]:
    """Each day at the vendor's supply and at 1.001 times its price, its realized cap the one whose `r_mvrv` is the day's
    in `r_mvrv`, else 0.01."""
    return {day: (PRICE_USD * 1.001, SPLY_CUR, PRICE_USD * SPLY_CUR / (CAP_MVRV * (1 + r_mvrv.get(day, 0.01)))) for day in days}


def _cm(vendor: dict[date, dict[str, str]]) -> dict[str, dict[date, str | None]]:
    metric = {series: series.rsplit("/", 1)[1] for series in CM_SERIES}
    return {series: {day: row[metric[series]] for day, row in vendor.items() if metric[series] in row} for series in CM_SERIES}


def _snapshot_dir(root: Path, frame: pl.DataFrame) -> Path:
    """`frame` as a frozen set under `root`, its manifest naming the file's content hash."""
    out = root / SET
    (out / SNAPSHOT_RELPATH).parent.mkdir(parents=True)
    frame.write_parquet(out / SNAPSHOT_RELPATH)
    manifest = build_manifest(
        {SNAPSHOT_RELPATH: series_entry(frame, SNAPSHOT_RELPATH)},
        written_at="2026-04-01T00:00:00+00:00",
        identity="set",
        provenance={"producer": "zcrypto onchain freeze"},
    )
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return out


def _table(root: Path, vendor: dict[date, dict[str, str]]) -> tuple[Path, str]:
    """A versions table derived from one tick whose cm-btc body serves `vendor`'s tokens; its root and its head's sha256."""
    rows = [{"asset": "btc", "time": f"{day}T00:00:00.000000000Z", **tokens} for day, tokens in sorted(vendor.items())]
    data = b"".join(json.dumps(row, separators=(",", ":")).encode() + b"\n" for row in rows)
    build_record(root / "vintages", [(BASE_TICK_START, {"cm-btc": data})])
    outcome = derive_table(
        root / "vintages" / "record", root / "versions", nas_mount=NAS, opened_by="0.0.0", clock=FakeClock(RUN_AT)
    )
    assert outcome.complete, outcome
    return root / "versions", outcome.head_sha256


@pytest.fixture(scope="module")
def vendor_table(tmp_path_factory) -> tuple[Path, str]:
    return _table(tmp_path_factory.mktemp("vendor"), VENDOR)


@pytest.fixture(scope="module")
def unspanned_table(tmp_path_factory) -> tuple[Path, str]:
    return _table(tmp_path_factory.mktemp("unspanned"), UNSPANNED)


@pytest.fixture(scope="module")
def standard_table(tmp_path_factory) -> tuple[Path, list[str]]:
    """The standard record's table and its heads' sha256s, oldest first."""
    root = tmp_path_factory.mktemp("standard")
    standard_record(root / "vintages")
    outcome = derive_table(
        root / "vintages" / "record", root / "versions", nas_mount=NAS, opened_by="0.0.0", clock=FakeClock(RUN_AT)
    )
    assert outcome.complete, outcome
    heads = sorted((root / "versions" / "gen-1" / "heads").glob("*/*/*/*/head.json"))
    return root / "versions", [hashlib.sha256(path.read_bytes()).hexdigest() for path in heads]


def _run(root: Path, table: tuple[Path, str], frame: pl.DataFrame, caplog) -> tuple[int, list[str], list[str]]:
    """`crosscheck` over `frame` frozen under `root` and `table` through its head: its code, its INFO and its ERROR lines."""
    snapshot = _snapshot_dir(root, frame)
    caplog.set_level(logging.INFO)
    caplog.clear()
    code = crosscheck(snapshot, table[0], generation=1, head=table[1])
    lines = [(record.levelno, record.getMessage()) for record in caplog.records if record.name == "zcrypto.onchain.crosscheck"]
    return code, [m for level, m in lines if level == logging.INFO], [m for level, m in lines if level == logging.ERROR]


def _reasons(errors: list[str]) -> list[str]:
    prefix = f"onchain crosscheck failed snapshot={SET} reason="
    assert all(error.startswith(prefix) for error in errors), errors
    return [error.removeprefix(prefix) for error in errors]


def _cli(argv: list[str]) -> tuple[int, list[tuple[str, str]]]:
    """`zcrypto onchain <argv>` through the app; each line it printed as (level, message)."""
    result = CliRunner().invoke(app, ["onchain", *argv])
    printed = result.output.splitlines()
    lines = [_LOG_LINE.fullmatch(line) for line in printed]
    assert all(lines), printed
    return result.exit_code, [line.groups() for line in lines]


def test_the_three_ratios_on_a_known_answer():
    one, two = date(2021, 6, 1), date(2021, 6, 2)
    snapshot = _snapshot({one: (55.0, 1010.0, 25000.0), two: (90.0, 2000.0, 60000.0)})
    cm = {MVRV: {one: "2", two: "3.5"}, PRICE: {one: "50", two: "100"}, SUPPLY: {one: "1000", two: "2100"}}

    values, left_out = ratios(snapshot, cm)

    # r_mvrv reads the vendor's price: at our own, day one's would be 0.111 and day two's -0.142857.
    assert values["r_mvrv"] == {one: pytest.approx(0.01), two: pytest.approx(-1 / 21)}
    assert values["r_price"] == {one: pytest.approx(0.1), two: pytest.approx(-0.1)}
    assert values["r_supply"] == {one: pytest.approx(0.01), two: pytest.approx(-1 / 21)}
    assert left_out == {"r_mvrv": {}, "r_price": {}, "r_supply": {}}


def test_a_day_either_side_lacks_is_counted_and_never_filled():
    both, vendor_only, snapshot_only, zero_realized, nan_price, retracted, zero_price = (date(2021, 6, d) for d in range(1, 8))
    ours = (55.0, 1010.0, 25000.0)
    snapshot = _snapshot(
        {
            both: ours,
            snapshot_only: ours,
            zero_realized: (55.0, 1010.0, 0.0),
            nan_price: (float("nan"), 1010.0, 25000.0),
            retracted: ours,
            zero_price: (0.0, 1010.0, 25000.0),
        }
    )
    # The vendor serves every day but `snapshot_only`, the day after one it serves; `retracted`'s CapMVRVCur is a
    # retraction, its current token null. `zero_price` is a day BRK has not priced, which it serves at 0.
    served = [both, vendor_only, zero_realized, nan_price, retracted, zero_price]
    cm = {
        MVRV: {day: None if day == retracted else "2" for day in served},
        PRICE: dict.fromkeys(served, "50"),
        SUPPLY: dict.fromkeys(served, "1000"),
    }

    values, left_out = ratios(snapshot, cm)

    assert left_out == {
        "r_mvrv": {vendor_only: "snapshot", snapshot_only: "vendor", zero_realized: "snapshot", retracted: "vendor"},
        "r_price": {vendor_only: "snapshot", snapshot_only: "vendor", nan_price: "snapshot", zero_price: "snapshot"},
        "r_supply": {vendor_only: "snapshot", snapshot_only: "vendor"},
    }
    assert values["r_mvrv"] == dict.fromkeys([both, nan_price, zero_price], pytest.approx(0.01))
    assert values["r_price"] == {both: pytest.approx(0.1), zero_realized: pytest.approx(0.1), retracted: pytest.approx(0.1)}
    assert values["r_supply"] == dict.fromkeys([both, zero_realized, nan_price, retracted, zero_price], pytest.approx(0.01))
    assert summary(values, left_out, (both, retracted))["all"]["r_mvrv"]["left_out"] == {"snapshot": 2, "vendor": 2}


def test_a_token_is_parsed_as_served():
    one, two = date(2026, 11, 11), date(2026, 11, 12)
    snapshot = _snapshot({one: (27000.0, 68888750.0, 3.2e11), two: (41000.0, 19000000.0, 3.0e11)})
    cm = {
        MVRV: {one: "5.887956238920945668", two: "2.6"},
        PRICE: {one: "27382.983663205", two: "4.0E+4"},
        SUPPLY: {one: "68888750.04312280", two: "19000000"},
    }

    values, _ = ratios(snapshot, cm)

    assert values["r_mvrv"] == {
        one: (27382.983663205 * 68888750.0 / 3.2e11) / 5.887956238920945668 - 1,
        two: (40000.0 * 19000000.0 / 3.0e11) / 2.6 - 1,
    }
    assert values["r_price"] == {one: 27000.0 / 27382.983663205 - 1, two: 41000.0 / 40000.0 - 1}
    assert values["r_supply"] == {one: 68888750.0 / 68888750.04312280 - 1, two: 0.0}


@pytest.mark.parametrize(
    ("case", "code", "reason"),
    [
        ("within", 0, None),
        ("median", 1, "the span's median |r_mvrv| 0.03 is above 0.02"),
        ("p99", 1, "the span's 99th percentile of |r_mvrv| 0.2 is above 0.1"),
        ("no-span-day", 1, "the span 2011-01-01..2026-03-30 holds no day r_mvrv compares"),
    ],
    ids=["within", "median", "p99", "no-span-day"],
)
def test_the_tolerance_exits_1_on_a_breach_and_0_within(tmp_path, vendor_table, unspanned_table, caplog, case, code, reason):
    """Every case's span holds no day the snapshot leaves out; `median` has every compared day at 0.03 and `p99` two
    of its 29 at -0.2 and the rest at 0.01, so each breaches its bar alone."""
    r_mvrv = {
        "within": {day: -0.015 for day in JANUARY[::2]},
        "median": dict.fromkeys(HELD, 0.03),
        "p99": {JANUARY[3]: -0.2, JANUARY[20]: -0.2},
        "no-span-day": {},
    }[case]
    table = unspanned_table if case == "no-span-day" else vendor_table

    got, infos, errors = _run(tmp_path, table, _snapshot(_ours(HELD, r_mvrv)), caplog)

    assert got == code
    assert _reasons(errors) == ([] if reason is None else [reason])
    if code == 0:
        assert infos[-1] == f"onchain crosscheck passed snapshot={SET} head={table[1]} span=2011-01-01..2026-03-30"


def test_the_span_bounds_the_tolerance(tmp_path, vendor_table, caplog):
    """A breach the day before the span and the day after it, at 5.0 each: counted with the span's 29, they would put
    its 99th percentile at 5.0."""
    code, infos, errors = _run(tmp_path, vendor_table, _snapshot(_ours(HELD, {PRE: 5.0, POST: 5.0})), caplog)

    assert (code, errors) == (0, [])
    assert re.search(r" r_mvrv n=31 .* max=5 ", next(line for line in infos if line.startswith("onchain crosscheck all ")))


def _planted(restored: bool, days: list[date] = HELD) -> pl.DataFrame:
    """`days`, each within both bars but FIRST, whose realized cap is null unless `restored`, and PRE, whose realized
    cap is 0.0; GAP, on which the vendor serves no CapMVRVCur, held as any other day."""
    rows = _ours(days, {})
    if not restored:
        rows[FIRST] = (rows[FIRST][0], rows[FIRST][1], None)
    rows[PRE] = (rows[PRE][0], rows[PRE][1], 0.0)
    return _snapshot(rows)


@pytest.mark.parametrize("restored", [False, True], ids=["as-planted", "restored"])
def test_a_day_the_snapshot_leaves_out_inside_the_span_exits_1_naming_it(tmp_path, vendor_table, caplog, restored):
    code, _, errors = _run(tmp_path, vendor_table, _planted(restored), caplog)

    if restored:
        assert (code, errors) == (0, [])
    else:
        assert code == 1
        assert _reasons(errors) == ["2011-01-01 is inside the span and the snapshot leaves it out of r_mvrv"]
        assert not [error for error in errors if str(PRE) in error or str(GAP) in error]


def test_the_span_line_counts_left_out_days_per_side():
    values, left_out = ratios(_planted(restored=False, days=SERVED), _cm(VENDOR))

    report = summary(values, left_out, (FIRST, LAST))

    assert report["span"]["r_mvrv"]["left_out"] == {"snapshot": 1, "vendor": 1}
    assert report["all"]["r_mvrv"]["left_out"] == {"snapshot": 2, "vendor": 1}
    assert (report["span"]["r_mvrv"]["n"], report["all"]["r_mvrv"]["n"]) == (28, 29)


def test_each_year_line_reads_its_own_year_alone():
    values, left_out = ratios(_planted(restored=False, days=SERVED), _cm(VENDOR))

    report = summary(values, left_out, (FIRST, LAST))

    assert list(report) == ["2010", "2011", "2020", "2026", "all", "span"]
    assert [report[year]["r_mvrv"]["n"] for year in ("2010", "2011", "2020", "2026")] == [0, 0, 27, 2]
    assert [report[year]["r_mvrv"]["left_out"] for year in ("2010", "2011")] == [{"snapshot": 1, "vendor": 0}] * 2


@pytest.mark.parametrize(("missing", "held"), [(FIRST, LAST), (LAST, FIRST)], ids=["first", "last"])
def test_the_span_s_calendar_reaches_both_its_ends(missing, held):
    _, left_out = ratios(_snapshot(_ours([held], {})), {}, SPAN)

    assert left_out["r_mvrv"].get(missing) == "snapshot"
    assert (min(left_out["r_mvrv"]), max(left_out["r_mvrv"])) == (FIRST, LAST)


def test_a_day_inside_the_span_neither_side_holds_is_the_snapshot_s_and_named(tmp_path, vendor_table, caplog):
    hole = date(2015, 5, 5)

    code, _, errors = _run(tmp_path, vendor_table, _snapshot(_ours([day for day in HELD if day != hole], {})), caplog)

    assert code == 1
    assert _reasons(errors) == ["2015-05-05 is inside the span and the snapshot leaves it out of r_mvrv"]


def _served_days(data: bytes) -> dict[date, dict[str, str]]:
    """Each day of a cm-btc body and the three metrics' tokens it serves."""
    rows = (json.loads(line) for line in data.splitlines() if line.strip())
    served = {date.fromisoformat(row["time"][:10]): {m: row[m] for m in TOKENS if row.get(m) is not None} for row in rows}
    return {day: tokens for day, tokens in served.items() if tokens}


def test_the_versions_are_read_through_the_head_named(tmp_path, standard_table, caplog):
    """The standard record's last tick is the first to serve 2026-11-11's three tokens; the snapshot agrees with every
    day that tick's body serves all three on and holds each day of the span and each day it serves any, so through
    the head before, that day alone moves from compared to the vendor's left-out."""
    versions, heads = standard_table
    served = _served_days(body("second/cm-btc-next"))
    full = [day for day, tokens in served.items() if len(tokens) == 3]
    rows = {day: (1.0, 1.0, 1.0) for day in [*CALENDAR, *served]}
    for day in full:
        price, supply, mvrv = (float(served[day][m]) for m in ("PriceUSD", "SplyCur", "CapMVRVCur"))
        rows[day] = (price, supply, price * supply / mvrv)
    unpaired = len(rows) - len(full)
    assert date(2026, 11, 11) in full and date(2026, 11, 11) not in _served_days(body("cm-btc"))

    for head, n, vendor in ((heads[-2], len(full) - 1, unpaired + 1), (heads[-1], len(full), unpaired)):
        root = tmp_path / head[:12]
        code, infos, errors = _run(root, (versions, head), _snapshot(rows), caplog)

        assert (code, errors) == (0, [])
        line = next(line for line in infos if line.startswith("onchain crosscheck all "))
        assert re.match(rf"onchain crosscheck all r_mvrv n={n} .* left_out=snapshot:0,vendor:{vendor} r_price ", line), line


def test_the_command_reads_a_snapshot_given_as_the_working_directory(tmp_path, vendor_table, monkeypatch):
    snapshot = _snapshot_dir(tmp_path, _planted(restored=True))
    monkeypatch.chdir(snapshot)
    versions, head = vendor_table

    code, lines = _cli(["crosscheck", "--snapshot", ".", "--versions", str(versions), "--generation", "1", "--head", head])

    assert code == 0
    assert lines[-1] == ("INFO", f"onchain crosscheck passed snapshot={SET} head={head} span=2011-01-01..2026-03-30")
    assert [label for label, _ in lines] == ["INFO"] * len(lines)


@pytest.mark.parametrize("form", ["stamp", "upper", "short"])
def test_a_head_named_by_anything_but_its_sha256_is_refused_in_one_line(tmp_path, vendor_table, form):
    """`stamp` is the head's own tick stamp, which the table would resolve."""
    versions, head = vendor_table
    named = {"stamp": next((versions / "gen-1" / "heads").glob("*/*/*/*")).name, "upper": head.upper(), "short": head[:63]}
    snapshot = _snapshot_dir(tmp_path, _planted(restored=True))

    code, lines = _cli(
        ["crosscheck", "--snapshot", str(snapshot), "--versions", str(versions), "--generation", "1", "--head", named[form]]
    )

    assert code == 1
    reason = f"--head {named[form]!r} is not a sha256 of 64 lowercase hex characters"
    assert lines == [("ERROR", f"onchain crosscheck refused snapshot={SET} reason={reason}")]


def test_a_head_the_table_lacks_is_refused_in_one_line(tmp_path, vendor_table):
    snapshot = _snapshot_dir(tmp_path, _planted(restored=True))
    versions, _ = vendor_table
    absent = "0" * 64

    code, lines = _cli(
        ["crosscheck", "--snapshot", str(snapshot), "--versions", str(versions), "--generation", "1", "--head", absent]
    )

    assert code == 1
    assert lines == [
        ("ERROR", f"onchain crosscheck refused snapshot={SET} reason=no head in {versions / 'gen-1'} hashes to {absent}")
    ]


def test_the_span_opens_on_the_readings_first_day():
    assert SPAN[0] == FIRST_DAY
