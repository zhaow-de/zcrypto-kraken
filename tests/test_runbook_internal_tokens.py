"""`infra/scripts/runbook-internal-tokens.py`: an internal token inside a runbook bullet or numbered
step is a hit, one in a paragraph is not, and one inside a real path is the operand it looks like.
One line per BULLET, whatever it carries, because the entry counting them is named for bullets."""

import importlib.util
import pathlib
import subprocess
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "infra" / "scripts" / "runbook-internal-tokens.py"


def _load():
    spec = importlib.util.spec_from_file_location("runbook_internal_tokens", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["runbook_internal_tokens"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def instrument():
    module = _load()
    return lambda text: module.hits(
        text,
        module._load(module._GUARD, "guidance_guard"),
        module._load(module._VOCABULARY, "internal_terms_vocabulary"),
    )


def test_a_token_in_a_bullet_is_a_hit_and_one_in_a_paragraph_is_not(instrument):
    """The rule binds a step, because that is what an operator acts on from a phone; the prose keeps
    the provenance for a claim the tree cannot otherwise re-derive."""
    found = instrument("- **Do the thing** because T0123 says so.\n\nThe paragraph explains T0456.\n")
    assert found == [(1, "T0123")], found


def test_a_numbered_step_is_read_like_a_bullet(instrument):
    found = instrument("1. **Read it.** The blindness is registered as T0123.\n")
    assert found == [(1, "T0123")], found


def test_a_token_on_a_wrapped_item_s_continuation_line_is_the_item_s_hit(instrument):
    """A wrapped bullet is one block at its first line, so a token below the fold does not escape by
    sitting on a line that is not itself a list item."""
    found = instrument("- **Disarm the band** while a record predating the key is\n  still in the window, T0123.\n")
    assert found == [(1, "T0123")], found


def test_a_token_inside_a_real_path_is_the_operand_it_looks_like(instrument):
    """You need the exact name to open the file — the vocabulary test's own PATH_LIKE rule, which
    this instrument reads rather than restates."""
    assert instrument("- **Open** `docs/open-topics/T0123-live-venue.md` and read it.\n") == []


def test_a_fenced_block_is_not_prose_and_the_step_under_it_still_is(instrument):
    """Two halves in one text: `spec 00106` inside the command an operator pastes is not vocabulary
    aimed at them, and the step's own prose under that block is still the step's. A blank line ends
    an item in `bullets()`, so the block sits directly under the step, as a page writes it."""
    text = "- **Run it** and read the output.\n  ```\n  zcrypto engine replay --spec 00106\n  ```\n  Then record T0123.\n"
    assert instrument(text) == [(1, "T0123")]


def test_every_spelling_of_the_vocabulary_reaches_the_instrument(instrument):
    """The classes are the vocabulary test's, not this file's: Phase, T, iter, spec, the work-package
    token and a spec decision number. A class this instrument silently could not see would be a hole
    nothing else covers, since the pages are outside every surface that test walks.

    The work-package token is assembled rather than written: it stays out of every tracked file but
    the carriers `test_internal_terms_not_operator_visible.py` records, and that allowlist is never
    widened -- so a fixture that needs the token builds it.
    """
    wp = "WP" + "3"
    found = instrument(f"- **A bullet** citing Phase 6a, T0123, iter-117, spec 00052, {wp} and D5a in one breath.\n")
    assert len(found) == 1, f"one bullet is one line: {found}"
    assert found[0][1].split(", ") == ["Phase 6", "T0123", "iter-117", "spec 00052", wp, "D5a"], found


def test_a_bullet_carrying_several_tokens_is_one_line(instrument):
    """The count is bullets: three tokens in one step are one finding to fix, and the line still says
    which three, so the reader does not have to open the page to know."""
    found = instrument("- **A step** registered as T0123, T0456 and spec 00052.\n")
    assert found == [(1, "T0123, T0456, spec 00052")], found


def test_the_tracked_pages_carry_no_token_in_a_bullet():
    """The count the corpus reads, asserted where CI runs it: the entry's own set, from the index
    rather than the working tree, so an untracked scratch page cannot turn the suite red."""
    listed = subprocess.run(
        ["git", "-C", str(_ROOT), "ls-files", "infra/runbooks/*.md"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    pages = [p for p in listed if "/" not in p[len("infra/runbooks/") :] and not p.endswith("README.md")]
    assert len(pages) > 10, f"the glob found {len(pages)} pages — it is broken, not the tree clean"
    run = subprocess.run(
        [sys.executable, str(_SCRIPT), *pages],
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout == "", f"a bullet carries an internal token:\n{run.stdout}"
