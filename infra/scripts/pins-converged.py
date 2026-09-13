#!/usr/bin/env python3
"""Pin rows of `fleet-pins.md` whose digest no deploy-log row records.

The set is the rows whose digest column carries a 12-hex prefix; a version pin (the second table) has no digest
to match and is converged by another path. A non-zero count is a pin recorded as live that no successful
converge in the log was handed.
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
    """Every column is found by its header, and a header row without a digest column (the version-pin table)
    turns the lookup off until the next header. A file with no digest header at all is an error, not an empty
    answer: a hand edit must not take every row out of the count silently."""
    rows: list[tuple[str, str, str]] = []
    cols: dict[str, int] | None = None
    scanned = 0
    for line in pins_path.read_text().splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().lower() for c in line.strip("|").split("|")]
        raw = [c.strip() for c in line.strip("|").split("|")]
        if any(c == "host" for c in cells):  # a header row: both tables carry a host column
            digest = [k for k, c in enumerate(cells) if DIGEST_HEADER in c]
            cols = (
                None
                if not digest
                else {
                    "digest": digest[0],
                    "service": next((k for k, c in enumerate(cells) if c in ("service", "package")), 0),
                    "host": cells.index("host"),
                }
            )
            continue
        if cols is None or len(raw) <= max(cols.values()) or set(raw) <= {"---", ""}:
            continue
        scanned += 1
        m = CELL_DIGEST.search(raw[cols["digest"]])
        if m and m.group(1) not in seen:
            rows.append((raw[cols["service"]], raw[cols["host"]], m.group(1)))
    if not scanned:
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
