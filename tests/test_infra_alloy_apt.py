"""The shared apt Alloy role, `alloy_apt`: its install and its post-condition, read off their YAML and evaluated through
Ansible's templar over constructed variables, and its share of each importer's exclusion allowlist."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.plugins.loader import init_plugin_loader
from ansible.template import Templar, trust_as_template
from ansible.utils.collection_loader import AnsibleCollectionConfig

from tests.alloy_part import module_entry
from tests.test_infra_converge_guards import ANSIBLE, assert_that, find_task, load_tasks, set_facts, truthy, when_conditions

TASKS = ANSIBLE / "roles" / "alloy_apt" / "tasks"
MAIN = TASKS / "main.yml"
POSTCONDITION = TASKS / "postcondition.yml"

REFUSAL = "refuse an alloy_deb_version that is not the one committed for this host, unless an alloy_override gives the reason"
ECHO = "the alloy_override's reason, on the record"
REPOSITORY = "add the Grafana apt repository (deb822; the module fetches and stores the signing key)"
PIN = "pin alloy at the version committed for this host, above every other candidate"
INSTALL = "install alloy at the version committed for this host, moving a newer or held one"
PREVIEWED = "note a preview that runs before alloy is installed and pinned at the version committed for this host"
HOLD = "hold alloy, so no apt upgrade moves it"
FLUSH = "apply the pending alloy restart before reading what the process runs"
READ = "read whether the running alloy process runs the installed binary"
RESTART = "restart alloy when its process predates the installed binary or none runs"

ALLOY_APT_MAIN = [REFUSAL, ECHO, REPOSITORY, PIN, INSTALL, PREVIEWED, HOLD]
ALLOY_APT_POSTCONDITION = [FLUSH, READ, RESTART]

# The shared role's share of each importer's exclusion allowlist, written out and never read from the role, so an edit
# to the role fails every importer's exclusion case until these move with it.
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

HOST = "zaccess"
FLEET = "1.20.1-1"
HELD = "1.19.2-1"
OTHER = "1.21.0-1"
REASON = "1.20.1 drops journal lines on the edge, back while the owner reads it"


@pytest.fixture(scope="module", autouse=True)
def _lookup_plugins():
    # The committed version is read through the `file` and `first_found` lookups, which resolve only once Ansible's
    # collection loader is configured; configuring it twice warns.
    if not AnsibleCollectionConfig.collection_finder:
        init_plugin_loader()


def _tree(tmp_path: Path, held: bool) -> Path:
    root = tmp_path / "ansible"
    (root / "group_vars" / "observed").mkdir(parents=True)
    (root / "group_vars" / "observed" / "alloy.yml").write_text(f'---\nalloy_version: "1.20.1"\nalloy_deb_version: "{FLEET}"\n')
    if held:
        (root / "host_vars" / HOST).mkdir(parents=True)
        (root / "host_vars" / HOST / "alloy.yml").write_text(
            f'---\n# 1.20.1 drops journal lines on the edge; held until the owner reads it\nalloy_deb_version: "{HELD}"\n'
        )
    return root


def _variables(task: dict, playbook_dir: Path, host: str, version: str, override: str | None) -> dict:
    variables = {
        "playbook_dir": str(playbook_dir),
        "inventory_hostname": host,
        "alloy_deb_version": version,
        **{name: trust_as_template(value) for name, value in task["vars"].items()},
    }
    return variables if override is None else {**variables, "alloy_override": override}


def _render(text: str, variables: dict) -> str:
    return Templar(loader=DataLoader(), variables=variables).template(trust_as_template(text))


def test_the_install_runs_the_refusal_its_echo_the_repository_the_pin_the_install_the_fact_and_the_hold_in_order():
    tasks = load_tasks(MAIN)
    assert [task["name"] for task in tasks] == ALLOY_APT_MAIN
    assert module_entry(tasks[-1]) == ("ansible.builtin.dpkg_selections", {"name": "alloy", "selection": "hold"})


@pytest.mark.parametrize(
    ("version", "override", "fires"),
    [
        pytest.param(OTHER, REASON, True, id="other-reason"),
        pytest.param(OTHER, None, False, id="other"),
        pytest.param(OTHER, "short", False, id="other-short"),
        pytest.param(FLEET, REASON, False, id="committed-reason"),
    ],
)
def test_the_echo_fires_only_on_an_accepted_override(tmp_path, version, override, fires):
    tasks, tree = load_tasks(MAIN), _tree(tmp_path, held=False)
    refusal, echo = find_task(tasks, REFUSAL), find_task(tasks, ECHO)
    # A failed assert ends the host's run, so the echo runs only where the refusal passed.
    ran = truthy(assert_that(refusal), _variables(refusal, tree, HOST, version, override))
    assert (ran and truthy(when_conditions(echo), _variables(echo, tree, HOST, version, override))) is fires


def test_the_install_takes_exactly_the_fleets_deb_version_with_both_options():
    args = find_task(load_tasks(MAIN), INSTALL)["ansible.builtin.apt"]
    assert args == {
        "name": "alloy={{ alloy_deb_version }}",
        "state": "present",
        "update_cache": True,
        "allow_downgrade": True,
        "allow_change_held_packages": True,
    }
    assert _render(args["name"], {"alloy_deb_version": FLEET}) == f"alloy={FLEET}"


def test_the_pin_file_reads_the_fleets_version_at_1001():
    args = find_task(load_tasks(MAIN), PIN)["ansible.builtin.copy"]
    assert args["dest"] == "/etc/apt/preferences.d/alloy"
    assert _render(args["content"], {"alloy_deb_version": FLEET}) == f"Package: alloy\nPin: version {FLEET}\nPin-Priority: 1001\n"


REAL_FLEET = yaml.safe_load((ANSIBLE / "group_vars" / "observed" / "alloy.yml").read_text())["alloy_deb_version"]


@pytest.mark.parametrize(
    ("held", "version", "override", "passes"),
    [
        pytest.param(False, FLEET, None, True, id="fleet"),
        pytest.param(False, OTHER, None, False, id="other"),
        pytest.param(False, OTHER, REASON, True, id="other-reason"),
        pytest.param(False, OTHER, "yes", False, id="other-yes"),
        pytest.param(True, HELD, None, True, id="held"),
        pytest.param(True, FLEET, None, False, id="held-host-fleet"),
        pytest.param(True, FLEET, REASON, True, id="held-host-fleet-reason"),
        pytest.param(None, REAL_FLEET, None, True, id="the-trees-fleet-file"),
        pytest.param(None, "0.0.0-0", None, False, id="the-trees-fleet-file-other"),
    ],
)
def test_the_version_refusal_admits_the_committed_version_or_a_reasoned_override(tmp_path, held, version, override, passes):
    refusal = find_task(load_tasks(MAIN), REFUSAL)
    # `held` None reads this tree's own fleet file, for a host no hold file names.
    playbook_dir, host = (ANSIBLE, "a-host-with-no-hold-file") if held is None else (_tree(tmp_path, held), HOST)
    assert truthy(assert_that(refusal), _variables(refusal, playbook_dir, host, version, override)) is passes


def _register(changed: bool, skipped: bool = False) -> dict:
    return {"changed": changed, "skipped": True} if skipped else {"changed": changed}


@pytest.mark.parametrize(
    ("check_mode", "repository", "pin", "runs"),
    [
        pytest.param(True, True, False, False, id="preview-repository"),
        pytest.param(True, False, True, False, id="preview-pin"),
        pytest.param(True, False, False, True, id="preview-neither"),
        pytest.param(False, True, True, True, id="real-run-both"),
    ],
)
def test_the_install_stands_down_in_a_preview_whose_repository_or_pin_file_would_change(check_mode, repository, pin, runs):
    variables = {
        "ansible_check_mode": check_mode,
        "alloy_apt_grafana_repo": _register(repository),
        "alloy_apt_pin": _register(pin),
    }
    assert truthy(when_conditions(find_task(load_tasks(MAIN), INSTALL)), variables) is runs


@pytest.mark.parametrize(
    ("check_mode", "repository", "pin", "install", "previewed"),
    [
        pytest.param(True, True, False, _register(False, skipped=True), True, id="preview-repository"),
        pytest.param(True, False, True, _register(False, skipped=True), True, id="preview-pin-install-skipped"),
        pytest.param(True, False, False, _register(True), True, id="preview-install-moved-by-hand"),
        pytest.param(True, False, False, _register(False), False, id="preview-established"),
        pytest.param(False, True, True, _register(True), False, id="real-run"),
    ],
)
def test_the_preview_fact_is_true_only_in_a_preview_whose_repository_pin_or_install_would_change(
    check_mode, repository, pin, install, previewed
):
    tasks = load_tasks(MAIN)
    variables = {
        "ansible_check_mode": check_mode,
        "alloy_apt_grafana_repo": _register(repository),
        "alloy_apt_pin": _register(pin),
        "alloy_apt_install": install,
    }
    fact = set_facts(find_task(tasks, PREVIEWED), variables)["alloy_apt_previewed"]
    assert fact is previewed
    assert truthy(when_conditions(find_task(tasks, HOLD)), {"alloy_apt_previewed": fact}) is (not previewed)


def test_the_postcondition_flushes_before_it_reads():
    tasks = load_tasks(POSTCONDITION)
    assert [task["name"] for task in tasks] == ALLOY_APT_POSTCONDITION
    assert tasks[0].get("ansible.builtin.meta") == "flush_handlers"


@pytest.mark.parametrize(
    ("stdout", "restarts"),
    [
        pytest.param("/usr/bin/alloy (deleted)", True, id="the-bridgeheads-shape-a-process-older-than-the-binary"),
        pytest.param("/usr/bin/alloy", False, id="the-nodes-shape-the-package-restarted-it"),
        pytest.param("__not_running__", True, id="no-process"),
        pytest.param("", True, id="an-empty-read"),
    ],
)
def test_the_postcondition_restarts_on_the_bridgeheads_shape_and_not_on_the_nodes(stdout, restarts):
    tasks = load_tasks(POSTCONDITION)
    read, restart = find_task(tasks, READ), find_task(tasks, RESTART)
    assert truthy(when_conditions(read), {"ansible_check_mode": False})
    real = {"ansible_check_mode": False, "alloy_apt_running_exe": {"changed": False, "stdout": stdout}}
    assert truthy(when_conditions(restart), real) is restarts
    assert not truthy(when_conditions(read), {"ansible_check_mode": True})
    preview = {"ansible_check_mode": True, "alloy_apt_running_exe": _register(False, skipped=True)}
    assert not truthy(when_conditions(restart), preview)
