"""The PostToolUse[Bash] behind-remote guard, driven with synthetic stdin over a scratch clone of a
bare remote that a second clone advances: after a command carrying `git fetch`, `git pull`,
`git merge`, `git rebase` or `git remote update`, a tracking branch left behind its upstream is
reported -- branch, upstream, count and the one command that closes it -- as hook JSON on stdout
with rc 0, and every other state is silent.

The script judges the repo the command names and reads no `cwd` field from the JSON, so a case pins
both the subprocess cwd and the directory written into the command.
"""

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "behind-remote-guard.sh"


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check)


def commit_file(repo: Path, name: str, content: str = "x\n") -> None:
    (repo / name).write_text(content)
    git(repo, "add", name)
    git(repo, "commit", "-qm", name)


def configured(repo: Path) -> Path:
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    return repo


def make_pair(root: Path) -> tuple[Path, Path]:
    """`local` tracks `main` on a bare remote; `other` is the second clone that advances it."""
    remote = root / "remote.git"
    git(root, "init", "-q", "--bare", "-b", "main", str(remote))
    local = root / "local"
    local.mkdir()
    git(local, "init", "-q", "-b", "main")
    configured(local)
    commit_file(local, "base.txt")
    git(local, "remote", "add", "origin", str(remote))
    git(local, "push", "-q", "-u", "origin", "main")
    git(root, "clone", "-q", str(remote), str(root / "other"))
    other = configured(root / "other")
    return local, other


def advance_remote(other: Path, n: int, branch: str | None = None) -> None:
    if branch:
        git(other, "checkout", "-q", "-b", branch)
    for i in range(n):
        commit_file(other, f"{branch or 'main'}-{i}.txt")
    git(other, "push", "-q", "-u", "origin", branch or "main")


def make_behind_repo(root: Path) -> Path:
    """`local` fetched a `main` that `other` moved two commits past it, and never fast-forwarded."""
    local, other = make_pair(root)
    advance_remote(other, 2)
    git(local, "fetch", "-q", "origin")
    assert git(local, "rev-list", "--count", "HEAD..@{u}").stdout.strip() == "2", "fixture failed to fall behind"
    return local


@pytest.fixture
def behind_repo(tmp_path: Path) -> Path:
    return make_behind_repo(tmp_path)


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    return make_pair(tmp_path)


def run_hook(payload: dict | str, cwd: Path) -> subprocess.CompletedProcess:
    """Run the hook with `cwd` as the PROCESS cwd; dicts are JSON-encoded, strings pass through
    verbatim so the malformed-input cases can hand the hook something that is not JSON."""
    return subprocess.run(
        ["bash", str(HOOK)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def hook_payload(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def reported(result: subprocess.CompletedProcess) -> str:
    """The systemMessage of a report; the rc, the clean stderr and the additionalContext copy are
    asserted on the way through."""
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout, "expected a report"
    out = json.loads(result.stdout)
    msg = out["systemMessage"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert msg in out["hookSpecificOutput"]["additionalContext"]
    return msg


def assert_silent(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_a_fetch_that_leaves_the_branch_behind_is_reported(behind_repo: Path):
    msg = reported(run_hook(hook_payload("git fetch origin"), cwd=behind_repo))
    assert "main is behind origin/main by 2" in msg
    assert "git pull --ff-only" in msg


@pytest.mark.parametrize(
    "command",
    [
        "git pull --ff-only",
        "git merge --ff-only origin/main",
        "git rebase origin/main",
        "git remote update",
        "gh pr merge 1 --squash --delete-branch && git fetch origin",
    ],
    ids=["pull", "merge", "rebase", "remote_update", "compound_fetch"],
)
def test_every_verb_that_moves_refs_is_judged(behind_repo: Path, command: str):
    # The five verbs, fetch buried in the compound shape a merge closeout takes.
    assert "by 2" in reported(run_hook(hook_payload(command), cwd=behind_repo))


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git merge-base HEAD origin/main",
        "git log --merges -1",
        "gh pr merge 1 --squash",
        "git remote -v",
        "git switch -c topic",
        "git checkout main",
        "git worktree add ../wt",
    ],
    ids=["status", "merge_base", "log_merges", "gh_pr_merge", "remote_v", "switch", "checkout", "worktree_add"],
)
def test_a_command_without_a_verb_is_silent_on_the_same_behind_state(behind_repo: Path, command: str):
    # Same behind state -- so this pins the COMMAND filter, `merge-base` included, not an absent condition.
    assert_silent(run_hook(hook_payload(command), cwd=behind_repo))


@pytest.mark.parametrize(
    "command",
    [
        "git --no-pager fetch origin",
        "git -c core.pager=cat fetch origin",
        "git -ccore.pager=cat --no-optional-locks --literal-pathspecs fetch origin",
    ],
    ids=["no_pager", "dash_c", "dash_c_attached_and_two_more"],
)
def test_a_global_option_between_git_and_the_verb_is_stepped_over(behind_repo: Path, command: str):
    # git 2.47.3 refuses the attached `-c` spelling; the arm stays, since what is reported is the
    # repo's state, true whether or not the command ran.
    assert "by 2" in reported(run_hook(hook_payload(command), cwd=behind_repo))


def test_a_diverged_branch_names_both_counts_and_the_rebase(behind_repo: Path):
    commit_file(behind_repo, "mine.txt")
    msg = reported(run_hook(hook_payload("git pull --ff-only"), cwd=behind_repo))
    assert "by 2 and ahead by 1" in msg
    assert "git pull --rebase" in msg


def test_a_fetch_of_another_branch_leaves_a_level_branch_silent(pair: tuple[Path, Path]):
    local, other = pair
    advance_remote(other, 1, branch="side")
    git(local, "fetch", "-q", "origin", "side")
    assert_silent(run_hook(hook_payload("git fetch origin side"), cwd=local))


def test_a_branch_ahead_of_its_upstream_is_silent(pair: tuple[Path, Path]):
    local, _ = pair
    commit_file(local, "mine.txt")
    assert_silent(run_hook(hook_payload("git fetch origin"), cwd=local))


def test_a_branch_with_no_upstream_is_silent(behind_repo: Path):
    git(behind_repo, "checkout", "-q", "-b", "topic")
    assert git(behind_repo, "rev-parse", "--abbrev-ref", "@{u}", check=False).returncode != 0
    assert_silent(run_hook(hook_payload("git fetch origin"), cwd=behind_repo))


def test_a_detached_head_is_silent(behind_repo: Path):
    git(behind_repo, "checkout", "-q", "--detach")
    assert_silent(run_hook(hook_payload("git fetch origin"), cwd=behind_repo))


def test_a_pruned_upstream_is_silent(pair: tuple[Path, Path]):
    # The closeout shape: the PR branch's remote is deleted, the local checkout keeps its tracking
    # config, and `git fetch --prune` removes the ref -- there is nothing to be behind.
    local, other = pair
    advance_remote(other, 1, branch="feature")
    git(local, "fetch", "-q", "origin")
    git(local, "checkout", "-q", "-b", "feature", "origin/feature")
    git(other, "push", "-q", "origin", "--delete", "feature")
    git(local, "fetch", "-q", "--prune")
    assert git(local, "rev-parse", "--abbrev-ref", "@{u}", check=False).returncode != 0
    assert_silent(run_hook(hook_payload("git fetch --prune"), cwd=local))


def test_a_merge_in_progress_is_silent(pair: tuple[Path, Path]):
    # HEAD..@{u} is non-empty while the merge is unresolved, and `git pull --ff-only` would be the
    # wrong instruction: the fix is to finish the merge.
    local, other = pair
    commit_file(other, "clash.txt", "theirs\n")
    git(other, "push", "-q")
    commit_file(local, "clash.txt", "mine\n")
    git(local, "fetch", "-q", "origin")
    assert git(local, "merge", "origin/main", check=False).returncode != 0
    assert git(local, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0
    assert_silent(run_hook(hook_payload("git merge origin/main"), cwd=local))


def test_a_cherry_pick_in_progress_is_silent(behind_repo: Path):
    # Diverged (behind 2, ahead 1) while the pick is unresolved, the same shape as the merge above.
    commit_file(behind_repo, "main-0.txt", "mine\n")
    assert git(behind_repo, "cherry-pick", "origin/main~1", check=False).returncode != 0
    assert git(behind_repo, "rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD").returncode == 0
    assert_silent(run_hook(hook_payload("git fetch origin && git cherry-pick origin/main~1"), cwd=behind_repo))


def test_a_revert_in_progress_is_silent(behind_repo: Path):
    commit_file(behind_repo, "base.txt", "mine\n")
    assert git(behind_repo, "revert", "--no-edit", "HEAD~1", check=False).returncode != 0
    assert git(behind_repo, "rev-parse", "-q", "--verify", "REVERT_HEAD").returncode == 0
    assert_silent(run_hook(hook_payload("git fetch origin && git revert HEAD~1"), cwd=behind_repo))


@pytest.mark.parametrize(
    "payload",
    [
        "",  # empty stdin
        "not json at all",
        "{",  # truncated object
        "[]",  # valid JSON, wrong shape
        '{"tool_input": {}}',  # right shape, no command key
    ],
)
def test_bad_input_never_reports_or_breaks_the_bash_call(behind_repo: Path, payload: str):
    # Behind state present, so a hook that mis-parsed into a truthy command would report here.
    assert_silent(run_hook(payload, cwd=behind_repo))


def test_outside_a_git_repo_is_silent(tmp_path: Path):
    outside = tmp_path / "plain"
    outside.mkdir()
    assert_silent(run_hook(hook_payload("git fetch origin"), cwd=outside))


def test_dash_c_form_judges_the_named_repo_and_the_fix_carries_it(tmp_path: Path):
    other = tmp_path / "named"
    other.mkdir()
    make_behind_repo(other)
    clean_cwd = tmp_path / "clean"
    clean_cwd.mkdir()
    msg = reported(run_hook(hook_payload(f"git -C {other / 'local'} fetch origin"), cwd=clean_cwd))
    assert "main is behind origin/main by 2" in msg
    assert f"git -C {other / 'local'} pull --ff-only" in msg


def test_repeated_dash_c_is_joined_as_git_chdirs_through_it(tmp_path: Path):
    other = tmp_path / "named"
    other.mkdir()
    make_behind_repo(other)
    clean_cwd = tmp_path / "clean"
    clean_cwd.mkdir()
    command = f"git -C {clean_cwd} -c core.pager=cat -C {other} -C local fetch origin"
    msg = reported(run_hook(hook_payload(command), cwd=clean_cwd))
    assert f"git -C {other / 'local'} pull --ff-only" in msg


def test_unspaced_cd_form_judges_the_named_repo(tmp_path: Path):
    other = tmp_path / "named"
    other.mkdir()
    make_behind_repo(other)
    clean_cwd = tmp_path / "clean"
    clean_cwd.mkdir()
    msg = reported(run_hook(hook_payload(f"cd {other / 'local'};git pull --ff-only"), cwd=clean_cwd))
    assert "main is behind origin/main by 2" in msg


@pytest.mark.parametrize(
    "template",
    [
        'git -C "$WORKDIR" fetch origin',
        "git --git-dir={repo}/.git fetch origin",
        "git --git-dir={repo}/.git --work-tree={repo} fetch origin",
    ],
    ids=["variable", "git_dir", "git_dir_and_work_tree"],
)
def test_an_unresolvable_dir_judges_nothing(behind_repo: Path, template: str):
    # Behind state in the PROCESS cwd, so a fallback to it would report here.
    assert_silent(run_hook(hook_payload(template.format(repo=behind_repo)), cwd=behind_repo))


def test_two_repos_in_one_command_are_each_judged(tmp_path: Path):
    first = tmp_path / "first"
    first.mkdir()
    make_behind_repo(first)
    second = tmp_path / "second"
    second.mkdir()
    make_behind_repo(second)
    command = f"git -C {first / 'local'} fetch origin && git -C {second / 'local'} fetch origin"
    msg = reported(run_hook(hook_payload(command), cwd=tmp_path))
    assert f"git -C {first / 'local'} pull --ff-only" in msg
    assert f"git -C {second / 'local'} pull --ff-only" in msg


def test_hook_is_executable():
    assert HOOK.stat().st_mode & 0o111, "the hook must be executable -- settings.json invokes it directly"


def test_hook_is_wired_as_a_posttooluse_bash_hook():
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    commands = [
        hook["command"] for entry in settings["hooks"]["PostToolUse"] if entry["matcher"] == "Bash" for hook in entry["hooks"]
    ]
    assert any("behind-remote-guard.sh" in c for c in commands), "the hook is inert unless settings.json wires it"
