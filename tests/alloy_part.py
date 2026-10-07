"""A role's Alloy part under the fleet-wide `alloy` tag, read through `alloy-version.py`'s walk, and the sets its exclusions hold it to."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import yaml
from ansible.playbook.handler import Handler
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


def topics(handler: dict) -> set[str]:
    raw = handler.get("listen") or []
    return {topic for topic in (handler.get("name"), *([raw] if isinstance(raw, str) else raw)) if topic}


INCLUDE_TASKS = ("ansible.builtin.include_tasks", "ansible.legacy.include_tasks", "include_tasks")


def _spliced(path: Path, directory: Path) -> list[dict]:
    handlers = []
    for entry in load_tasks(path) or []:
        imported = next((key for key in alloy_version.IMPORT_TASKS if key in entry), None)
        if imported is None:
            handlers.append(entry)
            continue
        target = entry[imported]
        handlers += _spliced(directory / (target["file"] if isinstance(target, dict) else target), directory)
    return handlers


def role_handlers(role: str, stem: str | None = None) -> list[dict]:
    """The role's handlers file and its static imports, where Ansible's `Role._load_role_yaml` and
    `path_dwim_relative` look first."""
    directory = ROLES / role / "handlers"
    extensions = ("", ".yml", ".yaml", ".json") if stem else (".yml", ".yaml", ".json", "")
    found = [directory / f"{stem or 'main'}{ext}" for ext in extensions if (directory / f"{stem or 'main'}{ext}").is_file()]
    return _spliced(found[0], directory) if found else []


def _role_imports(tasks, base: Path, seen: set) -> list[tuple[str, str | None]]:
    imports = []
    for task in tasks or []:
        role = next((key for key in alloy_version.IMPORT_ROLE if key in task), None)
        imported = next((key for key in alloy_version.IMPORT_TASKS if key in task), None)
        if role:
            entry = (task[role]["name"], task[role].get("handlers_from"))
            path = alloy_version._role_tasks(ROLES, task[role])
            if (entry, path) not in seen:
                seen.add((entry, path))
                imports += [entry, *_role_imports(load_tasks(path), path.parent, seen)]
        elif imported:
            path = base / task[imported]
            imports += _role_imports(load_tasks(path), path.parent, seen)
        else:
            imports += [entry for key in STRUCTURE for entry in _role_imports(task.get(key), base, seen)]
    return imports


def play_handlers(role: str) -> list[dict]:
    """Each handler of a play that runs the role: Ansible puts every role entry's handlers in its play's scope, and
    those of each role a static `import_role` in their tasks brings, where a notify reaches one by its name or a
    `listen` topic."""
    handlers = []
    for play in load_tasks(SITE):
        roles = [entry["role"] for entry in play.get("roles") or []]
        if role in roles:
            sources = dict.fromkeys((name, None) for name in roles)
            for name in roles:
                path = alloy_version._role_tasks(ROLES, {"name": name})
                sources |= dict.fromkeys(_role_imports(load_tasks(path), path.parent, set()))
            handlers += (play.get("handlers") or []) + [h for name, stem in sources for h in role_handlers(name, stem)]
    return handlers


def reached_handlers(role: str) -> list[dict]:
    notifies = {handler for task, _, _ in tagged(role) for handler in notified(task)}
    return [handler for handler in play_handlers(role) if topics(handler) & notifies]


def unproduced_reads(role: str) -> list[tuple[str, str]]:
    """A register, `set_fact` or getent fact read in a gate, an argument or a rendered template: the narrow run skips
    every untagged producer, so a read of one fails that run on an undefined variable or, behind `is defined`, skips its
    task silently."""
    leaves = alloy_version.role_leaves(role, frozenset())
    reached = reached_handlers(role)
    handlers = role_handlers(role) + reached
    every = set().union(*(produced(task) for task, _, _ in leaves), *(produced(handler) for handler in handlers))
    tagged_leaves = [(task, gates) for task, tags, gates in leaves if TAG in tags]
    available: set[str] = set()
    unproduced = []
    for task, gates in tagged_leaves + [(handler, ()) for handler in reached]:
        text = read_text(role, task, gates)
        reads = {name for name in every if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text)}
        unproduced += [(task["name"], name) for name in sorted(reads - available - produced(task))]
        available |= produced(task)
    return unproduced


# A task the Alloy part takes later joins these lists in that change: the lists, beside each role's named refusals, are
# what refuse a shape no refusal names.
FREE_MODULES = {f"ansible.builtin.{m}" for m in ("assert", "debug", "stat", "getent", "set_fact")}
WRITER_ARGUMENTS = {
    "ansible.builtin.file": {"path", "state", "owner", "group", "mode"},
    "ansible.builtin.copy": {"src", "dest", "owner", "group", "mode"},
    "ansible.builtin.template": {"src", "dest", "owner", "group", "mode"},
}
WRITERS = set(WRITER_ARGUMENTS)

# The keywords each level carries where the tag runs, a keyword off its level's set refused by its name: `args`,
# `environment`, `module_defaults` and the like reach a module or its process past the module key the lists read, at
# any level from the play down. A keyword a level takes later joins its set in that change.
PLAY_KEYS = {"name", "hosts", "become", "pre_tasks", "roles"}
ROLE_ENTRY_KEYS = {"role", "tags"}
ENCLOSING_KEYS = {"name", "tags", "when", "block"}
TASK_KEYS = {
    *("name", "tags", "when", "register", "notify", "changed_when", "failed_when"),
    *("no_log", "diff", "become", "delegate_to", "check_mode", "vars"),
}
HANDLER_KEYS = {"name", "register", "changed_when", "when"}
ALLOY_HANDLERS = [
    ("ansible.builtin.uri", {"url": "http://127.0.0.1:12345/-/reload", "method": "POST", "status_code": [200, -1]}),
    ("ansible.builtin.systemd", {"name": "alloy", "state": "restarted"}),
    ("ansible.builtin.systemd_service", {"name": "alloy", "state": "restarted"}),
]


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


def module_entry(task: dict, attributes=Task.fattributes) -> tuple[str, object] | None:
    keys = [key for key in task if key not in attributes and not key.startswith("with_")]
    return (keys[0], task[keys[0]]) if len(keys) == 1 else None


def off_keys(node: dict, keys: set[str], attributes=Task.fattributes) -> list[str]:
    module = (module_entry(node, attributes) or (None,))[0]
    return sorted(set(node) - keys - {module})


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


def carried(task: dict) -> list[str]:
    module, value = module_entry(task) or (None, None)
    off = off_keys(task, TASK_KEYS)
    if module in WRITER_ARGUMENTS and isinstance(value, dict):
        off += sorted(set(value) - WRITER_ARGUMENTS[module])
    return off


def refusal_of(task: dict, role: str) -> str | None:
    if off := carried(task):
        return f"{task['name']}: carries {' and '.join(off)}"
    return None if admitted(task, role) else f"{task['name']}: not on the Alloy part's allowlist"


STRUCTURE = ("block", "rescue", "always")
IMPORTS = {*alloy_version.IMPORT_ROLE, *alloy_version.IMPORT_TASKS}


def _enclosing(tasks, tags: frozenset[str], base) -> list[dict]:
    found = []
    for task in tasks or []:
        if not any(TAG in leaf_tags for _, leaf_tags, _ in alloy_version.walk([task], tags, roles_dir=ROLES, base=base)):
            continue
        own = frozenset(tags | alloy_version.tags_of(task))
        role = next((key for key in alloy_version.IMPORT_ROLE if key in task), None)
        imported = next((key for key in alloy_version.IMPORT_TASKS if key in task), None)
        if role or imported:
            path = alloy_version._role_tasks(ROLES, task[role]) if role else base / task[imported]
            found += [task, *_enclosing(load_tasks(path), own, path.parent)]
        elif any(key in task for key in STRUCTURE):
            found += [task, *(inner for key in STRUCTURE for inner in _enclosing(task.get(key), own, base))]
    return found


def scope_refusals(role: str) -> list[str]:
    """The levels above a tagged task: a play that runs the role, the role's entry there, and each block or import that
    hands its keywords to a tagged task."""
    nodes = []
    for play in load_tasks(SITE):
        entries = [entry for entry in play.get("roles") or [] if entry["role"] == role]
        if entries:
            nodes += [(play["name"], play, PLAY_KEYS), *((role, entry, ROLE_ENTRY_KEYS) for entry in entries)]
    path = alloy_version._role_tasks(ROLES, {"name": role})
    statements = _enclosing(load_tasks(path), frozenset(), path.parent)
    nodes += [(statement["name"], statement, ENCLOSING_KEYS | IMPORTS) for statement in statements]
    return [f"{name}: carries {' and '.join(off)}" for name, node, keys in nodes if (off := sorted(set(node) - keys))]


INCLUDE_ROLE = ("ansible.builtin.include_role", "ansible.legacy.include_role", "include_role")
NOT_HANDLERS = (*STRUCTURE, *INCLUDE_TASKS, *INCLUDE_ROLE, *alloy_version.IMPORT_ROLE)


def handler_refusals(role: str) -> list[str]:
    """An entry among the play's handlers that is no handler — a block, `rescue` or `always`, an `include_tasks`, an
    `include_role` or an `import_role`, at any level the read loads — is refused: this read cannot see what it brings."""
    refusals = [
        f"{handler.get('name')}: carries {key}" for handler in play_handlers(role) for key in NOT_HANDLERS if key in handler
    ]
    for handler in reached_handlers(role):
        if module_entry(handler, Handler.fattributes) not in ALLOY_HANDLERS:
            refusals.append(f"{handler.get('name')}: answers an Alloy notify and is not an Alloy handler")
        elif off := off_keys(handler, HANDLER_KEYS, Handler.fattributes):
            refusals.append(f"{handler.get('name')}: carries {' and '.join(off)}")
    return refusals


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
            for t, tags, _ in alloy_version.walk(play.get("pre_tasks"), frozenset(play_tags), base=ANSIBLE)
            if _selected(tags)
        ]
        for entry in play["roles"]:
            inherited = frozenset(play_tags | alloy_version.tags_of(entry))
            for task, tags, _ in alloy_version.role_leaves(entry["role"], inherited):
                if _selected(tags):
                    role_tasks.append((entry["role"], task["name"]))
    return pre_tasks, role_tasks
