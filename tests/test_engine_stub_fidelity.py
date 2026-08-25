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
`test_every_test_double_in_the_engine_suite_is_classified` walks the
four modules and refuses a double that is not in the table; `test_every_guard_the_table_names_exists`
refuses a table entry whose guard has been renamed or deleted. A new stub is therefore a red test
until somebody says, in writing, what it models.

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

MODULES = (
    "test_engine_executor.py",
    "test_engine_command.py",
    "test_engine_node.py",
    "test_engine_metrics.py",
)

# What the walk must still find per module, so a walker that stops seeing a whole SHAPE of double
# reads as red rather than as a short table. Per module rather than one number for all four: a
# single floor is only ever as strong as the smallest inventory, and lowering it for that module
# silently un-guards every other one. Each sits below its module's real count where the inventory
# is big enough for slack to mean anything -- a floor tracking the count exactly goes red on every
# legitimate stub removal, which is how a guard gets loosened to nothing in one edit. `command` is
# the exception and sits AT its count of three: below it the floor would tolerate losing a third of
# the inventory, which is not a vacuity check at all, so a removal there is meant to be read.
_WALK_FLOOR = {
    "test_engine_executor.py": 9,
    "test_engine_command.py": 3,
    "test_engine_node.py": 4,
    "test_engine_metrics.py": 4,
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

TABLE: dict[str, dict[str, Standin]] = {
    "test_engine_executor.py": {
        # The instrument the executor rounds through. Only the five scalar fields are restated; the
        # two rounding calls are bound off a real CurrencyPair, so the library rounds for real.
        "_fake_instrument": Standin(LIBRARY, "nautilus_trader.model.CurrencyPair", (_OFFERS_EXECUTOR,)),
        "StubCache": Standin(LIBRARY, "nautilus_trader.common.Cache", (_CACHE_SURFACE, _OFFERS_EXECUTOR)),
        "_FlakyOrdersCache": Standin(LIBRARY, "nautilus_trader.common.Cache", (_CACHE_SURFACE, _OFFERS_EXECUTOR)),
        "_PositionReadFails": Standin(LIBRARY, "nautilus_trader.common.Cache", (_CACHE_SURFACE, _OFFERS_EXECUTOR)),
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
    return {n.name for n in _tree(module).body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}


def _discovered_doubles(module: str) -> set[str]:
    """The test doubles a walk can find without being told: every top-level class, plus every
    top-level non-test function that builds a `SimpleNamespace` -- the suite's two stub shapes.

    Deliberately over-broad on the class half: it sweeps in helpers that turn out not to be doubles
    at all, and the table has to say so for each. That is the trade -- a rule tight enough to admit
    only real stubs is a rule that can be stepped around by naming one differently."""
    found = set()
    for n in _tree(module).body:
        if isinstance(n, ast.ClassDef):
            found.add(n.name)
        elif isinstance(n, ast.FunctionDef) and not n.name.startswith("test_"):
            referenced = {s.attr for s in ast.walk(n) if isinstance(s, ast.Attribute)}
            referenced |= {s.id for s in ast.walk(n) if isinstance(s, ast.Name)}
            if "SimpleNamespace" in referenced:
                found.add(n.name)
    return found


@pytest.mark.parametrize("module", MODULES)
def test_every_test_double_in_the_engine_suite_is_classified(module):
    """A new stub is a red test until the table says what it models. Without this, extending the
    suite's stub inventory is invisible -- which is how seven separate restatements each reached
    production behaviour before a human happened to read them."""
    discovered = _discovered_doubles(module)
    assert len(discovered) >= _WALK_FLOOR[module], f"the walk found only {sorted(discovered)} in {module} -- it is checking nothing"
    unclassified = sorted(discovered - set(TABLE[module]))
    assert unclassified == [], f"{module} defines {unclassified}, which the table does not classify"


@pytest.mark.parametrize("module", MODULES)
def test_every_name_the_table_classifies_still_exists(module):
    """The mirror failure: an entry whose subject has been renamed or deleted. It reads as coverage
    and is none -- the same shape as a pinned constant no test consumes."""
    gone = sorted(set(TABLE[module]) - _defined_at_top_level(module))
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
