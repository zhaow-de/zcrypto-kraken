import inspect
import json
from pathlib import Path

import pytest

from cli.registry import GENESIS_HASH, SCHEMA_VERSION, ReadingLedger, RegistryCorruptionError, RegistryError, TrialRegistry
from cli.registry.record import canonical_json, compute_hash
from tests.test_trial_registry_provenance import LEDGER

_REGISTRY = Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl"

_BLOCK = {
    "files": {"BTC/EUR/1440.parquet": "c" * 64},
    "rows": 10,
    "span": ["2020-01-01 00:00:00+00:00", "2020-01-10 00:00:00+00:00"],
}


def _line(trial_id, family="A1", n=1, metrics=None, prev_hash=GENESIS_HASH):
    # The v3 helper: a literal 3, not SCHEMA_VERSION -- a v4 body would need a `datasets` block.
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
        TrialRegistry(_write(tmp_path, [_line(1), _line(3)]))
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [_line(2), _line(1)]))


def test_record_hash_mismatch_raises(tmp_path):
    good = _line(1)
    tampered = good.replace('"sharpe":0.3', '"sharpe":0.9')  # finite->finite edit, hash now stale
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [tampered]))


def test_torn_trailing_line_self_heals(tmp_path):
    p = _write(tmp_path, [_line(1)])
    with p.open("a", encoding="utf-8") as f:
        f.write('{"trial_id":2,"fam')  # crash mid-append, NO trailing newline
    reg = TrialRegistry(p)
    assert len(reg) == 1
    assert p.read_text(encoding="utf-8").endswith("}\n")  # partial line physically truncated


def test_torn_interior_line_raises(tmp_path):
    # the same torn content as an INTERIOR line: only a trailing line can be a torn append
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


COMMITTED_PATH = "cli/registry/record.py"  # a real, git-tracked file: run_ref must name one


def _invocation(datasets: dict, **over) -> dict:
    return {
        "subject": "stub",
        "dataset": next(iter(datasets)),
        "window": None,
        "as_of": None,
        "accept_holes": False,
        "comparator_trial": None,
        "commit": "a" * 40,
        **over,
    }


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
    kw.setdefault("invocation", _invocation(kw["datasets"]))
    return reg.append(**kw)


def test_append_assigns_contiguous_ids_across_reopen(tmp_path):
    p = tmp_path / "t.jsonl"
    r1 = _append(TrialRegistry(p))
    assert r1.trial_id == 1 and r1.record_hash and r1.timestamp.endswith("+00:00")
    r2 = _append(TrialRegistry(p))
    assert r2.trial_id == 2
    assert len(TrialRegistry(p)) == 2


def test_append_rejects_nonfinite_before_writing(tmp_path):
    p = tmp_path / "t.jsonl"
    with pytest.raises(RegistryError):
        _append(TrialRegistry(p), metrics={"dsr": float("nan")})
    assert not p.exists() or p.read_text() == ""


def test_append_family_count_floor(tmp_path):
    p = tmp_path / "t.jsonl"
    _append(TrialRegistry(p), family="A1", n_trials_in_family=1)  # 1st in A1, floor is 1 -> OK
    with pytest.raises(RegistryError):
        _append(TrialRegistry(p), family="A1", n_trials_in_family=1)  # 2nd in A1 needs >= 2


def test_append_then_records_snapshot(tmp_path):
    reg = TrialRegistry(tmp_path / "t.jsonl")
    _append(reg)
    assert reg.records[-1].trial_id == 1


def test_concurrent_registries_get_unique_ids(tmp_path):
    p = tmp_path / "t.jsonl"
    a, b = TrialRegistry(p), TrialRegistry(p)
    _append(a)
    _append(b)  # b re-reads under lock -> id 2, not a duplicate 1
    ids = sorted(r.trial_id for r in TrialRegistry(p).records)
    assert ids == [1, 2]


def test_append_after_torn_trailing_line_self_heal(tmp_path):
    p = _write(tmp_path, [_line(1)])
    with p.open("a", encoding="utf-8") as f:
        f.write('{"trial_id":2,"fam')  # torn append: no trailing newline
    reg = TrialRegistry(p)
    r = _append(reg, family="B1", n_trials_in_family=1)  # 1st in a fresh family -> floor OK
    assert r.trial_id == 2
    assert len(TrialRegistry(p)) == 2


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
    rec = json.loads(lines[1])
    rec["metrics"] = {**rec["metrics"], "sharpe": 999.0}
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
        TrialRegistry(reg.path)


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
    reg2 = TrialRegistry(reg.path)
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
    assert len(TrialRegistry(p)) == 1


def test_append_rejects_invalid_variant_before_writing(tmp_path):
    p = tmp_path / "t.jsonl"
    with pytest.raises(RegistryError):
        _append(TrialRegistry(p), variant="", n_trials_in_family=1)
    assert not p.exists() or p.read_text() == ""
    with pytest.raises(RegistryError):
        _append(TrialRegistry(p), variant=123, n_trials_in_family=1)
    assert not p.exists() or p.read_text() == ""


def test_mixed_v2_and_v4_file_loads_with_intact_chain(tmp_path):
    p = tmp_path / "trials.jsonl"
    l1 = _line_v2(1, n=1)
    l2 = _line_v2(2, n=2, prev_hash=_hash_of(l1))
    p.write_text(l1 + "\n" + l2 + "\n", encoding="utf-8")
    reg = TrialRegistry(p)
    assert len(reg) == 2

    r3 = _append(reg, family="A1", n_trials_in_family=3, variant="A2-donchian")
    assert r3.trial_id == 3
    assert r3.prev_hash == _hash_of(l2)

    fresh = TrialRegistry(p)
    assert [r.trial_id for r in fresh.records] == [1, 2, 3]
    assert fresh.records[0].schema_version == 2 and fresh.records[1].schema_version == 2
    assert fresh.records[2].schema_version == SCHEMA_VERSION
    assert fresh.records[2].variant == "A2-donchian"
    assert fresh.records[1].prev_hash == fresh.records[0].record_hash
    assert fresh.records[2].prev_hash == fresh.records[1].record_hash


def test_v2_record_with_variant_key_is_corruption(tmp_path):
    body = json.loads(_line_v2(1, n=1))
    body["variant"] = "A2-donchian"
    tampered = canonical_json(dict(body, record_hash=compute_hash({k: v for k, v in body.items() if k != "record_hash"})))
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [tampered]))


def test_v3_record_with_nonstr_variant_is_corruption(tmp_path):
    body = dict(
        trial_id=1,
        schema_version=3,
        timestamp="2026-07-07T00:00:00+00:00",
        iteration="iter-001",
        family="A1",
        variant=42,
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
        schema_version=3,
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
        variannt="x",  # deliberately misspelled
    )
    line = canonical_json(dict(body, record_hash=compute_hash(body)))
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [line]))


def test_v2_unknown_key_forge_is_corruption(tmp_path):
    body = json.loads(_line_v2(1, n=1))
    body["extra_key"] = 1
    tampered = canonical_json(dict(body, record_hash=compute_hash({k: v for k, v in body.items() if k != "record_hash"})))
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(_write(tmp_path, [tampered]))


def test_missing_base_key_is_corruption(tmp_path):
    body = dict(
        trial_id=1,
        schema_version=3,
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
        schema_version=3,
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
    rec["variant"] = "tampered"
    lines[0] = canonical_json(rec)
    reg.path.write_text("\n".join(lines) + "\n")
    with pytest.raises(RegistryCorruptionError):
        TrialRegistry(reg.path)


def test_live_registry_file_loads_clean():
    # Read-only: never write to this file. Records 1-32 predate schema 3 and are asserted verbatim;
    # the count is floored, never pinned, because the file grows with every registered trial.
    reg = TrialRegistry(Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl")
    assert len(reg) >= 33  # 32 pre-v3 + the first v3-era record (iter-059, P1)
    pre_v3 = reg.records[:32]
    assert all(r.schema_version == 2 for r in pre_v3)
    assert all(r.variant is None for r in pre_v3)  # trials 25-32 carry their variant in `notes` only
    assert all(r.schema_version >= 3 for r in reg.records[32:])


def test_live_reading_ledger_loads_clean():
    # Read-only, as the registry's: the load runs the ledger's contiguity and chain checks over the committed file.
    ledger = ReadingLedger(LEDGER)
    assert [r.reading_id for r in ledger.records] == list(range(1, len(ledger) + 1))


def test_append_records_a_committed_run_ref_end_to_end(tmp_path):
    p = tmp_path / "t.jsonl"
    r = _append(TrialRegistry(p), n_trials_in_family=1, run_ref=COMMITTED_PATH)
    assert r.run_ref == COMMITTED_PATH
    assert TrialRegistry(p).records[0].run_ref == COMMITTED_PATH


def test_append_rejects_unprovenanced_run_ref_before_writing(tmp_path):
    for bad in ("trial47_run.py (scratchpad)", "cli/registry/no_such_runner.py", "", None):
        p = tmp_path / f"t{hash(str(bad))}.jsonl"
        with pytest.raises(RegistryError):
            _append(TrialRegistry(p), n_trials_in_family=1, run_ref=bad)
        assert not p.exists() or p.read_text() == ""


def test_append_requires_run_ref_explicitly(tmp_path):
    # keyword-only with no default: omitting run_ref is a TypeError, not a recorded null
    reg = TrialRegistry(tmp_path / "t.jsonl")
    datasets = {"ohlc-test": dict(_BLOCK)}
    with pytest.raises(TypeError):
        reg.append(
            iteration="iter-001",
            family="A1",
            spec_hash="s",
            datasets=datasets,
            seeds=[0],
            metrics={"sharpe": 0.3},
            n_trials_in_family=1,
            verdict="adopt",
            invocation=_invocation(datasets),
        )


def test_append_requires_an_invocation_explicitly(tmp_path):
    reg = TrialRegistry(tmp_path / "t.jsonl")
    with pytest.raises(TypeError, match="invocation"):
        reg.append(
            iteration="iter-001",
            family="A1",
            spec_hash="s",
            datasets={"ohlc-test": dict(_BLOCK)},
            seeds=[0],
            metrics={"sharpe": 0.3},
            n_trials_in_family=1,
            verdict="adopt",
            run_ref=COMMITTED_PATH,
        )
    assert not reg.path.exists()


def test_an_appended_invocation_reloads_at_schema_five(tmp_path):
    reg = _new_registry(tmp_path)
    datasets = {"ohlc-test": dict(_BLOCK)}
    _append(reg, family="A", n_trials_in_family=1, datasets=datasets)
    invocation = _invocation(
        datasets,
        subject="b2-funding-derisk",
        window=["2020-01-02 00:00:00+00:00", "2020-01-09 00:00:00+00:00"],
        as_of="2026-10-02",
        accept_holes=True,
        comparator_trial=1,
        commit="0123456789abcdef" * 2 + "01234567",
    )
    written = _append(reg, family="A", n_trials_in_family=2, datasets=datasets, invocation=invocation)
    reloaded = _new_registry(tmp_path).records[-1]
    assert (reloaded.schema_version, reloaded.invocation) == (5, invocation)
    assert written.invocation == invocation


_DATASETS = {"ohlc-test": dict(_BLOCK)}


@pytest.mark.parametrize(
    "invocation, match",
    [
        pytest.param(None, "invocation must be a dict", id="not-a-dict"),
        pytest.param({k: v for k, v in _invocation(_DATASETS).items() if k != "commit"}, r"missing \['commit'\]", id="missing-key"),
        pytest.param(_invocation(_DATASETS, seed=7), r"unknown \['seed'\]", id="extra-key"),
        pytest.param(_invocation(_DATASETS, subject=""), "invocation subject", id="subject-empty"),
        pytest.param(_invocation(_DATASETS, dataset="ohlc-other"), "invocation dataset", id="dataset-not-in-datasets"),
        pytest.param(_invocation(_DATASETS, window=["2020-01-02 00:00:00+00:00"]), "invocation window", id="window-one-str"),
        pytest.param(_invocation(_DATASETS, window=["2020-01-02 00:00:00+00:00", 5]), "invocation window", id="window-str-and-int"),
        pytest.param(_invocation(_DATASETS, as_of="2026-1-1"), "invocation as_of", id="as-of-unpadded"),
        pytest.param(_invocation(_DATASETS, accept_holes=1), "invocation accept_holes", id="accept-holes-int"),
        pytest.param(_invocation(_DATASETS, comparator_trial=0), "invocation comparator_trial", id="comparator-zero"),
        pytest.param(_invocation(_DATASETS, comparator_trial=True), "invocation comparator_trial", id="comparator-bool"),
        pytest.param(_invocation(_DATASETS, comparator_trial=2), "invocation comparator_trial", id="comparator-own-id"),
        pytest.param(_invocation(_DATASETS, commit="a" * 39), "invocation commit", id="commit-39-hex"),
        pytest.param(_invocation(_DATASETS, commit="A" * 40), "invocation commit", id="commit-uppercase-hex"),
    ],
)
def test_an_ill_shaped_invocation_is_refused_before_the_write(tmp_path, invocation, match):
    # Appended as trial 2, so a comparator of True (== 1) is refused by the type check alone and not by the own-id bound.
    reg = _new_registry(tmp_path)
    _append(reg, family="A", n_trials_in_family=1, datasets=_DATASETS)
    before = reg.path.read_text()
    with pytest.raises(RegistryCorruptionError, match=match):
        _append(reg, family="A", n_trials_in_family=2, datasets=_DATASETS, invocation=invocation)
    assert reg.path.read_text() == before


def test_variant_does_not_affect_family_budget_monotonic_check(tmp_path):
    p = tmp_path / "t.jsonl"
    reg = TrialRegistry(p)
    _append(reg, family="A1", n_trials_in_family=1, variant="v1")
    with pytest.raises(RegistryError):
        _append(reg, family="A1", n_trials_in_family=1, variant="v2")
    r2 = _append(reg, family="A1", n_trials_in_family=2, variant="v2")
    assert r2.trial_id == 2


def test_all_46_committed_records_still_load():
    reg = TrialRegistry(_REGISTRY)
    assert len(reg) >= 46  # floored, never pinned: the file grows with every registered trial
    assert all(r.schema_version in (2, 3) or r.datasets for r in reg.records)


def test_append_has_no_dataset_hash_parameter():
    assert "dataset_hash" not in inspect.signature(TrialRegistry.append).parameters


def test_a_schema_five_record_round_trips_through_disk(tmp_path):
    reg = _new_registry(tmp_path)
    written = _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-test": dict(_BLOCK)})
    reloaded = _new_registry(tmp_path).records[-1]
    assert reloaded.schema_version == 5
    assert reloaded.dataset_hash == compute_hash(reloaded.datasets) == written.dataset_hash


def test_different_file_sets_give_different_digests(tmp_path):
    """The slice IS the file list: daily-only vs daily+4h differ by construction (spec 00086 D2)."""
    reg = _new_registry(tmp_path)
    daily = _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-test": dict(_BLOCK)})
    both_files = {**_BLOCK["files"], "BTC/EUR/240.parquet": "d" * 64}
    both = _append(reg, family="B", n_trials_in_family=1, datasets={"ohlc-test": {**_BLOCK, "files": both_files, "rows": 70}})
    assert daily.dataset_hash != both.dataset_hash


def test_a_windowed_read_gives_a_different_digest(tmp_path):
    """The sample window is expressible (spec 00086 D2): same files, different rows/span, different digest."""
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
        ({"dataset_hash": "deadbeef" * 8}, "dataset_hash"),  # spec 00086 D3: derived, never claimed
        ({"datasets": "ba47e37e"}, "datasets must be a non-empty dict"),  # a digest where the block belongs
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
    """spec 00086 D4: the invariant is a property of the FILE, not of append()."""
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
    """spec 00086 D4: a schema-2/3 record has no `datasets` block to derive from, so the non-empty-str
    check at load is the only one its `dataset_hash` gets."""
    body = json.loads(_line(1))
    del body["record_hash"]
    body["dataset_hash"] = bad
    with pytest.raises(RegistryError, match="dataset_hash"):
        TrialRegistry(_write(tmp_path, [canonical_json(dict(body, record_hash=compute_hash(body)))]))


def test_a_record_past_the_floors_must_declare_schema_five(tmp_path):
    """spec 00086 D4's floor at trial 46 and spec 00129 D1's at trial 47 bind the record after the last real one -- built
    on the real file, read-only."""
    real = _REGISTRY.read_text(encoding="utf-8").splitlines()
    prev = json.loads(real[-1])
    next_id = prev["trial_id"] + 1

    def _line_next(**over):
        body = dict(
            trial_id=next_id,
            schema_version=5,
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
            invocation=_invocation({"ohlc-test": dict(_BLOCK)}),
        )
        body.update(over)
        body["dataset_hash"] = compute_hash(body["datasets"])
        return canonical_json(dict(body, record_hash=compute_hash(body)))

    # Non-vacuous both directions: the same record at schema 5 loads, so the floors are what reject.
    assert len(TrialRegistry(_write(tmp_path, [*real, _line_next()]))) == next_id

    v4 = json.loads(_line_next())
    del v4["invocation"], v4["record_hash"]
    v4["schema_version"] = 4
    forged_v4 = canonical_json(dict(v4, record_hash=compute_hash(v4)))
    with pytest.raises(
        RegistryCorruptionError,
        match=f"trial {next_id} declares schema_version 4; every record past trial 47 must be schema_version 5",
    ):
        TrialRegistry(_write(tmp_path, [*real, forged_v4]))

    v3 = json.loads(_line_next())
    del v3["datasets"], v3["invocation"], v3["record_hash"]
    v3["schema_version"] = 3
    v3["dataset_hash"] = "ba47e37e2601d6098fd13c0e338a5301e8eeebb16bb4341c76a68147c7b08e42"  # spec 00086 D4's own example
    forged = canonical_json(dict(v3, record_hash=compute_hash(v3)))
    with pytest.raises(
        RegistryCorruptionError,
        match=f"trial {next_id} declares schema_version 3; every record past trial 46 must be schema_version 4",
    ):
        TrialRegistry(_write(tmp_path, [*real, forged]))


def test_append_revalidates_and_a_bad_block_writes_nothing(tmp_path):
    """One bad line is permanent (append-only, hash-chained) — refuse BEFORE the write."""
    reg = _new_registry(tmp_path)
    with pytest.raises(RegistryError):
        _append(reg, family="A", n_trials_in_family=1, datasets={"ohlc-test": {**_BLOCK, "rows": 0}})
    assert not reg.path.exists() or reg.path.read_text() == ""


_READING_DATASETS = {"ohlc-test": dict(_BLOCK)}


def _append_reading(ledger: ReadingLedger, **over):
    kw = dict(
        iteration="iter-001",
        spec_hash="s",
        invocation=_invocation(_READING_DATASETS),
        datasets=_READING_DATASETS,
        metrics={"sharpe": 0.3, "dsr": 0.1},
        outcome=None,
    )
    kw.update(over)
    return ledger.append(**kw)


def _reading_line(reading_id: int, prev_hash: str = GENESIS_HASH, **over) -> str:
    body = dict(
        reading_id=reading_id,
        schema_version=1,
        timestamp="2026-10-13T00:00:00+00:00",
        iteration="iter-001",
        spec_hash="s",
        invocation=_invocation(_READING_DATASETS),
        datasets=_READING_DATASETS,
        metrics={"sharpe": 0.3},
        outcome=None,
        notes="",
        prev_hash=prev_hash,
    )
    body.update(over)
    body["dataset_hash"] = over.get("dataset_hash", compute_hash(body["datasets"]))
    return canonical_json(dict(body, record_hash=compute_hash(body)))


def test_a_reading_round_trips_through_disk(tmp_path):
    path = tmp_path / "readings.jsonl"
    invocation = _invocation(_READING_DATASETS, subject="b2-arm-a-bar", as_of="2026-10-10", accept_holes=True, comparator_trial=44)
    written = _append_reading(ReadingLedger(path), invocation=invocation, outcome="the stub's stop", notes="kept")

    (reloaded,) = ReadingLedger(path).records

    assert reloaded == written
    assert (reloaded.reading_id, reloaded.schema_version, reloaded.prev_hash) == (1, 1, GENESIS_HASH)
    assert (reloaded.invocation, reloaded.outcome, reloaded.notes) == (invocation, "the stub's stop", "kept")
    assert reloaded.dataset_hash == compute_hash(_READING_DATASETS)
    assert set(json.loads(path.read_text())) == {
        "reading_id",
        "schema_version",
        "timestamp",
        "prev_hash",
        "record_hash",
        "dataset_hash",
        "iteration",
        "spec_hash",
        "invocation",
        "datasets",
        "metrics",
        "outcome",
        "notes",
    }


def test_two_readings_chain_with_contiguous_ids_across_a_reopen(tmp_path):
    path = tmp_path / "readings.jsonl"
    first = _append_reading(ReadingLedger(path))
    second = _append_reading(ReadingLedger(path), outcome="a stop")

    assert (first.reading_id, second.reading_id) == (1, 2)
    assert second.prev_hash == first.record_hash
    assert [r.reading_id for r in ReadingLedger(path).records] == [1, 2]


def test_a_torn_trailing_reading_heals_as_a_torn_trial_does(tmp_path):
    path = tmp_path / "readings.jsonl"
    path.write_text(_reading_line(1) + "\n" + '{"reading_id":2,"iter', encoding="utf-8")

    assert len(ReadingLedger(path)) == 1
    assert path.read_text(encoding="utf-8").endswith("}\n")
    assert _append_reading(ReadingLedger(path)).reading_id == 2


@pytest.mark.parametrize(
    "over, match",
    [
        pytest.param({"outcome": ""}, "outcome", id="outcome-empty"),
        pytest.param({"outcome": 1}, "outcome", id="outcome-int"),
        pytest.param({"invocation": None}, "invocation must be a dict", id="invocation-missing"),
        pytest.param({"metrics": {"dsr": float("nan")}}, "non-finite", id="metrics-nan"),
    ],
)
def test_an_ill_formed_reading_is_refused_before_the_write(tmp_path, over, match):
    path = tmp_path / "readings.jsonl"

    with pytest.raises(RegistryError, match=match):
        _append_reading(ReadingLedger(path), **over)

    assert not path.exists()


def test_a_stored_reading_without_its_invocation_is_refused_at_load(tmp_path):
    body = json.loads(_reading_line(1))
    del body["invocation"], body["record_hash"]
    line = canonical_json(dict(body, record_hash=compute_hash(body)))

    with pytest.raises(RegistryCorruptionError, match=r"missing \['invocation'\]"):
        ReadingLedger(_write(tmp_path, [line]))


@pytest.mark.parametrize(("ids", "out_of_place"), [((1, 3), 3), ((2, 1), 2)], ids=["1-then-3", "2-then-1"])
def test_a_ledger_whose_ids_skip_or_reorder_is_refused_naming_the_reading_out_of_place(tmp_path, ids, out_of_place):
    first = _reading_line(ids[0])
    second = _reading_line(ids[1], prev_hash=_hash_of(first))

    with pytest.raises(RegistryCorruptionError, match=f"reading_id {out_of_place} not contiguous"):
        ReadingLedger(_write(tmp_path, [first, second]))


def test_a_reading_whose_body_changed_under_its_record_hash_is_refused(tmp_path):
    tampered = _reading_line(1).replace('"sharpe":0.3', '"sharpe":0.9')

    with pytest.raises(RegistryCorruptionError, match="record_hash"):
        ReadingLedger(_write(tmp_path, [tampered]))


def test_a_reading_whose_dataset_hash_is_not_its_blocks_digest_is_refused(tmp_path):
    with pytest.raises(RegistryCorruptionError, match="dataset_hash"):
        ReadingLedger(_write(tmp_path, [_reading_line(1, dataset_hash="d" * 64)]))


def test_a_rewritten_first_reading_breaks_the_chain_at_the_second(tmp_path):
    first = _reading_line(1)
    second = _reading_line(2, prev_hash=_hash_of(first))
    rewritten = _reading_line(1, metrics={"sharpe": 0.9})

    with pytest.raises(RegistryCorruptionError, match="reading 2 prev_hash breaks the chain"):
        ReadingLedger(_write(tmp_path, [rewritten, second]))
