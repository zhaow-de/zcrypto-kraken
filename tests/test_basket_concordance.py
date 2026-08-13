"""The basket-vs-universe concordance pin (spec 00089 D2/D5; the ruled baseline is T0137's).

The traded basket is record 44's ten EUR legs, a code constant. The committed universe doc
carries the selection. This test is the ONLY place the two meet: a future regeneration that
shifts selection turns it red and forces a conscious edit of the ruled baseline -- divergence
can never again arrive silently, and the engine host never reads the universe artifact.
"""

import re
from pathlib import Path

_DOC = Path(__file__).resolve().parent.parent / "docs" / "universe" / "point-in-time-universe.md"

# The ruled exceptions -- each owned by T0137; editing either side without a ruling is the
# drift this test exists to catch.
RULED_TRADED_BUT_DESELECTED = {"DOT/EUR"}
RULED_SELECTED_BUT_UNREACHABLE = {"ETH/BTC", "SOL/BTC"}


def _selected() -> set[str]:
    text = _DOC.read_text()
    block = text.split("## Selected universe")[1].split("##")[0]
    symbols = {s.strip() for s in block.strip().split(",")}
    assert all(re.fullmatch(r"[A-Z]+/[A-Z]+", s) for s in symbols), symbols
    return symbols


def test_the_basket_and_the_universe_diverge_exactly_as_ruled():
    from cli.engine.store import PAIR_KEYS

    basket = {f"{base}/EUR" for base in PAIR_KEYS}
    selected = _selected()
    assert basket - selected == RULED_TRADED_BUT_DESELECTED, (
        "the traded basket carries symbols the universe no longer selects, beyond the ruled "
        "baseline -- a T0137 re-ratification decision, not an edit to this constant"
    )
    assert selected - basket == RULED_SELECTED_BUT_UNREACHABLE, (
        "the universe selects symbols the basket cannot express, beyond the ruled baseline -- "
        "T0137 owns whether the multi-quote solve makes them reachable"
    )
