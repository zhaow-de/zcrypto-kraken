"""The three review workflows carry one grading, one scope and one set of rules, copied because a workflow script
cannot import another; this holds the copies equal."""

from __future__ import annotations

import pathlib
import re

_FLOWS = pathlib.Path(__file__).resolve().parents[1] / ".claude" / "workflows"


def _constant(name: str, text: str) -> str:
    m = re.search(rf"^const {name} = `(.*?)`$", text, re.M | re.S)
    assert m, f"{name} is not a top-level template constant"
    return m.group(1)


def test_the_three_workflows_share_their_grading_scope_and_checkout_contract():
    texts = {f: (_FLOWS / f"{f}.js").read_text() for f in ("pre-read", "review", "re-review")}
    for name in ("GRADING", "SCOPE", "RULES"):
        values = {f: _constant(name, t) for f, t in texts.items()}
        assert len(set(values.values())) == 1, f"{name} differs between {sorted(values)}"


def test_the_grading_grades_prose_by_consequence():
    text = _constant("GRADING", (_FLOWS / "review.js").read_text())
    assert "prose that, acted on as written, breaks something no test stops" in text
