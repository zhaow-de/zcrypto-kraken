# Iterations history — Phase 0 (Preparation & Ratification)

Per-iteration changelog for Phase 0. Appended at each iteration's close-out; see `.claude/rules/iterations-history.md`.

## 2026-07-07 — iter-001: trial registry (Phase 0 · P0-1)

First iteration of the autonomous research loop, working Phase 0 of `docs/research/00.master-plan.md`.

- **Added `cli/registry/`** — the append-only, integrity-checked JSONL trial registry (`TrialRegistry`, `TrialRecord`, `RegistryError`/`RegistryCorruptionError`, plus `canonical_json`/`compute_hash`/`VERDICTS`/`SCHEMA_VERSION`), stdlib-only, mirroring `cli/logging/`. This is the master plan's first-class "integrity by construction" deliverable (§9).
- **Encodes the PoC NaN-DSR failure on both paths** so it cannot recur: `json.dumps(allow_nan=False)` on write and `json.loads(parse_constant=…)` on read, plus a recursive finiteness walk over nested dicts/lists of metrics (rejecting `bool`/numpy leaves via `type(x) is` checks).
- **Integrity by construction:** monotonic-contiguous `trial_id`; per-record `record_hash` self-check (accidental-edit detection — the cross-record hash chain is deferred to Phase 2); `n_trials_in_family >= recorded-family-count` floor (anti-gaming the DSR deflation denominator); `fcntl.flock` + `os.fsync` append that re-derives the next id from disk under lock; and a torn-trailing-line self-heal so a crashed append never bricks the autonomous loop.
- **33 unit tests** incl. planted-corruption: bare-`NaN` token at load, NaN buried in a nested list, `record_hash` mismatch, contiguity gap/dup/reorder, torn-tail heal vs. interior raise, unknown schema, family-count floor, concurrent-unique-ids.
- **Design/plan:** `docs/specs/00000-trial-registry-design.md` (from a 3-proposal + adversarial-critic design panel), `docs/plans/00000-trial-registry.md`. **Deferred to Phase 2:** the cross-record hash chain, the corrupt-a-copy CI test, and SPA/DSR computation. **Known minor:** an external-hand-edited complete last line lacking a trailing newline would make the *next* append concatenate — it fails *loudly* on the following load (never a silent fake winner), left as Phase-2 hardening.
- Phase 0 human-gated items (D3(i) account actions + live fee/AoP confirmation) parked in open-topic **T0000**.
- Reviewed by an independent whole-branch reviewer (verdict: approved, zero Critical/Important defects, integrity core verified under live probes).

## 2026-07-07 — iter-002: Kraken reference-data snapshot register (Phase 0 · P0-2)

- **Added `cli/snapshot/`** — a stdlib-only fetcher/deriver for Kraken's **public** reference endpoints: `fetch.py` GETs `AssetPairs`/`Assets` and raises `SnapshotError` on Kraken's in-body `error` array; `assetpairs.py` derives per-symbol margin/leverage/order-minimum and resolves symbol aliases; `register.py` builds a content-hashed snapshot and renders the register markdown; `errors.py`. No API key, no third-party HTTP client.
- **Committed the live register** `docs/research/01.1.kraken-snapshot-register.md` (added to the mdformat allowlist): the candidate basket's ground-truth margin/leverage table — all 12 §3 symbols online & margin-enabled (EUR majors 2–10×, DOT 2–5×, ETH/BTC 2–5×, SOL/BTC 2–4×) — the Kraken symbol-alias ledger (XBT=BTC, XDG=DOGE), order minimums, and provenance (endpoint + UTC + raw-snapshot sha256). This is the Phase-1 universe-selection ground truth §3 requires. The raw snapshot JSON lands under `data/snapshots/` (gitignored); the doc records its hash.
- **11 unit tests** on saved trimmed fixtures with monkeypatched `urlopen` (no live-network tests): error-array raise, symbol resolution + alias, non-margin/absent flagging, deterministic sha256.
- **Deferred / parked:** live fee-tier, the July-9 AoP rule, and rollover bands remain account-gated (open-topic **T0000**); the L2 capture daemon is Phase 1. **Known minor:** `fetch_public` on a malformed-but-`error`-free response (missing `result` — not a shape Kraken's API actually returns) raises `KeyError` rather than `SnapshotError`; a defensive guard is left as future hardening.
- Independent whole-branch review: approved, zero defects — the reviewer independently recomputed the register's raw-snapshot hash from disk and confirmed the fixtures are genuine trimmed live samples.

## 2026-07-07 — iter-003: NautilusTrader Kraken adapter smoke test (Phase 0 · P0-3)

- **Verified the NautilusTrader Kraken adapter's public data path** — the autonomous, no-trade-key half of the master-plan §9 Phase-0 adapter verification (the Phase-6 execution-engine adoption criterion). Run in a **throwaway venv**; `nautilus_trader` is **not** added to project deps (that is a Phase-6 step). `nautilus_trader==1.230.0` installs cleanly on Python 3.14.6 (cp314 wheel); connected to Kraken's real public Spot WS (`wss://ws.kraken.com/v2`, **no API key**), loaded 1829 instruments, streamed 152 QuoteTicks / 12 TradeTicks / 12 Bars for BTC/USD over a hard-bounded 45s, clean SIGINT shutdown, zero errors.
- **Memo:** `docs/research/01.2.nautilus-kraken-adapter-memo.md` (added to the mdformat allowlist) — the data-client API surface, the confirmed keyless public-data config, two documented rough edges (`InstrumentProviderConfig(load_ids=[...])` crashes the factory's `lru_cache` → use `load_all=True`; `node.run()` sync vs `run_async()` event-loop constraint), and a measured verdict (data path viable; caveats: short single-pair Spot-only run — no L3/Futures/reconnect/soak).
- **Parked (Phase 6 / T0000):** the execution side — spot-margin/leverage/short/post-only order semantics + reconciliation — needs a trade key.
- **This completes Phase 0's autonomous work** (trial registry, snapshot register, adapter memo). The remaining Phase-0 exit-bar items (ratifications already dated 2026-07-06; the D3(i) account actions) are human-gated in T0000. The loop advances to **Phase 1 (Data Foundation)** next.
