import math

import pytest

from cli.registry.errors import RegistryCorruptionError, RegistryError
from cli.registry.record import (
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
    assert canonical_json({"a": 1, "b": 2}) == a  # key order irrelevant


def test_canonical_json_refuses_to_emit_nan_or_inf():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            canonical_json({"dsr": bad})


def test_compute_hash_stable_and_order_independent():
    h1 = compute_hash({"a": 1, "b": [1, 2]})
    h2 = compute_hash({"b": [1, 2], "a": 1})
    assert h1 == h2 and len(h1) == 64


def test_loads_strict_rejects_bare_nan_token():
    # Python's json HAPPILY round-trips the bare NaN token by default; we must not.
    with pytest.raises(RegistryCorruptionError):
        loads_strict('{"dsr": NaN}')
    for tok in ("Infinity", "-Infinity"):
        with pytest.raises(RegistryCorruptionError):
            loads_strict('{"x": %s}' % tok)


def test_loads_strict_accepts_finite():
    assert loads_strict('{"dsr":0.3,"n":[1,2]}') == {"dsr": 0.3, "n": [1, 2]}


def test_constants():
    assert SCHEMA_VERSION == 1 and VERDICTS == frozenset({"adopt", "reject", "park"})


def _caller(**over):
    f = dict(
        iteration="iter-001",
        family="A1",
        spec_hash="s",
        dataset_hash="d",
        seeds=[0],
        metrics={"sharpe": 0.3, "dsr": 0.1},
        n_trials_in_family=1,
        verdict="adopt",
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
        {"metrics": {}},  # empty
        {"metrics": {"x": float("nan")}},  # flat NaN
        {"metrics": {"cv": {"paths": [0.1, float("inf")]}}},  # NaN/inf buried in a nested list
        {"trial_id": 9},  # caller supplied a store-owned field
    ],
)
def test_invalid_caller_rejected(over):
    with pytest.raises(RegistryError):
        validate_caller_fields(_caller(**over))


def test_seeds_may_be_empty_but_metrics_may_not():
    validate_caller_fields(_caller(seeds=[]))  # deterministic strategy: OK
    with pytest.raises(RegistryError):
        validate_caller_fields(_caller(metrics={}))


def test_stored_record_hash_and_schema_checks():
    body = dict(_caller(), trial_id=1, schema_version=SCHEMA_VERSION, timestamp="2026-07-07T00:00:00+00:00")
    rec = dict(body, record_hash=compute_hash(body))
    validate_stored_record(rec, "x")  # OK
    bad = dict(rec, metrics={"sharpe": 0.9, "dsr": 0.1})  # mutated, hash now stale
    with pytest.raises(RegistryCorruptionError):
        validate_stored_record(bad, "x")
    with pytest.raises(RegistryCorruptionError):
        validate_stored_record(dict(rec, schema_version=999), "x")
