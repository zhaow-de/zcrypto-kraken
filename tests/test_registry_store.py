import inspect
import json
from pathlib import Path

import pytest

from cli.registry import GENESIS_HASH, SCHEMA_VERSION, RegistryCorruptionError, RegistryError, TrialRegistry
from cli.registry.record import canonical_json, compute_hash

_REGISTRY = Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl"

_BLOCK = {
    "files": {"BTC/EUR/1440.parquet": "c" * 64},
    "rows": 10,
    "span": ["2020-01-01 00:00:00+00:00", "2020-01-10 00:00:00+00:00"],
}


def _line(trial_id, family="A1", n=1, metrics=None, prev_hash=GENESIS_HASH):
    # Pinned to a literal 3: this is the v3-semantics helper -- a v4 body would need a `datasets` block.
    body = dict(
        trial_id=trial_id,
        schema_version=3,
        timestamp="2026-07-07T00:00:00+00:00",
        iteration="iter-001",
        family=family,
        spec_hash="s",
        dataset_hash="d",
        seeds=[0],
        metrics=metrics or {"sharpe": 0.3, "dsr": 0.1},
        n_trials_in_family=n,
        verdict="adopt",
        run_ref=None,
        notes="",
        prev_hash=prev_hash,
    )
    return canonical_json(dict(body, record_hash=compute_hash(body)))


def _line_v2(trial_id, family="A1", n=1, metrics=None, prev_hash=GENESIS_HASH):
    # Mimics the pre-v3 writer: hardcodes schema_version=2, never emits a `variant` key.
    body = dict(
        trial_id=trial_id,
        schema_version=2,
        timestamp="2026-07-07T00:00:00+00:00",
        iteration="iter-001",
        family=family,
        spec_hash="s",
        dataset_hash="d",
        seeds=[0],
        metrics=metrics or {"sharpe": 0.3, "dsr": 0.1},
        n_trials_in_family=n,
        verdict="adopt",
        run_ref=None,
        notes="",
        prev_hash=prev_hash,
    )
    return canonical_json(dict(body, record_hash=compute_hash(body)))


def _hash_of(line: str) -> str:
    return json.loads(line)["record_hash"]


def _new_registry(tmp_path):
    return TrialRegistry(tmp_path / "t.jsonl")


def _write(tmp_path, lines, trailing_nl=True):
    p = tmp_path / "trials.jsonl"
    text = "\n".join(lines)
    if trailing_nl and lines:
        text += "\n"
    p.write_text(text, encoding="utf-8")
    return p


def test_absent_and_empty_file_is_empty_registry(tmp_path):
    assert len(TrialRegistry(tmp_path / "none.jsonl")) == 0
    assert len(TrialRegistry(_write(tmp_path, []))) == 0


def test_valid_file_loads(tmp_path):
    l1 = _line(1, n=2)
    l2 = _line(2, n=2, prev_hash=_hash_of(l1))
    reg = TrialRegistry(_write(tmp_path, [l1, l2]))
    assert len(reg) == 2 and reg.records[1].trial_id == 2


def test_bare_nan_token_line_raises(tmp_path):
    poison = '{"trial_id":1,"schema_version":1,"metrics":{"dsr":NaN}}'
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [poison]))


def test_contiguity_violation_raises(tmp_path):
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [_line(1), _line(3)]))  # gap
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [_line(2), _line(1)]))  # reorder


def test_record_hash_mismatch_raises(tmp_path):
    good = _line(1)
    tampered = good.replace('"sharpe":0.3', '"sharpe":0.9')  # finite->finite edit, hash now stale
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [tampered]))


def test_torn_trailing_line_self_heals(tmp_path):
    p = _write(tmp_path, [_line(1)])
    with p.open("a", encoding="utf-8") as f:
        f.write('{"trial_id":2,"fam')  # crash mid-append, NO trailing newline
    reg = TrialRegistry(p)  # heals, does not raise
    assert len(reg) == 1
    assert p.read_text(encoding="utf-8").endswith("}\n")  # partial line physically truncated


def test_torn_interior_line_raises(tmp_path):
    # same partial content but as an INTERIOR line (file ends in newline) -> body corruption, must raise
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, ['{"trial_id":1,"fam', _line(2)]))


def test_unknown_schema_version_raises(tmp_path):
    body = dict(
        trial_id=1,
        schema_version=999,
        timestamp="t",
        iteration="i",
        family="A1",
        spec_hash="s",
        dataset_hash="d",
        seeds=[0],
        metrics={"dsr": 0.1},
        n_trials_in_family=1,
        verdict="adopt",
        run_ref=None,
        notes="",
    )
    line = canonical_json(dict(body, record_hash=compute_hash(body)))
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [line]))


COMMITTED_PATH = "cli/registry/record.py"  # a real, git-tracked file: run_ref is now required to name one


def _append(reg, **over):
    kw = dict(
        iteration="iter-001",
        family="A1",
        spec_hash="s",
        datasets={"ohlc-test": dict(_BLOCK)},
        seeds=[0],
        metrics={"sharpe": 0.3, "dsr": 0.1},
        n_trials_in_family=2,
        verdict="adopt",
        run_ref=COMMITTED_PATH,
    )
    kw.update(over)
    return reg.append(**kw)


def test_append_assigns_contiguous_ids_across_reopen(tmp_path):
    p = tmp_path / "t.jsonl"
    r1 = _append(TrialRegistry(p))
    assert r1.trial_id == 1 and r1.record_hash and r1.timestamp.endswith("+00:00")
    r2 = _append(TrialRegistry(p))  # fresh registry, same path
    assert r2.trial_id == 2
    assert len(TrialRegistry(p)) == 2  # reload verifies all asserts


def test_append_rejects_nonfinite_before_writing(tmp_path):
    p = tmp_path / "t.jsonl"
    with pytest.raises(RegistryError):
        _append(TrialRegistry(p), metrics={"dsr": float("nan")})
    assert not p.exists() or p.read_text() == ""  # nothing was written


def test_append_family_count_floor(tmp_path):
    p = tmp_path / "t.jsonl"
    _append(TrialRegistry(p), family="A1", n_trials_in_family=1)  # 1st in A1, floor is 1 -> OK
    with pytest.raises(RegistryError):
        _append(TrialRegistry(p), family="A1", n_trials_in_family=1)  # 2nd in A1 needs >= 2


def test_append_then_records_snapshot(tmp_path):
    reg = TrialRegistry(tmp_path / "t.jsonl")
    _append(reg)
    assert reg.records[-1].trial_id == 1  # in-memory cache updated


def test_concurrent_registries_get_unique_ids(tmp_path):
    p = tmp_path / "t.jsonl"
    a, b = TrialRegistry(p), TrialRegistry(p)  # both see empty
    _append(a)
    _append(b)  # b re-reads under lock -> id 2, not a duplicate 1
    ids = sorted(r.trial_id for r in TrialRegistry(p).records)
    assert ids == [1, 2]


def test_append_after_torn_trailing_line_self_heal(tmp_path):
    p = _write(tmp_path, [_line(1)])
    with p.open("a", encoding="utf-8") as f:
        f.write('{"trial_id":2,"fam')  # crash mid-append, NO trailing newline
    reg = TrialRegistry(p)  # heals to len 1, does not raise
    r = _append(reg, family="B1", n_trials_in_family=1)  # 1st in a fresh family -> floor OK
    assert r.trial_id == 2
    assert len(TrialRegistry(p)) == 2  # reload confirms the registry stayed appendable


def test_chain_links_are_written(tmp_path):
    reg = _new_registry(tmp_path)
    r0 = _append(reg, family="A", n_trials_in_family=1)
    r1 = _append(reg, family="A", n_trials_in_family=2)
    r2 = _append(reg, family="A", n_trials_in_family=3)
    assert r0.prev_hash == GENESIS_HASH
    assert r1.prev_hash == r0.record_hash
    assert r2.prev_hash == r1.record_hash


def test_rehashing_tamper_of_middle_record_is_caught(tmp_path):
    reg = _new_registry(tmp_path)
    _append(reg, family="A", n_trials_in_family=1)
    _append(reg, family="A", n_trials_in_family=2)
    _append(reg, family="A", n_trials_in_family=3)
    lines = reg.path.read_text().splitlines()
    rec = json.loads(lines[1])  # record 2 (trial_id 2)
    rec["metrics"] = {**rec["metrics"], "sharpe": 999.0}  # tamper a metric
    body = {k: v for k, v in rec.items() if k != "record_hash"}
    rec["record_hash"] = compute_hash(body)  # re-hash so the SELF-hash check passes
    lines[1] = canonical_json(rec)
    reg.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(reg.path)  # chain check fails at record 3 (prev_hash mismatch)


def test_metric_tamper_without_rehash_still_caught(tmp_path):
    reg = _new_registry(tmp_path)
    _append(reg, family="A", n_trials_in_family=1)
    _append(reg, family="A", n_trials_in_family=2)
    lines = reg.path.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["metrics"] = {**rec["metrics"], "sharpe": 999.0}  # no re-hash
    lines[0] = canonical_json(rec)
    reg.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(reg.path)  # existing self-hash check fires


def test_deleting_middle_record_is_caught(tmp_path):
    reg = _new_registry(tmp_path)
    _append(reg, family="A", n_trials_in_family=1)
    _append(reg, family="A", n_trials_in_family=2)
    _append(reg, family="A", n_trials_in_family=3)
    lines = reg.path.read_text().splitlines()
    del lines[1]
    reg.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(reg.path)


def test_schema_version_1_record_is_rejected(tmp_path):
    reg = _new_registry(tmp_path)
    _append(reg, family="A", n_trials_in_family=1)
    lines = reg.path.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["schema_version"] = 1
    body = {k: v for k, v in rec.items() if k != "record_hash"}
    rec["record_hash"] = compute_hash(body)
    lines[0] = canonical_json(rec)
    reg.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(reg.path)


def test_chain_continues_across_registry_instances(tmp_path):
    reg = _new_registry(tmp_path)
    last = _append(reg, family="A", n_trials_in_family=1)
    reg2 = TrialRegistry(reg.path)  # reopen
    nxt = _append(reg2, family="A", n_trials_in_family=2)
    assert nxt.prev_hash == last.record_hash


def test_append_with_variant_round_trips(tmp_path):
    p = tmp_path / "t.jsonl"
    r = _append(TrialRegistry(p), variant="A2-donchian", n_trials_in_family=1)
    assert r.variant == "A2-donchian"
    assert r.schema_version == SCHEMA_VERSION
    reloaded = TrialRegistry(p)
    assert reloaded.records[0].variant == "A2-donchian"
    assert reloaded.records[0].record_hash == r.record_hash
    assert reloaded.records[0].prev_hash == GENESIS_HASH


def test_append_without_variant_omits_key_from_raw_line(tmp_path):
    p = tmp_path / "t.jsonl"
    r = _append(TrialRegistry(p), n_trials_in_family=1)
    assert r.variant is None
    raw = p.read_text(encoding="utf-8").strip()
    assert '"variant"' not in raw
    assert len(TrialRegistry(p)) == 1  # loads fine without the key


def test_append_rejects_invalid_variant_before_writing(tmp_path):
    p = tmp_path / "t.jsonl"
    with pytest.raises(RegistryError):
        _append(TrialRegistry(p), variant="", n_trials_in_family=1)
    assert not p.exists() or p.read_text() == ""
    with pytest.raises(RegistryError):
        _append(TrialRegistry(p), variant=123, n_trials_in_family=1)
    assert not p.exists() or p.read_text() == ""


def test_mixed_v2_and_v4_file_loads_with_intact_chain(tmp_path):
    # Two legacy v2 lines plus a freshly appended one, which the writer now emits at schema 4.
    p = tmp_path / "trials.jsonl"
    l1 = _line_v2(1, n=1)
    l2 = _line_v2(2, n=2, prev_hash=_hash_of(l1))
    p.write_text(l1 + "\n" + l2 + "\n", encoding="utf-8")
    reg = TrialRegistry(p)
    assert len(reg) == 2

    r3 = _append(reg, family="A1", n_trials_in_family=3, variant="A2-donchian")
    assert r3.trial_id == 3
    assert r3.prev_hash == _hash_of(l2)

    fresh = TrialRegistry(p)  # fresh instance re-reads and re-validates the whole file
    assert [r.trial_id for r in fresh.records] == [1, 2, 3]
    assert fresh.records[0].schema_version == 2 and fresh.records[1].schema_version == 2
    assert fresh.records[2].schema_version == SCHEMA_VERSION
    assert fresh.records[2].variant == "A2-donchian"
    assert fresh.records[1].prev_hash == fresh.records[0].record_hash
    assert fresh.records[2].prev_hash == fresh.records[1].record_hash


def test_v2_record_with_variant_key_is_corruption(tmp_path):
    body = json.loads(_line_v2(1, n=1))
    body["variant"] = "A2-donchian"  # a v2 record must never carry this key
    tampered = canonical_json(dict(body, record_hash=compute_hash({k: v for k, v in body.items() if k != "record_hash"})))
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [tampered]))


def test_v3_record_with_nonstr_variant_is_corruption(tmp_path):
    body = dict(
        trial_id=1,
        schema_version=3,  # v3 semantics: a v4 body would need a `datasets` block
        timestamp="2026-07-07T00:00:00+00:00",
        iteration="iter-001",
        family="A1",
        variant=42,  # non-str
        spec_hash="s",
        dataset_hash="d",
        seeds=[0],
        metrics={"sharpe": 0.3, "dsr": 0.1},
        n_trials_in_family=1,
        verdict="adopt",
        run_ref=None,
        notes="",
        prev_hash=GENESIS_HASH,
    )
    line = canonical_json(dict(body, record_hash=compute_hash(body)))
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [line]))


def test_v3_unknown_key_forge_is_corruption(tmp_path):
    body = dict(
        trial_id=1,
        schema_version=3,  # v3 semantics: a v4 body would need a `datasets` block
        timestamp="2026-07-07T00:00:00+00:00",
        iteration="iter-001",
        family="A1",
        variant="v1",
        spec_hash="s",
        dataset_hash="d",
        seeds=[0],
        metrics={"sharpe": 0.3, "dsr": 0.1},
        n_trials_in_family=1,
        verdict="adopt",
        run_ref=None,
        notes="",
        prev_hash=GENESIS_HASH,
        variannt="x",  # misspelled forge, not a real field
    )
    line = canonical_json(dict(body, record_hash=compute_hash(body)))
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [line]))


def test_v2_unknown_key_forge_is_corruption(tmp_path):
    body = json.loads(_line_v2(1, n=1))
    body["extra_key"] = 1  # unknown key, not part of any v2 field set
    tampered = canonical_json(dict(body, record_hash=compute_hash({k: v for k, v in body.items() if k != "record_hash"})))
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [tampered]))


def test_missing_base_key_is_corruption(tmp_path):
    body = dict(
        trial_id=1,
        schema_version=3,  # v3 semantics: a v4 body would need a `datasets` block
        timestamp="2026-07-07T00:00:00+00:00",
        iteration="iter-001",
        family="A1",
        spec_hash="s",
        dataset_hash="d",
        seeds=[0],
        metrics={"sharpe": 0.3, "dsr": 0.1},
        n_trials_in_family=1,
        verdict="adopt",
        run_ref=None,
        # notes intentionally omitted -- a required base key
        prev_hash=GENESIS_HASH,
    )
    line = canonical_json(dict(body, record_hash=compute_hash(body)))
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [line]))


def test_v3_without_variant_still_loads(tmp_path):
    body = dict(
        trial_id=1,
        schema_version=3,  # v3 semantics: a v4 body would need a `datasets` block
        timestamp="2026-07-07T00:00:00+00:00",
        iteration="iter-001",
        family="A1",
        spec_hash="s",
        dataset_hash="d",
        seeds=[0],
        metrics={"sharpe": 0.3, "dsr": 0.1},
        n_trials_in_family=1,
        verdict="adopt",
        run_ref=None,
        notes="",
        prev_hash=GENESIS_HASH,
    )
    line = canonical_json(dict(body, record_hash=compute_hash(body)))
    reg = TrialRegistry(_write(tmp_path, [line]))
    assert len(reg) == 1


def test_variant_tamper_without_rehash_is_caught(tmp_path):
    reg = _new_registry(tmp_path)
    _append(reg, family="A", n_trials_in_family=1, variant="v1")
    lines = reg.path.read_text().splitlines()
    rec = json.loads(lines[0])
    rec["variant"] = "tampered"  # no re-hash
    lines[0] = canonical_json(rec)
    reg.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(reg.path)


def test_live_registry_file_loads_clean():
    # Read-only: exercises the v2/v3 loader against the real, committed registry. Never write to this file.
    # The registry is append-only, so records 1-32 (the pre-v3 era) are a frozen historical fact asserted
    # verbatim; the total count grows with every registered trial and is only floored, never pinned.
    reg = TrialRegistry(Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl")
    assert len(reg) >= 33  # 32 pre-v3 + the first v3-era record (iter-059, P1)
    pre_v3 = reg.records[:32]
    assert all(r.schema_version == 2 for r in pre_v3)
    assert all(r.variant is None for r in pre_v3)  # pre-v3 records; variant-25..32 lives in `notes` only
    assert all(r.schema_version >= 3 for r in reg.records[32:])  # everything after landed on schema v3+


def test_append_records_a_committed_run_ref_end_to_end(tmp_path):
    p = tmp_path / "t.jsonl"
    r = _append(TrialRegistry(p), n_trials_in_family=1, run_ref=COMMITTED_PATH)
    assert r.run_ref == COMMITTED_PATH
    assert TrialRegistry(p).records[0].run_ref == COMMITTED_PATH  # survives the reload + re-validation


def test_append_rejects_unprovenanced_run_ref_before_writing(tmp_path):
    for bad in ("trial47_run.py (scratchpad)", "cli/registry/no_such_runner.py", "", None):
        p = tmp_path / f"t{hash(str(bad))}.jsonl"
        with pytest.raises(RegistryError):
            _append(TrialRegistry(p), n_trials_in_family=1, run_ref=bad)
        assert not p.exists() or p.read_text() == ""  # fail rather than be recorded


def test_append_requires_run_ref_explicitly(tmp_path):
    # No default: omitting run_ref is a TypeError at the call, not a silently-recorded null.
    reg = TrialRegistry(tmp_path / "t.jsonl")
    with pytest.raises(TypeError):
        reg.append(
            iteration="iter-001",
            family="A1",
            spec_hash="s",
            datasets={"ohlc-test": dict(_BLOCK)},
            seeds=[0],
            metrics={"sharpe": 0.3},
            n_trials_in_family=1,
            verdict="adopt",
        )


def test_variant_does_not_affect_family_budget_monotonic_check(tmp_path):
    p = tmp_path / "t.jsonl"
    reg = TrialRegistry(p)
    _append(reg, family="A1", n_trials_in_family=1, variant="v1")
    with pytest.raises(RegistryError):  # 2nd in A1 needs >= 2, regardless of a different variant
        _append(reg, family="A1", n_trials_in_family=1, variant="v2")
    r2 = _append(reg, family="A1", n_trials_in_family=2, variant="v2")
    assert r2.trial_id == 2


def test_all_46_committed_records_still_load():
    reg = TrialRegistry(_REGISTRY)
    assert len(reg) >= 46  # floored, never pinned: the file grows with every registered trial
    assert all(r.schema_version in (2, 3) or r.datasets for r in reg.records)


def test_append_has_no_dataset_hash_parameter():
    assert "dataset_hash" not in inspect.signature(TrialRegistry.append).parameters


def test_a_schema_four_record_round_trips_through_disk(tmp_path):
    reg = _new_registry(tmp_path)
    written = _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-test": dict(_BLOCK)})
    reloaded = _new_registry(tmp_path).records[-1]
    assert reloaded.schema_version == 4
    assert reloaded.dataset_hash == compute_hash(reloaded.datasets) == written.dataset_hash


def test_different_file_sets_give_different_digests(tmp_path):
    """The slice IS the file list: daily-only vs daily+4h differ by construction (D2)."""
    reg = _new_registry(tmp_path)
    daily = _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-test": dict(_BLOCK)})
    both_files = {**_BLOCK["files"], "BTC/EUR/240.parquet": "d" * 64}
    both = _append(reg, family="B", n_trials_in_family=1, datasets={"ohlc-test": {**_BLOCK, "files": both_files, "rows": 70}})
    assert daily.dataset_hash != both.dataset_hash


def test_a_windowed_read_gives_a_different_digest(tmp_path):
    """The sample window is expressible (D2): same files, different rows/span, different digest."""
    reg = _new_registry(tmp_path)
    full = _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-test": dict(_BLOCK)})
    windowed = _append(
        reg,
        family="B",
        n_trials_in_family=1,
        datasets={"ohlc-test": {**_BLOCK, "rows": 3, "span": ["2020-01-03 00:00:00+00:00", "2020-01-05 00:00:00+00:00"]}},
    )
    assert full.dataset_hash != windowed.dataset_hash


def _schema4_line(**over):
    body = dict(
        trial_id=1,
        schema_version=4,
        timestamp="2026-08-09T00:00:00+00:00",
        iteration="iter-001",
        family="A1",
        spec_hash="s",
        seeds=[0],
        metrics={"dsr": 0.1},
        n_trials_in_family=1,
        verdict="adopt",
        run_ref=None,
        notes="",
        prev_hash=GENESIS_HASH,
        datasets={"ohlc-test": dict(_BLOCK)},
    )
    body.update(over)
    body["dataset_hash"] = over.get("dataset_hash", compute_hash(body["datasets"]))
    return canonical_json(dict(body, record_hash=compute_hash(body)))


@pytest.mark.parametrize(
    "over, match",
    [
        ({"dataset_hash": "deadbeef" * 8}, "dataset_hash"),  # D4: derivation, not a caller claim
        ({"datasets": "ba47e37e"}, "datasets must be a non-empty dict"),  # the original failure, verbatim
        ({"datasets": {}}, "datasets must be a non-empty dict"),  # empty carries no provenance
        ({"datasets": {"ohlc-test": {**_BLOCK, "files": {}}}}, "files"),  # says nothing
        ({"datasets": {"ohlc-test": {**_BLOCK, "files": {"a.parquet": "C" * 64}}}}, "files"),  # uppercase hex
        ({"datasets": {"ohlc-test": {**_BLOCK, "files": {"a.parquet": "c" * 63}}}}, "files"),  # short hex
        ({"datasets": {"ohlc-test": {**_BLOCK, "rows": 0}}}, "rows"),  # zero-extent
        ({"datasets": {"ohlc-test": {**_BLOCK, "rows": True}}}, "rows"),  # bool-as-int
        ({"datasets": {"../infra": dict(_BLOCK)}}, "datasets key must be a relative path"),  # name escapes data/
        ({"datasets": {"ohlc-test": {**_BLOCK, "files": {"": "c" * 64}}}}, "files"),  # empty key
        ({"datasets": {"ohlc-test": {**_BLOCK, "files": {"a\\b.parquet": "c" * 64}}}}, "files"),  # backslash key
        ({"datasets": {"ohlc-test": {**_BLOCK, "files": {"/etc/x": "c" * 64}}}}, "files"),  # absolute key
        ({"datasets": {"ohlc-test": {**_BLOCK, "files": {"../x.parquet": "c" * 64}}}}, "files"),  # escaping key
        ({"datasets": {"ohlc-test": {**_BLOCK, "span": ["a"]}}}, "span"),  # wrong arity
        ({"datasets": {"ohlc-test": {k: v for k, v in _BLOCK.items() if k != "span"}}}, "span"),  # missing key
        ({"datasets": {"ohlc-test": {**_BLOCK, "extra": 1}}}, "datasets entry carries unknown key"),  # surplus
    ],
)
def test_a_forged_schema_four_record_is_rejected_at_load(tmp_path, over, match):
    """D4/D2: the invariant is a property of the FILE, not of append()."""
    with pytest.raises(RegistryCorruptionError, match=match):
        TrialRegistry(_write(tmp_path, [_schema4_line(**over)]))


def test_a_schema_four_record_missing_datasets_entirely_is_rejected(tmp_path):
    line = json.loads(_schema4_line())
    del line["datasets"]
    line["record_hash"] = compute_hash({k: v for k, v in line.items() if k != "record_hash"})
    with pytest.raises(RegistryCorruptionError, match="datasets"):
        TrialRegistry(_write(tmp_path, [canonical_json(line)]))


@pytest.mark.parametrize("bad", ["", 123])
def test_a_stored_schema_three_dataset_hash_must_still_be_a_nonempty_str(tmp_path, bad):
    """This check ran on EVERY load via `validate_caller_fields` until the key became store-owned;
    nothing else covers schema 2/3, so unless re-homed the guard lapses silently."""
    body = json.loads(_line(1))  # the schema-3 helper, pinned to a literal 3 in Step 4
    del body["record_hash"]
    body["dataset_hash"] = bad
    with pytest.raises(RegistryError, match="dataset_hash"):
        TrialRegistry(_write(tmp_path, [canonical_json(dict(body, record_hash=compute_hash(body)))]))


def test_a_record_past_the_legacy_floor_must_declare_schema_four(tmp_path):
    """D4: what actually binds record 47 — built on the REAL 46 records (read-only)."""
    real = _REGISTRY.read_text(encoding="utf-8").splitlines()
    prev = json.loads(real[-1])

    def _line47(**over):
        body = dict(
            trial_id=prev["trial_id"] + 1,
            schema_version=4,
            timestamp="2026-08-09T00:00:00+00:00",
            iteration="iter-001",
            family="FLOOR",
            spec_hash="s",
            seeds=[0],
            metrics={"dsr": 0.1},
            n_trials_in_family=1,
            verdict="adopt",
            run_ref=None,
            notes="",
            prev_hash=prev["record_hash"],
            datasets={"ohlc-test": dict(_BLOCK)},
        )
        body.update(over)
        body["dataset_hash"] = compute_hash(body["datasets"])
        return canonical_json(dict(body, record_hash=compute_hash(body)))

    # Non-vacuous both directions: the same record at schema 4 loads, so the floor is what rejects.
    assert len(TrialRegistry(_write(tmp_path, [*real, _line47()]))) == prev["trial_id"] + 1

    v3 = json.loads(_line47())
    del v3["datasets"], v3["record_hash"]
    v3["schema_version"] = 3
    v3["dataset_hash"] = "ba47e37e2601d6098fd13c0e338a5301e8eeebb16bb4341c76a68147c7b08e42"  # verbatim
    forged = canonical_json(dict(v3, record_hash=compute_hash(v3)))
    with pytest.raises(RegistryCorruptionError, match="schema_version"):
        TrialRegistry(_write(tmp_path, [*real, forged]))


def test_append_revalidates_and_a_bad_block_writes_nothing(tmp_path):
    """One bad line is permanent (append-only, hash-chained) — refuse BEFORE the write."""
    reg = _new_registry(tmp_path)
    with pytest.raises(RegistryError):
        _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-test": {**_BLOCK, "rows": 0}})
    assert not reg.path.exists() or reg.path.read_text() == ""
