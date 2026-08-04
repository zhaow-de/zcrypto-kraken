"""Every shell template must render, through Ansible's own engine, to valid bash.

This closes the defect class that shipped twice on `panel-regenerate.sh.j2` and was caught both
times by a live converge rather than by a test:

1. bash's string-length expansion opens with a brace-hash pair, which Jinja reads as a comment tag
   — the template did not render at all, so the script never installed;
2. the raw-block fix for (1) rendered perfectly under a bare `jinja2.Environment` and installed
   BROKEN shell, because Ansible renders with `trim_blocks=True`, which eats the newline after a
   block tag and welds the following line onto it.

A parse sweep cannot see the second class — trim_blocks changes rendered whitespace, not what
parses — so the guarantee has to be *render, then check the shell*.

The limit of that guarantee, measured rather than assumed: `bash -n` catches a weld only when the
joined line is a SYNTAX error, which is what both production defects produced (`len=${#override}`
welded onto an `if` line). A weld that happens to yield valid shell — `n=1` onto `rc=$?` giving
`n=1rc=$?` — renders, parses, and passes here while meaning something else entirely. Catching that
would need per-template behavioural fixtures, which is what the individual template test files
exist for; this file is the floor, not the ceiling. Two rules follow, and both are
enforced here rather than left to per-template files: use Ansible's `Templar` (never bare jinja2,
whose defaults differ from Ansible's in exactly the way that bit us), and require every shell
template to be registered, so a new one cannot arrive uncovered.
"""

import pathlib
import subprocess

import pytest
import yaml

ROLES = pathlib.Path(__file__).resolve().parent.parent / "infra" / "ansible" / "roles"

# Vars the templates need that their role defaults do not carry — runtime facts (ops_uid/ops_gid
# come from getent_passwd at converge time) or values supplied by inventory. The exact values are
# immaterial: this file asserts that the template RENDERS to valid shell, not what the uid is.
RUNTIME_FACTS = {
    "ops_uid": "1002",
    "ops_gid": "1002",
    # No repo default by design — the pins rule keeps it operand-only, always passed with -e.
    "ops_image_digest": "sha256:" + "ab" * 32,
    # The access role's ops-side probe reads ops vars that live in inventory, not in its own role.
    "ops_textfile_dir": "/var/lib/zcrypto-ops/textfile",
    "ops_data_dir": "/var/lib/zcrypto-ops",
}

# Every roles/*/templates/*.sh.j2 must appear here. The completeness test below fails on any
# unregistered template, so adding one forces a decision instead of silently landing unguarded.
REGISTERED = {
    "archive-pull.sh.j2",
    "grafana-watchdog.sh.j2",
    "panel-materialize.sh.j2",
    "panel-regenerate.sh.j2",
    "verified-replay.sh.j2",
    "verify-replay.sh.j2",
    "zaccess-probe-ops.sh.j2",
    "zaccess-probe.sh.j2",
}


def shell_templates():
    return sorted(ROLES.glob("*/templates/*.sh.j2"))


def role_variables(template):
    """Role defaults plus the runtime facts — the closest honest stand-in for converge context."""
    defaults = template.parent.parent / "defaults" / "main.yml"
    loaded = yaml.safe_load(defaults.read_text()) if defaults.exists() else {}
    variables = {key: ("" if value is None else value) for key, value in (loaded or {}).items()}
    variables.update(RUNTIME_FACTS)
    return variables


def ansible_render(source, variables):
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template

    return Templar(loader=DataLoader(), variables=variables).template(trust_as_template(source))


def test_every_shell_template_is_registered():
    found = {t.name for t in shell_templates()}
    assert found, "no shell templates found — the glob is wrong, not the tree"
    assert found == REGISTERED, f"unregistered: {sorted(found - REGISTERED)}; stale entries: {sorted(REGISTERED - found)}"


@pytest.mark.parametrize("template", shell_templates(), ids=lambda t: t.name)
def test_shell_template_renders_to_valid_bash(template):
    rendered = ansible_render(template.read_text(), role_variables(template))
    assert "{{" not in rendered and "{%" not in rendered, f"{template.name}: unrendered Jinja survived"
    proc = subprocess.run(["bash", "-n"], input=rendered, text=True, capture_output=True)
    assert proc.returncode == 0, f"{template.name}: renders to invalid bash — {proc.stderr.strip()}"
