"""Every shell template must render, through Ansible's own engine, to valid bash.

Render with Ansible's `Templar`, never a bare `jinja2.Environment`: Ansible renders with
`trim_blocks=True`, which eats the newline after a block tag and welds the following line onto it,
so a template that renders perfectly under bare jinja2 can still install BROKEN shell.
"""

import pathlib
import subprocess

import pytest
import yaml

ROLES = pathlib.Path(__file__).resolve().parent.parent / "infra" / "ansible" / "roles"

# Vars the templates need that their role defaults do not carry — runtime facts (ops_uid/ops_gid
# come from getent_passwd at converge time) or values supplied by inventory.
RUNTIME_FACTS = {
    "ops_uid": "1002",
    "ops_gid": "1002",
    # No repo default by design — the pins rule keeps it operand-only, always passed with -e.
    "ops_image_digest": "sha256:" + "ab" * 32,
    "ops_textfile_dir": "/var/lib/zcrypto-ops/textfile",
    "ops_data_dir": "/var/lib/zcrypto-ops",
    # The engine role reads these from getent at converge time and its defaults declare neither, so
    # the render has no other source for them.
    "engine_uid": "998",
    "engine_gid": "998",
}

# Every roles/*/templates/*.sh.j2 must appear here, so a new one cannot land unguarded.
REGISTERED = {
    "archive-pull.sh.j2",
    "grafana-watchdog.sh.j2",
    "panel-materialize.sh.j2",
    "panel-regenerate.sh.j2",
    "tape-bars.sh.j2",
    "verified-replay.sh.j2",
    "verify-replay.sh.j2",
    "zaccess-agentboard-start.sh.j2",
    "zaccess-probe-ops.sh.j2",
    "zaccess-probe.sh.j2",
    "zcrypto-flatten.sh.j2",
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


def welding_lines(source):
    """Line numbers where a `{% … %}` tag closes a line that already carries content — trim_blocks
    then eats the newline after the tag and welds the NEXT line onto that content."""
    welded = []
    for number, line in enumerate(source.splitlines(), 1):
        stripped = line.rstrip()
        if "{%" in stripped and stripped.endswith("%}") and stripped[: stripped.rfind("{%")].strip():
            welded.append(number)
    return welded


def ansible_render(source, variables):
    from ansible.parsing.dataloader import DataLoader
    from ansible.template import Templar, trust_as_template

    return Templar(loader=DataLoader(), variables=variables).template(trust_as_template(source))


def test_every_shell_template_is_registered():
    found = {t.name for t in shell_templates()}
    assert found, "no shell templates found — the glob is wrong, not the tree"
    assert found == REGISTERED, f"unregistered: {sorted(found - REGISTERED)}; stale entries: {sorted(REGISTERED - found)}"


WELDED = "rc=$?{% set n = 1 %}\nn=1\n"
SAFE = "rc=$?\n{% set n = 1 %}\nn=1\n"


def test_the_weld_is_real_and_bash_n_reads_it_as_valid():
    """Why the lint below exists rather than leaning on `bash -n`: the welded line is still valid
    shell, so the render test above stays green while `rc` has silently taken a different value."""
    assert ansible_render(WELDED, {}) == "rc=$?n=1\n", "the weld did not happen — trim_blocks is not in play"
    assert ansible_render(SAFE, {}) == "rc=$?\nn=1\n", "the tag on its own line must NOT weld"
    assert subprocess.run(["bash", "-n"], input="rc=$?n=1\n", text=True, capture_output=True).returncode == 0
    assert welding_lines(WELDED) == [1] and welding_lines(SAFE) == []


@pytest.mark.parametrize("template", shell_templates(), ids=lambda t: t.name)
def test_no_block_tag_closes_a_content_line(template):
    welded = welding_lines(template.read_text())
    assert not welded, f"{template.name}: line(s) {welded} end with a block tag that welds the next line onto them"


@pytest.mark.parametrize("template", shell_templates(), ids=lambda t: t.name)
def test_shell_template_renders_to_valid_bash(template):
    rendered = ansible_render(template.read_text(), role_variables(template))
    assert "{{" not in rendered and "{%" not in rendered, f"{template.name}: unrendered Jinja survived"
    proc = subprocess.run(["bash", "-n"], input=rendered, text=True, capture_output=True)
    assert proc.returncode == 0, f"{template.name}: renders to invalid bash — {proc.stderr.strip()}"
