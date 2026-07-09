# A1 alpha book — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]` checkboxes.

**Goal:** Build the A1 vol-targeted long/flat/short trend book (`cli/alpha/`) — a per-asset directional book aggregated
by inverse-vol weights, strictly look-ahead-free — plus the Phase-4 kill-bar evaluation harness, both TDD'd on
synthetic known-answers. This plan (iter-045) builds all the **code** (Tasks 1–5); the real-data 16-trial kill-bar
run + registry writes + results report (Tasks 6–8) execute in **iter-046**, a later branch, per the design decision
in `.tmp/decisions.md` `[iter-045]` (split code-now / verdict-next, to avoid a rushed real-data verdict).

**Architecture:** New `cli/alpha/` package (`a1.py`, `killbar.py`, `errors.py`, `__init__.py`), pure-Python/list-based
like `cli/benchmark/` and `cli/features/`. `a1.py` composes the existing reviewed primitives
(`sma_gate`, `vol_target`, `trend_agreement`, `run_backtest`) plus one small inline inverse-vol qualifying-weights
helper (mirroring — never modifying — the merged `dynamic_inverse_vol_basket`) into a per-asset direction builder
and a book assembler. `killbar.py` composes the validation harness (`deflated_sharpe_ratio`, `reality_check_pvalue`,
`sharpe`) into the Phase-4 kill-bar verdict + the short-leg whipsaw diagnostic.

**Tech Stack:** Python 3.14, uv, pytest, ruff (line 132, double quotes).

## Global Constraints

- Python 3.14, uv, pytest, ruff line-length 132 + double quotes; commit gate `uv run pre-commit run -a` (run the
  full suite, not individual tools — see CLAUDE.md).
- Pure-Python/list-based like `cli/benchmark/` and `cli/features/` — no numpy in the library. No logger is expected
  (`a1.py`/`killbar.py` are pure functions, same as `cli/benchmark/strategies.py` and `cli/features/*.py`, neither of
  which logs); add `get_logger("alpha.<module>")` only if a real logging need surfaces during implementation.
- **Look-ahead-free is non-negotiable** — every position/direction for return-period `k` uses only prices/features
  at `≤ k`; ship the book-level leak test proven to fail on a peeking implementation (see Task 4).
- Reuse `sma_gate` / `vol_target` / `trend_agreement` / `run_backtest` / the validation harness; do **not**
  reimplement metrics or the basket weighting logic beyond the small inline qualifying-weights helper
  (`_inverse_vol_weights`, Task 3), which is cross-checked bit-identical against `dynamic_inverse_vol_basket`. Do
  **not** modify `cli/benchmark/strategies.py`.
- Match the repo's alignment convention throughout: every per-period series has length `union_len - 1` (or
  `len(prices) - 1`), element `k` = the move into `k+1`, computed only from data at `≤ k`.
- Plan header per writing-plans (REQUIRED SUB-SKILL line, Goal, Architecture, Tech Stack, Global Constraints).
- Final task of the **whole plan** = iterations-history closeout (Task 5b closes iter-045; Task 8 closes iter-046).

## Design decisions made while writing this plan (flagged for review)

The spec (`docs/specs/00031-a1-alpha-book-design.md`) and the inputs brief leave a few implementation-level
judgment calls unresolved. Each is made concretely below (so the plan has no placeholders) with its confidence
noted; none block Tasks 1–5, but the first two are worth a deliberate look before Task 6 runs on real data.

1. **Kill-bar "worst walk-forward slice is not disqualifying" threshold** (medium confidence). No document gives a
   numeric bar. This plan defines it as: **the worst regime slice's Sharpe must be `> 0`** — every regime must be
   individually non-negative risk-adjusted, a common walk-forward robustness bar. Task 6 (real data) may want to
   recalibrate this against the frozen benchmark's own worst-slice Sharpe instead of an absolute `0`; flagged in
   `killbar.py`'s docstring for that reconsideration.
2. **Kill-bar "survives 1.5× cost stress" rule** (medium confidence). Defined as: **the cost-stressed return
   series' Sharpe must still be `> 0`** (the edge isn't wiped to negative by the extra cost). No compounding
   condition ("still beats the benchmark under stress") is layered on top — kept to the single, simplest
   falsifiable claim the name implies.
3. **`_asset_directions`' `union_ts` / `asset_ts` convention** (high confidence, cross-checked below). The union
   calendar is represented as a plain index/position (`union_ts = list(range(union_len))` in practice, built by
   `a1_book_returns`), and each asset's own "contiguous price series" for feature computation is the union series
   with `None` entries filtered out, paired with its **own** timestamps (`asset_ts[asset]`, the union positions
   where it's present). A dedicated helper (`_map_to_union_index`, Task 2) maps a feature/gate computed on that
   compressed series back onto the union return index **by timestamp**, returning `None` for any union transition
   the asset wasn't present for on **both** ends. This is a deliberate approximation for assets with **internal**
   gaps (a momentum lookback measured in "periods present" rather than "calendar days" once a gap is compressed
   out) — acceptable because real gaps are rare/one-time (mostly pre-listing), and it's exactly the design the
   inputs brief asks for ("computed on each asset's CONTIGUOUS price series then mapped onto the union return index
   by timestamp"). `_asset_directions` takes `union_ts`/`asset_ts` as explicit parameters (testable directly with
   non-trivial gapped calendars); `a1_book_returns` (Task 4) derives them internally from `prices_by_asset`, so its
   own public signature has no separate timestamp parameters — matching the exact signature given in the brief.
4. **Registry file location for Task 7** (unresolved, iter-046 concern) — the inputs brief itself flags this
   ("`runs/` (gitignored? confirm)"); left for iter-046 to resolve against how `cli/registry/` is used elsewhere in
   the repo (no prior caller exists yet — A1 is the first).

---

### Task 1: `AlphaError` + `A1Config`

**Files:**

- Create: `cli/alpha/__init__.py`, `cli/alpha/errors.py`, `cli/alpha/a1.py`
- Test: `tests/test_alpha_a1_config.py`

**Interfaces:**

- Produces: `AlphaError(Exception)`; `A1Config` — a frozen, kw-only dataclass with fields `base: str`,
  `regime: str`, `short: str`, `target_vol: float`, `gate_window: int = 200`, `vol_lookback: int = 30`,
  `basket_lookback: int = 30`, `trend_lookbacks: tuple[int, ...] = (20, 60, 120)`, `short_exposure: float = 0.5`,
  `max_leverage: float = 1.0`, `periods_per_year: int = 365`. Validated in `__post_init__`, raising `AlphaError`.

- [ ] **Step 1 — failing tests** (`tests/test_alpha_a1_config.py`):

  ```python
  import pytest

  from cli.alpha import A1Config, AlphaError


  def test_a1config_valid_defaults():
      cfg = A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10)
      assert cfg.gate_window == 200
      assert cfg.vol_lookback == 30
      assert cfg.basket_lookback == 30
      assert cfg.trend_lookbacks == (20, 60, 120)
      assert cfg.short_exposure == 0.5
      assert cfg.max_leverage == 1.0
      assert cfg.periods_per_year == 365


  def test_a1config_is_frozen():
      cfg = A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10)
      with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
          cfg.target_vol = 0.20


  @pytest.mark.parametrize("base", ["btc", "BTC_ONLY", "", None, 1])
  def test_a1config_bad_base(base):
      with pytest.raises(AlphaError):
          A1Config(base=base, regime="single_gate", short="off", target_vol=0.10)


  @pytest.mark.parametrize("regime", ["gate", "", None])
  def test_a1config_bad_regime(regime):
      with pytest.raises(AlphaError):
          A1Config(base="btc_only", regime=regime, short="off", target_vol=0.10)


  @pytest.mark.parametrize("short", ["bear", "", None])
  def test_a1config_bad_short(short):
      with pytest.raises(AlphaError):
          A1Config(base="btc_only", regime="single_gate", short=short, target_vol=0.10)


  @pytest.mark.parametrize("target_vol", [0.0, -0.1, float("nan"), float("inf"), "x", True])
  def test_a1config_bad_target_vol(target_vol):
      with pytest.raises(AlphaError):
          A1Config(base="btc_only", regime="single_gate", short="off", target_vol=target_vol)


  @pytest.mark.parametrize("field", ["gate_window", "vol_lookback", "basket_lookback"])
  @pytest.mark.parametrize("bad", [1, 1.5, True, "2", 0, -3])
  def test_a1config_bad_windows(field, bad):
      kwargs = dict(base="btc_only", regime="single_gate", short="off", target_vol=0.10)
      kwargs[field] = bad
      with pytest.raises(AlphaError):
          A1Config(**kwargs)


  @pytest.mark.parametrize("trend_lookbacks", [(), (1,), (2, True), [20, 60], (2.5,)])
  def test_a1config_bad_trend_lookbacks(trend_lookbacks):
      with pytest.raises(AlphaError):
          A1Config(
              base="btc_only", regime="single_gate", short="off", target_vol=0.10, trend_lookbacks=trend_lookbacks
          )


  @pytest.mark.parametrize("short_exposure", [0.0, -0.1, 1.1, float("nan"), True])
  def test_a1config_bad_short_exposure(short_exposure):
      with pytest.raises(AlphaError):
          A1Config(
              base="btc_only", regime="single_gate", short="off", target_vol=0.10, short_exposure=short_exposure
          )


  @pytest.mark.parametrize("max_leverage", [0.0, -1.0, float("nan"), "x"])
  def test_a1config_bad_max_leverage(max_leverage):
      with pytest.raises(AlphaError):
          A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, max_leverage=max_leverage)


  @pytest.mark.parametrize("periods_per_year", [0, -1, 2.5, True, "x"])
  def test_a1config_bad_periods_per_year(periods_per_year):
      with pytest.raises(AlphaError):
          A1Config(
              base="btc_only", regime="single_gate", short="off", target_vol=0.10, periods_per_year=periods_per_year
          )
  ```

- [ ] **Step 2 — run, verify red** (`uv run pytest tests/test_alpha_a1_config.py -v`).

- [ ] **Step 3 — implement** `cli/alpha/errors.py`:

  ```python
  class AlphaError(Exception):
      """Raised on invalid A1 alpha-book inputs."""
  ```

  `cli/alpha/a1.py`:

  ```python
  from __future__ import annotations

  import math
  from dataclasses import dataclass

  from cli.alpha.errors import AlphaError

  _BASES = frozenset({"btc_only", "equal_risk_basket"})
  _REGIMES = frozenset({"single_gate", "ensemble"})
  _SHORTS = frozenset({"off", "confirmed_bear"})


  def _check_enum(name: str, value: str, allowed: frozenset[str]) -> None:
      if value not in allowed:
          raise AlphaError(f"{name} must be one of {sorted(allowed)}, got {value!r}")


  def _check_positive_number(name: str, value: float) -> None:
      if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
          raise AlphaError(f"{name} must be a finite number > 0, got {value!r}")


  def _check_window(name: str, value: int) -> None:
      if not isinstance(value, int) or isinstance(value, bool) or value < 2:
          raise AlphaError(f"{name} must be an int >= 2, got {value!r}")


  @dataclass(frozen=True, kw_only=True)
  class A1Config:
      """A1 book configuration (docs/specs/00031): the four toggles (base, regime, short, target_vol)
      plus the fixed knobs shared by every trial. Validated at construction; every field is immutable
      thereafter."""

      base: str
      regime: str
      short: str
      target_vol: float
      gate_window: int = 200
      vol_lookback: int = 30
      basket_lookback: int = 30
      trend_lookbacks: tuple[int, ...] = (20, 60, 120)
      short_exposure: float = 0.5
      max_leverage: float = 1.0
      periods_per_year: int = 365

      def __post_init__(self) -> None:
          _check_enum("base", self.base, _BASES)
          _check_enum("regime", self.regime, _REGIMES)
          _check_enum("short", self.short, _SHORTS)
          _check_positive_number("target_vol", self.target_vol)
          _check_window("gate_window", self.gate_window)
          _check_window("vol_lookback", self.vol_lookback)
          _check_window("basket_lookback", self.basket_lookback)
          if not isinstance(self.trend_lookbacks, tuple) or not self.trend_lookbacks:
              raise AlphaError(f"trend_lookbacks must be a non-empty tuple of ints, got {self.trend_lookbacks!r}")
          for lb in self.trend_lookbacks:
              _check_window("trend_lookbacks element", lb)
          if (
              not isinstance(self.short_exposure, (int, float))
              or isinstance(self.short_exposure, bool)
              or not math.isfinite(self.short_exposure)
              or not (0 < self.short_exposure <= 1)
          ):
              raise AlphaError(f"short_exposure must be a finite number in (0, 1], got {self.short_exposure!r}")
          _check_positive_number("max_leverage", self.max_leverage)
          if (
              not isinstance(self.periods_per_year, int)
              or isinstance(self.periods_per_year, bool)
              or self.periods_per_year < 1
          ):
              raise AlphaError(f"periods_per_year must be an int >= 1, got {self.periods_per_year!r}")
  ```

  `cli/alpha/__init__.py`:

  ```python
  from cli.alpha.a1 import A1Config
  from cli.alpha.errors import AlphaError

  __all__ = ["A1Config", "AlphaError"]
  ```

- [ ] **Step 4 — run, verify green** (`uv run pytest tests/test_alpha_a1_config.py -v`).

- [ ] **Step 5 — commit** (`feat(alpha): add A1Config with validated toggle enums`).

### Task 2: `_map_to_union_index` + `_asset_directions`

**Files:**

- Modify: `cli/alpha/a1.py`
- Test: `tests/test_alpha_a1_directions.py`

**Interfaces:**

- Consumes: `sma_gate(prices, *, window)` (`cli.benchmark.strategies`), `trend_agreement(prices, *, lookbacks)`
  (`cli.features`), `A1Config` (Task 1).
- Produces (both private, unexported): `_map_to_union_index(own_ts: list, own_values: list[float], union_ts: list)
  -> list[float | None]`; `_asset_directions(prices_by_asset: dict[str, list[float | None]], btc_prices: list[float],
  union_ts: list, asset_ts: dict[str, list], *, config: A1Config) -> dict[str, list[float | None]]`.

- [ ] **Step 1 — failing tests** (`tests/test_alpha_a1_directions.py`):

  ```python
  import math

  from cli.alpha.a1 import A1Config, _asset_directions, _map_to_union_index

  BTC_PRICES = [100.0, 110.0, 90.0, 130.0, 60.0, 200.0]
  # sma_gate(window=2): warm-up k=0 -> 0; k=1: mean([100,110])=105, 110>105 -> 1;
  # k=2: mean([110,90])=100, 90 not>100 -> 0; k=3: mean([90,130])=110, 130>110 -> 1;
  # k=4: mean([130,60])=95, 60 not>95 -> 0.  g_btc = [0,1,0,1,0].
  # trend_agreement(lookbacks=[2]) = sign(momentum(lookback=2)): k=0,1 warm-up -> 0;
  # k=2: 90/100-1=-0.10 -> -1; k=3: 130/110-1=+0.18 -> +1; k=4: 60/90-1=-0.33 -> -1.
  # ta = [0,0,-1,1,-1].


  def _cfg(*, regime, short):
      return A1Config(
          base="btc_only", regime=regime, short=short, target_vol=0.10, gate_window=2, trend_lookbacks=(2,)
      )


  def _btc_only():
      union_ts = list(range(6))
      return {"BTC": list(BTC_PRICES)}, list(BTC_PRICES), union_ts, {"BTC": union_ts}


  def test_asset_directions_known_answer_single_gate_short_off():
      prices, btc, union_ts, asset_ts = _btc_only()
      d = _asset_directions(prices, btc, union_ts, asset_ts, config=_cfg(regime="single_gate", short="off"))
      assert d["BTC"] == [0.0, 1.0, 0.0, 1.0, 0.0]


  def test_asset_directions_ensemble_differs_from_single_gate():
      # At k=1 the gate is on (1) but ta[1]==0 (still warm-up) -> ensemble's AND-with-trend drops it
      # to flat while single_gate stays long: the two regimes provably differ on this split.
      prices, btc, union_ts, asset_ts = _btc_only()
      single = _asset_directions(prices, btc, union_ts, asset_ts, config=_cfg(regime="single_gate", short="off"))
      ensemble = _asset_directions(prices, btc, union_ts, asset_ts, config=_cfg(regime="ensemble", short="off"))
      assert single["BTC"][1] == 1.0
      assert ensemble["BTC"][1] == 0.0
      assert single["BTC"] != ensemble["BTC"]


  def test_asset_directions_confirmed_bear_short_engages():
      # gate==0 & ta<0 at k=2 and k=4 -> confirmed_bear shorts there; short=off stays flat there.
      # This also proves "short only on confirmed g_btc==0 AND ta<0": k=1 and k=3 have gate==1
      # (long, never short) despite short="confirmed_bear" being enabled.
      prices, btc, union_ts, asset_ts = _btc_only()
      off = _asset_directions(prices, btc, union_ts, asset_ts, config=_cfg(regime="single_gate", short="off"))
      bear = _asset_directions(
          prices, btc, union_ts, asset_ts, config=_cfg(regime="single_gate", short="confirmed_bear")
      )
      assert off["BTC"] == [0.0, 1.0, 0.0, 1.0, 0.0]
      assert bear["BTC"] == [0.0, 1.0, -0.5, 1.0, -0.5]
      assert bear["BTC"][1] == 1.0 and bear["BTC"][3] == 1.0  # never short while gate==1


  def test_asset_directions_ensemble_confirmed_bear_combo():
      prices, btc, union_ts, asset_ts = _btc_only()
      d = _asset_directions(
          prices, btc, union_ts, asset_ts, config=_cfg(regime="ensemble", short="confirmed_bear")
      )
      assert d["BTC"] == [0.0, 0.0, -0.5, 1.0, -0.5]


  def test_map_to_union_index_gap_and_adjacency():
      # own calendar has an internal gap (day 13 missing); union has a superset of days (13 exists for
      # some OTHER asset). Transitions touching day 13 must map to None; adjacent-in-own-terms
      # transitions (which skip the gap) must NOT be mistaken for the union's single-day moves either.
      own_ts = [10, 11, 12, 14, 15, 16]
      own_values = [1.0, 2.0, 3.0, 4.0, 5.0]
      union_ts = [10, 11, 12, 13, 14, 15, 16]
      mapped = _map_to_union_index(own_ts, own_values, union_ts)
      assert mapped == [1.0, 2.0, None, None, 4.0, 5.0]


  def test_asset_directions_absent_asset_is_none():
      # ALT is absent (None) only at union index 3 -> transitions k=2 (2->3) and k=3 (3->4) are None;
      # all other transitions have a real (finite) direction.
      btc = [100.0, 105.0, 102.0, 108.0, 103.0, 110.0, 107.0, 115.0]
      alt = [50.0, 51.0, 52.0, None, 54.0, 55.0, 56.0, 57.0]
      union_ts = list(range(8))
      asset_ts = {"BTC": union_ts, "ALT": [0, 1, 2, 4, 5, 6, 7]}
      cfg = A1Config(
          base="equal_risk_basket", regime="single_gate", short="off", target_vol=0.10,
          gate_window=2, trend_lookbacks=(2,),
      )
      d = _asset_directions({"BTC": btc, "ALT": alt}, btc, union_ts, asset_ts, config=cfg)
      assert d["ALT"][2] is None and d["ALT"][3] is None
      for k in (0, 1, 4, 5, 6):
          assert d["ALT"][k] is not None and math.isfinite(d["ALT"][k])


  def test_asset_directions_no_lookahead():
      # Prices identical through index 4 (5 elements); diverge from index 5 on. A direction at union
      # period t reads prices[t] and prices[t+1] (presence) plus causal features of prices[<=t], so
      # only t <= 3 is guaranteed invariant (t=4 already reads prices[5], the first divergent index).
      btc_base = [100.0, 108.0, 96.0, 121.0, 70.0]
      btc_1 = btc_base + [200.0, 90.0, 250.0]
      btc_2 = btc_base + [40.0, 500.0, 12.0]
      union_ts = list(range(8))
      asset_ts = {"BTC": union_ts}
      cfg = A1Config(base="btc_only", regime="ensemble", short="confirmed_bear", target_vol=0.10, gate_window=2, trend_lookbacks=(2,))
      d1 = _asset_directions({"BTC": btc_1}, btc_1, union_ts, asset_ts, config=cfg)
      d2 = _asset_directions({"BTC": btc_2}, btc_2, union_ts, asset_ts, config=cfg)
      assert d1["BTC"][:4] == d2["BTC"][:4]
  ```

- [ ] **Step 2 — run, verify red** (`uv run pytest tests/test_alpha_a1_directions.py -v`).

- [ ] **Step 3 — implement** (append to `cli/alpha/a1.py`):

  ```python
  from cli.benchmark.strategies import sma_gate
  from cli.features import trend_agreement


  def _map_to_union_index(own_ts: list, own_values: list[float], union_ts: list) -> list[float | None]:
      """Map a feature/gate computed on an asset's own CONTIGUOUS (gap-compressed) calendar (`own_ts`,
      length N; `own_values[j]` = the causal value for the move own_ts[j] -> own_ts[j+1], length N-1)
      onto the union return index (`union_ts`, length M; union period k = the move union_ts[k] ->
      union_ts[k+1]). Union period k gets own_values[own_pos[union_ts[k]]] iff BOTH union_ts[k] and
      union_ts[k+1] are present in own_ts AND are adjacent there (own_pos[union_ts[k+1]] ==
      own_pos[union_ts[k]] + 1) -- the asset was present for both endpoints of that exact move with
      nothing dropped in between; else None. Introduces no look-ahead: own_values[j] itself only used
      data at <= own_ts[j] (inherited from the source feature/gate); this only remaps by timestamp.
      """
      own_pos = {ts: j for j, ts in enumerate(own_ts)}
      mapped: list[float | None] = []
      for k in range(len(union_ts) - 1):
          j0 = own_pos.get(union_ts[k])
          j1 = own_pos.get(union_ts[k + 1])
          if j0 is not None and j1 is not None and j1 == j0 + 1:
              mapped.append(own_values[j0])
          else:
              mapped.append(None)
      return mapped


  def _asset_directions(
      prices_by_asset: dict[str, list[float | None]],
      btc_prices: list[float],
      union_ts: list,
      asset_ts: dict[str, list],
      *,
      config: A1Config,
  ) -> dict[str, list[float | None]]:
      """Per-asset direction d_i[k] on the union return index (docs/specs/00031). Every value uses only
      prices/features at <= union index k -> no look-ahead. None where the asset itself has no valid
      return that period (either endpoint's price is None). Assumes btc_prices/asset_ts["BTC"] have
      full coverage of union_ts (no internal gaps) -- true for the real BTC series; a1_book_returns
      (Task 4) enforces this at its validation boundary."""
      g_btc_own = sma_gate(btc_prices, window=config.gate_window)
      g_btc = _map_to_union_index(asset_ts["BTC"], g_btc_own, union_ts)

      directions: dict[str, list[float | None]] = {}
      for asset, prices in prices_by_asset.items():
          own_prices = [p for p in prices if p is not None]
          ta_own = trend_agreement(own_prices, lookbacks=list(config.trend_lookbacks))
          ta = _map_to_union_index(asset_ts[asset], ta_own, union_ts)

          d: list[float | None] = []
          for k in range(len(union_ts) - 1):
              if prices[k] is None or prices[k + 1] is None:
                  d.append(None)
                  continue
              gate = g_btc[k] if g_btc[k] is not None else 0.0
              # ta[k] is guaranteed non-None here: prices[k] and prices[k+1] both present means
              # union_ts[k]/union_ts[k+1] are adjacent in this asset's own compressed calendar too.
              ta_k = ta[k]
              if config.regime == "single_gate":
                  long_ok = gate == 1.0
              else:
                  long_ok = gate == 1.0 and ta_k > 0
              if long_ok:
                  d.append(1.0)
              elif config.short == "confirmed_bear" and gate == 0.0 and ta_k < 0:
                  d.append(-config.short_exposure)
              else:
                  d.append(0.0)
          directions[asset] = d
      return directions
  ```

- [ ] **Step 4 — run, verify green**; then `uv run pytest -q` (full suite) + `uv run ruff check` / `ruff format
  --check`.

- [ ] **Step 5 — commit** (`feat(alpha): add per-asset direction builder for the A1 book`).

### Task 3: `_asset_returns` + `_inverse_vol_weights`

**Files:**

- Modify: `cli/alpha/a1.py`
- Test: `tests/test_alpha_a1_weights.py`

**Interfaces:**

- Produces (both private, unexported): `_asset_returns(prices: list[float | None]) -> list[float | None]`;
  `_inverse_vol_weights(prices_by_asset: dict[str, list[float | None]], *, lookback: int) -> list[dict[str, float]]`.

- [ ] **Step 1 — failing tests** (`tests/test_alpha_a1_weights.py`):

  ```python
  import pytest

  from cli.alpha.a1 import _inverse_vol_weights
  from cli.benchmark.strategies import dynamic_inverse_vol_basket

  # Same fixture as test_dynamic_basket_known_answer_two_assets_entry (tests/test_benchmark_dynamic_basket.py)
  # -- reusing its already hand-verified basket values as an independent cross-check.
  A = [100, 102, 99.96, 109.956, 112.15512, 109.9120176]  # retA = [.02,-.02,.10,.02,-.02]
  B = [None, None, 100, 118, 110.92, 116.466]  # retB = [None,None,.18,-.06,.05]


  def test_inverse_vol_weights_known_answer():
      weights = _inverse_vol_weights({"A": A, "B": B}, lookback=2)
      assert weights[0] == {} and weights[1] == {}  # warm-up
      assert weights[2] == pytest.approx({"A": 1.0})  # only A qualifies
      assert weights[3] == pytest.approx({"A": 1.0})  # only A qualifies
      assert weights[4] == pytest.approx({"A": 0.75, "B": 0.25})  # both qualify, A's window 1/3 B's vol


  def test_inverse_vol_weights_reduces_to_basket():
      # Sigma_i weights[k][i] * ret_i[k] must be bit-identical to dynamic_inverse_vol_basket's own output.
      prices = {"A": A, "B": B}
      lookback = 2
      weights = _inverse_vol_weights(prices, lookback=lookback)
      basket = dynamic_inverse_vol_basket(prices, lookback=lookback)
      for k in range(len(basket)):
          combo = 0.0
          for asset, w in weights[k].items():
              p0, p1 = prices[asset][k], prices[asset][k + 1]
              combo += w * (p1 / p0 - 1)
          assert abs(combo - basket[k]) < 1e-12


  def test_inverse_vol_weights_no_look_ahead():
      # Mirrors test_dynamic_basket_no_look_ahead's future-leak check exactly (same fixture).
      common_a = [100, 101, 102, 103, 104, 105, 106]
      common_b = [100, 99, 101, 100, 102, 101, 103]
      a1, a2 = common_a + [107, 108, 109], common_a + [500, 2, 777]
      b1, b2 = common_b + [104, 105, 106], common_b + [3, 900, 12]
      w1 = _inverse_vol_weights({"A": a1, "B": b1}, lookback=2)
      w2 = _inverse_vol_weights({"A": a2, "B": b2}, lookback=2)
      assert w1[:6] == w2[:6]
  ```

- [ ] **Step 2 — run, verify red** (`uv run pytest tests/test_alpha_a1_weights.py -v`).

- [ ] **Step 3 — implement** (append to `cli/alpha/a1.py`):

  ```python
  import statistics


  def _asset_returns(prices: list[float | None]) -> list[float | None]:
      """Per-asset union-calendar returns: ret[t] = prices[t+1]/prices[t]-1 iff both present, else None."""
      return [
          (prices[t + 1] / prices[t] - 1) if prices[t] is not None and prices[t + 1] is not None else None
          for t in range(len(prices) - 1)
      ]


  def _inverse_vol_weights(prices_by_asset: dict[str, list[float | None]], *, lookback: int) -> list[dict[str, float]]:
      """Per-period renormalized inverse-vol qualifying weights over a union calendar (SAME qualifying
      rule as dynamic_inverse_vol_basket, kept in sync by test_inverse_vol_weights_reduces_to_basket):
      asset i qualifies at period t iff ret_i[t] is present, its trailing window ret_i[t-lookback:t]
      (strictly before t) is fully non-None, and that window has positive stdev; weight 1/stdev,
      renormalized over qualifiers. No qualifier -> {}. Returns weights (not a pre-combined return
      series) so a1_book_returns (Task 4) can apply per-asset directions before combining. Private
      helper: trusts a validated, equal-length, non-empty prices_by_asset (mirrors
      dynamic_inverse_vol_basket's own private _inverse_vol_weight)."""
      length = len(next(iter(prices_by_asset.values())))
      returns_by_asset = {asset: _asset_returns(prices) for asset, prices in prices_by_asset.items()}

      weights: list[dict[str, float]] = []
      for t in range(length - 1):
          inv_weights: dict[str, float] = {}
          if t >= lookback:
              for asset, rets in returns_by_asset.items():
                  if rets[t] is None:
                      continue
                  window = rets[t - lookback : t]
                  if any(r is None for r in window):
                      continue
                  vol = statistics.stdev(window)
                  if vol > 0:
                      inv_weights[asset] = 1.0 / vol
          if not inv_weights:
              weights.append({})
              continue
          total = sum(inv_weights.values())
          weights.append({asset: inv / total for asset, inv in inv_weights.items()})
      return weights
  ```

- [ ] **Step 4 — run, verify green**; then `uv run pytest -q` + `uv run ruff check` / `ruff format --check`.

- [ ] **Step 5 — commit** (`feat(alpha): add inline inverse-vol basket weights for A1`).

### Task 4: `a1_book_returns`

**Files:**

- Modify: `cli/alpha/a1.py`, `cli/alpha/__init__.py`
- Test: `tests/test_alpha_a1_book.py`

**Interfaces:**

- Consumes: `_asset_directions` (Task 2), `_asset_returns` / `_inverse_vol_weights` (Task 3), `vol_target`
  (`cli.benchmark.strategies`), `run_backtest` (`cli.backtest`).
- Produces: `a1_book_returns(prices_by_asset: dict[str, list[float | None]], btc_prices: list[float], *, config:
  A1Config) -> dict` with keys `book_base_returns`, `vol_target_positions`, `net_returns`, `metrics`.

- [ ] **Step 1 — failing tests** (`tests/test_alpha_a1_book.py`):

  ```python
  import math

  import pytest

  from cli.alpha import A1Config, AlphaError, a1_book_returns
  from cli.benchmark.strategies import dynamic_inverse_vol_basket, returns_from_prices, sma_gate

  BASE_KWARGS = dict(gate_window=20, vol_lookback=20, basket_lookback=20, trend_lookbacks=(5, 10, 20))


  def _synthetic_universe(n=150):
      # Three legs (rally / drawdown / recovery) for BTC and a phase-shifted ETH -- guarantees the SMA
      # gate and trend_agreement both flip regimes for real (not a same-signed drift throughout), so
      # every toggle has a genuine chance to engage.
      btc, eth = [], []
      for i in range(n):
          if i < 50:
              btc.append(100.0 * (1.01**i))
          elif i < 100:
              btc.append(btc[49] * (0.99 ** (i - 49)))
          else:
              btc.append(btc[99] * (1.008 ** (i - 99)))
          if i < 60:
              eth.append(50.0 * (1.012**i))
          elif i < 110:
              eth.append(eth[59] * (0.985 ** (i - 59)))
          else:
              eth.append(eth[109] * (1.01 ** (i - 109)))
      return {"BTC": btc, "ETH": eth}, btc


  def test_a1_book_returns_no_lookahead():
      # Prices identical through index 99 (100 elements); ETH diverges from index 100 on. A return at
      # period t needs prices[t]/prices[t+1], so only t <= 98 is guaranteed invariant -> [:99].
      n, k_common = 150, 99
      prices_a, btc = _synthetic_universe(n)
      prices_b = {a: list(p) for a, p in prices_a.items()}
      for j in range(k_common + 1, n):
          prices_b["ETH"][j] = 999.0 * (1 + 0.3 * math.sin(j))
      cfg = A1Config(base="equal_risk_basket", regime="ensemble", short="confirmed_bear", target_vol=0.10, **BASE_KWARGS)
      out_a = a1_book_returns(prices_a, btc, config=cfg)
      out_b = a1_book_returns(prices_b, btc, config=cfg)
      assert out_a["book_base_returns"][:k_common] == out_b["book_base_returns"][:k_common]
      assert out_a["net_returns"][:k_common] == out_b["net_returns"][:k_common]


  def test_a1_book_returns_toggles_engage():
      prices, btc = _synthetic_universe(150)
      cfg_btc = A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, **BASE_KWARGS)
      cfg_basket = A1Config(base="equal_risk_basket", regime="single_gate", short="off", target_vol=0.10, **BASE_KWARGS)
      cfg_ensemble = A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.10, **BASE_KWARGS)
      cfg_short = A1Config(base="equal_risk_basket", regime="single_gate", short="confirmed_bear", target_vol=0.10, **BASE_KWARGS)
      cfg_vol12 = A1Config(base="equal_risk_basket", regime="single_gate", short="off", target_vol=0.12, **BASE_KWARGS)

      r_btc = a1_book_returns(prices, btc, config=cfg_btc)
      r_basket = a1_book_returns(prices, btc, config=cfg_basket)
      r_ensemble = a1_book_returns(prices, btc, config=cfg_ensemble)
      r_short = a1_book_returns(prices, btc, config=cfg_short)
      r_vol12 = a1_book_returns(prices, btc, config=cfg_vol12)

      assert r_btc["net_returns"] != r_basket["net_returns"]  # base toggle engages
      assert r_basket["net_returns"] != r_ensemble["net_returns"]  # regime toggle engages
      assert r_basket["net_returns"] != r_short["net_returns"]  # short toggle engages
      assert r_basket["net_returns"] != r_vol12["net_returns"]  # vol_target toggle engages


  def test_a1_book_returns_reduces_to_gated_btc():
      prices, btc = _synthetic_universe(150)
      cfg = A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, **BASE_KWARGS)
      out = a1_book_returns(prices, btc, config=cfg)
      gate = sma_gate(btc, window=20)
      ret = returns_from_prices(btc)
      expected = [g * r for g, r in zip(gate, ret)]
      assert out["book_base_returns"] == pytest.approx(expected)


  def test_a1_book_returns_reduces_to_basket_when_always_long():
      # A strictly rising BTC keeps sma_gate at 1.0 for every post-warmup period (all-long, single_gate,
      # short=off) -> every present asset's direction is +1.0, so the weighted directional book
      # collapses to the plain dynamic_inverse_vol_basket over those gate-on periods -- an end-to-end
      # cross-check (through the public API) that the inline weights match the reviewed basket.
      n = 100
      btc = [100.0 * (1.01**i) for i in range(n)]
      eth = [50.0 * (1.008**i) * (1 + 0.02 * math.sin(i / 3)) for i in range(n)]
      prices = {"BTC": btc, "ETH": eth}
      cfg = A1Config(base="equal_risk_basket", regime="single_gate", short="off", target_vol=0.10, **BASE_KWARGS)
      out = a1_book_returns(prices, btc, config=cfg)
      basket = dynamic_inverse_vol_basket(prices, lookback=20)
      gate = sma_gate(btc, window=20)
      for k in range(len(basket)):
          if gate[k] == 1.0:
              assert out["book_base_returns"][k] == pytest.approx(basket[k], abs=1e-9)


  def test_a1_book_returns_planted_signal_positive_sharpe():
      prices, btc = _synthetic_universe(150)
      cfg = A1Config(base="equal_risk_basket", regime="single_gate", short="off", target_vol=0.10, **BASE_KWARGS)
      out = a1_book_returns(prices, btc, config=cfg)
      assert out["metrics"]["sharpe"] > 0


  def test_a1_book_returns_guards():
      prices, btc = _synthetic_universe(150)
      cfg = A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, **BASE_KWARGS)
      with pytest.raises(AlphaError):
          a1_book_returns(prices, btc, config="not a config")
      with pytest.raises(AlphaError):
          a1_book_returns({"ETH": prices["ETH"]}, btc, config=cfg)  # missing BTC
      with pytest.raises(AlphaError):
          a1_book_returns({"BTC": btc, "ETH": prices["ETH"][:-1]}, btc, config=cfg)  # unequal lengths
      with pytest.raises(AlphaError):
          a1_book_returns(prices, btc[:-1], config=cfg)  # btc_prices wrong length
      gapped = {"BTC": [None] + btc[1:], "ETH": prices["ETH"]}
      with pytest.raises(AlphaError):
          a1_book_returns(gapped, btc, config=cfg)  # BTC must have full coverage
  ```

- [ ] **Step 2 — run, verify red** (`uv run pytest tests/test_alpha_a1_book.py -v`).

- [ ] **Step 3 — implement** (append to `cli/alpha/a1.py`):

  ```python
  from cli.backtest import run_backtest
  from cli.benchmark.strategies import vol_target


  def _validate_prices_by_asset(prices_by_asset: dict[str, list[float | None]]) -> None:
      if not isinstance(prices_by_asset, dict) or not prices_by_asset:
          raise AlphaError("prices_by_asset must be a non-empty dict of price series")
      if "BTC" not in prices_by_asset:
          raise AlphaError("prices_by_asset must include 'BTC'")
      lengths: set[int] = set()
      for asset, prices in prices_by_asset.items():
          if not isinstance(prices, list):
              raise AlphaError(f"prices for {asset!r} must be a list, got {type(prices)!r}")
          for p in prices:
              if p is not None and (not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 0):
                  raise AlphaError(f"prices must be None or finite positive numbers, got {p!r}")
          lengths.add(len(prices))
      if len(lengths) != 1:
          raise AlphaError(f"all price series must have equal length, got {sorted(lengths)}")
      if any(p is None for p in prices_by_asset["BTC"]):
          raise AlphaError("BTC must have full coverage on the union calendar (no None gaps)")


  def _validate_btc_prices(btc_prices: list[float], *, length: int) -> None:
      if not isinstance(btc_prices, list) or len(btc_prices) != length:
          got = len(btc_prices) if isinstance(btc_prices, list) else btc_prices
          raise AlphaError(f"btc_prices must be a list of length {length} (the union length), got {got!r}")
      for p in btc_prices:
          if not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 0:
              raise AlphaError(f"btc_prices must be finite positive numbers, got {p!r}")


  def a1_book_returns(
      prices_by_asset: dict[str, list[float | None]], btc_prices: list[float], *, config: A1Config
  ) -> dict:
      """Assemble the A1 book (docs/specs/00031): per-asset directions x inverse-vol/BTC-only weights x
      union-calendar returns -> book_base_returns, then vol_target -> run_backtest. Returns
      {book_base_returns, vol_target_positions, net_returns, metrics}."""
      if not isinstance(config, A1Config):
          raise AlphaError(f"config must be an A1Config, got {type(config)!r}")
      _validate_prices_by_asset(prices_by_asset)
      length = len(prices_by_asset["BTC"])
      _validate_btc_prices(btc_prices, length=length)

      working = {"BTC": prices_by_asset["BTC"]} if config.base == "btc_only" else prices_by_asset
      union_ts = list(range(length))
      asset_ts: dict[str, list] = {"BTC": union_ts}
      for asset, prices in working.items():
          if asset != "BTC":
              asset_ts[asset] = [k for k, p in enumerate(prices) if p is not None]

      directions = _asset_directions(working, btc_prices, union_ts, asset_ts, config=config)
      returns = {asset: _asset_returns(prices) for asset, prices in working.items()}

      if config.base == "btc_only":
          weights = [({"BTC": 1.0} if r is not None else {}) for r in returns["BTC"]]
      else:
          weights = _inverse_vol_weights(working, lookback=config.basket_lookback)

      book_base_returns: list[float] = []
      for k in range(length - 1):
          total = 0.0
          for asset in working:
              r = returns[asset][k]
              d = directions[asset][k]
              if r is None or d is None:
                  continue
              total += weights[k].get(asset, 0.0) * d * r
          book_base_returns.append(total)

      positions = vol_target(
          book_base_returns,
          target_vol=config.target_vol / math.sqrt(config.periods_per_year),
          lookback=config.vol_lookback,
          max_leverage=config.max_leverage,
      )
      backtest = run_backtest(book_base_returns, positions, fee_rate=0.0, periods_per_year=config.periods_per_year)
      return {
          "book_base_returns": book_base_returns,
          "vol_target_positions": positions,
          "net_returns": backtest["net_returns"],
          "metrics": {k: v for k, v in backtest.items() if k != "net_returns"},
      }
  ```

  Update `cli/alpha/__init__.py`:

  ```python
  from cli.alpha.a1 import A1Config, a1_book_returns
  from cli.alpha.errors import AlphaError

  __all__ = ["A1Config", "AlphaError", "a1_book_returns"]
  ```

- [ ] **Step 4 — run, verify green**; then `uv run pytest -q` (full suite) + `uv run ruff check` / `ruff format
  --check`.

- [ ] **Step 5 — commit** (`feat(alpha): add a1_book_returns book assembler`).

### Task 5: `cli/alpha/killbar.py` — `a1_kill_bar` + `short_leg_whipsaw`

**Files:**

- Create: `cli/alpha/killbar.py`
- Modify: `cli/alpha/__init__.py`
- Test: `tests/test_alpha_killbar.py`

**Interfaces:**

- Consumes: `deflated_sharpe_ratio`, `reality_check_pvalue`, `sharpe`, `max_drawdown`, `ValidationError`
  (`cli.validation`); `linear_signal`, `sign_strategy_returns` (`cli.validation`, test-only synthetic fixtures).
- Produces: `a1_kill_bar(book_net_returns: list[float], benchmark_net_returns: list[float], *, n_trials: int,
  var_trials: float, mean_block: float, seed: int, cost_stressed_returns: list[float], regime_slices: dict[str,
  list[float]]) -> dict`; `short_leg_whipsaw(short_only_returns: list[float]) -> dict`.

- [ ] **Step 1 — failing tests** (`tests/test_alpha_killbar.py`):

  ```python
  import pytest

  from cli.alpha import AlphaError, a1_kill_bar, short_leg_whipsaw
  from cli.validation import linear_signal, sign_strategy_returns

  N = 200


  def _book_and_benchmark(*, beta, seed):
      x, r = linear_signal(N, beta=beta, noise_sd=1.0, seed=seed)
      book = sign_strategy_returns(x, r)
      benchmark = [0.0] * N  # flat benchmark -> the book's outperformance is just its own return
      return book, benchmark


  def _slices(book):
      return {"first_half": book[: N // 2], "second_half": book[N // 2 :]}


  def test_a1_kill_bar_planted_edge_passes():
      book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
      result = a1_kill_bar(
          book, benchmark, n_trials=16, var_trials=1.0, mean_block=5, seed=7,
          cost_stressed_returns=book, regime_slices=_slices(book),
      )
      assert result["dsr"] > 0
      assert result["spa_pass"] is True
      assert result["spa_p_value"] < 0.05
      assert result["cost_stress_pass"] is True
      assert result["worst_slice_pass"] is True
      assert result["passes"] is True


  def test_a1_kill_bar_null_rarely_passes():
      # Mirrors tests/test_acceptance.py's null-false-positive-rate style: over 20 seeds, a beta=0 (no
      # real edge) book should almost never clear all four kill-bar conditions simultaneously.
      passed = 0
      for seed in range(20):
          book, benchmark = _book_and_benchmark(beta=0.0, seed=seed)
          result = a1_kill_bar(
              book, benchmark, n_trials=16, var_trials=1.0, mean_block=5, seed=seed + 100,
              cost_stressed_returns=book, regime_slices=_slices(book),
          )
          if result["passes"]:
              passed += 1
      assert passed <= 4


  def test_a1_kill_bar_cost_stress_can_fail_alone():
      book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
      stressed = [r - 1.0 for r in book]  # a heavy flat cost drag that flips the stressed series negative
      result = a1_kill_bar(
          book, benchmark, n_trials=16, var_trials=1.0, mean_block=5, seed=7,
          cost_stressed_returns=stressed, regime_slices=_slices(book),
      )
      assert result["cost_stress_pass"] is False
      assert result["passes"] is False  # cost stress alone fails the all-must-hold bar


  def test_a1_kill_bar_worst_slice_can_fail_alone():
      book, benchmark = _book_and_benchmark(beta=1.2, seed=42)
      bad_slice = [-0.01 + 0.002 * ((i % 3) - 1) for i in range(50)]  # non-degenerate, clearly negative
      result = a1_kill_bar(
          book, benchmark, n_trials=16, var_trials=1.0, mean_block=5, seed=7,
          cost_stressed_returns=book, regime_slices={"good": book, "bad_regime": bad_slice},
      )
      assert result["worst_slice_name"] == "bad_regime"
      assert result["worst_slice_pass"] is False
      assert result["passes"] is False


  def test_a1_kill_bar_guards_length_mismatch():
      with pytest.raises(AlphaError):
          a1_kill_bar(
              [0.01, 0.02], [0.01], n_trials=16, var_trials=1.0, mean_block=5, seed=1,
              cost_stressed_returns=[0.01, 0.02], regime_slices={"x": [0.01, 0.02]},
          )


  def test_a1_kill_bar_guards_empty_regime_slices():
      with pytest.raises(AlphaError):
          a1_kill_bar(
              [0.01, 0.02, 0.03], [0.0, 0.0, 0.0], n_trials=16, var_trials=1.0, mean_block=5, seed=1,
              cost_stressed_returns=[0.01, 0.02, 0.03], regime_slices={},
          )


  def test_short_leg_whipsaw_known_answer():
      short_only = [0.0, 0.02, -0.01, 0.0, 0.03, -0.02, 0.0, 0.01, 0.0]
      # engaged = [F,T,T,F,T,T,F,T,F] -> 6 flips / 8 transitions = 0.75 turnover.
      # active returns = [0.02,-0.01,0.03,-0.02,0.01] -> 3/5 positive = 0.6 hit-rate.
      # equity: 1 -> 1.02 -> 1.0098 -> 1.0098 -> 1.040094 -> 1.01929212(=peak*0.98, dd=0.02 exactly) -> ...
      result = short_leg_whipsaw(short_only)
      assert result["turnover"] == pytest.approx(0.75)
      assert result["hit_rate"] == pytest.approx(0.6)
      assert result["max_drawdown"] == pytest.approx(0.02)


  def test_short_leg_whipsaw_never_engaged():
      result = short_leg_whipsaw([0.0, 0.0, 0.0, 0.0])
      assert result["turnover"] == 0.0
      assert result["hit_rate"] == 0.0


  @pytest.mark.parametrize("returns", [[0.01], [], [0.01, float("nan")], "not a list"])
  def test_short_leg_whipsaw_guards(returns):
      with pytest.raises(AlphaError):
          short_leg_whipsaw(returns)
  ```

- [ ] **Step 2 — run, verify red** (`uv run pytest tests/test_alpha_killbar.py -v`).

- [ ] **Step 3 — implement** `cli/alpha/killbar.py`:

  ```python
  from __future__ import annotations

  import math

  from cli.alpha.errors import AlphaError
  from cli.validation import ValidationError, deflated_sharpe_ratio, max_drawdown, reality_check_pvalue, sharpe


  def a1_kill_bar(
      book_net_returns: list[float],
      benchmark_net_returns: list[float],
      *,
      n_trials: int,
      var_trials: float,
      mean_block: float,
      seed: int,
      cost_stressed_returns: list[float],
      regime_slices: dict[str, list[float]],
  ) -> dict:
      """The Phase-4 kill bar (docs/research/00.master-plan.md sec12; docs/specs/00031): a variant is
      archived unless ALL hold: DSR > 0 at its trial count, SPA says it beats the benchmark, it
      survives 1.5x cost stress, and its worst walk-forward regime slice is not disqualifying.

      Two judgment calls made here (see docs/plans/00031 "Design decisions ... flagged for review"):
      "survives cost stress" = the cost-stressed series' own Sharpe is still > 0; "worst slice not
      disqualifying" = every regime_slices entry's Sharpe is > 0. Task 6 (real-data run) may want to
      recalibrate the worst-slice bar against the frozen benchmark's own worst-slice Sharpe instead.
      """
      if len(book_net_returns) != len(benchmark_net_returns):
          raise AlphaError("book_net_returns and benchmark_net_returns must have the same length")
      if not isinstance(regime_slices, dict) or not regime_slices:
          raise AlphaError("regime_slices must be a non-empty dict of regime -> return slice")

      try:
          n_obs = len(book_net_returns)
          sr = sharpe(book_net_returns)
          dsr = deflated_sharpe_ratio(sr, n_obs, n_trials, var_trials)

          outperformance = [[b - m] for b, m in zip(book_net_returns, benchmark_net_returns)]
          spa = reality_check_pvalue(outperformance, mean_block=mean_block, seed=seed)
          spa_pass = spa["p_value"] < 0.05

          cost_stress_sharpe = sharpe(cost_stressed_returns)
          cost_stress_pass = cost_stress_sharpe > 0

          slice_sharpes = {name: sharpe(rets) for name, rets in regime_slices.items()}
      except ValidationError as exc:
          raise AlphaError(f"kill-bar computation failed: {exc}") from exc

      worst_slice_name = min(slice_sharpes, key=slice_sharpes.get)
      worst_slice_sharpe = slice_sharpes[worst_slice_name]
      worst_slice_pass = worst_slice_sharpe > 0

      passes = dsr > 0 and spa_pass and cost_stress_pass and worst_slice_pass
      return {
          "dsr": dsr,
          "spa_p_value": spa["p_value"],
          "spa_pass": spa_pass,
          "cost_stress_sharpe": cost_stress_sharpe,
          "cost_stress_pass": cost_stress_pass,
          "worst_slice_name": worst_slice_name,
          "worst_slice_sharpe": worst_slice_sharpe,
          "worst_slice_pass": worst_slice_pass,
          "passes": passes,
      }


  def short_leg_whipsaw(short_only_returns: list[float]) -> dict:
      """Isolated whipsaw diagnostic for the short leg (finding-2's whipsaw kill test, docs/specs/00031):
      `short_only_returns` is the short leg's own per-period P&L contribution (0.0 when not engaged that
      period, its realized short return when engaged). turnover = fraction of period-to-period
      engagement flips (0 <-> nonzero); hit_rate = fraction of ENGAGED periods with a positive return;
      max_drawdown reuses the validation harness on the short-only series."""
      if not isinstance(short_only_returns, list) or len(short_only_returns) < 2:
          raise AlphaError(f"short_only_returns must be a list of >= 2 values, got {short_only_returns!r}")
      for r in short_only_returns:
          if not isinstance(r, (int, float)) or not math.isfinite(r):
              raise AlphaError(f"short_only_returns must be finite numbers, got {r!r}")

      engaged = [r != 0.0 for r in short_only_returns]
      flips = sum(1 for t in range(1, len(engaged)) if engaged[t] != engaged[t - 1])
      turnover = flips / (len(engaged) - 1)
      active = [r for r in short_only_returns if r != 0.0]
      hit_rate = (sum(1 for r in active if r > 0) / len(active)) if active else 0.0
      try:
          mdd = max_drawdown(short_only_returns)
      except ValidationError as exc:
          raise AlphaError(f"short_leg_whipsaw computation failed: {exc}") from exc
      return {"turnover": turnover, "hit_rate": hit_rate, "max_drawdown": mdd}
  ```

  Update `cli/alpha/__init__.py`:

  ```python
  from cli.alpha.a1 import A1Config, a1_book_returns
  from cli.alpha.errors import AlphaError
  from cli.alpha.killbar import a1_kill_bar, short_leg_whipsaw

  __all__ = ["A1Config", "AlphaError", "a1_book_returns", "a1_kill_bar", "short_leg_whipsaw"]
  ```

- [ ] **Step 4 — run, verify green**; then `uv run pytest -q` (full suite) + `uv run ruff check` / `ruff format
  --check`.

- [ ] **Step 5 — commit** (`feat(alpha): add the A1 kill-bar evaluation harness`).

### Task 5b (iter-045 closeout)

**Files:** Modify `docs/iterations-history.md`.

- [ ] **Step 1** — README Usage: **no change** — A1 adds no CLI subcommand (`cli/alpha/` is a library only), so
  `readme-usage.md`'s update rule doesn't apply this iteration. Note this explicitly in the closeout entry.
- [ ] **Step 2** — `.tmp/decisions.md`: **no new entry** — the `[iter-045]` decision (per-asset book architecture,
  code-now/verdict-next split) is already logged from the design/brainstorming pass; Tasks 1–5 execute that
  decision without introducing a new subject-matter question.
- [ ] **Step 3** — append a `## <YYYY-MM-DD> — iter-045: A1 book assembler + kill-bar harness (Phase 4, synthetic-
  proven)` section to `docs/iterations-history.md` at execution time (compute the real new-test count from the
  actual `uv run pytest -q` tally — do not pre-guess it here). Cover: the new `cli/alpha/` package
  (`A1Config`, `_asset_directions`, `_inverse_vol_weights`, `a1_book_returns`, `a1_kill_bar`,
  `short_leg_whipsaw`); that every leak test was confirmed to fail on a deliberately-broken (peeking)
  implementation before being restored (mirroring iter-040/041's "distrust the instrument" discipline); that this
  is **code only, no verdict** — the real-data 16-trial kill-bar run is iter-046; and the two flagged judgment
  calls (worst-slice threshold, cost-stress rule) for iter-046 to revisit.
- [ ] **Step 4** — `uv run pre-commit run -a`; stage everything it rewrites; commit
  (`docs: iter-045 closeout — A1 book assembler + kill-bar harness (synthetic-proven)`).

---

## iter-046 (outline only — expand into full TDD steps at that iteration)

### Task 6: real-data 16-trial kill-bar run

Design-level bullets; no code written here.

- Build the union-calendar `prices_by_asset` for the 10 EUR majors (reuse the loader pattern from plan `00032`'s
  Task 2: `cli.ohlc.dataset.read_parquet` per asset, union `ts` calendar, `None` where a bar is absent), and
  `btc_prices` as BTC's own full contiguous close series (needed by `a1_book_returns`'s `btc_prices` param and by
  `_asset_directions`'s full-coverage assumption).
- Build the frozen `gated-B1` benchmark net-return series (vol-targeted BTC x 200-day gate, full history) as
  `a1_kill_bar`'s `benchmark_net_returns`.
- Build the 1.5x-cost-stressed book returns per variant: re-run `a1_book_returns` with a `run_backtest` fee_rate of
  `spot_fee_rates(0.0)["maker"] * 1.5` (cli/costs) instead of `0.0`, feeding `a1_kill_bar`'s `cost_stressed_returns`.
- Build the calendar-year regime slices (per master-plan sec12's walk-forward folds) from the book's own
  `net_returns`, for `a1_kill_bar`'s `regime_slices`.
- Run all 16 toggle combinations (`base` x `regime` x `short` x `target_vol` in {10%, 12%}) through
  `a1_book_returns` -> `a1_kill_bar`; collect per-variant `passes` + the supporting DSR/SPA/cost-stress/worst-slice
  numbers + engagement evidence (arms differ; gate/short measurably changes exposure).
- Run `short_leg_whipsaw` on each `short="confirmed_bear"` variant's isolated short-leg return series (built the
  same way as the book, but zeroing out non-negative directions before combining).
- Revisit the two flagged kill-bar judgment calls (worst-slice threshold, cost-stress rule) against the real
  benchmark's own numbers before reading verdicts.

### Task 7: registry writes

- Write each of the 16 variants to `cli/registry/` (`TrialRegistry.append`): `family="A1"`, monotone
  `n_trials_in_family` (1..16 in run order), `spec_hash`/`dataset_hash` (derive from the spec file + the union
  dataset), the metrics dict (DSR, SPA p-value, cost-stress Sharpe, worst-slice Sharpe, `passes`, plus the raw
  Sharpe/maxDD/annualized-return from `a1_book_returns`'s own `metrics`), `verdict` in `{"adopt","reject","park"}`
  per the kill-bar's `passes` boolean (+ human judgment on ties/edge cases).
- Resolve the registry file's location before writing (flagged above: `runs/` gitignored vs. committed — check
  how `cli/registry/` is invoked/tested elsewhere and whether a `runs/`-relative default path already exists in
  config).
- Plausibility-gate every metric (finite, in-range) before appending — the registry's own `validate_caller_fields`
  already rejects non-finite leaves, but a sanity read (e.g., DSR in `[0, 1]`, Sharpe in a plausible range) before
  trusting a 16-row batch write is cheap insurance.

### Task 8: results report + iter-046 closeout

- Write `docs/research/06.phase4-a1-results.md` (a Phase-4 result note) with the 16-variant table (toggles, DSR,
  SPA p-value, cost-stress pass, worst-slice pass, overall verdict) and the A1 verdict: does any variant beat
  `gated-B1` under the full kill bar? An honest kill (none clears the bar) is a success, not a failure — record it
  as such, per the spec's Closeout section.
- **Add this report to the mdformat allowlist** (`.pre-commit-config.yaml`'s mdformat `files:` list) — per
  CLAUDE.md's rule for new research papers under `docs/research/`.
- Append the `.tmp/decisions.md` `[iter-046]` entries for the per-variant verdicts (or the overall kill), then
  persist per `decisions-log.md`'s phase-persistence rule **only if** this is Phase 4's close-out report — check
  master-plan sec12's Phase-4 exit bar first; if Phase 4 continues into further alpha families (A2, Bucket B),
  this is an interim result note, not the phase close-out, and `.tmp/decisions.md` stays live for those.
- Append the `## <YYYY-MM-DD> — iter-046: A1 real-data kill-bar verdict (Phase 4)` `docs/iterations-history.md`
  entry (final task of the whole plan): the 16-trial run, the per-variant verdicts, the registry's first real
  records, and the overall A1 read (adopted / killed).
- `uv run pre-commit run -a`; stage rewrites; commit.
