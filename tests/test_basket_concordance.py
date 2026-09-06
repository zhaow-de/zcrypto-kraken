"""The basket-vs-universe concordance pin (spec 00089 D2/D5): a universe regeneration that shifts
selection turns this red rather than letting `cli/engine/store.py::BASKET` diverge silently."""

import re
from pathlib import Path

_DOC = Path(__file__).resolve().parent.parent / "docs" / "universe" / "point-in-time-universe.md"

# The ruled exceptions (T0137): editing either side without a ruling is the drift this test catches.

# RULED (owner, T0137): DOT stays traded. It misses the universe's volume floor by ~2%, and that
# floor is a footprint-sizing rule the traded rung sizes sit far below -- retiring DOT would trade a
# marginal miss for a standing deviation between the live book and record 44's evidence base.
RULED_TRADED_BUT_DESELECTED = {"DOT/EUR"}

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
