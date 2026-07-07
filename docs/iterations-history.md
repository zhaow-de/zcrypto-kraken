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
