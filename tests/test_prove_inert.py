"""The inertness prover: a green from it is cited as why a change skipped a Fable review, so it must be able to fail."""

import importlib.util
import pathlib
import subprocess
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "prove-inert.py"


def _load():
    spec = importlib.util.spec_from_file_location("prove_inert", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["prove_inert"] = module
    spec.loader.exec_module(module)
    return module


pi = _load()

# Production-shaped rather than a toy.
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


def test_a_docstring_that_was_the_whole_body_is_not_certified() -> None:
    # `pass` deleted must differ and a docstring deleted must not, so the scope where the docstring IS
    # the body cannot satisfy both -- and a tool that certifies takes the refusing side of that.
    before = 'class E(Exception):\n    """Raised on a bad thing."""\n'
    after = "class E(Exception):\n    pass\n"
    result = pi.compare(before, after)
    assert not result.ast_inert
    assert "non-docstring statements per scope: [1, 0]" in result.detail


def test_a_deleted_pass_is_not_an_emptied_body() -> None:
    """The count, not the fill, tells the two apart -- the fill renders them as the same tree."""
    body = 'def f() -> None:\n    """Do nothing."""\n'
    result = pi.compare(body + "    pass\n", body)
    assert not result.ast_inert
    assert "non-docstring statements per scope: [1, 1]" in result.detail
    assert "non-docstring statements per scope: [1, 0]" in result.detail


def test_a_docstring_added_to_an_empty_module_stays_inert() -> None:
    """An empty `__init__.py` is a real before-side, so the fill must not be the statement it adds."""
    assert pi.compare("", '"""The package."""\n').ast_inert


def test_a_docstring_deleted_beside_other_statements_stays_inert() -> None:
    """The true positive beside the arm above: the count moves only when a statement does."""
    before = 'def f(x: int) -> int:\n    """Return it."""\n    return x\n'
    after = "def f(x: int) -> int:\n    return x\n"
    assert pi.compare(before, after).ast_inert


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
    assert done.returncode == pi.EXIT_USAGE
    assert "usage" in done.stderr.lower()


def test_the_usage_text_names_every_code_the_tool_can_return() -> None:
    """The contract is read at the moment of use, so a code the constants carry is named there."""
    done = subprocess.run([sys.executable, str(_SCRIPT)], capture_output=True, text=True, cwd=_ROOT)
    codes = (pi.EXIT_INERT, pi.EXIT_CODE_CHANGED, pi.EXIT_USAGE, pi.EXIT_COMMENTS_CHANGED, pi.EXIT_REFUSED)
    assert len(set(codes)) == 5
    for code in codes:
        assert f"exit {code}" in done.stderr, f"exit {code} is not named: {done.stderr}"


COMMAND = '''"""Module docstring, ordinary prose."""


@app.command(name="capture")
def capture(pair: str) -> None:
    """Stream the venue's book for PAIR."""
    run(pair)


def helper(x: int) -> int:
    """An ordinary helper's contract."""
    return x
'''


def test_a_command_docstring_is_program_output_and_is_refused() -> None:
    # A Typer command's docstring IS its `--help` body, which `operator-facing-text.md` puts in scope.
    after = COMMAND.replace('"""Stream the venue\'s book for PAIR."""', '"""Stream the venue\'s book for PAIR (Phase 3)."""')
    result = pi.compare(COMMAND, after)
    assert result.ast_inert  # the code really is unchanged
    assert result.output_docstring_changed, "a --help body changed and must not be certified prose-only"


def test_an_ordinary_helper_docstring_beside_it_is_still_inert() -> None:
    after = COMMAND.replace('"""An ordinary helper\'s contract."""', '"""Reworded contract."""')
    result = pi.compare(COMMAND, after)
    assert result.ast_inert
    assert not result.output_docstring_changed


def test_a_module_docstring_is_refused_when_the_module_hands_it_to_argparse() -> None:
    before = '"""Tool description, printed by argparse."""\n\nP = ArgumentParser(description=__doc__)\n'
    after = before.replace("Tool description, printed by argparse.", "Reworded description.")
    assert pi.compare(before, after).output_docstring_changed
    # ... and a module that never mentions __doc__ keeps its docstring as prose.
    plain = '"""Just prose."""\n\nX = 1\n'
    assert not pi.compare(plain, plain.replace("Just prose.", "Reworded")).output_docstring_changed


def test_module_and_async_docstrings_are_stripped() -> None:
    # Dropping either from _HOLDS_DOCSTRING leaves the commonest edit in the repo reading as a change.
    mod = '"""One."""\nX = 1\n'
    assert pi.compare(mod, '"""Two."""\nX = 1\n').ast_inert
    coro = 'async def f():\n    """One."""\n    return 1\n'
    assert pi.compare(coro, 'async def f():\n    """Two."""\n    return 1\n').ast_inert


def test_a_leading_non_string_expression_is_not_treated_as_a_docstring() -> None:
    # The isinstance(..., str) guard: a bare leading constant is a statement, not prose.
    before = "def f():\n    42\n    return 1\n"
    after = "def f():\n    return 1\n"
    assert not pi.compare(before, after).ast_inert


def _repo(tmp_path: pathlib.Path, body: str) -> pathlib.Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(tmp_path), "config", k, v], check=True)
    (tmp_path / "m.py").write_text(body)
    subprocess.run(["git", "-C", str(tmp_path), "add", "m.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "base"], check=True)
    return tmp_path


def _cli(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_SCRIPT), *args], capture_output=True, text=True, cwd=cwd)


def test_the_entry_point_exits_zero_on_a_prose_only_pair(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, 'def f():\n    """One."""\n    return 1\n')
    (repo / "m.py").write_text('def f():\n    """Two."""\n    return 1\n')
    done = _cli(repo, "HEAD", "m.py")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "m.py: INERT" in done.stdout


def test_the_entry_point_exits_nonzero_on_a_code_change(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, "def f():\n    return 1\n")
    (repo / "m.py").write_text("def f():\n    return 2\n")
    done = _cli(repo, "HEAD", "m.py")
    assert done.returncode == 1, done.stdout
    assert "CODE CHANGED" in done.stdout


def test_the_entry_point_refuses_a_revision_it_cannot_read(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, "X = 1\n")
    done = _cli(repo, "no-such-rev", "m.py")
    assert done.returncode == pi.EXIT_REFUSED, done.stdout
    assert "cannot read" in done.stdout


def test_the_entry_point_does_not_certify_a_comment_only_change(tmp_path: pathlib.Path) -> None:
    # A suppression directive is a comment a tool READS, so a changed comment stream is not prose.
    repo = _repo(tmp_path, "X = 1  # noqa: E501\n")
    (repo / "m.py").write_text("X = 1\n")
    done = _cli(repo, "HEAD", "m.py")
    assert done.returncode == 3, done.stdout
    assert "COMMENTS CHANGED" in done.stdout


def test_prose_merely_naming_dunder_doc_does_not_make_a_module_docstring_output() -> None:
    # The detection is a USE of the name, not a substring: this file's own docstring names it.
    before = '"""Prose that mentions __doc__ without using it."""\n\nX = 1\n'
    after = before.replace("Prose that mentions __doc__ without using it.", "Reworded prose.")
    assert not pi.compare(before, after).output_docstring_changed


def test_a_command_registered_by_call_is_found_in_the_real_entry_module() -> None:
    # `capture`, `liquidations` and `liquidations_poll` carry no decorator: they are registered from
    # `cli/__main__.py`, so a per-file scan cannot see that their docstring is a `--help` body.
    names = pi.registered_command_names((_ROOT / "cli" / "__main__.py").read_text())
    assert {"capture", "liquidations", "liquidations_poll"} <= names


def test_a_call_registered_command_docstring_is_refused() -> None:
    before = 'def capture(pair: str) -> None:\n    """Stream the book."""\n    run(pair)\n'
    after = before.replace("Stream the book.", "Stream the book (Phase 3).")
    assert pi.compare(before, after, output_names=frozenset({"capture"})).output_docstring_changed
    # Without the registration the same function is an ordinary helper and stays certifiable.
    assert not pi.compare(before, after).output_docstring_changed


def test_a_code_change_outranks_a_comment_change_across_paths(tmp_path: pathlib.Path) -> None:
    # The exit codes are an interface, so their NUMBERS cannot carry severity: aggregating by max()
    # made a run with one code change and one comment change exit 3, which a caller treating 0-or-3
    # as prose-only would certify.
    repo = _repo(tmp_path, "X = 1\n")
    (repo / "b.py").write_text("Y = 1  # keep\n")
    subprocess.run(["git", "-C", str(repo), "add", "b.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "b"], check=True)
    (repo / "m.py").write_text("X = 2\n")  # code changed
    (repo / "b.py").write_text("Y = 1\n")  # comment changed
    for order in (("m.py", "b.py"), ("b.py", "m.py")):
        done = _cli(repo, "HEAD", *order)
        assert done.returncode == 1, f"{order}: {done.stdout}"


def test_a_group_callback_docstring_is_program_output() -> None:
    # A Typer group callback's docstring is the group's `--help` body. Matched on the attribute, not
    # on the decorator's dump: a bare `@app.callback()` mentions neither `command` nor a keyword.
    before = 'def main() -> None:\n    """Group help."""\n    pass\n'
    after = before.replace("Group help.", "Reworded group help.")
    assert not pi.compare(before, after).output_docstring_changed
    decorated = "@app.callback()\n" + before
    assert pi.compare(decorated, "@app.callback()\n" + after).output_docstring_changed


def test_the_entry_point_exits_four_on_a_changed_command_docstring(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, '@app.command()\ndef go() -> None:\n    """Old help."""\n    pass\n')
    (repo / "m.py").write_text('@app.command()\ndef go() -> None:\n    """New help."""\n    pass\n')
    done = _cli(repo, "HEAD", "m.py")
    assert done.returncode == 4, done.stdout
    assert "REFUSED" in done.stdout


def test_every_call_registered_form_names_its_function() -> None:
    """A registration is selected by parsing the hook, so neither the argument's form nor the hook's."""
    main = (
        "app.command(name='capture')(capture)\n"
        "app.command(name='poll')(fn=poll)\n"
        "app.command(name='flat')(mod.flat)\n"
        "app.callback()(root)\n"
        "app.add_typer(other, name='commandeer')\n"
    )
    assert pi.registered_command_names(main) == frozenset({"capture", "poll", "flat", "root"})


def test_the_entry_point_refuses_a_docstring_another_file_pins_through_doc(tmp_path: pathlib.Path) -> None:
    # `pinned` carries no decorator and no registration, so only the cross-file `__doc__` scan can see
    # it -- and `loose`, edited identically in the same run, is what says the scan did the deciding.
    base = 'def pinned() -> None:\n    """Old contract."""\n    run()\n\n\ndef loose() -> None:\n    """Old note."""\n    run()\n'
    repo = _repo(tmp_path, base)
    (repo / "reads.py").write_text("import m\n\nassert m.pinned.__doc__\n")
    subprocess.run(["git", "-C", str(repo), "add", "reads.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "reader"], check=True)

    (repo / "m.py").write_text(base.replace('"""Old note."""', '"""New note."""'))
    loose = _cli(repo, "HEAD", "m.py")
    assert loose.returncode == pi.EXIT_INERT, loose.stdout

    (repo / "m.py").write_text(base.replace('"""Old contract."""', '"""New contract."""'))
    done = _cli(repo, "HEAD", "m.py")
    assert done.returncode == pi.EXIT_REFUSED, done.stdout


def test_the_entry_point_reads_the_entry_module_for_call_registered_commands(tmp_path: pathlib.Path) -> None:
    # `capture` carries no decorator; only `cli/__main__.py` says its docstring is a `--help` body.
    repo = _repo(tmp_path, 'def capture(pair: str) -> None:\n    """Old help."""\n    run(pair)\n')
    entry = repo / "cli" / "__main__.py"
    entry.parent.mkdir(parents=True)
    entry.write_text('from m import capture\n\napp.command(name="capture")(capture)\n')
    subprocess.run(["git", "-C", str(repo), "add", "cli/__main__.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "entry"], check=True)
    (repo / "m.py").write_text('def capture(pair: str) -> None:\n    """New help."""\n    run(pair)\n')
    done = _cli(repo, "HEAD", "m.py")
    assert done.returncode == 4, done.stdout


def test_a_docstring_read_through_an_attribute_is_output() -> None:
    reader = "assert clause in mod.run_flatten.__doc__\n"
    assert pi.docstring_reader_names(reader) == frozenset({"run_flatten"})
    before = 'def run_flatten():\n    """Old."""\n    return 1\n'
    after = before.replace("Old.", "New.")
    assert pi.compare(before, after, output_names=frozenset({"run_flatten"})).output_docstring_changed
    # Without a reader the same function is ordinary prose and stays certifiable.
    assert not pi.compare(before, after).output_docstring_changed


def test_the_real_tree_reads_run_flattens_docstring() -> None:
    # `tests/test_engine_flatten.py` asserts on `flatten.run_flatten.__doc__`; `run_flatten` carries
    # no decorator, so nothing else in this tool can see that its docstring is pinned.
    names = pi.docstring_reader_names((_ROOT / "tests" / "test_engine_flatten.py").read_text())
    assert "run_flatten" in names


def test_a_relocated_comment_is_not_the_same_comment_stream() -> None:
    # Same text, same order: only the comment's position relative to what it annotates moved, which
    # is what `test_the_exemption_window_is_the_comparisons_own` pins for the marker guard.
    before = "x = 1\n# marker\nassert x\ny = 2\n"
    after = "x = 1\nassert x\n# marker\ny = 2\n"
    result = pi.compare(before, after)
    assert result.ast_inert
    assert not result.comments_same


def test_a_comment_that_keeps_its_successors_token_still_moved() -> None:
    # The defect neither identity nor distance can see: the marker slides onto the NEXT `assert`, so
    # its column, its own text, its successor's token and the distance to it are all unchanged.
    before = "# marker\nassert a\nb = 1\nassert c\n"
    after = "assert a\nb = 1\n# marker\nassert c\n"
    assert pi.comment_stream(before) == [(0, "# marker", "assert a", 1)]
    assert pi.comment_stream(after) == [(0, "# marker", "assert c", 1)]
    result = pi.compare(before, after)
    assert result.ast_inert
    assert not result.comments_same


def test_a_reindented_comment_is_not_the_same_comment_stream() -> None:
    """The column is part of the fingerprint, which the tool's own exit-3 contract names."""
    before = "if x:\n    # marker\n    pass\n"
    after = "if x:\n  # marker\n    pass\n"
    result = pi.compare(before, after)
    assert result.ast_inert
    assert not result.comments_same


def test_a_docstring_read_through_a_bare_name_is_output() -> None:
    """The bare-`Name` owner, beside the `mod.fn.__doc__` form the tree happens to use."""
    assert pi.docstring_reader_names("assert run_flatten.__doc__\n") == frozenset({"run_flatten"})
    assert pi.docstring_reader_names("assert flatten.run_flatten.__doc__\n") == frozenset({"run_flatten"})


def test_a_tree_it_cannot_list_is_refused(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A listing that fails under-collects the names every refusal is driven by, so it refuses -- and the
    CODE is the claim: REFUSED, never the 1 that would tell a caller the diff was read and moved."""
    with pytest.raises(SystemExit) as raised:
        pi.output_names_in(tmp_path)
    assert raised.value.code == pi.EXIT_REFUSED
    assert "cannot list the tree" in capsys.readouterr().err


def test_a_cwd_outside_any_repo_is_a_usage_error_not_a_code_change(tmp_path: pathlib.Path) -> None:
    """The shape this setup produces routinely: a scratch worktree is removed while a shell still sits in
    it. The operator fixes that by moving, so it is EXIT_USAGE with the contract printed -- and never 1,
    which an agent reading WHICH code fired would record as CODE CHANGED for a file never compared."""
    done = _cli(tmp_path, "HEAD", "cli/engine/flatten.py")
    assert done.returncode == pi.EXIT_USAGE, done.stdout + done.stderr
    assert "not inside a git worktree" in done.stderr, done.stderr
    assert "exit 0  INERT" in done.stderr, "the contract is what EXIT_USAGE prints"


def test_a_closure_read_from_another_checkout_is_refused_rather_than_judged(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The third resolution base. `replay_closure` reads the INSTALLED package's root; if that is a second
    clone whose closure has grown, a member of the judged tree sits outside `relative` and can reach INERT.
    Refused instead, so the guard covers all three bases rather than two."""
    monkeypatch.setattr(pi, "replay_closure", lambda: (frozenset({"cli/engine/flatten.py"}), pathlib.Path("/nonexistent-checkout")))
    monkeypatch.chdir(_ROOT)
    assert pi.main(["prove-inert.py", "HEAD", "cli/engine/flatten.py"]) == pi.EXIT_USAGE
    assert "not the tree being judged" in capsys.readouterr().err


def test_a_file_it_cannot_parse_is_counted_not_skipped(tmp_path: pathlib.Path) -> None:
    """An unscannable file is counted, so the run can say the scan was incomplete."""
    repo = _repo(tmp_path, "X = 1\n")
    (repo / "broken.py").write_text("def (:\n")
    subprocess.run(["git", "-C", str(repo), "add", "broken.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "broken"], check=True)
    names, unscanned = pi.output_names_in(repo)
    assert unscanned == 1, names


def test_a_docstring_cut_leaves_the_comment_stream_alone() -> None:
    # The true positive beside it: the commonest prose-only edit must not read as a comment change.
    before = 'def f():\n    """Doc."""\n    # marker\n    return 1\n'
    after = "def f():\n    # marker\n    return 1\n"
    result = pi.compare(before, after)
    assert result.ast_inert
    assert result.comments_same


def test_a_replay_closure_member_is_refused_rather_than_certified() -> None:
    """A prose-only edit to a file `replay_fingerprint` digests is not inert: it changes the gate's cache key."""
    done = _cli(_ROOT, "HEAD", "cli/engine/flatten.py")
    assert done.returncode == pi.EXIT_REFUSED, done.stdout + done.stderr
    assert "digests this file" in done.stdout, done.stdout


def test_each_spelling_of_a_closure_member_is_refused_never_certified(tmp_path: pathlib.Path) -> None:
    """The list with the arm each row must refuse THROUGH, so a refusal for the wrong reason is not green.
    Membership folds `./`, `//` and an interior `..`; the two it does not fold reach `_at_revision`, which
    holds at the toplevel only -- `git show` resolves `../` against cwd -- so `main` refuses any other cwd,
    asserted below. `./a/../b` certified INERT before the normalisation; the pair below is the true positive."""
    closure = pi.replay_closure()
    assert not isinstance(closure, str), closure
    relative, _ = closure
    assert "cli/engine/flatten.py" in relative, "the member must be in the closure, or this proves nothing"

    spellings = [
        ("cli/engine/flatten.py", "digests this file"),
        ("./cli/engine/flatten.py", "digests this file"),
        ("cli//engine/flatten.py", "digests this file"),
        ("cli/engine/../engine/flatten.py", "digests this file"),
        ("./cli/engine/../engine/flatten.py", "digests this file"),
        (str(_ROOT / "cli/engine/flatten.py"), "cannot read"),
        (f"../{_ROOT.name}/cli/engine/flatten.py", "cannot read"),
    ]
    for spelling, arm in spellings:
        done = _cli(_ROOT, "HEAD", spelling)
        assert done.returncode == pi.EXIT_REFUSED, f"{spelling}: {done.stdout}{done.stderr}"
        assert "INERT" not in done.stdout, f"{spelling} certified a closure member: {done.stdout}"
        assert arm in done.stdout, f"{spelling} refused through the wrong arm: {done.stdout}"

    off_root = _cli(_ROOT / "cli", "HEAD", "engine/flatten.py")
    assert off_root.returncode == pi.EXIT_USAGE, off_root.stdout + off_root.stderr
    assert "run from the repo root" in off_root.stderr, off_root.stderr

    repo = _repo(tmp_path, 'def f():\n    """One."""\n    return 1\n')
    (repo / "m.py").write_text('def f():\n    """Two."""\n    return 1\n')
    clean = _cli(repo, "HEAD", "m.py")
    assert clean.returncode == 0, clean.stdout + clean.stderr


def test_the_closure_is_read_repo_relative_against_the_tree_it_describes() -> None:
    """Repo-relative, so it still matches when the installed package is a different checkout of the same tree."""
    closure = pi.replay_closure()
    assert not isinstance(closure, str), closure
    relative, closure_root = closure
    assert {"cli/engine/flatten.py", "cli/engine/executor.py"} <= relative
    assert (closure_root / "cli" / "engine" / "flatten.py").is_file()
    assert not [path for path in relative if path.startswith("/")]
    assert "tests/test_prove_inert.py" not in relative


def test_nothing_is_certified_when_the_closure_cannot_be_read(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unknown membership refuses, and NAMES its cause: nobody can fix an invocation the refusal never described."""
    repo = _repo(tmp_path, 'def f():\n    """One."""\n    return 1\n')
    (repo / "m.py").write_text('def f():\n    """Two."""\n    return 1\n')
    monkeypatch.chdir(repo)
    monkeypatch.setattr(pi, "replay_closure", lambda: "ModuleNotFoundError: no module named 'cli'")
    assert pi.main(["prove-inert.py", "HEAD", "m.py"]) == pi.EXIT_REFUSED
    assert "ModuleNotFoundError" in capsys.readouterr().out


def test_a_member_of_another_checkouts_closure_is_refused_by_its_relative_spelling(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The installed package can be a DIFFERENT checkout; that tree digests the same relative paths, unseen here."""
    repo = _repo(tmp_path, 'def f():\n    """One."""\n    return 1\n')
    (repo / "m.py").write_text('def f():\n    """Two."""\n    return 1\n')
    monkeypatch.chdir(repo)
    elsewhere = pathlib.Path("/somewhere/else")
    monkeypatch.setattr(pi, "replay_closure", lambda: (frozenset({"m.py"}), elsewhere))
    assert pi.main(["prove-inert.py", "HEAD", "m.py"]) == pi.EXIT_REFUSED
