"""Every reader of a journaled `CycleRecord` is adjudicated: it validates the record, or it is named here with why not.

Scope is the `from_json` sites under `cli/` -- `CycleRecord` readers. A sidecar, venue-record or ops-journal
reader is a different artifact and is not covered here.

`from_json` leaves schema keying, the snapshot no-peek invariant and `final_targets` finiteness to its caller
(its own docstring says so), so the guarantee is a property of each call site. T0194 enumerated the call sites;
this test keeps the enumeration true, because a census in a topic file rots the first time someone adds a reader.
"""

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
CLI = REPO / "cli"

# One row per `from_json` call site under `cli/`: the function it sits in, and how that site gets the guarantee.
# `"validates"` means `validate_record` is called on the record in the same function. `"replays"` means the site
# hands the record to `concordance.replay_cycle`, which validates -- it does NOT mean every branch of the site
# replays: `_evaluate_journal` scores from the gate cache when the evidence fingerprint hits, and that fingerprint
# does not cover the three fields `validate_record` alone checks. Any other value is the reason this reader needs
# neither, and it is checked against the site's own code below.
READERS = {
    ("cli/engine/command.py", "_evaluate_journal"): "replays",
    ("cli/engine/command.py", "replay"): "replays",
    # Reads `completed_at` alone -- and seeds `zcrypto_engine_cycle_success` True beside it, a startup gauge
    # the next cycle overwrites within four hours. Named here because the row must not read as "consumes
    # nothing": it publishes a verdict off an unvalidated record, bounded by that overwrite.
    ("cli/engine/command.py", "_seed_cycle_state"): "completed_at only, plus the startup gauge it seeds",
    ("cli/engine/command.py", "_window_records"): "validates",
    ("cli/engine/cycle.py", "_previous_success"): "validates",
    ("cli/engine/executor.py", "_cycle_records_through"): "validates",
    ("cli/engine/soak.py", "soak_report"): "validates",
}


def _enclosing(tree: ast.Module) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _sites() -> dict[tuple[str, str], ast.AST]:
    """Every `from_json(...)` call under `cli/`, keyed by (path, enclosing function), with that function's node."""
    found: dict[tuple[str, str], ast.AST] = {}
    for (rel, name), (fn, _calls_here) in _sites_with_counts().items():
        found[(rel, name)] = fn
    assert found, "no from_json call site found under cli/ -- the walk is broken, not the tree clean"
    return found


def _sites_with_counts() -> dict[tuple[str, str], tuple[ast.AST, int]]:
    """The same walk, keeping HOW MANY `from_json` calls each function holds.

    The key is (path, function name), so a second call added beside an adjudicated one would otherwise land on a
    row that already says `validates` and be admitted without being read -- which is the likeliest way a new
    reader gets written. The count is asserted below."""
    found: dict[tuple[str, str], tuple[ast.AST, int]] = {}
    for path in sorted(CLI.rglob("*.py")):
        tree = ast.parse(path.read_text())
        parents = _enclosing(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "from_json"):
                continue
            fn: ast.AST = node
            while fn in parents:
                fn = parents[fn]
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    break
            name = getattr(fn, "name", "<module>")
            key = (str(path.relative_to(REPO)), name)
            previous = found.get(key)
            found[key] = (fn, (previous[1] if previous else 0) + 1)
    return found


def _calls(fn: ast.AST, callee: str) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == callee for n in ast.walk(fn))


def test_every_journal_reader_is_adjudicated():
    """A new reader fails here until its row says how it gets the guarantee -- which is the adjudication T0194
    asked for, moved out of the topic file and into something that runs."""
    sites = set(_sites())
    assert sites == set(READERS), (
        f"unadjudicated reader(s): {sorted(sites - set(READERS))}; "
        f"row(s) for a reader that no longer exists: {sorted(set(READERS) - sites)}"
    )


@pytest.mark.parametrize(("site", "how"), sorted(READERS.items()), ids=lambda v: v[1] if isinstance(v, tuple) else v)
def test_the_row_matches_what_the_site_does(site, how):
    """The row is not a promise: a site marked `validates` really calls `validate_record`, one marked `replays`
    really calls into the replay that validates, and one excused really does neither."""
    fn = _sites()[site]
    if how == "validates":
        assert _calls(fn, "validate_record"), f"{site} is marked `validates` and calls no validate_record"
    elif how == "replays":
        assert _calls(fn, "replay_cycle") or _calls(fn, "_replay_one"), (
            f"{site} is marked `replays` and reaches no replay -- `cli.engine.concordance.replay_cycle` is what "
            f"validates on that path"
        )
    else:
        assert not _calls(fn, "validate_record"), (
            f"{site} carries the excuse {how!r} but does call validate_record -- change the row to `validates`"
        )


def test_the_replay_path_is_what_validates_for_the_sites_that_lean_on_it():
    """The two `replays` rows rest on one line in another module; if it moves, those rows are wrong and nothing
    else here would notice."""
    concordance = (CLI / "engine" / "concordance.py").read_text()
    tree = ast.parse(concordance)
    replay = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "replay_cycle"),
        None,
    )
    assert replay is not None, "cli/engine/concordance.py defines no replay_cycle"
    assert _calls(replay, "validate_record"), "replay_cycle no longer validates -- the `replays` rows above are stale"


@pytest.mark.parametrize("site", sorted(READERS), ids=lambda v: v[1] if isinstance(v, tuple) else v)
def test_one_reader_per_adjudicated_function(site):
    """A row is keyed by (path, function), so a SECOND `from_json` in an adjudicated function would inherit that
    row's verdict without anyone reading it -- and adding a call beside an existing one is the likeliest way a
    new reader arrives. One call per row, or the row is split."""
    _fn, calls = _sites_with_counts()[site]
    assert calls == 1, (
        f"{site} holds {calls} `from_json` calls; the table adjudicates the function, so split the function or "
        f"give each call its own adjudicated home"
    )


def _swallowing_try(fn: ast.AST, callee: str) -> ast.Try | None:
    """The `try` around a call to `callee` whose handler swallows -- `pass`, `continue`, or a bare `return`.

    A `validates` row proves only that the call is WRITTEN. A refusal caught and dropped leaves the caller
    holding the record it refused, which is the defect the row exists to deny."""
    parents = _enclosing(fn)
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == callee):
            continue
        up: ast.AST = node
        while up in parents:
            up = parents[up]
            if isinstance(up, ast.Try):
                for handler in up.handlers:
                    body = handler.body
                    if len(body) == 1 and isinstance(body[0], (ast.Pass, ast.Continue)):
                        return up
                    if len(body) == 1 and isinstance(body[0], ast.Return) and body[0].value is None:
                        return up
    return None


@pytest.mark.parametrize(
    "site", sorted(k for k, v in READERS.items() if v == "validates"), ids=lambda v: v[1] if isinstance(v, tuple) else v
)
def test_a_validating_site_does_not_swallow_the_refusal(site):
    """`validates` has to mean the refusal reaches the caller. A `validate_record` inside a `try` whose handler
    passes, continues or returns nothing is a call that reads as a guard and guards nothing."""
    swallowed = _swallowing_try(_sites()[site], "validate_record")
    assert swallowed is None, (
        f"{site} calls validate_record inside a try whose handler drops the error (line "
        f"{getattr(swallowed, 'lineno', '?')}) -- the record it refused is then used anyway"
    )


def test_the_walk_sees_every_call_form_the_tree_uses():
    """The walk matches a bare `from_json(...)`. An attribute call (`journal.from_json(...)`) or an aliased import
    would be invisible to it, so the walk's completeness is asserted here rather than assumed from house style."""
    attribute_calls: list[str] = []
    aliased: list[str] = []
    for path in sorted(CLI.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "from_json":
                attribute_calls.append(f"{path.relative_to(REPO)}:{node.lineno}")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name == "from_json" and alias.asname:
                        aliased.append(f"{path.relative_to(REPO)}:{node.lineno} as {alias.asname}")
    assert not attribute_calls and not aliased, (
        f"a journal read the walk cannot see: attribute calls {attribute_calls}, aliased imports {aliased} -- "
        f"either write it as a bare `from_json(...)` so the table adjudicates it, or widen the walk"
    )
