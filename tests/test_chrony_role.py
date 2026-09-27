"""The chrony role: PTB under the names its NTS-KE certificates carry, and a verify task that fails
without a selected source -- evaluated through Ansible's own templating, over `chronyc -N sources`
fixtures, so the expression is read the way a converge reads it."""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

REPO = Path(__file__).resolve().parents[1]
ROLE = REPO / "infra/ansible/roles/chrony"

# `chronyc -N sources` as chrony prints it: `^*` is the selected source, `^+`/`^-` combined or
# excluded peers, `^?` one never reached -- which is what a source whose NTS-KE fails shows forever.
SELECTED = """MS Name/IP address         Stratum Poll Reach LastRx Last sample
===============================================================================
^? time.cloudflare.com           0   6     0     -     +0ns[   +0ns] +/-    0ns
^* ptbtime1.ptb.de               1   6    17    20   +125us[ +140us] +/-   12ms
^+ ptbtime2.ptb.de               1   6    17    21   +130us[ +145us] +/-   12ms
^- ptbtime3.ptb.de               1   6    17    19   +128us[ +143us] +/-   13ms
"""
UNSELECTED = SELECTED.replace("^*", "^?").replace("^+", "^?").replace("^-", "^?")


def _defaults() -> dict:
    return yaml.safe_load((ROLE / "defaults/main.yml").read_text())


def _verify_task() -> dict:
    tasks = [t for t in yaml.safe_load((ROLE / "tasks/main.yml").read_text()) if "until" in t]
    assert len(tasks) == 1, f"expected one retrying verify task, found {len(tasks)}"
    return tasks[0]


def _holds(stdout: str) -> bool:
    """The verify task's `until`, evaluated by Ansible over a registered `chronyc -N sources` result."""
    templar = Templar(loader=DataLoader(), variables={"chrony_sources_result": {"stdout": stdout, "rc": 0}})
    return templar.evaluate_conditional(trust_as_template(_verify_task()["until"]))


def test_a_selected_source_satisfies_the_verify_task():
    assert _holds(SELECTED)


def test_a_fleet_of_unreached_sources_fails_the_verify_task():
    assert not _holds(UNSELECTED), "the verify task passes with every source at ^? -- it asserts nothing"


def test_the_selection_mark_is_read_in_the_ms_column_only():
    """A `*` anywhere else in the output -- a `Last sample` column, a name -- is not a selection."""
    assert not _holds(UNSELECTED.replace("+0ns[", "^* ns["))
    assert not _holds(UNSELECTED.replace("^? time.cloudflare.com", "^?*time.cloudflare.com"))


def test_the_verify_task_retries_through_the_handshake_and_reports_no_change():
    task = _verify_task()
    assert task["ansible.builtin.command"] == "chronyc -N sources"
    assert task["changed_when"] is False
    assert task["retries"] * task["delay"] >= 30, "NTS-KE plus the iburst exchange take seconds after a restart; one read is a race"


def test_every_ptb_server_is_named_as_its_certificate_names_it():
    """NTS-KE checks the configured name against the certificate, so an alias (ntp3.ptb.de is
    ptbtime3.ptb.de's) fails the handshake and the source is never selectable."""
    servers = _defaults()["chrony_nts_servers"]
    ptb = [s for s in servers if s.endswith(".ptb.de")]
    assert ptb, "no PTB server configured"
    misnamed = [s for s in ptb if not re.fullmatch(r"ptbtime[1-4]\.ptb\.de", s)]
    assert not misnamed, f"{misnamed} are not the names PTB's NTS-KE certificates carry"


def test_three_or_more_sources_let_chrony_outvote_one_that_is_wrong():
    assert len(_defaults()["chrony_nts_servers"]) >= 3


def test_the_template_hands_every_server_to_chrony_as_an_nts_source():
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    rendered = env.from_string((ROLE / "templates/chrony.conf.j2").read_text()).render(**_defaults())
    server_lines = [line for line in rendered.splitlines() if line.startswith("server ")]
    assert server_lines == [f"server {s} iburst nts" for s in _defaults()["chrony_nts_servers"]]
