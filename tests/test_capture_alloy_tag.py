"""The capture role's share of the fleet-wide `alloy` tag: a converge that lands the Alloy part on a capture host and nothing
of the capture daemon, read off the YAML the way Ansible selects by tag -- a block's tags reach its children, a role entry's
reach every task of the role, and `always` runs whatever was asked."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from ansible.playbook.task import Task

from tests.test_alloy_version import alloy_version
from tests.test_infra_converge_guards import ANSIBLE, CAPTURE, assert_that, find_task, load_tasks, truthy, when_conditions

TAG = "alloy"
ROLES = ANSIBLE / "roles"
CAPTURE_ROLE = ROLES / "capture"
SITE = ANSIBLE / "site.yml"
FAIL_FAST = "fail fast if an alloy run was not handed the capture host's Alloy digest"

ALLOY_PART = [
    FAIL_FAST,
    "remove the pre-conf layout's stale alloy config",
    "read the deployed alloy config's checksum (drift check — never gated on the digest)",
    "read the repo's alloy config checksum (controller-side, same algorithm)",
    "assert the deployed alloy config matches the repo",
    "refuse an Alloy digest that is not the one committed for this host, unless an alloy_override gives the reason",
    "the alloy_override's reason, on the record",
    "create the zcrypto-alloy system user (nologin, non-key-owning, dedicated to Alloy)",
    "look up the zcrypto-alloy account",
    "derive the zcrypto-alloy uid/gid for the container user mapping",
    "look up the systemd-journal group (Alloy's journal-read group_add needs its numeric gid)",
    "derive the systemd-journal group's numeric gid for the alloy container's group_add",
    "ensure the alloy project directory exists",
    "ensure the alloy data directory exists, owned by the dedicated Alloy user",
    "ensure the alloy config directory exists",
    "install the alloy pipeline config",
    "render the alloy secrets env file",
    "render the alloy compose file",
    "bring the alloy container to the digest, recreated when its secrets file changed",
    "read which image the running alloy container was created from",
    "refuse a converge whose alloy container does not run the digest it converged",
]

# The pre_tasks a `--tags alloy` run executes on the capture and engine plays: every one tagged `always`.
ALWAYS_PRE_TASKS = [
    ("capture_host", "refuse to converge the live primary unless explicitly asked"),
    ("capture_host", "refuse an un-tagged run on the live primary"),
    ("capture_host", "note — assumes bootstrap.yml already ran"),
    ("engine_host", "note — engine_host is deliberately narrower than capture_host"),
]


def _tagged() -> list[tuple[dict, set, tuple]]:
    return [leaf for leaf in alloy_version.walk(load_tasks(CAPTURE)) if TAG in leaf[1]]


def _notify(task: dict) -> list[str]:
    raw = task.get("notify") or []
    return [raw] if isinstance(raw, str) else list(raw)


def _module(task: dict) -> tuple[str, dict]:
    return next((k, v if isinstance(v, dict) else {}) for k, v in task.items() if k.startswith("ansible."))


def _produced(task: dict) -> set[str]:
    names = {task["register"]} if task.get("register") else set()
    names |= set(task.get("ansible.builtin.set_fact") or {})
    if "ansible.builtin.getent" in task:
        names.add(f"getent_{task['ansible.builtin.getent']['database']}")
    return names


def _read_text(task: dict, gates: tuple[str, ...]) -> str:
    body = yaml.safe_dump({k: v for k, v in task.items() if k not in ("name", "register")})
    module, args = _module(task)
    if module == "ansible.builtin.template":
        body += (CAPTURE_ROLE / "templates" / args["src"]).read_text()
    return body + "\n".join(gates)


def test_the_capture_roles_tagged_tasks_are_exactly_its_alloy_part():
    tagged = _tagged()
    assert [task["name"] for task, _, _ in tagged] == ALLOY_PART
    assert {handler for task, _, _ in tagged for handler in _notify(task)} == {"reload alloy"}


def test_every_name_a_tagged_task_reads_is_produced_by_an_earlier_tagged_task():
    """A register, `set_fact` or getent fact read in a gate, an argument or a rendered template: the narrow run skips
    every untagged producer, so a read of one fails that run on an undefined variable or, behind `is defined`, skips its
    task silently."""
    leaves = alloy_version.walk(load_tasks(CAPTURE))
    handlers = load_tasks(CAPTURE_ROLE / "handlers" / "main.yml")
    every = set().union(*(_produced(task) for task, _, _ in leaves), *(_produced(handler) for handler in handlers))
    tagged = [(task, gates) for task, tags, gates in leaves if TAG in tags]
    notified = {handler for task, _ in tagged for handler in _notify(task)}
    available: set[str] = set()
    unproduced = []
    for task, gates in tagged + [(handler, ()) for handler in handlers if handler["name"] in notified]:
        text = _read_text(task, gates)
        reads = {name for name in every if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text)}
        unproduced += [(task["name"], name) for name in sorted(reads - available - _produced(task))]
        available |= _produced(task)
    assert not unproduced, unproduced


CAPTURE_DAEMON_FILES = {"/opt/zcrypto-capture/compose.yaml", "/etc/systemd/system/zcrypto-capture.service"}
CAPTURE_DAEMON_SOURCES = {"compose.yaml.j2", "zcrypto-capture.service"}

# A task the Alloy part takes later joins these lists in that change: the lists, beside the four refusals, are what
# refuse a shape no refusal names.
FREE_MODULES = {f"ansible.builtin.{m}" for m in ("assert", "debug", "stat", "getent", "set_fact")}
WRITERS = {f"ansible.builtin.{m}" for m in ("file", "copy", "template")}
ALLOY_DIR = "{{ capture_alloy_dir }}"
VERBATIM = [
    (
        "ansible.builtin.user",
        {"name": "zcrypto-alloy", "system": True, "shell": "/usr/sbin/nologin", "create_home": False, "state": "present"},
    ),
    (
        "ansible.builtin.command",
        {"cmd": "docker compose up -d{{ ' --force-recreate' if capture_alloy_secrets is changed else '' }}", "chdir": ALLOY_DIR},
    ),
    ("ansible.builtin.command", """docker inspect grafana-alloy --format '{{ "{{" }}.Config.Image{{ "}}" }}'"""),
]


def _module_entry(task: dict) -> tuple[str, object] | None:
    keys = [key for key in task if key not in Task.fattributes and not key.startswith("with_")]
    return (keys[0], task[keys[0]]) if len(keys) == 1 else None


def _on_alloy_paths(path) -> bool:
    return isinstance(path, str) and (path == ALLOY_DIR or path.startswith(ALLOY_DIR + "/")) and ".." not in path.split("/")


def _admitted(task: dict) -> bool:
    entry = _module_entry(task)
    if entry is None:
        return False
    module, value = entry
    if module in FREE_MODULES:
        return True
    if module in WRITERS and isinstance(value, dict):
        written = [value[key] for key in ("path", "dest", "name") if key in value]
        return bool(written) and all(_on_alloy_paths(path) for path in written)
    return entry in VERBATIM


def test_no_tagged_task_reaches_the_capture_daemon():
    for task, _, gates in _tagged():
        assert _admitted(task), task["name"]
        module, args = _module(task)
        assert "restart capture service" not in _notify(task), task["name"]
        assert args.get("dest") not in CAPTURE_DAEMON_FILES and args.get("src") not in CAPTURE_DAEMON_SOURCES, task["name"]
        assert not module.endswith(("systemd", "systemd_service", "service")), task["name"]
        assert "capture_image_digest" not in _read_text(task, gates), task["name"]


def _role_yaml() -> list[Path]:
    return sorted(p for d in ("tasks", "handlers") for p in ROLES.glob(f"*/{d}/*.yml"))


def _every_tag(node) -> set[str]:
    if isinstance(node, list):
        return set().union(set(), *(_every_tag(item) for item in node))
    if isinstance(node, dict):
        return alloy_version.tags_of(node).union(*(_every_tag(value) for value in node.values()))
    return set()


def test_only_the_roles_that_joined_the_tag_carry_it_and_no_play_does():
    """The tag is shared by name, so another role joins it deliberately, with its own guards beside these: this list
    widens in that change."""
    carriers = [p for p in [*_role_yaml(), SITE, ANSIBLE / "bootstrap.yml"] if TAG in _every_tag(load_tasks(p))]
    assert carriers == [CAPTURE, ROLES / "nas" / "tasks" / "main.yml"], carriers


def _selected(tags: set[str]) -> bool:
    return "always" in tags or TAG in tags


def test_an_alloy_run_on_the_capture_and_engine_plays_runs_the_alloy_part_beside_the_always_pre_tasks():
    """Ansible's selection over every play that reaches a capture host: an `always` task in any of their roles would
    run on the primary beside the Alloy part, and only the four pre_tasks below may."""
    pre_tasks, role_tasks = [], []
    for play in load_tasks(SITE):
        if play["hosts"] not in ("capture_host", "engine_host"):
            continue
        play_tags = alloy_version.tags_of(play)
        pre_tasks += [
            (play["hosts"], t["name"])
            for t, tags, _ in alloy_version.walk(play.get("pre_tasks"), frozenset(play_tags))
            if _selected(tags)
        ]
        for entry in play["roles"]:
            inherited = frozenset(play_tags | alloy_version.tags_of(entry))
            for task, tags, _ in alloy_version.walk(load_tasks(ROLES / entry["role"] / "tasks" / "main.yml"), inherited):
                if _selected(tags):
                    role_tasks.append((entry["role"], task["name"]))
    assert pre_tasks == ALWAYS_PRE_TASKS
    assert role_tasks == [("capture", name) for name in ALLOY_PART]


def test_the_narrow_run_still_takes_the_primarys_explicit_yes():
    tasks = load_tasks(SITE)
    on_primary = {"inventory_hostname": "zcrypto", "groups": {"engine_host": ["zcrypto"]}}
    refusal = find_task(tasks, "refuse to converge the live primary unless explicitly asked")
    assert truthy(when_conditions(refusal), on_primary)
    assert not truthy(assert_that(refusal), {})
    assert truthy(assert_that(refusal), {"converge_primary": "true"})
    untagged = find_task(tasks, "refuse an un-tagged run on the live primary")
    assert truthy(assert_that(untagged), {"ansible_run_tags": [TAG], "ansible_skip_tags": []})


@pytest.mark.parametrize("seq", [tuple, list])
@pytest.mark.parametrize(
    ("run_tags", "digest", "engages", "passes"),
    [
        ([TAG], None, True, False),
        ([TAG], "", True, False),
        ([TAG], "sha256:" + "a" * 64, True, True),
        (["capture", TAG], None, True, False),
        (["capture"], None, False, False),
        (["all"], None, False, False),
        (["capture", "engine"], None, False, False),
    ],
)
def test_an_alloy_run_refuses_without_the_capture_alloy_digest_and_no_other_run_meets_that_refusal(
    seq, run_tags, digest, engages, passes
):
    task = find_task(load_tasks(CAPTURE), FAIL_FAST)
    assert truthy(when_conditions(task), {"ansible_run_tags": seq(run_tags)}) is engages
    assert truthy(assert_that(task), {} if digest is None else {"capture_alloy_digest": digest}) is passes
