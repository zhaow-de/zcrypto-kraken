"""The capturing loader: identity is what the run read (spec 00086 D1/D2)."""

import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

import pytest

from cli.data.rolling import ROLLING_SET
from cli.ohlc.dataset import to_frame, write_parquet
from cli.registry.errors import RegistryError
from cli.registry.observed import ObservedReader
from tests.rolling_fixtures import write_chain
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data


def _rows(n, start=1577836800):  # 2020-01-01, daily steps
    return [[start + i * 86400, "1", "2", "0.5", "1.5", "1.2", "10", 3] for i in range(n)]


def _dataset(tmp_path, name="ohlc-test", series=(("BTC/EUR/1440.parquet", 10), ("ETH/EUR/1440.parquet", 7))):
    root = tmp_path / "data"
    for relpath, n in series:
        write_parquet(to_frame(_rows(n)), root / name / relpath)
    return root


def test_block_records_files_rows_span_from_what_was_read(tmp_path):
    root = _dataset(tmp_path)
    reader = ObservedReader(root)
    reader.read_series("ohlc-test", "BTC/EUR/1440.parquet")
    reader.read_series("ohlc-test", "ETH/EUR/1440.parquet")
    block = reader.block()
    entry = block["ohlc-test"]
    assert set(entry) == {"files", "rows", "span"}
    assert set(entry["files"]) == {"BTC/EUR/1440.parquet", "ETH/EUR/1440.parquet"}
    raw = (root / "ohlc-test" / "BTC/EUR/1440.parquet").read_bytes()
    assert entry["files"]["BTC/EUR/1440.parquet"] == hashlib.sha256(raw).hexdigest()
    assert entry["rows"] == 17
    assert entry["span"][0] == "2020-01-01 00:00:00+00:00"


def test_a_flipped_byte_moves_the_hash(tmp_path):
    root = _dataset(tmp_path)
    before = ObservedReader(root)
    before.read_series("ohlc-test", "BTC/EUR/1440.parquet")
    p = root / "ohlc-test" / "BTC/EUR/1440.parquet"
    raw = bytearray(p.read_bytes())
    raw[len(raw) // 2] ^= 0x01
    p.write_bytes(bytes(raw))
    after = ObservedReader(root)
    try:  # the flip may or may not still parse as parquet; the hash is taken from bytes either way
        after.read_series("ohlc-test", "BTC/EUR/1440.parquet")
    except Exception:
        return  # an unreadable flip is also a detected change — the read refused
    # OUTSIDE the try: an except that swallows AssertionError makes a test that can never fail.
    assert after.block()["ohlc-test"]["files"] != before.block()["ohlc-test"]["files"]


def test_window_moves_rows_and_span_and_is_applied_by_the_loader(tmp_path):
    root = _dataset(tmp_path, series=(("BTC/EUR/1440.parquet", 10),))
    reader = ObservedReader(root)
    frame = reader.read_series(
        "ohlc-test", "BTC/EUR/1440.parquet", window=("2020-01-03 00:00:00+00:00", "2020-01-05 00:00:00+00:00")
    )
    assert frame.height == 3
    entry = reader.block()["ohlc-test"]
    assert entry["rows"] == 3
    assert entry["span"] == ["2020-01-03 00:00:00+00:00", "2020-01-05 00:00:00+00:00"]


def test_same_file_read_twice_is_one_entry_and_a_window_mismatch_is_refused(tmp_path):
    root = _dataset(tmp_path, series=(("BTC/EUR/1440.parquet", 10),))
    reader = ObservedReader(root)
    reader.read_series("ohlc-test", "BTC/EUR/1440.parquet")
    reader.read_series("ohlc-test", "BTC/EUR/1440.parquet")
    assert reader.block()["ohlc-test"]["rows"] == 10  # not 20 — one read, one entry
    with pytest.raises(RegistryError, match="window"):
        reader.read_series("ohlc-test", "BTC/EUR/1440.parquet", window=("2020-01-03 00:00:00+00:00", "2020-01-05 00:00:00+00:00"))


@pytest.mark.parametrize(
    "bad, match",
    [
        (("2020-01-03", "2020-01-05"), "no timezone"),  # valid ISO-8601, and the natural spelling
        (("garbage", "2020-01-05 00:00:00+00:00"), "not an ISO-8601 timestamp"),
    ],
)
def test_an_unusable_window_is_refused_typed(tmp_path, bad, match):
    """Naive bounds are the trap: polars raises SchemaError comparing tz-aware `ts` against a naive
    literal, so without this the paved door dies with a traceback on its most natural spelling."""
    root = _dataset(tmp_path, series=(("BTC/EUR/1440.parquet", 10),))
    with pytest.raises(RegistryError, match=match) as excinfo:
        ObservedReader(root).read_series("ohlc-test", "BTC/EUR/1440.parquet", window=bad)

    # Advice that does not work is worse than none: every quoted example must itself parse tz-aware.
    for example in re.findall(r"e\.g\. '([^']+)'", str(excinfo.value)):
        assert datetime.fromisoformat(example).tzinfo is not None, f"the refusal suggests {example!r}, which is still naive"


def test_empty_accumulation_and_zero_row_dataset_are_refused(tmp_path):
    root = _dataset(tmp_path, series=(("BTC/EUR/1440.parquet", 10),))
    with pytest.raises(RegistryError, match="accumulated nothing"):
        ObservedReader(root).block()
    reader = ObservedReader(root)
    with pytest.raises(RegistryError, match="zero rows"):
        reader.read_series("ohlc-test", "BTC/EUR/1440.parquet", window=("2031-01-01 00:00:00+00:00", "2031-01-02 00:00:00+00:00"))


def test_vouched_check_true_positive_mismatch_and_absence(tmp_path):
    from cli.ohlc.dataset import dataset_hash as content_hash
    from cli.ohlc.dataset import read_parquet

    root = _dataset(tmp_path)
    # No manifest at all -> inert, and the reader says so.
    reader = ObservedReader(root)
    reader.read_series("ohlc-test", "BTC/EUR/1440.parquet")
    assert reader.vouched_status()["ohlc-test"] == "inert (0 vouched hashes)"
    # TRUE POSITIVE: the frozen manifests vouch FRAME-CONTENT hashes, not file-byte ones, so a
    # manifest naming the correct content hash MUST pass -- a mismatch-only suite would ship a guard
    # that refuses every healthy read of ohlc-full/ohlc-15m while CI stays green.
    good = content_hash(read_parquet(root / "ohlc-test" / "BTC/EUR/1440.parquet"))
    (root / "ohlc-test" / "manifest.json").write_text(json.dumps({"series": {"BTC": {"sha256": good}}}))
    reader2 = ObservedReader(root)
    reader2.read_series("ohlc-test", "BTC/EUR/1440.parquet")  # healthy read passes
    assert reader2.vouched_status()["ohlc-test"] == "checked (1 vouched hashes)"
    # A manifest vouching a DIFFERENT hash -> the data changed since the freeze: refuse.
    (root / "ohlc-test" / "manifest.json").write_text(json.dumps({"series": {"X": {"sha256": "f" * 64}}}))
    reader3 = ObservedReader(root)
    with pytest.raises(RegistryError, match="vouched"):
        reader3.read_series("ohlc-test", "BTC/EUR/1440.parquet")


_AS_OF = "2026-10-03"


def _rolling(tmp_path, **chain) -> Path:
    root = tmp_path / "data"
    write_chain(root / ROLLING_SET, **chain)
    return root


def test_a_second_as_of_on_one_rolling_set_is_refused(tmp_path):
    reader = ObservedReader(_rolling(tmp_path))
    reader.read_rolling(ROLLING_SET, "BTC/EUR", 1440, "2026-10-02")

    with pytest.raises(RegistryError, match="already read as of 2026-10-02"):
        reader.read_rolling(ROLLING_SET, "BTC/EUR", 1440, _AS_OF)

    assert reader.block()[ROLLING_SET]["files"].keys() == {"index/2026/10/02.json"}


def test_a_rolling_read_honours_the_window_in_rows_and_span(tmp_path):
    reader = ObservedReader(_rolling(tmp_path))

    frame = reader.read_rolling(
        ROLLING_SET, "BTC/EUR", 15, _AS_OF, window=("2026-09-30 12:00:00+00:00", "2026-10-01 11:45:00+00:00")
    )

    assert frame.height == 96
    entry = reader.block()[ROLLING_SET]
    assert entry["rows"] == 96
    assert entry["span"] == ["2026-09-30 12:00:00+00:00", "2026-10-01 11:45:00+00:00"]


def test_an_accepted_rolling_hole_is_listed_by_pair_and_day(tmp_path):
    root = _rolling(tmp_path, holes={date(2026, 10, 2): {"BTC/EUR"}})
    with pytest.raises(RegistryError, match="BTC/EUR has a hole on 2026-10-02"):
        ObservedReader(root).read_rolling(ROLLING_SET, "BTC/EUR", 1440, _AS_OF)

    reader = ObservedReader(root)
    reader.read_rolling(ROLLING_SET, "BTC/EUR", 1440, _AS_OF, accept_holes=True)
    reader.read_rolling(ROLLING_SET, "BTC/EUR", 240, _AS_OF, accept_holes=True)
    reader.read_rolling(ROLLING_SET, "ETH/BTC", 1440, _AS_OF, accept_holes=True)

    assert reader.holes() == {ROLLING_SET: ["BTC/EUR 2026-10-02"]}


def test_a_rolling_dataset_reads_as_chained_not_inert(tmp_path):
    root = _rolling(tmp_path)
    reader = ObservedReader(root)
    reader.read_rolling(ROLLING_SET, "BTC/EUR", 1440, _AS_OF)
    digest = hashlib.sha256((root / ROLLING_SET / "index/2026/10/03.json").read_bytes()).hexdigest()

    assert reader.vouched_status() == {ROLLING_SET: f"chained (as of 2026-10-03, line {digest[:12]})"}


def test_rolling_reads_of_two_pairs_at_two_grids_accumulate_rows_and_span(tmp_path):
    reader = ObservedReader(_rolling(tmp_path))
    late = ("2026-10-02 00:00:00+00:00", "2026-10-03 23:45:00+00:00")
    reads = (("BTC/EUR", 1440, None), ("BTC/EUR", 240, late), ("ETH/BTC", 1440, None), ("ETH/BTC", 240, late))

    heights = [reader.read_rolling(ROLLING_SET, pair, grid, _AS_OF, window=window).height for pair, grid, window in reads]

    assert heights == [4, 12, 4, 12]
    expected = (32, ["2026-09-30 00:00:00+00:00", "2026-10-03 20:00:00+00:00"])
    entry = reader.block()[ROLLING_SET]
    assert (entry["rows"], entry["span"]) == expected
    reader.read_rolling(ROLLING_SET, "BTC/EUR", 240, _AS_OF, window=late)
    entry = reader.block()[ROLLING_SET]
    assert (entry["rows"], entry["span"]) == expected
    with pytest.raises(RegistryError, match="already read with window"):
        reader.read_rolling(ROLLING_SET, "BTC/EUR", 240, _AS_OF)


def test_a_series_read_of_a_rolling_dataset_is_refused(tmp_path):
    root = _rolling(tmp_path)
    rolling_first = ObservedReader(root)
    rolling_first.read_rolling(ROLLING_SET, "BTC/EUR", 1440, _AS_OF)
    with pytest.raises(RegistryError, match="reads one dataset one way"):
        rolling_first.read_series(ROLLING_SET, "base/BTC/EUR/15.parquet")

    series_first = ObservedReader(root)
    series_first.read_series(ROLLING_SET, "base/BTC/EUR/15.parquet")
    with pytest.raises(RegistryError, match="reads one dataset one way"):
        series_first.read_rolling(ROLLING_SET, "BTC/EUR", 1440, _AS_OF)


def test_a_rolling_read_of_zero_rows_is_refused(tmp_path):
    reader = ObservedReader(_rolling(tmp_path))

    with pytest.raises(RegistryError, match="zero rows"):
        reader.read_rolling(ROLLING_SET, "BTC/EUR", 15, _AS_OF, window=("2026-09-29 00:00:00+00:00", "2026-09-29 23:45:00+00:00"))
    with pytest.raises(RegistryError, match="accumulated nothing"):
        reader.block()


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_a_rolling_index_the_reader_cannot_list_is_a_registry_refusal_naming_it(tmp_path):
    root = _rolling(tmp_path)
    month = root / ROLLING_SET / "index/2026/10"
    os.chmod(month, 0o000)
    try:
        with pytest.raises(RegistryError, match=rf"^{ROLLING_SET}: .*Permission denied: '{re.escape(str(month))}'$"):
            ObservedReader(root).read_rolling(ROLLING_SET, "BTC/EUR", 1440, _AS_OF)
    finally:
        os.chmod(month, 0o755)


_FULL_SET_EXPECTATIONS = {  # measured 2026-08-08; spans in the loader's own stamp format
    "ohlc-full": (36, 1_052_322, "2013-09-10 00:00:00+00:00", "2026-03-31 23:00:00+00:00"),
    "ohlc-15m": (12, 3_122_044, "2013-09-10 23:45:00+00:00", "2026-03-31 23:45:00+00:00"),
    "ohlc-holdout-2026-07-10": (10, 30_032, "2013-09-10 00:00:00+00:00", "2026-07-09 00:00:00+00:00"),
}


@pytest.mark.parametrize("dataset", sorted(_FULL_SET_EXPECTATIONS))
def test_loader_reproduces_the_frozen_full_set_extents(dataset):
    # A figure that stops reproducing means the canonical dataset drifted — STOP, the same contract
    # as tests/test_crossfreq_system.py.
    root = Path(__file__).resolve().parents[1] / "data"
    if nothing_found_under(root, dataset):
        pytest.skip(f"{dataset} not on this host — data-bearing workstation only")
    reader = ObservedReader(root)
    for f in sorted((root / dataset).rglob("*.parquet")):
        reader.read_series(dataset, f.relative_to(root / dataset).as_posix())
    files, rows, first, last = _FULL_SET_EXPECTATIONS[dataset]
    entry = reader.block()[dataset]
    assert (len(entry["files"]), entry["rows"], *entry["span"]) == (files, rows, first, last)
