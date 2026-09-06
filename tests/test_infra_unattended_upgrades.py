"""The unattended-upgrades auto-reboot flip (spec 00071 D4, T0027).

`Automatic-Reboot` is a variable so the two capture VPSes can go attended while the ops node stays
automatic. The value must be a quoted string: a bare YAML `false` renders through Jinja as Python's
`False`, emitting `Automatic-Reboot "False";`, which apt reads as not-true by accident rather than
by intention.
"""

from __future__ import annotations

from pathlib import Path

import jinja2
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "infra/ansible/roles/base/templates/50unattended-upgrades.j2"
BASE_DEFAULTS = REPO / "infra/ansible/roles/base/defaults/main.yml"
CAPTURE_GROUP_VARS = REPO / "infra/ansible/group_vars/capture_host/vars.yml"
INVENTORY = REPO / "infra/ansible/inventory/hosts.yml"

VAR = "base_unattended_upgrades_automatic_reboot"

_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)


def _render(**overrides) -> str:
    """Render the apt config as ansible would, under StrictUndefined so a typo'd var fails loudly."""
    context = {
        "base_unattended_upgrades_reboot_time": "21:25",
        "base_unattended_upgrades_mail_to": "root",
        **overrides,
    }
    return _ENV.from_string(TEMPLATE.read_text()).render(**context)


def _directive(rendered: str, key: str) -> str:
    """The exact quoted value apt will read for one directive."""
    line = next(line for line in rendered.splitlines() if line.startswith(f"Unattended-Upgrade::{key} "))
    return line.split('"')[1]


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def test_automatic_reboot_is_driven_by_the_variable_not_hardcoded():
    assert _directive(_render(**{VAR: "false"}), "Automatic-Reboot") == "false"
    assert _directive(_render(**{VAR: "true"}), "Automatic-Reboot") == "true"


def test_the_role_default_preserves_todays_behaviour():
    """The ops node takes the flip's default: a default of "false" would silently disarm patch
    reboots on a host the owner decided should keep them (T0027's ruling)."""
    assert _yaml(BASE_DEFAULTS)[VAR] == "true"


def test_the_capture_group_flips_both_hosts_and_only_them():
    """Membership carries the "and only them" half: a capture host outside this group reboots
    unattended on an unbackfillable VPS, a non-capture host inside it loses T0027's patch reboots."""
    assert _yaml(CAPTURE_GROUP_VARS)[VAR] == "false"
    hosts = _yaml(INVENTORY)["all"]["children"]["capture_host"]["hosts"]
    assert set(hosts) == {"zcrypto", "zcrypto-red"}, f"capture_host membership drifted: {sorted(hosts)}"


@pytest.mark.parametrize("path", [BASE_DEFAULTS, CAPTURE_GROUP_VARS], ids=["defaults", "capture"])
def test_the_value_is_a_quoted_string_never_a_yaml_boolean(path):
    value = _yaml(path)[VAR]
    assert isinstance(value, str), (
        f"{path.name}: {VAR} parsed as {type(value).__name__} ({value!r}) — quote it, or Jinja "
        f'emits Automatic-Reboot "{value}" and apt reads it as not-true by accident'
    )
    assert value in ("true", "false"), f"{path.name}: unexpected value {value!r}"


def test_a_yaml_boolean_would_have_rendered_the_broken_value():
    """Proof the guard above is worth having: this is what the footgun actually produces."""
    assert _directive(_render(**{VAR: False}), "Automatic-Reboot") == "False"


def test_the_reboot_time_directive_survives_the_flip():
    """`Automatic-Reboot-Time` goes inert but must NOT be removed: it keeps the on-host file readable
    as human scheduling guidance, and `roles/base/tasks/main.yml`'s fleet-collision assert reads
    `base_unattended_upgrades_reboot_time` out of hostvars and fails the whole fleet closed if it is
    UNDECLARED (T0027 rules that assert stays)."""
    rendered = _render(**{VAR: "false"})
    assert _directive(rendered, "Automatic-Reboot-Time") == "21:25"
    assert _directive(rendered, "Automatic-Reboot-WithUsers") == "true", (
        "WithUsers is inert on capture but LIVE on the ops node — leave it alone"
    )
