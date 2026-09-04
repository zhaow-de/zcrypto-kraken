"""Guard: `infra/scripts/e1b-order-visibility-probe.py` reads the venue with the LIVE trade key on
the engine host. Two things must hold before it is ever run there, and neither is observable once it
is running: it must touch no method that writes to the venue, and it must refuse rather than build a
client when the credentials are absent. Both are asserted here against a stubbed client, because the
only other place they could be checked is an attended run against real money."""

import asyncio
import hashlib
import importlib.util
import os
import re
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

# Not methods and not writes: `api_key` is an unmasked getter on the real client, so a stray
# `print(client.api_key)` would put the live trade key on a terminal without touching anything the
# write guards watch. The probe takes its credentials as positionals and never needs either name,
# so their absence is checkable and free.
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


def test_the_credential_wrapper_targets_only_the_order_semantics_harness():
    """The probe's docstring tells an operator NOT to reach for `probe-with-vaulted-key.sh`, because
    that wrapper's target is fixed to a harness which places orders. That is a claim about another
    file, so it can rot silently if the wrapper ever grows a program selector — this is what would
    notice."""
    wrapper = (REPO / "infra/scripts/probe-with-vaulted-key.sh").read_text()
    # Comment and blank lines come out first, so re-wording that file's header -- its own subject is
    # which program it runs, so its comments name `.py` files -- never reddens this.
    code = [ln.rstrip() for ln in wrapper.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    body = "\n".join(code)
    # Named first because a digest alone says nothing about WHAT is protected: this wrapper runs one
    # program and the probe's docstring tells operators so.
    programs = sorted(set(re.findall(r"[\w-]+\.py", body)))
    assert programs == ["kraken-order-semantics-probe.py"], (
        f"the wrapper now names {programs}; the probe's docstring says it targets only the "
        "order-semantics harness, and that sentence must change with it"
    )
    # Then the whole executable content, as one value. Six review rounds each closed one spelling of
    # "add a program selector" and each found another: a default-plus-override, an `&&` twin, an
    # annotated rebind, a write to `sys.argv[3]`, an alias in the handoff, an interpreter override, a
    # repo override, `sys.argv.insert`, `printf -v`, a tuple unpack, a loop variable -- and `del
    # sys.argv[3]`, which makes the FIRST CALLER-SUPPLIED ARGUMENT the program. The set of spellings
    # is not enumerable, and every enumeration of it shipped a comment claiming the class. So this
    # stops describing the shape and pins the content: any change to what this wrapper executes,
    # however spelled, lands here. Its code has changed twice in its life (both 2026-08-26), so a
    # real edit costs one paste.
    digest = hashlib.sha256(body.encode()).hexdigest()
    assert digest == "b62790151caec841fcd6270a8d1e079cc153ffeb0e4fed49cbf78b7bb5c2521f", (
        f"probe-with-vaulted-key.sh's executable content changed (now {digest}).\n"
        "This is not a prompt to paste the new digest. Read the wrapper's diff first and answer the "
        "question the probe's docstring makes an operator act on: does it STILL run only "
        "kraken-order-semantics-probe.py, with the target fixed and unselectable? If yes, re-pin. If "
        "no, the docstring's 'must not be used for this' sentence is what has to change."
    )


def test_no_write_method_name_or_credential_accessor_appears_in_the_script_text():
    """The stub above guards the client handed to `sweep`. It cannot see a write on a SECOND client
    built inside the script — a bare `KrakenSpotHttpClient(...)` in `_main`, say — because that
    object never passes through the stub. Scanning the source closes exactly that gap, and it is the
    check the commit message and the changelog entry claim exists."""
    text = PROBE.read_text()
    # A bare substring, not `f"{name}("` or `f".{name}"`: those two miss
    # `getattr(client, "cancel_all_orders")`, which on a SECOND client the stub cannot see either —
    # so the two guards together would both be green on a real write. Measured: the bare form has
    # zero hits on this script today, so it costs nothing. What this does NOT see: a name built at
    # runtime (`"cancel_all_" + orders_var`), and a credential leaked without naming an accessor —
    # `print(key)` or `print(os.environ)`, both reachable in `_main`. Nor a name split across a
    # concatenation: `"cancel_all_" + "orders"` is one constant to CPython but two strings to a
    # reader of the source, and this scan is a reader of the source.
    present = sorted(name for name in FORBIDDEN | CREDENTIAL_ACCESSORS if name in text)
    assert not present, f"write or credential-accessor names in the probe's source: {present}"
    # A write that names no client method at all -- a hand-rolled signed REST call built with httpx --
    # is invisible to the stub AND to the scan above, since it borrows neither the adapter's methods
    # nor its credential properties. Both sides lowercased: HTTP header names are case-insensitive and
    # HTTP/2 lowercases every one on the wire, so `api-sign` is the spelling that actually goes out.
    # The concatenation limit named above applies here too. And unlike the scan above, this one CAN
    # redden on prose -- a comment or docstring writing `private/OpenOrders` trips it -- so say what
    # the calls do ("the eight order-status reads"), never the endpoint path.
    signing = sorted(t for t in ("private/", "api-sign") if t in text.lower())
    assert not signing, f"hand-rolled venue signing in the probe's source: {signing}"
