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
    # `# noqa` is a comment the gate reads, so a changed comment stream is not certifiable prose.
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
    # The refusal existed but nothing drove it through `main`, so downgrading it to INERT passed.
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
    # Same text, same order: only its position relative to the statement it annotates moved, which is
    # what `tests/test_config_selectors_are_parsed.py` reads above the comparison it exempts.
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


def test_a_docstring_cut_leaves_the_comment_stream_alone() -> None:
    # The true positive beside it: the commonest prose-only edit must not read as a comment change.
    before = 'def f():\n    """Doc."""\n    # marker\n    return 1\n'
    after = "def f():\n    # marker\n    return 1\n"
    result = pi.compare(before, after)
    assert result.ast_inert
    assert result.comments_same
