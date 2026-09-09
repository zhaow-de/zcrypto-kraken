"""Each arm of the docstring gate is seen to move on the edit it exists to catch and to hold on a docstring-only one, and both subcommands are seen to fail as well as to pass."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "infra" / "scripts" / "docstring-gate.py"
_spec = importlib.util.spec_from_file_location("docstring_gate", _SCRIPT)
gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gate
_spec.loader.exec_module(gate)


def _moved(before: str, after: str) -> set[str]:
    """The arms that separate two sources, by name."""
    return {n for n, b, a in zip(gate.ARMS, gate.digests(before), gate.digests(after), strict=True) if b != a}


# --- the arm that the AST fill hides, which is why there are three ---------------------------------


def test_deleting_a_pass_beside_a_docstring_moves_only_the_statement_arm():
    """The case a two-arm gate calls inert: dropping the docstring from `[docstring, pass]` leaves
    `[pass]`, and filling the emptied `[docstring]` leaves `[pass]` too, so the dumps agree."""
    assert _moved('def f():\n    """d."""\n    pass\n', 'def f():\n    """d."""\n') == {"stmt"}


def test_replacing_a_sole_docstring_with_pass_moves_only_the_statement_arm():
    """The same collision from the other side, and the shape that reached merged work: a class whose
    docstring is its whole body becomes `class E(Exception): pass`."""
    assert _moved('class E(Exception):\n    """d."""\n', "class E(Exception):\n    pass\n") == {"stmt"}


def test_a_sole_statement_docstring_cannot_be_deleted_at_all():
    """The operating constraint this implies for the pass: removing it leaves a suite that does not
    parse, so the edit is not writable, and writing `pass` instead is a statement change."""
    with pytest.raises(gate.Refused, match="does not parse"):
        gate.digests('def f():\n    """d."""\n'.replace('    """d."""\n', ""), "<mutant>")


# --- the three that must compare EQUAL, which a naive repair breaks --------------------------------


@pytest.mark.parametrize(
    ("before", "after", "why"),
    [
        ('def f():\n    """d."""\n    return 1\n', 'def f():\n    """rewritten, at length."""\n    return 1\n', "text changed"),
        ('def f():\n    """d."""\n    return 1\n', "def f():\n    return 1\n", "docstring deleted beside a statement"),
        ("x = 1\n", '"""m."""\n\nx = 1\n', "module docstring added"),
    ],
)
def test_a_prose_only_edit_moves_no_arm(before, after, why):
    assert _moved(before, after) == set(), why


def test_adding_a_module_docstring_leaves_the_comment_arm_alone():
    """The two instruments disagree about what a comment is and both are right: a docstring is not a
    `#` comment, so it must not reach the COMMENT stream."""
    assert gate.cmt_arm("# c\nx = 1\n") == gate.cmt_arm('"""m."""\n\n# c\nx = 1\n')


def test_a_module_docstring_added_to_an_EMPTY_module_moves_no_arm():
    """The fill runs for any emptied body, not only one a docstring emptied. An empty module never
    held a docstring, so filling only the stripped ones makes `Module()` differ from
    `Module(body=[Pass()])` and falsifies arm 6 on the pass's most routine edit."""
    assert _moved("", '"""m."""\n') == set()
    assert _moved("# c\n", '"""m."""\n\n# c\n') == set()


def test_the_fill_does_not_blind_an_empty_module_to_a_real_statement():
    """The control beside it: a blanket fill that swallowed any difference would pass the test above
    for the wrong reason."""
    assert _moved("", "x = 1\n") == {"ast", "stmt"}


def test_arms_on_an_empty_module_passes_arm_six_and_names_the_five_it_cannot_build(tmp_path, capsys):
    target = tmp_path / "__init__.py"
    target.write_text("", encoding="utf-8")
    assert gate.run_arms([str(target)]) == 0
    out = capsys.readouterr().out
    assert "[PASS] module docstring added" in out
    assert "arms: 1 passed, 0 failed, 5 not constructible, of 6" in out
    # the name promises the five are NAMED, so the rows are read rather than only counted
    assert out.count("NOT CONSTRUCTIBLE") == 5
    assert "NOT CONSTRUCTIBLE -- no docstring" in out
    assert "NOT CONSTRUCTIBLE -- no function carrying a docstring" in out


# --- the three that must DIFFER -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ('def f():\n    """d."""\n    return 1\n', 'def f():\n    """d."""\n    return 2\n', {"ast"}),
        ('def f():\n    """d."""\n    return 1\n', 'def f():\n    """d."""\n    y = 0\n    return 1\n', {"ast", "stmt"}),
        ("x = 1  # note\n", "x = 1  # NOTE\n", {"cmt"}),
    ],
)
def test_a_code_or_comment_edit_moves_the_arm_that_owns_it(before, after, expected):
    assert _moved(before, after) == expected


# --- the arms subcommand: constructibility is reported, never dropped ------------------------------


_SIX_SHAPES = (
    '"""m."""\n\n'
    "import os\n\n\n"
    "def helper():\n"
    '    """One statement beside the docstring, so `pass deleted` has an anchor."""\n'
    "    return os\n\n\n"
    "def compares(a, b):\n"
    '    """A comparison outside every docstring span -- em dashes here, so a character-offset\n'
    '    splice would over-consume: — — —."""\n'
    "    return a == b\n"
)


def test_every_arm_is_constructible_on_a_file_carrying_all_six_shapes(tmp_path, capsys):
    target = tmp_path / "m.py"
    target.write_text(_SIX_SHAPES, encoding="utf-8")
    assert gate.run_arms([str(target)]) == 0
    out = capsys.readouterr().out
    assert "arms: 6 passed, 0 failed, 0 not constructible, of 6" in out
    assert "NOT CONSTRUCTIBLE" not in out


def test_an_unbuildable_arm_is_named_and_counted_never_omitted(tmp_path, capsys):
    """A short set that certifies on silence is what this reporting refuses: the row appears with its
    reason and the total still accounts for six."""
    target = tmp_path / "m.py"
    target.write_text('def f():\n    """Only a docstring and a return; nothing to compare."""\n    return 1\n', encoding="utf-8")
    gate.run_arms([str(target)])
    out = capsys.readouterr().out
    assert "NOT CONSTRUCTIBLE -- no single-operator ast.Compare outside every docstring span" in out
    assert "arms: 5 passed, 0 failed, 1 not constructible, of 6" in out


def test_the_arms_report_a_failure_when_an_arm_stops_biting(tmp_path, capsys, monkeypatch):
    """The control on the reporter itself. Every other case here ends in PASS, and a driver that
    could only print PASS would be indistinguishable from one that works: with the statement arm
    pinned to a constant, `pass deleted` no longer differs and must be reported FAIL."""
    target = tmp_path / "m.py"
    target.write_text('def f():\n    """d."""\n    pass\n', encoding="utf-8")
    monkeypatch.setattr(gate, "stmt_arm", lambda src, where="<source>": "constant")
    assert gate.run_arms([str(target)]) == 1
    assert "[FAIL] pass deleted" in capsys.readouterr().out


# --- the compare subcommand, in a real repository -------------------------------------------------


def _repo(tmp_path: Path, body: str) -> Path:
    root = tmp_path / "r"
    root.mkdir()
    for argv in (["init", "-q", "."], ["config", "user.email", "a@b.c"], ["config", "user.name", "t"]):
        subprocess.run(["git", *argv], cwd=root, check=True)
    (root / "m.py").write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "m.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    return root


_BASE = 'def f():\n    """d."""\n    pass\n\n\n# a comment\nx = 1\n'


@pytest.mark.parametrize(
    ("after", "code", "verdict", "arm"),
    [
        ('def f():\n    """rewritten entirely."""\n    pass\n\n\n# a comment\nx = 1\n', 0, "INERT", None),
        ('def f():\n    """d."""\n\n\n# a comment\nx = 1\n', 1, "CHANGED", "stmt"),
        ('def f():\n    """d."""\n    pass\n\n\n# a DIFFERENT comment\nx = 1\n', 1, "CHANGED", "cmt"),
    ],
)
def test_compare_passes_a_prose_edit_and_fails_a_code_or_comment_one(tmp_path, capsys, monkeypatch, after, code, verdict, arm):
    """The three rows that make this gate more than `return 0`: it has been seen to fail, and to fail
    on the arm that owns each edit."""
    root = _repo(tmp_path, _BASE)
    (root / "m.py").write_text(after, encoding="utf-8")
    monkeypatch.chdir(root)
    assert gate.main(["compare", "HEAD", "m.py"]) == code
    out = capsys.readouterr().out
    assert out.startswith(verdict)
    if arm:
        assert [line for line in out.splitlines() if "MOVED" in line and line.strip().startswith(arm)]
        assert len([line for line in out.splitlines() if "MOVED" in line]) == 1


def test_the_statement_only_verdict_names_itself_and_the_comment_one_does_not(tmp_path, capsys, monkeypatch):
    """A reader hitting CHANGED on a file whose class body IS its docstring must be told that verdict
    is by design; a reader hitting it for any other reason must not be told something irrelevant."""
    root = _repo(tmp_path, _BASE)
    monkeypatch.chdir(root)

    (root / "m.py").write_text('def f():\n    """d."""\n\n\n# a comment\nx = 1\n', encoding="utf-8")
    gate.main(["compare", "HEAD", "m.py"])
    assert "only the statement count moved" in capsys.readouterr().out

    (root / "m.py").write_text('def f():\n    """d."""\n    pass\n\n\n# other\nx = 1\n', encoding="utf-8")
    gate.main(["compare", "HEAD", "m.py"])
    assert "only the statement count moved" not in capsys.readouterr().out


# --- refusals are distinct from a failed gate -----------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "fragment"),
    [
        (["arms", "README.md"], "not Python files"),
        (["compare", "nosuchrev", "m.py"], "not readable from git"),
    ],
)
def test_a_refusal_exits_two_and_names_the_alternative(tmp_path, capsys, monkeypatch, argv, fragment):
    monkeypatch.chdir(_repo(tmp_path, _BASE))
    assert gate.main(argv) == 2
    assert fragment in capsys.readouterr().err


def test_an_unparseable_file_is_refused_rather_than_reported_inert(tmp_path, capsys, monkeypatch):
    root = _repo(tmp_path, _BASE)
    (root / "m.py").write_text("def f(:\n", encoding="utf-8")
    monkeypatch.chdir(root)
    assert gate.main(["arms", "m.py"]) == 2
    assert "does not parse" in capsys.readouterr().err
