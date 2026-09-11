"""runbook-triggers.py: a section's kind marker is its trigger, a fired kind must be named where it fires, and the fired kinds carry a Retire when."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra" / "scripts" / "runbook-triggers.py"


def _load():
    spec = importlib.util.spec_from_file_location("runbook_triggers_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


rt = _load()

RUNBOOK = """# Capture

<a name="cap-alert"></a>

## zcrypto-capture-x — ALERT

### What to do

### Retire when

<a name="cap-limit"></a>

## a thing you meet — KNOWN LIMITATION

text, and a reference to its own anchor: infra/runbooks/capture.md#cap-limit

<a name="cap-proc"></a>

## reboot the host — PROCEDURE

steps

<a name="cap-reminder"></a>

## the sweep is due — SCHEDULED REMINDER

**Retire when** the register dies.

   <a name="cap-bridge"></a>

## zaccess-thing — PROCEDURE: converging the bridgehead

steps

## Standing rules — no kind

- rules
"""
ALERTS = "groups:\n- rules:\n  - annotations:\n      summary: 'Runbook: infra/runbooks/capture.md#cap-alert'\n"


def _tree(tmp_path: Path, *, alerts: str = ALERTS, namer: str = "", topic: str = "", test: str = "") -> list[str]:
    (tmp_path / "infra" / "runbooks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "infra" / "grafana").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "infra" / "runbooks" / "capture.md").write_text(RUNBOOK)
    (tmp_path / "infra" / "runbooks" / "README.md").write_text("# Runbooks\n\n## Scope\n")
    (tmp_path / "infra" / "grafana" / "alerts.yaml").write_text(alerts)
    (tmp_path / "infra" / "namer.md").write_text(namer)
    (tmp_path / "docs" / "topic.md").write_text(topic)
    (tmp_path / "tests" / "test_guard.py").write_text(test)
    return [
        "infra/runbooks/capture.md",
        "infra/runbooks/README.md",
        "infra/grafana/alerts.yaml",
        "infra/namer.md",
        "docs/topic.md",
        "tests/test_guard.py",
    ]


def test_sections_take_the_anchors_above_them_and_end_before_the_next_run():
    secs = rt.sections("infra/runbooks/capture.md", RUNBOOK)
    assert [(s.kind, s.anchors) for s in secs] == [
        ("ALERT", ("cap-alert",)),
        ("KNOWN LIMITATION", ("cap-limit",)),
        ("PROCEDURE", ("cap-proc",)),
        ("SCHEDULED REMINDER", ("cap-reminder",)),
        ("PROCEDURE", ("cap-bridge",)),
        (None, ()),
    ]
    assert "cap-limit" not in secs[0].body and secs[0].line == 5


def test_a_fired_kind_is_untriggered_until_something_else_names_it(tmp_path):
    files = _tree(tmp_path)
    found = {(s.heading, why) for s, why in rt.untriggered(tmp_path, files)}
    assert found == {
        (
            "a thing you meet — KNOWN LIMITATION",
            "no guard, comment, test or reminder under cli/, infra/, tests/ or .claude/ names it by file and anchor",
        ),
        (
            "the sweep is due — SCHEDULED REMINDER",
            "no guard, comment, test or reminder under cli/, infra/, tests/ or .claude/ names it by file and anchor",
        ),
        ("Standing rules — no kind", "no kind marker in the heading"),
    }
    files = _tree(tmp_path, namer="see `infra/runbooks/capture.md`'s `cap-limit`, and infra/runbooks/capture.md#cap-reminder. Next")
    assert [s.heading for s, _ in rt.untriggered(tmp_path, files)] == ["Standing rules — no kind"]


def test_a_test_naming_a_fired_section_is_its_trigger(tmp_path):
    files = _tree(tmp_path, test='assert ok, "see infra/runbooks/capture.md#cap-limit"\n')
    assert "a thing you meet — KNOWN LIMITATION" not in {s.heading for s, _ in rt.untriggered(tmp_path, files)}


def test_a_topic_or_plan_naming_a_fired_section_is_not_its_trigger(tmp_path):
    files = _tree(
        tmp_path, topic="the limit is infra/runbooks/capture.md#cap-limit and the reminder infra/runbooks/capture.md#cap-reminder"
    )
    assert {s.heading for s, _ in rt.untriggered(tmp_path, files)} == {
        "a thing you meet — KNOWN LIMITATION",
        "the sweep is due — SCHEDULED REMINDER",
        "Standing rules — no kind",
    }


def test_an_alert_section_needs_a_rule_that_links_it(tmp_path):
    files = _tree(tmp_path, alerts="groups: []\n", namer="infra/runbooks/capture.md#cap-alert is named here, not in a rule")
    assert ("zcrypto-capture-x — ALERT", "no rule in alerts.yaml links it as its Runbook") in {
        (s.heading, why) for s, why in rt.untriggered(tmp_path, files)
    }


def test_the_fired_kinds_carry_a_retire_when(tmp_path):
    files = _tree(tmp_path)
    assert [s.heading for s, _ in rt.without_retire_when(tmp_path, files)] == ["a thing you meet — KNOWN LIMITATION"]


def test_the_real_tree_counts_without_error():
    assert rt.untriggered(REPO) is not None and rt.without_retire_when(REPO) is not None
