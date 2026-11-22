import hashlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal
from typer.testing import CliRunner

from cli.__main__ import app
from cli.data.manifest import read_manifest, series_entry
from cli.onchain.chain import ChainError, Line, chain_name, line_relpath, write_base, write_day
from cli.onchain.freeze import SNAPSHOT_RELPATH, freeze
from cli.onchain.series import COLUMNS, SCHEMA
from cli.registry.observed import ObservedReader
from tests.onchain_stub import COMMIT

NAME = chain_name(COMMIT)
GENESIS = date(2009, 1, 3)
# No block's monotonic day is 2009-01-04 to 2009-01-08, so the base holds no row for them.
BASE_DAYS = [GENESIS, *(date(2009, 1, 9) + timedelta(days=n) for n in range(4))]
LINE_DAYS = [date(2009, 1, 13), date(2009, 1, 14), date(2009, 1, 15)]
AS_OF = LINE_DAYS[1]
SET = "btc-onchain-20090116T000000Z"
WRITTEN_AT = "2009-01-16T00:00:00+00:00"
CHANGED = "days/2009/01/13.parquet"
_LOG_LINE = re.compile(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} (INFO|WARNING|ERROR) zcrypto\.onchain\.\w+ \[[^\]]*\] - (.*)")


def _frame(days: list[date]) -> pl.DataFrame:
    index = [(day - GENESIS).days for day in days]
    rows = {
        "ts": [datetime.combine(day, time(), UTC) for day in days],
        "last_height": index,
        "last_hash": [f"{i:064x}" for i in index],
    } | {column: [1000.0 * i + n for i in index] for n, column in enumerate(COLUMNS[3:])}
    return pl.DataFrame(rows | {"mvrv_z": [None] * len(days)}, schema=SCHEMA)


def _vintage(day: date, release: int) -> dict:
    """Each line of `_chain` carries its own `release`, so the base's, the as-of line's and the head's image ids differ."""
    return {
        "written_at": f"{day + timedelta(days=1)}T02:17:00+00:00",
        "last_height": (day - GENESIS).days,
        "last_hash": f"{(day - GENESIS).days:064x}",
        "tip_height": (day - GENESIS).days + 12,
        "depth": 12,
        "brk_commit": COMMIT,
        "bitview_image": f"sha256:{release:064x}",
        "bitcoind_image": f"sha256:{release + 16:064x}",
        "chain": NAME,
    }


def _chain(root: Path) -> list[Line]:
    lines = [write_base(root, _frame(BASE_DAYS), _vintage(BASE_DAYS[-1], 0))]
    for release, day in enumerate(LINE_DAYS, start=1):
        lines.append(write_day(root, _frame([day]), _vintage(day, release)))
    return lines


def _change_a_listed_file(root: Path) -> None:
    """`CHANGED` replaced by a valid parquet of other bytes, its line and every link left as they are."""
    changed = pl.read_parquet(root / CHANGED).with_columns(pl.col("price") + 1.0)
    (root / CHANGED).unlink()
    changed.write_parquet(root / CHANGED)


def _tree(root: Path) -> dict[str, bytes | None]:
    return {path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None for path in sorted(root.rglob("*"))}


def _cli(argv: list[str]) -> tuple[int, list[tuple[str, str]]]:
    """`zcrypto onchain <argv>` through the app; each line it printed as (level, message)."""
    result = CliRunner().invoke(app, ["onchain", *argv])
    printed = result.output.splitlines()
    lines = [_LOG_LINE.fullmatch(line) for line in printed]
    assert all(lines), printed
    return result.exit_code, [line.groups() for line in lines]


def test_the_snapshot_is_one_file_and_a_conformant_manifest_naming_the_as_of_line(tmp_path):
    chain = tmp_path / NAME
    _chain(chain)
    out = tmp_path / SET

    assert freeze(chain, AS_OF, out, written_at=WRITTEN_AT) == out / "manifest.json"

    assert [path for path, data in _tree(out).items() if data is not None] == ["BTC/onchain.parquet", "manifest.json"]
    expected = _frame([*BASE_DAYS, *LINE_DAYS[:2]])
    assert_frame_equal(pl.read_parquet(out / SNAPSHOT_RELPATH), expected)
    manifest = json.loads((out / "manifest.json").read_text())
    assert read_manifest(out / "manifest.json").identity == "set"
    assert manifest["written_at"] == WRITTEN_AT
    assert manifest["series"] == {"BTC/onchain.parquet": series_entry(expected, "BTC/onchain.parquet")}
    as_of_line = chain / "index/2009/01/14.json"
    assert manifest["provenance"] == {
        "producer": "zcrypto onchain freeze",
        "chain": "btc-brk1a19c5e96976-g1",
        "as_of_line": {"relpath": "index/2009/01/14.json", "sha256": hashlib.sha256(as_of_line.read_bytes()).hexdigest()},
        "brk_commit": COMMIT,
        "bitview_image": f"sha256:{2:064x}",
        "bitcoind_image": f"sha256:{18:064x}",
    }


def test_observed_reader_reads_the_snapshot(tmp_path):
    _chain(tmp_path / NAME)
    out = tmp_path / SET

    code, lines = _cli(["freeze", "--chain", str(tmp_path / NAME), "--as-of", "2009-01-14", "--out", str(out)])

    assert code == 0
    assert lines == [("INFO", f"onchain freeze complete chain={NAME} as_of=2009-01-14 manifest={out / 'manifest.json'}")]
    reader = ObservedReader(tmp_path)
    assert_frame_equal(reader.read_series(SET, SNAPSHOT_RELPATH), _frame([*BASE_DAYS, *LINE_DAYS[:2]]))
    assert reader.vouched_status() == {SET: "checked (1 vouched hashes)"}
    assert datetime.fromisoformat(read_manifest(out / "manifest.json").written_at).utcoffset() == timedelta(0)


def test_an_as_of_past_the_head_is_refused(tmp_path):
    _chain(tmp_path / NAME)

    with pytest.raises(ChainError, match="holds no line for 2009-01-16; its newest is for 2009-01-15"):
        freeze(tmp_path / NAME, date(2009, 1, 16), tmp_path / SET, written_at=WRITTEN_AT)

    assert not (tmp_path / SET).exists()


def test_an_existing_out_is_refused(tmp_path):
    _chain(tmp_path / NAME)
    out = tmp_path / SET
    out.mkdir()
    (out / "notes.txt").write_bytes(b"a set begun by hand")

    with pytest.raises(ChainError, match=f"{re.escape(str(out))} exists"):
        freeze(tmp_path / NAME, AS_OF, out, written_at=WRITTEN_AT)

    assert _tree(out) == {"notes.txt": b"a set begun by hand"}


def test_a_chain_that_does_not_verify_is_refused_and_no_manifest_is_written(tmp_path):
    chain = tmp_path / NAME
    _chain(chain)
    _change_a_listed_file(chain)

    with pytest.raises(ChainError, match=f"index/2009/01/13.json: {CHANGED} does not hash to its listing"):
        freeze(chain, AS_OF, tmp_path / SET, written_at=WRITTEN_AT)

    assert not (tmp_path / SET).exists()


@pytest.mark.parametrize(
    ("chain", "as_of", "day", "days"),
    [(None, None, LINE_DAYS[-1], 4), (None, AS_OF, AS_OF, 3), (".", None, LINE_DAYS[-1], 4)],
    ids=["the-head", "an-as-of", "the-chain-as-the-working-directory"],
)
def test_the_verify_summary_names_the_head_and_its_sha256(tmp_path, monkeypatch, chain, as_of, day, days):
    _chain(tmp_path / NAME)
    sha256 = hashlib.sha256((tmp_path / NAME / line_relpath(day)).read_bytes()).hexdigest()
    monkeypatch.chdir(tmp_path / NAME)

    code, lines = _cli(["verify", "--chain", chain or str(tmp_path / NAME), *(["--as-of", as_of.isoformat()] if as_of else [])])

    assert code == 0
    assert lines == [("INFO", f"onchain verify complete chain={NAME} head={day} head_sha256={sha256} days={days}")]


@pytest.mark.parametrize(
    ("argv", "reason"),
    [
        (["verify"], f"index/2009/01/13.json: {CHANGED} does not hash to its listing"),
        (["freeze", "--as-of", "2009-01-14", "--out", SET], f"index/2009/01/13.json: {CHANGED} does not hash to its listing"),
        (["verify", "--as-of", "2009-01-32"], "--as-of '2009-01-32' is not a YYYY-MM-DD date"),
    ],
    ids=["verify-a-changed-file", "freeze-a-changed-file", "an-as-of-not-a-day"],
)
def test_a_refusal_is_one_error_line_and_exit_1(tmp_path, monkeypatch, argv, reason):
    _chain(tmp_path / NAME)
    _change_a_listed_file(tmp_path / NAME)
    monkeypatch.chdir(tmp_path)

    code, lines = _cli([*argv, "--chain", str(tmp_path / NAME)])

    assert code == 1
    assert lines == [("ERROR", f"onchain {argv[0]} refused chain={NAME} reason={reason}")]
    assert not (tmp_path / SET).exists()


def test_a_verify_of_a_chain_with_no_line_is_refused(tmp_path):
    code, lines = _cli(["verify", "--chain", str(tmp_path / NAME)])

    assert code == 1
    assert lines == [("ERROR", f"onchain verify refused chain={NAME} reason={tmp_path / NAME} holds no line")]
