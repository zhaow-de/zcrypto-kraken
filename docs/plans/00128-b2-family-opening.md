# B2 family opening — the funding-extreme de-risk overlay, its subject and trial 1

**Spec:** `docs/specs/00128-b2-family-opening-design.md` — binding; every constant, window and matrix row below is the spec's, repeated here only where a task needs the value in front of it. **Iteration:** iter-175. **Topic:** T0023 under T0016. **Branch:** `research/00128-b2-family-opening`, worktree `.claude/worktrees/b2-opening`.

**Goal:** the emission and overlay module `cli/alpha/b2.py`, the committed research subject `b2-funding-derisk`, and trial 1 registered through `zcrypto research eval` on the owner's word, with its verdict in the registry and the decisions log and T0023 and T0016 updated.

**Architecture:** one module mirrors `cli/alpha/b1.py`'s shape (a frozen config, pure functions over lists, engagement helpers); the subject in `cli/research/subjects.py` composes the existing readers (`_capturing_union` for the 4h closes, `ObservedReader.read_series` for the funding parquet), the three adopted A2 arms, the overlay, the frozen benchmark recipe, `a1_kill_bar` and `net_of_cost_verdict`, and returns the metrics block the command registers. No change to `cli/alpha/a2.py`, `cli/portfolio/*`, `cli/features/derivatives.py` or any adopted artifact.

**Tech stack:** Python 3.14, polars for the parquet reads, `cli.alpha.a2` (`A2Config`, `a2_book_returns`), `cli.alpha.killbar` (`a1_kill_bar`, `net_of_cost_verdict`), `cli.features.derivatives` (`align_asof`, `funding_zscore`, `coverage_by_year`), `cli.derivatives.funding` (`PERP_SYMBOLS`, the parquet's schema), `cli.registry` (`ObservedReader`, `TrialRegistry`), `cli.research` (`Subject`, `_capturing_union`, the `eval` command).

## Global constraints

- TDD per task: the failing test first, the implementation second, the test green third; every mutation probe through `infra/scripts/mutate-probe.sh`, its verdict line in the commit message or the PR body naming the script.
- No conditional return of arm B is computed, printed or read before Task 4 runs the trial on the owner's word; Tasks 1–3 test on synthetic series and on engagement counts alone.
- The two stamp rulings (spec D2) live in `cli/alpha/b2.py` and nowhere else; `cli/features/derivatives.py` is not edited.
- Every data-gated test gates on `substrate_root` / `nothing_found_under` (the six forms `tests/test_live_venue_opt_in.py` admits); the data-gated family runs locally before the first push (`uv run pytest -m data` over the files this branch touches), the skip count read.
- Commits by kind: `feat(alpha)` for the module, `feat(research)` for the subject, `test` where a task is tests alone, `docs` for the records; each task its own commit; no amend.
- Reads: the trio over the branch; the final PR read on Opus with the Fable line unless the owner names a difficulty; the trial's registration commit (the registry append, the decisions-log entry) is a records commit and takes a `pre-review` over itself.

## Task 1 — the emission: `funding_grid_feature`

**Files:** `cli/alpha/b2.py` (new), `tests/test_alpha_b2.py` (new).

1. `B2Config` frozen dataclass: `z_threshold: float = 2.0`, `derisk_scale: float = 0.5`, `z_window: int = 90`, `stamp_tolerance_s: int = 60`; construction refuses a non-positive threshold, a scale outside (0, 1], a window below 2, a tolerance outside [0, 3600).
2. `funding_grid_feature(prints_ts: list[datetime], prints_rate: list[float | None], prints_interval_hours: list[int], close_ts: list[datetime], *, config: B2Config) -> list[float | None]`:
   - refuses unsorted or tz-naive stamps, and any print more than `stamp_tolerance_s` past its hour (`AlphaError` naming the print);
   - normalises each stamp to its hour (`replace(minute=0, second=0, microsecond=0)`);
   - maps a print whose `interval_hours` ≠ 8 to `None` before the z-score;
   - `funding_zscore(rates, window=config.z_window)` then `align_asof(normalised_ts, z, close_ts)`; returns `len(close_ts)` values.
3. Tests (known answers, synthetic series): a print 30 ms past the hour and one on the hour align identically; a print 61 s past the hour is refused by name; an off-cadence print yields `None` at its index and the z-score window skips it as `funding_zscore` does; the truncating-prefix property (the feature over `close_ts[:n]` equals the first `n` of the feature over `close_ts`); a planted two-sigma print lifts the feature from its settlement hour's boundary until the next print's.
4. Probe: the normalisation removed (mutation) against the 30 ms/on-the-hour test — expect KILLED; the tolerance check removed against the 61 s test — expect KILLED.

**Commit:** `feat(alpha): the B2 emission — funding prints to the 4h close grid, stamps normalised, leak-free`.

## Task 2 — the overlay: `derisk_scales`, `scale_positions`, the engagement helpers

**Files:** `cli/alpha/b2.py`, `tests/test_alpha_b2.py`.

1. `derisk_scales(z_by_asset: dict[str, list[float | None]], *, config: B2Config) -> dict[str, list[float]]`: `config.derisk_scale` where `z > config.z_threshold`, else `1.0`; `None` → `1.0`; every list the same length or refused.
2. `scale_positions(asset_positions: dict[str, list[float]], scales: dict[str, list[float]]) -> dict[str, list[float]]`: elementwise product; the key sets must match; lengths must match.
3. `per_year_engaged_counts(scales, close_ts) -> dict[int, int]` (scaled stamps per year, keyed by the close stamp's year); `stamps_positions_differ(a, b) -> int`; `book_turnover` imported from `cli.alpha.b1`.
4. Tests: a planted threshold crossing scales exactly those stamps; `None` leaves 1.0; mismatched keys refused; the engagement count per year on a two-year synthetic series; the turnover of a scaled book exceeds the unscaled one by exactly the scaling trades on a hand-computed case.
5. Probe: the `None → 1.0` arm mutated to `0.0` against the None test — expect KILLED; the threshold comparison flipped to `>=` against the planted-crossing test with a value exactly at the threshold — expect KILLED.

**Commit:** `feat(alpha): the B2 overlay — a fixed half-scale while the funding z-score exceeds its threshold`.

## Task 3 — the research subject `b2-funding-derisk`

**Files:** `cli/research/subjects.py`, `tests/test_research_subjects.py` (or the existing subject test file), `tests/test_alpha_b2.py` for the data-gated engagement case.

1. `Subject("b2-funding-derisk", (240,), _ASSETS, _build_b2_funding_derisk)` registered beside the two existing subjects; `required_relpaths` extended so the funding parquets (`<PERP>/funding.parquet` under `derivatives-funding`) are named for the datasets block.
2. `_build_b2_funding_derisk(reader, dataset, window, as_of, accept_holes) -> dict`:
   - the 4h union through `_capturing_union(reader, dataset, 240, window, as_of, accept_holes)`;
   - per asset, the funding prints through `reader.read_series("derivatives-funding", f"{PERP_SYMBOLS[asset]}/funding.parquet")` (the reader vouches the set's attestation), then `funding_grid_feature` on `close_ts = [t + 4h for t in h4_ts[:-1]]`;
   - arm A: the three adopted arms (the constants of `crossfreq_system.py`: lookbacks (20, 50, 100) at 0.12, (60, 120, 240) at 0.10 and 0.12, short off, vol and basket lookback 180, 2,190 periods a year), the equal-weight per-asset mean of their `asset_positions`; arm B through `derisk_scales` and `scale_positions`; both costed at 0.006/side on per-asset turnover with the trials-45–46 inline convention;
   - the frozen benchmark at 4h over the same window with the `a2_4h_run.py:52-69` recipe spec 00045 cites, copied verbatim into the subject with its citation;
   - `a1_kill_bar` with the spec's constants and `decisive_start=1380`; the SPA grid blocks {30, 102} × seeds {42, 7, 1234}; `net_of_cost_verdict(B, A)` on the full window and from 2021-01-01;
   - the engagement block: per-year engaged counts, positions-differ count, turnover A and B, max drawdown A and B, `coverage_by_year` of the feature per asset;
   - the metrics dict with the spec D7 key set, bools as 0/1, keys str; the datasets block the reader records.
3. Tests: the subject is registered and names its intervals and assets; a data-gated test (gated on the rolling set and the funding set through `substrate_root`) runs the subject over a one-month window and asserts the metrics keys and the engagement block's shape, never a value of arm B's return; a unit test on a synthetic reader asserts the costing convention on a hand-computed two-asset case.
4. Probe: the as-of grid mutated from `ts + 4h` to `ts` against the subject's synthetic test with a print at the boundary hour — expect KILLED.

**Commit:** `feat(research): the b2-funding-derisk subject — arms, benchmark, bar and verdicts through the reader`.

## Task 4 — trial 1, on the owner's word

**Files:** `docs/reference/trial-registry.jsonl`, `docs/research/14.phase6-decisions.md` (or the research decisions log the family's records use — the one `[iter-175]` lands in is the one T0022's records used, `docs/research/10.phase4-decisions.md`), `docs/open-topics/T0023-…`, `docs/open-topics/T0016-…`.

1. Pre-flight, read-only: `uv run zcrypto research eval --subject b2-funding-derisk --dataset ohlc-rolling --as-of 2026-10-10 --window "2020-09-22 00:00:00+00:00" "2026-06-30 23:59:59+00:00" --accept-holes` prints the engagement block first; the orchestrator reads the engagement proof (spec D6: zero engaged stamps in every year is an instrument finding and stops here) and the coverage block, and hands the owner the line to run with `--register --iteration iter-175 --family B2 --spec-hash <sha256 of the spec> --n-trials 1 --variant B2-funding-derisk-a2eq-v1 --verdict <per the matrix> --notes "<the recipe and the DSR note>"`.
2. The owner's word runs the registration; the verdict is the matrix's row, no interpretation; the record's `datasets` block is read back and the `dataset_hash` recipe checked by hand (`sha256(hex_rolling_line + ":" + hex_funding)`).
3. The decisions-log entry `[iter-175] B2 trial 1 — the funding-extreme de-risk on the adopted A2-4h ensemble (Decision: <row>)` in the family's log, with the numbered options as the matrix rows; T0023's `## Done so far` takes the emission and the subject, its next steps the OI and liquidation legs; T0016's B2 line records the opening and the budget (22 remain).
4. The registration commit takes its own `pre-review`.

**Commit:** `docs(research): B2 trial 1 registered — <verdict>`.

## Task 5 — closeout

1. The change-index row at PR-open (`iter-175` in the title); the PR `feat(alpha): iter-175 — B2 family opening, the funding-extreme de-risk overlay` with the trial's verdict in the body; the trio's reads; merge on the owner's word.
2. The memo's T0023 item condensed to the family's state and its next trial; the handoff line.
