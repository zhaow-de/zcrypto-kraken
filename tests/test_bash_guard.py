"""The PreToolUse[Bash] guard's four arms -- the git hook bypasses, a stream a cap has already shortened being
counted or compared, a vaulted file printed, and a dispatched agent's push, GitHub write or git that moves the main
checkout -- driven with synthetic stdin JSON.

The hook is `.claude/hooks/bash-guard.sh`; its header carries only what this corpus and the code cannot say. Every
family is driven in both directions: the spelling an arm refuses (exit 2, `BLOCKED` and the spelling on stderr) beside
the ordinary shape nearest to it that it must admit (exit 0, silent) -- the flag as message text, in a heredoc body, in a
comment, after `--`, or on a subcommand where it means something else; the `head` that opens a file rather than a
pipe, the `tail -n +2` that caps nothing, the count before the cap, and the pipe into `head` that only looks; the
count, the hash and the public half beside a vaulted file; the read, the worktree and the main loop beside a dispatched
agent's write.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "bash-guard.sh"
# The hook judges these paths as text and never touches them, so a worktree need not exist to be one.
MAIN = str(
    Path(
        subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    ).parent
)
WORKTREE = f"{MAIN}/.claude/worktrees/agent-x"
SCRATCH = f"{MAIN}/.tmp/scratch"

HEREDOC_MESSAGE = (
    "$(cat <<'EOF'\nclaude(settings): --no-verify and -n are refused\n\n-n in a bundle too, and \"--no-verify\" quoted\nEOF\n)"
)

# (command, the spelling the message must name)
REFUSED = [
    # commit: the flag in any position, an abbreviation, a bundle
    ("git commit --no-verify", "--no-verify"),
    ("git commit -m msg --no-verify", "--no-verify"),
    ("git commit --amend --no-verify", "--no-verify"),
    ("git commit --no-veri -am msg", "--no-veri"),
    ("git commit --no-v -m msg", "--no-v"),  # ambiguous to git; refused all the same
    ("git commit -n", "-n"),
    ("git commit -n -m msg", "-n"),
    ("git commit -nm msg", "-nm"),
    ("git commit -an -m msg", "-an"),
    ("git commit -qn -m msg", "-qn"),
    ("git commit -anm msg", "-anm"),
    ("git commit -am msg -n", "-n"),
    # an option before the subcommand, a path to git, an env prefix, a wrapper
    ("git -C /repo commit --no-verify -m msg", "--no-verify"),
    ("git -C /repo commit -n -m msg", "-n"),
    ('git -C "$WORKDIR" commit -n -m msg', "-n"),
    ("git --git-dir=.git --work-tree=. commit --no-verify", "--no-verify"),
    ("git --git-dir .git commit -n", "-n"),
    ("git --no-pager -c color.ui=never commit -n", "-n"),
    ("/usr/bin/git commit --no-verify", "--no-verify"),
    ("GIT_EDITOR=true git commit --no-verify", "--no-verify"),
    ("sudo git commit -n", "-n"),
    ("PATH=/opt/git git commit -n", "-n"),
    ("GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/x timeout 5 git commit -m x", "GIT_CONFIG_KEY_0"),
    ("GIT_CONFIG_PARAMETERS=\"'core.hooksPath=/x'\" setsid git commit -m x", "GIT_CONFIG_PARAMETERS"),
    ("nice env GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/x git commit -m x", "GIT_CONFIG_KEY_0"),
    ("git commit -m x $'\\x2dn'", "-n"),
    ("git commit -m x $'\\055n'", "-n"),
    ("git commit -n && (echo x)# don't", "-n"),
    ("git commit -m $(date)#x -n", "-n"),
    ("git add . && git commit -m $(date)#msg --no-verify", "--no-verify"),
    ("echo $(date)#c; git commit -n", "-n"),
    ("git commit -m <(date)#x -n", "-n"),
    ("git commit -m <(date)#x --no-verify", "--no-verify"),
    ("echo >(true)#c; git commit --no-verify", "--no-verify"),
    ("cat <(git commit -n)", "-n"),
    # a compound command, a redirect, a heredoc message beside the flag
    ("cd /repo && git commit --no-verify -m msg", "--no-verify"),
    ("git add . ; git commit -n -m msg", "-n"),
    ("git add x\ngit commit -n -m x", "-n"),
    ("git commit -m msg --no-verify >/dev/null 2>&1", "--no-verify"),
    (f'git commit -m "{HEREDOC_MESSAGE}" --no-verify', "--no-verify"),
    (f'git commit --no-verify -m "{HEREDOC_MESSAGE}"', "--no-verify"),
    # an unquoted # inside a word is text to bash, not a comment
    ("git commit -m issue#42 -n", "-n"),
    ("git commit -m fix#123 --no-verify", "--no-verify"),
    ("echo a#b; git commit -n", "-n"),
    ("cd /repo#1 && git commit -n", "-n"),
    ("git -C /repo commit -m x#y -n", "-n"),
    # an ANSI-C quoted message beside the flag
    ("git commit --amend -n -m $'it\\'s'", "-n"),
    ("git -C . commit -n -m $'don\\'t'", "-n"),
    ("git commit --no-veri -m $'don\\'t'", "--no-veri"),
    # a command substitution: $( .. ) and backticks, bare, assigned, double-quoted, inside a heredoc bash expands
    ("x=$(git commit -n)", "-n"),
    ('echo "$(git commit -n)"', "-n"),
    ("x=`git commit -n`", "-n"),
    ("`git commit --no-verify`", "--no-verify"),
    ('echo "`git commit -n`"', "-n"),
    ("cat <<EOF\n$(git commit -n)\nEOF", "-n"),
    ("cat <<EOF\n`git commit --no-verify`\nEOF", "--no-verify"),
    # merge, rebase, am; -n is --no-verify on am
    ("git merge --no-verify feature", "--no-verify"),
    ("git merge --no-veri feature", "--no-veri"),
    ("git rebase --no-verify main", "--no-verify"),
    ("git am --no-verify < patch", "--no-verify"),
    ("git am -n", "-n"),
    ("git am -n patch.mbox", "-n"),
    ("git am -3n patch.mbox", "-3n"),
    ("git -C /repo merge --no-verify feature", "--no-verify"),
    # core.hooksPath on the command line, in the environment, through config
    ("git -c core.hooksPath=/dev/null commit -m msg", "core.hooksPath"),
    ("git -c core.hookspath=/dev/null log -1", "core.hookspath"),
    ("git -C /repo -c core.hooksPath=/dev/null commit -m msg", "core.hooksPath"),
    ("git --config-env=core.hooksPath=HP commit -m msg", "core.hooksPath"),
    ("git --config-env core.hooksPath=HP commit -m msg", "core.hooksPath"),
    ("GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m msg", "GIT_CONFIG_KEY_0"),
    ("export GIT_CONFIG_PARAMETERS=\"'core.hooksPath=/dev/null'\"; git commit -m msg", "GIT_CONFIG_PARAMETERS"),
    ("env GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/x git commit -m msg", "GIT_CONFIG_KEY_0"),
    ("sudo GIT_CONFIG_PARAMETERS=\"'core.hooksPath=/x'\" git commit -m msg", "GIT_CONFIG_PARAMETERS"),
    ("git config core.hooksPath /dev/null", "core.hooksPath"),
    ("git config --local core.hooksPath /tmp/none", "core.hooksPath"),
    ("git config --global core.hooksPath /x", "core.hooksPath"),
    ("git config --worktree core.hooksPath /x", "core.hooksPath"),
    ("git config --file .git/config core.hooksPath /x", "core.hooksPath"),
    ("git config -f .git/config core.hooksPath /x", "core.hooksPath"),
    ("git config --add core.hooksPath /x", "core.hooksPath"),
    ("git config --replace-all core.hooksPath /x", "core.hooksPath"),
    ("git config set core.hooksPath /x", "core.hooksPath"),
    ("git config set --local core.hooksPath /x", "core.hooksPath"),
    ("git config core.HooksPath /x", "core.HooksPath"),
    ("git config core.hooksPath ''", "core.hooksPath"),
    ("git -C /repo config core.hooksPath /x", "core.hooksPath"),
    # a cap on a piped stream, then a count of it: in the pipeline, inside a substitution, through a heredoc
    ("git log --oneline | head -5 | wc -l", "head -5"),
    ("git ls-files | head -20 | wc -l", "head -20"),
    ("git log --oneline | tail -3 | grep -c fix", "tail -3"),
    ("grep -rn NEEDLE . | head | wc -l", "head"),
    ("cat f | head -n 5 | wc -l", "head -n 5"),
    ("git status --porcelain | head -1 | wc -c", "head -1"),
    ("git log | head -20 | sort -u | wc -l", "head -20"),  # the count need not be the next stage
    ("git grep -n TODO | head -10 | grep -c cli/", "head -10"),
    ("git log --oneline | head -5 | grep --count fix", "head -5"),
    ("git log --oneline | head -5 | rg --count-matches fix", "head -5"),
    ("uv run pytest -q | tail -1 | grep -c passed", "tail -1"),
    ("find . -name '*.py' | head -100 | wc -l", "head -100"),
    ("x=$(git log | head -3 | wc -l)", "head -3"),
    ('echo "$(git log | head -3 | wc -l)"', "head -3"),
    ("cat <<EOF\n$(ls | head -2 | wc -l)\nEOF", "head -2"),
    # a cap on a piped stream a test then compares: quoted, unquoted, backticked, behind `if`
    ('test "$(ls | tail -1)" = x', "tail -1"),
    ("[[ $(git ls-files | tail -1) = x ]]", "tail -1"),
    ('[ "`ls | head -1`" = x ]', "head -1"),
    ('if [ "$(git diff --name-only | tail -1)" = x ]; then echo one; fi', "tail -1"),
    # the bypass arm still judges the rest of a command line whose test holds a body that does not tokenise
    ('[ -n "$(git log --grep=doesn\'t)" ] && git commit -n -m x', "-n"),
]

# (command, the vaulted file or the decrypting program the message must name)
VAULTED = [
    # the 2026-09-24 shape, and every reader the family names, over each kind of vaulted file
    ("head -1 infra/ansible/files/deploy_zaccess_ed25519", "infra/ansible/files/deploy_zaccess_ed25519"),
    ("cat infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("tail -n 3 infra/ansible/host_vars/zcrypto-ops/vault.yml", "infra/ansible/host_vars/zcrypto-ops/vault.yml"),
    ("less infra/ansible/vault-password.sops.yaml", "infra/ansible/vault-password.sops.yaml"),
    ("more infra/ansible/files/zaccess_ca.key.vault", "infra/ansible/files/zaccess_ca.key.vault"),
    ("sed -n 1p infra/ansible/files/sync_ed25519", "infra/ansible/files/sync_ed25519"),
    ("awk 'NR==1' infra/ansible/files/zcrypto_hot_push_ed25519", "infra/ansible/files/zcrypto_hot_push_ed25519"),
    ("cut -c1-20 infra/ansible/group_vars/engine_host/vault.yml", "infra/ansible/group_vars/engine_host/vault.yml"),
    ("strings infra/ansible/files/deploy_nas_ed25519", "infra/ansible/files/deploy_nas_ed25519"),
    ("xxd infra/ansible/files/deploy_zcrypto_ed25519 | head", "infra/ansible/files/deploy_zcrypto_ed25519"),
    ("od -c infra/ansible/files/deploy_zcrypto-ops_ed25519", "infra/ansible/files/deploy_zcrypto-ops_ed25519"),
    ("base64 infra/ansible/files/deploy_zcrypto-red_ed25519", "infra/ansible/files/deploy_zcrypto-red_ed25519"),
    ("tac infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("hexdump -C infra/ansible/files/deploy_zcrypto-valkey1_ed25519", "infra/ansible/files/deploy_zcrypto-valkey1_ed25519"),
    # relative to another directory, bare, globbed, redirected, wrapped, substituted
    ("cd infra/ansible && cat files/deploy_zcrypto_ed25519", "files/deploy_zcrypto_ed25519"),
    ("cat deploy_zcrypto_ed25519", "deploy_zcrypto_ed25519"),
    ("cat group_vars/all/vault.yml", "group_vars/all/vault.yml"),
    ("cat infra/ansible/files/deploy_*", "infra/ansible/files/deploy_*"),
    ("head -2 infra/ansible/group_vars/*/vault.yml", "infra/ansible/group_vars/*/vault.yml"),
    ("cat infra/ansible/group_vars/all/*", "infra/ansible/group_vars/all/*"),
    ("head -1 < infra/ansible/files/deploy_zaccess_ed25519", "infra/ansible/files/deploy_zaccess_ed25519"),
    ("sudo cat infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("timeout 5 head -1 infra/ansible/files/deploy_zaccess_ed25519", "infra/ansible/files/deploy_zaccess_ed25519"),
    ("x=$(cat infra/ansible/files/deploy_zaccess_ed25519)", "infra/ansible/files/deploy_zaccess_ed25519"),
    # python -c opening one, a copy of one elsewhere, a decrypt, a revision's copy
    (
        "python3 -c \"print(open('infra/ansible/files/deploy_zaccess_ed25519').read())\"",
        "infra/ansible/files/deploy_zaccess_ed25519",
    ),
    (
        "uv run python -c \"import pathlib; print(pathlib.Path('infra/ansible/group_vars/all/vault.yml').read_text())\"",
        "infra/ansible/group_vars/all/vault.yml",
    ),
    ("cp infra/ansible/files/deploy_zaccess_ed25519 /tmp/k", "infra/ansible/files/deploy_zaccess_ed25519"),
    ("scp infra/ansible/files/deploy_zaccess_ed25519 nas:/tmp/", "infra/ansible/files/deploy_zaccess_ed25519"),
    ("rsync -a infra/ansible/group_vars/all/vault.yml /tmp/v.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("cp -t /tmp infra/ansible/files/deploy_nas_ed25519", "infra/ansible/files/deploy_nas_ed25519"),
    (
        "cd infra/ansible && uv run ansible-vault view --vault-password-file scripts/vault-pass.sh files/zaccess_ca.key.vault",
        "ansible-vault view",
    ),
    ("ansible-vault decrypt --output - files/deploy_zaccess_ed25519", "ansible-vault decrypt"),
    ("sops -d infra/ansible/vault-password.sops.yaml", "sops -d"),
    ("sops --decrypt --extract '[\"vault_password\"]' infra/ansible/vault-password.sops.yaml", "sops --decrypt"),
    ("git show HEAD:infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("git -C /repo show develop:infra/ansible/files/deploy_zaccess_ed25519", "infra/ansible/files/deploy_zaccess_ed25519"),
]

ADMITTED = [
    # commit without the flag; the flag as message text, in a heredoc, in a comment, after --
    "git commit -m msg",
    "git commit -am msg",
    "git commit --amend -m msg",
    "git commit -a -q -m msg",
    'git commit -m "docs: never --no-verify"',
    'git commit -m "chore: drop the -n door"',
    "git commit -m 'refuse -n and --no-verify'",
    f'git commit -m "{HEREDOC_MESSAGE}"',
    "git commit -F .tmp/msg.txt",
    "git commit -m -n",  # the message is `-n`
    "git commit -am -n",
    "git commit --message -n",
    "git commit -m msg -- -n",
    "git commit -m msg # not --no-verify",
    'git commit -m "a#b"',
    "git commit -m $'it\\'s -n'",  # the flag inside an ANSI-C quoted value
    "git commit -m $'plain' -m more",
    "git commit -m $'a\\tb\\x21'",
    "(echo hi)# git commit -n",
    "echo $(date)#c; git status",
    "echo >(true)#c; git status",
    'echo "<(git commit -n)"',
    "echo GIT_CONFIG_KEY_0=core.hooksPath",
    "git commit -uno -m msg",  # -u<mode>: `no` is the mode, not a bundle carrying n
    "git commit --no-status -m msg",
    "git commit -m msg && git push",
    'git commit -m "a && git commit -n"',
    "git commit -m 'see `git commit -n`'",
    'git commit -m "see \\`git commit -n\\`"',  # an escaped backtick is text
    "cat <<'EOF'\n$(git commit -n)\nEOF",  # a quoted delimiter expands nothing
    'echo "$(git rev-parse HEAD)"',
    # -n and --no-verify where they mean something else, and outside git
    "git merge -n feature",
    "git rebase -n main",
    "git am -3 patch.mbox",
    "git log --oneline -n 5",
    "git grep -n -- no-verify",
    "git push --no-verify",
    "sed -n 1,5p file",
    "ls -n",
    "grep -rn -- --no-verify docs/",
    'echo "git commit -n"',
    "cat <<'EOF' > notes.txt\ngit commit --no-verify\nEOF",
    "uv run pytest tests/test_bash_guard.py -k no_verify",
    # core.hooksPath read or unset, and other keys set
    "git config --get core.hooksPath",
    "git config core.hooksPath",
    "git config --unset core.hooksPath",
    "git config --unset-all core.hooksPath",
    "git config --get-all core.hooksPath",
    "git config --local --get core.hooksPath",
    "git config get core.hooksPath",
    "git config unset core.hooksPath",
    "git config --list",
    "git config user.name x",
    "git config --local user.email x@example.invalid",
    "git -c color.ui=never log -1",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=t git commit -m msg",
    # an assignment-shaped word where git never sees it: a search, a note, a bare assignment
    "grep -rn 'GIT_CONFIG_KEY_0=core.hooksPath' docs/",
    "rg -n 'GIT_CONFIG_PARAMETERS=.*core.hooksPath' .",
    "echo \"GIT_CONFIG_PARAMETERS='core.hooksPath=/dev/null' is the env door\" >> notes.md",
    "GIT_CONFIG_KEY_0=core.hooksPath; git commit -m msg",
    "git -C /repo status",
    "git status",
    "which git",
    "git --version",
    # a cap that only looks, a cap that opens a file rather than a pipe, a cap that caps nothing
    "git log --oneline | head -20",
    "cat f | head -3 | cut -d, -f1",
    "git log | head -5 | grep fix",
    "git log | head -5 | grep -C 3 fix",  # -C is context, not --count
    "tail -f logs/engine.log",
    "tail -20 infra/runbooks/gate.md",
    "head -1 .python-version",
    "head -c 20 /dev/urandom | base64",
    "head -50 data/catalog.jsonl | wc -l",  # the cap opens the file it counts: a bounded read, not a stream unseen
    '[ "$(head -1 VERSION)" = 3.14 ]',
    # an emptiness test over a capped substitution: `$( .. )` strips the trailing newlines, so `head -1` of a
    # non-empty stream is non-empty and capped and uncapped give the same verdict
    '[ "$(git status --porcelain | head -1)" = "" ]',
    "[[ -n $(git ls-files | head -1) ]]",
    '[ -n "`ls | head -1`" ]',
    'if [ -z "$(git diff --name-only | head -1)" ]; then echo clean; fi',
    "git log --oneline | tail -n +2 | wc -l",
    "ls | tail +2 | wc -l",
    # the count without a cap, the count before one, the two in separate commands
    "git log --oneline | wc -l",
    "grep -c NEEDLE file",
    "git log | wc -l | head -1",
    "git ls-files | wc -l; head -3 README.md",
    "git log --oneline | head -5 && git status",
    '[ -n "$(git rev-parse HEAD)" ]',
    "sed -n 1,5p file | wc -l",  # another truncation, outside the arm
    "git log --oneline | head -5 | uniq -c",  # `counting` is closed over wc and the greps: another -c is not one
    # the shape as text: a message, an echo, a quoted heredoc body, a pytest selector
    'git commit -m "head -5 | wc -l is the defect"',
    'echo "git log | head -5 | wc -l"',
    "cat <<'EOF'\nls | head -2 | wc -l\nEOF",
    'uv run pytest tests/test_bash_guard.py -k "head or tail"',  # the ids are the commands, so this is the selector
    # a vaulted file counted, hashed, listed or logged; its public half, its neighbours, its path as text
    "grep -c ANSIBLE_VAULT infra/ansible/files/deploy_zaccess_ed25519",
    "grep -c '^\\$ANSIBLE_VAULT' infra/ansible/group_vars/all/vault.yml",
    "sha256sum infra/ansible/files/deploy_zaccess_ed25519",
    "wc -c infra/ansible/group_vars/all/vault.yml",
    "stat infra/ansible/vault-password.sops.yaml",
    "ls -la infra/ansible/files/",
    "git log --oneline -- infra/ansible/group_vars/all/vault.yml",
    "cat infra/ansible/files/deploy_zaccess_ed25519.pub",
    "cat infra/ansible/files/*.pub",
    "git show HEAD:infra/ansible/files/deploy_zaccess_ed25519.pub",
    "head -3 infra/ansible/files/README.md",
    "cat infra/ansible/.sops.yaml",
    "head -5 .github/workflows/*.yml",
    "echo infra/ansible/group_vars/all/vault.yml",
    "grep -rn 'cat infra/ansible/group_vars/all/vault.yml' docs/",
    "python3 -c \"print(open('README.md').read())\"",
    # the vault's own consumers: its password script, the playbook, a value read into a variable, a write to one
    "cat infra/ansible/scripts/vault-pass.sh",
    "bash -n infra/ansible/scripts/vault-pass.sh",
    "cd infra/ansible && uv run ansible-playbook --vault-password-file scripts/vault-pass.sh site.yml --list-tags",
    "infra/ansible/scripts/converge.sh --limit zcrypto-red --tags capture",
    'TOKEN="$(uv run python -c \'from grafana_auth import vault_var; print(vault_var("grafana_sa_token"))\')"',
    "uv run ansible-vault encrypt_string --stdin-name x",
    "cp /tmp/new_key infra/ansible/files/deploy_zaccess_ed25519",
    "sed -i 's/old_name:/new_name:/' infra/ansible/group_vars/all/vault.yml",
]

# (command, the stage the message must name) -- refused from a dispatched agent in its own worktree
AGENT_WRITES = [
    ("git push", "git push"),
    ("git push -u origin claude/refine-round-17", "git push -u origin claude/refine-round-17"),
    ("git push --no-verify", "git push --no-verify"),
    (f"git -C {WORKTREE} push origin HEAD", f"git -C {WORKTREE} push origin HEAD"),
    ("git status && git push", "git push"),
    ("git add f; git commit -m x; git push", "git push"),
    ("git log -1 | git push", "git push"),
    ("x=$(git push)", "'x=$' git push"),  # the walk reads the assignment's words as one stage, as it does for `git commit -n`
    ("echo `git push`", "git push"),
    ("timeout 60 git push origin x", "timeout 60 git push origin x"),
    ("/usr/bin/git push", "/usr/bin/git push"),
    ("gh pr create --base develop --title x --body y", "gh pr create --base develop --title x --body y"),
    ("gh pr ready 624", "gh pr ready 624"),
    ("gh pr merge 624 --merge", "gh pr merge 624 --merge"),
    ("gh pr edit 624 --body-file b.md", "gh pr edit 624 --body-file b.md"),
    ("gh pr close 624", "gh pr close 624"),
    ("gh pr comment 624 --body x", "gh pr comment 624 --body x"),
    ("gh pr review 624 --approve", "gh pr review 624 --approve"),
    ("gh pr -R zhaow-de/zcrypto-kraken merge 624", "gh pr -R zhaow-de/zcrypto-kraken merge 624"),
    ("gh api -X POST repos/o/r/issues/1/comments -f body=x", "gh api -X POST repos/o/r/issues/1/comments -f body=x"),
    ("gh api repos/o/r/pulls/624/merge -X PUT", "gh api repos/o/r/pulls/624/merge -X PUT"),
    ("gh api --method PATCH repos/o/r/pulls/624", "gh api --method PATCH repos/o/r/pulls/624"),
    ("gh api --method=DELETE repos/o/r/git/refs/heads/x", "gh api --method=DELETE repos/o/r/git/refs/heads/x"),
    ("gh api -XPOST repos/o/r/pulls", "gh api -XPOST repos/o/r/pulls"),
    ("gh api -X post repos/o/r/pulls", "gh api -X post repos/o/r/pulls"),
    ("gh cache delete --all", "gh cache delete --all"),
    ("cd /tmp && timeout 30 gh pr create --fill", "timeout 30 gh pr create --fill"),
]

# (command, the payload's cwd, the stage the message must name) -- refused from a dispatched agent
AGENT_IN_MAIN = [
    ("git commit -m x", MAIN, "git commit -m x"),
    ("git add cli/x.py", MAIN, "git add cli/x.py"),
    ("git checkout develop", MAIN, "git checkout develop"),
    ("git switch -c y", MAIN, "git switch -c y"),
    ("git reset --hard origin/develop", MAIN, "git reset --hard origin/develop"),
    ("git stash", MAIN, "git stash"),
    ("git stash pop", MAIN, "git stash pop"),
    ("git rebase develop", MAIN, "git rebase develop"),
    ("git merge --ff-only origin/develop", MAIN, "git merge --ff-only origin/develop"),
    ("git cherry-pick abc1234", MAIN, "git cherry-pick abc1234"),
    ("git branch -d x", MAIN, "git branch -d x"),
    ("git branch -D x", MAIN, "git branch -D x"),
    ("git branch --delete x", MAIN, "git branch --delete x"),
    ("git branch -rd origin/x", MAIN, "git branch -rd origin/x"),
    ("git worktree remove .claude/worktrees/agent-x", MAIN, "git worktree remove .claude/worktrees/agent-x"),
    ("git add x.py", f"{MAIN}/cli", "git add x.py"),  # below the main checkout
    ("git commit -m x", f"{MAIN}/.claude/worktrees", "git commit -m x"),  # the directory holding the worktrees
    (f"git -C {MAIN} commit -m x", WORKTREE, f"git -C {MAIN} commit -m x"),
    (f"cd {MAIN} && git commit -m x", WORKTREE, "git commit -m x"),
    ("git -C ../../.. add f", WORKTREE, "git -C ../../.. add f"),
    ("cd ../../.. && git stash", WORKTREE, "git stash"),
    (f"git -C {MAIN} checkout develop", "/tmp", f"git -C {MAIN} checkout develop"),
    (f"git -C {WORKTREE} -C ../../.. commit -m x", "/tmp", f"git -C {WORKTREE} -C ../../.. commit -m x"),
    (f"cd {WORKTREE} && cd {MAIN} && git reset --hard", MAIN, "git reset --hard"),
    (f"cd {WORKTREE}/../../.. && git add f", "/tmp", "git add f"),
    (f"pushd {MAIN} && git commit -m x", WORKTREE, "git commit -m x"),
    (f'cd "$WT" && git -C {MAIN} commit -m x', WORKTREE, f"git -C {MAIN} commit -m x"),  # an absolute -C past an unknown cd
]

# (command, the payload's cwd) -- admitted silently from a dispatched agent
AGENT_ADMITTED = [
    ("git status", WORKTREE),
    ("git log --oneline develop..HEAD", WORKTREE),
    ("git fetch origin develop", WORKTREE),
    ('git commit -m "then git push"', WORKTREE),
    ('echo "git push"', WORKTREE),
    ("gh pr view 624 --json body", WORKTREE),
    ("gh pr list --state merged", WORKTREE),
    ("gh pr diff 624", WORKTREE),
    ("gh pr checks 624", WORKTREE),
    ("gh api repos/o/r/pulls/624", WORKTREE),
    ("gh api -X GET repos/o/r/pulls/624/files --paginate", WORKTREE),
    ("gh cache list", WORKTREE),
    ("gh run view 1 --log", WORKTREE),
    ("git commit -m x", WORKTREE),
    ("git add -A", WORKTREE),
    ("git reset --soft HEAD~1", WORKTREE),
    ("git checkout -b y", WORKTREE),
    ("git branch -D x", WORKTREE),
    ("git stash", WORKTREE),
    ("git rebase develop", WORKTREE),
    (f"cd {WORKTREE} && git commit -m x", MAIN),
    (f"git -C {WORKTREE} commit -m x", MAIN),
    ("git -C .claude/worktrees/agent-x add f", MAIN),
    ("cd .claude/worktrees/agent-x && git commit -m x", MAIN),
    (f"git -C {SCRATCH} commit -m x", MAIN),
    ("cd .tmp/scratch && git init -q && git add . && git commit -m x", MAIN),
    (f"git -C {WORKTREE} worktree remove --force {WORKTREE}", MAIN),
    ("git status", MAIN),
    ("git log --oneline -3", MAIN),
    ("git diff develop...HEAD", MAIN),
    ("git worktree list", MAIN),
    ("git worktree add .claude/worktrees/y -b y develop", MAIN),
    ("git branch --list", MAIN),
    ("git branch -a", MAIN),
    ("git branch -u origin/develop", MAIN),
    ("git stash list", MAIN),
    ("git stash show -p", MAIN),
    ("git merge-base develop HEAD", MAIN),
    ("git cherry develop", MAIN),
    ('cd "$WT" && git commit -m x', MAIN),  # a directory through a variable is judged as nothing
    ("cd - && git commit -m x", MAIN),
    ("popd && git commit -m x", MAIN),
    (f"pushd {WORKTREE} && git commit -m x", MAIN),
    ("git commit -m x", "/tmp/elsewhere"),
    ("git commit -m x", f"{MAIN}-other"),  # a sibling sharing the main checkout's path as a prefix
]


def run_hook(payload: dict | str, cwd: Path) -> subprocess.CompletedProcess:
    """Dicts are JSON-encoded; strings pass through verbatim so the malformed-input cases can hand the hook
    something that is not JSON."""
    return subprocess.run(
        ["bash", str(HOOK)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def call(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


@pytest.mark.parametrize(("command", "spelling"), REFUSED, ids=[c for c, _ in REFUSED])
def test_a_refused_shape_is_blocked_and_the_message_names_it(tmp_path: Path, command: str, spelling: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 2, r.stderr
    assert "BLOCKED" in r.stderr
    # Where the message names the spelling: a flag as a word of the first backtick pair (`git <sub> <tok>`), never the
    # later echo of the whole command; a capping stage as that pair entire; a key or a variable before " sets ".
    named = r.stderr.partition("`")[2].partition("`")[0]
    capping = spelling.split()[0] in ("head", "tail")
    if capping:
        assert named == spelling, r.stderr
    elif spelling.startswith("-"):
        assert spelling in named.split(), r.stderr
    else:
        assert spelling in r.stderr.partition(" sets ")[0], r.stderr
    assert ("cap" if capping else "hooks") in r.stderr  # what the shape costs
    assert r.stdout == ""


@pytest.mark.parametrize(("command", "spelling"), VAULTED, ids=[c for c, _ in VAULTED])
def test_a_command_that_prints_a_vaulted_file_is_blocked_with_the_remedy(tmp_path: Path, command: str, spelling: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 2, r.stderr
    claim = r.stderr.partition("; in `")[0]  # the message's own words, before its echo of the command
    named = claim.partition("`")[2].partition("`")[0]
    if spelling.startswith(("ansible-vault", "sops")):
        assert spelling in named and "decrypts" in claim, r.stderr
    else:
        assert f"`{spelling}`" in claim and named != spelling, r.stderr  # the file in a span of its own, past the stage
    assert "BLOCKED" in claim
    assert "`vault_var` through command substitution" in r.stderr and "`grep -c`" in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize("command", ADMITTED)
def test_an_ordinary_command_is_admitted_silently(tmp_path: Path, command: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == ""
    assert r.stderr == ""


@pytest.mark.parametrize("payload", ["", "not json at all", "{", "[]", '{"tool_input": "x"}'])
def test_stdin_that_is_not_the_call_admits_with_a_note(tmp_path: Path, payload: str):
    r = run_hook(payload, cwd=tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""
    assert "bash-guard: NOTE" in r.stderr
    assert "unjudged" in r.stderr


def test_a_call_with_no_command_is_admitted_silently(tmp_path: Path):
    r = run_hook({"tool_name": "Bash", "tool_input": {}}, cwd=tmp_path)
    assert r.returncode == 0
    assert r.stdout == "" and r.stderr == ""


def test_a_command_that_does_not_tokenise_admits_with_a_note(tmp_path: Path):
    # The hook's own parse failure is never a block. Bash refuses this spelling too; the class is wider than that,
    # and the header says how.
    r = run_hook(call('git commit -n -m "unterminated'), cwd=tmp_path)
    assert r.returncode == 0
    assert "bash-guard: NOTE" in r.stderr


def test_hook_is_executable():
    assert HOOK.stat().st_mode & 0o111, "the hook must be executable -- settings.json invokes it directly"


def test_hook_is_wired_as_a_pretooluse_bash_hook():
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    commands = [
        hook["command"] for entry in settings["hooks"]["PreToolUse"] if entry["matcher"] == "Bash" for hook in entry["hooks"]
    ]
    assert any("bash-guard.sh" in c for c in commands), "the hook is inert unless settings.json wires it"


def agent_call(command: str, cwd: str, **extra: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd, **extra}


def _named(stderr: str) -> str:
    return stderr.partition("; in `")[0].partition("`")[2].partition("`")[0]


@pytest.mark.parametrize(("command", "spelling"), AGENT_WRITES, ids=[c for c, _ in AGENT_WRITES])
def test_a_dispatched_agents_push_or_github_write_is_blocked_with_the_remedy(tmp_path: Path, command: str, spelling: str):
    r = run_hook(agent_call(command, WORKTREE, agent_id="a1", agent_type="general-purpose"), cwd=tmp_path)
    assert r.returncode == 2, r.stderr
    assert "BLOCKED" in r.stderr and _named(r.stderr) == spelling, r.stderr
    assert "a dispatched agent reports and stops" in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize(("command", "where", "spelling"), AGENT_IN_MAIN, ids=[f"{c} @ {w}" for c, w, _ in AGENT_IN_MAIN])
def test_a_dispatched_agents_git_that_moves_the_main_checkout_is_blocked_with_the_remedy(
    tmp_path: Path, command: str, where: str, spelling: str
):
    r = run_hook(agent_call(command, where, agent_id="a1"), cwd=tmp_path)
    assert r.returncode == 2, r.stderr
    assert "BLOCKED" in r.stderr and _named(r.stderr) == spelling and "in the main checkout" in r.stderr, r.stderr
    assert "the main checkout is the coordinator's" in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize(("command", "where"), AGENT_ADMITTED, ids=[f"{c} @ {w}" for c, w in AGENT_ADMITTED])
def test_a_dispatched_agents_read_and_worktree_git_are_admitted_silently(tmp_path: Path, command: str, where: str):
    r = run_hook(agent_call(command, where, agent_id="a1"), cwd=tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


MAIN_LOOP = [(c, WORKTREE) for c, _ in AGENT_WRITES] + [(c, w) for c, w, _ in AGENT_IN_MAIN]


@pytest.mark.parametrize(("command", "where"), MAIN_LOOP, ids=[f"{c} @ {w}" for c, w in MAIN_LOOP])
@pytest.mark.parametrize("extra", [{}, {"agent_type": "reviewer"}], ids=["bare", "agent_type alone"])
def test_the_main_loop_runs_what_a_dispatched_agent_may_not(tmp_path: Path, command: str, where: str, extra: dict):
    r = run_hook(agent_call(command, where, **extra), cwd=tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
