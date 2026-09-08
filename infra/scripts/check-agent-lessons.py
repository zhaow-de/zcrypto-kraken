#!/usr/bin/env python3
"""Shape check for an agent-lessons inbox (`.local/agent-lessons/<session>.jsonl`), run at harvest.
Refuses prose, blank lines and extra keys: an inbox is a harvest input for the refine-rules round,
not a story board.
"""

import io
import json
import sys

REQUIRED = {"ts", "session", "branch", "kind", "cites", "what", "why"}
KINDS = {"self-correction", "rule-deviation", "rule-feedback", "skill-feedback", "miscount"}
# A lesson field is one line, and every other check accepts a multi-line one: it is a non-empty string
# of the right type, so nothing else here refuses it.
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
    try:
        # Universal-newline mode is load-bearing: `newline=""` lets a lone CR collapse an inbox to one line.
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        # Acquiring the text, not examining it: nothing was read AS a record, so nothing here can be a
        # malformed one. Caught any later, the decode escapes `check` and strands the paths after this.
        reason = exc.strerror if isinstance(exc, OSError) else str(exc)
        print(f"cannot read {path}: {reason}", file=sys.stderr)
        return 2
    # `io.StringIO` iterates the text exactly as iterating the file object would; `splitlines()` breaks
    # on separators that iteration does not, leaving the tool disagreeing with the file about its lines.
    for n, raw in enumerate(io.StringIO(text), 1):
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
    if not sys.argv[1:]:
        # Exiting 0 with nothing opened reports a clean this run never measured.
        print(f"usage: {sys.argv[0]} <inbox.jsonl>...", file=sys.stderr)
        sys.exit(2)
    sys.exit(max(check(p) for p in sys.argv[1:]))
