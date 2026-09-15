"""`infra/scripts/sweep.sh` — the sweep that opens what a bare one does not (`.local/`, a file not yet added), and
reports a clean only over a `--control` pattern that hit.

The pattern is required as `-e <pattern>`, so the script reads exactly three things out of the caller's words --
the pattern, the control, and two refusals -- and every other word reaches grep unexamined. The tables below are
the two refusals in every spelling, and the words they must leave alone."""

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
    done = _sweep(_repo(tmp_path), "-l", "-e", "NEEDLE")
    hits = sorted(done.stdout.split())
    assert hits == [".local/memo.md", "cli/thing.py"], done.stdout + done.stderr
    assert done.returncode == 0


def test_a_pattern_nothing_holds_exits_1_over_a_control_that_hit(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "--control", "NEEDLE", "-e", "no-such-string-anywhere")
    assert done.returncode == 1 and done.stdout == "", done.stdout + done.stderr


def test_a_clean_with_no_control_is_an_error(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "-e", "no-such-string-anywhere")
    assert done.returncode == 2 and "nothing here proves this sweep could see" in done.stderr, done.stdout + done.stderr


def test_a_control_that_misses_makes_the_clean_an_error(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "--control", "no-such-control-either", "-e", "no-such-string-anywhere")
    assert done.returncode == 2 and "no-such-control-either" in done.stderr, done.stdout + done.stderr


def test_a_hit_needs_no_control(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "-e", "NEEDLE")
    assert done.returncode == 0 and ".local/memo.md" in done.stdout, done.stdout + done.stderr


def test_the_control_flag_never_reaches_grep(tmp_path):
    """grep has no `--control`: passed through, it would make a usage error of every sweep that carries one."""
    done = _sweep(_repo(tmp_path), "-l", "--control", "NEEDLE", "-e", "NEEDLE")
    assert done.returncode == 0 and done.stderr == "", done.stdout + done.stderr
    assert sorted(done.stdout.split()) == [".local/memo.md", "cli/thing.py"], done.stdout


def test_the_controls_own_operand_is_not_the_swept_pattern(tmp_path):
    """`--control`'s operand is stepped over without recording a pattern, so a sweep carrying only a control is the
    no-pattern error."""
    done = _sweep(_repo(tmp_path), "-l", "--control", "NEEDLE")
    assert done.returncode == 2 and "no pattern" in done.stderr, done.stdout + done.stderr


def test_a_control_with_no_pattern_of_its_own_is_an_error(tmp_path):
    """Dangling and attached-empty alike: the empty pattern every line matches is the control that proves
    nothing."""
    for n, words in enumerate(
        (("-l", "-e", "no-such-string-anywhere", "--control"), ("-l", "-e", "no-such-string-anywhere", "--control="))
    ):
        done = _sweep(_repo(tmp_path / str(n)), *words)
        assert done.returncode == 2, done.stdout + done.stderr
        assert "takes its known positive as its own word" in done.stderr, done.stdout + done.stderr


def test_the_attached_spelling_of_the_control_is_read(tmp_path):
    done = _sweep(_repo(tmp_path), "-l", "--control=NEEDLE", "-e", "no-such-string-anywhere")
    assert done.returncode == 1, done.stdout + done.stderr


def test_the_control_is_matched_with_the_callers_flags(tmp_path):
    """What the control must prove is the matcher the sweep ran: under `-w` a substring of a word is no proof.
    The control is the caller's own words with its pattern standing where the sweep's did, so this holds for
    every flag at once, whatever its spelling, and nothing here reads which flag it was."""
    repo = _repo(tmp_path)
    under_w = _sweep(repo, "-w", "--control", "NEEDL", "-e", "no-such-string-anywhere")
    assert under_w.returncode == 2 and "NEEDL" in under_w.stderr, under_w.stdout + under_w.stderr
    plain = _sweep(repo, "--control", "NEEDL", "-e", "no-such-string-anywhere")
    assert plain.returncode == 1, plain.stdout + plain.stderr
    clustered = _sweep(repo, "-il", "--control", "needle", "-e", "no-such-string-anywhere")
    assert clustered.returncode == 1, clustered.stdout + clustered.stderr
    uncased = _sweep(repo, "-l", "--control", "needle", "-e", "no-such-string-anywhere")
    assert uncased.returncode == 2 and "needle" in uncased.stderr, uncased.stdout + uncased.stderr


def test_the_control_carries_the_operand_of_the_flag_it_carries(tmp_path):
    """An operand rides along because nothing is removed from between a flag and it: the control is a copy of the
    sweep's words with one element replaced. Held back, the letter would eat the control's own pattern."""
    repo = _repo(tmp_path)
    kept = _sweep(repo, "-im", "5", "--control", "needle", "-e", "no-such-string-anywhere")
    assert kept.returncode == 1, kept.stdout + kept.stderr
    absent = _sweep(repo, "-im", "5", "--control", "no-such-control-either", "-e", "no-such-string-anywhere")
    assert absent.returncode == 2, absent.stdout + absent.stderr


# Every spelling of an inverting selection grep accepts: the two letters alone, at either end of a cluster and in
# the middle of one, and the two long options down to the shortest prefix grep still resolves. Each must be
# refused -- under `-v` a pattern nothing holds selects every line, so a control carrying the sweep's words hits
# whatever the tree holds and the clean it licenses proves nothing.
_INVERTING = [
    "-v",
    "-L",
    "-lv",
    "-vl",
    "-iv",
    "-vi",
    "-vL",
    "-Lv",
    "-ivl",
    "-vil",
    "-liv",
    "-lvm",
    "-iL",
    "-Li",
    "--invert-match",
    "--invert",
    "--inv",
    "--files-without-match",
    "--files-witho",
]


def test_an_inverting_selection_is_refused(tmp_path):
    """`-vl` is the `-lv` sweep spelled backwards, and a refusal that answered one and not the other would turn on
    how the operator typed it."""
    repo = _repo(tmp_path)
    wrong = []
    for word in _INVERTING:
        done = _sweep(repo, "-e", "no-such-string-anywhere", word, "--control", "NEEDLE")
        if done.returncode != 2 or "inverts the selection" not in done.stderr:
            wrong.append(f"{word}: rc {done.returncode} -- {(done.stdout + done.stderr).strip()[:70]}")
    assert not wrong, "\n".join(wrong)


# Every spelling of a pattern FILE, standalone, attached, clustered and long. Each must be refused: reading one
# would put a reader of the caller's patterns ahead of grep's, and no sweep prescribed here uses one.
_A_PATTERN_FILE = ["-f", "-fpat.txt", "-lf", "-fl", "-lfpat.txt", "--file", "--file=pat.txt"]


def test_a_pattern_file_is_refused(tmp_path):
    repo = _repo(tmp_path)
    (repo / "pat.txt").write_text("NEEDLE\n")
    wrong = []
    for word in _A_PATTERN_FILE:
        done = _sweep(repo, "-e", "NEEDLE", word, "pat.txt")
        if done.returncode != 2 or "names a pattern FILE" not in done.stderr:
            wrong.append(f"{word}: rc {done.returncode} -- {(done.stdout + done.stderr).strip()[:70]}")
    assert not wrong, "\n".join(wrong)


# The words the two refusals above must leave alone -- a refusal that reached an ordinary sweep is one the next
# operator turns off. Every short option GNU grep 3.11 takes that carries no pattern file and does not invert,
# clustered and not, with its operand as its own word and attached; and the long options whose names carry a `v`
# or an `f` and mean neither thing.
_ORDINARY = [
    ("-l",),
    ("-i",),
    ("-w",),
    ("-n",),
    ("-c",),
    ("-H",),
    ("-h",),
    ("-o",),
    ("-s",),
    ("-a",),
    ("-r",),
    ("-R",),
    ("-E",),
    ("-F",),
    ("-G",),
    ("-P",),
    ("-U",),
    ("-b",),
    ("-q",),
    ("-T",),
    ("-y",),
    ("-il",),
    ("-lm5",),
    ("-ldread",),
    ("-lXgrep",),
    ("-m", "5"),
    ("-A", "1"),
    ("-B", "1"),
    ("-C", "1"),
    ("-d", "read"),
    ("-D", "read"),
    ("-X", "grep"),
    ("--color",),
    ("--recursive",),
    ("--devices", "read"),
    ("--devices=read",),
    ("--files-with-matches",),
    ("--label", "LAB"),
    ("--line-number",),
    ("--include", "*.py"),
    ("--after-context", "1"),
    ("--after-context=1",),
]


def test_the_refusals_leave_an_ordinary_sweep_alone(tmp_path):
    """Both refusals read letters out of a cluster, which is the shape that over-reaches: `-lXgrep` carries an
    `f` inside grep's own matcher name, and `--devices` and `--recursive` carry a `v` inside theirs."""
    repo = _repo(tmp_path)
    wrong = []
    for words in _ORDINARY:
        done = _sweep(repo, "-e", "NEEDLE", *words)
        if done.returncode != 0:
            wrong.append(f"{' '.join(words)}: rc {done.returncode}, want 0 -- {(done.stdout + done.stderr).strip()[:70]}")
    assert not wrong, "\n".join(wrong)


# A pattern is `-e <word>` and nothing else. Every row here carries something that reads like one and is not --
# an operand of another flag, a bare word, a pattern flag in a spelling this script does not take -- and every
# row must be the no-pattern refusal rather than a sweep for whatever grep would have bound.
_NOT_A_PATTERN = [
    ("-l",),
    ("-l", "NEEDLE"),  # a bare word: which word is the pattern is exactly what is no longer asked
    ("-l", "--include", "*.py"),
    ("-l", "-m", "5"),
    ("-lm5",),
    ("-l", "-X", "grep"),
    ("-l", "-e"),  # a promise no word keeps
    ("-le", "NEEDLE"),  # `-e` clustered: grep binds it, this script does not read it
    ("-l", "--regexp", "NEEDLE"),
    ("-l", "--regexp=NEEDLE"),
]


def test_a_pattern_is_the_operand_of_a_bare_e_and_nothing_else(tmp_path):
    """Given no `-e`, grep would take the first path of the file list as its regex and answer whatever that earns,
    a hit or a clean, never the error this is. The control stands FIRST in every row, so the last row's dangling
    `-e` has nothing of the caller's left to bind and is the promise no word keeps."""
    repo = _repo(tmp_path)
    wrong = []
    for words in _NOT_A_PATTERN:
        done = _sweep(repo, "--control", "NEEDLE", *words)
        if done.returncode != 2 or "no pattern" not in done.stderr:
            wrong.append(f"{' '.join(words)}: rc {done.returncode} -- {(done.stdout + done.stderr).strip()[:70]}")
    assert not wrong, "\n".join(wrong)


def test_the_attached_pattern_is_refused_by_the_spelling_that_works(tmp_path):
    """grep takes `-eNEEDLE`, so passing it on would sweep for a pattern this script never recorded -- and the
    rest of the word is the operator's text, which reads as letters of a cluster to anything that looks."""
    repo = _repo(tmp_path)
    for word in ("-eNEEDLE", "-e."):
        done = _sweep(repo, "-l", word, "--control", "NEEDLE")
        assert done.returncode == 2, word + ": " + done.stdout + done.stderr
        assert "attaches the pattern to its flag" in done.stderr, word + ": " + done.stdout + done.stderr


def test_the_word_form_the_refusal_advertises_works(tmp_path):
    """A pattern beginning with a dash is where requiring `-e` pays: it is the one spelling that reaches grep as
    a pattern and not as a flag."""
    repo = _repo(tmp_path)
    (repo / "cli" / "dashed.py").write_text("a -NEEDLE here\n")
    done = _sweep(repo, "-l", "-e", "-NEEDLE")
    assert done.returncode == 0 and "cli/dashed.py" in done.stdout, done.stdout + done.stderr


def test_a_control_pattern_beginning_with_a_dash_is_the_controls_own(tmp_path):
    """`--control`'s operand is taken whatever it spells, so a control that looks like a flag is still a
    control."""
    repo = _repo(tmp_path)
    (repo / "cli" / "dashed.py").write_text("a -e here\n")
    done = _sweep(repo, "-l", "--control", "-e", "-e", "no-such-string-anywhere")
    assert done.returncode == 1, done.stdout + done.stderr


# A sweep whose grep opens no file at all: an invalid `-d` ACTION is the one word in grep 3.11 refused at rc 1
# rather than 2, so the sweep's own rc reads exactly like "nothing matched" over files it never opened. Every row
# must end in a refusal, never in the clean that rc 1 would otherwise license.
_OPENED_NOTHING = [
    ("-ld", "recursive"),  # `recurse` misspelt: the typo this costs
    ("-ld", "bogus"),
    ("-l", "-d", "recursive"),
    ("-l", "--directories", "bogus"),
    ("-l", "--directories=bogus"),
]


def test_a_grep_that_opened_no_file_is_never_reported_as_a_clean(tmp_path):
    """The control is the whole of what tells a refusal from an absence, and it can only do that while it carries
    the words the sweep carried: run under the same bad ACTION it opens nothing either, misses, and the clean is
    refused. A control held back from those words would run a laxer matcher, hit, and license a clean over a grep
    that read nothing -- a one-letter typo reading as an absence, invisible to anything reading rc."""
    repo = _repo(tmp_path)
    wrong = []
    for words in _OPENED_NOTHING:
        done = _sweep(repo, *words, "--control", "NEEDLE", "-e", "NEEDLE")
        if done.returncode != 2:
            wrong.append(f"{' '.join(words)}: rc {done.returncode}, want 2 -- {done.stderr.strip()[:70]}")
    assert not wrong, "\n".join(wrong)


def test_a_control_grep_refused_is_named_as_the_controls_own_pattern(tmp_path):
    """The control's words are the sweep's own but for the pattern, and the sweep's grep compiled them one run
    ago, so an rc 2 from the control is of that pattern and of nothing else -- which is what the message says, and
    what makes replacing the control the move that helps. An unclosed group or bracket class is an ordinary typo
    in a regex, so it is the door this arrives at most often."""
    repo = _repo(tmp_path)
    for control in ("NEEDLE\\(", "["):
        done = _sweep(repo, "-l", "--control", control, "-e", "no-such-string-anywhere")
        assert done.returncode == 2, control + ": " + done.stdout + done.stderr
        assert "refused the control pattern" in done.stderr, control + ": " + done.stdout + done.stderr
    missed = _sweep(repo, "-l", "--control", "no-such-control-either", "-e", "no-such-string-anywhere")
    assert "refused the control pattern" not in missed.stderr, missed.stdout + missed.stderr
    assert "pick a control this tree holds" in missed.stderr, missed.stdout + missed.stderr


def test_a_word_grep_refuses_ends_in_greps_own_complaint(tmp_path):
    """Nothing here reads grep's option table, so a word outside it is answered by grep and reported as the
    error it is, rather than explained in this script's words."""
    done = _sweep(_repo(tmp_path), "-l", "--no-such-option", "-e", "NEEDLE")
    assert done.returncode == 2 and "grep" in done.stderr, done.stdout + done.stderr


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
    done = _sweep(repo, "-e", "NEEDLE")
    assert done.stdout == "only.py:NEEDLE alone\n", done.stdout + done.stderr


def test_it_runs_from_a_subdirectory(tmp_path):
    """The skills that call it run from wherever the session stands."""
    repo = _repo(tmp_path)
    done = subprocess.run(["bash", str(SCRIPT), "-l", "-e", "NEEDLE"], cwd=repo / "cli", capture_output=True, text=True)
    assert sorted(done.stdout.split()) == [".local/memo.md", "cli/thing.py"], done.stdout + done.stderr


def test_a_worktree_sweeps_the_main_checkouts_local(tmp_path):
    """`.local/` is per-checkout, and a linked worktree's carries nothing but the tracked `.gitignore` — only the main checkout's holds the memo."""
    repo = _repo(tmp_path)
    wt = tmp_path / "wt"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "--detach", str(wt)], check=True, capture_output=True)
    done = subprocess.run(["bash", str(SCRIPT), "-l", "-e", "NEEDLE"], cwd=wt, capture_output=True, text=True)
    assert sorted(done.stdout.split()) == [str(repo / ".local" / "memo.md"), "cli/thing.py"], done.stdout + done.stderr


def test_a_tracked_file_deleted_in_the_worktree_keeps_the_rc_contract(tmp_path):
    """`git ls-files` reads the index, and grep exits 2 over a missing path however many hits it printed."""
    repo = _repo(tmp_path)
    (repo / "cli" / "gone.py").write_text("NEEDLE in a doomed file\n")
    subprocess.run(["git", "-C", str(repo), "add", "cli/gone.py"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "doomed"], check=True, capture_output=True)
    (repo / "cli" / "gone.py").unlink()
    done = _sweep(repo, "-l", "-e", "NEEDLE")
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stderr == "" and "gone.py" not in done.stdout, done.stdout + done.stderr


def test_nothing_to_search_is_an_error_not_a_clean(tmp_path):
    """rc 1 means the pattern is absent; a sweep that opened no file at all must not say that."""
    repo = tmp_path / "bare"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "develop"], check=True, capture_output=True)
    done = _sweep(repo, "-e", "NEEDLE")
    assert done.returncode == 2 and "no files to search" in done.stderr, done.stdout + done.stderr


def test_a_tracked_file_under_local_is_swept_once(tmp_path):
    """This repo tracks `.local/.gitignore`, so both halves of the list would otherwise hand grep one file twice."""
    repo = _repo(tmp_path)
    subprocess.run(["git", "-C", str(repo), "add", "-f", ".local/memo.md"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "tracked under .local"], check=True, capture_output=True)
    done = _sweep(repo, "-e", "NEEDLE")
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
    done = _sweep(repo, "-e", "NEEDLE")
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
    done = _sweep(repo, "-e", "NEEDLE")
    assert done.returncode == 0 and "not in this sweep" in done.stderr, done.stdout + done.stderr


def test_an_untracked_unignored_file_is_swept(tmp_path):
    """A session writes a file before it adds it; the shell grep this script replaces opens it, so this must too."""
    repo = _repo(tmp_path)
    (repo / "docs").mkdir()
    (repo / "docs" / "new-spec.md").write_text("NEEDLE not yet added\n")
    done = _sweep(repo, "-l", "-e", "NEEDLE")
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
    done = _sweep(repo, "-l", "-e", "NEEDLE")
    assert done.stdout.split().count("cli/thing.py") == 1, done.stdout + done.stderr


def test_an_untracked_nested_checkout_is_named_not_dropped(tmp_path):
    """`git ls-files --others` lists a nested repo as the bare directory, which the regular-file filter drops."""
    repo = _repo(tmp_path)
    (repo / "vendor").mkdir()
    (repo / "vendor" / "thing.py").write_text("NEEDLE in a nested checkout\n")
    subprocess.run(["git", "-C", str(repo / "vendor"), "init", "-q", "-b", "develop"], check=True, capture_output=True)
    done = _sweep(repo, "-l", "-e", "NEEDLE")
    assert "vendor" in done.stderr and "not swept" in done.stderr, done.stdout + done.stderr


def test_a_dangling_symlink_is_named_not_dropped(tmp_path):
    """A broken link satisfies neither the regular-file test nor the directory test, and a path still in the worktree is never dropped in silence."""
    repo = _repo(tmp_path)
    (repo / "cli" / "gone.py").symlink_to("/nonexistent/never-here.py")
    subprocess.run(["git", "-C", str(repo), "add", "cli/gone.py"], check=True, capture_output=True)
    done = _sweep(repo, "-l", "-e", "NEEDLE")
    assert "gone.py" in done.stderr and "not swept" in done.stderr, done.stdout + done.stderr


def test_a_non_regular_entry_under_the_ledger_is_named(tmp_path):
    """The git half names these shapes; the ledger half must not filter them out before the loop sees them."""
    repo = _repo(tmp_path)
    (repo / ".local" / "dangling").symlink_to("/nonexistent/never-here.md")
    done = _sweep(repo, "-l", "-e", "NEEDLE")
    assert "dangling" in done.stderr and "not swept" in done.stderr, done.stdout + done.stderr


def test_a_fifo_under_the_ledger_is_named(tmp_path):
    """`[ -e ]` rather than `[ -d ]` is what reaches a fifo or socket: neither is a directory nor a link."""
    repo = _repo(tmp_path)
    os.mkfifo(repo / ".local" / "pipe")
    done = _sweep(repo, "-l", "-e", "NEEDLE")
    assert "pipe" in done.stderr and "not swept" in done.stderr, done.stdout + done.stderr


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
    ("sweep.sh -l --control 'PAT' -e x", ["PAT"]),
    ('sweep.sh -l --control "PAT" -e x', ["PAT"]),
    ("sweep.sh -l --control PAT -e x", ["PAT"]),
    ("sweep.sh -l --control='PAT' -e x", ["PAT"]),
    ('sweep.sh -l --control="PAT" -e x', ["PAT"]),
    ("sweep.sh -l --control=PAT -e x", ["PAT"]),
    ("sweep.sh -l \\\n  --control 'PAT' -e x", ["PAT"]),
    ("sweep.sh -l --control \\\n  'PAT' -e x", ["PAT"]),
    ("sweep.sh -l --control '<pattern>' -e x", []),
    ("git grep -l --control 'PAT' x", []),
    # A control given through a shell variable is read, but as the literal `$CTL`: what it expands to is outside
    # anything a scan of the tracked text can see, so the exclusivity below is checked over a word nobody sweeps
    # for. The comment above says so, and this is the row that makes the saying testable.
    ('sweep.sh -l --control "$CTL" -e x', ["$CTL"]),
    # A bare newline is not a continuation: a control on the next line of a fenced block is a prescription this
    # scan does not reach, and the line above it is not read as prescribing the words below.
    ("sweep.sh -l\n--control 'PAT' -e x", []),
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
