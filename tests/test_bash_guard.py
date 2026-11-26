"""The PreToolUse[Bash] guard's families, driven with synthetic stdin JSON.

Every family is driven in both directions: the spelling an arm refuses (exit 2, `BLOCKED` and the spelling on stderr)
beside the ordinary shape nearest to it that it must admit (exit 0, silent).
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

from tests.test_consumers_sh import VAULT_SPECIMENS, vault_excludes

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "bash-guard.sh"
# Judged as text but for a worktree remove's operand, whose ancestors the hook reads for a worktree of this
# repository: agent-x is none.
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
SESSION, OTHER_SESSION = "0a1b2c3d-0000-4000-8000-000000000001", "0a1b2c3d-0000-4000-8000-000000000002"
TMP_ROOT = "/home/u/.cache/claude-tmp"
PROJECT = f"claude-{os.getuid()}/-home-u-Projects-zcrypto-kraken"
SCRATCHPAD = f"{TMP_ROOT}/{PROJECT}/{SESSION}/scratchpad"
AGENT_ENV = {**os.environ, "CLAUDE_CODE_TMPDIR": TMP_ROOT}

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
    ("git 2>/dev/null commit -n", "-n"),
    ("git commit -m 2 > /dev/null -n", "-n"),  # a number apart from its redirection is a word: here -m's value
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
    ("git commit -n -m $'\\uD800'", "-n"),
    ("git commit -m x $'--no-verify\\0'", "--no-verify"),
    ("git commit -m x $'--no-verify\\c`'", "--no-verify"),
    # a command substitution: $( .. ) and backticks, bare, assigned, double-quoted, inside a heredoc bash expands
    ("x=$(git commit -n)", "-n"),
    ('echo "$(git commit -n)"', "-n"),
    ("x=`git commit -n`", "-n"),
    ("`git commit --no-verify`", "--no-verify"),
    ('echo "`git commit -n`"', "-n"),
    ("cat <<EOF\n$(git commit -n)\nEOF", "-n"),
    ("cat <<EOF\n`git commit --no-verify`\nEOF", "--no-verify"),
    # a here-string's word is a word, no heredoc's delimiter: its substitution runs, and the next line is a command
    ('cat <<< "$(git commit -n -m x)"', "-n"),
    ("cat <<<`git commit --no-verify`", "--no-verify"),
    ("read -r x <<< y\ngit commit -n -m x", "-n"),
    # a `<<` quoted inside a backtick opens no heredoc: the next line, and the backtick's own next line, are judged
    ('echo `echo "<<EOF"`\ngit commit --no-verify -m x', "--no-verify"),
    ('echo `echo "<<EOF"\necho y` ; git commit --no-verify -m x', "--no-verify"),
    # a command after a heredoc's delimiter word, which a metacharacter ends and quoted pieces build
    ("cat <<EOF;git commit -n\nx\nEOF", "-n"),
    ("cat <<EOF&&git commit --no-verify\nx\nEOF", "--no-verify"),
    ("cat > .tmp/x <<E\\OF\nx\nEOF\ngit commit -n", "-n"),
    ("cat > .tmp/x <<E'OF'\nx\nEOF\ngit commit -n", "-n"),
    ("cat > .tmp/x <<$'EOF'\nx\nEOF\ngit commit --no-verify", "--no-verify"),
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
    ("git grep -n TODO -- cli ':!*vault*' ':!*.sops.*' ':!infra/ansible/files/*_ed25519' | head -10 | grep -c cli/", "head -10"),
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
    ("nl -ba infra/ansible/files/deploy_zaccess_ed25519", "infra/ansible/files/deploy_zaccess_ed25519"),
    ("hd infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("cat infra/ansible/.sops.yaml", "infra/ansible/.sops.yaml"),
    ("cd infra/ansible && cat files/deploy_zcrypto_ed25519", "files/deploy_zcrypto_ed25519"),
    ("cd infra/ansible/files && cat deploy_zcrypto_ed25519", "deploy_zcrypto_ed25519"),
    ("cd infra/ansible && cat group_vars/all/vault.yml", "group_vars/all/vault.yml"),
    ("cat infra/ansible/files/deploy_{nas,zaccess}_ed25519", "infra/ansible/files/deploy_nas_ed25519"),
    ("cat infra/ansible/files/deploy_zcrypto-valkey{3..1}_ed25519", "infra/ansible/files/deploy_zcrypto-valkey3_ed25519"),
    ("cat infra/ansible/group_vars/all/vault.yml $'\\uD800'", "infra/ansible/group_vars/all/vault.yml"),
    ("cat infra/ansible/group_vars/all/vault$'\\0x'.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("cat infra/ansible/group_vars/all/vault.yml$'\\c@'", "infra/ansible/group_vars/all/vault.yml"),
    ("cat infra/ansible/group_vars/all/vault.yml$'\\c\u0801'", "infra/ansible/group_vars/all/vault.yml"),
    ("cat infra/ansible/group_vars/all/vault.ym\x00l", "infra/ansible/group_vars/all/vault.yml"),
    (
        "awk --file=infra/ansible/files/deploy_{nas,zaccess}_ed25519 docs/reference/fleet.md",
        "infra/ansible/files/deploy_nas_ed25519",
    ),
    ("cd infra/ansible/files && head -3 deploy_*", "deploy_*"),
    ("{fd}>/dev/null cat infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("coproc cat infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("flock /tmp/l cat infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("echo cat infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("cat infra/ansible/files/deploy_*", "infra/ansible/files/deploy_*"),
    ("head -2 infra/ansible/group_vars/*/vault.yml", "infra/ansible/group_vars/*/vault.yml"),
    ("cat infra/ansible/group_vars/all/*", "infra/ansible/group_vars/all/*"),
    ("head -1 < infra/ansible/files/deploy_zaccess_ed25519", "infra/ansible/files/deploy_zaccess_ed25519"),
    ("sudo cat infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("timeout 5 head -1 infra/ansible/files/deploy_zaccess_ed25519", "infra/ansible/files/deploy_zaccess_ed25519"),
    ("x=$(cat infra/ansible/files/deploy_zaccess_ed25519)", "infra/ansible/files/deploy_zaccess_ed25519"),
    (
        "python3 -c \"print(open('infra/ansible/files/deploy_zaccess_ed25519').read())\"",
        "infra/ansible/files/deploy_zaccess_ed25519",
    ),
    (
        "uv run python -c \"import pathlib; print(pathlib.Path('infra/ansible/group_vars/all/vault.yml').read_text())\"",
        "infra/ansible/group_vars/all/vault.yml",
    ),
    (
        "python3 -c \"import pathlib; print(pathlib.Path('infra/ansible/files/zaccess_ca.key.vault').read_bytes())\"",
        "infra/ansible/files/zaccess_ca.key.vault",
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
    ("sops decrypt infra/ansible/vault-password.sops.yaml", "sops decrypt"),
    ("sops exec-env infra/ansible/vault-password.sops.yaml env", "sops exec-env"),
    ("sops exec-file infra/ansible/vault-password.sops.yaml 'cat {}'", "sops exec-file"),
    ("git show HEAD:infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("git -C infra show HEAD:infra/ansible/files/deploy_zaccess_ed25519", "infra/ansible/files/deploy_zaccess_ed25519"),
    ("git -C infra/ansible show HEAD:./files/deploy_zaccess_ed25519", "./files/deploy_zaccess_ed25519"),
    ("git show :infra/ansible/vault-password.sops.yaml", "infra/ansible/vault-password.sops.yaml"),
    ("git cat-file -p HEAD:infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("2>/dev/null git show HEAD:infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("flock /tmp/l git show HEAD:infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("awk -f prog.awk infra/ansible/files/deploy_zaccess_ed25519", "infra/ansible/files/deploy_zaccess_ed25519"),
    ("awk -f infra/ansible/files/deploy_zaccess_ed25519 docs/reference/fleet.md", "infra/ansible/files/deploy_zaccess_ed25519"),
    ("awk --file=infra/ansible/files/deploy_nas_ed25519 docs/reference/fleet.md", "infra/ansible/files/deploy_nas_ed25519"),
    ("sed -e p infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("sed -n 's/x/vault.yml/p' infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
    ("sed -f infra/ansible/files/deploy_zaccess_ed25519 docs/reference/fleet.md", "infra/ansible/files/deploy_zaccess_ed25519"),
    (
        "awk -W exec infra/ansible/files/deploy_zaccess_ed25519 docs/reference/fleet.md",
        "infra/ansible/files/deploy_zaccess_ed25519",
    ),
    ("awk -We infra/ansible/files/deploy_nas_ed25519 docs/reference/fleet.md", "infra/ansible/files/deploy_nas_ed25519"),
    ("awk -Wexec=infra/ansible/files/sync_ed25519 docs/reference/fleet.md", "infra/ansible/files/sync_ed25519"),
    ("awk -W EXEC infra/ansible/files/deploy_nas_ed25519 docs/reference/fleet.md", "infra/ansible/files/deploy_nas_ed25519"),
    (
        "awk -W interactive,exec infra/ansible/files/deploy_nas_ed25519 docs/reference/fleet.md",
        "infra/ansible/files/deploy_nas_ed25519",
    ),
    ("awk -Wi,e infra/ansible/files/deploy_nas_ed25519 docs/reference/fleet.md", "infra/ansible/files/deploy_nas_ed25519"),
    ("sed -nf infra/ansible/files/deploy_nas_ed25519 docs/reference/fleet.md", "infra/ansible/files/deploy_nas_ed25519"),
    ("awk -v x=infra/ansible/files/deploy_nas_ed25519 1 docs/reference/fleet.md", "infra/ansible/files/deploy_nas_ed25519"),
    (
        "python3 -c \"p='infra/ansible/group_vars/all/vault.yml'; print(open(p.strip()).read())\"",
        "infra/ansible/group_vars/all/vault.yml",
    ),
    (
        "python3 -c \"import os; print(open(os.path.join('infra/ansible/group_vars/all', 'vault.yml')).read())\"",
        "infra/ansible/group_vars/all/vault.yml",
    ),
    (
        "python3 -c \"import os; print(open(os.path.join('infra', 'ansible', 'group_vars', 'all', 'vault.yml')).read())\"",
        "infra/ansible/group_vars/all/vault.yml",
    ),
    (
        "python3 -c \"import pathlib; print((pathlib.Path('infra/ansible/files') / 'sync_ed25519').read_text())\"",
        "infra/ansible/files/sync_ed25519",
    ),
    (
        "python3 -c \"f=lambda: 'infra/ansible/group_vars/all/vault.yml'; print(open(f()).read())\"",
        "infra/ansible/group_vars/all/vault.yml",
    ),
    (
        'python3 -c "exec(\\"print(open(\'infra/ansible/group_vars/all/vault.yml\').read())\\")"',
        "infra/ansible/group_vars/all/vault.yml",
    ),
    (
        "python3 -c \"p = 'infra/ansible/files/deploy_zaccess_ed25519'; print(open(p).read())\"",
        "infra/ansible/files/deploy_zaccess_ed25519",
    ),
]

# (a reader's program or option value naming vault.yml over an ordinary file, the same reader over a vaulted one)
READER_PROGRAMS = [
    ("awk '/vault.yml/' docs/reference/fleet.md", "awk '/vault.yml/' infra/ansible/group_vars/all/vault.yml"),
    ("awk '$0 ~ /vault.yml/' infra/runbooks/fleet.md", "awk '$0 ~ /vault.yml/' infra/ansible/host_vars/zcrypto-ops/vault.yml"),
    ("awk -v f=vault.yml '$2 == f' docs/reference/fleet.md", "awk -v f=vault.yml '$2 == f' infra/ansible/group_vars/all/vault.yml"),
    ("less -p vault.yml docs/reference/fleet.md", "less -p vault.yml infra/ansible/group_vars/all/vault.yml"),
    ("less +/vault.yml docs/reference/fleet.md", "less +/vault.yml infra/ansible/group_vars/observed/vault.yml"),
    ("more +/vault.yml docs/reference/fleet.md", "more +/vault.yml infra/ansible/group_vars/all/vault.yml"),
]

# (a word past the brace cap, the glob or file the message must name)
PAST_THE_BRACE_CAP = [
    (
        "awk --file=infra/ansible/files/deploy_zcrypto-valkey{1..257}_ed25519 docs/reference/fleet.md",
        "infra/ansible/files/deploy_zcrypto-valkey*_ed25519",
    ),
    (
        "awk --file=infra/ansible/files/deploy_{zcrypto-valkey{1..300},nas}_ed25519 docs/reference/fleet.md",
        "infra/ansible/files/deploy_zcrypto-valkey*_ed25519",
    ),
    (
        "awk --file=infra/ansible/files/deploy_nas_ed25519{,}{,}{,}{,}{,}{,}{,}{,}{,} docs/reference/fleet.md",
        "infra/ansible/files/deploy_nas_ed25519*********",
    ),
    ("cat infra/ansible/files/{deploy_nas,{x,y}}_ed25519{,}{,}{,}{,}{,}{,}{,}{,}", "infra/ansible/files/*_ed25519********"),
    ("cat {infra/ansible/files/deploy_nas_ed25519,{1..300}}", "infra/ansible/files/deploy_nas_ed25519"),
    ("cat {1..99999999999999999999} infra/ansible/group_vars/all/vault.yml", "infra/ansible/group_vars/all/vault.yml"),
]

PAST_THE_BRACE_CAP_ADMITTED = {
    "a thousand groups": "cat " + "{a,b}" * 1000,
    "a sequence end of 5000 digits": "cat {1.." + "9" * 5000 + "}",
}

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
    "cat <<E'OF'\n$(git commit -n)\nEOF",  # nor does one quoted in part
    "cat <<$'EOF'\n$(git commit -n)\nEOF",
    'echo "$(git rev-parse HEAD)"',
    # -n and --no-verify where they mean something else, and outside git
    "git merge -n feature",
    "git rebase -n main",
    "git am -3 patch.mbox",
    "git log --oneline -n 5",
    "git grep -n no-verify -- tests ':!*vault*' ':!*.sops.*' ':!infra/ansible/files/*_ed25519'",
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
    "grep -c ANSIBLE_VAULT infra/ansible/files/deploy_zaccess_ed25519",
    "grep -c '^\\$ANSIBLE_VAULT' infra/ansible/group_vars/all/vault.yml",
    "sha256sum infra/ansible/files/deploy_zaccess_ed25519",
    "wc -c infra/ansible/group_vars/all/vault.yml",
    "stat infra/ansible/vault-password.sops.yaml",
    "ls -la infra/ansible/files/",
    "git log --oneline -- infra/ansible/group_vars/all/vault.yml",
    "cat infra/ansible/files/deploy_zaccess_ed25519.pub",
    "cat infra/ansible/files/*.pub",
    "nl -ba infra/ansible/files/deploy_zaccess_ed25519.pub",
    "hd infra/ansible/files/deploy_zaccess_ed25519.pub",
    "git show HEAD:infra/ansible/files/deploy_zaccess_ed25519.pub",
    "git cat-file -p HEAD:infra/ansible/files/deploy_zaccess_ed25519.pub",
    "head -3 infra/ansible/files/README.md",
    "head -5 .github/workflows/*.yml",
    "echo infra/ansible/group_vars/all/vault.yml",
    "grep -rn 'cat infra/ansible/group_vars/all/vault.yml' docs/",
    "python3 -c \"print(open('README.md').read())\"",
    "python3 -c \"import pathlib; print(len(pathlib.Path('infra/ansible/files/deploy_zaccess_ed25519.pub').read_bytes()))\"",
    "cat infra/ansible/scripts/vault-pass.sh",
    "bash -n infra/ansible/scripts/vault-pass.sh",
    "cd infra/ansible && uv run ansible-playbook --vault-password-file scripts/vault-pass.sh site.yml --list-tags",
    "infra/ansible/scripts/converge.sh --limit zcrypto-red --tags capture",
    'TOKEN="$(uv run python -c \'from grafana_auth import vault_var; print(vault_var("grafana_sa_token"))\')"',
    "uv run ansible-vault encrypt_string --stdin-name x",
    "cd infra/ansible && uv run ansible-vault encrypt files/deploy_zcrypto_ed25519",
    "ansible-vault encrypt --output infra/ansible/files/zaccess_ca.key.vault -",
    "ansible-vault rekey infra/ansible/group_vars/all/vault.yml",
    "ansible-vault edit infra/ansible/group_vars/all/vault.yml",
    "sops filestatus infra/ansible/vault-password.sops.yaml",
    "sops -e -i infra/ansible/vault-password.sops.yaml",
    "sops --encrypt --in-place infra/ansible/vault-password.sops.yaml",
    "sops updatekeys infra/ansible/vault-password.sops.yaml",
    "sops rotate -i infra/ansible/vault-password.sops.yaml",
    "sops edit infra/ansible/vault-password.sops.yaml",
    "cp /tmp/new_key infra/ansible/files/deploy_zaccess_ed25519",
    "sed -i 's/old_name:/new_name:/' infra/ansible/group_vars/all/vault.yml",
    "awk -v n=1 '/vault.yml/' docs/reference/fleet.md",
    "awk -F , '/vault.yml/' docs/reference/fleet.md",
    "awk '{print v}' v=vault.yml docs/reference/fleet.md",
    "sed 's/secrets.yml/vault.yml/' docs/reference/fleet.md",
    "sed -n -e 's/a/vault.yml/' docs/reference/fleet.md",
    "sed --expression='s/a/vault.yml/' docs/reference/fleet.md",
    "python3 -c \"print('vault.yml' in open('docs/reference/fleet.md').read())\"",
    "python3 -c \"import pathlib; print('vault.yml' in pathlib.Path('docs/reference/fleet.md').read_text())\"",
    "awk -W interactive '/vault.yml/' docs/reference/fleet.md",
    "awk -W EXEC infra/ansible/files/no_such_ed25519 docs/reference/fleet.md",
    "awk -W interactive,exec infra/ansible/files/no_such_ed25519 docs/reference/fleet.md",
    "awk -Wi,e infra/ansible/files/no_such_ed25519 docs/reference/fleet.md",
    "python3 -c \"f=lambda: 'infra/ansible/group_vars/no_such/vault.yml'; print(open(f()).read())\"",
    'python3 -c "exec(\\"print(open(\'infra/ansible/group_vars/no_such/vault.yml\').read())\\")"',
    "cat deploy_zcrypto_ed25519",  # a key's name where no such file is
    "git show HEAD:infra/ansible/files/no_such_ed25519",
    "cd infra/ansible/files && head -3 README*",
    "cat infra/ansible/files/{README.md,rrsync-shell}",
    "awk --file=infra/ansible/files/deploy_* docs/reference/fleet.md",
    "cat infra/ansible/group_vars/all/vault.yml$'\\0'x",
]

# (command, the memo path the message must name)
MEMO_WRITES = [
    ("sed -i 's/- old/- new/' .local/memo.md", ".local/memo.md"),
    ("sed -i.bak -e 's/a/b/' .local/memo.md", ".local/memo.md"),
    ("sed --in-place '/^- done/d' .local/memo.md", ".local/memo.md"),
    ("sed -ni p .local/memo.md", ".local/memo.md"),
    ("sed -i -- 's/a/b/' .tmp/x.md .local/memo.md", ".local/memo.md"),
    ("sed -i 's/a/b/' .local/./memo.md", ".local/./memo.md"),
    ("echo '- item' >> .local/memo.md", ".local/memo.md"),
    ("printf 'x\\n' > .local/memo.md", ".local/memo.md"),
    ("echo x >| ./.local/memo.md", "./.local/memo.md"),
    ("git log -1 --format=%H &>> .local/memo.md", ".local/memo.md"),
    ("> .local/memo.md", ".local/memo.md"),
    ("cat <<'EOF' >> .local/memo.md\n- item\nEOF", ".local/memo.md"),
    ("cat <<EOF>>.local/memo.md\n- item\nEOF", ".local/memo.md"),
    ("cat <<EOF|tee .local/memo.md\n- item\nEOF", ".local/memo.md"),
    ("cat > .tmp/x <<E\\OF\n- item\nEOF\necho x >> .local/memo.md", ".local/memo.md"),
    ("{ echo a; echo b; } >> .local/memo.md", ".local/memo.md"),
    ('echo x >> "$CLAUDE_PROJECT_DIR/.local/memo.md"', "$CLAUDE_PROJECT_DIR/.local/memo.md"),
    ("echo x | tee .local/memo.md", ".local/memo.md"),
    ("echo x | tee -a .local/memo.md >/dev/null", ".local/memo.md"),
    ("echo x | tee --append /dev/null .local/memo.md", ".local/memo.md"),
    ("x=$(echo y | tee -a .local/memo.md)", ".local/memo.md"),
    ("cp .tmp/memo.new .local/memo.md", ".local/memo.md"),
    ("cp /tmp/memo.md .local/", ".local/memo.md"),
    ("cp -t .local .tmp/memo.md", ".local/memo.md"),
    ("cp .tmp/memo.md.bak .tmp/memo.md .local/", ".local/memo.md"),
    ("cp .tmp/memo.bak.md .local/memo.md", ".local/memo.md"),
    ("mv .tmp/memo.md.orig .local/memo.md", ".local/memo.md"),
    ("mv .tmp/memo.new .local/memo.md", ".local/memo.md"),
    (
        "install -m 600 .tmp/memo.new /home/u/Projects/zcrypto-kraken/.local/memo.md",
        "/home/u/Projects/zcrypto-kraken/.local/memo.md",
    ),
    ("truncate -s 0 .local/memo.md", ".local/memo.md"),
    ("time -p sed -i 's/a/b/' .local/memo.md", ".local/memo.md"),
    ("cd .local && sed -i 's/a/b/' memo.md", "memo.md"),
]

MEMO_READS = [
    "cat .local/memo.md",
    "grep -n T0217 .local/memo.md",
    "sed -n '1,40p' .local/memo.md",
    "head -50 .local/memo.md",
    "tail -20 .local/memo.md | cut -c1-80",
    "wc -l .local/memo.md",
    "diff .local/memo.md .tmp/memo.bak",
    "grep -rn tee .local/memo.md",
    "grep -c 'sed -i' .local/memo.md",
    "sha256sum .local/memo.md > .tmp/memo.sha",
    # the memo copied aside, a restore from `.bak` copies, a read piped onward, a write of another file
    "cp .local/memo.md .tmp/memo.bak",
    "cp .local/memo.md .tmp/",
    "cp .tmp/memo.md.bak .local/memo.md",
    "mv .local/memo.md.bak .local/memo.md",
    "install -m 600 .tmp/memo.md.bak .local/memo.md",
    "cat .local/memo.md | tee .tmp/memo.copy",
    "sed -n '/QUEUE/,$p' .local/memo.md > .tmp/queue.md",
    "sed -i 's|.local/memo.md|the memo|' docs/x.md",
    "sed -i 's/.local/memo.md/' docs/x.md",  # the script, not a file: its words end in the memo's two
    "echo x >> .local/memo.md.bak",
    "echo x >> docs/memo.md",
    # the write as text
    "echo '>> .local/memo.md is refused'",
    "cat <<'EOF' > .tmp/note.md\necho x >> .local/memo.md\nEOF",
    'git commit -m "docs: never sed -i .local/memo.md"',
]

MEMO_HOOK = REPO / ".claude" / "hooks" / "memo-guard.sh"

# Each shell writer the stamp family reads, `{text}` the stamp it writes and `{target}` the file it lands in.
STAMP_WRITERS = [
    "cat > {target} <<'EOF'\n- landed {text}\nEOF",
    "cat >> {target} <<'EOF'\n- landed {text}\nEOF",
    "cat <<EOF >> {target}\n- landed {text}\nEOF",
    "cat <<-'EOF' > {target}\n\t- landed {text}\n\tEOF",
    "tee {target} <<'EOF'\n- landed {text}\nEOF",
    "tee -a {target} >/dev/null <<'EOF'\n- landed {text}\nEOF",
    "cat <<'EOF' | tee -a {target}\n- landed {text}\nEOF",
    "cat >> {target} <<< '- landed {text}'",
    "echo '- landed {text}' > {target}",
    'echo "- landed {text}" >> {target}',
    "printf '%s\\n' '- landed {text}' >> {target}",
    "echo '- landed {text}' | tee {target}",
    "printf -- '- landed {text}\\n' | tee -a {target} >/dev/null",
    "git status && cat >> {target} <<'EOF'\n- landed {text}\nEOF",
    "x=$(cat <<'EOF' > {target}\n- landed {text}\nEOF\n)",
    "python - <<'PY' && cat >> {target} <<'EOF'\nprint(1)\nPY\n- landed {text}\nEOF",
    # a delimiter word a metacharacter ends, a command after one on its line, a delimiter built of quoted pieces
    "cat <<EOF>{target}\n- landed {text}\nEOF",
    "cat<<EOF>>{target}\n- landed {text}\nEOF",
    "cat <<EOF>|{target}\n- landed {text}\nEOF",
    "cat <<EOF&>{target}\n- landed {text}\nEOF",
    "cat <<-EOF>{target}\n\t- landed {text}\n\tEOF",
    "cat <<EOF|tee {target}\n- landed {text}\nEOF",
    "cat <<EOF|&tee -a {target}\n- landed {text}\nEOF",
    "cat <<EOF;echo '- landed {text}' >> {target}\nhi\nEOF",
    "cat <<EOF&&echo '- landed {text}' >> {target}\nhi\nEOF",
    "cat > {target} <<E'OF'\n- landed {text}\nEOF",
    "cat > {target} <<'E'OF\n- landed {text}\nEOF",
    'cat > {target} <<"E"OF\n- landed {text}\nEOF',
    "cat > {target} <<$'EOF'\n- landed {text}\nEOF",
    'cat > {target} <<$"EOF"\n- landed {text}\nEOF',
    "cat > .tmp/x <<E\\OF\nhi\nEOF\necho '- landed {text}' >> {target}",
    # a cat naming its stdin by a path, and a writer `time` runs
    "cat /dev/stdin > {target} <<'EOF'\n- landed {text}\nEOF",
    "cat /dev/fd/0 >> {target} <<'EOF'\n- landed {text}\nEOF",
    "cat /proc/self/fd/0 > {target} <<< '- landed {text}'",
    "cat - /dev/./stdin > {target} <<'EOF'\n- landed {text}\nEOF",
    "time echo '- landed {text}' > {target}",
    "time -p printf '%s\\n' '- landed {text}' >> {target}",
]
# The file the writers land in: as written, and through a path that opens under /dev/ and climbs out of it.
STAMP_TARGETS = [".tmp/notes.md", f"/dev/..{REPO}/.tmp/notes.md"]
# (the stamp written, the placeholder the message names)
PLACEHOLDERS = [("19:4xZ", "19:4x"), ("??:??", "??:??")]
PASTED = ["19:45Z", "2026-11-26T19:45:02Z", "mask 0x1F:0x20 of buf[16:0x20]"]

# A text the family does not judge: a here-document an interpreter, a shell or git reads, whatever it then writes; a
# text printed, discarded, sent to a device or piped to another program; a here-document beside a file cat reads.
STAMP_UNWRITTEN = [
    "python - <<'PY'\nprint('19:4xZ')\nPY",
    "uv run python - <<'PY' > .tmp/out.txt\nprint('19:4xZ')\nPY",
    "bash <<'EOF' > .tmp/out.txt\necho 19:4xZ\nEOF",
    "git commit -q -F - <<'EOF'\nfix: landed at 19:4xZ\nEOF",
    "git commit -m \"$(cat <<'EOF'\nfix: landed at 19:4xZ\nEOF\n)\"",
    "cat <<'EOF'\n- landed 19:4xZ\nEOF",
    "echo '- landed 19:4xZ'",
    "echo '- landed 19:4xZ' >&2",
    "echo '- landed 19:4xZ' > /dev/null",
    "echo '- landed 19:4xZ' > /dev/./stderr",
    "echo '- landed 19:4xZ' | tee /dev/tty",
    "echo '- landed 19:4xZ' | grep -c landed > .tmp/count",
    "cat .tmp/draft.md > .tmp/notes.md <<'EOF'\n- landed 19:4xZ\nEOF",
    "python - <<'PY' && cat >> .tmp/notes.md <<'EOF'\nprint('19:4xZ')\nPY\n- landed 19:45Z\nEOF",
]

# A test module's or a hook's own text, which spells the placeholders, a hex literal and the shell pattern.
CASE_TEXT = '("received 12:1xZ", "12:1x"), r"[0-9x?]{2}:[0-9x?]{2}", "??:??", 0x1F'
CASE_FILES = ["tests/test_x.py", "/home/u/Projects/zcrypto-kraken/tests/fixtures/cases.py", ".claude/hooks/x.sh"]
NO_CASE_FILES = ["tests/notes.md", "data/tests/x.md", ".tmp/test_x.py"]

# (command, the approximate clock the message names, the ledger it lands in)
APPROXIMATE_CLOCKS = [
    ("cat >> .local/coordination.md <<'EOF'\n| zcrypto-alex | read ~19:45Z |\nEOF", "~19:45", ".local/coordination.md"),
    ("echo '| zcrypto-alex | ~19:45 |' >> ./.local/coordination.md", "~19:45", "./.local/coordination.md"),
    ("tee -a /home/u/x/.local/coordination.md <<< 'at ~ 19:45Z'", "~ 19:45", "/home/u/x/.local/coordination.md"),
    ("cat <<EOF>>.local/coordination.md\n| zcrypto-alex | read ~19:45Z |\nEOF", "~19:45", ".local/coordination.md"),
    ("cat >> .local/coordination.md <<E'OF'\n| zcrypto-alex | read ~19:45Z |\nEOF", "~19:45", ".local/coordination.md"),
    ("cd .local && printf '%s\\n' 'at ~2026-11-26T19:45Z' >> coordination.md", "~2026-11-26T19:45", "coordination.md"),
    ("echo '| zcrypto-alex | back ~9:45Z |' >> .local/coordination.md", "~9:45", ".local/coordination.md"),
    ("cat /dev/stdin >> .local/coordination.md <<'EOF'\n| a | ~19:45Z |\nEOF", "~19:45", ".local/coordination.md"),
    (
        f"echo '| zcrypto-alex | ~19:45 |' >> /dev/..{REPO}/.local/coordination.md",
        "~19:45",
        f"/dev/..{REPO}/.local/coordination.md",
    ),
    ("echo '- landed ~19:45Z' >> .local/memo.md", "~19:45", ".local/memo.md"),
    (
        "cat <<'EOF' >> /home/u/Projects/zcrypto-kraken/.local/memo.md\n- read ~01:40Z\nEOF",
        "~01:40",
        "/home/u/Projects/zcrypto-kraken/.local/memo.md",
    ),
]
# A tilde before a clock in any other file, and in the coordination table a pasted stamp, a range and a strikethrough.
APPROXIMATE_ELSEWHERE = [
    "echo '- landed ~19:45Z' >> .tmp/notes.md",
    "cat >> docs/coordination.md <<'EOF'\n| x | ~19:45Z |\nEOF",
    "echo '~19:45' > .local/notes.md",
    "echo '| zcrypto-alex | read 19:45Z |' >> .local/coordination.md",
    "echo '| zcrypto-alex | window 19:30~19:45Z |' >> .local/coordination.md",
    "echo '| zcrypto-alex | ~~19:45Z~~ 19:52:03Z |' >> .local/coordination.md",
]

# (text, the placeholder memo-guard.sh and bash-guard.sh both name, or None where both admit it): memo-guard's own cases,
# the lesson's shape, a hex beside a colon and the pattern's own spelling.
STAMP_SPECIMENS = [
    ("received 12:1xZ (the owner's read)", "12:1x"),
    ("at 08:5xZ", "08:5x"),
    ("about 03:0x", "03:0x"),
    ("at 12:xxZ", "12:xx"),
    ("at 1x:30Z", "1x:30"),
    ("at 12:3X", "12:3X"),
    ("at 12:3?Z", "12:3?"),
    ("at 2026-10-11T12:3xZ", "12:3x"),
    ("at ?2:30Z", "?2:30"),
    ("at ??:??Z", "??:??"),
    ("read 01:4xZ", "01:4x"),
    ("received 12:15Z", None),
    ("the fetch at 13:18:04Z", None),
    ("0x1F and 2026-10-11T12:02:30Z", None),
    ("slice buf[16:0x20]", None),
    ("x1:2x0 and 0x10:0x20", None),
    ("[0-9x?]{2}:[0-9x?]{2}", None),
]
# (the file a specimen is written into, whether both hooks exempt it)
SPECIMEN_TARGETS = [("ledger.md", False), ("tests/notes.md", False), ("tests/test_x.py", True), (".claude/hooks/x.sh", True)]

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
    ("sudo -u zhaow git push", "sudo -u zhaow git push"),
    ("if false; then :; else git push; fi", "else git push"),
    ("nice -n 5 gh pr merge 624", "nice -n 5 gh pr merge 624"),
    ("2>/dev/null git push origin x", "git push origin x"),
    ("2>&1 git push origin x", "git push origin x"),
    ("0<&- git push origin x", "git push origin x"),
    ("git 2>/dev/null push origin x", "git push origin x"),
    ("2>/dev/null gh pr merge 624", "gh pr merge 624"),
    ("{fd}>/dev/null git push origin x", "'{fd}' git push origin x"),
    ("{fd}>&- git push origin x", "'{fd}' git push origin x"),
    ("2>/dev/null {fd}>x git push origin x", "'{fd}' git push origin x"),
    ("{fd}>/dev/null gh pr merge 624", "'{fd}' gh pr merge 624"),
    ("coproc git push origin x", "coproc git push origin x"),
    ("flock /tmp/l git push origin x", "flock /tmp/l git push origin x"),
    ("xargs git push origin x", "xargs git push origin x"),
    ("eval git push origin x", "eval git push origin x"),
    ("case x in x) git push;; esac", "case x in x git push"),
    ("echo git push origin x", "echo git push origin x"),
    ("echo gh pr merge 624", "echo gh pr merge 624"),
    ("cat {1..99999999999999999999}; git push origin x", "git push origin x"),
    ("git commit -m x $'\\UFFFFFFFF'; git push origin x", "git push origin x"),
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
    ("git pull", MAIN, "git pull"),
    ("git pull --rebase origin develop", MAIN, "git pull --rebase origin develop"),
    ("git clean -fdx", MAIN, "git clean -fdx"),
    ("git restore .", MAIN, "git restore ."),
    ("git rm -r cli", MAIN, "git rm -r cli"),
    ("git mv a b", MAIN, "git mv a b"),
    ("git revert HEAD", MAIN, "git revert HEAD"),
    ("git am x.patch", MAIN, "git am x.patch"),
    ("git apply --index x.patch", MAIN, "git apply --index x.patch"),
    ("git cherry develop", MAIN, "git cherry develop"),
    ("git config user.name x", MAIN, "git config user.name x"),
    ("git remote add up x", MAIN, "git remote add up x"),
    ("git remote -v prune origin", MAIN, "git remote -v prune origin"),
    ("git branch y develop", MAIN, "git branch y develop"),
    ("git branch -a y", MAIN, "git branch -a y"),
    ("git branch -u origin/develop", MAIN, "git branch -u origin/develop"),
    ("git branch -vv", MAIN, "git branch -vv"),
    ("git tag -a v1 -m x", MAIN, "git tag -a v1 -m x"),
    ("git stash push", MAIN, "git stash push"),
    ("git reflog exists refs/heads/develop", MAIN, "git reflog exists refs/heads/develop"),
    ("git fetch --prune origin", MAIN, "git fetch --prune origin"),
    ("git fetch --pru origin", MAIN, "git fetch --pru origin"),
    ("git fetch -pj4 origin", MAIN, "git fetch -pj4 origin"),
    ("git fetch -tp origin", MAIN, "git fetch -tp origin"),
    ("git fetch --prune-tags origin", MAIN, "git fetch --prune-tags origin"),
    ("git fetch --refmap=+refs/heads/*:refs/heads/* origin", MAIN, "git fetch '--refmap=+refs/heads/*:refs/heads/*' origin"),
    ("git fetch origin develop:develop", MAIN, "git fetch origin develop:develop"),
    ("git worktree prune", MAIN, "git worktree prune"),
    ("2>/dev/null git clean -fdx", MAIN, "git clean -fdx"),
    ("{fd}>&- git reset --hard", MAIN, "'{fd}' git reset --hard"),
    ("flock /tmp/l git clean -fdx", MAIN, "flock /tmp/l git clean -fdx"),
    ("echo git clean -fdx", MAIN, "echo git clean -fdx"),
    ("grep -n git README.md", MAIN, "grep -n git README.md"),
]

# (command, the payload's cwd, the stage the message must name) -- refused from a dispatched agent
AGENT_BRANCH_DELETES = [
    ("git branch -d x", MAIN, "git branch -d x"),
    ("git branch -D x", MAIN, "git branch -D x"),
    ("git branch --delete x", MAIN, "git branch --delete x"),
    ("git branch -rd origin/x", MAIN, "git branch -rd origin/x"),
    ("git branch -D x", WORKTREE, "git branch -D x"),
    (f"git -C {WORKTREE} branch -D develop", MAIN, f"git -C {WORKTREE} branch -D develop"),
    ("git branch --del x", "/tmp/elsewhere", "git branch --del x"),
    ("2>/dev/null git branch -D x", WORKTREE, "git branch -D x"),
    ("{fd}>/dev/null git branch -D x", WORKTREE, "'{fd}' git branch -D x"),
    ("echo git branch -D x", WORKTREE, "echo git branch -D x"),
]

# (command, the payload's cwd, the stage the message must name, what it says the stage does) -- refused from a
# dispatched agent
AGENT_REF_WRITES = [
    ("git branch -m x y", WORKTREE, "git branch -m x y", "renames a branch"),
    ("git branch -M develop x", WORKTREE, "git branch -M develop x", "renames a branch"),
    ("git branch --move x y", MAIN, "git branch --move x y", "renames a branch"),
    ("git branch --mo x y", "/tmp/elsewhere", "git branch --mo x y", "renames a branch"),
    (f"git -C {WORKTREE} branch -M develop", MAIN, f"git -C {WORKTREE} branch -M develop", "renames a branch"),
    ("git branch -c x y", WORKTREE, "git branch -c x y", "copies a branch"),
    ("git branch -C x develop", WORKTREE, "git branch -C x develop", "copies a branch"),
    ("git branch --copy x y", MAIN, "git branch --copy x y", "copies a branch"),
    ("git branch -f develop origin/develop", WORKTREE, "git branch -f develop origin/develop", "forces a branch"),
    ("git branch --force x develop", WORKTREE, "git branch --force x develop", "forces a branch"),
    ("git branch -vf x develop", MAIN, "git branch -vf x develop", "forces a branch"),
    ("git branch --sort -committerdate -D x", WORKTREE, "git branch --sort -committerdate -D x", "deletes a branch"),
    ("git tag -d v1", WORKTREE, "git tag -d v1", "deletes a tag"),
    ("git tag --delete v1 v2", MAIN, "git tag --delete v1 v2", "deletes a tag"),
    ("git tag -f v1 origin/develop", WORKTREE, "git tag -f v1 origin/develop", "forces a tag"),
    ("git tag --force -a v1 -m x", WORKTREE, "git tag --force -a v1 -m x", "forces a tag"),
    ("git tag -af v1 -m x", "/tmp/elsewhere", "git tag -af v1 -m x", "forces a tag"),
    ("git tag -m -fixed -f v1", WORKTREE, "git tag -m -fixed -f v1", "forces a tag"),
    ("git update-ref refs/heads/agent-y HEAD", WORKTREE, "git update-ref refs/heads/agent-y HEAD", "rewrites a ref"),
    ("git update-ref -d refs/heads/develop", WORKTREE, "git update-ref -d refs/heads/develop", "rewrites a ref"),
    ("git update-ref -m why -d refs/heads/x", MAIN, "git update-ref -m why -d refs/heads/x", "rewrites a ref"),
    ("git -C ../../.. update-ref --stdin", WORKTREE, "git -C ../../.. update-ref --stdin", "rewrites a ref"),
    ("git symbolic-ref HEAD refs/heads/develop", WORKTREE, "git symbolic-ref HEAD refs/heads/develop", "rewrites a symbolic ref"),
    ("git symbolic-ref -m why HEAD refs/heads/x", MAIN, "git symbolic-ref -m why HEAD refs/heads/x", "rewrites a symbolic ref"),
    ("git symbolic-ref -- HEAD refs/heads/x", WORKTREE, "git symbolic-ref -- HEAD refs/heads/x", "rewrites a symbolic ref"),
    ("git symbolic-ref -d HEAD", WORKTREE, "git symbolic-ref -d HEAD", "deletes a symbolic ref"),
    ("git symbolic-ref --delete -q HEAD", MAIN, "git symbolic-ref --delete -q HEAD", "deletes a symbolic ref"),
    ("git symbolic-ref -qd HEAD", WORKTREE, "git symbolic-ref -qd HEAD", "deletes a symbolic ref"),
    ("git reflog expire --expire=now --all", WORKTREE, "git reflog expire --expire=now --all", "expires reflog entries"),
    ("git reflog delete HEAD@{1}", MAIN, "git reflog delete 'HEAD@{1}'", "deletes reflog entries"),
    (
        f"git worktree move {MAIN}/.claude/worktrees/refine-17 /tmp/x",
        WORKTREE,
        f"git worktree move {MAIN}/.claude/worktrees/refine-17 /tmp/x",
        "moves a worktree",
    ),
    ("git worktree move .tmp/reads/x/wt .tmp/reads/y", MAIN, "git worktree move .tmp/reads/x/wt .tmp/reads/y", "moves a worktree"),
]

# (command, the payload's cwd, the path the message must name) -- refused from a dispatched agent
AGENT_WORKTREE_REMOVES = [
    ("git worktree remove .claude/worktrees/agent-x", MAIN, ".claude/worktrees/agent-x"),
    (
        f"git -C {WORKTREE} worktree remove --force {MAIN}/.claude/worktrees/refine-17",
        WORKTREE,
        f"{MAIN}/.claude/worktrees/refine-17",
    ),
    (f"git -C {WORKTREE} worktree remove --force {WORKTREE}", MAIN, WORKTREE),
    ("git worktree remove .tmp/reads/x/wt", WORKTREE, ".tmp/reads/x/wt"),  # a .tmp/ of a directory that is no worktree
    (f"git worktree remove {MAIN}/.tmpx/wt", MAIN, f"{MAIN}/.tmpx/wt"),
    (f"git worktree remove {MAIN}/.tmp", MAIN, f"{MAIN}/.tmp"),
    ('git worktree remove --force "$WT"', WORKTREE, "$WT"),
    (f"git worktree remove --force {TMP_ROOT}/{PROJECT}/wt-b", WORKTREE, f"{TMP_ROOT}/{PROJECT}/wt-b"),  # a payload session's
    (f"git worktree remove {TMP_ROOT}/{PROJECT}/{OTHER_SESSION}/wt", WORKTREE, f"{TMP_ROOT}/{PROJECT}/{OTHER_SESSION}/wt"),
    (f"git worktree remove {TMP_ROOT}/{PROJECT}/{SESSION}", WORKTREE, f"{TMP_ROOT}/{PROJECT}/{SESSION}"),
    (f"cd {MAIN} && git worktree remove .claude/worktrees/y", "/tmp", ".claude/worktrees/y"),
    ('cd "$WT" && git worktree remove wt', MAIN, "wt"),  # relative to a directory the hook cannot know
]

# (command, the payload's cwd) -- admitted silently from a dispatched agent
AGENT_ADMITTED = [
    ("git status", WORKTREE),
    ("git log --oneline develop..HEAD", WORKTREE),
    ("git fetch origin develop", WORKTREE),
    ('git commit -m "then git push"', WORKTREE),
    ('echo "git push"', WORKTREE),
    (">out git status", MAIN),
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
    ("git branch --merged develop", WORKTREE),
    ("git branch -vv", WORKTREE),
    ("git branch agent-y develop", WORKTREE),
    ("git branch -uorigin/develop", WORKTREE),
    ("git branch -tdirect agent-y origin/develop", WORKTREE),
    ("git branch --format=%(refname:short) --sort=-committerdate", WORKTREE),
    ("git branch --sort -committerdate", WORKTREE),
    ("git tag", WORKTREE),
    ("git tag -l", WORKTREE),
    ("git tag -l 'v*' -n3", WORKTREE),
    ("git tag --list --sort=-v:refname --contains HEAD", WORKTREE),
    ("git tag -a v1 -m -fixed", WORKTREE),
    ("git tag -a v1 -mdraft", WORKTREE),
    ("git tag -a v1 --message -fixed", WORKTREE),
    ("git symbolic-ref HEAD", WORKTREE),
    ("git symbolic-ref --short HEAD", WORKTREE),
    ("git symbolic-ref -q HEAD", MAIN),
    ("git symbolic-ref -m why HEAD", WORKTREE),
    ("git reflog", WORKTREE),
    ("git reflog show", WORKTREE),
    ("git reflog show --date=iso develop", WORKTREE),
    ("git reflog exists refs/heads/develop", WORKTREE),
    ("git reflog list", WORKTREE),
    ("git stash", WORKTREE),
    ("git rebase develop", WORKTREE),
    (f"cd {WORKTREE} && git commit -m x", MAIN),
    (f"git -C {WORKTREE} commit -m x", MAIN),
    ("git -C .claude/worktrees/agent-x add f", MAIN),
    ("cd .claude/worktrees/agent-x && git commit -m x", MAIN),
    (f"git -C {SCRATCH} commit -m x", MAIN),
    ("cd .tmp/scratch && git init -q && git add . && git commit -m x", MAIN),
    (f"git -C {MAIN} worktree remove --force {MAIN}/.tmp/reads/x/wt-pre-head", MAIN),
    ("git worktree remove --force .tmp/reads/x/wt-pre-head", MAIN),
    (f"git worktree remove --force {MAIN}/.tmp/reads/x/wt-pre-head", WORKTREE),
    ("git worktree remove ../../../.tmp/reads/x/wt", WORKTREE),
    (f"git -C {WORKTREE} worktree remove --force {SCRATCHPAD}/wt", WORKTREE),
    (f"git -C {MAIN} worktree remove /tmp/{PROJECT}/{SESSION}/wt", "/tmp"),
    ("git status", MAIN),
    ("git log --oneline -3", MAIN),
    ("git show HEAD", MAIN),
    ("git diff develop...HEAD", MAIN),
    ("git diff-tree -r HEAD", MAIN),
    ("git rev-parse HEAD", MAIN),
    ("git rev-list -n1 HEAD", MAIN),
    ("git ls-files", MAIN),
    ("git ls-tree HEAD", MAIN),
    ("git ls-remote origin", MAIN),
    ("git cat-file -t HEAD", MAIN),
    ("git grep -n TODO -- cli ':!*vault*' ':!*.sops.*' ':!infra/ansible/files/*_ed25519'", MAIN),
    ("git blame README.md", MAIN),
    ("git describe --tags", MAIN),
    ("git name-rev HEAD", MAIN),
    ("git merge-base develop HEAD", MAIN),
    ("git merge-tree --write-tree develop HEAD", MAIN),
    ("git for-each-ref refs/heads", MAIN),
    ("git count-objects -v", MAIN),
    ("git check-ignore -v data/x", MAIN),
    ("git config --get user.name", MAIN),
    ("git config --list", MAIN),
    ("git config get user.name", MAIN),
    ("git remote", MAIN),
    ("git remote -v", MAIN),
    ("git remote show origin", MAIN),
    ("git branch", MAIN),
    ("git branch --list", MAIN),
    ("git branch --list 'claude/*'", MAIN),
    ("git branch -a", MAIN),
    ("git branch -r", MAIN),
    ("git branch --show-current", MAIN),
    ("git branch --contains HEAD", MAIN),
    ("git branch --merged develop", MAIN),
    ("git branch --no-merged develop", MAIN),
    ("git tag", MAIN),
    ("git tag -l", MAIN),
    ("git tag --list 'v*'", MAIN),
    ("git tag --contains HEAD", MAIN),
    ("git stash list", MAIN),
    ("git stash show -p", MAIN),
    ("git reflog", MAIN),
    ("git reflog show", MAIN),
    ("git fetch origin", MAIN),
    ("git fetch --no-prune origin develop", MAIN),
    ("git fetch -j4 origin", MAIN),
    ("git worktree list", MAIN),
    ("git worktree add .claude/worktrees/y -b y develop", MAIN),
    (f"git -C {MAIN} worktree add --detach {MAIN}/.tmp/reads/x/wt-pre-head HEAD", "/tmp"),
    ("git pull", WORKTREE),
    ("git pull --rebase origin develop", WORKTREE),
    ("git clean -fdx", WORKTREE),
    ("git restore .", WORKTREE),
    ("git rm -r cli", WORKTREE),
    ("git mv a b", WORKTREE),
    ("git revert HEAD", WORKTREE),
    ("git am x.patch", WORKTREE),
    ("git apply --index x.patch", WORKTREE),
    ('cd "$WT" && git commit -m x', MAIN),  # a directory through a variable is judged as nothing
    ("cd - && git commit -m x", MAIN),
    ("popd && git commit -m x", MAIN),
    (f"pushd {WORKTREE} && git commit -m x", MAIN),
    ("git commit -m x", "/tmp/elsewhere"),
    ("git commit -m x", f"{MAIN}-other"),  # a sibling sharing the main checkout's path as a prefix
]


# `grep` and `rg` stay the printing arm's: the git-grep arm admits them whatever their scope.
UNSCOPED_GREPS = [
    ("git grep -l foo -- tests infra", "."),
    ("git grep -n foo", "."),
    ("git grep -n foo HEAD", "."),
    ("git grep -n foo HEAD:infra", "."),
    ("git grep -n foo 'HEAD^{tree}'", "."),
    ("git grep -n foo ':/caddy'", "."),
    ("git grep -n foo ':0:infra/ansible/files/deploy_zcrypto_ed25519'", "."),
    ("git grep -n foo 0e950ee10 -- infra/ansible/files", "."),
    ("git grep -l foo 0e950ee10 -- infra/ansible/files/deploy_ed25519", "."),
    ("git grep -O foo infra docs", "."),
    ("git grep --open-files-in-pager foo infra docs", "."),
    ("git grep --cont 3 docs", "."),
    ("git grep --max-c 1 docs", "."),
    ("git grep --after 3 docs", "."),
    ("git grep --thr 2 docs", "."),
    ("git grep --max-dep 1 docs", "."),
    ("git grep -nC 3 docs", "."),
    ("git grep -lm 1 docs", "."),
    ("git grep -nA 2 docs", "."),
    ("git grep -n foo archive/w4-status-after-pipeline -- docs", "."),
    ("git grep -C 99 -e -- 0e950ee10 'infra/ansible/files/deploy_ed2551*'", "."),
    ("git grep -ne -- HEAD:infra", "."),
    ("git grep -n -- foo", "."),
    ("git grep -n -- foo HEAD:infra", "."),
    ("git grep -C 99 -- BEGIN 0e950ee10 'infra/ansible/files/deploy_ed2551*'", "."),
    ("git grep --no-inde -l foo -- docs", "."),
    ("git grep --untrack -l foo -- docs", "."),
    ("git grep -n foo -- ':(nonsense)infra'", "."),
    ("git grep -n foo -- infra/ansible", "."),
    ("git grep -n foo -- ./infra ':!*.sops.*'", "."),
    ("git grep -n foo -- infra//ansible", "."),
    ("git grep -n foo -- ':(icase)INFRA'", "."),
    ("git grep -n foo -- infra/ansible/group_vars/all/vault.yml", "."),
    ("git grep -n foo -- README.md ':/'", "."),
    ("git grep -l foo -- infra ':!*vault*' ':!*.sops.*' ':!infra/ansible/files/deploy_*'", "."),
    ("git grep -l foo -- infra ':!*vault*' ':!*.sops.*' ':!*/deploy_*_ed25519'", "."),
    ("git grep -l foo -- infra ':!docs/vault-notes.md' ':!x.sops.d' ':!y_ed25519'", "."),
    ("git grep -n foo -- infra ':(exclude,glob)*vault*' ':(exclude)*.sops.*' ':(exclude)infra/ansible/files/*_ed25519'", "."),
    ("git grep -n foo -- ../infra", "docs"),
    ("git grep -n foo -- ':/'", "docs"),
    ("git grep -n foo -- ':(top)infra'", "docs"),
    ("git grep -l foo -- ':!*vault*' ':!*.sops.*'", "infra"),
    ("git grep -n foo -- files/deploy_zcrypto_ed25519", "infra/ansible"),
    ("git grep -c ANSIBLE -- infra/ansible/group_vars ':!zzzz'", "."),
    ("git grep -c ANSIBLE -- infra/ansible/group_vars ':/!zzzz'", "."),
    ("git grep -c ANSIBLE -- infra/ansible/group_vars ':(exclude)zzzz'", "."),
]
SCOPED_GREPS = [
    # excludes of every vaulted file the positives reach
    ("git grep -l foo -- tests infra ':!*vault*' ':!*.sops.*' ':!infra/ansible/files/*_ed25519'", "."),
    (
        "git grep -n -e foo -- infra ':!*vault.yml' ':!*.vault' ':!*.sops.*' ':!*vault-password*' ':!infra/ansible/files/*_ed25519'",
        ".",
    ),
    ("git grep -n foo -- infra ':^*vault*' ':^*.sops.*' ':^infra/ansible/files/*_ed25519'", "."),
    (
        "git grep -l foo -- infra/ansible ':!*vault.yml' ':!*.vault' ':!*.sops.*' ':!*vault-password*' ':!infra/ansible/files/*_ed25519'",
        ".",
    ),
    (
        "git grep -n foo -- docs ':!*vault.yml' ':!*.vault' ':!*.sops.*' ':!*vault-password*' ':!infra/ansible/files/*_ed25519'",
        ".",
    ),
    ("git grep -n foo -- '*.md' ':!*vault-password*'", "."),
    ("git grep -l foo -- infra/ansible/roles ':!*.vault'", "."),
    ("git grep -n foo -- ':!*vault.yml' ':!*.vault' ':!*.sops.*' ':!*vault-password*' ':!infra/ansible/files/*_ed25519'", "."),
    ("git grep -l foo -- infra/scripts infra/runbooks tests", "."),
    ("git grep -n foo -- tests/test_bash_guard.py", "."),
    ("git grep -n foo tests/test_bash_guard.py README.md", "."),
    ("git grep -n foo -- README.md ':(glob)infra/*'", "."),
    ("git grep -n foo -- ':(top)README.md'", "."),
    ("git grep -n foo -- ':(literal)README.md'", "."),
    ("git grep --max-count 1 foo pyproject.toml", "."),
    ("git grep -l -e foo -e bar -- tests", "."),
    ("git grep -n foo -- docs/reference cli", "."),
    # docs holds a topic about the vault password, which no pattern of the set names
    ("git grep -n -l x -- tests docs cli", "."),
    ("git grep -n foo -- docs", "."),
    ("git grep -n foo -- docs/open-topics", "."),
    ("git grep -n foo HEAD -- docs/reference", "."),
    ("git grep -n foo HEAD -- README.md", "."),
    ("git grep -Ofoo infra docs/reference", "."),
    ("git grep -nC3 foo -- docs/reference", "."),
    ("git grep --cont 3 foo -- docs/reference", "."),
    ("git grep -e -- -- docs/reference", "."),
    ("git grep -ne -- docs/README.md", "."),
    ("git grep -n -- foo -- docs/reference", "."),
    ("git grep -n -- foo docs/README.md", "."),
    ("git grep -n -- foo -- HEAD:infra", "."),
    ("git grep -n foo -- .", "docs/reference"),
    ("git grep -n foo -- ':/tests'", "infra"),
    ("grep -n foo README.md", "."),
]


def git_dir(checkout: str | Path) -> Path:
    return Path(
        subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "--absolute-git-dir"], capture_output=True, text=True, check=True
        ).stdout.strip()
    )


CONSUMERS_SILENCED = [
    "bash infra/scripts/consumers.sh --direct cli/x.py 2>/dev/null",
    "infra/scripts/consumers.sh cli/x.py 2>/dev/null | sort -u",
    "bash infra/scripts/consumers.sh --direct cli/x.py 2>/dev/null | sort -u > .tmp/T.txt",
    "mkdir -p .tmp && bash infra/scripts/consumers.sh --direct cli/x.py >/dev/null 2>&1",
    "cd /x && bash infra/scripts/consumers.sh --direct cli/x.py 2> /dev/null",
    "T=$(bash infra/scripts/consumers.sh --direct cli/x.py 2>/dev/null)",
    "timeout 5 bash infra/scripts/consumers.sh --direct cli/x.py 2>/dev/null",
    "bash -x infra/scripts/consumers.sh --direct cli/x.py 2>/dev/null",
    "env FOO=1 bash infra/scripts/consumers.sh --direct cli/x.py 2>/dev/null",
    "echo cli/x.py | xargs bash infra/scripts/consumers.sh --direct 2>/dev/null",
    "source infra/scripts/consumers.sh 2>/dev/null",
]
CONSUMERS_ADMITTED = [
    "bash infra/scripts/consumers.sh --direct cli/x.py 2> .tmp/err.txt | sort -u",
    "bash infra/scripts/consumers.sh --direct cli/x.py",
    "uv run pytest tests/x.py -q 2>/dev/null",
    "ls 2>/dev/null; bash infra/scripts/consumers.sh cli/x.py",
    # a read or a check of the script, not a run of it
    "ls infra/scripts/consumers.sh 2>/dev/null",
    "git diff --quiet -- infra/scripts/consumers.sh 2>/dev/null",
    "bash -n infra/scripts/consumers.sh 2>/dev/null",
    "grep -n direct_readers infra/scripts/consumers.sh >/dev/null && echo yes",
    "cat infra/scripts/consumers.sh 2>/dev/null",
    "shellcheck infra/scripts/consumers.sh >/dev/null",
]
STAMP_NAME = "zcrypto-git-state-stamp"
# The checkouts the corpus's admitted `git commit`s stamp for the runs-alone arm: the cases run one at a time across
# xdist workers, each with those stamps gone, or the next admitted commit within 3 s is refused.
STAMPS = [git_dir(d) / STAMP_NAME for d in (str(REPO), MAIN)]
LOCK = REPO / ".tmp" / ".bash-guard-tests.lock"


def run_hook(payload: dict | str, cwd: Path, env: dict | None = None, hook: Path = HOOK) -> subprocess.CompletedProcess:
    """Dicts are JSON-encoded; strings pass through verbatim so the malformed-input cases can hand the hook
    something that is not JSON."""
    LOCK.parent.mkdir(exist_ok=True)
    with open(LOCK, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for stamp in STAMPS:
            stamp.unlink(missing_ok=True)
        return subprocess.run(
            ["bash", str(hook)],
            input=payload if isinstance(payload, str) else json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
        )


def call(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(REPO)}


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


@pytest.mark.parametrize(("admitted", "refused"), READER_PROGRAMS, ids=[a for a, _ in READER_PROGRAMS])
@pytest.mark.parametrize("extra", [{}, {"agent_id": "a1"}], ids=["main loop", "dispatched agent"])
def test_a_readers_program_naming_vault_yml_is_admitted_and_the_vaulted_file_it_reads_is_refused(
    tmp_path: Path, admitted: str, refused: str, extra: dict
):
    r = run_hook(agent_call(admitted, str(REPO), **extra), cwd=tmp_path, env=AGENT_ENV)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    r = run_hook(agent_call(refused, str(REPO), **extra), cwd=tmp_path, env=AGENT_ENV)
    assert r.returncode == 2 and f"prints the vaulted file `{refused.split()[-1]}`;" in r.stderr, r.stderr


@pytest.mark.parametrize(("command", "spelling"), PAST_THE_BRACE_CAP, ids=[c for c, _ in PAST_THE_BRACE_CAP])
@pytest.mark.parametrize("extra", [{}, {"agent_id": "a1"}], ids=["main loop", "dispatched agent"])
def test_a_word_past_the_brace_cap_is_refused_by_a_tail_that_globs_to_a_vaulted_file(
    tmp_path: Path, command: str, spelling: str, extra: dict
):
    r = run_hook(agent_call(command, str(REPO), **extra), cwd=tmp_path, env=AGENT_ENV)
    assert r.returncode == 2 and f"prints the vaulted file `{spelling}`;" in r.stderr, r.stderr


@pytest.mark.parametrize("command", PAST_THE_BRACE_CAP_ADMITTED.values(), ids=PAST_THE_BRACE_CAP_ADMITTED.keys())
@pytest.mark.parametrize("extra", [{}, {"agent_id": "a1"}], ids=["main loop", "dispatched agent"])
def test_a_word_past_the_brace_cap_naming_no_vaulted_file_is_admitted(tmp_path: Path, command: str, extra: dict):
    r = run_hook(agent_call(command, str(REPO), **extra), cwd=tmp_path, env=AGENT_ENV)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def test_a_star_read_for_a_brace_group_matches_a_leading_dot(tmp_path: Path):
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "vault.yml").write_text("")
    r = run_hook(agent_call("cat {.,x}hidden/vault.yml{,}{,}{,}{,}{,}{,}{,}{,}", str(tmp_path)), cwd=tmp_path)
    assert r.returncode == 2 and "prints the vaulted file `*hidden/vault.yml********`;" in r.stderr, r.stderr


@pytest.fixture(scope="module")
def specimen_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    repo = tmp_path_factory.mktemp("specimens")
    for path, _ in VAULT_SPECIMENS:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text("x\n")
    for args in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "s"]):
        subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    return repo


# (a read of a specimen, what its refusal says) -- the arms that judge a path on disk, a pathspec and a revision's path
SPECIMEN_READS = [
    ("cat {}", "prints the vaulted file `{}`;"),
    ("git grep -n x -- {}", "may search the vaulted file `{}`"),
    ("git show HEAD:{}", "prints the vaulted file `{}` at a revision"),
]


@pytest.mark.parametrize(("path", "vaulted"), VAULT_SPECIMENS, ids=[p for p, _ in VAULT_SPECIMENS])
@pytest.mark.parametrize(("read", "refusal"), SPECIMEN_READS, ids=[r.format("<path>") for r, _ in SPECIMEN_READS])
def test_the_hook_refuses_a_read_of_exactly_the_specimens_consumers_sh_excludes(
    specimen_repo: Path, tmp_path: Path, path: str, vaulted: bool, read: str, refusal: str
):
    r = run_hook(agent_call(read.format(path), str(specimen_repo)), cwd=tmp_path)
    if vaulted:
        assert r.returncode == 2 and refusal.format(path) in r.stderr, r.stderr
    else:
        assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def test_a_git_grep_over_a_directory_holding_a_specimen_consumers_sh_excludes_is_refused_reciting_the_set(
    specimen_repo: Path, tmp_path: Path
):
    for command in ("git grep -n x -- docs", "git grep -n x -- docs ':!*.vault'"):
        r = run_hook(agent_call(command, str(specimen_repo)), cwd=tmp_path)
        assert r.returncode == 2 and "may search the vaulted file `docs/x/fake-vault.yml`" in r.stderr, r.stderr
        assert all(f"`{spec.removeprefix(':!')}`" in r.stderr for spec in vault_excludes()), r.stderr
    r = run_hook(agent_call("git grep -n x -- tests", str(specimen_repo)), cwd=tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


EXCLUDES = shlex.join(vault_excludes())
# (a git grep over the specimens, the directory it runs from, the vaulted file its refusal names or None for an
# admission); a positive naming a directory beside an exclude is a row of its own because git's ls-files, reading
# both at once, keeps the member `docs/x ':!*fake*'` drops and lists nothing for `infra/ansible/files ':!*.pub'`.
SPECIMEN_GREPS = [
    ("git grep -n x -- docs ':!*vault.yml'", ".", None),
    (f"git grep -n x -- docs {EXCLUDES}", ".", None),
    (f"git grep -n x -- . {EXCLUDES}", ".", None),
    ("git grep -n x -- docs/open-topics", ".", None),
    ("git grep -n x -- docs ':^*vault.yml'", ".", None),
    ("git grep -n x -- docs ':(exclude)*vault.yml'", ".", None),
    ("git grep -n x -- docs ':/!*vault.yml'", ".", None),
    ("git grep -n x -- docs ':!docs/x'", ".", None),
    ("git grep -n x -- docs/x ':!*fake*'", ".", None),
    ("git grep -n x -- '*.yml' ':!*vault.yml'", ".", None),
    ("git grep -n x -- infra ':!infra/ansible/files/*_ed25519'", ".", None),
    ("git grep -n x HEAD -- docs ':!*vault.yml'", ".", None),
    ("git grep -n x HEAD -- docs/x ':!*fake*'", ".", None),
    ("git grep -n x -- ':!*vault.yml'", "docs", None),
    ("git grep -n x -- . ':!fake-vault.yml'", "docs/x", None),
    ("git grep -n x -- ':/docs' ':/!*vault.yml'", "tests", None),
    ("git grep -n x -- docs", ".", "docs/x/fake-vault.yml"),
    ("git grep -n x -- docs ':!*.vault'", ".", "docs/x/fake-vault.yml"),
    ("git grep -n x -- docs ':!docs/y'", ".", "docs/x/fake-vault.yml"),
    ("git grep -n x -- infra/ansible/files ':!*.pub'", ".", "infra/ansible/files/deploy_x_ed25519"),
    ("git grep -n x -- '*.yml' ':!*fake*'", ".", "group_vars/x/vault.yml"),
    ("git grep -n x -- . ':!*vault.yml' ':!*.vault' ':!*.sops.*' ':!infra/ansible/files/*_ed25519'", ".", "vault-password"),
    ("git grep -n x -- infra ':!infra/ansible/files/*.pub'", ".", "infra/ansible/files/deploy_x_ed25519"),
    ("git grep -n x HEAD -- docs ':!*.vault'", ".", "docs/x/fake-vault.yml"),
    ("git grep -n x HEAD -- infra/ansible/files ':!*.pub'", ".", "infra/ansible/files/deploy_x_ed25519"),
    ("git grep -n x -- ':!*.vault'", "docs", "docs/x/fake-vault.yml"),
    ("git grep -n x -- ':/' ':!*vault.yml'", "docs", "a.sops.yaml"),
    ("git grep -n x -- ':/docs' ':!*.vault'", "tests", "docs/x/fake-vault.yml"),
    ("git grep -n x -- ':/docs' ':!*vault.yml'", "tests", "docs/x/fake-vault.yml"),
]


def grep_reads(cwd: Path, command: str) -> set[str]:
    # The files git grep itself reads under the command's pathspecs, named from the top: every specimen holds `x`.
    done = subprocess.run(["git", "grep", "--full-name", "-l", *shlex.split(command)[2:]], cwd=cwd, capture_output=True, text=True)
    return {line.removeprefix("HEAD:") for line in done.stdout.splitlines()}


@pytest.mark.parametrize(("command", "sub", "hit"), SPECIMEN_GREPS, ids=[f"{c} @ {s}" for c, s, _ in SPECIMEN_GREPS])
def test_a_git_grep_is_refused_exactly_when_git_would_search_a_specimen_consumers_sh_excludes(
    specimen_repo: Path, tmp_path: Path, command: str, sub: str, hit: str | None
):
    reached = grep_reads(specimen_repo / sub, command) & {path for path, vaulted in VAULT_SPECIMENS if vaulted}
    assert (hit is not None) == bool(reached) and (hit is None or hit in reached), reached
    r = run_hook(agent_call(command, str(specimen_repo / sub)), cwd=tmp_path)
    if hit is None:
        assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    else:
        assert r.returncode == 2 and f"may search the vaulted file `{hit}`" in r.stderr, r.stderr


# (a checkout's place under a directory of its own, its files each with whether consumers.sh's excludes drop it there):
# a directory above the top whose name a pattern matches -- a trailing `*` takes a whole path, `*` crosses `/` --
# never makes a file vaulted, as git reads the pathspecs from the top.
CHECKOUTS = {
    "vault-password.d": [("README.md", False), ("cli/a.py", False), ("vault.yml", True), ("docs/fake-vault.yml", True)],
    "notes.sops.d": [("README.md", False), ("cli/a.py", False), ("x.vault", True)],
    "infra/ansible/files/k": [("README.md", False), ("x_ed25519", False), ("infra/ansible/files/deploy_x_ed25519", True)],
}
# A read of `{f}` from its checkout's top by each arm judging a path on disk: printers, a copier, an interpreter's
# `-c`, a redirect, an absolute path, a glob, a brace group, and from a subdirectory.
CHECKOUT_READS = [
    "cat {f}",
    "head -5 {f}",
    "sed -n 1p {f}",
    "cp {f} /dev/null",
    "python3 -c \"open('{f}')\"",
    "cat < {f}",
    "cat {top}/{f}",
    "cat {glob}",
    "cat {{{f},none}}",
    "cd sub && cat ../{f}",
]


@pytest.fixture(scope="module")
def checkouts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("above")
    for top, files in CHECKOUTS.items():
        for path, _ in files:
            (base / top / path).parent.mkdir(parents=True, exist_ok=True)
            (base / top / path).write_text("x\n")
        (base / top / "sub").mkdir()
        for args in (["init", "-q"], ["add", "-A"]):
            subprocess.run(["git", "-C", str(base / top), *args], capture_output=True, check=True)
    return base


@pytest.mark.parametrize("read", CHECKOUT_READS)
@pytest.mark.parametrize(
    ("top", "path", "vaulted"), [(t, p, v) for t, files in CHECKOUTS.items() for p, v in files], ids=lambda x: str(x)
)
def test_a_file_under_a_checkouts_top_is_vaulted_exactly_when_its_pathspecs_drop_it_there(
    checkouts: Path, tmp_path: Path, top: str, path: str, vaulted: bool, read: str
):
    repo = checkouts / top
    kept = subprocess.run(["git", "-C", str(repo), "ls-files", "--", *vault_excludes()], capture_output=True, text=True)
    assert (path not in kept.stdout.splitlines()) == vaulted, kept.stdout
    command = read.format(f=path, top=repo, glob=path[:-1] + "?")
    r = run_hook(agent_call(command, str(repo)), cwd=tmp_path)
    if vaulted:
        assert r.returncode == 2 and "the vaulted file" in r.stderr, r.stderr
    else:
        assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def test_outside_every_repository_each_directory_of_a_path_is_read_as_a_top(tmp_path: Path):
    files = [
        ("plain/README.md", False),
        ("vault-password.d/README.md", True),
        ("plain/fake-vault.yml", True),
        ("x/infra/ansible/files/deploy_x_ed25519", True),
    ]
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": os.path.realpath(tmp_path)}
    for path, vaulted in files:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("x\n")
        where = (tmp_path / path).parent
        assert subprocess.run(["git", "-C", str(where), "rev-parse"], capture_output=True, env=env).returncode
        r = run_hook(agent_call(f"cat {path}", str(tmp_path)), cwd=tmp_path, env=env)
        if vaulted:
            assert r.returncode == 2 and f"prints the vaulted file `{path}`" in r.stderr, r.stderr
        else:
            assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def hook_beside(tmp_path: Path, definition: str | None) -> Path:
    # A copy of the hook in a checkout of its own, beside a consumers.sh holding `definition`, or none.
    top = tmp_path / "checkout"
    (top / ".claude" / "hooks").mkdir(parents=True)
    hook = top / ".claude" / "hooks" / "bash-guard.sh"
    hook.write_bytes(HOOK.read_bytes())
    if definition is not None:
        (top / "infra" / "scripts").mkdir(parents=True)
        (top / "infra" / "scripts" / "consumers.sh").write_text(definition)
    return hook


# (the case, what the consumers.sh beside the hook holds or None for no file, what the refusal says of it)
NO_LINE = "holds no one-line `VAULT_EXCLUDES=("
UNREAD_SETS = [
    ("no file", None, "could not be read"),
    ("no assignment", "set -euo pipefail\n", NO_LINE),
    ("an array over lines", "VAULT_EXCLUDES=(\n  ':!*vault.yml'\n)\n", NO_LINE),
    ("a double-quoted word", 'VAULT_EXCLUDES=(":!*vault.yml")\n', NO_LINE),
    ("a second assignment", "VAULT_EXCLUDES=(':!*vault.yml')\nVAULT_EXCLUDES+=(':!*.vault')\n", NO_LINE),
    ("a long-form exclude", "VAULT_EXCLUDES=(':!*vault.yml' ':(exclude)*.vault')\n", "`:(exclude)*.vault` in"),
    ("a character class", "VAULT_EXCLUDES=(':!*vault.yml' ':!infra/[a-z]*_ed25519')\n", "`:!infra/[a-z]*_ed25519` in"),
    # every other bash writer of the array, which a parse of the one line would miss, and words bash joins into one
    ("an indexed element", "VAULT_EXCLUDES=(':!*vault.yml')\nVAULT_EXCLUDES[1]=':!*.vault'\n", NO_LINE),
    ("an indexed append", "VAULT_EXCLUDES=(':!*vault.yml')\nVAULT_EXCLUDES[0]+='x'\n", NO_LINE),
    ("a declare", "VAULT_EXCLUDES=(':!*vault.yml')\ndeclare -a VAULT_EXCLUDES=(':!*.vault')\n", NO_LINE),
    ("a mapfile", "VAULT_EXCLUDES=(':!*vault.yml')\nmapfile -t VAULT_EXCLUDES < x\n", NO_LINE),
    ("a read", "VAULT_EXCLUDES=(':!*vault.yml')\nread -ra VAULT_EXCLUDES <<< x\n", NO_LINE),
    ("an unset element", "VAULT_EXCLUDES=(':!*vault.yml' ':!*.vault')\nunset 'VAULT_EXCLUDES[1]'\n", NO_LINE),
    ("a printf -v", "VAULT_EXCLUDES=(':!*vault.yml')\nprintf -v 'VAULT_EXCLUDES[1]' %s ':!*.vault'\n", NO_LINE),
    ("a nameref", "VAULT_EXCLUDES=(':!*vault.yml')\ndeclare -n v=VAULT_EXCLUDES\nv+=(':!*.vault')\n", NO_LINE),
    ("adjacent quoted words", "VAULT_EXCLUDES=(':!*vault.yml'':!*.vault')\n", NO_LINE),
]
UNREAD_SET_READS = ["cat README.md", "git grep -n x -- README.md", "git show HEAD:README.md", "cp README.md .tmp/x"]


@pytest.mark.parametrize("command", UNREAD_SET_READS)
@pytest.mark.parametrize(("definition", "why"), [s[1:] for s in UNREAD_SETS], ids=[s[0] for s in UNREAD_SETS])
def test_a_vaulted_set_the_hook_cannot_read_refuses_every_command_judged_against_it(
    tmp_path: Path, definition: str | None, why: str, command: str
):
    r = run_hook(call(command), cwd=tmp_path, hook=hook_beside(tmp_path, definition))
    claim = r.stderr.partition("; in `")[0]
    assert r.returncode == 2 and "the vaulted set cannot be had" in claim and why in claim, r.stderr


@pytest.mark.parametrize("command", ["git status", "ls -la infra/ansible/files", "grep -c x README.md"])
@pytest.mark.parametrize(("definition", "why"), [s[1:] for s in UNREAD_SETS], ids=[s[0] for s in UNREAD_SETS])
def test_a_vaulted_set_the_hook_cannot_read_admits_what_is_judged_against_no_set(
    tmp_path: Path, definition: str | None, why: str, command: str
):
    r = run_hook(call(command), cwd=tmp_path, hook=hook_beside(tmp_path, definition))
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def test_a_pattern_with_no_wildcard_names_the_files_under_a_directory_as_gits_exclude_does(tmp_path: Path):
    hook = hook_beside(tmp_path, "VAULT_EXCLUDES=(':!keys')\n")
    repo = tmp_path / "repo"
    for path in ("keys/a", "keysake/b", "c"):
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text("x\n")
    for args in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True)
    kept = subprocess.run(["git", "-C", str(repo), "ls-files", "--", ":!keys"], capture_output=True, text=True, check=True)
    assert kept.stdout.splitlines() == ["c", "keysake/b"]
    for path, vaulted in (("keys/a", True), ("keysake/b", False), ("c", False)):
        r = run_hook(agent_call(f"cat {path}", str(repo)), cwd=tmp_path, hook=hook)
        assert r.returncode == (2 if vaulted else 0) and ("prints the vaulted file" in r.stderr) == vaulted, r.stderr


@pytest.mark.parametrize(("path", "vaulted"), VAULT_SPECIMENS, ids=[p for p, _ in VAULT_SPECIMENS])
def test_a_copy_of_the_hook_beside_the_trees_consumers_sh_judges_as_the_hook_does(
    specimen_repo: Path, tmp_path: Path, path: str, vaulted: bool
):
    copy = hook_beside(tmp_path, (REPO / "infra/scripts/consumers.sh").read_text())
    for read, _ in SPECIMEN_READS:
        payload = agent_call(read.format(path), str(specimen_repo))
        theirs, ours = run_hook(payload, cwd=tmp_path, hook=copy), run_hook(payload, cwd=tmp_path)
        assert theirs.returncode == ours.returncode == (2 if vaulted else 0) and theirs.stderr == ours.stderr, theirs.stderr


@pytest.mark.parametrize("command", ADMITTED)
def test_an_ordinary_command_is_admitted_silently(tmp_path: Path, command: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == ""
    assert r.stderr == ""


@pytest.mark.parametrize(("command", "path"), MEMO_WRITES, ids=[c for c, _ in MEMO_WRITES])
def test_a_shell_write_of_the_memo_is_blocked_with_the_remedy(tmp_path: Path, command: str, path: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 2, r.stderr
    claim = r.stderr.partition("; in `")[0]
    assert "BLOCKED" in claim and f" writes the memo `{path}` " in claim, r.stderr
    assert "through the Edit tool after a Read" in r.stderr and "memo-guard" in r.stderr
    assert r.stdout == ""


def test_a_redirect_standing_alone_before_a_command_is_named_as_its_own_stage(tmp_path: Path):
    r = run_hook(call("> .local/memo.md; echo done"), cwd=tmp_path)
    assert r.returncode == 2 and "BLOCKED — `> .local/memo.md` writes the memo" in r.stderr, r.stderr


@pytest.mark.parametrize("command", MEMO_READS)
def test_a_read_of_the_memo_and_a_write_of_another_file_are_admitted_silently(tmp_path: Path, command: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def refused_stamp(r: subprocess.CompletedProcess, what: str, stamp: str, target: str) -> bool:
    claim = r.stderr.partition("; in `")[0]
    named = f" writes the {what} `{stamp}` into `{target}`" in claim and "BLOCKED" in claim
    return r.returncode == 2 and named and "the printed value of `date -u` or of the record" in r.stderr


@pytest.mark.parametrize("target", STAMP_TARGETS, ids=["as written", "past /dev/"])
@pytest.mark.parametrize(("text", "stamp"), PLACEHOLDERS, ids=[t for t, _ in PLACEHOLDERS])
@pytest.mark.parametrize("writer", STAMP_WRITERS)
def test_a_placeholder_stamp_a_shell_writer_puts_in_a_file_is_blocked_with_the_remedy(
    tmp_path: Path, writer: str, text: str, stamp: str, target: str
):
    r = run_hook(call(writer.format(target=target, text=text)), cwd=tmp_path)
    assert refused_stamp(r, "placeholder stamp", stamp, target), r.stderr
    assert "through the Edit tool" not in r.stderr


@pytest.mark.parametrize("writer", STAMP_WRITERS)
def test_a_placeholder_on_its_way_into_the_memo_names_the_memos_edit_route_too(tmp_path: Path, writer: str):
    r = run_hook(call(writer.format(target=".local/memo.md", text="19:4xZ")), cwd=tmp_path)
    assert refused_stamp(r, "placeholder stamp", "19:4x", ".local/memo.md"), r.stderr
    assert "through the Edit tool after a Read" in r.stderr


@pytest.mark.parametrize("text", PASTED)
@pytest.mark.parametrize("writer", STAMP_WRITERS)
def test_a_stamp_pasted_from_the_clock_is_admitted_in_every_shell_writer(tmp_path: Path, writer: str, text: str):
    r = run_hook(call(writer.format(target=".tmp/notes.md", text=text)), cwd=tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


@pytest.mark.parametrize("command", STAMP_UNWRITTEN)
def test_a_placeholder_an_interpreter_or_git_reads_or_no_file_holds_is_admitted_silently(tmp_path: Path, command: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


@pytest.mark.parametrize("target", CASE_FILES)
def test_a_placeholder_written_into_a_test_module_or_a_hook_is_admitted(tmp_path: Path, target: str):
    r = run_hook(call(f"cat >> {target} <<'EOF'\n{CASE_TEXT}\nEOF"), cwd=tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


@pytest.mark.parametrize("target", NO_CASE_FILES)
def test_a_placeholder_written_into_a_file_merely_under_tests_or_named_for_one_is_blocked(tmp_path: Path, target: str):
    r = run_hook(call(f"cat >> {target} <<'EOF'\n{CASE_TEXT}\nEOF"), cwd=tmp_path)
    assert refused_stamp(r, "placeholder stamp", "12:1x", target), r.stderr


@pytest.mark.parametrize(("command", "clock", "target"), APPROXIMATE_CLOCKS, ids=[c for c, _, _ in APPROXIMATE_CLOCKS])
def test_an_approximate_clock_written_into_the_memo_or_the_coordination_table_is_blocked(
    tmp_path: Path, command: str, clock: str, target: str
):
    r = run_hook(call(command), cwd=tmp_path)
    assert refused_stamp(r, "approximate clock", clock, target), r.stderr
    assert ("through the Edit tool after a Read" in r.stderr) == target.endswith("memo.md"), r.stderr


@pytest.mark.parametrize("command", APPROXIMATE_ELSEWHERE)
def test_an_approximate_clock_elsewhere_and_a_pasted_one_in_the_table_are_admitted(tmp_path: Path, command: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


@pytest.mark.parametrize(("name", "exempt"), SPECIMEN_TARGETS, ids=[n for n, _ in SPECIMEN_TARGETS])
@pytest.mark.parametrize(("text", "stamp"), STAMP_SPECIMENS, ids=[t for t, _ in STAMP_SPECIMENS])
def test_memo_guard_and_bash_guard_read_a_stamp_alike(tmp_path: Path, text: str, stamp: str | None, name: str, exempt: bool):
    target = tmp_path / name
    stamp = None if exempt else stamp
    edit = subprocess.run(
        ["bash", str(MEMO_HOOK), "pre-write"],
        input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(target), "new_string": text}}),
        capture_output=True,
        text=True,
        env={**os.environ, "TMPDIR": str(tmp_path)},
    )
    shell = run_hook(call(f"cat >> {target} <<'EOF'\n{text}\nEOF"), cwd=tmp_path)
    by_edit = re.search(r"'([^']*)' is a placeholder stamp", edit.stderr)
    by_shell = re.search(r" writes the placeholder stamp `([^`]*)` into ", shell.stderr)
    assert (by_edit and by_edit[1], by_shell and by_shell[1]) == (stamp, stamp), (edit.stderr, shell.stderr)
    assert (edit.returncode, shell.returncode) == ((2, 2) if stamp else (0, 0))


@pytest.mark.parametrize("payload", ["", "not json at all", "{", "[]", '{"tool_input": "x"}'])
def test_stdin_that_is_not_the_call_admits_with_a_note(tmp_path: Path, payload: str):
    r = run_hook(payload, cwd=tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""
    assert "bash-guard: NOTE" in r.stderr
    assert "unjudged" in r.stderr


@pytest.mark.parametrize("command", CONSUMERS_SILENCED)
def test_a_consumers_stage_sent_to_dev_null_is_blocked_with_the_remedy(tmp_path: Path, command: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 2, r.stderr
    assert "BLOCKED" in r.stderr and "names consumers.sh under no reader the guard knows" in r.stderr, r.stderr
    assert "send it to a file" in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize("command", CONSUMERS_ADMITTED)
def test_a_command_outside_the_consumers_family_is_admitted_silently(tmp_path: Path, command: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stderr == "" and r.stdout == ""


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


@pytest.mark.parametrize(
    ("first_line", "budget", "error"),
    [
        ('raise RuntimeError("probe")', 5, "RuntimeError: probe"),
        ("signal.pause()", 1, "TimeoutError: the judging ran past 1 seconds"),
    ],
    ids=["an error", "an overrun"],
)
def test_a_judging_that_fails_refuses_a_dispatched_agent_and_admits_the_main_loop_with_a_note(
    tmp_path: Path, first_line: str, budget: int, error: str
):
    probed = HOOK.read_text().replace("def judge(words):\n", f"def judge(words):\n    {first_line}\n", 1)
    probed = probed.replace("BUDGET = 5 ", f"BUDGET = {budget} ", 1)
    assert probed.count(f"    {first_line}\n") == 1 and f"BUDGET = {budget} " in probed
    hook = tmp_path / "bash-guard.sh"
    hook.write_text(probed)
    r = run_hook(agent_call("git status", WORKTREE, agent_id="a1"), cwd=tmp_path, env=AGENT_ENV, hook=hook)
    assert r.returncode == 2 and f"BLOCKED — the hook could not judge the command ({error})" in r.stderr, r.stderr
    assert "a dispatched agent's command it cannot judge is refused; in `git status`." in r.stderr
    r = run_hook(agent_call("git status", WORKTREE), cwd=tmp_path, env=AGENT_ENV, hook=hook)
    assert r.returncode == 0 and "NOTE — the hook failed on its own (rc 1); the command runs unjudged." in r.stderr, r.stderr


def state_repo(tmp_path: Path) -> tuple[dict, Path]:
    """A checkout of its own and its stamp's path: the payload's cwd is the repo, so the stamp lands in its git dir."""
    repo = (tmp_path / "repo").resolve()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return {"tool_name": "Bash", "tool_input": {"command": ""}, "cwd": str(repo)}, git_dir(repo) / STAMP_NAME


# On the wall clock a stamp ages while its case queues behind `run_hook`'s lock, so the age the hook prints and judges
# is the queue's.
# The fraction is what shows a whole-second truncation of the clock or the stamp.
FROZEN_NOW = 1_800_000_000.5


@pytest.fixture
def frozen_env(tmp_path: Path) -> dict:
    shim = tmp_path / "frozen-clock"
    shim.mkdir()
    (shim / "sitecustomize.py").write_text(f"import time\n\ntime.time = lambda: {FROZEN_NOW!r}\n")
    return {**os.environ, "PYTHONPATH": str(shim)}


def stamped(payload: dict, stamp: Path, age: float) -> dict:
    stamp.write_text(repr(FROZEN_NOW - age))
    return payload


STATE_CHANGERS = ["git commit -m x", "git cherry-pick abc1234"]


@pytest.mark.parametrize("age", [0.4, 2.9])
@pytest.mark.parametrize("command", STATE_CHANGERS)
def test_a_state_changing_git_command_within_the_gap_of_another_is_refused(
    tmp_path: Path, frozen_env: dict, command: str, age: float
):
    payload, stamp = state_repo(tmp_path)
    payload = stamped(payload, stamp, age)
    before = stamp.read_text()
    payload["tool_input"]["command"] = command
    r = run_hook(payload, cwd=tmp_path, env=frozen_env)
    assert r.returncode == 2, r.stderr
    assert (
        f"BLOCKED — `{command}`: a state-changing git command started {age} s ago in this checkout and each runs alone — "
        "if that one has already returned, re-send this one after the gap"
    ) in r.stderr
    assert stamp.read_text() == before and r.stdout == ""


@pytest.mark.parametrize("age", [3.0, 5.0])
@pytest.mark.parametrize("command", STATE_CHANGERS)
def test_a_state_changing_git_command_past_the_gap_is_admitted_and_restamps(
    tmp_path: Path, frozen_env: dict, command: str, age: float
):
    payload, stamp = state_repo(tmp_path)
    payload = stamped(payload, stamp, age)
    payload["tool_input"]["command"] = command
    r = run_hook(payload, cwd=tmp_path, env=frozen_env)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    assert float(stamp.read_text()) == FROZEN_NOW


def test_a_git_read_within_the_gap_is_admitted_and_leaves_the_stamp(tmp_path: Path, frozen_env: dict):
    payload, stamp = state_repo(tmp_path)
    payload = stamped(payload, stamp, 0.4)
    before = stamp.read_text()
    payload["tool_input"]["command"] = "git status"
    r = run_hook(payload, cwd=tmp_path, env=frozen_env)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    assert stamp.read_text() == before


def test_a_state_changing_git_command_with_no_stamp_is_admitted_and_stamps(tmp_path: Path, frozen_env: dict):
    payload, stamp = state_repo(tmp_path)
    payload["tool_input"]["command"] = "git add . && git commit -m x"
    r = run_hook(payload, cwd=tmp_path, env=frozen_env)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
    assert float(stamp.read_text()) == FROZEN_NOW


def test_the_stamp_is_not_in_the_tree_an_admitted_commit_commits(tmp_path: Path):
    payload, stamp = state_repo(tmp_path)
    repo = Path(payload["cwd"])
    (repo / "a.txt").write_text("a\n")
    payload["tool_input"]["command"] = "git add . && git commit -q -m first"
    r = run_hook(payload, cwd=tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "") and stamp.is_file()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "commit.gpgsign", "GIT_CONFIG_VALUE_0": "false"})
    subprocess.run(["bash", "-c", payload["tool_input"]["command"]], cwd=repo, env=env, check=True)
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, check=True)
    assert status.stdout == "" and not (repo / ".gitignore").exists()
    shown = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, text=True, check=True).stdout
    assert shown == "a.txt\n"


def test_hook_is_executable():
    assert HOOK.stat().st_mode & 0o111, "the hook must be executable -- settings.json invokes it directly"


def test_hook_is_wired_as_a_pretooluse_bash_hook():
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    commands = [
        hook["command"] for entry in settings["hooks"]["PreToolUse"] if entry["matcher"] == "Bash" for hook in entry["hooks"]
    ]
    assert any("bash-guard.sh" in c for c in commands), "the hook is inert unless settings.json wires it"


def agent_call(command: str, cwd: str, **extra: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": cwd, "session_id": SESSION, **extra}


def _named(stderr: str) -> str:
    return stderr.partition("; in `")[0].partition("`")[2].partition("`")[0]


@pytest.mark.parametrize(("command", "spelling"), AGENT_WRITES, ids=[c for c, _ in AGENT_WRITES])
def test_a_dispatched_agents_push_or_github_write_is_blocked_with_the_remedy(tmp_path: Path, command: str, spelling: str):
    r = run_hook(agent_call(command, WORKTREE, agent_id="a1", agent_type="general-purpose"), cwd=tmp_path, env=AGENT_ENV)
    assert r.returncode == 2, r.stderr
    assert "BLOCKED" in r.stderr and _named(r.stderr) == spelling, r.stderr
    assert "a dispatched agent reports and stops" in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize(("command", "where", "spelling"), AGENT_IN_MAIN, ids=[f"{c} @ {w}" for c, w, _ in AGENT_IN_MAIN])
def test_a_dispatched_agents_git_that_moves_the_main_checkout_is_blocked_with_the_remedy(
    tmp_path: Path, command: str, where: str, spelling: str
):
    r = run_hook(agent_call(command, where, agent_id="a1"), cwd=tmp_path, env=AGENT_ENV)
    assert r.returncode == 2, r.stderr
    assert "BLOCKED" in r.stderr and _named(r.stderr) == spelling and "in the main checkout" in r.stderr, r.stderr
    assert "the main checkout is the coordinator's" in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize(
    ("command", "where", "spelling"), AGENT_BRANCH_DELETES, ids=[f"{c} @ {w}" for c, w, _ in AGENT_BRANCH_DELETES]
)
def test_a_dispatched_agents_branch_delete_is_blocked_wherever_it_runs(tmp_path: Path, command: str, where: str, spelling: str):
    r = run_hook(agent_call(command, where, agent_id="a1"), cwd=tmp_path, env=AGENT_ENV)
    assert r.returncode == 2, r.stderr
    assert "BLOCKED" in r.stderr and _named(r.stderr) == spelling and "deletes a branch" in r.stderr, r.stderr
    assert "A dispatched agent creates the branches it needs and reports them." in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize(
    ("command", "where", "spelling", "claim"), AGENT_REF_WRITES, ids=[f"{c} @ {w}" for c, w, _, _ in AGENT_REF_WRITES]
)
def test_a_dispatched_agents_ref_rename_force_or_delete_or_worktree_move_is_blocked_wherever_it_runs(
    tmp_path: Path, command: str, where: str, spelling: str, claim: str
):
    r = run_hook(agent_call(command, where, agent_id="a1"), cwd=tmp_path, env=AGENT_ENV)
    assert r.returncode == 2, r.stderr
    assert "BLOCKED" in r.stderr and _named(r.stderr) == spelling and f"` {claim} from a dispatched agent" in r.stderr, r.stderr
    assert "A dispatched agent creates the branches it needs and reports them." in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize(
    ("command", "where", "path"), AGENT_WORKTREE_REMOVES, ids=[f"{c} @ {w}" for c, w, _ in AGENT_WORKTREE_REMOVES]
)
def test_a_dispatched_agents_worktree_remove_outside_its_scratch_is_blocked_wherever_it_runs(
    tmp_path: Path, command: str, where: str, path: str
):
    r = run_hook(agent_call(command, where, agent_id="a1"), cwd=tmp_path, env=AGENT_ENV)
    assert r.returncode == 2, r.stderr
    assert "BLOCKED" in r.stderr and f"removes the worktree `{path}` from a dispatched agent" in r.stderr, r.stderr
    assert "a worktree, and another session's directory, are that session's" in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize(("command", "where"), AGENT_ADMITTED, ids=[f"{c} @ {w}" for c, w in AGENT_ADMITTED])
def test_a_dispatched_agents_read_and_worktree_git_are_admitted_silently(tmp_path: Path, command: str, where: str):
    r = run_hook(agent_call(command, where, agent_id="a1"), cwd=tmp_path, env=AGENT_ENV)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


@pytest.mark.parametrize(
    ("session", "env"),
    [
        (None, AGENT_ENV),
        ("", AGENT_ENV),
        (OTHER_SESSION, AGENT_ENV),
        (SESSION, {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_TMPDIR"}),
    ],
    ids=["no session_id", "an empty session_id", "another session", "no CLAUDE_CODE_TMPDIR"],
)
def test_a_scratchpad_removal_is_the_payload_sessions_under_the_hooks_temp_root(tmp_path: Path, session: str | None, env: dict):
    payload = agent_call(f"git worktree remove --force {SCRATCHPAD}/wt", WORKTREE, agent_id="a1")
    del payload["session_id"]
    if session is not None:
        payload["session_id"] = session
    r = run_hook(payload, cwd=tmp_path, env=env)
    assert r.returncode == 2 and f"removes the worktree `{SCRATCHPAD}/wt`" in r.stderr, r.stderr


@pytest.fixture(scope="module")
def repository(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """A repository whose worktrees exist on disk, holding the copy of the hook the calls below run."""
    base = tmp_path_factory.mktemp("repository").resolve()
    main, root = base / "main", base / "root"
    paths = {"main": main, "root": root, "wt": main / ".claude/worktrees/agent-y", "other": base / "other"}
    paths |= {"scratch": paths["wt"] / ".tmp/reads/pre-review-abc1234", "session_wt": root / PROJECT / "wt-b"}
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid"}
    env |= {"GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], env=env, input="", capture_output=True, text=True, check=True).stdout.strip()

    git("init", "-q", str(main))
    git("init", "-q", str(paths["other"]))
    (main / ".claude/hooks").mkdir(parents=True)
    (main / ".claude/hooks/bash-guard.sh").write_bytes(HOOK.read_bytes())
    commit = git("-C", str(main), "commit-tree", "--no-gpg-sign", "-m", "base", git("-C", str(main), "mktree"))
    for name in ("wt", "scratch", "session_wt"):
        git("-C", str(main), "worktree", "add", "-q", "--no-checkout", "--detach", str(paths[name]), commit)
    return {k: str(v) for k, v in paths.items()}


# (command, the payload's cwd) in `repository` -- admitted from a dispatched agent
SCRATCH_IN_A_WORKTREE = [
    ("git -C {wt} worktree remove --force {scratch}", "{wt}"),
    ("git -C {main} worktree remove --force {scratch}", "{main}"),
    ("git worktree remove --force .tmp/reads/pre-review-abc1234", "{wt}"),
    ("git worktree remove {session_wt}/.tmp/reads/x", "{wt}"),
    ("git worktree remove {main}/.tmp/reads/x/wt", "{wt}"),
]

# (command, the payload's cwd, the path the message must name) in `repository` -- refused from a dispatched agent
NO_SCRATCH_IN_A_WORKTREE = [
    ("git -C {main} worktree remove --force {wt}", "{main}", "{wt}"),
    ("git worktree remove {session_wt}", "{wt}", "{session_wt}"),
    ("git worktree remove {wt}/.tmp", "{wt}", "{wt}/.tmp"),
    ("git worktree remove {other}/.tmp/x", "{wt}", "{other}/.tmp/x"),
]


def repository_call(repository: dict[str, str], tmp_path: Path, command: str, where: str) -> subprocess.CompletedProcess:
    payload = agent_call(command.format(**repository), where.format(**repository), agent_id="a1")
    env = {**os.environ, "CLAUDE_CODE_TMPDIR": repository["root"]}
    for top in ("main", "wt"):  # the checkouts the module's worktree removes stamp
        (git_dir(repository[top]) / STAMP_NAME).unlink(missing_ok=True)
    return run_hook(payload, cwd=tmp_path, env=env, hook=Path(repository["main"]) / ".claude/hooks/bash-guard.sh")


@pytest.mark.parametrize(("command", "where"), SCRATCH_IN_A_WORKTREE, ids=[f"{c} @ {w}" for c, w in SCRATCH_IN_A_WORKTREE])
def test_a_scratch_tree_under_any_worktrees_tmp_is_admitted(repository: dict[str, str], tmp_path: Path, command: str, where: str):
    r = repository_call(repository, tmp_path, command, where)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


@pytest.mark.parametrize(
    ("command", "where", "path"), NO_SCRATCH_IN_A_WORKTREE, ids=[f"{c} @ {w}" for c, w, _ in NO_SCRATCH_IN_A_WORKTREE]
)
def test_a_worktree_or_a_tmp_no_worktree_of_this_repository_holds_is_refused(
    repository: dict[str, str], tmp_path: Path, command: str, where: str, path: str
):
    r = repository_call(repository, tmp_path, command, where)
    assert r.returncode == 2 and f"removes the worktree `{path.format(**repository)}`" in r.stderr, r.stderr


MAIN_LOOP = (
    [(c, WORKTREE) for c, _ in AGENT_WRITES]
    + [(c, w) for c, w, _ in AGENT_IN_MAIN]
    + [(c, w) for c, w, _ in AGENT_BRANCH_DELETES + AGENT_WORKTREE_REMOVES]
    + [(c, w) for c, w, _, _ in AGENT_REF_WRITES]
)


@pytest.mark.parametrize(("command", "where"), MAIN_LOOP, ids=[f"{c} @ {w}" for c, w in MAIN_LOOP])
@pytest.mark.parametrize("extra", [{}, {"agent_type": "reviewer"}], ids=["bare", "agent_type alone"])
def test_the_main_loop_runs_what_a_dispatched_agent_may_not(tmp_path: Path, command: str, where: str, extra: dict):
    r = run_hook(agent_call(command, where, **extra), cwd=tmp_path, env=AGENT_ENV)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


# (command, the stage the message must name) -- a grep handed files in a pipeline naming infra
HANDED_GREPS = [
    ("git ls-files 'infra/ansible/**/*.j2' | xargs grep -l foo", "xargs grep -l foo"),
    ("find infra/ansible -name '*.j2' -exec grep -l foo {} +", "find infra/ansible -name '*.j2' -exec grep -l foo '{}' +"),
    ("git ls-files infra | xargs grep -l key", "xargs grep -l key"),
    ("git ls-files cli | xargs grep -rlekey infra", "xargs grep -rlekey infra"),
    ("git ls-files cli | xargs grep -rle key infra", "xargs grep -rle key infra"),
    ("git ls-files cli | xargs grep -l -e key infra/ansible/x.yml", "xargs grep -l -e key infra/ansible/x.yml"),
]
HANDED_GREPS_ADMITTED = [
    "git ls-files 'cli/**/*.py' | xargs grep -l foo",
    "git ls-files cli | xargs grep -rle infra",
    "git ls-files 'infra/**/*.bak' | xargs rm",
    "git ls-files cli | xargs grep -l infra",
    "git ls-files cli | xargs grep -l -e infra",
    "git ls-files cli | xargs grep -l --regexp=infra",
    "find cli -name '*.py' -exec grep -l infra {} +",
]


@pytest.mark.parametrize(("command", "stage"), HANDED_GREPS, ids=[c for c, _ in HANDED_GREPS])
def test_a_grep_handed_files_in_a_pipeline_naming_infra_is_blocked_with_the_remedy(tmp_path: Path, command: str, stage: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 2, r.stderr
    assert f"BLOCKED — `{stage}` greps the files it is handed in a pipeline naming infra" in r.stderr, r.stderr
    assert "`vault_var` through command substitution" in r.stderr and r.stdout == ""


@pytest.mark.parametrize("command", HANDED_GREPS_ADMITTED)
def test_a_grep_handed_files_outside_infra_or_another_program_over_infra_is_admitted(tmp_path: Path, command: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


def call_from(command: str, sub: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(REPO / sub)}


@pytest.mark.parametrize(("command", "sub"), UNSCOPED_GREPS, ids=[f"{c} @ {s}" for c, s in UNSCOPED_GREPS])
def test_a_git_grep_that_selects_a_vaulted_file_is_blocked_with_the_remedy(tmp_path: Path, command: str, sub: str):
    r = run_hook(call_from(command, sub), cwd=tmp_path)
    assert r.returncode == 2, r.stderr
    assert "BLOCKED" in r.stderr and "`vault_var` through command substitution" in r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize(
    ("command", "remedy"),
    [
        ("git grep -n foo HEAD:infra", "search a commit, or the index"),
        ("git grep --no-inde -l foo -- docs", "drop `--no-index` or `--untracked`"),
        ("git grep -n foo -- ':(nonsense)infra'", "spell it as git ls-files accepts it"),
        ("git grep -n foo -- infra", "name directories or files outside the vaulted set"),
    ],
)
def test_a_refused_git_greps_remedy_names_its_own_way_through(tmp_path: Path, command: str, remedy: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 2 and remedy in r.stderr, r.stderr


@pytest.mark.parametrize(("command", "sub"), SCOPED_GREPS, ids=[f"{c} @ {s}" for c, s in SCOPED_GREPS])
def test_a_git_grep_that_selects_no_vaulted_file_is_admitted_silently(tmp_path: Path, command: str, sub: str):
    r = run_hook(call_from(command, sub), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stderr == "" and r.stdout == ""


SHELLS_WITH_C = [
    "ash",
    "csh",
    "dash",
    "elvish",
    "fish",
    "ksh",
    "ksh93",
    "mksh",
    "nu",
    "posh",
    "pwsh",
    "rbash",
    "tcsh",
    "xonsh",
    "yash",
    "zsh",
]

# (command, the alias the remedy must name) -- a fleet host of docs/reference/fleet.md reached past host-run.sh
FLEET_REACHED = [
    ("ssh red uptime", "red"),
    ("ssh -o BatchMode=yes red 'sudo docker ps'", "red"),
    ("ssh zcrypto", "zcrypto"),
    ("ssh deploy@nas df -h", "nas"),
    ("ssh -l deploy -p 22 -i .tmp/key db1 hostname", "db1"),
    ("ssh -tt mon", "mon"),
    ("ssh -oBatchMode=yes hc true", "hc"),
    ("ssh -- access uptime", "access"),
    ("ssh ssh://deploy@db2:22 uptime", "db2"),
    ("ssh RED uptime", "red"),
    ("ssh zcrypto-red uptime", "red"),
    ("ssh zcrypto-ops.tailnet.example uptime", "hp"),
    ("ssh hp -v uptime", "hp"),
    ("ssh -o HostName=zcrypto-red example.org uptime", "red"),
    ("scp notes.txt nas:/tmp/", "nas"),
    ("scp deploy@db3:/etc/hostname .", "db3"),
    ("scp -r -P 22 dir hp:", "hp"),
    ("scp scp://red//tmp/x .", "red"),
    ("sftp nas", "nas"),
    ("sftp deploy@nas:/volume1", "nas"),
    ("sftp -b batch.txt sftp://red", "red"),
    ("rsync -a -e ssh dir/ red:/tmp/dir/", "red"),
    ("rsync -av --rsh=ssh dir/ deploy@nas:/x", "nas"),
    ("rsync -avze 'ssh -p 22' dir red:/x", "red"),
    ("rsync -a --partial dir nas:/x", "nas"),  # rsync's remote shell is ssh unless -e names another
    ("rsync -a --chown zcrypto:zcrypto red:/x .", "red"),  # an option's value is no operand
    ("rsync -a nas::backup/x .", "nas"),
    ("rsync -e 'ssh -o HostName=nas' dir example.org:/x", "nas"),
    # a wrapper, a path, a quote, a shell string, a pipe, a chain, a substitution
    ("sudo ssh red uptime", "red"),
    ("sudo -u deploy ssh red uptime", "red"),
    ("env FOO=1 ssh red uptime", "red"),
    ("timeout 10 ssh red uptime", "red"),
    ("nohup ssh red uptime &", "red"),
    ("/usr/bin/ssh red uptime", "red"),
    # a path where a runner takes its command, past the runner's options, their values, assignments and a duration
    ("sudo /usr/bin/ssh red uptime", "red"),
    ("sudo -u deploy /usr/bin/ssh red uptime", "red"),
    ("timeout 10 /usr/bin/ssh red uptime", "red"),
    ("env -i FOO=1 /usr/bin/ssh red uptime", "red"),
    ("nohup /usr/bin/scp f nas:/tmp/ &", "nas"),
    ("echo uptime | xargs -n 1 /usr/bin/ssh red", "red"),
    ("\\ssh red uptime", "red"),
    ("bash -c 'ssh red uptime'", "red"),
    ('sh -lc "ssh nas df"', "nas"),
    ("sudo bash -c 'cd /tmp && scp f nas:/x'", "nas"),
    ("eval 'ssh red uptime'", "red"),
    ("echo uptime | ssh red bash", "red"),
    ("cd /x && ssh red uptime", "red"),
    ("true; ssh red uptime", "red"),
    ("x=$(ssh red hostname)", "red"),
    ("echo `ssh nas hostname`", "nas"),
    ("infra/scripts/host-run.sh red <<EOF\n$(ssh nas hostname)\nEOF", "nas"),  # runs here, before the wrapper
    ("echo ssh red", "red"),  # a word is judged wherever it stands
    # a here-string's word, whatever its quoting or spacing, and every line after one
    ('jq . <<< "$(ssh red cat /etc/x.json)"', "red"),
    ('wc -l <<<"$(ssh nas ls /volume1)"', "nas"),
    ("cat <<< $(ssh red uptime)", "red"),
    ('cat 0<<< "`ssh nas hostname`"', "nas"),
    ("cat <<<`ssh nas hostname`", "nas"),
    ("cat <<< <(ssh red uptime)", "red"),
    ('x=$(cat <<< "$(ssh red uptime)")', "red"),
    ('grep -q ok <<< "$status"\nssh red uptime', "red"),
    ("read -r a <<< 'x'\nssh nas df", "nas"),
    ("cat <<< x\nscp f red:/tmp/", "red"),
    # a handler with the host spelled out
    ("echo uptime | xargs ssh red", "red"),
    ("parallel ssh nas cat ::: a b", "nas"),
    # beside a reader, past its operands, behind a git that is no read, or an `-O` that carries traffic to the host
    ("grep -q x f && ssh red uptime", "red"),
    ("grep -l x $(ssh red ls)", "red"),
    ("find . -exec grep -l ssh {} + -exec ssh red uptime \\;", "red"),
    ("git bisect run ssh red uptime", "red"),
    ("ssh -O forward -L 8080:localhost:80 red", "red"),
    ("ssh -O proxy red", "red"),
    ("ssh -O check -O forward red", "red"),
    # a command line env splits from a string: `-S` and `--split-string` in each spelling getopt takes, its words
    # after it appended, its `\_` a separator, env's own options inside it
    ("env -S 'ssh red uptime'", "red"),
    ("env -S'ssh red uptime'", "red"),
    ("env -iS 'ssh red uptime'", "red"),
    ("env --split-string='ssh red uptime'", "red"),
    ("env --split-string 'ssh red uptime'", "red"),
    ("env --split='ssh red uptime'", "red"),
    ("env -u HOME -C /tmp -S 'ssh nas' df", "nas"),
    ("env -S ssh red uptime", "red"),
    ("env -S 'ssh\\_red\\_uptime'", "red"),
    ("env -S '-i ssh red uptime'", "red"),
    ("sudo env -S 'scp f nas:/tmp/'", "nas"),
    # a `-c` string to any shell, and fish's `--command`
    *[(f"{sh} -c 'ssh red uptime'", "red") for sh in SHELLS_WITH_C],
    ("fish --command='ssh red uptime'", "red"),
    ("fish --command 'ssh red uptime'", "red"),
    # an rsync `-e` naming ssh behind a wrapper or a path
    ("rsync -e 'sudo ssh -o HostName=nas' f example.org:/x", "nas"),
    ("rsync --rsh='/usr/bin/env ssh -o HostName=nas' f example.org:/x", "nas"),
    # `-o HostName` in each spelling ssh's config parser reads: a leading `=` or space, a quote closing the keyword,
    # a quoted value
    ("ssh -o=HostName=zcrypto-red example.org", "red"),
    ("ssh -o '=HostName nas' example.org", "nas"),
    ("ssh -o 'Host\"Name\" nas' example.org", "nas"),
    ("ssh -o 'HostName \"red\"' example.org", "red"),
    ("rsync -e 'ssh -o=HostName=nas' f example.org:/x", "nas"),
]

# A host only run time knows.
FLEET_UNRESOLVED = [
    'ssh "$HOST" uptime',
    "ssh deploy@${H} uptime",
    "ssh $(cat .tmp/host) uptime",
    "ssh `cat .tmp/host` uptime",
    'ssh -o HostName="$H" example.org',
    "scp f $H:/tmp/",
    'scp "$SRC" .',
    "sftp $H",
    "rsync -a dir/ $DEST",
    'for h in red nas; do ssh "$h" uptime; done',
    "ssh red* uptime",
    "ssh {red,nas} uptime",
    "printf 'red\\n' | xargs -I{} ssh {} uptime",
    "echo red | xargs ssh",
    # a replace string a handler fills in at run time, in each spelling the handler takes, wherever the host carries it
    "echo red | xargs -I% ssh % uptime",
    "echo red | xargs -I HOST ssh HOST uptime",
    "printf 'red\\nnas\\n' | xargs -n1 -I@ ssh @ uptime",
    "echo red | xargs -0I% ssh % uptime",
    "echo red | xargs --replace=H ssh H uptime",
    "echo red | xargs --replace ssh {}.example uptime",
    "echo red | xargs -iH ssh H uptime",
    "echo red | xargs -J % ssh % uptime",  # BSD xargs' own replace option
    "echo red | xargs -I% ssh deploy@% uptime",
    "echo red | xargs -I% ssh zcrypto-% uptime",
    "echo ple | xargs -I e ssh example.org uptime",  # xargs replaces the string wherever it stands
    "echo red | xargs -I% ssh -o HostName=% example.org",
    "echo red | xargs -I H ssh -J H example.org",
    "echo red | xargs -I% ssh -o % example.org",
    "echo red | xargs -I% scp f %:/tmp/",
    "echo red | xargs -I% sftp %",
    "echo red | xargs -I% rsync -a f %:/tmp/",
    "echo red | xargs -I% sudo ssh % uptime",
    "echo red | xargs -I% sh -c 'ssh % uptime'",
    "find hosts -type f -exec ssh {} uptime \\;",
    "find hosts -type f -exec /usr/bin/ssh {} uptime \\;",
    "find hosts -type f -ok scp f {}:/tmp/ \\;",
    "parallel ssh ::: red nas",
    "parallel ssh :::: hosts.txt",
    "parallel ssh {} uptime ::: red",
    "parallel -I% ssh % uptime ::: red",
    "printf 'red\\n' | parallel ssh",
]

# (command, the ssh option the message must name) -- to a host outside the fleet
FLEET_HOPS = [
    ("ssh -o ProxyCommand='nc %h %p' example.org", "ProxyCommand"),
    ("ssh -oProxyCommand=none example.org", "ProxyCommand"),
    ('ssh -o "ProxyCommand nc example.net 22" example.org', "ProxyCommand"),
    ("ssh -o proxycommand=x example.org", "ProxyCommand"),
    ("ssh -o 'PROXYCOMMAND = x' example.org", "ProxyCommand"),
    ("ssh -o '\"ProxyCommand\" x' example.org", "ProxyCommand"),
    ("ssh -o LocalCommand=id example.org", "LocalCommand"),
    ("ssh -o PermitLocalCommand=yes example.org", "PermitLocalCommand"),
    ("ssh -o KnownHostsCommand=/bin/true example.org", "KnownHostsCommand"),
    # an option that loads or runs local code, by its keyword and by ssh's short option for it
    ("ssh -I /tmp/evil.so example.org", "PKCS11Provider"),
    ("ssh -I/tmp/evil.so example.org", "PKCS11Provider"),
    ("ssh -o PKCS11Provider=/tmp/evil.so example.org", "PKCS11Provider"),
    ("scp -o PKCS11Provider=/tmp/evil.so f example.org:", "PKCS11Provider"),
    ("ssh -o SecurityKeyProvider=/tmp/evil.so example.org", "SecurityKeyProvider"),
    ("ssh -X -o XAuthLocation=/tmp/evil example.org", "XAuthLocation"),
    ("ssh -o ProxyJump=deploy@jump.example:22 example.org", "ProxyJump"),
    ("ssh -J deploy@jump.example example.org", "ProxyJump"),
    ("ssh -Jjump.example:2222 example.org", "ProxyJump"),
    ("ssh -J a,b example.org", "ProxyJump"),
    ("ssh -J jump.example example.org", "ProxyJump"),
    ('ssh -vJ "$JUMP" example.org', "ProxyJump"),
    ("ssh example.org -o ProxyCommand=x", "ProxyCommand"),  # ssh reads options after its destination too
    ("sudo ssh -o ProxyCommand=x example.org", "ProxyCommand"),
    ("scp -o ProxyCommand=x f example.org:", "ProxyCommand"),
    ("scp -J deploy@jump.example f example.org:", "ProxyJump"),
    ("sftp -oProxyJump=deploy@jump.example example.org", "ProxyJump"),
    ("rsync -e 'ssh -o ProxyCommand=x' f example.org:/x", "ProxyCommand"),
    ("rsync --rsh='ssh -J deploy@jump.example' f example.org:/x", "ProxyJump"),
    ("bash -c \"ssh -o 'ProxyCommand x' example.org\"", "ProxyCommand"),
    ("env -S 'ssh -o ProxyCommand=x example.org'", "ProxyCommand"),
    ("fish -c 'ssh -J deploy@jump.example example.org'", "ProxyJump"),
    ("rsync -e 'sudo ssh -J deploy@jump.example' f example.org:/x", "ProxyJump"),
    ("rsync -e 'env ssh -o ProxyCommand=x' f example.org:/x", "ProxyCommand"),
    ("rsync --rsh='timeout 5 /usr/bin/ssh -o LocalCommand=id' f example.org:/x", "LocalCommand"),
    # each spelling ssh's config parser reads a keyword in: after one `=` that opens the value, after spaces and an `=`,
    # with a quote closing it mid-word
    ("ssh -o=ProxyCommand=x example.org", "ProxyCommand"),
    ("ssh '-o=ProxyCommand nc %h %p' example.org", "ProxyCommand"),
    ("ssh -o '= ProxyCommand x' example.org", "ProxyCommand"),
    ("ssh -o ' =ProxyCommand x' example.org", "ProxyCommand"),
    ("ssh -o 'Proxy\"Command\" x' example.org", "ProxyCommand"),
    ("ssh -o 'P\"roxyCommand\"=x' example.org", "ProxyCommand"),
    ("ssh -o=LocalCommand=id example.org", "LocalCommand"),
    ("ssh -o=ProxyJump=deploy@jump.example example.org", "ProxyJump"),
    ("ssh -o 'ProxyJump access,jump.example' example.org", "ProxyJump"),
    ("scp -o=ProxyCommand=x f example.org:", "ProxyCommand"),
    ("sftp '-o =ProxyCommand x' example.org", "ProxyCommand"),
    ("rsync -e 'ssh -o=ProxyCommand=x' f example.org:/x", "ProxyCommand"),
    # a keyword, or an rsync remote shell, only run time knows
    ('ssh -o "$OPT" example.org', "option"),
    ('ssh -o"${K}=x" example.org', "option"),
    ("ssh -o 'Proxy$X=y' example.org", "option"),
    ('rsync -e "$RSH" f example.org:/x', "command line"),
    ("rsync -e 'ssh $OPTS' f example.org:/x", "command line"),
    ("rsync -e 'sudo $X' f example.org:/x", "command line"),
]

FLEET_ADMITTED = [
    # the prescribed route: its block is its own judge's
    "infra/scripts/host-run.sh red <<'EOF'\nssh nas uptime\nscp /etc/hostname db1:/tmp/\nEOF",
    "infra/scripts/host-run.sh --timeout 30 nas <<'EOF'\nsudo docker ps --format '{{.Names}}'\nEOF",
    "infra/scripts/host-run.sh --judge red < .tmp/block.sh",
    # git over its ssh remotes
    "git push origin HEAD",
    "git fetch origin develop",
    "git ls-remote git@github.com:o/r.git",
    "GIT_SSH_COMMAND='ssh -o BatchMode=yes' git fetch origin",
    # ssh as data: a quoted pattern, an echo, a message, a heredoc written to a file, a comment, an assignment
    "grep -rn 'ssh red' docs/",
    "git grep -n 'ssh -o ProxyCommand' -- docs/reference",
    'echo "ssh red uptime"',
    'git commit -m "docs: ssh red is refused; scp nas:/x too"',
    "cat <<'EOF' > .tmp/notes.md\nssh red uptime\nrsync -a d nas:/x\nEOF",
    "ls # ssh red",
    "SSH=/usr/bin/ssh make check",
    "cat <<< 'ssh red uptime'",
    'wc -c <<< "ssh nas df"',
    "cat <<< x; cat <<'EOF'\nssh red uptime\nEOF",
    # a handler running a command on a host outside the fleet, what it reads filling the remote command alone
    "echo a | xargs -I% ssh example.org cat %",
    "echo uptime | xargs ssh example.org",
    "find . -name '*.log' -exec ssh example.org cat {} \\;",
    "parallel ssh example.org cat ::: a b",
    # what connects nowhere, or to no fleet host
    "ssh -V",
    "ssh -G red",
    "ssh -G -p 22 zcrypto",
    "ssh -Q cipher",
    "ssh -Q key red",
    "ssh -O check red",
    "ssh -O exit red",
    "ssh -O stop nas",
    "ssh -T git@github.com",
    "ssh -o BatchMode=yes -o ConnectTimeout=5 example.org true",
    "ssh -J access example.org",
    "ssh -o ProxyJump=access example.org",
    "ssh -o 'ProxyJump none' example.org",
    "ssh nasa.example.org",
    "ssh -o HostName=example.net example.org",
    "scp f example.org:/tmp/",
    "scp ./red:x .",  # a slash before the colon: a local path
    "scp red.txt nas.txt /tmp/",
    "rsync -a dir/ /mnt/backup/",
    "rsync -a red/ nas/",
    "sftp example.org",
    "ssh-keygen -lf .tmp/key.pub",
    "ssh-add -l",
    "which ssh scp sftp rsync",
    "man ssh",
    "pgrep -a ssh",
    # a path to an ssh-family program, or a directory so named, as another program's operand, behind a runner too
    # (`/usr/bin/ssh red uptime` and `sudo /usr/bin/ssh red uptime` are calls)
    "find /etc/ssh -name '*.pub'",
    "[ -d /etc/ssh ] && echo present",
    "[ -x /usr/bin/sftp ] || echo missing",
    "ls -l /usr/bin/ssh /usr/bin/ssh-*",
    "sudo grep -rn PermitRootLogin /etc/ssh",
    "sudo find /etc/ssh -name '*.pub'",
    "cat ~/.ssh/config",
    # a string env or a shell runs, read as a command and admitted as one
    "env -S 'git status'",
    "env -u FOO -S 'ssh -V'",
    "env --split-string='grep -c ssh access.log'",
    "fish -c 'ssh example.org uptime'",
    "rsync -e 'sudo ssh' dir/ /mnt/backup/",
    # an option ssh's config parser reads as harmless, a value only run time knows beside a known keyword
    "ssh -o=BatchMode=yes example.org true",
    "ssh -o 'ProxyJump \"access\"' example.org",
    'ssh -o ConnectTimeout="$T" example.org true',
    'rsync -e "ssh -p $PORT" f example.org:/x',
    # an ssh-family word a reader takes as data: a grep's, an rg's, journalctl's, systemctl's or a git read's operand,
    # that reader the stage's program or what `xargs` or a find `-exec` runs, up to the `-exec`'s `+`
    "git grep -n ssh -- 'docs/reference/*.md'",
    "rg -n ssh -g '*.md'",
    "grep -rn ssh --include '*.yml' infra/ansible/roles/",
    "git log --oneline -S ssh -- '*.sh'",
    "git -C docs log --grep ssh -- '*.md'",
    "grep -l ssh *.md",
    "grep -c ssh access.log",
    'grep -c "ssh" access.log',
    "grep -e ssh -e scp nas.log",
    "grep -rn ssh -o ProxyCommand=x docs/",
    "egrep -l rsync red*.md",
    "journalctl -t ssh -g nas",
    "systemctl status ssh nas.mount",
    "git ls-files docs | xargs grep -ln ssh",
    "git ls-files -z docs | xargs -0 -n 20 rg -l ssh",
    "find docs -name '*.md' -exec grep -l ssh {} +",
    "find docs -name '*.md' -exec grep -l ssh {} \\;",
]

HOST_RUN_REMEDY = "infra/scripts/host-run.sh {} <<'EOF' … EOF"


@pytest.mark.parametrize(("command", "alias"), FLEET_REACHED, ids=[c for c, _ in FLEET_REACHED])
def test_a_fleet_host_reached_past_host_run_is_blocked_with_the_remedy(tmp_path: Path, command: str, alias: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 2, r.stderr
    claim = r.stderr.partition("; in `")[0]
    assert "BLOCKED" in claim and " reaches the fleet host `" in claim, r.stderr
    assert f"`{HOST_RUN_REMEDY.format(alias)}`" in r.stderr, r.stderr
    assert r.stdout == ""


@pytest.mark.parametrize(
    ("command", "transfer"),
    [("scp notes.txt nas:/tmp/", True), ("sftp deploy@nas", True), ("rsync -a d red:/x", True), ("ssh red uptime", False)],
)
def test_a_refused_file_transfer_says_the_wrapper_moves_no_file(tmp_path: Path, command: str, transfer: bool):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 2 and " reaches the fleet host `" in r.stderr, r.stderr
    said = "a file transfer has no route through that wrapper" in r.stderr and "`nas-file-transfer`" in r.stderr
    assert said == transfer, r.stderr


@pytest.mark.parametrize("command", FLEET_UNRESOLVED)
def test_an_ssh_family_host_the_guard_cannot_resolve_is_blocked_as_unresolvable(tmp_path: Path, command: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 2, r.stderr
    claim = r.stderr.partition("; in `")[0]
    assert "BLOCKED" in claim and "which the guard cannot resolve to a host in or out of the fleet" in claim, r.stderr
    assert f"`{HOST_RUN_REMEDY.format('<alias>')}`" in r.stderr, r.stderr


@pytest.mark.parametrize(("command", "option"), FLEET_HOPS, ids=[c for c, _ in FLEET_HOPS])
def test_an_ssh_option_that_hops_or_runs_a_local_command_is_blocked_to_any_host(tmp_path: Path, command: str, option: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 2, r.stderr
    claim = r.stderr.partition("; in `")[0]
    assert "BLOCKED" in claim and f": ssh's {option} " in claim, r.stderr
    assert "a jump host is a bare alias" in r.stderr and f"`{HOST_RUN_REMEDY.format('<alias>')}`" in r.stderr


@pytest.mark.parametrize("command", FLEET_ADMITTED)
def test_host_run_git_over_ssh_ssh_as_data_and_a_host_outside_the_fleet_are_admitted(tmp_path: Path, command: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


@pytest.mark.parametrize("command", ["ssh red uptime", "ssh -o ProxyCommand=x example.org"])
def test_a_dispatched_agent_is_held_to_the_fleet_family_as_the_main_loop_is(tmp_path: Path, command: str):
    r = run_hook(agent_call(command, str(REPO), agent_id="a1"), cwd=tmp_path, env=AGENT_ENV)
    assert r.returncode == 2 and "BLOCKED" in r.stderr and HOST_RUN_REMEDY.split()[0] in r.stderr, r.stderr


# A string a shell, eval or env -S runs whose quotes shlex cannot pair -- a quote inside a quoted `$( .. )` -- and
# whether it names an ssh-family program.
UNSPLIT_STRINGS = [
    ('bash -c \'ssh red uptime; echo "$(printf %s "\'"\'"\'")"\'', True),
    ('eval \'scp f nas:/x; echo "$(printf %s "\'"\'"\'")"\'', True),
    ('sh -c \'/usr/bin/rsync -a d nas:/x; echo "$(printf %s "\'"\'"\'")"\'', True),
    ('bash -c \'echo "$(printf %s "\'"\'"\'")"\'', False),
    ('bash -c \'ssh-keygen -l; echo "$(printf %s "\'"\'"\'")"\'', False),
]


@pytest.mark.parametrize(("command", "names_ssh"), UNSPLIT_STRINGS, ids=[c for c, _ in UNSPLIT_STRINGS])
def test_a_string_the_guard_cannot_split_is_refused_when_it_names_an_ssh_family_program(
    tmp_path: Path, command: str, names_ssh: bool
):
    r = run_hook(call(command), cwd=tmp_path)
    if names_ssh:
        assert r.returncode == 2 and "BLOCKED" in r.stderr and "cannot split into words" in r.stderr, r.stderr
    else:
        assert (r.returncode, r.stdout, r.stderr) == (0, "", "")


# (the table the call's checkout holds -- None for no checkout at all --, what the message says of it)
UNREAD_TABLES = [
    (None, "no checkout holds the call's directory"),
    ("", "could not be read"),
    ("# Fleet\n\nno host table here\n", "names no host"),
]


def unread_table_call(tmp_path: Path, table: str | None, command: str) -> subprocess.CompletedProcess:
    where = tmp_path / "checkout"
    if table is not None:
        subprocess.run(["git", "init", "-q", str(where)], check=True)
        if table:
            (where / "docs" / "reference").mkdir(parents=True)
            (where / "docs" / "reference" / "fleet.md").write_text(table)
    return run_hook(agent_call(command, str(where)), cwd=tmp_path)


@pytest.mark.parametrize("command", ["ssh -T git@github.com", "scp f example.org:/tmp/", "rsync -a d example.org:/x"])
@pytest.mark.parametrize(("table", "why"), UNREAD_TABLES, ids=[w for _, w in UNREAD_TABLES])
def test_a_fleet_table_the_calls_checkout_cannot_give_refuses_every_ssh_family_call_to_a_host(
    tmp_path: Path, table: str | None, why: str, command: str
):
    r = unread_table_call(tmp_path, table, command)
    assert r.returncode == 2, r.stderr
    claim = r.stderr.partition("; in `")[0]
    assert "BLOCKED" in claim and why in claim and "so the guard cannot tell a fleet host from another" in claim, r.stderr


@pytest.mark.parametrize("command", ["ssh -V", "ssh -G example.org", "rsync -a d/ e/"])
@pytest.mark.parametrize(("table", "why"), UNREAD_TABLES, ids=[w for _, w in UNREAD_TABLES])
def test_a_fleet_table_the_calls_checkout_cannot_give_admits_what_reaches_no_host(
    tmp_path: Path, table: str | None, why: str, command: str
):
    r = unread_table_call(tmp_path, table, command)
    assert (r.returncode, r.stdout, r.stderr) == (0, "", "")
