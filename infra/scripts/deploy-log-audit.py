#!/usr/bin/env python3
"""Count the deploy-log rows that landed inside a published Kraken API-impacting maintenance window (`maintenance`) or outside the engine's 4-hourly inter-cycle gap (`engine-window`).

Both arms are counts and neither is a gate: they exit 0 whatever they find, and the reader judges.
The one non-zero exit is an unreachable feed, which is an absent measurement rather than a clean one.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.request

FEED_URL = "https://status.kraken.com/api/v2/scheduled-maintenances.json"
FEED_TIMEOUT_SECONDS = 20
USER_AGENT = "zcrypto-deploy-log-audit"

_REPO = pathlib.Path(__file__).resolve().parents[2]
DEPLOY_LOG = _REPO / "docs" / "reference" / "deploy-log.jsonl"

# The engine's window: a row must sit at least `_AFTER_BOUNDARY_SECONDS` past a 4-hourly boundary and
# leave at least `_BEFORE_BOUNDARY_SECONDS` before the next one.
_CYCLE_SECONDS = 4 * 60 * 60
_AFTER_BOUNDARY_SECONDS = 1800
_BEFORE_BOUNDARY_SECONDS = 600

EXIT_OK = 0
EXIT_FEED_UNREACHABLE = 2


def at(stamp: str) -> dt.datetime:
    """The log's and the feed's `...Z` stamps, which `fromisoformat` does not take as written."""
    return dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def load_rows(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


# Same word-boundary shape as `cli/snapshot/delistings.py`'s `_mentions`, for the same reason.
_NAMES_AN_API = re.compile(r"(?<![A-Za-z0-9])(?:websocket|rest)(?![A-Za-z0-9])", re.IGNORECASE)


def api_impacting(maintenances: list[dict]) -> list[dict]:
    """The entries naming WebSocket or REST in a component or in their own name -- an empty
    `components` is not an absent impact.

    Case-folded because the venue spells the same component `WebSocket` and `Websocket` across
    entries, and word-bounded because `REST` is an API: a substring test reads `restart`,
    `Restricted` and `Interest` as API-impacting and books a converge against a window that
    constrains nothing.
    """
    out = []
    for entry in maintenances:
        names = [c.get("name", "") for c in entry.get("components", [])] + [entry.get("name", "")]
        if any(_NAMES_AN_API.search(name) for name in names):
            out.append(entry)
    return out


def inside_window(stamp: str, window: dict) -> bool:
    """A row is inside a window when its stamp falls between that window's own bounds."""
    return at(window["scheduled_for"]) <= at(stamp) <= at(window["scheduled_until"])


def inside_gap(stamp: str) -> bool:
    """A row is inside the engine's gap when it clears the boundary behind it and the one ahead."""
    moment = at(stamp)
    since = (moment.hour * 3600 + moment.minute * 60 + moment.second) % _CYCLE_SECONDS
    return since >= _AFTER_BOUNDARY_SECONDS and _CYCLE_SECONDS - since >= _BEFORE_BOUNDARY_SECONDS


def fetch_maintenances(url: str = FEED_URL, timeout: int = FEED_TIMEOUT_SECONDS) -> list[dict]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)["scheduled_maintenances"]


def read_snapshot(path: str) -> list[dict]:
    return json.loads(pathlib.Path(path).read_text())["scheduled_maintenances"]


def write_snapshot(path: str, maintenances: list[dict]) -> None:
    """The feed's own shape, so a snapshot reads back through the same filter the network path uses."""
    payload = {"scheduled_maintenances": maintenances}
    pathlib.Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


# Hosts whose converge touches nothing that speaks to the venue; re-judged by
# `tests/test_deploy_log_audit.py::test_the_venue_facing_derivation_still_holds`.
NO_VENUE_EXPOSURE = frozenset({"nas", "zaccess"})


def run_maintenance(rows: list[dict], windows: list[dict], *, venue_facing_only: bool = False) -> int:
    considered = [row for row in rows if not (venue_facing_only and row.get("limit", "") in NO_VENUE_EXPOSURE)]
    hits = [
        (row["ts"], row.get("limit", ""), window["name"])
        for row in considered
        for window in windows
        if inside_window(row["ts"], window)
    ]
    scope = " venue-facing" if venue_facing_only else ""
    print(f"rows inside an API-impacting window {len(hits)} of {len(considered)}{scope}")
    for stamp, limit, name in hits:
        print(f"  {stamp} {limit} {name}")
    return EXIT_OK


def run_engine_window(rows: list[dict]) -> int:
    engine = [row for row in rows if "engine" in row["tags"].split(",")]
    outside = [row for row in engine if not inside_gap(row["ts"])]
    failed = [row for row in engine if row["rc"] != 0]
    print(f"engine rows {len(engine)} outside window {len(outside)} failed {len(failed)}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("arm", choices=["maintenance", "engine-window"])
    parser.add_argument("--log", default=str(DEPLOY_LOG), help="the deploy log to read (default: the tracked one)")
    parser.add_argument("--snapshot", help="write the fetched windows here, so a later count keeps this run's coverage")
    parser.add_argument("--from-snapshot", dest="from_snapshot", help="read the windows from this file instead of the network")
    parser.add_argument(
        "--venue-facing",
        dest="venue_facing",
        action="store_true",
        help=f"count only rows whose host has venue exposure (excludes {', '.join(sorted(NO_VENUE_EXPOSURE))})",
    )
    args = parser.parse_args(argv)

    rows = load_rows(pathlib.Path(args.log))
    if args.arm == "engine-window":
        if args.snapshot or args.from_snapshot or args.venue_facing:
            parser.error("--snapshot, --from-snapshot and --venue-facing belong to the maintenance arm")
        return run_engine_window(rows)

    if args.snapshot and args.from_snapshot:
        parser.error("--snapshot records what the network returned; --from-snapshot reads instead of the network")
    if args.from_snapshot:
        maintenances = read_snapshot(args.from_snapshot)
    else:
        try:
            maintenances = fetch_maintenances()
        except (OSError, TimeoutError, ValueError, KeyError) as exc:
            print(f"feed unreachable: {exc}", file=sys.stderr)
            return EXIT_FEED_UNREACHABLE
        if args.snapshot:
            write_snapshot(args.snapshot, maintenances)
    return run_maintenance(rows, api_impacting(maintenances), venue_facing_only=args.venue_facing)


if __name__ == "__main__":
    sys.exit(main())
