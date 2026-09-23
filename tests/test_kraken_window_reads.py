"""Guard: `infra/scripts/kraken-window-reads.py` reads the live account with the trade key inside the
attended window, so it must send nothing but reads, refuse rather than build a client without
credentials, and give the verdict the window acts on. Driven here with the real client against the
loopback venue in `tests/kraken_loopback.py`; nothing leaves 127.0.0.1."""

import ast
import asyncio
import importlib.util
import sys
from pathlib import Path

import nautilus_trader.adapters.kraken
import pytest

from tests import kraken_loopback

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra/scripts/kraken-window-reads.py"
BTC_TXID = "OBTCAA-BBBBB-CCCCC1"
SOL_TXID = "OSOLAA-BBBBB-CCCCC2"


def _load():
    """A script, not a package module: loaded by path under a private name."""
    spec = importlib.util.spec_from_file_location("_kraken_window_reads", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wr = _load()


@pytest.fixture(autouse=True)
def _no_client_for_the_real_venue(monkeypatch):
    """The script's own `build_client` points at the real venue. Every test hands the script a
    loopback client instead, so a path that builds its own raises here rather than dialling out."""

    def _refuse(*_args, **_kwargs):
        raise AssertionError("the script built a client for the real venue")

    monkeypatch.setattr(nautilus_trader.adapters.kraken, "KrakenSpotHttpClient", _refuse)


@pytest.fixture
def venue():
    with kraken_loopback.serve() as served:
        served.open_orders = {
            BTC_TXID: kraken_loopback.open_order("XBTEUR", price="20000.0", volume="0.00010000"),
            SOL_TXID: kraken_loopback.open_order("SOLEUR", price="50.00", volume="0.06000000"),
        }
        yield served


def _run(mode, venue, *txids):
    read = wr.orders if mode == "orders" else wr.absent

    async def go():
        return await read(kraken_loopback.client(venue), list(txids))

    return asyncio.run(go())


def _verdict(capsys) -> str:
    return capsys.readouterr().out.splitlines()[-1]


def test_orders_reads_safe_when_both_unscoped_shapes_see_each_target_once(venue, capsys):
    """The XBTEUR-spelled order is read as BTC/EUR, and the open_only=False shape is really issued:
    it is the one that pages ClosedOrders."""
    assert _run("orders", venue, BTC_TXID, SOL_TXID) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == "SAFE"
    assert "-- cache FULL, unscoped, open_only=True:" in out
    assert "-- cache FULL, unscoped, open_only=False:" in out
    assert f"{BTC_TXID} instrument_id=BTC/EUR.KRAKEN" in out
    assert "ClosedOrders" in venue.private_calls


def test_the_scoped_read_is_printed_as_a_contrast_and_never_decides(venue, capsys):
    """On this wheel the scoped BTC/EUR read comes back empty while the order rests, and the verdict
    is still SAFE: that is the case the contrast line exists for."""
    assert _run("orders", venue, BTC_TXID, SOL_TXID) == 0
    lines = capsys.readouterr().out.splitlines()
    scoped = {
        iid: [line for line in lines if f"-- contrast, not the verdict: scoped {iid}, open_only=True:" in line] for iid in wr.SCOPED
    }
    assert all(len(found) == 1 for found in scoped.values()), scoped
    assert scoped["BTC/EUR.KRAKEN"][0].endswith("-> 0 row(s)")
    assert lines[-1] == "SAFE"


def test_orders_reads_hazard_when_a_target_is_not_open(venue, capsys):
    del venue.open_orders[BTC_TXID]
    assert _run("orders", venue, BTC_TXID, SOL_TXID) == 1
    verdict = _verdict(capsys)
    assert verdict == (
        f"HAZARD: cache FULL, unscoped, open_only=True: 0 row(s) carry {BTC_TXID}; "
        f"cache FULL, unscoped, open_only=False: 0 row(s) carry {BTC_TXID}"
    )


def test_orders_reads_hazard_and_prints_the_adapter_s_error_when_an_unscoped_read_raises(venue, capsys):
    venue.open_orders["OETHAA-BBBBB-CCCCC3"] = kraken_loopback.open_order("ETHEUR", price="1000.0", volume="0.01000000")
    assert _run("orders", venue, BTC_TXID, SOL_TXID) == 1
    out = capsys.readouterr().out
    assert "OpenOrders: instrument not in cache for pair ETHEUR" in out
    assert (
        out.splitlines()[-1] == "HAZARD: cache FULL, unscoped, open_only=True raised; cache FULL, unscoped, open_only=False raised"
    )


def test_a_round_trip_longer_than_one_tick_is_a_hazard(venue, capsys, monkeypatch):
    monkeypatch.setattr(wr, "ONE_TICK_SECS", 0.0)
    assert _run("orders", venue, BTC_TXID, SOL_TXID) == 1
    verdict = _verdict(capsys)
    assert "open_only=True: round trip" in verdict
    assert "open_only=False: round trip" in verdict


@pytest.mark.parametrize("mode", ["orders", "absent"])
def test_a_listing_that_cannot_be_read_gives_no_verdict(venue, capsys, mode):
    venue.errors["AssetPairs"] = "EService:Unavailable"
    assert _run(mode, venue, BTC_TXID) == 3
    out = capsys.readouterr().out
    assert "-- listing FAILED" in out
    assert "SAFE" not in out
    assert "HAZARD" not in out


def test_absent_reads_safe_once_no_target_is_open(venue, capsys):
    """An order that is not a target, left resting, does not count."""
    venue.open_orders = {"OOTHER-BBBBB-CCCCC9": kraken_loopback.open_order("SOLEUR", price="40.00", volume="0.06000000")}
    assert _run("absent", venue, BTC_TXID, SOL_TXID) == 0
    assert _verdict(capsys) == "SAFE"


def test_absent_reads_hazard_while_a_target_is_still_open(venue, capsys):
    del venue.open_orders[SOL_TXID]
    assert _run("absent", venue, BTC_TXID, SOL_TXID) == 1
    assert _verdict(capsys) == f"HAZARD: still open at the venue: {BTC_TXID}"


def test_absent_reads_hazard_when_the_read_raises(venue, capsys):
    venue.open_orders = {"OETHAA-BBBBB-CCCCC3": kraken_loopback.open_order("ETHEUR", price="1000.0", volume="0.01000000")}
    assert _run("absent", venue, BTC_TXID) == 1
    verdict = _verdict(capsys)
    assert verdict.startswith("HAZARD: the unscoped read raised after ")
    assert verdict.endswith("OpenOrders: instrument not in cache for pair ETHEUR")


def test_both_modes_send_nothing_but_reads(venue):
    """What reached the venue, read off the wire: the listing's fee read and the order reads, and
    nothing else -- the check that also covers a client the script might build for itself."""
    _run("orders", venue, BTC_TXID, SOL_TXID)
    _run("absent", venue, BTC_TXID, SOL_TXID)
    assert set(venue.private_calls) == {"TradeVolume", "OpenOrders", "ClosedOrders"}


@pytest.mark.parametrize("argv", [[], ["orders"], ["absent", " "], ["cancel", BTC_TXID]])
def test_main_reads_nothing_on_a_usage_error(capsys, argv):
    assert wr.main(argv) == 2
    assert capsys.readouterr().out == "usage: kraken-window-reads.py orders|absent <TXID>...\n"


def test_main_refuses_without_credentials_and_never_echoes_a_value(monkeypatch, capsys):
    """Exit 2, never 1: an operator reads 1 as HAZARD. The refusal names the VARIABLES."""
    monkeypatch.delenv(wr.API_KEY_VAR, raising=False)
    monkeypatch.setenv(wr.API_SECRET_VAR, "s3cr3t-not-a-real-secret")
    assert wr.main(["orders", BTC_TXID]) == 2
    out = capsys.readouterr().out
    assert out == f"refusing: {wr.API_KEY_VAR} not set in the environment\n"


def test_credentials_return_both_when_set(monkeypatch):
    """The true positive: an always-refusing guard would pass the test above and be useless."""
    monkeypatch.setenv(wr.API_KEY_VAR, "k")
    monkeypatch.setenv(wr.API_SECRET_VAR, "s")
    assert wr.credentials() == ("k", "s")


@pytest.mark.parametrize(("mode", "code"), [("orders", 0), ("absent", 1)])
def test_main_runs_the_named_mode_on_the_client_it_builds_from_the_environment(venue, monkeypatch, capsys, mode, code):
    monkeypatch.setenv(wr.API_KEY_VAR, "k-from-env")
    monkeypatch.setenv(wr.API_SECRET_VAR, "s-from-env")
    built = []

    def _build(key, secret):
        built.append((key, secret))
        return kraken_loopback.client(venue)

    monkeypatch.setattr(wr, "build_client", _build)
    assert wr.main([mode, BTC_TXID, SOL_TXID]) == code
    assert built == [("k-from-env", "s-from-env")]


def test_the_client_is_built_as_the_red_button_builds_it(monkeypatch):
    """`cli/engine/command.py` builds `KrakenSpotHttpClient(key, secret)` and nothing else: a
    `base_url` or any other argument here would point the window's read somewhere the engine's is not."""
    seen = {}

    class _Ctor:
        def __init__(self, *args, **kwargs):
            seen.update(args=args, kwargs=kwargs)

    monkeypatch.setattr(nautilus_trader.adapters.kraken, "KrakenSpotHttpClient", _Ctor)
    wr.build_client("k", "s")
    assert seen == {"args": ("k", "s"), "kwargs": {}}


# The venue-write surface of `KrakenSpotHttpClient`, read from its stub. `cancel_all_requests` aborts
# in-flight requests client-side and reaches no venue, but a read-only script has no reason to call it.
FORBIDDEN = frozenset(
    {
        "submit_order",
        "submit_orders_batch",
        "cancel_order",
        "cancel_orders_batch",
        "cancel_all_orders",
        "modify_order",
        "cancel_all_requests",
    }
)
# Not writes: `api_key` is an unmasked getter, so a stray print of it puts the live trade key on a
# terminal without touching anything the wire check watches.
CREDENTIAL_ACCESSORS = frozenset({"api_key", "api_secret"})


def test_no_write_method_name_or_credential_accessor_appears_in_the_script_text():
    """The source, comments and docstrings included: a name reached through getattr never parses as a call."""
    text = SCRIPT.read_text()
    # config-selector-ok: containment IS the semantics -- the needle is a name in arbitrary text
    present = sorted(name for name in FORBIDDEN | CREDENTIAL_ACCESSORS if name in text)
    assert not present, f"write or credential-accessor names in the script's source: {present}"
    # A hand-rolled signed REST call borrows neither the adapter's methods nor its credential
    # properties. Lowercased because HTTP/2 lowercases every header name on the wire.
    # config-selector-ok: containment over the lowercased text is the only selector spanning all three
    signing = sorted(token for token in ("private/", "api-sign") if token in text.lower())
    assert not signing, f"hand-rolled venue signing in the script's source: {signing}"


# The names `credentials()` binds in `main`, and the mapping it reads them out of.
CREDENTIAL_BINDINGS = frozenset({"key", "secret"})


def test_no_print_in_the_script_reaches_a_credential():
    """`main` binds `key, secret = credentials()` in the same scope as its prints, so a debugging
    `print(key)` would put the live trade key on the operator's terminal."""
    tree = ast.parse(SCRIPT.read_text())
    printers = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"]
    # The selection, before the check: a walk that finds no print would pass on anything.
    assert printers, f"no print call found in {SCRIPT.name} -- the walk selects nothing, so it proves nothing"
    reached = [
        f"line {n.lineno}: {sub.id if isinstance(sub, ast.Name) else 'os.environ'}"
        for n in printers
        for arg in (*n.args, *(kw.value for kw in n.keywords))
        for sub in ast.walk(arg)
        if (isinstance(sub, ast.Name) and sub.id in CREDENTIAL_BINDINGS)
        or (isinstance(sub, ast.Attribute) and sub.attr == "environ")
    ]
    assert not reached, f"a print in the script reaches a credential: {reached}"
