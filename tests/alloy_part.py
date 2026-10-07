"""A role's Alloy part under the fleet-wide `alloy` tag, read through `alloy-version.py`'s walk: the tagged leaves, the names they read before a tagged task produces them, the allowlists the roles' exclusions hold them to beside their own named refusals, and what a play runs under the tag."""

from __future__ import annotations

import re
from collections.abc import Callable

import yaml
from ansible.playbook.task import Task

from tests.test_alloy_version import alloy_version
from tests.test_infra_converge_guards import ANSIBLE, load_tasks

TAG = "alloy"
ROLES = ANSIBLE / "roles"
SITE = ANSIBLE / "site.yml"


def tagged(role: str) -> list[tuple[dict, set, tuple]]:
    return [leaf for leaf in alloy_version.role_leaves(role, frozenset()) if TAG in leaf[1]]


def notified(task: dict) -> list[str]:
    raw = task.get("notify") or []
    return [raw] if isinstance(raw, str) else list(raw)


def module_and_args(task: dict) -> tuple[str, dict]:
    return next((k, v if isinstance(v, dict) else {}) for k, v in task.items() if k.startswith("ansible."))


def produced(task: dict) -> set[str]:
    names = {task["register"]} if task.get("register") else set()
    names |= set(task.get("ansible.builtin.set_fact") or {})
    if "ansible.builtin.getent" in task:
        names.add(f"getent_{task['ansible.builtin.getent']['database']}")
    return names


def task_text(task: dict, gates: tuple[str, ...]) -> str:
    return yaml.safe_dump({k: v for k, v in task.items() if k not in ("name", "register")}) + "\n".join(gates)


def read_text(role: str, task: dict, gates: tuple[str, ...]) -> str:
    module, args = module_and_args(task)
    template = (ROLES / role / "templates" / args["src"]).read_text() if module == "ansible.builtin.template" else ""
    return task_text(task, ()) + template + "\n".join(gates)


def unproduced_reads(role: str) -> list[tuple[str, str]]:
    """A register, `set_fact` or getent fact read in a gate, an argument or a rendered template: the narrow run skips
    every untagged producer, so a read of one fails that run on an undefined variable or, behind `is defined`, skips its
    task silently."""
    leaves = alloy_version.role_leaves(role, frozenset())
    handlers = load_tasks(ROLES / role / "handlers" / "main.yml")
    every = set().union(*(produced(task) for task, _, _ in leaves), *(produced(handler) for handler in handlers))
    tagged_leaves = [(task, gates) for task, tags, gates in leaves if TAG in tags]
    notifies = {handler for task, _ in tagged_leaves for handler in notified(task)}
    available: set[str] = set()
    unproduced = []
    for task, gates in tagged_leaves + [(handler, ()) for handler in handlers if handler["name"] in notifies]:
        text = read_text(role, task, gates)
        reads = {name for name in every if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text)}
        unproduced += [(task["name"], name) for name in sorted(reads - available - produced(task))]
        available |= produced(task)
    return unproduced


# A task the Alloy part takes later joins these lists in that change: the lists, beside each role's named refusals, are
# what refuse a shape no refusal names.
FREE_MODULES = {f"ansible.builtin.{m}" for m in ("assert", "debug", "stat", "getent", "set_fact")}
WRITERS = {f"ansible.builtin.{m}" for m in ("file", "copy", "template")}
# `args` merges into the module's arguments and `environment` into the command's process, past the module key the lists read.
ARGUMENT_KEYWORDS = ("args", "environment")


def alloy_dir(role: str) -> str:
    return "{{ " + f"{role}_alloy_dir" + " }}"


# A role's own verbatim task beside the three every container role shares: the cache role's Alloy block probes the digest
# its recreate replaces, for the pins-recording refusal that follows.
ROLE_VERBATIM = {
    "cache": [("ansible.builtin.command", """docker inspect --format '{{ "{{" }}.Config.Image{{ "}}" }}' grafana-alloy""")],
}


def verbatim(role: str) -> list[tuple[str, object]]:
    return ROLE_VERBATIM.get(role, []) + [
        (
            "ansible.builtin.user",
            {"name": "zcrypto-alloy", "system": True, "shell": "/usr/sbin/nologin", "create_home": False, "state": "present"},
        ),
        (
            "ansible.builtin.command",
            {
                "cmd": "docker compose -f compose.yaml up -d"
                f"{{{{ ' --force-recreate' if {role}_alloy_secrets is changed else '' }}}}",
                "chdir": alloy_dir(role),
            },
        ),
        ("ansible.builtin.command", """docker inspect grafana-alloy --format '{{ "{{" }}.Config.Image{{ "}}" }}'"""),
    ]


# The shared role's share of each apt importer's exclusion allowlist, written out and never read from the role, so an
# edit to the role fails every importer's exclusion case until these move with it.
ALLOY_APT_FREE = {f"ansible.builtin.{m}" for m in ("assert", "debug", "set_fact")}
ALLOY_APT_VERBATIM = [
    (
        "ansible.builtin.deb822_repository",
        {
            "name": "grafana",
            "types": ["deb"],
            "uris": "https://apt.grafana.com",
            "suites": ["stable"],
            "components": ["main"],
            "signed_by": "https://apt.grafana.com/gpg.key",
            "install_python_debian": True,
        },
    ),
    (
        "ansible.builtin.copy",
        {
            "content": "Package: alloy\nPin: version {{ alloy_deb_version }}\nPin-Priority: 1001\n",
            "dest": "/etc/apt/preferences.d/alloy",
            "owner": "root",
            "group": "root",
            "mode": "0644",
        },
    ),
    (
        "ansible.builtin.apt",
        {
            "name": "alloy={{ alloy_deb_version }}",
            "state": "present",
            "update_cache": True,
            "allow_downgrade": True,
            "allow_change_held_packages": True,
        },
    ),
    ("ansible.builtin.dpkg_selections", {"name": "alloy", "selection": "hold"}),
    ("ansible.builtin.meta", "flush_handlers"),
    (
        "ansible.builtin.shell",
        {
            "cmd": "set -o pipefail\n"
            "pid=$(systemctl show -p MainPID --value alloy)\n"
            'if [ -z "$pid" ] || [ "$pid" = "0" ]; then echo __not_running__; else readlink "/proc/$pid/exe"; fi\n',
            "executable": "/bin/bash",
        },
    ),
    ("ansible.builtin.systemd_service", {"name": "alloy", "state": "restarted"}),
]


def module_entry(task: dict) -> tuple[str, object] | None:
    keys = [key for key in task if key not in Task.fattributes and not key.startswith("with_")]
    return (keys[0], task[keys[0]]) if len(keys) == 1 else None


def on_alloy_paths(path, role: str) -> bool:
    root = alloy_dir(role)
    return isinstance(path, str) and (path == root or path.startswith(root + "/")) and ".." not in path.split("/")


def admitted(task: dict, role: str) -> bool:
    entry = module_entry(task)
    if entry is None:
        return False
    module, value = entry
    if module in FREE_MODULES:
        return True
    if module in WRITERS and isinstance(value, dict):
        written = [value[key] for key in ("path", "dest", "name") if key in value]
        return bool(written) and all(on_alloy_paths(path, role) for path in written)
    return entry in verbatim(role)


def apt_admitted(task: dict, writers: set[str], on_paths: Callable[[object], bool], own_verbatim: list) -> bool:
    entry = module_entry(task)
    if entry is None:
        return False
    module, value = entry
    if module in ALLOY_APT_FREE or entry in ALLOY_APT_VERBATIM or entry in own_verbatim:
        return True
    if module in writers and isinstance(value, dict):
        written = [value[key] for key in ("path", "dest", "name") if key in value]
        return bool(written) and all(on_paths(path) for path in written)
    return False


def refusal_of(task: dict, role: str) -> str | None:
    carried = [key for key in ARGUMENT_KEYWORDS if key in task]
    if carried:
        return f"{task['name']}: carries {' and '.join(carried)}"
    return None if admitted(task, role) else f"{task['name']}: not on the Alloy part's allowlist"


def _selected(tags: set[str]) -> bool:
    return "always" in tags or TAG in tags


def play_selection(*hosts: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """What `--tags alloy` runs on the plays of `site.yml` whose `hosts` is one of these: `(hosts, name)` per pre_task,
    `(role, name)` per role task."""
    pre_tasks, role_tasks = [], []
    for play in load_tasks(SITE):
        if play["hosts"] not in hosts:
            continue
        play_tags = alloy_version.tags_of(play)
        pre_tasks += [
            (play["hosts"], t["name"])
            for t, tags, _ in alloy_version.walk(play.get("pre_tasks"), frozenset(play_tags))
            if _selected(tags)
        ]
        for entry in play["roles"]:
            inherited = frozenset(play_tags | alloy_version.tags_of(entry))
            for task, tags, _ in alloy_version.role_leaves(entry["role"], inherited):
                if _selected(tags):
                    role_tasks.append((entry["role"], task["name"]))
    return pre_tasks, role_tasks
