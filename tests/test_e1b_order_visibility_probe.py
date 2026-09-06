"""Guard: `infra/scripts/e1b-order-visibility-probe.py` reads the venue with the LIVE trade key on
the engine host, so before it is ever run there it must touch no method that writes to the venue and
must refuse rather than build a client when the credentials are absent."""

import ast
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
# `cancel_all_requests` aborts in-flight HTTP requests client-side and reaches no venue, but stays in
# FORBIDDEN: a probe has no reason to call it, and which `cancel_*` is which should not be re-derived.
VENUE_WRITES = frozenset(
    {"submit_order", "submit_orders_batch", "cancel_order", "cancel_orders_batch", "cancel_all_orders", "modify_order"}
)
FORBIDDEN = VENUE_WRITES | {"cancel_all_requests"}

# Not writes: `api_key` is an unmasked getter, so a stray `print(client.api_key)` puts the live trade
# key on a terminal without touching anything the write guards watch, and the probe needs neither name.
CREDENTIAL_ACCESSORS = frozenset({"api_key", "api_secret"})


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
    bare client -- that row must be in the table AND marked, or the probe settles nothing."""
    m = _load()
    flatten_like = [s for s in m.SHAPES if s.open_only and not s.by_instrument and not s.cache_populated]
    assert len(flatten_like) == 1, "exactly one shape is flatten's"
    assert flatten_like[0].is_flatten_shape is True


def test_the_probe_touches_no_write_method():
    """The read-only claim, checked in the only place it can be checked without money on the line."""
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
    """The refusal names the VARIABLES: quoting what it found would put the trade key in a scrollback."""
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
    """`cli/engine/command.py` builds `KrakenSpotHttpClient(key, secret)` and nothing else: an
    argument the probe adds would end the like-for-like comparison the run exists to make."""
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
# Gated on a variable, never on reachability: a skip on an unreachable venue reads as coverage. It
# gives an attended operator one command exercising the probe's own `__main__` path.
LIVE_OPT_IN = "ZCRYPTO_E1B_LIVE"


@pytest.mark.skipif(os.environ.get(LIVE_OPT_IN) != "1", reason=f"{LIVE_OPT_IN}=1 not set; this reaches the live venue")
def test_the_live_sweep_returns_every_shape():
    """Attended only. Asserts shape, not content: how many rows a shape returns is the RESULT of the
    run, and pinning it would make the probe's own finding a precondition of its passing."""
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
    """`sweep` populates the cache once and never un-populates, so the ORDER is load-bearing: move a
    populated shape earlier and every later empty-labelled shape reads a populated cache."""
    m = _load()
    assert [s.cache_populated for s in m.SHAPES] == [False] * 4 + [True] * 4


def test_no_write_method_name_or_credential_accessor_appears_in_the_script_text():
    """The stub guards only the client handed to `sweep`: a SECOND client built inside the script
    never passes through it, and scanning the source closes exactly that gap."""
    text = PROBE.read_text()
    # A bare substring, not `f"{name}("` or `f".{name}"`: those miss a name reached through getattr.
    # And no parse replaces it -- this scan is MEANT to read comments and docstrings, absent from any AST.
    # config-selector-ok: containment IS the semantics -- the needle is a name in arbitrary text
    present = sorted(name for name in FORBIDDEN | CREDENTIAL_ACCESSORS if name in text)
    assert not present, f"write or credential-accessor names in the probe's source: {present}"
    # A hand-rolled signed REST call borrows neither the adapter's methods nor its credential
    # properties, so the stub and the scan above both miss it. Lowercased because HTTP/2 lowercases
    # every header name on the wire; prose in the probe naming an endpoint path trips this too.
    # config-selector-ok: containment over the lowercased text is the only selector spanning all three
    signing = sorted(t for t in ("private/", "api-sign") if t in text.lower())
    assert not signing, (
        f"hand-rolled venue signing in the probe's source: {signing} -- or prose naming an endpoint "
        'path, in which case say what the calls do ("the eight order-status reads") instead'
    )


# The locals `credentials()` binds, and the mapping it reads them out of. The scan above forbids the
# ADAPTER's accessors; a print of the script's own local touches none of those names.
CREDENTIAL_BINDINGS = frozenset({"key", "secret"})
_PRINTERS = frozenset({"print", "echo"})  # `print`, and `typer.echo` if the probe ever grows one


def _callee(func: ast.expr) -> str:
    """`print` and `typer.echo` both reduce to the name being called."""
    return func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")


def test_no_print_in_the_probe_reaches_a_credential():
    """`_main` binds `key, secret = credentials()` in the same scope as its prints, so a debugging
    `print(key)` would put the live trade key on the engine host's terminal without naming an
    accessor for `test_no_write_method_name_or_credential_accessor_appears_in_the_script_text`."""
    tree = ast.parse(PROBE.read_text())
    printers = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _callee(n.func) in _PRINTERS]
    # The selection, before the check: an AST walk that finds no printer would pass on anything.
    assert printers, f"no print/echo call found in {PROBE.name} -- the walk selects nothing, so it proves nothing"
    print(f"printer calls selected: {len(printers)} at lines {[n.lineno for n in printers]}")

    reached = [
        f"line {n.lineno}: {sub.id if isinstance(sub, ast.Name) else 'os.environ'}"
        for n in printers
        for arg in (*n.args, *(kw.value for kw in n.keywords))
        for sub in ast.walk(arg)
        if (isinstance(sub, ast.Name) and sub.id in CREDENTIAL_BINDINGS)
        or (isinstance(sub, ast.Attribute) and sub.attr == "environ")
    ]
    assert not reached, f"a print in the probe reaches a credential: {reached}"
