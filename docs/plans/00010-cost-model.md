# Kraken Cost Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open `cli/costs/` with the confirmed Kraken spot fee ladder + per-base margin open/rollover accrual per `docs/specs/00010-cost-model-design.md`. Pure functions over the July-9 schedule; degenerate input raises `CostModelError`.

**Architecture:** New package `cli/costs/` (`errors.py`, `fees.py`, `margin.py`, `__init__.py`). Stdlib-only. TDD.

**Tech Stack:** Python 3.14, stdlib `math`, pytest. Ruff line-length 132, double quotes.

## Global Constraints

- stdlib-only. Fee/margin values are EXACTLY per `docs/reference/kraken-fee-schedule.md` (fractions).
- Never crash weirdly: raise `CostModelError` on negative / non-finite numeric inputs, unknown base, bad band.
- `spot_fee_rates` returns 1-based `tier`; `margin_carry` uses `n_rollovers = floor(hold_hours / 4)` (opening + one rollover per completed 4h). No spread, no AoP, no combined-cost function (deferred). No CLI/README change.

---

### Task 1: `cli/costs/` — errors + fees + margin

**Files:**
- Create: `cli/costs/__init__.py`, `cli/costs/errors.py`, `cli/costs/fees.py`, `cli/costs/margin.py`
- Test: `tests/test_costs_fees.py`, `tests/test_costs_margin.py`

**Interfaces:**
- Produces: `CostModelError`; `SPOT_FEE_TIERS`, `spot_fee_rates(thirty_day_volume_usd) -> dict`, `round_trip_fee(notional, *, maker_rate, taker_rate, taker_open=False, taker_close=False) -> float`; `MARGIN_RATES`, `margin_rate(base, *, band="high") -> float`, `margin_carry(notional, hold_hours, rate) -> float`.

- [ ] **Step 1: Write failing tests.**

`tests/test_costs_fees.py`:
```python
import pytest

from cli.costs import CostModelError, round_trip_fee, spot_fee_rates


@pytest.mark.parametrize(
    "vol,tier,maker,taker",
    [
        (0, 1, 0.0040, 0.0080),
        (2_499, 1, 0.0040, 0.0080),
        (2_500, 2, 0.0030, 0.0060),
        (9_999, 2, 0.0030, 0.0060),
        (10_000, 3, 0.0022, 0.0038),
        (25_000, 4, 0.0020, 0.0035),
        (1e12, 17, 0.0000, 0.0005),
    ],
)
def test_spot_fee_rates(vol, tier, maker, taker):
    r = spot_fee_rates(vol)
    assert r == {"tier": tier, "maker": maker, "taker": taker}


def test_spot_fee_rates_monotonic():
    vols = [0, 2_500, 10_000, 25_000, 50_000, 100_000, 1_000_000, 10_000_000, 1e12]
    makers = [spot_fee_rates(v)["maker"] for v in vols]
    takers = [spot_fee_rates(v)["taker"] for v in vols]
    assert makers == sorted(makers, reverse=True)
    assert takers == sorted(takers, reverse=True)


@pytest.mark.parametrize("vol", [-1.0, float("nan"), float("inf")])
def test_spot_fee_rates_guards(vol):
    with pytest.raises(CostModelError):
        spot_fee_rates(vol)


def test_round_trip_fee_maker_taker_mixed():
    assert round_trip_fee(1000, maker_rate=0.0040, taker_rate=0.0080) == pytest.approx(8.0)
    assert round_trip_fee(1000, maker_rate=0.0040, taker_rate=0.0080, taker_open=True, taker_close=True) == pytest.approx(16.0)
    assert round_trip_fee(1000, maker_rate=0.0040, taker_rate=0.0080, taker_close=True) == pytest.approx(12.0)


@pytest.mark.parametrize(
    "notional,kwargs",
    [
        (-1.0, {"maker_rate": 0.004, "taker_rate": 0.008}),
        (1000, {"maker_rate": -0.004, "taker_rate": 0.008}),
        (1000, {"maker_rate": 0.004, "taker_rate": float("nan")}),
    ],
)
def test_round_trip_fee_guards(notional, kwargs):
    with pytest.raises(CostModelError):
        round_trip_fee(notional, **kwargs)
```

`tests/test_costs_margin.py`:
```python
import pytest

from cli.costs import CostModelError, margin_carry, margin_rate


def test_margin_rate_lookup():
    assert margin_rate("BTC", band="high") == 0.0002
    assert margin_rate("BTC", band="low") == 0.0001
    assert margin_rate("ETH", band="high") == 0.0004
    assert margin_rate("AVAX", band="low") == 0.0002


@pytest.mark.parametrize("base,band", [("XBT", "high"), ("BTC", "mid"), ("FOO", "low")])
def test_margin_rate_guards(base, band):
    with pytest.raises(CostModelError):
        margin_rate(base, band=band)


@pytest.mark.parametrize(
    "notional,hours,rate,expected",
    [
        (1000, 3, 0.0002, 0.2),    # < 4h -> opening only (floor=0 rollovers)
        (1000, 4, 0.0002, 0.4),    # 1 rollover + opening
        (1000, 24, 0.0002, 1.4),   # floor(24/4)=6 rollovers + opening = 7 units
        (1000, 0, 0.0002, 0.2),    # opening only
        (1000, 120, 0.0002, 6.2),  # 5 days: 30 rollovers + opening = 31 units
    ],
)
def test_margin_carry(notional, hours, rate, expected):
    assert margin_carry(notional, hours, rate) == pytest.approx(expected)


@pytest.mark.parametrize(
    "args",
    [(-1.0, 4, 0.0002), (1000, -4, 0.0002), (1000, 4, -0.0002), (1000, float("inf"), 0.0002), (1000, 4, float("nan"))],
)
def test_margin_carry_guards(args):
    with pytest.raises(CostModelError):
        margin_carry(*args)
```

- [ ] **Step 2: Run tests, verify they fail** — `uv run pytest tests/test_costs_fees.py tests/test_costs_margin.py -q` → ImportError.

- [ ] **Step 3: Implement `cli/costs/errors.py`:**
```python
class CostModelError(Exception):
    """Raised on invalid cost-model inputs."""
```

- [ ] **Step 4: Implement `cli/costs/fees.py`:**
```python
from __future__ import annotations

import math

from cli.costs.errors import CostModelError

# (min_30d_volume_usd, maker, taker) as fractions — Kraken spot schedule effective 2026-07-09
# (docs/reference/kraken-fee-schedule.md). Ascending by volume; tier is 1-based on this order.
SPOT_FEE_TIERS: tuple[tuple[float, float, float], ...] = (
    (0, 0.0040, 0.0080),
    (2_500, 0.0030, 0.0060),
    (10_000, 0.0022, 0.0038),
    (25_000, 0.0020, 0.0035),
    (50_000, 0.0015, 0.0030),
    (100_000, 0.0012, 0.0025),
    (250_000, 0.0010, 0.0022),
    (500_000, 0.0008, 0.0020),
    (1_000_000, 0.0006, 0.0018),
    (2_500_000, 0.0004, 0.0015),
    (5_000_000, 0.0002, 0.0012),
    (10_000_000, 0.0000, 0.0010),
    (50_000_000, 0.0000, 0.0009),
    (100_000_000, 0.0000, 0.0008),
    (250_000_000, 0.0000, 0.0007),
    (400_000_000, 0.0000, 0.0006),
    (500_000_000, 0.0000, 0.0005),
)


def spot_fee_rates(thirty_day_volume_usd: float) -> dict:
    """Maker/taker fee fractions + 1-based tier for a 30-day USD spot volume (Kraken, 2026-07-09 schedule)."""
    if not math.isfinite(thirty_day_volume_usd) or thirty_day_volume_usd < 0:
        raise CostModelError(f"thirty_day_volume_usd must be finite and >= 0, got {thirty_day_volume_usd}")
    idx = 0
    for i, (min_vol, _maker, _taker) in enumerate(SPOT_FEE_TIERS):
        if thirty_day_volume_usd >= min_vol:
            idx = i
        else:
            break
    _min_vol, maker, taker = SPOT_FEE_TIERS[idx]
    return {"tier": idx + 1, "maker": maker, "taker": taker}


def round_trip_fee(
    notional: float,
    *,
    maker_rate: float,
    taker_rate: float,
    taker_open: bool = False,
    taker_close: bool = False,
) -> float:
    """Open+close fee cost on `notional`; each leg is taker if flagged, else maker (default maker-first)."""
    for name, value in (("notional", notional), ("maker_rate", maker_rate), ("taker_rate", taker_rate)):
        if not math.isfinite(value) or value < 0:
            raise CostModelError(f"{name} must be finite and >= 0, got {value}")
    open_rate = taker_rate if taker_open else maker_rate
    close_rate = taker_rate if taker_close else maker_rate
    return notional * (open_rate + close_rate)
```

- [ ] **Step 5: Implement `cli/costs/margin.py`:**
```python
from __future__ import annotations

import math

from cli.costs.errors import CostModelError

# Base crypto -> (low, high) fraction, charged per open AND per 4h rollover (docs/reference/kraken-fee-schedule.md).
MARGIN_RATES: dict[str, tuple[float, float]] = {
    "BTC": (0.0001, 0.0002),
    "ETH": (0.0002, 0.0004),
    "SOL": (0.0002, 0.0004),
    "XRP": (0.0002, 0.0004),
    "ADA": (0.0002, 0.0004),
    "LINK": (0.0002, 0.0004),
    "DOGE": (0.0002, 0.0004),
    "LTC": (0.0002, 0.0004),
    "DOT": (0.0002, 0.0004),
    "AVAX": (0.0002, 0.0004),
}


def margin_rate(base: str, *, band: str = "high") -> float:
    """The low/high per-open-and-rollover margin rate fraction for `base`."""
    if band not in ("low", "high"):
        raise CostModelError(f"band must be 'low' or 'high', got {band!r}")
    if base not in MARGIN_RATES:
        raise CostModelError(f"unknown margin base {base!r}; known: {sorted(MARGIN_RATES)}")
    low, high = MARGIN_RATES[base]
    return low if band == "low" else high


def margin_carry(notional: float, hold_hours: float, rate: float) -> float:
    """Margin carry = notional * rate * (1 opening + floor(hold_hours / 4) rollovers)."""
    for name, value in (("notional", notional), ("hold_hours", hold_hours), ("rate", rate)):
        if not math.isfinite(value) or value < 0:
            raise CostModelError(f"{name} must be finite and >= 0, got {value}")
    n_rollovers = math.floor(hold_hours / 4)
    return notional * rate * (1 + n_rollovers)
```

- [ ] **Step 6: Implement `cli/costs/__init__.py`:**
```python
from cli.costs.errors import CostModelError
from cli.costs.fees import SPOT_FEE_TIERS, round_trip_fee, spot_fee_rates
from cli.costs.margin import MARGIN_RATES, margin_carry, margin_rate

__all__ = [
    "MARGIN_RATES",
    "SPOT_FEE_TIERS",
    "CostModelError",
    "margin_carry",
    "margin_rate",
    "round_trip_fee",
    "spot_fee_rates",
]
```

- [ ] **Step 7: Run tests, verify they pass** — `uv run pytest tests/test_costs_fees.py tests/test_costs_margin.py -q`.

- [ ] **Step 8: Full gate** — `uv run pre-commit run -a` clean; `uv run pytest -q` (whole suite) green.

- [ ] **Step 9: Commit** — `feat(costs): add Kraken spot-fee ladder + margin carry`.

---

### Task 2: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-017: Kraken cost model — fees + margin (Phase 2)`: `cli/costs/` — the confirmed July-9 spot fee ladder (`spot_fee_rates`, Tier 1 0.40%/0.80% → volume tiers) + `round_trip_fee`; per-base margin `margin_rate` + `margin_carry` (open + floor(h/4) rollovers; BTC 0.01–0.02%/4h, alts 0.02–0.04%/4h). Data from `docs/reference/kraken-fee-schedule.md` (T0000). Spread deferred (T0003), AoP omitted (YAGNI). Property-tested; `CostModelError` guards. §12 Phase-2 exit-bar component; spec/plan `00010`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-017 closeout — cost model (fees + margin)`.
