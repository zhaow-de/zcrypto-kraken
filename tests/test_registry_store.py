import json

import pytest

from cli.registry import GENESIS_HASH, SCHEMA_VERSION, RegistryCorruptionError, RegistryError, TrialRegistry
from cli.registry.record import canonical_json, compute_hash


def _line(trial_id, family="A1", n=1, metrics=None, prev_hash=GENESIS_HASH):
    body = dict(
        trial_id=trial_id,
        schema_version=SCHEMA_VERSION,
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


def _append(reg, **over):
    kw = dict(
        iteration="iter-001",
        family="A1",
        spec_hash="s",
        dataset_hash="d",
        seeds=[0],
        metrics={"sharpe": 0.3, "dsr": 0.1},
        n_trials_in_family=2,
        verdict="adopt",
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
