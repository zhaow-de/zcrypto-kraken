"""Tests for the journal contract (cli/engine/journal.py): the pinned content-hash byte layout,
None -> NaN encoding, to_json/from_json round-trip, and validate_record's schema + snapshot-
boundary (no-peek) invariant checks. No dataset access -- everything here is synthetic."""

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

# Computed independently (struct.pack("<q", epoch_seconds) per ts, then struct.pack("<d", ...) per
# close, NaN for None, sha256 of the two blocks concatenated) for two naive UTC bar-start stamps
# (2024-01-01T00:00Z = epoch 1704067200, 2024-01-01T04:00Z = epoch 1704081600) and closes
# [100.0, None] -- pinned so the byte layout can never silently change.
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
    # schema_version is a LITERAL 1, not the imported SCHEMA_VERSION (now 2 post spec 00094) --
    # this fixture's base-keyed pair/final_targets are a v1 shape, and schema-version-generic
    # tests below (snapshot-boundary, field-type checks, ...) must stay pinned to v1 regardless of
    # which schema is newest. See _valid_record_v2 for the symbol-keyed v2 counterpart.
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
    # 99 is not in _LOADABLE_SCHEMA_VERSIONS ({1, 2}) -- must be refused for THAT reason (match
    # pins the message), not incidentally via the schema-aware key check (2 is now a valid,
    # loadable version, so validate_record(_valid_record(schema_version=2)) would raise for the
    # wrong reason -- _valid_record's fixture stays base-keyed, which is a v1 shape).
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
    # cycle_ts is 08:00 (non-midnight); a daily last_ts of "today" (2026-07-10 00:00) instead of the
    # correct "yesterday" (2026-07-09 00:00) must be rejected -- guards against an off-by-one that
    # only shows up away from a midnight cycle.
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

# Captured with `to_json` from the code AS IT STOOD BEFORE schema 2 existed (SCHEMA_VERSION == 1,
# no _LOADABLE_SCHEMA_VERSIONS, no schema-aware key checks) -- a literal byte-for-byte snapshot of
# what a real v1 journal record on disk looks like. This is the compatibility pin: schema 2 must
# not change one byte of how a v1 record round-trips. Regenerating this string from current code
# would prove nothing about compatibility -- it must stay exactly as captured.
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
    # The compatibility pin itself: parse the golden, re-serialize, and the bytes must be identical
    # to what was captured pre-schema-2 -- a real v1 record on disk must still load and re-emit
    # exactly the same JSON post-change.
    restored = from_json(_V1_GOLDEN_JSON)
    assert to_json(restored) == _V1_GOLDEN_JSON
    validate_record(restored)  # a real v1 record must still validate post-change


def test_v1_golden_hash_stability():
    # snapshot_content_hash is untouched by schema 2 (no record-level hash exists) -- recomputing
    # from the golden's raw (ts, closes) inputs must still reproduce the exact hashes embedded in
    # the golden JSON, proving the byte layout has not silently shifted.
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
