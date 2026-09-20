"""`.claude/skills/zcrypto-plan-review/scripts/union.py` as a command: `OUT.md` and at least one report, or usage on
stderr at exit 1 with nothing written; a report path that does not exist is an error, not an empty report. The union
orders its clusters by their maximum severity and then by key, keeps every member's body under the cluster heading
after a marker naming the report and the grade it gave, and ends `OUT.md` with the summary line it prints. What the
parser accepts as a finding is `tests/test_plan_review_union.py`'s."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_UNION = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "zcrypto-plan-review" / "scripts" / "union.py"

_A = (
    "### [Minor] · [in-original] · docs/plans/x.md:9\nbody of a-minor\n\n"
    "### [Important] · [in-original] · docs/plans/x.md:2\nbody of a-important\n"
)
_B = (
    "### [Minor] · [earlier-fix] · docs/plans/x.md:1\nbody of b-minor\n\n"
    "### [Critical] · [last-fix] · docs/plans/x.md:9\nbody of b-critical\n"
)
_SUMMARY = (
    "counts (from headings): Critical 1 · Important 1 · Minor 1 · keys 3 · raw findings 4 · unparsed 0"
    " · Important by origin: last-fix 0 · earlier-fix 0 · in-original 1"
)


def _run(*argv: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(_UNION), *map(str, argv)], capture_output=True, text=True)


def test_fewer_than_two_arguments_is_usage_and_writes_nothing(tmp_path):
    out = tmp_path / "union.md"
    for argv in ((), (out,)):
        done = _run(*argv)
        assert done.returncode == 1 and "usage: union.py OUT.md REPORT.md [REPORT.md ...]" in done.stderr
    assert not out.exists()


def test_a_missing_report_is_an_error_not_an_empty_report(tmp_path):
    out = tmp_path / "union.md"
    done = _run(out, tmp_path / "absent.md")
    assert done.returncode not in (0, 2) and not out.exists()


def test_clusters_order_by_maximum_severity_then_key_and_keep_every_body(tmp_path):
    (tmp_path / "a.md").write_text(_A, encoding="utf-8")
    (tmp_path / "b.md").write_text(_B, encoding="utf-8")
    out = tmp_path / "union.md"
    done = _run(out, tmp_path / "a.md", tmp_path / "b.md")
    assert done.returncode == 0, done.stderr
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Union\n")
    assert [line for line in text.splitlines() if line.startswith("### ")] == [
        "### [Critical] · [last-fix] · docs/plans/x.md:9",
        "### [Important] · [in-original] · docs/plans/x.md:2",
        "### [Minor] · [earlier-fix] · docs/plans/x.md:1",
    ]
    cluster = text.split("docs/plans/x.md:9\n", 1)[1].split("### [Important]", 1)[0]
    assert "<!-- a.md graded Minor -->\nbody of a-minor\n" in cluster
    assert "<!-- b.md graded Critical -->\nbody of b-critical\n" in cluster
    assert done.stdout.strip() == _SUMMARY and text.rstrip("\n").splitlines()[-1] == _SUMMARY
