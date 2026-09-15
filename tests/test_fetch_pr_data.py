"""`.claude/skills/release/scripts/fetch-pr-data.py` prepares the changelog's input: the version `cz version --project`
reports, today's date, and of the merged PRs into `develop` that `gh pr list` returns, those merged after the last tag
reachable from `origin/main` -- every one when there is no such tag -- each classified by its Conventional Commits
type, written to `/tmp/release_pr_data_<session>.json` for the session named by the first argument. `cz` and `gh` are
PATH stubs here; git is real, over a scratch repository."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "release" / "scripts" / "fetch-pr-data.py"
_TAG_DATE = "2026-01-02T00:00:00+00:00"
_PRS = [
    {
        "number": 1,
        "title": "fix(cli): before the tag",
        "body": "b1",
        "url": "u1",
        "author": {"login": "ann"},
        "mergedAt": "2026-01-01T10:00:00Z",
    },
    {
        "number": 2,
        "title": "feat(engine): after the tag",
        "body": "b2",
        "url": "u2",
        "author": {"login": "bob"},
        "mergedAt": "2026-01-03T10:00:00Z",
    },
    {
        "number": 3,
        "title": "no conventional prefix",
        "body": "",
        "url": "u3",
        "author": {"login": "cid"},
        "mergedAt": "2026-01-04T10:00:00Z",
    },
    {"number": 4, "title": "chore(deps): never merged", "body": "", "url": "u4", "author": {"login": "dee"}, "mergedAt": None},
]


def _stub(path: Path, body: str) -> None:
    path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _repo(tmp_path: Path, *, tagged: bool) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_DATE": _TAG_DATE, "GIT_COMMITTER_DATE": _TAG_DATE}

    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)

    git("init", "-q", "-b", "develop")
    git("config", "user.email", "t@example.invalid")
    git("config", "user.name", "t")
    git("config", "commit.gpgsign", "false")
    (repo / "seed").write_text("x\n", encoding="utf-8")
    git("add", "seed")
    git("commit", "-qm", "seed")
    if tagged:
        git("tag", "v1.0.0")
        git("update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def _prepare(tmp_path: Path, session: str, *, tagged: bool) -> tuple[subprocess.CompletedProcess[str], str]:
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    _stub(bin_ / "cz", "[ \"$1 $2\" = 'version --project' ] || exit 9\necho 9.9.9")
    _stub(bin_ / "gh", 'printf \'%s\\n\' "$*" > "$GH_ARGS"\ncat "$GH_PRS"')
    (tmp_path / "prs.json").write_text(json.dumps(_PRS), encoding="utf-8")
    env = {
        "PATH": f"{bin_}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "GH_ARGS": str(tmp_path / "gh.args"),
        "GH_PRS": str(tmp_path / "prs.json"),
    }
    done = subprocess.run(
        [sys.executable, str(_SCRIPT), session], capture_output=True, text=True, cwd=_repo(tmp_path, tagged=tagged), env=env
    )
    return done, (tmp_path / "gh.args").read_text(encoding="utf-8")


def _session() -> tuple[str, Path]:
    session = f"test-{uuid.uuid4().hex}"
    return session, Path(f"/tmp/release_pr_data_{session}.json")


def test_only_prs_merged_after_the_last_tag_are_kept_each_classified_by_type(tmp_path):
    session, out = _session()
    try:
        before = dt.date.today().isoformat()
        done, gh_args = _prepare(tmp_path, session, tagged=True)
        after = dt.date.today().isoformat()
        assert done.returncode == 0, done.stderr
        assert "pr list --state merged --base develop" in gh_args
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["version"] == "9.9.9" and data["release_date"] in {before, after}
        assert [pr["number"] for pr in data["prs"]] == [2, 3]
        feat, other = data["prs"]
        assert feat == {
            "number": 2,
            "title": "feat(engine): after the tag",
            "description": "b2",
            "url": "u2",
            "author": "bob",
            "type": "feat",
            "type_label": "Features",
            "short_desc": "after the tag",
        }
        assert (other["type"], other["type_label"], other["short_desc"]) == ("other", "Other Changes", "no conventional prefix")
        assert done.stdout.splitlines() == ["Prepared 2 PRs for changelog generation", f"Data saved to {out}"]
    finally:
        out.unlink(missing_ok=True)


def test_without_a_tag_every_merged_pr_is_kept(tmp_path):
    session, out = _session()
    try:
        done, _ = _prepare(tmp_path, session, tagged=False)
        assert done.returncode == 0, done.stderr
        assert [pr["number"] for pr in json.loads(out.read_text(encoding="utf-8"))["prs"]] == [1, 2, 3]
        assert done.stdout.splitlines()[0] == "Prepared 3 PRs for changelog generation"
    finally:
        out.unlink(missing_ok=True)
