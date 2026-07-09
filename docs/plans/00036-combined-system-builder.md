# Combined-System Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The adopted P1 system's full pipeline as one committed, tested function (`cli/portfolio/build_combined_system`), with record 33's frozen figures as a standing regression guard.

**Architecture:** Pure composition of the existing tested building blocks (`dynamic_inverse_vol_basket`, `sma_gate`, `vol_target`, `_inverse_vol_weights`/`_asset_returns` from `cli.alpha.a1` — deliberately, same-code-path reproduction — `apply_position_caps`, `drawdown_governor`), exactly the QA-verified iter-059 construction. No reimplementation.

**Tech Stack:** Python 3.14, stdlib only; pytest (`skipif` for the real-data integration test).

## Global Constraints

- Stdlib only in `cli/portfolio/`; ruff line 132, double quotes; gate `uv run pre-commit run -a`.
- Defaults verbatim from the spec: `basket_lookback=30, gate_window=200, target_vol_annual=0.10, vol_lookback=30, max_leverage=1.0, periods_per_year=365, spot_fee_per_side=0.006, long_cap=0.20, short_cap=0.10, governor=GovernorConfig()`.
- Composition order is the adopted construction: gate on the basket's **own equity index**; vol-target on the **raw** basket, gate applied after; cap **then** governor; the governor runs on the **capped** book's net-of-cost series.
- Frozen-figure tolerances (integration test): system Sharpe 1.3263 ± 0.005, maxDD 0.1449 ± 0.003, benchmark Sharpe 1.2455 ± 0.005, `cap_breach_bars == 100`, occupancy `{1.0: 2476, 0.5: 1711, 0.25: 394}` exact.
- Commits end with `Co-Authored-By:` (actual model) + `Claude-Session:` trailers.

______________________________________________________________________

### Task 1: `cli/portfolio/` — the builder, TDD

**Files:**

- Create: `cli/portfolio/__init__.py`, `cli/portfolio/errors.py`, `cli/portfolio/builder.py`
- Test: `tests/test_portfolio_builder.py`

**Interfaces:**

- Consumes: `cli.risk` (`GovernorConfig`, `GovernorResult`, `apply_position_caps`, `drawdown_governor`), `cli.benchmark.strategies` (`dynamic_inverse_vol_basket`, `sma_gate`, `vol_target`), `cli.alpha.a1` (`_asset_returns`, `_inverse_vol_weights`), `cli.validation.sharpe` + `cli.ohlc.dataset.read_parquet` (integration test only).
- Produces: `from cli.portfolio import CombinedSystemConfig, CombinedSystemResult, PortfolioError, build_combined_system`.

- [ ] **Step 1: Write the failing tests** — full file `tests/test_portfolio_builder.py`:

```python
import math
from pathlib import Path

import pytest

from cli.portfolio import CombinedSystemConfig, CombinedSystemResult, PortfolioError, build_combined_system
from cli.risk import GovernorConfig

# Small-window config so ~40 synthetic bars exercise every stage (defaults need 200+ bars).
SMALL = dict(basket_lookback=3, gate_window=5, vol_lookback=3)
# Overlay-disabling knobs: a cap that can never clip and a governor whose rules cannot fire.
NO_CAP = dict(long_cap=100.0, short_cap=100.0)
NO_GOV = GovernorConfig(daily_loss_limit=0.9, ladder=((0.95, 0.5),))


def rising_prices(n: int, *, start: float, step: float, wobble: float = 0.0) -> list[float]:
    # Deterministic gently-rising series; wobble keeps realized vol > 0 without randomness.
    return [start * (1 + step) ** k * (1 + wobble * math.sin(k)) for k in range(n)]


def three_assets(n: int = 40) -> dict[str, list[float]]:
    return {
        "AAA": rising_prices(n, start=100.0, step=0.004, wobble=0.01),
        "BBB": rising_prices(n, start=50.0, step=0.003, wobble=0.02),
        "CCC": rising_prices(n, start=10.0, step=0.005, wobble=0.015),
    }


def test_result_shape_and_identities():
    res = build_combined_system(three_assets(), config=CombinedSystemConfig(**SMALL))
    assert isinstance(res, CombinedSystemResult)
    n = res.n_periods
    assert n == 39  # len(prices) - 1
    for series in (res.net_of_cost, res.benchmark_net_of_cost, res.capped_net_of_cost, res.multipliers):
        assert len(series) == n
    assert set(res.positions) == {"AAA", "BBB", "CCC"}
    assert res.net_of_cost == res.governor.governed_returns
    # positions are the capped book scaled by the multiplier stream: where mult == 0.0 the position
    # is exactly 0.0; everywhere the position respects the cap scaled by the multiplier.
    for a, series in res.positions.items():
        assert len(series) == n
        for k in range(n):
            if res.multipliers[k] == 0.0:
                assert series[k] == 0.0
            else:
                assert series[k] <= 0.20 * res.multipliers[k] + 1e-12
    res2 = build_combined_system(three_assets(), config=CombinedSystemConfig(**SMALL))
    assert res2.positions == res.positions  # deterministic


def test_disable_degeneracy_overlays_compose_to_identity():
    cfg = CombinedSystemConfig(**SMALL, **NO_CAP, governor=NO_GOV)
    res = build_combined_system(three_assets(), config=cfg)
    assert res.cap_breach_bars == 0
    assert res.multipliers == [1.0] * res.n_periods
    for k in range(res.n_periods):
        assert res.net_of_cost[k] == pytest.approx(res.benchmark_net_of_cost[k], rel=1e-9, abs=1e-12)


def test_cap_engages_on_concentration():
    # One near-zero-vol asset draws ~all inverse-vol weight -> pre-cap position >> 0.20.
    prices = {
        "CALM": rising_prices(40, start=100.0, step=0.0001, wobble=0.0002),
        "WILD": rising_prices(40, start=100.0, step=0.004, wobble=0.06),
    }
    res = build_combined_system(prices, config=CombinedSystemConfig(**SMALL))
    assert res.cap_breach_bars > 0
    assert max(max(s) for s in res.positions.values()) <= 0.20 + 1e-12


def test_warmup_flat():
    res = build_combined_system(three_assets(), config=CombinedSystemConfig(**SMALL))
    for a in res.positions:
        assert all(p == 0.0 for p in res.positions[a][:3])  # gate warm-up (window 5 -> k < 4 flat, first 3 certainly)


def test_no_lookahead():
    base = build_combined_system(three_assets(), config=CombinedSystemConfig(**SMALL))
    prices = three_assets()
    prices["AAA"][-1] *= 1.5
    pert = build_combined_system(prices, config=CombinedSystemConfig(**SMALL))
    n = base.n_periods
    for a in base.positions:
        assert pert.positions[a][: n - 1] == base.positions[a][: n - 1]


@pytest.mark.parametrize(
    "prices,kwargs",
    [
        ({}, {}),
        ("not a dict", {}),
        (None, {}),
        ({"AAA": [100.0, 101.0] * 20}, {"spot_fee_per_side": 0.0}),
        ({"AAA": [100.0, 101.0] * 20}, {"spot_fee_per_side": float("nan")}),
        ({"AAA": [100.0, 101.0] * 20}, {"target_vol_annual": -0.1}),
        ({"AAA": [100.0, 101.0] * 20}, {"periods_per_year": 0}),
    ],
)
def test_invalid_inputs(prices, kwargs):
    with pytest.raises(PortfolioError):
        build_combined_system(prices, config=CombinedSystemConfig(**SMALL, **kwargs))


DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "ohlc-full"


@pytest.mark.skipif(not DATA_ROOT.exists(), reason="canonical dataset not present")
def test_frozen_figures_regression():
    # Registry record 33's figures, reproduced through the committed pipeline (the drivers' QA gates, made permanent).
    from cli.ohlc.dataset import read_parquet
    from cli.validation import sharpe

    assets = ["ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP"]
    frames = {a: read_parquet(DATA_ROOT / a / "EUR" / "1440.parquet") for a in assets}
    union_ts = sorted(set().union(*[set(f["ts"].to_list()) for f in frames.values()]))
    prices = {}
    for a in assets:
        m = dict(zip(frames[a]["ts"].to_list(), frames[a]["close"].to_list()))
        prices[a] = [m.get(t) for t in union_ts]
    res = build_combined_system(prices)

    def max_dd(rs):
        eq, peak, dd = 1.0, 1.0, 0.0
        for r in rs:
            eq *= 1 + r
            peak = max(peak, eq)
            dd = max(dd, 1 - eq / peak)
        return dd

    assert sharpe(res.net_of_cost, periods_per_year=365) == pytest.approx(1.3263, abs=0.005)
    assert max_dd(res.net_of_cost) == pytest.approx(0.1449, abs=0.003)
    assert sharpe(res.benchmark_net_of_cost, periods_per_year=365) == pytest.approx(1.2455, abs=0.005)
    assert res.cap_breach_bars == 100
    assert res.governor.rung_bars == {1.0: 2476, 0.5: 1711, 0.25: 394}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_portfolio_builder.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'cli.portfolio'`.

- [ ] **Step 3: Implement**

`cli/portfolio/errors.py`:

```python
class PortfolioError(Exception):
    """Raised on invalid portfolio-builder inputs."""
```

`cli/portfolio/builder.py`:

```python
"""Combined-system builder — the adopted P1 system (registry record 33) as one composed pipeline.

Composes the QA-verified iter-059 construction verbatim: dynamic inverse-vol basket -> 200d SMA gate
on the basket's own equity index -> vol target sized on the RAW basket (gate applied after) ->
per-asset inverse-vol weights -> §10 per-asset cap (clip, no redistribution) -> §10 drawdown
governor on the capped book's own net-of-cost series (the linear-cost overlay approximation,
decisions log iter-058). The frozen benchmark's series (uncapped, ungoverned — master-plan §9) is
returned alongside for head-to-heads, e.g. the pre-registered holdout look.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Deliberate cross-package import of a1's private helpers: the builder must run the SAME code path
# the QA-gated drivers and registry record 33 ran — a reimplementation could silently diverge.
from cli.alpha.a1 import _asset_returns, _inverse_vol_weights
from cli.benchmark.strategies import dynamic_inverse_vol_basket, sma_gate, vol_target
from cli.portfolio.errors import PortfolioError
from cli.risk import GovernorConfig, GovernorResult, apply_position_caps, drawdown_governor


@dataclass(frozen=True)
class CombinedSystemConfig:
    """Record 33's frozen parameters as defaults; see docs/specs/00036-combined-system-builder-design.md."""

    basket_lookback: int = 30
    gate_window: int = 200
    target_vol_annual: float = 0.10
    vol_lookback: int = 30
    max_leverage: float = 1.0
    periods_per_year: int = 365
    spot_fee_per_side: float = 0.006
    long_cap: float = 0.20
    short_cap: float = 0.10
    governor: GovernorConfig = GovernorConfig()


@dataclass(frozen=True)
class CombinedSystemResult:
    net_of_cost: list[float]
    benchmark_net_of_cost: list[float]
    capped_net_of_cost: list[float]
    positions: dict[str, list[float]]
    multipliers: list[float]
    governor: GovernorResult
    cap_breach_bars: int
    n_periods: int


def _net_of_cost(positions: dict[str, list[float]], gross: list[float], fee: float) -> list[float]:
    out: list[float] = []
    prev = dict.fromkeys(positions, 0.0)
    for k in range(len(gross)):
        turnover = 0.0
        for asset, series in positions.items():
            p = series[k]
            turnover += abs(p - prev[asset])
            prev[asset] = p
        out.append(gross[k] - turnover * fee)
    return out


def build_combined_system(
    prices_by_asset: dict[str, list[float | None]], *, config: CombinedSystemConfig = CombinedSystemConfig()
) -> CombinedSystemResult:
    """Build the adopted combined system + its frozen benchmark from union-calendar prices."""
    if not isinstance(prices_by_asset, dict) or not prices_by_asset:
        raise PortfolioError(f"prices_by_asset must be a non-empty dict, got {prices_by_asset!r}")
    c = config
    for name, value in (
        ("target_vol_annual", c.target_vol_annual),
        ("max_leverage", c.max_leverage),
        ("spot_fee_per_side", c.spot_fee_per_side),
    ):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise PortfolioError(f"{name} must be a finite number > 0, got {value!r}")
    if not isinstance(c.periods_per_year, int) or c.periods_per_year < 1:
        raise PortfolioError(f"periods_per_year must be an int >= 1, got {c.periods_per_year!r}")

    basket = dynamic_inverse_vol_basket(prices_by_asset, lookback=c.basket_lookback)
    equity = [1.0]
    for r in basket:
        equity.append(equity[-1] * (1 + r))
    gate = sma_gate(equity, window=c.gate_window)
    vt = vol_target(
        basket,
        target_vol=c.target_vol_annual / math.sqrt(c.periods_per_year),
        lookback=c.vol_lookback,
        max_leverage=c.max_leverage,
    )
    l3 = [gate[k] * vt[k] for k in range(len(gate))]

    weights = _inverse_vol_weights(prices_by_asset, lookback=c.basket_lookback)
    returns_by_asset = {a: _asset_returns(prices_by_asset[a]) for a in prices_by_asset}
    n = len(basket)

    bench_positions = {a: [weights[k].get(a, 0.0) * l3[k] for k in range(n)] for a in prices_by_asset}
    bench_gross = [l3[k] * basket[k] for k in range(n)]
    benchmark_net_of_cost = _net_of_cost(bench_positions, bench_gross, c.spot_fee_per_side)

    capped = apply_position_caps(bench_positions, long_cap=c.long_cap, short_cap=c.short_cap)
    capped_gross: list[float] = []
    for k in range(n):
        g = 0.0
        for a, series in capped.items():
            p = series[k]
            if p != 0.0:
                r = returns_by_asset[a][k]
                g += p * (r if r is not None else 0.0)
        capped_gross.append(g)
    capped_net_of_cost = _net_of_cost(capped, capped_gross, c.spot_fee_per_side)

    gov = drawdown_governor(capped_net_of_cost, config=c.governor)
    positions = {a: [gov.multipliers[k] * series[k] for k in range(n)] for a, series in capped.items()}
    cap_breach_bars = sum(
        1
        for k in range(n)
        if any(bench_positions[a][k] > c.long_cap or bench_positions[a][k] < -c.short_cap for a in bench_positions)
    )
    return CombinedSystemResult(
        net_of_cost=gov.governed_returns,
        benchmark_net_of_cost=benchmark_net_of_cost,
        capped_net_of_cost=capped_net_of_cost,
        positions=positions,
        multipliers=gov.multipliers,
        governor=gov,
        cap_breach_bars=cap_breach_bars,
        n_periods=n,
    )
```

`cli/portfolio/__init__.py`:

```python
from cli.portfolio.builder import CombinedSystemConfig, CombinedSystemResult, build_combined_system
from cli.portfolio.errors import PortfolioError

__all__ = ["CombinedSystemConfig", "CombinedSystemResult", "PortfolioError", "build_combined_system"]
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `uv run pytest tests/test_portfolio_builder.py -q` — Expected: all pass, including `test_frozen_figures_regression` if `data/ohlc-full` exists locally (it does on this machine; it is skipped in CI).
Run: `uv run pytest -q` — Expected: 904 existing + new all green.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a   # until clean; re-stage rewrites
git add cli/portfolio/ tests/test_portfolio_builder.py
git commit -m "feat(portfolio): combined-system builder — record 33's pipeline as committed code

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01A7RnbvMKGoUqnZaE48acVN"
```

______________________________________________________________________

### Task 2 (orchestrator-run, closeout): iterations-history entry

Append the iter-063 entry (builder shipped, frozen figures now a standing regression test, drivers superseded) to `docs/iterations-history.md`; decisions-log verdict entry. Closeout-docs commit (review-exempt).
