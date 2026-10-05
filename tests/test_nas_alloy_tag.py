"""The nas role's `alloy` tag: a converge that lands the NAS's Alloy config and secrets file and recreates Alloy alone,
never archive-pull, read off the YAML the way Ansible selects by tag -- a block's tags and `when` reach its children, a
role entry's tags reach every task of the role, and `always` runs whatever was asked."""

from __future__ import annotations

import re

import pytest
import yaml

from tests.test_infra_converge_guards import ANSIBLE, NAS, assert_that, find_task, load_tasks, truthy, when_conditions
from tests.test_pins_converged import pins

TAG = "alloy"
NAS_ROLE = ANSIBLE / "roles" / "nas"
SITE = ANSIBLE / "site.yml"
PIN_ASSERT = "refuse to recreate Alloy from a stack .env that names another Alloy pin"
NARROW_APPLY = "apply — recreate alloy alone (its secrets env and config, nothing of the puller)"

ALWAYS = [
    "read the NAS clock's UTC offset (the TZ guard's evidence)",
    "refuse to manage a non-UTC NAS (docker logs --since parses LOCAL time)",
]
RENDERS = [
    "ensure the alloy config directory exists",
    "deploy the alloy pipeline config",
    "remove the pre-conf layout's stale alloy config",
    "render the alloy secrets env file",
]
NARROW_REPORT = "report which Alloy files this converge changed"
NARROW_APPLY_PATH = ["read whether the stack .env names the committed Alloy pin", PIN_ASSERT, NARROW_APPLY]
ALLOY_PART = [*RENDERS, NARROW_REPORT, *NARROW_APPLY_PATH]

# The whole apply as it stood before the tag: every task, in order, and the three apply commands verbatim.
WHOLE_RENDER = [
    *ALWAYS,
    "deploy the pull-entrypoint (the in-container scheduler)",
    "deploy the compose file",
    "ensure the alloy config directory exists",
    "deploy the alloy pipeline config",
    "remove the pre-conf layout's stale alloy config",
    "refuse an archive-pull hash scope the CLI would reject",
    "render the stack .env (image pins, pull sources, the vaulted gate dead-man URL)",
    "render the alloy secrets env file",
    "ensure the hot/ hub directory exists (setgid so both writers' children inherit group zcrypto)",
    "deploy the vendored rrsync jailer (the NAS ships no rrsync -- rsync 3.4.1's python3 rrsync)",
    "install the hot-push pubkey as a write-capable rrsync forced command jailed to hot/ (on zcrypto-data)",
    "report which stack files this converge changed",
]
WHOLE_APPLY = {
    "apply — converge the containers onto the rendered files": "cd {{ nas_stack_dir }} && {{ nas_docker }} compose up -d",
    "apply — restart archive-pull (bind-mounted entrypoint changes are invisible to `up -d`)": (
        "cd {{ nas_stack_dir }} && {{ nas_docker }} compose restart archive-pull"
    ),
    "apply — restart alloy (re-reads the config.alloy this converge deployed)": (
        "cd {{ nas_stack_dir }} && {{ nas_docker }} compose restart alloy"
    ),
}
APPLY_FLAG = "nas_apply_compose | default(false) | bool"

PULLER_PIECES = {".env", "compose.yaml", "pull-entrypoint.sh", "rrsync"}
PULLER_SOURCES = {"env.j2"}
WRITERS = ("copy", "template", "file", "lineinfile", "blockinfile", "replace")
SCOPED_COMPOSE = "compose up -d --no-deps --force-recreate alloy"


def _tags(node: dict) -> set[str]:
    raw = node.get("tags") or []
    items = [raw] if isinstance(raw, str) else raw
    return {tag.strip() for item in items for tag in str(item).split(",") if tag.strip()}


def _walk(tasks: list[dict], tags: frozenset[str] = frozenset(), gates: tuple[str, ...] = ()) -> list[tuple[dict, set, tuple]]:
    out = []
    for task in tasks or []:
        own, conds = tags | _tags(task), gates + tuple(str(c) for c in when_conditions(task))
        children = [task[k] for k in ("block", "rescue", "always") if k in task]
        if children:
            for child in children:
                out.extend(_walk(child, frozenset(own), conds))
        else:
            out.append((task, own, conds))
    return out


def _leaves() -> list[tuple[dict, set, tuple]]:
    return _walk(load_tasks(NAS), frozenset({"nas"}))


def _selected(tags: set[str], run_tags: list[str]) -> bool:
    asked = set(run_tags)
    return "always" in tags or bool(tags & asked) or bool({"all", "tagged"} & asked)


def _executed(run_tags: list[str], apply: bool) -> list[str]:
    facts = {"ansible_run_tags": run_tags, "nas_apply_compose": apply}
    return [task["name"] for task, tags, gates in _leaves() if _selected(tags, run_tags) and truthy(list(gates), facts)]


def _module(task: dict) -> tuple[str, dict | str]:
    return next((k, v) for k, v in task.items() if k.startswith("ansible."))


def _produced(task: dict) -> set[str]:
    names = {task["register"]} if task.get("register") else set()
    return names | set(task.get("ansible.builtin.set_fact") or {})


def _read_text(task: dict, gates: tuple[str, ...]) -> str:
    body = yaml.safe_dump({k: v for k, v in task.items() if k not in ("name", "register")})
    module, args = _module(task)
    if module == "ansible.builtin.template":
        body += (NAS_ROLE / "templates" / args["src"]).read_text()
    return body + "\n".join(gates)


def test_the_tag_selects_exactly_the_alloy_part():
    leaves = _leaves()
    assert [task["name"] for task, tags, _ in leaves if TAG in tags] == ALLOY_PART
    assert not [task["name"] for task, _, _ in leaves if task.get("notify")]


def test_every_name_a_tagged_task_reads_is_produced_by_an_earlier_tagged_or_always_task():
    """A register or `set_fact` read in a gate, an argument or a rendered template: `--tags alloy` skips every untagged
    producer, so a read of one fails that run on an undefined variable."""
    leaves = _leaves()
    every = set().union(*(_produced(task) for task, _, _ in leaves))
    available: set[str] = set()
    unproduced = []
    for task, tags, gates in leaves:
        if not ({TAG, "always"} & tags):
            continue
        reads = {name for name in every if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", _read_text(task, gates))}
        unproduced += [(task["name"], name) for name in sorted(reads - available - _produced(task))]
        available |= _produced(task)
    assert not unproduced, unproduced


def _compose_calls(task: dict) -> list[str]:
    module, args = _module(task)
    assert "docker" not in module, task["name"]
    if module not in ("ansible.builtin.shell", "ansible.builtin.command"):
        return []
    line = args if isinstance(args, str) else " ".join(args.get("argv") or [args.get("cmd") or ""])
    return re.findall(r"(?<![\w-])compose\s.*", line)


def test_no_tagged_task_reaches_the_puller():
    for task, tags, gates in _leaves():
        if TAG not in tags:
            continue
        module, args = _module(task)
        assert "archive-pull" not in _read_text(task, gates), task["name"]
        if module.rsplit(".", 1)[-1] in WRITERS:
            target = str(args.get("dest") or args.get("path") or "")
            assert target.rsplit("/", 1)[-1] not in PULLER_PIECES, task["name"]
            assert str(args.get("src") or "").rsplit("/", 1)[-1] not in PULLER_PIECES | PULLER_SOURCES, task["name"]
        assert all(call.strip() == SCOPED_COMPOSE for call in _compose_calls(task)), (task["name"], _compose_calls(task))


def test_the_narrow_apply_is_the_one_tagged_compose_call():
    calls = [(task["name"], _compose_calls(task)) for task, tags, _ in _leaves() if TAG in tags]
    assert [(name, found) for name, found in calls if found] == [(NARROW_APPLY, [SCOPED_COMPOSE])]


@pytest.mark.parametrize("run_tags", [["all"], ["nas"], ["nas", TAG], [TAG, "nas"], ["tagged"]])
@pytest.mark.parametrize("apply", [True, False])
def test_a_whole_converge_runs_the_tasks_it_ran_before_the_tag_and_never_the_alloy_only_apply(run_tags, apply):
    assert _executed(run_tags, apply) == WHOLE_RENDER + (list(WHOLE_APPLY) if apply else [])
    tasks = load_tasks(NAS)
    for name, command in WHOLE_APPLY.items():
        task = find_task(tasks, name)
        assert (task["ansible.builtin.shell"], when_conditions(task), _tags(task)) == (command, [APPLY_FLAG], set())


@pytest.mark.parametrize(("apply", "tail"), [(False, []), (True, NARROW_APPLY_PATH)])
def test_an_alloy_run_renders_alloys_files_reports_and_recreates_alloy_alone_under_the_flag(apply, tail):
    assert _executed([TAG], apply) == [*ALWAYS, *RENDERS, NARROW_REPORT, *tail]


@pytest.mark.parametrize("seq", [tuple, list])
@pytest.mark.parametrize(
    ("run_tags", "narrow"),
    [
        ([TAG], True),
        (["all"], False),
        (["nas"], False),
        (["nas", TAG], False),
        (["all", TAG], False),
        (["tagged", TAG], False),
        (["tagged"], False),
    ],
)
def test_the_alloy_only_block_engages_on_a_run_that_selects_alloy_without_the_whole_role(seq, run_tags, narrow):
    block = next(task for task in load_tasks(NAS) if "block" in task)
    assert _tags(block) == {TAG}
    assert truthy(when_conditions(block), {"ansible_run_tags": seq(run_tags)}) is narrow


@pytest.mark.parametrize(("rc", "passes"), [(0, True), (1, False), (2, False)])
def test_the_recreate_refuses_a_stack_env_that_does_not_name_the_committed_alloy_pin(rc, passes):
    tasks = load_tasks(NAS)
    assert truthy(assert_that(find_task(tasks, PIN_ASSERT)), {"nas_env_alloy_pin": {"rc": rc}}) is passes
    read = find_task(tasks, NARROW_APPLY_PATH[0])
    assert read["ansible.builtin.command"]["argv"] == [
        "grep",
        "-qxF",
        "ALLOY_IMAGE={{ nas_alloy_image }}",
        "{{ nas_stack_dir }}/.env",
    ]
    assert read["check_mode"] is False and read["changed_when"] is False and read["failed_when"] is False


def _plays_reaching(host: str) -> list[dict]:
    groups = pins.inventory_groups(ANSIBLE.parents[1])
    return [play for play in load_tasks(SITE) if host in (groups.get(play["hosts"]) or {play["hosts"]})]


def test_an_alloy_run_on_the_nas_runs_the_alloy_part_beside_the_always_tasks_and_nothing_else():
    """Ansible's selection over every play that reaches the NAS: an `always` task or an `alloy` tag in any of their roles
    would run beside the Alloy part."""
    pre_tasks, role_tasks = [], []
    for play in _plays_reaching("nas"):
        play_tags = frozenset(_tags(play))
        pre_tasks += [t["name"] for t, tags, _ in _walk(play.get("pre_tasks"), play_tags) if _selected(tags, [TAG])]
        for entry in play["roles"]:
            role = load_tasks(ANSIBLE / "roles" / entry["role"] / "tasks" / "main.yml")
            role_tasks += [
                (entry["role"], t["name"]) for t, tags, _ in _walk(role, play_tags | _tags(entry)) if _selected(tags, [TAG])
            ]
    assert pre_tasks == ["note — the NAS play's charter"]
    assert role_tasks == [("nas", name) for name in ALWAYS + ALLOY_PART]


def test_the_always_tasks_an_alloy_run_takes_read_and_assert_and_restart_nothing():
    for task, tags, _ in _leaves():
        if "always" in tags:
            module, args = _module(task)
            assert module in ("ansible.builtin.command", "ansible.builtin.assert"), task["name"]
            assert module != "ansible.builtin.command" or (args == "date +%z" and task["changed_when"] is False), task["name"]
