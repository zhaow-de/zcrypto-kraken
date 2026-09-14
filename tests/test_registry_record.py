import math

import pytest

from cli.registry.errors import RegistryCorruptionError, RegistryError
from cli.registry.record import (
    GENESIS_HASH,
    SCHEMA_VERSION,
    VERDICTS,
    canonical_json,
    compute_hash,
    loads_strict,
    validate_caller_fields,
    validate_stored_record,
)


def test_canonical_json_is_deterministic_and_sorted():
    a = canonical_json({"b": 2, "a": 1})
    assert a == '{"a":1,"b":2}'
    assert canonical_json({"a": 1, "b": 2}) == a


def test_canonical_json_refuses_to_emit_nan_or_inf():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            canonical_json({"dsr": bad})


def test_compute_hash_stable_and_order_independent():
    h1 = compute_hash({"a": 1, "b": [1, 2]})
    h2 = compute_hash({"b": [1, 2], "a": 1})
    assert h1 == h2 and len(h1) == 64


def test_loads_strict_rejects_bare_nan_token():
    # json.loads accepts the bare NaN/Infinity tokens by default.
    with pytest.raises(RegistryCorruptionError):
        loads_strict('{"dsr": NaN}')
    for tok in ("Infinity", "-Infinity"):
        with pytest.raises(RegistryCorruptionError):
            loads_strict('{"x": %s}' % tok)


def test_loads_strict_accepts_finite():
    assert loads_strict('{"dsr":0.3,"n":[1,2]}') == {"dsr": 0.3, "n": [1, 2]}


def test_constants():
    assert SCHEMA_VERSION == 4 and VERDICTS == frozenset({"adopt", "reject", "park"})


COMMITTED_PATH = "cli/registry/record.py"  # a real, git-tracked file: run_ref must name one


def _caller(**over):
    f = dict(
        iteration="iter-001",
        family="A1",
        spec_hash="s",
        seeds=[0],
        metrics={"sharpe": 0.3, "dsr": 0.1},
        n_trials_in_family=1,
        verdict="adopt",
        run_ref=COMMITTED_PATH,
    )
    f.update(over)
    return f


def test_valid_caller_passes():
    validate_caller_fields(_caller())


@pytest.mark.parametrize(
    "over",
    [
        {"iteration": ""},
        {"family": 5},
        {"verdict": "maybe"},
        {"seeds": [0, True]},  # bool is not int
        {"n_trials_in_family": True},  # bool is not int
        {"metrics": {}},
        {"metrics": {"x": float("nan")}},  # flat NaN
        {"metrics": {"cv": {"paths": [0.1, float("inf")]}}},  # NaN/inf buried in a nested list
        {"trial_id": 9},  # caller supplied a store-owned field
        {"dataset_hash": "d"},  # store-owned: derived from `datasets`, never claimed
        {"variant": ""},
        {"variant": 123},
    ],
)
def test_invalid_caller_rejected(over):
    with pytest.raises(RegistryError):
        validate_caller_fields(_caller(**over))


def test_variant_is_optional_and_validated():
    validate_caller_fields(_caller())
    validate_caller_fields(_caller(variant="A2-donchian"))


def test_seeds_may_be_empty_but_metrics_may_not():
    validate_caller_fields(_caller(seeds=[]))  # a deterministic strategy has no seeds
    with pytest.raises(RegistryError):
        validate_caller_fields(_caller(metrics={}))


def test_bool_metric_leaf_rejected():
    with pytest.raises(RegistryError):
        validate_caller_fields(_caller(metrics={"flag": True}))


def test_stored_record_hash_and_schema_checks():
    body = dict(
        _caller(),
        trial_id=1,
        schema_version=3,  # v3 semantics: a schema-4 body would additionally need a `datasets` block
        dataset_hash="d",
        timestamp="2026-07-07T00:00:00+00:00",
        prev_hash=GENESIS_HASH,
        run_ref=None,
        notes="",
    )
    rec = dict(body, record_hash=compute_hash(body))
    validate_stored_record(rec, "x")
    bad = dict(rec, metrics={"sharpe": 0.9, "dsr": 0.1})
    with pytest.raises(RegistryCorruptionError):
        validate_stored_record(bad, "x")
    with pytest.raises(RegistryCorruptionError):
        validate_stored_record(dict(rec, schema_version=999), "x")


def test_stored_record_schema_version_variant_compat():
    body_v2 = dict(
        _caller(),
        trial_id=1,
        schema_version=2,
        dataset_hash="d",
        timestamp="2026-07-07T00:00:00+00:00",
        prev_hash=GENESIS_HASH,
        run_ref=None,
        notes="",
    )
    validate_stored_record(dict(body_v2, record_hash=compute_hash(body_v2)), "x")

    body_v3 = dict(
        _caller(),
        trial_id=1,
        schema_version=3,
        dataset_hash="d",
        timestamp="2026-07-07T00:00:00+00:00",
        prev_hash=GENESIS_HASH,
        run_ref=None,
        notes="",
    )
    validate_stored_record(dict(body_v3, record_hash=compute_hash(body_v3)), "x")
    body_v3_variant = dict(body_v3, variant="A2-donchian")
    validate_stored_record(dict(body_v3_variant, record_hash=compute_hash(body_v3_variant)), "x")

    # variant is v3-only
    body_v2_bad = dict(body_v2, variant="A2-donchian")
    with pytest.raises(RegistryCorruptionError):
        validate_stored_record(dict(body_v2_bad, record_hash=compute_hash(body_v2_bad)), "x")

    body_v3_bad = dict(body_v3, variant=42)
    with pytest.raises(RegistryCorruptionError):
        validate_stored_record(dict(body_v3_bad, record_hash=compute_hash(body_v3_bad)), "x")


def test_run_ref_naming_an_existing_repo_relative_file_passes():
    validate_caller_fields(_caller(run_ref=COMMITTED_PATH))
    # free text mixed with a real path still passes: >=1 path-like token must resolve, not all of them.
    validate_caller_fields(_caller(run_ref=f"nightly rerun {COMMITTED_PATH} + notes.txt (seeded)"))


@pytest.mark.parametrize("bad", [None, "", 5, ["x"]])
def test_run_ref_must_be_a_non_empty_str(bad):
    with pytest.raises(RegistryError) as e:
        validate_caller_fields(_caller(run_ref=bad))
    assert "non-empty str" in str(e.value)


def test_run_ref_is_required_not_merely_optional():
    f = _caller()
    del f["run_ref"]
    with pytest.raises(RegistryError):
        validate_caller_fields(f)


def test_scratchpad_run_ref_is_rejected_with_its_own_distinct_message():
    with pytest.raises(RegistryError) as scratch:
        validate_caller_fields(_caller(run_ref="trial47_run.py + trial47_write.py (scratchpad)"))
    with pytest.raises(RegistryError) as unresolved:
        validate_caller_fields(_caller(run_ref="trial47_run.py + trial47_write.py"))
    assert "scratchpad" in str(scratch.value)
    assert str(scratch.value) != str(unresolved.value)
    # the marker is refused even beside a real committed path
    with pytest.raises(RegistryError) as mixed:
        validate_caller_fields(_caller(run_ref=f"{COMMITTED_PATH} (scratchpad)"))
    assert "scratchpad" in str(mixed.value)


def test_scratchpad_marker_is_case_insensitive():
    with pytest.raises(RegistryError) as e:
        validate_caller_fields(_caller(run_ref="trial47_run.py (Scratchpad)"))
    assert "scratchpad" in str(e.value)


def test_run_ref_naming_only_nonexistent_paths_is_rejected():
    with pytest.raises(RegistryError) as e:
        validate_caller_fields(_caller(run_ref="cli/registry/no_such_runner.py"))
    msg = str(e.value)
    assert "cli/registry/no_such_runner.py" in msg
    assert "commit" in msg.lower()  # the remedy


def test_run_ref_with_no_path_like_token_is_rejected():
    with pytest.raises(RegistryError):
        validate_caller_fields(_caller(run_ref="ran it locally, looked fine"))


def test_run_ref_must_be_inside_the_repo():
    # existing is not enough: provenance is a path inside the repo
    for outside in ("/etc/hostname", "../../etc/hostname", "cli/../../etc/hostname"):
        with pytest.raises(RegistryError):
            validate_caller_fields(_caller(run_ref=outside))


def test_run_ref_does_not_accept_a_directory():
    with pytest.raises(RegistryError):
        validate_caller_fields(_caller(run_ref="cli/registry"))


def test_stored_record_validation_stays_lenient_about_run_ref():
    # Append-only: records written before the guard existed must keep loading.
    for legacy in (None, "iter-080 crossfreq_run.py + crossfreq_stage2.py (scratchpad)"):
        body = dict(
            _caller(),
            trial_id=1,
            schema_version=3,
            dataset_hash="d",
            timestamp="2026-07-07T00:00:00+00:00",
            prev_hash=GENESIS_HASH,
            run_ref=legacy,
            notes="",
        )
        validate_stored_record(dict(body, record_hash=compute_hash(body)), "x")
