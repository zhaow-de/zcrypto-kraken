import math

import pytest

from cli.registry.errors import RegistryCorruptionError
from cli.registry.record import SCHEMA_VERSION, VERDICTS, canonical_json, compute_hash, loads_strict


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
