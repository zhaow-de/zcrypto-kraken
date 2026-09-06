"""The capturing loader: identity is what the run read (spec 00086 D1/D2)."""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from cli.ohlc.dataset import to_frame, write_parquet
from cli.registry.errors import RegistryError
from cli.registry.observed import ObservedReader


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
    if not (root / dataset).is_dir():
        pytest.skip(f"{dataset} not on this host — data-bearing workstation only")
    reader = ObservedReader(root)
    for f in sorted((root / dataset).rglob("*.parquet")):
        reader.read_series(dataset, f.relative_to(root / dataset).as_posix())
    files, rows, first, last = _FULL_SET_EXPECTATIONS[dataset]
    entry = reader.block()[dataset]
    assert (len(entry["files"]), entry["rows"], *entry["span"]) == (files, rows, first, last)
