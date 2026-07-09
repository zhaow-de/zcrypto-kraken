# Drawdown governor (§10 risk layer) — design

**Iteration:** iter-058 (Phase 5, unattended). **Goal:** the master-plan §10 drawdown-governance ladder as tested library code, plus the pre-registered threshold backtest on the frozen candidate B3+vt-dynamic — per §10: *"These thresholds are themselves backtested (they are part of the system, not an afterthought)."*

## What §10 ratifies (D1, 2026-07-06 — constants are fixed, not re-decided here)

- **Daily-loss rule:** daily loss ≥ 3 % → flatten new risk, halve targets, human review flag.
- **Trailing ladder** on max drawdown from the high-water mark, budget 15 %: DD ≥ 7.5 % → risk ×0.5; DD ≥ 11 % → risk ×0.25; DD ≥ 15 % → flat + post-mortem before restart.

## Architecture (decided, logged `[iter-058]`)

A **pure-function overlay** on a net-of-cost daily returns series, with **governed-equity feedback**: the multiplier for bar *t* is decided from the *governed* path through bar *t−1* (the live book only ever sees its own equity), then `governed_returns[t] = multiplier[t] * returns[t]`. No look-ahead by construction. Approximation accepted: scaling a net return scales its cost component linearly (turnover scales with exposure) — adequate at daily bars; the Phase-6 engine enforces the same rules at weight level.

Rejected: weight-level governor inside the backtest engine (drags the per-asset pipeline into this iteration; the combination iteration does weight-level assembly anyway); deferring the backtest to Phase 6 (violates §10's pre-registration).

## Package: `cli/risk/`

New sibling package mirroring `cli/benchmark/` style — stdlib only, `list[float]`, double quotes, line length 132:

- `cli/risk/__init__.py` — re-exports `drawdown_governor`, `GovernorConfig`, `GovernorResult`, `RiskError`.
- `cli/risk/errors.py` — `RiskError(Exception)`, module-level, matching `cli/benchmark/errors.py`.
- `cli/risk/governor.py` — the implementation below.
- `tests/test_risk_governor.py` — the TDD suite.

## API

```python
@dataclass(frozen=True)
class GovernorConfig:
    daily_loss_limit: float = 0.03          # trigger: governed return of bar t ≤ -daily_loss_limit
    daily_loss_multiplier: float = 0.5      # the "halve targets" action
    daily_loss_cooldown: int = 5            # bars the halving persists; renewed by each new trigger bar
    ladder: tuple[tuple[float, float], ...] = ((0.075, 0.5), (0.11, 0.25), (0.15, 0.0))
                                            # (dd_threshold, multiplier), ascending; DD ≥ threshold → multiplier
    restart_after: int | None = 30          # bars flat after a terminal-rung breach before re-arm (HWM reset);
                                            # None = never restart (the diagnostic variant)

@dataclass(frozen=True)
class GovernorResult:
    multipliers: list[float]                # per bar, the multiplier actually applied
    governed_returns: list[float]           # multipliers[t] * returns[t]
    daily_loss_triggers: int                # count of governed bars breaching the daily limit
    rung_bars: dict[float, int]             # bars spent at each distinct multiplier (incl. 1.0)
    breaches: int                           # terminal-rung (flat) entries
    rung_transitions: int                   # count of bar-to-bar multiplier changes (flicker diagnostic)

def drawdown_governor(returns: list[float], *, config: GovernorConfig = GovernorConfig()) -> GovernorResult
```

## Semantics (each decided + logged `[iter-058]`)

1. **State evolves on the governed path.** Equity `E[t] = E[t-1] * (1 + governed_returns[t])`, `E[-1] = 1.0`; HWM and drawdown are computed on `E`. The daily-loss trigger reads the **governed** return (the book's actual P&L day).
2. **Ordering per bar t:** multiplier is fixed **before** bar t from state through t−1 → `governed_returns[t]` → update equity/HWM/DD → evaluate triggers for t+1. Bar 0 always gets multiplier 1.0 (no history).
3. **Ladder:** pure threshold mapping, DD ≥ threshold (inclusive) selects that rung's multiplier; rungs ascending; no hysteresis (§10 names none); flicker is reported, not suppressed.
4. **Daily-loss rule:** a governed return ≤ −3 % sets a 5-bar cooldown during which the daily multiplier is 0.5; a new trigger bar renews the cooldown. Mechanical stand-in for "flatten new risk, halve targets, human review flag".
5. **Composition:** `multiplier = min(ladder_mult, daily_mult)` — the most restrictive control governs (product would double-count the same drawdown).
6. **Terminal rung (flat at −15 %):** multiplier 0.0 for `restart_after` bars, then re-arm with the **HWM reset to current governed equity** (fresh budget after the post-mortem — a flat book's DD is frozen, so re-arm cannot key on DD recovery; that deadlock is why the reset exists). Daily-loss cooldown clears on re-arm. `restart_after=None` = flat forever (diagnostic variant, reported alongside).
7. **Validation:** non-finite input (NaN/inf), empty series, a return ≤ −1, non-ascending ladder, or negative config values → `RiskError`. No silent coercion.

## TDD plan (tests written first; planted paths with hand-computed answers)

- **Planted ladder walk:** a constructed series that walks DD through 7.4 % → 7.5 % → 11 % → 15 % asserts the exact multiplier sequence 1.0 → 0.5 → 0.25 → 0.0 at the exact bars (inclusive boundaries).
- **No look-ahead:** changing `returns[t]` must not change `multipliers[t]` (only `multipliers[t+1:]`).
- **Governed feedback:** a crash that breaches 15 % ungoverned but, damped by the 0.5/0.25 rungs, stays above 15 % governed → no terminal breach (hand-computed).
- **Daily-loss rule:** a single −3 % governed bar halves the next 5 bars exactly, then releases; a second trigger inside the window renews it; a −2.99 % bar does not trigger (strict ≥ on the loss).
- **min-composition:** a bar where the ladder says 0.5 and the daily rule says 0.5 → 0.5 (not 0.25).
- **Terminal + re-arm:** after a breach, exactly `restart_after` flat bars, then HWM reset (a subsequent small dip from the new base does not instantly re-trip the ladder); `restart_after=None` stays flat to the end.
- **Degenerate:** all-positive series → all multipliers 1.0, zero triggers; `RiskError` cases per validation above.
- **Identity:** `governed_returns[t] == multipliers[t] * returns[t]` for all t; `rung_bars` sums to `len(returns)`.

## The threshold backtest (the deliverable §10 pre-registers)

Scratchpad driver (not committed, like every prior driver) rebuilding **B3+vt-dynamic net-of-cost** exactly per the iter-055 construction (`b3b4_dynamic_run.py`: dynamic inverse-vol basket lookback 30 over the 10-major union calendar; 200d `sma_gate` on the basket's own equity index; `vol_target` 10 %/yr 30d max 1.0× on the RAW basket, gate applied after; per-asset turnover + no short carry), **QA-gated first**: the driver must reproduce the frozen reference figures (net-of-cost Sharpe 1.245 full / 1.278 k≥230, maxDD 21.9 %) before any governed number is read.

Then report, governed vs ungoverned, full window and k≥230:

- Sharpe, annualized return, annualized vol, maxDD, worst calendar year (P&L and DD, benchmark-relative reading per iter-054's diagnostic).
- Engagement evidence (mandatory): rung occupancy, daily-loss trigger count, breach count — a governor that never engages on a 21.9 %-maxDD series is an instrument bug, not a result.
- The `restart_after=None` diagnostic variant.
- **Sensitivity read (robustness, not re-decision — the constants are D1-ratified):** one-at-a-time ±25 % on each threshold (daily limit, the three rungs, cooldown, restart), Sharpe/maxDD per variant. A knife-edge (governed metrics swinging disproportionately) is a finding to register as an open topic for the human, not a knob to tune.

**Reading protocol (pre-registered):** this is a *measurement of the ratified constants*, not an adopt/reject trial — no registry spend (the combination trial next iteration is the registry event). Success = the governor demonstrably engages and the governed maxDD lands below the ungoverned 21.9 %; the Sharpe delta is reported symmetrically whatever its sign. Results land in the iter-058 history entry and feed the combination iteration.

## Out of scope (registered elsewhere, not lost)

- **Portfolio limits** (gross/net/per-asset caps, margin floor): weight-level rules — they belong to the combination-assembly iteration (Phase-5 queue item 2, `10.phase4-closeout.md` §Phase-5 orientation), where an actual weight series exists. Note: the dynamic basket's early 2-asset years violate a naive ≤20 %-per-asset cap by construction — that interaction is the combination iteration's first design question.
- **Short-side rules** (§10): no short sleeve exists in the candidate; falls in with a future short-carrying sleeve.
- **Live/runtime governor** (watchdog, reconciliation): Phase 6, attended.
