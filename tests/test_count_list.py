"""count-list.sh: one entry per count the corpus names by entry name plus the four it does not, a name filter, and a topic-only-merge arm that counts a merge only when every file it brought in is a topic file."""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]


def _tracked(pathspec: str) -> list[str]:
    """The index's paths, so an untracked scratch page under a judged directory never turns the suite red."""
    return subprocess.run(["git", "-C", str(REPO), "ls-files", pathspec], capture_output=True, text=True, check=True).stdout.split()


SCRIPT = REPO / "infra" / "scripts" / "count-list.sh"
FEED = REPO / "tests" / "fixtures" / "kraken_scheduled_maintenances.json"
CORPUS = (
    REPO / "CLAUDE.md",
    REPO / ".claude" / "rules" / "fleet-deploys.md",
    REPO / "docs" / "reference" / "fleet.md",
    REPO / "docs" / "reference" / "fleet-pins.md",
    REPO / ".claude" / "skills" / "zcrypto-grooming" / "references" / "memo-protocol.md",
    *sorted(REPO / p for p in _tracked("infra/runbooks/*.md") if "/" not in p[len("infra/runbooks/") :]),
)  # the always-loaded guidance, and the contracts the guard reads for universals -- every top-level runbook page among them since 2026-09-12

_ENTRY = re.compile(r'^\s*emit "([^"]+)"', re.MULTILINE)
_CORPUS_ENTRY = re.compile(r"count: `infra/scripts/count-list\.sh ([a-z0-9-]+)`")
NOT_NAMED = {"topic-only-merges", "claude-commits-since-the-round-closed", "worktrees", "ambient-bytes"}
_VALUE = re.compile(r"\d+(?: passed)?")


def _corpus_entries() -> set[str]:
    return {name for path in CORPUS for name in _CORPUS_ENTRY.findall(path.read_text())}


def _develop_resolves() -> bool:
    done = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", "--quiet", "develop"], capture_output=True)
    return done.returncode == 0


def test_every_rule_window_is_a_full_instant_and_not_a_bare_date():
    """`git log --since=<bare date>` is approxidate: the missing time comes from the RUN's clock, so a bare date
    slides the window through the day and a morning run reads 0 over an empty set."""
    since = re.findall(r"^([A-Z_]*RULE_SINCE)=\"([^\"]+)\"", SCRIPT.read_text(), re.MULTILINE)
    assert since, "no RULE_SINCE constant found -- the windows moved somewhere this test cannot see"
    for name, value in since:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value), f"{name}={value!r} is not an instant"
    code = "\n".join(line for line in SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#"))
    assert "--since=2026-" not in code, "a window is inlined instead of naming its RULE_SINCE"


def test_the_corpus_names_every_entry_but_the_four_the_script_carries_on_its_own():
    """A corpus count names an entry that exists, and an entry the corpus does not name is one of the four -- a universal whose count is not run here is the finding."""
    names = _ENTRY.findall(SCRIPT.read_text())
    assert len(names) == len(set(names)), f"two entries answer to one name: {sorted(names)}"
    corpus = _corpus_entries()
    inline = sum(p.read_text().count("count: ") for p in CORPUS) - sum(len(_CORPUS_ENTRY.findall(p.read_text())) for p in CORPUS)
    assert inline == 0, f"{inline} corpus count(s) carry a command inline instead of naming an entry"
    assert corpus <= set(names), f"the corpus names entries the script lacks: {sorted(corpus - set(names))}"
    assert set(names) - corpus == NOT_NAMED, f"entries the corpus does not name: {sorted(set(names) - corpus)}"


@pytest.mark.skipif(not _develop_resolves(), reason="main() refuses a checkout with no develop ref before any entry runs")
def test_the_read_count_finds_its_line_anywhere_in_the_body_and_only_at_the_floor(tmp_path):
    """A Fable line on the body's third line is a read; a Haiku line at the top is not; the journal PR is left out
    while it carries journal files ALONE; no line counts. Every row carries the `headRefOid` and `files` the gate
    reads, because the counter now calls `read_line_fails` rather than restating it: a row missing either is a
    violation there, which is the right answer for a real fetch and a fixture bug in a snapshot."""
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    head = "22ac48df1111111111111111111111111111abcd"
    line = "Read before push by: Claude Fable 5.1 at 22ac48df"
    journal = [{"path": "docs/reference/ops-journal/2026-09.md"}]
    prs = [
        {
            "headRefName": "feat/a",
            "mergedAt": stamp,
            "headRefOid": head,
            "files": [],
            "body": f"## Summary\n\n{line}\n\n- [x] done",
        },
        {
            "headRefName": "feat/b",
            "mergedAt": stamp,
            "headRefOid": head,
            "files": [],
            "body": "Read before push by: Claude Haiku 4.5 at 22ac48df\n",
        },
        {"headRefName": "ops-journal", "mergedAt": stamp, "headRefOid": head, "files": journal, "body": "## 2026-09\n"},
        # The journal exemption is scoped, not by branch name: one non-journal file and the read line is owed.
        {
            "headRefName": "ops-journal",
            "mergedAt": stamp,
            "headRefOid": head,
            "files": journal + [{"path": "cli/x.py"}],
            "body": "## 2026-09\n",
        },
        {"headRefName": "feat/c", "mergedAt": stamp, "headRefOid": head, "files": [], "body": "## Summary\n"},
        # Older than the window on purpose: it is BELOW the floor, so it is not counted, and its presence is what
        # tells the counter the fetch reached past the window rather than stopping inside it.
        {"headRefName": "feat/old", "mergedAt": "2026-01-01T00:00:00Z", "headRefOid": head, "files": [], "body": "## Summary\n"},
    ]
    snapshot = tmp_path / "prs.json"
    snapshot.write_text(json.dumps(prs))
    done = subprocess.run(
        ["bash", str(SCRIPT), "merged-prs-without-a-floor-read-30d"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "COUNT_LIST_PRS_SNAPSHOT": str(snapshot)},
        timeout=120,
    )
    assert done.returncode == 0 and done.stdout == "merged-prs-without-a-floor-read-30d\t3\n", done.stdout + done.stderr


@pytest.mark.skipif(not _develop_resolves(), reason="main() refuses a checkout with no develop ref before any entry runs")
def test_the_count_reads_the_line_the_way_the_gate_does(tmp_path):
    """One rule, one implementation. Three jq attempts to restate `merge-gate.py`'s arm each diverged in a
    different direction — case, line anchoring, an invented floor divergence — so the counter calls
    `read_line_fails` now and these rows pin the shapes those attempts got wrong: a lowercase MODEL is a read
    (only FLOOR is `re.I`), a lowercase PREFIX is not, a tail after the sha is not (the gate's line ends there),
    and an Opus read on a Fable path is not without the substitution line."""
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    head = "abcdef1234567aaaaaaaaaaaaaaaaaaaaaaaaaaa"
    prs = [
        {
            "headRefName": "feat/lower",
            "mergedAt": stamp,
            "headRefOid": head,
            "files": [],
            "body": "Read before push by: claude opus at abcdef1234567\n",
        },
        {
            "headRefName": "feat/spaced",
            "mergedAt": stamp,
            "headRefOid": head,
            "files": [],
            "body": "Read before push by:  Claude Fable 5.1  at  abcdef1234567\n",
        },
        {
            "headRefName": "feat/prefix",
            "mergedAt": stamp,
            "headRefOid": head,
            "files": [],
            "body": "read before push by: Claude Opus at abcdef1234567\n",
        },
        {
            "headRefName": "feat/tail",
            "mergedAt": stamp,
            "headRefOid": head,
            "files": [],
            "body": "Read before push by: Claude Opus at abcdef1234567 (tip)\n",
        },
        {
            "headRefName": "feat/fable-path",
            "mergedAt": stamp,
            "headRefOid": head,
            "files": [{"path": "cli/engine/soak.py"}],
            "body": "Read before push by: Claude Opus at abcdef1234567\n",
        },
        {
            "headRefName": "feat/substituted",
            "mergedAt": stamp,
            "headRefOid": head,
            "files": [{"path": "cli/engine/soak.py"}],
            "body": "Read before push by: Claude Opus at abcdef1234567\n\nFable floor substituted by Opus: the account's Fable quota is exhausted.\n",
        },
        {"headRefName": "feat/old", "mergedAt": "2026-01-01T00:00:00Z", "headRefOid": head, "files": [], "body": "## Summary\n"},
    ]
    snapshot = tmp_path / "prs.json"
    snapshot.write_text(json.dumps(prs))
    done = subprocess.run(
        ["bash", str(SCRIPT), "merged-prs-without-a-floor-read-30d"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "COUNT_LIST_PRS_SNAPSHOT": str(snapshot)},
        timeout=120,
    )
    assert done.returncode == 0 and done.stdout.strip().endswith("\t3"), done.stdout + done.stderr


@pytest.mark.skipif(not _develop_resolves(), reason="main() refuses a checkout with no develop ref before any entry runs")
def test_the_change_index_row_commit_is_the_one_head_the_read_line_need_not_cover(tmp_path):
    """The gate admits exactly one commit past the tip a read line names: a single-parent commit whose only file
    is the change index, which `open-pr` pushes after the read. The counter has to admit it too or it books every
    PR that used the exception. This arm needs the head COMMIT, not just its oid, so it was unkillable while the
    snapshot path could only return None -- `COUNT_LIST_HEADS_SNAPSHOT` is why it is killable now."""
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    read, head, other = "abcdef1234567", "99887766554433221100ffeeddccbbaa99887766", "0011223344556677889900aabbccddeeff001122"
    body = f"Read before push by: Claude Opus at {read}\n"
    prs = [
        {"headRefName": "feat/index-row", "mergedAt": stamp, "headRefOid": head, "files": [], "body": body},
        {"headRefName": "feat/other-commit", "mergedAt": stamp, "headRefOid": other, "files": [], "body": body},
        {"headRefName": "feat/old", "mergedAt": "2026-01-01T00:00:00Z", "headRefOid": head, "files": [], "body": "## Summary\n"},
    ]
    heads = {
        # One parent, and the change index alone: the exception.
        head: {"parents": [{"sha": read + "0" * (40 - len(read))}], "files": [{"filename": "docs/reference/change-index.md"}]},
        # One parent, but a second file: not the exception, so the read line does not cover this head.
        other: {
            "parents": [{"sha": read + "0" * (40 - len(read))}],
            "files": [{"filename": "docs/reference/change-index.md"}, {"filename": "cli/x.py"}],
        },
    }
    snapshot, head_snapshot = tmp_path / "prs.json", tmp_path / "heads.json"
    snapshot.write_text(json.dumps(prs))
    head_snapshot.write_text(json.dumps(heads))
    done = subprocess.run(
        ["bash", str(SCRIPT), "merged-prs-without-a-floor-read-30d"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "COUNT_LIST_PRS_SNAPSHOT": str(snapshot),
            "COUNT_LIST_HEADS_SNAPSHOT": str(head_snapshot),
        },
        timeout=120,
    )
    assert done.returncode == 0 and done.stdout.strip().endswith("\t1"), done.stdout + done.stderr


@pytest.mark.skipif(not _develop_resolves(), reason="main() refuses a checkout with no develop ref before any entry runs")
def test_a_truncated_file_list_is_refetched_before_the_fable_arm_decides(tmp_path):
    """`gh pr list --json files` returns the first page only, so a PR whose Fable path falls outside it reads as
    touching none — the counter would book it compliant where the gate refuses it. `changedFiles` is the exact
    truncation test, and the re-fetch has to happen BEFORE `read_line_fails` sees the list. The row below carries
    an Opus read, two innocuous paths and `changedFiles: 3`; the recorded full list adds `cli/engine/soak.py`, so
    it must count. Without the re-fetch it reads as touching nothing and does not."""
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    head = "abcdef1234567aaaaaaaaaaaaaaaaaaaaaaaaaaa"
    prs = [
        {
            "number": 4242,
            "headRefName": "feat/truncated",
            "mergedAt": stamp,
            "headRefOid": head,
            "changedFiles": 3,
            "files": [{"path": "docs/a.md"}, {"path": "docs/b.md"}],
            "body": "Read before push by: Claude Opus at abcdef1234567\n",
        },
        {
            "number": 4243,
            "headRefName": "feat/old",
            "mergedAt": "2026-01-01T00:00:00Z",
            "headRefOid": head,
            "changedFiles": 0,
            "files": [],
            "body": "## Summary\n",
        },
    ]
    snapshot, files_snapshot = tmp_path / "prs.json", tmp_path / "files.json"
    snapshot.write_text(json.dumps(prs))
    files_snapshot.write_text(json.dumps({"4242": ["docs/a.md", "docs/b.md", "cli/engine/soak.py"]}))
    done = subprocess.run(
        ["bash", str(SCRIPT), "merged-prs-without-a-floor-read-30d"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "COUNT_LIST_PRS_SNAPSHOT": str(snapshot),
            "COUNT_LIST_FILES_SNAPSHOT": str(files_snapshot),
        },
        timeout=120,
    )
    assert done.returncode == 0 and done.stdout.strip().endswith("\t1"), done.stdout + done.stderr


@pytest.mark.skipif(not _develop_resolves(), reason="main() refuses a checkout with no develop ref before any entry runs")
def test_a_row_with_no_file_list_is_counted_rather_than_read_as_touching_nothing(tmp_path):
    """`read_line_fails` has two refusals that fire only when `files` is None — the ops-journal exemption cannot
    be scoped, and the Fable paths cannot be checked. Mapping an ABSENT list to `[]` reports "touched nothing"
    and makes both unreachable, which books an Opus read on a Fable path compliant. The row below carries an
    Opus read and no `files` key at all, so it must count."""
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    head = "abcdef1234567aaaaaaaaaaaaaaaaaaaaaaaaaaa"
    prs = [
        {
            "headRefName": "feat/no-files",
            "mergedAt": stamp,
            "headRefOid": head,
            "body": "Read before push by: Claude Opus at abcdef1234567\n",
        },
        {"headRefName": "feat/old", "mergedAt": "2026-01-01T00:00:00Z", "headRefOid": head, "files": [], "body": "## Summary\n"},
    ]
    snapshot = tmp_path / "prs.json"
    snapshot.write_text(json.dumps(prs))
    done = subprocess.run(
        ["bash", str(SCRIPT), "merged-prs-without-a-floor-read-30d"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "COUNT_LIST_PRS_SNAPSHOT": str(snapshot)},
        timeout=120,
    )
    assert done.returncode == 0 and done.stdout.strip().endswith("\t1"), done.stdout + done.stderr


@pytest.mark.skipif(not _develop_resolves(), reason="main() refuses a checkout with no develop ref before any entry runs")
def test_an_empty_pr_fetch_is_an_error_rather_than_perfect_compliance(tmp_path):
    """An empty fetch used to print 0, which reads as every merged PR carrying its read line."""
    snapshot = tmp_path / "prs.json"
    snapshot.write_text("[]")
    done = subprocess.run(
        ["bash", str(SCRIPT), "merged-prs-without-a-floor-read-30d"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "COUNT_LIST_PRS_SNAPSHOT": str(snapshot)},
        timeout=120,
    )
    assert done.returncode == 2, f"an empty fetch must be an error, got rc {done.returncode}: {done.stdout}"
    assert "no rows at all" in done.stderr, done.stderr


@pytest.mark.skipif(not _develop_resolves(), reason="main() refuses a checkout with no develop ref before any entry runs")
def test_a_saturated_pr_fetch_is_an_error_rather_than_an_under_count(tmp_path):
    """Every row inside the window means the fetch stopped there: rows below it were never seen, so the count
    would under-report by however many it missed. 204 PRs against a --limit 200 is how this read 184 and called
    it a measurement."""
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    prs = [{"headRefName": f"feat/{i}", "mergedAt": stamp, "body": "## Summary\n"} for i in range(3)]
    snapshot = tmp_path / "prs.json"
    snapshot.write_text(json.dumps(prs))
    done = subprocess.run(
        ["bash", str(SCRIPT), "merged-prs-without-a-floor-read-30d"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "COUNT_LIST_PRS_SNAPSHOT": str(snapshot)},
        timeout=120,
    )
    assert done.returncode == 2, f"a saturated fetch must be an error, got rc {done.returncode}: {done.stdout}"
    assert "saturated" in done.stderr, done.stderr


@pytest.mark.skipif(not _develop_resolves(), reason="main() refuses a checkout with no develop ref before any entry runs")
def test_a_named_entry_runs_alone_and_an_unknown_name_is_refused():
    one = subprocess.run(
        ["bash", str(SCRIPT), "markdown-directly-under-docs"], cwd=REPO, capture_output=True, text=True, timeout=120
    )
    assert one.returncode == 0 and one.stdout.splitlines() == [
        f"markdown-directly-under-docs\t{one.stdout.split(chr(9))[1].strip()}"
    ], one.stdout + one.stderr
    none = subprocess.run(["bash", str(SCRIPT), "no-such-entry"], cwd=REPO, capture_output=True, text=True, timeout=120)
    assert none.returncode == 2 and "no entry named no-such-entry" in none.stderr, none.stdout + none.stderr


@pytest.mark.skipif(not _develop_resolves(), reason="five counts read the develop ref by name, and this checkout has none")
def test_the_script_prints_one_shaped_line_per_entry():
    """Run against a recorded feed, so the maintenance count reaches no venue from a test."""
    done = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "COUNT_LIST_FEED_SNAPSHOT": str(FEED)},
        timeout=1800,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert len(lines) == len(_ENTRY.findall(SCRIPT.read_text())), done.stdout
    for line in lines:
        name, tab, value = line.partition("\t")
        assert tab == "\t" and name, f"no name and tab: {line!r}"
        for part in value.split("; "):
            assert _VALUE.fullmatch(part), f"{name} printed no count: {value!r}"


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def _merge(repo: pathlib.Path, branch: str, files: list[str]) -> None:
    _git(repo, "checkout", "-q", "-b", branch)
    for rel in files:
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(f"{branch}\n")
        _git(repo, "add", rel)
        _git(repo, "commit", "-qm", f"add {rel}")
    _git(repo, "checkout", "-q", "develop")
    _git(repo, "merge", "-q", "--no-ff", "-m", f"Merge pull request from {branch}", branch)


def _topic_only_merges(repo: pathlib.Path) -> str:
    script = f'source "{SCRIPT}"; cd "{repo}"; count_micro_prs develop'
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    subprocess.run(["git", "init", "-q", "-b", "develop", str(tmp_path)], check=True)
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "README.md").write_text("base\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def test_the_topic_only_arm_counts_a_merge_only_when_every_file_it_brought_in_is_a_topic_file(repo):
    """One file outside `docs/open-topics/` disqualifies the whole merge, however many topic files ride with it."""
    _merge(repo, "mixed", ["docs/open-topics/T9998-parked.md", "cli/thing.py"])
    assert _topic_only_merges(repo) == "0"
    _merge(repo, "topics-only", ["docs/open-topics/T9999-parked.md", "docs/open-topics/README.md"])
    assert _topic_only_merges(repo) == "1"
