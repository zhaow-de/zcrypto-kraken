"""Scan Kraken's published maintenance feed for delistings that name a selected asset.

`sweep_refusals` (register.py) catches an identity change once `AssetPairs` reflects it -- the day
it happens. Kraken announces an ASSET delisting on its status page 93-116 days ahead (measured
2026-08-28 over the four asset-delisting entries then live), so the same finding is available a
quarter earlier from a feed this repo already fetches for converge scheduling
(`.claude/rules/fleet-deploys.md`). One fetch, a second filter.

Notice is a property of the entry CLASS, not of the feed: `_DELISTING_WORDS` also matches the
funding-rail shape, which can be retroactive -- "Arbitrum Nova Deposits and Withdrawals
Discontinued" was published five minutes before its effective time, for a change already a day old.
Read a hit's own dates; never assume the quarter.

The feed is the caller's to supply. A module that fetched would put a live venue endpoint inside
the test suite, where it is a flake source and skips silently if the venue blocks the runner -- and
a silent skip on the routine that gates the go/no-go reads as coverage.
"""

from __future__ import annotations

import re

# Name OR components: the 2026-09-25 "Rain (RAIN) Delisting" entry carries its asset only in
# `components`, so a name-only scan misses that shape. Both halves are searched.
_DELISTING_WORDS = ("delist", "discontinu")


def _mentions(text: str, asset: str, *, ignore_case: bool = True) -> bool:
    """Word-boundary match: `DOT` must not fire on `POLKADOT`, and a false alarm on the routine that
    gates the go/no-go costs more than the substring convenience is worth.

    `ignore_case` is False over announcement PROSE. Titles and component names are ticker-shaped, so
    folding case there is free; bodies are English sentences, where `LINK` would match "the link
    below" -- constructed, in `test_body_matching_is_case_sensitive_so_prose_cannot_fire_a_ticker`;
    no live body has collided yet. Kraken writes tickers uppercase in bodies, so a case-sensitive
    pass keeps the notice without importing that false positive.
    """
    flags = re.IGNORECASE if ignore_case else 0
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(asset)}(?![A-Za-z0-9])", text, flags) is not None


def scan_delistings(feed: dict, selected_assets: tuple[str, ...] | list[str]) -> list[dict]:
    """Entries in `feed` announcing a delisting that names one of `selected_assets`.

    Completed entries are NOT filtered out: the feed retains them, and a sweep run after the fact
    needs to see a delisting that already happened at least as much as one that has not.
    """
    hits: list[dict] = []
    for entry in feed.get("scheduled_maintenances", []):
        name = entry.get("name") or ""
        if not any(word in name.lower() for word in _DELISTING_WORDS):
            continue
        # THREE places an asset can be named, and the third is why this is not just name+components:
        # the 2026-09-25 "Delisting assets for UAE clients" entry names its seven assets ONLY in
        # `incident_updates[].body` -- no ticker in the title, no components at all. The argument for
        # reading components applies one level further down, and a name+components scan is silent on
        # that shape. Bodies are matched case-SENSITIVELY (see `_mentions`). A FOURTH site exists --
        # `incident_updates[].affected_components[]` -- deliberately unread: every ticker it carries
        # is also in the name or the body across all five live delisting entries (2026-08-28), so it
        # would widen the haystack and reach nothing new.
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
