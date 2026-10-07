"""`infra/scripts/alloy-version.py` — what an `alloy` run selects, read off `site.yml`, the inventory and the roles; the
bump gate, read from the sources' recorded answers; and the `observed` hosts off the fleet's version."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import re
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


@pytest.mark.parametrize(
    ("tasks_from", "files", "found"),
    [
        ("install", {"install": "bare", "install.yml": "yml"}, "bare"),
        ("install.yml", {"install.yml": "yml", "install.yml.yml": "doubled"}, "yml"),
        ("install", {"install.yaml": "yaml"}, "yaml"),
    ],
    ids=["the-name-as-written-first", "an-extension-written-in-the-name", "the-yaml-extension"],
)
def test_an_import_role_finds_its_tasks_file_as_ansible_does(tmp_path, tasks_from, files, found):
    ansible = _tree(
        tmp_path,
        {
            **{f"roles/shared/tasks/{name}": [_task(task)] for name, task in files.items()},
            "roles/r/tasks/main.yml": [
                {"name": "bring in", "ansible.builtin.import_role": {"name": "shared", "tasks_from": tasks_from}, "tags": ["alloy"]}
            ],
        },
    )
    assert _named(alloy_version.role_leaves("r", frozenset(), ansible_dir=ansible)) == [(found, {"alloy"}, ())]


def test_a_play_role_whose_tasks_file_is_main_yaml_is_read_as_ansible_reads_it(tmp_path, capsys):
    ansible = _tree(
        tmp_path,
        {
            "site.yml": [{"name": "the box's play", "hosts": "box_host", "roles": [{"role": "r"}]}],
            "roles/r/tasks/main.yaml": [_task("render", "alloy")],
        },
    )
    assert (alloy_version.main(["reaches", "--ansible-dir", str(ansible), "box"]), capsys.readouterr().err) == (0, "")


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
        "tasks": [_task("own task", "alloy")],
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
    ("box_host", "own task"),
    ("box_host", "wrap up"),
]


@pytest.mark.parametrize(
    ("run_tags", "expected"),
    [
        (
            ["alloy"],
            [
                ("box_host", "note"),
                ("capture", "fail fast"),
                ("capture", "clock"),
                ("box_host", "own task"),
                ("box_host", "wrap up"),
            ],
        ),
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
                ("box_host", "own task"),
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


FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "alloy_version"
HUB_TAGS = "https://hub.docker.com/v2/repositories/grafana/alloy/tags?page_size=100&ordering=last_updated"
TOKEN = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:grafana/alloy:pull"
APT_INDEX = "https://apt.grafana.com/dists/stable/main/binary-amd64/Packages"
INDEX_ACCEPT = "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"
PULL = {"Authorization": "Bearer anonymous", "Accept": INDEX_ACCEPT}
RECORDED_DIGEST = (FIXTURES / "index-v1.20.1.digest").read_text().strip()
LISTED_1_20_0 = "sha256:f111cce835516c5f99166342be7038496b52ced16667be5a11e19258a3e4cd30"
FLEETS = {
    "1.19.2": ("sha256:b8ec653c44235fbe910879145dac3597d66b0aaecf60bcbbe82580767771a839", "1.19.2-1"),
    "1.20.0": (LISTED_1_20_0, "1.20.0-1"),
    "1.20.1": (RECORDED_DIGEST, "1.20.1-1"),
}
TARGET = f"target: 1.20.1 {RECORDED_DIGEST} 1.20.1-1"
NO_TARGET = "target: none — the fleet runs the newest version present in both"


def test_the_recorded_index_hashes_to_the_recorded_digest():
    index = (FIXTURES / "index-v1.20.1.json").read_bytes()
    assert f"sha256:{hashlib.sha256(index).hexdigest()}" == RECORDED_DIGEST


def _manifest(version: str) -> str:
    return f"https://registry-1.docker.io/v2/grafana/alloy/manifests/v{version}"


def _fleet_line(version: str) -> str:
    digest, deb = FLEETS[version]
    return f"fleet: {version} {digest} {deb}"


def _hub(**digests: str) -> bytes:
    """The recorded listing, each named tag's digest set or, for a tag it lacks, the tag added."""
    listing = json.loads((FIXTURES / "hub-tags.json").read_text())
    for tag in listing["results"]:
        tag["digest"] = digests.pop(tag["name"], tag["digest"])
    listing["results"] += [{"name": name, "digest": digest} for name, digest in digests.items()]
    return json.dumps(listing).encode()


def _packages(*stanzas: str, replace: tuple[str, str] = ("", "")) -> bytes:
    recorded = (FIXTURES / "Packages").read_text().replace(*replace).rstrip("\n")
    return "\n\n".join([recorded, *stanzas]).encode() + b"\n"


def _index(amd64: bool = True) -> bytes:
    index = json.loads((FIXTURES / "index-v1.20.1.json").read_text())
    linux_amd64 = {"architecture": "amd64", "os": "linux"}
    index["manifests"] = [entry for entry in index["manifests"] if amd64 or entry["platform"] != linux_amd64]
    return json.dumps(index).encode()


def _upstream(changed: dict[str, object] | None = None) -> dict[str, object]:
    """Each URL the gate may ask, answered as the fixtures recorded it unless the case changes it; a URL left out goes
    unanswered."""
    return {
        HUB_TAGS: (_hub(), {}),
        APT_INDEX: (_packages(), {}),
        TOKEN: (json.dumps({"token": "anonymous"}).encode(), {}),
        _manifest("1.20.1"): (_index(), {"Docker-Content-Digest": RECORDED_DIGEST}),
        **(changed or {}),
    }


def _stub(answers: dict[str, object]):
    def fetch(url, headers):
        if url.startswith(_manifest("")) and dict(headers) != PULL:
            raise PermissionError(f"{url} asked without the anonymous pull token and the index media types")
        answer = answers.get(url, OSError(f"nothing answers {url}"))
        if isinstance(answer, Exception):
            raise answer
        return answer

    return fetch


def _fleet_file(fleet: str) -> str:
    digest, deb = FLEETS[fleet]
    return f'alloy_version: "{fleet}"\nalloy_image_digest: {digest}\nalloy_deb_version: "{deb}"\n'


def _gate(tmp_path, capsys, fleet: str, answers: dict[str, object]) -> tuple[int, list[str], str]:
    ansible = _tree(tmp_path, {"group_vars/observed/alloy.yml": _fleet_file(fleet)})
    code = alloy_version.main(["gate", "--ansible-dir", str(ansible)], fetch=_stub(answers))
    out, err = capsys.readouterr()
    return code, out.splitlines(), err


@pytest.mark.parametrize("fleet", ["1.20.0", "1.19.2"], ids=["one-version-above", "two-versions-above-in-both"])
def test_the_newest_version_in_both_is_the_target_with_its_index_digest_and_deb_version(tmp_path, capsys, fleet):
    answers = _upstream({_manifest("1.20.0"): (_index(), {"docker-content-digest": LISTED_1_20_0})})
    assert _gate(tmp_path, capsys, fleet, answers) == (0, [_fleet_line(fleet), TARGET], "")


def test_a_version_in_one_source_alone_is_named_and_never_the_target(tmp_path, capsys):
    answers = _upstream(
        {
            HUB_TAGS: (_hub(**{"v1.21.0": "sha256:" + "1" * 64}), {}),
            APT_INDEX: (_packages("Package: alloy\nVersion: 1.20.2-1\nArchitecture: amd64"), {}),
            _manifest("1.21.0"): (_index(), {"Docker-Content-Digest": "sha256:" + "1" * 64}),
        }
    )
    assert _gate(tmp_path, capsys, "1.20.0", answers) == (
        0,
        [_fleet_line("1.20.0"), TARGET, "image only: v1.21.0", "apt only: 1.20.2-1"],
        "",
    )


def test_an_index_without_linux_amd64_is_never_the_target(tmp_path, capsys):
    answers = _upstream({_manifest("1.20.1"): (_index(amd64=False), {"Docker-Content-Digest": RECORDED_DIGEST})})
    assert _gate(tmp_path, capsys, "1.20.0", answers) == (0, [_fleet_line("1.20.0"), NO_TARGET, "apt only: 1.20.1-1"], "")


def test_the_deb_version_is_the_indexs_own_string(tmp_path, capsys):
    answers = _upstream({APT_INDEX: (_packages(replace=("Version: 1.20.1-1", "Version: 1.20.1-2")), {})})
    assert _gate(tmp_path, capsys, "1.20.0", answers) == (
        0,
        [_fleet_line("1.20.0"), f"target: 1.20.1 {RECORDED_DIGEST} 1.20.1-2"],
        "",
    )


@pytest.mark.parametrize(
    "packages",
    [
        _packages("Package: alloy\nVersion: 1.20.1-2\nArchitecture: amd64"),
        _packages("Package: alloy\nVersion: 1.20.1-1\nArchitecture: amd64", replace=("Version: 1.20.1-1", "Version: 1.20.1-2")),
    ],
    ids=["the-higher-revision-last", "the-higher-revision-first"],
)
def test_the_deb_version_is_the_highest_revision_of_its_upstream_version(tmp_path, capsys, packages):
    answers = _upstream({APT_INDEX: (packages, {})})
    assert _gate(tmp_path, capsys, "1.20.0", answers) == (
        0,
        [_fleet_line("1.20.0"), f"target: 1.20.1 {RECORDED_DIGEST} 1.20.1-2"],
        "",
    )


def test_a_tag_that_is_not_a_release_is_not_a_version(tmp_path, capsys):
    answers = _upstream({HUB_TAGS: (_hub(**{"v1.21.0-rc.0": "sha256:" + "1" * 64}), {})})
    assert _gate(tmp_path, capsys, "1.20.0", answers) == (0, [_fleet_line("1.20.0"), TARGET], "")


def test_no_newer_version_in_both_prints_none(tmp_path, capsys):
    assert _gate(tmp_path, capsys, "1.20.1", _upstream()) == (0, [_fleet_line("1.20.1"), NO_TARGET], "")


@pytest.mark.parametrize(
    ("url", "source"),
    [(HUB_TAGS, "docker hub"), (APT_INDEX, "apt index"), (TOKEN, "registry"), (_manifest("1.20.1"), "registry")],
    ids=["the-tag-listing", "the-apt-index", "the-pull-token", "the-index"],
)
def test_a_source_that_fails_ends_gate_failed_naming_it(tmp_path, capsys, url, source):
    answers = _upstream({url: OSError("the source does not answer")})
    assert _gate(tmp_path, capsys, "1.20.0", answers) == (2, [], f"gate: failed: {source}: OSError: the source does not answer\n")


@pytest.mark.parametrize(
    ("fleet_file", "failed"),
    [
        ('alloy_version: "1.20.0"\nalloy_image_digest: sha256:' + "a" * 64 + "\n", "KeyError: 'alloy_deb_version'"),
        (_fleet_file("1.20.0").replace('"1.20.0"', '"1.20.x"', 1), "ValueError: invalid literal for int() with base 10: 'x'"),
    ],
    ids=["a-key-missing", "a-version-that-is-not-one"],
)
def test_a_fleet_file_the_gate_cannot_read_ends_gate_failed_naming_it(tmp_path, capsys, fleet_file, failed):
    ansible = _tree(tmp_path, {"group_vars/observed/alloy.yml": fleet_file})
    code = alloy_version.main(["gate", "--ansible-dir", str(ansible)], fetch=_stub(_upstream()))
    out, err = capsys.readouterr()
    assert (code, out, err) == (2, "", f"gate: failed: fleet file: {failed}\n")


class _Response:
    def __init__(self, body: bytes, headers: dict[str, str]):
        self.body, self.headers = body, headers

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self.body


def test_every_request_carries_its_timeout(tmp_path, capsys, monkeypatch):
    answers = _upstream()
    asked = []

    def urlopen(request, timeout=None):
        asked.append((request.full_url, timeout))
        return _Response(*answers[request.full_url])

    monkeypatch.setattr(alloy_version.urllib.request, "urlopen", urlopen)
    ansible = _tree(tmp_path, {"group_vars/observed/alloy.yml": _fleet_file("1.20.0")})
    assert alloy_version.main(["gate", "--ansible-dir", str(ansible)]) == 0, capsys.readouterr()
    assert sorted(asked) == sorted((url, 30) for url in answers), asked


def test_the_digest_is_the_registrys_answer_and_not_the_listings(tmp_path, capsys):
    answers = _upstream({HUB_TAGS: (_hub(**{"v1.20.1": "sha256:" + "0" * 64}), {})})
    assert _gate(tmp_path, capsys, "1.20.0", answers) == (0, [_fleet_line("1.20.0"), TARGET], "")


def test_a_package_named_like_alloy_is_not_alloy(tmp_path, capsys):
    decoy = "Package: alloy-boringcrypto\nVersion: 1.21.0-1\nArchitecture: amd64"
    answers = _upstream({APT_INDEX: (_packages(decoy), {})})
    assert _gate(tmp_path, capsys, "1.20.0", answers) == (0, [_fleet_line("1.20.0"), TARGET], "")


OBSERVED_INVENTORY = {
    "all": {
        "children": {
            "observed": {"children": {"container_host": {}, "apt_host": {}}},
            "container_host": {"hosts": {"box": {}, "crate": {}}},
            "apt_host": {"hosts": {"edge": {}, "node": {}}},
            "outside_host": {"hosts": {"outside": {}}},
        }
    }
}
FLEET_HEX = RECORDED_DIGEST.removeprefix("sha256:")[:12]
ON = {"box": FLEET_HEX, "crate": FLEET_HEX, "edge": "1.20.1-1", "node": "1.20.1-1"}
IMAGE_HEADER = (
    "| service | host | digest (sha256, first 12) | since (UTC) | rollback operand (resident on the host at the re-pin) |\n"
    "| --- | --- | --- | --- | --- |\n"
)
PACKAGE_HEADER = "| package | host | version | since (UTC) | notes |\n| --- | --- | --- | --- | --- |\n"


def _pins_text(image: dict[str, str], package: dict[str, str], tables=("image", "package"), other=()) -> str:
    image_rows = "".join(
        f"| alloy | {host} | `{hex12}` — v1.20.1 | 2026-10-06 10:00:00 | first pin |\n" for host, hex12 in image.items()
    )
    image_rows += "".join(
        f"| valkey + sentinel | {host} | `{'4' * 12}` — Valkey | 2026-10-06 10:00:00 | first pin |\n" for host in other
    )
    package_rows = "".join(
        f"| alloy | {host} | {version} | 2026-10-06 | dpkg hold; pinned at 1001 |\n" for host, version in package.items()
    )
    parts = {"image": IMAGE_HEADER + image_rows, "package": PACKAGE_HEADER + package_rows}
    return "# Fleet pins\n\n## Current pins\n\n" + "\n**Non-image pins.**\n\n".join(parts[t] for t in tables) + "\n"


def _off_fleet(tmp_path, capsys, pins: str, inventory: dict = OBSERVED_INVENTORY) -> tuple[int, str, str]:
    ansible = _tree(
        tmp_path,
        {
            "inventory/hosts.yml": inventory,
            "group_vars/observed/alloy.yml": _fleet_file("1.20.1"),
        },
    )
    (tmp_path / "docs" / "reference").mkdir(parents=True)
    (tmp_path / "docs" / "reference" / "fleet-pins.md").write_text(pins)
    code = alloy_version.main(["off-fleet", "--ansible-dir", str(ansible)])
    out, err = capsys.readouterr()
    return code, out, err


def _image(**hosts: str) -> dict[str, str]:
    return {host: hosts.get(host, ON[host]) for host in ("box", "crate")}


def _package(**hosts: str) -> dict[str, str]:
    return {host: hosts.get(host, f"`{ON[host]}`") for host in ("edge", "node")}


def test_an_image_row_off_the_fleets_digest_is_off(tmp_path, capsys):
    pins = _pins_text(_image(crate="b8ec653c4423"), _package())
    assert _off_fleet(tmp_path, capsys, pins) == (0, "1\n", f"  crate: image row at b8ec653c4423, the fleet's is {FLEET_HEX}\n")


def test_an_apt_row_at_the_fleets_deb_version_is_on_and_another_is_off(tmp_path, capsys):
    pins = _pins_text(_image(), _package(node="`1.20.0-1`"))
    assert _off_fleet(tmp_path, capsys, pins) == (0, "1\n", "  node: package row at 1.20.0-1, the fleet's is 1.20.1-1\n")


def test_an_observed_host_with_no_alloy_row_is_off(tmp_path, capsys):
    image = _image()
    del image["crate"]
    pins = _pins_text(image, _package(), other=("crate",))
    assert _off_fleet(tmp_path, capsys, pins) == (0, "1\n", "  crate: no alloy row\n")


def test_a_host_outside_observed_is_not_read(tmp_path, capsys):
    pins = _pins_text({**_image(), "outside": "b8ec653c4423"}, _package())
    assert _off_fleet(tmp_path, capsys, pins) == (0, "0\n", "")


@pytest.mark.parametrize("tables", [(), ("image",), ("package",)], ids=["neither-table", "no-package-table", "no-image-table"])
def test_a_pins_file_without_its_tables_exits_2(tmp_path, capsys, tables):
    code, out, err = _off_fleet(tmp_path, capsys, _pins_text(_image(), _package(), tables=tables))
    assert (code, out, err.startswith("off-fleet: ValueError: ")) == (2, "", True), err


def test_an_inventory_without_the_observed_group_exits_2(tmp_path, capsys):
    code, out, err = _off_fleet(tmp_path, capsys, _pins_text(_image(), _package()), inventory=INVENTORY)
    assert (code, out, err) == (2, "", "off-fleet: KeyError: 'observed'\n")


def test_the_real_tree_prints_one_count():
    done = _cli("off-fleet")
    assert done.returncode == 0 and re.fullmatch(r"\d+\n", done.stdout), done.stdout + done.stderr
    observed = alloy_version._pins.inventory_groups(_SCRIPT.parents[2])["observed"]
    named = [re.fullmatch(r"  (\S+): .+", line) for line in done.stderr.splitlines()]
    assert all(named) and len(named) == int(done.stdout), done.stderr
    assert {m.group(1) for m in named} <= observed, done.stderr
