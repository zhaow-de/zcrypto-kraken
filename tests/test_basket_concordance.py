"""The basket-vs-universe concordance pin (spec 00089 D2/D5, baseline shrunk per spec 00094 D7;
the ruled baseline is T0137's).

The traded basket is record 47's twelve legs -- the ten /EUR bases plus ETH/BTC and SOL/BTC held
at structurally-zero targets (spec 00094 D1) -- a code constant, `cli/engine/store.py::BASKET`.
The committed universe doc carries the selection. This test is the ONLY place the two meet: a
future regeneration that shifts selection turns it red and forces a conscious edit of the ruled
baseline -- divergence can never again arrive silently, and the engine host never reads the
universe artifact.
"""

import re
from pathlib import Path

_DOC = Path(__file__).resolve().parent.parent / "docs" / "universe" / "point-in-time-universe.md"

# The ruled exceptions -- each owned by T0137; editing either side without a ruling is the
# drift this test exists to catch.

# RULED (owner, 2026-08-14, T0137): DOT stays traded. The 150,000 volume floor it misses is a
# footprint-sizing rule -- a full EUR 1,400 position is roughly 1% of median daily volume -- and
# DOT at 146,957 is only 2% under it, with 6b rung sizes sitting far below that footprint.
# Retiring it would trade a 2% miss for a standing deviation between the live book and record
# 44's evidence base. No revisit deferral dangles: this test is the trigger, DOT's re-entry
# included.
RULED_TRADED_BUT_DESELECTED = {"DOT/EUR"}

# RETIRED (T0137's 2026-08-14 multi-quote solve survey + the owner's same-day ruling): the /BTC
# legs WERE genuinely unreachable, but the RECORDED REASON was wrong -- the adapter always saw
# both XXBT-quoted legs, and the real obstacle was the engine's own EUR-only plumbing (base-keyed
# PAIR_KEYS/INSTRUMENT_IDS/VenueState, EUR-only sizing and costmin). The owner ruled the /BTC
# half pursued during 6b, ahead of phase 7, and spec 00094 removes that plumbing. Kept empty
# rather than deleted so a future selected-but-unreachable divergence still has somewhere to land.
RULED_SELECTED_BUT_UNREACHABLE = set()


def _selected() -> set[str]:
    text = _DOC.read_text()
    block = text.split("## Selected universe")[1].split("##")[0]
    symbols = {s.strip() for s in block.strip().split(",")}
    assert all(re.fullmatch(r"[A-Z]+/[A-Z]+", s) for s in symbols), symbols
    return symbols


def test_the_basket_and_the_universe_diverge_exactly_as_ruled():
    from cli.engine.store import BASKET

    basket = set(BASKET)
    selected = _selected()
    assert basket - selected == RULED_TRADED_BUT_DESELECTED, (
        "the traded basket carries symbols the universe no longer selects, beyond the ruled "
        "baseline -- a T0137 re-ratification decision, not an edit to this constant"
    )
    assert selected - basket == RULED_SELECTED_BUT_UNREACHABLE, (
        "the universe selects symbols the basket cannot express, beyond the ruled baseline -- "
        "the /BTC legs are reachable now (spec 00094), so this is a genuine new divergence, "
        "not the retired exception"
    )
