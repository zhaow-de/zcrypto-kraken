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
CELL_DIGEST = re.compile(r"`([0-9a-f]{12})[0-9a-f]*`")
DIGEST_HEADER = "digest"


def repo_root() -> pathlib.Path:
    done = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if done.returncode != 0:
        print(f"pins-converged: not a git checkout: {done.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2)
    return pathlib.Path(done.stdout.strip())


def converged_digests(log_path: pathlib.Path) -> set[str]:
    """Every 12-hex prefix a SUCCESSFUL converge was handed on the command line.

    Two exclusions a reader would otherwise undo. `rc != 0`: `converge.sh` records a refused run exactly like a
    pass. `committed_pins`: it is read from `host_vars` at record time, so it lands in the row whatever the run
    deployed. Matched on the digest, not the var's name, which differs per role.
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
        if row.get("rc") != 0:
            continue
        out.update(m.group(1) for m in DIGEST.finditer(json.dumps(row.get("extra_vars") or {})))
    return out


def unconverged_pins(pins_path: pathlib.Path, seen: set[str]) -> list[tuple[str, str, str]]:
    """A table whose digest header this cannot find is an error, not an empty answer: a hand edit must not take
    every row out of the count silently."""
    rows: list[tuple[str, str, str]] = []
    digest_col: int | None = None
    scanned = 0
    for line in pins_path.read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if digest_col is None or DIGEST_HEADER in cells[digest_col].lower():
            found = [k for k, c in enumerate(cells) if DIGEST_HEADER in c.lower()]
            if found:
                digest_col = found[0]
                continue
        if digest_col is None or len(cells) <= max(digest_col, 1):
            continue
        scanned += 1
        m = CELL_DIGEST.search(cells[digest_col])
        if m and m.group(1) not in seen:
            rows.append((cells[0], cells[1], m.group(1)))
    if digest_col is None or not scanned:
        print(f"pins-converged: no digest column found in {pins_path} -- the table's shape changed", file=sys.stderr)
        raise SystemExit(2)
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
