"""Kraken announces an asset delisting 93-116 days ahead on its status page, and nothing read it.

T0025's trigger is a selected pair changing identity underneath us. `sweep_refusals` catches the
change once `AssetPairs` reflects it -- which is the day it happens. This reads the announcement
instead, which is the same finding with a quarter's notice -- for the asset-delisting class; the
funding-rail shape the same filter catches can be published after it takes effect. The feed already governs
converge scheduling (`fleet-deploys.md`); this is a second filter over one fetch.

The scan takes the FEED as an argument rather than fetching: a test that reaches the network is a
flake source in CI and skips silently when the venue blocks the runner, so a skip would read as
coverage. `zcrypto-refdata-sweep` does the fetching.
"""

from cli.snapshot.delistings import scan_delistings

SELECTED = ("BTC", "ETH", "DOGE", "EUR")


def _feed(*entries):
    return {"scheduled_maintenances": list(entries)}


def _entry(name, when="2026-12-01T00:00:00.000Z", components=()):
    return {
        "name": name,
        "scheduled_for": when,
        "created_at": "2026-08-01T00:00:00.000Z",
        "status": "scheduled",
        "components": [{"name": c} for c in components],
    }


def test_an_unrelated_delisting_is_not_a_hit():
    """The true positive, and the common case: Kraken delists assets constantly and almost none of
    them are ours. A scan that flags every delisting is a scan nobody reads."""
    feed = _feed(
        _entry("PLANCK, AIR, MICHI, FLY Delisting"), _entry("Rain (RAIN) Delisting", components=("Rain (RAIN) - Arbitrum One",))
    )
    assert scan_delistings(feed, SELECTED) == []


def test_a_selected_asset_named_in_a_delisting_is_a_hit():
    hits = scan_delistings(_feed(_entry("DOGE, MOON, KET Delisting")), SELECTED)
    assert len(hits) == 1 and hits[0]["asset"] == "DOGE"
    assert hits[0]["scheduled_for"].startswith("2026-12-01")


def test_a_selected_asset_in_the_components_is_a_hit_too():
    """The 2026-09-25 Rain entry carries its asset only in `components`, not in the name -- a
    name-only scan misses that shape entirely."""
    hits = scan_delistings(_feed(_entry("Asset Delisting", components=("Ethereum (ETH) - Mainnet",))), SELECTED)
    assert len(hits) == 1 and hits[0]["asset"] == "ETH"


def test_a_substring_of_a_longer_ticker_is_not_a_hit():
    """`DOT` must not match `POLKADOT` or `DOTX`. Word-boundary matching, because a substring hit
    here costs a false alarm on the one routine that gates the go/no-go."""
    assert scan_delistings(_feed(_entry("POLKADOTX, DOTTED Delisting")), SELECTED) == []


def test_a_completed_window_in_the_past_is_still_reported():
    """The feed retains completed entries (T0145). A delisting that already happened is exactly what
    a sweep run after the fact needs to see -- filtering by status would hide it."""
    hits = scan_delistings(_feed(_entry("BTC Delisting", when="2026-01-01T00:00:00.000Z")), SELECTED)
    assert len(hits) == 1


def test_non_delisting_maintenance_is_ignored():
    """The feed is mostly maintenance windows; only the delisting class concerns identity."""
    assert scan_delistings(_feed(_entry("Kraken Website and API Maintenance", components=("WebSocket",))), SELECTED) == []


def _entry_with_body(name, body, when="2026-12-01T00:00:00.000Z"):
    e = _entry(name, when=when)
    e["incident_updates"] = [{"body": body}]
    return e


def test_an_asset_named_only_in_the_announcement_body_is_a_hit():
    """The shape the live feed actually contains: "Delisting assets for UAE clients" (2026-09-25)
    names its seven assets only in `incident_updates[].body` -- no ticker in the title, no
    components. A name+components scan is silent on it, which is the whole notice lost."""
    feed = _feed(
        _entry_with_body(
            "Delisting assets for UAE clients", "…delisting cycle for the following assets…: XMR, ZEC, DASH, ETH, and USDE."
        )
    )
    hits = scan_delistings(feed, SELECTED)
    assert len(hits) == 1 and hits[0]["asset"] == "ETH", hits


def test_body_matching_is_case_sensitive_so_prose_cannot_fire_a_ticker():
    """Bodies are English. `LINK` matches "the link below" under IGNORECASE -- constructed below, not
    taken from a live entry. Kraken writes tickers uppercase, so case-sensitivity over prose keeps
    the notice and drops the noise."""
    feed = _feed(_entry_with_body("Some Delisting", "Please check the link below and the dot point."))
    assert scan_delistings(feed, ("LINK", "DOT")) == []
    feed_real = _feed(_entry_with_body("Some Delisting", "Delisting LINK and DOT."))
    assert {h["asset"] for h in scan_delistings(feed_real, ("LINK", "DOT"))} == {"LINK", "DOT"}
