"""The inertness prover: a green from it is cited as why a change skipped a Fable review, so it must be able to fail."""

import importlib.util
import pathlib
import subprocess
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "prove-inert.py"


def _load():
    spec = importlib.util.spec_from_file_location("prove_inert", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["prove_inert"] = module
    spec.loader.exec_module(module)
    return module


pi = _load()

# Production-shaped rather than a toy: a module docstring, a class, a method, a comment, a guard.
BEFORE = '''"""Read a series and refuse a stamp outside the plausible range."""

MIN_TS = 1_000_000_000


class Reader:
    """One sentence of contract."""

    def read(self, rows: list[int]) -> list[int]:
        """Rows whose stamp is implausible are refused rather than reinterpreted."""
        # A stamp in another unit casts cleanly, so nothing above sees it.
        return [r for r in rows if r >= MIN_TS]
'''


def test_a_prose_only_cut_is_inert() -> None:
    after = BEFORE.replace('        """Rows whose stamp is implausible are refused rather than reinterpreted."""\n', "")
    result = pi.compare(BEFORE, after)
    assert result.ast_inert, result.detail
    assert result.comments_same


def test_a_planted_behavioural_change_is_reported_with_what_changed() -> None:
    after = BEFORE.replace("r >= MIN_TS", "r > MIN_TS")
    result = pi.compare(BEFORE, after)
    assert not result.ast_inert
    # WHICH difference, not merely that there was one: a bare boolean cannot be read.
    assert "GtE()" in result.detail and "Gt()" in result.detail  # `Gt()` is not a substring of `GtE()`


def test_a_body_that_is_only_a_docstring_does_not_false_trip() -> None:
    # The case that defeated the ad-hoc strippers: stripping empties the body, and a naive
    # comparison reports the statement-count change as a code change.
    before = 'class E(Exception):\n    """Raised on a bad thing."""\n'
    after = "class E(Exception):\n    pass\n"
    result = pi.compare(before, after)
    assert result.ast_inert, result.detail


def test_a_comment_only_change_separates_the_two_arms() -> None:
    after = BEFORE.replace("# A stamp in another unit casts cleanly, so nothing above sees it.", "# Reworded.")
    result = pi.compare(BEFORE, after)
    assert result.ast_inert, result.detail
    assert not result.comments_same


def test_identical_sources_are_inert_on_both_arms() -> None:
    result = pi.compare(BEFORE, BEFORE)
    assert result.ast_inert and result.comments_same


def test_the_entry_point_refuses_with_no_arguments() -> None:
    done = subprocess.run([sys.executable, str(_SCRIPT)], capture_output=True, text=True, cwd=_ROOT)
    assert done.returncode == 2
    assert "usage" in done.stderr.lower()
