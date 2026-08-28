import json
from pathlib import Path

from cli.snapshot.register import build_snapshot, render_markdown

_FIXTURES = Path(__file__).parent / "fixtures"
ASSETPAIRS = json.loads((_FIXTURES / "kraken_assetpairs.json").read_text())
ASSETS = json.loads((_FIXTURES / "kraken_assets.json").read_text())
SYMBOLS = ["BTC/EUR", "DOGE/EUR", "1INCH/EUR"]
FETCHED_AT = "2026-07-07T00:00:00+00:00"


def test_build_snapshot_deterministic_given_fixed_fetched_at():
    a = build_snapshot(ASSETPAIRS, ASSETS, SYMBOLS, FETCHED_AT)
    b = build_snapshot(ASSETPAIRS, ASSETS, SYMBOLS, FETCHED_AT)
    assert a == b
    assert a["fetched_at"] == FETCHED_AT
    assert len(a["raw_sha256"]) == 64
    assert a["raw"] == {"assetpairs": ASSETPAIRS, "assets": ASSETS}


def test_build_snapshot_hash_changes_with_raw_input():
    a = build_snapshot(ASSETPAIRS, ASSETS, SYMBOLS, FETCHED_AT)
    mutated_assets = dict(ASSETS, XXBT=dict(ASSETS["XXBT"], status="disabled"))
    b = build_snapshot(ASSETPAIRS, mutated_assets, SYMBOLS, FETCHED_AT)
    assert a["raw_sha256"] != b["raw_sha256"]


def test_render_markdown_contains_basket_rows_and_provenance_hash():
    snapshot = build_snapshot(ASSETPAIRS, ASSETS, SYMBOLS, FETCHED_AT)
    md = render_markdown(snapshot)
    assert "BTC/EUR" in md
    assert "DOGE/EUR" in md
    assert snapshot["raw_sha256"] in md
    assert FETCHED_AT in md
    assert "XBT" in md and "XDG" in md  # alias ledger


# --- the sweep's verdict is a refusal, not a table a human diffs by eye ----------------------------
# `/zcrypto-refdata-sweep` step 3 says "diff the rendered tables against the committed ones". A
# twelve-row table read by eye is exactly where a `NOT FOUND`, a `status` that stopped saying
# `online`, or a renamed altname gets scrolled past -- and those three ARE [[T0025]]'s trigger:
# a selected pair changing identity underneath us. `sweep_refusals` turns each into a reason string,
# so the routine refuses instead of the reader noticing.

from cli.snapshot.register import sweep_refusals  # noqa: E402 -- the file's own section header above


def _snapshot(**overrides):
    """A clean two-pair snapshot, then whatever the case under test breaks."""
    snap = build_snapshot(ASSETPAIRS, ASSETS, ["BTC/EUR", "DOGE/EUR"], FETCHED_AT)
    for row in snap["universe"]:
        row.setdefault("status", "online")
        if row["symbol"] in overrides:
            row.update(overrides[row["symbol"]])
    return snap


def test_a_clean_snapshot_refuses_nothing():
    """The true positive. A guard that refuses everything is as useless as one that refuses nothing,
    and this is the case that must stay silent on every routine sweep."""
    assert sweep_refusals(_snapshot()) == []


def test_a_selected_pair_that_left_assetpairs_is_a_refusal():
    """Delisting -- the trigger leg T0025 was actually waiting for. `found` false is how the register
    already renders it (`NOT FOUND`); the difference is that nothing acted on it."""
    reasons = sweep_refusals(_snapshot(**{"BTC/EUR": {"found": False, "pair_key": None}}))
    assert len(reasons) == 1 and "BTC/EUR" in reasons[0]
    assert "not in AssetPairs" in reasons[0], reasons


def test_a_pair_whose_status_stopped_saying_online_is_a_refusal():
    """A pair can stay listed and stop being tradeable -- `cancel_only`, `post_only`, `reduce_only`.
    Rendered in the table today, acted on by nothing."""
    reasons = sweep_refusals(_snapshot(**{"DOGE/EUR": {"status": "cancel_only"}}))
    assert len(reasons) == 1 and "DOGE/EUR" in reasons[0] and "cancel_only" in reasons[0], reasons


def test_an_altname_that_drifted_from_the_committed_alias_is_a_refusal():
    """A redenomination reaches us as an altname change. The baseline is `_COMMON_TO_KRAKEN`, the
    same constant the wsname lookup tolerates spellings from, so the check and the parser cannot
    disagree about what the alias IS."""
    reasons = sweep_refusals(_snapshot(**{"BTC/EUR": {"base_altname": "XBTNEW"}}))
    assert len(reasons) == 1 and "BTC" in reasons[0] and "XBTNEW" in reasons[0], reasons


def test_every_refusal_is_reported_not_just_the_first():
    """Two pairs can move in one sweep -- a batch delisting is announced as a batch. A check that
    returns on the first one hides the rest until the next month."""
    reasons = sweep_refusals(_snapshot(**{"BTC/EUR": {"found": False, "pair_key": None}, "DOGE/EUR": {"status": "cancel_only"}}))
    assert len(reasons) == 2, reasons
