# soak-check realized governor/cap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote governor-engagement and cap-breach from null-side context to real realized-vs-backtest gating comparisons, taking the soak-check fingerprint from 5 to 7 gating metrics (spec `00059`, [[T0072]]).

**Architecture:** One extra `build_crossfreq_system_fast` rebuild on the **latest journal record's snapshots** yields `multipliers` / `sleeve_positions` for every bar in the journal span; a timestamp-keyed lookup maps each scored cycle to its row. All new code lands in `cli/engine/soak.py`; the command surface is unchanged.

**Tech Stack:** Python 3.14, numpy, polars (via existing readers), Typer + `CliRunner`, pytest.

## Global Constraints

- **THE KEYSTONE (spec D1/D2):** the row for a decision at cycle `T` is the index `k` where `h4_ts[k] == T − 4h`. Resolve **by timestamp**, never positionally. At that `k`, the rebuild's `final_targets[a][k]` **must equal** the journaled `final_targets[a]` of cycle `T` to `1e-6` for **every** scored cycle and asset — window-wide identity. Failure ⇒ VOID. A missing `T−4h` in the grid ⇒ `SoakError`, never a silent skip.
- **Cap-breach predicate (D3):** `breach[k] = any(|capped[a][k] − combined[a][k]| > 1e-15)` where `combined = ⅓(B+A1+A2)` from `sleeve_positions` and `capped = apply_position_caps(combined)` — identical to `crossfreq_system.py:636`. Summing over completed bars must equal the builder's `cap_breach_bars` ⇒ else VOID.
- **Governor granularity (D4):** a realized **day** is engaged iff any of its scored bars has `mult < 1.0`; rate = engaged days / scored days.
- **Null windows in the metric's own unit (D5):** cap-breach → `L` bars; governor → the realized **day count**. `effective_n = len(null_series)/window`.
- **Multiplicity (D6):** `summarize_panel`'s `n_metrics` counts only metrics whose verdict is **not** `"n/a"`.
- **Degrade, don't void (D7):** if the rebuild cannot run (snapshots absent/corrupt → `EngineError`), the two metrics are `"n/a"` with a reason and the other 5 still gate. A rebuild that *runs but disagrees* (D2/D3) VOIDs.
- Vocabulary lock (no validated/passed/confirmed/proven in rendered text), banner every run, no holdout access — all unchanged from `00058`.

## File Structure

- `cli/engine/soak.py` (modify) — `RealizedInternals` + `realized_internals` (Task 1), `NullSystem.cap_breach` (Task 2), `analyze_soak` (Task 3), render/JSON/`soak_report` (Task 4).
- `tests/test_engine_soak.py` (modify) — Tasks 1–3 tests.
- `tests/test_engine_soak_command.py` (modify) — Task 4 command/render tests.
- `README.md` (modify) — only if the option surface changes (it should not).

---

## Task 1: `realized_internals` — the timestamp-keyed rebuild + keystone identity

**Files:** modify `cli/engine/soak.py`, `tests/test_engine_soak.py`.

**Interfaces:**
```python
@dataclass(frozen=True)
class RealizedInternals:
    available: bool                     # False when the rebuild could not run (D7 degrade)
    reason: str                         # why unavailable (empty when available)
    mult_by_cycle: dict[datetime, float]      # scored cycle_ts -> multiplier at its row
    breach_by_cycle: dict[datetime, bool]     # scored cycle_ts -> cap-breach flag at its row
    identity_ok: bool                   # D2 window-wide identity
    identity_detail: str
    cap_consistent: bool                # D3 sum(breach) == result.cap_breach_bars
    cap_detail: str

def realized_internals(scored_records: list[CycleRecord], latest_record: CycleRecord,
                       snapshot_reader, *, tol: float = 1e-6) -> RealizedInternals: ...
```

Implementation notes:
- Assemble the latest record's grids exactly as `cli/engine/concordance.py:replay_cycle` does (hash-verify each `SnapshotEntry` via `snapshot_content_hash`, group by grid, assert one shared calendar per grid). Factor the assembly if convenient, but **do not change `replay_cycle`'s behavior**.
- `result = build_crossfreq_system_fast(daily_prices, daily_ts, h4_prices, h4_ts)`.
- `idx = {ts: k for k, ts in enumerate(h4_ts)}`.
- For each scored record with `cycle_ts = T`: `k = idx.get(T - timedelta(hours=4))`; `None` ⇒ raise `SoakError` naming `T`.
- `mult_by_cycle[T] = result.multipliers[k]`; `breach_by_cycle[T] = breach[k]` (per the D3 predicate over all `n_rows_h` rows).
- Identity: for each scored record, every asset `|result.final_targets[a][k] − record.final_targets[a]| <= tol`; record the worst diff in `identity_detail`.
- Cap consistency: `sum(breach[:result.n_periods]) == result.cap_breach_bars`.
- Wrap the whole rebuild in `try/except EngineError` → return `available=False, reason=str(exc)` (D7).

- [ ] **Step 1: failing tests** — in `tests/test_engine_soak.py`:
  - `test_realized_internals_identity_holds_and_shift_breaks_it`: build a synthetic journal whose snapshots the stub reader serves; assert `identity_ok is True` on correct alignment. Then **inject a ±1 index shift** into the lookup (e.g. monkeypatch the resolver, or construct records whose `cycle_ts` is off by one bar) and assert `identity_ok is False`. *The shifted case MUST fail the identity — a guard that cannot bite is not a guard.*
  - `test_realized_internals_missing_stamp_raises`: a scored cycle whose `T−4h` is absent from the grid ⇒ `pytest.raises(SoakError)`.
  - `test_realized_internals_cap_breach_matches_builder`: `cap_consistent is True`; and a case where `combined` exceeds the cap so `breach` is 1 on a bar where the traded `final_targets` alone would read 0 (proves the metric measures what the weights cannot).
  - `test_realized_internals_unavailable_degrades`: a reader that raises `EngineJournalError` ⇒ `available is False`, non-empty `reason`, no exception escapes.
- [ ] **Step 2:** run `uv run pytest tests/test_engine_soak.py -v` → new tests fail.
- [ ] **Step 3:** implement `RealizedInternals` + `realized_internals`.
- [ ] **Step 4:** re-run → all pass.
- [ ] **Step 5:** `uv run pre-commit run -a`; re-stage rewrites; commit `feat(cli): soak-check realized internals (ts-keyed governor/cap rebuild)`.

---

## Task 2: per-bar cap-breach on the null

**Files:** modify `cli/engine/soak.py`, `tests/test_engine_soak.py`.

`_net_live_from_result` already builds `combined` and `capped`. Return the per-bar breach series from it (or compute it in `build_null` from the same reconstruction) and add to `NullSystem`:
```python
    cap_breach: list[float]   # n_periods, 1.0 on a bar where the pre-cap book was clipped
```
`build_null` populates it; the existing scalar `cap_breach_bars` is **retained** and used as the cross-check.

- [ ] **Step 1: failing tests** — `test_null_cap_breach_series_sums_to_cap_breach_bars` (synthetic `_fake_result` with a known number of breaching bars); extend the data-gated `test_build_null_on_real_canonical` to assert `len(ns.cap_breach) == ns.n_periods` and `sum(ns.cap_breach) == ns.cap_breach_bars`.
- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5:** gate + commit `feat(cli): soak-check null per-bar cap-breach series`.

---

## Task 3: `analyze_soak` — 7 gating metrics, discriminating-only multiplicity, redundancy note

**Files:** modify `cli/engine/soak.py`, `tests/test_engine_soak.py`.

- `analyze_soak(realized, null, *, band=0.90, internals: RealizedInternals | None = None) -> SoakAnalysis`.
- When `internals` is available:
  - **governor_engagement**: group scored `cycle_ts` by UTC date; day engaged iff any bar `mult < 1.0`; `live = engaged_days/total_days`. Null series = `governor_engaged_daily(null.multipliers, null.day_index)`; `window = total_days`.
  - **cap_breach**: `live = mean(breach over scored cycles)`. Null series = `null.cap_breach`; `window = L`.
  - Both judged with `metric_verdict(live, windowed_null(series, window), band=band, effective_n=len(series)/window)`.
- When `internals` is `None`/unavailable: both verdicts are `"n/a"` with the reason carried into `SoakAnalysis` (new field `internals_reason: str`).
- `summarize_panel`: `n_metrics` counts verdicts != `"n/a"`; `expected_by_chance = n_metrics × (1 − band)`.
- New `SoakAnalysis` fields: `internals_available: bool`, `internals_reason: str`, `redundant_pairs: tuple[str, ...]` (e.g. `("gross~net",)` when the realized `gross`/`net` series correlate ≥0.99 or the book has no short exposure).

- [ ] **Step 1: failing tests** — planted-consistent and planted-inconsistent for `governor_engagement` and `cap_breach` (jittered non-degenerate nulls, assert `== "consistent"` / `== "inconsistent"`); `test_summarize_panel_excludes_na` (7 verdicts with 2 `"n/a"` ⇒ `n_metrics == 5`, `expected_by_chance == 5×0.10`); `test_governor_day_aggregation` (one sub-1.0 bar engages its whole day); `test_analyze_soak_degrades_without_internals` (both `"n/a"`, other 5 still gate); `test_redundancy_note_on_long_only` (identical gross/net ⇒ `redundant_pairs` non-empty; genuine shorts ⇒ empty).
- [ ] **Step 2–4:** fail → implement → pass.
- [ ] **Step 5:** gate + commit `feat(cli): soak-check gates governor-engagement and cap-breach`.

---

## Task 4: report + JSON + `soak_report` wiring

**Files:** modify `cli/engine/soak.py`, `tests/test_engine_soak_command.py` (+ `tests/test_engine_soak.py` for render units).

- `soak_report` builds `internals` (latest record + scored records + `_snapshot_reader`) and passes it to `analyze_soak`; a D2/D3 disagreement adds a void reason (`"realized-internals identity mismatch"` / `"cap-breach inconsistent"`).
- `render_report`: delete the "GOVERNOR / CAP CONTEXT — backtest context (not a realized comparison)" block; the fingerprint table now prints 7 rows; append the governor day-granularity caveat (`n days`) and the redundancy note when `redundant_pairs` is non-empty; when internals are unavailable print the two rows as `n/a` with the reason.
- `_json_payload`: carry `governor_engagement`/`cap_breach` verdicts, `internals_available`, `internals_reason`, `identity_ok`, `cap_consistent`, `redundant_pairs`.

- [ ] **Step 1: failing tests** — render shows 7 metric rows and no "backtest context" phrase; vocabulary lock + banner still hold; unavailable-internals render shows `n/a` + reason and keeps 5 gating rows; JSON carries the new keys.
- [ ] **Step 2–4:** fail → implement → pass. Also run `uv run pytest tests/test_cli_help_hygiene.py -q`.
- [ ] **Step 5:** gate + commit `feat(cli): soak-check report + json for the 7-metric fingerprint`.

---

## Task 5 (orchestrator, not a subagent): real-data verification + closeout

- [ ] Run `uv run zcrypto engine soak-check --journal-dir /mnt/zhao-crypto/engine-journal --json <scratch>` and confirm: all **7** metrics populate, `identity_ok` true across all scored cycles, `cap_consistent` true, `void_reasons` empty, banner + vocabulary lock intact.
- [ ] Compare against the pre-change baseline (`soak-ops-baseline.json`) — the 5 original metrics must be **unchanged** (this change must not perturb them).
- [ ] Final whole-branch review; fix wave if needed.
- [ ] Closeout: iter-108 entry in `docs/iterations-history-phase6.md`; flip [[T0072]] → `resolved` + archive + index sync; decisions-log entry; PR into `develop`; merge via `merge-pr` when green.

## Self-Review

- Spec coverage: D1/D2→Task 1; D3→Tasks 1–2; D4→Task 3; D5→Tasks 2–3; D6/D6a→Task 3; D7→Tasks 1,3,4. Test list 1–2→Task 1; 3–4→Tasks 1–2; 5–6→Task 3; 7/7a→Task 3; 8→Tasks 1,3,4; 9→Task 5; 10→Task 4.
- Type consistency: `RealizedInternals` is keyed by `datetime` (scored `cycle_ts`) throughout; `NullSystem.cap_breach` is `list[float]` of length `n_periods`, matching the other null series.
- Grounded APIs: `build_crossfreq_system_fast`, `apply_position_caps`, `governor_engaged_daily`, `windowed_null`, `metric_verdict`, `summarize_panel`, `snapshot_content_hash`, `_snapshot_reader`, `_journal_artifacts` — all verified present.
