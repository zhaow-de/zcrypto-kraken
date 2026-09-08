#!/usr/bin/env python3
"""Shape check for an agent-lessons inbox (`.local/agent-lessons/<session>.jsonl`), run at harvest.
Refuses prose, blank lines and extra keys: an inbox is a harvest input for the refine-rules round,
not a story board.
"""

import json
import sys

REQUIRED = {"ts", "session", "branch", "kind", "cites", "what", "why"}
KINDS = {"self-correction", "rule-deviation", "rule-feedback", "skill-feedback", "miscount"}
# A lesson field is one line. A newline in one means something else wrote it -- most often a command
# substitution splicing multi-line output in, since a backticked symbol name inside a DOUBLE-quoted
# shell argument runs -- and every other check accepts the result, being a non-empty string.
_ONE_LINE = "%s must be one line, but contains a newline (if a shell substitution ran in your argument, single-quote it)"


def record_errors(rec: object) -> list[str]:
    """Every way one parsed record fails the shape, so a writer can refuse before it appends."""
    if not isinstance(rec, dict) or set(rec) != REQUIRED:
        return [f"keys must be exactly {sorted(REQUIRED)}"]
    out = []
    if rec["kind"] not in KINDS:
        out.append(f"kind must be one of {sorted(KINDS)}, got {rec['kind']!r}")
    if not isinstance(rec["cites"], list) or not all(isinstance(c, str) and c for c in rec["cites"]):
        out.append("cites must be a list of non-empty strings")
    elif any("\n" in c for c in rec["cites"]):
        out.append(_ONE_LINE % "a cite")
    for key in ("ts", "session", "branch", "what", "why"):
        if not isinstance(rec[key], str) or not rec[key].strip():
            out.append(f"{key} must be a non-empty string")
        elif "\n" in rec[key]:
            out.append(_ONE_LINE % key)
    return out


def check(path: str) -> int:
    bad = 0
    with open(path, encoding="utf-8") as fh:
        for n, raw in enumerate(fh, 1):
            line = raw.rstrip("\n")
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"{path}:{n}: not a JSON record ({exc.msg})")
                bad += 1
                continue
            for problem in record_errors(rec):
                print(f"{path}:{n}: {problem}")
                bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(max(check(p) for p in sys.argv[1:]) if sys.argv[1:] else 0)
