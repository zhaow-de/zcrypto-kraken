"""`infra/scripts/sweep.sh` — the sweep that opens what a bare one does not (`.local/`, a file not yet added), and
reports a clean only over a `--control` pattern that hit."""

from __future__ import annotations

import os
import pathlib
import pty
import re
import socket
import subprocess
import threading

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


def _sweep(repo: pathlib.Path, *args: str, feed: str | None = None) -> subprocess.CompletedProcess[str]:
    """`feed` makes the child's stdin a pipe carrying it, which is what `-f -` and `-f /dev/stdin` name; without it
    stdin is whatever the runner left, and a row about stdin would be measuring the runner."""
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=repo, capture_output=True, text=True, input=feed)


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
    """The separate-word spelling is the recovery the refusal advertises, and it is asserted here rather than
    only advertised."""
    repo = _repo(tmp_path)
    done = _sweep(repo, "-ive", ".", "--control", "needle")
    assert done.returncode == 2, done.stdout + done.stderr
    assert "-ive" in done.stderr and "held back whole" in done.stderr, done.stdout + done.stderr
    kept = _sweep(repo, "-i", "-v", "-e", ".", "--control", "needle")
    assert kept.returncode == 1, kept.stdout + kept.stderr


def test_a_cluster_whose_binding_letter_takes_a_num_an_action_or_a_matcher_goes_over_whole(tmp_path):
    """Its operand is grep's own -- a NUM, an ACTION, a matcher name -- not the sweep's pattern, so the whole
    cluster goes to the control with the operand behind it and the control runs the matcher the sweep ran."""
    repo = _repo(tmp_path)
    kept = _sweep(repo, "-ivm", "5", ".", "--control", "needle")
    assert kept.returncode == 1, kept.stdout + kept.stderr
    assert "held back whole" not in kept.stderr, kept.stdout + kept.stderr
    absent = _sweep(repo, "-ivm", "5", ".", "--control", "no-such-control-either")
    assert absent.returncode == 2, absent.stdout + absent.stderr


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
    # Every long option grep answers "requires an argument" to, in its full spelling and in the shortest prefix
    # grep still resolves. The operand is a separate word this loop must step over: left behind, it is read as
    # the sweep's pattern and the option reaches the control alone, where it eats the control's own `-e`.
    (("-l", "--after-context", "1", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--a", "1", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--before-context", "1", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--be", "1", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--context", "1", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--con", "1", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--max-count", "5", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--m", "5", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--include", "*.py", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--inc", "*.py", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--exclude", "*.md", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--exclude-dir", ".venv", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--exclude-d", ".venv", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--label", "LAB", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--la", "LAB", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--binary-files", "text", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--binary-", "text", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--devices", "read", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--dev", "read", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--directories", "read", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--di", "read", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--group-separator", "SEP", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--g", "SEP", "no-such-string-anywhere"), "NEEDLE", 1),
    # The pattern-bearing long options, where an abbreviation costs what an operand-taking one costs: the control
    # inherits the option, it eats the control's own `-e`, and the clean the sweep earned is refused.
    (("-l", "--regexp", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--regex", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--reg", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-lv", "--file", "pat.txt"), "NEEDLE", 1),
    # Attached, where nothing stays behind and the word goes to the control whole -- the arm that keeps the
    # globs above off the pattern that follows.
    (("-l", "--after-context=1", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--a=1", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--regexp=no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--reg=no-such-string-anywhere"), "NEEDLE", 1),
    # The neighbours each glob stops short of. Every one takes NO operand, so a glob one letter too wide steps
    # over the pattern and the sweep is refused for having none.
    (("-l", "--ini", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--cou", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--binary", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--ext", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--der", "no-such-string-anywhere"), "NEEDLE", 1),
    (("-l", "--line-n", "no-such-string-anywhere"), "NEEDLE", 1),
    # `--file` and `--reg` are the two whose neighbours a glob would reach for nothing: the words it would take
    # carry no operand, so the pattern still lands and the rc is unchanged. Written LAST, before `--control`,
    # they answer: a glob one letter wider steps over `--control` itself, and grep is handed a flag it has never
    # heard of instead of a control.
    (("-l", "no-such-string-anywhere", "--files-with-matches"), "NEEDLE", 1),
    (("-l", "no-such-string-anywhere", "--recursive"), "NEEDLE", 1),
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


# Flags whose last operand belongs to grep, written every way grep accepts them -- standalone, clustered, the
# operand attached, long, abbreviated, and the letter absent from `--help` -- and not one pattern among them.
# Every row is driven twice: as written, where the answer has to be a refusal, and again with a pattern of the
# caller's own, which is what the second column's rc is for. `-f` is absent from these rows: its operand IS a
# pattern, so there is no row to write where the same word means both things.
_MISSING_PATTERN = [
    (("-l", "-m", "5"), 1),
    (("-lm", "5"), 1),
    (("-lm5",), 1),
    (("-l", "-A", "1"), 1),
    (("-lA", "1"), 1),
    (("-lA1",), 1),
    (("-l", "-B", "1"), 1),
    (("-lB", "1"), 1),
    (("-l", "-C", "1"), 1),
    (("-lC", "1"), 1),
    (("-l", "-d", "read"), 1),
    (("-ld", "read"), 1),
    (("-l", "-D", "read"), 1),
    (("-lD", "read"), 1),
    (("-l", "-X", "grep"), 1),
    (("-lX", "grep"), 1),
    # The same letters clustered with an inverting one, which is where the sweep's own answer is inverted too.
    (("-ivm", "5"), 0),
    (("-vlA", "1"), 0),
    # Long, abbreviated to the shortest prefix grep resolves, and with the operand attached.
    (("-l", "--include", "*.py"), 1),
    (("-l", "--inc", "*.py"), 1),
    (("-l", "--include=*.py"), 1),
    (("-l", "--after-context", "1"), 1),
    (("-l", "--a", "1"), 1),
    (("-l", "--after-context=1"), 1),
    (("-l", "--label", "LAB"), 1),
    (("-l", "--la", "LAB"), 1),
    # A pattern flag promising a pattern the words never supply, clustered and not.
    (("-l", "-e"), 1),
    (("-le",), 1),
    (("-l", "--regexp"), 1),
    (("-l", "--reg"), 1),
    # Flags alone, which is the same missing pattern with nothing to blame it on.
    (("-l",), 1),
]


def test_no_spelling_of_a_missing_pattern_is_answered_rather_than_refused(tmp_path):
    """The operand of a flag is not a pattern in any spelling, and what holds every spelling at once is that the
    question goes to grep rather than to a table read here: handed these words and no file list, grep says it has
    no pattern. `infra/scripts/sweep.sh`'s probe carries what a wrong answer costs. The second drive is the other
    direction, a pattern of the caller's own in the same flags, which must still be answered."""
    repo = _repo(tmp_path)
    wrong = []
    for flags, want in _MISSING_PATTERN:
        spelt = " ".join(flags)
        done = _sweep(repo, *flags, "--control", "NEEDLE")
        if done.returncode != 2:
            wrong.append(
                f"{spelt} --control NEEDLE: rc {done.returncode}, want 2 -- {done.stdout.strip()[:60]}{done.stderr.strip()[:60]}"
            )
        done = _sweep(repo, *flags, "no-such-string-anywhere", "--control", "NEEDLE")
        if done.returncode != want:
            wrong.append(
                f"{spelt} no-such-string-anywhere --control NEEDLE: rc {done.returncode}, want {want} -- {done.stderr.strip()[:60]}"
            )
    assert not wrong, "\n".join(wrong)


def test_the_words_grep_refuses_are_refused_in_greps_own_terms(tmp_path):
    """Which refusal answers the clustered spelling is the whole point: a table widened to cover `-lX` would pass
    the rows above and leave the next spelling standing, so the refusal here has to be the one that quotes grep's
    own complaint back. `-lX grep` is the case because `-X` is in no `--help` this script could have read."""
    done = _sweep(_repo(tmp_path), "-lX", "grep", "--control", "NEEDLE")
    assert done.returncode == 2 and "grep refuses these words" in done.stderr, done.stdout + done.stderr
    assert "Usage: grep" in done.stderr, done.stdout + done.stderr


# Every flag whose operand grep takes from the NEXT word, written in the position where the next word is not the
# caller's at all: grep 3.11's nine such letters standing alone and ending a cluster, and its fifteen long
# options. `-f` and `-e` belong in these rows although they are absent from the ones above -- a promise of a
# pattern is a promise like any other once no word keeps it.
_TAKES_THE_NEXT_WORD = (
    [f"-{letter}" for letter in "efmABCdDX"]
    + [f"-l{letter}" for letter in "efmABCdDX"]
    + [f"-vl{letter}" for letter in "efmABCdDX"]
    + [
        "--regexp",
        "--file",
        "--max-count",
        "--after-context",
        "--before-context",
        "--context",
        "--devices",
        "--directories",
        "--exclude",
        "--exclude-dir",
        "--exclude-from",
        "--group-separator",
        "--include",
        "--label",
        "--binary-files",
    ]
)


def test_a_flag_standing_last_is_refused_before_grep_is_asked(tmp_path):
    """The probe below the loop asks grep which word is the pattern, and that question is only a fair one while
    every word in it but the appended one is the caller's. A flag standing last takes the appended one, and the
    sweep then answers about a word nobody typed. So the promise is refused instead, in the script's own words,
    naming the flag rather than what grep bound."""
    repo = _repo(tmp_path)
    wrong = []
    for flag in _TAKES_THE_NEXT_WORD:
        done = _sweep(repo, "-l", "--control", "NEEDLE", "cli/thing.py", flag)
        if done.returncode != 2 or "stands last" not in done.stderr:
            wrong.append(f"{flag}: rc {done.returncode} -- {done.stdout.strip()[:60]}{done.stderr.strip()[:60]}")
    assert not wrong, "\n".join(wrong)


def test_a_flag_whose_operand_is_supplied_is_an_ordinary_sweep(tmp_path):
    """The other direction of the rows above, since a refusal that reached an ordinary sweep is one the next
    operator turns off. What the refusal has to read past is a word that LOOKS like an unkept promise: a cluster
    standing last whose operand is attached to it or whose letters take none at all, and a `--control` pattern
    beginning with a dash, which is the one word that may follow a flag without being what that flag asked for."""
    repo = _repo(tmp_path)
    (repo / "pat.txt").write_text(".\n")
    (repo / "cli" / "dashed.py").write_text("a -e here\n")
    wrong = []
    for words, want in [
        (("-le", "NEEDLE"), 0),
        (("-l", "-e", "NEEDLE"), 0),
        (("-l", "--regexp", "NEEDLE"), 0),
        (("-lvf", "pat.txt", "--control", "NEEDLE"), 1),
        (("-l", "-d", "read", "NEEDLE"), 0),
        (("-l", "-X", "grep", "NEEDLE"), 0),
        (("-l", "--label", "LAB", "NEEDLE"), 0),
        (("-ldread", "NEEDLE"), 0),
        (("-lXgrep", "NEEDLE"), 0),
        (("-lm5", "NEEDLE"), 0),
        (("-l", "NEEDLE", "-lm5"), 0),
        (("-l", "NEEDLE", "-il"), 0),
        (("-l", "NEEDLE", "--files-with-matches"), 0),
        (("-l", "no-such-string-anywhere", "--control", "-e"), 1),
    ]:
        done = _sweep(repo, *words)
        if done.returncode != want:
            wrong.append(f"{' '.join(words)}: rc {done.returncode}, want {want} -- {done.stderr.strip()[:80]}")
    assert not wrong, "\n".join(wrong)


# One sweep whose grep opens no file at all, written every way grep accepts it. `-d` with an ACTION grep refuses
# is the one operand in this script's table GNU grep 3.11 rejects at rc 1 rather than 2, so rc 1 here is the
# sweep's grep saying "nothing matched" about files it never opened. Every row must be a refusal; the standalone
# and long spellings are rows because the clustered ones were the only leak and nothing else would notice if they
# stopped being.
_OPENED_NOTHING = [
    ("-ld", "recursive", "NEEDLE"),  # `recurse` misspelt: the typo this costs
    ("-ld", "bogus", "no-such-string-anywhere"),
    ("-lde", "no-such-string-anywhere"),  # the ACTION attached inside the cluster, and it is `e`
    ("-ld", "NEEDLE"),  # no ACTION typed at all, so grep binds the pattern as one
    ("-vld", "bogus", "NEEDLE"),
    ("-l", "-d", "recursive", "NEEDLE"),
    ("-l", "--directories", "bogus", "NEEDLE"),
    ("-l", "--di", "bogus", "NEEDLE"),
    ("-l", "--directories=bogus", "NEEDLE"),
]

# The same letters with an ACTION grep takes, which is an ordinary sweep and must stay one: a refusal that reached
# these is a refusal the next operator turns off.
_OPENED_EVERYTHING = [
    (("-ld", "read", "NEEDLE"), 0),
    (("-lD", "read", "NEEDLE"), 0),
    (("-ldread", "NEEDLE"), 0),
    (("-lvd", "read", ".", "--control", "NEEDLE"), 1),
    (("-l", "--directories=read", "NEEDLE"), 0),
]


def test_a_grep_that_opened_no_file_is_never_reported_as_a_clean(tmp_path):
    """A grep that refused its own words read none of the files, and the control is the whole of what tells that
    from an absence -- so the control has to carry the words the sweep carried, operands and all. Held back
    instead, it runs a laxer matcher, hits, and licenses a clean over a grep that opened nothing: a one-letter
    typo then reads as an absence, visible only to a human watching stderr and invisible to anything reading
    rc."""
    repo = _repo(tmp_path)
    wrong = []
    for words in _OPENED_NOTHING:
        done = _sweep(repo, *words, "--control", "NEEDLE")
        if done.returncode != 2:
            spelt = " ".join(words)
            wrong.append(f"{spelt} --control NEEDLE: rc {done.returncode}, want 2 -- {done.stderr.strip()[:70]}")
    for words, want in _OPENED_EVERYTHING:
        done = _sweep(repo, *words)
        if done.returncode != want:
            wrong.append(f"{' '.join(words)}: rc {done.returncode}, want {want} -- {done.stderr.strip()[:70]}")
    assert not wrong, "\n".join(wrong)


# A sweep whose pattern SET is empty, written every way that reaches one. Only `-f`/`--file` does, since every
# other pattern source is a pattern by being written. Every row must be a refusal.
_AN_EMPTY_PATTERN_SET = [
    ("-lf", "empty.txt"),
    ("-l", "-f", "empty.txt"),
    ("-l", "--file", "empty.txt"),
    ("-l", "--file=empty.txt"),
    ("-l", "-f", "/dev/null"),
    ("-lf", "empty.txt", "cli/thing.py"),  # a bare word after `-f` is a FILE to grep, not a pattern
    ("-Lf", "empty.txt"),  # `-L` names every file in the list without opening one, and still exits 1
]

# Words this check must leave alone -- a refusal that reached these is one the next operator turns off. `-m 0`
# stops before the file list with a pattern and without one alike, so its emptiness is the control's business
# below and not this check's; under `-v` an empty pattern set selects every line, so that grep opens every file
# and hits.
_STILL_A_PATTERN = [
    (("-lf", "pat.txt"), 0),
    (("-l", "-f", "pat.txt", "--control", "NEEDLE"), 0),
    (("-lvf", "empty.txt"), 0),
    (("-l", "-m", "0", "--control", "NEEDLE", "NEEDLE"), 2),
    (("-l", "--control", "NEEDLE", "no-such-string-anywhere"), 1),
]


def test_an_empty_pattern_set_is_refused_rather_than_answered(tmp_path):
    """rc 1 over a control that hit is this script's clean, and a pattern set grep never had earns that rc from
    files it never opened. The control is no guard here -- it carries a pattern of its own, so it hits whatever
    the sweep's grep did -- and what tells the two apart is whether these words reach a file operand at all,
    which is asked of grep rather than derived from the words."""
    repo = _repo(tmp_path)
    (repo / "empty.txt").write_text("")
    (repo / "pat.txt").write_text("NEEDLE\n")
    wrong = []
    for words in _AN_EMPTY_PATTERN_SET:
        done = _sweep(repo, *words, "--control", "NEEDLE")
        if done.returncode != 2 or "empty pattern set" not in done.stderr:
            spelt = " ".join(words)
            wrong.append(f"{spelt} --control NEEDLE: rc {done.returncode}, want 2 -- {done.stderr.strip()[:70]}")
    for words, want in _STILL_A_PATTERN:
        done = _sweep(repo, *words)
        if done.returncode != want or "empty pattern set" in done.stderr:
            wrong.append(f"{' '.join(words)}: rc {done.returncode}, want {want} -- {done.stderr.strip()[:70]}")
    assert not wrong, "\n".join(wrong)


# Pattern sources the admission does not take, written as their own word and attached behind the letter: names
# for the caller's stdin, a path that is no file to read, a directory. `-lf -` is not among them: a bare `-` is
# no pattern word, so that spelling ends at the no-pattern refusal before any of this is asked. Every row must be
# refused, and refused HERE -- the empty-set check one screen up answers the stdin rows with a diagnosis about a
# file that holds no pattern, which is false of every one of them, and the last two reach grep's own complaint at
# the pattern question, which names the path and not what a pattern source has to be.
_NOT_A_PATTERN_SOURCE = [
    ("-l", "-f", "-"),
    ("-l", "--file", "-"),
    ("-l", "--file=-"),
    ("-l", "-f", "/dev/stdin"),
    ("-l", "--file=/dev/stdin"),
    ("-l", "-f", "/dev/fd/0"),
    ("-lf/dev/stdin", "NEEDLE"),  # attached: grep binds the rest of the cluster, so the path never stands alone
    ("-l", "-f", "no-such-pattern-file.txt"),
    ("-l", "-f", "cli"),
]

# What the admission takes, and the one kind outside it that is admitted anyway. A symlink is a row because the
# admission follows one. `/dev/null` is the exception and its rc says why it is safe to make: it reads empty to
# every reader, so the empty-set refusal above owns it and gives the diagnosis that helps. The exception is over
# the resolved name, so a re-spelling of it lands on the same diagnosis rather than on a refusal about its kind.
_ADMITTED_AS_A_PATTERN_SOURCE = [
    (("-l", "-f", "pat.txt", "--control", "NEEDLE"), 0),
    (("-lf", "pat.txt"), 0),
    (("-l", "--file=pat.txt", "--control", "NEEDLE"), 0),
    (("-l", "-f", "link.txt", "--control", "NEEDLE"), 0),
    (("-l", "-f", "/dev/null", "--control", "NEEDLE"), 2),
    (("-l", "-f", "/dev//null", "--control", "NEEDLE"), 2),
]


def test_only_a_regular_file_is_admitted_as_a_pattern_source(tmp_path):
    """This script reads the caller's pattern source before the sweep does -- three times -- so what it needs is
    a source all four reads answer alike, and a regular file under a name that means one file to each of them is
    the one thing that is. The rows here are the kinds, in the spellings that reach the kind test; the names that
    pass that test and still hand each reader a different file are the case two below."""
    repo = _repo(tmp_path)
    (repo / "pat.txt").write_text("NEEDLE\n")
    (repo / "link.txt").symlink_to(repo / "pat.txt")
    wrong = []
    for words in _NOT_A_PATTERN_SOURCE:
        done = _sweep(repo, *words, "--control", "NEEDLE", feed="NEEDLE\n")
        if done.returncode != 2 or "is not a pattern source this sweep can use" not in done.stderr:
            spelt = " ".join(words)
            wrong.append(f"{spelt} --control NEEDLE: rc {done.returncode}, want 2 -- {done.stderr.strip()[:70]}")
    for words, want in _ADMITTED_AS_A_PATTERN_SOURCE:
        done = _sweep(repo, *words, feed="NEEDLE\n")
        if done.returncode != want or "is not a pattern source this sweep can use" in done.stderr:
            wrong.append(f"{' '.join(words)}: rc {done.returncode}, want {want} -- {done.stderr.strip()[:70]}")
    assert not wrong, "\n".join(wrong)


def test_a_source_named_as_stdin_is_refused_where_no_stat_could_tell(tmp_path):
    """Over a redirected regular file every one of these names stats as that regular file -- `-` as nothing at
    all -- so the admission below them would take four of the five, and the name is the whole of what tells.
    The last row is the shape a clean comes out of: beside an ordinary `-f` the set is not empty either, so
    nothing downstream asks again."""
    repo = _repo(tmp_path)
    pats = repo.parent / "pats.txt"
    pats.write_text("NEEDLE\n")
    ordinary = repo.parent / "absent.txt"
    ordinary.write_text("no-such-string-anywhere\n")
    rows = [
        ("-l", "-f", "/dev/stdin", "--control", "NEEDLE"),
        ("-l", "-f", "-", "--control", "NEEDLE"),
        ("-l", "-f", "/dev/fd/0", "--control", "NEEDLE"),
        ("-l", "-f", "/proc/self/fd/0", "--control", "NEEDLE"),
        ("-l", "-f", "/proc/thread-self/fd/0", "--control", "NEEDLE"),
        ("-l", "-f", str(ordinary), "-f", "/proc/thread-self/fd/0", "--control", "NEEDLE"),
    ]
    for words in rows:
        with pats.open() as fh:
            done = subprocess.run(["bash", str(SCRIPT), *words], cwd=repo, capture_output=True, text=True, stdin=fh)
        spelt = " ".join(words)
        assert done.returncode == 2, spelt + ": " + done.stdout + done.stderr
        assert "is not a pattern source this sweep can use" in done.stderr, spelt + ": " + done.stdout + done.stderr


def test_a_name_that_answers_per_reader_is_refused_whatever_its_spelling(tmp_path):
    """The kind test cannot reach these: every row here IS a regular file to the stat the admission makes, and a
    different file to each of the four greps -- `/proc/self` is whichever of them is asking, and the descriptor
    names resolve against the stdin each one was handed. Every row is driven beside an ordinary `-f`, the
    arrangement nothing downstream catches: the pattern set is not empty, so the sweep runs and answers 1 with an
    empty stderr, which this script reports as a clean. None of the spellings is a name any list held -- they are
    re-spellings of the two filesystems, which is what the arm tests -- and one of them climbs there from the
    toplevel by a relative path, so a test of the word as written would walk past it. The procfs rows stand only
    where procfs does; the `/dev` rows need only `/dev` itself, which is where the resolution happens."""
    repo = _repo(tmp_path)
    pats = repo.parent / "pats.txt"
    pats.write_text("NEEDLE\n")
    ordinary = repo.parent / "absent.txt"
    ordinary.write_text("no-such-string-anywhere\n")
    # Lexical, from the physical toplevel the script `cd`s to, so the climb lands where the script resolves it.
    climb = os.path.relpath("/dev/stdin", os.path.realpath(repo))
    rows = ["/dev//stdin", "/dev/./stdin", "//dev/stdin", "/dev/./fd/0", climb]
    procfs = [p for p in ("/proc/self/cmdline", "/proc/self/maps", "/proc/thread-self/stat") if os.path.isfile(p)]
    # The leading `//` that `pwd -P` hands back is driven over procfs too, and not over `/dev` alone: every `/dev`
    # name here is a link onward to a descriptor, so the chain below the arm refuses it a hop later whatever the
    # collapse does, and procfs is where dropping the collapse is a reported clean rather than a later refusal.
    rows += procfs + [f"/{p}" for p in procfs]
    wrong = []
    for row in rows:
        words = ("-l", "-f", str(ordinary), "-f", row, "--control", "NEEDLE")
        with pats.open() as fh:
            done = subprocess.run(["bash", str(SCRIPT), *words], cwd=repo, capture_output=True, text=True, stdin=fh)
        if done.returncode != 2 or "is not a pattern source this sweep can use" not in done.stderr:
            wrong.append(f"-f {row}: rc {done.returncode}, want 2 -- {(done.stdout + done.stderr).strip()[:80]}")
    # `/dev/stdout` is a regular file to the stat only when stdout is one, which is also the only run where a
    # miss here would be a silent clean rather than a refusal about its kind -- so the drive redirects it.
    written = repo.parent / "stdout.txt"
    words = ("-l", "-f", str(ordinary), "-f", "/dev/stdout", "--control", "NEEDLE")
    with pats.open() as fh, written.open("w") as out:
        done = subprocess.run(["bash", str(SCRIPT), *words], cwd=repo, stdout=out, stderr=subprocess.PIPE, text=True, stdin=fh)
    if done.returncode != 2 or "is not a pattern source this sweep can use" not in done.stderr:
        wrong.append(f"-f /dev/stdout: rc {done.returncode}, want 2 -- {(written.read_text() + done.stderr).strip()[:80]}")
    assert not wrong, "\n".join(wrong)


def test_a_link_whose_leaf_answers_per_reader_is_refused_though_its_own_name_does_not(tmp_path):
    """The carrier no name of the caller's shows: the source is an ordinary relative name in the tree, so neither
    prefix matches it, and it stats as a REGULAR FILE, so the kind test takes it -- while each of the four greps
    follows it and opens its own `/proc/self`. Every row is driven beside an ordinary `-f`, the arrangement
    nothing downstream catches: the set is not empty, so the sweep runs and answers 1 over an empty stderr, which
    this script reports as a clean standing on a grep that carried its own argv as the pattern set.
    The descriptor spellings are rows here and not only in the case above because they are what the resolution
    must not be bought with: over a redirected regular file the END of `/dev/fd/0` is that regular file, outside
    both prefixes, so a walk that judged the end of the chain would admit the names this arm was first written
    for. What answers them stands a hop before the end, which is why every hop is asked and not the last. The
    cycle row is the walk's own bound, which has to answer rather than follow; the last row is the admission it
    must leave standing, a chain that ends on an ordinary regular file. The procfs rows stand only where procfs
    does; the two `/dev` rows need only `/dev`."""
    repo = _repo(tmp_path)
    pats = repo.parent / "pats.txt"
    pats.write_text("NEEDLE\n")
    ordinary = repo.parent / "absent.txt"
    ordinary.write_text("no-such-string-anywhere\n")
    leaves = [p for p in ("/proc/self/cmdline", "/proc/self/maps", "/proc/self/environ") if os.path.isfile(p)]
    leaves.append("/dev/stdin")
    rows = []
    for n, target in enumerate(leaves):
        (repo / f"leaf{n}").symlink_to(target)
        rows.append(f"leaf{n}")
    # One hop is not the rule: a chain that leaves the tree and comes back to one of them is the same source.
    (tmp_path / "mid").symlink_to(leaves[0])
    (repo / "chained").symlink_to(tmp_path / "mid")
    rows.append("chained")
    (repo / "ring").symlink_to(repo / "ring-back")
    (repo / "ring-back").symlink_to(repo / "ring")
    rows.append("ring")
    rows.append("/dev/fd/0")
    wrong = []
    for row in rows:
        words = ("-l", "-f", str(ordinary), "-f", row, "--control", "NEEDLE")
        # The timeout is no part of the assertion: it is what keeps a tree whose walk has lost its bound from
        # spinning on the cycle row for good.
        with pats.open() as fh:
            done = subprocess.run(["bash", str(SCRIPT), *words], cwd=repo, capture_output=True, text=True, stdin=fh, timeout=30)
        if done.returncode != 2 or "is not a pattern source this sweep can use" not in done.stderr:
            wrong.append(f"-f {row}: rc {done.returncode}, want 2 -- {(done.stdout + done.stderr).strip()[:80]}")
    # In a tree of its own, so the links above are no part of the file list this one sweeps.
    plain = _repo(tmp_path / "plain")
    (plain.parent / "outside.txt").write_text("NEEDLE\n")
    (plain / "mid.txt").symlink_to(plain.parent / "outside.txt")
    (plain / "ok.txt").symlink_to(plain / "mid.txt")
    done = _sweep(plain, "-l", "-f", "ok.txt", "--control", "NEEDLE")
    if done.returncode != 0 or "is not a pattern source" in done.stderr:
        wrong.append(f"-f ok.txt: rc {done.returncode}, want 0 -- {(done.stdout + done.stderr).strip()[:80]}")
    assert not wrong, "\n".join(wrong)


def test_a_fifo_and_a_socket_are_refused_before_a_reader_drains_them(tmp_path):
    """The half no name can do: a pipe or a socket reaches `-f` under a path of its own -- a `mkfifo`, or a
    process substitution on a shell that has no `/dev/fd` -- and what refuses them is being no regular file. The
    socket stands first because its open fails fast, so a tree that has lost the admission fails on it and never
    reaches the fifo, whose open blocks until a writer arrives -- the second thing this refusal replaces, a sweep
    that hangs with nothing on stderr."""
    repo = _repo(tmp_path)
    sock = tmp_path / "sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as bound:
        bound.bind(str(sock))
        done = _sweep(repo, "-l", "-f", str(sock), "--control", "NEEDLE")
    assert done.returncode == 2, done.stdout + done.stderr
    assert "is not a pattern source this sweep can use" in done.stderr, done.stdout + done.stderr
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    # The timeout is no part of the assertion: it is what keeps a tree that has lost the admission from blocking
    # the suite for good on grep's open of a writerless fifo.
    done = subprocess.run(
        ["bash", str(SCRIPT), "-l", "-f", str(fifo), "--control", "NEEDLE"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert done.returncode == 2, done.stdout + done.stderr
    assert "is not a pattern source this sweep can use" in done.stderr, done.stdout + done.stderr


def test_a_character_device_is_refused_though_no_reader_drains_it(tmp_path):
    """The kind that answers to neither half: a pty slave is a character device, so no name tells it and it is
    neither `-p` nor `-S`, and it is what a rule written as the kinds that fail lets through. Each of the four
    greps opens it afresh and the sweep's own, reading last, gets whatever is there then. It is driven beside an
    ordinary `-f` because that is the arrangement no measurement downstream catches, which the sibling below
    prices. The device is reached through a LINK in the tree, because the only path an unprivileged tree can make
    one at is under `/dev`, where the name arm would refuse it before its kind was ever asked; the link's own
    name is the toplevel's, so the kind test is what answers it -- and the `/dev/pts` path is driven too, for
    the refusal an operator naming the device directly actually gets. What this row does NOT do is tell the two
    doors apart: the chain the name arm walks reaches `/dev/pts` a hop on, so a tree that has lost the kind test
    still refuses both rows here, and where that loss is caught is the missing file and the directory of
    `test_only_a_regular_file_is_admitted_as_a_pattern_source`. The writer feeds one EOF per reader so a
    tree without the admission ANSWERS instead of blocking on a read no writer ends, and the timeout bounds the
    case whatever the tree does; neither is asserted on."""
    repo = _repo(tmp_path)
    ordinary = repo.parent / "absent.txt"
    ordinary.write_text("no-such-string-anywhere\n")
    master, slave = pty.openpty()
    stop = threading.Event()

    def eof_per_reader() -> None:
        while not stop.wait(0.2):
            try:
                os.write(master, b"\x04")
            except OSError:
                return

    writer = threading.Thread(target=eof_per_reader, daemon=True)
    writer.start()
    (repo / "tty-link").symlink_to(os.ttyname(slave))
    try:
        runs = [
            subprocess.run(
                ["bash", str(SCRIPT), "-l", "-f", str(ordinary), "-f", named, "--control", "NEEDLE"],
                cwd=repo,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=30,
            )
            for named in ("tty-link", os.ttyname(slave))
        ]
    finally:
        stop.set()
        writer.join(timeout=5)
        os.close(master)
        os.close(slave)
    for done in runs:
        assert done.returncode == 2, done.stdout + done.stderr
        assert "is not a pattern source this sweep can use" in done.stderr, done.stdout + done.stderr


def test_a_stream_beside_an_ordinary_pattern_file_is_refused_rather_than_swept(tmp_path):
    """The shape no measurement downstream can catch: the ordinary `-f` keeps the pattern set non-empty, so the
    empty-set check stays quiet, while the stream reaches the sweep's grep drained. Without the refusal what
    stands is rc 1 with an empty stderr -- a clean over a pattern the tree holds. A process substitution needs a
    shell to write it, which is also the only way an operator does."""
    repo = _repo(tmp_path)
    absent = repo.parent / "absent.txt"
    absent.write_text("no-such-string-anywhere\n")
    done = subprocess.run(
        ["bash", "-c", 'bash "$1" -l -f "$2" -f <(echo NEEDLE) --control NEEDLE', "sweep", str(SCRIPT), str(absent)],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 2, done.stdout + done.stderr
    assert "is not a pattern source this sweep can use" in done.stderr, done.stdout + done.stderr


def test_a_control_grep_refused_is_not_reported_as_a_control_that_missed(tmp_path):
    """The two arrive as the same rc from the same grep -- an invalid `-d` ACTION is rc 1, exactly like an honest
    miss -- and they want opposite next moves: a control refused by a word of the CALLER'S was never wrong, and
    replacing it is the move that cannot help. The control carrying the sweep's operand-taking words is what makes
    a mistyped ACTION end here routinely."""
    repo = _repo(tmp_path)
    refused = _sweep(repo, "-ld", "recursive", "NEEDLE", "--control", "NEEDLE")
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert "refused the control's words" in refused.stderr, refused.stdout + refused.stderr
    assert "pick a control this tree holds" not in refused.stderr, refused.stdout + refused.stderr
    missed = _sweep(repo, "-lm", "5", "--control", "no-such-control-either", "no-such-string-anywhere")
    assert missed.returncode == 2, missed.stdout + missed.stderr
    assert "pick a control this tree holds" in missed.stderr, missed.stdout + missed.stderr
    assert "refused the control's words" not in missed.stderr, missed.stdout + missed.stderr


def test_a_control_refused_for_its_own_pattern_is_not_blamed_on_the_callers_words(tmp_path):
    """The words put to grep are the sweep's own PLUS the control's pattern, so a refusal of them is of one or the
    other, and again the two want opposite moves. Refused for the caller's word, the sweep's own grep was refused
    the same way and its rc 1 is no absence -- the sibling above. Refused for the pattern, that rc stands unproven
    and replacing the control is the whole fix, which is the move the sibling's message tells the operator not to
    make. A group left unclosed or a bracket class left open is an ordinary typo in a regex, so this is the
    category the two share a door with most often."""
    repo = _repo(tmp_path)
    for control in ("NEEDLE\\(", "["):
        done = _sweep(repo, "-l", "--control", control, "no-such-string-anywhere")
        assert done.returncode == 2, control + ": " + done.stdout + done.stderr
        assert "refused the control pattern" in done.stderr, control + ": " + done.stdout + done.stderr
        assert "refused the control's words" not in done.stderr, control + ": " + done.stdout + done.stderr
    theirs = _sweep(repo, "-ld", "recursive", "NEEDLE", "--control", "NEEDLE")
    assert "refused the control pattern" not in theirs.stderr, theirs.stdout + theirs.stderr


def test_a_control_that_is_itself_bad_too_is_not_called_sound(tmp_path):
    """Both refusals can be waiting at once, and grep names the option error first, so this arrives at the arm
    that blames the caller's word -- rightly, since that word refused the sweep's grep too and fixing it is the
    move that helps. What the message must not do there is clear the control, which is what the operator then
    keeps: the next pass refuses it, and a message that called it sound has cost the round it was meant to save.
    The second drive is that next pass, and it is what makes the claim false rather than merely unproven."""
    repo = _repo(tmp_path)
    both = _sweep(repo, "-ld", "recursive", "NEEDLE", "--control", "[")
    assert both.returncode == 2, both.stdout + both.stderr
    assert "refused the control's words" in both.stderr, both.stdout + both.stderr
    assert "is not what is wrong here" not in both.stderr, both.stdout + both.stderr
    after = _sweep(repo, "-l", "no-such-string-anywhere", "--control", "[")
    assert "refused the control pattern" in after.stderr, after.stdout + after.stderr


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
    """`-X MATCHER` is grep's obsolete matcher selection -- accepted, operand-taking, in no `--help` -- and the
    case that holds the two letter lists to one set."""
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
