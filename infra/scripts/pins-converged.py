#!/usr/bin/env python3
"""(Pin, host) pairs of `fleet-pins.md` that no deploy-log row on that host converged.

The set is the rows whose digest column carries a 12-hex prefix and whose `since` falls inside the log's span; a
version pin (the second table) has no digest to match and is converged by another path.
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


def converged_digests(log_path: pathlib.Path) -> tuple[dict[str, set[str]], str]:
    """Each 12-hex prefix a successful converge was handed on the command line, with the hosts it ran on, and
    the log's first stamp.

    Two exclusions a reader would otherwise undo. `rc != 0`: `converge.sh` records a pass whatever its `rc`, so
    an interrupted one (the log's `rc 99`) lands like a clean one. `committed_pins`: it is read from `host_vars`
    at record time, so it lands in the row whatever the run deployed. Matched on the digest, not the var's name,
    which differs per role.
    """
    out: dict[str, set[str]] = {}
    first = ""
    for n, line in enumerate(log_path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"pins-converged: {log_path} is not JSONL at line {n}: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        stamp = str(row.get("ts", ""))
        first = min(first, stamp) if first else stamp
        if row.get("rc") != 0:
            continue
        for m in DIGEST.finditer(json.dumps(row.get("extra_vars") or {})):
            out.setdefault(m.group(1), set()).add(str(row.get("limit", "")))
    return out, first


def unconverged_pins(pins_path: pathlib.Path, evidence: dict[str, set[str]], log_start: str) -> list[tuple[str, str, str]]:
    """One (pin, host) per host the row names that no successful row on that host evidences. A row whose `since`
    predates the log's first stamp is named on stderr and left out: the log cannot speak for it either way.

    Every column is found by its header, and a header row without a digest column (the version-pin table)
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
                    "since": next((k for k, c in enumerate(cells) if c.startswith("since")), -1),
                }
            )
            continue
        if cols is None or len(raw) <= max(cols.values()) or set(raw) <= {"---", ""}:
            continue
        scanned += 1
        m = CELL_DIGEST.search(raw[cols["digest"]])
        if not m:
            continue
        since = raw[cols["since"]][:10] if cols["since"] >= 0 else ""
        if since and log_start and since < log_start[:10]:
            print(
                f"pins-converged: {raw[cols['service']]} since {since} predates the log's first row ({log_start[:10]}); not in the set",
                file=sys.stderr,
            )
            continue
        for host in (h.strip() for h in raw[cols["host"]].split(",")):
            if host not in evidence.get(m.group(1), set()):
                rows.append((raw[cols["service"]], host, m.group(1)))
    if not scanned:
        print(f"pins-converged: no digest column found in {pins_path} -- the table's shape changed", file=sys.stderr)
        raise SystemExit(2)
    return rows


def main() -> int:
    root = repo_root()
    evidence, log_start = converged_digests(root / "docs/reference/deploy-log.jsonl")
    owed = unconverged_pins(root / "docs/reference/fleet-pins.md", evidence, log_start)
    print(len(owed))
    for service, host, digest in owed:
        print(f"  {service} on {host}: {digest} is pinned and no deploy-log row on {host} converged it", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
