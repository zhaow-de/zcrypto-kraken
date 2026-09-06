"""`scan_delistings` over a caller-supplied Kraken maintenance feed -- no test here reaches the network."""

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
    """The true positive: Kraken delists constantly and almost none of it is ours."""
    feed = _feed(
        _entry("PLANCK, AIR, MICHI, FLY Delisting"), _entry("Rain (RAIN) Delisting", components=("Rain (RAIN) - Arbitrum One",))
    )
    assert scan_delistings(feed, SELECTED) == []


def test_a_selected_asset_named_in_a_delisting_is_a_hit():
    hits = scan_delistings(_feed(_entry("DOGE, MOON, KET Delisting")), SELECTED)
    assert len(hits) == 1 and hits[0]["asset"] == "DOGE"
    assert hits[0]["scheduled_for"].startswith("2026-12-01")


def test_a_selected_asset_in_the_components_is_a_hit_too():
    """The 2026-09-25 Rain entry carries its asset only in `components`, not in the name."""
    hits = scan_delistings(_feed(_entry("Asset Delisting", components=("Ethereum (ETH) - Mainnet",))), SELECTED)
    assert len(hits) == 1 and hits[0]["asset"] == "ETH"


def test_a_substring_of_a_longer_ticker_is_not_a_hit():
    """A substring hit costs a false alarm on the one routine that gates the go/no-go."""
    assert scan_delistings(_feed(_entry("POLKADOTX, DOTTED Delisting")), SELECTED) == []


def test_a_completed_window_in_the_past_is_still_reported():
    """The feed retains completed entries (T0145)."""
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
    """The live feed's "Delisting assets for UAE clients" (2026-09-25) names its assets only in
    `incident_updates[].body` -- no ticker in the title, no components."""
    feed = _feed(
        _entry_with_body(
            "Delisting assets for UAE clients", "…delisting cycle for the following assets…: XMR, ZEC, DASH, ETH, and USDE."
        )
    )
    hits = scan_delistings(feed, SELECTED)
    assert len(hits) == 1 and hits[0]["asset"] == "ETH", hits


def test_body_matching_is_case_sensitive_so_prose_cannot_fire_a_ticker():
    """Kraken writes tickers uppercase and bodies are English, so body matching is case-sensitive;
    the `LINK` false positive below is constructed, not taken from a live entry."""
    feed = _feed(_entry_with_body("Some Delisting", "Please check the link below and the dot point."))
    assert scan_delistings(feed, ("LINK", "DOT")) == []
    feed_real = _feed(_entry_with_body("Some Delisting", "Delisting LINK and DOT."))
    assert {h["asset"] for h in scan_delistings(feed_real, ("LINK", "DOT"))} == {"LINK", "DOT"}
