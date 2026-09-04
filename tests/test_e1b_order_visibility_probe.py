"""Guard: `infra/scripts/e1b-order-visibility-probe.py` reads the venue with the LIVE trade key on
the engine host. Two things must hold before it is ever run there, and neither is observable once it
is running: it must touch no method that writes to the venue, and it must refuse rather than build a
client when the credentials are absent. Both are asserted here against a stubbed client, because the
only other place they could be checked is an attended run against real money."""

import asyncio
import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PROBE = REPO / "infra/scripts/e1b-order-visibility-probe.py"


def _load():
    """The probe is a script, not a package module: load it by path under a private name."""
    spec = importlib.util.spec_from_file_location("_e1b_probe", PROBE)
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: `@dataclass` under `from __future__ import annotations` resolves its
    # annotations through `sys.modules[cls.__module__]`, which is None for an unregistered module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# The venue-write surface of `KrakenSpotHttpClient`, read from its stub rather than guessed.
# `cancel_all_requests` is deliberately NOT here: it aborts in-flight HTTP requests client-side and
# reaches no venue. It is still in the forbidden set below, because a probe has no reason to call it
# and a future reader should not have to re-derive which `cancel_*` is which.
VENUE_WRITES = frozenset(
    {"submit_order", "submit_orders_batch", "cancel_order", "cancel_orders_batch", "cancel_all_orders", "modify_order"}
)
FORBIDDEN = VENUE_WRITES | {"cancel_all_requests"}


class _Instrument:
    id = "SOL/EUR.KRAKEN"


class _RecordingClient:
    """Records every attribute the probe touches. Returns shapes the probe can walk without a venue."""

    def __init__(self, rows):
        self.touched: list[str] = []
        self._rows = rows

    def __getattr__(self, name):
        self.touched.append(name)
        if name in FORBIDDEN:
            raise AssertionError(f"the probe reached a forbidden method: {name}")

        async def _areader(*args, **kwargs):
            if name == "request_instruments":
                return [_Instrument()]
            return self._rows

        def _sync(*args, **kwargs):
            return None

        return _sync if name == "cache_instrument" else _areader


def test_the_sweep_enumerates_all_eight_shapes_and_no_duplicate():
    """Two booleans and one instrument-id choice: 2x2x2. A missing shape leaves a question the run
    was dispatched to answer unanswered, and a duplicate spends a venue call proving nothing."""
    m = _load()
    keys = [(s.cache_populated, s.open_only, s.by_instrument) for s in m.SHAPES]
    assert len(keys) == 8, f"expected 8 shapes, got {len(keys)}"
    assert len(set(keys)) == 8, f"duplicate shapes: {sorted(k for k in keys if keys.count(k) > 1)}"
    assert {k[0] for k in keys} == {False, True}
    assert {k[1] for k in keys} == {False, True}
    assert {k[2] for k in keys} == {False, True}


def test_flattens_own_shape_is_one_of_the_eight():
    """`cli/engine/flatten.py` reads open orders with `open_only=True`, no `instrument_id`, on a
    client it built bare — so the row that answers 'what does flatten see' must be in the table,
    and must be marked, or the probe reports eight numbers and settles nothing."""
    m = _load()
    flatten_like = [s for s in m.SHAPES if s.open_only and not s.by_instrument and not s.cache_populated]
    assert len(flatten_like) == 1, "exactly one shape is flatten's"
    assert flatten_like[0].is_flatten_shape is True


def test_the_probe_touches_no_write_method():
    """The whole point of the read-only claim. A stub records every attribute reached; any write
    raises. This is the only place the claim can be checked without money on the line."""
    m = _load()
    client = _RecordingClient(rows=[])
    asyncio.run(m.sweep(client, account_id="KRAKEN-001", pair="SOLEUR", instrument_id="SOL/EUR.KRAKEN"))
    reached = set(client.touched)
    assert not (reached & FORBIDDEN), f"forbidden methods reached: {sorted(reached & FORBIDDEN)}"
    assert "request_order_status_reports" in reached, "the probe never made the read it exists for"


def test_the_sweep_makes_exactly_nine_venue_calls():
    """Eight order reads, plus the one `request_instruments` the populated-cache arm needs. Stated
    so a rate-limit question has a number, and so an extra call added later trips this."""
    m = _load()
    client = _RecordingClient(rows=[])
    asyncio.run(m.sweep(client, account_id="KRAKEN-001", pair="SOLEUR", instrument_id="SOL/EUR.KRAKEN"))
    assert client.touched.count("request_order_status_reports") == 8
    assert client.touched.count("request_instruments") == 1


def test_credentials_refuse_when_unset_and_never_echo_a_value(monkeypatch):
    """The refusal names the VARIABLES. A refusal that quotes what it found puts the trade key in a
    terminal and a scrollback."""
    m = _load()
    monkeypatch.delenv(m.API_KEY_VAR, raising=False)
    monkeypatch.setenv(m.API_SECRET_VAR, "s3cr3t-not-a-real-secret")
    with pytest.raises(m.Refusal) as exc:
        m.credentials()
    assert m.API_KEY_VAR in str(exc.value)
    assert "s3cr3t-not-a-real-secret" not in str(exc.value)


def test_credentials_return_both_when_set(monkeypatch):
    """The true positive: an always-refusing guard would pass the test above and be useless."""
    m = _load()
    monkeypatch.setenv(m.API_KEY_VAR, "k")
    monkeypatch.setenv(m.API_SECRET_VAR, "s")
    assert m.credentials() == ("k", "s")


def test_the_client_is_built_exactly_as_flatten_builds_it():
    """`cli/engine/command.py` builds `KrakenSpotHttpClient(key, secret)` and passes nothing else.
    If the probe adds an argument, its empty-cache row stops being flatten's row and the comparison
    the run exists to make is no longer like-for-like."""
    m = _load()
    seen = {}

    class _Ctor:
        def __init__(self, *args, **kwargs):
            seen["args"] = args
            seen["kwargs"] = kwargs

    m.build_client("k", "s", _ctor=_Ctor)
    assert seen["args"] == ("k", "s"), "flatten passes key and secret positionally and nothing more"
    assert seen["kwargs"] == {}, f"flatten passes no keyword arguments; probe passed {seen['kwargs']}"


# --- The attended run, behind an explicit opt-in ------------------------------------------------
# Gated on a variable rather than on reachability: a test that skips when the venue is unreachable
# reports a skip that reads as coverage, and CLAUDE.md names that failure directly. This never runs
# in CI and never runs beside a normal suite; it exists so the attended operator has one command
# that exercises the same code path the probe's `__main__` does.
LIVE_OPT_IN = "ZCRYPTO_E1B_LIVE"


@pytest.mark.skipif(os.environ.get(LIVE_OPT_IN) != "1", reason=f"{LIVE_OPT_IN}=1 not set; this reaches the live venue")
def test_the_live_sweep_returns_every_shape():
    """Attended only, on the engine host, with the credentials in the environment. Asserts shape,
    not content: how many rows each shape returns is the RESULT of the run, never something a test
    should pin — pinning it here would make the probe's own finding a precondition of its passing."""
    m = _load()
    key, secret = m.credentials()
    from nautilus_trader.model import AccountId, InstrumentId

    client = m.build_client(key, secret)
    results = asyncio.run(
        m.sweep(
            client,
            account_id=AccountId(m.ACCOUNT_ID),
            pair=m.PAIR,
            instrument_id=InstrumentId.from_str(m.INSTRUMENT_ID),
        )
    )
    assert len(results) == 8
    assert all(isinstance(count, int) for _, count, _ in results)
    print(m._render(results))


def test_the_shapes_are_ordered_empty_arm_first():
    """`sweep` populates the cache once, on the first shape that asks for it, and never un-populates.
    So the ORDER is load-bearing: a populated shape moved earlier would have every later
    empty-labelled shape read against a populated cache, and both tests above would stay green — one
    is set-based, the other counts calls."""
    m = _load()
    assert [s.cache_populated for s in m.SHAPES] == [False] * 4 + [True] * 4


def test_no_write_method_name_appears_in_the_script_text():
    """The stub above guards the client handed to `sweep`. It cannot see a write on a SECOND client
    built inside the script — a bare `KrakenSpotHttpClient(...)` in `_main`, say — because that
    object never passes through the stub. Scanning the source closes exactly that gap, and it is the
    check the commit message and the changelog entry claim exists."""
    text = PROBE.read_text()
    # A bare substring, not `f"{name}("` or `f".{name}"`: those two miss
    # `getattr(client, "cancel_all_orders")`, which on a SECOND client the stub cannot see either —
    # so the two guards together would both be green on a real write. Measured: the bare form has
    # zero hits on this script today, so it costs nothing. A name assembled from parts
    # ("cancel_all_" + "orders") is beyond any source scan and is not claimed.
    present = sorted(name for name in FORBIDDEN if name in text)
    assert not present, f"write method names in the probe's source: {present}"
