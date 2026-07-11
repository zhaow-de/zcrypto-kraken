# B2 Funding Substrate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement spec `docs/specs/00047-b2-funding-substrate-design.md`: the `cli/derivatives/funding.py` backfill (checksum-verified Binance Vision funding dumps) + the real build of `data/derivatives-funding/` for the 10 perps, QA'd and manifest-hashed.

**Architecture:** One TDD task (the fetch/parse/backfill module with an injectable opener) then the real network build + QA in the same task's report; orchestrator closeout. No consumer wired (the B2 harness is a later iteration).

**Tech Stack:** Python 3.14 stdlib (`urllib`, `zipfile`, `hashlib`, `io`), polars, `cli.ohlc.dataset.write_parquet/read_parquet` (reuse the parquet writer), the `cli/ohlc/fetch.py` injectable-opener idiom.

## Global Constraints

- **Checksum enforced**: every downloaded zip's sha256 is verified against its `.CHECKSUM`; a mismatch raises `DerivativesError`, never a silent accept.
- **Aware-UTC** for every `ts` (from `calc_time` ms); the current incomplete month is excluded; a 404 inside a listed series (after the leading pre-listing run) is an error.
- New derived root `data/derivatives-funding/` only — canonical untouched; the dataset is gitignored by `data/.gitignore`.
- Ruff 132/double quotes; `uv run pre-commit run -a`; actual-model trailers + `Claude-Session`; subagent review + `Reviewed-by` before push.

______________________________________________________________________

### Task 1 (subagent, TDD + real build): the funding backfill module

**Files:** Create `cli/derivatives/__init__.py`, `cli/derivatives/funding.py`, `cli/derivatives/errors.py` (`DerivativesError`), `tests/test_derivatives_funding.py`.

**Interfaces (produces):** exactly the spec's block — `PERP_SYMBOLS`, `fetch_funding_month(perp, year, month, *, opener=...) -> list[list] | None`, `backfill_funding(perp, *, start=(2019,9), clock=_utc_now, opener=...) -> pl.DataFrame`, `build_funding_substrate(out_root, *, perps=PERP_SYMBOLS, clock=_utc_now, opener=...) -> dict`, `read_funding_series(out_root, perp) -> pl.DataFrame`. Loggers `get_logger("derivatives.funding")`.

**TDD (inject a fake opener returning canned zip bytes — build a tiny in-memory zip with `zipfile` in the fixtures; no network in tests):**

1. `fetch_funding_month` parses a fixture zip (header + 3 rows) → `[[calc_time_ms, interval_hours, rate], …]`; **checksum match required** (fixture `.CHECKSUM` = real sha256 of the fixture zip) — a wrong-checksum fixture raises `DerivativesError`; an opener raising HTTP 404 → returns `None`; a transport error → `DerivativesError`.
2. `backfill_funding` — a fake opener mapping (perp, y, m) → bytes with 404 before a listing month: assert the leading 404 run is skipped, the frame starts at the first data month, and a 404 injected *inside* the data range raises `DerivativesError`. `clock` set mid-month → that month excluded; the prior complete month included. `ts` aware-UTC, sorted, deduped (feed a duplicated row → one survives).
3. `build_funding_substrate` over two fake perps → writes `data/.../funding.parquet` per perp + a manifest with per-perp `{rows, first_ts, last_ts, sha256}` + `basket_sha256`; `read_funding_series` round-trips.
4. Schema: `ts` Datetime(UTC), `funding_rate` Float64, `interval_hours` Int64.

Then implement; file green; **full suite** (`uv run pytest`, expect 1269 + new); `uv run pre-commit run -a` clean.

**The real build (in the task report, after the commit — foreground, chunked per perp with `timeout` guards; artifacts land under gitignored `data/`):** `build_funding_substrate(Path("data/derivatives-funding"))` for the 10 perps against the live Binance Vision CDN (be polite: the module should fetch sequentially per perp; ~78 months × 10 = small zips). Then QA: per-perp coverage table (rows, first/last ts, cadence-gap count + largest gap), the balanced-panel start (max first_ts), and the funding-rate/interval sanity flags. Paste the QA tables + the `basket_sha256` into the report. Commit `feat(derivatives): B2 funding substrate — checksum-verified Binance Vision backfill (spec 00047)`.

### Task 2 (orchestrator, closeout)

- [ ] Read the QA against the spec's checks (expected panel start ≈ 2020-09; no unexplained cadence gaps beyond listing-day partials / known funding outages; `interval_hours` == 8 throughout the era, or a disclosed venue change). A material anomaly → instrument bug-hunt, not shipping.
- [ ] T0023: `## Done so far` gains the funding substrate (dataset hash + path); the "build the funding + OI backfill" next-step reworded to OI-remaining; status → `partial`; index bullet moved to Partially done.
- [ ] Decisions-log verdict (`[iter-090]`: funding substrate delivered, `basket_sha256`, panel start, coverage); iterations-history entry; pre-commit; commit; final whole-branch review; PR `feat(derivatives): iter-090 — B2 funding substrate`; merge via merge-pr when green.
