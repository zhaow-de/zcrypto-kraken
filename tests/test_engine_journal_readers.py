"""Every reader of a journal artifact is adjudicated: it validates the record, or it is named here with why not.

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
# `"validates"` means `validate_record` is called on the record in the same function. Any other value is the
# reason this reader does not need it, and it is checked against the site's own code below.
READERS = {
    ("cli/engine/command.py", "_evaluate_journal"): "replays",
    ("cli/engine/command.py", "replay"): "replays",
    ("cli/engine/command.py", "_seed_cycle_state"): "completed_at only",
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
            found[(str(path.relative_to(REPO)), name)] = fn
    assert found, "no from_json call site found under cli/ -- the walk is broken, not the tree clean"
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
