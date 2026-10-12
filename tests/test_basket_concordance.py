"""The basket-vs-universe concordance pin (spec 00089 D2/D5): a universe regeneration that shifts
selection turns this red rather than letting `cli/engine/store.py::BASKET` diverge silently."""

import re
from pathlib import Path

_DOC = Path(__file__).resolve().parent.parent / "docs" / "universe" / "point-in-time-universe.md"

# The ruled exceptions (T0137): editing either side without a ruling is the drift this test catches.

# RULED (owner, T0137): DOT stayed traded while it missed the universe's volume floor by ~2%. The
# 2026-10-12 refresh selects it again (median 768,357 EUR/day against the 150,000 floor), so the ruled
# exception is discharged; kept empty rather than deleted, as the home of the next such ruling.
RULED_TRADED_BUT_DESELECTED: set[str] = set()

# Kept empty rather than deleted: the /BTC legs' unreachability was retired by spec 00094 (T0137),
# and an empty set is where a future selected-but-unreachable divergence lands.
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
