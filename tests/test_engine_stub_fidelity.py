"""Every test double in the engine suite, classified: what it stands in for, and how the standing-in
is kept honest.

A stub that stands in for a type this repo does not own is a hand-written restatement of somebody
else's contract, and a restatement nothing checks drifts silently. The failure is not that a test
goes red -- it is that every test stays GREEN while production, driving the real class, raises inside
an `except` that refuses an intent, trips the kill switch, or dies on the live trade path.

The two directions are NOT symmetric, and only one of them is self-policing:

  * A stub MISSING something production calls fails loudly the first time a test runs it -- the call
    raises, and the test that made it goes red. Nothing extra is owed here beyond having the test.
  * A stub OFFERING something the real type LACKS fails nothing at all. Every test simply believes
    the fabricated attribute, forever, and production is the only place the read comes back wrong.
    That direction has to be checked explicitly, and this suite has already paid for not checking
    it: a stub node carrying an attribute the library never had kept the whole `engine run` suite
    green while production raised on that same read, at start, on the live trade path.

So each library stand-in owes both directions -- most cover them in two tests, a few in one -- and
the classification below is what makes "each" checkable.
`test_every_test_double_in_the_engine_suite_is_classified` walks EVERY `test_engine_*.py` in this
directory and refuses a double that is not in the table; `test_every_guard_the_table_names_exists`
refuses a table entry whose guard has been renamed or deleted. A new stub is therefore a red test
until somebody says, in writing, what it models.

The module list is derived from the directory rather than written down, so the file's opening claim
is true rather than aspirational: a hand-written list silently exempts every module nobody
remembered to add, which is how five library stand-ins in the venue-reader suite went unguarded.
The cost is the point -- a NEW `test_engine_*.py` carrying a double is a red run until its doubles
are classified here.

Three verdicts, and the reason the distinction matters:

  LIBRARY       stands in for a type this repo does not own (nautilus, or the stdlib). Checked
                against the real class -- always both directions.
  OURS          stands in for a type this repo owns. The library has no say: the modelled type's own
                tests are its contract, and a drifting stub goes red there rather than silently.
  NOT_A_STANDIN not a test double -- a fixture-environment helper, or a class that models an event
                rather than a type. The doubles such a helper installs are registered on their own.

One fact the table records rather than fixes, because measuring it is the honest answer:
`_fake_instrument`'s `make_qty`/`make_price` are not restatements at all -- they are BOUND off a
real `CurrencyPair` at the leg's precisions, so the library itself does the rounding. Delegation
beats verification wherever the real type is constructible offline, and where it is constructible
the double should not exist at all: the order events, the quote, the commission and the currency
this suite once restated are built from the library's own classes now, and are absent from the
table for that reason.

Nothing here imports the modules it classifies: the walk reads them as source, so this file cannot
be satisfied by a stub and costs no collection-time nautilus import.
"""

import ast
from pathlib import Path
from typing import NamedTuple

import pytest

MODULES = tuple(sorted(p.name for p in Path(__file__).parent.glob("test_engine_*.py") if p.name != Path(__file__).name))

# What the walk must still find per module, so a walker that stops seeing a whole SHAPE of double
# reads as red rather than as a short table. Per module rather than one number for all of them: a
# single floor is only ever as strong as the smallest inventory, and lowering it for that module
# silently un-guards every other one. Each sits below its module's real count where the inventory
# is big enough for slack to mean anything -- a floor tracking the count exactly goes red on every
# legitimate stub removal, which is how a guard gets loosened to nothing in one edit. The small
# inventories sit AT their count: one below, the floor would tolerate losing a third or more of
# them, which is not a vacuity check at all, so a removal there is meant to be read.
#
# Keyed only by the modules that HAVE doubles, in lock-step with the table below (its own test
# holds them there). A module absent from both is one the walk found nothing in, where any floor
# above zero would be a claim rather than a check.
_WALK_FLOOR = {
    "test_engine_concordance.py": 1,
    "test_engine_command.py": 3,
    "test_engine_cycle.py": 4,
    "test_engine_executor.py": 9,
    "test_engine_flatten.py": 7,
    "test_engine_gate_export.py": 1,
    "test_engine_gate_export_cache.py": 1,
    "test_engine_metrics.py": 4,
    "test_engine_node.py": 4,
    "test_engine_soak.py": 1,
    "test_engine_tracking.py": 2,
    "test_engine_venuestate.py": 3,
}

LIBRARY = "library"
OURS = "ours"
NOT_A_STANDIN = "not-a-standin"


class Standin(NamedTuple):
    verdict: str
    models: str  # the real type, or -- for OURS -- the type this repo owns, or why it is not a double
    guards: tuple[str, ...]  # test names, checked to exist; required for LIBRARY, empty otherwise


_OFFERS_EXECUTOR = "test_no_stub_in_this_file_offers_a_name_its_real_nautilus_type_lacks"
_OFFERS_NODE = "test_no_stub_in_this_file_offers_a_name_its_real_library_type_lacks"
_NODE_SURFACE = "test_every_node_surface_engine_run_reaches_exists_on_the_real_type"
_NODE_OFFERS = "test_the_node_stub_offers_nothing_the_real_type_lacks"
_CACHE_SURFACE = "test_every_cache_accessor_the_engine_reaches_exists_on_the_real_cache"
_OFFERS_VENUESTATE = "test_no_stub_in_the_venue_reader_suite_offers_a_name_its_real_library_type_lacks"
_OFFERS_FLATTEN = "test_no_stub_in_the_red_button_suite_offers_a_name_its_real_library_type_lacks"
_BINDS_FLATTEN = "test_the_submit_call_carries_the_library_s_own_types_and_binds_against_the_real_client"

_BUILDER = "cli.engine.concordance.build_crossfreq_system_fast"
_BUILDER_RESULT = "the result cli.engine.concordance.build_crossfreq_system_fast returns"

TABLE: dict[str, dict[str, Standin]] = {
    "test_engine_concordance.py": {
        "_fake_builder": Standin(OURS, _BUILDER, ()),
    },
    "test_engine_cycle.py": {
        "FlakyFetch": Standin(OURS, "cli.ohlc.fetch.fetch_ohlc, the fetch_fn run_cycle is called with", ()),
        "SettleFetch": Standin(OURS, "cli.ohlc.fetch.fetch_ohlc, the fetch_fn run_cycle is called with", ()),
        "SteppingClock": Standin(OURS, "the now-callable cli.engine.cycle.run_cycle is built with", ()),
        "_fake_builder": Standin(OURS, _BUILDER, ()),
        "_sleeve_result": Standin(OURS, _BUILDER_RESULT, ()),
    },
    "test_engine_gate_export.py": {
        "_fake_builder": Standin(OURS, _BUILDER, ()),
    },
    "test_engine_gate_export_cache.py": {
        "_fake_builder": Standin(OURS, _BUILDER, ()),
    },
    "test_engine_soak.py": {
        "_fake_result": Standin(OURS, _BUILDER_RESULT, ()),
    },
    "test_engine_tracking.py": {
        "_Run": Standin(NOT_A_STANDIN, "a value record for one CLI invocation's exit code, output and file mtimes", ()),
        "_Slice": Standin(NOT_A_STANDIN, "a value record naming a copied journal slice and its per-file minimums", ()),
    },
    # The red button drives the venue's HTTP client directly rather than the node, so all but one
    # of its doubles stand in for something the venue hands over. `typing.Any` is what the client's
    # signatures promise, which is why the real answer classes are named per row rather than read
    # off a signature -- the offers guard is what keeps each name, and its KIND, honest against the
    # real class: `_Book` once restated OrderBook's `bids`/`asks` METHODS as plain lists and every
    # name-only check agreed.
    "test_engine_flatten.py": {
        "FakeClient": Standin(LIBRARY, "nautilus_trader.adapters.kraken.KrakenSpotHttpClient", (_BINDS_FLATTEN, _OFFERS_FLATTEN)),
        # `request_instruments()`'s row. Measured against the installed adapter's public listing
        # endpoint, not inferred: the answer is a list of these.
        "_Instrument": Standin(LIBRARY, "nautilus_trader.model.CurrencyPair", (_OFFERS_FLATTEN,)),
        "_Position": Standin(LIBRARY, "nautilus_trader.model.PositionStatusReport", (_OFFERS_FLATTEN,)),
        "_AccountState": Standin(LIBRARY, "nautilus_trader.model.AccountState", (_OFFERS_FLATTEN,)),
        "_Balance": Standin(LIBRARY, "nautilus_trader.model.AccountBalance", (_OFFERS_FLATTEN,)),
        # `request_book_snapshot()`'s answer and one of its levels, measured the same way.
        "_Book": Standin(LIBRARY, "nautilus_trader.model.OrderBook", (_OFFERS_FLATTEN,)),
        "_Level": Standin(LIBRARY, "nautilus_trader.model.BookLevel", (_OFFERS_FLATTEN,)),
        "_StdoutThatDies": Standin(OURS, "the echo-callable cli.engine.flatten.run_flatten is built with", ()),
    },
    "test_engine_venuestate.py": {
        "FakeCache": Standin(LIBRARY, "nautilus_trader.common.Cache", (_CACHE_SURFACE, _OFFERS_VENUESTATE)),
        "_fake_position": Standin(LIBRARY, "nautilus_trader.model.Position", (_OFFERS_VENUESTATE,)),
        # What `Cache.account_for_venue` hands back on a margin account, which is what the engine runs.
        "_fake_account": Standin(LIBRARY, "nautilus_trader.model.MarginAccount", (_OFFERS_VENUESTATE,)),
    },
    "test_engine_executor.py": {
        # The instrument the executor rounds through. Only the five scalar fields are restated; the
        # two rounding calls are bound off a real CurrencyPair, so the library rounds for real.
        "_fake_instrument": Standin(LIBRARY, "nautilus_trader.model.CurrencyPair", (_OFFERS_EXECUTOR,)),
        "StubCache": Standin(LIBRARY, "nautilus_trader.common.Cache", (_CACHE_SURFACE, _OFFERS_EXECUTOR)),
        "_FlakyOrdersCache": Standin(LIBRARY, "nautilus_trader.common.Cache", (_CACHE_SURFACE, _OFFERS_EXECUTOR)),
        "_PositionReadFails": Standin(LIBRARY, "nautilus_trader.common.Cache", (_CACHE_SURFACE, _OFFERS_EXECUTOR)),
        "_UnreadableOrderCache": Standin(LIBRARY, "nautilus_trader.common.Cache", (_CACHE_SURFACE, _OFFERS_EXECUTOR)),
        # `limit(**kwargs)` agrees with every keyword, including ones the real factory rejects, so
        # the calls direction has to bind production's call against the real signature.
        "StubOrderFactory": Standin(
            LIBRARY,
            "nautilus_trader.common.OrderFactory",
            ("test_the_limit_call_the_executor_makes_binds_against_the_real_order_factory", _OFFERS_EXECUTOR),
        ),
        "StubClient": Standin(
            LIBRARY,
            "nautilus_trader.trading.Strategy",
            ("test_every_client_surface_the_executor_reaches_exists_on_the_real_strategy", _OFFERS_EXECUTOR),
        ),
        "_held": Standin(LIBRARY, "nautilus_trader.model.Position", (_OFFERS_EXECUTOR,)),
        "_open_order": Standin(LIBRARY, "nautilus_trader.model.LimitOrder", (_OFFERS_EXECUTOR,)),
        "_closed_order": Standin(LIBRARY, "nautilus_trader.model.LimitOrder", (_OFFERS_EXECUTOR,)),
        "CountingGate": Standin(OURS, "cli.engine.execgate.ExecutionGate", ()),
        "_Clock": Standin(OURS, "the now-callable cli.engine.executor.ProbeExecutor is built with", ()),
        "RecordingMetrics": Standin(OURS, "cli.engine.command._ExecutionMetrics", ()),
    },
    "test_engine_command.py": {
        "_FakeNode": Standin(LIBRARY, "nautilus_trader.live.LiveNode", (_NODE_SURFACE, _NODE_OFFERS)),
        "_fake_node": Standin(LIBRARY, "nautilus_trader.live.LiveNode", (_NODE_SURFACE, _NODE_OFFERS)),
        "_fake_builder": Standin(OURS, "cli.engine.concordance.build_crossfreq_system_fast", ()),
        "_run_env": Standin(
            NOT_A_STANDIN, "assembles a passable `engine run` environment; the doubles it installs are registered separately", ()
        ),
    },
    "test_engine_node.py": {
        "RecordingBuilder": Standin(
            LIBRARY, "nautilus_trader.live.LiveNodeBuilder", ("test_every_builder_call_exists_on_the_library", _OFFERS_NODE)
        ),
        "RecordingLiveNode": Standin(
            LIBRARY,
            "nautilus_trader.live.LiveNode",
            ("test_the_builder_arguments_the_assembly_passes_bind_against_the_real_live_node", _OFFERS_NODE),
        ),
        "FakeClock": Standin(
            LIBRARY,
            "nautilus_trader.common.Clock",
            ("test_every_clock_call_the_strategy_makes_lands_on_the_same_parameters_as_the_real_clock", _OFFERS_NODE),
        ),
        "RecordingExecutor": Standin(OURS, "cli.engine.executor.ProbeExecutor", ()),
        "_exec_stub": Standin(OURS, "cli.engine.node.ShadowStrategy", ()),
    },
    "test_engine_metrics.py": {
        # The names `run()` READS off a node are walked once, over the one production module, in
        # test_engine_command.py -- that walk covers this stub too, so only the offered direction is
        # owed here.
        "_fake_node": Standin(
            LIBRARY,
            "nautilus_trader.live.LiveNode",
            (_NODE_SURFACE, "test_the_stub_node_offers_nothing_the_real_type_lacks"),
        ),
        "_StubGate": Standin(OURS, "cli.engine.execgate.ExecutionGate", ()),
        "_RaisingGate": Standin(OURS, "cli.engine.execgate.ExecutionGate", ()),
        "_SteppingClock": Standin(OURS, "the now-callable cli.engine.command.run() is built with", ()),
        "_fake_builder": Standin(OURS, "cli.engine.concordance.build_crossfreq_system_fast", ()),
    },
}


def _tree(module: str) -> ast.Module:
    return ast.parse((Path(__file__).parent / module).read_text())


def _defined_at_top_level(module: str) -> set[str]:
    """Every top-level name a table entry or a guard reference can point at -- classes and
    functions, plus the names a class factory binds, so the two walks agree on what exists."""
    defined = {n.name for n in _tree(module).body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    return defined | _discovered_doubles(module)


# A class is a class however it is spelled. `X = namedtuple(...)` / `X = type(...)` /
# `X = NamedTuple(...)` bind one to a name through an assignment, which no `ClassDef` walk sees --
# and this suite has already used that spelling for a library stand-in that sat unclassified inside
# a module the walk was reading.
_CLASS_FACTORIES = frozenset({"namedtuple", "type", "NamedTuple"})


def _discovered_doubles(module: str) -> set[str]:
    """The test doubles a walk can find without being told, in one of this directory's modules."""
    return _doubles_in(_tree(module))


def _doubles_in(tree: ast.Module) -> set[str]:
    """The test doubles a walk can find without being told: every top-level class -- defined with
    `class` or bound by a class factory -- plus every top-level non-test function that builds a
    `SimpleNamespace`. Those are the suite's stub shapes.

    Deliberately over-broad on the class half: it sweeps in helpers that turn out not to be doubles
    at all, and the table has to say so for each. That is the trade -- a rule tight enough to admit
    only real stubs is a rule that can be stepped around by naming one differently.

    Takes a parsed tree rather than a module name so the factory branch can be handed a synthetic
    one: it has no live member in this directory today, so nothing else here would notice its
    removal."""
    found = set()
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            found.add(n.name)
        elif isinstance(n, ast.FunctionDef) and not n.name.startswith("test_"):
            referenced = {s.attr for s in ast.walk(n) if isinstance(s, ast.Attribute)}
            referenced |= {s.id for s in ast.walk(n) if isinstance(s, ast.Name)}
            if "SimpleNamespace" in referenced:
                found.add(n.name)
        elif isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            called = n.value.func
            name = called.id if isinstance(called, ast.Name) else getattr(called, "attr", None)
            if name in _CLASS_FACTORIES:
                found |= {t.id for t in n.targets if isinstance(t, ast.Name)}
    return found


# A double in each spelling the factory branch claims to cover, plus assignments it must NOT claim.
# The `class` and SimpleNamespace halves of the walk are floored by real members in every module the
# table covers; this branch has none, so this snippet is its only floor.
_FACTORY_FORMS = """
import collections
from collections import namedtuple
from typing import NamedTuple

BareCall = namedtuple("BareCall", "a b")
DottedCall = collections.namedtuple("DottedCall", "a")
BuiltinType = type("BuiltinType", (), {})
TypedTuple = NamedTuple("TypedTuple", [("a", int)])

not_a_double = dict(a=1)
also_not = sorted([3, 1])
plain_value = 5
"""


def test_the_class_factory_branch_of_the_walk_finds_an_assignment_form_double():
    """The branch's own floor, and the only one it has.

    `X = namedtuple(...)` binds a class through an assignment, which no `ClassDef` walk sees -- and
    this suite has already carried a library stand-in in exactly that spelling, sitting unclassified
    inside a module the walk was reading. Nothing in this directory is spelled that way TODAY, so
    deleting the branch re-opens that blind spot with every test still green. This is what goes red.

    Both directions are asserted from one snippet. Discovering the four factory forms is the
    true positive; the three ordinary assignments beside them are the true negative, without which a
    branch that simply claimed every assignment target would pass."""
    found = _doubles_in(ast.parse(_FACTORY_FORMS))

    assert found == {"BareCall", "DottedCall", "BuiltinType", "TypedTuple"}, sorted(found)
    assert {"not_a_double", "also_not", "plain_value"}.isdisjoint(found)


@pytest.mark.parametrize("module", MODULES)
def test_every_test_double_in_the_engine_suite_is_classified(module):
    """A new stub is a red test until the table says what it models. Without this, extending the
    suite's stub inventory is invisible -- which is how seven separate restatements each reached
    production behaviour before a human happened to read them."""
    discovered = _discovered_doubles(module)
    floor = _WALK_FLOOR.get(module, 0)
    assert len(discovered) >= floor, f"the walk found only {sorted(discovered)} in {module} -- it is checking nothing"
    unclassified = sorted(discovered - set(TABLE.get(module, {})))
    assert unclassified == [], f"{module} defines {unclassified}, which the table does not classify"


@pytest.mark.parametrize("module", MODULES)
def test_every_name_the_table_classifies_still_exists(module):
    """The mirror failure: an entry whose subject has been renamed or deleted. It reads as coverage
    and is none -- the same shape as a pinned constant no test consumes."""
    gone = sorted(set(TABLE.get(module, {})) - _defined_at_top_level(module))
    assert gone == [], f"the table classifies {gone}, which {module} no longer defines"


def test_every_guard_the_table_names_exists():
    """A named guard that no longer exists is the table asserting coverage it does not have. Checked
    across the whole engine suite rather than per module, because one walk over one production
    module can cover a stub in another file."""
    defined = set().union(*(_defined_at_top_level(module) for module in MODULES))
    named = {guard for entries in TABLE.values() for entry in entries.values() for guard in entry.guards}
    assert len(named) >= 8, f"the table names only {sorted(named)} -- it is checking nothing"
    missing = sorted(named - defined)
    assert missing == [], f"the table names {missing}, which no module in the engine suite defines"


def test_the_table_and_the_floor_cover_the_same_modules():
    """Both are keyed only by the modules the walk finds doubles in, so they have to agree. A table
    entry with no floor is an inventory nothing measures; a floor with no table entry is a number
    guarding a module whose doubles are unclassified. Every key must also name a module that still
    exists -- a renamed file leaves both behind, silently."""
    assert set(TABLE) == set(_WALK_FLOOR), f"table {sorted(set(TABLE) ^ set(_WALK_FLOOR))} is not floored in lock-step"
    assert set(TABLE) <= set(MODULES), f"the table names {sorted(set(TABLE) - set(MODULES))}, which this directory does not hold"
    empty = sorted(module for module in TABLE if not _discovered_doubles(module))
    assert empty == [], f"the table classifies {empty}, where the walk now finds no double at all"


def test_every_library_standin_names_a_guard_and_nothing_else_does():
    """The verdict is what decides whether guards are owed, so it cannot be decorative. A LIBRARY
    entry with no guard is an unverified restatement wearing a label; an OURS entry that names one
    is a classification somebody got wrong in the safe-looking direction."""
    for module, entries in TABLE.items():
        for name, entry in entries.items():
            where = f"{module}::{name}"
            assert entry.verdict in (LIBRARY, OURS, NOT_A_STANDIN), f"{where} carries an unknown verdict {entry.verdict!r}"
            assert entry.models, f"{where} says nothing about what it models"
            if entry.verdict == LIBRARY:
                assert len(entry.guards) >= 1, f"{where} stands in for {entry.models} and names no guard"
            else:
                assert entry.guards == (), f"{where} is {entry.verdict} and should owe no library guard"
