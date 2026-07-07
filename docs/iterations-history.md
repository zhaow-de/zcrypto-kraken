# Iterations history

Per-iteration changelog of the zcrypto project. New entries are appended at the bottom by Claude Code as the final task of each iteration's implementation plan; each entry is a `## <YYYY-MM-DD> — <heading>` section with a bullet list (one bullet per feature/change/fix). CLAUDE.md's "Project state notes" section points here.

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
- **Committed the live register** `docs/research/01.kraken-snapshot-register.md` (added to the mdformat allowlist): the candidate basket's ground-truth margin/leverage table — all 12 §3 symbols online & margin-enabled (EUR majors 2–10×, DOT 2–5×, ETH/BTC 2–5×, SOL/BTC 2–4×) — the Kraken symbol-alias ledger (XBT=BTC, XDG=DOGE), order minimums, and provenance (endpoint + UTC + raw-snapshot sha256). This is the Phase-1 universe-selection ground truth §3 requires. The raw snapshot JSON lands under `data/snapshots/` (gitignored); the doc records its hash.
- **11 unit tests** on saved trimmed fixtures with monkeypatched `urlopen` (no live-network tests): error-array raise, symbol resolution + alias, non-margin/absent flagging, deterministic sha256.
- **Deferred / parked:** live fee-tier, the July-9 AoP rule, and rollover bands remain account-gated (open-topic **T0000**); the L2 capture daemon is Phase 1. **Known minor:** `fetch_public` on a malformed-but-`error`-free response (missing `result` — not a shape Kraken's API actually returns) raises `KeyError` rather than `SnapshotError`; a defensive guard is left as future hardening.
- Independent whole-branch review: approved, zero defects — the reviewer independently recomputed the register's raw-snapshot hash from disk and confirmed the fixtures are genuine trimmed live samples.
