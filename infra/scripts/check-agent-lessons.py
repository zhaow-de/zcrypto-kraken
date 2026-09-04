#!/usr/bin/env python3
"""Shape check for an agent-lessons inbox (`.local/agent-lessons/<session>.jsonl`), run at harvest.

Every line is one JSON object with exactly the required keys, `kind` from the enum, `cites`
a list of strings, every other value a non-empty string. Refuses prose, blank lines and extra
keys: an inbox is a harvest input for the refine-rules round, not a story board.
"""

import json
import sys

REQUIRED = {"ts", "session", "branch", "kind", "cites", "what", "why"}
KINDS = {"self-correction", "rule-deviation", "rule-feedback", "skill-feedback", "miscount"}


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
            if not isinstance(rec, dict) or set(rec) != REQUIRED:
                print(f"{path}:{n}: keys must be exactly {sorted(REQUIRED)}")
                bad += 1
                continue
            if rec["kind"] not in KINDS:
                print(f"{path}:{n}: kind must be one of {sorted(KINDS)}, got {rec['kind']!r}")
                bad += 1
            if not isinstance(rec["cites"], list) or not all(isinstance(c, str) and c for c in rec["cites"]):
                print(f"{path}:{n}: cites must be a list of non-empty strings")
                bad += 1
            for key in ("ts", "session", "branch", "what", "why"):
                if not isinstance(rec[key], str) or not rec[key].strip():
                    print(f"{path}:{n}: {key} must be a non-empty string")
                    bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(max(check(p) for p in sys.argv[1:]) if sys.argv[1:] else 0)
