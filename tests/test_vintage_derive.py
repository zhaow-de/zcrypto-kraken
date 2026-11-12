from __future__ import annotations

import gzip
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import polars as pl
import pytest

from cli.vintage.asof import as_of
from cli.vintage.chain import chain, scan
from cli.vintage.derive import (
    COVERAGE_SCHEMA,
    LATER_FACTS_SCHEMA,
    SERIES_KINDS,
    VERSIONS_SCHEMA,
    DeriveState,
    changed_values,
    derive_record,
    derive_tick,
    flags,
    frames,
    parse_series,
)
from cli.vintage.record import Published
from cli.vintage.sources import SOURCE_BY_ID, LinkAcknowledgment
from tests.vintage_fixtures import BASE_TICK_START, FROZEN_METRIC, GAP_METRIC, GONE_METRIC, body, dumps_compact, loads_tokens
from tests.vintage_stub import Reply, build_record, standard_record

T0 = BASE_TICK_START
HOUR = timedelta(hours=1)
CM_BTC = SOURCE_BY_ID["cm-btc"]


def _second(name: str) -> bytes:
    return body(f"second/{name}")


def _record(root: Path, ticks: list[dict]) -> tuple[list[Published], tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]]:
    """One tick per entry at `T0 + 3 h × i`, every source its default body but where the entry names its own."""
    published = build_record(root, [(T0 + 3 * i * HOUR, replies) for i, replies in enumerate(ticks)])
    return published, derive_record(root / "record")


def _fetch(published: Published, source_id: str) -> dict:
    (fetch,) = (fetch for fetch in published.manifest["fetches"] if fetch["source"] == source_id)
    return fetch


def _ended(published: Published, source_id: str) -> datetime:
    return datetime.fromisoformat(_fetch(published, source_id)["attempts"][-1]["ended_at"])


def _after(published: Published) -> datetime:
    return datetime.fromisoformat(published.manifest["ended_at"])


def _stored(published: Published, source_id: str) -> bytes:
    return gzip.decompress((published.dir / _fetch(published, source_id)["body"]["file"]).read_bytes())


def _view(derived: tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame], t: datetime) -> pl.DataFrame:
    """The values as of t: the last-seen time is left out, since a later observation that held the day moves it."""
    return as_of(*derived, t).drop("last_seen_at")


def _at(frame: pl.DataFrame, position: int) -> pl.DataFrame:
    return frame.filter(pl.col("position") == position)


def _day(frame: pl.DataFrame, series: str, day: date) -> pl.DataFrame:
    return frame.filter((pl.col("series") == series) & (pl.col("ts") == datetime(day.year, day.month, day.day, tzinfo=UTC)))


def _rows(lines: bytes) -> list[dict]:
    return [loads_tokens(line) for line in lines.split(b"\n") if line.strip()]


def _stream(rows: list[dict]) -> bytes:
    return b"\n".join(dumps_compact(row) for row in rows)


def _carrying(rows: list[dict], key: str) -> list[int]:
    return [i for i, row in enumerate(rows) if key in row]


def test_as_of_never_returns_a_version_before_its_knowable_time(tmp_path):
    restated = _second("cm-btc-restatement")
    probe = build_record(tmp_path / "probe", [(T0, {}), (T0 + 3 * HOUR, {"cm-btc": restated})])
    ended = _ended(probe[1], "cm-btc")
    server = ended.replace(microsecond=0) + timedelta(seconds=5)
    served = Reply(200, restated, headers=[("Date", format_datetime(server, usegmt=True))])
    published, derived = _record(tmp_path / "real", [{}, {"cm-btc": served}])
    assert _ended(published[1], "cm-btc") == ended
    (restatement,) = derived[0].filter(pl.col("kind") == "restatement").iter_rows(named=True)
    day = restatement["ts"].date()
    base_token = parse_series(CM_BTC, body("cm-btc"))[restatement["series"]][day]

    def token(t: datetime) -> str:
        return _day(as_of(*derived, t), restatement["series"], day)["token"].item()

    assert token(ended) == base_token
    assert token(server) == base_token
    assert token(server + timedelta(seconds=1)) == restatement["token"] != base_token


def test_an_outcome_2_body_that_lost_history_leaves_as_of_unchanged(tmp_path):
    published, derived = _record(tmp_path, [{}, {"cm-btc": _second("cm-btc-lost-newest")}])
    assert _fetch(published[1], "cm-btc")["check"]["outcome"] == 2
    assert _view(derived, _after(published[1])).equals(_view(derived, _after(published[0])))
    # Its losses lie above each series' new range, so they read as no retraction either way; what tells its absences
    # apart is the last-seen time, which a row with a hole and no evidence leaves where it was.
    lost = parse_series(CM_BTC, _second("cm-btc-lost-newest"))
    holed = [series for series, days in lost.items() if len(days) < (max(days) - min(days)).days + 1]
    assert holed
    kept = (pl.col("source") == "cm-btc") & pl.col("series").is_in(holed)
    assert as_of(*derived, _after(published[1])).filter(kept).equals(as_of(*derived, _after(published[0])).filter(kept))


def test_a_value_its_retraction_and_the_same_value_again(tmp_path):
    published, derived = _record(tmp_path, [{}, {"cm-btc": _second("cm-btc-retraction")}, {}])
    (retraction,) = derived[0].filter(pl.col("kind") == "retraction").iter_rows(named=True)
    series, day = retraction["series"], retraction["ts"].date()
    assert _day(derived[0], series, day)["kind"].to_list() == ["inherited", "retraction", "restoration"]
    now = _day(as_of(*derived, _after(published[2]) + 24 * HOUR), series, day)
    assert now["kind"].item() == "restoration"
    assert now["token"].item() == parse_series(CM_BTC, body("cm-btc"))[series][day]


def test_inherited_is_set_per_series_at_its_first_carrying_observation(tmp_path):
    _, (versions, _, _) = _record(tmp_path, [{"cm-btc": _second("cm-btc-metric-gone")}, {}])
    gone = f"cm/btc/{GONE_METRIC}"
    second = _at(versions, 1)
    assert set(second["series"]) == {gone}
    assert set(second["kind"]) == {"inherited"}
    assert second.height == len(parse_series(CM_BTC, body("cm-btc"))[gone])
    assert versions.filter((pl.col("series") == gone) & (pl.col("kind") == "first_publication")).is_empty()


def test_the_kinds_are_told_apart(tmp_path):
    _, (versions, _, _) = _record(tmp_path, [{}, {"cm-btc": _second("cm-btc-next")}, {"cm-btc": _second("cm-btc-restatement")}])
    base, after = parse_series(CM_BTC, body("cm-btc")), parse_series(CM_BTC, _second("cm-btc-next"))
    new = {(series, day) for series, days in after.items() for day in days if day not in base.get(series, {})}
    assert new
    second = _at(versions, 1)
    assert set(second["kind"]) == {"first_publication"}
    assert {(row["series"], row["ts"].date()) for row in second.iter_rows(named=True)} == new
    assert _at(versions, 2)["kind"].to_list() == ["restatement"]


def test_a_gap_filled_after_a_truncated_outcome_2_body_is_a_backfill(tmp_path):
    published, (versions, _, _) = _record(
        tmp_path, [{"cm-btc": _second("cm-btc-gap")}, {"cm-btc": _second("cm-btc-lost-newest")}, {}]
    )
    series = f"cm/btc/{GAP_METRIC}"
    (gap,) = parse_series(CM_BTC, body("cm-btc"))[series].keys() - parse_series(CM_BTC, _second("cm-btc-gap"))[series].keys()
    assert max(parse_series(CM_BTC, _second("cm-btc-lost-newest"))[series]) < gap
    assert _fetch(published[1], "cm-btc")["check"]["outcome"] == 2
    filled = _day(versions, series, gap)
    assert filled["kind"].to_list() == ["backfill"]
    assert filled["position"].to_list() == [2]


def test_a_value_gone_and_restored_changed_is_a_restatement(tmp_path):
    _, (versions, _, _) = _record(
        tmp_path, [{}, {"cm-btc": _second("cm-btc-metric-gone")}, {"cm-btc": _second("cm-btc-metric-back-changed")}]
    )
    assert _at(versions, 1).is_empty()
    third = _at(versions, 2)
    assert third["kind"].to_list() == ["restatement"]
    assert third["series"].to_list() == [f"cm/btc/{GONE_METRIC}"]


def test_an_outcome_2_bodys_absences_are_evidence_only_for_the_series_it_does_not_name(tmp_path):
    rows = _rows(_second("cm-btc-frozen"))
    frozen_rows = _carrying(rows, FROZEN_METRIC)
    del rows[frozen_rows[len(frozen_rows) // 2]][FROZEN_METRIC]
    other = "TxTfrCnt"
    other_rows = _carrying(rows, other)
    withdrawn = rows[other_rows[len(other_rows) // 2]]
    del withdrawn[other]
    published, (versions, _, _) = _record(tmp_path, [{}, {"cm-btc": _stream(rows)}])
    check = _fetch(published[1], "cm-btc")["check"]
    assert check["outcome"] == 2
    assert {failure[0] for failure in check["metrics_failed"]} == {FROZEN_METRIC}
    second = _at(versions, 1)
    assert second["kind"].to_list() == ["retraction"]
    assert second["series"].to_list() == [f"cm/btc/{other}"]
    assert second["ts"].item().date() == date.fromisoformat(withdrawn["time"][:10])


def test_a_status_companion_takes_its_metrics_evidence_rule(tmp_path):
    """FlowInExNtv loses its newest days, so the check names it; its -status companion, which the check never reads,
    loses a day inside its range, and that absence is no more evidence than its metric's."""
    rows = _rows(body("cm-btc"))
    for i in _carrying(rows, "FlowInExNtv")[-5:]:
        del rows[i]["FlowInExNtv"]
    companion = _carrying(rows, "FlowInExNtv-status")
    del rows[companion[len(companion) // 2]]["FlowInExNtv-status"]
    published, (versions, coverage, _) = _record(tmp_path, [{}, {"cm-btc": _stream(rows)}])
    assert {failure[0] for failure in _fetch(published[1], "cm-btc")["check"]["metrics_failed"]} == {"FlowInExNtv"}
    assert _at(versions, 1).is_empty()
    family = ["cm/btc/FlowInExNtv", "cm/btc/FlowInExNtv-status", "cm/btc/FlowInExNtv-status-time"]
    second = _at(coverage, 1).filter(pl.col("series").is_in(family))
    assert second.select("series", "evidence").rows() == [(series, False) for series in family]


def test_a_source_level_outcome_2_bodys_absences_are_no_evidence_for_any_series(tmp_path):
    published, derived = _record(tmp_path, [{}, {"cm-btc": _second("cm-btc-collapse")}])
    assert _fetch(published[1], "cm-btc")["check"]["metrics_failed"] == [["*", "collapse"]]
    assert derived[0].filter(pl.col("kind") == "retraction").is_empty()
    assert _view(derived, _after(published[1])).equals(_view(derived, _after(published[0])))


def _gzip(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=9, mtime=0)


NESTED = "cm/btc/FlowInExNtv-status"


def _nested_status() -> bytes:
    """`cm-btc` with an object under `FlowInExNtv-status` in its newest row carrying the key: a body the check passes,
    one key of which is no series."""
    rows = _rows(body("cm-btc"))
    [row for row in rows if "FlowInExNtv-status" in row][-1]["FlowInExNtv-status"] = {"state": "flash"}
    return _stream(rows)


UNPARSEABLE = {
    "cm-btc-nested-status": ("cm-btc", _nested_status()),
    "cm-btc-gzip": ("cm-btc", Reply(200, _gzip(body("cm-btc")), headers=[("Content-Encoding", "gzip")])),
    "cm-btc-html": ("cm-btc", b"<!DOCTYPE html><html><body>Service moved</body></html>"),
    "fng-empty": ("fng", b""),
    "bg-sopr-object": ("bg-sopr", b'{"d":"2026-11-01","unixTs":1793491200,"sopr":1.01}'),
    "cm-btc-array-line": ("cm-btc", body("cm-btc") + b"\n[]"),
    "fng-data-object": ("fng", b'{"name":"Fear and Greed Index","data":{"value":"29"},"metadata":{"error":null}}'),
    "cm-btc-not-utf-8": ("cm-btc", b"\xff\xfe" + body("cm-btc")),
    # Readable JSON with values the base does not hold, refused for shape by its check: it must add none of them.
    "fng-metadata-error": ("fng", _second("fng-next").replace(b'"error": null', b'"error": "Rate limit exceeded"')),
}


@pytest.mark.parametrize("stamp", ["+1794355200", " 1794355200", "-86400"])
def test_parse_series_refuses_the_epoch_forms_the_check_refuses(stamp):
    fng = body("fng").replace(b'"timestamp": "1794355200"', b'"timestamp": "%s"' % stamp.encode(), 1)
    assert fng != body("fng")
    with pytest.raises(ValueError):
        parse_series(SOURCE_BY_ID["fng"], fng)


@pytest.mark.parametrize("case", list(UNPARSEABLE))
def test_an_unparseable_observation_adds_no_version_and_never_stops_the_derive(tmp_path, case):
    source_id, served = UNPARSEABLE[case]
    published, derived = _record(tmp_path, [{}, {source_id: served}, {}])
    versions, coverage, _ = derived
    assert _at(versions, 1).filter(pl.col("source") == source_id).is_empty()
    rows = _at(coverage, 1).filter(pl.col("source") == source_id)
    if case == "cm-btc-nested-status":
        base = parse_series(CM_BTC, body("cm-btc"))
        assert NESTED in base
        assert parse_series(CM_BTC, served) == {series: days for series, days in base.items() if series != NESTED}
        assert sorted(rows["series"]) == sorted(set(base) - {NESTED})
        assert set(rows.select("outcome", "evidence").rows()) == {(0, True)}
    else:
        assert rows.select("series", "outcome", "evidence").rows() == [("*", 2, False)]
    assert _view(derived, _after(published[1])).equals(_view(derived, _after(published[0])))
    assert _at(versions, 2).filter(pl.col("source") == source_id).is_empty()


def test_the_coverage_rows_by_value(tmp_path):
    failing = [Reply(503, b"busy", reason="Service Unavailable")] * 3
    published, (_, coverage, _) = _record(
        tmp_path,
        [{}, {"cm-btc": _second("cm-btc-frozen")}, {"cm-btc": _second("cm-btc-collapse")}, {"fng": failing}],
    )
    assert {failure[0] for failure in _fetch(published[1], "cm-btc")["check"]["metrics_failed"]} == {FROZEN_METRIC}
    assert {failure[0] for failure in _fetch(published[2], "cm-btc")["check"]["metrics_failed"]} == {"*"}
    expected = {}
    for position, tick in enumerate(published):
        for fetch in tick.manifest["fetches"]:
            source = SOURCE_BY_ID[fetch["source"]]
            if source.kind not in SERIES_KINDS or fetch["check"]["outcome"] == 1:
                continue
            for series, days in parse_series(source, _stored(tick, source.id)).items():
                expected[(position, source.id, series)] = (min(days), max(days), len(days))
    unevidenced = {(1, "cm-btc", f"cm/btc/{FROZEN_METRIC}")} | {key for key in expected if key[:2] == (2, "cm-btc")}
    observed = coverage.filter(pl.col("series") != "*")
    found = {
        (row["position"], row["source"], row["series"]): (row["first_day"], row["last_day"], row["days"])
        for row in observed.iter_rows(named=True)
    }
    assert observed.height == len(found)
    assert found == expected
    assert {
        (row["position"], row["source"], row["series"]) for row in observed.filter(~pl.col("evidence")).iter_rows(named=True)
    } == unevidenced
    assert coverage.filter(pl.col("series") == "*").select(
        "position", "source", "series", "outcome", "reason", "evidence"
    ).rows() == [(3, "fng", "*", 1, "HTTP 503 after 3 attempts", False)]


def test_q3_brackets_a_day_first_held_at_the_second_tick(tmp_path):
    published, (versions, _, _) = _record(tmp_path, [{}, {"cm-btc": _second("cm-btc-next")}])
    new = _at(versions, 1)
    assert not new.is_empty()
    assert set(new["appeared_after"]) == {_ended(published[0], "cm-btc")}
    assert set(new["ended_at"]) == {_ended(published[1], "cm-btc")}
    inherited = versions.filter(pl.col("kind") == "inherited")
    assert inherited["appeared_after"].null_count() == inherited.height > 0


def test_q3s_lower_end_passes_over_an_observation_that_names_the_series(tmp_path):
    published, (versions, _, _) = _record(tmp_path, [{}, {"cm-btc": _second("cm-btc-frozen")}, {"cm-btc": _second("cm-btc-next")}])
    assert {failure[0] for failure in _fetch(published[1], "cm-btc")["check"]["metrics_failed"]} == {FROZEN_METRIC}
    series = f"cm/btc/{FROZEN_METRIC}"
    newest = max(parse_series(CM_BTC, _second("cm-btc-next"))[series])
    assert newest not in parse_series(CM_BTC, body("cm-btc"))[series]
    first = _day(versions, series, newest)
    assert first.select("kind", "position").rows() == [("first_publication", 2)]
    assert first["appeared_after"].item() == _ended(published[0], "cm-btc")


HOLDER = "ReferenceRate"


def _named_holders() -> tuple[list[dict], dict[str, date]]:
    """Three cm-btc bodies: the base; `cm-btc-frozen` with `ReferenceRate`'s newest day also gone, so its check names
    both metrics, the frozen one's days holed and `ReferenceRate`'s unbroken; then the base with a day each of the
    two restated, a day the second body still held. Every other source its default body."""
    second = _rows(_second("cm-btc-frozen"))
    del second[_carrying(second, HOLDER)[-1]][HOLDER]
    third = _rows(body("cm-btc"))
    restated = {}
    for metric in (FROZEN_METRIC, HOLDER):
        carrying = _carrying(third, metric)
        row = third[carrying[len(carrying) // 2]]
        row[metric] += "1"
        restated[f"cm/btc/{metric}"] = date.fromisoformat(row["time"][:10])
    return [{}, {"cm-btc": _stream(second)}, {"cm-btc": _stream(third)}], restated


def test_q3s_lower_end_for_a_restatement_is_the_last_observation_known_to_have_held_the_day(tmp_path):
    """The second body's check names both metrics, so neither's absences are evidence. Its `ReferenceRate` days run
    unbroken, so it is known to have held the restated day with the old token: the tighter lower end. Its frozen
    metric's days have holes, so coverage cannot say it held its day, and the lower end passes over it to the base."""
    ticks, restated = _named_holders()
    published, (versions, coverage, _) = _record(tmp_path, ticks)
    assert {failure[0] for failure in _fetch(published[1], "cm-btc")["check"]["metrics_failed"]} == {FROZEN_METRIC, HOLDER}
    second = _at(coverage, 1).filter(pl.col("series").is_in(list(restated)))
    unbroken = (pl.col("days") == (pl.col("last_day") - pl.col("first_day")).dt.total_days() + 1).alias("unbroken")
    assert second.select("series", "evidence", unbroken).sort("series").rows() == [
        ("cm/btc/AdrActCnt", False, False),
        ("cm/btc/ReferenceRate", False, True),
    ]
    lower_ends = {}
    for series, day in restated.items():
        assert day in parse_series(CM_BTC, _stored(published[1], "cm-btc"))[series]
        restatement = _day(versions, series, day).filter(pl.col("kind") == "restatement")
        assert restatement["position"].to_list() == [2]
        lower_ends[series] = restatement["appeared_after"].item()
    assert lower_ends == {
        f"cm/btc/{HOLDER}": _ended(published[1], "cm-btc"),
        f"cm/btc/{FROZEN_METRIC}": _ended(published[0], "cm-btc"),
    }


def _resumed(record_root: Path, split: int) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """The record derived through `split` ticks, then resumed from those ticks' frames alone, as a run resumes from
    its table."""
    order = chain(scan(record_root).ticks).order
    state = DeriveState.empty()
    found: tuple[list, list, list] = ([], [], [])
    for position, tick in enumerate(order):
        if position == split:
            state = DeriveState.from_frames(*frames(*found)[:2])
        regression = position > 0 and tick.stamp <= order[position - 1].stamp
        for into, rows in zip(found, derive_tick(state, tick, position, tick_dir=tick.dir, regression=regression), strict=True):
            into += rows
    return frames(*found)


@pytest.mark.parametrize("record", ["named-holders", "standard", "newest-back"])
def test_a_derive_resumed_from_its_frames_equals_one_run_tick_by_tick(tmp_path, record):
    if record == "standard":
        standard_record(tmp_path)
    elif record == "newest-back":
        back, withdrawn = _mempool(_newest_back), _mempool(_newest_withdrawn)
        _record(tmp_path, [{}, {}, {"mempool-hashrate": back}, {"mempool-hashrate": withdrawn}])
    else:
        _record(tmp_path, _named_holders()[0])
    whole = derive_record(tmp_path / "record")
    ticks = len(chain(scan(tmp_path / "record").ticks).order)
    for split in range(1, ticks):
        resumed = _resumed(tmp_path / "record", split)
        assert resumed[0].equals(whole[0]), split
        assert resumed[1].equals(whole[1]), split


MEMPOOL = SOURCE_BY_ID["mempool-hashrate"]


def _mempool(edit) -> bytes:
    doc = loads_tokens(body("mempool-hashrate"))
    edit(doc["hashrates"])
    return dumps_compact(doc)


def _newest_back(hashrates: list[dict]) -> None:
    del hashrates[-1]


def _newest_withdrawn(hashrates: list[dict]) -> None:
    """The newest day gone and the day after it added, so the gone day lies inside the body's range."""
    newest = hashrates.pop()
    hashrates.append(
        {"timestamp": type(newest["timestamp"])(int(newest["timestamp"]) + 86400), "avgHashrate": newest["avgHashrate"]}
    )


def _newest_restated(hashrates: list[dict]) -> None:
    hashrates[-1]["avgHashrate"] = type(hashrates[-1]["avgHashrate"])(hashrates[-1]["avgHashrate"] + "1")


def test_q3s_lower_end_for_a_new_day_outlives_a_later_unbroken_body_its_check_names(tmp_path):
    """Four days on, a repeat of the base is stale, so its check names every series at source level, yet its
    `ReferenceRate` days still run unbroken over the base's range. It shows those days but is no evidence that a later
    day was not yet held, so the base still bounds that day's first appearance."""
    rows = _rows(body("cm-btc"))
    newest = rows[_carrying(rows, HOLDER)[-1]]
    day = date.fromisoformat(newest["time"][:10]) + timedelta(days=1)
    rows.append({"asset": "btc", "time": f"{day.isoformat()}T00:00:00.000000000Z", HOLDER: newest[HOLDER]})
    published = build_record(tmp_path, [(T0, {}), (T0 + 96 * HOUR, {}), (T0 + 99 * HOUR, {"cm-btc": _stream(rows)})])
    versions, coverage, _ = derive_record(tmp_path / "record")
    assert ["*", "newest"] in _fetch(published[1], "cm-btc")["check"]["metrics_failed"]
    first, second = (_at(coverage, i).filter(pl.col("series") == f"cm/btc/{HOLDER}") for i in (0, 1))
    assert second.select("evidence", "first_day", "last_day", "days").rows() == [
        (False, first["first_day"].item(), first["last_day"].item(), first["days"].item())
    ]
    (version,) = _day(versions, f"cm/btc/{HOLDER}", day).iter_rows(named=True)
    assert (version["kind"], version["appeared_after"]) == ("first_publication", _ended(published[0], "cm-btc"))


@pytest.mark.parametrize(("third", "kind"), [(_newest_withdrawn, "retraction"), (_newest_restated, "restatement")])
def test_q3s_lower_end_for_a_held_day_passes_over_a_body_whose_newest_day_went_back(tmp_path, third, kind):
    """The third body's newest day goes back, an ok body whose absences are evidence: it shows the base's newest day
    absent past its range, which says nothing of the version the fourth body brings for that day. The lower end is the
    second body, the last to show the old value."""
    ticks = [{}, {}, {"mempool-hashrate": _mempool(_newest_back)}, {"mempool-hashrate": _mempool(third)}]
    published, (versions, coverage, _) = _record(tmp_path, ticks)
    assert [_fetch(tick, "mempool-hashrate")["check"]["outcome"] for tick in published] == [0, 0, 0, 0]
    assert _at(coverage, 2).filter(pl.col("source") == "mempool-hashrate")["evidence"].to_list() == [True]
    newest = max(parse_series(MEMPOOL, body("mempool-hashrate"))["mempool/avgHashrate"])
    (version,) = _day(versions, "mempool/avgHashrate", newest).filter(pl.col("position") == 3).iter_rows(named=True)
    assert version["kind"] == kind
    assert version["appeared_after"] == _ended(published[1], "mempool-hashrate")


def test_q3s_lower_end_is_null_for_a_day_before_every_earlier_observations_range(tmp_path):
    """A series' history extended backwards: no earlier observation's range reached the new day, so none is evidence
    that it was not yet held."""
    rows = _rows(body("cm-btc"))
    earlier = rows[_carrying(rows, GONE_METRIC)[0] - 1]
    earlier[GONE_METRIC] = "1.5"
    published, (versions, _, _) = _record(tmp_path, [{}, {"cm-btc": _stream(rows)}])
    assert _fetch(published[1], "cm-btc")["check"]["outcome"] == 0
    extended = _at(versions, 1)
    assert extended.select("series", "kind").rows() == [(f"cm/btc/{GONE_METRIC}", "backfill")]
    assert extended["ts"].item().date() == date.fromisoformat(earlier["time"][:10])
    assert extended["appeared_after"].to_list() == [None]


def test_a_change_of_time_format_keeps_every_key(tmp_path):
    _, (versions, _, _) = _record(tmp_path, [{}, {"cm-btc": _second("cm-btc-time-format")}])
    assert set(versions["position"]) == {0}


def test_a_token_beyond_2_53_survives(tmp_path):
    restated = _second("mempool-hashrate-restated-big")
    _, (versions, _, _) = _record(tmp_path, [{}, {"mempool-hashrate": restated}])
    before = loads_tokens(body("mempool-hashrate"))["hashrates"]
    after = loads_tokens(restated)["hashrates"]
    (changed,) = [row["avgHashrate"] for old, row in zip(before, after, strict=True) if old["avgHashrate"] != row["avgHashrate"]]
    assert int(changed) > 2**53
    (restatement,) = versions.filter(pl.col("kind") == "restatement").iter_rows(named=True)
    assert restatement["series"] == "mempool/avgHashrate"
    assert restatement["token"] == changed
    assert f'"avgHashrate":{changed}}}'.encode() in restated


def test_a_bg_day_leaving_the_window_is_no_retraction(tmp_path):
    rolled = _second("bg-sopr-rolled")
    _, (versions, _, _) = _record(tmp_path, [{}, {"bg-sopr": rolled}])
    dropped = loads_tokens(body("bg-sopr"))[0]["d"]
    assert dropped not in {row["d"] for row in loads_tokens(rolled)}
    assert versions.filter(pl.col("kind") == "retraction").is_empty()
    assert _at(versions, 1).select("series", "kind").rows() == [("bg/sopr", "first_publication")]


# Hand frames: one (S, D), each tick's fetch knowable at its `ended_at` (no Date), every coverage row holding D in a
# 10-day range.
HAND_T0 = datetime(2026, 11, 12, 0, 37, tzinfo=UTC)
MICROSECOND = timedelta(microseconds=1)


def _stamp(position: int) -> str:
    return f"202611{12 + position:02d}T003700Z"


def _hand_version(position: int, token: str, knowable: datetime) -> dict:
    return {
        "ts": datetime(2026, 11, 5, tzinfo=UTC),
        "provider": "coinmetrics",
        "source": "cm-btc",
        "series": "cm/btc/TxCnt",
        "kind": "inherited" if position == 0 else "restatement",
        "token": token,
        "tick": _stamp(position),
        "position": position,
        "ended_at": knowable,
        "knowable_at": knowable,
        "appeared_after": None,
        "outcome": 0,
        "flags": "",
    }


def _hand_coverage(position: int, knowable: datetime, *, evidence: bool = True, days: int = 10) -> dict:
    return {
        "ts": knowable - timedelta(minutes=1),
        "provider": "coinmetrics",
        "tick": _stamp(position),
        "position": position,
        "tick_json_sha256": "0" * 64,
        "source": "cm-btc",
        "series": "cm/btc/TxCnt",
        "outcome": 0 if evidence else 2,
        "reason": None if evidence else "TxCnt top",
        "ended_at": knowable,
        "knowable_at": knowable,
        "first_day": date(2026, 11, 1),
        "last_day": date(2026, 11, 10),
        "days": days,
        "evidence": evidence,
        "flags": "",
    }


def _link_error(about: int, taught_by: int, taught_at: datetime) -> dict:
    return {
        "tick": _stamp(about),
        "fact": "link-error",
        "taught_by": _stamp(taught_by),
        "taught_position": taught_by,
        "taught_at": taught_at,
    }


@pytest.mark.parametrize(
    ("second_evidence", "second_days", "seen"),
    [(False, 9, 0), (True, 9, 1), (False, 10, 1)],
    ids=["a-hole-and-no-evidence-skipped", "evidence-counts", "unbroken-days-count"],
)
def test_last_seen_reads_only_rows_known_to_have_held_the_day(second_evidence, second_days, seen):
    knowable = (HAND_T0 + HOUR, HAND_T0 + 4 * HOUR)
    coverage = [_hand_coverage(0, knowable[0]), _hand_coverage(1, knowable[1], evidence=second_evidence, days=second_days)]
    derived = frames([_hand_version(0, "7", knowable[0])], coverage, [])
    assert as_of(*derived, HAND_T0 + 24 * HOUR)["last_seen_at"].to_list() == [knowable[seen]]


@pytest.mark.parametrize("step", ["at-the-first", "between", "a-microsecond-before-the-second", "at-the-second"])
def test_last_seen_and_a_later_fact_wait_for_their_ticks_knowable_time(step):
    """Tick 1 holds the day again and teaches a fact about tick 0: neither shows before tick 1 is knowable."""
    knowable = (HAND_T0 + HOUR, HAND_T0 + 4 * HOUR)
    derived = frames(
        [_hand_version(0, "7", knowable[0])],
        [_hand_coverage(0, knowable[0]), _hand_coverage(1, knowable[1])],
        [_link_error(about=0, taught_by=1, taught_at=knowable[1])],
    )
    t = {
        "at-the-first": knowable[0],
        "between": knowable[0] + HOUR,
        "a-microsecond-before-the-second": knowable[1] - MICROSECOND,
        "at-the-second": knowable[1],
    }[step]
    seen = as_of(*derived, t).select("token", "last_seen_at", "flags").rows()
    assert seen == ([("7", knowable[1], "link-error")] if step == "at-the-second" else [("7", knowable[0], "")])


@pytest.mark.parametrize("step", ["a-microsecond-before", "at"])
def test_a_fact_from_a_tick_with_no_knowable_coverage_row_shows_from_its_ticks_knowable_time(step):
    """Tick 1 fetched no series, so it has no coverage row: its fact about tick 0 shows from tick 1's own knowable
    time, never before."""
    knowable = (HAND_T0 + HOUR, HAND_T0 + 4 * HOUR)
    derived = frames(
        [_hand_version(0, "7", knowable[0])],
        [_hand_coverage(0, knowable[0])],
        [_link_error(about=0, taught_by=1, taught_at=knowable[1])],
    )
    t = knowable[1] - MICROSECOND if step == "a-microsecond-before" else knowable[1]
    assert as_of(*derived, t)["flags"].to_list() == ["" if step == "a-microsecond-before" else "link-error"]


def test_a_fact_shows_from_its_teaching_ticks_server_date_when_that_runs_past_the_ticks_end(tmp_path):
    restated = _second("cm-btc-restatement")
    plan = [{}, {"cm-btc": restated}]
    probe = build_record(tmp_path / "probe", [(T0 + 3 * i * HOUR, replies) for i, replies in enumerate([*plan, plan[1]])])
    server = _after(probe[2]).replace(microsecond=0) + timedelta(seconds=5)
    served = Reply(200, restated, headers=[("Date", format_datetime(server, usegmt=True))])
    published = build_record(
        tmp_path / "real", [(T0 + 3 * i * HOUR, replies) for i, replies in enumerate([*plan, {"cm-btc": served}])]
    )
    assert _after(published[2]) == _after(probe[2]) < server
    entry = LinkAcknowledgment(published[2].stamp, "0" * 64, "0" * 64)
    derived = derive_record(tmp_path / "real" / "record", entries=(entry,))
    taught_at = server + timedelta(seconds=1)
    assert derived[2].rows(named=True) == [
        {
            "tick": published[1].stamp,
            "fact": "link-acknowledged",
            "taught_by": published[2].stamp,
            "taught_position": 2,
            "taught_at": taught_at,
        }
    ]
    (restatement,) = derived[0].filter(pl.col("kind") == "restatement").iter_rows(named=True)

    def flags_at(t: datetime) -> str:
        return _day(as_of(*derived, t), restatement["series"], restatement["ts"].date())["flags"].item()

    assert "link-acknowledged" not in flags_at(taught_at - MICROSECOND).split(",")
    assert "link-acknowledged" in flags_at(taught_at).split(",")


@pytest.mark.parametrize("step", ["at-the-third", "a-microsecond-before-the-second", "at-the-second"])
def test_last_seen_stops_at_the_next_version_across_a_clock_regression(step):
    """Tick 1 ran under a clock ahead, knowable after tick 2: until it is, tick 0's value stands, tick 2's row, which
    held tick 1's value, is no last-seen time for it, and tick 1's fact about tick 0 is not shown though a later
    position is knowable. Tick 2's fact about tick 1 shows with tick 1's value."""
    knowable = (HAND_T0 + HOUR, HAND_T0 + 24 * HOUR, HAND_T0 + 12 * HOUR)
    regression = {
        "tick": _stamp(1),
        "fact": "regression-predecessor",
        "taught_by": _stamp(2),
        "taught_position": 2,
        "taught_at": knowable[2],
    }
    derived = frames(
        [_hand_version(0, "7", knowable[0]), _hand_version(1, "8", knowable[1])],
        [_hand_coverage(position, at) for position, at in enumerate(knowable)],
        [_link_error(about=0, taught_by=1, taught_at=knowable[1]), regression],
    )
    t = {"at-the-third": knowable[2], "a-microsecond-before-the-second": knowable[1] - MICROSECOND, "at-the-second": knowable[1]}[
        step
    ]
    seen = as_of(*derived, t).select("token", "position", "last_seen_at", "flags").rows()
    if step == "at-the-second":
        assert seen == [("8", 1, knowable[2], "regression-predecessor")]
    else:
        assert seen == [("7", 0, knowable[0], "")]


def test_every_versions_token_is_its_ticks_body_token(tmp_path):
    published = standard_record(tmp_path)
    versions, _, _ = derive_record(tmp_path / "record")
    by_stamp = {tick.stamp: tick for tick in published}
    assert set(versions["kind"]) == {"inherited", "first_publication", "restatement", "retraction", "restoration"}
    parsed = {}
    for row in versions.iter_rows(named=True):
        key = (row["tick"], row["source"])
        if key not in parsed:
            parsed[key] = parse_series(SOURCE_BY_ID[row["source"]], _stored(by_stamp[row["tick"]], row["source"]))
        held = parsed[key].get(row["series"], {}).get(row["ts"].date())
        assert (row["token"] is None) == (row["kind"] == "retraction")
        assert row["token"] == held


def test_changed_values_counts_restatement_retraction_and_backfill_never_a_first_publication():
    def parsed(name: str) -> dict:
        return parse_series(CM_BTC, body(name))

    base = parsed("cm-btc")
    assert changed_values(base, parsed("second/cm-btc-restatement")) == 1
    assert changed_values(base, parsed("second/cm-btc-retraction")) == 1
    assert changed_values(parsed("second/cm-btc-gap"), base) == 1
    assert changed_values(base, parsed("second/cm-btc-next")) == 0
    assert changed_values(parsed("second/cm-btc-retraction"), base) == 1
    assert changed_values(base, parsed("second/cm-btc-metric-back-changed")) == 1


def test_the_status_companions_are_series_of_their_own():
    assert "cm/btc/FlowInExNtv-status" in parse_series(CM_BTC, body("cm-btc"))


def test_a_json_stream_body_parses_with_or_without_a_trailing_newline():
    base = body("cm-btc")
    lines = base.split(b"\n")
    blank = b"\n".join([*lines[:3], b"", *lines[3:]])
    assert parse_series(CM_BTC, base) == parse_series(CM_BTC, base + b"\n") == parse_series(CM_BTC, blank)


ENDED = datetime(2026, 11, 12, 0, 37, 30, tzinfo=UTC)


def _flags(*, offset: float | None = 0.0, synchronised: int = 1, age: float = 30.0, skew: int = 0) -> tuple[str, ...]:
    manifest = {"clock": {"offset_seconds": offset, "synchronised": synchronised, "prom_age_seconds": age, "error": None}}
    fetch = {
        "attempts": [{"ended_at": ENDED.strftime("%Y-%m-%dT%H:%M:%S.%fZ")}],
        "headers": [["Date", format_datetime(ENDED - timedelta(seconds=skew), usegmt=True)]],
    }
    return flags(manifest, fetch)


def test_the_flags(tmp_path):
    assert _flags(synchronised=0) == ("clock-unsynchronised",)
    assert _flags(offset=11) == ("clock-offset",)
    assert _flags(offset=-11) == ("clock-offset",)
    assert _flags(offset=None) == ("clock-offset",)
    assert _flags(age=601) == ("clock-file-stale",)
    assert _flags(skew=301) == ("date-skew",)
    assert _flags(offset=10, age=600, skew=300) == ()

    published = build_record(tmp_path, [(T0, {}), (T0 + 12 * HOUR, {}), (T0 + 11 * HOUR, {})])
    _, coverage, facts = derive_record(tmp_path / "record")
    regressed = coverage.with_columns(pl.col("flags").str.split(",").list.contains("stamp-regression").alias("regressed"))
    assert set(regressed.filter(pl.col("position") == 2)["regressed"]) == {True}
    assert set(regressed.filter(pl.col("position") < 2)["regressed"]) == {False}
    assert facts.rows(named=True) == [
        {
            "tick": published[1].stamp,
            "fact": "regression-predecessor",
            "taught_by": published[2].stamp,
            "taught_position": 2,
            "taught_at": _after(published[2]),
        }
    ]


def test_the_frames_carry_the_specs_columns_in_order():
    versions, coverage, facts = frames([], [], [])
    assert versions.columns == list(VERSIONS_SCHEMA) == [
        "ts", "provider", "source", "series", "kind", "token", "tick", "position",
        "ended_at", "knowable_at", "appeared_after", "outcome", "flags",
    ]  # fmt: skip
    assert coverage.columns == list(COVERAGE_SCHEMA) == [
        "ts", "provider", "tick", "position", "tick_json_sha256", "source", "series", "outcome", "reason",
        "ended_at", "knowable_at", "first_day", "last_day", "days", "evidence", "flags",
    ]  # fmt: skip
    assert facts.columns == list(LATER_FACTS_SCHEMA) == ["tick", "fact", "taught_by", "taught_position", "taught_at"]
    assert versions.schema["knowable_at"] == coverage.schema["knowable_at"] == pl.Datetime("us", "UTC")
