from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "infra" / "scripts"
SCRIPT = SCRIPTS / "launch-read.py"
LEDGER = SCRIPTS / "review-ledger.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def _git(repo: Path, *args: str) -> str:
    when = "2026-09-01T00:00:00Z"
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_AUTHOR_DATE": when}
    env |= {"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_COMMITTER_DATE": when}
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args], env=env, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    for n in range(4):
        (root / "a.txt").write_text(f"{n}\n")
        _git(root, "add", "a.txt")
        _git(root, "commit", "-q", "-m", f"c{n}")
    return root


@pytest.fixture
def shas(repo: Path) -> list[str]:
    return [_git(repo, "rev-parse", f"HEAD~{n}") for n in (3, 2, 1, 0)]


def _args(kind: str, repo: Path, *extra: str, base: str = "HEAD~3", tip: str = "HEAD") -> subprocess.CompletedProcess:
    report_dir = repo.parent / "reads"
    return _run("args", kind, "--repo", str(repo), "--base", base, "--tip", tip, "--report-dir", str(report_dir), *extra)


def _ok(done: subprocess.CompletedProcess) -> dict:
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _refused(done: subprocess.CompletedProcess, *names: str) -> None:
    assert done.returncode == 2, (done.returncode, done.stdout, done.stderr)
    assert done.stdout == ""
    for name in names:
        assert name in done.stderr, done.stderr


def _prior(repo: Path, *severities: str) -> str:
    path = repo.parent / "prior.json"
    rows = [{"id": n, "severity": s, "path": "a.txt", "line": 1, "claim": "one line"} for n, s in enumerate(severities, 1)]
    path.write_text(json.dumps(rows))
    return str(path)


def test_args_resolves_every_rev_to_its_full_sha(repo: Path, shas: list[str]):
    out = _ok(_args("pre-review", repo, base="HEAD~3", tip=shas[3][:7]))
    assert out == {
        "repo": str(repo.resolve()),
        "range": f"{shas[0]}..{shas[3]}",
        "tip": shas[3],
        "reportDir": str((repo.parent / "reads").resolve()),
        "model": "opus",
    }


@pytest.mark.parametrize("end", ["base", "tip"])
def test_a_hand_extended_sha_is_refused_by_name(repo: Path, shas: list[str], end: str):
    full = shas[3] if end == "tip" else shas[0]
    extended = full[:7] + ("0" if full[7] != "0" else "1")
    _refused(_args("review", repo, **{end: extended}), repr(extended), "names no commit")


def test_review_takes_the_ledger_review_ledger_reads(repo: Path, shas: list[str]):
    reads = repo.parent / "reads"
    reads.mkdir()
    rows = [{"kind": "pre-review", "range": "a..b", "tip": shas[3][:7]}, {"kind": "pre-review", "range": "a..b", "tip": shas[2]}]
    (reads / "ledger.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    expected = subprocess.run(
        [sys.executable, str(LEDGER), "read", str(reads), "--tip", shas[3], "--repo", str(repo)],
        capture_output=True,
        text=True,
        check=True,
    )
    ledger = json.loads(expected.stdout)
    assert [e["against"] for e in ledger] == [shas[3], shas[3]]
    out = _ok(_args("review", repo, tip="HEAD"))
    assert out["ledger"] == ledger
    assert list(out) == ["repo", "range", "tip", "reportDir", "ledger", "model"]


def test_re_review_carries_its_priors_and_the_ledger(repo: Path):
    out = _ok(
        _args("re-review", repo, "--prior", _prior(repo, "Critical", "Important"), "--reported", "#3 left", "--model", "fable")
    )
    assert [p["severity"] for p in out["prior"]] == ["Critical", "Important"]
    assert out["ledger"] == [] and out["reported"] == "#3 left" and out["model"] == "fable"


@pytest.mark.parametrize("kind", ["review", "re-review"])
def test_a_drive_over_400_characters_is_refused(repo: Path, kind: str):
    prior = ("--prior", _prior(repo, "Important")) if kind == "re-review" else ()
    assert _ok(_args(kind, repo, *prior, "--drive", "d" * 400))["drive"] == "d" * 400
    _refused(_args(kind, repo, *prior, "--drive", "d" * 401), "401 characters", "at most 400")


def test_the_drive_is_measured_in_utf16_units_as_the_workflow_counts_it(repo: Path):
    _refused(_args("review", repo, "--drive", "d" * 399 + "\U0001f600"), "401 characters")


@pytest.mark.parametrize("severity", ["Minor", "minor", None])
def test_a_prior_that_is_not_critical_or_important_is_refused(repo: Path, severity: str | None):
    _refused(_args("re-review", repo, "--prior", _prior(repo, "Critical", severity)), f"prior #2 is {severity}", "--reported")


def test_a_prior_file_that_is_not_an_array_of_findings_is_refused(repo: Path):
    path = repo.parent / "prior.json"
    path.write_text(json.dumps({"id": 1, "severity": "Critical"}))
    _refused(_args("re-review", repo, "--prior", str(path)), "not a JSON array")


def test_chained_ranges_pass_with_full_shas(repo: Path, shas: list[str]):
    out = _ok(_args("pre-review", repo, "--ranges", "one=HEAD~3..HEAD~2", f"two={shas[1][:9]}..HEAD", "--rulings", "r.md"))
    assert out["ranges"] == [{"label": "one", "range": f"{shas[0]}..{shas[1]}"}, {"label": "two", "range": f"{shas[1]}..{shas[3]}"}]
    assert out["rulings"] == "r.md"


@pytest.mark.parametrize(
    ("ranges", "says"),
    [
        (["one=HEAD~2..HEAD~1", "two=HEAD~1..HEAD"], "one opens at"),
        (["one=HEAD~3..HEAD~2", "two=HEAD~1..HEAD"], "two opens at"),
        (["one=HEAD~3..HEAD~1", "two=HEAD~2..HEAD"], "two opens at"),
        (["one=HEAD~3..HEAD~3", "two=HEAD~3..HEAD"], "one is empty"),
        (["one=HEAD~3..HEAD~2", "two=HEAD~2..HEAD~1"], "the last slice closes at"),
    ],
    ids=["opens-late", "gap", "overlap", "empty", "closes-short"],
)
def test_ranges_that_do_not_chain_from_base_to_tip_are_refused(repo: Path, ranges: list[str], says: str):
    _refused(_args("pre-review", repo, "--ranges", *ranges), "chain from --base to --tip", says)


@pytest.mark.parametrize(
    ("extra", "says"),
    [
        (["--ranges", "HEAD~3..HEAD"], "is not <label>=<base>..<tip>"),
        (["--ranges", "one=HEAD~3...HEAD"], "is not <label>=<base>..<tip>"),
        (["--ranges", "One=HEAD~3..HEAD"], "label 'One'"),
        (["--ranges=-one=HEAD~3..HEAD"], "label '-one'"),
        (["--ranges", "a" * 33 + "=HEAD~3..HEAD"], "is not 1 to 32"),
        (["--ranges", "one=HEAD~3..HEAD~1", "one=HEAD~1..HEAD"], "not unique"),
    ],
    ids=["no-label", "three-dots", "uppercase", "dash-first", "too-long", "repeated"],
)
def test_a_malformed_or_repeated_range_label_is_refused(repo: Path, extra: list[str], says: str):
    _refused(_args("pre-review", repo, *extra), says)


@pytest.mark.parametrize(
    ("kind", "extra", "says"),
    [
        ("pre-review", ("--drive", "x"), "pre-review takes no --drive"),
        ("pre-review", ("--reported", "x"), "pre-review takes no --reported"),
        ("review", ("--rulings", "x"), "review takes no --rulings"),
        ("review", ("--ranges", "one=HEAD~3..HEAD"), "review takes no --ranges"),
        ("review", ("--prior", "p.json"), "review takes no --prior"),
        ("re-review", ("--prior", "p.json", "--rulings", "x"), "re-review takes no --rulings"),
    ],
)
def test_a_flag_the_workflow_does_not_take_is_refused(repo: Path, kind: str, extra: tuple[str, ...], says: str):
    _refused(_args(kind, repo, *extra), says)


def test_pre_review_runs_on_opus_alone(repo: Path):
    assert _ok(_args("review", repo, "--model", "fable"))["model"] == "fable"
    _refused(_args("pre-review", repo, "--model", "fable"), "pre-review runs on opus, never fable")


def test_re_review_without_priors_is_refused(repo: Path):
    _refused(_args("re-review", repo), "re-review takes --prior")


def test_brief_appends_the_standing_lines_once(tmp_path: Path):
    brief, lines = tmp_path / "brief.md", tmp_path / "lines.md"
    brief.write_text("# Brief\n\nBuild the thing.")
    lines.write_text("## Standing lines\n\n- One.\n- Two.\n")
    for _ in range(2):
        done = _run("brief", str(brief), "--lines", str(lines))
        assert done.returncode == 0, done.stderr
        assert done.stdout == f"{brief.resolve()}\n"
        assert brief.read_text() == "# Brief\n\nBuild the thing.\n## Standing lines\n\n- One.\n- Two.\n"


@pytest.mark.parametrize("which", ["missing", "empty"])
def test_brief_refuses_a_lines_file_with_nothing_to_append(tmp_path: Path, which: str):
    brief, lines = tmp_path / "brief.md", tmp_path / "lines.md"
    brief.write_text("# Brief\n")
    if which == "empty":
        lines.write_text("\n")
    _refused(_run("brief", str(brief), "--lines", str(lines)), str(lines))
    assert brief.read_text() == "# Brief\n"
