# B2 trials 3–5 — the three overlays on frozen ohlc-full, the daily liquidation backfill, the two frozen liquidation blocks, the tape's reading, the gated runs and the verdicts — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Execution is subagent-driven — the owner's "one SDD loop". Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/alpha/b2.py tests/test_alpha_b2.py cli/liquidations/coinalyze.py cli/__main__.py tests/test_liquidations_coinalyze.py cli/research/subjects.py tests/test_research_command.py tests/test_research_b2_overlays_basis.py README.md tests/slow-cases.txt docs/reference/vouched-dataset-hashes.jsonl docs/reference/data-catalog-full.md zcrypto.toml docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl tests/test_trial_registry_provenance.py tests/retired_subjects.py docs/specs/00138-b2-three-overlays-design.md` prints `tier: full`, for `tests/test_alpha_b2.py` "a test importing cli.alpha.b1", `cli/__main__.py` "under cli/__main__.py", `tests/test_liquidations_coinalyze.py` "a test importing cli.capture", `tests/test_research_command.py` "a test importing cli.alpha", `zcrypto.toml` "under zcrypto.toml", `docs/reference/trial-registry.jsonl` and `tests/test_trial_registry_provenance.py`; `tests/test_research_b2_overlays_basis.py` is read once Task 5 creates it).

**Goal:** B2's trials 3, 4 and 5 (spec 00138) — five emitters in `cli/alpha/b2.py`; the daily liquidation backfill command in `cli/liquidations/coinalyze.py`; the frozen daily block and the frozen block of the live tape, their attestations, the tape's coverage proof and their one push to the hub; the completed basis; seven research subjects in `cli/research/subjects.py` — three trials, their evaluate-only pre-flight twins and the tape's reading; the data-gated test of the trials' inputs half; the three trials run in order through spec 00133's trial-attempts log and the reading run after them — each verdict, stop or reading in the registry or the ledger and the decisions log, then T0023, T0016 and the owner's pick recorded.

**Architecture:** no new module. `cli/alpha/b2.py` gains `ratio_zscore_grid_features`, `ratio_max_signal`, `daily_zscore_grid_feature`, `liquidation_hourly_totals` and `event_contrast`. `cli/liquidations/coinalyze.py` gains `backfill_daily` and the command `liquidations_backfill`, and `fetch_liquidation_history` the keyword `interval`, default `"1min"`, so the poller, which passes none, sends what it sent. `cli/research/subjects.py` gains one overlay machinery — `_B2OverlayInputs`, `_b2_overlay_inputs` (the union, arm A by `_b2_inputs`' expression, the signal, the threshold — a constant, or `_b2_engagement_threshold` called on the signal and arm A — and the scales), `_b2_overlay_metrics` (`_b2_full_metrics`' body with the signal's own start in `k21`'s place) and `_b2_overlay_preflight_metrics` — three signal readers, six thin `_build_` wrappers, and the reading's `_build_b2_liq_tape_reading` over `_b2_tape_reads` and `_b2_tape_forwards`. The freeze is two controller programs and the daily fetch one command the controller runs; nothing else writes a block.

**Tech Stack:** Python 3.14 through uv; polars; numpy; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00138-b2-three-overlays-design.md` — binding; D1–D12 are cited by name and the values below are copied from it. It copies spec 00137's instrument, bar, arms and costing and spec 00128's matrix, both frozen (record 51's and reading 1's `spec_hash`). **Iteration:** iter-182. **Topic:** T0023 under T0016. **Branch:** `research/iter-182-b2-three-overlays`, worktree `.claude/worktrees/iter182`, `data/ohlc-full`, `data/derivatives-funding` and `data/derivatives-oi` linked read-only from the main checkout; Task 3 links `data/liquidations-frozen` and `data/liquidations-daily`, Task 10 `data/ohlc-rolling`. A choice this plan makes that the spec leaves open is marked **Author's call**. Every code fence below was extracted from this file and run against the tree in task order in a detached scratch worktree before this plan was committed — the commands against their `Expected`, each `-k` filter's collect count, each probe row's two seds matching exactly one line of the code the fences write and each probe run to its verdict, one hundred nineteen of one hundred nineteen `KILLED`; Task 3's two freeze programs ran against the live tree read-only with their writes redirected into scratch, the second 603 s after the first and finding the closed span unchanged, the first run again with its asserted-hours line as it stands, its backfill, daily attestation and daily-basis program ran over a synthetic response through an injected opener, written into scratch — the program over the frozen union's arm A positions and that synthetic block, no bar — the network and the vault untouched; Task 6 step 1a's hub read ran over the sets already on `hot/`, `ohlc-full`, `derivatives-oi` and the rolling set's line for 2026-10-10, each `rederived`; the three check programs printed over synthetic inputs. Not run: the daily fetch itself (Task 3 step 5, the controller's), the hub push's dry inspection and push (Task 6 step 1a, the controller's), any `zcrypto research eval` (Tasks 7–10), the data-gated test and its probes beyond `--collect-only` (Task 5 steps 2 and 4) but the arm A case's probe row, run to `KILLED` with the frozen union and the OI set linked, the check programs beyond a parse and a synthetic print (Task 6 step 5), the replays and the literal probes beyond their seds (Tasks 7–10), the topic edits (Task 11 steps 1–3) and the PR (Task 12).

## Global Constraints

- **The signals and thresholds** (D3–D6): OI — `oi_zscore_grid_feature(rows["ts"], rows["sum_open_interest"], h4_ts)` per asset over `derivatives-oi/<PERP>/oi.parquet` read whole, key `binperp_oi_z30d`, threshold `_B2_OI_THRESHOLD = 2.5`; ratios — `ratio_max_signal(ratio_zscore_grid_features(rows["ts"], {the four columns}, h4_ts))` over the same files, key `binperp_ratio_max_z30d`, `_B2_RATIO_THRESHOLD = 2.5`; liquidations — `daily_zscore_grid_feature(rows["ts"], rows["long_usd"], h4_ts)` per coin over `liquidations-daily/<COIN>/daily.parquet`, key `binperp_liq_long_z30d`, threshold `_b2_engagement_threshold(signal, arm_a)`: of 2.0 and 2.5 the one whose share of arm A's long asset-stamps where the signal is defined lies nearer `_B2_TRIAL_2_ENGAGED_SHARE = 3_486 / 70_682`, 2.5 on a tie or where no long stamp holds the signal; every scale `derisk_scales(signal, config=B2Config(z_threshold=<threshold>))`, arm B `scale_positions(arm_a, scales)`.
- **The reading** (D12): `b2-liq-tape-reading` over `--dataset ohlc-rolling --as-of 2026-10-10 --window "2026-07-14 11:00:00+00:00" "2026-10-10 23:59:59+00:00"`, the hourly and 15-minute unions; per coin `liquidation_hourly_totals` over `liquidations-frozen/<COIN>/buckets.parquet` with `covered` from `liquidations-frozen/covered-hours.parquet`, its `funding_zscore(totals, window=720)` above 2.0 an event; `_b2_tape_forwards` at 1, 4 and 24 hours from the hour's close; `event_contrast(flags, forwards, mean_block=24, n_resamples=2000, seed=42)`; 12 keys; no rule, family or count.
- **The bars** (D2, D8): every `a1_kill_bar` call `n_trials=<the subject's count>, var_trials=0.0, mean_block=<30 or 102>, seed=<42, 7 or 1234>, cost_stressed_returns=<×1.5 series>, regime_slices=calendar_year_slices(<series>, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000`, the headline (30, 42); arm A's bar the same call at (30, 42) on `net_a`; the head-to-heads `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)` for `("full", 0)` and `("primary", start)`, `start` `_b2_overlay_start(inputs)`, the first return index every asset's signal holds; the drawdown pair from `start`; refused before any bar: fewer than 2 return indices from `start`, or arm A never drawing down from it.
- **The counts** (D8): `_B2_OI_N_TRIALS = 2`, `_B2_RATIO_N_TRIALS = 3`, `_B2_LIQ_N_TRIALS = 4`, fixed by the spec's hash; at `var_trials` 0.0 none moves a figure of the bar.
- **The rule** (D8): `_b2_overlay_verdict` — `None` when `arm_a_passes` is 0 or no year holds an engaged stamp, `reject` on a failed bar, `adopt` on `head_to_head_mean_outperf_primary > 0`, `max_drawdown_reduction_pct > 1e-6` and `head_to_head_spa_p_primary < 0.05`, `park` on the first two with the p at or above 0.05, `reject` otherwise.
- **The records** (D9): family `B2`; `n_trials_in_family` the count; variants `B2-oi-derisk-a2eq-full-v1`, `B2-ratio-derisk-a2eq-full-v1`, `B2-liq-derisk-a2eq-full-v1`; iteration `iter-182`; seeds (42, 7, 1234); 42 metric keys, `threshold` among them; the OI and ratio records' `dataset_hash` `69d7e9d6b531de063810c35b9a75c6538948f4e526ad2769ad0f961a03f078cf`, the liquidations record's block `ohlc-full`'s ten files beside `liquidations-daily`'s ten; no `--verdict`.
- **The pre-flight read** (D10), in this order: (a) the block; (b) arm A's seven anchors at record 45's precision — `arm_a_ann_sharpe_noc` 1.405, `arm_a_ann_sharpe_noc_decisive` 1.3716, `arm_a_max_drawdown_full` 0.2154, `arm_a_spot_drag_pct_yr` 0.0703, the benchmark's 1.2128 and 1.2447 at four decimals, `turnover_a` 146.19 at two; (c) `engaged_per_asset`, `engaged_per_year`, the signal's coverage, `primary_returns` and `threshold` the measured basis's — for liquidations the completed basis's `DAILY_BASIS` line; (d) the engaged total above 0; (e) arm A's `passes` 1.
- **The hash rule** (D10): before Task 6 step 2 takes the spec's sha256, nobody computes arm A's bar or any position or return of arm B over the trials' data, nor runs `b2-liq-tape-reading` over the real sets; the data-gated test (Task 5) and Task 3's daily-basis program compute arm A's positions, the signals and the engagement — the basis's own measures — and no bar; no reader, reviewer or plan-review dispatch runs any of the seven subjects over the real sets before the hash, and every read's dispatch carries this rule. No return of arm B is computed over the trial's data before that trial's `--register` run, and no trial subject is ever run as a plain eval.
- **Unchanged** (D9): every existing function of `cli/alpha/b2.py`, `cli/research/subjects.py`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/engine/*` and `cli/liquidations/*` but `fetch_liquidation_history`, whose signature gains `interval` and whose URL reads it; the poller's behaviour; the subjects of trials 1 and 2; any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-only $(git merge-base HEAD origin/develop) -- cli/` prints `cli/alpha/b2.py` from Task 1 on, `cli/__main__.py` and `cli/liquidations/coinalyze.py` from Task 2 on and `cli/research/subjects.py` from Task 4 on, nothing else; `git diff -U0 $(git merge-base HEAD origin/develop) -- cli/ | grep '^-[^-]'` prints only the lines the tasks replace — from Task 1 `-from cli.validation import max_drawdown`; from Task 2 also `-from cli.liquidations.coinalyze import liquidations_poll`, `-def fetch_liquidation_history(api_key: str, symbols: list[str], frm: int, to: int, *, opener=urllib.request.urlopen) -> list[dict]:` and `-    url = f"{_BASE_URL}?symbols={symbols_csv}&interval=1min&from={frm}&to={to}&convert_to_usd=true"`; from Task 4 also `-from datetime import UTC, datetime` and `-from cli.features.derivatives import coverage_by_year` — 1, 4 and 6 lines. Measured on the transcription, the hunks: `cli/alpha/b2.py`'s `@@ -9,0 +10,2 @@`, `@@ -23 +25 @@`, `@@ -37,0 +40,3 @@`, `@@ -38,0 +44 @@` and `@@ -293,0 +300,126 @@`; `cli/liquidations/coinalyze.py`'s `@@ -113 +113,3 @@`, `@@ -119 +121 @@` and `@@ -361,0 +364,74 @@`; `cli/__main__.py`'s `@@ -12 +12 @@` and `@@ -27,0 +28 @@`; `cli/research/subjects.py`'s `@@ -8,0 +9 @@`, `@@ -12 +13 @@`, `@@ -56,0 +58 @@`, `@@ -57,0 +60 @@`, `@@ -58,0 +62 @@`, `@@ -59,0 +64 @@`, `@@ -63,0 +69,2 @@`, `@@ -71 +78 @@`, `@@ -1992,0 +2000,570 @@` and `@@ -2161,0 +2739,84 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00138-b2-three-overlays-design.md` after Task 6 step 2, nor specs 00128 and 00137, nor the spec before then except Task 3's completed basis and a fix commit a read of Task 5 step 7 asks for; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Tasks 7–10 name it. Never `git stash`; no amend; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-full`, `data/derivatives-oi`, from Task 3 `data/liquidations-frozen` and `data/liquidations-daily`, and from Task 10 `data/ohlc-rolling`, read-only links, never written under; `data/derivatives-funding` only where an existing test reads it and in Task 3 step 11's `_b2_inputs` call. The live tree `/var/lib/zcrypto-ops/liquidations` is read by Task 3's two freeze programs alone, read-only. The vault is read by Task 3 step 5's one command alone, the key reaching that process's environment by command substitution, never printed, never in a file, a log or a message; the network is touched by that command's one Coinalyze call and by Task 6 step 1a's dry inspection and push, each an rsync to `zcrypto.toml`'s `push_dest`; no test and no implementer touches either. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/` but Task 6 step 1a's read of its `hot/`, ssh or a fleet host but that step's rsync to the NAS's hub, docker, `kraken-cli`, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 3, Task 5 step 7's reads, Tasks 6–10 and Task 12's steps 2–4, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads), the vault (the fetch) and runs awaited in the background to a completion notification (the freeze's second read, the data tests, the pre-flights, the registers, the reading, the replays), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1, 2, 4 and 11, Task 5's steps 1–6 and Task 12's step 1.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00138 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` (or a file, or `-k`). An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file or node id into parts that cannot, each its own `--basetemp=.tmp/plan-00138/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `T=$(bash infra/scripts/consumers.sh --direct <each changed path> | sort -u)` and `[ -n "$T" ] && uv run pytest $T -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt`, never a bare `uv run pytest`; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. A commit message's test result line is a run over that commit's own tree.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
test ! -e .tmp/plan-00138/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00138/probe HEAD &&
  git -C .tmp/plan-00138/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00138/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00138/probe/.tmp
```

  Then, from `.tmp/plan-00138/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, so it fails at import or at its call. After the last verdict, `git worktree remove --force .tmp/plan-00138/probe` — a data link in it unlinked first. Every removal of a probe worktree that held a data link — Task 5 step 4's, Tasks 7–9 step 6's and each of Task 10 step 5's — is followed by `ls -la /home/zhaow/Projects/zcrypto-kraken/data`, each set it linked still listed. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.
- **Commits**: one per task that changes the tree, two for Task 3 (the blocks' attestation, catalog and `authored_sets`, then the spec's completed basis), two for Task 5 (the test, then step 6's conventions entry), one per trial for Tasks 7–9, one for Task 10, two for Task 12 (the decisions-log entry, then the change-index row); Task 6 adds none, a merge of develop aside. Each ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and `Claude-Session: <the executing session's URL>`; an implementer on another model names its own.
- **The reads**: the trio over the branch through Task 5 (`pre-review`, `review`, `re-review`, as CLAUDE.md orders them; Task 5 step 7) — the completed basis among what it reads — closes with no open Critical or Important before Task 6 step 2, and nothing the runs execute or the records pin changes from that read to the registrations unless a read of the change follows; Tasks 7–12's commits take their own `pre-review`, then the read of the delta from the tip the last read covered (Task 12 step 3) before the push that carries it; the PR is created and edited through `open-pr`, its read line naming the tip read.

## Review Focus

- The ratio signal must read the four z-scores' maximum only where all four are defined, never the maximum of those defined. Test: Task 1, `test_the_ratio_signal_is_the_columns_maximum_where_every_column_is_read`.
- A day's liquidation value must reach no close before the day has ended. Test: Task 1, `test_a_daily_zscore_reaches_a_close_only_once_its_day_has_ended`.
- A day the daily series lacks must darken every z-score window holding it, never read as a zero. Test: Task 1, `test_a_day_the_series_lacks_darkens_every_window_holding_it`.
- The reading's bounds must come from one draw of hour indices shared by every series and coin. Test: Task 1, `test_the_event_contrast_compares_the_means_after_events_and_after_the_others_with_shared_bootstrap_bounds`.
- The backfill must write nothing when the response fails any check, and never over a set; the poller's request must stay at the one-minute interval. Tests: Task 2, `test_the_daily_backfill_refuses_a_response_it_cannot_trust_and_writes_nothing`, `test_the_daily_backfill_never_writes_over_a_set`, `test_poll_cycle_requests_the_one_minute_interval`.
- An overlay trial's metrics must be trial 2's with only the start and the count moved, the threshold reaching the scales. Test: Task 4, `test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count`.
- The liquidations threshold must be the rule's pick, read off arm A's long stamps where the signal is defined. Test: Task 4, `test_the_engagement_threshold_is_the_nearer_of_2_0_and_2_5_to_trial_2s_share`.
- The reading's forwards must start at the close of the event's own hour, never at its open. Test: Task 4, `test_the_tape_forwards_read_from_the_close_its_hour_ends_on_and_merge_a_missing_quarter`.
- A twin whose signal no close carries must evaluate, never refuse, so D10's dead-knob stop is kept as a reading. Test: Task 4, `test_a_b2_overlay_preflight_whose_signal_no_close_carries_prints_its_figures_at_zero`.
- A frozen file whose content moved since it was written must be refused at the read, through the sidecar's path binding. Tests: Task 5, `test_the_daily_block_is_attested_and_its_signal_reproduces_the_completed_basis` (`checked (10 vouched hashes)`) and `test_the_tape_block_is_attested_file_by_file` (`checked (11 vouched hashes)`), `ObservedReader`'s existing path-bound check (`tests/test_data_vouched_sidecar.py::test_the_sidecar_arms_the_read_guard_and_a_tampered_frame_is_refused`) its refusal.

## File structure

- Modify `cli/alpha/b2.py` — two imports, three constants and five functions (Task 1); `tests/test_alpha_b2.py` — their tests.
- Modify `cli/liquidations/coinalyze.py` — `fetch_liquidation_history`'s `interval`, the backfill and its command; `cli/__main__.py` — the command's registration; `tests/test_liquidations_coinalyze.py`; `README.md` — the command's section (Task 2).
- Create `data/liquidations-frozen/` and `data/liquidations-daily/` in the main checkout (gitignored) and link them; modify `docs/reference/vouched-dataset-hashes.jsonl` — twenty-one lines; `docs/reference/data-catalog-full.md` — the two blocks' entries; `zcrypto.toml` — the two blocks join `authored_sets`; `docs/specs/00138-b2-three-overlays-design.md` — the completed basis (Task 3); push the two blocks to the hub's `hot/` (Task 6).
- Modify `cli/research/subjects.py` — the imports, the overlay and reading machinery before `SUBJECTS`, seven entries at its end; `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt` (Task 4).
- Create `tests/test_research_b2_overlays_basis.py` (data-gated); modify `tests/slow-cases.txt`, `docs/research/10.phase4-decisions.md` (Task 5).
- At the runs: `docs/reference/trial-registry.jsonl`, `docs/reference/reading-ledger.jsonl`, `tests/test_trial_registry_provenance.py`, `docs/research/10.phase4-decisions.md`, `tests/slow-cases.txt`, and on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md` and `docs/open-topics/README.md` (Tasks 7–10); `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/retired_subjects.py`, `tests/test_research_command.py` (Task 11); `docs/research/10.phase4-decisions.md`, `docs/reference/change-index.md` (Task 12). Scratch under `.tmp/plan-00138/`.

______________________________________________________________________

### Task 1: the five emitters — the ratio z-scores, their maximum, the daily z-score, the hourly totals and the event contrast (D5, D6, D12)

**Files:**
- Modify: `cli/alpha/b2.py` — `import numpy as np` between the standard-library imports and `from cli.alpha.errors import AlphaError`; `stationary_bootstrap_indices` beside `max_drawdown`; three constants after `_OI_MOMENTUM_LOOKBACK = 180` and `_HOUR = timedelta(hours=1)`; five functions after `liquidation_grid_features` and before `_check_lengths`
- Modify: `tests/test_alpha_b2.py`

**Interfaces:**
- Consumes: `cli/alpha/b2.py` as `a9c8be5d1` holds it — `_rows_at_union_closes(label, feature, oi_ts, values_name, levels, union_ts)`, `ratio_features` (imported from `cli.features.derivatives`, which names the four columns `binperp_<column>` and validates them finite or null), `funding_zscore` and `oi_zscore` (imported), `close_grid`, `_validate_stamps`, `_validate_union_marks`, `_EPOCH`, `_HOUR`, `_check_lengths`, `_check_paired`, `partial`; `cli.validation.stationary_bootstrap_indices`; in the tests, `_hours`, `DAY0`, `_RATIO_COLUMNS`, `_each_ratio`, `_oi_prefix_fixture`, and `cli.validation.bootstrap._percentile`, the bootstrap's own linear-interpolation percentile, against which the contrast's test computes its bounds by hand.
- Produces:

```python
# cli/alpha/b2.py
_RATIO_ZSCORE_WINDOW = 180
_DAILY_ZSCORE_WINDOW = 30
_DAY = timedelta(days=1)

def ratio_zscore_grid_features(oi_ts: list[datetime], ratios: dict[str, list[float | None]], union_ts: list[datetime]) -> dict[str, list[float | None]]: ...  # binperp_<column>_z30d
def ratio_max_signal(z_columns: dict[str, list[float | None]]) -> list[float | None]: ...
def daily_zscore_grid_feature(day_ts: list[datetime], values: list[float | None], union_ts: list[datetime]) -> list[float | None]: ...
def liquidation_hourly_totals(bucket_ts: list[datetime], long_usd: list[float], short_usd: list[float], hour_ts: list[datetime], covered: Collection[datetime]) -> list[float | None]: ...
def event_contrast(flags: dict[str, list[bool | None]], forwards: dict[str, dict[str, list[float | None]]], *, mean_block: float, n_resamples: int, seed: int) -> dict[str, dict[str, list[float]]]: ...
```

- [ ] **Step 1: Write the failing tests** — in `tests/test_alpha_b2.py`, the `from cli.alpha.b2 import (` block gains `daily_zscore_grid_feature,` after `close_grid,`, `event_contrast,` after `derisk_scales,`, `liquidation_hourly_totals,` after `liquidation_grid_features,`, and `ratio_max_signal,` and `ratio_zscore_grid_features,` after `ratio_grid_features,`; `from cli.validation import stationary_bootstrap_indices` and `from cli.validation.bootstrap import _percentile` go after `from cli.features.errors import FeatureError`; and at the end of the file:

```python
def _ratios_on_the_grid(marks: int) -> tuple[list[datetime], dict[str, list[float | None]], list[datetime]]:
    """Column i holds 1.0 at every mark but mark 180 + i, where it holds 2.0, each level the later of two rows inside its
    bar, the earlier 1.5 times it: a z-score over the raw rows, or a column read in another's place, differs."""
    union_ts = _hours(*range(0, 4 * (marks + 1), 4))
    oi_ts, ratios = [], {name: [] for name in _RATIO_COLUMNS}
    for k in range(marks):
        close = union_ts[k] + timedelta(hours=4)
        oi_ts += [close - timedelta(minutes=10), close - timedelta(minutes=5)]
        for i, name in enumerate(_RATIO_COLUMNS):
            level = 2.0 if k == 180 + i else 1.0
            ratios[name] += [1.5 * level, level]
    return oi_ts, ratios, union_ts


def test_each_ratio_zscore_scores_its_own_columns_level_over_180_grid_marks():
    spike, after = pytest.approx(179 / math.sqrt(180)), pytest.approx(-1 / math.sqrt(180))
    expected = {
        f"binperp_{name}_z30d": [None] * 179 + [0.0] * (1 + i) + [spike] + [after] * (3 - i)
        for i, name in enumerate(_RATIO_COLUMNS)
    }
    assert ratio_zscore_grid_features(*_ratios_on_the_grid(184)) == expected


def test_a_zero_taker_ratio_is_scored_where_an_oi_level_gate_would_refuse_it():
    oi_ts, ratios, union_ts = _ratios_on_the_grid(181)
    ratios["sum_taker_long_short_vol_ratio"] = [0.0] * len(oi_ts)
    features = ratio_zscore_grid_features(oi_ts, ratios, union_ts)
    assert features["binperp_sum_taker_long_short_vol_ratio_z30d"] == [None] * 179 + [0.0, 0.0]


def test_a_null_ratio_leaves_every_zscore_window_holding_its_mark_none():
    oi_ts, ratios, union_ts = _ratios_on_the_grid(181)
    ratios["count_long_short_ratio"][1] = None
    # Bar 0's later row is null: fallen back to its earlier row, 1.5, the first window would score.
    assert ratio_zscore_grid_features(oi_ts, ratios, union_ts)["binperp_count_long_short_ratio_z30d"] == [None] * 180 + [0.0]


def test_the_ratio_and_daily_windows_are_the_pre_registered_180_marks_and_30_days():
    assert (b2._RATIO_ZSCORE_WINDOW, b2._DAILY_ZSCORE_WINDOW) == (180, 30)


def test_a_truncated_prefix_of_the_rows_reproduces_the_ratio_zscores_bit_for_bit():
    oi_ts, oi_values, union_ts = _oi_prefix_fixture()
    ratios = _each_ratio([None if v == 0.0 else v / 100 for v in oi_values]) | {
        "sum_taker_long_short_vol_ratio": [v / 100 for v in oi_values]
    }
    full = ratio_zscore_grid_features(oi_ts, ratios, union_ts)
    # Exact: a stale level read in place of None, or a null fallen back to its row's predecessor, defines more closes.
    assert {name: sum(v is not None for v in values) for name, values in full.items()} == {
        f"binperp_{name}_z30d": 22 for name in _RATIO_COLUMNS
    }
    for n in range(1, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        visible = [i for i, t in enumerate(oi_ts) if t <= cutoff]
        prefix = ratio_zscore_grid_features(
            [oi_ts[i] for i in visible], {name: [values[i] for i in visible] for name, values in ratios.items()}, union_ts[: n + 1]
        )
        assert prefix == {name: values[:n] for name, values in full.items()}, f"prefix at n={n} disagrees with the full run"


def test_the_ratio_signal_is_the_columns_maximum_where_every_column_is_read():
    columns = {"a": [1.0, 3.0, None, -0.5], "b": [2.0, -1.0, 4.0, None], "c": [0.0, 0.0, 0.0, 0.0]}
    # Their mean reads 1.0 and 0.667 at the first two, their minimum 0.0 and -1.0, the read ones' maximum 4.0 and 0.0 at
    # the last two.
    assert ratio_max_signal(columns) == [2.0, 3.0, None, None]


@pytest.mark.parametrize(
    ("columns", "match"),
    [({}, "z_columns is empty"), ({"a": [1.0], "b": [1.0, 2.0]}, "b has length 2, expected 1")],
    ids=["no-column", "unequal-length"],
)
def test_ratio_max_signal_refuses_no_column_or_columns_of_unequal_length(columns, match):
    with pytest.raises(AlphaError, match=match):
        ratio_max_signal(columns)


def _days(*days: int) -> list[datetime]:
    return [DAY0 + timedelta(days=d) for d in days]


def test_a_daily_zscore_reaches_a_close_only_once_its_day_has_ended():
    # Day 30 doubles the 1.0 of days 0-29. Union closes run from day 30 20:00 to day 32 04:00.
    union = [DAY0 + timedelta(days=30, hours=16 + 4 * k) for k in range(10)]
    feature = daily_zscore_grid_feature(_days(*range(31)), [1.0] * 30 + [2.0], union)
    # Day 30 20:00 reads day 29, flat; day 31 00:00 to 20:00 read day 30; day 32 reads day 31, which the series lacks.
    assert feature == [0.0] + [pytest.approx(29 / math.sqrt(30))] * 6 + [None] * 2


def test_a_day_the_series_lacks_darkens_every_window_holding_it():
    days = [d for d in range(62) if d != 10]
    union = [DAY0 + timedelta(days=d + 1) for d in range(62)]
    feature = daily_zscore_grid_feature(_days(*days), [1.0] * len(days), union)
    # Each close at day d + 1 00:00 reads day d: day 10 is absent, so windows over days 0..39 hold it, and day 40's opens clean.
    assert [d for d, v in enumerate(feature) if v is not None] == list(range(40, 61))


@pytest.mark.parametrize(
    ("day_ts", "named"),
    [
        (_days(0, 1)[:1] + [DAY0 + timedelta(days=1, hours=1)], "day_ts[1] = 2024-03-02T01:00:00+00:00 is not a UTC day's start"),
        (_days(0) + [DAY0.replace(day=2, tzinfo=timezone(timedelta(hours=5)))], "is not a UTC day's start"),
        (_days(1, 0), "day_ts must be strictly increasing, violated at index 1"),
        ([DAY0.replace(tzinfo=None), DAY0.replace(day=2, tzinfo=None)], "day_ts must be tz-aware datetimes"),
    ],
    ids=["off-midnight", "a-zone-midnight", "unsorted", "naive"],
)
def test_daily_zscore_refuses_a_stamp_off_a_utc_day_start_by_name(day_ts, named):
    with pytest.raises(AlphaError, match=re.escape(named)):
        daily_zscore_grid_feature(day_ts, [1.0, 2.0], _hours(0, 4))


@pytest.mark.parametrize(
    ("day_ts", "values", "named"),
    [(_days(0, 1), [1.0], "day_ts and values must be equal length, got 2 and 1"), ([], [], "day_ts is empty")],
    ids=["unequal-length", "empty"],
)
def test_daily_zscore_refuses_unequal_lengths_and_an_empty_series(day_ts, values, named):
    with pytest.raises(AlphaError, match=re.escape(named)):
        daily_zscore_grid_feature(day_ts, values, _hours(0, 4))


def test_a_truncated_prefix_of_the_days_reproduces_the_daily_zscore_bit_for_bit():
    days = [d for d in range(70) if d not in (12, 33)]
    values = [100.0 + (37 * d) % 23 for d in days]
    # A union with a hole at day 40's first bar, opening a bar before day 0 ends.
    union = [t for t in (DAY0 + timedelta(hours=20 + 4 * k) for k in range(6 * 70)) if t != DAY0 + timedelta(days=40)]
    full = daily_zscore_grid_feature(_days(*days), values, union)
    # Exact: day 33 is absent, so no window before day 63 is whole; day 63's value enters at day 64's first close.
    assert [j for j, v in enumerate(full) if v is not None][0] == union.index(DAY0 + timedelta(days=63, hours=20))
    for n in range(1, len(union)):
        cutoff = union[n - 1] + timedelta(hours=4)
        # Two days at least: the z-score reads a list of two or more.
        k = sum(DAY0 + timedelta(days=d + 1) <= cutoff for d in days)
        if k < 2:
            continue
        prefix = daily_zscore_grid_feature(_days(*days[:k]), values[:k], union[: n + 1])
        assert prefix == full[:n], f"prefix at n={n} disagrees with the full run"


def test_each_covered_hour_sums_both_legs_of_its_buckets_and_any_other_hour_reads_none():
    bucket_ts, long_usd, short_usd = _buckets(_LIQUIDATIONS["BTC"])
    # Hour 9 is not asserted covered; hour 16 is, and holds no bucket.
    hours = _hours(0, 1, 2, 9, 15, 16)
    covered = [t for t in _hours(*range(17)) if t != DAY0 + timedelta(hours=9)]
    totals = liquidation_hourly_totals(bucket_ts, long_usd, short_usd, hours, covered)
    assert totals == [100.0, 300.0, 50.0, None, 6.0, 0.0] and type(totals[-1]) is float


@pytest.mark.parametrize(
    ("hours", "covered", "named"),
    [
        (_hours(0, 1) + [DAY0 + timedelta(hours=2, minutes=5)], _hours(0, 1, 2), "hour_ts must be tz-aware hour starts, got"),
        (_hours(0, 1, 2), _hours(0, 1) + [DAY0 + timedelta(hours=2, minutes=5)], "covered must be tz-aware hour starts, got"),
    ],
    ids=["an-hour-off-its-start", "a-covered-stamp-off-its-start"],
)
def test_liquidation_hourly_totals_refuses_a_stamp_off_an_hour_start_by_name(hours, covered, named):
    with pytest.raises(AlphaError, match=re.escape(named)):
        liquidation_hourly_totals(*_buckets(_LIQUIDATIONS["BTC"]), hours, covered)


def _reference_contrast(rows: list[tuple[list, list]], draws: list[list[int]]) -> list[float]:
    """The contrast's row by hand: point means over the read indices, and the percentile bounds over the resamples that
    hold an event and another."""
    events = [v for flags, values in rows for f, v in zip(flags, values) if f is True and v is not None]
    others = [v for flags, values in rows for f, v in zip(flags, values) if f is False and v is not None]
    diffs = []
    for idx in draws:
        ev = [values[k] for flags, values in rows for k in idx if flags[k] is True and values[k] is not None]
        ot = [values[k] for flags, values in rows for k in idx if flags[k] is False and values[k] is not None]
        if ev and ot:
            diffs.append(sum(ev) / len(ev) - sum(ot) / len(ot))
    diffs.sort()
    point = sum(events) / len(events) - sum(others) / len(others)
    return [
        len(events),
        len(others),
        sum(events) / len(events),
        sum(others) / len(others),
        point,
        _percentile(diffs, 0.025),
        _percentile(diffs, 0.975),
    ]


def test_the_event_contrast_compares_the_means_after_events_and_after_the_others_with_shared_bootstrap_bounds():
    flags = {
        "BTC": [True, False, False, True, None, False, True, False, False, False, True, False],
        "ETH": [False, True, False, False, True, False, None, True, False, False, False, True],
        "DOT": [True, False, False, False, False, False, False, False, False, False, False, False],
    }
    values = {
        "BTC": [0.03, 0.01, -0.02, 0.05, 9.0, 0.0, 0.04, 0.02, -0.01, 0.01, None, 0.00],
        "ETH": [0.01, -0.03, 0.02, 0.00, -0.02, 0.01, 9.0, -0.04, 0.03, 0.01, 0.02, -0.01],
        "DOT": [0.07, 0.01, 0.0, 0.01, 0.02, 0.0, 0.01, 0.0, 0.02, 0.01, 0.0, 0.03],
    }
    out = event_contrast(flags, {"ret": values}, mean_block=3, n_resamples=200, seed=7)
    draws = stationary_bootstrap_indices(12, mean_block=3, n_resamples=200, seed=7)
    # DOT holds one event and is left out; BTC's fourth event has no forward value, and an unread flag reads nothing.
    assert set(out["ret"]) == {"BTC", "ETH", "pooled"}
    for name, rows in (("BTC", [(flags["BTC"], values["BTC"])]), ("ETH", [(flags["ETH"], values["ETH"])])):
        assert out["ret"][name] == pytest.approx(_reference_contrast(rows, draws)), name
    pooled = [(flags[a], values[a]) for a in ("BTC", "ETH")]
    assert out["ret"]["pooled"] == pytest.approx(_reference_contrast(pooled, draws))
    assert out["ret"]["BTC"][:2] == [3, 7] and [type(x) for x in out["ret"]["BTC"]] == [int, int] + [float] * 5


def test_event_contrast_refuses_a_forward_series_of_another_length():
    with pytest.raises(AlphaError, match=re.escape("forwards['ret']['BTC'] has length 2, expected 3")):
        event_contrast({"BTC": [True, False, True]}, {"ret": {"BTC": [0.1, 0.2]}}, mean_block=2, n_resamples=10, seed=1)
```

  **Author's call** — the known answers are hand values (`179 / sqrt(180)`, `-1 / sqrt(180)`, `29 / sqrt(30)`); each column of `_ratios_on_the_grid` spikes at a different mark and each bar's earlier row is 1.5 times its last, so a column read in another's place or a z-score over the raw rows differs; the daily case's closes run from inside day 30 through day 31 to day 32's start, so a day read one close early or late differs, and the missing-day case's first clean close is the one whose window first leaves the gap; the prefix tests follow spec 00131's and spec 00136's, the daily one from two days because `funding_zscore` refuses a list of one value; the contrast's reference recomputes the bounds with the bootstrap's own indices and percentile, so a per-asset draw, another percentile or an event counted among the others differs.

- [ ] **Step 2: Run them to verify they fail**

Run: `mkdir -p .tmp/plan-00138 && uv run pytest tests/test_alpha_b2.py -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt`
Expected: the module fails to collect, `ImportError: cannot import name 'daily_zscore_grid_feature' from 'cli.alpha.b2'`, `1 error` (measured on the transcription)

- [ ] **Step 3: Implement in `cli/alpha/b2.py`** — `import numpy as np` and a blank line after `from functools import partial`'s blank line, before `from cli.alpha.errors import AlphaError`; `from cli.validation import max_drawdown` becomes `from cli.validation import max_drawdown, stationary_bootstrap_indices`; after `_OI_MOMENTUM_LOOKBACK = 180`:

```python
# Pre-registered 30-day windows (docs/specs/00138 D5, D6), not knobs: a change to one is a new trial.
_RATIO_ZSCORE_WINDOW = 180
_DAILY_ZSCORE_WINDOW = 30
```

  after `_HOUR = timedelta(hours=1)`, `_DAY = timedelta(days=1)`; and after `liquidation_grid_features` and before `def _check_lengths(`:

```python
def ratio_zscore_grid_features(
    oi_ts: list[datetime], ratios: dict[str, list[float | None]], union_ts: list[datetime]
) -> dict[str, list[float | None]]:
    """Each ratio's trailing z-score over its level on the OI rows' regular grid, read at a union's closes
    (docs/specs/00138 D5), through `funding_zscore`, the finite-or-null trailing z-score: a `0.0` taker ratio is a reading
    and is scored."""
    zscore = partial(funding_zscore, window=_RATIO_ZSCORE_WINDOW)
    return {
        f"{name}_z30d": _rows_at_union_closes(f"{name} z-score", zscore, oi_ts, name, values, union_ts)
        for name, values in ratio_features(ratios).items()
    }


def ratio_max_signal(z_columns: dict[str, list[float | None]]) -> list[float | None]:
    """The columns' maximum at each index, None wherever any column is None (docs/specs/00138 D5)."""
    if not z_columns:
        raise AlphaError("z_columns is empty: the signal reads at least one column")
    n = _check_lengths(z_columns)
    columns = list(z_columns.values())
    return [None if any(column[k] is None for column in columns) else max(column[k] for column in columns) for k in range(n)]


def daily_zscore_grid_feature(day_ts: list[datetime], values: list[float | None], union_ts: list[datetime]) -> list[float | None]:
    """A daily series' trailing z-score at each union close (docs/specs/00138 D6): a day's value reaches a close once the
    day has ended, from the close at or after the next day's 00:00Z until the next day's own value is due, and a day the
    series lacks is None, darkening every window holding it."""
    if len(day_ts) != len(values):
        raise AlphaError(f"day_ts and values must be equal length, got {len(day_ts)} and {len(values)}")
    if not day_ts:
        raise AlphaError("day_ts is empty: no close would read a day")
    _validate_stamps("day_ts", day_ts)
    for i, t in enumerate(day_ts):
        if (t - _EPOCH) % _DAY:
            raise AlphaError(f"day_ts[{i}] = {t.isoformat()} is not a UTC day's start")
    _validate_union_marks(union_ts)
    first = day_ts[0]
    grid: list[float | None] = [None] * ((day_ts[-1] - first) // _DAY + 1)
    for t, v in zip(day_ts, values):
        grid[(t - first) // _DAY] = v
    zscores = funding_zscore(grid, window=_DAILY_ZSCORE_WINDOW)
    # The latest day a close has seen end is the one before the day the close falls in.
    days = [(c - first) // _DAY - 1 for c in close_grid(union_ts)]
    return [zscores[k] if 0 <= k < len(grid) else None for k in days]


def liquidation_hourly_totals(
    bucket_ts: list[datetime],
    long_usd: list[float],
    short_usd: list[float],
    hour_ts: list[datetime],
    covered: Collection[datetime],
) -> list[float | None]:
    """One coin's liquidated notional, both legs, in each hour of `hour_ts` (docs/specs/00138 D12): an hour the caller
    asserts covered sums the buckets stamped inside it, zero where there are none, and any other hour reads None."""
    if not len(bucket_ts) == len(long_usd) == len(short_usd):
        raise AlphaError(
            f"bucket_ts, long_usd and short_usd must be equal length, got {len(bucket_ts)}, {len(long_usd)} and {len(short_usd)}"
        )
    if not bucket_ts:
        raise AlphaError("bucket_ts is empty: every covered hour would sum to zero")
    _validate_stamps("bucket_ts", bucket_ts)
    _validate_stamps("hour_ts", hour_ts)
    for name, stamps in (("hour_ts", hour_ts), ("covered", covered)):
        for t in stamps:
            if t.utcoffset() is None or (t - _EPOCH) % _HOUR:
                raise AlphaError(f"{name} must be tz-aware hour starts, got {t.isoformat()}")
    asserted = set(covered)
    out: list[float | None] = []
    for h in hour_ts:
        if h not in asserted:
            out.append(None)
            continue
        lo, hi = bisect_left(bucket_ts, h), bisect_left(bucket_ts, h + _HOUR)
        out.append(sum(long_usd[lo:hi], 0.0) + sum(short_usd[lo:hi], 0.0))
    return out


def event_contrast(
    flags: dict[str, list[bool | None]],
    forwards: dict[str, dict[str, list[float | None]]],
    *,
    mean_block: float,
    n_resamples: int,
    seed: int,
) -> dict[str, dict[str, list[float]]]:
    """Per forward series, per asset and pooled over the assets kept: `[events, others, mean after an event, mean after
    the others, their difference, its 2.5 % and 97.5 % stationary-bootstrap bounds]` over the indices where both the flag
    and the forward value are read (docs/specs/00138 D12). One set of index draws serves every series and asset, so the
    pooled bounds keep the assets' common hours together; an asset with fewer than two events or two others in a series is
    left out of it, and a resample holding no event or no other for a row is skipped for that row."""
    n = _check_lengths({f"flags[{asset!r}]": values for asset, values in flags.items()})
    for series, by_asset in forwards.items():
        _check_paired("flags", flags, f"forwards[{series!r}]", by_asset, n)
    draws = np.array(stationary_bootstrap_indices(n, mean_block=mean_block, n_resamples=n_resamples, seed=seed))
    out: dict[str, dict[str, list[float]]] = {}
    for series, by_asset in forwards.items():
        kept = {}
        for asset, flag in flags.items():
            values = by_asset[asset]
            event = np.array([f is True and v is not None for f, v in zip(flag, values)])
            other = np.array([f is False and v is not None for f, v in zip(flag, values)])
            if event.sum() >= 2 and other.sum() >= 2:
                kept[asset] = (event, other, np.array([0.0 if v is None else v for v in values]))
        rows = {}
        for name, members in [*((asset, [member]) for asset, member in kept.items()), ("pooled", list(kept.values()))]:
            if not members:
                continue
            n_event = sum(int(event.sum()) for event, _, _ in members)
            n_other = sum(int(other.sum()) for _, other, _ in members)
            mean_event = sum(float(x[event].sum()) for event, _, x in members) / n_event
            mean_other = sum(float(x[other].sum()) for _, other, x in members) / n_other
            resampled = [(event[draws], other[draws], x[draws]) for event, other, x in members]
            boot_events = sum(e.sum(axis=1) for e, _, _ in resampled)
            boot_others = sum(o.sum(axis=1) for _, o, _ in resampled)
            usable = (boot_events > 0) & (boot_others > 0)
            if not usable.any():
                continue
            boot_event_means = sum((x * e).sum(axis=1) for e, _, x in resampled)[usable] / boot_events[usable]
            boot_other_means = sum((x * o).sum(axis=1) for _, o, x in resampled)[usable] / boot_others[usable]
            low, high = np.percentile(boot_event_means - boot_other_means, [2.5, 97.5])
            diff = mean_event - mean_other
            rows[name] = [n_event, n_other, mean_event, mean_other, diff, float(low), float(high)]
        out[series] = rows
    return out
```

- [ ] **Step 4: Run them to verify they pass** — Step 2's command. Expected: `136 passed`; and `uv run pytest tests/test_alpha_b2.py -k "ratio_zscore or ratio_signal or ratio_max_signal or ratio_and_daily_windows or zero_taker_ratio_is_scored or null_ratio_leaves or daily_zscore or day_the_series_lacks or covered_hour_sums or hourly_totals or event_contrast" -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` prints `22 passed, 114 deselected`, the twenty-two new cases.

- [ ] **Step 5: Stage, consumers, gate** — `git add cli/alpha/b2.py tests/test_alpha_b2.py`; the Global Constraints' `T` over the two paths, run as they run it (measured on the transcription: `tests/test_alpha_b1_exit.py`, `tests/test_alpha_b2.py`, `tests/test_research_b1_hourly_exit_basis.py`, `tests/test_research_b1_volume_basis.py`, `tests/test_research_b2_basis.py`, `tests/test_research_b2_full_basis.py` and `tests/test_research_command.py`, `588 passed, 57 deselected` in 3 min 37 s); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.

- [ ] **Step 6: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured on the transcription, twenty-seven of twenty-seven):

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation '/^def ratio_zscore_grid_features(/,/^def /s/        f"{name}_z30d": _rows_at_union_closes(/        name: _rows_at_union_closes(/' -- uv run pytest 'tests/test_alpha_b2.py::test_each_ratio_zscore_scores_its_own_columns_level_over_180_grid_marks' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation '/^def ratio_zscore_grid_features(/,/^def /s/    zscore = partial(funding_zscore, window=_RATIO_ZSCORE_WINDOW)/    zscore = list/' -- uv run pytest 'tests/test_alpha_b2.py::test_each_ratio_zscore_scores_its_own_columns_level_over_180_grid_marks' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation '/^def ratio_zscore_grid_features(/,/^def /s/    zscore = partial(funding_zscore, window=_RATIO_ZSCORE_WINDOW)/    zscore = partial(oi_zscore, window=_RATIO_ZSCORE_WINDOW)/' -- uv run pytest 'tests/test_alpha_b2.py::test_a_zero_taker_ratio_is_scored_where_an_oi_level_gate_would_refuse_it' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation '/^def ratio_zscore_grid_features(/,/^def /s/oi_ts, name, values, union_ts)/oi_ts, name, [1.5 if v is None else v for v in values], union_ts)/' -- uv run pytest 'tests/test_alpha_b2.py::test_a_null_ratio_leaves_every_zscore_window_holding_its_mark_none' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation 's/^_RATIO_ZSCORE_WINDOW = 180/_RATIO_ZSCORE_WINDOW = 179/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_ratio_and_daily_windows_are_the_pre_registered_180_marks_and_30_days' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation '/^def ratio_zscore_grid_features(/,/^def /s/    zscore = partial(funding_zscore, window=_RATIO_ZSCORE_WINDOW)/    zscore = lambda v: funding_zscore(v[1:] + v[-1:], window=_RATIO_ZSCORE_WINDOW)/' -- uv run pytest 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_rows_reproduces_the_ratio_zscores_bit_for_bit' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_max_signal(/def ratio_max_signal_gone(/' --mutation '/^def ratio_max_signal(/,/^def /s/ else max(column\[k\] for column in columns)/ else min(column[k] for column in columns)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_ratio_signal_is_the_columns_maximum_where_every_column_is_read' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_max_signal(/def ratio_max_signal_gone(/' --mutation '/^def ratio_max_signal(/,/^def /s/None if any(column\[k\] is None for column in columns) else max(column\[k\] for column in columns)/None if all(column[k] is None for column in columns) else max(column[k] for column in columns if column[k] is not None)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_ratio_signal_is_the_columns_maximum_where_every_column_is_read' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_max_signal(/def ratio_max_signal_gone(/' --mutation '/^def ratio_max_signal(/,/^def /s/    if not z_columns:/    if False:/' -- uv run pytest 'tests/test_alpha_b2.py::test_ratio_max_signal_refuses_no_column_or_columns_of_unequal_length[no-column]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_max_signal(/def ratio_max_signal_gone(/' --mutation '/^def ratio_max_signal(/,/^def /s/    n = _check_lengths(z_columns)/    n = len(next(iter(z_columns.values())))/' -- uv run pytest 'tests/test_alpha_b2.py::test_ratio_max_signal_refuses_no_column_or_columns_of_unequal_length[unequal-length]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def ratio_zscore_grid_features(/def ratio_zscore_grid_features_gone(/' --mutation 's/^_DAILY_ZSCORE_WINDOW = 30/_DAILY_ZSCORE_WINDOW = 31/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_ratio_and_daily_windows_are_the_pre_registered_180_marks_and_30_days' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def daily_zscore_grid_feature(/def daily_zscore_grid_feature_gone(/' --mutation '/^def daily_zscore_grid_feature(/,/^def /s/    days = \[(c - first) \/\/ _DAY - 1 for c in close_grid(union_ts)\]/    days = [(c - first) \/\/ _DAY for c in close_grid(union_ts)]/' -- uv run pytest 'tests/test_alpha_b2.py::test_a_daily_zscore_reaches_a_close_only_once_its_day_has_ended' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def daily_zscore_grid_feature(/def daily_zscore_grid_feature_gone(/' --mutation '/^def daily_zscore_grid_feature(/,/^def /s/    days = \[(c - first) \/\/ _DAY - 1 for c in close_grid(union_ts)\]/    days = [(c - first) \/\/ _DAY - 1 for c in union_ts[:-1]]/' -- uv run pytest 'tests/test_alpha_b2.py::test_a_daily_zscore_reaches_a_close_only_once_its_day_has_ended' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def daily_zscore_grid_feature(/def daily_zscore_grid_feature_gone(/' --mutation '/^def daily_zscore_grid_feature(/,/^def /s/    grid: list\[float | None\] = \[None\] \* /    grid: list[float | None] = [1.0] * /' -- uv run pytest 'tests/test_alpha_b2.py::test_a_day_the_series_lacks_darkens_every_window_holding_it' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def daily_zscore_grid_feature(/def daily_zscore_grid_feature_gone(/' --mutation '/^def daily_zscore_grid_feature(/,/^def /s/        if (t - _EPOCH) % _DAY:/        if False:/' -- uv run pytest 'tests/test_alpha_b2.py::test_daily_zscore_refuses_a_stamp_off_a_utc_day_start_by_name[off-midnight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def daily_zscore_grid_feature(/def daily_zscore_grid_feature_gone(/' --mutation '/^def daily_zscore_grid_feature(/,/^def /s/        if (t - _EPOCH) % _DAY:/        if False:/' -- uv run pytest 'tests/test_alpha_b2.py::test_daily_zscore_refuses_a_stamp_off_a_utc_day_start_by_name[a-zone-midnight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def daily_zscore_grid_feature(/def daily_zscore_grid_feature_gone(/' --mutation '/^def daily_zscore_grid_feature(/,/^def /s/    if len(day_ts) != len(values):/    if False:/' -- uv run pytest 'tests/test_alpha_b2.py::test_daily_zscore_refuses_unequal_lengths_and_an_empty_series[unequal-length]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def daily_zscore_grid_feature(/def daily_zscore_grid_feature_gone(/' --mutation '/^def daily_zscore_grid_feature(/,/^def /s/    if not day_ts:/    if False:/' -- uv run pytest 'tests/test_alpha_b2.py::test_daily_zscore_refuses_unequal_lengths_and_an_empty_series[empty]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def daily_zscore_grid_feature(/def daily_zscore_grid_feature_gone(/' --mutation '/^def daily_zscore_grid_feature(/,/^def /s/    zscores = funding_zscore(grid, window=_DAILY_ZSCORE_WINDOW)/    zscores = funding_zscore(grid[1:] + grid[-1:], window=_DAILY_ZSCORE_WINDOW)/' -- uv run pytest 'tests/test_alpha_b2.py::test_a_truncated_prefix_of_the_days_reproduces_the_daily_zscore_bit_for_bit' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_hourly_totals(/def liquidation_hourly_totals_gone(/' --mutation '/^def liquidation_hourly_totals(/,/^def /s/        out.append(sum(long_usd\[lo:hi\], 0.0) + sum(short_usd\[lo:hi\], 0.0))/        out.append(sum(long_usd[lo:hi], 0.0) + 0.0)/' -- uv run pytest 'tests/test_alpha_b2.py::test_each_covered_hour_sums_both_legs_of_its_buckets_and_any_other_hour_reads_none' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_hourly_totals(/def liquidation_hourly_totals_gone(/' --mutation '/^def liquidation_hourly_totals(/,/^def /s/        if h not in asserted:/        if False:/' -- uv run pytest 'tests/test_alpha_b2.py::test_each_covered_hour_sums_both_legs_of_its_buckets_and_any_other_hour_reads_none' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_hourly_totals(/def liquidation_hourly_totals_gone(/' --mutation '/^def liquidation_hourly_totals(/,/^def /s/            if t.utcoffset() is None or (t - _EPOCH) % _HOUR:/            if False:/' -- uv run pytest 'tests/test_alpha_b2.py::test_liquidation_hourly_totals_refuses_a_stamp_off_an_hour_start_by_name[an-hour-off-its-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def liquidation_hourly_totals(/def liquidation_hourly_totals_gone(/' --mutation '/^def liquidation_hourly_totals(/,/^def /s/            if t.utcoffset() is None or (t - _EPOCH) % _HOUR:/            if False:/' -- uv run pytest 'tests/test_alpha_b2.py::test_liquidation_hourly_totals_refuses_a_stamp_off_an_hour_start_by_name[a-covered-stamp-off-its-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast(/def event_contrast_gone(/' --mutation '/^def event_contrast(/,/^def /s/            if event.sum() >= 2 and other.sum() >= 2:/            if event.sum() >= 1 and other.sum() >= 1:/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_event_contrast_compares_the_means_after_events_and_after_the_others_with_shared_bootstrap_bounds' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast(/def event_contrast_gone(/' --mutation '/^def event_contrast(/,/^def /s/\[2.5, 97.5\])/[5.0, 95.0])/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_event_contrast_compares_the_means_after_events_and_after_the_others_with_shared_bootstrap_bounds' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast(/def event_contrast_gone(/' --mutation '/^def event_contrast(/,/^def /s/            other = np.array(\[f is False and v is not None/            other = np.array([f is not True and v is not None/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_event_contrast_compares_the_means_after_events_and_after_the_others_with_shared_bootstrap_bounds' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast(/def event_contrast_gone(/' --mutation '/^def event_contrast(/,/^def /s/        _check_paired("flags", flags, f"forwards\[{series!r}\]", by_asset, n)/        pass/' -- uv run pytest 'tests/test_alpha_b2.py::test_event_contrast_refuses_a_forward_series_of_another_length' -q -p no:cacheprovider --basetemp=.tmp/pt
```

- [ ] **Step 7: Commit**

```bash
git commit -F - <<'EOF'
feat(alpha): the B2 ratio z-scores and their all-four maximum, the daily z-score read once its day has ended, the hourly liquidation totals and the event contrast

<the task's pytest result line, pasted from its run over this tree>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<each probe: its infra/scripts/mutate-probe.sh command, then its verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

______________________________________________________________________

### Task 2: the daily liquidation backfill — `fetch_liquidation_history`'s interval, `backfill_daily` and `zcrypto liquidations-backfill` (D7)

**Files:**
- Modify: `cli/liquidations/coinalyze.py` — `fetch_liquidation_history`'s signature and URL; two constants and two functions at the end of the file
- Modify: `cli/__main__.py` — the command's import and registration
- Modify: `tests/test_liquidations_coinalyze.py`, `README.md`

**Interfaces:**
- Consumes: `cli/liquidations/coinalyze.py` as `a9c8be5d1` holds it — `fetch_liquidation_history(api_key, symbols, frm, to, *, opener=urllib.request.urlopen)`, `poll_cycle`, `symbol_for`, `COINS`, `API_KEY_ENV_VAR`, `_CLOSE_MARGIN_SECONDS`, `LiquidationsError`, `logger`, `pl`, `typer`, `os`, `Path`, `datetime`, `UTC`; in the tests, `runner`, `app`, `SegmentWriter`, `LIQ_AGG_SCHEMA`, `io`, `json`, `monkeypatch`.
- Produces:

```python
# cli/liquidations/coinalyze.py
def fetch_liquidation_history(api_key: str, symbols: list[str], frm: int, to: int, *, interval: str = "1min", opener=urllib.request.urlopen) -> list[dict]: ...
_DAY_SECONDS = 86_400
_BACKFILL_FROM = datetime(2018, 1, 1, tzinfo=UTC)
def backfill_daily(api_key: str, coins: list[str], out_dir: Path, *, now: datetime | None = None, opener=urllib.request.urlopen) -> dict[str, int]: ...
def liquidations_backfill(out_dir: Path = typer.Option(..., "--out", ...)) -> None: ...  # zcrypto liquidations-backfill
```

- [ ] **Step 1: Write the failing tests** — in `tests/test_liquidations_coinalyze.py`, the line `from cli.liquidations.coinalyze import COINS, fetch_liquidation_history, poll_cycle, prime_bucket_watermarks, symbol_for` becomes:

```python
from cli.liquidations.coinalyze import (
    COINS,
    backfill_daily,
    fetch_liquidation_history,
    poll_cycle,
    prime_bucket_watermarks,
    symbol_for,
)
```

  and at the end of the file:

```python
# --- the daily backfill ------------------------------------------------------------------------


def _capturing(body):
    urls = []

    def _open(request, timeout=None):
        urls.append(request.full_url)
        return io.BytesIO(json.dumps(body).encode("utf-8"))

    return _open, urls


def test_fetch_liquidation_history_sends_the_interval_it_is_given():
    opener, urls = _capturing([])
    fetch_liquidation_history("key", ["BTCUSDT_PERP.A"], 900, 1900, interval="daily", opener=opener)
    assert "interval=daily" in urls[0] and "interval=1min" not in urls[0]


def test_poll_cycle_requests_the_one_minute_interval(tmp_path):
    opener, urls = _capturing([])
    writers = {"BTC": SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")}
    poll_cycle("key", ["BTC"], writers, now=datetime(2024, 3, 1, 12, 5, tzinfo=UTC), opener=opener)
    writers["BTC"].close()
    assert len(urls) == 1 and "interval=1min" in urls[0]


# 2024-03-01 12:05Z: days to 2024-02-29 are closed, 2024-03-01's is still open.
_BACKFILL_NOW = datetime(2024, 3, 1, 12, 5, tzinfo=UTC)
_DAY_S = 86_400
_FEB_27 = int(datetime(2024, 2, 27, tzinfo=UTC).timestamp())


def _daily_body(coins=("BTC", "ETH"), *, stamps=(_FEB_27, _FEB_27 + _DAY_S, _FEB_27 + 2 * _DAY_S, _FEB_27 + 3 * _DAY_S)):
    return [
        {
            "symbol": f"{coin}USDT_PERP.A",
            "history": [{"t": t, "l": 1000.0 * (i + 1) + k, "s": 10.0 * k} for k, t in enumerate(stamps)],
        }
        for i, coin in enumerate(coins)
    ]


def test_the_daily_backfill_writes_one_file_per_coin_of_its_closed_days(tmp_path):
    opener, urls = _capturing(_daily_body())

    written = backfill_daily("key", ["BTC", "ETH"], tmp_path / "set", now=_BACKFILL_NOW, opener=opener)

    assert written == {"BTC": 3, "ETH": 3}
    assert "interval=daily" in urls[0] and f"from={int(datetime(2018, 1, 1, tzinfo=UTC).timestamp())}" in urls[0]
    frame = pl.read_parquet(tmp_path / "set" / "ETH" / "daily.parquet")
    assert frame.schema == {"ts": pl.Datetime("us", "UTC"), "long_usd": pl.Float64, "short_usd": pl.Float64}
    assert frame["ts"].to_list() == [datetime(2024, 2, d, tzinfo=UTC) for d in (27, 28, 29)]
    assert (frame["long_usd"].to_list(), frame["short_usd"].to_list()) == ([2000.0, 2001.0, 2002.0], [0.0, 10.0, 20.0])


@pytest.mark.parametrize(
    ("body", "refused"),
    [
        pytest.param(_daily_body(("BTC",)), "the response holds no closed day for ['ETH']", id="a-coin-missing"),
        pytest.param(
            [*_daily_body(("BTC",), stamps=(_FEB_27 - _DAY_S,)), *_daily_body()],
            "BTCUSDT_PERP.A: the response holds the coin twice",
            id="a-coin-twice",
        ),
        pytest.param({"error": "nope"}, "malformed Coinalyze liquidation-history response", id="a-non-list-body"),
        pytest.param(_daily_body(stamps=(_FEB_27, _FEB_27 + 3600)), "BTCUSDT_PERP.A: a day stamp off 00:00Z", id="off-midnight"),
        pytest.param(
            _daily_body(stamps=(_FEB_27 + _DAY_S, _FEB_27)), "BTCUSDT_PERP.A: day stamps not strictly increasing", id="non-monotone"
        ),
        pytest.param(
            [{"symbol": "BTCUSDT_PERP.A", "history": [{"t": _FEB_27, "l": 1.0}]}, *_daily_body(("ETH",))],
            "BTCUSDT_PERP.A: a malformed daily bucket",
            id="a-malformed-bucket",
        ),
        pytest.param(
            [{"symbol": "BTCUSDT_PERP.A", "history": [{"t": _FEB_27, "l": float("nan"), "s": 1.0}]}, *_daily_body(("ETH",))],
            "BTCUSDT_PERP.A: a malformed daily bucket: a leg non-finite or negative",
            id="a-non-finite-leg",
        ),
        pytest.param(
            [{"symbol": "BTCUSDT_PERP.A", "history": [{"t": _FEB_27, "l": 1.0, "s": -5.0}]}, *_daily_body(("ETH",))],
            "BTCUSDT_PERP.A: a malformed daily bucket: a leg non-finite or negative",
            id="a-negative-leg",
        ),
    ],
)
def test_the_daily_backfill_refuses_a_response_it_cannot_trust_and_writes_nothing(tmp_path, body, refused):
    opener, _ = _capturing(body)

    with pytest.raises(LiquidationsError, match=re.escape(refused)):
        backfill_daily("key", ["BTC", "ETH"], tmp_path / "set", now=_BACKFILL_NOW, opener=opener)

    assert not (tmp_path / "set").exists()


def test_the_daily_backfill_never_writes_over_a_set(tmp_path):
    (tmp_path / "set").mkdir()

    def _never(request, timeout=None):
        raise AssertionError("the backfill fetched before refusing an existing set")

    with pytest.raises(LiquidationsError, match="exists: a backfill never writes over a set"):
        backfill_daily("key", ["BTC"], tmp_path / "set", now=_BACKFILL_NOW, opener=_never)


def test_liquidations_backfill_requires_the_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("COINALYZE_API_KEY", raising=False)

    def _never(api_key, coins, out_dir, **kwargs):
        raise AssertionError("the backfill ran without a key")

    monkeypatch.setattr("cli.liquidations.coinalyze.backfill_daily", _never)
    result = runner.invoke(app, ["liquidations-backfill", "--out", str(tmp_path / "set")])
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert not (tmp_path / "set").exists()


def test_liquidations_backfill_writes_the_ten_coins_and_prints_their_days(tmp_path, monkeypatch):
    monkeypatch.setenv("COINALYZE_API_KEY", "test-key")
    calls = []

    def _fake(api_key, coins, out_dir, **kwargs):
        calls.append((api_key, coins, out_dir))
        return {coin: 3 for coin in coins}

    monkeypatch.setattr("cli.liquidations.coinalyze.backfill_daily", _fake)
    result = runner.invoke(app, ["liquidations-backfill", "--out", str(tmp_path / "set")])
    assert result.exit_code == 0, result.output
    assert calls == [("test-key", COINS, tmp_path / "set")]
    assert [line for line in result.output.splitlines() if line] == [f"{coin}: 3 days" for coin in sorted(COINS)]


def test_liquidations_backfill_exits_on_a_refusal_naming_it(tmp_path, monkeypatch):
    monkeypatch.setenv("COINALYZE_API_KEY", "test-key")

    def _refuse(api_key, coins, out_dir, **kwargs):
        raise LiquidationsError("the response holds no closed day for ['ETH']")

    monkeypatch.setattr("cli.liquidations.coinalyze.backfill_daily", _refuse)
    result = runner.invoke(app, ["liquidations-backfill", "--out", str(tmp_path / "set")])
    assert result.exit_code == 1 and "liquidations-backfill: the response holds no closed day for ['ETH']" in result.output
```

  **Author's call** — every case drives the fetch through an injected opener or a monkeypatched `backfill_daily`, so no case reaches the network; the refusals each spoil one thing of an otherwise passing response and assert nothing was written; the poller's case reads the URL its own cycle builds, so the one-minute interval is proven at the caller, not at the default.

- [ ] **Step 2: Run them to verify they fail**

Run: `mkdir -p .tmp/plan-00138 && uv run pytest tests/test_liquidations_coinalyze.py -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt`
Expected: the module fails to collect, `ImportError: cannot import name 'backfill_daily' from 'cli.liquidations.coinalyze'`, `1 error` (measured on the transcription)

- [ ] **Step 3: Implement** — in `cli/liquidations/coinalyze.py`, the line `def fetch_liquidation_history(api_key: str, symbols: list[str], frm: int, to: int, *, opener=urllib.request.urlopen) -> list[dict]:` becomes:

```python
def fetch_liquidation_history(
    api_key: str, symbols: list[str], frm: int, to: int, *, interval: str = "1min", opener=urllib.request.urlopen
) -> list[dict]:
```

  its URL line `    url = f"{_BASE_URL}?symbols={symbols_csv}&interval=1min&from={frm}&to={to}&convert_to_usd=true"` becomes `    url = f"{_BASE_URL}?symbols={symbols_csv}&interval={interval}&from={frm}&to={to}&convert_to_usd=true"`, and after `liquidations_poll`'s last line, at the end of the file:

```python
_DAY_SECONDS = 86_400
_BACKFILL_FROM = datetime(2018, 1, 1, tzinfo=UTC)


def backfill_daily(
    api_key: str, coins: list[str], out_dir: Path, *, now: datetime | None = None, opener=urllib.request.urlopen
) -> dict[str, int]:
    """Coinalyze's daily liquidation history of `coins` from 2018-01-01 to the last day proven closed, one
    `<COIN>/daily.parquet` each — `ts` the day's 00:00Z, `long_usd`, `short_usd` — returning the days written per coin.
    Coinalyze returns about 1,500 days, so the first day is whatever its window holds on the fetch day. Nothing is
    written unless the whole response passes: `out_dir` absent, every coin present once with at least one day, each day stamp
    on 00:00Z and strictly increasing, each leg finite and non-negative."""
    if out_dir.exists():
        raise LiquidationsError(f"{out_dir} exists: a backfill never writes over a set")
    now_s = int((now or datetime.now(UTC)).timestamp())
    symbol_to_coin = {symbol_for(coin): coin for coin in coins}
    payload = fetch_liquidation_history(
        api_key, list(symbol_to_coin), int(_BACKFILL_FROM.timestamp()), now_s, interval="daily", opener=opener
    )
    days: dict[str, list[tuple[int, float, float]]] = {}
    for entry in payload:
        coin = symbol_to_coin.get(entry.get("symbol")) if isinstance(entry, dict) else None
        if coin is None:
            continue
        if coin in days:
            raise LiquidationsError(f"{entry['symbol']}: the response holds the coin twice")
        try:
            rows = [(int(b["t"]), float(b["l"]), float(b["s"])) for b in entry.get("history", [])]
        except (KeyError, TypeError, ValueError) as exc:
            raise LiquidationsError(f"{entry['symbol']}: a malformed daily bucket: {exc!r}") from exc
        if not all(0.0 <= leg < float("inf") for _, long, short in rows for leg in (long, short)):
            raise LiquidationsError(f"{entry['symbol']}: a malformed daily bucket: a leg non-finite or negative")
        # A day is proven closed as a minute bucket is, once its end lies the poller's margin behind the fetch.
        rows = [row for row in rows if row[0] + _DAY_SECONDS <= now_s - _CLOSE_MARGIN_SECONDS]
        stamps = [t for t, _, _ in rows]
        if any(t % _DAY_SECONDS for t in stamps):
            raise LiquidationsError(f"{entry['symbol']}: a day stamp off 00:00Z")
        if any(later <= earlier for earlier, later in zip(stamps, stamps[1:])):
            raise LiquidationsError(f"{entry['symbol']}: day stamps not strictly increasing")
        days[coin] = rows
    if missing := sorted(coin for coin in coins if not days.get(coin)):
        raise LiquidationsError(f"the response holds no closed day for {missing}")
    for coin, rows in days.items():
        frame = pl.DataFrame(
            {
                "ts": [datetime.fromtimestamp(t, tz=UTC) for t, _, _ in rows],
                "long_usd": [long for _, long, _ in rows],
                "short_usd": [short for _, _, short in rows],
            },
            schema={"ts": pl.Datetime("us", "UTC"), "long_usd": pl.Float64, "short_usd": pl.Float64},
        )
        (out_dir / coin).mkdir(parents=True)
        frame.write_parquet(out_dir / coin / "daily.parquet")
    return {coin: len(rows) for coin, rows in days.items()}


def liquidations_backfill(
    out_dir: Path = typer.Option(..., "--out", help="The new set's directory, refused if it exists."),
) -> None:
    """Fetch Coinalyze's daily liquidation history for the funding basket's 10 USDT perps, from 2018-01-01 to the last
    closed day (Coinalyze keeps about 1,500 days), into one parquet per coin under --out, reading $COINALYZE_API_KEY."""
    api_key = os.environ.get(API_KEY_ENV_VAR)
    if not api_key:
        logger.error("%s is required", API_KEY_ENV_VAR)
        raise typer.Exit(code=1)
    try:
        written = backfill_daily(api_key, COINS, out_dir)
    except LiquidationsError as exc:
        typer.echo(f"liquidations-backfill: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for coin, n_days in sorted(written.items()):
        typer.echo(f"{coin}: {n_days} days")
```

  In `cli/__main__.py`, `from cli.liquidations.coinalyze import liquidations_poll` becomes `from cli.liquidations.coinalyze import liquidations_backfill, liquidations_poll`, and `app.command(name="liquidations-backfill")(liquidations_backfill)` goes after `app.command(name="liquidations-poll")(liquidations_poll)`. **Author's call** — `poll_cycle`'s call is left as it is, passing no interval, so the poller's code is unchanged and its default is what it sends.

- [ ] **Step 4: `README.md`** — the table of contents gains `  - [`zcrypto liquidations-backfill`](#zcrypto-liquidations-backfill)` after its `zcrypto liquidations-poll` line, and before `### `zcrypto engine`<a name="zcrypto-engine"></a>`:

````markdown
### `zcrypto liquidations-backfill`<a name="zcrypto-liquidations-backfill"></a>

A one-shot fetch of Coinalyze's **daily** liquidation history for the same 10 USDT perps, from 2018-01-01 to the last day proven closed (`day_end <= now - 120s`), in one batched call. Coinalyze returns about 1,500 points at every interval, so the first day is whatever its window holds on the fetch day. Nothing is written unless every coin is present once, each with day stamps on 00:00Z, strictly increasing, and both legs finite and non-negative.

```bash
zcrypto liquidations-backfill --out <PATH>
```

| Option | Description |
| -- | -- |
| `--out <PATH>` | The new set's directory; refused if it exists. |

Requires `$COINALYZE_API_KEY` (exits with an error if unset). Writes `<out>/<COIN>/daily.parquet` with columns `ts` (the day's 00:00Z), `long_usd` and `short_usd`, and prints each coin's day count.
````

- [ ] **Step 5: Run them to verify they pass** — Step 2's command. Expected: `50 passed`; and `uv run pytest tests/test_liquidations_coinalyze.py -k "interval or daily_backfill or liquidations_backfill" -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` prints `15 passed, 35 deselected`, the fifteen new cases.

- [ ] **Step 6: Stage, consumers, gate** — `git add cli/liquidations/coinalyze.py cli/__main__.py tests/test_liquidations_coinalyze.py README.md`; `T` over the four paths (measured on the transcription: fifty-one files, `cli/__main__.py`'s readers among them, `5561 passed, 1 skipped, 305 deselected, 4 warnings` in 6 min 6 s, one plain call with `timeout` 600000 ms); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.

- [ ] **Step 7: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured on the transcription, seventeen of seventeen):

```bash
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation 's/&interval={interval}&/\&interval=1min\&/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_fetch_liquidation_history_sends_the_interval_it_is_given' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation 's/interval: str = "1min", opener/interval: str = "daily", opener/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_poll_cycle_requests_the_one_minute_interval' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def backfill_daily(/,/^def /s/if row\[0\] + _DAY_SECONDS <= now_s - _CLOSE_MARGIN_SECONDS\]/if row[0] <= now_s]/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_the_daily_backfill_writes_one_file_per_coin_of_its_closed_days' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def backfill_daily(/,/^def /s/interval="daily", opener=opener/interval="1min", opener=opener/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_the_daily_backfill_writes_one_file_per_coin_of_its_closed_days' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation 's/^_BACKFILL_FROM = datetime(2018, 1, 1, tzinfo=UTC)/_BACKFILL_FROM = datetime(2019, 1, 1, tzinfo=UTC)/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_the_daily_backfill_writes_one_file_per_coin_of_its_closed_days' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def backfill_daily(/,/^def /s/    if missing := sorted(coin for coin in coins if not days.get(coin)):/    if missing := []:/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_the_daily_backfill_refuses_a_response_it_cannot_trust_and_writes_nothing[a-coin-missing]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def backfill_daily(/,/^def /s/        if coin in days:/        if False:/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_the_daily_backfill_refuses_a_response_it_cannot_trust_and_writes_nothing[a-coin-twice]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation 's/    if not isinstance(payload, list):/    if False:/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_the_daily_backfill_refuses_a_response_it_cannot_trust_and_writes_nothing[a-non-list-body]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def backfill_daily(/,/^def /s/        if any(t % _DAY_SECONDS for t in stamps):/        if False:/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_the_daily_backfill_refuses_a_response_it_cannot_trust_and_writes_nothing[off-midnight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def backfill_daily(/,/^def /s/        if any(later <= earlier for earlier, later in zip(stamps, stamps\[1:\])):/        if False:/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_the_daily_backfill_refuses_a_response_it_cannot_trust_and_writes_nothing[non-monotone]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def backfill_daily(/,/^def /s/        except (KeyError, TypeError, ValueError) as exc:/        except (TypeError, ValueError) as exc:/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_the_daily_backfill_refuses_a_response_it_cannot_trust_and_writes_nothing[a-malformed-bucket]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def backfill_daily(/,/^def /s/        if not all(0.0 <= leg < float("inf") for/        if not all(not leg < 0.0 for/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_the_daily_backfill_refuses_a_response_it_cannot_trust_and_writes_nothing[a-non-finite-leg]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def backfill_daily(/,/^def /s/        if not all(0.0 <= leg < float("inf") for/        if not all(leg == leg for/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_the_daily_backfill_refuses_a_response_it_cannot_trust_and_writes_nothing[a-negative-leg]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def backfill_daily(/,/^def /s/    if out_dir.exists():/    if False:/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_the_daily_backfill_never_writes_over_a_set' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def liquidations_backfill(/,$s/    if not api_key:/    if False:/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_liquidations_backfill_requires_the_api_key' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def liquidations_backfill(/,$s/        typer.echo(f"{coin}: {n_days} days")/        typer.echo(f"{coin}: {n_days}")/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_liquidations_backfill_writes_the_ten_coins_and_prints_their_days' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/liquidations/coinalyze.py --control 's/^def backfill_daily(/def backfill_daily_gone(/' --mutation '/^def liquidations_backfill(/,$s/        typer.echo(f"liquidations-backfill: {exc}", err=True)/        typer.echo(f"{exc}", err=True)/' -- uv run pytest 'tests/test_liquidations_coinalyze.py::test_liquidations_backfill_exits_on_a_refusal_naming_it' -q -p no:cacheprovider --basetemp=.tmp/pt
```

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(liquidations): zcrypto liquidations-backfill — Coinalyze's daily liquidation history in one checked fetch, the poller's interval unchanged

<the task's pytest result line, pasted from its run over this tree>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<each probe: its infra/scripts/mutate-probe.sh command, then its verdict line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

______________________________________________________________________

### Task 3 (the controller's): the two frozen blocks, their attestations, the tape's coverage proof and the completed basis (D7, the completed basis)

**Files:** create `/home/zhaow/Projects/zcrypto-kraken/data/liquidations-frozen/` and `/home/zhaow/Projects/zcrypto-kraken/data/liquidations-daily/` (gitignored) and their links in this worktree's `data/`; modify `docs/reference/vouched-dataset-hashes.jsonl` (eleven lines, then ten), `docs/reference/data-catalog-full.md`, `zcrypto.toml` and `docs/specs/00138-b2-three-overlays-design.md`; scratch `.tmp/plan-00138/freeze-read-1.json`, `.tmp/plan-00138/freeze.out`, `.tmp/plan-00138/freeze-check.out`, `.tmp/plan-00138/backfill.out`, `.tmp/plan-00138/attest-daily.out`, `.tmp/plan-00138/daily-basis.out`.

**Interfaces:**
- Consumes: the live tree `/var/lib/zcrypto-ops/liquidations`, read-only — `<COIN>/liquidations-1m/<YYYY>/<MM>/<DD>/<HH>.parquet` finals, each beside `<HH>.parquet.sha256` whose first token is its bytes' sha256 (spec 00136's measured basis); Task 2's `zcrypto liquidations-backfill`; Task 1's `daily_zscore_grid_feature`; `subjects._b2_inputs`, `derisk_scales`, `per_year_engaged_counts`, `coverage_by_year`; `cli.ohlc.dataset.dataset_hash` and `write_parquet`; the sidecar's line shape (`dataset`, `dataset_sha256`, `first_ts`, `last_ts`, `relpath`, `rows`), which `cli/data/sync.py`'s `_sidecar_by_dataset` reads; `infra/scripts/grafana_auth.py`'s `vault_var`.
- Produces: the tape block — `<COIN>/buckets.parquet` for the ten coins and `covered-hours.parquet`, eleven files — and its eleven sidecar lines; `freeze.out` holding the coverage proof (D7); `freeze-check.out` the second read; the daily block — `<COIN>/daily.parquet` for the ten coins — and its ten sidecar lines; `daily-basis.out`, pasted into the spec as its completed basis.

- [ ] **Step 1: The gate** — each its own call: `git status --short` prints nothing; `test ! -e /home/zhaow/Projects/zcrypto-kraken/data/liquidations-frozen`, `test ! -e /home/zhaow/Projects/zcrypto-kraken/data/liquidations-daily`, `test ! -e data/liquidations-frozen` and `test ! -e data/liquidations-daily` each exit 0; `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/vouched-dataset-hashes.jsonl` exits 0, so develop has appended nothing to the sidecar since this branch's base.

- [ ] **Step 2: The freeze** — from this worktree's root, one call, about 15 s (measured on a transcription writing to scratch: 11 s):

```bash
mkdir -p .tmp/plan-00138 && uv run python - > .tmp/plan-00138/freeze.out 2>&1 <<'EOF'
import hashlib
import json
import math
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.ohlc.dataset import dataset_hash, write_parquet
from cli.registry.observed import ObservedReader
from cli.research import subjects

LIVE = Path("/var/lib/zcrypto-ops/liquidations")
OUT = Path("/home/zhaow/Projects/zcrypto-kraken/data/liquidations-frozen")
SIDECAR = Path("docs/reference/vouched-dataset-hashes.jsonl")
READ = Path(".tmp/plan-00138/freeze-read-1.json")
COINS = ("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP")
H = timedelta(hours=1)
FILE = re.compile(r"(\d{4})/(\d{2})/(\d{2})/(\d{2})\.(parquet|parquet\.sha256|.+)")
if OUT.exists():
    sys.exit(f"{OUT} exists: a freeze never writes over one")
if sorted(d.name for d in LIVE.iterdir() if d.is_dir()) != sorted(COINS):
    sys.exit("the live tree's coin directories are not the ten")
now = datetime.now(UTC)
closed_before = now.replace(minute=0, second=0, microsecond=0) - 31 * H
finals, digests, stray = {}, {}, []
for coin in COINS:
    tree = LIVE / coin / "liquidations-1m"
    finals[coin], digests[coin] = {}, {}
    for p in sorted(q for q in tree.rglob("*") if q.is_file()):
        m = FILE.fullmatch(p.relative_to(tree).as_posix())
        hour = datetime(*map(int, m.groups()[:4]), tzinfo=UTC) if m else None
        if hour is None or hour >= closed_before:
            if hour is None:
                stray.append(f"{coin}/{p.relative_to(tree)}")
            continue
        if m.group(5) == "parquet":
            manifest = p.with_name(p.name + ".sha256").read_text().split()[0]
            if hashlib.sha256(p.read_bytes()).hexdigest() != manifest:
                sys.exit(f"{coin}/{p.relative_to(tree)}: its bytes do not hash to its manifest")
            finals[coin][hour], digests[coin][hour.isoformat()] = p, manifest
        elif m.group(5) != "parquet.sha256":
            stray.append(f"{coin}/{p.relative_to(tree)}")
if stray:
    sys.exit(f"files neither a final nor its manifest, outside an hour or inside the closed span: {stray}")
held = set().union(*(set(f) for f in finals.values()))
first = min(held)
span = [first + k * H for k in range((closed_before - first) // H)]
holes = [h for h in span if h not in held]
asserted = [h for k, h in enumerate(span) if k and h in held and span[k - 1] in held and k + 1 < len(span) and span[k + 1] in held]
at = set(asserted)
bars = subjects._capturing_union(ObservedReader(Path("data")), "ohlc-full", 240, None, None, False)[0][:-1]
reach = sum(all(t + k * H in at for k in range(4)) for t in bars)
written = {}
for coin in COINS:
    frame = pl.concat([pl.read_parquet(p).with_columns(pl.lit(h).alias("hour")) for h, p in sorted(finals[coin].items())]).sort("ts")
    stamps = frame["ts"].dt.epoch("s")
    legs = [*frame["long_usd"].to_list(), *frame["short_usd"].to_list()]
    faults = {
        "off the minute": int((stamps % 60 != 0).sum()),
        "outside its file's hour": int((frame["ts"].dt.truncate("1h") != frame["hour"]).sum()),
        "repeated stamps": frame.height - frame["ts"].n_unique(),
        "nulls": int(frame.null_count().sum_horizontal().item()),
        "non-finite or negative legs": sum(not math.isfinite(x) or x < 0 for x in legs),
        "symbol or event_id off form": int(
            ((frame["symbol"] != f"{coin}USDT_PERP.A") | (frame["event_id"] != frame["symbol"] + "-" + stamps.cast(pl.String))).sum()
        ),
    }
    if any(faults.values()):
        sys.exit(f"{coin}: {faults}")
    written[f"{coin}/buckets.parquet"] = frame.drop("hour")
written["covered-hours.parquet"] = pl.DataFrame({"ts": asserted}, schema={"ts": pl.Datetime("us", "UTC")})
lines = []
for relpath, frame in written.items():
    write_parquet(frame, OUT / relpath)
    back = pl.read_parquet(OUT / relpath)
    row = {
        "dataset": "liquidations-frozen",
        "dataset_sha256": dataset_hash(back),
        "first_ts": str(back["ts"][0]),
        "last_ts": str(back["ts"][-1]),
        "relpath": relpath,
        "rows": back.height,
    }
    lines.append(json.dumps(row))
with SIDECAR.open("a", encoding="utf-8") as sidecar:
    sidecar.write("".join(f"{line}\n" for line in lines))
READ.parent.mkdir(parents=True, exist_ok=True)
READ.write_text(json.dumps({"read_at": now.isoformat(), "closed_before": closed_before.isoformat(), "digests": digests}))
print(f"read at {now:%Y-%m-%dT%H:%M:%SZ}; closed span {span[0]:%Y-%m-%dT%HZ} -> {span[-1]:%Y-%m-%dT%HZ}, {len(span)} hours, holes {[f'{h:%Y-%m-%dT%HZ}' for h in holes]}")
print(f"asserted hours {len(asserted)}, {asserted[0]:%Y-%m-%dT%HZ} -> {asserted[-1]:%Y-%m-%dT%HZ}")
print(f"the 4h grid's reach: {reach} of the frozen ohlc-full union's {len(bars)} bars hold four asserted hours")
for coin in COINS:
    hours = sorted(finals[coin])
    print(f"{coin}: finals {len(hours)}, {hours[0]:%Y-%m-%dT%HZ} -> {hours[-1]:%Y-%m-%dT%HZ}, buckets {written[f'{coin}/buckets.parquet'].height}")
print("\n".join(lines))
EOF
echo "exit $?"; cat .tmp/plan-00138/freeze.out
```

  Exit 0 prints the read's time, the closed span and its holes, the asserted hours, the 4h grid's reach — the frozen `ohlc-full` union's bars whose four hours are asserted (D7's coverage proof) — each coin's finals, first and last, and buckets, and the eleven sidecar lines it appended. Any `sys.exit` — a target that exists, a coin directory missing, a final whose bytes miss its manifest, a stray file in the span, a bucket fault — wrote nothing, and is the owner's question with its line quoted. A traceback can leave a partial block: where `/home/zhaow/Projects/zcrypto-kraken/data/liquidations-frozen` exists, `rm -r` of it (the block this step wrote, no other) and `git checkout -- docs/reference/vouched-dataset-hashes.jsonl`, each its own call, then this step once more; a second traceback is the owner's question.

- [ ] **Step 3: The second read** — at least 600 s after step 2's read, so a whole poll cycle runs between the reads, as its own background call, acted on at its notification:

```bash
uv run python - > .tmp/plan-00138/freeze-check.out 2>&1 <<'EOF'
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

LIVE = Path("/var/lib/zcrypto-ops/liquidations")
READ = Path(".tmp/plan-00138/freeze-read-1.json")
first = json.loads(READ.read_text())
closed_before = datetime.fromisoformat(first["closed_before"])
elapsed = (datetime.now(UTC) - datetime.fromisoformat(first["read_at"])).total_seconds()
if elapsed < 600:
    sys.exit(f"{elapsed:.0f} s since the first read: the second waits two of the poller's 300 s sleeps, 600 s")
now = {}
for coin in first["digests"]:
    tree = LIVE / coin / "liquidations-1m"
    now[coin] = {}
    for p in tree.rglob("*.parquet.sha256"):
        y, m, d, h = (int(x) for x in [*p.relative_to(tree).parts[:3], p.name.split(".")[0]])
        hour = datetime(y, m, d, h, tzinfo=UTC)
        if hour < closed_before:
            now[coin][hour.isoformat()] = p.read_text().split()[0]
if now != first["digests"]:
    changed = {coin: sorted(set(now[coin].items()) ^ set(first["digests"][coin].items())) for coin in now if now[coin] != first["digests"][coin]}
    sys.exit(f"the live tree's closed span changed since the copy: {changed}")
print(f"{elapsed:.0f} s after the copy, the live tree's closed span holds the same {sum(map(len, now.values()))} finals and manifests")
EOF
echo "exit $?"; cat .tmp/plan-00138/freeze-check.out
```

  Exit 0 prints that the closed span's finals and manifests are unchanged since the copy. An exit on the 600 s floor is re-run later. An exit on a changed span means a final reached the span after the copy: `rm -r /home/zhaow/Projects/zcrypto-kraken/data/liquidations-frozen` (the block this task wrote, no other) and `git checkout -- docs/reference/vouched-dataset-hashes.jsonl`, each its own call, then steps 2 and 3 once more; a second change is the owner's question.

- [ ] **Step 4: Link and read back the tape block** — `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/liquidations-frozen data/liquidations-frozen` (`-n`, so an existing link is refused, never followed); then `uv run python -c 'from pathlib import Path; from cli.registry.observed import ObservedReader; r = ObservedReader(Path("data")); [r.read_series("liquidations-frozen", p) for p in ["covered-hours.parquet", *(f"{c}/buckets.parquet" for c in ("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP"))]]; print(r.vouched_status(), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in r.block().items()})'` prints `{'liquidations-frozen': 'checked (11 vouched hashes)'}` and the eleven files.

- [ ] **Step 5: The daily fetch** — the one Coinalyze call and the one vault read of this plan, one call from this worktree's root, the key set for the backfill's process alone and never printed:

```bash
COINALYZE_API_KEY="$(uv run python -c 'import sys; sys.path.insert(0, "/home/zhaow/Projects/zcrypto-kraken/infra/scripts"); import grafana_auth; print(grafana_auth.vault_var("coinalyze_api_key", "host_vars/zcrypto-ops/vault.yml"))')" uv run zcrypto liquidations-backfill --out /home/zhaow/Projects/zcrypto-kraken/data/liquidations-daily > .tmp/plan-00138/backfill.out 2>&1; echo "exit $?"; date -u +%FT%TZ; cat .tmp/plan-00138/backfill.out
```

  Exit 0 prints each coin's day count; the stamp is the fetch's, the catalog's. Exit 1 on the log line `COINALYZE_API_KEY is required` is the vault read failing, nothing fetched: the controller's environment, re-run once it reads. `liquidations-backfill: <cause>` wrote nothing and is the owner's question with its line quoted. A traceback can leave some coins written: where `/home/zhaow/Projects/zcrypto-kraken/data/liquidations-daily` exists, `rm -r` of it (the block this step wrote, no other), its own call, then this step once more; a second traceback is the owner's question. **Author's call** — `date` runs after the fetch, so the stamp the catalog carries is never earlier than the response.

- [ ] **Step 6: The daily attestation** — one call:

```bash
uv run python - > .tmp/plan-00138/attest-daily.out 2>&1 <<'EOF'
import json
import sys
from pathlib import Path

import polars as pl

from cli.ohlc.dataset import dataset_hash

ROOT = Path("/home/zhaow/Projects/zcrypto-kraken/data/liquidations-daily")
SIDECAR = Path("docs/reference/vouched-dataset-hashes.jsonl")
COINS = ("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP")
files = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file())
if files != [f"{coin}/daily.parquet" for coin in COINS]:
    sys.exit(f"the block holds {files}, not one daily.parquet per coin")
if any(json.loads(line)["dataset"] == "liquidations-daily" for line in SIDECAR.read_text().splitlines() if line.strip()):
    sys.exit("the sidecar already attests liquidations-daily: a block is attested once")
lines = []
for relpath in files:
    frame = pl.read_parquet(ROOT / relpath)
    row = {
        "dataset": "liquidations-daily",
        "dataset_sha256": dataset_hash(frame),
        "first_ts": str(frame["ts"][0]),
        "last_ts": str(frame["ts"][-1]),
        "relpath": relpath,
        "rows": frame.height,
    }
    lines.append(json.dumps(row))
with SIDECAR.open("a", encoding="utf-8") as sidecar:
    sidecar.write("".join(f"{line}\n" for line in lines))
print("\n".join(lines))
EOF
echo "exit $?"; cat .tmp/plan-00138/attest-daily.out
```

  Exit 0 prints the ten sidecar lines it appended. A `sys.exit` appended nothing and is the owner's question.

- [ ] **Step 7: Link and read back the daily block** — `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/liquidations-daily data/liquidations-daily`; then `uv run python -c 'from pathlib import Path; from cli.registry.observed import ObservedReader; r = ObservedReader(Path("data")); [r.read_series("liquidations-daily", f"{c}/daily.parquet") for c in ("ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP")]; print(r.vouched_status(), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in r.block().items()})'` prints `{'liquidations-daily': 'checked (10 vouched hashes)'}` and the ten files.

- [ ] **Step 8: The catalog entries** — in `docs/reference/data-catalog-full.md`, after the `### Binance liquidations, 1-minute buckets` section and before `## private`, one line per paragraph and list item, the bracketed values read off `freeze.out`, `backfill.out`, `attest-daily.out` and step 7's line:

```markdown
### Binance liquidations, frozen block (`data/liquidations-frozen/`, the live tape's closed span to <the last asserted hour>; written once)

- **Producer:** the freeze of spec/plan `00138` (D7, Task 3): one read-only copy of the live tree's (coin, hour) finals of every hour starting 31 h or more before its read at <the read's time>, each final's bytes checked against its manifest, every bucket checked, the tree read again 600 s later, a whole poll cycle between, and found unchanged over that span.
- **Schema:** `<COIN>/buckets.parquet` — the coin's closed-span finals concatenated in stamp order, the live schema `ts, symbol, long_usd, short_usd, event_id`; `covered-hours.parquet` — one `ts` column, the hours asserted covered for every coin: each hour of the closed span that some coin's final holds, but its first and last, partial ones, and the held hours beside a hole (<n> hours, <first> → <last>).
- **Attestation:** eleven path-bound lines in `docs/reference/vouched-dataset-hashes.jsonl`, each file's `dataset_hash`, which `ObservedReader` checks on every read; no manifest. Never rewritten: a re-freeze is a new name under a new spec.
- **Caveats:** the live stream's lower bound, and the coverage assertion's own: the hours at which spec `00138` D7 says a coin can read low. In `zcrypto.toml`'s `authored_sets`: pushed once to the hub's `hot/`, where `data fetch` carries it to each research node.
- **Consumers:** `b2-liq-tape-reading` (spec `00138` D12); <the 4h grid's reach, off `freeze.out`> of the frozen `ohlc-full` union's bars hold four asserted hours.

### Binance liquidations, daily history (`data/liquidations-daily/`, Coinalyze's daily window <the first day> → <the last day>; written once)

- **Producer:** `zcrypto liquidations-backfill` (spec/plan `00138`, D7, Task 3), run once at <the fetch's stamp>: one batched Coinalyze `/v1/liquidation-history` call at `interval=daily`, `convert_to_usd=true`, for the ten `<COIN>USDT_PERP.A` symbols from 2018-01-01, the days kept once ended 120 s or more before the fetch; Coinalyze's window of about 1,500 points set the first day.
- **Schema:** `<COIN>/daily.parquet` — `ts` (the day's 00:00Z), `long_usd`, `short_usd`, a row per day the response held (<the rows per coin>).
- **Attestation:** ten path-bound lines in `docs/reference/vouched-dataset-hashes.jsonl`, each file's `dataset_hash`, which `ObservedReader` checks on every read. Never rewritten: a second fetch can return another window, so it is another block, under a new name and a new spec.
- **Caveats:** Coinalyze's day aggregate of Binance's feed, which reports at most the largest liquidation per 1000 ms per symbol, so a lower bound; a day the response lacks is a gap (<the days missing per coin: each file's span in days less its rows, off `attest-daily.out`>). In `zcrypto.toml`'s `authored_sets`: pushed once to the hub's `hot/`, where `data fetch` carries it to each research node.
- **Consumers:** `b2-liq-derisk` and its pre-flight (spec `00138` D6).
```

- [ ] **Step 9: `authored_sets` and the gate** — in `zcrypto.toml`, `authored_sets` gains `"liquidations-frozen", "liquidations-daily"` after `"snapshots"` (D7's hub); `git add docs/reference/vouched-dataset-hashes.jsonl docs/reference/data-catalog-full.md zcrypto.toml`; `T` over the three paths, fourteen files — the sidecar's `tests/test_data_vouched_sidecar.py` and `tests/test_manifest_conformance.py` (measured on the transcription with the first draft's eleven scratch-freeze lines and the ten a synthetic backfill's attestation wrote: `18 passed, 5 deselected`) and the twelve readers of `zcrypto.toml` (all fourteen measured with that line edited: `1604 passed, 60 deselected, 44 warnings`); `uv run pre-commit run -a` until clean.

- [ ] **Step 10: Commit**

```bash
git commit -F - <<'EOF'
feat(data): the two frozen liquidation blocks — the live tape's closed span in eleven files and Coinalyze's daily history in ten, attested in the sidecar, catalogued and listed in authored_sets

<freeze.out, whole>
<freeze-check.out, whole>
<step 4's read-back line>
<backfill.out, whole, with the fetch's stamp>
<attest-daily.out, whole>
<step 7's read-back line>
<the gate's pytest result line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 11: The daily-basis program** — one background call, acted on at its notification:

```bash
date -u +%FT%TZ; uv run python - > .tmp/plan-00138/daily-basis.out 2>&1 <<'EOF'
import json
from datetime import timedelta
from pathlib import Path

from cli.alpha.b2 import B2Config, daily_zscore_grid_feature, derisk_scales, per_year_engaged_counts
from cli.features.derivatives import coverage_by_year
from cli.registry.observed import ObservedReader
from cli.research import subjects

TRIAL_2_SHARE = 3_486 / 70_682  # spec 00137's measured basis, the share D3's rule aims at
inputs = subjects._b2_inputs(ObservedReader(Path("data")), "ohlc-full", None, None, False, subject="b2-liq-daily-basis")
close, arm_a, n = inputs.close, inputs.arm_a, len(inputs.close)
reader = ObservedReader(Path("data"))
signal = {}
for asset in subjects._ASSETS:
    rows = reader.read_series("liquidations-daily", f"{asset}/daily.parquet")
    ts, long_usd, short_usd = rows["ts"].to_list(), rows["long_usd"].to_list(), rows["short_usd"].to_list()
    span = (ts[-1] - ts[0]) // timedelta(days=1) + 1
    inside = sum(t + timedelta(days=1) <= close[-1] for t in ts)
    print(
        f"{asset}: days {len(ts)}, {ts[0]:%Y-%m-%d} -> {ts[-1]:%Y-%m-%d}, days missing between {span - len(ts)}, "
        f"days ended by the union's last close {inside}, long share of the notional {sum(long_usd) / (sum(long_usd) + sum(short_usd)):.3f}"
    )
    signal[asset] = daily_zscore_grid_feature(ts, long_usd, inputs.h4_ts)
print("block", {d: (len(e["files"]), e["rows"], e["span"]) for d, e in reader.block().items()}, reader.vouched_status())
held = [z for a in subjects._ASSETS for p, z in zip(arm_a[a], signal[a]) if p > 0 and z is not None]
shares = {t: sum(z > t for z in held) / len(held) for t in (2.0, 2.5)}
threshold = min((2.5, 2.0), key=lambda t: abs(shares[t] - TRIAL_2_SHARE))
for t in (2.0, 2.5):
    print(f"long asset-stamps where the signal is defined {len(held)}; engaged above {t}: {sum(z > t for z in held)} ({100 * shares[t]:.2f} %)")
print(f"trial 2's share {100 * TRIAL_2_SHARE:.2f} %: the rule takes {threshold}")
scales = derisk_scales(signal, config=B2Config(z_threshold=threshold))
start = next((k for k in range(n) if all(signal[a][k] is not None for a in subjects._ASSETS)), n)
print(f"first close every asset's signal holds: index {start}, close {close[start] if start < n else None}, returns from it {n - start}")
basis = {
    "engaged_per_asset": {a: sum(p > 0 and s < 1 for p, s in zip(arm_a[a], scales[a])) for a in subjects._ASSETS},
    "engaged_per_year": per_year_engaged_counts(arm_a, scales, close),
    "binperp_liq_long_z30d_coverage": {
        a: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(close, signal[a]).items()} for a in subjects._ASSETS
    },
    "primary_returns": n - start,
    "threshold": threshold,
}
print("engaged per asset", basis["engaged_per_asset"], "per close year", basis["engaged_per_year"])
print("DAILY_BASIS " + json.dumps(basis))
EOF
echo "exit $?"; grep -c '^DAILY_BASIS {' .tmp/plan-00138/daily-basis.out; cat .tmp/plan-00138/daily-basis.out
```

  Exit 0 and a count of 1: step 12; the stamp printed first is the run's. Measured on the transcription over a synthetic block: 75 s. Its block line must name `liquidations-daily` alone and its `vouched_status` `checked (10 vouched hashes)`; a `first close every asset's signal holds` at `None`, or an engaged total of 0 at the rule's pick, is the dead knob D10 (d) would stop on, and the owner's question before the hash.

- [ ] **Step 12: The completed basis** — in `docs/specs/00138-b2-three-overlays-design.md`, under `## The completed basis (the controller's, after the daily fetch)`, after its paragraph and before `## Operating model`, one line — `The plan's Task 3 step 11 program over the attested block, run at <step 11's stamp>, the fetch at <step 5's stamp>:` — and a fenced block holding `daily-basis.out` whole, its `DAILY_BASIS` line unindented; then `grep -c '^DAILY_BASIS ' docs/specs/00138-b2-three-overlays-design.md` prints 1; `git add docs/specs/00138-b2-three-overlays-design.md`; `T` over it; `uv run pre-commit run -a` until clean; committed alone:

```bash
git commit -F - <<'EOF'
docs(specs): 00138 — the completed basis: the daily block's coverage, the engagement at 2.0 and 2.5, the threshold the rule picks and the window's start

<daily-basis.out's lines but the DAILY_BASIS line, whole>
<the gate's pytest result line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

______________________________________________________________________

### Task 4: the seven subjects — three trials, their pre-flight twins and the tape's reading (D8, D9, D12)

**Files:**
- Modify: `cli/research/subjects.py` — the imports; the overlay and reading machinery after `_B2_FULL_PREFLIGHT_KEYS` and before `SUBJECTS`; seven entries at the end of `SUBJECTS`
- Modify: `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`

**Interfaces:**
- Consumes: Task 1's five functions; `cli/research/subjects.py` as `a9c8be5d1` holds it — `_capturing_union`, `_b2_over`, `_b2_returns`, `_b2_slices`, `_b2_full_metrics(inputs)`, `_B2Inputs`, `_B2_METRIC_KEYS`, `_B2_FULL_PREFLIGHT_KEYS`, `_B2_ARM_A_BAR_KEYS`, `_B2_ARM_A_BAR_FLAGS`, `_B2_COST_PER_SIDE`, `_B2_A2_ARMS`, `_B2_LOOKBACK`, `_DECISIVE_START`, `_N_RESAMPLES`, `_FROM_2021`, `_B2_FULL_N_TRIALS`, `_ASSETS`, `PPY_4H`, `SubjectError`, `Subject`, `ObservedReader`, and the names it imports (`a1_kill_bar`, `net_of_cost_verdict`, `net_of_cost`, `scale_positions`, `derisk_scales`, `B2Config`, `benchmark_4h_net_of_cost`, `calendar_year_slices`, `per_year_engaged_counts`, `per_year_positions_differ`, `per_year_turnover`, `per_year_max_drawdown`, `book_turnover`, `coverage_by_year`, `close_grid`, `max_drawdown`, `sharpe`, `a2_book_returns`, `A2Config`, `_ffill_btc`, `statistics`, `PERP_SYMBOLS`, `pl`, `AlphaError`, `FeatureError`, `ValidationError`), each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; `cli/research/command.py`'s `eval_subject` (spec 00133: a plain eval of a ruled subject refused before any read, `--n-trials` other than `Subject.n_trials` refused, a count below `required_n` refused, a dirty tree refused under `--register`; a rolling dataset read with `--as-of`); in the tests, `_anchor`, `_as_trial`, `_rolling_set`, `_recording`, `_block_and_metrics`, `_b2_ohlc_rows`, `_fake_kill_bar`, `_fake_benchmark`, `_fake_head_to_head`, `_B2_START`, `_B2_BARS`, `_B2_FALLS`, `_B2_FUNDING_FROM`, `_B2_NEVER_SPIKES`, `_B2_SPOILT`, `_B2_ASSETS`, `_B2_METRIC_KEYS`, `_B2_FULL_PREFLIGHT_KEYS`, `_ARM_A_BAR_KEYS`, `_ARM_A_BAR_FLAGS`, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `_CONTRACT_DATASETS`.
- Produces:

```python
# cli/research/subjects.py
_B2_OI_N_TRIALS = 2; _B2_RATIO_N_TRIALS = 3; _B2_LIQ_N_TRIALS = 4
_B2_OI_THRESHOLD = 2.5; _B2_RATIO_THRESHOLD = 2.5
_B2_LIQ_SET = "liquidations-daily"
_B2_TRIAL_2_ENGAGED_SHARE = 3_486 / 70_682
class _B2OverlayInputs(NamedTuple): h4_ts, h4_prices, close, arm_a, signal, scales, threshold
def _b2_oi_signal(reader, h4_ts) -> dict[str, list[float | None]]: ...
def _b2_ratio_signal(reader, h4_ts) -> dict[str, list[float | None]]: ...
def _b2_liq_signal(reader, h4_ts) -> dict[str, list[float | None]]: ...
def _b2_engagement_threshold(signal, arm_a) -> float: ...
def _b2_overlay_inputs(subject, read_signal, threshold, reader, dataset, window, accept_holes) -> _B2OverlayInputs: ...  # threshold a float or the rule
def _b2_overlay_start(inputs) -> int: ...
def _b2_overlay_arm_a_bar(inputs, *, n_trials) -> tuple[dict, list[float], list[float]]: ...
def _b2_overlay_engagement(inputs, signal_key) -> dict: ...
def _b2_overlay_metrics(inputs, *, signal_key, n_trials) -> dict: ...  # 42 keys
def _b2_overlay_preflight_metrics(inputs, *, signal_key, n_trials) -> dict: ...  # 22 keys
def _b2_overlay_build(subject, signal_key, read_signal, threshold, compute, n_trials, reader, dataset, window, as_of, accept_holes) -> dict: ...
def _build_b2_oi_derisk(...), _build_b2_oi_derisk_preflight(...), _build_b2_ratio_derisk(...), _build_b2_ratio_derisk_preflight(...), _build_b2_liq_derisk(...), _build_b2_liq_derisk_preflight(...) -> dict
def _b2_overlay_verdict(m: dict) -> str | None: ...
def _b2_overlay_metric_keys(signal_key: str) -> frozenset[str]: ...
def _b2_overlay_preflight_keys(signal_key: str) -> frozenset[str]: ...
_B2_TAPE_SET = "liquidations-frozen"; _B2_TAPE_ZSCORE_HOURS = 720; _B2_TAPE_THRESHOLD = 2.0; _B2_TAPE_HORIZONS = (1, 4, 24); _B2_TAPE_BLOCK = 24
def _b2_tape_reads(reader) -> tuple[list[datetime], dict[str, tuple[list, list, list]]]: ...
def _b2_tape_forwards(hours, hourly, quarters, quarterly) -> dict[str, dict[str, list[float | None]]]: ...
def _build_b2_liq_tape_reading(reader, dataset, window, as_of=None, accept_holes=False) -> dict: ...  # 12 keys
_B2_TAPE_KEYS: frozenset[str]
```

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - the `from cli.alpha.b2 import (` block gains `daily_zscore_grid_feature,` after `B2Config,`, `liquidation_hourly_totals,` after `derisk_scales,`, `oi_zscore_grid_feature,` after `net_of_cost,`, and `ratio_max_signal,` and `ratio_zscore_grid_features,` after `per_year_turnover,`;
  - `from cli.data import sync` goes after `from cli.benchmark.errors import BenchmarkError`, and `from cli.features.derivatives import coverage_by_year` becomes `from cli.features.derivatives import coverage_by_year, funding_zscore`;
  - `test_each_subject_declares_the_metric_keys_its_build_returns` ends with:

```python
    for name, (signal_key, _, _) in _B2_OVERLAYS.items():
        assert subjects.SUBJECTS[name].metric_keys == _overlay_metric_keys(signal_key)
        assert subjects.SUBJECTS[f"{name}-preflight"].metric_keys == _overlay_preflight_keys(signal_key)
    assert subjects.SUBJECTS["b2-liq-tape-reading"].metric_keys == _B2_TAPE_SPEC_KEYS
```

  - after `test_the_b2_full_subject_refuses_a_funding_file_it_cannot_read_naming_it` and before the comment `# Records 45 and 46's metric keys (docs/specs/00130 D3), pinned against the committed records below.`:

```python
_B2_OVERLAY_SPEC = "docs/specs/00138-b2-three-overlays-design.md"
_B2_OVERLAY_NO_VERDICT = (
    "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, the trial unspent"
)
# Spec 00138's three trials: each signal's key, threshold and count, typed from the spec, never read off a subject; the
# liquidations trial's threshold is the one its build reads off the engagement rule, `None` here.
_B2_OVERLAYS = {
    "b2-oi-derisk": ("binperp_oi_z30d", 2.5, 2),
    "b2-ratio-derisk": ("binperp_ratio_max_z30d", 2.5, 3),
    "b2-liq-derisk": ("binperp_liq_long_z30d", None, 4),
}
_B2_OVERLAY_RATIOS = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)
_B2_OVERLAY_FROM_BAR = 300
_B2_OVERLAY_SPIKE_BARS = 12


def _overlay_metric_keys(signal_key: str) -> frozenset[str]:
    moved = {"head_to_head_mean_outperf_2021", "head_to_head_spa_p_2021", "binperp_funding_z30d_coverage"}
    return frozenset(_B2_METRIC_KEYS - moved) | {
        "head_to_head_mean_outperf_primary",
        "head_to_head_spa_p_primary",
        "primary_returns",
        "threshold",
        f"{signal_key}_coverage",
    }


def _overlay_preflight_keys(signal_key: str) -> frozenset[str]:
    return (_B2_FULL_PREFLIGHT_KEYS - {"binperp_funding_z30d_coverage"}) | {
        "primary_returns",
        "threshold",
        f"{signal_key}_coverage",
    }


def _overlay_threshold(name: str):
    threshold = _B2_OVERLAYS[name][1]
    return subjects._b2_engagement_threshold if threshold is None else threshold


def _overlay_signal(name: str):
    return {
        "b2-oi-derisk": subjects._b2_oi_signal,
        "b2-ratio-derisk": subjects._b2_ratio_signal,
        "b2-liq-derisk": subjects._b2_liq_signal,
    }[name]


@pytest.fixture(autouse=True)
def _liquidations_blocks_unattested(monkeypatch):
    """Keeps the read guard inert over a fixture's synthetic `liquidations-daily` and `liquidations-frozen`."""
    attested = sync._sidecar_by_dataset()
    blocks = ("liquidations-daily", "liquidations-frozen")
    monkeypatch.setattr(sync, "_sidecar_by_dataset", lambda: {name: s for name, s in attested.items() if name not in blocks})


def _b2_overlay_dataset(
    tmp_path: Path, *, start: datetime = _B2_START, flat: bool = False, from_bar: int = _B2_OVERLAY_FROM_BAR
) -> Path:
    """`_b2_dataset`'s ten 4h series, a `derivatives-oi` set and a daily liquidations block, each running 30 days past the
    union: BTC's OI rows open 47 days before it, every other asset's at bar `from_bar` and the daily rows at the first day
    after it; every asset but one spikes in its OI level and one of its four ratios for twelve bars, and in its long
    notional for two days, from its own bar inside the second fall, so each overlay de-risks each asset at its own
    stamps."""
    root = tmp_path / "data"
    for i, asset in enumerate(_B2_ASSETS):
        write_parquet(to_frame(_b2_ohlc_rows(i * 0.7, start, flat)), root / "ohlc-test" / f"{asset}/EUR/240.parquet")
    opens, end = start + timedelta(hours=4 * from_bar), start + timedelta(hours=4 * _B2_BARS, days=30)
    day0 = (opens + timedelta(days=1)).replace(hour=0)
    days = [day0 + timedelta(days=d) for d in range((end - day0) // timedelta(days=1))]
    for i, asset in enumerate(_B2_ASSETS):
        spike = start + timedelta(hours=4 * (_B2_FALLS[1][0] + 2 * i))

        def hot(t: datetime) -> bool:
            return asset != _B2_NEVER_SPIKES and spike <= t < spike + timedelta(hours=4 * _B2_OVERLAY_SPIKE_BARS)

        first = _B2_FUNDING_FROM if asset == "BTC" else opens
        marks = [first + timedelta(hours=4 * j) for j in range((end - first) // timedelta(hours=4))]
        columns = {
            "ts": marks,
            "sum_open_interest": [2_000.0 if hot(t) else 1_000.0 + 10 * math.sin(j / 3 + i) for j, t in enumerate(marks)],
            "sum_open_interest_value": [1e7] * len(marks),
        }
        for c, ratio in enumerate(_B2_OVERLAY_RATIOS):
            columns[ratio] = [3.0 if hot(t) and c == i % 4 else 1.0 + 0.05 * math.sin(j / 5 + i + c) for j, t in enumerate(marks)]
        schema = {"ts": pl.Datetime("us", "UTC")} | dict.fromkeys(list(columns)[1:], pl.Float64)
        write_parquet(pl.DataFrame(columns, schema=schema), root / "derivatives-oi" / PERP_SYMBOLS[asset] / "oi.parquet")
        spike_day = spike.replace(hour=0)
        daily = {
            "ts": days,
            "long_usd": [
                1e7
                if asset != _B2_NEVER_SPIKES and spike_day <= d <= spike_day + timedelta(days=1)
                else 1e4 + 3e3 * math.sin(k / 3 + i)
                for k, d in enumerate(days)
            ],
            "short_usd": [8e3 + 2e3 * math.cos(k / 5 + i) for k in range(len(days))],
        }
        schema = {"ts": pl.Datetime("us", "UTC"), "long_usd": pl.Float64, "short_usd": pl.Float64}
        write_parquet(pl.DataFrame(daily, schema=schema), root / "liquidations-daily" / asset / "daily.parquet")
    return root


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
def test_each_b2_overlay_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count(name):
    signal_key, _, count = _B2_OVERLAYS[name]
    trial, preflight = subjects.SUBJECTS[name], subjects.SUBJECTS[f"{name}-preflight"]
    builder = f"_build_{name.replace('-', '_')}"
    assert (len(_overlay_metric_keys(signal_key)), len(_overlay_preflight_keys(signal_key))) == (42, 22)
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        name,
        (240,),
        _B2_ASSETS,
        _B2_OVERLAY_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is getattr(subjects, builder) and trial.metric_keys == _overlay_metric_keys(signal_key)
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b2_overlay_verdict, _B2_OVERLAY_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B2", count)
    assert (preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == ((240,), _B2_ASSETS, _B2_OVERLAY_SPEC, (42,))
    assert preflight.build is getattr(subjects, f"{builder}_preflight")
    assert preflight.metric_keys == _overlay_preflight_keys(signal_key)
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5


# Adopting on every key the rule reads, the full-window head-to-head and the block-102 cell set against the verdict, so a
# rule reading either in place of the primary read or the headline cell moves the first row.
_B2_OVERLAY_ADOPTING = {
    "arm_a_passes": 1,
    "engaged_per_year": {"2013": 0, "2023": 4},
    "passes": 1,
    "head_to_head_mean_outperf_primary": 0.001,
    "head_to_head_spa_p_primary": 0.01,
    "head_to_head_mean_outperf_full": -0.001,
    "head_to_head_spa_p_full": 0.9,
    "spa_p_decisive_b102_s42": 0.9,
    "max_drawdown_reduction_pct": 5.0,
}
_B2_OVERLAY_NEVER_ENGAGED = {"engaged_per_year": {"2013": 0, "2023": 0}}


@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="row-1-outperforms-significantly-from-the-start-and-draws-down-less"),
        pytest.param({"head_to_head_spa_p_primary": 0.0499}, "adopt", id="row-1-p-at-0.0499"),
        pytest.param({"max_drawdown_reduction_pct": 2e-6}, "adopt", id="row-1-reduction-past-1e-6"),
        pytest.param({"head_to_head_spa_p_primary": 0.2}, "park", id="row-2-outperforms-insignificantly-from-the-start"),
        pytest.param({"head_to_head_spa_p_primary": 0.05}, "park", id="row-2-p-at-exactly-0.05"),
        pytest.param({"head_to_head_mean_outperf_primary": -0.001}, "reject", id="row-3-underperforms-from-the-start"),
        pytest.param({"head_to_head_mean_outperf_primary": 0.0}, "reject", id="row-3-mean-at-exactly-0"),
        pytest.param({"max_drawdown_reduction_pct": -5.0}, "reject", id="row-3-draws-down-more"),
        pytest.param({"max_drawdown_reduction_pct": 1e-6}, "reject", id="row-3-reduction-at-exactly-1e-6"),
        pytest.param(
            {"head_to_head_mean_outperf_primary": -0.001, "head_to_head_mean_outperf_full": 0.001, "head_to_head_spa_p_full": 0.01},
            "reject",
            id="row-3-outperforms-over-the-full-window-alone",
        ),
        pytest.param({"passes": 0}, "reject", id="row-4-arm-b-fails-its-bar"),
        pytest.param({"arm_a_passes": 0}, None, id="arm-a-fails-its-bar"),
        pytest.param(_B2_OVERLAY_NEVER_ENGAGED, None, id="the-overlay-never-engages"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="arm-a-read-before-passes"),
        pytest.param({**_B2_OVERLAY_NEVER_ENGAGED, "passes": 0}, None, id="engagement-read-before-passes"),
    ],
)
def test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop(change, verdict):
    assert subjects._b2_overlay_verdict({**_B2_OVERLAY_ADOPTING, **change}) == verdict


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
def test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count(tmp_path, monkeypatch, name):
    signal_key, threshold, count = _B2_OVERLAYS[name]
    scalings = _recording(monkeypatch, "derisk_scales", lambda arguments, result: result)
    reader = ObservedReader(_b2_overlay_dataset(tmp_path))
    inputs = subjects._b2_overlay_inputs(name, _overlay_signal(name), _overlay_threshold(name), reader, "ohlc-test", None, False)
    start = next(k for k in range(len(inputs.close)) if all(inputs.signal[a][k] is not None for a in _B2_ASSETS))
    assert 0 < start < len(inputs.close) - 2
    ruled = subjects._b2_engagement_threshold(inputs.signal, inputs.arm_a) if threshold is None else threshold
    assert [(arguments["z_by_asset"], arguments["config"]) for arguments, _ in scalings] == [
        (inputs.signal, B2Config(z_threshold=ruled))
    ]
    assert inputs.threshold == ruled
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects._b2_overlay_metrics(inputs, signal_key=signal_key, n_trials=count)

    assert set(metrics) == _overlay_metric_keys(signal_key) and {arguments["n_trials"] for arguments, _ in bars} == {count}
    # Trial 2's metrics over the same positions and signal, its from-2021 read moved to this signal's start and its count to
    # this trial's: `_b2_full_metrics`' own test proves it against a hand computation.
    monkeypatch.setattr(subjects, "_FROM_2021", inputs.close[start])
    monkeypatch.setattr(subjects, "_B2_FULL_N_TRIALS", count)
    trial_2 = subjects._b2_full_metrics(subjects._B2Inputs(*inputs[:6]))
    renamed = {
        "head_to_head_mean_outperf_2021": "head_to_head_mean_outperf_primary",
        "head_to_head_spa_p_2021": "head_to_head_spa_p_primary",
        "binperp_funding_z30d_coverage": f"{signal_key}_coverage",
    }
    assert {renamed.get(key, key): value for key, value in trial_2.items()} | {
        "primary_returns": len(inputs.close) - start,
        "threshold": ruled,
    } == metrics


def test_where_no_signal_crosses_its_threshold_a_b2_overlays_arm_b_is_arm_a_bit_for_bit(tmp_path, monkeypatch):
    reader = ObservedReader(_b2_overlay_dataset(tmp_path))
    inputs = subjects._b2_overlay_inputs("b2-oi-derisk", subjects._b2_oi_signal, 2.5, reader, "ohlc-test", None, False)
    calm = {a: [0.0] * len(inputs.close) for a in _B2_ASSETS}
    inputs = inputs._replace(signal=calm, scales=derisk_scales(calm, config=B2Config(z_threshold=2.5)))
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    head_to_heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    metrics = subjects._b2_overlay_metrics(inputs, signal_key="binperp_oi_z30d", n_trials=2)

    assert [arguments["book_net_of_cost"] == arguments["benchmark_net_of_cost"] for arguments, _ in head_to_heads] == [True] * 2
    assert (
        metrics["stamps_positions_differ"],
        metrics["turnover_b"],
        metrics["max_drawdown"],
        metrics["max_drawdown_reduction_pct"],
    ) == (
        0,
        metrics["turnover_a"],
        metrics["arm_a_max_drawdown"],
        0.0,
    )
    assert metrics["primary_returns"] == len(inputs.close) and set(metrics["engaged_per_year"].values()) == {0}


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
def test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b(tmp_path, monkeypatch, name):
    signal_key, threshold, count = _B2_OVERLAYS[name]
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)

    def arm_b(*args, **kwargs):
        raise AssertionError("the pre-flight built arm B's positions")

    monkeypatch.setattr(subjects, "scale_positions", arm_b)
    reads = _recording(monkeypatch, "_b2_overlay_inputs", lambda arguments, result: result)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects.SUBJECTS[f"{name}-preflight"].build(ObservedReader(_b2_overlay_dataset(tmp_path)), "ohlc-test", None)

    ((read, inputs),) = reads
    assert (read["subject"], read["read_signal"], read["threshold"]) == (
        f"{name}-preflight",
        _overlay_signal(name),
        _overlay_threshold(name),
    )
    returns = {a: _asset_returns(_ffill_btc(inputs.h4_prices)[a]) for a in _B2_ASSETS}
    net_a, net_a_x15 = (net_of_cost(inputs.arm_a, returns, cost_per_side=cost) for cost in (0.006, 1.5 * 0.006))
    bench = _fake_benchmark(inputs.h4_prices, cost_per_side=0.006)
    turnover_a, n = book_turnover(inputs.arm_a), len(inputs.close)
    start = next((k for k in range(n) if all(inputs.signal[a][k] is not None for a in _B2_ASSETS)), n)
    ((arguments, bar),) = bars
    assert arguments == {
        "book_net_returns": net_a,
        "benchmark_net_returns": bench,
        "n_trials": count,
        "var_trials": 0.0,
        "mean_block": 30,
        "seed": 42,
        "cost_stressed_returns": net_a_x15,
        "regime_slices": calendar_year_slices(net_a, inputs.h4_ts),
        "benchmark_slices": calendar_year_slices(bench, inputs.h4_ts),
        "decisive_start": 1380,
        "n_resamples": 2000,
    }
    engaged = {a: sum(p > 0 and s < 1 for p, s in zip(inputs.arm_a[a], inputs.scales[a])) for a in _B2_ASSETS}
    assert metrics == {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / n * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
        **{key: int(bar[key]) if key in _ARM_A_BAR_FLAGS else bar[key] for key in _ARM_A_BAR_KEYS},
        "engaged_per_asset": engaged,
        "engaged_per_year": per_year_engaged_counts(inputs.arm_a, inputs.scales, inputs.close),
        f"{signal_key}_coverage": {
            a: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(inputs.close, inputs.signal[a]).items()}
            for a in _B2_ASSETS
        },
        "primary_returns": n - start,
        "threshold": inputs.threshold,
    }
    assert set(metrics) == _overlay_preflight_keys(signal_key) and 0 < start < n - 2
    assert inputs.threshold == (subjects._b2_engagement_threshold(inputs.signal, inputs.arm_a) if threshold is None else threshold)
    assert sum(engaged.values()) == sum(metrics["engaged_per_year"].values()) > 0
    assert metrics["engaged_per_asset"][_B2_NEVER_SPIKES] == 0


def test_a_b2_overlay_preflight_whose_signal_no_close_carries_prints_its_figures_at_zero(tmp_path, monkeypatch):
    # The daily block opening where the union ends: no close carries the signal, and the rule reads no long stamp.
    root = _b2_overlay_dataset(tmp_path, from_bar=_B2_BARS)
    _anchor(monkeypatch, root)
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)

    result = runner.invoke(app, ["research", "eval", "--subject", "b2-liq-derisk-preflight", "--dataset", "ohlc-test"])

    assert result.exit_code == 0, result.output
    metrics = _block_and_metrics(result.output)["metrics"]
    assert (metrics["primary_returns"], set(metrics["engaged_per_year"].values()), set(metrics["engaged_per_asset"].values())) == (
        0,
        {0},
        {0},
    )
    assert {count for years in metrics["binperp_liq_long_z30d_coverage"].values() for count, _ in years.values()} == {0}
    assert metrics["threshold"] == 2.5


@pytest.mark.parametrize("name", sorted({*_B2_OVERLAYS, *(f"{name}-preflight" for name in _B2_OVERLAYS)}))
def test_a_b2_overlay_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the subject read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)
    args = ["research", "eval", "--subject", name, "--dataset", "ohlc-rolling", "--as-of", "2026-10-03"]

    result = runner.invoke(app, [*args, *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        f"{name} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen "
        "--dataset"
    ) in result.output


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
@pytest.mark.parametrize("plain", [True, False], ids=["plain-eval", "another-count"])
def test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, name, plain):
    count = _B2_OVERLAYS[name][2]
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b2_overlay_inputs", lambda arguments, result: result)
    flags = [] if plain else ["--register", "--iteration", "iter-182", "--family", "B2", "--n-trials", str(count + 1)]
    refused = (
        f"{name} declares a verdict rule, so every run of it is a trial: run it with --register"
        if plain
        else f"--n-trials {count + 1} is not {count}, the count {name} declares and deflates at: pass --n-trials {count}"
    )

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []


@pytest.mark.parametrize(
    ("name", "from_bar", "cause"),
    [
        pytest.param(
            "b2-oi-derisk",
            1_460,
            "1 of its return indices carry every asset's binperp_oi_z30d, and the head-to-head from the signal's own start needs 2",
            id="oi-one-index-from-the-start",
        ),
        pytest.param(
            "b2-liq-derisk",
            1_460,
            "0 of its return indices carry every asset's binperp_liq_long_z30d, and the head-to-head from the signal's own "
            "start needs 2",
            id="liquidations-no-index-from-the-start",
        ),
        pytest.param(
            "b2-oi-derisk",
            1_459,
            "arm A never draws down from the signal's own start, so max_drawdown_reduction_pct divides by zero",
            id="oi-arm-a-never-draws-down-from-the-start",
        ),
    ],
)
def test_a_b2_overlay_trial_refuses_a_start_it_cannot_evaluate_before_any_bar(tmp_path, monkeypatch, name, from_bar, cause):
    _anchor(monkeypatch, _b2_overlay_dataset(tmp_path, from_bar=from_bar))
    kill_bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{name} over the full history: {cause}" in result.output
    assert kill_bars == []


def _not_parquet(path: Path) -> None:
    path.write_bytes(b"not a parquet file")


@pytest.mark.parametrize(
    ("name", "relpath", "spoil", "cause"),
    [
        pytest.param("b2-oi-derisk", f"derivatives-oi/{_B2_SPOILT}/oi.parquet", _not_parquet, "File out of specification", id="oi"),
        pytest.param(
            "b2-ratio-derisk-preflight",
            f"derivatives-oi/{_B2_SPOILT}/oi.parquet",
            lambda path: pl.read_parquet(path).drop("count_long_short_ratio").write_parquet(path),
            '"count_long_short_ratio" not found',
            id="ratio",
        ),
        pytest.param(
            "b2-liq-derisk",
            "liquidations-daily/SOL/daily.parquet",
            lambda path: pl.read_parquet(path).drop("long_usd").write_parquet(path),
            '"long_usd" not found',
            id="liquidation-daily",
        ),
        pytest.param(
            "b2-liq-derisk-preflight",
            "liquidations-daily/BTC/daily.parquet",
            _not_parquet,
            "File out of specification",
            id="liquidation-daily-preflight",
        ),
    ],
)
def test_a_b2_overlay_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it(
    tmp_path, monkeypatch, name, relpath, spoil, cause
):
    root = _b2_overlay_dataset(tmp_path)
    spoil(root / relpath)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *_as_trial(name, tmp_path)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{relpath}: " in result.output and cause in result.output


@pytest.mark.parametrize("name", sorted(_B2_OVERLAYS))
def test_each_b2_overlay_reads_its_signal_off_its_own_columns(tmp_path, name):
    root = _b2_overlay_dataset(tmp_path)
    h4_ts, _ = subjects._capturing_union(ObservedReader(root), "ohlc-test", 240, None, None, False)
    expected = {}
    for asset in _B2_ASSETS:
        oi = pl.read_parquet(root / "derivatives-oi" / PERP_SYMBOLS[asset] / "oi.parquet")
        daily = pl.read_parquet(root / "liquidations-daily" / asset / "daily.parquet")
        if name == "b2-oi-derisk":
            expected[asset] = oi_zscore_grid_feature(oi["ts"].to_list(), oi["sum_open_interest"].to_list(), h4_ts)
        elif name == "b2-ratio-derisk":
            ratios = {column: oi[column].to_list() for column in _B2_OVERLAY_RATIOS}
            expected[asset] = ratio_max_signal(ratio_zscore_grid_features(oi["ts"].to_list(), ratios, h4_ts))
        else:
            expected[asset] = daily_zscore_grid_feature(daily["ts"].to_list(), daily["long_usd"].to_list(), h4_ts)

    signal = _overlay_signal(name)(ObservedReader(root), h4_ts)

    assert signal == expected
    assert sum(v is not None and v > 2.5 for v in signal["BTC"]) > 0


def _ruled_signal(held: list[float | None], flat: list[float]) -> tuple[dict, dict]:
    """BTC's signal at its long stamps `held` and at its flat ones `flat`, every other asset's flat and unread."""
    n = len(held) + len(flat)
    signal = {a: [None] * n for a in _B2_ASSETS} | {"BTC": [*held, *flat]}
    arm_a = {a: [0.0] * n for a in _B2_ASSETS} | {"BTC": [0.3] * len(held) + [0.0] * len(flat)}
    return signal, arm_a


@pytest.mark.parametrize(
    ("held", "flat", "share", "threshold"),
    [
        # Shares of 6 % above 2.0 and 2 % above 2.5: the first is nearer 4.93 %.
        pytest.param([2.2] * 40 + [2.6] * 20 + [0.0] * 940, [], None, 2.0, id="2.0-nearer"),
        # 15 % and 6 %: the second is nearer.
        pytest.param([2.2] * 90 + [2.6] * 60 + [0.0] * 850, [], None, 2.5, id="2.5-nearer"),
        # 50 % and 0 % against a share of 25 %: a tie, read as 2.5.
        pytest.param([2.2, 2.3, 0.0, 0.0], [], 0.25, 2.5, id="a-tie"),
        # Flat stamps at 9.0 count for neither share: read over the long stamps alone, 6 % and 2 % again.
        pytest.param([2.2] * 40 + [2.6] * 20 + [0.0] * 940, [9.0] * 500, None, 2.0, id="flat-stamps-left-out"),
        # Long stamps the signal does not reach count for neither share: 8 % and 5 % over the 1,000 it reads, 4 % and 2.5 %
        # over all 2,000.
        pytest.param([2.2] * 30 + [2.6] * 50 + [0.0] * 920 + [None] * 1000, [], None, 2.5, id="unread-long-stamps-left-out"),
        pytest.param([], [9.0] * 10, None, 2.5, id="no-long-stamp-holds-the-signal"),
    ],
)
def test_the_engagement_threshold_is_the_nearer_of_2_0_and_2_5_to_trial_2s_share(monkeypatch, held, flat, share, threshold):
    if share is not None:
        monkeypatch.setattr(subjects, "_B2_TRIAL_2_ENGAGED_SHARE", share)
    assert subjects._B2_TRIAL_2_ENGAGED_SHARE == (share if share is not None else 3_486 / 70_682)
    assert subjects._b2_engagement_threshold(*_ruled_signal(held, flat)) == threshold


_B2_TAPE_SPEC_KEYS = frozenset(
    {
        "fwd_logret_1h",
        "fwd_logret_4h",
        "fwd_logret_24h",
        "fwd_rv_1h",
        "fwd_rv_4h",
        "fwd_rv_24h",
        "events_per_asset",
        "zscore_hours_per_asset",
        "threshold",
        "zscore_hours",
        "mean_block",
        "n_resamples",
    }
)
_B2_TAPE_START = datetime(2026, 7, 14, tzinfo=UTC)
_B2_TAPE_HOURS = 900


def _b2_tape_dataset(tmp_path: Path, *, hours: int = _B2_TAPE_HOURS, gap: range = range(0)) -> Path:
    """Ten assets' hourly and 15-minute series over `hours` hours, each hourly close its last quarter's, and a 1-minute
    liquidations block covering every hour but `gap`'s, one bucket an hour: every asset but one liquidates 50 times its
    usual notional in each of ten hours past the 720-hour warm-up, each from its own hour."""
    root = tmp_path / "data"
    start = int(_B2_TAPE_START.timestamp())
    stamps = [_B2_TAPE_START + timedelta(hours=h) for h in range(hours)]
    write_parquet(
        pl.DataFrame({"ts": [t for h, t in enumerate(stamps) if h not in gap]}, schema={"ts": pl.Datetime("us", "UTC")}),
        root / "liquidations-frozen" / "covered-hours.parquet",
    )
    for i, asset in enumerate(_B2_ASSETS):
        quarter = [100.0 * (1 + 0.02 * math.sin(q / 9 + i)) * (1.0001**q) for q in range(4 * hours)]
        rows15 = [[start + 900 * q, f"{c}", f"{c * 1.01}", f"{c * 0.99}", f"{c}", f"{c}", "10", 3] for q, c in enumerate(quarter)]
        rows60 = [
            [start + 3600 * h, f"{c}", f"{c * 1.01}", f"{c * 0.99}", f"{c}", f"{c}", "40", 12] for h, c in enumerate(quarter[3::4])
        ]
        write_parquet(to_frame(rows15), root / "ohlc-test" / f"{asset}/EUR/15.parquet")
        write_parquet(to_frame(rows60), root / "ohlc-test" / f"{asset}/EUR/60.parquet")
        hot = set() if asset == _B2_NEVER_SPIKES else {760 + 13 * i + 7 * j for j in range(10)}
        buckets = {
            "ts": [t + timedelta(minutes=1) for t in stamps],
            "symbol": [f"{asset}USDT_PERP.A"] * hours,
            "long_usd": [5e4 if h in hot else 600.0 + 400 * math.sin(h / 5 + i) for h in range(hours)],
            "short_usd": [500.0 + 300 * math.cos(h / 7 + i) for h in range(hours)],
            "event_id": [f"{asset}USDT_PERP.A-{start + 3600 * h + 60}" for h in range(hours)],
        }
        schema = {
            "ts": pl.Datetime("us", "UTC"),
            "symbol": pl.String,
            "long_usd": pl.Float64,
            "short_usd": pl.Float64,
            "event_id": pl.String,
        }
        write_parquet(pl.DataFrame(buckets, schema=schema), root / "liquidations-frozen" / asset / "buckets.parquet")
    return root


def test_the_tape_reading_declares_the_hourly_and_quarter_hour_grids_its_keys_and_no_rule():
    reading = subjects.SUBJECTS["b2-liq-tape-reading"]
    assert (reading.intervals, reading.assets, reading.spec, reading.seeds) == ((60, 15), _B2_ASSETS, _B2_OVERLAY_SPEC, (42,))
    assert reading.build is subjects._build_b2_liq_tape_reading and reading.metric_keys == _B2_TAPE_SPEC_KEYS
    assert (reading.verdict, reading.no_verdict, reading.incumbent, reading.family, reading.n_trials) == (None,) * 5


def test_the_tape_forwards_read_from_the_close_its_hour_ends_on_and_merge_a_missing_quarter():
    hours = [_B2_TAPE_START + timedelta(hours=h) for h in range(30)]
    quarters = [_B2_TAPE_START + timedelta(minutes=15 * q) for q in range(120)]
    fine = [100.0 + q + (q % 3) for q in range(120)]
    # The quarter opening at 2h 30min is missing; the one opening at 10h 45min, hour 10's anchor, too.
    fine[10] = fine[43] = None
    hourly = [fine[4 * h + 3] for h in range(30)]
    out = subjects._b2_tape_forwards(hours, dict.fromkeys(_B2_ASSETS, hourly), quarters, dict.fromkeys(_B2_ASSETS, fine))

    assert set(out) == {f"fwd_{kind}_{h}h" for kind in ("logret", "rv") for h in (1, 4, 24)}
    btc = {series: values["BTC"] for series, values in out.items()}
    # Hour 0 ends at 1h, the close of the quarter opening at 45 min: its 1-hour return runs to the close at 2h.
    assert btc["fwd_logret_1h"][0] == pytest.approx(math.log(fine[7] / fine[3]))
    assert btc["fwd_logret_4h"][0] == pytest.approx(math.log(fine[19] / fine[3]))
    assert btc["fwd_rv_1h"][0] == pytest.approx(math.sqrt(sum(math.log(fine[q + 1] / fine[q]) ** 2 for q in range(3, 7))))
    # Hour 1's path runs 2h .. 3h: the missing 2h 30min quarter merges its neighbours' returns into one.
    path = [fine[7], fine[8], fine[9], fine[11]]
    assert btc["fwd_rv_1h"][1] == pytest.approx(math.sqrt(sum(math.log(b / a) ** 2 for a, b in zip(path, path[1:]))))
    # Hour 10's anchor quarter is missing, and the last hours lack the closes their horizons end on.
    assert (btc["fwd_rv_1h"][10], btc["fwd_logret_1h"][29], btc["fwd_logret_24h"][6], btc["fwd_rv_24h"][6]) == (
        None,
        None,
        None,
        None,
    )
    assert btc["fwd_logret_24h"][5] == pytest.approx(math.log(fine[119] / fine[23]))


def test_the_tape_reading_flags_an_hour_whose_z_score_exceeds_2_and_hands_its_forwards_to_the_contrast(tmp_path, monkeypatch):
    # Hours 850-859 are not asserted: each asset's 720-hour z-score is read at hours 719-849 alone, where the gap read as
    # covered would add hours 850-899.
    root = _b2_tape_dataset(tmp_path, gap=range(850, 860))
    contrasts = _recording(monkeypatch, "event_contrast", lambda arguments, result: result)

    metrics = subjects.SUBJECTS["b2-liq-tape-reading"].build(ObservedReader(root), "ohlc-test", None)

    reader = ObservedReader(root)
    hours, hourly = subjects._capturing_union(reader, "ohlc-test", 60, None, None, False)
    quarters, quarterly = subjects._capturing_union(reader, "ohlc-test", 15, None, None, False)
    covered = pl.read_parquet(root / "liquidations-frozen" / "covered-hours.parquet")["ts"].to_list()
    flags = {}
    for asset in _B2_ASSETS:
        rows = pl.read_parquet(root / "liquidations-frozen" / asset / "buckets.parquet")
        totals = liquidation_hourly_totals(
            rows["ts"].to_list(), rows["long_usd"].to_list(), rows["short_usd"].to_list(), hours, covered
        )
        flags[asset] = [None if z is None else z > 2.0 for z in funding_zscore(totals, window=720)]
    ((arguments, result),) = contrasts
    assert arguments == {
        "flags": flags,
        "forwards": subjects._b2_tape_forwards(hours, hourly, quarters, quarterly),
        "mean_block": 24,
        "n_resamples": 2000,
        "seed": 42,
    }
    assert set(metrics) == _B2_TAPE_SPEC_KEYS and {key: metrics[key] for key in result} == result
    assert metrics["events_per_asset"] == {a: sum(flag is True for flag in flags[a]) for a in _B2_ASSETS}
    assert metrics["events_per_asset"][_B2_NEVER_SPIKES] == 0 < metrics["events_per_asset"]["BTC"]
    assert metrics["zscore_hours_per_asset"] == dict.fromkeys(_B2_ASSETS, 849 - 718)
    assert (metrics["threshold"], metrics["zscore_hours"], metrics["mean_block"], metrics["n_resamples"]) == (2.0, 720, 24, 2000)


def test_the_tape_reading_refuses_a_bucket_file_it_cannot_read_naming_it(tmp_path, monkeypatch):
    root = _b2_tape_dataset(tmp_path)
    _not_parquet(root / "liquidations-frozen" / "SOL" / "buckets.parquet")
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", "b2-liq-tape-reading", "--dataset", "ohlc-test"])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert "liquidations-frozen/SOL/buckets.parquet: " in result.output and "File out of specification" in result.output
```

  - `_RULED_FIXTURES` gains, after `"b2-funding-derisk-full": _b2_dataset,`:

```python
    "b2-liq-derisk": _b2_overlay_dataset,
    "b2-oi-derisk": _b2_overlay_dataset,
    "b2-ratio-derisk": _b2_overlay_dataset,
```

  - `_DECLARED_COUNT` gains, after `"b2-funding-derisk-full": "_B2_FULL_N_TRIALS",`:

```python
    "b2-liq-derisk": "_B2_LIQ_N_TRIALS",
    "b2-oi-derisk": "_B2_OI_N_TRIALS",
    "b2-ratio-derisk": "_B2_RATIO_N_TRIALS",
```

  - the literal of `test_the_ruled_subjects_declare_their_families_and_trial_counts` gains, after `"b2-funding-derisk-full": ("B2", 1),`:

```python
        "b2-liq-derisk": ("B2", 4),
        "b2-oi-derisk": ("B2", 2),
        "b2-ratio-derisk": ("B2", 3),
```

  - `_CONTRACT_DATASETS` gains, after its `"b2-funding-derisk-full-preflight"` entry:

```python
    "b2-oi-derisk": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-oi-derisk-preflight": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-ratio-derisk": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-ratio-derisk-preflight": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-liq-derisk": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-liq-derisk-preflight": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-liq-tape-reading": lambda tmp_path, subject: (_b2_tape_dataset(tmp_path), _B2_TAPE_START),
```

  **Author's call** — the wiring test proves `_b2_overlay_metrics` against `_b2_full_metrics` itself, run on the same positions and signal with `_FROM_2021` moved to the signal's start and `_B2_FULL_N_TRIALS` to the subject's count, under argument-derived stand-ins for the bars, the benchmark and the head-to-heads: equal dicts, keys renamed, prove D9's "trial 2's body with the start in `k21`'s place", `_b2_full_metrics`' own test proving that body, while the recorded `derisk_scales` call proves the threshold reaches the scales; the fixture `_b2_overlay_dataset` writes every set the three overlays read, BTC's OI rows opening before the union and every other asset's at bar 300, as the real panel opens, and the daily block from the first day after that bar, so each signal's start falls inside the union and BTC's OI engages before it; the autouse `_liquidations_blocks_unattested` drops the committed sidecar's attestations of `liquidations-daily` and `liquidations-frozen` inside this module alone — the sidecar binds a set by its name, so Task 3's lines would refuse every fixture's synthetic block, and the data-gated basis test reads the attested blocks themselves, while `tests/test_registry_replay.py` imports none of it; the start refusals ride `from_bar` 1,460 and 1,459, measured on the transcription to leave the OI signal 1 and 2 return indices and the daily liquidations' none; the threshold rule's rows each move one side of the 4.93 % share and the tie row moves the share itself, and the unread row's long stamps without a signal turn a rule dividing by every long stamp to the other pick; the tape fixture `_b2_tape_dataset` writes a rolling set of 900 hours from 2026-07-14 with its hourly and 15-minute grids and a tape block whose covered hours open with it, the flag case leaving hours 850-859 unasserted so a build that reads every hour as covered moves its z-score hours, and the forwards' known answers are hand values at hours whose quarter-hour closes the fixture leaves out.

- [ ] **Step 2: Run them to verify they fail**

Run: `mkdir -p .tmp/plan-00138 && uv run pytest tests/test_research_command.py -k "b2_overlay or b2-oi-derisk or b2-ratio-derisk or b2-liq-derisk or ruled_subjects or declares_the_metric_keys or tape or engagement_threshold" -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt`
Expected: `63 failed, 458 deselected` (measured on the transcription): the 58 new cases, the families and metric-keys tests and the count-tie rows of the three trials, each on what Step 3 adds; the seven subjects' rows of the contract, tracked-spec and shared-defaults tests are not collected until `SUBJECTS` holds them

- [ ] **Step 3: Implement in `cli/research/subjects.py`** — `import math` before `import statistics`; `from datetime import UTC, datetime` becomes `from datetime import UTC, datetime, timedelta`; the `from cli.alpha.b2 import (` block gains `daily_zscore_grid_feature,` after `close_grid,`, `event_contrast,` after `derisk_scales,`, `liquidation_hourly_totals,` after `funding_grid_feature,`, `oi_zscore_grid_feature,` after `net_of_cost,`, and `ratio_max_signal,` and `ratio_zscore_grid_features,` after `per_year_turnover,`; `from cli.features.derivatives import coverage_by_year` becomes `from cli.features.derivatives import coverage_by_year, funding_zscore`; after `_B2_FULL_PREFLIGHT_KEYS`' closing `}` and before `SUBJECTS: dict[str, Subject] = {`:

```python
# docs/specs/00138 D3-D10: B2's trials 3-5, spec 00128's half-scale de-risk on three signals of their own, each on a frozen
# set's full history with trial 2's bars, the head-to-head read from the first close every asset's signal is defined.
_B2_OI_N_TRIALS = 2  # docs/specs/00138 D8: each count fixed by the spec's hash; a different one is a new subject
_B2_RATIO_N_TRIALS = 3
_B2_LIQ_N_TRIALS = 4
_B2_OI_THRESHOLD = 2.5
_B2_RATIO_THRESHOLD = 2.5
_B2_LIQ_SET = "liquidations-daily"
# Spec 00137's measured basis: trial 2's engaged long asset-stamps over those where its funding z-score is defined.
_B2_TRIAL_2_ENGAGED_SHARE = 3_486 / 70_682
_B2_RATIO_COLUMNS = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)


class _B2OverlayInputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    close: list[datetime]
    arm_a: dict[str, list[float]]
    signal: dict[str, list[float | None]]
    scales: dict[str, list[float]]
    threshold: float


def _b2_oi_signal(reader: ObservedReader, h4_ts: list[datetime]) -> dict[str, list[float | None]]:
    signal = {}
    for asset in _ASSETS:
        relpath = f"{PERP_SYMBOLS[asset]}/oi.parquet"
        try:
            rows = reader.read_series("derivatives-oi", relpath)
            signal[asset] = oi_zscore_grid_feature(rows["ts"].to_list(), rows["sum_open_interest"].to_list(), h4_ts)
        except (pl.exceptions.PolarsError, AlphaError, FeatureError) as exc:
            raise SubjectError(f"derivatives-oi/{relpath}: {exc}") from exc
    return signal


def _b2_ratio_signal(reader: ObservedReader, h4_ts: list[datetime]) -> dict[str, list[float | None]]:
    signal = {}
    for asset in _ASSETS:
        relpath = f"{PERP_SYMBOLS[asset]}/oi.parquet"
        try:
            rows = reader.read_series("derivatives-oi", relpath)
            ratios = {column: rows[column].to_list() for column in _B2_RATIO_COLUMNS}
            signal[asset] = ratio_max_signal(ratio_zscore_grid_features(rows["ts"].to_list(), ratios, h4_ts))
        except (pl.exceptions.PolarsError, AlphaError, FeatureError) as exc:
            raise SubjectError(f"derivatives-oi/{relpath}: {exc}") from exc
    return signal


def _b2_liq_signal(reader: ObservedReader, h4_ts: list[datetime]) -> dict[str, list[float | None]]:
    """The long side's daily notional, the side a long-only book's de-risk reads (docs/specs/00138 D6)."""
    signal = {}
    for asset in _ASSETS:
        relpath = f"{asset}/daily.parquet"
        try:
            rows = reader.read_series(_B2_LIQ_SET, relpath)
            signal[asset] = daily_zscore_grid_feature(rows["ts"].to_list(), rows["long_usd"].to_list(), h4_ts)
        except (pl.exceptions.PolarsError, AlphaError, FeatureError) as exc:
            raise SubjectError(f"{_B2_LIQ_SET}/{relpath}: {exc}") from exc
    return signal


def _b2_engagement_threshold(signal: dict[str, list[float | None]], arm_a: dict[str, list[float]]) -> float:
    """Of spec 00128's two thresholds, the one whose share of arm A's long asset-stamps where the signal is defined the
    signal exceeds lies nearer trial 2's share, 2.5 on a tie or where no long stamp holds the signal (docs/specs/00138
    D3)."""
    held = [z for a in _ASSETS for p, z in zip(arm_a[a], signal[a]) if p > 0 and z is not None]
    if not held:
        return 2.5
    return min((2.5, 2.0), key=lambda t: abs(sum(z > t for z in held) / len(held) - _B2_TRIAL_2_ENGAGED_SHARE))


def _b2_overlay_inputs(
    subject: str,
    read_signal: Callable[[ObservedReader, list[datetime]], dict[str, list[float | None]]],
    threshold: float | Callable[[dict[str, list[float | None]], dict[str, list[float]]], float],
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    accept_holes: bool,
) -> _B2OverlayInputs:
    """Arm A's positions, the signal and its scales, and no return of arm B: the pre-flight reads this half alone."""
    h4_ts, h4_prices = _capturing_union(reader, dataset, 240, window, None, accept_holes)
    close = close_grid(h4_ts)
    if len(close) < _DECISIVE_START + 2:
        raise SubjectError(
            f"{_b2_over(subject, window)}: it holds {len(close)} return indices, and the kill bar's decisive window opens at index "
            f"{_DECISIVE_START} and needs 2"
        )
    if not calendar_year_slices([0.0] * len(close), h4_ts):
        raise SubjectError(
            f"{_b2_over(subject, window)}: none of its return indices closes in a calendar year the worst-slice leg reads, the "
            "stub years left out"
        )
    signal = read_signal(reader, h4_ts)
    # `_b2_inputs`' arm A, built here because that half also reads the funding set.
    fed = _ffill_btc(h4_prices)
    arms = [
        a2_book_returns(
            fed,
            config=A2Config(
                lookbacks=lookbacks,
                short="off",
                target_vol=target_vol,
                vol_lookback=_B2_LOOKBACK,
                basket_lookback=_B2_LOOKBACK,
                periods_per_year=PPY_4H,
            ),
        )["asset_positions"]
        for lookbacks, target_vol in _B2_A2_ARMS
    ]
    arm_a = {a: [statistics.mean(arm[a][k] for arm in arms) for k in range(len(h4_ts) - 1)] for a in _ASSETS}
    if callable(threshold):
        threshold = threshold(signal, arm_a)
    scales = derisk_scales(signal, config=B2Config(z_threshold=threshold))
    return _B2OverlayInputs(h4_ts, h4_prices, close, arm_a, signal, scales, threshold)


def _b2_overlay_start(inputs: _B2OverlayInputs) -> int:
    """The first return index at which every asset's signal is defined, the length when none is (docs/specs/00138 D8)."""
    signal = inputs.signal
    return next((k for k in range(len(inputs.close)) if all(signal[a][k] is not None for a in _ASSETS)), len(inputs.close))


def _b2_overlay_arm_a_bar(inputs: _B2OverlayInputs, *, n_trials: int) -> tuple[dict, list[float], list[float]]:
    cost = _B2_COST_PER_SIDE
    returns = _b2_returns(inputs.h4_prices)
    net_a = net_of_cost(inputs.arm_a, returns, cost_per_side=cost)
    net_a_x15 = net_of_cost(inputs.arm_a, returns, cost_per_side=1.5 * cost)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=cost)
    bar = a1_kill_bar(
        net_a,
        bench,
        n_trials=n_trials,
        var_trials=0.0,
        mean_block=30,
        seed=42,
        cost_stressed_returns=net_a_x15,
        regime_slices=calendar_year_slices(net_a, inputs.h4_ts),
        benchmark_slices=calendar_year_slices(bench, inputs.h4_ts),
        decisive_start=_DECISIVE_START,
        n_resamples=_N_RESAMPLES,
    )
    return bar, net_a, bench


def _b2_overlay_engagement(inputs: _B2OverlayInputs, signal_key: str) -> dict:
    arm_a, scales, close = inputs.arm_a, inputs.scales, inputs.close
    return {
        "engaged_per_asset": {a: sum(p > 0 and s < 1 for p, s in zip(arm_a[a], scales[a])) for a in _ASSETS},
        "engaged_per_year": per_year_engaged_counts(arm_a, scales, close),
        f"{signal_key}_coverage": {
            asset: {str(year): [c.non_null, c.total] for year, c in coverage_by_year(close, values).items()}
            for asset, values in inputs.signal.items()
        },
        "primary_returns": len(close) - _b2_overlay_start(inputs),
        "threshold": inputs.threshold,
    }


def _b2_overlay_metrics(inputs: _B2OverlayInputs, *, signal_key: str, n_trials: int) -> dict:
    arm_a, scales, close = inputs.arm_a, inputs.scales, inputs.close
    start = _b2_overlay_start(inputs)
    if len(close) - start < 2:
        raise ValidationError(
            f"{len(close) - start} of its return indices carry every asset's {signal_key}, and the head-to-head from the "
            "signal's own start needs 2"
        )
    arm_b = scale_positions(arm_a, scales)
    cost = _B2_COST_PER_SIDE
    returns = _b2_returns(inputs.h4_prices)
    net_a = net_of_cost(arm_a, returns, cost_per_side=cost)
    net_b = net_of_cost(arm_b, returns, cost_per_side=cost)
    net_b_x15 = net_of_cost(arm_b, returns, cost_per_side=1.5 * cost)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=cost)
    slices_b, slices_bench = calendar_year_slices(net_b, inputs.h4_ts), calendar_year_slices(bench, inputs.h4_ts)
    drawdown_b = max_drawdown(net_b[start:])
    drawdown_a = max_drawdown(net_a[start:])
    if drawdown_a == 0:
        raise ValidationError("arm A never draws down from the signal's own start, so max_drawdown_reduction_pct divides by zero")
    grid = {
        (block, seed): a1_kill_bar(
            net_b,
            bench,
            n_trials=n_trials,
            var_trials=0.0,
            mean_block=block,
            seed=seed,
            cost_stressed_returns=net_b_x15,
            regime_slices=slices_b,
            benchmark_slices=slices_bench,
            decisive_start=_DECISIVE_START,
            n_resamples=_N_RESAMPLES,
        )
        for block in (30, 102)
        for seed in (42, 7, 1234)
    }
    headline = grid[(30, 42)]
    head_to_head = {}
    for label, first in (("full", 0), ("primary", start)):
        verdict = net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=_N_RESAMPLES)
        head_to_head[f"head_to_head_mean_outperf_{label}"] = verdict["mean_outperformance"]
        head_to_head[f"head_to_head_spa_p_{label}"] = verdict["spa_p_value"]
    positions_differ = per_year_positions_differ(arm_a, arm_b, close)
    engagement = _b2_overlay_engagement(inputs, signal_key)
    del engagement["engaged_per_asset"]
    return {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=PPY_4H),
        "ann_sharpe_noc_decisive": sharpe(net_b[_DECISIVE_START:], periods_per_year=PPY_4H),
        "per_period_sharpe_4h": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_DECISIVE_START:], periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_DECISIVE_START:], periods_per_year=PPY_4H),
        "dsr_corrected": headline["dsr"],
        "dsr_pass": int(headline["dsr_pass"]),
        "spa_pass": int(headline["spa_pass"]),
        "spa_p_full": headline["spa_p_value_full"],
        "cost_stress_pass": int(headline["cost_stress_pass"]),
        "worst_slice_relative_pass": int(headline["worst_slice_pass"]),
        "passes": int(headline["passes"]),
        "decisive_start": _DECISIVE_START,
        "n_resamples": _N_RESAMPLES,
        "arm_a_passes": int(_b2_overlay_arm_a_bar(inputs, n_trials=n_trials)[0]["passes"]),
        **{f"spa_p_decisive_b{block}_s{seed}": result["spa_p_value"] for (block, seed), result in grid.items()},
        **head_to_head,
        "max_drawdown": drawdown_b,
        "arm_a_max_drawdown": drawdown_a,
        "max_drawdown_reduction_pct": 100 * (drawdown_a - drawdown_b) / drawdown_a,
        "turnover_a": book_turnover(arm_a),
        "turnover_b": book_turnover(arm_b),
        "stamps_positions_differ": sum(positions_differ.values()),
        "positions_differ_per_year": positions_differ,
        "turnover_a_per_year": per_year_turnover(arm_a, close),
        "turnover_b_per_year": per_year_turnover(arm_b, close),
        "max_drawdown_per_year": per_year_max_drawdown(net_b, close),
        "arm_a_max_drawdown_per_year": per_year_max_drawdown(net_a, close),
        **engagement,
    }


def _b2_overlay_preflight_metrics(inputs: _B2OverlayInputs, *, signal_key: str, n_trials: int) -> dict:
    """Arm A's anchors and bar and the engagement (docs/specs/00138 D9): no position or return of arm B."""
    bar, net_a, bench = _b2_overlay_arm_a_bar(inputs, n_trials=n_trials)
    turnover_a = book_turnover(inputs.arm_a)
    return {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_DECISIVE_START:], periods_per_year=PPY_4H),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / len(inputs.close) * _B2_COST_PER_SIDE * PPY_4H,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_4H),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_DECISIVE_START:], periods_per_year=PPY_4H),
        **{key: int(bar[key]) if key in _B2_ARM_A_BAR_FLAGS else bar[key] for key in sorted(_B2_ARM_A_BAR_KEYS)},
        **_b2_overlay_engagement(inputs, signal_key),
    }


def _b2_overlay_build(
    subject: str,
    signal_key: str,
    read_signal: Callable[[ObservedReader, list[datetime]], dict[str, list[float | None]]],
    threshold: float | Callable[[dict[str, list[float | None]], dict[str, list[float]]], float],
    compute: Callable[..., dict],
    n_trials: int,
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
    accept_holes: bool,
) -> dict:
    if as_of is not None:
        raise SubjectError(
            f"{subject} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a "
            "frozen --dataset"
        )
    try:
        inputs = _b2_overlay_inputs(subject, read_signal, threshold, reader, dataset, window, accept_holes)
        return compute(inputs, signal_key=signal_key, n_trials=n_trials)
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b2_oi_derisk(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-oi-derisk",
        "binperp_oi_z30d",
        _b2_oi_signal,
        _B2_OI_THRESHOLD,
        _b2_overlay_metrics,
        _B2_OI_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_oi_derisk_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-oi-derisk-preflight",
        "binperp_oi_z30d",
        _b2_oi_signal,
        _B2_OI_THRESHOLD,
        _b2_overlay_preflight_metrics,
        _B2_OI_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_ratio_derisk(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-ratio-derisk",
        "binperp_ratio_max_z30d",
        _b2_ratio_signal,
        _B2_RATIO_THRESHOLD,
        _b2_overlay_metrics,
        _B2_RATIO_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_ratio_derisk_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-ratio-derisk-preflight",
        "binperp_ratio_max_z30d",
        _b2_ratio_signal,
        _B2_RATIO_THRESHOLD,
        _b2_overlay_preflight_metrics,
        _B2_RATIO_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_liq_derisk(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-liq-derisk",
        "binperp_liq_long_z30d",
        _b2_liq_signal,
        _b2_engagement_threshold,
        _b2_overlay_metrics,
        _B2_LIQ_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_liq_derisk_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-liq-derisk-preflight",
        "binperp_liq_long_z30d",
        _b2_liq_signal,
        _b2_engagement_threshold,
        _b2_overlay_preflight_metrics,
        _B2_LIQ_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


# docs/specs/00138 D8's matrix, spec 00128's with the head-to-head read from the signal's own start, and the two instrument
# findings its metrics show: a change to it is a new spec and a new trial, never an edit here.
def _b2_overlay_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not any(m["engaged_per_year"].values()):
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0 and m["max_drawdown_reduction_pct"] > 1e-6:
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 else "park"
    return "reject"


# docs/specs/00138 D9's keys: trial 2's, the head-to-head's from-2021 pair read from the signal's own start, each signal's
# coverage in the funding z-score's place, and the returns from that start.
def _b2_overlay_metric_keys(signal_key: str) -> frozenset[str]:
    moved = {"head_to_head_mean_outperf_2021", "head_to_head_spa_p_2021", "binperp_funding_z30d_coverage"}
    return (_B2_METRIC_KEYS - moved) | {
        "head_to_head_mean_outperf_primary",
        "head_to_head_spa_p_primary",
        "primary_returns",
        "threshold",
        f"{signal_key}_coverage",
    }


def _b2_overlay_preflight_keys(signal_key: str) -> frozenset[str]:
    return (_B2_FULL_PREFLIGHT_KEYS - {"binperp_funding_z30d_coverage"}) | {
        "primary_returns",
        "threshold",
        f"{signal_key}_coverage",
    }


# docs/specs/00138 D12: the 1-minute tape's event study, a reading on the rolling set with no rule, kept by --reading.
_B2_TAPE_SET = "liquidations-frozen"
_B2_TAPE_ZSCORE_HOURS = 720
_B2_TAPE_THRESHOLD = 2.0
_B2_TAPE_HORIZONS = (1, 4, 24)
_B2_TAPE_BLOCK = 24
_HOUR = timedelta(hours=1)
_QUARTER = timedelta(minutes=15)


def _b2_tape_reads(reader: ObservedReader) -> tuple[list[datetime], dict[str, tuple[list, list, list]]]:
    try:
        covered = reader.read_series(_B2_TAPE_SET, "covered-hours.parquet")["ts"].to_list()
    except pl.exceptions.PolarsError as exc:
        raise SubjectError(f"{_B2_TAPE_SET}/covered-hours.parquet: {exc}") from exc
    buckets = {}
    for asset in _ASSETS:
        relpath = f"{asset}/buckets.parquet"
        try:
            rows = reader.read_series(_B2_TAPE_SET, relpath)
            buckets[asset] = (rows["ts"].to_list(), rows["long_usd"].to_list(), rows["short_usd"].to_list())
        except pl.exceptions.PolarsError as exc:
            raise SubjectError(f"{_B2_TAPE_SET}/{relpath}: {exc}") from exc
    return covered, buckets


def _b2_tape_forwards(
    hours: list[datetime],
    hourly: dict[str, list[float | None]],
    quarters: list[datetime],
    quarterly: dict[str, list[float | None]],
) -> dict[str, dict[str, list[float | None]]]:
    """Per hour h, from the price at h + 1 h, the close of h's own hourly bar, forward over each horizon H: the log return
    to the close of the hourly bar opening at h + H, and the realized volatility from the 15-minute closes at h + 1 h, h +
    1 h 15 min, ..., h + 1 h + H, each the close of the bar opening 15 minutes before it, a missing one merging its
    neighbours' returns and a missing first or last one leaving the hour None (docs/specs/00138 D12)."""
    for prices in (hourly, quarterly):
        for asset, closes in prices.items():
            if any(c is not None and c <= 0 for c in closes):
                raise ValidationError(f"{asset} holds a close at or below zero, which carries no log return")
    hour_at = {t: k for k, t in enumerate(hours)}
    quarter_at = {t: k for k, t in enumerate(quarters)}
    out: dict[str, dict[str, list[float | None]]] = {}
    for horizon in _B2_TAPE_HORIZONS:
        returns, vols = {}, {}
        for asset in _ASSETS:
            closes, fine = hourly[asset], quarterly[asset]
            returns[asset], vols[asset] = [], []
            for h in hours:
                start, k_end = closes[hour_at[h]], hour_at.get(h + horizon * _HOUR)
                end = None if k_end is None else closes[k_end]
                returns[asset].append(None if start is None or end is None else math.log(end / start))
                opens = [h + 3 * _QUARTER + j * _QUARTER for j in range(4 * horizon + 1)]
                path = [fine[quarter_at[t]] if t in quarter_at else None for t in opens]
                if path[0] is None or path[-1] is None:
                    vols[asset].append(None)
                    continue
                kept = [c for c in path if c is not None]
                vols[asset].append(math.sqrt(sum(math.log(b / a) ** 2 for a, b in zip(kept, kept[1:]))))
        out[f"fwd_logret_{horizon}h"], out[f"fwd_rv_{horizon}h"] = returns, vols
    return out


def _build_b2_liq_tape_reading(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    subject = "b2-liq-tape-reading"
    hours, hourly = _capturing_union(reader, dataset, 60, window, as_of, accept_holes)
    need = _B2_TAPE_ZSCORE_HOURS + max(_B2_TAPE_HORIZONS) + 1
    if len(hours) < need:
        raise SubjectError(
            f"{_b2_over(subject, window)}: it holds {len(hours)} hourly bars, and the {_B2_TAPE_ZSCORE_HOURS}-hour z-score and "
            f"the {max(_B2_TAPE_HORIZONS)}-hour forward read need {need}"
        )
    quarters, quarterly = _capturing_union(reader, dataset, 15, window, as_of, accept_holes)
    covered, buckets = _b2_tape_reads(reader)
    flags = {}
    for asset in _ASSETS:
        try:
            totals = liquidation_hourly_totals(*buckets[asset], hours, covered)
            zscores = funding_zscore(totals, window=_B2_TAPE_ZSCORE_HOURS)
        except (AlphaError, FeatureError) as exc:
            raise SubjectError(f"{_B2_TAPE_SET}/{asset}/buckets.parquet: {exc}") from exc
        flags[asset] = [None if z is None else z > _B2_TAPE_THRESHOLD for z in zscores]
    try:
        forwards = _b2_tape_forwards(hours, hourly, quarters, quarterly)
        contrast = event_contrast(flags, forwards, mean_block=_B2_TAPE_BLOCK, n_resamples=_N_RESAMPLES, seed=42)
    except (AlphaError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc
    return {
        **contrast,
        "events_per_asset": {a: sum(flag is True for flag in flags[a]) for a in _ASSETS},
        "zscore_hours_per_asset": {a: sum(flag is not None for flag in flags[a]) for a in _ASSETS},
        "threshold": _B2_TAPE_THRESHOLD,
        "zscore_hours": _B2_TAPE_ZSCORE_HOURS,
        "mean_block": _B2_TAPE_BLOCK,
        "n_resamples": _N_RESAMPLES,
    }


# docs/specs/00138 D12's keys of the reading.
_B2_TAPE_KEYS = frozenset(
    {
        *(f"fwd_{kind}_{horizon}h" for kind in ("logret", "rv") for horizon in _B2_TAPE_HORIZONS),
        "events_per_asset",
        "zscore_hours_per_asset",
        "threshold",
        "zscore_hours",
        "mean_block",
        "n_resamples",
    }
)
```

  and at the end of `SUBJECTS`, after the `"b2-funding-derisk-full-preflight"` entry:

```python
    "b2-oi-derisk": Subject(
        "b2-oi-derisk",
        (240,),
        _ASSETS,
        _build_b2_oi_derisk,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_b2_overlay_metric_keys("binperp_oi_z30d"),
        seeds=(42, 7, 1234),
        verdict=_b2_overlay_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, "
            "the trial unspent"
        ),
        family="B2",
        n_trials=_B2_OI_N_TRIALS,
    ),
    "b2-oi-derisk-preflight": Subject(
        "b2-oi-derisk-preflight",
        (240,),
        _ASSETS,
        _build_b2_oi_derisk_preflight,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_b2_overlay_preflight_keys("binperp_oi_z30d"),
        seeds=(42,),
    ),
    "b2-ratio-derisk": Subject(
        "b2-ratio-derisk",
        (240,),
        _ASSETS,
        _build_b2_ratio_derisk,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_b2_overlay_metric_keys("binperp_ratio_max_z30d"),
        seeds=(42, 7, 1234),
        verdict=_b2_overlay_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, "
            "the trial unspent"
        ),
        family="B2",
        n_trials=_B2_RATIO_N_TRIALS,
    ),
    "b2-ratio-derisk-preflight": Subject(
        "b2-ratio-derisk-preflight",
        (240,),
        _ASSETS,
        _build_b2_ratio_derisk_preflight,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_b2_overlay_preflight_keys("binperp_ratio_max_z30d"),
        seeds=(42,),
    ),
    "b2-liq-derisk": Subject(
        "b2-liq-derisk",
        (240,),
        _ASSETS,
        _build_b2_liq_derisk,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_b2_overlay_metric_keys("binperp_liq_long_z30d"),
        seeds=(42, 7, 1234),
        verdict=_b2_overlay_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, "
            "the trial unspent"
        ),
        family="B2",
        n_trials=_B2_LIQ_N_TRIALS,
    ),
    "b2-liq-derisk-preflight": Subject(
        "b2-liq-derisk-preflight",
        (240,),
        _ASSETS,
        _build_b2_liq_derisk_preflight,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_b2_overlay_preflight_keys("binperp_liq_long_z30d"),
        seeds=(42,),
    ),
    "b2-liq-tape-reading": Subject(
        "b2-liq-tape-reading",
        (60, 15),
        _ASSETS,
        _build_b2_liq_tape_reading,
        spec="docs/specs/00138-b2-three-overlays-design.md",
        metric_keys=_B2_TAPE_KEYS,
        seeds=(42,),
    ),
```

  **Author's call** — the wrappers read each count and threshold constant, and the rule, at call time, so the shared count-tie test's raise of a constant reaches every bar; the twin passes its trial's count to arm A's bar, as trial 2's twin did, a figure no number reads at `var_trials` 0.0; the reading refuses a window too short for its z-score and longest forward before the tape is read.

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row's list, which now ends `` …, `b2-funding-derisk-full` (…) or `b2-funding-derisk-full-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the stamps the halving engages, with no return of the halved book; it has no rule, so its run is kept with `--reading`). | ``, ends instead:

```markdown
…, `b2-funding-derisk-full` (the A2 4h ensemble against the same ensemble halved per asset while that asset's 30-day funding z-score exceeds 2; the 4h series of `--dataset`, a frozen set only, and the `derivatives-funding` set's ten funding files read whole), `b2-funding-derisk-full-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the stamps the halving engages, with no return of the halved book; it has no rule, so its run is kept with `--reading`), `b2-oi-derisk` (the A2 4h ensemble against the same ensemble halved per asset while that asset's 30-day open-interest z-score exceeds 2.5; the 4h series of `--dataset`, a frozen set only, and the `derivatives-oi` set's ten files read whole), `b2-oi-derisk-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the stamps the halving engages, with no return of the halved book; it has no rule, so its run is kept with `--reading`), `b2-ratio-derisk` (the same comparison with the largest of the asset's four 30-day long/short-ratio z-scores above 2.5, read only where all four are; the 4h series of `--dataset`, a frozen set only, and the `derivatives-oi` set's ten files read whole), `b2-ratio-derisk-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the stamps the halving engages, with no return of the halved book; it has no rule, so its run is kept with `--reading`), `b2-liq-derisk` (the same comparison with the 30-day z-score of the asset's daily long-side liquidated notional, a day read once it has ended, above 2.0 or 2.5, whichever engages the book about as often as the funding comparison did; the 4h series of `--dataset`, a frozen set only, and the `liquidations-daily` set read whole), `b2-liq-derisk-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the stamps the halving engages, with no return of the halved book; it has no rule, so its run is kept with `--reading`) or `b2-liq-tape-reading` (an event study rather than a comparison: per asset and pooled, the forward 1-, 4- and 24-hour log returns and realized volatility after an hour whose 720-hour z-score of liquidated notional exceeds 2, against the other hours, with stationary-bootstrap bounds; the hourly and 15-minute series of `--dataset` and the `liquidations-frozen` set read whole; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: Run them to verify they pass** — first, timed, in three parts, each its own plain call after the previous one's exit: with `F` the filter `b2_overlay or b2-oi-derisk or b2-ratio-derisk or b2-liq-derisk or ruled_subjects or declares_the_metric_keys or tape or engagement_threshold`, `uv run pytest tests/test_research_command.py -k "shared_defaults_move and ($F)" -m "not data" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt-1`, then the same with `-k "evaluates_its_fixture and ($F)"` and `--basetemp=.tmp/plan-00138/pt-2`, then with `-k "($F) and not shared_defaults_move and not evaluates_its_fixture"` and `--basetemp=.tmp/plan-00138/pt-3` — collecting 7, 52 and 75 cases, 134 in all (measured on the transcription at about 200, 198 and 251 s, every case passing, before the threshold rule's `unread-long-stamps-left-out` row and the flag case's unasserted hours, measured since at under a second and 4.4 s): each row at 10 s or more joins `tests/slow-cases.txt` at its `sorted()` place — on the transcription these seventeen:

```text
tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-ratio-derisk]
tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-ratio-derisk]
tests/test_research_command.py::test_each_b2_overlay_reads_its_signal_off_its_own_columns[b2-ratio-derisk]
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b2-liq-derisk]
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b2-oi-derisk]
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b2-ratio-derisk]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-liq-derisk-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-oi-derisk-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-oi-derisk-preflight-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-ratio-derisk-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-ratio-derisk-preflight-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-liq-derisk-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-liq-derisk]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-oi-derisk-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-oi-derisk]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-ratio-derisk-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-ratio-derisk]
```

  the run's own timing deciding, a row the run puts at 10 s or more beyond them listed too (the six spoilt-file contract rows of the ratio pair measured 9.6–9.7 s, the liquidations twin's evaluates row 9.4 s), one below it left off. Then Step 2's command, expected `112 passed, 475 deselected` (measured on the transcription in 3 min 21 s) with the seventeen listed, each row moved between the lists moving one case between the counts; `uv run pytest tests/test_slow_cases.py -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` passes.

- [ ] **Step 6: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the direct readers in two parts, the second after the first's exit — `tests/test_research_command.py` alone, `--basetemp=.tmp/plan-00138/pt-1` (measured `520 passed, 67 deselected` in 6 min 51 s), and the other readers of the four paths, `--basetemp=.tmp/plan-00138/pt-2` (measured `4112 passed, 42 deselected` in 1 min 51 s), each `-m "not slow and not data"`; `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.

- [ ] **Step 7: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured on the transcription, seventy-five of seventy-five); the contract, tracked-spec, shared-defaults and count-tie rows of the seven subjects are new rows of existing tests, not new guards, and are not probed; the ratio rows of the wiring, pre-flight and signal tests are slow, each recorded `probe skipped: slow case` with its node id; a row below whose node id step 5 listed beyond the seventeen is not run either, and the commit records `probe skipped: slow case` with its node id in its place:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-oi-derisk-preflight": Subject(/,/^    ),/s/metric_keys=_b2_overlay_preflight_keys("binperp_oi_z30d"),/metric_keys=_b2_overlay_metric_keys("binperp_oi_z30d"),/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_overlay_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-ratio-derisk": Subject(/,/^    ),/s/seeds=(42, 7, 1234),/seeds=(42,),/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_overlay_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b2-ratio-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-liq-derisk": Subject(/,/^    ),/s/n_trials=_B2_LIQ_N_TRIALS,/n_trials=_B2_RATIO_N_TRIALS,/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_overlay_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation 's/^_B2_OI_N_TRIALS = 2 /_B2_OI_N_TRIALS = 1 /' -- uv run pytest 'tests/test_research_command.py::test_the_ruled_subjects_declare_their_families_and_trial_counts' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/m\["head_to_head_mean_outperf_primary"\] > 0/m["head_to_head_mean_outperf_full"] > 0/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-3-outperforms-over-the-full-window-alone]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/if m\["head_to_head_spa_p_primary"\] < 0.05 else/if m["head_to_head_spa_p_full"] < 0.05 else/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-1-outperforms-significantly-from-the-start-and-draws-down-less]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/< 0.05 else "park"/< 0.05 and m["spa_p_decisive_b102_s42"] < 0.05 else "park"/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-1-outperforms-significantly-from-the-start-and-draws-down-less]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/< 0.05 else/<= 0.05 else/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-2-p-at-exactly-0.05]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/< 0.05 else/< 0.0499 else/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-1-p-at-0.0499]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/else "park"/else "reject"/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-2-outperforms-insignificantly-from-the-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/_primary"\] > 0 and/_primary"] >= 0 and/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-3-mean-at-exactly-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/_primary"\] > 0 and/_primary"] > -1 and/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-3-underperforms-from-the-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/> 1e-6/>= 1e-6/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-3-reduction-at-exactly-1e-6]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/> 1e-6/> 1e-5/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-1-reduction-past-1e-6]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/ and m\["max_drawdown_reduction_pct"\] > 1e-6/ and True/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-3-draws-down-more]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/    if not m\["passes"\]:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[row-4-arm-b-fails-its-bar]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/if not m\["arm_a_passes"\] or/if False or/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[arm-a-fails-its-bar]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/ or not any(m\["engaged_per_year"\].values()):/ or False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[the-overlay-never-engages]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/if not m\["arm_a_passes"\] or not any/if not m["arm_a_passes"] and not any/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[arm-a-read-before-passes]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_verdict(/,/^[^ #]/s/if not m\["arm_a_passes"\] or not any/if not m["arm_a_passes"] and not any/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop[engagement-read-before-passes]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    for label, first in (("full", 0), ("primary", start)):/    for label, first in (("full", 0), ("primary", 0)):/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/^            n_trials=n_trials,$/            n_trials=1,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    drawdown_b = max_drawdown(net_b\[start:\])/    drawdown_b = max_drawdown(net_b)/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/        "turnover_b": book_turnover(arm_b),/        "turnover_b": book_turnover(arm_a),/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    slices_b, slices_bench = calendar_year_slices(net_b, inputs.h4_ts), calendar_year_slices(bench, inputs.h4_ts)/    slices_b, slices_bench = _b2_slices(net_b, inputs.h4_ts), _b2_slices(bench, inputs.h4_ts)/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/        "arm_a_passes": int(_b2_overlay_arm_a_bar(inputs, n_trials=n_trials)\[0\]\["passes"\]),/        "arm_a_passes": int(headline["passes"]),/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_inputs(/,/^def /s/config=B2Config(z_threshold=threshold)/config=B2Config()/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_arm_a_bar(/,/^def /s/        regime_slices=calendar_year_slices(net_a, inputs.h4_ts),/        regime_slices=_b2_slices(net_a, inputs.h4_ts),/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_start(/,/^def /s/if all(signal\[a\]\[k\] is not None for a in _ASSETS)/if any(signal[a][k] is not None for a in _ASSETS)/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    arm_b = scale_positions(arm_a, scales)/    arm_b = scale_positions(arm_a, {a: [0.5] * len(close) for a in scales})/' -- uv run pytest 'tests/test_research_command.py::test_where_no_signal_crosses_its_threshold_a_b2_overlays_arm_b_is_arm_a_bit_for_bit' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_preflight_metrics(/,/^def /s/        "arm_a_max_drawdown_full": max_drawdown(net_a),/        "arm_a_max_drawdown_full": max_drawdown(bench),/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_preflight_metrics(/,/^def /s/turnover_a \/ len(inputs.close)/turnover_a \/ len(inputs.h4_ts)/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_engagement(/,/^def /s/p > 0 and s < 1/p > 0 and s <= 1/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_engagement(/,/^def /s/        "primary_returns": len(close) - _b2_overlay_start(inputs),/        "primary_returns": len(close),/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _build_b2_liq_derisk_preflight(/,/^def /s/        _b2_liq_signal,/        _b2_oi_signal,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_start(/,/^def /s/for a in _ASSETS)), len(inputs.close))/for a in _ASSETS)), 0)/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_preflight_whose_signal_no_close_carries_prints_its_figures_at_zero' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_as_of_before_any_read[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_as_of_before_any_read[b2-liq-derisk-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_as_of_before_any_read[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_as_of_before_any_read[b2-oi-derisk-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_as_of_before_any_read[b2-ratio-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_as_of_before_any_read[b2-ratio-derisk-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-liq-derisk": Subject(/,/^    ),/s/verdict=_b2_overlay_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-oi-derisk": Subject(/,/^    ),/s/verdict=_b2_overlay_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-ratio-derisk": Subject(/,/^    ),/s/verdict=_b2_overlay_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-b2-ratio-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-liq-derisk": Subject(/,/^    ),/s/n_trials=_B2_LIQ_N_TRIALS,/n_trials=5,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-oi-derisk": Subject(/,/^    ),/s/n_trials=_B2_OI_N_TRIALS,/n_trials=3,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-ratio-derisk": Subject(/,/^    ),/s/n_trials=_B2_RATIO_N_TRIALS,/n_trials=4,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b2-ratio-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    if len(close) - start < 2:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_start_it_cannot_evaluate_before_any_bar[oi-one-index-from-the-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    if len(close) - start < 2:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_start_it_cannot_evaluate_before_any_bar[liquidations-no-index-from-the-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_metrics(/,/^def /s/    if drawdown_a == 0:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_trial_refuses_a_start_it_cannot_evaluate_before_any_bar[oi-arm-a-never-draws-down-from-the-start]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_oi_signal(/,/^def /s/raise SubjectError(f"derivatives-oi\/{relpath}: {exc}") from exc/raise SubjectError(f"oi\/{relpath}: {exc}") from exc/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it[oi]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_ratio_signal(/,/^def /s/raise SubjectError(f"derivatives-oi\/{relpath}: {exc}") from exc/raise SubjectError(f"oi\/{relpath}: {exc}") from exc/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it[ratio]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_oi_signal(/,/^def /s/rows\["sum_open_interest"\].to_list()/rows["sum_open_interest_value"].to_list()/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_overlay_reads_its_signal_off_its_own_columns[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation 's/^_B2_OI_THRESHOLD = 2.5/_B2_OI_THRESHOLD = 2.0/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _build_b2_oi_derisk_preflight(/,/^def /s/        _B2_OI_THRESHOLD,/        2.0,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-oi-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_overlay_inputs(/,/^def /s/    if callable(threshold):/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_engagement_threshold(/,/^def /s/    return min((2.5, 2.0), key=/    return min((2.0, 2.5), key=/' -- uv run pytest 'tests/test_research_command.py::test_the_engagement_threshold_is_the_nearer_of_2_0_and_2_5_to_trial_2s_share[a-tie]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_engagement_threshold(/,/^def /s/ if p > 0 and z is not None\]/ if z is not None]/' -- uv run pytest 'tests/test_research_command.py::test_the_engagement_threshold_is_the_nearer_of_2_0_and_2_5_to_trial_2s_share[flat-stamps-left-out]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_engagement_threshold(/,/^def /s/ \/ len(held) - _B2_TRIAL_2_ENGAGED_SHARE/ \/ sum(p > 0 for a in _ASSETS for p in arm_a[a]) - _B2_TRIAL_2_ENGAGED_SHARE/' -- uv run pytest 'tests/test_research_command.py::test_the_engagement_threshold_is_the_nearer_of_2_0_and_2_5_to_trial_2s_share[unread-long-stamps-left-out]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_engagement_threshold(/,/^def /s/        return 2.5$/        return 2.0/' -- uv run pytest 'tests/test_research_command.py::test_the_engagement_threshold_is_the_nearer_of_2_0_and_2_5_to_trial_2s_share[no-long-stamp-holds-the-signal]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_engagement_threshold(/,/^def /s/key=lambda t: abs(sum(z > t for z in held) \/ len(held) - _B2_TRIAL_2_ENGAGED_SHARE))/key=lambda t: sum(z > t for z in held) \/ len(held) - _B2_TRIAL_2_ENGAGED_SHARE)/' -- uv run pytest 'tests/test_research_command.py::test_the_engagement_threshold_is_the_nearer_of_2_0_and_2_5_to_trial_2s_share[2.0-nearer]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation 's/^_B2_TRIAL_2_ENGAGED_SHARE = 3_486 \/ 70_682/_B2_TRIAL_2_ENGAGED_SHARE = 0.15/' -- uv run pytest 'tests/test_research_command.py::test_the_engagement_threshold_is_the_nearer_of_2_0_and_2_5_to_trial_2s_share[2.5-nearer]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _build_b2_liq_derisk_preflight(/,/^def /s/        _b2_engagement_threshold,/        _B2_RATIO_THRESHOLD,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_liq_signal(/,/^def /s/rows\["long_usd"\].to_list(), h4_ts)/rows["short_usd"].to_list(), h4_ts)/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_overlay_reads_its_signal_off_its_own_columns[b2-liq-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_liq_signal(/,/^def /s/raise SubjectError(f"{_B2_LIQ_SET}\/{relpath}: {exc}") from exc/raise SubjectError(f"{relpath}: {exc}") from exc/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it[liquidation-daily]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_liq_signal(/,/^def /s/raise SubjectError(f"{_B2_LIQ_SET}\/{relpath}: {exc}") from exc/raise SubjectError(f"{relpath}: {exc}") from exc/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_overlay_subject_refuses_a_file_of_its_signal_it_cannot_read_naming_it[liquidation-daily-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/"b2-liq-tape-reading": Subject(/,/^    ),/s/metric_keys=_B2_TAPE_KEYS,/metric_keys=_B2_ARM_A_BAR_KEYS,/' -- uv run pytest 'tests/test_research_command.py::test_the_tape_reading_declares_the_hourly_and_quarter_hour_grids_its_keys_and_no_rule' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_tape_forwards(/,/^def /s/                opens = \[h + 3 \* _QUARTER + j \* _QUARTER/                opens = [h + 4 * _QUARTER + j * _QUARTER/' -- uv run pytest 'tests/test_research_command.py::test_the_tape_forwards_read_from_the_close_its_hour_ends_on_and_merge_a_missing_quarter' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_tape_forwards(/,/^def /s/                if path\[0\] is None or path\[-1\] is None:/                if path[0] is None:/' -- uv run pytest 'tests/test_research_command.py::test_the_tape_forwards_read_from_the_close_its_hour_ends_on_and_merge_a_missing_quarter' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation 's/^_B2_TAPE_THRESHOLD = 2.0/_B2_TAPE_THRESHOLD = 2.5/' -- uv run pytest 'tests/test_research_command.py::test_the_tape_reading_flags_an_hour_whose_z_score_exceeds_2_and_hands_its_forwards_to_the_contrast' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _build_b2_liq_tape_reading(/,$s/liquidation_hourly_totals(\*buckets\[asset\], hours, covered)/liquidation_hourly_totals(*buckets[asset], hours, hours)/' -- uv run pytest 'tests/test_research_command.py::test_the_tape_reading_flags_an_hour_whose_z_score_exceeds_2_and_hands_its_forwards_to_the_contrast' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation 's/^_B2_TAPE_BLOCK = 24/_B2_TAPE_BLOCK = 12/' -- uv run pytest 'tests/test_research_command.py::test_the_tape_reading_flags_an_hour_whose_z_score_exceeds_2_and_hands_its_forwards_to_the_contrast' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation 's/^_B2_TAPE_ZSCORE_HOURS = 720/_B2_TAPE_ZSCORE_HOURS = 360/' -- uv run pytest 'tests/test_research_command.py::test_the_tape_reading_flags_an_hour_whose_z_score_exceeds_2_and_hands_its_forwards_to_the_contrast' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation '/^def _b2_tape_reads(/,/^def /s/            raise SubjectError(f"{_B2_TAPE_SET}\/{relpath}: {exc}") from exc/            raise SubjectError(f"{relpath}: {exc}") from exc/' -- uv run pytest 'tests/test_research_command.py::test_the_tape_reading_refuses_a_bucket_file_it_cannot_read_naming_it' -q -p no:cacheprovider --basetemp=.tmp/pt
```

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(research): B2 trials 3–5's subjects — the OI, ratio and daily-liquidation overlays and their pre-flight twins on a frozen set's full history, and the tape's event-study reading

<the task's pytest result line, pasted from its run over this tree>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<each probe: its infra/scripts/mutate-probe.sh command, then its verdict line>
probe skipped: slow case — tests/test_research_command.py::test_a_b2_overlays_metrics_are_trial_2s_read_from_its_signals_own_start_at_its_count[b2-ratio-derisk]
probe skipped: slow case — tests/test_research_command.py::test_a_b2_overlays_preflight_reads_arm_a_and_the_engagement_and_never_builds_arm_b[b2-ratio-derisk]
probe skipped: slow case — tests/test_research_command.py::test_each_b2_overlay_reads_its_signal_off_its_own_columns[b2-ratio-derisk]
<probe skipped: slow case — each probe row's node id step 5 listed beyond the seventeen>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

______________________________________________________________________

### Task 5: the data-gated basis test, the conventions entry, the reads (D9, D10's (c))

**Files:**
- Create: `tests/test_research_b2_overlays_basis.py` (module-marked `data`)
- Modify: `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 6's own commit

**Interfaces:**
- Consumes: Task 4's `_b2_overlay_inputs`, `_b2_oi_signal`, `_b2_ratio_signal`, `_b2_liq_signal`, `_b2_engagement_threshold`, `_b2_overlay_engagement`, `_b2_returns`, `_ASSETS`; Task 3's blocks, sidecar lines and the spec's `DAILY_BASIS` line; `tests.skip_gates.nothing_found_under`; `tests.test_trial_registry_provenance._trials`.
- Produces: four tests sharing one module-scoped read; the module names `_CLOSES_PER_YEAR`, `_START`, `ENGAGED_PER_ASSET`, `ENGAGED_PER_YEAR`, `coverage()`, `daily_basis()` and `attested()`, which Task 6's check programs import. No test computes a bar or a position or return of arm B.

- [ ] **Step 1: Write the test** — every OI and ratio literal copied from the spec's measured basis, the daily block's read from the spec's `DAILY_BASIS` line, never from a run:

```python
"""B2 trials 3-5's inputs half on the frozen ohlc-full set against spec 00138's measured basis -- the OI and ratio signals'
coverage, start and engagement, the daily liquidations block's attestation and its signal against the spec's completed
basis, the 1-minute block's attestation -- and arm A against records 50 and 51's stored figures: no bar, and no position
or return of arm B."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import B2Config, derisk_scales, net_of_cost
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from cli.validation import max_drawdown, sharpe
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _trials

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the basis test's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_SIDECAR = Path(__file__).resolve().parents[1] / "docs" / "reference" / "vouched-dataset-hashes.jsonl"
_SPEC = Path(__file__).resolve().parents[1] / "docs" / "specs" / "00138-b2-three-overlays-design.md"
# Copied from the spec's measured basis, never from a run.
_BLOCK_HASH = "69d7e9d6b531de063810c35b9a75c6538948f4e526ad2769ad0f961a03f078cf"
_RETURN_INDICES = 27_337
_CLOSES_PER_YEAR = {
    "2013": 509,
    "2014": 2_190,
    "2015": 2_190,
    "2016": 2_195,
    "2017": 2_190,
    "2018": 2_183,
    "2019": 2_190,
    "2020": 2_196,
    "2021": 2_190,
    "2022": 2_190,
    "2023": 2_190,
    "2024": 2_195,
    "2025": 2_189,
    "2026": 540,
}
# Per overlay: the first close every asset's signal holds, the returns from it, and per asset the closes holding the
# signal in each close year that holds any.
_START = {
    "b2-oi-derisk": (datetime(2021, 12, 30, 20, tzinfo=UTC), 9_311),
    "b2-ratio-derisk": (datetime(2023, 1, 13, 12, tzinfo=UTC), 7_039),
}
_OI_NINE = {"2021": 7, "2022": 2_008, "2023": 2_010, "2025": 2_189, "2026": 540}
_RATIO_NINE = {"2023": 1_755, "2024": 1_835, "2025": 2_009, "2026": 540}
_HELD = {
    "b2-oi-derisk": {
        "ADA": _OI_NINE | {"2024": 1_830},
        "AVAX": _OI_NINE | {"2024": 2_015},
        "BTC": {"2020": 553, "2021": 2_010, "2022": 2_008, "2023": 2_010, "2024": 1_815, "2025": 2_189, "2026": 540},
        "DOGE": _OI_NINE | {"2024": 2_015},
        "DOT": _OI_NINE | {"2024": 2_015},
        "ETH": _OI_NINE | {"2024": 1_835},
        "LINK": _OI_NINE | {"2024": 2_015},
        "LTC": _OI_NINE | {"2024": 1_816},
        "SOL": _OI_NINE | {"2024": 1_829},
        "XRP": _OI_NINE | {"2024": 1_835},
    },
    "b2-ratio-derisk": {
        "ADA": _RATIO_NINE | {"2023": 1_575},
        "AVAX": _RATIO_NINE,
        "BTC": _RATIO_NINE | {"2020": 553, "2021": 2_002},
        "DOGE": _RATIO_NINE,
        "DOT": _RATIO_NINE | {"2023": 1_575},
        "ETH": _RATIO_NINE | {"2025": 1_829},
        "LINK": _RATIO_NINE,
        "LTC": _RATIO_NINE,
        "SOL": _RATIO_NINE,
        "XRP": _RATIO_NINE,
    },
}
ENGAGED_PER_ASSET = {
    "b2-oi-derisk": {
        "ADA": 210,
        "AVAX": 224,
        "BTC": 262,
        "DOGE": 489,
        "DOT": 159,
        "ETH": 237,
        "LINK": 333,
        "LTC": 319,
        "SOL": 181,
        "XRP": 371,
    },
    "b2-ratio-derisk": {
        "ADA": 411,
        "AVAX": 381,
        "BTC": 515,
        "DOGE": 436,
        "DOT": 459,
        "ETH": 224,
        "LINK": 492,
        "LTC": 435,
        "SOL": 418,
        "XRP": 385,
    },
}
ENGAGED_PER_YEAR = {
    "b2-oi-derisk": dict.fromkeys(map(str, range(2013, 2020)), 0)
    | {"2020": 31, "2021": 40, "2022": 556, "2023": 636, "2024": 639, "2025": 725, "2026": 158},
    "b2-ratio-derisk": dict.fromkeys(map(str, range(2013, 2020)), 0)
    | {"2020": 39, "2021": 116, "2022": 0, "2023": 1_394, "2024": 1_236, "2025": 1_139, "2026": 232},
}
_SIGNAL_KEY = {"b2-oi-derisk": "binperp_oi_z30d", "b2-ratio-derisk": "binperp_ratio_max_z30d"}
# Records 48-51's arm A and benchmark, stored unrounded; record 51 keys arm_a_max_drawdown as its from-2021 read's.
ARM_A = {
    "arm_a_ann_sharpe_noc": 1.404998307684581,
    "arm_a_ann_sharpe_noc_decisive": 1.3716011675660076,
    "arm_a_max_drawdown": 0.2154323695072342,
    "turnover_a": 146.18534602048504,
    "arm_a_spot_drag_pct_yr": 0.07026650498259404,
    "benchmark_ann_sharpe_noc": 1.2128451567638199,
    "benchmark_ann_sharpe_noc_decisive": 1.2446890489958136,
}


def daily_basis() -> dict:
    """The daily block's figures as the spec's completed basis prints them on its one `DAILY_BASIS` line."""
    lines = [line for line in _SPEC.read_text().splitlines() if line.startswith("DAILY_BASIS ")]
    assert len(lines) == 1, f"the spec holds {len(lines)} DAILY_BASIS lines, and its completed basis prints one"
    return json.loads(lines[0].removeprefix("DAILY_BASIS "))


def attested(dataset: str) -> dict[str, dict]:
    return {row["relpath"]: row for row in map(json.loads, _SIDECAR.read_text().splitlines()) if row["dataset"] == dataset}


def coverage(name: str) -> dict[str, dict[str, list[int]]]:
    """A signal's per-asset, per-close-year `[non_null, total]` as the basis measured it."""
    return {
        asset: {year: [held.get(year, 0), total] for year, total in _CLOSES_PER_YEAR.items()} for asset, held in _HELD[name].items()
    }


@pytest.fixture(scope="module")
def _reads():
    reader = ObservedReader(_DATA_ROOT)
    oi = subjects._b2_overlay_inputs("b2-oi-derisk", subjects._b2_oi_signal, 2.5, reader, "ohlc-full", None, False)
    ratio = subjects._b2_ratio_signal(reader, oi.h4_ts)
    by_overlay = {
        "b2-oi-derisk": oi,
        "b2-ratio-derisk": oi._replace(signal=ratio, scales=derisk_scales(ratio, config=B2Config(z_threshold=2.5)), threshold=2.5),
    }
    return by_overlay, reader.block()


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet"),
    reason="the frozen ohlc-full set or the derivatives-oi set is absent under data/",
)
def test_the_oi_and_ratio_signals_reproduce_the_measured_basis(_reads):
    assert _DATA_ROOT == research_command._DATA_ROOT
    by_overlay, block = _reads
    assert compute_hash(block) == _BLOCK_HASH
    assert {dataset: (len(entry["files"]), entry["rows"], entry["span"]) for dataset, entry in block.items()} == {
        "derivatives-oi": (10, 5_010_882, ["2020-09-01 00:00:00+00:00", "2026-07-22 23:55:00+00:00"]),
        "ohlc-full": (10, 173_373, ["2013-09-10 20:00:00+00:00", "2026-03-31 20:00:00+00:00"]),
    }
    for name, inputs in by_overlay.items():
        first, returns = _START[name]
        assert (len(inputs.close), inputs.close[_RETURN_INDICES - returns]) == (_RETURN_INDICES, first), name
        assert subjects._b2_overlay_engagement(inputs, _SIGNAL_KEY[name]) == {
            "engaged_per_asset": ENGAGED_PER_ASSET[name],
            "engaged_per_year": ENGAGED_PER_YEAR[name],
            f"{_SIGNAL_KEY[name]}_coverage": coverage(name),
            "primary_returns": returns,
            "threshold": 2.5,
        }, name


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-daily/*/daily.parquet"),
    reason="the frozen ohlc-full set, the derivatives-oi set or the frozen daily liquidations block is absent under data/",
)
def test_the_daily_block_is_attested_and_its_signal_reproduces_the_completed_basis(_reads):
    inputs = _reads[0]["b2-oi-derisk"]
    reader = ObservedReader(_DATA_ROOT)
    signal = subjects._b2_liq_signal(reader, inputs.h4_ts)
    block, rows = reader.block()["liquidations-daily"], attested("liquidations-daily")
    assert set(reader.block()) == {"liquidations-daily"} and set(block["files"]) == set(rows)
    assert set(rows) == {f"{asset}/daily.parquet" for asset in subjects._ASSETS}
    assert block["rows"] == sum(row["rows"] for row in rows.values())
    assert reader.vouched_status() == {"liquidations-daily": "checked (10 vouched hashes)"}
    basis = daily_basis()
    threshold = subjects._b2_engagement_threshold(signal, inputs.arm_a)
    held = inputs._replace(signal=signal, scales=derisk_scales(signal, config=B2Config(z_threshold=threshold)), threshold=threshold)
    keys = ("engaged_per_asset", "engaged_per_year", "binperp_liq_long_z30d_coverage", "primary_returns", "threshold")
    assert subjects._b2_overlay_engagement(held, "binperp_liq_long_z30d") == {key: basis[key] for key in keys}
    # The fetch's window is longer than trial 4's for a fetch up to 95 days after the probe (D6).
    assert basis["primary_returns"] > _START["b2-ratio-derisk"][1]


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "liquidations-frozen/*/buckets.parquet"),
    reason="the frozen 1-minute liquidations block is absent under data/",
)
def test_the_tape_block_is_attested_file_by_file():
    reader = ObservedReader(_DATA_ROOT)
    for relpath in ("covered-hours.parquet", *(f"{asset}/buckets.parquet" for asset in subjects._ASSETS)):
        reader.read_series("liquidations-frozen", relpath)
    block, rows = reader.block()["liquidations-frozen"], attested("liquidations-frozen")
    assert set(block["files"]) == set(rows) and len(rows) == 11
    assert block["rows"] == sum(row["rows"] for row in rows.values())
    assert reader.vouched_status() == {"liquidations-frozen": "checked (11 vouched hashes)"}


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet"),
    reason="the frozen ohlc-full set or the derivatives-oi set is absent under data/",
)
def test_the_overlays_arm_a_reproduces_records_50_and_51s_arm_a(_reads):
    inputs = _reads[0]["b2-oi-derisk"]
    net_a = net_of_cost(inputs.arm_a, subjects._b2_returns(inputs.h4_prices), cost_per_side=0.006)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=0.006)
    turnover_a = book_turnover(inputs.arm_a)

    assert {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / _RETURN_INDICES * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
    } == ARM_A
    assert {key: _trials()[50]["metrics"][key] for key in ARM_A} == ARM_A
    shared = (
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "turnover_a",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
    )
    assert {key: _trials()[51]["metrics"][key] for key in shared} == {key: ARM_A[key] for key in shared}
```

  **Author's call**: one `_b2_overlay_inputs` read builds arm A once, the ratio signal and the scales riding its union through `_b2_ratio_signal` and `derisk_scales` — the same function the OI read runs, at the same threshold — and the daily signal through `_b2_liq_signal` and the subject's own rule, since each arm-A build costs about a minute; each block's test reads it through its own reader, so the block it checks is that block's alone; the daily literals are the completed basis's one line, which Task 3's program printed off the attested block, so the test compares the subject's rule with the program's own writing of it.

- [ ] **Step 2: Run it** — the four sets `data/ohlc-full`, `data/derivatives-oi`, `data/liquidations-daily` and `data/liquidations-frozen` linked in this worktree: `mkdir -p .tmp/plan-00138 && uv run pytest tests/test_research_b2_overlays_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt`, one plain blocking call, `timeout` 600000 ms: `4 passed`, never a skip; `--collect-only` on the transcription: `4 tests collected`. Each node id at 10 s or more (setup counted with the first) joins `tests/slow-cases.txt` at its `sorted()` place, and `tests/test_slow_cases.py` passes.

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b2_overlays_basis.py tests/slow-cases.txt`; the Global Constraints' `T` over the two paths; the two tree walkers its skip gates and data mark meet, `uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` (measured on the transcription `320 passed`); `uv run pre-commit run -a` until clean.

- [ ] **Step 4: Probes** — none for a listed slow case, each recorded `probe skipped: slow case`; a case step 2 measures under 10 s is probed as the Global Constraints have it, with `data/ohlc-full`, `data/derivatives-oi`, `data/liquidations-daily` and `data/liquidations-frozen` linked into the probe worktree by `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/<set> .tmp/plan-00138/probe/data/<set>` and unlinked before its removal, since unlinked every case skips and no mutation can fail it; its row `--file tests/test_research_b2_overlays_basis.py`, the control renaming a `def` the case reaches and the mutation substituting one literal it asserts:
  - `test_the_oi_and_ratio_signals_reproduce_the_measured_basis` — `--control 's/^def coverage(/def coverage_gone(/' --mutation 's/^    "b2-oi-derisk": (datetime(2021, 12, 30, 20, tzinfo=UTC), 9_311),/    "b2-oi-derisk": (datetime(2021, 12, 30, 20, tzinfo=UTC), 9_312),/'`;
  - `test_the_daily_block_is_attested_and_its_signal_reproduces_the_completed_basis` — `--control 's/^def attested(/def attested_gone(/' --mutation 's/"checked (10 vouched hashes)"}/"checked (9 vouched hashes)"}/'`;
  - `test_the_tape_block_is_attested_file_by_file` — `--control 's/^def attested(/def attested_gone(/' --mutation 's/ and len(rows) == 11$/ and len(rows) == 10/'`;
  - `test_the_overlays_arm_a_reproduces_records_50_and_51s_arm_a` — `--control 's/^def _reads(/def _reads_gone(/'`, the case then failing at its fixture's setup, `--mutation 's/^    "turnover_a": 146.18534602048504,/    "turnover_a": 146.18534602048507,/'`, the next float up.

- [ ] **Step 5: Commit**

```bash
git commit -F - <<'EOF'
test(research): B2 trials 3–5's inputs half against the measured and completed bases, the two frozen liquidation blocks' attestations, and arm A against records 50 and 51

<the test's pytest result line, pasted from its run over this tree>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<each probed case: its infra/scripts/mutate-probe.sh command, then its verdict line>
<probe skipped: slow case — each listed node id>
They read data/ohlc-full, data/derivatives-oi, data/liquidations-daily and data/liquidations-frozen: re-run them with the four sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, they skip.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 6: The conventions entry** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`:

```markdown
[iter-182] B2 trials 3–5's conventions, pinned by spec 00138 before its hash (Decision: 1)
  The three trials' details and the tape reading's are fixed in the spec, reviewed, and frozen by its sha256, every record's and reading's `spec_hash`, before any position or return of arm B, any kill bar or any forward read of the tape is computed over the data; each call below is one the spec marks as the author's, every value the owner or specs 00128 and 00137 fixed staying theirs.
  1. **As the spec pins them** — the trials run OI, ratios, daily liquidations, the owner's listing, and the reading after them (D1); each signal takes the one of spec 00128's two thresholds, 2.0 and 2.5, whose engagement share is nearer trial 2's 4.93 %, 2.5 on a tie: OI 2.5 (6.08 % against 11.48 %), ratios 2.5 (12.09 % against 23.84 %), the daily liquidations by the same rule applied in the subject, its pick the completed basis's (D3); the OI leg on the trio's z-score, its one reading on the same scale on every asset (D4); one ratio overlay, not one per ratio, on the four z-scores' maximum where all four are read (D5); the liquidations leg on the daily long side's 30-day z-score, a day read from the first close after it ends — the long side because a long-only book carries the forced sale of leveraged longs and the tape's two sides spike apart — its key carrying no `lowerbound_` (D6); the daily block named `liquidations-daily` with a `ts` day column, fetched once, and the tape's block as one file per coin beside the asserted hours, its coverage asserted for every coin from the one-request fetch, the 31 h finalize lag and a second read 600 s later, a whole poll cycle between, and both blocks pushed once to the hub's `hot/`, as every other cited set reached it (D7); the head-to-head from the first close every asset's signal holds (D8); the counts 2, 3 and 4 fixed by the hash, a stopped predecessor leaving the next one above what the count needs (D8); the variants `B2-<signal>-derisk-a2eq-full-v1`, and arm A by `_b2_inputs`' expression rather than `_b2_inputs` itself (D9); no `--verdict`, and notes naming only what is fixed before each run (D10); an adopt deployed on the B1 precedent, T0123's trigger qualified in its record's commit and the live feed on T0023 (D11); the reading on the hour's total notional, its 720-hour z-score above 2, forwards from the hour's close, volatility from 15-minute closes and one 24-hour-block bootstrap draw shared by every series and coin (D12). Chosen.
  2. **The alternatives each weighed** — the trials in another order; 2.0 for every signal, a threshold fitted per signal, or the liquidations' set by hand after the fetch; the log-delta or the momentum, or a per-asset cut on either; four ratio trials, four B slots for one of the owner's three; the four z-scores' mean, minimum, or the maximum of whichever are defined; the short side or the total for the daily leg, or a day read before it ends; a set name dated by its fetch; the freeze as the tree of finals, about 19,700 files in a record's block; coverage inferred from each coin's own finals; the blocks kept off the hub, its nightly pass then failing on every record that cites them; the next calendar-year boundary as the start; a count raised in place; another variant scheme; `_b2_inputs` called, the funding set entering the OI and ratio records' blocks unread; a `--verdict` asserted; notes reading results into the record; T0123 left reading any ADOPT; the reading on one side, a shorter window, forwards from the hour's open, or a bootstrap drawn per coin.
  Source: spec 00138's **Author's call**s (D1, D3–D12); the owner's words of 2026-10-20 quoted in its ruling.
```

  staged alone, its gate `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-182] B2 trials 3–5's conventions, pinned by spec 00138 before its hash`.

- [ ] **Step 7 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec with its completed basis, this plan, Tasks 1–5 and the conventions entry — as CLAUDE.md orders it: `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every dispatch carries the hash rule — in a `review` or `re-review` `drive` as one sentence in words: nothing runs a bar, arm B or the tape's reading over the real data before the spec's hash, and the data-gated cases run with the frozen full set, the OI set and the two frozen liquidation blocks linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip. Each report names the tip it read, the tip Task 6 step 1 diffs from. Task 6 waits until the trio has closed with no open Critical or Important.

______________________________________________________________________

### Task 6 (the controller's): the gate, the hub push, the spec hash, the develop check, the data tests and the check programs (D7's hub, D10)

**Files:** scratch under `.tmp/plan-00138/`, `hub-dry.out`, `hub-push.out` and `hub-read.out` among it; both blocks pushed to the hub's `hot/` (step 1a).

**Interfaces:** step 1a consumes `cli.config`'s `load_config` and `resolve_push_dest`, `cli.data.sync`'s `push_hot` and the dry-run half it runs before each transfer (`_run_rsync` with `dry_run=True`, `_parse_new_files`, `_verify_outgoing`) and `sidecar_hash_by_path`, and `tests/test_registry_conformance.py`'s `conformance`, `_hub_root` and `FINDING`, the hub pass's own re-hash; it produces both blocks on the hub's `hot/`, and `hub-read.out` holding the read that every file the four citing runs will read is there.

- [ ] **Step 1: The gate** — each check its own call, each read before the next:
  - The reads through Task 5 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00138-b2-three-overlays-design.md docs/research/10.phase4-decisions.md docs/reference/vouched-dataset-hashes.jsonl` exits 0; with no report naming a tip, stop: the reads come first.
  - The conventions entry against the spec at that tip, `grep -n "Author's call" docs/specs/00138-b2-three-overlays-design.md`: each call the entry names reads as the spec makes it; where a fix moved one, the entry is corrected in its own `docs(research)` commit and the first check runs again after a read of it.
  - Arm A's code path since record 51's run: `git log --oneline 044b14d3c0e8e5a247fe70bf25b30f7eb7a65196..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/derivatives cli/data uv.lock pyproject.toml .python-version` lists `e8c8e374b` and `358e6da11` (the spec's measured basis), Tasks 1's and 4's commits and their fixes alone; any other commit is named, step 4's data tests deciding whether it moved arm A.

- [ ] **Step 1a: The hub push** (D7's hub) — after step 1's gate, which reads the trio closed over the blocks' attestation and the completed basis, and before step 2's hash, so no read's finding against a block lands after the block is on `hot/`; three calls, each read before the next. First the dry inspection, which sends nothing:

```bash
uv run python - > .tmp/plan-00138/hub-dry.out 2>&1 <<'EOF'
import subprocess
import sys
from pathlib import Path

from cli.config import load_config, resolve_push_dest
from cli.data.errors import DataSyncError
from cli.data.sync import _parse_new_files, _run_rsync, _verify_outgoing, sidecar_hash_by_path

ROOT = Path("/home/zhaow/Projects/zcrypto-kraken/data")
cfg = load_config()
dest = resolve_push_dest(cfg)
for name in ("liquidations-frozen", "liquidations-daily"):
    if name not in cfg.data.authored_sets:
        sys.exit(f"{name} is not in zcrypto.toml's authored_sets")
    planned = _parse_new_files(_run_rsync(ROOT / name, f"{dest}{name}/", subprocess.run, dry_run=True))
    attested = sorted(sidecar_hash_by_path(name))
    if sorted(planned) != attested:
        sys.exit(f"{name}: the push would send {sorted(planned)}, not the {len(attested)} files its sidecar lines attest")
    try:
        _verify_outgoing(ROOT / name, name, planned)
    except DataSyncError as exc:
        sys.exit(str(exc))
    print(f"{name}: {len(planned)} files to send, each re-hashed against its sidecar line: {sorted(planned)}")
EOF
echo "exit $?"; cat .tmp/plan-00138/hub-dry.out
```

  Exit 0 prints eleven files for `liquidations-frozen` and ten for `liquidations-daily`. A `sys.exit` or a traceback sent nothing and is the owner's question with its line quoted — a set already on `hot/`, which the push would not complete, among them. Then the push, a one-way door — `hot/` keeps what lands and no later push corrects it:

```bash
uv run python - > .tmp/plan-00138/hub-push.out 2>&1 <<'EOF'
from pathlib import Path

from cli.config import load_config, resolve_push_dest
from cli.data.sync import push_hot

report = push_hot(
    Path("/home/zhaow/Projects/zcrypto-kraken/data"),
    [],
    resolve_push_dest(load_config()),
    extra_sets=["liquidations-frozen", "liquidations-daily"],
)
print(f"new {len(report.new_files)}, skipped {report.skipped_existing}: {sorted(report.new_files)}")
EOF
echo "exit $?"; date -u +%FT%TZ; cat .tmp/plan-00138/hub-push.out
```

  Exit 0 prints `new 21, skipped 0`; anything else is the owner's question, quoted whole, since what landed stays. **Author's call** — `push_hot` with the two blocks as `extra_sets`, as `data rebuild` pushes what it minted, rather than `zcrypto data push`, which pushes every authored set out of the data root its checkout's `zcrypto.toml` names and refuses one missing: this worktree's `data/` links only the sets the plan reads, and only this branch's sidecar attests the two blocks; the call here reads this worktree's sidecar and the main checkout's data root and touches no other set, `data/ohlc-holdout-*` among them. Then the read of `hot/`, the hub pass's own re-hash over the files the four citing runs will read:

```bash
uv run python - > .tmp/plan-00138/hub-read.out 2>&1 <<'EOF'
import sys
from pathlib import Path

from cli.registry.observed import ObservedReader
from cli.research import subjects
from tests.test_registry_conformance import FINDING, _hub_root, conformance

ROOT = Path("/home/zhaow/Projects/zcrypto-kraken/data")
WINDOW = ("2026-07-14 11:00:00+00:00", "2026-10-10 23:59:59+00:00")
cited = []
for label, dataset, relpaths in (
    ("the OI and ratio records", "derivatives-oi", [f"{subjects.PERP_SYMBOLS[a]}/oi.parquet" for a in subjects._ASSETS]),
    ("trial 5's record", "liquidations-daily", [f"{a}/daily.parquet" for a in subjects._ASSETS]),
):
    reader = ObservedReader(ROOT)
    subjects._capturing_union(reader, "ohlc-full", 240, None, None, False)
    for relpath in relpaths:
        reader.read_series(dataset, relpath)
    cited.append((label, reader.block()))
reader = ObservedReader(ROOT)
for interval in (60, 15):
    subjects._capturing_union(reader, "ohlc-rolling", interval, WINDOW, "2026-10-10", False)
for relpath in ("covered-hours.parquet", *(f"{a}/buckets.parquet" for a in subjects._ASSETS)):
    reader.read_series("liquidations-frozen", relpath)
cited.append(("the reading", reader.block()))
verdicts = conformance(cited, _hub_root(), frozenset())
for v in verdicts:
    print(v.label, v.dataset, v.verdict, v.detail)
sys.exit(1 if any(v.verdict == FINDING for v in verdicts) else 0)
EOF
echo "exit $?"; cat .tmp/plan-00138/hub-read.out
```

  Exit 0 prints six lines, each `rederived` — `derivatives-oi` and `ohlc-full` for the OI and ratio records, `liquidations-daily` and `ohlc-full` for trial 5's, `liquidations-frozen` and `ohlc-rolling` for the reading; a `finding`, a file missing from `hot/` or holding other bytes, is the owner's question before step 2's hash, since the nightly hub pass would fail on the record or reading that cites it. The read computes no return. The three outputs go to the PR body (Task 12 step 4), with D7's hub window: until the merge carries the blocks' sidecar lines to develop, another checkout's first `data fetch` into a root without the blocks exits on their refusal.

- [ ] **Step 2: D10 (1), the spec hash** — `sha256sum docs/specs/00138-b2-three-overlays-design.md`; its value, pasted from that call, is every run's `--spec-hash` and every record's and reading's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D10 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0: develop has appended nothing since this branch's base, so each append chains onto the branch's own last line; if not, develop is merged first (`git merge --no-edit origin/develop`, alone, then step 1's checks again). It runs again before each trial's pre-flight and the reading (Tasks 7–10 step 1).
- [ ] **Step 4: D10 (3), the data tests on the run's tree** — `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b2_overlays_basis.py tests/test_data_vouched_sidecar.py -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt > .tmp/plan-00138/basis.out 2>&1`, one background call, reads every case passed, never a skip; a failure is the owner's question before the first pre-flight.
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00138/preflight_check.py`, D10's (a)–(e) in order, exit 0 on a pass, else one `sys.exit` naming the step that stopped:

```python
"""Spec 00138 D10's pre-flight read, (a) to (e) in order: exit 0 on a pass, else the one sys.exit naming what stopped it."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from tests.test_research_b2_overlays_basis import _START, ENGAGED_PER_ASSET, ENGAGED_PER_YEAR, attested, coverage, daily_basis

name = sys.argv[1]
signal_key = {"b2-oi-derisk": "binperp_oi_z30d", "b2-ratio-derisk": "binperp_ratio_max_z30d", "b2-liq-derisk": "binperp_liq_long_z30d"}[name]
out = Path(f".tmp/plan-00138/{name}-preflight.out").read_text()
run = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
m, block = run["metrics"], run["datasets"]
print("block", compute_hash(block), run["vouched"])
if name == "b2-liq-derisk":
    union = block.get("ohlc-full", {})
    if not (
        set(block) == {"ohlc-full", "liquidations-daily"}
        and (len(union["files"]), union["rows"], union["span"]) == (10, 173_373, ["2013-09-10 20:00:00+00:00", "2026-03-31 20:00:00+00:00"])
        and set(block["liquidations-daily"]["files"]) == set(attested("liquidations-daily"))
        and len(attested("liquidations-daily")) == 10
        and run["vouched"]["liquidations-daily"] == "checked (10 vouched hashes)"
    ):
        sys.exit("(a) the inputs' block is not the frozen union beside the attested daily block")
elif compute_hash(block) != "69d7e9d6b531de063810c35b9a75c6538948f4e526ad2769ad0f961a03f078cf":
    sys.exit("(a) the inputs' block differs from the spec's")
anchors = {
    "arm_a_ann_sharpe_noc": (1.405, 4),
    "arm_a_ann_sharpe_noc_decisive": (1.3716, 4),
    "arm_a_max_drawdown_full": (0.2154, 4),
    "arm_a_spot_drag_pct_yr": (0.0703, 4),
    "benchmark_ann_sharpe_noc": (1.2128, 4),
    "benchmark_ann_sharpe_noc_decisive": (1.2447, 4),
    "turnover_a": (146.19, 2),
}
off = {key: m[key] for key, (value, digits) in anchors.items() if round(m[key], digits) != value}
if off:
    sys.exit(f"(b) arm A does not reproduce record 45's arm A: {off}")
keys = ("engaged_per_asset", "engaged_per_year", f"{signal_key}_coverage", "primary_returns", "threshold")
if name == "b2-liq-derisk":
    basis = {key: daily_basis()[key] for key in keys}
else:
    basis = dict(zip(keys, (ENGAGED_PER_ASSET[name], ENGAGED_PER_YEAR[name], coverage(name), _START[name][1], 2.5)))
off = [key for key, value in basis.items() if m[key] != value]
if off:
    sys.exit(f"(c) the engagement, the coverage, the start or the threshold differs from the measured basis: {off}")
print("engaged", sum(m["engaged_per_asset"].values()), m["engaged_per_year"], "primary_returns", m["primary_returns"], "threshold", m["threshold"])
if not any(m["engaged_per_asset"].values()):
    sys.exit("(d) the overlay engages no stamp: the dead knob")
print({key: m[key] for key in ("dsr", "dsr_pass", "spa_p_value", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes")})
sys.exit(0 if m["passes"] == 1 else "(e) arm A fails its bar")
```

  `.tmp/plan-00138/record_check.py`, the record's checks:

```python
"""Spec 00138 D9's record, read off the registry's last line against the run's print, its pre-flight's block and the
measured basis: exit 0 when every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b2_overlays_basis import _START, ENGAGED_PER_YEAR, coverage, daily_basis

name, spec_hash = sys.argv[1], sys.argv[2]
signal_key = {"b2-oi-derisk": "binperp_oi_z30d", "b2-ratio-derisk": "binperp_ratio_max_z30d", "b2-liq-derisk": "binperp_liq_long_z30d"}[name]
labels = {
    "b2-oi-derisk": (2, "B2-oi-derisk-a2eq-full-v1"),
    "b2-ratio-derisk": (3, "B2-ratio-derisk-a2eq-full-v1"),
    "b2-liq-derisk": (4, "B2-liq-derisk-a2eq-full-v1"),
}[name]
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(f".tmp/plan-00138/{name}.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]
before = Path(f".tmp/plan-00138/{name}-preflight.out").read_text()
preflight_block = compute_hash(json.JSONDecoder().raw_decode(before, before.index("{"))[0]["datasets"])
subject = SUBJECTS[name]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
if name == "b2-liq-derisk":
    basis = daily_basis()
    expected = (basis["engaged_per_year"], basis[f"{signal_key}_coverage"], basis["primary_returns"], basis["threshold"])
else:
    expected = (ENGAGED_PER_YEAR[name], coverage(name), _START[name][1], 2.5)
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == preflight_block,
    "invocation": invocation
    == {"subject": name, "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"]) == ("B2", *labels, "iter-182", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "engagement": (m["engaged_per_year"], m[f"{signal_key}_coverage"], m["primary_returns"], m["threshold"]) == expected,
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
```

  and `.tmp/plan-00138/reading_check.py`, the reading's (D12):

```python
"""Spec 00138 D12's reading, read off the ledger's last line against the run's print and the tape block's attestation:
exit 0 when every check holds."""

import json
import sys
from pathlib import Path

from cli.research.subjects import SUBJECTS
from tests.test_research_b2_overlays_basis import attested

spec_hash = sys.argv[1]
r = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(".tmp/plan-00138/b2-liq-tape-reading.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
blocks = r["datasets"]
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "invocation": invocation
    == {
        "subject": "b2-liq-tape-reading",
        "dataset": "ohlc-rolling",
        "window": ["2026-07-14 11:00:00+00:00", "2026-10-10 23:59:59+00:00"],
        "as_of": "2026-10-10",
        "accept_holes": False,
        "comparator_trial": None,
    },
    "labels": (r["iteration"], r["outcome"]) == ("iter-182", None),
    "keys": set(m) == SUBJECTS["b2-liq-tape-reading"].metric_keys,
    "printed": printed == m,
    "block": set(blocks) == {"ohlc-rolling", "liquidations-frozen"}
    and list(blocks["ohlc-rolling"]["files"]) == ["index/2026/10/10.json"]
    and set(blocks["liquidations-frozen"]["files"]) == set(attested("liquidations-frozen")),
    "constants": (m["threshold"], m["zscore_hours"], m["mean_block"], m["n_resamples"]) == (2.0, 720, 24, 2000),
}
print(r["reading_id"], checks, "events", m["events_per_asset"])
sys.exit(0 if all(checks.values()) else 1)
```

  Each is written with `cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00138/preflight_check.py .tmp/plan-00138/record_check.py .tmp/plan-00138/reading_check.py`.

______________________________________________________________________

### Task 7 (the controller's): trial 3 — the OI leg, its pre-flight, its run and its record (D4, D10)

Every step's command is read here and run in its step, never before; `<H>` is Task 6 step 2's sha256.

- [ ] **Step 1: The develop check** — Task 6 step 3's two commands; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `uv run zcrypto research eval --subject b2-oi-derisk-preflight --dataset ohlc-full > .tmp/plan-00138/b2-oi-derisk-preflight.out 2>&1`, a plain eval of a subject with no rule, about 3–4 min, one background call; at its notification and on its exit 0, `uv run python .tmp/plan-00138/preflight_check.py b2-oi-derisk`. Exit 0: step 4. One of the check's five `sys.exit` lines: D10's instrument finding, step 3. A traceback from the check, a pre-flight a signal ended, or a refusal before the build (`dataset 'ohlc-full' is absent: …`) is a code or environment fault and the owner's question; a refused build — exit 1 with no traceback, its output ending `b2-oi-derisk-preflight over the full history: …` or naming `derivatives-oi/<PERP>/oi.parquet: …` or `ohlc-full/<ASSET>/EUR/240.parquet: …` first — prints no metrics, keeps no reading, and is recorded in Task 11's T0023 findings with its line quoted, the trial unspent; Task 8 runs regardless.
- [ ] **Step 3: On a stop, the reading** — `uv run zcrypto research eval --subject b2-oi-derisk-preflight --dataset ohlc-full --reading --iteration iter-182 --spec-hash <H> --notes "B2 trial 3's pre-flight (spec 00138 D10): <the check's sys.exit line, quoted>; no verdict, the trial unspent" > .tmp/plan-00138/b2-oi-derisk-reading.out 2>&1`, one background call; then step 6's stop arm.
- [ ] **Step 4: The trial** — one run: `uv run zcrypto research eval --subject b2-oi-derisk --dataset ohlc-full --register --iteration iter-182 --family B2 --n-trials 2 --variant B2-oi-derisk-a2eq-full-v1 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00138/b2-oi-derisk.out 2>&1`, about 5–6 min, one background call, `cat` at its notification. No `--verdict` and no plain eval, before or after. The notes, written before the run, name only what is fixed before it: `subject b2-oi-derisk over ohlc-full, full history, no as-of; arm A the adopted equal-weight A2 4h ensemble, arm B the same ensemble at half its position on an asset while that asset's 180-mark open-interest z-score (sum_open_interest on the regular 4h grid, read at the close) exceeds 2.5, no hold-through, every position change charged 0.006 per side; the hypothesis: the half-scale improves the ensemble's net-of-cost performance through a lower drawdown at the engaged stamps, against the unconditioned ensemble; n_trials 2, var_trials 0.0, the DSR leg binding; the head-to-head from the first close every asset's signal holds (index 18026, 2021-12-30 20:00) decides, the full-window read beside it; pre-flight: block 69d7e9d6…, arm A <the seven anchors>, passes 1, engaged <the total> (<the per-year counts>); park variants, pre-registered: scale 0.25, threshold 3.0; the matrix pre-registered by the spec's sha256 <H>`. A refusal from the count — an orphan, or bucket B spent — comes before the fit or after the print, naming each orphan or the bucket's figure: no record, no reading; T0023 carries it to the owner (Task 11) and Task 8 runs. A stop by the rule writes a reading carrying its attempt, which counts 0: step 6's stop arm. On any other exit — a refused build, a traceback, a signal, a refusal after the print — the attempt check runs, `uv run python -c 'import json; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; a = [x for x in lines if x["kind"] == "begin" and x["invocation"]["subject"] == "b2-oi-derisk"][-1]["attempt"]; print(a, [x["failed"] for x in lines if x["kind"] == "end" and x["attempt"] == a] or "open")'`: a refused build of the window or a set ends its attempt failed, counting 0, recorded in T0023 with its line, the trial unspent; any other `failed` text, `open`, or `<id> [None]` is the owner's question before Task 8, quoted whole with the end of the run's output.
- [ ] **Step 5: The record's checks** — on a record: `uv run python .tmp/plan-00138/record_check.py b2-oi-derisk <H>` exits 0; its printed `counted` is read, never checked, and named on T0016's line (Task 11) when non-empty. A failed check is the owner's question before step 6.
- [ ] **Step 6: The records commit** — on a record: (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-182] Verdict — B2 trial 3 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family B2 n=2)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry, its text to its first `. ` holding no other verdict word; the body: the matrix row that fired, read off the record's stored keys beside its stored verdict with D8's table (`sed -n '/^| Kill bar/,/^  The rows are disjoint/p' docs/specs/00138-b2-three-overlays-design.md`), with `passes`, `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary` and `max_drawdown_reduction_pct` unrounded, `max_drawdown` beside `arm_a_max_drawdown`, the full-window pair beside them; `n_trials` 2, `var_trials` 0.0 and the DSR leg (`dsr_corrected`, `dsr_pass`); the pre-flight's block, anchors and `passes` from `.tmp/plan-00138/b2-oi-derisk-preflight.out`; the engagement proof — `engaged_per_year`, `primary_returns`, `threshold`, `stamps_positions_differ`, `turnover_a` beside `turnover_b`; on a park its variants; on an adopt D11's path in its order; on a reject the hypothesis as the notes word it, archived — in the form of `[iter-181] Verdict — B2 trial 2 REJECT`; (ii) in `tests/test_trial_registry_provenance.py`, `LANDED_N_TRIALS` and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts each gain `"b2-oi-derisk": 2,` after `"b2-funding-derisk-full": 1,`; (iii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<its trial_id>]` at its `sorted()` place; on an adopt, (iv) T0123's `ripe_when` gains `— registry trial <N>, B2 trial 3's ADOPT on the A2 ensemble alone, ripens this only once the P1 combination trial over record 47's book that carries it adopts`, in this commit (D11), and `uv run python infra/scripts/topics-index.py` re-renders `docs/open-topics/README.md`, which carries every live topic's trigger, staged with it. Then `T` over the staged paths — `tests/test_open_topics_frontmatter.py` among the index's readers on an adopt — with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path; `uv run pre-commit run -a` until clean. In the probe worktree (Global Constraints' probe line), `data/ohlc-full` and `data/derivatives-oi` linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/<set> .tmp/plan-00138/probe/data/<set>` and unlinked before its removal: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'trial-<its trial_id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt` passes, one background call, its result line and call time for the message — a difference, or a call under 10 s, the owner's question; then the literal's probe, expected `KILLED`: `infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation 's/^_B2_OI_N_TRIALS = 2 /_B2_OI_N_TRIALS = 3 /' -- uv run pytest tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal -q -p no:cacheprovider --basetemp=.tmp/pt`. Commit, `git add` by path of the registry, the provenance test, the decisions log, the slow-cases file and on an adopt T0123 and the index:

```bash
git commit -F - <<'EOF'
docs(research): B2 trial 3 registered — <verdict>, the OI de-risk on the A2 ensemble, registry trial <N>

<the tie and provenance tests' pytest result line, and the replay case's with its call time>

Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):
<the literal's infra/scripts/mutate-probe.sh command, then its verdict line>
probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<N>]
The replay reads data/ohlc-full and data/derivatives-oi: re-run it with the two sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

  On a stop (step 3, or the rule's stop under `--register`): the ledger's last line is checked — its subject `b2-oi-derisk-preflight` with outcome `null`, or `b2-oi-derisk` with the `no_verdict` text and a non-null `attempt`; its `spec_hash` `<H>`; its metrics the run's printed ones — the entry is `[iter-182] B2 trial 3 — instrument finding, the trial unspent (reading <its reading_id>)`, naming what failed, quoted; no literal; the slow row `[reading-<its id>]`; the replay `-k 'reading-<its id>'`; committed as `docs(research): B2 trial 3 — instrument finding, kept as reading <id>; no trial spent` with no probe. On a refusal from the count or a refused build: no commit here; Task 11 records it.

______________________________________________________________________

### Task 8 (the controller's): trial 4 — the ratio leg, its pre-flight, its run and its record (D5, D10)

Task 7's steps with these values, each command written out: the subject `b2-ratio-derisk`, its twin `b2-ratio-derisk-preflight`, the outputs `.tmp/plan-00138/b2-ratio-derisk-preflight.out`, `.tmp/plan-00138/b2-ratio-derisk-reading.out` and `.tmp/plan-00138/b2-ratio-derisk.out`; the count `--n-trials 3`; the variant `B2-ratio-derisk-a2eq-full-v1`; "B2 trial 4" in every note, entry and message.

- [ ] **Step 1: The develop check** — Task 6 step 3's two commands; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `uv run zcrypto research eval --subject b2-ratio-derisk-preflight --dataset ohlc-full > .tmp/plan-00138/b2-ratio-derisk-preflight.out 2>&1`, one background call (about 5 min: the ratio z-scores run over four columns), then `uv run python .tmp/plan-00138/preflight_check.py b2-ratio-derisk`, read as Task 7 step 2 reads its own.
- [ ] **Step 3: On a stop, the reading** — `uv run zcrypto research eval --subject b2-ratio-derisk-preflight --dataset ohlc-full --reading --iteration iter-182 --spec-hash <H> --notes "B2 trial 4's pre-flight (spec 00138 D10): <the check's sys.exit line, quoted>; no verdict, the trial unspent" > .tmp/plan-00138/b2-ratio-derisk-reading.out 2>&1`.
- [ ] **Step 4: The trial** — `uv run zcrypto research eval --subject b2-ratio-derisk --dataset ohlc-full --register --iteration iter-182 --family B2 --n-trials 3 --variant B2-ratio-derisk-a2eq-full-v1 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00138/b2-ratio-derisk.out 2>&1`, one background call; the notes: `subject b2-ratio-derisk over ohlc-full, full history, no as-of; arm A the adopted equal-weight A2 4h ensemble, arm B the same ensemble at half its position on an asset while the largest of that asset's four 180-mark long/short-ratio z-scores, read only where all four are defined, exceeds 2.5, no hold-through, every position change charged 0.006 per side; the hypothesis: the half-scale improves the ensemble's net-of-cost performance through a lower drawdown at the engaged stamps, against the unconditioned ensemble; n_trials 3, var_trials 0.0, the DSR leg binding; the head-to-head from the first close every asset's signal holds (index 20298, 2023-01-13 12:00) decides, the full-window read beside it; pre-flight: block 69d7e9d6…, arm A <the seven anchors>, passes 1, engaged <the total> (<the per-year counts>); park variants, pre-registered: scale 0.25, threshold 3.0; the matrix pre-registered by the spec's sha256 <H>`; every other exit read as Task 7 step 4 reads its own, the attempt check naming `b2-ratio-derisk`.
- [ ] **Step 5: The record's checks** — `uv run python .tmp/plan-00138/record_check.py b2-ratio-derisk <H>` exits 0.
- [ ] **Step 6: The records commit** — Task 7 step 6's three edits with `[iter-182] Verdict — B2 trial 4 <ADOPT, PARK or REJECT> (registry trial <N>, family B2 n=3)`, `"b2-ratio-derisk": 3,` after `"b2-oi-derisk": 2,` (or after `"b2-funding-derisk-full": 1,` where trial 3 landed no record), and the replay row; on an adopt T0123's qualification naming B2 trial 4, once only — a second adopt adds its record to the same qualification — and the index re-rendered and staged with it, as Task 7's (iv); the replay with the same two sets linked; the literal's probe `--mutation 's/^_B2_RATIO_N_TRIALS = 3$/_B2_RATIO_N_TRIALS = 4/'`, every other argument Task 7's; committed as `docs(research): B2 trial 4 registered — <verdict>, the ratio de-risk on the A2 ensemble, registry trial <N>`, or on a stop as Task 7's stop arm with "B2 trial 4" and `b2-ratio-derisk`.

______________________________________________________________________

### Task 9 (the controller's): trial 5 — the daily liquidations leg, its pre-flight, its run and its record (D6, D10)

Task 7's steps with these values, each command written out: the subject `b2-liq-derisk`, its twin `b2-liq-derisk-preflight`, the outputs `.tmp/plan-00138/b2-liq-derisk-preflight.out`, `.tmp/plan-00138/b2-liq-derisk-reading.out` and `.tmp/plan-00138/b2-liq-derisk.out`; the count `--n-trials 4`; the variant `B2-liq-derisk-a2eq-full-v1`; "B2 trial 5" in every note, entry and message; the sets `data/ohlc-full` and `data/liquidations-daily`.

- [ ] **Step 1: The develop check** — Task 6 step 3's two commands; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `uv run zcrypto research eval --subject b2-liq-derisk-preflight --dataset ohlc-full > .tmp/plan-00138/b2-liq-derisk-preflight.out 2>&1`, one background call, then `uv run python .tmp/plan-00138/preflight_check.py b2-liq-derisk`, read as Task 7 step 2 reads its own, a refused build naming `liquidations-daily/<COIN>/daily.parquet: …` among the files.
- [ ] **Step 3: On a stop, the reading** — `uv run zcrypto research eval --subject b2-liq-derisk-preflight --dataset ohlc-full --reading --iteration iter-182 --spec-hash <H> --notes "B2 trial 5's pre-flight (spec 00138 D10): <the check's sys.exit line, quoted>; no verdict, the trial unspent" > .tmp/plan-00138/b2-liq-derisk-reading.out 2>&1`.
- [ ] **Step 4: The trial** — `uv run zcrypto research eval --subject b2-liq-derisk --dataset ohlc-full --register --iteration iter-182 --family B2 --n-trials 4 --variant B2-liq-derisk-a2eq-full-v1 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00138/b2-liq-derisk.out 2>&1`, one background call; the notes: `subject b2-liq-derisk over ohlc-full, full history, no as-of; arm A the adopted equal-weight A2 4h ensemble, arm B the same ensemble at half its position on an asset while the 30-day z-score of that asset's daily long-side liquidated notional (Coinalyze's daily history of <COIN>USDT_PERP.A, frozen as liquidations-daily, a day read from the first close at or after its end) exceeds <the threshold the pre-flight printed>, the one of 2.0 and 2.5 whose engagement share lies nearer trial 2's 4.93 %, no hold-through, every position change charged 0.006 per side; the hypothesis: the half-scale improves the ensemble's net-of-cost performance through a lower drawdown at the engaged stamps, against the unconditioned ensemble; n_trials 4, var_trials 0.0, the DSR leg binding; the head-to-head from the first close every asset's signal holds (index <the completed basis's>, <its close>) decides, the full-window read beside it; pre-flight: block <its hash>, arm A <the seven anchors>, passes 1, engaged <the total> (<the per-year counts>); park variants, pre-registered: scale 0.25, threshold <one step up: 3.0 from 2.5, 2.5 from 2.0>; the matrix pre-registered by the spec's sha256 <H>`; every other exit read as Task 7 step 4 reads its own, the attempt check naming `b2-liq-derisk`.
- [ ] **Step 5: The record's checks** — `uv run python .tmp/plan-00138/record_check.py b2-liq-derisk <H>` exits 0.
- [ ] **Step 6: The records commit** — Task 7 step 6's three edits with `[iter-182] Verdict — B2 trial 5 <ADOPT, PARK or REJECT> (registry trial <N>, family B2 n=4)`, `"b2-liq-derisk": 4,` after the last landed B2 overlay's line (or after `"b2-funding-derisk-full": 1,` where trials 3 and 4 landed none), and the replay row; on an adopt T0123's qualification naming B2 trial 5 and the index re-rendered, as Task 8's; the replay with `data/ohlc-full` and `data/liquidations-daily` linked; the literal's probe `--mutation 's/^_B2_LIQ_N_TRIALS = 4$/_B2_LIQ_N_TRIALS = 5/'`, every other argument Task 7's; committed as `docs(research): B2 trial 5 registered — <verdict>, the daily liquidation de-risk on the A2 ensemble, registry trial <N>`, its message's replay line naming the two sets, or on a stop as Task 7's stop arm with "B2 trial 5" and `b2-liq-derisk`.

______________________________________________________________________

### Task 10 (the controller's): the tape's reading — its run, its line and its entry (D12, D10 (7))

`<H>` is Task 6 step 2's sha256; the run comes after Task 9's commit, whatever Tasks 7–9 recorded.

- [ ] **Step 1: The develop check** — Task 6 step 3's two commands; `git status --short` prints nothing.
- [ ] **Step 2: The window and the set** — each its own call: `uv run python -c 'import json; print([r["first_ts"] for r in map(json.loads, open("docs/reference/vouched-dataset-hashes.jsonl")) if r["dataset"] == "liquidations-frozen" and r["relpath"] == "covered-hours.parquet"])'` prints `['2026-07-14 11:00:00+00:00']`, the window's pre-registered start, any other value the owner's question; `test ! -e data/ohlc-rolling` exits 0, then `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/ohlc-rolling data/ohlc-rolling`; `test -f data/ohlc-rolling/index/2026/10/10.json` exits 0.
- [ ] **Step 3: The run** — one run, no plain eval before or after it: `uv run zcrypto research eval --subject b2-liq-tape-reading --dataset ohlc-rolling --as-of 2026-10-10 --window "2026-07-14 11:00:00+00:00" "2026-10-10 23:59:59+00:00" --reading --iteration iter-182 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00138/b2-liq-tape-reading.out 2>&1`, one background call, `cat` at its notification; the notes, written before the run: `subject b2-liq-tape-reading over ohlc-rolling as of 2026-10-10, window 2026-07-14 11:00 to 2026-10-10 23:59:59 (the frozen tape's first asserted hour to the rolling set's last bar that day), no holes accepted; descriptive, outside the B2 instrument ruling, no bar, no verdict, no B slot, changing no verdict of trials 3-5; per coin and pooled, the forward 1-, 4- and 24-hour log returns and realized volatility (15-minute closes) from the close of an hour whose 720-hour z-score of liquidated notional (long plus short, the frozen block's covered hours) exceeds 2, against the other hours whose z-score is defined; stationary-bootstrap 95 % bounds of the difference, mean block 24 h, 2000 resamples, seed 42, one draw shared by every series and coin; the return leg mixes long cascades and short squeezes; pre-registered by the spec's sha256 <H>`. A refused build — exit 1 naming `b2-liq-tape-reading over …` or `liquidations-frozen/<file>: …` — keeps no reading and is recorded in T0023 with its line (Task 11); a hole refusal (`… has a hole on …`) contradicts the measured basis and is the owner's question, never re-run with `--accept-holes`; a traceback is the owner's question.
- [ ] **Step 4: The reading's checks** — `uv run python .tmp/plan-00138/reading_check.py <H>` exits 0; a failed check is the owner's question before step 5.
- [ ] **Step 5: The records commit** — (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-182] B2's liquidation tape read as an event study on ohlc-rolling as of 2026-10-10 (reading <its reading_id>)`, its header to its first `. ` holding no verdict word; the body: per series the pooled row — events, others, the two means, the difference and its bounds — unrounded, and the coins whose bounds exclude 0, read off the ledger line; `events_per_asset` and `zscore_hours_per_asset`; that the reading is descriptive, outside the instrument ruling, spends no slot and changes no verdict (D12); the return leg's mixing of the two sides and the tape's coverage caveat (D7), stated; in the form of the `[iter-175]` entry that keeps reading 1; (ii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-<its id>]` at its `sorted()` place when the replay's first call below runs 10 s or more, and not otherwise. Then, (i) staged and (ii) not yet, `T` over the staged paths with the two decisions-log tests and `tests/test_slow_cases.py` by path; `uv run pre-commit run -a`; in the probe worktree with `data/ohlc-full`, `data/ohlc-rolling` and `data/liquidations-frozen` linked and unlinked before its removal, `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'reading-<its id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt` passes, one background call — a difference is the owner's question. A call of 10 s or more stages (ii), and the gate, the probe worktree — the old one unlinked and removed first — and the replay run once more over the new staged tree, its line the message's whatever its time, the first call's alone deciding (ii); under 10 s, (ii) stays out and the first run's line is the message's. Committed as `docs(research): B2's liquidation tape — the event-study reading on ohlc-rolling, kept as reading <id>; no trial spent` with the replay's line and call time, `probe skipped: slow case` for its node id when listed, and the line `The replay reads data/ohlc-full, data/ohlc-rolling and data/liquidations-frozen: re-run it with the three sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.` The entry adds no guard: no probe.

______________________________________________________________________

### Task 11: T0023, T0016, the index and the retirement of the seven subjects (D11, D12)

**Files:** `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/retired_subjects.py`, `tests/test_research_command.py`.

**Interfaces:** Consumes the registry's and the ledger's lines Tasks 7–10 committed and their decisions-log entries; the outcomes Tasks 7–10 hand here with no line in the registry or the ledger — a pre-flight's refused build (Task 7 step 2), a refusal from the count or a refused build under `--register` (Task 7 step 4), Tasks 8 and 9 through Task 7's steps, and the reading's refused build (Task 10 step 3) — each refused line read whole by the controller off its `.tmp/plan-00138/<subject>-preflight.out`, `<subject>.out` or `b2-liq-tape-reading.out` and passed in the dispatch; `topic-ops`; `infra/scripts/topics-index.py`.

- [ ] **Step 1: T0023**, per `topic-ops`, every figure read off the committed records, readings and entries:
  - `## Findings so far` gains one bullet per trial — `**B2 trial 3 <VERDICT> (iter-182, spec 00138, registry trial <N>).**` with the row that fired and the engagement in one or two sentences, or `**B2 trial 3 — instrument finding (iter-182, spec 00138, reading <R>).**` with what failed, or, for an outcome the dispatch passes, `**B2 trial 3 — not run (iter-182, spec 00138).**` with its refused line quoted whole and the trial unspent; trials 4 and 5 alike, trial 5's naming its threshold and window; one for the reading, `**B2's liquidation tape, event study (iter-182, spec 00138, reading <R>).**`, its pooled differences and bounds in a sentence and that it changes no verdict, or, on a refused build, `**B2's liquidation tape, event study — not run (iter-182, spec 00138).**` with its line quoted whole; and one for the two frozen blocks: the tape's eleven files, closed span and asserted hours, and the daily block's ten files and span, each attested and on the hub's `hot/`.
  - `## Done so far` gains a bullet, **B2 trials 3–5 (iter-182, spec/plan 00138)**, naming the ratio z-scores, their all-four maximum, the daily z-score, the hourly totals and the event contrast in `cli/alpha/b2.py`, `zcrypto liquidations-backfill`, the frozen blocks `data/liquidations-frozen/` and `data/liquidations-daily/`, the seven subjects and the data-gated basis test, and the records and readings by id.
  - `## Suggested next steps`: the item `(owner) B2's next step after trial 2's reject` is replaced by `(owner) B2's next step after trials 3–5` — <the verdicts, stops and trials not run in one clause>; a park's variants, a further leg, a trial on the tape, a follow-up the reading's figures invite (the daily history reconciled with the tape, the reading at a later as-of or over a longer span, a per-side reading), or closing the family — the owner's pick, recorded as a `[iter-NNN] B2's next step after trial 5` entry; the later-trials item drops the OI leg and the four ratio columns, keeps the funding variants, and says a trial on the 1-minute tape waits on an instrument whose window reaches the frozen block, which re-proves its coverage, the reading's figures beside it; on an adopt, the live feed's spec after the combination trial (D11); on a refusal from the count, an `(owner)` item naming the trial and each orphan or the bucket's figure its line printed, a further count being a new subject under a new spec (D8).
  - `ripe_when` — on no adopt: `an activity: the owner picks B2's next step after trials 3–5 — a park variant, a further leg, or closing the family — recorded in the decisions log; check: grep -c -E '^\[iter-[0-9]+\] B2.s next step after trial 5' docs/research/10.phase4-decisions.md prints at least 1`; on an adopt: `an activity: the P1 combination trial over record 47's book carrying B2 trial <k>'s arm B is picked for an iteration; check: cat docs/research/10.phase4-decisions.md docs/research/13.phase5-decisions.md | grep -c -E '^\[iter-[0-9]+\] [^.]*combination trial over record 47.s book' prints at least 1`. The check is run as committed and prints 0.
- [ ] **Step 2: T0016** — its budget line reads `B1 spent 5, B2 spent <1 + the records Tasks 7–9 landed>, <19 − those records> remain`, less one for each orphan a record's `attempt.counted` lists, named on that line; its B2 line under `## Done so far` names trials 3–5 and the reading (iter-182, spec/plan `00138`) with their records or readings and verdicts.
- [ ] **Step 3: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 4: The retirement** — **Author's call**, as `tests/retired_subjects.py`'s own rule has it: no trial still to run evaluates the seven subjects, so `RETIRED_SUBJECTS` gains, after `"b2-funding-derisk-full-preflight",`:

```python
        # B2's trials 3-5, their pre-flights and the liquidation tape's reading.
        "b2-oi-derisk",
        "b2-oi-derisk-preflight",
        "b2-ratio-derisk",
        "b2-ratio-derisk-preflight",
        "b2-liq-derisk",
        "b2-liq-derisk-preflight",
        "b2-liq-tape-reading",
```

  and `@pytest.mark.retired` goes above the `@pytest.mark.parametrize(` of `test_the_b2_overlay_rule_maps_the_matrix_to_a_verdict_or_a_stop` and of `test_the_engagement_threshold_is_the_nearer_of_2_0_and_2_5_to_trial_2s_share`, and above `def test_where_no_signal_crosses_its_threshold_a_b2_overlays_arm_b_is_arm_a_bit_for_bit(`, `def test_a_b2_overlay_preflight_whose_signal_no_close_carries_prints_its_figures_at_zero(`, `def test_the_tape_reading_declares_the_hourly_and_quarter_hour_grids_its_keys_and_no_rule(`, `def test_the_tape_forwards_read_from_the_close_its_hour_ends_on_and_merge_a_missing_quarter(`, `def test_the_tape_reading_flags_an_hour_whose_z_score_exceeds_2_and_hands_its_forwards_to_the_contrast(` and `def test_the_tape_reading_refuses_a_bucket_file_it_cannot_read_naming_it(` — the eight functions specific to the seven that no parameter names. Measured on the transcription: `uv run pytest tests/test_research_command.py -m "not retired" --collect-only -q` prints `164/587 tests collected (423 deselected)` with no overlay or tape case kept, and `tests/test_retired_subjects.py` `5 passed`.
- [ ] **Step 5: Gate and commit** — `git add docs/open-topics/T0023-b2-derivatives-data-sourcing.md docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/README.md tests/retired_subjects.py tests/test_research_command.py`; `T` over them with `tests/test_open_topics_frontmatter.py` and `tests/test_retired_subjects.py` by path; `uv run pre-commit run -a` until clean; committed as `docs(open-topics): T0023 and T0016 after B2 trials 3–5 and the tape's reading; the seven subjects retired` with the result line. The retirement adds names to an existing guard's data and marks to existing tests, and no guard: no probe.

______________________________________________________________________

### Task 12: the owner's pick in the decisions log, the read and the PR

- [ ] **Step 1: The decisions-log entry** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`:

```markdown
[iter-182] B2's next step after trial 2 — the OI leg, the four ratio columns and a liquidations trial as one spec with three trials in sequence, the owner's pick, attended, 2026-10-20 (Decision: 3)
  Said: "continue working on T0023 for the B2's next steps: the OI leg, the four ratio columns, and a liquidations trial". Asked how to shape the three, answered: "One spec, three trials in sequence (Recommended)" — one iteration and branch, one spec and plan naming three subjects with one bar and matrix each, one plan review, one task loop; the trials run one after another, each registering its own record, a reject of one never stopping the next; the liquidations trial also does the frozen block's coverage proof spec 00136 left to it. Told that the spec's first draft measured no overlap between the live tape (from 2026-07-14) and frozen `ohlc-full` (to 2026-03-31), said: "the liquidation tape is an area we've never explored. it might be too brutal to just drop it. Is there any (easy) way to align the data set to conduct a meaningful evaluation?"; offered three steps — probe Coinalyze's retention at longer intervals; if the daily history is long enough, trial 5 on a daily backfill on the ruled instrument; the tape's study beside it as a reading — answered: "yes, execute the three recommended steps". The probe found the daily history reaching 2022-08-24 to 2022-09-10 on every coin. Standing from trial 2 and unchanged: the instrument ruling "Frozen ohlc-full (Recommended)", the treatment "Unchanged (Recommended)" and the head-to-head read "From-2021 primary (Recommended)", the read opening at a later signal's own start. The options are T0023's after trial 2's reject, record 51, with the work's two shapes.
  1. **Close the family** — archive T0023 on its two trials: the funding de-risk, the family's lead hypothesis, measured where arm A clears the bar and rejected. Spends no trial and none of a spec, plan, review and run cycle; leaves the OI, ratio and liquidation legs, whose substrates and emitters specs 00131 and 00136 built, untested, and the 19 B slots to B3 and B4.
  2. **Three separate iterations** — a spec, plan, plan review, task loop and pull request per leg, each pre-registered after the one before it has run. A later design could take in an earlier result — the look one spec rules out — at the price of three review cycles and branches for three overlays sharing their instrument, bar, arms and matrix.
  3. **One spec, three trials in sequence** — spec 00138 pre-registers the OI leg, one ratio overlay and the daily liquidations leg on trial 2's instrument and bar, each its own subject, count and record, run OI, ratios, liquidations, every design fixed by one hash before the first runs, and the tape's event study beside them as a reading on `ohlc-rolling`; one review cycle and one branch. Spends up to three B slots, 19 to 16; the reading spends none. Chosen.
```

  Its gate `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00138/pt` and `uv run pre-commit run -a`; committed as `docs(research): [iter-182] B2's next step after trial 2 — the owner's pick, one spec with three trials in sequence, trial 5 on the daily history and the tape a reading`. T0023's trigger before Task 11 read this entry's header, which now prints 1 on that check; Task 11 already moved the topic to its next trigger.
- [ ] **Step 2 (the controller's): The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-182 — B2 trials 3–5: OI, ratio, liquidation de-risk` (72 characters by `wc -m`, at `open-pr`'s cap), its own commit.
- [ ] **Step 3 (the controller's): The read** — the `pre-review` of Tasks 7–12's commits, then `review` over `<the tip the last read covered>..HEAD`, since the commits add files outside that read's range, and `re-review` over a fix of it within the branch's two, each `drive` carrying one sentence in words: the data-gated cases and replays the messages record run with the frozen full set, the OI set, the rolling set and the two frozen liquidation blocks linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 4 (the controller's): The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the three verdicts or stops and the reading, each pre-flight's output and the reading's quoted whole in a fenced block (`.tmp/plan-00138/*-preflight.out`, `.tmp/plan-00138/b2-liq-tape-reading.out`), the freeze's and the backfill's output, the hub push's three (`.tmp/plan-00138/hub-dry.out`, `hub-push.out` and `hub-read.out`) with D7's hub window, every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the delta's read covered. Merged on the owner's word through `merge-pr`; before it, `git status --short --ignored` read, `.tmp/plan-00138` removed, and `unlink data/ohlc-full`, `unlink data/derivatives-oi`, `unlink data/derivatives-funding`, `unlink data/liquidations-frozen`, `unlink data/liquidations-daily` and `unlink data/ohlc-rolling` run in this worktree and in each reader's checkout whose `data/` holds the link; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows `ohlc-full`, `derivatives-oi`, `derivatives-funding`, `ohlc-rolling`, `liquidations-frozen` and `liquidations-daily` still there.

Decisions log: the conventions entry (Task 5 step 6), before the hash; the verdict or instrument-finding entries (Tasks 7–9 step 6), each in its record's commit; the reading's entry (Task 10 step 5); and this task's `[iter-182] B2's next step after trial 2`.
