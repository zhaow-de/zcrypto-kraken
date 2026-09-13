#!/usr/bin/env python3
"""Pin rows of `fleet-pins.md` whose digest no deploy-log row records.

The set is the rows that CARRY a digest: the third cell holds a 12-hex prefix for an image pin and a version
string for a package pin (alloy's v-string twin, agentboard), and a version pin is converged by a path with no
digest to match. A non-zero count is a pin recorded as live that no converge in the log produced.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

DIGEST = re.compile(r"\b([0-9a-f]{12})[0-9a-f]*\b")
CELL_DIGEST = re.compile(r"`([0-9a-f]{12})`")


def repo_root() -> pathlib.Path:
    done = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if done.returncode != 0:
        print(f"pins-converged: not a git checkout: {done.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2)
    return pathlib.Path(done.stdout.strip())


def converged_digests(log_path: pathlib.Path) -> set[str]:
    """Every 12-hex prefix any row passed as an extra var or committed as a pin.

    Matched on the digest, not the var's name: the name differs per role, so a name list would rot.
    """
    out: set[str] = set()
    for n, line in enumerate(log_path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"pins-converged: {log_path} is not JSONL at line {n}: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        blob = json.dumps(row.get("extra_vars") or {}) + " " + json.dumps(row.get("committed_pins") or {})
        out.update(m.group(1) for m in DIGEST.finditer(blob))
    return out


def unconverged_pins(pins_path: pathlib.Path, seen: set[str]) -> list[tuple[str, str, str]]:
    rows = []
    for line in pins_path.read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        m = CELL_DIGEST.search(cells[2])
        if m and m.group(1) not in seen:
            rows.append((cells[0], cells[1], m.group(1)))
    return rows


def main() -> int:
    root = repo_root()
    seen = converged_digests(root / "docs/reference/deploy-log.jsonl")
    owed = unconverged_pins(root / "docs/reference/fleet-pins.md", seen)
    print(len(owed))
    for service, host, digest in owed:
        print(f"  {service} on {host}: {digest} is pinned and no deploy-log row converged it", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
