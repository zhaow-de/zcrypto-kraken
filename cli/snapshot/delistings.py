"""Scan a caller-supplied Kraken maintenance feed (`zcrypto-refdata-sweep` fetches it) for delistings naming a selected asset -- the
identity change `sweep_refusals` catches only the day it happens. Fetching would put a live venue endpoint in the test suite, where
a silent skip reads as coverage. How much notice a hit gives is a property of its entry class, not the feed: `_DELISTING_WORDS` also
matches funding-rail discontinuations, which can be published after they take effect, so read a hit's own dates."""

from __future__ import annotations

import re

_DELISTING_WORDS = ("delist", "discontinu")


def _mentions(text: str, asset: str, *, ignore_case: bool = True) -> bool:
    """Word-boundary match (`DOT` not `POLKADOT`); fold case over ticker-shaped text, never English bodies where `LINK` is prose."""
    flags = re.IGNORECASE if ignore_case else 0
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(asset)}(?![A-Za-z0-9])", text, flags) is not None


def scan_delistings(feed: dict, selected_assets: tuple[str, ...] | list[str]) -> list[dict]:
    """Entries in `feed` announcing a delisting that names one of `selected_assets`, completed windows included -- the feed retains
    them, and a sweep run after the fact needs a delisting that already happened."""
    hits: list[dict] = []
    for entry in feed.get("scheduled_maintenances", []):
        name = entry.get("name") or ""
        if not any(word in name.lower() for word in _DELISTING_WORDS):
            continue
        # Bodies are scanned: an entry has named its assets only there; `affected_components[]` stays unread, measured.
        tickerish = name + " " + " ".join(c.get("name", "") for c in entry.get("components", []))
        prose = " ".join(u.get("body", "") for u in entry.get("incident_updates", []))
        for asset in selected_assets:
            if _mentions(tickerish, asset) or _mentions(prose, asset, ignore_case=False):
                hits.append(
                    {
                        "asset": asset,
                        "name": name,
                        "scheduled_for": entry.get("scheduled_for", ""),
                        "created_at": entry.get("created_at", ""),
                        "status": entry.get("status", ""),
                    }
                )
    return hits
