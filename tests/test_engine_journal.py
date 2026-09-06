"""The journal record contract (cli/engine/journal.py): its pinned content-hash byte layout, schema
validation, and the snapshot-boundary (no-peek) invariant."""

import json
from datetime import datetime, timedelta

import pytest

from cli.engine import (
    SCHEMA_VERSION,
    CycleRecord,
    EngineJournalError,
    SnapshotEntry,
    from_json,
    snapshot_content_hash,
    to_json,
    validate_record,
)

# --- snapshot_content_hash: the pinned byte layout ----------------------------------------------

# Computed independently of the code under test -- struct.pack("<q", epoch_seconds) per ts,
# struct.pack("<d", close) per close with NaN for None, sha256 of the two blocks concatenated.
_EXPECTED_HASH = "fb5c564f0ff9ba2201efcf6fc4ca8585a33349424d9dbd7364b4526f40698557"


def test_snapshot_content_hash_pinned_layout():
    ts = [datetime(2024, 1, 1, 0, 0), datetime(2024, 1, 1, 4, 0)]
    closes = [100.0, None]
    assert snapshot_content_hash(ts, closes) == _EXPECTED_HASH


def test_snapshot_content_hash_none_is_not_zero():
    # None must encode as NaN, not 0.0 -- a silent "treat missing as zero" bug would collide here.
    ts = [datetime(2024, 1, 1, 0, 0), datetime(2024, 1, 1, 4, 0)]
    assert snapshot_content_hash(ts, [100.0, None]) != snapshot_content_hash(ts, [100.0, 0.0])


def test_snapshot_content_hash_deterministic():
    ts = [datetime(2024, 1, 1, 0, 0), datetime(2024, 1, 1, 4, 0), datetime(2024, 1, 1, 8, 0)]
    closes = [100.0, 101.5, None]
    assert snapshot_content_hash(ts, closes) == snapshot_content_hash(list(ts), list(closes))
    assert len(snapshot_content_hash(ts, closes)) == 64


def test_snapshot_content_hash_length_mismatch():
    with pytest.raises(EngineJournalError):
        snapshot_content_hash([datetime(2024, 1, 1)], [1.0, 2.0])


# --- fixtures: a valid record satisfying the snapshot-boundary invariant at a non-midnight cycle -


def _entry(pair: str, grid: str, first_ts: datetime, last_ts: datetime) -> SnapshotEntry:
    return SnapshotEntry(
        pair=pair,
        grid=grid,
        n_bars=3,
        first_ts=first_ts,
        last_ts=last_ts,
        content_hash="a" * 64,
        path=f"/snap/{pair}/{grid}.parquet",
    )


# cycle_ts 08:00 (non-midnight): last 4h stamp == 04:00 (cycle_ts - 4h); last daily stamp ==
# (last midnight <= 08:00 == 2026-07-10 00:00) - 1 day == 2026-07-09 00:00.
CYCLE_TS = datetime(2026, 7, 10, 8, 0)
VALID_H4_LAST = datetime(2026, 7, 10, 4, 0)
VALID_DAILY_LAST = datetime(2026, 7, 9, 0, 0)


def _valid_record(**overrides) -> CycleRecord:
    # schema_version is a LITERAL 1, not the imported SCHEMA_VERSION: this fixture's base-keyed
    # pair/final_targets are a v1 shape, and the tests below must stay pinned to v1 as schemas advance.
    snapshots = overrides.pop(
        "snapshots",
        (
            _entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST),
            _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST),
        ),
    )
    fields = {
        "schema_version": 1,
        "cycle_ts": CYCLE_TS,
        "snapshots": snapshots,
        "final_targets": {"BTC": 0.1},
        "started_at": CYCLE_TS,
        "completed_at": CYCLE_TS + timedelta(minutes=5),
        "code_version": "0.1.0+fast",
        "builder_path": "fast",
    }
    fields.update(overrides)
    return CycleRecord(**fields)


def test_valid_record_passes():
    validate_record(_valid_record())  # no raise


def test_valid_record_at_midnight_cycle():
    # The other branch of "last midnight <= cycle_ts": when cycle_ts itself IS midnight, last
    # midnight <= cycle_ts is cycle_ts itself, so the daily stamp is cycle_ts - 1 day (not cycle_ts).
    midnight = datetime(2026, 7, 10, 0, 0)
    record = _valid_record(
        cycle_ts=midnight,
        snapshots=(
            _entry("BTC", "240", datetime(2026, 7, 9, 12, 0), midnight - timedelta(hours=4)),
            _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), datetime(2026, 7, 9, 0, 0)),
        ),
        started_at=midnight,
        completed_at=midnight + timedelta(minutes=5),
    )
    validate_record(record)  # no raise


# --- schema violations ----------------------------------------------------------------------


def test_wrong_schema_version():
    # 99 is outside _LOADABLE_SCHEMA_VERSIONS, so the refusal is for THAT reason (the match pins the
    # message): 2 is loadable, and would instead raise on this base-keyed fixture's v1 shape.
    with pytest.raises(EngineJournalError, match="unsupported schema_version"):
        validate_record(_valid_record(schema_version=99))


def test_cycle_ts_not_datetime():
    with pytest.raises(EngineJournalError):
        validate_record(_valid_record(cycle_ts="2026-07-10T08:00:00"))


@pytest.mark.parametrize("snapshots", [(), "not a tuple", ["not", "a", "tuple"]])
def test_snapshots_must_be_nonempty_tuple(snapshots):
    with pytest.raises(EngineJournalError):
        validate_record(_valid_record(snapshots=snapshots))


def test_snapshot_missing_daily_grid():
    with pytest.raises(EngineJournalError):
        validate_record(_valid_record(snapshots=(_entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST),)))


def test_snapshot_duplicate_grid():
    with pytest.raises(EngineJournalError):
        validate_record(
            _valid_record(
                snapshots=(
                    _entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST),
                    _entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST),
                    _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST),
                )
            )
        )


@pytest.mark.parametrize(
    "bad_entry",
    [
        _entry("", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST),  # empty pair
        SnapshotEntry("BTC", "60", 3, datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "a" * 64, "p"),  # bad grid
        SnapshotEntry("BTC", "240", 0, datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "a" * 64, "p"),  # n_bars < 1
        SnapshotEntry("BTC", "240", 3, VALID_H4_LAST, VALID_H4_LAST, "a" * 64, "p"),  # first_ts == last_ts
        SnapshotEntry("BTC", "240", 3, datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "tooshort", "p"),  # bad hash len
        SnapshotEntry("BTC", "240", 3, datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "a" * 64, ""),  # empty path
    ],
)
def test_snapshot_field_violations(bad_entry):
    with pytest.raises(EngineJournalError):
        validate_record(_valid_record(snapshots=(bad_entry, _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST))))


@pytest.mark.parametrize(
    "final_targets",
    [{}, "not a dict", {"": 0.1}, {"BTC": float("nan")}, {"BTC": float("inf")}, {"BTC": True}, {"BTC": "0.1"}],
)
def test_final_targets_violations(final_targets):
    with pytest.raises(EngineJournalError):
        validate_record(_valid_record(final_targets=final_targets))


def test_completed_before_started():
    with pytest.raises(EngineJournalError):
        validate_record(_valid_record(started_at=CYCLE_TS, completed_at=CYCLE_TS - timedelta(minutes=1)))


@pytest.mark.parametrize("code_version", ["", 123, None])
def test_code_version_violations(code_version):
    with pytest.raises(EngineJournalError):
        validate_record(_valid_record(code_version=code_version))


@pytest.mark.parametrize("builder_path", ["", "quick", "FAST"])
def test_builder_path_violations(builder_path):
    with pytest.raises(EngineJournalError):
        validate_record(_valid_record(builder_path=builder_path))


# --- the snapshot-boundary (no-peek) invariant --------------------------------------------------


def test_h4_boundary_violation():
    bad = _entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST - timedelta(hours=4))
    with pytest.raises(EngineJournalError):
        validate_record(_valid_record(snapshots=(bad, _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST))))


def test_daily_boundary_violation_at_non_midnight_cycle():
    # A daily last_ts of "today" instead of the correct "yesterday" is the off-by-one that only
    # shows up away from a midnight cycle.
    bad_daily = _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), datetime(2026, 7, 10, 0, 0))
    with pytest.raises(EngineJournalError):
        validate_record(_valid_record(snapshots=(_entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST), bad_daily)))


# --- to_json / from_json round-trip --------------------------------------------------------------


def test_json_round_trip():
    record = _valid_record()
    restored = from_json(to_json(record))
    assert restored == record


def test_json_round_trip_multi_pair_multi_asset():
    snapshots = (
        _entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST),
        _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST),
        _entry("ETH", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST),
        _entry("ETH", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST),
    )
    record = _valid_record(snapshots=snapshots, final_targets={"BTC": 0.1, "ETH": -0.05})
    restored = from_json(to_json(record))
    assert restored == record
    validate_record(restored)


def test_from_json_malformed():
    with pytest.raises(EngineJournalError):
        from_json("not json")


def test_from_json_missing_key():
    with pytest.raises(EngineJournalError):
        from_json('{"schema_version": 1}')


# --- schema 2 (spec 00094): the v1 golden compatibility pin --------------------------------------

# Captured with `to_json` from the code as it stood BEFORE schema 2 existed -- a real v1 record on
# disk, byte for byte. Regenerating it from current code would prove nothing about compatibility:
# it must stay exactly as captured.
_V1_GOLDEN_JSON = (
    '{"builder_path": "fast", "code_version": "1.4.2+fast", "completed_at": "2026-07-10T08:03:12", '
    '"cycle_ts": "2026-07-10T08:00:00", "final_targets": {"BTC": 0.1373, "ETH": -0.0621}, "schema_version": 1, '
    '"snapshots": [{"content_hash": "c1c1132ceec88bc8f14ea18070aff5d80e9f2a6a3019840ce021e7dc6379fa3d", '
    '"first_ts": "2026-07-09T20:00:00", "grid": "240", "last_ts": "2026-07-10T04:00:00", "n_bars": 3, "pair": "BTC", '
    '"path": "2026-07-10/snapshots/cycle-08/BTC-240.parquet"}, '
    '{"content_hash": "4d6df27cceb88b722664c7dea214817284a5f051d196b3320643965920b79374", '
    '"first_ts": "2026-07-06T00:00:00", "grid": "1440", "last_ts": "2026-07-09T00:00:00", "n_bars": 4, "pair": "BTC", '
    '"path": "2026-07-10/snapshots/cycle-08/BTC-1440.parquet"}, '
    '{"content_hash": "af9e732daa317f02170116cd8d0e4a1ceeaea65a2e678878f73f357f65c0a33b", '
    '"first_ts": "2026-07-09T20:00:00", "grid": "240", "last_ts": "2026-07-10T04:00:00", "n_bars": 3, "pair": "ETH", '
    '"path": "2026-07-10/snapshots/cycle-08/ETH-240.parquet"}, '
    '{"content_hash": "05dafb9cdb865a60fa168efa3dc89089be3bee34f1b19b571155a05d79402a55", '
    '"first_ts": "2026-07-06T00:00:00", "grid": "1440", "last_ts": "2026-07-09T00:00:00", "n_bars": 4, "pair": "ETH", '
    '"path": "2026-07-10/snapshots/cycle-08/ETH-1440.parquet"}], "started_at": "2026-07-10T08:01:35"}'
)

# The raw (ts, closes) inputs that produced each golden snapshot's content_hash, so the hash-
# stability test recomputes from source rather than re-reading the pinned string back at itself.
_GOLDEN_BTC_240_TS = [datetime(2026, 7, 9, 20, 0), datetime(2026, 7, 10, 0, 0), datetime(2026, 7, 10, 4, 0)]
_GOLDEN_BTC_240_CLOSES = [41000.123, 41001.123, 41002.123]
_GOLDEN_BTC_1440_TS = [
    datetime(2026, 7, 6, 0, 0),
    datetime(2026, 7, 7, 0, 0),
    datetime(2026, 7, 8, 0, 0),
    datetime(2026, 7, 9, 0, 0),
]
_GOLDEN_BTC_1440_CLOSES = [40500.5, 40501.5, None, 40503.5]
_GOLDEN_ETH_240_TS = _GOLDEN_BTC_240_TS
_GOLDEN_ETH_240_CLOSES = [2200.75, 2201.75, 2202.75]
_GOLDEN_ETH_1440_TS = _GOLDEN_BTC_1440_TS
_GOLDEN_ETH_1440_CLOSES = [2100.25, 2101.25, None, 2103.25]


def test_v1_golden_round_trips_byte_identically():
    restored = from_json(_V1_GOLDEN_JSON)
    assert to_json(restored) == _V1_GOLDEN_JSON
    validate_record(restored)  # a real v1 record must still validate post-change


def test_v1_golden_hash_stability():
    assert (
        snapshot_content_hash(_GOLDEN_BTC_240_TS, _GOLDEN_BTC_240_CLOSES)
        == "c1c1132ceec88bc8f14ea18070aff5d80e9f2a6a3019840ce021e7dc6379fa3d"
    )
    assert (
        snapshot_content_hash(_GOLDEN_BTC_1440_TS, _GOLDEN_BTC_1440_CLOSES)
        == "4d6df27cceb88b722664c7dea214817284a5f051d196b3320643965920b79374"
    )
    assert (
        snapshot_content_hash(_GOLDEN_ETH_240_TS, _GOLDEN_ETH_240_CLOSES)
        == "af9e732daa317f02170116cd8d0e4a1ceeaea65a2e678878f73f357f65c0a33b"
    )
    assert (
        snapshot_content_hash(_GOLDEN_ETH_1440_TS, _GOLDEN_ETH_1440_CLOSES)
        == "05dafb9cdb865a60fa168efa3dc89089be3bee34f1b19b571155a05d79402a55"
    )


# --- schema 2: symbol-keyed final_targets and snapshot pairs -------------------------------------


def _valid_record_v2(**overrides) -> CycleRecord:
    snapshots = overrides.pop(
        "snapshots",
        (
            _entry("BTC/EUR", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST),
            _entry("BTC/EUR", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST),
        ),
    )
    fields = {
        "schema_version": SCHEMA_VERSION,
        "cycle_ts": CYCLE_TS,
        "snapshots": snapshots,
        "final_targets": {"BTC/EUR": 0.1},
        "started_at": CYCLE_TS,
        "completed_at": CYCLE_TS + timedelta(minutes=5),
        "code_version": "0.1.0+fast",
        "builder_path": "fast",
    }
    fields.update(overrides)
    return CycleRecord(**fields)


def test_v2_valid_record_passes():
    validate_record(_valid_record_v2())  # no raise


def test_v2_json_round_trip():
    snapshots = (
        _entry("BTC/EUR", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST),
        _entry("BTC/EUR", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST),
        _entry("ETH/BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST),
        _entry("ETH/BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST),
    )
    record = _valid_record_v2(snapshots=snapshots, final_targets={"BTC/EUR": 0.1, "ETH/BTC": 0.0})
    restored = from_json(to_json(record))
    assert restored == record
    validate_record(restored)


def test_v2_final_targets_base_key_refused():
    # Only final_targets is wrong (snapshots stay v2-valid) -- isolates the final_targets check.
    record = _valid_record_v2(final_targets={"BTC/EUR": 0.1, "ETH": -0.05})
    with pytest.raises(EngineJournalError, match="final_targets"):
        validate_record(record)


def test_v2_snapshot_pair_base_key_refused():
    # Only the snapshot pair is wrong (final_targets stays v2-valid) -- isolates the pair check.
    record = _valid_record_v2(
        snapshots=(
            _entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST),
            _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST),
        )
    )
    with pytest.raises(EngineJournalError, match="snapshot pair"):
        validate_record(record)


def test_v1_final_targets_symbol_key_refused():
    # Only final_targets is wrong (snapshots stay v1-valid) -- isolates the final_targets check.
    record = _valid_record(final_targets={"BTC/EUR": 0.1})
    with pytest.raises(EngineJournalError, match="final_targets"):
        validate_record(record)


def test_v1_snapshot_pair_symbol_key_refused():
    # Only the snapshot pair is wrong (final_targets stays v1-valid) -- isolates the pair check.
    record = _valid_record(
        snapshots=(
            _entry("BTC/EUR", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST),
            _entry("BTC/EUR", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST),
        )
    )
    with pytest.raises(EngineJournalError, match="snapshot pair"):
        validate_record(record)


# --- closes: the forming row's 4h close per model base -------------------------------------------

# closes is BASE-keyed over the /EUR legs the model sees; final_targets is SYMBOL-keyed over the
# basket. The two key spaces sit side by side in one record and never merge.
_EUR_BASES = ("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP")
_BASKET_TARGETS = {f"{base}/EUR": 0.05 for base in _EUR_BASES} | {"ETH/BTC": 0.0, "SOL/BTC": 0.0}


def _ten_eur_closes() -> dict[str, float]:
    return {base: 100.0 * (i + 1) for i, base in enumerate(_EUR_BASES)}


def _record(**overrides) -> CycleRecord:
    """A v2 record carrying the full basket in final_targets -- the shape run_cycle writes."""
    fields = {"final_targets": dict(_BASKET_TARGETS)}
    fields.update(overrides)
    return _valid_record_v2(**fields)


def test_the_record_round_trips_its_closes():
    rec = _record(closes={"BTC": 50000.0, "ETH": 3000.0})
    assert from_json(to_json(rec)).closes == {"BTC": 50000.0, "ETH": 3000.0}


def test_closes_are_base_keyed_ten_and_positive():
    art = json.loads(to_json(_record(closes=_ten_eur_closes())))
    assert set(art["closes"]) == {s.split("/")[0] for s in art["final_targets"] if s.endswith("/EUR")}
    assert "BTC" in art["closes"] and "BTC/EUR" not in art["closes"]
    assert all(isinstance(v, float) and v > 0 for v in art["closes"].values())
    validate_record(_record(closes=_ten_eur_closes()))  # and the production shape validates


def test_an_artifact_without_closes_still_loads():
    # A reader that raised on a record written before the key existed would take the tracking report
    # down over its own upgrade -- this IS the readers-before-writer guarantee.
    payload = json.loads(to_json(_record(closes=_ten_eur_closes())))
    del payload["closes"]
    assert from_json(json.dumps(payload)).closes is None


@pytest.mark.parametrize("corrupt", [[1, 2, 3], 50000.0, "BTC", True])
def test_a_corrupt_closes_is_refused_at_load_not_left_to_validate_record(corrupt):
    # from_json's callers do not all call validate_record (the soak/report loaders read a record
    # straight off disk), so a truncated artifact whose closes is a list or a scalar must fail HERE.
    payload = json.loads(to_json(_record(closes=_ten_eur_closes())))
    payload["closes"] = corrupt
    with pytest.raises(EngineJournalError):
        from_json(json.dumps(payload))


def test_a_record_without_closes_still_validates():
    validate_record(_record())  # absence is legal; every record written before this key existed


def test_to_json_omits_closes_when_absent():
    # Omission, not '"closes": null' -- a record that predates the key must re-serialize
    # byte-identically (test_v1_golden_round_trips_byte_identically is that pin), and an
    # absent-vs-null distinction would be a second dialect for every reader to carry.
    assert "closes" not in json.loads(to_json(_record()))


def test_validate_record_refuses_a_pair_keyed_closes():
    # validate_record takes a CycleRecord, not a payload dict -- construct it directly.
    with pytest.raises(EngineJournalError, match="closes"):
        validate_record(_record(closes={"BTC/EUR": 50000.0}))


def test_nav_and_held_round_trip():
    r = _record(nav=100000.0, held={"BTC": 0.5, "ETH": -2.0})
    back = from_json(to_json(r))
    assert back.nav == 100000.0
    assert back.held == {"BTC": 0.5, "ETH": -2.0}


def test_to_json_omits_nav_and_held_when_absent():
    # Same contract closes established: omission, never '"nav": null'.
    payload = json.loads(to_json(_record()))
    assert "nav" not in payload
    assert "held" not in payload


def test_a_record_without_nav_or_held_still_validates():
    validate_record(_record())  # every artifact written before the keys existed


def test_validate_record_refuses_a_non_positive_nav():
    # NAV sets BOTH halves of drift -- a target is `weight * nav / close` and the drift divides by
    # nav -- so a zero divides by zero and a negative signs every reading.
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(EngineJournalError, match="nav"):
            validate_record(_record(nav=bad))


def test_from_json_type_guards_nav_at_read_time():
    """`nav` is guarded at READ time like `closes` and `held`: `True` is an `int`, `isfinite(True)`
    is True and it is > 0, so a corrupted `"nav": true` would clear every downstream check and score
    the cycle at NAV=1."""
    payload = json.loads(to_json(_record(nav=1000.0)))
    for bad in (True, "1000", [1000]):
        payload["nav"] = bad
        with pytest.raises(EngineJournalError, match="nav"):
            from_json(json.dumps(payload))


def test_validate_record_refuses_a_pair_keyed_held():
    # held is SIGNED BASE UNITS in the model's key space, exactly like closes.
    with pytest.raises(EngineJournalError, match="held"):
        validate_record(_record(held={"BTC/EUR": 0.5}))


def test_held_admits_zero_and_negative_but_not_a_non_number():
    validate_record(_record(held={"BTC": 0.0, "ETH": -2.0}))  # flat and short are both real books
    with pytest.raises(EngineJournalError, match="held"):
        validate_record(_record(held={"BTC": "0.5"}))


def test_evidence_fingerprint_ignores_nav_and_held():
    # Deliberate, and the same reasoning that excludes `closes`: the fingerprint covers what a
    # REPLAY verdict depends on, and these are drift-scoring inputs a replay never reads. Pinned so
    # a future widening does not quietly fold them in and invalidate every cached verdict.
    from cli.engine.gate_cache import evidence_fingerprint

    base = _record()
    assert evidence_fingerprint(base) == evidence_fingerprint(_record(nav=1.0, held={"BTC": 9.0}))


def test_v1_closes_stay_base_keyed_too():
    # The base keying is NOT schema-conditional: the model's key space never widened, so a v1
    # record's closes are refused for a symbol key on exactly the same terms as a v2's.
    with pytest.raises(EngineJournalError, match="closes"):
        validate_record(_valid_record(closes={"BTC/EUR": 50000.0}))


@pytest.mark.parametrize(
    "closes",
    [
        {},  # present-but-empty is a writer bug, not "no closes" -- that is None
        "not a dict",
        {"": 50000.0},
        {"BTC": 0.0},  # a zero close divides in the drift arithmetic downstream
        {"BTC": -1.0},
        {"BTC": float("nan")},
        {"BTC": float("inf")},
        {"BTC": True},
        {"BTC": "50000.0"},
    ],
)
def test_closes_violations(closes):
    with pytest.raises(EngineJournalError, match="closes"):
        validate_record(_record(closes=closes))
