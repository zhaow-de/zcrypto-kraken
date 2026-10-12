"""The bridgehead's Caddy apt mirror and the Caddy sources that read it: what the access role syncs, serves and installs
from, and what every role pins Caddy's candidates to."""

from __future__ import annotations

import hashlib
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

from tests import role_render
from tests.test_infra_converge_guards import find_task, iter_tasks, load_tasks, set_facts, task_index, truthy, when_conditions

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra/ansible"
ACCESS = ANSIBLE / "roles/access"
ACCESS_TASKS = ACCESS / "tasks/main.yml"
EDGE_SOURCE = ANSIBLE / "roles/edge/tasks/caddy-source.yml"
KEYRING = ANSIBLE / "files/caddy-archive-keyring.gpg"
KEYRING_SHA256 = "c17cd5298a0bab02fda439fff278d9a55df2120cf9dac790c6ce71930db90b37"
UNVAULTED = (":!*vault.yml", ":!*.vault", ":!*.sops.*", ":!*vault-password*", ":!infra/ansible/files/*_ed25519")
ALL = yaml.safe_load((ANSIBLE / "group_vars/all/vars.yml").read_text())
MIRROR = {key: ALL[key] for key in ("caddy_mirror_host", "caddy_mirror_keyring")}
PIN = "Package: caddy\nPin: release o=Debian\nPin-Priority: -1\n"
SERVED, STAGING = "/var/lib/caddy-apt-mirror/served", "/var/lib/caddy-apt-mirror/staging"

DEBMIRROR = "debmirror and gpgv present — the mirror's tool and its signature check, both from Debian"
KEY = "the Caddy vendor key the mirror and apt verify its Release with"
EDGE_KEY = "the Caddy vendor key apt verifies the mirror's Release with"
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


@pytest.mark.parametrize(("path", "name"), [(ACCESS_TASKS, KEY), (EDGE_SOURCE, EDGE_KEY)], ids=["access", "edge"])
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
    # Closed: systemd runs ExecStartPost after any status SuccessExitStatus= lists, so a new key can exchange a failed sync in.
    assert set(unit) == {
        "Description",
        "Wants",
        "After",
        "Type",
        "User",
        "Group",
        "UMask",
        "TimeoutStartSec",
        "ExecStartPre",
        "ExecStart",
        "ExecStartPost",
        "ProtectSystem",
        "ReadWritePaths",
        "PrivateTmp",
        "NoNewPrivileges",
    }, sorted(unit)


def test_the_sync_runs_daily_and_a_day_the_bridgehead_was_down_runs_at_its_next_start():
    timer = _unit("zaccess-caddy-mirror.timer.j2")
    assert {key: values for key, values in timer.items() if key != "Description"} == {
        "OnCalendar": ["*-*-* 03:41:00"],
        "RandomizedDelaySec": ["30min"],
        "Persistent": ["true"],
        "Unit": ["zaccess-caddy-mirror.service"],
        "WantedBy": ["timers.target"],
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
    # One source in the file: a second, built from the upstream defaults, would read the vendor without naming it.
    deb822 = "ansible.builtin.deb822_repository"
    (source,) = [task[deb822] for task, _ in iter_tasks(tasks) if deb822 in task]
    assert find_task(tasks, SOURCE)[deb822] == source
    assert source == {
        "name": "caddy",
        "types": ["deb"],
        "uris": "file:{{ access_caddy_mirror_served }}",
        "suites": ["any-version"],
        "components": ["main"],
        "signed_by": "{{ caddy_mirror_keyring }}",
        "install_python_debian": True,
    }


@pytest.mark.parametrize(("exists", "runs"), [(False, True), (True, False)])
def test_the_first_sync_runs_on_an_empty_mirror_and_never_in_a_preview(exists, runs):
    tasks = load_tasks(ACCESS_TASKS)
    sync = find_task(tasks, FIRST_SYNC)
    # Closed: a check_mode: false would run the sync in a preview, an ignore_errors let a failed one through.
    assert set(sync) == {"name", "ansible.builtin.command", "changed_when", "when"}, sorted(sync)
    assert sync["ansible.builtin.command"] == "systemctl start zaccess-caddy-mirror.service"
    release = find_task(tasks, RELEASE)
    assert release["ansible.builtin.stat"] == {"path": "{{ access_caddy_mirror_served }}/dists/any-version/Release"}
    assert release["register"] == "access_caddy_mirror_release"
    assert truthy(when_conditions(sync), {"access_caddy_mirror_release": {"stat": {"exists": exists}}}) is runs


@pytest.mark.parametrize(
    ("check", "units", "previewed"),
    [(True, {"changed": True}, True), (True, {"changed": False}, False), (False, {"changed": True}, False)],
)
def test_the_timer_skips_the_preview_that_has_not_written_its_unit(check, units, previewed):
    tasks = load_tasks(ACCESS_TASKS)
    assert find_task(tasks, UNITS)["register"] == "access_caddy_mirror_units"
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
@pytest.mark.parametrize("path", [ACCESS_TASKS, EDGE_SOURCE], ids=["access", "edge"])
def test_debians_own_caddy_is_never_a_candidate(path):
    pin = find_task(load_tasks(path), DEBIAN_PIN)["ansible.builtin.copy"]
    assert pin == {"content": PIN, "dest": "/etc/apt/preferences.d/caddy", "owner": "root", "group": "root", "mode": "0644"}


def test_the_bridgehead_installs_caddy_never_forced_or_held():
    tasks = iter_tasks(load_tasks(ACCESS_TASKS))
    modules = ("ansible.builtin.apt", "ansible.builtin.dpkg_selections")
    caddy = [task[module] for task, _ in tasks for module in modules if task.get(module, {}).get("name") == "caddy"]
    assert caddy == [{"name": "caddy", "state": "present", "update_cache": True}, {"name": "caddy", "selection": "install"}], caddy


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
    caddyfile = _caddyfile()
    importing = [name for name, body in caddyfile.items() if ("import mtls", []) in body]
    assert importing == ["tmux.zaccess.zhaow.me", "nas.zaccess.zhaow.me"], importing
    # A global `servers { strict_sni_host insecure_off }` lets a client with no certificate reach these sites under the apt. name.
    assert [line.split()[0] for line, _ in caddyfile[""]] == ["email"], caddyfile[""]
    tls = dict(caddyfile["(mtls)"])["tls"]
    assert ("mode require_and_verify", []) in dict(tls)["client_auth"], tls


# --- the vendor's repository: read by the sync alone ------------------------------------------------------------------
def test_the_vendors_repository_is_named_by_the_mirrors_upstream_alone():
    # The excludes stand alone: beside an `infra/ansible` pathspec, `git ls-files` misapplies them.
    listed = subprocess.run(["git", "ls-files", "-z", "--full-name", "--", *UNVAULTED], cwd=REPO, capture_output=True, check=True)
    files = [(REPO / name).relative_to(ANSIBLE) for name in listed.stdout.decode().split("\0") if name.startswith("infra/ansible/")]
    tops = {path.parts[0] for path in files}
    assert {"files", "group_vars", "host_vars", "roles"} <= tops, sorted(tops)
    hits = sorted(str(path) for path in files if b"cloudsmith" in (ANSIBLE / path).read_bytes().lower())
    assert hits == ["roles/access/defaults/main.yml"], hits
