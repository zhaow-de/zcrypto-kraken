"""`infra/scripts/alloy-version.py` — what an `alloy` run selects, read off `site.yml`, the inventory and the roles."""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

import pytest
import yaml

_SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "infra" / "scripts" / "alloy-version.py"


def _load():
    spec = importlib.util.spec_from_file_location("alloy_version", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


alloy_version = _load()

INVENTORY = {
    "all": {
        "children": {
            "box_host": {"hosts": {"box": {}}},
            "other_host": {"hosts": {"other": {}}},
        }
    }
}


def _tree(tmp_path: pathlib.Path, files: dict[str, object]) -> pathlib.Path:
    ansible = tmp_path / "infra" / "ansible"
    for rel, data in {"inventory/hosts.yml": INVENTORY, **files}.items():
        path = ansible / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else yaml.safe_dump(data, sort_keys=False))
    return ansible


def _task(name: str, *tags: str, **keys) -> dict:
    return {"name": name, "ansible.builtin.debug": {"msg": name}, **({"tags": list(tags)} if tags else {}), **keys}


def _named(leaves) -> list[tuple[str, set[str], tuple[str, ...]]]:
    return [(task["name"], set(tags), gates) for task, tags, gates in leaves]


def test_a_block_tagged_alloy_hands_the_tag_to_its_children(tmp_path):
    ansible = _tree(
        tmp_path,
        {
            "roles/r/tasks/main.yml": [
                {
                    "name": "the alloy part",
                    "tags": ["alloy"],
                    "when": "wanted",
                    "block": [_task("render"), _task("reload", "extra")],
                    "rescue": [_task("report")],
                },
                _task("the daemon"),
            ]
        },
    )
    assert _named(alloy_version.role_leaves("r", frozenset({"r"}), ansible_dir=ansible)) == [
        ("render", {"r", "alloy"}, ("wanted",)),
        ("reload", {"r", "alloy", "extra"}, ("wanted",)),
        ("report", {"r", "alloy"}, ("wanted",)),
        ("the daemon", {"r"}, ()),
    ]


@pytest.mark.parametrize("module", ["ansible.builtin.import_role", "ansible.legacy.import_role", "import_role"])
def test_an_import_role_under_the_tag_hands_it_to_every_imported_task(tmp_path, module):
    ansible = _tree(
        tmp_path,
        {
            "roles/shared/tasks/main.yml": [_task("the shared role's default entry")],
            "roles/shared/tasks/install.yml": [_task("install"), {"name": "hold", "when": "held", "block": [_task("hold it")]}],
            "roles/r/tasks/main.yml": [
                {
                    "name": "bring in the install",
                    module: {"name": "shared", "tasks_from": "install"},
                    "tags": ["alloy"],
                    "when": "wanted",
                },
                _task("the role's own task"),
            ],
        },
    )
    assert _named(alloy_version.role_leaves("r", frozenset({"r"}), ansible_dir=ansible)) == [
        ("install", {"r", "alloy"}, ("wanted",)),
        ("hold it", {"r", "alloy"}, ("wanted", "held")),
        ("the role's own task", {"r"}, ()),
    ]


@pytest.mark.parametrize("module", ["ansible.builtin.import_tasks", "ansible.legacy.import_tasks", "import_tasks"])
def test_an_import_tasks_under_the_tag_hands_it_to_every_imported_task(tmp_path, module):
    ansible = _tree(
        tmp_path,
        {
            "roles/r/tasks/alloy.yml": [_task("render"), _task("reload")],
            "roles/r/tasks/main.yml": [
                {"name": "bring in the alloy part", module: "alloy.yml", "tags": ["alloy"]},
                _task("the daemon"),
            ],
        },
    )
    assert _named(alloy_version.role_leaves("r", frozenset(), ansible_dir=ansible)) == [
        ("render", {"alloy"}, ()),
        ("reload", {"alloy"}, ()),
        ("the daemon", set(), ()),
    ]
    with pytest.raises(ValueError, match="no importing file"):
        alloy_version.walk([{"name": "unanchored", module: "alloy.yml"}])


def test_an_include_role_under_the_tag_stays_one_leaf(tmp_path):
    ansible = _tree(
        tmp_path,
        {
            "roles/shared/tasks/main.yml": [_task("a task the include brings in at run time")],
            "roles/r/tasks/main.yml": [
                {"name": "include the shared role", "ansible.builtin.include_role": {"name": "shared"}, "tags": ["alloy"]}
            ],
        },
    )
    assert _named(alloy_version.role_leaves("r", frozenset(), ansible_dir=ansible)) == [("include the shared role", {"alloy"}, ())]


def test_a_host_in_a_child_group_is_reached_through_its_parent_play(tmp_path):
    ansible = _tree(
        tmp_path,
        {
            "inventory/hosts.yml": {
                "all": {"children": {"parent_host": {"children": {"child_host": {}}}, "child_host": {"hosts": {"box": {}}}}}
            },
            "site.yml": [{"name": "the parent's play", "hosts": "parent_host", "roles": [{"role": "r", "tags": ["r"]}]}],
            "roles/r/tasks/main.yml": [_task("render", "alloy")],
        },
    )
    assert [play["name"] for play in alloy_version.plays_reaching("box", ansible_dir=ansible)] == ["the parent's play"]
    assert alloy_version.reaches("box", ansible_dir=ansible)


def test_a_host_whose_plays_carry_no_alloy_task_is_not_reached(tmp_path):
    ansible = _tree(
        tmp_path,
        {
            "inventory/hosts.yml": {
                "all": {"children": {"box_host": {"hosts": {"box": {}}}, "both_host": {"hosts": {"box": {}, "other": {}}}}}
            },
            "site.yml": [
                {"name": "carries the tag", "hosts": "box_host", "roles": [{"role": "r", "tags": ["r"]}]},
                {"name": "carries none", "hosts": "both_host", "pre_tasks": [_task("note", "always")], "roles": [{"role": "q"}]},
            ],
            "roles/r/tasks/main.yml": [_task("render", "alloy")],
            "roles/q/tasks/main.yml": [_task("clock", "always"), _task("daemon", "q")],
        },
    )
    assert alloy_version.reaches("box", ansible_dir=ansible)
    assert not alloy_version.reaches("other", ansible_dir=ansible)


def test_a_host_in_no_play_is_not_reached(tmp_path):
    ansible = _tree(
        tmp_path,
        {
            "site.yml": [{"name": "the box's play", "hosts": "box_host", "roles": [{"role": "r"}]}],
            "roles/r/tasks/main.yml": [_task("render", "alloy")],
        },
    )
    assert not alloy_version.reaches("other", ansible_dir=ansible)
    assert not alloy_version.reaches("a-host-the-inventory-never-names", ansible_dir=ansible)
    assert alloy_version.reaches("box", ansible_dir=ansible)


SELECTION_SITE = [
    {
        "name": "the box's play",
        "hosts": "box_host",
        "pre_tasks": [_task("note", "always"), _task("check")],
        "roles": [{"role": "capture", "tags": ["capture"]}, {"role": "docker", "tags": ["docker"]}],
        "post_tasks": [_task("wrap up", "alloy")],
    },
    {"name": "another host's play", "hosts": "other_host", "pre_tasks": [_task("elsewhere", "always")]},
]
SELECTION_ROLES = {
    "roles/capture/tasks/main.yml": [
        _task("fail fast", "alloy"),
        _task("daemon"),
        _task("dump", "never", "debug"),
        _task("clock", "always"),
    ],
    "roles/docker/tasks/main.yml": [_task("install docker")],
}


SELECTED_BY_ALL = [
    ("box_host", "note"),
    ("box_host", "check"),
    ("capture", "fail fast"),
    ("capture", "daemon"),
    ("capture", "clock"),
    ("docker", "install docker"),
    ("box_host", "wrap up"),
]


@pytest.mark.parametrize(
    ("run_tags", "expected"),
    [
        (["alloy"], [("box_host", "note"), ("capture", "fail fast"), ("capture", "clock"), ("box_host", "wrap up")]),
        (["debug"], [("box_host", "note"), ("capture", "dump"), ("capture", "clock")]),
        (["all"], SELECTED_BY_ALL),
        ([], SELECTED_BY_ALL),
        (
            ["tagged"],
            [
                ("box_host", "note"),
                ("capture", "fail fast"),
                ("capture", "daemon"),
                ("capture", "clock"),
                ("docker", "install docker"),
                ("box_host", "wrap up"),
            ],
        ),
    ],
)
def test_the_selection_runs_always_tasks_and_the_asked_tags_alone(tmp_path, run_tags, expected):
    ansible = _tree(tmp_path, {"site.yml": SELECTION_SITE, **SELECTION_ROLES})
    assert alloy_version.selection("box", run_tags, ansible_dir=ansible) == expected


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_SCRIPT), *args], capture_output=True, text=True)


def test_the_cli_exits_0_1_and_2_with_its_lines(tmp_path):
    ansible = _tree(
        tmp_path,
        {
            "site.yml": [
                {"name": "the box's play", "hosts": "box_host", "roles": [{"role": "r"}]},
                {"name": "another host's play", "hosts": "other_host", "roles": [{"role": "q"}]},
            ],
            "roles/r/tasks/main.yml": [_task("render", "alloy")],
            "roles/q/tasks/main.yml": [_task("daemon", "q")],
        },
    )
    # An unresolved `<dir>/..`, the form of converge.sh's ADIR.
    reached = _cli("reaches", "--ansible-dir", str(ansible / "roles" / ".."), "box")
    assert (reached.returncode, reached.stdout, reached.stderr) == (0, "", "")
    unreached = _cli("reaches", "--ansible-dir", str(ansible), "other")
    assert (unreached.returncode, unreached.stdout, unreached.stderr) == (
        1,
        "",
        "no play that reaches other runs an alloy-tagged task\n",
    )
    (ansible / "site.yml").write_text("- name: [an unclosed list\n")
    broken = _cli("reaches", "--ansible-dir", str(ansible), "box")
    assert (broken.returncode, broken.stdout, broken.stderr.startswith("reaches: ")) == (2, "", True), broken.stderr
