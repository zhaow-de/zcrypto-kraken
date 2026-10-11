# The bridgehead's Caddy apt mirror: debmirror on zaccess, served over public HTTPS, the edge nodes' Caddy source pointed at it, the interim of 2026-10-11 retired — implementation plan

> Every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The bridgehead mirrors the vendor's Caddy apt repository — its one suite, `amd64`, `main`, the whole history — with `debmirror` from a daily timer into `/var/lib/caddy-apt-mirror`, installs its own Caddy from that copy through a `file:` source, and serves the copy publicly at `https://apt.zaccess.zhaow.me`; `zcrypto-mon` and `zcrypto-hc` take their Caddy from that address, each refusing in its preview a mirror that does not answer; all three verify the vendor's signature with a vendored keyring and pin Debian's own `caddy` out; the interim of 2026-10-11 leaves every file that carries it (spec 00127).

**Architecture:** Seven tasks on `docs/00127-caddy-apt-mirror`, one pull request, then an attended rollout. The vendored key and the two shared values first, since both roles read them; then the access role's sync, `file:` source and install, with the interim's removal and refusal leaving the bridgehead; the bridgehead's public site; the edge and mon roles' mirror source, preflight and pin, with the interim leaving them; the pages, the skill, and last the carriers' sweep. The Rollout converges the bridgehead first, reads the site from the workstation, then converges the two edge nodes onto it.

**Tech Stack:** Ansible (ansible-core 2.21.4; the access, edge and mon roles; the Templar test substrate of `tests/test_infra_converge_guards.py` and `tests/role_render.py`), systemd units, Caddy's Caddyfile, `debmirror` 1:2.47+deb13u1 and `gpgv` from Debian 13 main, pytest, `infra/scripts/mutate-probe.sh` for guard verdicts.

**Spec:** `docs/specs/00127-caddy-apt-mirror-design.md`, D1 to D10, with "What changes in the repo", the invariants, `## Lost` and the measured basis; the spec is the one text of every decision this plan implements without restating it.

## Global Constraints

- Every line number this plan gives for existing code or text is a reading at `56a855371` (develop's `3d54c79fd` plus the branch's two carried commits); a task that edits a file reads the lines it cites again before its first edit, and every edit below is anchored on quoted text, never on a number.
- No executor step reaches a host, the NAS, a venue, Grafana or the vendor's repository: every such step is an operator step of the Rollout, attended. The vendor's key is written from the text this plan carries (Task 1), never fetched. `ansible-playbook` and `infra/ansible/scripts/converge.sh` are never run by an executor in any form — this workstation is the fleet host `zcrypto-ops`; a role's YAML is proven by the tests' walk and the commit gate's `ansible-lint`. No executor step writes under `/var/lib/`, `/etc/` or `/mnt/zhao-crypto/`; a scratch file goes under `.tmp/00127/` in the worktree.
- Every commit is green over its consumers, the files `infra/scripts/consumers.sh` prints for the task's changed files, run as each task's consumer step writes it; the full suite runs in CI alone. A task that adds or edits text `tests/test_internal_terms_not_operator_visible.py` walks — a role task name or message, a systemd `Description=`, a runbook page — runs that file too, and its allowlist is never widened.
- A guard is proven by `infra/scripts/mutate-probe.sh`, never a hand-rolled mutate-and-restore. The script refuses a dirty tree, so a task commits with the line `PROBE_VERDICT` in its message, runs its probes on the committed tree, each line below ending `mutate-probe: KILLED (control proven, tree restored byte-identically)`, then a message-only amend with the tree clean replaces `PROBE_VERDICT` with each probe's command and its verbatim verdict — the branch is unpushed and unread while the tasks run, so the amend rewrites nothing a reader holds. A probe's sed is addressed by a pattern the file holds once, or by line numbers read from the committed file as this plan writes it; a task whose file differs from this plan's text re-reads the numbers before the probe. The control is `'1,$d'` unless the probe passes on an emptied file, where the control is a mutation its test must fail (Task 4's two vendor-name probes).
- The commit gate, before every commit: the commit's files staged by path, its new and deleted files among them, then `uv run pre-commit run -a` until clean, its rewrites staged. One file kind per commit: the `.claude/` change rides a `claude(...)` commit carrying no other file (Task 6), and `zcrypto-refine-rules` is loaded before the edits to the runbook pages and the skill (Tasks 5 and 6).
- A commit message ends with the trailer `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>`, the placeholder replaced by the executing model's own name, followed by the executing session's `Claude-Session:` line where its harness supplies one; each commit fence below carries the trailer in that form.
- A code comment, task name, task message or docstring a task's edit falsifies is re-trued in that task's commit; a new one stays only if a reader would act differently without it.
- Never print a container's environment. A search over `infra/` is a `git grep` with the pathspecs `':!*vault*' ':!*.sops.*' ':!infra/ansible/files/*_ed25519'`, never `grep -r`; no vault file is read, printed, grepped or diffed.
- Every reviewer runs on Opus, the model passed explicitly.

## File structure

- `infra/ansible/files/caddy-archive-keyring.gpg` (new), `infra/ansible/files/README.md` (its row), `infra/ansible/group_vars/all/vars.yml` (`caddy_mirror_host`, `caddy_mirror_keyring`) — Task 1.
- `infra/ansible/roles/access/defaults/main.yml` (the upstream, the user, the directory, its served tree), `infra/ansible/roles/access/tasks/main.yml` (the sync, the `file:` source, the pin and the install in place of `:44-70`), `infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2` and `zaccess-caddy-mirror.timer.j2` (new) — Task 2.
- `infra/ansible/roles/access/templates/Caddyfile.j2` (the `apt.` site) — Task 3.
- `infra/ansible/roles/edge/tasks/caddy-source.yml` (new, by `git mv` of `caddy-source-absent.yml`), `infra/ansible/roles/edge/tasks/main.yml` (`:3-33`), `infra/ansible/roles/mon/tasks/main.yml` (`:2-6`, `:34-36`) — Task 4.
- `infra/runbooks/zaccess.md` (`:3`, `:21`, `:50`, `:99`, `:123`, and the `zaccess-caddy-mirror` section before `zaccess-bridgehead-dark`), `infra/runbooks/hc.md` (`:37`, `:292`, `:302`, `:332`), `infra/runbooks/mon.md` (`:100`, `:218`, `:224`, `:274`), `infra/runbooks/drills-telemetry.md` (`:656`), `docs/reference/fleet.md` (`:13`, `:25`, `:43`, a row before `:47`) — Task 5.
- `.claude/skills/zcrypto-bump-alloy/SKILL.md` (`:90`) — Task 6.
- Tests: `tests/test_infra_caddy_mirror.py` (new: Task 1, grown in Tasks 2, 3 and 4), `tests/test_infra_converge_guards.py` (the access role's three interim tests, `:2387-2430`, leave — Task 2), `tests/test_infra_edge_role.py` (`:26`, `:105-183` — Task 4), `tests/test_infra_mon_role.py` (`:385-391` — Task 4).

## Review Focus

- The bootstrap order on the bridgehead: debmirror and gpgv, the key, the user, the directory and its served tree, the units, the timer, the served tree's `Release` read, the first sync while the served tree holds no `Release`, the `file:` source over the served tree, the pin, the install — nothing reads the copy before it exists, and nothing in the chain fails a preview of the established bridgehead (the timer and the first sync skipped by `access_caddy_mirror_previewed`).
- The swap: debmirror syncs a hard-linked copy of the served tree, and systemd exchanges the copy with the served tree only after debmirror exits 0, since debmirror 2.47 moves a new index in when a pool file failed; the served tree changes by that exchange alone, so a failed sync leaves it as the last sync that passed.
- The vendor's repository is read by the sync alone: no role's `deb822_repository` names it, and the access role's defaults are the one file that does.
- The served copy is the vendor's signed files unchanged, verified on every node against the vendored keyring, and the site serves `/dists/*` and `/pool/*` alone, without a listing or mTLS, while the two mTLS sites keep theirs.
- The preflight: mon and hc read the mirror's `Release` in a preview too (`check_mode: false`), and in a converge that selects their role refuse before the key, the source, the pin or — on mon — Alloy's pin file moves; the refusal carries no modifier that would soften it, and names the runbook section that takes each answer. A `--tags alloy` converge selects no preflight, so the two Alloy-dark procedures and the bump skill read the mirror before one (Tasks 5 and 6).
- The pin: Debian's `caddy` at `-1` on all three, so apt's one candidate is the mirror's; the install stays followed from apt, never forced, never held.
- The interim leaves every carrier: the sweep in Task 7 reads no hit, and no runbook or skill sentence still orders a role-tagged converge first.

---

### Before Task 1: the branch holds develop's tip and the plan's premises hold

- [ ] **Step 1: The branch holds develop's tip**

```bash
git fetch origin develop && git merge-base --is-ancestor origin/develop HEAD; echo "rc $?"
```

Expected: `rc 0`. On `rc 1`, `git merge origin/develop` into the branch — never a rebase, the spec and plan commits having been read — and re-check.

- [ ] **Step 2: The interim's carriers are where the spec reads them**

```bash
git grep -n -e 'interim of 2026-10-11' -e 'caddy-source-absent' -e 'Caddy interim' -- infra .claude tests ':!*vault*' ':!*.sops.*' ':!infra/ansible/files/*_ed25519' | cut -d: -f1-2
```

Expected, 20 lines: `.claude/skills/zcrypto-bump-alloy/SKILL.md:90`, `infra/ansible/roles/access/tasks/main.yml:44`, `:62`, `infra/ansible/roles/edge/tasks/caddy-source-absent.yml:3`, `infra/ansible/roles/edge/tasks/main.yml:4`, `:20`, `infra/ansible/roles/mon/tasks/main.yml:36`, `infra/runbooks/drills-telemetry.md:656`, `infra/runbooks/hc.md:37`, `:292`, `:302`, `:332`, `infra/runbooks/mon.md:100`, `:218`, `:224`, `:274`, `infra/runbooks/zaccess.md:50`, `:99`, `tests/test_infra_edge_role.py:26`, `tests/test_infra_mon_role.py:385`. A line that moved is read at its new number; a carrier added since is retired by the task that owns its file.

---

### Task 1: The vendor's key, vendored, and the mirror's two shared values

**Files:**
- Create: `infra/ansible/files/caddy-archive-keyring.gpg`, `tests/test_infra_caddy_mirror.py`
- Modify: `infra/ansible/group_vars/all/vars.yml` (two values after the last line, `:9`), `infra/ansible/files/README.md` (a row before the `zaccess_ca.crt` row)

- [ ] **Step 1: Read** spec 00127 D3 and its measured basis's key lines; `infra/ansible/files/README.md`; `infra/ansible/group_vars/all/vars.yml`.
- [ ] **Step 2: Write the failing test**

```bash
cat > tests/test_infra_caddy_mirror.py <<'EOF'
"""The bridgehead's Caddy apt mirror and the Caddy sources that read it: what the access role syncs, serves and installs
from, and what every role pins Caddy's candidates to."""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra/ansible"
KEYRING = ANSIBLE / "files/caddy-archive-keyring.gpg"
KEYRING_SHA256 = "c17cd5298a0bab02fda439fff278d9a55df2120cf9dac790c6ce71930db90b37"


# --- the key ----------------------------------------------------------------------------------------------------------
def test_the_vendored_keyring_is_the_vendor_key_as_measured():
    assert hashlib.sha256(KEYRING.read_bytes()).hexdigest() == KEYRING_SHA256
EOF
```

- [ ] **Step 3: Run it and read the failure**

```bash
uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider
```

Expected: `1 failed`, a `FileNotFoundError` on the keyring.

- [ ] **Step 4: Write the key** — the vendor's `gpg.key` as the spec's measured basis fetched it (sha256 `783dfee0…`), then its dearmored bytes into the tree:

```bash
mkdir -p .tmp/00127 && cat > .tmp/00127/caddy-gpg.key <<'EOF'
-----BEGIN PGP PUBLIC KEY BLOCK-----

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
=wl92
-----END PGP PUBLIC KEY BLOCK-----
EOF
sha256sum .tmp/00127/caddy-gpg.key
python3 -I - .tmp/00127/caddy-gpg.key infra/ansible/files/caddy-archive-keyring.gpg <<'EOF'
import base64, sys
lines = open(sys.argv[1], encoding="ascii").read().splitlines()
body = lines[lines.index("-----BEGIN PGP PUBLIC KEY BLOCK-----") + 1 : lines.index("-----END PGP PUBLIC KEY BLOCK-----")]
open(sys.argv[2], "wb").write(base64.b64decode("".join(line for line in body[body.index("") + 1 :] if not line.startswith("="))))
EOF
sha256sum infra/ansible/files/caddy-archive-keyring.gpg
```

Expected: `783dfee04b19e851a928cd87b34710213ebbe7628f98d9f34595ab83be578c00  .tmp/00127/caddy-gpg.key`, then `c17cd5298a0bab02fda439fff278d9a55df2120cf9dac790c6ce71930db90b37  infra/ansible/files/caddy-archive-keyring.gpg`; a different first hash is a transcription fault, and the task stops there.

- [ ] **Step 5: The shared values and the inventory row**

```bash
cat >> infra/ansible/group_vars/all/vars.yml <<'EOF'

# The Caddy apt mirror on the bridgehead (spec 00127): its public host, and the path of the vendor key its Release is
# verified with, copied from infra/ansible/files/caddy-archive-keyring.gpg.
caddy_mirror_host: apt.zaccess.zhaow.me
caddy_mirror_keyring: /etc/apt/keyrings/caddy-archive-keyring.gpg
EOF
python3 -I - infra/ansible/files/README.md <<'EOF'
import sys
path = sys.argv[1]
text = open(path).read()
anchor = "| `zaccess_ca.crt`, `zaccess_ca.key.vault` |"
row = "| `caddy-archive-keyring.gpg` | none: the Caddy vendor's public signing key, dearmored | the Caddy apt mirror's `debmirror --keyring` and every Caddy source's `Signed-By`, at `/etc/apt/keyrings/` on zaccess, zcrypto-mon and zcrypto-hc |\n"
assert text.count(anchor) == 1
open(path, "w").write(text.replace(anchor, row + anchor))
EOF
```

- [ ] **Step 6: Run the test** — Step 3's command; Expected: `1 passed`.
- [ ] **Step 7: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh infra/ansible/group_vars/all/vars.yml infra/ansible/files/caddy-archive-keyring.gpg infra/ansible/files/README.md | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_infra_caddy_mirror.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 8: The commit gate**

```bash
git add infra/ansible/files/caddy-archive-keyring.gpg infra/ansible/files/README.md infra/ansible/group_vars/all/vars.yml tests/test_infra_caddy_mirror.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`; on a rewrite, stage it and run again.

- [ ] **Step 9: Commit**

```bash
git commit -F - <<'EOF'
feat(ansible): the Caddy vendor's signing key, vendored as a binary keyring, and the mirror's host and keyring path for every play

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 10: Prove the guard**

```bash
infra/scripts/mutate-probe.sh --file infra/ansible/files/caddy-archive-keyring.gpg --control '1,$d' --mutation '1s/^/X/' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_vendored_keyring_is_the_vendor_key_as_measured
```

Expected: `KILLED`; then the message-only amend.

- [ ] **Step 11: The tree is clean** — `git status --porcelain`; Expected: empty (`.tmp/` is ignored).

---

### Task 2: The bridgehead syncs the mirror, reads it from disk and installs Caddy from it; the interim leaves the access role

**Files:**
- Create: `infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2`, `infra/ansible/roles/access/templates/zaccess-caddy-mirror.timer.j2`
- Modify: `infra/ansible/roles/access/defaults/main.yml` (five values after `:14`), `infra/ansible/roles/access/tasks/main.yml` (`:44-70`, the interim's removal, read, refusal, the renamed install and the hold, become the chain below), `tests/test_infra_caddy_mirror.py` (rewritten whole), `tests/test_infra_converge_guards.py` (`:2387-2430`, the access role's three interim tests and their three name constants, leave: the new file holds the install and the hold)

**What this task decides, where the spec leaves it open:**
- The first sync is the systemd module's `state: started` on the oneshot service, gated on the preview fact and on the served tree's `Release` read — `systemctl start` waits for a oneshot to end, its `ExecStartPost` included, so the `file:` source after it reads the tree the exchange put in place, and the gate keeps every converge after a passing sync off the vendor; a first sync that failed leaves the served tree empty, and the next converge syncs again.
- The swap is the unit's own, with no script: `ExecStartPre` removes the last staging tree and hard-links a copy of the served one in its place, `ExecStart` is debmirror over the copy, and `ExecStartPost`, which systemd runs only after `ExecStart` exits 0, exchanges the two trees in one `mv -T --exchange` (coreutils 9.7 on Debian 13; without `-T`, `mv` reads the served tree as a target directory and refuses). debmirror 2.47 writes each index and pool file by unlinking and re-creating it (`http_get`, `system_redirect_io`, its meta-file move), so a write to the copy reaches no file of the served tree; its trace file under `project/`, which the site does not serve, is the one file it rewrites in place.
- The task names are the operator's handles and carry no internal term; the unit's `Description=` is walked by `tests/test_internal_terms_not_operator_visible.py`.

- [ ] **Step 1: Read** spec 00127 D1, D3, D4, D5's pin and D7; `infra/ansible/roles/access/tasks/main.yml:1-71`; `infra/ansible/roles/access/defaults/main.yml`; `infra/ansible/roles/access/templates/zaccess-probe.service.j2`; `tests/test_infra_converge_guards.py:2387-2431`.
- [ ] **Step 2: Write the failing tests**

```bash
cat > tests/test_infra_caddy_mirror.py <<'EOF'
"""The bridgehead's Caddy apt mirror and the Caddy sources that read it: what the access role syncs, serves and installs
from, and what every role pins Caddy's candidates to."""

from __future__ import annotations

import hashlib
import shlex
from pathlib import Path

import pytest
import yaml

from tests import role_render
from tests.test_infra_converge_guards import find_task, iter_tasks, load_tasks, set_facts, task_index, truthy, when_conditions

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra/ansible"
ACCESS = ANSIBLE / "roles/access"
ACCESS_TASKS = ACCESS / "tasks/main.yml"
KEYRING = ANSIBLE / "files/caddy-archive-keyring.gpg"
KEYRING_SHA256 = "c17cd5298a0bab02fda439fff278d9a55df2120cf9dac790c6ce71930db90b37"
ALL = yaml.safe_load((ANSIBLE / "group_vars/all/vars.yml").read_text())
MIRROR = {key: ALL[key] for key in ("caddy_mirror_host", "caddy_mirror_keyring")}
PIN = "Package: caddy\nPin: release o=Debian\nPin-Priority: -1\n"
SERVED, STAGING = "/var/lib/caddy-apt-mirror/served", "/var/lib/caddy-apt-mirror/staging"

DEBMIRROR = "debmirror and gpgv present — the mirror's tool and its signature check, both from Debian"
KEY = "the Caddy vendor key the mirror and apt verify its Release with"
USER = "the mirror's system user"
DIRECTORY = "the mirror's directory and its served tree, readable by the caddy user"
UNITS = "the mirror's service + timer"
PREVIEWED = "note a preview that runs before the mirror's units exist"
TIMER = "the mirror's timer enabled"
RELEASE = "read whether the mirror's served tree holds a Release"
FIRST_SYNC = "the mirror's first sync, before the Caddy source reads it from disk"
SOURCE = "the Caddy apt source — the bridgehead's own mirror, read from disk"
DEBIAN_PIN = "Debian's own caddy never a candidate — the mirror's is the one apt installs"
INSTALL = "caddy present — version FOLLOWED from apt, never forced (the Caddyfile validate is the guard)"


def _render(name: str) -> str:
    return role_render.render(ACCESS, name, {}, exclude=("access_pinned_leaves",), access_pinned_leaves=["a.pem"], **MIRROR)


def _unit(name: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in _render(name).splitlines():
        if line and not line.startswith(("#", "[")):
            key, _, value = line.partition("=")
            out.setdefault(key, []).append(value)
    return out


# --- the key ----------------------------------------------------------------------------------------------------------
def test_the_vendored_keyring_is_the_vendor_key_as_measured():
    assert hashlib.sha256(KEYRING.read_bytes()).hexdigest() == KEYRING_SHA256


@pytest.mark.parametrize(("path", "name"), [(ACCESS_TASKS, KEY)], ids=["access"])
def test_the_vendored_keyring_lands_where_the_caddy_source_reads_it(path, name):
    copy = find_task(load_tasks(path), name)["ansible.builtin.copy"]
    assert copy == {
        "src": "{{ playbook_dir }}/files/caddy-archive-keyring.gpg",
        "dest": "{{ caddy_mirror_keyring }}",
        "owner": "root",
        "group": "root",
        "mode": "0644",
    }


# --- the sync ---------------------------------------------------------------------------------------------------------
def test_the_sync_runs_debmirror_over_one_suite_amd64_and_main_checking_the_release_signature():
    unit = _unit("zaccess-caddy-mirror.service.j2")
    (debmirror,) = unit["ExecStart"]
    assert shlex.split(debmirror) == [
        "/usr/bin/debmirror",
        "--method=https",
        "--host=dl.cloudsmith.io",
        "--root=public/caddy/stable/deb/debian",
        "--dist=any-version",
        "--section=main",
        "--arch=amd64",
        "--nosource",
        "--check-gpg",
        "--keyring=/etc/apt/keyrings/caddy-archive-keyring.gpg",
        "--rsync-extra=none",
        "--diff=none",
        "--postcleanup",
        "--verbose",
        STAGING,
    ]
    assert {key: unit[key] for key in ("Type", "User", "Group", "UMask", "ProtectSystem", "ReadWritePaths")} == {
        "Type": ["oneshot"],
        "User": ["caddy-mirror"],
        "Group": ["caddy-mirror"],
        "UMask": ["0022"],
        "ProtectSystem": ["strict"],
        "ReadWritePaths": ["/var/lib/caddy-apt-mirror"],
    }


def test_a_sync_reaches_the_served_tree_only_after_debmirror_exits_0():
    unit = _unit("zaccess-caddy-mirror.service.j2")
    assert unit["ExecStartPre"] == [f"/usr/bin/rm -rf {STAGING}", f"/usr/bin/cp -al {SERVED} {STAGING}"]
    assert unit["ExecStartPost"] == [f"/usr/bin/mv -T --exchange {STAGING} {SERVED}"]


def test_the_sync_runs_daily_and_a_day_the_bridgehead_was_down_runs_at_its_next_start():
    timer = _unit("zaccess-caddy-mirror.timer.j2")
    assert {key: timer[key] for key in ("OnCalendar", "RandomizedDelaySec", "Persistent", "Unit")} == {
        "OnCalendar": ["*-*-* 03:41:00"],
        "RandomizedDelaySec": ["30min"],
        "Persistent": ["true"],
        "Unit": ["zaccess-caddy-mirror.service"],
    }


# --- the bootstrap: the mirror first, then Caddy from it on disk -------------------------------------------------------
def test_the_bridgehead_mirrors_then_reads_its_mirror_from_disk_then_installs_caddy():
    tasks = load_tasks(ACCESS_TASKS)
    names = (DEBMIRROR, KEY, USER, DIRECTORY, UNITS, PREVIEWED, TIMER, RELEASE, FIRST_SYNC, SOURCE, DEBIAN_PIN, INSTALL)
    order = [task_index(tasks, name) for name in names]
    assert order == sorted(order), order
    assert find_task(tasks, DEBMIRROR)["ansible.builtin.apt"]["name"] == ["debmirror", "gpgv"]
    directory = find_task(tasks, DIRECTORY)
    assert directory["loop"] == ["{{ access_caddy_mirror_dir }}", "{{ access_caddy_mirror_served }}"]
    assert directory["ansible.builtin.file"] == {
        "path": "{{ item }}",
        "state": "directory",
        "owner": "{{ access_caddy_mirror_user }}",
        "group": "{{ access_caddy_mirror_user }}",
        "mode": "0755",
    }
    source = find_task(tasks, SOURCE)["ansible.builtin.deb822_repository"]
    assert source == {
        "name": "caddy",
        "types": ["deb"],
        "uris": "file:{{ access_caddy_mirror_served }}",
        "suites": ["any-version"],
        "components": ["main"],
        "signed_by": "{{ caddy_mirror_keyring }}",
        "install_python_debian": True,
    }


@pytest.mark.parametrize(
    ("previewed", "exists", "runs"), [(False, False, True), (False, True, False), (True, False, False), (True, True, False)]
)
def test_the_first_sync_runs_on_an_empty_mirror_and_never_in_a_preview_without_its_unit(previewed, exists, runs):
    tasks = load_tasks(ACCESS_TASKS)
    sync = find_task(tasks, FIRST_SYNC)
    assert sync["ansible.builtin.systemd"] == {"name": "zaccess-caddy-mirror.service", "state": "started"}
    release = find_task(tasks, RELEASE)["ansible.builtin.stat"]
    assert release == {"path": "{{ access_caddy_mirror_served }}/dists/any-version/Release"}
    variables = {"access_caddy_mirror_previewed": previewed, "access_caddy_mirror_release": {"stat": {"exists": exists}}}
    assert truthy(when_conditions(sync), variables) is runs


@pytest.mark.parametrize(
    ("check", "units", "previewed"),
    [(True, {"changed": True}, True), (True, {"changed": False}, False), (False, {"changed": True}, False)],
)
def test_the_timer_skips_the_preview_that_has_not_written_its_unit(check, units, previewed):
    tasks = load_tasks(ACCESS_TASKS)
    fact = set_facts(find_task(tasks, PREVIEWED), {"ansible_check_mode": check, "access_caddy_mirror_units": units})
    assert bool(fact["access_caddy_mirror_previewed"]) is previewed
    timer = find_task(tasks, TIMER)
    assert timer["ansible.builtin.systemd"] == {
        "name": "zaccess-caddy-mirror.timer",
        "enabled": True,
        "state": "started",
        "daemon_reload": True,
    }
    assert when_conditions(timer) == ["not access_caddy_mirror_previewed"]


# --- what apt may install -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("path", [ACCESS_TASKS], ids=["access"])
def test_debians_own_caddy_is_never_a_candidate(path):
    pin = find_task(load_tasks(path), DEBIAN_PIN)["ansible.builtin.copy"]
    assert pin == {"content": PIN, "dest": "/etc/apt/preferences.d/caddy", "owner": "root", "group": "root", "mode": "0644"}


def test_the_bridgehead_installs_caddy_never_forced_or_held():
    tasks = iter_tasks(load_tasks(ACCESS_TASKS))
    modules = ("ansible.builtin.apt", "ansible.builtin.dpkg_selections")
    caddy = [task[module] for task, _ in tasks for module in modules if task.get(module, {}).get("name") == "caddy"]
    assert caddy == [{"name": "caddy", "state": "present", "update_cache": True}, {"name": "caddy", "selection": "install"}], caddy
EOF
```

- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider
```

Expected: `13 failed, 2 passed` — the keyring's hash and `test_the_bridgehead_installs_caddy_never_forced_or_held`, whose install and hold the interim kept, pass; the others fail on the absent templates and task names.

- [ ] **Step 4: Implement** — the defaults, the two units, the chain in place of the interim's block, and the interim tests' removal:

```bash
cat >> infra/ansible/roles/access/defaults/main.yml <<'EOF'

# The Caddy apt mirror (spec 00127): the repository it copies, named here and in no other role file, the system user
# its sync runs as, the directory it syncs under, and the served tree in it.
access_caddy_mirror_upstream_host: dl.cloudsmith.io
access_caddy_mirror_upstream_root: public/caddy/stable/deb/debian
access_caddy_mirror_user: caddy-mirror
access_caddy_mirror_dir: /var/lib/caddy-apt-mirror
access_caddy_mirror_served: "{{ access_caddy_mirror_dir }}/served"
EOF
cat > infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2 <<'EOF'
# Rendered by the `access` Ansible role at /etc/systemd/system/zaccess-caddy-mirror.service — edit
# infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2 instead. Traceability: spec 00127.
[Unit]
Description=Sync of the Caddy apt mirror, one suite, amd64 and main, for the edge nodes
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User={{ access_caddy_mirror_user }}
Group={{ access_caddy_mirror_user }}
UMask=0022
TimeoutStartSec=2h
# debmirror moves a new index in even when a pool file failed, so it syncs a hard-linked copy of the served tree, and
# the copy replaces the served tree only once debmirror has exited 0.
ExecStartPre=/usr/bin/rm -rf {{ access_caddy_mirror_dir }}/staging
ExecStartPre=/usr/bin/cp -al {{ access_caddy_mirror_served }} {{ access_caddy_mirror_dir }}/staging
ExecStart=/usr/bin/debmirror --method=https --host={{ access_caddy_mirror_upstream_host }} --root={{ access_caddy_mirror_upstream_root }} --dist=any-version --section=main --arch=amd64 --nosource --check-gpg --keyring={{ caddy_mirror_keyring }} --rsync-extra=none --diff=none --postcleanup --verbose {{ access_caddy_mirror_dir }}/staging
ExecStartPost=/usr/bin/mv -T --exchange {{ access_caddy_mirror_dir }}/staging {{ access_caddy_mirror_served }}
ProtectSystem=strict
ReadWritePaths={{ access_caddy_mirror_dir }}
PrivateTmp=true
NoNewPrivileges=true
EOF
cat > infra/ansible/roles/access/templates/zaccess-caddy-mirror.timer.j2 <<'EOF'
# Rendered by the `access` Ansible role at /etc/systemd/system/zaccess-caddy-mirror.timer — edit
# infra/ansible/roles/access/templates/zaccess-caddy-mirror.timer.j2 instead. Traceability: spec 00127.
[Unit]
Description=Daily sync of the Caddy apt mirror

[Timer]
OnCalendar=*-*-* 03:41:00
RandomizedDelaySec=30min
# A day the bridgehead was down is synced at its next start.
Persistent=true
Unit=zaccess-caddy-mirror.service

[Install]
WantedBy=timers.target
EOF
python3 -I - infra/ansible/roles/access/tasks/main.yml <<'PYEOF'
import sys
path = sys.argv[1]
BLOCK = '''# The Caddy apt mirror, then Caddy from it (spec 00127): debmirror is Debian's, so a bridgehead without Caddy mirrors
# the vendor's repository first and installs Caddy from that copy on disk.
- name: debmirror and gpgv present — the mirror's tool and its signature check, both from Debian
  ansible.builtin.apt:
    name: [debmirror, gpgv]
    state: present
    update_cache: true
    cache_valid_time: 3600
- name: the Caddy vendor key the mirror and apt verify its Release with
  ansible.builtin.copy:
    src: "{{ playbook_dir }}/files/caddy-archive-keyring.gpg"
    dest: "{{ caddy_mirror_keyring }}"
    owner: root
    group: root
    mode: "0644"
- name: the mirror's system user
  ansible.builtin.user:
    name: "{{ access_caddy_mirror_user }}"
    system: true
    shell: /usr/sbin/nologin
    home: "{{ access_caddy_mirror_dir }}"
    create_home: false
- name: the mirror's directory and its served tree, readable by the caddy user
  ansible.builtin.file:
    path: "{{ item }}"
    state: directory
    owner: "{{ access_caddy_mirror_user }}"
    group: "{{ access_caddy_mirror_user }}"
    mode: "0755"
  loop: ["{{ access_caddy_mirror_dir }}", "{{ access_caddy_mirror_served }}"]
- name: the mirror's service + timer
  ansible.builtin.template:
    src: "zaccess-caddy-mirror.{{ item }}.j2"
    dest: "/etc/systemd/system/zaccess-caddy-mirror.{{ item }}"
    mode: "0644"
  loop: [service, timer]
  register: access_caddy_mirror_units
  notify: reload systemd
# A preview has not written the units, and systemd refuses a unit it cannot find.
- name: note a preview that runs before the mirror's units exist
  ansible.builtin.set_fact:
    access_caddy_mirror_previewed: "{{ ansible_check_mode and access_caddy_mirror_units is changed }}"
- name: the mirror's timer enabled
  ansible.builtin.systemd: {name: zaccess-caddy-mirror.timer, enabled: true, state: started, daemon_reload: true}
  when: not access_caddy_mirror_previewed
- name: read whether the mirror's served tree holds a Release
  ansible.builtin.stat:
    path: "{{ access_caddy_mirror_served }}/dists/any-version/Release"
  register: access_caddy_mirror_release
- name: the mirror's first sync, before the Caddy source reads it from disk
  ansible.builtin.systemd: {name: zaccess-caddy-mirror.service, state: started}
  when:
    - not access_caddy_mirror_previewed
    - not access_caddy_mirror_release.stat.exists
- name: the Caddy apt source — the bridgehead's own mirror, read from disk
  ansible.builtin.deb822_repository:
    name: caddy
    types: [deb]
    uris: "file:{{ access_caddy_mirror_served }}"
    suites: [any-version]
    components: [main]
    signed_by: "{{ caddy_mirror_keyring }}"
    install_python_debian: true
- name: Debian's own caddy never a candidate — the mirror's is the one apt installs
  ansible.builtin.copy:
    content: |
      Package: caddy
      Pin: release o=Debian
      Pin-Priority: -1
    dest: /etc/apt/preferences.d/caddy
    owner: root
    group: root
    mode: "0644"
- name: caddy present — version FOLLOWED from apt, never forced (the Caddyfile validate is the guard)
  ansible.builtin.apt:
    name: caddy
    state: present
    update_cache: true
- name: caddy is never held — a hold makes `apt upgrade` skip it silently
  ansible.builtin.dpkg_selections: {name: caddy, selection: install}
'''
text = open(path).read()
start = text.index("- name: the Caddy apt repository removed — the interim of 2026-10-11\n")
end = text.index("\n# spec 00075 D16.\n- name: zaccess mTLS CA cert")
assert text.count("- name: the Caddy apt repository removed") == 1
open(path, "w").write(text[:start] + BLOCK + text[end:])
PYEOF
python3 -I - tests/test_infra_converge_guards.py <<'PYEOF'
import sys
path = sys.argv[1]
text = open(path).read()
start = text.index("def test_the_caddy_repository_is_removed_and_caddy_kept_installed_never_forced_or_held():")
end = text.index('AGENTBOARD_UNIT = ANSIBLE / "roles" / "access_ops"')
open(path, "w").write(text[:start] + text[end:])
PYEOF
```

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/test_infra_caddy_mirror.py tests/test_infra_converge_guards.py tests/test_access_alloy_tag.py -q -p no:cacheprovider
```

Expected: no failure; `tests/test_infra_caddy_mirror.py` reads `15 passed` on its own.

- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh infra/ansible/roles/access/defaults/main.yml infra/ansible/roles/access/tasks/main.yml infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2 infra/ansible/roles/access/templates/zaccess-caddy-mirror.timer.j2 tests/test_infra_converge_guards.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_infra_caddy_mirror.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add infra/ansible/roles/access/defaults/main.yml infra/ansible/roles/access/tasks/main.yml infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2 infra/ansible/roles/access/templates/zaccess-caddy-mirror.timer.j2 tests/test_infra_caddy_mirror.py tests/test_infra_converge_guards.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`, `ansible-lint` and `yamllint` among them; a finding of either is fixed in the task's YAML before the commit, and Step 9's line-addressed probes then read their numbers from the committed file (Global Constraints).

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(ansible): the bridgehead mirrors Caddy's apt repository daily with debmirror, reads the copy from disk and installs its Caddy from it; the interim's removal and refusal leave the access role

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Prove the guards** — the service's signature check, keyring, architecture and umask, and the served tree it does not sync; the swap's copy and exchange; the timer's catch-up and delay; the vendor key's copy; the chain's order, its user, the directory's mode, the apt list and the `file:` source; the first sync's two gates and the served tree it reads; the preview fact and the timer's gate; the pin; the hold:

```bash
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2 --control '1,$d' --mutation 's/ --check-gpg//' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_sync_runs_debmirror_over_one_suite_amd64_and_main_checking_the_release_signature
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2 --control '1,$d' --mutation 's/ --keyring={{ caddy_mirror_keyring }}//' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_sync_runs_debmirror_over_one_suite_amd64_and_main_checking_the_release_signature
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2 --control '1,$d' --mutation 's/--arch=amd64/--arch=amd64,arm64/' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_sync_runs_debmirror_over_one_suite_amd64_and_main_checking_the_release_signature
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2 --control '1,$d' --mutation '/^UMask=0022$/d' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_sync_runs_debmirror_over_one_suite_amd64_and_main_checking_the_release_signature
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2 --control '1,$d' --mutation 's|--verbose {{ access_caddy_mirror_dir }}/staging$|--verbose {{ access_caddy_mirror_served }}|' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_sync_runs_debmirror_over_one_suite_amd64_and_main_checking_the_release_signature
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2 --control '1,$d' --mutation '\|^ExecStartPre=/usr/bin/cp -al |d' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_a_sync_reaches_the_served_tree_only_after_debmirror_exits_0
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2 --control '1,$d' --mutation '/^ExecStartPost=/d' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_a_sync_reaches_the_served_tree_only_after_debmirror_exits_0
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/zaccess-caddy-mirror.timer.j2 --control '1,$d' --mutation '/^Persistent=true$/d' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_sync_runs_daily_and_a_day_the_bridgehead_was_down_runs_at_its_next_start
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/zaccess-caddy-mirror.timer.j2 --control '1,$d' --mutation '/^RandomizedDelaySec=30min$/d' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_sync_runs_daily_and_a_day_the_bridgehead_was_down_runs_at_its_next_start
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation 's|    dest: "{{ caddy_mirror_keyring }}"|    dest: /etc/apt/keyrings/caddy.gpg|' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k 'test_the_vendored_keyring_lands_where_the_caddy_source_reads_it and access'
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation '93h;94,97H;93,97d;106G' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_bridgehead_mirrors_then_reads_its_mirror_from_disk_then_installs_caddy
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation '59h;60,65H;59,65d;81G' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_bridgehead_mirrors_then_reads_its_mirror_from_disk_then_installs_caddy
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation 's/^    mode: "0755"$/    mode: "0750"/' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_bridgehead_mirrors_then_reads_its_mirror_from_disk_then_installs_caddy
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation 's/name: \[debmirror, gpgv\]/name: [debmirror]/' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_bridgehead_mirrors_then_reads_its_mirror_from_disk_then_installs_caddy
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation 's|uris: "file:{{ access_caddy_mirror_served }}"|uris: "https://{{ caddy_mirror_host }}"|' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_bridgehead_mirrors_then_reads_its_mirror_from_disk_then_installs_caddy
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation '/^    - not access_caddy_mirror_release.stat.exists$/d' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_first_sync_runs_on_an_empty_mirror_and_never_in_a_preview_without_its_unit
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation '/^    - not access_caddy_mirror_previewed$/d' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_first_sync_runs_on_an_empty_mirror_and_never_in_a_preview_without_its_unit
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation 's|path: "{{ access_caddy_mirror_served }}/dists/any-version/Release"|path: "{{ access_caddy_mirror_dir }}/staging/dists/any-version/Release"|' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_first_sync_runs_on_an_empty_mirror_and_never_in_a_preview_without_its_unit
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation 's/ansible_check_mode and access_caddy_mirror_units is changed/access_caddy_mirror_units is changed/' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_timer_skips_the_preview_that_has_not_written_its_unit
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation '/^  when: not access_caddy_mirror_previewed$/d' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_timer_skips_the_preview_that_has_not_written_its_unit
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation 's/Pin-Priority: -1/Pin-Priority: 100/' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k 'test_debians_own_caddy_is_never_a_candidate and access'
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1,$d' --mutation 's/selection: install/selection: hold/' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_bridgehead_installs_caddy_never_forced_or_held
```

Expected: each `KILLED`; then the message-only amend.

- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 3: The bridgehead's Caddy serves the mirror publicly, the two apt trees alone

**Files:**
- Modify: `infra/ansible/roles/access/templates/Caddyfile.j2` (a site after `:33`), `tests/test_infra_caddy_mirror.py` (two tests appended)

- [ ] **Step 1: Read** spec 00127 D2; `infra/ansible/roles/access/templates/Caddyfile.j2`; `tests/role_render.py`'s `blocks`.
- [ ] **Step 2: Write the failing tests**

```bash
cat >> tests/test_infra_caddy_mirror.py <<'EOF'


# --- the site ---------------------------------------------------------------------------------------------------------------
def _caddyfile() -> dict[str, list]:
    return dict(role_render.blocks(_render("Caddyfile.j2").splitlines()))


def test_the_mirror_site_is_public_and_serves_the_two_apt_trees_alone():
    body = _caddyfile()["apt.zaccess.zhaow.me"]
    lines = [line for line, _ in body]
    assert len(lines) == len(set(lines)), "a repeated line: Caddy routes a handle by the first, a dict by the last"
    site = dict(body)
    assert list(site) == ["@apt path /dists/* /pool/*", "handle @apt", "handle"], list(site)
    assert site["handle @apt"] == [("root * /var/lib/caddy-apt-mirror/served", []), ("file_server", [])]
    assert site["handle"] == [("respond 404", [])]


def test_the_two_mtls_sites_still_import_the_snippet():
    importing = [name for name, body in _caddyfile().items() if ("import mtls", []) in body]
    assert importing == ["tmux.zaccess.zhaow.me", "nas.zaccess.zhaow.me"], importing
EOF
```

- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider
```

Expected: `1 failed, 16 passed`, the site test on a `KeyError` for `apt.zaccess.zhaow.me`; the mTLS test passes already, the regression it holds being one this task could cause.
- [ ] **Step 4: Implement**

```bash
cat >> infra/ansible/roles/access/templates/Caddyfile.j2 <<'EOF'

# The Caddy apt mirror, public, without mTLS: the vendor's signed repository, re-served as it is.
{{ caddy_mirror_host }} {
	@apt path /dists/* /pool/*
	handle @apt {
		root * {{ access_caddy_mirror_served }}
		file_server
	}
	handle {
		respond 404
	}
}
EOF
```

- [ ] **Step 5: Run the tests** — Step 3's command; Expected: `17 passed`.
- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh infra/ansible/roles/access/templates/Caddyfile.j2 | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_infra_caddy_mirror.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add infra/ansible/roles/access/templates/Caddyfile.j2 tests/test_infra_caddy_mirror.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`.

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(ansible): the bridgehead's Caddy serves the apt mirror at apt.zaccess.zhaow.me, public, /dists/* and /pool/* alone

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Prove the guards** — the site imports no mTLS, lists nothing, serves two trees, answers 404 elsewhere and repeats no line; the two mTLS sites keep the snippet:

```bash
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/Caddyfile.j2 --control '1,$d' --mutation 's|^\t@apt path /dists/\* /pool/\*$|\timport mtls\n&|' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_mirror_site_is_public_and_serves_the_two_apt_trees_alone
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/Caddyfile.j2 --control '1,$d' --mutation 's|^\t\tfile_server$|\t\tfile_server browse|' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_mirror_site_is_public_and_serves_the_two_apt_trees_alone
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/Caddyfile.j2 --control '1,$d' --mutation 's|@apt path /dists/\* /pool/\*|@apt path /*|' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_mirror_site_is_public_and_serves_the_two_apt_trees_alone
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/Caddyfile.j2 --control '1,$d' --mutation '/^\thandle {$/,/^\t}$/d' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_mirror_site_is_public_and_serves_the_two_apt_trees_alone
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/Caddyfile.j2 --control '1,$d' --mutation 's|^\thandle @apt {$|\thandle @apt {\n\t\tfile_server browse\n\t}\n&|' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_mirror_site_is_public_and_serves_the_two_apt_trees_alone
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/templates/Caddyfile.j2 --control '1,$d' --mutation '/^nas.zaccess.zhaow.me {$/,/^}$/{/import mtls/d}' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_two_mtls_sites_still_import_the_snippet
```

Expected: each `KILLED`; then the message-only amend.

- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 4: The edge nodes' Caddy source is the mirror, refused while it does not answer; the interim leaves the edge and mon roles

**Files:**
- Create: `infra/ansible/roles/edge/tasks/caddy-source.yml`, by `git mv` of `caddy-source-absent.yml`
- Modify: `infra/ansible/roles/edge/tasks/main.yml` (`:3-33`, the interim's import, read, refusal, install name and one-fact gate, become the import of `caddy-source.yml` and the pre-interim pair), `infra/ansible/roles/mon/tasks/main.yml` (`:2-6`, the header's interim clause; `:34-36`, the include), `tests/test_infra_edge_role.py` (`:26`; `:105-183` rewritten), `tests/test_infra_mon_role.py` (`:385-391`), `tests/test_infra_caddy_mirror.py` (the edge's pin and keyring cases and the vendor-name test)

**What this task decides, where the spec leaves it open:**
- The preflight reads `HEAD` of `Release`, the file debmirror copies whatever it does with `InRelease`, and holds the register's `status`, which `ansible.builtin.uri` sets to `-1` on a connection that fails; its assert carries no modifier, as the interim's refusal did not, and its message names `infra/runbooks/zaccess.md`'s `zaccess-caddy-mirror`, whose step for a refusal takes each answer — not a bridgehead converge, which mends a bridgehead without the mirror's units alone and reopens a cut SSH relay.
- The pre-interim preview pair returns under its pre-interim task names: the gate the mon role carried as `mon_repos_previewed` until `4f2f7f8ce` moved its Caddy into the edge role, which drill W3's fresh-host preview read on 2026-10-04 (`docs/reference/drill-log.md:129`).

- [ ] **Step 1: Read** spec 00127 D5 and D6; `infra/ansible/roles/edge/tasks/main.yml`; `infra/ansible/roles/edge/tasks/caddy-source-absent.yml`; `infra/ansible/roles/mon/tasks/main.yml:1-45`; `git show 02b74a133:infra/ansible/roles/edge/tasks/main.yml`, the pre-interim pair; `tests/test_infra_edge_role.py:1-40`, `:100-188`; `tests/test_infra_mon_role.py:380-392`.
- [ ] **Step 2: Write the failing tests**

```bash
python3 -I - tests/test_infra_edge_role.py <<'PYEOF'
import sys
path = sys.argv[1]
BLOCK = '''# --- packages: Caddy from the bridgehead's mirror, followed from apt -----------------------------------------------
_SOURCE_IMPORT = "the Caddy apt source, its key and Debian's caddy pinned out, from the bridgehead's mirror"
_MIRROR_SOURCE = {
    "name": "caddy",
    "types": ["deb"],
    "uris": "https://{{ caddy_mirror_host }}",
    "suites": ["any-version"],
    "components": ["main"],
    "signed_by": "{{ caddy_mirror_keyring }}",
    "install_python_debian": True,
}
_INSTALL = "caddy present — version FOLLOWED from apt, never forced or held"


def test_caddy_comes_from_the_bridgeheads_mirror_and_is_never_forced_held_or_pinned_to_a_version():
    tasks = iter_tasks(load_tasks(TASKS))
    assert find_task(load_tasks(TASKS), _SOURCE_IMPORT)["ansible.builtin.import_tasks"] == SOURCE.name
    files = sorted((ROLE / "tasks").glob("*.yml"))
    leaves = [task for path in files for task, _ in iter_tasks(load_tasks(path))]
    (repository,) = [task["ansible.builtin.deb822_repository"] for task in leaves if "ansible.builtin.deb822_repository" in task]
    assert repository == _MIRROR_SOURCE
    (install,) = [task["ansible.builtin.apt"] for task, _ in tasks if "ansible.builtin.apt" in task]
    assert install == {"name": "caddy", "state": "present", "update_cache": True}, "the repository task refreshes no cache"
    assert "ansible.builtin.dpkg_selections" not in {key for task, _ in tasks for key in task}, "a hold skips caddy silently"


def test_the_caddy_source_names_the_mirror_before_the_edges_first_apt_refresh():
    leaves = [task for task, _, _ in alloy_version.role_leaves("edge", frozenset())]
    sources = [i for i, task in enumerate(leaves) if task.get("ansible.builtin.deb822_repository") == _MIRROR_SOURCE]
    refreshes = [i for i, task in enumerate(leaves) if refreshes_the_apt_cache(task)]
    assert sources and refreshes and sources[0] < refreshes[0], (sources, refreshes)


_MIRROR_READ = "read whether the bridgehead's Caddy mirror answers"
_MIRROR_REFUSAL = "refuse a Caddy source the bridgehead's mirror does not serve"
_KEY = "the Caddy vendor key apt verifies the mirror's Release with"
_SOURCE_TASK = "the Caddy apt source — the bridgehead's mirror"


@pytest.mark.parametrize(("status", "admitted"), [(200, True), (404, False), (402, False), (-1, False)])
def test_a_mirror_that_does_not_answer_is_refused_before_the_source_is_written_and_in_a_preview(status, admitted):
    tasks = load_tasks(SOURCE)
    assert find_task(tasks, _MIRROR_READ) == {
        "name": _MIRROR_READ,
        "ansible.builtin.uri": {"url": "https://{{ caddy_mirror_host }}/dists/any-version/Release", "method": "HEAD"},
        "register": "edge_caddy_mirror",
        "failed_when": False,
        "check_mode": False,
    }
    refusal = find_task(tasks, _MIRROR_REFUSAL)
    assert set(refusal) == {"name", "ansible.builtin.assert"}, sorted(refusal)
    assert truthy(assert_that(refusal), {"edge_caddy_mirror": {"status": status}}) is admitted
    names = [task.get("name") for task in tasks]
    assert names.index(_MIRROR_READ) < names.index(_MIRROR_REFUSAL) < names.index(_KEY) < names.index(_SOURCE_TASK), names


# --- the preview on a node that has nothing yet -------------------------------------------------------------------
_CHANGED, _UNCHANGED, _SKIPPED = {"changed": True}, {"changed": False}, {"changed": False, "skipped": True}


# Each disjunct of the two facts has a case in which it alone is true.
@pytest.mark.parametrize(
    ("check", "repository", "install", "expected"),
    [
        (True, _CHANGED, _SKIPPED, (True, True)),  # a fresh node's preview, or the first onto the mirror
        (True, _UNCHANGED, _CHANGED, (False, True)),  # caddy alone still to install
        (True, _UNCHANGED, _UNCHANGED, (False, False)),  # an established node's preview
        (False, _CHANGED, _CHANGED, (False, False)),  # the real first converge
    ],
)
def test_the_two_preview_facts_are_true_only_where_a_preview_has_no_package_to_find(check, repository, install, expected):
    tasks = load_tasks(TASKS)
    variables = {"ansible_check_mode": check, "edge_caddy_repo": repository}
    first = set_facts(find_task(tasks, "note a preview that runs before the Caddy repository exists"), variables)
    variables |= first | {"edge_caddy_install": install}
    second = set_facts(find_task(tasks, "note a preview that runs before caddy is installed"), variables)
    assert (bool(first["edge_repo_previewed"]), bool(second["edge_units_previewed"])) == expected


def test_what_needs_the_repository_or_the_unit_skips_the_preview_that_has_neither():
    tasks = load_tasks(TASKS)
    assert when_conditions(find_task(tasks, _INSTALL)) == ["not edge_repo_previewed"]
    units = [(task["name"], gates) for task, gates in iter_tasks(tasks) if "ansible.builtin.systemd_service" in task]
    assert units == [("caddy enabled + started", ("not edge_units_previewed",))], units
    assert find_task(tasks, "Caddyfile — the one public listener's routes")["notify"] == "reload caddy"
    (handler,) = yaml.safe_load(HANDLERS.read_text())
    assert (handler["name"], handler["ansible.builtin.systemd_service"]) == ("reload caddy", {"name": "caddy", "state": "reloaded"})
    assert when_conditions(handler) == ["not edge_units_previewed"]


'''
text = open(path).read()
old_source = 'SOURCE = ROLE / "tasks/caddy-source-absent.yml"'
assert text.count(old_source) == 1
text = text.replace(old_source, 'SOURCE = ROLE / "tasks/caddy-source.yml"')
start = text.index("# --- packages: Caddy kept at its installed version")
end = text.index("# --- the role is reached by an include alone")
open(path, "w").write(text[:start] + BLOCK + text[end:])
PYEOF
python3 -I - tests/test_infra_mon_role.py <<'PYEOF'
import sys
path = sys.argv[1]
OLD = '''CADDY_SOURCE_ABSENT = {"name": "edge", "tasks_from": "caddy-source-absent"}


def test_the_caddy_source_comes_off_before_the_first_apt_refresh():
    leaves = [task for task, _, _ in alloy_version.role_leaves("mon", frozenset())]
    removals = [i for i, task in enumerate(leaves) if task.get("ansible.builtin.include_role") == CADDY_SOURCE_ABSENT]
    refreshes = [i for i, task in enumerate(leaves) if refreshes_the_apt_cache(task)]
    assert removals and refreshes and removals[0] < refreshes[0], (removals, refreshes)
'''
NEW = '''CADDY_SOURCE = {"name": "edge", "tasks_from": "caddy-source"}


def test_the_caddy_source_names_the_mirror_before_the_first_apt_refresh():
    leaves = [task for task, _, _ in alloy_version.role_leaves("mon", frozenset())]
    sources = [i for i, task in enumerate(leaves) if task.get("ansible.builtin.include_role") == CADDY_SOURCE]
    refreshes = [i for i, task in enumerate(leaves) if refreshes_the_apt_cache(task)]
    assert sources and refreshes and sources[0] < refreshes[0], (sources, refreshes)
'''
text = open(path).read()
assert text.count(OLD) == 1
open(path, "w").write(text.replace(OLD, NEW))
PYEOF
python3 -I - tests/test_infra_caddy_mirror.py <<'PYEOF'
import sys
path = sys.argv[1]
APPEND = '''

# --- the vendor's repository: read by the sync alone ------------------------------------------------------------------
def test_the_vendors_repository_is_named_by_the_mirrors_upstream_alone():
    files = [path for path in (ANSIBLE / "roles").rglob("*") if path.suffix in {".yml", ".j2"}]
    hits = sorted(str(path.relative_to(ANSIBLE)) for path in files if "cloudsmith" in path.read_text().lower())
    assert hits == ["roles/access/defaults/main.yml"], hits
'''
text = open(path).read()
ADDED = {
    'ACCESS_TASKS = ACCESS / "tasks/main.yml"\n': 'EDGE_SOURCE = ANSIBLE / "roles/edge/tasks/caddy-source.yml"\n',
    'KEY = "the Caddy vendor key the mirror and apt verify its Release with"\n': "EDGE_KEY = \"the Caddy vendor key apt verifies the mirror's Release with\"\n",
}
CASES = {
    '@pytest.mark.parametrize("path", [ACCESS_TASKS], ids=["access"])': '@pytest.mark.parametrize("path", [ACCESS_TASKS, EDGE_SOURCE], ids=["access", "edge"])',
    '@pytest.mark.parametrize(("path", "name"), [(ACCESS_TASKS, KEY)], ids=["access"])': '@pytest.mark.parametrize(("path", "name"), [(ACCESS_TASKS, KEY), (EDGE_SOURCE, EDGE_KEY)], ids=["access", "edge"])',
}
for old in [*ADDED, *CASES]:
    assert text.count(old) == 1, old
for anchor, line in ADDED.items():
    text = text.replace(anchor, anchor + line)
for old, new in CASES.items():
    text = text.replace(old, new)
open(path, "w").write(text + APPEND)
PYEOF
```

- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_infra_caddy_mirror.py tests/test_infra_edge_role.py tests/test_infra_mon_role.py -q -p no:cacheprovider
```

Expected: `15 failed, 102 passed` — the edge's pin and keyring cases and the vendor-name test (the interim's edge and mon comments name the vendor), the edge's source, order, preflight and pair tests on the absent `caddy-source.yml` and task names, and mon's include.

- [ ] **Step 4: Implement**

```bash
git mv infra/ansible/roles/edge/tasks/caddy-source-absent.yml infra/ansible/roles/edge/tasks/caddy-source.yml
cat > infra/ansible/roles/edge/tasks/caddy-source.yml <<'EOF'
---
# Caddy's apt source on an edge node, the bridgehead's mirror (spec 00127); its own file so mon writes it before its
# first apt refresh.
- name: read whether the bridgehead's Caddy mirror answers
  ansible.builtin.uri:
    url: "https://{{ caddy_mirror_host }}/dists/any-version/Release"
    method: HEAD
  register: edge_caddy_mirror
  failed_when: false
  check_mode: false

- name: refuse a Caddy source the bridgehead's mirror does not serve
  ansible.builtin.assert:
    that: edge_caddy_mirror.status == 200
    fail_msg: >-
      https://{{ caddy_mirror_host }}/dists/any-version/Release answers {{ edge_caddy_mirror.status }} to
      {{ inventory_hostname }} ({{ edge_caddy_mirror.msg | default('') }}), so every apt refresh would fail on the
      Caddy source this play writes. infra/runbooks/zaccess.md's zaccess-caddy-mirror procedure reads each answer.

- name: the Caddy vendor key apt verifies the mirror's Release with
  ansible.builtin.copy:
    src: "{{ playbook_dir }}/files/caddy-archive-keyring.gpg"
    dest: "{{ caddy_mirror_keyring }}"
    owner: root
    group: root
    mode: "0644"

- name: the Caddy apt source — the bridgehead's mirror
  ansible.builtin.deb822_repository:
    name: caddy
    types: [deb]
    uris: "https://{{ caddy_mirror_host }}"
    suites: [any-version]
    components: [main]
    signed_by: "{{ caddy_mirror_keyring }}"
    install_python_debian: true
  register: edge_caddy_repo

- name: Debian's own caddy never a candidate — the mirror's is the one apt installs
  ansible.builtin.copy:
    content: |
      Package: caddy
      Pin: release o=Debian
      Pin-Priority: -1
    dest: /etc/apt/preferences.d/caddy
    owner: root
    group: root
    mode: "0644"
EOF
python3 -I - infra/ansible/roles/edge/tasks/main.yml <<'PYEOF'
import sys
path = sys.argv[1]
NEW = '''- name: the Caddy apt source, its key and Debian's caddy pinned out, from the bridgehead's mirror
  ansible.builtin.import_tasks: caddy-source.yml

# A preview on a node that never had the source cannot see caddy: apt fails on a name its cache does not hold, and
# converge.sh stops on a failed preview. What needs the package or its unit skips exactly that case.
- name: note a preview that runs before the Caddy repository exists
  ansible.builtin.set_fact:
    edge_repo_previewed: "{{ ansible_check_mode and edge_caddy_repo is changed }}"

- name: caddy present — version FOLLOWED from apt, never forced or held
  ansible.builtin.apt:
    name: caddy
    state: present
    update_cache: true
  register: edge_caddy_install
  when: not edge_repo_previewed

# A preview that would install caddy has no unit of it for systemd to find.
- name: note a preview that runs before caddy is installed
  ansible.builtin.set_fact:
    edge_units_previewed: "{{ ansible_check_mode and (edge_repo_previewed or edge_caddy_install is changed) }}"

'''
text = open(path).read()
start = text.index("- name: the Caddy apt repository removed\n")
end = text.index("# Validated by the installed binary")
open(path, "w").write(text[:start] + NEW + text[end:])
PYEOF
python3 -I - infra/ansible/roles/mon/tasks/main.yml <<'PYEOF'
import sys
path = sys.argv[1]
EDITS = [
    (
        """# single-binary Loki, Caddy as the one public listener, and the node's own Alloy. Packages followed from
# apt, never forced or held, but Alloy, held and pinned at the fleet's version, and Caddy, frozen at the
# installed version while the edge role removes its apt source; tests/test_infra_mon_role.py holds what the
# public login rests on.
""",
        """# single-binary Loki, Caddy as the one public listener, and the node's own Alloy. Packages followed from
# apt, never forced or held, but Alloy, held and pinned at the fleet's version; tests/test_infra_mon_role.py
# holds what the public login rests on.
""",
    ),
    (
        """# `apt update` fails on Caddy's Cloudsmith source while that repository is out.
- name: the Caddy apt repository removed before any apt refresh
  ansible.builtin.include_role: {name: edge, tasks_from: caddy-source-absent}
""",
        """# Before the first apt refresh below, which reads the mirror's source: a mirror that does not answer is refused here.
# A --tags alloy run selects no task of this include.
- name: the Caddy apt source names the bridgehead's mirror before any apt refresh
  ansible.builtin.include_role: {name: edge, tasks_from: caddy-source}
""",
    ),
]
text = open(path).read()
for old, new in EDITS:
    assert text.count(old) == 1, old[:60]
    text = text.replace(old, new)
open(path, "w").write(text)
PYEOF
```

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/test_infra_caddy_mirror.py tests/test_infra_edge_role.py tests/test_infra_mon_role.py tests/test_infra_hc_role.py tests/test_mon_alloy_tag.py -q -p no:cacheprovider
```

Expected: no failure; `tests/test_infra_caddy_mirror.py` reads `20 passed` on its own.

- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh infra/ansible/roles/edge/tasks/caddy-source.yml infra/ansible/roles/edge/tasks/main.yml infra/ansible/roles/mon/tasks/main.yml tests/test_infra_edge_role.py tests/test_infra_mon_role.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_infra_caddy_mirror.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add infra/ansible/roles/edge/tasks/caddy-source.yml infra/ansible/roles/edge/tasks/main.yml infra/ansible/roles/mon/tasks/main.yml tests/test_infra_edge_role.py tests/test_infra_mon_role.py tests/test_infra_caddy_mirror.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`, `ansible-lint` among them, an `ansible-lint` finding fixed in the task's YAML before the commit, and Step 9's line-addressed probes then reading their numbers from the committed file (Global Constraints); Step 4's `git mv` staged the old file's removal, so `git add` names the new path alone — the old one, no longer on disk or in the index, is a pathspec error.

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(ansible): the edge nodes' Caddy source is the bridgehead's mirror, refused in the preview while it does not answer, Debian's caddy pinned out; the interim leaves the edge and mon roles

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Prove the guards** — the source's address; the vendor named by the access defaults alone, its control a comment naming the vendor, since an emptied file passes that test; the preflight's condition, modifier, preview read and order; the edge's pin and its vendor key's copy; the edge's and mon's source before the first refresh; the pair:

```bash
infra/scripts/mutate-probe.sh --file infra/ansible/roles/edge/tasks/caddy-source.yml --control '1,$d' --mutation 's|uris: "https://{{ caddy_mirror_host }}"|uris: "https://dl.cloudsmith.io/public/caddy/stable/deb/debian"|' -- uv run pytest tests/test_infra_edge_role.py -q -p no:cacheprovider -k test_caddy_comes_from_the_bridgeheads_mirror_and_is_never_forced_held_or_pinned_to_a_version
infra/scripts/mutate-probe.sh --file infra/ansible/roles/access/tasks/main.yml --control '1i\# dl.cloudsmith.io' --mutation 's|uris: "file:{{ access_caddy_mirror_served }}"|uris: https://dl.cloudsmith.io/public/caddy/stable/deb/debian|' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_vendors_repository_is_named_by_the_mirrors_upstream_alone
infra/scripts/mutate-probe.sh --file infra/ansible/roles/edge/tasks/caddy-source.yml --control '1a\# dl.cloudsmith.io' --mutation 's|uris: "https://{{ caddy_mirror_host }}"|uris: "https://dl.cloudsmith.io/public/caddy/stable/deb/debian"|' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k test_the_vendors_repository_is_named_by_the_mirrors_upstream_alone
infra/scripts/mutate-probe.sh --file infra/ansible/roles/edge/tasks/caddy-source.yml --control '1,$d' --mutation 's/that: edge_caddy_mirror.status == 200/that: edge_caddy_mirror.status is defined/' -- uv run pytest tests/test_infra_edge_role.py -q -p no:cacheprovider -k test_a_mirror_that_does_not_answer_is_refused_before_the_source_is_written_and_in_a_preview
infra/scripts/mutate-probe.sh --file infra/ansible/roles/edge/tasks/caddy-source.yml --control '1,$d' --mutation '12a\  ignore_errors: true' -- uv run pytest tests/test_infra_edge_role.py -q -p no:cacheprovider -k test_a_mirror_that_does_not_answer_is_refused_before_the_source_is_written_and_in_a_preview
infra/scripts/mutate-probe.sh --file infra/ansible/roles/edge/tasks/caddy-source.yml --control '1,$d' --mutation '/^  check_mode: false$/d' -- uv run pytest tests/test_infra_edge_role.py -q -p no:cacheprovider -k test_a_mirror_that_does_not_answer_is_refused_before_the_source_is_written_and_in_a_preview
infra/scripts/mutate-probe.sh --file infra/ansible/roles/edge/tasks/caddy-source.yml --control '1,$d' --mutation '4h;5,19H;4,19d;37G' -- uv run pytest tests/test_infra_edge_role.py -q -p no:cacheprovider -k test_a_mirror_that_does_not_answer_is_refused_before_the_source_is_written_and_in_a_preview
infra/scripts/mutate-probe.sh --file infra/ansible/roles/edge/tasks/caddy-source.yml --control '1,$d' --mutation 's/Pin-Priority: -1/Pin-Priority: 100/' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k 'test_debians_own_caddy_is_never_a_candidate and edge'
infra/scripts/mutate-probe.sh --file infra/ansible/roles/edge/tasks/caddy-source.yml --control '1,$d' --mutation 's|    dest: "{{ caddy_mirror_keyring }}"|    dest: /etc/apt/keyrings/caddy.gpg|' -- uv run pytest tests/test_infra_caddy_mirror.py -q -p no:cacheprovider -k 'test_the_vendored_keyring_lands_where_the_caddy_source_reads_it and edge'
infra/scripts/mutate-probe.sh --file infra/ansible/roles/edge/tasks/main.yml --control '1,$d' --mutation '3h;4H;3,4d;18G' -- uv run pytest tests/test_infra_edge_role.py -q -p no:cacheprovider -k test_the_caddy_source_names_the_mirror_before_the_edges_first_apt_refresh
infra/scripts/mutate-probe.sh --file infra/ansible/roles/edge/tasks/main.yml --control '1,$d' --mutation '/^  when: not edge_repo_previewed$/d' -- uv run pytest tests/test_infra_edge_role.py -q -p no:cacheprovider -k test_what_needs_the_repository_or_the_unit_skips_the_preview_that_has_neither
infra/scripts/mutate-probe.sh --file infra/ansible/roles/edge/tasks/main.yml --control '1,$d' --mutation 's/(edge_repo_previewed or edge_caddy_install is changed)/(edge_caddy_install is changed)/' -- uv run pytest tests/test_infra_edge_role.py -q -p no:cacheprovider -k test_the_two_preview_facts_are_true_only_where_a_preview_has_no_package_to_find
infra/scripts/mutate-probe.sh --file infra/ansible/roles/edge/tasks/main.yml --control '1,$d' --mutation 's/ansible_check_mode and edge_caddy_repo is changed/edge_caddy_repo is changed/' -- uv run pytest tests/test_infra_edge_role.py -q -p no:cacheprovider -k test_the_two_preview_facts_are_true_only_where_a_preview_has_no_package_to_find
infra/scripts/mutate-probe.sh --file infra/ansible/roles/mon/tasks/main.yml --control '1,$d' --mutation '35h;36H;35,36d;42G' -- uv run pytest tests/test_infra_mon_role.py -q -p no:cacheprovider -k test_the_caddy_source_names_the_mirror_before_the_first_apt_refresh
```

Expected: each `KILLED`; then the message-only amend.

- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 5: The pages — the bridgehead's procedure, the monthly passes, the rebuilds, the fleet reference

**Files:**
- Modify: `infra/runbooks/zaccess.md` (`:3`, the page's procedure list; `:21`, the preview's keys; `:50` and `:99`, the interim's order sentences; `:123`, `zaccess-disk-high`'s step 2; the new section before `<a name="zaccess-bridgehead-dark">`), `infra/runbooks/hc.md` (`:37`, `:292` twice, `:302`, `:332`), `infra/runbooks/mon.md` (`:100`, `:218`, `:224`, `:274`), `infra/runbooks/drills-telemetry.md` (`:656`), `docs/reference/fleet.md` (`:13`, `:25`, `:43`, a row before `:47`)

- [ ] **Step 1: Load `zcrypto-refine-rules`**; read spec 00127 D6, D8 and D9; each line above; `infra/runbooks/README.md`'s scope — four parts for a PROCEDURE, no internal token, a universal in a bullet or a numbered step counted or declared (none below carries one).
- [ ] **Step 2: The edits** — each quoted text becomes the text after it, nothing else on its line moving; the script refuses a quoted text that is not on its page once:

```bash
python3 -I - <<'PYEOF'
from pathlib import Path

SECTION = """<a name="zaccess-caddy-mirror"></a>

## zaccess-caddy-mirror — PROCEDURE: syncing and reading the Caddy apt mirror

### What you are seeing

Nothing fired. You mean to bring a Caddy release onto the bridgehead's mirror before its daily sync and onto the bridgehead's own Caddy, or to read whether the mirror is current. Or a converge of the observability node or the dead-man node refused in its preview with `https://apt.zaccess.zhaow.me/dists/any-version/Release answers <status>`, or a read of that address answered other than `200`.

### What it means

The bridgehead mirrors the vendor's Caddy apt repository, one suite (`any-version`), `amd64` and `main`, with `debmirror`, run by `zaccess-caddy-mirror.service` from a daily timer, and its Caddy serves the copy publicly at `https://apt.zaccess.zhaow.me`, `/dists/` and `/pool/` alone. A sync runs over `/var/lib/caddy-apt-mirror/staging`, a hard-linked copy of `/var/lib/caddy-apt-mirror/served`, and the unit exchanges the two trees once debmirror has ended without an error, so the served tree is the last sync that passed and a failed sync leaves it as it was. The vendor's repository is read by the sync alone, so a vendor outage delays a Caddy release and breaks no apt refresh. The observability node and the dead-man node install Caddy from that address, the bridgehead from the served tree on its own disk. The copy keeps the vendor's signed `Release`, and apt on each node checks its signature against the vendor key the converge installs at `/etc/apt/keyrings/caddy-archive-keyring.gpg`; Debian's own older `caddy` is pinned out, so a node whose mirror holds no Caddy fails its install rather than taking Debian's. A converge of the observability node or the dead-man node reads the mirror's `Release` before it writes their Caddy source, and refuses in its preview on an answer other than `200`; a `--tags alloy` converge of either reads nothing of the mirror before its apt refresh, so the Alloy procedures of those two nodes read it before one. A new bridgehead's first access converge syncs the mirror before it installs Caddy, so that converge needs the vendor's repository to answer.

### What to do

1. **Sync now**: `ssh access 'sudo systemctl start zaccess-caddy-mirror.service'` returns when the sync has ended, and prints `Job for zaccess-caddy-mirror.service failed` when it failed.
2. **Read the sync's result**: `ssh access 'systemctl show -p Result -p ExecMainExitTimestamp zaccess-caddy-mirror.service'` reads `Result=success` and the time the sync ended. `Result=exit-code` is read by `ssh access 'sudo journalctl -u zaccess-caddy-mirror.service --no-pager -n 50'`: a download from `dl.cloudsmith.io` that failed is the vendor's repository not answering, and the mirror goes on serving the last sync that passed; a line ending `signature does not verify.` goes to the owner, since the vendor has rotated its key and each sync fails there until a change vendors the new one.
3. **Read whether the mirror is current**: `curl -fsS https://apt.zaccess.zhaow.me/dists/any-version/Release | grep '^Date:'` and `curl -fsS https://dl.cloudsmith.io/public/caddy/stable/deb/debian/dists/any-version/Release | grep '^Date:'` print the same `Date:` on a current mirror. A mirror whose `Date:` is more than a month older than the vendor's goes to the owner: its syncs have failed for a month or more.
4. **Read what a node installs from**: `ssh mon 'apt-cache policy caddy'`, or `ssh hc`, names `https://apt.zaccess.zhaow.me any-version/main` under the candidate, and Debian's `caddy` at priority `-1`.
5. **Upgrade the bridgehead's own Caddy**, after step 1, for a Caddy security release the day it is read: `ssh access 'sudo apt-get update && sudo apt-get -o Dpkg::Options::=--force-confold install --only-upgrade caddy && sudo systemctl restart caddy'`. Then `ssh access 'apt-cache policy caddy'` reads the installed version equal to the candidate, `ssh access 'systemctl is-active caddy'` reads `active`, and from the workstation `curl -s -o /dev/null -w '%{http_code}\\n' https://tmux.zaccess.zhaow.me/` prints `000`, the mTLS edge refusing a client without a certificate. A Caddy that does not read `active` goes to the owner, and the mirror keeps the version before, which `apt-cache policy caddy` lists. The observability node and the dead-man node take the release by their patch passes, `mon.md`'s `mon-patch-pass` and `hc.md`'s `hc-patch-pass`, whose package step syncs this mirror first.
6. **A preview refused at the mirror read, or a read of it answering other than `200`**, by the answer. `-1` with `CERTIFICATE_VERIFY_FAILED` is the `apt.` site's certificate, whose renewal `ssh access 'sudo journalctl -u caddy --no-pager -n 200'` shows. `-1` with the connection refused or timed out is the bridgehead's Caddy down, which `ssh access 'systemctl status caddy'` reads, or the bridgehead itself where ssh does not answer, `zaccess-bridgehead-dark` below. `404` is a served tree without a passing sync, which step 1 mends and step 2 reads. An access converge, `infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags access`, mends a bridgehead without the mirror's units alone, `ssh access 'systemctl cat zaccess-caddy-mirror.service'` answering `No files found`, and is taken outside a relay cut, since it reopens a cut SSH relay (`zaccess-cut-ssh-relay` step 3).

### Retire when

`infra/ansible/roles/access/templates/zaccess-caddy-mirror.service.j2` is absent from the tree.

______________________________________________________________________

"""

MIRROR_READ = "`curl -fsS -o /dev/null -w '%{http_code}\\n' https://apt.zaccess.zhaow.me/dists/any-version/Release` from the workstation reads `200`"
SYNC = "`ssh access 'sudo systemctl start zaccess-caddy-mirror.service'`, which returns when the sync has ended; a start that fails is read by `zaccess.md`'s `zaccess-caddy-mirror` steps 2 and 3 before the pass goes on with the last sync that passed, which the mirror still serves"
ALLOY_READ = f" Before it, the bridgehead's Caddy mirror answers: {MIRROR_READ}, and another answer is `zaccess.md`'s `zaccess-caddy-mirror` first, since this converge's apt refresh reads the node's Caddy source, the mirror, and a `--tags alloy` converge reads nothing of the mirror before that refresh."
EDITS = {
    "infra/runbooks/hc.md": [
        (
            " While the Caddy interim of 2026-10-11 stands, a rebuild stops at the edge role's refusal of a node without Caddy, so a dark node is not rebuilt until the owner's debmirror replaces Caddy's apt source. Otherwise: ",
            f" The rebuild installs Caddy from the bridgehead's mirror, so the mirror answers first: {MIRROR_READ}, and another answer sends you to `zaccess.md`'s `zaccess-caddy-mirror` before the rebuild. Then: ",
        ),
        (
            " Docker comes from its vendor's repository, which that origin does not cover, and is upgraded here, by hand, once a month, Caddy too once its source is back: the edge role removes Caddy's repository while Cloudsmith's is out (the interim of 2026-10-11), so Caddy stays at its installed version until the owner's debmirror replaces the source.",
            " Caddy and Docker come from their vendors' repositories, Caddy through the bridgehead's mirror of its repository, which that origin does not cover, and are upgraded here, by hand, once a month.",
        ),
        (
            "a security release of the clone, or of Caddy once its source is back, is taken",
            "a security release of the clone, or of Caddy, is taken",
        ),
        (
            "4. **Upgrade the packages**, on the node: `sudo apt-get update`,",
            f"4. **Upgrade the packages**: first sync the bridgehead's Caddy mirror, {SYNC}; then on the node: `sudo apt-get update`,",
        ),
        (
            " After the Caddy interim of 2026-10-11 merges, the node's first converge is its `--tags hc` one, which removes Caddy's Cloudsmith source that `apt-get update` errors on; a `--tags alloy` converge, an un-tagged converge and this refresh come after it, since an Alloy run before it passes its preview and fails in the real pass at Alloy's apt refresh, a bump with its pin file already moved.",
            "",
        ),
        (
            " After the Caddy interim of 2026-10-11 merges and before the node's `--tags hc` converge has run, this `--tags alloy` converge fails loudly at Alloy's apt refresh on the Cloudsmith source that converge removes: take `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags hc -e hc_image_tag=<the pinned tag>` first.",
            ALLOY_READ,
        ),
    ],
    "infra/runbooks/mon.md": [
        (
            " While the Caddy interim of 2026-10-11 stands, that rebuild stops at the edge role's refusal of a node without Caddy after Grafana and Loki are installed, as drill W3's first Precondition says, so a disk-gone node waits for the owner's debmirror.",
            " That rebuild installs Caddy from the bridgehead's mirror, so the mirror answers first, as drill W3's first Precondition reads, and another answer sends you to `zaccess.md`'s `zaccess-caddy-mirror` before the rebuild.",
        ),
        (
            " Grafana and Loki come from their vendors' repositories, which that origin does not cover, and the two are upgraded here, by hand, once a month, Caddy too once its source is back: the edge role removes Caddy's repository while Cloudsmith's is out (the interim of 2026-10-11), so Caddy stays at its installed version until the owner's debmirror replaces the source;",
            " Grafana, Loki and Caddy come from their vendors' repositories, Caddy through the bridgehead's mirror of its repository, which that origin does not cover, and the three are upgraded here, by hand, once a month;",
        ),
        (
            "2. **Read what would move**, on the node: `sudo apt-get update`, then `apt list --upgradable`. After the Caddy interim of 2026-10-11 merges, the node's first converge is its `--tags mon` one, which removes Caddy's Cloudsmith source that `apt-get update` errors on; a `--tags alloy` converge, an un-tagged converge and this refresh come after it, since an Alloy run before it passes its preview and fails in the real pass at Alloy's apt refresh, a bump with its pin file already moved.",
            f"2. **Read what would move**: first sync the bridgehead's Caddy mirror, {SYNC}; then on the node: `sudo apt-get update`, then `apt list --upgradable`.",
        ),
        (
            " After the Caddy interim of 2026-10-11 merges and before the node's `--tags mon` converge has run, this `--tags alloy` converge fails loudly at Alloy's apt refresh on the Cloudsmith source that converge removes: take `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon` first.",
            ALLOY_READ,
        ),
    ],
    "infra/runbooks/zaccess.md": [
        (
            "ship its Alloy config or cut the public SSH relay: the procedures at the top",
            "ship its Alloy config, cut the public SSH relay or sync its Caddy apt mirror: the procedures at the top",
        ),
        (
            "its preview fetches the Grafana and Caddy repositories' signing keys:",
            "its preview fetches the Grafana repository's signing key:",
        ),
        (
            " After the Caddy interim of 2026-10-11 merges, the bridgehead's first converge is its `--tags access` one, which removes Caddy's Cloudsmith source and is taken outside a relay cut, since it reopens a cut SSH relay (`zaccess-cut-ssh-relay` step 3); this `--tags alloy` converge, an un-tagged converge and a hand `apt-get update` come after it, since an Alloy run before it passes its preview and fails in the real pass at Alloy's apt refresh, a bump with its pin file already moved.",
            "",
        ),
        (
            " After the Caddy interim of 2026-10-11 merges and before the bridgehead's `--tags access` converge has run, that `--tags alloy` converge fails loudly at Alloy's apt refresh on the Cloudsmith source the `--tags access` converge removes: take `infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags access` first, which reopens a cut SSH relay (`zaccess-cut-ssh-relay` step 3); a relay cut on purpose is cut again afterwards by that procedure's steps 1 and 2.",
            "",
        ),
        (
            "2. `du -sh /var/log/* /var/lib/alloy* 2>/dev/null | sort -rh | head` — journald and Alloy's own WAL are the usual growth points on a host this small.",
            "2. `du -sh /var/log/* /var/lib/alloy* /var/lib/caddy-apt-mirror 2>/dev/null | sort -rh | head` — journald and Alloy's own WAL are the usual growth points on a host this small. The Caddy apt mirror holds the vendor's whole release history, about 18 MB more a release, and is not pruned by hand: its signed index names each file in it (`zaccess-caddy-mirror`).",
        ),
        (
            '<a name="zaccess-bridgehead-dark"></a>\n',
            SECTION + '<a name="zaccess-bridgehead-dark"></a>\n',
        ),
    ],
    "infra/runbooks/drills-telemetry.md": [
        (
            "- The owner's debmirror in place of Caddy's apt source: while the interim of 2026-10-11 stands, the rebuild stops at the edge role's refusal of a node without Caddy, after Grafana and Loki are installed.\n",
            f"- The bridgehead's Caddy mirror answers: {MIRROR_READ}, and another answer sends you to `zaccess.md`'s `zaccess-caddy-mirror` before the rebuild. The rebuild installs Caddy from it, and the node's converge refuses in its preview while it does not answer.\n",
        ),
    ],
    "docs/reference/fleet.md": [
        (
            "Caddy mTLS edge, SSH and NAS socket-proxyd relays |",
            "Caddy mTLS edge, SSH and NAS socket-proxyd relays, the Caddy apt mirror |",
        ),
        ("the `tmux.` and `nas.` records and the `CAA`", "the `tmux.`, `nas.` and `apt.` records and the `CAA`"),
        (
            "`:443` (mTLS, require_and_verify); admin `:2019` on localhost |",
            "`:443` (mTLS, require_and_verify; `apt.` public, `/dists/*` and `/pool/*` alone); admin `:2019` on localhost |",
        ),
        (
            "\n| access probe timers |",
            "\n| Caddy apt mirror | zaccess | `zaccess-caddy-mirror.{service,timer}`: daily debmirror of the vendor's Caddy repository, one suite, `amd64`, `main`, into a copy that becomes `/var/lib/caddy-apt-mirror/served` when the sync passes | `https://apt.zaccess.zhaow.me`; zaccess reads `/var/lib/caddy-apt-mirror/served` as a `file:` source, zcrypto-mon and zcrypto-hc the address |\n| access probe timers |",
        ),
    ],
}

root = Path.cwd()
for name, pairs in EDITS.items():
    path = root / name
    text = path.read_text()
    for old, new in pairs:
        assert text.count(old) == 1, (name, old[:60], text.count(old))
        text = text.replace(old, new)
    path.write_text(text)
    print(name, len(pairs))
PYEOF
```

Expected: one line per page, `infra/runbooks/hc.md 6`, `infra/runbooks/mon.md 4`, `infra/runbooks/zaccess.md 6`, `infra/runbooks/drills-telemetry.md 1`, `docs/reference/fleet.md 4`.

- [ ] **Step 3: Read back the anchor and the counts**

```bash
grep -c '<a name="zaccess-caddy-mirror"></a>' infra/runbooks/zaccess.md
infra/scripts/count-list.sh runbook-universals-without-a-count runbook-sections-without-a-trigger runbook-sections-without-a-retire-when runbook-bullets-with-an-internal-token
```

Expected: `1`; each count `0`.

- [ ] **Step 4: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh infra/runbooks/zaccess.md infra/runbooks/hc.md infra/runbooks/mon.md infra/runbooks/drills-telemetry.md docs/reference/fleet.md | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_internal_terms_not_operator_visible.py tests/test_fleet_contracts.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 5: The commit gate and commit**

```bash
git add infra/runbooks/zaccess.md infra/runbooks/hc.md infra/runbooks/mon.md infra/runbooks/drills-telemetry.md docs/reference/fleet.md && uv run pre-commit run -a && git commit -F - <<'EOF'
docs(runbooks): the bridgehead's Caddy mirror procedure, the monthly passes sync it first, the rebuilds and the Alloy-dark re-converges read that it answers, and the interim's order sentences leave the pages

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

Expected: the commit made, its hooks `Passed` or `Skipped`; no guard changes, so no probe; `infra/scripts/prove-inert.py` parses no Markdown, so the message does not call the change prose-only.

- [ ] **Step 6: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 6: The bump-alloy skill's interim line becomes the read of the mirror before an edge node's Alloy converge

**Files:**
- Modify: `.claude/skills/zcrypto-bump-alloy/SKILL.md` (`:90` and the blank line after it)

- [ ] **Step 1: Load `zcrypto-refine-rules`**; read `.claude/skills/zcrypto-bump-alloy/SKILL.md:84-96`, `:229-240` (*Rollback*) and spec 00127 D5, D6, D8 and D9: the once-only order that line carried is the Rollout's from the merge to R6, and its place takes the steady state's read, since a `--tags alloy` converge of mon or hc selects no read of the mirror before Alloy's apt refresh.
- [ ] **Step 2: The edit**

```bash
python3 -I - .claude/skills/zcrypto-bump-alloy/SKILL.md <<'PYEOF'
import sys
path = sys.argv[1]
NEW = (
    "The observability node's and the dead-man node's Alloy refresh reads their Caddy source, the bridgehead's mirror, "
    "and a `--tags alloy` converge reads nothing of the mirror before that refresh: before either node's `--tags alloy` "
    "converge, here or in *Rollback*, `curl -fsS -o /dev/null -w '%{http_code}\\n' https://apt.zaccess.zhaow.me/dists/any-version/Release` "
    "from the workstation reads `200`, and another answer is `infra/runbooks/zaccess.md`'s `zaccess-caddy-mirror` first; "
    "a converge run while the mirror does not answer passes its preview and fails at Alloy's apt refresh, the pin file already moved. "
    "The bridgehead reads its own mirror from disk and takes no such read."
)
text = open(path).read()
start = text.index("Once, after the Caddy interim of 2026-10-11 merges and before the first Alloy wave,")
end = text.index("\n\n", start)
assert text[end + 2 : end + 9] == "```bash", repr(text[end + 2 : end + 22])
open(path, "w").write(text[:start] + NEW + text[end:])
PYEOF
```

- [ ] **Step 3: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh .claude/skills/zcrypto-bump-alloy/SKILL.md | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_guidance_refs_resolve.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 4: The commit gate and commit**

```bash
git add .claude/skills/zcrypto-bump-alloy/SKILL.md && uv run pre-commit run -a && git commit -F - <<'EOF'
claude(skills): the bump-alloy wave's edge-node step reads the bridgehead's Caddy mirror before an edge node's --tags alloy converge, in place of the Caddy interim's once-only role-tagged converge

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

Expected: the commit made, `claude-kind files not mixed with other kinds` `Passed`; the skill's name and description are unchanged, so no `Ambient grows by` line.

- [ ] **Step 5: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 7: The carriers' sweep, the counts, the branch's tests together and the body

- [ ] **Step 1: The interim's carriers are gone**

```bash
git grep -n -e 'interim of 2026-10-11' -e 'caddy-source-absent' -e 'Caddy interim' -e "owner's debmirror" -- infra .claude tests ':!*vault*' ':!*.sops.*' ':!infra/ansible/files/*_ed25519'; echo "rc $?"
```

Expected: `rc 1`, no line.

- [ ] **Step 2: The gate and the counts**

```bash
uv run pre-commit run -a && infra/scripts/count-list.sh probe-verdicts-without-the-script prose-only-commits-without-the-prover
```

Expected: every hook `Passed` or `Skipped`; `prose-only-commits-without-the-prover` `0`; `probe-verdicts-without-the-script` what it read at the branch's base, `1` at `56a855371`, so the branch's own commits add none.

- [ ] **Step 3: The branch's own tests together**

```bash
uv run pytest tests/test_infra_caddy_mirror.py tests/test_infra_edge_role.py tests/test_infra_mon_role.py tests/test_infra_hc_role.py tests/test_infra_converge_guards.py tests/test_access_alloy_tag.py tests/test_mon_alloy_tag.py tests/test_internal_terms_not_operator_visible.py tests/test_fleet_contracts.py tests/test_guidance_refs_resolve.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 4: The pull request body, drafted for R1** in `open-pr`'s shape: `## Spec / Plan` names 00127; the probes; `## Changes` from the diff, the interim's retirement named with the carriers spec D6 lists; the bootstrap verdict, and the spec's three questions with the owner's answers — the two drops and the name — without the read line and its `Fable floor substituted by Opus: <reason>` line, which name a read not yet taken and are R1's.

---

## Rollout (attended)

**Operator steps.** Nothing below is an executor step: each reaches the bridgehead, an edge node, the vendor or DNS. `W$` is a shell on this workstation, `zcrypto-ops`, at the main checkout's root on merged `develop`. None of the three hosts is venue-facing, so no Kraken maintenance window bounds these converges (spec 00127 D8).

**Stop conditions.** A preview that names a file outside the role's Caddy, Alloy and mirror paths holds the rollout until the owner has read it. A first sync that fails, a site that serves anything but the vendor's `Release` byte for byte, or a node's preview refused at the mirror read after R4 passed stops the rollout for the owner; nothing under `/var/lib/caddy-apt-mirror` is edited by hand to get past it.

**R0. Preconditions**, at planning, again immediately before R2, and again at R3, each its own call:
- No Alloy wave open, since each role-tagged converge below lands the committed Alloy: `W$ uv run python infra/scripts/alloy-version.py off-fleet` prints `0`.
- The vendor answers, for the first sync: `W$ curl -fsS -o /dev/null -w '%{http_code}\n' https://dl.cloudsmith.io/public/caddy/stable/deb/debian/dists/any-version/Release` prints `200`.
- The name: the `apt` `A` and `AAAA` records the owner created in the `zaccess.zhaow.me` hosted zone, copies of the apex's, as the `tmux.` and `nas.` records are; `W$ dig +short apt.zaccess.zhaow.me A` prints what `W$ dig +short zaccess.zhaow.me A` prints, and the same for `AAAA`; `[[ROLLOUT: the apt.zaccess.zhaow.me A and AAAA records and their dig reads]]`.
- The disk: `W$ ssh access 'df -B1 --output=size,avail /'`; the available bytes less 15 % of the size, the `zaccess-disk-high` threshold, are at least 1,000,000,000 — the mirror's 567,935,364 bytes with room for its releases; `[[ROLLOUT: the bridgehead's bytes above the disk alert's threshold]]`.
- The relay: no SSH relay cut is in force, since R3's `--tags access` reopens it (`zaccess.md`'s `zaccess-cut-ssh-relay` step 3), or the cut is taken again after R3 by that procedure's steps 1 and 2.
- Each node's Caddy source, read and not changed: `W$ ssh access 'cat /etc/apt/sources.list.d/caddy.sources'`, then `ssh mon …`, then `ssh hc …` — the vendor's `URIs`, or `No such file or directory` where a role converge since the interim's merge removed it; either converges onto the mirror. Then `W$ ssh access 'grep -rlis cloudsmith /etc/apt/sources.list /etc/apt/sources.list.d/'`, then on `mon`, then on `hc`, names `/etc/apt/sources.list.d/caddy.sources` or nothing: a vendor source in another file is one no converge rewrites, and goes to the owner; `[[ROLLOUT: each node's Caddy source before the rollout]]`.
- The dates: the mon monthly pass falls due on 2026-11-04 and hc's on 2026-11-07; R3 to R6 land before them, and R2 holds each node's pass until that node's converge has passed.

**R1. The pull request** (after Task 7). Through `open-pr`, a draft carrying Task 7 Step 4's body; the `pre-review` workflow over the range's prose and messages, then `review` once the branch is complete, `re-review` over a fix range at most twice, every reviewer on Opus; at the undraft, once the review has read the branch, the read line naming that reader and the tip it read, and the `Fable floor substituted by Opus: <reason>` line, which the gate asks for since Task 6 touches `.claude/` (`uv run python infra/scripts/merge-gate.py --fable-paths`).

**R2. The merge**, in the sitting R3 follows, R0's reads passed immediately before it, the vendor's among them. `merge-pr`, then `W$ git switch develop && git pull --ff-only && git status --porcelain`, reading empty. From here until R3 has passed, the bridgehead takes no `--tags access` converge but R3's: the merged role's real pass refreshes apt over the bridgehead's Cloudsmith source and runs the first sync from the vendor before it reaches the pinned leaves and the Caddyfile, so a revocation (`zaccess.md`'s `zaccess-revoke-client-cert` step 2) or a relay's reopen taken in that window waits on the vendor. From here until R6: no `--tags alloy` converge of `zaccess`, `zcrypto-mon` or `zcrypto-hc`, and no Alloy wave — before its role-tagged converge a node may still carry the vendor's source, on which Alloy's apt refresh fails while the vendor is out. No monthly pass on `zcrypto-mon` until R5 has passed, nor on `zcrypto-hc` until R6 has: the merged pass starts the mirror's unit, which R3 writes, and its hand upgrades run before its converge reads the mirror, so a pass taken earlier changes the node and stops half done.

**R3. The bridgehead.** R0's reads again, then:

```bash
infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags access --check
```

Expected: the preview passes; it changes `debmirror` and `gpgv`, the keyring, the user `caddy-mirror`, `/var/lib/caddy-apt-mirror` and its `served` tree, the two units, `/etc/apt/sources.list.d/caddy.sources` (to `URIs: file:/var/lib/caddy-apt-mirror/served`), `/etc/apt/preferences.d/caddy` and the Caddyfile (the `apt.zaccess.zhaow.me` site); it skips the mirror's timer and first sync. Then the same without `--check`: the first sync runs inside the real pass, minutes for 568 MB, and its exchange puts the copy in the served tree. Then, each its own call:

```bash
ssh access 'systemctl show -p Result -p ExecMainExitTimestamp zaccess-caddy-mirror.service'
ssh access 'systemctl is-active zaccess-caddy-mirror.timer'
ssh access 'sudo du -sb /var/lib/caddy-apt-mirror/served/pool'
ssh access 'ls /var/lib/caddy-apt-mirror/served/dists/any-version /var/lib/caddy-apt-mirror/served/dists/any-version/main/binary-amd64'
ssh access 'apt-cache policy caddy'
```

Expected: `Result=success` and a timestamp from the converge; `active`; the pool at 567,935,364 bytes or more by the releases since 2026-10-03; the listing names whether `InRelease` and a `by-hash` directory were copied — the reading of spec D3's and D4's premises; the policy's candidate from `file:/var/lib/caddy-apt-mirror/served any-version/main`, the installed version unchanged, Debian's at `-1`; `[[ROLLOUT: the bridgehead's converge, its first sync's result, the pool's bytes and the copied index files]]`.

**R4. The site, from the workstation**, a minute after R3 for its certificate:

```bash
mkdir -p .tmp/00127-r4 && curl -fsS -o .tmp/00127-r4/Release https://apt.zaccess.zhaow.me/dists/any-version/Release && curl -fsS -o .tmp/00127-r4/Release.gpg https://apt.zaccess.zhaow.me/dists/any-version/Release.gpg
curl -fsS https://dl.cloudsmith.io/public/caddy/stable/deb/debian/dists/any-version/Release | cmp - .tmp/00127-r4/Release; echo "cmp rc $?"
gpgv --keyring infra/ansible/files/caddy-archive-keyring.gpg .tmp/00127-r4/Release.gpg .tmp/00127-r4/Release
curl -s -o /dev/null -w '%{http_code}\n' https://apt.zaccess.zhaow.me/
curl -s -o /dev/null -w '%{http_code}\n' https://apt.zaccess.zhaow.me/dists/
curl -s -o /dev/null -w '%{http_code}\n' https://apt.zaccess.zhaow.me/pool/
curl -s -o /dev/null -w '%{http_code}\n' https://tmux.zaccess.zhaow.me/
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: tmux.zaccess.zhaow.me' https://apt.zaccess.zhaow.me/
```

Expected: both fetches succeed; `cmp rc 0` — the vendor's `Release` byte for byte (a later vendor release between R3 and R4 reads `cmp rc 1`, and a sync by `zaccess.md`'s `zaccess-caddy-mirror` step 1 is taken and the read run again); `Good signature from "Caddy Web Server <contact@caddyserver.com>"`; `404` three times — the site block's behaviour on the bridgehead's own Caddy, which the tests read as text alone, so a listing or a `200` among them stops the rollout before an edge node points at the site; `000` for `tmux.`, the mTLS edge refusing a client without a certificate; and `421` for the `tmux.` Host over the `apt.` name, Caddy's strict SNI-to-Host match on a listener with client auth — a `2xx` or `3xx` there is the tmux site reached without a certificate, and a stop. Then `rm -r .tmp/00127-r4`; `[[ROLLOUT: the served Release against the vendor's, its signature check, the three 404 reads and the two tmux reads]]`.

**R5. The observability node.**

```bash
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags mon --check
```

Expected: the preview passes the mirror read, and changes `caddy.sources` (to `URIs: https://apt.zaccess.zhaow.me`), the keyring and the pin file; it skips the Caddy install and unit, the preview pair's case. Then the same without `--check`, and `ssh mon 'apt-cache policy caddy'`: the candidate from `https://apt.zaccess.zhaow.me any-version/main`, the installed version unchanged, Debian's at `-1`; `[[ROLLOUT: mon's converge and its caddy policy]]`.

**R6. The dead-man node**, the tag read from the `hc` row of `docs/reference/fleet-pins.md`:

```bash
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-hc --tags hc -e hc_image_tag=<the pinned tag> --check
```

Expected: as R5's, on `zcrypto-hc`. Then the same without `--check`, and `ssh hc 'apt-cache policy caddy'`, read as R5's. Then `ssh access 'grep -rlis cloudsmith /etc/apt/sources.list /etc/apt/sources.list.d/'`, then on `mon`, then on `hc`, each its own call, prints nothing: no apt source on the three names the vendor's repository; `[[ROLLOUT: hc's converge, its caddy policy and the three nodes' vendor-source reads]]`.

**R7. The first sync the timer starts**, the day after R3, after 05:00 UTC:

```bash
ssh access 'systemctl show -p Result -p ExecMainStartTimestamp zaccess-caddy-mirror.service'
```

Expected: `Result=success` and debmirror's start between 03:41 and 04:13 UTC that day — the timer's 03:41, its 30-minute random delay, systemd's one-minute timer accuracy, and the hard-linked copy before debmirror; `[[ROLLOUT: the first timer-started sync's result]]`.

**R-records.** A records pull request after R7: the deploy-log rows `converge.sh` appended at R3, R5 and R6; the slots' readings in its message. Caddy is unversioned, so `docs/reference/fleet-pins.md` takes no row.

## Resolution

This plan delivers spec 00127: the bridgehead's daily debmirror copy of the vendor's Caddy repository, its own Caddy installed from that copy on disk, the copy served publicly at `apt.zaccess.zhaow.me`, the edge nodes' Caddy source pointed at it behind a preview-time read, Debian's `caddy` pinned out on all three, a sync that reaches the served copy only when debmirror exits 0, and the interim of 2026-10-11 retired from every carrier spec D6 lists. It drops, on the owner's answers to the spec's questions 1 and 2, a gate for a fresh bridgehead's preview and an alert on the mirror's age or certificate.

## Slots the rollout fills

- `[[ROLLOUT: the apt.zaccess.zhaow.me A and AAAA records and their dig reads]]` (R0).
- `[[ROLLOUT: the bridgehead's bytes above the disk alert's threshold]]` (R0).
- `[[ROLLOUT: each node's Caddy source before the rollout]]` (R0).
- `[[ROLLOUT: the bridgehead's converge, its first sync's result, the pool's bytes and the copied index files]]` (R3) — the reading of the spec's debmirror premises on the host.
- `[[ROLLOUT: the served Release against the vendor's, its signature check, the three 404 reads and the two tmux reads]]` (R4).
- `[[ROLLOUT: mon's converge and its caddy policy]]` (R5).
- `[[ROLLOUT: hc's converge, its caddy policy and the three nodes' vendor-source reads]]` (R6).
- `[[ROLLOUT: the first timer-started sync's result]]` (R7).
