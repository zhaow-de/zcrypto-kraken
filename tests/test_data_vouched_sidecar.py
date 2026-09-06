"""Committed attestations for frozen sets whose producer this repo does not write."""

import json
from pathlib import Path

import pytest

import cli.data.sync as sync
from cli.data.errors import DataSyncError
from cli.ohlc.dataset import dataset_hash, to_frame, write_parquet
from cli.registry.errors import RegistryError
from cli.registry.observed import ObservedReader

ROOT = Path(__file__).resolve().parent.parent
COMMITTED_SIDECAR = ROOT / "docs" / "reference" / "vouched-dataset-hashes.jsonl"
HOLDOUT = "ohlc-holdout-2026-07-10"


@pytest.fixture(autouse=True)
def _clear_sidecar_cache():
    # The loader is lru_cached, so a monkeypatched path leaks into later tests without this.
    sync._sidecar_by_dataset.cache_clear()
    yield
    sync._sidecar_by_dataset.cache_clear()


def _rows(n, start=1577836800):
    return [[start + i * 86400, "1", "2", "0.5", "1.5", "1.2", "10", 3] for i in range(n)]


def _point_sidecar_at(tmp_path, monkeypatch, records):
    path = tmp_path / "sidecar.jsonl"
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records), encoding="utf-8")
    monkeypatch.setattr(sync, "_VOUCHED_SIDECAR", path)
    sync._sidecar_by_dataset.cache_clear()


# --- the committed file itself -------------------------------------------------------------------


def test_the_committed_sidecar_attests_every_holdout_series():
    """CI-runnable: the sidecar is committed even though `data/` is not, so this holds everywhere."""
    lines = [json.loads(x) for x in COMMITTED_SIDECAR.read_text(encoding="utf-8").splitlines() if x.strip()]
    holdout = [r for r in lines if r["dataset"] == HOLDOUT]
    assert len(holdout) == 10, "the freeze has ten series; a missing line is a silently unattested one"
    assert len({r["relpath"] for r in holdout}) == 10
    assert sum(r["rows"] for r in holdout) == 30_032  # the freeze's recorded total
    for r in holdout:
        assert len(r["dataset_sha256"]) == 64 and int(r["dataset_sha256"], 16) >= 0


def test_sidecar_hashes_are_keyed_by_dataset(tmp_path, monkeypatch):
    _point_sidecar_at(
        tmp_path,
        monkeypatch,
        [
            {"dataset": "set-a", "relpath": "A.parquet", "dataset_sha256": "a" * 64, "rows": 1},
            {"dataset": "set-b", "relpath": "B.parquet", "dataset_sha256": "b" * 64, "rows": 1},
        ],
    )
    assert sync.sidecar_hashes("set-a") == {"a" * 64}
    assert sync.sidecar_hashes("set-b") == {"b" * 64}
    assert sync.sidecar_hashes("set-never-heard-of") == set()


@pytest.mark.parametrize(
    ("line", "because"),
    [
        ("{not json", "unparseable"),
        (json.dumps({"dataset": "x"}), "missing dataset_sha256"),
        (json.dumps([1, 2]), "valid JSON but not an object"),
        (json.dumps("x"), "a bare JSON string"),
    ],
)
def test_a_broken_sidecar_line_is_refused_typed_rather_than_ignored(tmp_path, monkeypatch, line, because):
    # Silently skipping a bad line is how a set loses its attestation without anyone noticing.
    path = tmp_path / "sidecar.jsonl"
    path.write_text(line + "\n", encoding="utf-8")
    monkeypatch.setattr(sync, "_VOUCHED_SIDECAR", path)
    sync._sidecar_by_dataset.cache_clear()
    with pytest.raises(DataSyncError):
        sync.sidecar_hashes("x")


def test_a_corrupt_sidecar_refuses_in_the_read_surfaces_own_dialect(tmp_path, monkeypatch):
    # `read_series` speaks RegistryError; a DataSyncError escaping through it would bypass every
    # caller that catches the documented type.
    root, _ = _frozen_set(tmp_path)
    path = tmp_path / "sidecar.jsonl"
    path.write_text("{not json\n", encoding="utf-8")
    monkeypatch.setattr(sync, "_VOUCHED_SIDECAR", path)
    sync._sidecar_by_dataset.cache_clear()
    with pytest.raises(RegistryError, match="attestations are unreadable"):
        ObservedReader(root).read_series("frozen-set", "BTC/EUR/1440.parquet")


def test_a_missing_sidecar_says_so_rather_than_degrading_in_silence(tmp_path, monkeypatch, caplog):
    # Absent attestations revert every frozen set to unverified -- survivable, but only if it is not also silent.
    monkeypatch.setattr(sync, "_VOUCHED_SIDECAR", tmp_path / "nope.jsonl")
    sync._sidecar_by_dataset.cache_clear()
    with caplog.at_level("WARNING"):
        assert sync.sidecar_hashes("anything") == set()
    assert "vouched attestations absent" in caplog.text


# --- the read-time guard, which is the one that protects the copy already on disk -----------------


def _frozen_set(tmp_path, name="frozen-set"):
    """A set whose manifest vouches NOTHING -- the holdout's shape, without needing `data/`."""
    root = tmp_path / "data"
    frame = to_frame(_rows(10))
    write_parquet(frame, root / name / "BTC/EUR/1440.parquet")
    (root / name / "manifest.json").write_text(
        json.dumps({"pulled_at": "2026-07-10", "series": {"BTC/EUR": {"rows": 10}}, "manifest_sha256": "9" * 64})
    )
    return root, dataset_hash(frame)


def test_a_manifest_that_vouches_nothing_leaves_the_read_guard_inert_without_a_sidecar(tmp_path, monkeypatch):
    root, _ = _frozen_set(tmp_path)
    _point_sidecar_at(tmp_path, monkeypatch, [])
    reader = ObservedReader(root)
    reader.read_series("frozen-set", "BTC/EUR/1440.parquet")
    assert reader.vouched_status() == {"frozen-set": "inert (0 vouched hashes)"}


def test_the_sidecar_arms_the_read_guard_and_a_tampered_frame_is_refused(tmp_path, monkeypatch):
    root, good = _frozen_set(tmp_path)
    _point_sidecar_at(
        tmp_path,
        monkeypatch,
        [{"dataset": "frozen-set", "relpath": "BTC/EUR/1440.parquet", "dataset_sha256": good, "rows": 10}],
    )
    reader = ObservedReader(root)
    reader.read_series("frozen-set", "BTC/EUR/1440.parquet")  # healthy read still passes
    assert reader.vouched_status() == {"frozen-set": "checked (1 vouched hashes)"}

    # Tamper preserving ROW COUNT and SPAN -- what the manifest's own metadata cannot catch.
    tampered = _rows(10)
    tampered[5][4] = "99.5"
    write_parquet(to_frame(tampered), root / "frozen-set" / "BTC/EUR/1440.parquet")
    with pytest.raises(RegistryError, match="frame-content hash"):
        ObservedReader(root).read_series("frozen-set", "BTC/EUR/1440.parquet")


def test_two_swapped_series_are_caught_although_the_hash_SET_is_unchanged(tmp_path, monkeypatch):
    """The case membership provably cannot catch, which is why the attestation is path-keyed."""
    root = tmp_path / "data"
    a, b = to_frame(_rows(10)), to_frame(_rows(7))
    write_parquet(a, root / "frozen-set" / "A/EUR/1440.parquet")
    write_parquet(b, root / "frozen-set" / "B/EUR/1440.parquet")
    _point_sidecar_at(
        tmp_path,
        monkeypatch,
        [
            {"dataset": "frozen-set", "relpath": "A/EUR/1440.parquet", "dataset_sha256": dataset_hash(a), "rows": 10},
            {"dataset": "frozen-set", "relpath": "B/EUR/1440.parquet", "dataset_sha256": dataset_hash(b), "rows": 7},
        ],
    )
    ObservedReader(root).read_series("frozen-set", "A/EUR/1440.parquet")  # healthy, before the swap

    # The premise: the set of vouched hashes is IDENTICAL after the swap, so membership is blind.
    assert sync.sidecar_hashes("frozen-set") == {dataset_hash(a), dataset_hash(b)}
    write_parquet(b, root / "frozen-set" / "A/EUR/1440.parquet")
    write_parquet(a, root / "frozen-set" / "B/EUR/1440.parquet")

    with pytest.raises(RegistryError, match="two series were swapped"):
        ObservedReader(root).read_series("frozen-set", "A/EUR/1440.parquet")


# --- the push side: a node that accepts bad bytes is never corrected ------------------------------


def test_a_path_named_twice_with_different_hashes_is_refused(tmp_path, monkeypatch):
    # A second line for a path silently shadowing the first is how a set ends up attested by the
    # wrong hash.
    rec = {"dataset": "d", "relpath": "A.parquet", "dataset_sha256": "a" * 64, "rows": 1}
    _point_sidecar_at(tmp_path, monkeypatch, [rec, dict(rec)])
    assert sync.sidecar_hashes("d") == {"a" * 64}  # exact duplicate: fine

    with pytest.raises(DataSyncError, match="attested twice, differently"):
        _point_sidecar_at(tmp_path, monkeypatch, [rec, {**rec, "dataset_sha256": "b" * 64}])
        sync.sidecar_hashes("d")


# --- the FETCH side, which is where a first ingest lands ------------------------------------------


def _hot_set_attested(tmp_path, monkeypatch, *, hash_the_sidecar_names):
    """A hot set whose sidecar line names its path, with a caller-chosen hash for that path."""
    hot = tmp_path / "hot"
    frame = to_frame(_rows(10))
    write_parquet(frame, hot / "frozen-set" / "BTC/EUR/1440.parquet")
    (hot / "frozen-set" / "manifest.json").write_text(json.dumps({"series": {"BTC/EUR": {"rows": 10}}}))
    _point_sidecar_at(
        tmp_path,
        monkeypatch,
        [{"dataset": "frozen-set", "relpath": "BTC/EUR/1440.parquet", "dataset_sha256": hash_the_sidecar_names, "rows": 10}],
    )
    return hot, dataset_hash(frame)


def test_a_fetch_accepts_content_matching_the_path_the_sidecar_names(tmp_path, monkeypatch):
    # The true positive: without it, a path-bound check that refuses everything would look correct.
    frame_hash = dataset_hash(to_frame(_rows(10)))
    hot, _ = _hot_set_attested(tmp_path, monkeypatch, hash_the_sidecar_names=frame_hash)
    report = sync.fetch_hot(hot, tmp_path / "data")
    assert "frozen-set/BTC/EUR/1440.parquet" in report.new_files


def test_a_fetch_refuses_content_that_is_not_what_the_sidecar_names_for_that_path(tmp_path, monkeypatch):
    # Its manifest vouches nothing, so only the sidecar can speak -- and it names a hash this file
    # does not have.
    hot, _ = _hot_set_attested(tmp_path, monkeypatch, hash_the_sidecar_names="c" * 64)
    with pytest.raises(DataSyncError, match="attests for THAT path"):
        sync.fetch_hot(hot, tmp_path / "data")


def test_push_refuses_unattested_content_before_it_leaves(tmp_path, monkeypatch):
    root, good = _frozen_set(tmp_path)
    _point_sidecar_at(
        tmp_path,
        monkeypatch,
        [{"dataset": "frozen-set", "relpath": "BTC/EUR/1440.parquet", "dataset_sha256": good, "rows": 10}],
    )
    dest = tmp_path / "hub"
    dest.mkdir()

    tampered = _rows(10)
    tampered[5][4] = "99.5"
    write_parquet(to_frame(tampered), root / "frozen-set" / "BTC/EUR/1440.parquet")

    with pytest.raises(DataSyncError, match="refusing to transmit"):
        sync.push_hot(root, ["frozen-set"], str(dest) + "/")
    # PRE-flight is the whole point: the channel never overwrites, so bytes that leave are permanent.
    assert not list(dest.rglob("*.parquet")), "the tampered parquet reached the hub before being refused"


def test_push_still_carries_an_attested_set(tmp_path, monkeypatch):
    root, good = _frozen_set(tmp_path)
    _point_sidecar_at(
        tmp_path,
        monkeypatch,
        [{"dataset": "frozen-set", "relpath": "BTC/EUR/1440.parquet", "dataset_sha256": good, "rows": 10}],
    )
    dest = tmp_path / "hub"
    dest.mkdir()
    report = sync.push_hot(root, ["frozen-set"], str(dest) + "/")
    assert "frozen-set/BTC/EUR/1440.parquet" in report.new_files
    assert (dest / "frozen-set" / "BTC/EUR/1440.parquet").is_file()


# --- the waiting consumer T0133 parked: manifest-attested sets become path-bound -------------------


def _conformant_set(tmp_path, name="ohlc-thing"):
    """A set attested by its OWN manifest (no sidecar), in the contract shape."""
    from cli.data.manifest import build_manifest, series_entry

    root = tmp_path / "data"
    a, b = to_frame(_rows(10)), to_frame(_rows(7))
    write_parquet(a, root / name / "A/EUR/1440.parquet")
    write_parquet(b, root / name / "B/EUR/1440.parquet")
    series = {
        "A/EUR/1440.parquet": series_entry(a, "A/EUR/1440.parquet"),
        "B/EUR/1440.parquet": series_entry(b, "B/EUR/1440.parquet"),
    }
    (root / name / "manifest.json").write_text(json.dumps(build_manifest(series, written_at="2026-08-24T00:00:00+00:00")))
    return root, a, b


def test_a_swap_inside_a_manifest_attested_set_is_refused_at_read(tmp_path, monkeypatch):
    """A conformant manifest's series key IS the path, so it binds paths exactly as the sidecar does
    -- the residual T0133 parked."""
    _point_sidecar_at(tmp_path, monkeypatch, [])  # no sidecar: the manifest is the only attestor
    root, a, b = _conformant_set(tmp_path)
    ObservedReader(root).read_series("ohlc-thing", "A/EUR/1440.parquet")  # healthy

    write_parquet(b, root / "ohlc-thing" / "A/EUR/1440.parquet")
    write_parquet(a, root / "ohlc-thing" / "B/EUR/1440.parquet")
    with pytest.raises(RegistryError):
        ObservedReader(root).read_series("ohlc-thing", "A/EUR/1440.parquet")


def test_a_swap_inside_a_manifest_attested_set_is_refused_at_fetch(tmp_path, monkeypatch):
    _point_sidecar_at(tmp_path, monkeypatch, [])
    hot, a, b = _conformant_set(tmp_path, name="ohlc-thing")
    hot = hot / "ohlc-thing"
    swapped = tmp_path / "hot"
    (swapped / "ohlc-thing").mkdir(parents=True)
    for f in hot.rglob("*"):
        if f.is_file():
            target = swapped / "ohlc-thing" / f.relative_to(hot)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f.read_bytes())
    write_parquet(b, swapped / "ohlc-thing" / "A/EUR/1440.parquet")
    write_parquet(a, swapped / "ohlc-thing" / "B/EUR/1440.parquet")

    with pytest.raises(DataSyncError, match="attests for THAT path|is not what"):
        sync.fetch_hot(swapped, tmp_path / "dest")
