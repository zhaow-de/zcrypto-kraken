"""`infra/scripts/sweep.sh` — the sweep that opens what a bare one does not (`.local/`, a file not yet added), and
reports a clean only over a `--control` pattern that hit."""

from __future__ import annotations

import os
import pathlib
import re
import subprocess

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "infra" / "scripts" / "sweep.sh"


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    (repo / ".local").mkdir(parents=True)
    (repo / ".venv" / "lib").mkdir(parents=True)
    (repo / "cli").mkdir()
    (repo / ".gitignore").write_text(".venv\n.local\n")
    (repo / ".local" / ".gitignore").write_text("*\n")
    (repo / ".local" / "memo.md").write_text("NEEDLE in the memo\n")
    (repo / ".venv" / "lib" / "vendored.py").write_text("NEEDLE in a dependency\n")
    (repo / "cli" / "thing.py").write_text("NEEDLE in the tree\n")
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "develop")
    run("config", "user.email", "sweep@test")
    run("config", "user.name", "sweep")
    run("add", "-f", ".gitignore", "cli/thing.py", ".local/.gitignore")
    run("commit", "-qm", "tracked")
    return repo


def _sweep(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=repo, capture_output=True, text=True)


def test_the_sweep_sees_the_tracked_tree_and_local_and_not_the_ignored_rest(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "NEEDLE")
    hits = sorted(done.stdout.split())
    assert hits == [".local/memo.md", "cli/thing.py"], done.stdout + done.stderr
    assert done.returncode == 0


def test_a_pattern_nothing_holds_exits_1_over_a_control_that_hit(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "--control", "NEEDLE", "no-such-string-anywhere")
    assert done.returncode == 1 and done.stdout == "", done.stdout + done.stderr


def test_a_clean_with_no_control_is_an_error(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "no-such-string-anywhere")
    assert done.returncode == 2 and "nothing here proves this sweep could see" in done.stderr, done.stdout + done.stderr


def test_a_control_that_misses_makes_the_clean_an_error(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "--control", "no-such-control-either", "no-such-string-anywhere")
    assert done.returncode == 2 and "no-such-control-either" in done.stderr, done.stdout + done.stderr


def test_a_hit_needs_no_control(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "NEEDLE")
    assert done.returncode == 0 and ".local/memo.md" in done.stdout, done.stdout + done.stderr


def test_the_control_flag_never_reaches_grep(tmp_path):
    """grep has no `--control`: passed through, it would make a usage error of every sweep that carries one."""
    done = _sweep(_repo(tmp_path), "-l", "--control", "NEEDLE", "NEEDLE")
    assert done.returncode == 0 and done.stderr == "", done.stdout + done.stderr
    assert sorted(done.stdout.split()) == [".local/memo.md", "cli/thing.py"], done.stdout


def test_the_controls_own_operand_is_not_the_swept_pattern(tmp_path):
    """`--control`'s operand is stepped over without recording a pattern, so a sweep carrying only a control is the
    no-pattern error."""
    done = _sweep(_repo(tmp_path), "-l", "--control", "NEEDLE")
    assert done.returncode == 2 and "no pattern" in done.stderr, done.stdout + done.stderr


def test_a_control_with_no_pattern_of_its_own_is_an_error(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "no-such-string-anywhere", "--control")
    assert done.returncode == 2 and "takes its known positive as its own word" in done.stderr, done.stdout + done.stderr


def test_the_control_is_matched_with_the_callers_flags(tmp_path):
    """What the control must prove is the matcher the sweep ran: under `-w` a substring of a word is no proof."""
    repo = _repo(tmp_path)
    under_w = _sweep(repo, "-w", "--control", "NEEDL", "no-such-string-anywhere")
    assert under_w.returncode == 2 and "NEEDL" in under_w.stderr, under_w.stdout + under_w.stderr
    plain = _sweep(repo, "--control", "NEEDL", "no-such-string-anywhere")
    assert plain.returncode == 1, plain.stdout + plain.stderr


def test_the_control_is_not_matched_under_an_inverting_flag(tmp_path):
    """`-v .` selects no line, so the sweep is clean and the control decides; inherited, that same `-v` makes a
    pattern nothing holds select every line, and the clean passes over a control that proves nothing."""
    repo = _repo(tmp_path)
    absent = _sweep(repo, "-v", "--control", "no-such-control-either", ".")
    assert absent.returncode == 2 and "no-such-control-either" in absent.stderr, absent.stdout + absent.stderr
    held = _sweep(repo, "-v", "--control", "NEEDLE", ".")
    assert held.returncode == 1, held.stdout + held.stderr


def test_an_inverting_flag_clustered_with_another_is_not_matched_either(tmp_path):
    repo = _repo(tmp_path)
    absent = _sweep(repo, "-lv", "--control", "no-such-control-either", ".")
    assert absent.returncode == 2 and "no-such-control-either" in absent.stderr, absent.stdout + absent.stderr
    held = _sweep(repo, "-lv", "--control", "NEEDLE", ".")
    assert held.returncode == 1, held.stdout + held.stderr
    separate = _sweep(repo, "-l", "-v", "--control", "no-such-control-either", ".")
    assert separate.returncode == 2 and "no-such-control-either" in separate.stderr, separate.stdout + separate.stderr


def test_an_inverting_cluster_keeps_the_letters_that_still_select(tmp_path):
    """Only the inverting letters leave the control, so `-iv` and `-i -v` are one sweep: the tree holds the
    control in the other case, which `-i` is what finds."""
    repo = _repo(tmp_path)
    clustered = _sweep(repo, "-iv", "--control", "needle", ".")
    separate = _sweep(repo, "-i", "-v", "--control", "needle", ".")
    assert clustered.returncode == 1, clustered.stdout + clustered.stderr
    assert separate.returncode == 1, separate.stdout + separate.stderr
    uncased = _sweep(repo, "-v", "--control", "needle", ".")
    assert uncased.returncode == 2 and "needle" in uncased.stderr, uncased.stdout + uncased.stderr


def test_a_cluster_that_does_not_invert_still_reaches_the_control(tmp_path):
    """A cluster carrying no `v` or `L` loses nothing to the hand-back: under `-il` the control keeps the `-i` the
    sweep ran, so a control in the other case still hits."""
    done = _sweep(_repo(tmp_path), "-il", "--control", "needle", "no-such-string-anywhere")
    assert done.returncode == 1, done.stdout + done.stderr


def test_a_refused_control_names_the_cluster_the_sweep_held_back(tmp_path):
    """A cluster held back whole takes its narrowing letters with it, so a control the sweep's own matcher would
    have found is refused. Named nowhere, the operator's next move is to replace a control that was never wrong;
    the separate-word spelling is the recovery, and it is asserted here rather than only advertised."""
    repo = _repo(tmp_path)
    done = _sweep(repo, "-ivm", "5", "--control", "needle", ".")
    assert done.returncode == 2, done.stdout + done.stderr
    assert "-ivm" in done.stderr and "held back whole" in done.stderr, done.stdout + done.stderr
    kept = _sweep(repo, "-i", "-m", "5", "-v", "--control", "needle", ".")
    assert kept.returncode == 1, kept.stdout + kept.stderr


def test_a_refusal_that_held_nothing_back_names_nothing(tmp_path):
    """On an ordinary bad control the note would send the operator looking for a withholding that never happened,
    which is the same wrong next move pointing the other way."""
    done = _sweep(_repo(tmp_path), "-l", "--control", "no-such-control-either", "no-such-string-anywhere")
    assert done.returncode == 2 and "held back whole" not in done.stderr, done.stdout + done.stderr


# One sweep written every way grep accepts it. A row is the words before `--control`, the control, and the rc
# those words MEAN: rc 1 the clean a control that hit licenses, rc 2 the refusal of a control that missed. The
# control doubles as the question -- `NEEDLE` the tree holds either way, `needle` only under an `-i` the cluster
# must have handed back, `no-such-control-either` nothing holds, so rc 1 there is the inversion leaking into the
# probe. What rc cannot answer: `-L` does not invert grep's exit status, only `-v` does, so the `-L` rows pin the
# hand-back and nothing pins their withholding.
_SPELLINGS = [
    # An inverting cluster in both orderings, and one that is nothing but inverting letters.
    (("-lv", "."), "no-such-control-either", 2),
    (("-vl", "."), "no-such-control-either", 2),
    (("-iv", "."), "no-such-control-either", 2),
    (("-vi", "."), "no-such-control-either", 2),
    (("-vL", "."), "no-such-control-either", 2),
    (("-lv", "."), "NEEDLE", 1),
    (("-vl", "."), "NEEDLE", 1),
    # The hand-back, which is what makes the orderings one sweep: `i` survives it, and a cluster without one
    # cannot find the control in the other case.
    (("-iv", "."), "needle", 1),
    (("-vi", "."), "needle", 1),
    (("-lv", "."), "needle", 2),
    (("-ivl", "."), "needle", 1),
    (("-vil", "."), "needle", 1),
    (("-liv", "."), "needle", 1),
    # `-L` inverts what the output names, not the exit status, so its rows are driven by an absent pattern.
    (("-iL", "no-such-string-anywhere"), "needle", 1),
    (("-Li", "no-such-string-anywhere"), "needle", 1),
    # Each letter grep gives an operand, clustered with the inverting one. The operand is a separate word this
    # loop leaves in the sweep's arguments, so the letter must not be handed back alone.
    (("-lvm", "5", "."), "NEEDLE", 1),
    (("-lvA", "1", "."), "NEEDLE", 1),
    (("-lvB", "1", "."), "NEEDLE", 1),
    (("-lvC", "1", "."), "NEEDLE", 1),
    (("-lvd", "read", "."), "NEEDLE", 1),
    (("-lvD", "read", "."), "NEEDLE", 1),
    (("-lvm", "5", "."), "no-such-control-either", 2),
    # The same withholding for the pattern-bearing letters, whose operand the control must not inherit at all.
    (("-lve", "."), "NEEDLE", 1),
    (("-lvf", "pat.txt"), "NEEDLE", 1),
    (("-lve", "."), "no-such-control-either", 2),
    # The long spellings and the prefixes of them grep resolves: `--inv` and `--files-witho` are the shortest
    # that are not ambiguous, and every longer prefix is the same flag.
    (("-l", "--invert-match", "."), "no-such-control-either", 2),
    (("-l", "--invert", "."), "no-such-control-either", 2),
    (("-l", "--inv", "."), "no-such-control-either", 2),
    (("-l", "--inv", "."), "NEEDLE", 1),
    (("-i", "--files-without-match", "no-such-string-anywhere"), "needle", 1),
    (("-i", "--files-witho", "no-such-string-anywhere"), "needle", 1),
    # The separate-word spellings each cluster above is one word of, including the operand grep takes as its own.
    (("-l", "-v", "."), "no-such-control-either", 2),
    (("-i", "-v", "."), "needle", 1),
    (("-l", "-m", "5", "-v", "."), "NEEDLE", 1),
    # A cluster that does not invert keeps everything it can carry, and loses what it cannot.
    (("-il", "no-such-string-anywhere"), "needle", 1),
    (("-lm", "5", "no-such-string-anywhere"), "NEEDLE", 1),
]


def test_every_spelling_of_the_same_sweep_answers_alike(tmp_path):
    """A guard that answers one way for `-lv` and another for `-vl` is a guard whose verdict depends on how the
    operator typed the sweep, and the operator has no way to know which spelling is the read one."""
    repo = _repo(tmp_path)
    (repo / "pat.txt").write_text(".\n")  # the `-f` rows' pattern file: one pattern every line matches
    wrong = []
    for words, control, want in _SPELLINGS:
        done = _sweep(repo, *words, "--control", control)
        if done.returncode != want:
            wrong.append(f"{' '.join(words)} --control {control}: rc {done.returncode}, want {want} -- {done.stderr.strip()}")
    assert not wrong, "\n".join(wrong)


def test_the_attached_spelling_of_the_control_is_read(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "--control=NEEDLE", "no-such-string-anywhere")
    assert done.returncode == 1, done.stdout + done.stderr


def test_a_hit_names_its_file_when_the_list_is_one_file(tmp_path):
    """GNU grep drops the filename when it is handed a single file, so `-H` is what makes a hit readable."""
    repo = tmp_path / "solo"
    repo.mkdir()
    (repo / "only.py").write_text("NEEDLE alone\n")
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "develop")
    run("config", "user.email", "sweep@test")
    run("config", "user.name", "sweep")
    run("add", "only.py")
    run("commit", "-qm", "one file")
    done = _sweep(repo, "NEEDLE")
    assert done.stdout == "only.py:NEEDLE alone\n", done.stdout + done.stderr


def test_it_runs_from_a_subdirectory(tmp_path):
    """The skills that call it run from wherever the session stands."""
    repo = _repo(tmp_path)
    done = subprocess.run(["bash", str(SCRIPT), "-l", "NEEDLE"], cwd=repo / "cli", capture_output=True, text=True)
    assert sorted(done.stdout.split()) == [".local/memo.md", "cli/thing.py"], done.stdout + done.stderr


def test_a_worktree_sweeps_the_main_checkouts_local(tmp_path):
    """`.local/` is per-checkout, and a linked worktree's carries nothing but the tracked `.gitignore` — only the main checkout's holds the memo."""
    repo = _repo(tmp_path)
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(wt)], check=True, capture_output=True)
    done = subprocess.run(["bash", str(SCRIPT), "-l", "NEEDLE"], cwd=wt, capture_output=True, text=True)
    assert sorted(done.stdout.split()) == [str(repo / ".local" / "memo.md"), "cli/thing.py"], done.stdout + done.stderr


def test_a_tracked_file_deleted_in_the_worktree_keeps_the_rc_contract(tmp_path):
    """`git ls-files` reads the index, and grep exits 2 over a missing path however many hits it printed."""
    repo = _repo(tmp_path)
    (repo / "cli" / "gone.py").write_text("NEEDLE in a doomed file\n")
    subprocess.run(["git", "-C", str(repo), "add", "cli/gone.py"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "doomed"], check=True, capture_output=True)
    (repo / "cli" / "gone.py").unlink()
    done = _sweep(repo, "-l", "NEEDLE")
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stderr == "" and "gone.py" not in done.stdout, done.stdout + done.stderr


def test_nothing_to_search_is_an_error_not_a_clean(tmp_path):
    """rc 1 means the pattern is absent; a sweep that opened no file at all must not say that."""
    repo = tmp_path / "bare"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "develop"], check=True, capture_output=True)
    done = _sweep(repo, "NEEDLE")
    assert done.returncode == 2 and "no files to search" in done.stderr, done.stdout + done.stderr


def test_a_tracked_file_under_local_is_swept_once(tmp_path):
    """This repo tracks `.local/.gitignore`, so both halves of the list would otherwise hand grep one file twice."""
    repo = _repo(tmp_path)
    subprocess.run(["git", "-C", str(repo), "add", "-f", ".local/memo.md"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "tracked under .local"], check=True, capture_output=True)
    done = _sweep(repo, "NEEDLE")
    assert done.stdout.count(".local/memo.md:") == 1, done.stdout + done.stderr


def test_a_main_checkout_that_does_not_resolve_is_refused(tmp_path):
    """Under `--separate-git-dir` the common dir's parent is no checkout, and a sweep of the tracked tree alone is the silent clean."""
    repo = tmp_path / "sep"
    (tmp_path / "elsewhere").mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "develop", "--separate-git-dir", str(tmp_path / "elsewhere" / "sep.git"), str(repo)],
        check=True,
        capture_output=True,
    )
    (repo / "only.py").write_text("NEEDLE alone\n")
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("config", "user.email", "sweep@test")
    run("config", "user.name", "sweep")
    run("add", "only.py")
    run("commit", "-qm", "one file")
    done = _sweep(repo, "NEEDLE")
    assert done.returncode == 2 and "no main checkout" in done.stderr, done.stdout + done.stderr


def test_an_absent_ledger_directory_says_so_on_stderr(tmp_path):
    """rc stays the pattern's answer, but a sweep that could not open `.local/` must not read like one that did."""
    repo = tmp_path / "solo"
    repo.mkdir()
    (repo / "only.py").write_text("NEEDLE alone\n")
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q", "-b", "develop")
    run("config", "user.email", "sweep@test")
    run("config", "user.name", "sweep")
    run("add", "only.py")
    run("commit", "-qm", "one file")
    done = _sweep(repo, "NEEDLE")
    assert done.returncode == 0 and "not in this sweep" in done.stderr, done.stdout + done.stderr


def test_an_untracked_unignored_file_is_swept(tmp_path):
    """A session writes a file before it adds it; the shell grep this script replaces opens it, so this must too."""
    repo = _repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs" / "new-spec.md").write_text("NEEDLE not yet added\n")
    done = _sweep(repo, "-l", "NEEDLE")
    assert sorted(done.stdout.split()) == [".local/memo.md", "cli/thing.py", "docs/new-spec.md"], done.stdout + done.stderr


def test_no_pattern_at_all_is_an_error(tmp_path):
    """Given no pattern grep takes the first path as one and answers that accidental regex's rc — a hit or a clean, never the error this is."""
    done = _sweep(_repo(tmp_path))
    assert done.returncode == 2 and "usage" in done.stderr, done.stdout + done.stderr


def test_a_conflicted_file_is_swept_once(tmp_path):
    """During a merge conflict the index carries a path once per stage, and grep would open it once per entry."""
    repo = _repo(tmp_path)
    run = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)  # noqa: E731
    run("checkout", "-q", "-b", "other")
    (repo / "cli" / "thing.py").write_text("NEEDLE from the other branch\n")
    run("commit", "-qam", "other")
    run("checkout", "-q", "develop")
    (repo / "cli" / "thing.py").write_text("NEEDLE from develop\n")
    run("commit", "-qam", "develop")
    subprocess.run(["git", "-C", str(repo), "merge", "other"], capture_output=True)
    done = _sweep(repo, "-l", "NEEDLE")
    assert done.stdout.split().count("cli/thing.py") == 1, done.stdout + done.stderr


def test_an_untracked_nested_checkout_is_named_not_dropped(tmp_path):
    """`git ls-files --others` lists a nested repo as the bare directory, which the regular-file filter drops."""
    repo = _repo(tmp_path)
    (repo / "vendor").mkdir()
    (repo / "vendor" / "thing.py").write_text("NEEDLE in a nested checkout\n")
    subprocess.run(["git", "-C", str(repo / "vendor"), "init", "-q", "-b", "develop"], check=True, capture_output=True)
    done = _sweep(repo, "-l", "NEEDLE")
    assert "vendor" in done.stderr and "not swept" in done.stderr, done.stdout + done.stderr


def test_a_dangling_symlink_is_named_not_dropped(tmp_path):
    """A broken link satisfies neither the regular-file test nor the directory test, and a path still in the worktree is never dropped in silence."""
    repo = _repo(tmp_path)
    (repo / "cli" / "gone.py").symlink_to("/nonexistent/never-here.py")
    subprocess.run(["git", "-C", str(repo), "add", "cli/gone.py"], check=True, capture_output=True)
    done = _sweep(repo, "-l", "NEEDLE")
    assert "gone.py" in done.stderr and "not swept" in done.stderr, done.stdout + done.stderr


def test_flags_without_a_pattern_are_an_error(tmp_path):
    done = _sweep(_repo(tmp_path), "-l")
    assert done.returncode == 2 and "no pattern" in done.stderr, done.stdout + done.stderr


def test_a_pattern_that_a_flag_carries_is_still_a_pattern(tmp_path):
    """Every argument here begins with `-`, so only the flags that carry a pattern can tell this from a typo."""
    done = _sweep(_repo(tmp_path), "-l", "--regexp=NEEDLE")
    assert done.returncode == 0 and ".local/memo.md" in done.stdout, done.stdout + done.stderr


def test_a_non_regular_entry_under_the_ledger_is_named(tmp_path):
    """The git half names these shapes; the ledger half must not filter them out before the loop sees them."""
    repo = _repo(tmp_path)
    (repo / ".local" / "dangling").symlink_to("/nonexistent/never-here.md")
    done = _sweep(repo, "-l", "NEEDLE")
    assert "dangling" in done.stderr and "not swept" in done.stderr, done.stdout + done.stderr


def test_a_fifo_under_the_ledger_is_named(tmp_path):
    """`[ -e ]` rather than `[ -d ]` is what reaches a fifo or socket: neither is a directory nor a link."""
    repo = _repo(tmp_path)
    os.mkfifo(repo / ".local" / "pipe")
    done = _sweep(repo, "-l", "NEEDLE")
    assert "pipe" in done.stderr and "not swept" in done.stderr, done.stdout + done.stderr


def test_a_flags_operand_is_not_a_pattern(tmp_path):
    """`--include '*.py'` carries a bare operand that grep consumes, so counting it as the pattern is the silent clean."""
    done = _sweep(_repo(tmp_path), "-l", "--include", "*.py")
    assert done.returncode == 2 and "no pattern" in done.stderr, done.stdout + done.stderr


def test_the_letter_absent_from_greps_help_skips_its_operand_too(tmp_path):
    """`-X MATCHER` is grep's obsolete matcher selection: missing from `--help`, accepted, operand-taking. Read as
    the pattern, its operand leaves grep with none and grep binds a file path as the regex instead -- a clean
    reported over a sweep that searched for a filename. This is the case that holds the two letter lists to one
    set, since the letter that decides it was in the cluster reading and out of the standalone one."""
    done = _sweep(_repo(tmp_path), "-l", "-X", "grep", "--control", "NEEDLE")
    assert done.returncode == 2 and "no pattern" in done.stderr, done.stdout + done.stderr


def test_the_word_form_the_refusal_advertises_works(tmp_path):
    """`-e` is the recovery the refusal names; a pattern beginning with a dash is where the arm is load-bearing."""
    repo = _repo(tmp_path)
    (repo / "cli" / "dashed.py").write_text("a -NEEDLE here\n")
    done = _sweep(repo, "-l", "-e", "-NEEDLE")
    assert done.returncode == 0 and "cli/dashed.py" in done.stdout, done.stdout + done.stderr


def test_an_optional_argument_flag_does_not_eat_the_pattern(tmp_path):
    """The case that keeps `--color` out of sweep.sh's option table; the table's own comment says why."""
    done = _sweep(_repo(tmp_path), "-l", "--color", "NEEDLE")
    assert done.returncode == 0 and ".local/memo.md" in done.stdout, done.stdout + done.stderr


def test_a_pattern_flag_with_no_operand_is_an_error(tmp_path):
    """`-e` promises a pattern the argument list never supplies; grep then binds the script's own `--`."""
    done = _sweep(_repo(tmp_path), "-e")
    assert done.returncode == 2 and "no pattern" in done.stderr, done.stdout + done.stderr


# A prescribing line names the script and carries the control, over a backslash continuation wherever it has one
# -- before `--control`, or between the flag and its operand. Both spellings the script accepts, quoted either way
# or bare, so a prescriber cannot leave the scan by rewriting its own quotes or its line breaks. What does leave
# it is a control the line does not itself hold: `--control "$CTL"` is read as the literal `$CTL`, and what that
# expands to is outside anything a scan of the tracked text can see.
_PRESCRIBED = re.compile(r"""sweep\.sh(?:[^\n]|\\\n)*?--control(?:[ =]|\\\n)+(?:'([^']+)'|"([^"]+)"|(\S+))""")


def _controls(text: str) -> list[str]:
    """The controls a text prescribes. `<pattern>` is this repo's usage convention, the script's own line
    included: a line showing the flag prescribes no control, and reading one out of it would fail the case over a
    word nobody sweeps for."""
    return [p for groups in _PRESCRIBED.findall(text) for p in [next(g for g in groups if g)] if not p.startswith("<")]


# One prescription in every spelling, and what the scan must read out of it -- including the two that prescribe
# nothing, the one shape that leaves the scan, and the one it reads as a literal nothing can resolve.
_PRESCRIPTIONS = [
    ("sweep.sh -l --control 'PAT' x", ["PAT"]),
    ('sweep.sh -l --control "PAT" x', ["PAT"]),
    ("sweep.sh -l --control PAT x", ["PAT"]),
    ("sweep.sh -l --control='PAT' x", ["PAT"]),
    ('sweep.sh -l --control="PAT" x', ["PAT"]),
    ("sweep.sh -l --control=PAT x", ["PAT"]),
    ("sweep.sh -l \\\n  --control 'PAT' x", ["PAT"]),
    ("sweep.sh -l --control \\\n  'PAT' x", ["PAT"]),
    ("sweep.sh -l --control '<pattern>' x", []),
    ("git grep -l --control 'PAT' x", []),
    # A control given through a shell variable is read, but as the literal `$CTL`: what it expands to is outside
    # anything a scan of the tracked text can see, so the exclusivity below is checked over a word nobody sweeps
    # for. The comment above says so, and this is the row that makes the saying testable.
    ('sweep.sh -l --control "$CTL" x', ["$CTL"]),
    # A bare newline is not a continuation: a control on the next line of a fenced block is a prescription this
    # scan does not reach, and the line above it is not read as prescribing the words below.
    ("sweep.sh -l\n--control 'PAT' x", []),
]


def test_the_prescription_scan_reads_every_spelling_the_script_accepts():
    """The scan is the only thing holding the exclusivity below true as the tree moves, so a spelling it cannot
    read is a prescription nothing checks at all."""
    wrong = []
    for text, want in _PRESCRIPTIONS:
        got = _controls(text)
        if got != want:
            wrong.append(f"{text!r}: read {got}, want {want}")
    assert not wrong, "\n".join(wrong)


def test_every_prescribed_sweep_control_is_a_pattern_no_tracked_file_carries():
    """A control the tracked tree carries cannot miss, so the clean it licenses proves nothing -- the silent
    clean this script exists to end, one level up. Each prescribing line says no tracked file carries its
    pattern, and nothing else holds that true as the tree moves. The script's own header example is
    illustrative rather than prescribed, so it is outside."""
    root = SCRIPT.parents[2]
    git = lambda *a: subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True)  # noqa: E731
    outside = {"infra/scripts/sweep.sh", "tests/test_sweep_sh.py"}
    prescribed = [
        (path, pattern)
        for path in git("grep", "-l", "--fixed-strings", "sweep.sh").stdout.split()
        if path not in outside
        for pattern in _controls((root / path).read_text())
    ]
    assert prescribed, "no prescribed sweep control found: the scan has gone blind, which is not the tree clean"
    carried = []
    for path, pattern in prescribed:
        # Case-folded, and without the prescriber's own selecting flags: both widen what counts as a carrier, and
        # a check that errs wide refuses a control the sweep would have accepted rather than passing one it holds.
        # `-E`/`-P` are the exception -- an alternation dropped to a BRE matches its own text, which is narrower.
        done = git("grep", "-l", "-i", "-e", pattern)
        assert done.returncode in (0, 1), (
            f"{path}: git grep could not read {pattern!r} -- rc {done.returncode}, {done.stderr.strip()}"
        )
        carried.append((path, pattern, done.stdout.split()))
    assert not [c for c in carried if c[2]], "\n".join(
        f"{path} prescribes {pattern!r}, which these files carry: {files}" for path, pattern, files in carried if files
    )
