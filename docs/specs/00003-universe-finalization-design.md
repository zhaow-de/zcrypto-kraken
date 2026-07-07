# Rule-Driven Universe Finalization — Design (Phase 1)

**Iteration:** iter-005 · **Phase:** 1 (Data Foundation) · **Status:** design approved (unattended loop)
**Master plan refs:** §3 (universe governance — the mechanical selection rule; BTC/ETH mandatory; escalate on <8/>15), §6 (decision cadence), §8 (hash-versioned artifacts).

## Problem & context

Every backtest needs a **point-in-time universe file**: the mechanically-selected set of tradeable pairs plus the criteria values that selected them. This iteration composes the two prior reference datasets — iter-002's margin/leverage snapshot (`cli.snapshot`) and iter-004's daily OHLC (`cli.ohlc`) — into §3's rule, and writes a committed, versioned universe file.

## Goals

- `cli/universe/` — pure rule application + a 30-day-median-quote-volume signal from the OHLC daily bars, producing a `UniverseSelection` and a committed point-in-time universe file. TDD.

## Non-goals

- No spread criterion yet (needs the L2 capture daemon — VPS/infra-gated, not built): the file records `spread_cap: "pending-capture"` for each name. No corporate-action ledger beyond iter-002's aliases (a light note only; the DOT-redenomination-style entries are a follow-up). No new external deps (uses `cli.snapshot`, `cli.ohlc`, polars, stdlib).

## Design

**Module `cli/universe/` (stdlib + polars; consumes `cli.snapshot` + `cli.ohlc`):**

- `errors.py` — `UniverseError(Exception)`.
- `volume.py` — `median_quote_volume(daily: pl.DataFrame, *, window: int = 30) -> float`: over the last `window` daily bars, quote volume per day = `volume * vwap` (base volume × price ≈ quote/EUR turnover); return the median. Raises `UniverseError` if fewer than `window` rows.
- `rules.py` — the §3 rule, pure:
  - `DEFAULT_MIN_LEVERAGE = 2`, `DEFAULT_MIN_MEDIAN_QUOTE_VOLUME = 1_000_000.0` (€/day; documented, tunable), `MANDATORY = ("BTC", "ETH")`, `MIN_NAMES = 8`, `MAX_NAMES = 15`.
  - `finalize_universe(pairs: list, volumes: dict[str, float], *, min_leverage=…, min_median_quote_volume=…, mandatory=MANDATORY) -> UniverseSelection`: for each candidate, evaluate `margin_enabled ∧ max(leverage_buy) ≥ min_leverage ∧ volumes[sym] ≥ floor`; a `mandatory` name is always selected (and flagged if it would otherwise fail). Return per-symbol `{symbol, selected, margin_enabled, max_leverage, median_quote_volume, reasons[]}` + the selected set + an `escalate` bool (true iff `len(selected) < MIN_NAMES or > MAX_NAMES`). `pairs` are `cli.snapshot` `PairSnapshot`s; `volumes` is `{symbol: median_quote_volume}`.
- `build.py` — `build_universe_file(selection, *, as_of: str, params: dict, provenance: dict) -> dict`: assemble the point-in-time file (as-of UTC date, the selected symbols, the full per-symbol criteria table, the parameter values used, `spread_cap: "pending-capture"`, and provenance — the snapshot + OHLC dataset hashes it was derived from). `render_markdown(file) -> str`.

**Artifact:** committed `docs/universe/point-in-time-universe.md` (hand-formatted; NOT on the mdformat allowlist) — the human-readable universe file with the selection table + params + provenance. (The machine-readable JSON can live under gitignored `data/` and be regenerated; the committed markdown is the versioned record, since the universe is a small, load-bearing backtest input.)

## Testing

`tests/test_universe_*.py`, on synthetic `PairSnapshot`s + a small polars frame (no live network):
- `median_quote_volume`: correct median of `volume*vwap` over the window; raises if too few rows.
- `finalize_universe`: a name below the leverage floor / volume floor is dropped; a `mandatory` name is kept even if failing (and flagged); `escalate` true when the selected count is <8 or >15; the per-symbol reasons are populated.
- `build_universe_file`: deterministic given fixed `as_of`/provenance; `render_markdown` contains the selected names, the param values, and `pending-capture` for spread.

## Deferred / parked

- Spread-cap criterion → the L2 capture daemon (VPS-gated). Full symbol & corporate-action ledger (redenominations, quote-book migrations) → follow-up. Full-history volume → improves once T0001 backfill lands.

## Closeout (planned)

On merge: generate the live universe file from the current snapshot + OHLC dataset, commit `docs/universe/point-in-time-universe.md`; append the `iter-005` iterations-history entry.
