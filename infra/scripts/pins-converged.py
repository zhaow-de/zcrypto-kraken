#!/usr/bin/env python3
"""(Pin, host) pairs of `fleet-pins.md` that no deploy-log row on that host converged.

The set is the rows whose digest column carries a 12-hex prefix; a version pin (the second table) has no digest
to match and is converged by another path.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import yaml

DIGEST = re.compile(r"\b([0-9a-f]{12})[0-9a-f]*\b")
CELL_DIGEST = re.compile(r"`([0-9a-f]{12})[0-9a-f]*`")
DIGEST_HEADER = "digest"


def repo_root() -> pathlib.Path:
    done = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if done.returncode != 0:
        print(f"pins-converged: not a git checkout: {done.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2)
    return pathlib.Path(done.stdout.strip())


def inventory_groups(root: pathlib.Path) -> dict[str, set[str]]:
    """Group name -> the hosts under it, from the committed inventory file (never `ansible-inventory`).

    A child group is a reference -- defined with its hosts elsewhere in the file -- so every definition is
    collected before any is resolved."""
    tree = yaml.safe_load((root / "infra/ansible/inventory/hosts.yml").read_text()) or {}
    hosts: dict[str, set[str]] = {}
    children: dict[str, set[str]] = {}

    def collect(name: str, node: dict) -> None:
        hosts.setdefault(name, set()).update((node or {}).get("hosts") or {})
        for child, sub in ((node or {}).get("children") or {}).items():
            children.setdefault(name, set()).add(child)
            collect(child, sub)

    for name, node in tree.items():
        collect(name, node)

    def resolve(name: str, seen: frozenset[str] = frozenset()) -> set[str]:
        return hosts.get(name, set()) | {h for c in children.get(name, set()) - seen for h in resolve(c, seen | {name})}

    return {name: resolve(name) for name in hosts}


def _hosts(limit: str, groups: dict[str, set[str]]) -> set[str]:
    return {h for part in limit.split(",") for h in (groups.get(part.strip()) or {part.strip()})}


def converged_digests(log_path: pathlib.Path, groups: dict[str, set[str]]) -> dict[str, set[str]]:
    """Each 12-hex prefix a successful converge was handed, mapped to the hosts it ran on.

    `rc != 0` is out: `converge.sh` records a pass whatever its `rc`, so an interrupted one (the log's `rc 99`)
    lands like a clean one. An extra var counts on any run. `committed_pins` counts only on a run that applied
    the rendered stack (`-e nas_apply_compose=true`): the field is read from `host_vars/<limit>/vars.yml` at
    record time, and the nas role's `compose up -d` and restarts are flag-gated, so a render-only run lands the
    pin in the row having restarted nothing. Matched on the digest, not the var's name, which differs per role.
    """
    out: dict[str, set[str]] = {}
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
        extra = row.get("extra_vars") or {}
        payloads = [extra]
        if extra.get("nas_apply_compose") in (True, "true"):
            payloads.append(row.get("committed_pins") or {})
        for m in DIGEST.finditer(json.dumps(payloads)):
            out.setdefault(m.group(1), set()).update(_hosts(str(row.get("limit", "")), groups))
    return out


def unconverged_pins(pins_path: pathlib.Path, evidence: dict[str, set[str]]) -> list[tuple[str, str, str]]:
    """One (pin, host) per host the row names that no successful row on that host evidences.

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
                }
            )
            continue
        if cols is None or len(raw) <= max(cols.values()) or set(raw) <= {"---", ""}:
            continue
        scanned += 1
        m = CELL_DIGEST.search(raw[cols["digest"]])
        if not m:
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
    evidence = converged_digests(root / "docs/reference/deploy-log.jsonl", inventory_groups(root))
    owed = unconverged_pins(root / "docs/reference/fleet-pins.md", evidence)
    print(len(owed))
    for service, host, digest in owed:
        print(f"  {service} on {host}: {digest} is pinned and no deploy-log row on {host} converged it", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
