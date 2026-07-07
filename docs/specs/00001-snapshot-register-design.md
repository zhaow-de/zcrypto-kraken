# Kraken Reference-Data Snapshot + Register — Design (Phase 0 · P0-2)

**Iteration:** iter-002 · **Phase:** 0 (Preparation) · **Status:** design approved (unattended loop)
**Master plan refs:** §Phase 0 autonomous work (⏱ reconfirmation sweep), §3 (universe governance / symbol ledger), §8 (data QA), §14 (snapshot register).

## Problem & context

Phase 1's universe selection and the cost model need **ground-truth** Kraken reference data — which pairs are margin-enabled, their per-pair leverage, order minimums, and the internal symbol aliases (XBT=BTC, XDG=DOGE, §3) — not values transcribed from a doc. This iteration builds a small, tested fetcher for Kraken's **public** REST reference endpoints (no API key) and commits a versioned **snapshot register**: the reconfirmed ⏱ facts plus the candidate-basket margin/leverage table, with provenance.

Feasibility confirmed at kickoff: `GET https://api.kraken.com/0/public/AssetPairs` → 1509 pairs, 265 margin-enabled, ETH/EUR & XBT/EUR at leverage 2–10×.

## Goals

- `cli/snapshot/` — a stdlib-only fetcher + deriver for Kraken public reference data, unit-tested against saved fixtures (no live-network tests).
- A committed, dated snapshot-register document capturing: the candidate-basket margin/leverage ground truth, symbol aliases, and the fee/rollover ⏱ facts (with what is account-confirmable flagged, since that is parked in T0000).

## Non-goals

- No trade/private endpoints, no API keys (public only). No WebSocket. No fee-tier or rollover-band values that require the live account (those stay in T0000).
- No third-party HTTP client — stdlib `urllib.request` is enough for two GETs.
- No scheduling/daemon (that is the Phase-1 capture pipeline, a separate future iteration).

## Design

**Module `cli/snapshot/` (stdlib only), mirroring `cli/logging/`/`cli/registry/`:**

- `fetch.py` — `fetch_public(method: str) -> dict`: GET `https://api.kraken.com/0/public/{method}` via `urllib.request` with a timeout, parse JSON, and **raise `SnapshotError` on a non-empty Kraken `error` array** (Kraken returns HTTP 200 with errors in the body) or on a transport error. Returns `result`. Thin; the network call is the only impure part.
- `assetpairs.py` — pure derivation: `derive_universe(assetpairs: dict, assets: dict, symbols: list[str]) -> list[PairSnapshot]`. For each candidate symbol, resolve its Kraken pair key + `wsname`, and record `margin_enabled` (truthy `leverage_buy`), `leverage_buy`/`leverage_sell`, `ordermin`, `costmin`, `status`. Resolve asset aliases from the `Assets` result (altname/alias → the XBT=BTC / XDG=DOGE ledger).
- `register.py` — `build_snapshot(result_assetpairs, result_assets, symbols, fetched_at) -> dict`: assemble a structured, content-hashed snapshot dict (raw endpoint results + derived universe table + `fetched_at` UTC + a sha256 over the canonical JSON). `render_markdown(snapshot) -> str`: render the register section (candidate-basket table + aliases + provenance). `fetched_at` is injected (not read from the clock inside the pure function) for testability.
- `errors.py` — `SnapshotError(Exception)`.

**Candidate symbols** (from §3, EUR-quoted primary + BTC-quoted RV legs): BTC, ETH, SOL, XRP, ADA, LINK, DOGE, LTC, DOT, AVAX (vs EUR); ETH/BTC, SOL/BTC (vs BTC). Resolve via `wsname` (e.g. `XBT/EUR`, `XETH/XXBT`), tolerating Kraken's alias spellings.

**Committed artifact:** `docs/research/01.1.kraken-snapshot-register.md` — the dated register: candidate-basket margin/leverage/ordermin table, symbol-alias ledger, and the ⏱ fee/margin facts carried from the master plan §14 (marked "account-confirmation pending → T0000"). Add this file to the mdformat allowlist (it is a research report, per CLAUDE.md). The raw snapshot JSON writes under `data/snapshots/` (gitignored); the register doc records its sha256 for reproducibility.

## Testing

`tests/test_snapshot_*.py`, against **saved trimmed fixtures** (a real `AssetPairs`/`Assets` sample, captured once and committed under `tests/fixtures/`):
- `fetch_public` raises `SnapshotError` when the Kraken `error` array is non-empty (fixture with `{"error":["EGeneral:Invalid arguments"]}`); returns `result` on success. (Monkeypatch `urllib.request.urlopen` — no live network.)
- `derive_universe` resolves BTC→`XBT/EUR` with `margin_enabled=True`, leverage list captured; a non-margin or absent symbol → `margin_enabled=False` / flagged missing; aliases resolved (XBT→BTC, XDG→DOGE).
- `build_snapshot` is deterministic given a fixed `fetched_at` (stable sha256); `render_markdown` contains the basket rows and the provenance hash.

## Deferred / parked

- Live fee-tier, AoP rule, and rollover bands → **T0000** (need the account).
- Scheduled re-fetch / the L2 capture daemon → Phase 1.

## Closeout (planned)

On merge: append an `iter-002` entry to `docs/iterations-history.md`; add `docs/research/01.1.kraken-snapshot-register.md` to the mdformat allowlist in the same change.
