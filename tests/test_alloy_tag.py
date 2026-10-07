"""The fleet-wide `alloy` tag over every play, which converge.sh's refusal of an `alloy` run that would land nothing reads."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

import pytest

from tests import alloy_part
from tests.alloy_part import ROLES, SITE, TAG
from tests.test_alloy_version import alloy_version
from tests.test_infra_converge_guards import ANSIBLE, REPO, load_tasks
from tests.test_pins_converged import pins


def test_every_observed_host_has_a_play_that_runs_an_alloy_task():
    observed = pins.inventory_groups(REPO).get("observed")
    assert observed, "the inventory's observed group has no host"
    unreached = sorted(host for host in observed if not alloy_version.reaches(host))
    assert not unreached, unreached


# By each play's `hosts`: the engine play carries no Alloy part, its host's is the capture play's.
ALLOY_ROLE = {
    "capture_host": "capture",
    "engine_host": None,
    "ops_host": "ops",
    "nas_host": "nas",
    "access_host": "access",
    "cache_host": "cache",
    "mon_host": "mon",
}
NO_ALLOY_TASK = {"base", "hardening", "firewall", "fail2ban", "chrony", "docker", "cache_link", "access_ops", "engine"}


def test_an_alloy_run_runs_each_plays_always_tasks_and_its_alloy_part_and_nothing_else():
    plays = load_tasks(SITE)
    assert [play["hosts"] for play in plays] == list(ALLOY_ROLE)
    groups = pins.inventory_groups(REPO)
    for play in plays:
        host = min(groups[play["hosts"]])
        reaching = {other["hosts"] for other in alloy_version.plays_reaching(host)}
        selected = alloy_version.selection(host, [TAG])
        roles = {where for where, _ in selected if where not in reaching}
        assert not roles & NO_ALLOY_TASK, (host, sorted(roles & NO_ALLOY_TASK))
        assert roles == {ALLOY_ROLE[hosts] for hosts in reaching} - {None}, (host, sorted(roles))
        play_tasks = [leaf for leaf in selected if leaf[0] in reaching]
        assert play_tasks == [leaf for leaf in alloy_version.selection(host, ["always"]) if leaf[0] in reaching], host


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
    assert carriers == [
        ROLES / "access" / "tasks" / "main.yml",
        ROLES / "cache" / "tasks" / "main.yml",
        ROLES / "capture" / "tasks" / "main.yml",
        ROLES / "mon" / "tasks" / "main.yml",
        ROLES / "nas" / "tasks" / "main.yml",
        ROLES / "ops" / "tasks" / "main.yml",
    ], carriers


SHARED = ROLES / "alloy_apt"
PACKAGE_MODULES = ("apt", "package", "dpkg_selections")
ALLOY_PACKAGE = re.compile(r"alloy(?:[<>=].*)?")


def _statements(tasks) -> list[dict]:
    """Each task as written, a block's children among them: an import or an include is one statement, unfollowed."""
    out = []
    for task in tasks or []:
        out.append(task)
        for key in ("block", "rescue", "always"):
            out += _statements(task.get(key))
    return out


def _task_statements() -> list[tuple[Path, dict]]:
    play_tasks = [
        task
        for play in load_tasks(SITE)
        for section in ("pre_tasks", "tasks", "post_tasks", "handlers")
        for task in _statements(play.get(section))
    ]
    return [(SITE, task) for task in play_tasks] + [(p, task) for p in _role_yaml() for task in _statements(load_tasks(p))]


def _calls(task: dict, *modules: str) -> list[tuple[str, object]]:
    return [(key, value) for key, value in task.items() if key.rsplit(".", 1)[-1] in modules]


def _names_alloy(args) -> bool:
    if not isinstance(args, dict):
        return False
    values = [args[key] for key in ("name", "pkg", "package") if key in args]
    items = [item for value in values for item in (value if isinstance(value, list) else str(value).split(","))]
    return any(ALLOY_PACKAGE.fullmatch(str(item).strip()) for item in items)


def _includes_the_shared_role(module: str, args) -> bool:
    if module.rsplit(".", 1)[-1] == "include_role":
        return isinstance(args, dict) and args.get("name") == "alloy_apt"
    included = args.get("file") if isinstance(args, dict) else args
    return "alloy_apt" in PurePosixPath(str(included)).parts


def test_the_alloy_package_is_installed_and_held_by_alloy_apt_alone_and_each_importer_takes_its_postcondition():
    """An include is one leaf to the walk and, without `apply`, selects nothing inside under the tag: a role that included
    the shared role would pass the other checks here while its install, pin and hold went unselected."""
    statements = _task_statements()
    naming = [
        (path, task.get("name"), module.rsplit(".", 1)[-1])
        for path, task in statements
        for module, args in _calls(task, *PACKAGE_MODULES)
        if _names_alloy(args)
    ]
    assert sorted(module for path, _, module in naming if path.is_relative_to(SHARED)) == ["apt", "dpkg_selections"], naming
    elsewhere = [(str(path.relative_to(ANSIBLE)), name) for path, name, _ in naming if not path.is_relative_to(SHARED)]
    assert not elsewhere, elsewhere

    includes = [
        (str(path.relative_to(ANSIBLE)), task.get("name"))
        for path, task in statements
        for module, args in _calls(task, "include_role", "include_tasks")
        if _includes_the_shared_role(module, args)
    ]
    assert not includes, includes

    imported: dict[str, set[str]] = {}
    for path, task in statements:
        key = next((key for key in alloy_version.IMPORT_ROLE if key in task), None)
        if key and path.is_relative_to(ROLES) and task[key].get("name") == "alloy_apt":
            imported.setdefault(path.relative_to(ROLES).parts[0], set()).add(task[key].get("tasks_from", "main"))
    assert imported, "no role imports alloy_apt"
    assert not [role for role, files in imported.items() if "postcondition" not in files], imported


@pytest.mark.parametrize("importer", ["access", "mon"])
def test_a_listening_handler_a_role_imported_in_the_importers_tasks_brings_is_refused(monkeypatch, importer):
    listener = {
        "name": "restart caddy too",
        "ansible.builtin.systemd": {"name": "caddy", "state": "restarted"},
        "listen": ["restart alloy"],
    }
    role_handlers = alloy_part.role_handlers
    monkeypatch.setattr(
        alloy_part, "role_handlers", lambda role, stem=None: [listener] if role == "alloy_apt" else role_handlers(role, stem)
    )
    assert alloy_part.handler_refusals(importer) == ["restart caddy too: answers an Alloy notify and is not an Alloy handler"]
