# C3 trial 1 — aSOPR's low tail as a re-entry for the A1 sleeve's flat state, on the two sets reading 10 read: the compute, the family key, the trial subject and its twin, the data-gated basis test, the gated run and the record, the topics after the verdict — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/alpha/c3_reentry.py tests/test_alpha_c3_reentry.py cli/registry/budget.py cli/research/subjects.py tests/test_trial_registry_provenance.py tests/test_research_command.py tests/test_research_c3_asopr_reentry.py README.md tests/test_research_c3_asopr_reentry_basis.py tests/slow-cases.txt docs/research/10.phase4-decisions.md docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl docs/open-topics/T0228-btc-on-chain-metrics-computed-from-chain-data.md docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/T0123-sleeve-promotion-path.md docs/open-topics/README.md docs/reference/change-index.md docs/specs/00165-c3-trial-1-asopr-reentry-design.md docs/plans/00165-c3-trial-1-asopr-reentry.md` prints `tier: full`, for `tests/test_alpha_c3_reentry.py` and `tests/test_research_c3_asopr_reentry.py` "a test importing cli.alpha.a1", `cli/registry/budget.py` "under cli/registry/", `tests/test_trial_registry_provenance.py` "a test importing cli.registry", `tests/test_research_command.py` "a test importing cli.alpha", `tests/test_research_c3_asopr_reentry_basis.py` "a test importing cli.alpha.b1" once Task 3 has created it, and `docs/reference/trial-registry.jsonl`; measured on the authoring tree). No Fable-floor path: `uv run python infra/scripts/merge-gate.py --fable-paths` printed `CLAUDE.md`, `.claude/`, `cli/engine/`, `cli/capture/`, `infra/ansible/roles/capture/` and `infra/ansible/roles/engine/`, and no task edits one.

**Goal:** C3's trial 1 (spec 00165) — the A1 sleeve as records 44 and 47 build it against the same sleeve with a long re-entry in each asset it holds flat at a daily close under aSOPR's low band, sized as the sleeve's own constants size a book long in every weighted asset and held 7 daily closes, on the frozen snapshot `btc-onchain-20261124T162656Z` and frozen `ohlc-full`: a compute module `cli/alpha/c3_reentry.py`; the family key `C3` in `cli/registry/budget.py`; two research subjects in `cli/research/subjects.py`, the trial and its evaluate-only pre-flight twin, reading reading 10's reads and inputs half; the data-gated test of their inputs half; the trial run through spec 00133's trial-attempts log at C3's count 1, its verdict or stop in the registry and the decisions log; then T0228 and T0016 rewritten for the owner's next pick.

**Architecture:** one new module, one key and no change to an existing function. `cli/alpha/c3_reentry.py`, new: `SLEEVE` (records 44's and 47's `A1Config`), `reentry_fires` (the cell's flag as booleans per asset) and `full_long_positions` (the inverse-vol weight times the vol target of the equal-risk basket, through the sleeve's 7-offset block-start mean). `cli/registry/budget.py`'s `BUCKET_OF` gains `"C3": "C"`. `cli/research/subjects.py` gains three insertions and changes no existing line: the module's import, a block before `SUBJECTS` — `_C3_ASOPR_REENTRY_N_TRIALS`, `_C3_REENTRY_HOLD`, `_C3_REENTRY_DECISIVE_START`, `_C3_REENTRY_BLOCKS`, `_C3_REENTRY_SEEDS`, `_C3ReentryInputs`, `_c3_reentry_inputs`, `_c3_reentry_first_engaged`, `_c3_reentry_engagement`, `_c3_reentry_net`, `_c3_reentry_bar`, `_c3_reentry_benchmark`, `_c3_reentry_arm_a_bar`, `_c3_reentry_metrics`, `_c3_reentry_preflight_metrics`, `_c3_reentry_build`, the two builders, the rule `_c3_asopr_reentry_verdict` and the three key sets — and two `SUBJECTS` entries. Reading 10's `_c3_reads` (`cli/research/subjects.py:5179`) and `_c3_reading_inputs` (`:5216`), `cli/alpha/c3.py`'s `a1_daily_positions` (`:59`) and `flags` (`:81`), `cli/alpha/b2.py`'s `reentry_positions` (`:687`), `net_of_cost` (`:725`) and per-year helpers, `cli/alpha/killbar.py`'s `a1_kill_bar` (`:14`) and `net_of_cost_verdict` (`:151`), and `cli/portfolio/builder.py`'s `build_combined_system` are read as they are. Nothing writes a dataset.

**Tech Stack:** Python 3.14 through uv; polars; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00165-c3-trial-1-asopr-reentry-design.md` — binding; D1–D16 are cited by name and the values below are copied from it. The owner ruled its seven open decisions on 2026-11-24, each the option marked Recommended, quoted at D5, D6, D7, D8, D11, D13 and D16 and in the phase-4 decisions log's seven `[iter-210] C3's trial 1 (spec 00165 D<N>)` entries (`docs/research/10.phase4-decisions.md:1141-1173`). It reads spec 00164's D6, D7 and D12, frozen by reading 10's `spec_hash`. **Iteration:** iter-210. **Topics:** T0228 and T0016's C3 arm. **Branch:** `feat/iter-210-c3-trial-1`, worktree `.claude/worktrees/c3-trial-1`, `data/btc-onchain-20261124T162656Z` and `data/ohlc-full` linked from the main checkout, and no other set. A choice this plan makes that the spec leaves open is marked **Author's call**.

**Spec amendments this plan's writing made**, each in the spec's own commit before this plan's, none contradicting a ruled decision: (i) its head and its hypothesis's last line, which still called the seven decisions open after the owner's picks; (ii) the basis's engagement bullet, which now says that a year a per-year list leaves out counts 0 there — `per_year_counts` keys every year the closes span (`cli/alpha/b4.py:117`), so `events_per_year` and `positions_differ_per_year` carry `2016: 0`; (iii) D14's module bullet, which names `SLEEVE`, and its file list, whose parenthetical names the block as built and which gains `tests/slow-cases.txt`; (iv) D15's step 3, its hash rule's last sentence and the closed-world claim on unchanged functions — records 55's and 56's replays read `liquidations-daily` and `derivatives-funding`, two sets this branch does not link, so the run's step 3 takes reading 10's own basis case, its replay and record 33's regression, and the branch's diff over `cli/alpha/b2.py` holds `reentry_positions` and `net_of_cost`; (v) the guards table's last row, which names what the data-gated case holds — the block, the events per asset and the engagement — and leaves reading 10's `arm` and `counts` to that reading's own basis case.

**What the author ran.** Every code fence below was cut from the files the author ran. Tasks 1–3's code and tests were written in a detached scratch worktree at `3a7878308`, this branch's tip before this plan's two commits, under `.tmp/plan-00165-author/`, and committed there; every `path:line` this plan cites is that tree's. There Task 1's tests measured red at collection in a worktree at the tip holding the test file alone (`1 error in 0.11s`) and green with the module (`10 passed`); Task 2's step 2 selection measured red on the base's `cli/research/subjects.py` and `cli/registry/budget.py` (`36 failed, 8 errors`) and green on the code (`44 passed in 3.64s`), and the rows of `tests/test_research_command.py` carrying the subjects' names green (`15 passed, 1056 deselected in 18.44s`); Task 2's gate ran green in its four parts; Task 1's 25 probe rows and Task 2's 111 ran on the authoring tree, every one `KILLED`. A first pass ran 154 rows over Task 2's code, 152 `KILLED`: 109 of those are listed, and 43, aimed at other keys and arguments of the same functions, are not; the two that `SURVIVED` moved the drawdown pair's start on a fixture whose drawdown from the first engagement equalled its drawdown over the window — `test_the_c3_reentry_trial_reads_its_drawdown_pair_from_the_first_engagement_and_not_over_the_window` was added for them, and aimed at it they are Task 2's rows 92–93. With both sets linked, Task 3's data-gated case measured `1 passed` (a call of 11.33 s), and Task 4 step 4's basis case with the two fixture rows `3 passed in 17.51s`, reading 10's basis case `1 passed in 9.05s` and record 33's regression `1 passed in 3.00s`; Task 4 step 1's count program ran on a fresh log; Task 4 step 5's two extractions were run on this plan's text and the pre-flight check over synthetic pre-flight prints; and Task 6's edits — both arms, and Task 5 step 6's T0123 line — were tried on the base's topics with sample figures, run through the topic and index tests, and reverted. The fences as authored, applied to the tip as the steps say, reproduced every authoring file (checked by a program over the tip's files, the result diffed against the scratch commit). Not run: any `zcrypto research eval` of the two subjects, or either of their computes, over the real sets; reading 10's replay; the record's check program beyond a parse; the record's replay and the literal's probe (Task 5); and the PR (Task 7).

## Global Constraints

- **The books and the costing** (D3–D9): the reads `_c3_reads(reader, dataset, subject)` — the snapshot, its manifest's as-of line and `ohlc-full`'s ten EUR daily legs by `_capturing_union(reader, "ohlc-full", 1440, None, None, False)` — and reading 10's `_c3_reading_inputs(snapshot, daily_ts, daily_prices)`, both unchanged; `--as-of` and `--window` refused before any read. Arm A `reading.positions` less its forming row, `n = len(daily_ts) - 1` rows; the events `reentry_fires(reading.bands["asopr"], reading.states)`; the size `full_long_positions(daily_prices)`; arm B `reentry_positions(arm_a, size, fires, hold=7)`; the returns `{a: _asset_returns(_ffill_btc(daily_prices)[a])}`; every book costed by `net_of_cost(positions, returns, cost_per_side=stress * 0.006)`, `stress` 1.0 or, for the bar's cost-stressed series, 1.5 (the float `1.5 * 0.006`, as the B2 overlays' arm-A bar writes it, `cli/research/subjects.py:2206`); no borrow, no carry, no limit wired; the close of return index `k` is `daily_ts[k + 1]`, and every year key is that close's year.
- **The size's constants** (D7) are read off `SLEEVE = A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)`, never retyped: `basket_lookback` 30, `vol_lookback` 30, `periods_per_year` 365, `max_leverage` 1.0 (`cli/alpha/a1.py:33`), and the cadence off `_A1_CADENCE` 7 and `_block_start` (`cli/portfolio/crossfreq_system.py:77`, `:214`). **Author's call**: the spec's formula carries those values as literals; reading them off the sleeve's own config leaves no second copy to drift, and Task 1's first case pins each to the spec's value.
- **The bars** (D6, D12): every `a1_kill_bar` call `n_trials=1, var_trials=0.0, mean_block=<17 or 102>, seed=<42, 7 or 1234>, cost_stressed_returns=<the book's own ×1.5 series>, regime_slices=calendar_year_slices(<series>, daily_ts), benchmark_slices=calendar_year_slices(bench, daily_ts), decisive_start=230, n_resamples=2000`, `bench = build_combined_system(daily_prices, config=_RECORD33_CONFIG).benchmark_net_of_cost` on the raw union closes; arm B's six cells, the headline (17, 42); arm A's bar at (17, 42); the head-to-heads `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=17, seed=42, n_resamples=2000)` at `first` 0 and at arm B's first engagement, `reentry_first_engaged`, the first return index at which arm B's positions differ from arm A's (97, the spec's basis); the drawdown pair from that index. Refused before any bar, each a `ValidationError` the build turns into a `SubjectError`: fewer than 2 return indices from the first engagement, and an arm A that never draws down from it.
- **The count** (D2, D11): `_C3_ASOPR_REENTRY_N_TRIALS = 1`, `required_n("C3")` as the spec derived it and Task 4 step 1 reads it from the log, fixed by the spec's hash; at `var_trials` 0.0 the DSR leg is the PSR against 0.
- **The rule** (D13): `_c3_asopr_reentry_verdict` — `None` when `arm_a_passes` is 0 or `reentered_per_year` counts no asset-close, `reject` on a failed bar, `adopt` on `head_to_head_mean_outperf_primary > 0` with `head_to_head_spa_p_primary < 0.05` and `max_drawdown_reduction_pct >= -20.0`, `park` on the first without both of the others, `reject` otherwise; the park row names no variant.
- **The record** (D14): family `C3`; `n_trials_in_family` 1; variant `C3-asopr-reentry-a1lf-full-v1`; iteration `iter-210`; seeds (42, 7, 1234); 47 metric keys, the twin's 28; `--dataset btc-onchain-20261124T162656Z`; the block `19ee5c231d34aa4d6f7851ad243765bf9c39058de99a5199f3f9efd7c1674f7a`, reading 10's; no `--verdict`.
- **The pre-flight read** (D15), in this order: (a) the block and both sets' vouched status (Task 3's `BLOCK` and `VOUCHED`); (b) the events, `events_per_year` Task 3's and its sum reading 10's count for `asopr|low|flat`, read off the ledger; (c) the dead knob — a non-zero count in `reentered_per_year`, read before the engagement; (d) the engagement the measured basis's — Task 3's `ENGAGEMENT`; (e) `benchmark_ann_sharpe_noc` within 0.005 of record 33's stored `benchmark_sharpe_full`; (f) arm A's `passes` 1.
- **The hash rule** (D15): before Task 4 step 2 takes the spec's sha256, nobody reads or computes arm B's returns or net-of-cost series, a head-to-head or a bar leg of arm B — by code, a program or arithmetic over a stored figure — nor runs `c3-asopr-reentry` or `c3-asopr-reentry-preflight` over the real sets, nor recomputes, extends or conditions further any forward of reading 10; weights, scales, bands, states, events, sizes, positions, exposures and turnover are allowed — what the data-gated test (Task 3) computes, and no return of a book. `a1_book_returns`, `dynamic_inverse_vol_basket` and `build_combined_system` compute a book's base returns on every call that sizes it; nothing reads them. The fixture cases of Tasks 1–2 run the whole build on planted prices and a planted snapshot, never the real sets. No reader, reviewer or plan-review dispatch runs either new subject, or `_c3_reentry_metrics` or `_c3_reentry_preflight_metrics`, over the real sets before the hash, and every read's dispatch carries this rule. After the hash arm A's returns are read once, by the pre-flight; arm B's once, by the trial's `--register` run, and after it only by its replay case in `tests/test_registry_replay.py`, wherever that case runs with the sets linked. The trial subject is never run as a plain eval.
- **Unchanged** (D4, D14): every existing function and subject of `cli/research/subjects.py` — reading 10's `_c3_reads`, `_c3_reading_inputs` and `c3-onchain-reading` among them — `cli/alpha/a1.py`, `cli/alpha/b2.py`, `cli/alpha/c3.py`, `cli/alpha/killbar.py`, `cli/portfolio/*`, `cli/onchain/*`, `cli/features/*`, `cli/risk/*`, `cli/costs/*`, `cli/validation/*` and `cli/engine/*`; `zcrypto.toml`; every record, reading and adopted artifact. After every task, from the merge base with develop, each its own call: `git diff --name-status $(git merge-base HEAD origin/develop) -- cli/` prints `A	cli/alpha/c3_reentry.py` from Task 1 on and `M	cli/registry/budget.py` and `M	cli/research/subjects.py` beside it from Task 2 on, nothing else; from Task 2 on, `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@')" = 3` and `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@ -[0-9]*,0 ')" = 3` each exit 0 — three hunks, each a pure insertion, so a line changed or added anywhere but at Task 2 step 3's three sites is a fourth hunk or an impure one — and `git diff -U0 $(git merge-base HEAD origin/develop) -- cli/registry/budget.py | grep -c '^@@'` prints 1. Measured on the authoring tree: `@@ -120,0 +121 @@`, `@@ -5324,0 +5326,303 @@` and `@@ -5883,0 +6188,26 @@` in `cli/research/subjects.py`, `@@ -6 +6 @@` in `cli/registry/budget.py`.
- Never edit `docs/specs/00165-c3-trial-1-asopr-reentry-design.md` after Task 4 step 2, nor spec 00164, nor the spec before then except a fix commit a read asks for; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Task 5 names it. Never `git stash`; no amend; never `--no-verify`; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/btc-onchain-20261124T162656Z` and `data/ohlc-full`, links into the main checkout's `data/`, never written under; a worktree that lacks one links it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/<set> <its absolute data/ path>/<set>`. Never `data/ohlc-holdout-*` — not read, not listed, not opened — nor `data/ohlc-rolling`, any other set, `/mnt/zhao-crypto/`, a fleet host, docker, `kraken-cli`, the vault, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`. The trial, every test and every implementer step make no network call and no ssh connection; the controller's `git fetch origin develop` (Task 4 step 3, Task 5 step 1) and Task 7's `gh` calls, push and `merge-pr` are the exceptions. A data link is removed with `test -L <its absolute path> && unlink <its absolute path>`, never `rm`, and after a worktree that held one is removed, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` is read, `ohlc-full` and `btc-onchain-20261124T162656Z` still listed.
- **Research only**: nothing is armed, deployed, converged, pinned, rolled out or dropped — no fleet host, image, unit, alert rule or dashboard is touched, and no step of this plan waits on a maintenance window or a converge gap. This worktree is on `zcrypto-ops`, a live venue-facing host: no play, no `ssh`, no `docker`.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 3 step 5's reads, Tasks 4–5 and Task 7, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the data test, the pre-flight, the register, the replays), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1, 2 and 6 and Task 3's steps 1–4. Every dispatch and reviewer runs on Opus, the model passed explicitly.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00165 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00165/pt` (or a file, or `-k`): every `--basetemp` under `.tmp/plan-00165/` follows `mkdir -p .tmp/plan-00165 &&` in the same command, since pytest creates the base temp's leaf and never its parents. An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file, node id or `-k` selection into parts that cannot, each its own `--basetemp=.tmp/plan-00165/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `mkdir -p .tmp/plan-00165 && bash infra/scripts/consumers.sh --direct <each changed path> 2> .tmp/plan-00165/T.err | sort -u > .tmp/plan-00165/T.txt`, `.tmp/plan-00165/T.err` read before the list is used — never `2>/dev/null`, whose stderr is where a refusal speaks — and `test -s .tmp/plan-00165/T.txt && uv run pytest $(cat .tmp/plan-00165/T.txt) -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00165/pt`, so that an empty list fails closed and never becomes a bare `uv run pytest`; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. Every file a commit carries is staged by explicit path — the registry's line by `--register`, the ledger's by `--reading` or by a stop under `--register`, among them, whose one commit is Task 5 step 6's — since the commit and the probe setup's `git write-tree` read the index while the list reads the working tree. Every list holding `tests/test_research_command.py` runs it in four parts, each one plain blocking call under `-m "not slow and not data"`, `timeout` 600000 ms, so that none can pass 600 s: `tests/test_research_command.py -k "not reentry and not b2"` (`--basetemp=.tmp/plan-00165/pt-1`, measured on the authoring tree, the first three parts running at once in three scratch worktrees, `628 passed, 443 deselected in 317.06s`), `tests/test_research_command.py -k "b2 and not reentry"` (`pt-2`, measured `227 passed, 844 deselected in 326.76s`), `tests/test_research_command.py -k reentry` (`pt-3`, measured `86 passed, 985 deselected in 112.64s`) and the rest of the list, read off `.tmp/plan-00165/T.txt` with that file's line left out (`pt-4`). Every commit message carries the result line of each test command its gate ran, a run over that commit's own tree, and the two trailer lines exactly as the executing session's attribution gives them — `Co-Authored-By:` naming the model that ran the step, and `Claude-Session:`.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
mkdir -p .tmp/plan-00165 &&
  test ! -e .tmp/plan-00165/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00165/probe HEAD &&
  git -C .tmp/plan-00165/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00165/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00165/probe/.tmp
```

  Then, from `.tmp/plan-00165/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, so it fails at import or at its call. A mutation whose text also stands in another function carries the address of its own function's range, `/^def <name>(/,/^def /`, of the rule's, `/^def _c3_asopr_reentry_verdict(/,/^_C3_REENTRY_ENGAGEMENT_KEYS/`, or of its entry's, `/"<subject>": Subject(/,/^    ),/` — the twin builder's range ends at the rule's comment, `/^def _build_c3_asopr_reentry_preflight(/,/^# docs/`, and the pre-flight key set's is `/^_C3_REENTRY_PREFLIGHT_KEYS/,/^)/` — so its dry run changes one line; no pattern holds a `'`. After the last verdict, `git worktree remove --force .tmp/plan-00165/probe` — each data link in it unlinked first, as the Data bullet removes one. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <the hash the setup printed>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes. A row alone takes about 6 s (measured).
- **The subjects' names** (D14): `c3-asopr-reentry` and `c3-asopr-reentry-preflight`, which no registered or retired subject's name equals or opens with a hyphen, and which open none (the spec's basis). The new function in `tests/test_research_command.py` and every function of `tests/test_research_c3_asopr_reentry.py` carry `c3_reentry` in their names, which no other test's name in `tests/test_research_command.py` carries (measured: `grep -c c3_reentry tests/test_research_command.py` printed `0` at the base), so `-k c3_reentry` selects the new function alone there; the shared rows the two subjects add there carry the hyphenated `c3-asopr-reentry` in their ids.

## Task 1: the compute module `cli/alpha/c3_reentry.py` (D3, D7)

**Files:** Create `cli/alpha/c3_reentry.py`, `tests/test_alpha_c3_reentry.py`.

**Interfaces:** Consumes `cli/alpha/a1.py`'s `A1Config` (`:33`) and `_inverse_vol_weights(prices_by_asset, *, lookback)` (`:164`), `cli/alpha/c3.py`'s `flags(band, state, *, tail, in_state)` (`:81`), `cli/benchmark/strategies.py`'s `vol_target(returns, *, target_vol, lookback, max_leverage=1.0)` (`:16`) and `dynamic_inverse_vol_basket(prices_by_asset, *, lookback)` (`:120`), and `cli/portfolio/crossfreq_system.py`'s `_A1_CADENCE` (`:77`), `CrossfreqSystemConfig`, `_dummy_close` (`:190`), `_ffill_btc` (`:199`) and `_block_start` (`:214`); in the tests, `cli/alpha/c3.py`'s `a1_daily_positions` (`:59`). Produces `SLEEVE`, `reentry_fires(band, states) -> dict[str, list[bool]]` and `full_long_positions(daily_prices) -> dict[str, list[float]]`, which Task 2's block imports; each returns one row per close, the forming row last, as `a1_daily_positions` does.

- [ ] **Step 1: Write the failing tests** — `tests/test_alpha_c3_reentry.py`, whole:

```python
import math
import statistics

import pytest

from cli.alpha.a1 import A1Config
from cli.alpha.c3 import a1_daily_positions
from cli.alpha.c3_reentry import SLEEVE, full_long_positions, reentry_fires
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig

ASSETS = CrossfreqSystemConfig().assets
N = 150
# Every close moves the five assets at even places by _move(k) and the five at odd places by twice it, so the calm ones
# weigh 2/15 each and the wild ones 1/15, and the equal-risk basket moves by 4/3 of _move(k).
CALM, WILD = ASSETS[0::2], ASSETS[1::2]


def _move(k: int) -> float:
    return (0.01 + 0.0001 * k) * (1 if k % 2 == 0 else -1)


def _prices(n: int = N) -> dict[str, list[float | None]]:
    prices = {}
    for i, asset in enumerate(ASSETS):
        closes = [10.0 * (i + 1)]
        for k in range(n - 1):
            closes.append(closes[-1] * (1 + (2 if asset in WILD else 1) * _move(k)))
        prices[asset] = closes
    return prices


def _own_daily(weight: float) -> list[float]:
    """The size before the cadence, by hand: no weight and no basket return before row 30, the vol target on the 30
    basket returns before the row, capped at 1."""
    target = 0.12 / math.sqrt(365)
    basket = [0.0 if t < 30 else 4 / 3 * _move(t) for t in range(N)]
    daily = []
    for t in range(N):
        deviation = statistics.stdev(basket[t - 30 : t]) if t >= 30 else 0.0
        daily.append(weight * min(target / deviation, 1.0) if deviation > 0 else 0.0)
    return daily


def _block_start(k: int, offset: int) -> int:
    return 0 if k < offset else offset + 7 * ((k - offset) // 7)


def test_the_sleeve_is_records_44s_and_47s_configuration():
    assert SLEEVE == A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)
    assert (SLEEVE.basket_lookback, SLEEVE.vol_lookback, SLEEVE.periods_per_year, SLEEVE.max_leverage) == (30, 30, 365, 1.0)


def test_the_size_is_the_inverse_vol_weight_times_the_baskets_vol_target_through_the_seven_block_starts():
    size = full_long_positions(_prices())
    assert tuple(size) == ASSETS and {len(rows) for rows in size.values()} == {N}
    for assets, weight in ((CALM, 2 / 15), (WILD, 1 / 15)):
        daily = _own_daily(weight)
        expected = [statistics.mean(daily[_block_start(k, o)] for o in range(7)) for k in range(N)]
        for asset in assets:
            assert size[asset] == pytest.approx(expected, rel=1e-9, abs=1e-15), asset
    # The cap binds on the first sized rows, whose 30 basket returns are nearly all the warm-up's zeros, and not later.
    assert _own_daily(2 / 15)[31] == 2 / 15 and 0 < _own_daily(2 / 15)[100] < 0.5 * 2 / 15


def test_the_size_is_the_sleeves_own_position_once_it_has_been_long_in_every_asset_through_its_windows():
    # Every asset climbs on an alternating step of its own size, so the sleeve is long in all ten from the gate's first
    # warm close, 199; from row 240 every block start's 30 base returns are a fully long book's, the basket's own.
    prices = {}
    for i, asset in enumerate(ASSETS):
        closes = [10.0 * (i + 1)]
        for k in range(299):
            closes.append(closes[-1] * (1.004 + 0.003 * (1 + i / 10) * (1 if k % 2 == 0 else -1)))
        prices[asset] = closes
    sleeve, size = a1_daily_positions(prices), full_long_positions(prices)
    for asset in ASSETS:
        assert sleeve[asset][150] == 0 < size[asset][150]
        assert all(p > 0 for p in sleeve[asset][240:])
        assert size[asset][240:] == pytest.approx(sleeve[asset][240:], rel=1e-9)


@pytest.mark.parametrize("cut", [61, 97, 149])
def test_a_row_of_the_size_reads_no_later_close(cut):
    prices = _prices()
    planted = {a: closes[:cut] + [3 * c for c in closes[cut:]] for a, closes in prices.items()}
    whole, moved = full_long_positions(prices), full_long_positions(planted)
    assert all(moved[a][:cut] == whole[a][:cut] for a in ASSETS)
    assert all(moved[a][cut:] != whole[a][cut:] for a in ASSETS)


def test_an_asset_the_basket_does_not_weight_yet_takes_no_size():
    prices = _prices()
    prices["SOL"] = [None] * 40 + prices["SOL"][40:]
    size = full_long_positions(prices)
    # SOL's first return is at row 40, so its first 30-return window ends at row 70.
    assert set(size["SOL"][:70]) == {0.0} and all(s > 0 for s in size["SOL"][70:])
    assert all(size[a][69] > 0 for a in ASSETS if a != "SOL")


def test_btc_is_sized_across_a_missing_close_on_its_forward_fill():
    prices = _prices()
    prices["BTC"][100] = None
    size = full_long_positions(prices)
    assert all(s > 0 for s in size["BTC"][100:137])


def test_the_size_refuses_an_order_other_than_the_builders():
    prices = _prices()
    reordered = {"BTC": prices["BTC"], **{a: closes for a, closes in prices.items() if a != "BTC"}}
    with pytest.raises(ValueError) as refused:
        full_long_positions(reordered)
    assert str(ASSETS) in str(refused.value) and str(tuple(reordered)) in str(refused.value)


def test_an_event_is_a_flat_close_under_the_low_band():
    band = ["low", "low", "low", "mid", "high", None, "low"]
    states = {
        "BTC": ["flat", "long", None, "flat", "flat", "flat", "flat"],
        "ETH": ["long", "flat", "flat", "flat", "long", None, None],
    }
    assert reentry_fires(band, states) == {
        "BTC": [True, False, False, False, False, False, True],
        "ETH": [False, True, True, False, False, False, False],
    }
```

  **Author's call** — known answers, each a clause of D3 or D7: the sleeve's config and the four values the size reads off it, typed from the spec; the size by hand on a planted union where the five assets at even places move by `_move(k)` and the five at odd places by twice it, so the weights are 2/15 and 1/15 and the basket moves by 4/3 of `_move(k)` — the vol target written out with `statistics.stdev`, its cap binding on the first sized rows and not later, the cadence written out over the seven block starts, the amplitude growing with `k` so a daily size differs from its cadence mean; the size equal to the sleeve's own position where the sleeve has been long in every asset through its windows, D7's "what it is"; no row moved by any later close, at three cuts, the forming row among the rows that do move; an asset the basket does not weight yet sized 0 until its first 30-return window ends; BTC sized across a missing close on its forward fill; the builder's asset order; an event only at a flat close under the low band, none at a `None` state, a long one or another band.
- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00165 && uv run pytest tests/test_alpha_c3_reentry.py -q -p no:cacheprovider --basetemp=.tmp/plan-00165/pt`: collection stops at the import of `cli.alpha.c3_reentry` (measured in the scratch worktree with the module aside: `1 error in 0.11s`).
- [ ] **Step 3: Implement `cli/alpha/c3_reentry.py`**, whole:

```python
"""C3 trial 1's compute (docs/specs/00165-c3-trial-1-asopr-reentry-design.md D3, D7): the cell's events and the size a
re-entry takes.

A position is a fraction of NAV held over return index k, from close k to close k + 1."""

from __future__ import annotations

import math
import statistics

from cli.alpha.a1 import A1Config, _inverse_vol_weights
from cli.alpha.c3 import flags
from cli.benchmark.strategies import dynamic_inverse_vol_basket, vol_target
from cli.portfolio.crossfreq_system import _A1_CADENCE, CrossfreqSystemConfig, _block_start, _dummy_close, _ffill_btc

# Records 44's and 47's A1 sleeve, as `cli/alpha/c3.py`'s `a1_daily_positions` configures it.
SLEEVE = A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)


def reentry_fires(band: list[str | None], states: dict[str, list[str | None]]) -> dict[str, list[bool]]:
    """Per asset and row, the cell's event: the asset flat with a close while the band is low."""
    return {asset: [flag is True for flag in flags(band, held, tail="low", in_state="flat")] for asset, held in states.items()}


def full_long_positions(daily_prices: dict[str, list[float | None]]) -> dict[str, list[float]]:
    """Per asset and row, the position the sleeve's constants give a book long in every weighted asset: its inverse-vol
    weight times the vol target of the equal-risk basket itself, through the sleeve's weekly 7-offset mean. One row per
    close, the last the forming one, as `a1_daily_positions` returns them; the order is refused unless it is the builder's."""
    order = CrossfreqSystemConfig().assets
    if tuple(daily_prices) != order:
        raise ValueError(f"daily_prices must be in the order {order}, got {tuple(daily_prices)}")
    d_pf = _ffill_btc({a: list(closes) + [_dummy_close(closes)] for a, closes in daily_prices.items()})
    rows = len(d_pf["BTC"]) - 1
    weights = _inverse_vol_weights(d_pf, lookback=SLEEVE.basket_lookback)
    scale = vol_target(
        dynamic_inverse_vol_basket(d_pf, lookback=SLEEVE.basket_lookback),
        target_vol=SLEEVE.target_vol / math.sqrt(SLEEVE.periods_per_year),
        lookback=SLEEVE.vol_lookback,
        max_leverage=SLEEVE.max_leverage,
    )
    daily = {a: [weights[k].get(a, 0.0) * scale[k] for k in range(rows)] for a in d_pf}
    return {a: [statistics.mean(daily[a][_block_start(k, o)] for o in range(_A1_CADENCE)) for k in range(rows)] for a in d_pf}
```

- [ ] **Step 4: Run them to verify they pass** — step 2's command, measured `10 passed`.
- [ ] **Step 5: Stage, consumers, gate** — `git add cli/alpha/c3_reentry.py tests/test_alpha_c3_reentry.py`; the Global Constraints' list over the two paths — `tests/test_alpha_c3_reentry.py` on this task's tree, whatever else it names; `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 6: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured in the scratch worktree on the authoring tree, 25 of 25):

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def reentry_fires(/def reentry_fires_gone(/' --mutation 's/tail="low", in_state="flat"/tail="high", in_state="flat"/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_an_event_is_a_flat_close_under_the_low_band' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def reentry_fires(/def reentry_fires_gone(/' --mutation 's/tail="low", in_state="flat"/tail="low", in_state="long"/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_an_event_is_a_flat_close_under_the_low_band' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def reentry_fires(/def reentry_fires_gone(/' --mutation 's/flag is True for flag/flag is not False for flag/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_an_event_is_a_flat_close_under_the_low_band' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/target_vol=0.12)$/target_vol=0.10)/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_sleeve_is_records_44s_and_47s_configuration' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/regime="ensemble", short="off"/regime="single_gate", short="off"/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_sleeve_is_records_44s_and_47s_configuration' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/dynamic_inverse_vol_basket(d_pf, lookback=SLEEVE.basket_lookback)/dynamic_inverse_vol_basket(d_pf, lookback=SLEEVE.basket_lookback + 1)/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_is_the_inverse_vol_weight_times_the_baskets_vol_target_through_the_seven_block_starts' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/target_vol=SLEEVE.target_vol \/ math.sqrt(SLEEVE.periods_per_year)/target_vol=SLEEVE.target_vol \/ SLEEVE.periods_per_year/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_is_the_inverse_vol_weight_times_the_baskets_vol_target_through_the_seven_block_starts' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/lookback=SLEEVE.vol_lookback,/lookback=SLEEVE.vol_lookback + 1,/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_is_the_inverse_vol_weight_times_the_baskets_vol_target_through_the_seven_block_starts' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/max_leverage=SLEEVE.max_leverage,/max_leverage=2 * SLEEVE.max_leverage,/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_is_the_inverse_vol_weight_times_the_baskets_vol_target_through_the_seven_block_starts' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/weights\[k\].get(a, 0.0) \* scale\[k\]/0.1 * scale[k]/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_is_the_inverse_vol_weight_times_the_baskets_vol_target_through_the_seven_block_starts' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/daily\[a\]\[_block_start(k, o)\]/daily[a][k]/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_is_the_inverse_vol_weight_times_the_baskets_vol_target_through_the_seven_block_starts' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/for o in range(_A1_CADENCE)) for k/for o in range(1)) for k/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_is_the_inverse_vol_weight_times_the_baskets_vol_target_through_the_seven_block_starts' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/list(closes) + \[_dummy_close(closes)\]/list(closes)/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_is_the_inverse_vol_weight_times_the_baskets_vol_target_through_the_seven_block_starts' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/statistics.mean(daily/max(daily/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_is_the_inverse_vol_weight_times_the_baskets_vol_target_through_the_seven_block_starts' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/max_leverage=SLEEVE.max_leverage,/max_leverage=2 * SLEEVE.max_leverage,/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_is_the_sleeves_own_position_once_it_has_been_long_in_every_asset_through_its_windows' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/weights\[k\].get(a, 0.0) \* scale\[k\]/0.1 * scale[k]/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_is_the_sleeves_own_position_once_it_has_been_long_in_every_asset_through_its_windows' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/target_vol=SLEEVE.target_vol \/ math.sqrt(SLEEVE.periods_per_year)/target_vol=0.5 * SLEEVE.target_vol \/ math.sqrt(SLEEVE.periods_per_year)/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_is_the_sleeves_own_position_once_it_has_been_long_in_every_asset_through_its_windows' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/daily\[a\]\[_block_start(k, o)\]/daily[a][min(_block_start(k, o) + 1, rows - 1)]/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_a_row_of_the_size_reads_no_later_close[61]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/daily\[a\]\[_block_start(k, o)\]/daily[a][min(_block_start(k, o) + 1, rows - 1)]/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_a_row_of_the_size_reads_no_later_close[97]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/daily\[a\]\[_block_start(k, o)\]/daily[a][min(_block_start(k, o) + 1, rows - 1)]/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_a_row_of_the_size_reads_no_later_close[149]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/_inverse_vol_weights(d_pf, lookback=SLEEVE.basket_lookback)/_inverse_vol_weights(d_pf, lookback=SLEEVE.basket_lookback + 1)/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_an_asset_the_basket_does_not_weight_yet_takes_no_size' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/_inverse_vol_weights(d_pf, lookback=SLEEVE.basket_lookback)/_inverse_vol_weights(d_pf, lookback=SLEEVE.basket_lookback - 1)/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_an_asset_the_basket_does_not_weight_yet_takes_no_size' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/    d_pf = _ffill_btc({a: /    d_pf = dict({a: /' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_btc_is_sized_across_a_missing_close_on_its_forward_fill' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/    if tuple(daily_prices) != order:/    if False:/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_refuses_an_order_other_than_the_builders' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/c3_reentry.py --control 's/^def full_long_positions(/def full_long_positions_gone(/' --mutation 's/must be in the order {order}, got/must be in the order {sorted(order)}, got/' -- uv run pytest 'tests/test_alpha_c3_reentry.py::test_the_size_refuses_an_order_other_than_the_builders' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  Each row moves one clause D3 or D7 gives the module. The event: the band, the state and a `None` flag read as an event (rows 1–3). The sleeve's config: its target and its regime (rows 4–5). The size: the basket's lookback, the target's annualisation, the vol target's lookback and its cap, the weight, the cadence's block start and its seven offsets, the forming row and the mean (rows 6–14); the same size against the sleeve's own position — the cap, the weight and the target (rows 15–17); a one-close look-ahead at each cut (rows 18–20); the weights' lookback one longer and one shorter (rows 21–22); BTC's fill (row 23); the order's refusal and its message (rows 24–25). **Author's call — the clause no row moves**: the dummy close's value, to which no row of the size is sensitive by construction (`_dummy_close`, `cli/portfolio/crossfreq_system.py:190`); row 13 moves its presence.
- [ ] **Step 7: Commit** — `feat(alpha): C3 trial 1's compute — the cell's events as flags per asset, and the size a re-entry takes, the sleeve's inverse-vol weight times the equal-risk basket's vol target through its seven block starts`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 2: the family key, the trial subject and its pre-flight twin (D2–D14)

**Files:** Modify `cli/registry/budget.py`, `cli/research/subjects.py`, `tests/test_trial_registry_provenance.py`, `tests/test_research_command.py`, `README.md`; create `tests/test_research_c3_asopr_reentry.py`.

**Interfaces:** Consumes Task 1's `full_long_positions` and `reentry_fires`; `cli/research/subjects.py`'s `_c3_reads(reader, dataset, subject)` (`:5179`), `_c3_reading_inputs(snapshot, daily_ts, daily_prices)` (`:5216`) and its `positions`, `states` and `bands` fields, `_RECORD33_CONFIG` (`:250`), `_N_RESAMPLES` (`:319`), `_B2_COST_PER_SIDE` (`:321`), `_b2_over` (`:390`), `_B2_ARM_A_BAR_FLAGS` and `_B2_ARM_A_BAR_KEYS` (`:467-468`), `EVALUATION_ERRORS` (`:167`), `PPY_DAILY` (`:156`), `Subject`, `SubjectError` and the names it already imports — `reentry_positions`, `net_of_cost`, `reentry_counts_per_year`, `per_year_positions_differ`, `per_year_turnover`, `per_year_max_drawdown` (`cli/alpha/b2.py:687`, `:725`, `:712`, `:764`, `:775`, `:787`), `per_year_counts` (`cli/alpha/b4.py:117`), `book_turnover` (`cli/alpha/b1.py:210`), `a1_kill_bar`, `net_of_cost_verdict`, `build_combined_system`, `calendar_year_slices` (`cli/portfolio/record44_legs.py:108`), `_asset_returns`, `_ffill_btc`, `max_drawdown`, `sharpe` and `ValidationError` — each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; in the tests, `tests/test_research_command.py`'s `_recording` (`:1570`), `_fake_kill_bar` (`:2087`), `_fake_head_to_head` (`:2129`), `_COMPUTE_ERRORS` (`:8637`), `_c3_dataset` (`:8413`), `_anchor`, `runner` and `app`. Produces the key, the two subjects, `_c3_reentry_inputs`, `_c3_reentry_engagement` and `_C3_ASOPR_REENTRY_N_TRIALS`, which Task 3's test and Task 5's literal read.

- [ ] **Step 1: Write the failing tests** —
  - in `tests/test_trial_registry_provenance.py`, `test_the_budgets_and_buckets_are_the_master_plans_literals`' line `assert budget.BUCKET_OF == {"A1": "A", "B1": "B", "B2": "B", "B3": "B", "B4": "B", "P1": None}, growth` (`:576`) becomes `assert budget.BUCKET_OF == {"A1": "A", "B1": "B", "B2": "B", "B3": "B", "B4": "B", "C3": "C", "P1": None}, growth`;
  - `tests/test_research_c3_asopr_reentry.py`, new, whole:

```python
import math
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import polars as pl
import pytest

from cli.alpha import c3 as alpha_c3
from cli.alpha.a1 import _asset_returns
from cli.alpha.c3_reentry import full_long_positions
from cli.onchain.series import COLUMNS, SCHEMA
from cli.portfolio.builder import CombinedSystemConfig
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, _ffill_btc
from cli.portfolio.record44_legs import calendar_year_slices
from cli.research import subjects
from cli.validation import ValidationError, max_drawdown, sharpe
from tests.test_research_command import _COMPUTE_ERRORS, _fake_head_to_head, _fake_kill_bar, _recording

TRIAL, TWIN = "c3-asopr-reentry", "c3-asopr-reentry-preflight"
PAIR = pytest.mark.parametrize("name", [TRIAL, TWIN])
SPEC = "docs/specs/00165-c3-trial-1-asopr-reentry-design.md"
NO_VERDICT = (
    "instrument finding: arm A fails the bar this window sets, or the re-entry holds no asset at any close; no verdict, the "
    "trial unspent"
)
ASSETS = CrossfreqSystemConfig().assets
UNION_START = datetime(2020, 10, 1, tzinfo=UTC)
N_DAYS = 400
LEAD = 800
SOL_LISTED = 100
# The union indices whose decision reads a low aSOPR: four inside the gate's 200-close warm-up, where the sleeve is flat,
# one where it is long, and six in the fall that closes the gate, three of them on consecutive closes.
LOW = (50, 120, 121, 150, 210, 310, 311, 312, 330, 360, 395)
ENGAGEMENT_KEYS = {
    "reentry_first_engaged",
    "primary_returns",
    "stamps_positions_differ",
    "positions_differ_per_year",
    "events_per_year",
    "reentered_per_year",
    "reentry_entries",
    "events_without_size",
    "turnover_b",
    "turnover_b_per_year",
    "gross_max",
}
ARM_A_BAR_KEYS = {
    "dsr",
    "dsr_pass",
    "spa_p_value",
    "spa_p_value_full",
    "spa_pass",
    "cost_stress_sharpe",
    "cost_stress_pass",
    "worst_slice_sharpe",
    "worst_slice_pass",
    "passes",
}
ANCHOR_KEYS = {
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "arm_a_max_drawdown_full",
    "turnover_a",
    "arm_a_spot_drag_pct_yr",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
}
TRIAL_KEYS = ENGAGEMENT_KEYS | {
    "ann_sharpe_noc",
    "ann_sharpe_noc_decisive",
    "per_period_sharpe",
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
    "dsr_corrected",
    "dsr_pass",
    "spa_pass",
    "spa_p_full",
    "cost_stress_pass",
    "worst_slice_relative_pass",
    "passes",
    "decisive_start",
    "n_resamples",
    "arm_a_passes",
    "spa_p_decisive_b17_s42",
    "spa_p_decisive_b17_s7",
    "spa_p_decisive_b17_s1234",
    "spa_p_decisive_b102_s42",
    "spa_p_decisive_b102_s7",
    "spa_p_decisive_b102_s1234",
    "head_to_head_mean_outperf_full",
    "head_to_head_spa_p_full",
    "head_to_head_mean_outperf_primary",
    "head_to_head_spa_p_primary",
    "max_drawdown",
    "arm_a_max_drawdown",
    "max_drawdown_per_year",
    "arm_a_max_drawdown_per_year",
    "turnover_a",
    "turnover_a_per_year",
    "max_drawdown_primary",
    "arm_a_max_drawdown_primary",
    "max_drawdown_reduction_pct",
}
ADOPTING = {
    "arm_a_passes": 1,
    "reentered_per_year": {"2020": 0, "2021": 3},
    "passes": 1,
    "head_to_head_mean_outperf_primary": 1e-6,
    "head_to_head_spa_p_primary": 0.049,
    "max_drawdown_reduction_pct": -20.0,
}


def _union() -> tuple[list[datetime], dict[str, list[float | None]]]:
    """Every asset rises to index 260, falls to 320 and rises again, on an alternating step of its own size; SOL lists at
    index 100 and BTC has no close at 300. The sleeve is long from the gate's first warm close, 200, into the fall, and
    flat on either side."""
    prices: dict[str, list[float | None]] = {}
    for i, asset in enumerate(ASSETS):
        closes = [10.0 * (i + 1)]
        for k in range(N_DAYS - 1):
            drift = 0.004 if k < 260 else -0.012 if k < 320 else 0.003
            closes.append(closes[-1] * math.exp(drift + 0.004 * (1 + i / 10) * (1 if (k + i) % 2 == 0 else -1)))
        prices[asset] = closes
    prices["SOL"] = [None] * SOL_LISTED + prices["SOL"][SOL_LISTED:]
    prices["BTC"][300] = None
    return [UNION_START + timedelta(days=k) for k in range(N_DAYS)], prices


def _snapshot() -> pl.DataFrame:
    """Day j lies LEAD days before the union's first day; `asopr` is 0.5 on the day before each index of LOW and 1.0 on
    every other, so those days alone sit in its low band."""
    n = LEAD + N_DAYS
    columns = {column: [1.0] * n for column in COLUMNS[3:]}
    columns["price"] = [10_000.0 + j for j in range(n)]
    columns["market_cap"] = [20_000.0 + j for j in range(n)]
    columns["asopr"] = [0.5 if j - LEAD + 1 in LOW else 1.0 for j in range(n)]
    return pl.DataFrame(
        {
            "ts": [UNION_START - timedelta(days=LEAD - j) for j in range(n)],
            "last_height": list(range(n)),
            "last_hash": [f"{j:064x}" for j in range(n)],
        }
        | columns,
        schema=SCHEMA,
    )


@pytest.fixture(scope="module")
def inputs():
    daily_ts, daily_prices = _union()
    return subjects._c3_reentry_inputs(_snapshot(), daily_ts, daily_prices)


def _own_books() -> tuple[dict, dict, dict, dict]:
    """Arm A by the reading's own function, the events and arm B by hand: an asset flat with a close at an index of LOW
    fires, and holds the size through 7 closes from its last event unless the sleeve holds it."""
    _, prices = _union()
    n = N_DAYS - 1
    arm_a = {a: held[:n] for a, held in alpha_c3.a1_daily_positions(prices).items()}
    size = {a: sized[:n] for a, sized in full_long_positions(prices).items()}
    fires = {a: [k in LOW and arm_a[a][k] == 0 and prices[a][k] is not None for k in range(n)] for a in ASSETS}
    arm_b = {}
    for a in ASSETS:
        row, last = [], None
        for k in range(n):
            if arm_a[a][k] > 0:
                last = None
            elif fires[a][k]:
                last = k
            held = arm_a[a][k] == 0 and last is not None and k - last < 7
            row.append(size[a][k] if held and size[a][k] > 0 else arm_a[a][k])
        arm_b[a] = row
    return arm_a, arm_b, fires, size


def _own_net(positions: dict, returns: dict, cost: float) -> list[float]:
    previous, net = dict.fromkeys(positions, 0.0), []
    for k in range(len(returns["BTC"])):
        gross = turnover = 0.0
        for a, held in positions.items():
            gross += held[k] * (returns[a][k] or 0.0)
            turnover += abs(held[k] - previous[a])
            previous[a] = held[k]
        net.append(gross - turnover * cost)
    return net


def _by_close_year(values: list, close: list[datetime]) -> dict[str, list]:
    out: dict[str, list] = {}
    for value, stamp in zip(values, close, strict=True):
        out.setdefault(str(stamp.year), []).append(value)
    return out


def _fake_system(daily_prices, *, config):
    """The benchmark a function of the prices and the config, so one built on other closes or another cost differs."""
    seed = sum(c for closes in daily_prices.values() for c in closes if c is not None) + 1e6 * config.spot_fee_per_side
    return SimpleNamespace(benchmark_net_of_cost=[math.sin(seed + k) / 100 for k in range(len(daily_prices["BTC"]) - 1)])


def _faked(monkeypatch) -> tuple[list, list]:
    bars, reads = [], []

    def kill_bar(*args, **kwargs):
        bars.append((args, kwargs))
        return _fake_kill_bar(*args, **kwargs)

    def head_to_head(*args, **kwargs):
        reads.append((args, kwargs))
        return _fake_head_to_head(*args, **kwargs)

    monkeypatch.setattr(subjects, "a1_kill_bar", kill_bar)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", head_to_head)
    monkeypatch.setattr(subjects, "build_combined_system", _fake_system)
    # A cost of its own, so a benchmark built on the builder's default config differs.
    monkeypatch.setattr(subjects, "_RECORD33_CONFIG", CombinedSystemConfig(spot_fee_per_side=0.0123))
    return bars, reads


def _own_bar(net, stressed, bench, daily_ts, block, seed) -> dict:
    return _fake_kill_bar(
        net,
        bench,
        n_trials=1,
        var_trials=0.0,
        mean_block=block,
        seed=seed,
        cost_stressed_returns=stressed,
        regime_slices=calendar_year_slices(net, daily_ts),
        benchmark_slices=calendar_year_slices(bench, daily_ts),
        decisive_start=230,
        n_resamples=2000,
    )


@PAIR
def test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count(name):
    subject = subjects.SUBJECTS[name]
    assert (subject.name, subject.spec, subject.intervals, subject.assets) == (name, SPEC, (1440,), ())
    assert subject.incumbent is None
    if name == TRIAL:
        assert subject.metric_keys == TRIAL_KEYS and len(TRIAL_KEYS) == 47
        assert (subject.seeds, subject.verdict, subject.no_verdict) == (
            (42, 7, 1234),
            subjects._c3_asopr_reentry_verdict,
            NO_VERDICT,
        )
        assert (subject.family, subject.n_trials, subject.build) == ("C3", 1, subjects._build_c3_asopr_reentry)
    else:
        assert subject.metric_keys == ENGAGEMENT_KEYS | ARM_A_BAR_KEYS | ANCHOR_KEYS and len(subject.metric_keys) == 28
        assert (subject.seeds, subject.verdict, subject.no_verdict) == ((42,), None, None)
        assert (subject.family, subject.n_trials, subject.build) == (None, None, subjects._build_c3_asopr_reentry_preflight)
    assert subjects._C3_ASOPR_REENTRY_N_TRIALS == 1
    assert (subjects._C3_REENTRY_HOLD, subjects._C3_REENTRY_DECISIVE_START) == (7, 230)
    assert (subjects._C3_REENTRY_BLOCKS, subjects._C3_REENTRY_SEEDS) == ((17, 102), (42, 7, 1234))


@pytest.mark.parametrize("name", [TRIAL])
@pytest.mark.parametrize(
    ("change", "verdict"),
    [
        pytest.param({}, "adopt", id="adopt-at-the-bound"),
        pytest.param({"max_drawdown_reduction_pct": -20.000001}, "park", id="park-past-the-drawdown-bound"),
        pytest.param({"head_to_head_spa_p_primary": 0.05}, "park", id="park-at-p-0.05"),
        pytest.param({"head_to_head_mean_outperf_primary": 0.0}, "reject", id="reject-at-no-outperformance"),
        pytest.param({"passes": 0, "head_to_head_mean_outperf_primary": 1.0}, "reject", id="reject-on-a-failed-bar"),
        pytest.param({"arm_a_passes": 0, "passes": 0}, None, id="stop-when-arm-a-fails"),
        pytest.param({"reentered_per_year": {"2020": 0, "2021": 0}, "passes": 0}, None, id="stop-on-the-dead-knob"),
    ],
)
def test_the_c3_reentry_rule_maps_its_metrics_to_a_verdict_or_a_stop(name, change, verdict):
    assert subjects.SUBJECTS[name].verdict({**ADOPTING, **change}) == verdict


class _Unread:
    def __getattr__(self, attribute):
        raise AssertionError(f"a refused run reads nothing, and this one asked for {attribute}")


@PAIR
@pytest.mark.parametrize(
    ("window", "as_of", "refusal"),
    [
        pytest.param(
            None,
            "2026-03-31",
            "{name} evaluates a frozen snapshot whole, never the rolling dataset as of a day: drop --as-of",
            id="as-of",
        ),
        pytest.param(
            ("2021-01-01", "2021-06-01"),
            None,
            "{name} over the window 2021-01-01 .. 2021-06-01: it reads its frozen sets whole, and the bands' history reaches "
            "back past any window's first day; drop --window",
            id="window",
        ),
    ],
)
def test_a_c3_reentry_subject_refuses_as_of_and_a_window_before_any_read(name, window, as_of, refusal):
    with pytest.raises(subjects.SubjectError) as refused:
        subjects.SUBJECTS[name].build(_Unread(), "btc-onchain-test", window, as_of=as_of)
    assert str(refused.value) == refusal.format(name=name)


@PAIR
def test_a_c3_reentry_build_reads_the_readings_sets_and_computes_its_own_half_at_the_count(monkeypatch, name):
    calls = []
    reader, snapshot, daily_ts, daily_prices, built = object(), object(), object(), object(), object()

    def reads(*args):
        calls.append(("reads", args))
        return {}, snapshot, daily_ts, daily_prices

    def half(*args):
        calls.append(("inputs", args))
        return built

    def compute(label):
        def stand_in(*args, **kwargs):
            calls.append((label, args, kwargs))
            return {"computed_by": label}

        return stand_in

    monkeypatch.setattr(subjects, "_c3_reads", reads)
    monkeypatch.setattr(subjects, "_c3_reentry_inputs", half)
    monkeypatch.setattr(subjects, "_c3_reentry_metrics", compute("metrics"))
    monkeypatch.setattr(subjects, "_c3_reentry_preflight_metrics", compute("preflight"))
    monkeypatch.setattr(subjects, "_C3_ASOPR_REENTRY_N_TRIALS", 5)
    own = "metrics" if name == TRIAL else "preflight"

    assert subjects.SUBJECTS[name].build(reader, "btc-onchain-test", None) == {"computed_by": own}
    assert calls == [
        ("reads", (reader, "btc-onchain-test", name)),
        ("inputs", (snapshot, daily_ts, daily_prices)),
        (own, (built,), {"n_trials": 5}),
    ]


@pytest.mark.parametrize(
    ("name", "compute"),
    [(TRIAL, "_c3_reentry_metrics"), (TWIN, "_c3_reentry_preflight_metrics")],
)
def test_each_c3_reentry_builder_names_its_own_subject_and_compute(monkeypatch, name, compute):
    calls = []
    monkeypatch.setattr(subjects, "_c3_reentry_build", lambda *args: calls.append(args) or {"built": name})
    reader = object()

    assert subjects.SUBJECTS[name].build(reader, "btc-onchain-test", ("a", "b"), "2026-03-31", True) == {"built": name}
    assert calls == [(name, getattr(subjects, compute), reader, "btc-onchain-test", ("a", "b"), "2026-03-31")]


@PAIR
@pytest.mark.parametrize("error", _COMPUTE_ERRORS, ids=lambda error: error.__name__)
def test_a_c3_reentry_compute_error_is_refused_over_the_full_history(monkeypatch, name, error):
    monkeypatch.setattr(subjects, "_c3_reads", lambda *args: ({}, None, None, None))

    def raising(*args):
        raise error("the stub's cause")

    monkeypatch.setattr(subjects, "_c3_reentry_inputs", raising)

    with pytest.raises(subjects.SubjectError) as refused:
        subjects.SUBJECTS[name].build(object(), "btc-onchain-test", None)
    assert str(refused.value) == f"{name} over the full history: the stub's cause"


def test_the_c3_reentry_inputs_hold_the_sleeve_the_cells_events_the_size_and_arm_b_and_no_net_series(monkeypatch):
    daily_ts, daily_prices = _union()
    held = _recording(monkeypatch, "reentry_positions", lambda arguments, result: result)

    built = subjects._c3_reentry_inputs(_snapshot(), daily_ts, daily_prices)

    arm_a, arm_b, fires, size = _own_books()
    assert built._fields == ("daily_ts", "daily_prices", "close", "returns", "arm_a", "arm_b", "fires", "size")
    assert (built.daily_ts, built.daily_prices, built.close) == (daily_ts, daily_prices, daily_ts[1:])
    assert built.returns == {a: _asset_returns(_ffill_btc(daily_prices)[a]) for a in ASSETS}
    assert (built.arm_a, built.fires, built.size, built.arm_b) == (arm_a, fires, size, arm_b)
    assert [call[0] for call in held] == [{"asset_positions": arm_a, "full_long": size, "fires": fires, "hold": 7}]
    # The fixture: the sleeve long at 210 and flat at every other index of LOW, SOL unlisted at 50 and unsized at 120 and
    # 121, three overlapping events held as one entry from 310 through 318, and the last hold cut by the set's end.
    assert arm_a["BTC"][210] > 0 and all(arm_a["BTC"][k] == 0 for k in LOW if k != 210)
    assert [k for k, fired in enumerate(fires["BTC"]) if fired] == [k for k in LOW if k != 210]
    assert [k for k, fired in enumerate(fires["SOL"]) if fired] == [k for k in LOW if k not in (50, 210)]
    assert size["SOL"][120] == size["SOL"][121] == 0 and arm_b["SOL"][120:128] == [0.0] * 8
    assert [k for k in range(N_DAYS - 1) if arm_b["BTC"][k] != arm_a["BTC"][k]] == [
        *range(50, 57),
        *range(120, 128),
        *range(150, 157),
        *range(310, 319),
        *range(330, 337),
        *range(360, 367),
        *range(395, 399),
    ]
    assert all(p >= 0 for row in arm_b.values() for p in row)


def test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover(inputs):
    arm_a, arm_b, fires, size = _own_books()
    n, close = N_DAYS - 1, inputs.close
    year = [str(stamp.year) for stamp in close]
    differ = [any(arm_b[a][k] != arm_a[a][k] for a in ASSETS) for k in range(n)]
    reentered = {a: [arm_a[a][k] == 0 and arm_b[a][k] > 0 for k in range(n)] for a in ASSETS}
    turnover = [sum(abs(arm_b[a][k] - (arm_b[a][k - 1] if k else 0.0)) for a in ASSETS) for k in range(n)]

    def per_year(counts: list) -> dict:
        return {y: sum(c for c, at in zip(counts, year, strict=True) if at == y) for y in ("2020", "2021")}

    engagement = subjects._c3_reentry_engagement(inputs)

    assert set(engagement) == ENGAGEMENT_KEYS
    assert engagement["reentry_first_engaged"] == 50 == differ.index(True) and engagement["primary_returns"] == n - 50
    assert engagement["stamps_positions_differ"] == sum(differ) == 49
    assert engagement["positions_differ_per_year"] == per_year(differ) == {"2020": 7, "2021": 42}
    assert (
        engagement["events_per_year"] == per_year([sum(fires[a][k] for a in ASSETS) for k in range(n)]) == {"2020": 9, "2021": 90}
    )
    assert engagement["reentered_per_year"] == per_year([sum(reentered[a][k] for a in ASSETS) for k in range(n)])
    assert engagement["reentered_per_year"] == {"2020": 63, "2021": 412}
    # An entry per asset and hold: seven holds on the nine assets listed at 50, six on SOL, less SOL's unsized one.
    assert engagement["reentry_entries"] == 9 * 7 + 5 == 68
    assert engagement["reentry_entries"] == sum(row[k] and not (k and row[k - 1]) for row in reentered.values() for k in range(n))
    assert engagement["events_without_size"] == 2 == sum(fires[a][k] and size[a][k] == 0 for a in ASSETS for k in range(n))
    assert engagement["turnover_b"] == pytest.approx(sum(turnover), rel=1e-12)
    assert engagement["turnover_b_per_year"] == pytest.approx(per_year(turnover), rel=1e-12)
    assert engagement["gross_max"] == max(math.fsum(arm_b[a][k] for a in ASSETS) for k in range(n))


def test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement(
    monkeypatch, inputs
):
    bars, reads = _faked(monkeypatch)
    arm_a, arm_b, _, _ = _own_books()
    daily_ts, close, returns = inputs.daily_ts, inputs.close, inputs.returns
    net_a, net_b = _own_net(arm_a, returns, 0.006), _own_net(arm_b, returns, 0.006)
    net_a_x15, net_b_x15 = _own_net(arm_a, returns, 1.5 * 0.006), _own_net(arm_b, returns, 1.5 * 0.006)
    bench = _fake_system(inputs.daily_prices, config=subjects._RECORD33_CONFIG).benchmark_net_of_cost
    grid = {(b, s): _own_bar(net_b, net_b_x15, bench, daily_ts, b, s) for b in (17, 102) for s in (42, 7, 1234)}
    bar_a, headline = _own_bar(net_a, net_a_x15, bench, daily_ts, 17, 42), grid[(17, 42)]
    full = _fake_head_to_head(net_b, net_a, mean_block=17, seed=42, n_resamples=2000)
    primary = _fake_head_to_head(net_b[50:], net_a[50:], mean_block=17, seed=42, n_resamples=2000)
    drawdown_a, drawdown_b = max_drawdown(net_a[50:]), max_drawdown(net_b[50:])

    metrics = subjects._c3_reentry_metrics(inputs, n_trials=1)

    assert metrics == {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=365),
        "ann_sharpe_noc_decisive": sharpe(net_b[230:], periods_per_year=365),
        "per_period_sharpe": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=365),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[230:], periods_per_year=365),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=365),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[230:], periods_per_year=365),
        "dsr_corrected": headline["dsr"],
        "dsr_pass": headline["dsr_pass"],
        "spa_pass": headline["spa_pass"],
        "spa_p_full": headline["spa_p_value_full"],
        "cost_stress_pass": headline["cost_stress_pass"],
        "worst_slice_relative_pass": headline["worst_slice_pass"],
        "passes": headline["passes"],
        "decisive_start": 230,
        "n_resamples": 2000,
        "arm_a_passes": bar_a["passes"],
        **{f"spa_p_decisive_b{b}_s{s}": bar["spa_p_value"] for (b, s), bar in grid.items()},
        "head_to_head_mean_outperf_full": full["mean_outperformance"],
        "head_to_head_spa_p_full": full["spa_p_value"],
        "head_to_head_mean_outperf_primary": primary["mean_outperformance"],
        "head_to_head_spa_p_primary": primary["spa_p_value"],
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "max_drawdown_per_year": {y: max_drawdown(r) for y, r in _by_close_year(net_b, close).items()},
        "arm_a_max_drawdown_per_year": {y: max_drawdown(r) for y, r in _by_close_year(net_a, close).items()},
        "turnover_a": subjects.book_turnover(arm_a),
        "turnover_a_per_year": subjects.per_year_turnover(arm_a, close),
        "max_drawdown_primary": drawdown_b,
        "arm_a_max_drawdown_primary": drawdown_a,
        "max_drawdown_reduction_pct": 100 * (drawdown_a - drawdown_b) / drawdown_a,
        **subjects._c3_reentry_engagement(inputs),
    }
    assert set(metrics) == TRIAL_KEYS
    assert len(bars) == 7 and {kwargs["n_trials"] for _, kwargs in bars} == {1} and len(reads) == 2
    assert len({m for m in (full["mean_outperformance"], primary["mean_outperformance"])}) == 2 and drawdown_b != drawdown_a


def test_the_c3_reentry_trial_reads_its_drawdown_pair_from_the_first_engagement_and_not_over_the_window(monkeypatch, inputs):
    _faked(monkeypatch)
    # Both arms long BTC over returns 5 to 39, each a 2 % loss: a drawdown before the first engagement deeper than any
    # after it, the books still one there.
    arm_a, arm_b = ({a: list(held) for a, held in arm.items()} for arm in (inputs.arm_a, inputs.arm_b))
    for arm in (arm_a, arm_b):
        arm["BTC"][5:40] = [0.9] * 35
    returns = inputs.returns | {"BTC": inputs.returns["BTC"][:5] + [-0.02] * 35 + inputs.returns["BTC"][40:]}
    net_a, net_b = _own_net(arm_a, returns, 0.006), _own_net(arm_b, returns, 0.006)
    drawdown_a, drawdown_b = max_drawdown(net_a[50:]), max_drawdown(net_b[50:])

    metrics = subjects._c3_reentry_metrics(inputs._replace(arm_a=arm_a, arm_b=arm_b, returns=returns), n_trials=1)

    assert metrics["reentry_first_engaged"] == 50
    assert (metrics["arm_a_max_drawdown_primary"], metrics["max_drawdown_primary"]) == (drawdown_a, drawdown_b)
    assert metrics["max_drawdown_reduction_pct"] == 100 * (drawdown_a - drawdown_b) / drawdown_a
    assert (metrics["arm_a_max_drawdown"], metrics["max_drawdown"]) == (max_drawdown(net_a), max_drawdown(net_b))
    assert max_drawdown(net_a) > drawdown_a and max_drawdown(net_b) > drawdown_b != drawdown_a


def test_the_c3_reentry_trial_deflates_every_bar_at_the_count_it_is_handed(monkeypatch, inputs):
    bars, _ = _faked(monkeypatch)

    subjects._c3_reentry_metrics(inputs, n_trials=4)

    assert len(bars) == 7 and {kwargs["n_trials"] for _, kwargs in bars} == {4}


@pytest.mark.parametrize(
    ("differing", "refusal"),
    [
        pytest.param(
            0, "0 of its return indices follow the re-entry's first engagement, and the head-to-head from it needs 2", id="none"
        ),
        pytest.param(
            1, "1 of its return indices follow the re-entry's first engagement, and the head-to-head from it needs 2", id="one"
        ),
    ],
)
def test_the_c3_reentry_trial_refuses_a_head_to_head_shorter_than_2_before_any_bar(monkeypatch, inputs, differing, refusal):
    bars, reads = _faked(monkeypatch)
    arm_b = {a: list(held) for a, held in inputs.arm_a.items()}
    if differing:
        arm_b["BTC"][-1] = 0.25

    with pytest.raises(ValidationError) as refused:
        subjects._c3_reentry_metrics(inputs._replace(arm_b=arm_b), n_trials=1)

    assert str(refused.value) == refusal and not bars and not reads


def test_the_c3_reentry_trial_refuses_an_arm_a_that_never_draws_down_before_any_bar(monkeypatch, inputs):
    bars, reads = _faked(monkeypatch)
    n = len(inputs.close)
    flat = {a: [0.0] * n for a in ASSETS}
    arm_b = flat | {"BTC": [0.0] * 300 + [0.25] * (n - 300)}

    with pytest.raises(ValidationError) as refused:
        subjects._c3_reentry_metrics(inputs._replace(arm_a=flat, arm_b=arm_b), n_trials=1)

    assert str(refused.value) == (
        "arm A never draws down from the re-entry's first engagement, so max_drawdown_reduction_pct divides by zero"
    )
    assert not bars and not reads


def test_the_c3_reentry_preflight_reads_arm_as_anchors_and_bar_and_the_engagement_and_costs_no_arm_b(monkeypatch, inputs):
    bars, reads = _faked(monkeypatch)
    costed = _recording(monkeypatch, "net_of_cost", lambda arguments, result: result)
    arm_a = _own_books()[0]
    net_a, net_a_x15 = _own_net(arm_a, inputs.returns, 0.006), _own_net(arm_a, inputs.returns, 1.5 * 0.006)
    bench = _fake_system(inputs.daily_prices, config=subjects._RECORD33_CONFIG).benchmark_net_of_cost
    bar = _own_bar(net_a, net_a_x15, bench, inputs.daily_ts, 17, 42)
    turnover_a = subjects.book_turnover(arm_a)

    metrics = subjects._c3_reentry_preflight_metrics(inputs, n_trials=1)

    assert metrics == {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=365),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[230:], periods_per_year=365),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / (N_DAYS - 1) * 0.006 * 365,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=365),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[230:], periods_per_year=365),
        **{key: bar[key] for key in ARM_A_BAR_KEYS},
        **subjects._c3_reentry_engagement(inputs),
    }
    assert [(call[0]["asset_positions"], call[0]["cost_per_side"]) for call in costed] == [(arm_a, 0.006), (arm_a, 1.5 * 0.006)]
    assert len(bars) == 1 and not reads
```

  - in `tests/test_research_command.py`, after `test_the_b3_overlay_trial_refuses_a_plain_eval_and_another_count_before_any_read` and before `def _ruled_signal(` (`:6333`), two blank lines either side:

```python
@pytest.mark.parametrize("name", ["c3-asopr-reentry"])
@pytest.mark.parametrize("plain", [True, False], ids=["plain-eval", "another-count"])
def test_the_c3_reentry_trial_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, name, plain):
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    flags = [] if plain else ["--register", "--iteration", "iter-210", "--family", "C3", "--n-trials", "2"]
    refused = (
        f"{name} declares a verdict rule, so every run of it is a trial: run it with --register"
        if plain
        else f"--n-trials 2 is not 1, the count {name} declares and deflates at: pass --n-trials 1"
    )

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "btc-onchain-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output
```

  - in the same file, `_RULED_FIXTURES` gains `"c3-asopr-reentry": lambda tmp_path: _c3_dataset(tmp_path, subjects.SUBJECTS["c3-asopr-reentry"])[0],` after `"b4-sol-noborrow-rolling": _b4_sol_dataset,` (`:6816`); `_DECLARED_COUNT` gains `"c3-asopr-reentry": "_C3_ASOPR_REENTRY_N_TRIALS",` after `"b4-sol-noborrow-rolling": "_B4_SOL_N_TRIALS",` (`:6837`); the literal of `test_the_ruled_subjects_declare_their_families_and_trial_counts` gains `"c3-asopr-reentry": ("C3", 1),` after `"b4-sol-noborrow-rolling": ("B4", 2),` (`:6861`); and `_CONTRACT_DATASETS` gains `"c3-asopr-reentry": _c3_dataset,` and `"c3-asopr-reentry-preflight": _c3_dataset,` after `"c3-onchain-reading": _c3_dataset,` (`:8488`).

  **Author's call** — new guards where the code is new, the shared rows where it is the registry's: the key's literal; the declaration — the 47 and 28 keys typed from the spec, the spec, intervals, assets, seeds, rule, `no_verdict`, family, count, builders and the five constants; the rule's rows on `ADOPTING`, an adopt exactly at the drawdown bound and a park one step past it, the dead knob read before `passes`; `--as-of` and `--window` refused before any read, on a reader that fails any attribute read; the builders on stand-ins for the reads, the inputs half and the two computes, so the subject name each passes, its arguments in order and the count it calls at are each seen, and each compute-package error refused over the full history; the inputs half on a planted union and snapshot — every asset rising to index 260, falling to 320 and rising again, SOL listed at 100, BTC without a close at 300, aSOPR in its low band on the day before each of eleven indices — held field for field to the test's own books: arm A by reading 10's `a1_daily_positions`, the events and arm B written out by hand, the hold through 7 closes from the last event, an event while the sleeve is long firing nothing, SOL's two unsized events re-entering nothing, three overlapping events one entry, the last hold cut by the set's end, `reentry_positions` called with the size, the events and `hold=7`, the field list pinned and no position below 0; the engagement by hand; the trial's metrics on fakes of the kill bar and the head-to-head whose every value is a function of every argument, and a benchmark at a config of the case's own, so a net costed at another rate, a slice cut on another series, a block, a seed, a count or a key read off another call differs — both arms' nets written out by hand; the drawdown pair on arms planted with a loss before the first engagement, so a pair read over the window differs; the count each bar deflates at; the two refusals before any bar; the pre-flight's anchors and bar, and no book but arm A costed; the plain eval and the count refused at the command before any read. The shared rows — the tracked-spec, contract, shared-defaults and deflation rows, which `_RULED_FIXTURES`, `_DECLARED_COUNT` and `_CONTRACT_DATASETS` reach — run both subjects end to end on `_c3_dataset`, the trial's arm B and real bars among them.
- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00165 && uv run pytest tests/test_research_c3_asopr_reentry.py tests/test_trial_registry_provenance.py::test_the_budgets_and_buckets_are_the_master_plans_literals tests/test_research_command.py::test_the_ruled_subjects_declare_their_families_and_trial_counts 'tests/test_research_command.py::test_the_c3_reentry_trial_refuses_a_plain_eval_and_another_count_before_any_read' -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00165/pt`: collection completes and every selected case fails at its call — on a key `SUBJECTS` or `BUCKET_OF` lacks, a name `subjects` lacks or a subject the CLI does not know — or, for the eight that take the module's `inputs` fixture, errors at its setup on the same lack (measured on the base's `cli/research/subjects.py` and `cli/registry/budget.py` with Task 1's module in place: `36 failed, 8 errors`).
- [ ] **Step 3: Implement** — in `cli/registry/budget.py`, `BUCKET_OF` (`:6`) becomes `BUCKET_OF: dict[str, str | None] = {"A1": "A", "B1": "B", "B2": "B", "B3": "B", "B4": "B", "C3": "C", "P1": None}`. In `cli/research/subjects.py`: after the `from cli.alpha.c2 import (` block and before `from cli.alpha.errors import AlphaError` (`:121`), the line `from cli.alpha.c3_reentry import full_long_positions, reentry_fires`; after `_C3_READING_KEYS = frozenset(…)` (`:5322`) and before `SUBJECTS: dict[str, Subject] = {` (`:5325`), two blank lines on each side:

```python
# docs/specs/00165-c3-trial-1-asopr-reentry-design.md D2-D14: C3's trial 1, a long re-entry in each asset the A1 sleeve
# holds flat at a close under aSOPR's low band, on the two sets reading 10 read; a changed constant is a new trial.
_C3_ASOPR_REENTRY_N_TRIALS = 1  # docs/specs/00165 D2: fixed by the spec's hash; a different count is a new subject
_C3_REENTRY_HOLD = 7
_C3_REENTRY_DECISIVE_START = 230
_C3_REENTRY_BLOCKS = (17, 102)
_C3_REENTRY_SEEDS = (42, 7, 1234)


class _C3ReentryInputs(NamedTuple):
    daily_ts: list[datetime]
    daily_prices: dict[str, list[float | None]]
    close: list[datetime]
    returns: dict[str, list[float | None]]
    arm_a: dict[str, list[float]]
    arm_b: dict[str, list[float]]
    fires: dict[str, list[bool]]
    size: dict[str, list[float]]


def _c3_reentry_inputs(
    snapshot: pl.DataFrame, daily_ts: list[datetime], daily_prices: dict[str, list[float | None]]
) -> _C3ReentryInputs:
    """Both arms' positions and the returns they are costed on, and no return of a book: the half the data-gated case runs
    over the real sets before the spec's hash (docs/specs/00165 D15). The forming row has no return and is dropped."""
    reading = _c3_reading_inputs(snapshot, daily_ts, daily_prices)
    n = len(daily_ts) - 1
    arm_a = {asset: held[:n] for asset, held in reading.positions.items()}
    fires = {asset: fired[:n] for asset, fired in reentry_fires(reading.bands["asopr"], reading.states).items()}
    size = {asset: sized[:n] for asset, sized in full_long_positions(daily_prices).items()}
    arm_b = reentry_positions(arm_a, size, fires, hold=_C3_REENTRY_HOLD)
    fed = _ffill_btc(daily_prices)
    returns = {asset: _asset_returns(fed[asset]) for asset in arm_a}
    return _C3ReentryInputs(daily_ts, daily_prices, daily_ts[1:], returns, arm_a, arm_b, fires, size)


def _c3_reentry_first_engaged(inputs: _C3ReentryInputs) -> int:
    """The first return index at which arm B's positions differ from arm A's, the length when none does."""
    n = len(inputs.close)
    return next((k for k in range(n) if any(inputs.arm_b[a][k] != inputs.arm_a[a][k] for a in inputs.arm_a)), n)


def _c3_reentry_engagement(inputs: _C3ReentryInputs) -> dict:
    close, arm_a, arm_b, fires, size = inputs.close, inputs.arm_a, inputs.arm_b, inputs.fires, inputs.size
    n, start = len(close), _c3_reentry_first_engaged(inputs)
    differ = per_year_positions_differ(arm_a, arm_b, close)
    fired = [per_year_counts(flags, close) for flags in fires.values()]
    reentered = {asset: [arm_a[asset][k] == 0 and arm_b[asset][k] > 0 for k in range(n)] for asset in arm_a}
    return {
        "reentry_first_engaged": start,
        "primary_returns": n - start,
        "stamps_positions_differ": sum(differ.values()),
        "positions_differ_per_year": differ,
        "events_per_year": {year: sum(counts[year] for counts in fired) for year in fired[0]},
        "reentered_per_year": reentry_counts_per_year(arm_a, arm_b, close),
        "reentry_entries": sum(held[k] and not (k and held[k - 1]) for held in reentered.values() for k in range(n)),
        "events_without_size": sum(fires[asset][k] and size[asset][k] == 0 for asset in fires for k in range(n)),
        "turnover_b": book_turnover(arm_b),
        "turnover_b_per_year": per_year_turnover(arm_b, close),
        "gross_max": max(math.fsum(held[k] for held in arm_b.values()) for k in range(n)),
    }


def _c3_reentry_net(positions: dict[str, list[float]], inputs: _C3ReentryInputs, *, stress: float) -> list[float]:
    return net_of_cost(positions, inputs.returns, cost_per_side=stress * _B2_COST_PER_SIDE)


def _c3_reentry_bar(
    net: list[float], stressed: list[float], bench: list[float], inputs: _C3ReentryInputs, *, n_trials: int, block: int, seed: int
) -> dict:
    """Record 34's call of the ratified bar on the daily grid (docs/specs/00165 D6, D12)."""
    return a1_kill_bar(
        net,
        bench,
        n_trials=n_trials,
        var_trials=0.0,
        mean_block=block,
        seed=seed,
        cost_stressed_returns=stressed,
        regime_slices=calendar_year_slices(net, inputs.daily_ts),
        benchmark_slices=calendar_year_slices(bench, inputs.daily_ts),
        decisive_start=_C3_REENTRY_DECISIVE_START,
        n_resamples=_N_RESAMPLES,
    )


def _c3_reentry_benchmark(inputs: _C3ReentryInputs) -> list[float]:
    """Record 33's frozen daily benchmark on the raw union closes, the series record 34's bar read."""
    return build_combined_system(inputs.daily_prices, config=_RECORD33_CONFIG).benchmark_net_of_cost


def _c3_reentry_arm_a_bar(inputs: _C3ReentryInputs, net_a: list[float], bench: list[float], *, n_trials: int) -> dict:
    stressed = _c3_reentry_net(inputs.arm_a, inputs, stress=1.5)
    block, seed = _C3_REENTRY_BLOCKS[0], _C3_REENTRY_SEEDS[0]
    return _c3_reentry_bar(net_a, stressed, bench, inputs, n_trials=n_trials, block=block, seed=seed)


def _c3_reentry_metrics(inputs: _C3ReentryInputs, *, n_trials: int) -> dict:
    close, start = inputs.close, _c3_reentry_first_engaged(inputs)
    if len(close) - start < 2:
        raise ValidationError(
            f"{len(close) - start} of its return indices follow the re-entry's first engagement, and the head-to-head from it "
            "needs 2"
        )
    net_a = _c3_reentry_net(inputs.arm_a, inputs, stress=1.0)
    net_b = _c3_reentry_net(inputs.arm_b, inputs, stress=1.0)
    drawdown_a, drawdown_b = max_drawdown(net_a[start:]), max_drawdown(net_b[start:])
    if drawdown_a == 0:
        raise ValidationError(
            "arm A never draws down from the re-entry's first engagement, so max_drawdown_reduction_pct divides by zero"
        )
    bench = _c3_reentry_benchmark(inputs)
    bar_a = _c3_reentry_arm_a_bar(inputs, net_a, bench, n_trials=n_trials)
    net_b_x15 = _c3_reentry_net(inputs.arm_b, inputs, stress=1.5)
    grid = {
        (block, seed): _c3_reentry_bar(net_b, net_b_x15, bench, inputs, n_trials=n_trials, block=block, seed=seed)
        for block in _C3_REENTRY_BLOCKS
        for seed in _C3_REENTRY_SEEDS
    }
    headline = grid[(_C3_REENTRY_BLOCKS[0], _C3_REENTRY_SEEDS[0])]
    head_to_head = {}
    for label, first in (("full", 0), ("primary", start)):
        verdict = net_of_cost_verdict(
            net_b[first:], net_a[first:], mean_block=_C3_REENTRY_BLOCKS[0], seed=_C3_REENTRY_SEEDS[0], n_resamples=_N_RESAMPLES
        )
        head_to_head[f"head_to_head_mean_outperf_{label}"] = verdict["mean_outperformance"]
        head_to_head[f"head_to_head_spa_p_{label}"] = verdict["spa_p_value"]
    return {
        "ann_sharpe_noc": sharpe(net_b, periods_per_year=PPY_DAILY),
        "ann_sharpe_noc_decisive": sharpe(net_b[_C3_REENTRY_DECISIVE_START:], periods_per_year=PPY_DAILY),
        "per_period_sharpe": sharpe(net_b),
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_DAILY),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_C3_REENTRY_DECISIVE_START:], periods_per_year=PPY_DAILY),
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_DAILY),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_C3_REENTRY_DECISIVE_START:], periods_per_year=PPY_DAILY),
        "dsr_corrected": headline["dsr"],
        "dsr_pass": int(headline["dsr_pass"]),
        "spa_pass": int(headline["spa_pass"]),
        "spa_p_full": headline["spa_p_value_full"],
        "cost_stress_pass": int(headline["cost_stress_pass"]),
        "worst_slice_relative_pass": int(headline["worst_slice_pass"]),
        "passes": int(headline["passes"]),
        "decisive_start": _C3_REENTRY_DECISIVE_START,
        "n_resamples": _N_RESAMPLES,
        "arm_a_passes": int(bar_a["passes"]),
        **{f"spa_p_decisive_b{block}_s{seed}": result["spa_p_value"] for (block, seed), result in grid.items()},
        **head_to_head,
        "max_drawdown": max_drawdown(net_b),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "max_drawdown_per_year": per_year_max_drawdown(net_b, close),
        "arm_a_max_drawdown_per_year": per_year_max_drawdown(net_a, close),
        "turnover_a": book_turnover(inputs.arm_a),
        "turnover_a_per_year": per_year_turnover(inputs.arm_a, close),
        "max_drawdown_primary": drawdown_b,
        "arm_a_max_drawdown_primary": drawdown_a,
        "max_drawdown_reduction_pct": 100 * (drawdown_a - drawdown_b) / drawdown_a,
        **_c3_reentry_engagement(inputs),
    }


def _c3_reentry_preflight_metrics(inputs: _C3ReentryInputs, *, n_trials: int) -> dict:
    """Arm A's anchors and bar and the engagement: no return of arm B."""
    net_a = _c3_reentry_net(inputs.arm_a, inputs, stress=1.0)
    bench = _c3_reentry_benchmark(inputs)
    bar = _c3_reentry_arm_a_bar(inputs, net_a, bench, n_trials=n_trials)
    turnover_a = book_turnover(inputs.arm_a)
    return {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=PPY_DAILY),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[_C3_REENTRY_DECISIVE_START:], periods_per_year=PPY_DAILY),
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / len(inputs.close) * _B2_COST_PER_SIDE * PPY_DAILY,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=PPY_DAILY),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[_C3_REENTRY_DECISIVE_START:], periods_per_year=PPY_DAILY),
        **{key: int(bar[key]) if key in _B2_ARM_A_BAR_FLAGS else bar[key] for key in sorted(_B2_ARM_A_BAR_KEYS)},
        **_c3_reentry_engagement(inputs),
    }


def _c3_reentry_build(
    subject: str,
    compute: Callable[..., dict],
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None,
) -> dict:
    if as_of is not None:
        raise SubjectError(f"{subject} evaluates a frozen snapshot whole, never the rolling dataset as of a day: drop --as-of")
    if window is not None:
        raise SubjectError(
            f"{_b2_over(subject, window)}: it reads its frozen sets whole, and the bands' history reaches back past any "
            "window's first day; drop --window"
        )
    try:
        _, snapshot, daily_ts, daily_prices = _c3_reads(reader, dataset, subject)
        return compute(_c3_reentry_inputs(snapshot, daily_ts, daily_prices), n_trials=_C3_ASOPR_REENTRY_N_TRIALS)
    except EVALUATION_ERRORS as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_c3_asopr_reentry(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _c3_reentry_build("c3-asopr-reentry", _c3_reentry_metrics, reader, dataset, window, as_of)


def _build_c3_asopr_reentry_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _c3_reentry_build("c3-asopr-reentry-preflight", _c3_reentry_preflight_metrics, reader, dataset, window, as_of)


# docs/specs/00165 D13's matrix and the two instrument findings its metrics show: a change to it is a new spec and a new
# trial, never an edit here.
def _c3_asopr_reentry_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not any(m["reentered_per_year"].values()):
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0:
        bounded = m["max_drawdown_reduction_pct"] >= -20.0
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 and bounded else "park"
    return "reject"


# docs/specs/00165 D14's keys.
_C3_REENTRY_ENGAGEMENT_KEYS = frozenset(
    {
        "reentry_first_engaged",
        "primary_returns",
        "stamps_positions_differ",
        "positions_differ_per_year",
        "events_per_year",
        "reentered_per_year",
        "reentry_entries",
        "events_without_size",
        "turnover_b",
        "turnover_b_per_year",
        "gross_max",
    }
)
_C3_REENTRY_METRIC_KEYS = _C3_REENTRY_ENGAGEMENT_KEYS | {
    "ann_sharpe_noc",
    "ann_sharpe_noc_decisive",
    "per_period_sharpe",
    "arm_a_ann_sharpe_noc",
    "arm_a_ann_sharpe_noc_decisive",
    "benchmark_ann_sharpe_noc",
    "benchmark_ann_sharpe_noc_decisive",
    "dsr_corrected",
    "dsr_pass",
    "spa_pass",
    "spa_p_full",
    "cost_stress_pass",
    "worst_slice_relative_pass",
    "passes",
    "decisive_start",
    "n_resamples",
    "arm_a_passes",
    "spa_p_decisive_b17_s42",
    "spa_p_decisive_b17_s7",
    "spa_p_decisive_b17_s1234",
    "spa_p_decisive_b102_s42",
    "spa_p_decisive_b102_s7",
    "spa_p_decisive_b102_s1234",
    "head_to_head_mean_outperf_full",
    "head_to_head_spa_p_full",
    "head_to_head_mean_outperf_primary",
    "head_to_head_spa_p_primary",
    "max_drawdown",
    "arm_a_max_drawdown",
    "max_drawdown_per_year",
    "arm_a_max_drawdown_per_year",
    "turnover_a",
    "turnover_a_per_year",
    "max_drawdown_primary",
    "arm_a_max_drawdown_primary",
    "max_drawdown_reduction_pct",
}
_C3_REENTRY_PREFLIGHT_KEYS = (
    _B2_ARM_A_BAR_KEYS
    | _C3_REENTRY_ENGAGEMENT_KEYS
    | {
        "arm_a_ann_sharpe_noc",
        "arm_a_ann_sharpe_noc_decisive",
        "arm_a_max_drawdown_full",
        "turnover_a",
        "arm_a_spot_drag_pct_yr",
        "benchmark_ann_sharpe_noc",
        "benchmark_ann_sharpe_noc_decisive",
    }
)
```

  `SUBJECTS` gains, after its `"c3-onchain-reading"` entry (`:5875`) and before its closing `}`:

```python
    # No assets, as `c3-onchain-reading`: `--dataset` is the snapshot, and the `ohlc-full` legs are read by name.
    "c3-asopr-reentry": Subject(
        "c3-asopr-reentry",
        (1440,),
        (),
        _build_c3_asopr_reentry,
        spec="docs/specs/00165-c3-trial-1-asopr-reentry-design.md",
        metric_keys=_C3_REENTRY_METRIC_KEYS,
        seeds=(42, 7, 1234),
        verdict=_c3_asopr_reentry_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the re-entry holds no asset at any close; no "
            "verdict, the trial unspent"
        ),
        family="C3",
        n_trials=_C3_ASOPR_REENTRY_N_TRIALS,
    ),
    "c3-asopr-reentry-preflight": Subject(
        "c3-asopr-reentry-preflight",
        (1440,),
        (),
        _build_c3_asopr_reentry_preflight,
        spec="docs/specs/00165-c3-trial-1-asopr-reentry-design.md",
        metric_keys=_C3_REENTRY_PREFLIGHT_KEYS,
        seeds=(42,),
    ),
```

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row (`:444`): `` ), or `c3-onchain-reading` ( `` becomes `` ), `c3-onchain-reading` ( ``, and the row's closing `` no `--window` and no `--as-of`; it has no rule, so its run is kept with `--reading`). | `` becomes, its leading space kept:

```text
 no `--window` and no `--as-of`; it has no rule, so its run is kept with `--reading`), `c3-asopr-reentry` (the cross-frequency system's weekly trend sleeve on daily closes against the same sleeve with a re-entry: each asset the sleeve holds flat at a daily close, after a day whose adjusted SOPR lies in the lowest tenth of its own history to that day, is bought at the size the sleeve's own weights and volatility target give a book long in every asset, and held 7 daily closes from the last such close unless the sleeve itself turns long; both books charged 0.006 a side on their own turnover; a frozen btc-onchain snapshot, whole — `--dataset btc-onchain-<stamp>` — and the `ohlc-full` set's ten daily series, read by name and whole, no `--window` and no `--as-of`) or `c3-asopr-reentry-preflight` (that comparison's instrument check: the sleeve's own figures and kill bar and the re-entry's events and positions, no return of the book that re-enters; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: Run them to verify they pass** — step 2's command, measured `44 passed in 3.64s`; then every row of `tests/test_research_command.py` that carries the subjects' names — the tracked-spec, contract, shared-defaults and deflation rows, and the two command rows again — `mkdir -p .tmp/plan-00165 && uv run pytest tests/test_research_command.py -k "c3-asopr-reentry" -m "not data" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00165/pt`, one plain blocking call, `timeout` 600000 ms (measured `15 passed, 1056 deselected in 18.44s`, the slowest `test_every_subjects_metrics_hold_when_the_shared_defaults_move[c3-asopr-reentry]` at 6.62 s). No case times at 10 s, so `tests/slow-cases.txt` is not touched here; a case that times at 10 s or more on the implementer's own run joins the list at its `sorted()` place (`tests/test_slow_cases.py` passes).
- [ ] **Step 6: Stage, consumers, gate** — `git add cli/registry/budget.py cli/research/subjects.py tests/test_trial_registry_provenance.py tests/test_research_command.py tests/test_research_c3_asopr_reentry.py README.md`; the Global Constraints' list over the six paths in its four parts (measured on the authoring tree in the scratch worktrees: `628 passed, 443 deselected in 317.06s`, `227 passed, 844 deselected in 326.76s`, `86 passed, 985 deselected in 112.64s`; the other 57 direct readers, `5084 passed, 94 deselected, 44 warnings in 177.52s`, the warnings `tests/test_infra_converge_guards.py`'s own); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 7: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured in the scratch worktrees on the authoring tree, 111 of 111); the ruled-subjects literal and the tracked-spec, contract, shared-defaults and deflation rows are new rows of existing tests, not new guards, and are not probed:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation 's/^_C3_ASOPR_REENTRY_N_TRIALS = 1 /_C3_ASOPR_REENTRY_N_TRIALS = 2 /' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation 's/^_C3_REENTRY_HOLD = 7$/_C3_REENTRY_HOLD = 6/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation 's/^_C3_REENTRY_DECISIVE_START = 230$/_C3_REENTRY_DECISIVE_START = 231/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation 's/^_C3_REENTRY_BLOCKS = (17, 102)$/_C3_REENTRY_BLOCKS = (30, 102)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation 's/^_C3_REENTRY_SEEDS = (42, 7, 1234)$/_C3_REENTRY_SEEDS = (7, 42, 1234)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation '/"c3-asopr-reentry": Subject(/,/^    ),/s/00165-c3-trial-1-asopr-reentry-design.md/00164-t0228-btc-onchain-design.md/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation '/"c3-asopr-reentry-preflight": Subject(/,/^    ),/s/00165-c3-trial-1-asopr-reentry-design.md/00164-t0228-btc-onchain-design.md/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation '/"c3-asopr-reentry": Subject(/,/^    ),/s/seeds=(42, 7, 1234),/seeds=(42,),/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation '/"c3-asopr-reentry": Subject(/,/^    ),/s/verdict=_c3_asopr_reentry_verdict,/verdict=_b2_reentry_verdict,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation '/"c3-asopr-reentry": Subject(/,/^    ),/s/family="C3",/family="B3",/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation '/"c3-asopr-reentry": Subject(/,/^    ),/s/metric_keys=_C3_REENTRY_METRIC_KEYS,/metric_keys=_C3_REENTRY_PREFLIGHT_KEYS,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation '/"c3-asopr-reentry-preflight": Subject(/,/^    ),/s/metric_keys=_C3_REENTRY_PREFLIGHT_KEYS,/metric_keys=_C3_REENTRY_METRIC_KEYS,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation '/"c3-asopr-reentry": Subject(/,/^    ),/s/^        _build_c3_asopr_reentry,/        _build_c3_asopr_reentry_preflight,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation '/"c3-asopr-reentry": Subject(/,/^    ),/s/the re-entry holds no asset at any close; no "/the re-entry holds no asset at any stamp; no "/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation 's/^        "gross_max",$/        "gross_maximum",/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation '/^_C3_REENTRY_PREFLIGHT_KEYS/,/^)/s/^        "arm_a_spot_drag_pct_yr",$/        "arm_a_spot_drag",/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_pair_declares_its_spec_keys_rule_and_count[c3-asopr-reentry-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_asopr_reentry_verdict(/def _c3_asopr_reentry_verdict_gone(/' --mutation '/^def _c3_asopr_reentry_verdict(/,/^_C3_REENTRY_ENGAGEMENT_KEYS/s/ or not any(m\["reentered_per_year"\].values()):/:/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_rule_maps_its_metrics_to_a_verdict_or_a_stop[stop-on-the-dead-knob-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_asopr_reentry_verdict(/def _c3_asopr_reentry_verdict_gone(/' --mutation '/^def _c3_asopr_reentry_verdict(/,/^_C3_REENTRY_ENGAGEMENT_KEYS/s/    if not m\["arm_a_passes"\] or not any/    if not any/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_rule_maps_its_metrics_to_a_verdict_or_a_stop[stop-when-arm-a-fails-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_asopr_reentry_verdict(/def _c3_asopr_reentry_verdict_gone(/' --mutation '/^def _c3_asopr_reentry_verdict(/,/^_C3_REENTRY_ENGAGEMENT_KEYS/s/    if not m\["passes"\]:/    if False:/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_rule_maps_its_metrics_to_a_verdict_or_a_stop[reject-on-a-failed-bar-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_asopr_reentry_verdict(/def _c3_asopr_reentry_verdict_gone(/' --mutation '/^def _c3_asopr_reentry_verdict(/,/^_C3_REENTRY_ENGAGEMENT_KEYS/s/m\["head_to_head_mean_outperf_primary"\] > 0:/m["head_to_head_mean_outperf_primary"] >= 0:/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_rule_maps_its_metrics_to_a_verdict_or_a_stop[reject-at-no-outperformance-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_asopr_reentry_verdict(/def _c3_asopr_reentry_verdict_gone(/' --mutation '/^def _c3_asopr_reentry_verdict(/,/^_C3_REENTRY_ENGAGEMENT_KEYS/s/>= -20.0$/> -20.0/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_rule_maps_its_metrics_to_a_verdict_or_a_stop[adopt-at-the-bound-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_asopr_reentry_verdict(/def _c3_asopr_reentry_verdict_gone(/' --mutation '/^def _c3_asopr_reentry_verdict(/,/^_C3_REENTRY_ENGAGEMENT_KEYS/s/>= -20.0$/>= -25.0/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_rule_maps_its_metrics_to_a_verdict_or_a_stop[park-past-the-drawdown-bound-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_asopr_reentry_verdict(/def _c3_asopr_reentry_verdict_gone(/' --mutation '/^def _c3_asopr_reentry_verdict(/,/^_C3_REENTRY_ENGAGEMENT_KEYS/s/m\["head_to_head_spa_p_primary"\] < 0.05 and/m["head_to_head_spa_p_primary"] <= 0.05 and/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_rule_maps_its_metrics_to_a_verdict_or_a_stop[park-at-p-0.05-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_asopr_reentry_verdict(/def _c3_asopr_reentry_verdict_gone(/' --mutation '/^def _c3_asopr_reentry_verdict(/,/^_C3_REENTRY_ENGAGEMENT_KEYS/s/< 0.05 and bounded else/< 0.05 or bounded else/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_rule_maps_its_metrics_to_a_verdict_or_a_stop[park-at-p-0.05-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_asopr_reentry_verdict(/def _c3_asopr_reentry_verdict_gone(/' --mutation '/^def _c3_asopr_reentry_verdict(/,/^_C3_REENTRY_ENGAGEMENT_KEYS/s/return "adopt" if/return "park" if/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_rule_maps_its_metrics_to_a_verdict_or_a_stop[adopt-at-the-bound-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _c3_reentry_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_a_c3_reentry_subject_refuses_as_of_and_a_window_before_any_read[as-of-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _c3_reentry_build(/,/^def /s/    if window is not None:/    if False:/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_a_c3_reentry_subject_refuses_as_of_and_a_window_before_any_read[window-c3-asopr-reentry-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _c3_reentry_build(/,/^def /s/never the rolling dataset as of a day: drop --as-of/never the rolling dataset as of a day/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_a_c3_reentry_subject_refuses_as_of_and_a_window_before_any_read[as-of-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _c3_reentry_build(/,/^def /s/window.s first day; drop --window/window.s first day/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_a_c3_reentry_subject_refuses_as_of_and_a_window_before_any_read[window-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _c3_reentry_build(/,/^def /s/_c3_reads(reader, dataset, subject)/_c3_reads(reader, dataset, "c3-onchain-reading")/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_a_c3_reentry_build_reads_the_readings_sets_and_computes_its_own_half_at_the_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _c3_reentry_build(/,/^def /s/n_trials=_C3_ASOPR_REENTRY_N_TRIALS)/n_trials=1)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_a_c3_reentry_build_reads_the_readings_sets_and_computes_its_own_half_at_the_count[c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _c3_reentry_build(/,/^def /s/n_trials=_C3_ASOPR_REENTRY_N_TRIALS)/n_trials=1)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_a_c3_reentry_build_reads_the_readings_sets_and_computes_its_own_half_at_the_count[c3-asopr-reentry-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _c3_reentry_build(/,/^def /s/_c3_reentry_inputs(snapshot, daily_ts, daily_prices)/_c3_reentry_inputs(snapshot, daily_prices, daily_ts)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_a_c3_reentry_build_reads_the_readings_sets_and_computes_its_own_half_at_the_count[c3-asopr-reentry-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _build_c3_asopr_reentry(/,/^def /s/_c3_reentry_build("c3-asopr-reentry", _c3_reentry_metrics,/_c3_reentry_build("c3-asopr-reentry-preflight", _c3_reentry_metrics,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_each_c3_reentry_builder_names_its_own_subject_and_compute[c3-asopr-reentry-_c3_reentry_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _build_c3_asopr_reentry(/,/^def /s/reader, dataset, window, as_of)$/reader, dataset, window, None)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_each_c3_reentry_builder_names_its_own_subject_and_compute[c3-asopr-reentry-_c3_reentry_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _build_c3_asopr_reentry_preflight(/,/^# docs/s/_c3_reentry_build("c3-asopr-reentry-preflight", _c3_reentry_preflight_metrics,/_c3_reentry_build("c3-asopr-reentry-preflight", _c3_reentry_metrics,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_each_c3_reentry_builder_names_its_own_subject_and_compute[c3-asopr-reentry-preflight-_c3_reentry_preflight_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _c3_reentry_build(/,/^def /s/    except EVALUATION_ERRORS as exc:/    except (AlphaError, ValidationError) as exc:/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_a_c3_reentry_compute_error_is_refused_over_the_full_history[BenchmarkError-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_build(/def _c3_reentry_build_gone(/' --mutation '/^def _c3_reentry_build(/,/^def /s/raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc/raise SubjectError(f"{subject}: {exc}") from exc/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_a_c3_reentry_compute_error_is_refused_over_the_full_history[ValidationError-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_inputs(/def _c3_reentry_inputs_gone(/' --mutation 's/^    fires: dict\[str, list\[bool\]\]$/    fired: dict[str, list[bool]]/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_inputs_hold_the_sleeve_the_cells_events_the_size_and_arm_b_and_no_net_series' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_inputs(/def _c3_reentry_inputs_gone(/' --mutation '/^def _c3_reentry_inputs(/,/^def /s/reading.bands\["asopr"\]/reading.bands["mvrv"]/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_inputs_hold_the_sleeve_the_cells_events_the_size_and_arm_b_and_no_net_series' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_inputs(/def _c3_reentry_inputs_gone(/' --mutation '/^def _c3_reentry_inputs(/,/^def /s/hold=_C3_REENTRY_HOLD)/hold=_C3_REENTRY_HOLD + 1)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_inputs_hold_the_sleeve_the_cells_events_the_size_and_arm_b_and_no_net_series' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_inputs(/def _c3_reentry_inputs_gone(/' --mutation '/^def _c3_reentry_inputs(/,/^def /s/reentry_positions(arm_a, size, fires,/reentry_positions(arm_a, arm_a, fires,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_inputs_hold_the_sleeve_the_cells_events_the_size_and_arm_b_and_no_net_series' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_inputs(/def _c3_reentry_inputs_gone(/' --mutation '/^def _c3_reentry_inputs(/,/^def /s/sized in full_long_positions(daily_prices).items()/sized in reading.positions.items()/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_inputs_hold_the_sleeve_the_cells_events_the_size_and_arm_b_and_no_net_series' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_inputs(/def _c3_reentry_inputs_gone(/' --mutation '/^def _c3_reentry_inputs(/,/^def /s/    fed = _ffill_btc(daily_prices)/    fed = daily_prices/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_inputs_hold_the_sleeve_the_cells_events_the_size_and_arm_b_and_no_net_series' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_inputs(/def _c3_reentry_inputs_gone(/' --mutation '/^def _c3_reentry_inputs(/,/^def /s/daily_ts, daily_prices, daily_ts\[1:\], returns/daily_ts, daily_prices, daily_ts[:-1], returns/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_inputs_hold_the_sleeve_the_cells_events_the_size_and_arm_b_and_no_net_series' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_inputs(/def _c3_reentry_inputs_gone(/' --mutation '/^def _c3_reentry_inputs(/,/^def /s/    n = len(daily_ts) - 1/    n = len(daily_ts) - 2/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_inputs_hold_the_sleeve_the_cells_events_the_size_and_arm_b_and_no_net_series' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_inputs(/def _c3_reentry_inputs_gone(/' --mutation '/^def _c3_reentry_inputs(/,/^def /s/returns, arm_a, arm_b, fires, size)/returns, arm_b, arm_b, fires, size)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_inputs_hold_the_sleeve_the_cells_events_the_size_and_arm_b_and_no_net_series' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_engagement(/def _c3_reentry_engagement_gone(/' --mutation '/^def _c3_reentry_first_engaged(/,/^def /s/for a in inputs.arm_a)), n)/for a in inputs.arm_a)), n) + 1/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_engagement(/def _c3_reentry_engagement_gone(/' --mutation '/^def _c3_reentry_engagement(/,/^def /s/"primary_returns": n - start,/"primary_returns": n - start - 1,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_engagement(/def _c3_reentry_engagement_gone(/' --mutation '/^def _c3_reentry_engagement(/,/^def /s/"stamps_positions_differ": sum(differ.values()),/"stamps_positions_differ": len(differ),/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_engagement(/def _c3_reentry_engagement_gone(/' --mutation '/^def _c3_reentry_engagement(/,/^def /s/{year: sum(counts\[year\] for counts in fired) for year in fired\[0\]}/{year: fired[0][year] for year in fired[0]}/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_engagement(/def _c3_reentry_engagement_gone(/' --mutation '/^def _c3_reentry_engagement(/,/^def /s/"reentered_per_year": reentry_counts_per_year(arm_a, arm_b, close),/"reentered_per_year": differ,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_engagement(/def _c3_reentry_engagement_gone(/' --mutation '/^def _c3_reentry_engagement(/,/^def /s/sum(held\[k\] and not (k and held\[k - 1\]) for held/sum(held[k] for held/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_engagement(/def _c3_reentry_engagement_gone(/' --mutation '/^def _c3_reentry_engagement(/,/^def /s/fires\[asset\]\[k\] and size\[asset\]\[k\] == 0 for asset/fires[asset][k] and size[asset][k] > 0 for asset/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_engagement(/def _c3_reentry_engagement_gone(/' --mutation '/^def _c3_reentry_engagement(/,/^def /s/"turnover_b": book_turnover(arm_b),/"turnover_b": book_turnover(arm_a),/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_engagement(/def _c3_reentry_engagement_gone(/' --mutation '/^def _c3_reentry_engagement(/,/^def /s/"turnover_b_per_year": per_year_turnover(arm_b, close),/"turnover_b_per_year": per_year_turnover(arm_a, close),/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_engagement(/def _c3_reentry_engagement_gone(/' --mutation '/^def _c3_reentry_engagement(/,/^def /s/"gross_max": max(math.fsum(/"gross_max": min(math.fsum(/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_engagement(/def _c3_reentry_engagement_gone(/' --mutation '/^def _c3_reentry_engagement(/,/^def /s/arm_a\[asset\]\[k\] == 0 and arm_b\[asset\]\[k\] > 0 for k in range(n)\]/arm_b[asset][k] > 0 for k in range(n)]/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_engagement_counts_the_events_the_re_entered_closes_and_arm_bs_turnover' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_net(/,/^def /s/cost_per_side=stress \* _B2_COST_PER_SIDE)/cost_per_side=_B2_COST_PER_SIDE)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_net(/,/^def /s/net_of_cost(positions, inputs.returns,/net_of_cost(inputs.arm_a, inputs.returns,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_bar(/,/^def /s/        var_trials=0.0,/        var_trials=0.1,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_bar(/,/^def /s/        mean_block=block,/        mean_block=17,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_bar(/,/^def /s/        seed=seed,/        seed=42,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_bar(/,/^def /s/        cost_stressed_returns=stressed,/        cost_stressed_returns=net,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_bar(/,/^def /s/regime_slices=calendar_year_slices(net, inputs.daily_ts),/regime_slices=calendar_year_slices(bench, inputs.daily_ts),/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_bar(/,/^def /s/benchmark_slices=calendar_year_slices(bench, inputs.daily_ts),/benchmark_slices=calendar_year_slices(net, inputs.daily_ts),/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_bar(/,/^def /s/decisive_start=_C3_REENTRY_DECISIVE_START,/decisive_start=0,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_bar(/,/^def /s/n_resamples=_N_RESAMPLES,/n_resamples=1000,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_bar(/,/^def /s/^        bench,$/        net,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_benchmark(/,/^def /s/config=_RECORD33_CONFIG)/config=CombinedSystemConfig(spot_fee_per_side=0.006))/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_benchmark(/,/^def /s/build_combined_system(inputs.daily_prices,/build_combined_system(_ffill_btc(inputs.daily_prices),/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_arm_a_bar(/,/^def /s/_c3_reentry_net(inputs.arm_a, inputs, stress=1.5)/_c3_reentry_net(inputs.arm_b, inputs, stress=1.5)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_arm_a_bar(/,/^def /s/_C3_REENTRY_BLOCKS\[0\], _C3_REENTRY_SEEDS\[0\]/_C3_REENTRY_BLOCKS[1], _C3_REENTRY_SEEDS[0]/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/    net_a = _c3_reentry_net(inputs.arm_a, inputs, stress=1.0)/    net_a = _c3_reentry_net(inputs.arm_b, inputs, stress=1.0)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/    net_b = _c3_reentry_net(inputs.arm_b, inputs, stress=1.0)/    net_b = _c3_reentry_net(inputs.arm_a, inputs, stress=1.0)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/    net_b_x15 = _c3_reentry_net(inputs.arm_b, inputs, stress=1.5)/    net_b_x15 = _c3_reentry_net(inputs.arm_b, inputs, stress=2.0)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/    headline = grid\[(_C3_REENTRY_BLOCKS\[0\], _C3_REENTRY_SEEDS\[0\])\]/    headline = grid[(_C3_REENTRY_BLOCKS[1], _C3_REENTRY_SEEDS[0])]/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/(("full", 0), ("primary", start))/(("full", 0), ("primary", 0))/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/net_b\[first:\], net_a\[first:\], mean_block/net_a[first:], net_b[first:], mean_block/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/mean_block=_C3_REENTRY_BLOCKS\[0\], seed=_C3_REENTRY_SEEDS\[0\], n_resamples=_N_RESAMPLES/mean_block=_C3_REENTRY_BLOCKS[1], seed=_C3_REENTRY_SEEDS[0], n_resamples=_N_RESAMPLES/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/\] = verdict\["mean_outperformance"\]/] = verdict["spa_p_value"]/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/"ann_sharpe_noc": sharpe(net_b, periods_per_year=PPY_DAILY),/"ann_sharpe_noc": sharpe(net_b, periods_per_year=PPY_4H),/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/"ann_sharpe_noc_decisive": sharpe(net_b\[_C3_REENTRY_DECISIVE_START:\],/"ann_sharpe_noc_decisive": sharpe(net_b,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/"dsr_corrected": headline\["dsr"\],/"dsr_corrected": bar_a["dsr"],/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/"spa_p_full": headline\["spa_p_value_full"\],/"spa_p_full": headline["spa_p_value"],/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/"passes": int(headline\["passes"\]),/"passes": int(bar_a["passes"]),/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/"arm_a_passes": int(bar_a\["passes"\]),/"arm_a_passes": int(headline["passes"]),/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/result\["spa_p_value"\] for (block, seed), result in grid.items()/result["spa_p_value_full"] for (block, seed), result in grid.items()/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/"max_drawdown_per_year": per_year_max_drawdown(net_b, close),/"max_drawdown_per_year": per_year_max_drawdown(net_a, close),/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/100 \* (drawdown_a - drawdown_b) \/ drawdown_a,/100 * (drawdown_b - drawdown_a) \/ drawdown_a,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/        \*\*_c3_reentry_engagement(inputs),/        **{},/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_costs_both_arms_and_reads_record_34s_bar_at_the_count_and_the_head_to_heads_from_the_first_engagement' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/max_drawdown(net_a\[start:\]), max_drawdown(net_b\[start:\])/max_drawdown(net_a), max_drawdown(net_b[start:])/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_reads_its_drawdown_pair_from_the_first_engagement_and_not_over_the_window' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/max_drawdown(net_a\[start:\]), max_drawdown(net_b\[start:\])/max_drawdown(net_a[start:]), max_drawdown(net_b)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_reads_its_drawdown_pair_from_the_first_engagement_and_not_over_the_window' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_bar(/,/^def /s/        n_trials=n_trials,/        n_trials=1,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_deflates_every_bar_at_the_count_it_is_handed' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/_c3_reentry_arm_a_bar(inputs, net_a, bench, n_trials=n_trials)/_c3_reentry_arm_a_bar(inputs, net_a, bench, n_trials=_C3_ASOPR_REENTRY_N_TRIALS)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_deflates_every_bar_at_the_count_it_is_handed' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/bench, inputs, n_trials=n_trials, block=block, seed=seed)/bench, inputs, n_trials=_C3_ASOPR_REENTRY_N_TRIALS, block=block, seed=seed)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_deflates_every_bar_at_the_count_it_is_handed' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/    if len(close) - start < 2:/    if False:/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_refuses_a_head_to_head_shorter_than_2_before_any_bar[none]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/    if len(close) - start < 2:/    if len(close) - start < 1:/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_refuses_a_head_to_head_shorter_than_2_before_any_bar[one]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/and the head-to-head from it "/and the head-to-head "/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_refuses_a_head_to_head_shorter_than_2_before_any_bar[one]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/    if drawdown_a == 0:/    if drawdown_b == 0:/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_refuses_an_arm_a_that_never_draws_down_before_any_bar' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_metrics(/def _c3_reentry_metrics_gone(/' --mutation '/^def _c3_reentry_metrics(/,/^def /s/so max_drawdown_reduction_pct divides by zero/so the reduction divides by zero/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_trial_refuses_an_arm_a_that_never_draws_down_before_any_bar' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_preflight_metrics(/def _c3_reentry_preflight_metrics_gone(/' --mutation '/^def _c3_reentry_preflight_metrics(/,/^def /s/    net_a = _c3_reentry_net(inputs.arm_a, inputs, stress=1.0)/    net_a = _c3_reentry_net(inputs.arm_b, inputs, stress=1.0)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_preflight_reads_arm_as_anchors_and_bar_and_the_engagement_and_costs_no_arm_b' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_preflight_metrics(/def _c3_reentry_preflight_metrics_gone(/' --mutation '/^def _c3_reentry_preflight_metrics(/,/^def /s/"arm_a_ann_sharpe_noc_decisive": sharpe(net_a\[_C3_REENTRY_DECISIVE_START:\],/"arm_a_ann_sharpe_noc_decisive": sharpe(net_a,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_preflight_reads_arm_as_anchors_and_bar_and_the_engagement_and_costs_no_arm_b' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_preflight_metrics(/def _c3_reentry_preflight_metrics_gone(/' --mutation '/^def _c3_reentry_preflight_metrics(/,/^def /s/"arm_a_max_drawdown_full": max_drawdown(net_a),/"arm_a_max_drawdown_full": max_drawdown(bench),/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_preflight_reads_arm_as_anchors_and_bar_and_the_engagement_and_costs_no_arm_b' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_preflight_metrics(/def _c3_reentry_preflight_metrics_gone(/' --mutation '/^def _c3_reentry_preflight_metrics(/,/^def /s/    turnover_a = book_turnover(inputs.arm_a)/    turnover_a = book_turnover(inputs.arm_b)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_preflight_reads_arm_as_anchors_and_bar_and_the_engagement_and_costs_no_arm_b' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_preflight_metrics(/def _c3_reentry_preflight_metrics_gone(/' --mutation '/^def _c3_reentry_preflight_metrics(/,/^def /s/len(inputs.close) \* _B2_COST_PER_SIDE \* PPY_DAILY,/len(inputs.close) * _B2_COST_PER_SIDE * PPY_4H,/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_preflight_reads_arm_as_anchors_and_bar_and_the_engagement_and_costs_no_arm_b' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_preflight_metrics(/def _c3_reentry_preflight_metrics_gone(/' --mutation '/^def _c3_reentry_preflight_metrics(/,/^def /s/if key in _B2_ARM_A_BAR_FLAGS else bar\[key\] for key/if key in _B2_ARM_A_BAR_FLAGS else 0.5 for key/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_preflight_reads_arm_as_anchors_and_bar_and_the_engagement_and_costs_no_arm_b' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_preflight_metrics(/def _c3_reentry_preflight_metrics_gone(/' --mutation '/^def _c3_reentry_preflight_metrics(/,/^def /s/        \*\*_c3_reentry_engagement(inputs),/        **{},/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_preflight_reads_arm_as_anchors_and_bar_and_the_engagement_and_costs_no_arm_b' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _c3_reentry_preflight_metrics(/def _c3_reentry_preflight_metrics_gone(/' --mutation '/^def _c3_reentry_preflight_metrics(/,/^def /s/_c3_reentry_arm_a_bar(inputs, net_a, bench, n_trials=n_trials)/_c3_reentry_arm_a_bar(inputs._replace(arm_a=inputs.arm_b), net_a, bench, n_trials=n_trials)/' -- uv run pytest 'tests/test_research_c3_asopr_reentry.py::test_the_c3_reentry_preflight_reads_arm_as_anchors_and_bar_and_the_engagement_and_costs_no_arm_b' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation '/"c3-asopr-reentry": Subject(/,/^    ),/s/        verdict=_c3_asopr_reentry_verdict,/        verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_the_c3_reentry_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation 's/^_C3_ASOPR_REENTRY_N_TRIALS = 1 /_C3_ASOPR_REENTRY_N_TRIALS = 2 /' -- uv run pytest 'tests/test_research_command.py::test_the_c3_reentry_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-c3-asopr-reentry]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  Each row moves one clause D2, D3, D6, D8, D9, D12, D13 or D14 gives the new code. The declaration: the count, the hold, the decisive start, the blocks, the seeds, each subject's spec, the trial's seeds, rule, family and keys, the twin's keys, the trial's builder, the `no_verdict` text, an engagement key and a pre-flight key (rows 1–16). The rule: the dead knob, arm A's bar, arm B's bar, the mean's bound, the drawdown bound at and past −20, the p's bound, `and` read as `or`, and the adopt return (rows 17–25). The refusals before any read: `--as-of` on the trial, `--window` on the twin, and each message's remedy (rows 26–29). The build: the subject name the reads are given, the count each compute is called at on each subject, the inputs half's arguments in order, the trial builder's own name and the `--as-of` it forwards, the twin builder's own compute, the error classes turned into a refusal and the refusal's words (rows 30–38). The inputs: the field list, the feature's band, the hold, the size handed to `reentry_positions`, the size itself, BTC's fill under the returns, the closes, the forming row's cut and arm A's field (rows 39–47). The engagement: the first engagement, the primary count, the differing closes, the events summed over the assets, the re-entered closes, the entries, the unsized events, arm B's turnover and its per-year split, the largest gross and the re-entered test's flat leg (rows 48–58). The trial's metrics: the stress on the cost and the book costed; the bar's `var_trials`, block, seed, stressed series, both slice sets, decisive start, resamples and benchmark; the benchmark's config and its raw closes; arm A's stressed book and its block; each arm's net and arm B's stressed rate; the headline's cell; the primary read's start, the arms' order and the head-to-head's block; and eleven keys, each read off another call, another series or another window (rows 59–91). The drawdown pair from the first engagement, each arm's (rows 92–93). The count at the bar, at arm A's bar and at the grid (rows 94–96). The refusals before any bar: the short read's test at both of its cases and its words, arm A's flat drawdown and its words (rows 97–101). The pre-flight: the book it costs, a decisive slice, the drawdown's series, the turnover's book, the drag's annualisation, the bar's keys, the engagement and the bar's own book (rows 102–109). The plain eval and the count at the command (rows 110–111). **Author's call — the clauses no row moves.** The two refusals' place before the bars: a substitution cannot move a line, and each refusal's case asserts that no bar and no head-to-head ran. `_c3_reentry_build`'s `SubjectError` passing `_c3_reads`' own refusals through: reading 10's cases hold those refusals (`tests/test_research_c3_onchain_reading.py`), which this build calls unchanged.
- [ ] **Step 8: Commit** — `feat(research): C3 trial 1's subjects — the A1 sleeve against the same sleeve with a re-entry in each asset it holds flat under aSOPR's low band, and its pre-flight twin; the family key C3 in bucket C`, the message quoting the owner's pick as the spec's head carries it, since the key's literal asks for the ruling, and carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 3: the data-gated basis test and the reads (D15)

**Files:** Create `tests/test_research_c3_asopr_reentry_basis.py` (module-marked `data`); modify `tests/slow-cases.txt`.

**Interfaces:** Consumes Task 2's `_c3_reentry_inputs` and `_c3_reentry_engagement` and reading 10's `_c3_reads`; `cli.alpha.b1.book_turnover`; `cli.registry.observed.ObservedReader`, `cli.registry.record.compute_hash` and `cli.research.command._DATA_ROOT`; `tests.skip_gates.nothing_found_under`; `tests.test_trial_registry_provenance._readings` (`:209`). Produces one test, its own `trial_inputs()`, and the module names `BLOCK`, `VOUCHED`, `DATASET` and `ENGAGEMENT`, which Task 4's check programs import. No test computes a return of a book.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis, reading 10's figures read off the committed ledger:

```python
import math
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _readings

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
SUBJECT = "c3-asopr-reentry"
DATASET = "btc-onchain-20261124T162656Z"

# docs/specs/00165-c3-trial-1-asopr-reentry-design.md's measured basis, read from positions, events and sizes alone.
BLOCK = "19ee5c231d34aa4d6f7851ad243765bf9c39058de99a5199f3f9efd7c1674f7a"
VOUCHED = {DATASET: "checked (1 vouched hashes)", "ohlc-full": "checked (36 vouched hashes)"}
AS_OF_LINE = {"relpath": "index/2026/11/23.json", "sha256": "2d9b2f4529042094111751c8b1f22ec5cd04577be507e2a8911a2e1a228bb5e2"}
RETURN_INDICES = 4581
TURNOVER_A = 46.72757036801258
ENGAGEMENT = {
    "reentry_first_engaged": 97,
    "primary_returns": 4484,
    "stamps_positions_differ": 977,
    "positions_differ_per_year": {
        "2013": 10,
        "2014": 189,
        "2015": 114,
        "2016": 0,
        "2017": 7,
        "2018": 183,
        "2019": 112,
        "2020": 40,
        "2021": 52,
        "2022": 170,
        "2023": 35,
        "2024": 7,
        "2025": 14,
        "2026": 44,
    },
    "events_per_year": {
        "2013": 4,
        "2014": 125,
        "2015": 76,
        "2016": 0,
        "2017": 1,
        "2018": 294,
        "2019": 146,
        "2020": 76,
        "2021": 59,
        "2022": 580,
        "2023": 30,
        "2024": 8,
        "2025": 20,
        "2026": 130,
    },
    "reentered_per_year": {
        "2013": 20,
        "2014": 374,
        "2015": 228,
        "2016": 0,
        "2017": 7,
        "2018": 726,
        "2019": 516,
        "2020": 243,
        "2021": 283,
        "2022": 1700,
        "2023": 166,
        "2024": 56,
        "2025": 140,
        "2026": 440,
    },
    "reentry_entries": 367,
    "events_without_size": 29,
    "turnover_b": 69.84081467289158,
    "gross_max": 0.7648558752122554,
}
REENTERED_PER_ASSET = {
    "ADA": 483,
    "AVAX": 254,
    "BTC": 913,
    "DOGE": 326,
    "DOT": 289,
    "ETH": 559,
    "LINK": 333,
    "LTC": 902,
    "SOL": 246,
    "XRP": 594,
}


def trial_inputs():
    reader = ObservedReader(_DATA_ROOT)
    provenance, snapshot, daily_ts, daily_prices = subjects._c3_reads(reader, DATASET, SUBJECT)
    return reader, provenance, subjects._c3_reentry_inputs(snapshot, daily_ts, daily_prices)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "btc-onchain-*/BTC/onchain.parquet"),
    reason="the frozen btc-onchain snapshot is absent under data/",
)
def test_the_c3_reentry_inputs_reproduce_the_measured_basis_on_reading_10s_block_and_events():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, provenance, inputs = trial_inputs()
    reading = _readings()[10]
    assert reading["invocation"]["subject"] == "c3-onchain-reading"
    block = reader.block()
    assert compute_hash(block) == BLOCK == reading["dataset_hash"] and block == reading["datasets"]
    assert reader.vouched_status() == VOUCHED and reader.holes() == {}
    assert provenance["as_of_line"] == AS_OF_LINE
    arm_a, arm_b, n = inputs.arm_a, inputs.arm_b, len(inputs.close)
    assert n == RETURN_INDICES
    # Never the computes half here: docs/specs/00165 D15's hash rule.
    assert {a: sum(fired) for a, fired in inputs.fires.items()} == {
        a: counts["events"] for a, counts in reading["metrics"]["counts"]["asopr|low|flat"].items()
    }
    engagement = subjects._c3_reentry_engagement(inputs)
    by_year = engagement.pop("turnover_b_per_year")
    assert engagement == ENGAGEMENT
    assert set(by_year) == set(ENGAGEMENT["events_per_year"]) and math.fsum(by_year.values()) == pytest.approx(
        ENGAGEMENT["turnover_b"]
    )
    assert sum(ENGAGEMENT["events_per_year"].values()) == 1549
    assert book_turnover(arm_a) == TURNOVER_A
    first = ENGAGEMENT["reentry_first_engaged"]
    assert all(arm_b[a][:first] == arm_a[a][:first] for a in arm_a)
    assert all(p >= 0 for held in arm_b.values() for p in held)
    reentered = {a: [arm_a[a][k] == 0 and arm_b[a][k] > 0 for k in range(n)] for a in arm_a}
    assert {a: sum(held) for a, held in reentered.items()} == REENTERED_PER_ASSET
    assert sum(held[k] for held in reentered.values() for k in range(199)) == 52
    assert sum(held[k] for held in reentered.values() for k in range(230)) == 114
    assert sum(any(arm_a[a][k] > 0.20 for a in arm_a) for k in range(n)) == 224
    assert sum(any(arm_b[a][k] > 0.20 for a in arm_b) for k in range(n)) == 238
```

  **Author's call** — the case holds the subject's inputs half to the spec's books program, which built the events by `cli/alpha/c3.py`'s `flags`, the size written out and the hold by `reentry_positions` — two derivations that must agree; the block to reading 10's `dataset_hash` and `datasets`, read off the ledger, never a second typing; the events per asset to reading 10's stored counts for `asopr|low|flat`; ten of the engagement's eleven keys exactly, `turnover_b` to the last digit among them, and `turnover_b_per_year`, which the basis did not print, by its years and its sum; arm A's turnover; the books one to the bit before the first engagement; no position below 0; the re-entered closes per asset and before the gate's first warm close and the bar's decisive start; and the closes at which each arm holds an asset above 0.20.
- [ ] **Step 2: Run it** — with both sets linked in this worktree: `mkdir -p .tmp/plan-00165 && uv run pytest tests/test_research_c3_asopr_reentry_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00165/pt`, one plain blocking call, `timeout` 600000 ms: `1 passed`, never a skip (measured on the authoring tree, a call of 11.33 s). The case joins `tests/slow-cases.txt` at its `sorted()` place, after the `tests/test_research_b4_sol_noborrow_rolling_basis.py` line (`:81`):

```text
tests/test_research_c3_asopr_reentry_basis.py::test_the_c3_reentry_inputs_reproduce_the_measured_basis_on_reading_10s_block_and_events
```

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_c3_asopr_reentry_basis.py tests/slow-cases.txt`; the Global Constraints' list over the two paths (measured on the authoring tree: `18 passed, 1 deselected in 30.56s`); the two tree walkers its skip gate and data mark meet, `mkdir -p .tmp/plan-00165 && uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00165/pt` (measured `376 passed in 13.29s`); `uv run pre-commit run -a` until clean. No probe: the case is slow, recorded `probe skipped: slow case`.
- [ ] **Step 4: Commit** — `test(research): C3 trial 1's inputs half against the measured basis — reading 10's block and events, the first engagement, the re-entered closes, the entries, arm B's turnover and largest gross, arm A's turnover`, the message carrying the gate's result line, `probe skipped: slow case — tests/test_research_c3_asopr_reentry_basis.py::test_the_c3_reentry_inputs_reproduce_the_measured_basis_on_reading_10s_block_and_events`, the line `It reads data/btc-onchain-20261124T162656Z and data/ohlc-full: re-run it with both linked into the worktree (ln -sn) and unlinked before its removal; with the snapshot unlinked, it skips.` and the two trailer lines.
- [ ] **Step 5 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, the owner's entries, this plan and Tasks 1–3 — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing computes or reads arm B's returns or net-of-cost series, a head-to-head or a bar leg of arm B — through the code, a program or arithmetic over a stored figure — or runs either new subject or either of its computes over the real sets, or recomputes or extends a forward of reading 10, before the spec's hash, and the data-gated case runs with both sets linked into the reader's worktree and unlinked by the reader before its report, since with the snapshot unlinked it skips. Each report names the tip it read, the tip Task 4 step 1 diffs from. Task 4 waits until the trio has closed with no open Critical or Important. No decisions-log entry is owed before the hash: the owner's eight `[iter-210]` entries hold every decision the spec carries (`docs/research/10.phase4-decisions.md:1136-1173`).

## Task 4 (the controller's): the gate, the spec hash, the develop check, the data test and the check programs (D15)

- [ ] **Step 1: The gate** — each check its own call, each read before the next: the reads through Task 3 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00165-c3-trial-1-asopr-reentry-design.md docs/research/10.phase4-decisions.md` exits 0; the owner's picks stand at the spec's seven heads, `grep -c '^\*\*The owner.s pick, 2026-11-24' docs/specs/00165-c3-trial-1-asopr-reentry-design.md` printing `7` (measured at `3a7878308`); the code path since reading 10's run — the spec's basis lists it from that run's commit to the branch's cut — `git log --oneline 88fdf97e14a4ee5076db35468f4b0177d0e7cb31..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/onchain cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version`, lists Tasks 1–2's commits and their fixes alone (measured at the base: nothing); any other commit is named, step 4 deciding whether it moved the inputs half or the computes the trial reuses; and the count, read from the trial-attempts log, which the spec left unread:

```bash
uv run python -c 'import json; from pathlib import Path; from cli.registry import attempts, budget; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print("required_n", c.required_n("C3"), "; bucket C spent", c.spent("C"), "of", budget.BUDGET["C"], "; orphans", [o.describe() for o in c.orphans])'
```

  It prints `required_n 1 ; bucket C spent 0 of 10 ; orphans []` (measured in the scratch worktree with the log's path swapped for a fresh log made by `attempts.init_log` in a temporary directory; the main checkout's log is the controller's to read). A `required_n` above 1 or an orphan in bucket C stops the task before the hash: the count is fixed at 1 by the spec (D2), and the trial goes back to the owner through T0228.
- [ ] **Step 2: D15 (1), the spec hash** — `sha256sum docs/specs/00165-c3-trial-1-asopr-reentry-design.md`; its value, pasted from that call, is the run's `--spec-hash` and the record's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D15 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0. A non-zero exit stops before the run: the controller reads which line moved, the same `git diff` without `--quiet`, and only for a line another writer appended legitimately — a registry record or a reading another branch's merged PR carries — merges develop, alone (`git merge --no-edit origin/develop`) — a conflict confined to `docs/research/10.phase4-decisions.md` or `tests/slow-cases.txt` resolved keeping both sides' lines, in the decisions log develop's entries above this branch's and in the slow-cases file each line at its `sorted()` place, and committed as the merge; a conflict in any other file aborted with `git merge --abort`, which stops the task, T0228's — then takes a delta read of the merge in place of re-running step 1: step 1's code-path log over `<the tip the last read names>..HEAD`, then `pre-review`, then `review` over that range and `re-review` over a fix of it within the branch's two, each `drive` carrying Task 3 step 5's sentence with its "before the spec's hash" read "before Task 5's run, reading 10's replay excepted", the commits the log lists, and one sentence more: develop's commits were each read on their own PR, so the read judges the merge's resolution and each listed commit's effect on the trial — whose tip becomes the tip the last read names, and step 4 runs on the merged tree. A C3 record another branch landed raises `required_n("C3")` above 1, and the run is then refused before its fit (D2): the trial stops, T0228's. The check has two sites, this step and Task 5 step 1, and both take this path.
- [ ] **Step 4: D15 (3), the data test on the run's tree, with the subjects' two fixture rows, reading 10's basis case and replay and record 33's regression** — with both sets linked: `mkdir -p .tmp/plan-00165 && ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_c3_asopr_reentry_basis.py tests/test_research_c3_onchain_reading_basis.py::test_the_inputs_half_reads_the_snapshots_measured_basis 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[c3-asopr-reentry-evaluates]' 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[c3-asopr-reentry-preflight-evaluates]' 'tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-10]' tests/test_portfolio_builder.py::test_frozen_figures_regression -q -p no:cacheprovider --basetemp=.tmp/plan-00165/pt > .tmp/plan-00165/basis.out 2>&1`, one background call: `6 passed`, never a skip or an xfail — the fixture rows run the build end to end on the tree a fix of the reads may have changed, reading 10's basis case holds its `arm`, `counts` and `features` to `_c3_reading_inputs`, the half this trial's inputs call unchanged, its replay rebuilds its stored figures through that half and `_c3_reads`, and the regression holds the daily benchmark's Sharpe to record 33's 1.2455 (measured on the authoring tree in the scratch worktree: the basis case and the two fixture rows `3 passed in 17.51s`, reading 10's basis case `1 passed in 9.05s`, the regression `1 passed in 3.00s`; reading 10's replay not run by the author, since it recomputes that reading's forwards and this plan is written before the hash); a failure is a finding before the run — the data test's an instrument finding, a fixture row's a defect in the code, the replay's a moved inputs half, the regression's a moved benchmark — T0228's, and the run waits. Records 55's and 56's replays read two sets this branch does not link and are not run here (D15).
- [ ] **Step 5: The check programs** — reviewed with this plan and extracted from the tip the last read names, never retyped, each its own call: `mkdir -p .tmp/plan-00165 && git show <that tip>:docs/plans/00165-c3-trial-1-asopr-reentry.md | sed -n '/^"""Spec 00165 D15.s pre-flight read/,/^\x60\x60\x60$/p' | sed '$d' > .tmp/plan-00165/preflight_check.py`, D15's (a)–(f) in order, the dead knob read before the engagement, exit 0 on a pass, else one `sys.exit` naming the step that stopped:

```python
"""Spec 00165 D15's pre-flight read, (a) to (f) in order: exit 0 on a pass, else the one sys.exit naming what stopped it."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from tests.test_research_c3_asopr_reentry_basis import BLOCK, ENGAGEMENT, VOUCHED
from tests.test_trial_registry_provenance import _readings, _trials

out = Path(".tmp/plan-00165/c3-asopr-reentry-preflight.out").read_text()
run = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
m, block = run["metrics"], run["datasets"]
print("block", compute_hash(block), run["vouched"])
if compute_hash(block) != BLOCK:
    sys.exit("(a) the inputs' block differs from reading 10's")
if run["vouched"] != VOUCHED:
    sys.exit("(a) a set is not vouched as the spec reads it")
counted = sum(asset["events"] for asset in _readings()[10]["metrics"]["counts"]["asopr|low|flat"].values())
print("events", sum(m["events_per_year"].values()), "reading 10's", counted)
if m["events_per_year"] != ENGAGEMENT["events_per_year"] or sum(m["events_per_year"].values()) != counted:
    sys.exit("(b) the events are not the cell's as reading 10 counted them")
print(f"first engaged {m['reentry_first_engaged']} primary {m['primary_returns']} differ {m['stamps_positions_differ']}")
print(f"re-entered {sum(m['reentered_per_year'].values())} entries {m['reentry_entries']} turnover_b {m['turnover_b']}")
if not any(m["reentered_per_year"].values()):
    sys.exit("(c) the re-entry holds no asset at any close: the dead knob")
off = [key for key, value in ENGAGEMENT.items() if m[key] != value]
if off:
    sys.exit(f"(d) the engagement differs from the measured basis: {off}")
stored = _trials()[33]["metrics"]["benchmark_sharpe_full"]
print("benchmark", m["benchmark_ann_sharpe_noc"], "record 33's", stored)
if abs(m["benchmark_ann_sharpe_noc"] - stored) >= 0.005:
    sys.exit("(e) the daily benchmark is not record 33's")
print({key: m[key] for key in ("dsr", "dsr_pass", "spa_p_value", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes")})
sys.exit(0 if m["passes"] == 1 else "(f) arm A fails its bar")
```

  and `mkdir -p .tmp/plan-00165 && git show <that tip>:docs/plans/00165-c3-trial-1-asopr-reentry.md | sed -n '/^"""Spec 00165 D14.s record, read off/,/^\x60\x60\x60$/p' | sed '$d' > .tmp/plan-00165/record_check.py`, the record's checks, its one argument the spec's sha256:

```python
"""Spec 00165 D14's record, read off the registry's last line against the run's print, its pre-flight's block and the
measured basis: exit 0 when every check holds. Its one argument is the spec's sha256."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_c3_asopr_reentry_basis import BLOCK, DATASET, ENGAGEMENT

name, spec_hash = "c3-asopr-reentry", sys.argv[1]
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(f".tmp/plan-00165/{name}.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]
before = Path(f".tmp/plan-00165/{name}-preflight.out").read_text()
preflight_block = compute_hash(json.JSONDecoder().raw_decode(before, before.index("{"))[0]["datasets"])
subject = SUBJECTS[name]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == preflight_block == BLOCK,
    "invocation": invocation
    == {"subject": name, "dataset": DATASET, "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"])
    == ("C3", 1, "C3-asopr-reentry-a1lf-full-v1", "iter-210", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "engagement": {key: m[key] for key in ENGAGEMENT} == ENGAGEMENT,
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
```

  Both are then checked with `test -s .tmp/plan-00165/preflight_check.py && test -s .tmp/plan-00165/record_check.py && uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00165/preflight_check.py .tmp/plan-00165/record_check.py`, exit 0. Neither is committed. The pre-flight check was run in the scratch worktree over synthetic pre-flight prints carrying the real block and vouched status, read by `_c3_reads` with no compute, the real engagement, which is positions alone, and typed stand-ins for arm A's figures and bar: it printed the block, the events beside reading 10's count, the first engagement, the primary count, the differing closes, the re-entered closes, the entries, arm B's turnover, the benchmark beside record 33's and the bar's flags, and exited 0; with `passes` 0 it exited 1 on `(f) arm A fails its bar`, with `reentered_per_year` counting no asset-close on `(c) the re-entry holds no asset at any close: the dead knob`, and with the benchmark at 1.2399 on `(e) the daily benchmark is not record 33's`. The record check was parsed and not run: no record exists.

## Task 5 (the controller's): trial 1 — its pre-flight, its run and its record (D12–D15)

`<H>` is Task 4 step 2's sha256.

**The notes rule**: every free-text `--notes` this plan passes is written first, in a call of its own, to its own file under `.tmp/plan-00165/` by a quoted heredoc — `mkdir -p .tmp/plan-00165 && cat > <its file> <<'EOF'`, the text on the lines after it, `EOF` alone on the last — and passed as `--notes "$(cat <its file>)"` behind `test -s <its file> &&` in the run's own line: no `'` or `"` in the text can end the argument, and an absent or empty file stops the line before `uv run` starts, never a run with empty notes. The sites, the whole of them: step 3's reading, `.tmp/plan-00165/c3-asopr-reentry-reading-notes.txt`, and step 4's trial, `.tmp/plan-00165/c3-asopr-reentry-notes.txt` — the two `--notes` spec 00165 D15 names; no other step of this plan passes one.

- [ ] **Step 1: The develop check** — Task 4 step 3 whole, its stop, its merge path and Task 4 step 4 after a merge with it; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `mkdir -p .tmp/plan-00165 && uv run zcrypto research eval --subject c3-asopr-reentry-preflight --dataset btc-onchain-20261124T162656Z > .tmp/plan-00165/c3-asopr-reentry-preflight.out 2>&1`, a plain eval of a subject with no rule — the inputs half and one bar, well under a minute (measured: the data-gated case's inputs half 11.33 s, one `a1_kill_bar` over 4,581 synthetic returns 2.08 s) — one background call; at its notification and on its exit 0, `uv run python .tmp/plan-00165/preflight_check.py`. Exit 0: step 4. A `sys.exit` message naming one of (a)–(f): D15's instrument finding, step 3. A traceback, or a refusal before the build, is a code or environment fault, the step stopped and T0228's with its line; a refused build — exit 1 with no traceback, its output naming `c3-asopr-reentry-preflight over the full history: …` — prints no metrics, keeps no reading, and is recorded in Task 6's T0228 findings with its line quoted, the trial unspent.
- [ ] **Step 3: On a stop, the reading** — its notes, by the notes rule, in `.tmp/plan-00165/c3-asopr-reentry-reading-notes.txt`: `C3 trial 1's pre-flight (spec 00165 D15): <the check's sys.exit line, whole, between single quotes, never a double quote>; no verdict, the trial unspent`; then `mkdir -p .tmp/plan-00165 && test -s .tmp/plan-00165/c3-asopr-reentry-reading-notes.txt && uv run zcrypto research eval --subject c3-asopr-reentry-preflight --dataset btc-onchain-20261124T162656Z --reading --iteration iter-210 --spec-hash <H> --notes "$(cat .tmp/plan-00165/c3-asopr-reentry-reading-notes.txt)" > .tmp/plan-00165/c3-asopr-reentry-reading.out 2>&1`, one background call; then step 6's stop arm.
- [ ] **Step 4: The trial** — one run: `mkdir -p .tmp/plan-00165 && test -s .tmp/plan-00165/c3-asopr-reentry-notes.txt && uv run zcrypto research eval --subject c3-asopr-reentry --dataset btc-onchain-20261124T162656Z --register --iteration iter-210 --family C3 --n-trials 1 --variant C3-asopr-reentry-a1lf-full-v1 --spec-hash <H> --notes "$(cat .tmp/plan-00165/c3-asopr-reentry-notes.txt)" > .tmp/plan-00165/c3-asopr-reentry.out 2>&1`, about half a minute (measured parts: the inputs half 11.33 s, seven bars at 2.08 s and two head-to-heads at 1.11 s over synthetic returns of its length), one background call, `cat` at its notification. No `--verdict` and no plain eval, before or after. The notes, written before the run to `.tmp/plan-00165/c3-asopr-reentry-notes.txt` by the notes rule, name only what is fixed before it, each `<…>` read off `.tmp/plan-00165/c3-asopr-reentry-preflight.out` or step 2 of Task 4:

```text
subject c3-asopr-reentry over btc-onchain-20261124T162656Z with ohlc-full beside it, both read whole, no window and no as-of; C3 trial 1, the one cell reading 10 found with potential, asopr|low|flat|H7, on the owner's pick of 2026-11-24; arm A the A1 sleeve as records 44 and 47 build it, the A1-lf weekly book at target vol 0.12 averaged over its seven weekly offsets, on the ten EUR assets' daily closes; arm B that sleeve with a long re-entry in each asset it holds flat at a daily close whose previous UTC day's adjusted SOPR lies at or below the 10th percentile of its own history from 2011-01-01, read after 365 values and one day late; the re-entry sized at the asset's inverse-vol weight times the vol target of the equal-risk basket itself at 0.12, through the sleeve's seven block starts, held 7 daily closes from the last such close and closed where the sleeve itself turns long; long-only, nothing borrowed; every asset charged 0.006 per side on its own turnover; no limit wired, arm B's largest gross 0.7649; the hypothesis: the sleeve with the re-entry has a higher mean net-of-cost return than the sleeve alone from the first close the two books differ; n_trials 1, C3's true count, var_trials 0.0, the DSR leg binding; the bar record 34's call on the daily grid against record 33's frozen daily benchmark, decisive from return index 230, mean block 17, seed 42, 2000 resamples, blocks 17 and 102 by seeds 42, 7 and 1234 recorded; the head-to-head from return index 97 (close 2013-12-21), arm B's first engagement, decides, the full-window read and the drawdown pair from that index beside it, an adopt needing arm B's maximum drawdown at most 1.2 times arm A's; the contamination: the cell was searched for by reading 10 (record_hash ed1bb73e..., spec 00164 at 89eb8be9...) among 32 cells over the history the A1 sleeve was designed and adopted on, the block this trial reads again, every return of the verdict inside that search; the trigger's constants reading 10's, the size and the hold chosen after it on positions and turnover alone; 1549 events at 309 closes, 1496 of them with BTC at or below its 200-day SMA, 4899 re-entered asset-closes in 367 entries, arm B trading 69.84 against arm A's 46.73; pre-flight: block 19ee5c23..., arm A <its seven anchors>, the bar's dsr <its dsr> and SPA p <its spa_p_value>, passes 1, the benchmark's Sharpe <its value> against record 33's 1.2455; the park row names no variant, C3's next step after the verdict the owner's pick; the matrix pre-registered by the spec's sha256 <H>
```

  A refusal from the count — an orphan, a C3 record landed elsewhere, or bucket C spent — comes before the fit or after the print, naming each orphan, the count or the bucket's figure: no record, no reading; T0228 carries it (Task 6). A stop by the rule writes a reading carrying its attempt, which counts 0: step 6's stop arm. On any other exit — a refused build, a traceback, a signal, a refusal after the print — the attempt check runs, `uv run python -c 'import json; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; b = [x["attempt"] for x in lines if x["kind"] == "begin" and x["invocation"]["subject"] == "c3-asopr-reentry"]; print(b[-1], [x["failed"] for x in lines if x["kind"] == "end" and x["attempt"] == b[-1]] or "open") if b else print("none")'`: `none` — no begin line names the subject — is a refusal before the attempt opened, recorded in T0228 with the run's last line, the trial unspent; a refused build ends its attempt failed, counting 0, recorded in T0228 with its line, the trial unspent; any other `failed` text, `open`, or `<id> [None]` stops the task, T0228's with the end of the run's output quoted whole.
- [ ] **Step 5: The record's checks** — on a record: `uv run python .tmp/plan-00165/record_check.py <H>` exits 0; its printed `counted` is read, never checked: T0016's line takes every orphan off the count (Task 6 step 2). A failed check — this one, the record's replay in step 6, or on step 6's stop arm the reading's line check and its replay — stops the task where it stands: what the run appended, the record or the reading, stays in place uncommitted and nothing is committed; the controller hands the owner the failing check's output quoted whole, and what becomes of the record or reading is the owner's word, Task 6 waiting on it.
- [ ] **Step 6: The records commit** — on a record: (i) at the end of `docs/research/10.phase4-decisions.md`, after one blank line, with `iteration-closeout` loaded, the entry `[iter-210] Verdict — C3 trial 1 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family C3 n=1)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry, its text to its first `. ` holding no other verdict word; the body: the matrix row that fired, read off the record's stored keys beside its stored verdict with D13's table (`sed -n '/^| Arm A.s bar and the re-entry/,/^Every quantity the matrix reads/p' docs/specs/00165-c3-trial-1-asopr-reentry-design.md`), with `arm_a_passes`, `reentered_per_year` summed, `passes`, `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary` and `max_drawdown_reduction_pct` unrounded, the full-window pair beside them; `n_trials` 1, `var_trials` 0.0 and the DSR leg (`dsr_corrected`, `dsr_pass`); the bar's other legs and the six `spa_p_decisive_*`; `max_drawdown_primary` beside `arm_a_max_drawdown_primary`, and `max_drawdown` beside `arm_a_max_drawdown`; the pre-flight's block, anchors, benchmark and `passes` from `.tmp/plan-00165/c3-asopr-reentry-preflight.out`; the engagement — `reentry_first_engaged`, `primary_returns`, `stamps_positions_differ`, `events_per_year` and `reentered_per_year` summed, `reentry_entries`, `events_without_size`, `turnover_a` beside `turnover_b`, `gross_max`; the contamination D10 states — reading 10, its 32 cells and its `record_hash`, every return of the verdict inside that search; on an adopt D16's path in its order; on any verdict, C3's next step the owner's pick (Task 6); on a reject the hypothesis as the notes word it, archived — in the form of `[iter-194] Verdict — B3 trial 3 REJECT` (`docs/research/10.phase4-decisions.md:714`); (ii) in `tests/test_trial_registry_provenance.py`, `LANDED_N_TRIALS` (`:40`) and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts (`:978`) each gain `"c3-asopr-reentry": 1,` after `"b3-btc-overlay": 3,`; (iii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<its trial_id>]` at its `sorted()` place; on an adopt, (iv) in `docs/open-topics/T0123-sleeve-promotion-path.md`'s `ripe_when`, `whose subject is no revalidation of record 47.` becomes `whose subject is no revalidation of record 47 — registry trial <N>, C3 trial 1's ADOPT on the A1 sleeve alone, ripens this only once the P1 combination trial over record 47's book that carries its re-entry adopts.` (D16; the anchor counted unique with `grep -c` first), and `uv run python infra/scripts/topics-index.py` re-renders `docs/open-topics/README.md`. Then `git add` by path of `docs/reference/trial-registry.jsonl`, the record step 4's run appended, `docs/research/10.phase4-decisions.md`, `tests/test_trial_registry_provenance.py` and `tests/slow-cases.txt`, and on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md` and `docs/open-topics/README.md`; the list over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path — `tests/test_open_topics_frontmatter.py` among the index's readers on an adopt — `tests/test_research_command.py` in its four parts where the list names it; `uv run pre-commit run -a` until clean, its rewrites staged. In the probe worktree, which the Global Constraints' probe setup creates from that index and whose tree it prints, both sets linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/ohlc-full /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/c3-trial-1/.tmp/plan-00165/probe/data/ohlc-full` and `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/btc-onchain-20261124T162656Z /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/c3-trial-1/.tmp/plan-00165/probe/data/btc-onchain-20261124T162656Z`, each unlinked after the replay and the probe and the worktree removed as the Global Constraints' probe paragraph removes one that held a link: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'trial-<its trial_id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt`, one background call: `1 passed`, never a skip, its result line and call time for the message — a difference or a skip is a failed check, step 5's stop; then the literal's probe, expected `KILLED` (its two seds dry-run on the authoring tree, each changing one line): `infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_c3_asopr_reentry(/def _build_c3_asopr_reentry_gone(/' --mutation 's/^_C3_ASOPR_REENTRY_N_TRIALS = 1 /_C3_ASOPR_REENTRY_N_TRIALS = 2 /' -- uv run pytest tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal -q -p no:cacheprovider --basetemp=.tmp/pt`. Commit that index, with no `git add` after the setup, as `docs(research): C3 trial 1 registered — <verdict>, the A1 sleeve with a re-entry in each asset it holds flat under aSOPR's low band, registry trial <N>`, the message carrying the tie and provenance tests' result line, the replay's with its call time, `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):`, the literal's `infra/scripts/mutate-probe.sh` command and its verdict line, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<N>]`, the line `The replay reads data/btc-onchain-20261124T162656Z and data/ohlc-full: re-run it with both linked into the worktree (ln -sn) and unlinked before its removal; with ohlc-full unlinked, it skips.`, and the two trailer lines; after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.

  On a stop (step 3, or the rule's stop under `--register`): the ledger's last line is checked — its subject `c3-asopr-reentry-preflight` with outcome `null`, or `c3-asopr-reentry` with the `no_verdict` text and a non-null `attempt`; its `spec_hash` `<H>`; its metrics the run's printed ones, a line off any of them a failed check, step 5's stop — the entry is `[iter-210] C3 trial 1 — instrument finding, the trial unspent (reading <its reading_id>)`, naming what failed, quoted; no literal; the slow row `[reading-<its id>]` at its `sorted()` place, the replay rebuilding the run over the real sets, as (iii) adds the record's; `git add` by path of `docs/reference/reading-ledger.jsonl`, the reading the run appended, `docs/research/10.phase4-decisions.md` and `tests/slow-cases.txt`, then the record arm's list, pre-commit, probe worktree and replay, with `-k 'reading-<its id>'`, `1 passed`, never a skip; committed as `docs(research): C3 trial 1 — instrument finding, kept as reading <id>; no trial spent` with no literal's probe. On a refusal from the count or a refused build: no commit here; Task 6 records it.

## Task 6: the topics after the verdict — T0228, T0016 and the index (D16)

**Files:** `docs/open-topics/T0228-btc-on-chain-metrics-computed-from-chain-data.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`.

Every figure is read off the committed record or reading and its entry. Task 5's outcome picks the arm: a verdict — adopt, park or reject — takes the verdict arm; no verdict — a stop kept as a reading, a refused build, a refusal from the count, a merge aborted at a develop check, the data test, the replay or the regression failing or skipping, or any other end Task 5 sends to T0228 — the stop arm. Neither arm closes C3, retires a subject or writes a decisions-log entry: C3's next step is the owner's pick (D16), its entry a later branch's.

- [ ] **Step 1: T0228**, per `topic-ops`, each anchor counted unique with `grep -c` before its edit and the heading set (`grep '^#'`) compared before and after:
  - `ripe_when` (`:3`): on the verdict arm it becomes `` ripe_when: 'an activity — C3''s next step after trial 1 is picked; check: `grep -c -E ''^\[iter-[0-9]+\] C3.s next step after trial 1'' docs/research/10.phase4-decisions.md` prints at least 1' ``; on the stop arm `` ripe_when: 'an activity — the owner''s call on trial 1''s stop is recorded; check: `grep -c -E ''^\[iter-[0-9]+\] C3.s next step after trial 1.s stop'' docs/research/10.phase4-decisions.md` prints at least 1' `` — in the frontmatter's single quotes, each `'` inside it doubled as written here, the check kept in its own backticks, its `.` standing for the apostrophe a shell's single quotes cannot hold.
  - `## Findings so far`: after the `**Reading 10 (iter-209, spec 00164): one cell has potential, `asopr|low|flat|H7`**` bullet, one bullet `**C3 trial 1 <VERDICT> (iter-210, spec 00165, registry trial <N>).**` — the row that fired and the re-entry's engagement in one or two sentences, pointing at its decisions-log entry for the figures — or, on the stop arm, `**C3 trial 1, no verdict (iter-210, spec 00165).**`, naming the reading by id where one was kept and quoting whole the line that stopped it — the check's `sys.exit` line, the conflict `git merge` printed, which stands in no file, only in the controller's call, and so reaches this task quoted whole in the controller's dispatch of it, the failure or skip line in `.tmp/plan-00165/basis.out`, the line in `.tmp/plan-00165/c3-asopr-reentry-preflight.out` or `.tmp/plan-00165/c3-asopr-reentry.out`, or that run's output's end as Task 5 step 4 quotes it — the trial unspent unless step 2's count lists its attempt as an orphan, which spends the slot.
  - `## Done so far`: after the `**The reading's branch, iter-209**` bullet, one bullet: `` - **C3's trial 1, iter-210 (spec/plan `00165`)**: the family key `C3` in `cli/registry/budget.py`, the module `cli/alpha/c3_reentry.py`, the subjects `c3-asopr-reentry` and `c3-asopr-reentry-preflight` in `cli/research/subjects.py` and the data-gated basis test `tests/test_research_c3_asopr_reentry_basis.py`; registry trial <N>, <VERDICT>. `` — on the stop arm its last clause reads `` no verdict, no slot spent. ``, or, where step 2's count lists the trial's attempt as an orphan, `` no verdict, one slot spent by its orphaned attempt. ``
  - `## Suggested next steps`: the bullet that opens `- **C3's trial 1, on the owner's pick**:` becomes on the verdict arm `` - **(owner) C3's next step after trial 1**: a further trial from bucket C's remaining slots, [[T0016]]'s Glassnode step, `_pit` diff first, LTC and DOGE below, or the family's close — asked of the owner with trial 1's verdict entry and recorded in `docs/research/10.phase4-decisions.md` as `[iter-<N>] C3's next step after trial 1`, this topic's trigger (spec 00165 D16). ``; on an adopt a bullet after it, `` - **(owner) C3 trial 1's ADOPT (registry trial <N>), recorded, never deployed**: its path in order — a read of the days no forward has read, the snapshot's after 2026-03-30 and every day the chain has added since, over `ohlc-rolling`, under its own spec and a criterion fixed before it; then a P1 combination trial over record 47's book with the re-entry in its A1 sleeve, outside every bucket's budget; then [[T0123]]'s promotion path (spec 00165 D16). ``; on the stop arm the bullet becomes instead `` - **(owner) C3's next step after trial 1's stop**: trial 1 run again once its cause, quoted in Findings, is fixed, or another step for C3 — recorded in `docs/research/10.phase4-decisions.md` as `[iter-<N>] C3's next step after trial 1's stop`, this topic's trigger. `` The `**Only then LTC and DOGE**` bullet stands.
- [ ] **Step 2: T0016**, the same mechanics:
  - `ripe_when` (`:3`): on the verdict arm `` ripe_when: 'C3: an activity, C3''s next step after trial 1 is picked, recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] C3.s next step after trial 1'' docs/research/10.phase4-decisions.md` prints at least 1' ``; on the stop arm `` ripe_when: 'C3: an activity, the owner''s call on trial 1''s stop, recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] C3.s next step after trial 1.s stop'' docs/research/10.phase4-decisions.md` prints at least 1' ``.
  - `## Findings so far`: the budget bullet's C figure (`:20`) read off the count Task 4 step 1's program prints, run again here on the committed record, every orphan in it: `and **C = 10**, untouched;` becomes `and **C = 10** (C3 spent <its spent>, <10 less it> remain);`, each orphan it lists named there — on the stop arm with no orphan the bullet stands; after the `**C3's on-chain reading (iter-209, spec 00164, reading 10).**` bullet, the bullet step 1 adds to T0228's findings, word for word.
  - `## Suggested next steps`: the bullet that opens `- C3 is bucket C's last family, open since iter-204` becomes on the verdict arm `` - C3 is bucket C's last family, open since iter-204 (spec/plan `00164`), its trial 1 run at iter-210 (spec/plan `00165`, registry trial <N>, <VERDICT>); (owner) its next step — a further trial, the Glassnode step below, LTC and DOGE, or the family's close — is asked of the owner and recorded in `docs/research/10.phase4-decisions.md` as `[iter-<N>] C3's next step after trial 1`, this topic's trigger (spec 00165 D16). ``; on the stop arm `` - C3 is bucket C's last family, open since iter-204 (spec/plan `00164`); its trial 1 (iter-210, spec/plan `00165`) stopped with no verdict, and (owner) what follows — the trial run again once its cause is fixed, or another step — is recorded in `docs/research/10.phase4-decisions.md` as `[iter-<N>] C3's next step after trial 1's stop`, this topic's trigger. ``
  **Author's call — each arm's check reads a heading no entry carries yet**: measured in the scratch worktree on the base's topics with sample figures: each arm kept both files' heading sets, parsed to the intended frontmatter text and, with step 3 applied, passed `tests/test_open_topics_frontmatter.py tests/test_topics_index.py` (`1151 passed` on each arm, and again with Task 5 step 6's T0123 line); the verdict arm's check and the stop arm's each print 0 on the log at `3a7878308`.
- [ ] **Step 3: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 4: Gate and commit** — `git add` the three paths by name; the Global Constraints' list over them, `tests/test_research_command.py` in its four parts if the list names it, with `tests/test_open_topics_frontmatter.py` and `tests/test_topics_index.py` by path; `uv run pre-commit run -a` until clean; committed on the verdict arm as `docs(open-topics): T0228 and T0016 after C3 trial 1 — <verdict>, C3's next step the owner's pick`, and on the stop arm as `docs(open-topics): T0228 and T0016 after C3 trial 1's stop — no verdict, what follows the owner's`, its message naming no guard added or changed and so no probe.

## Task 7 (the controller's): the change-index row, the read and the PR

- [ ] **Step 1: The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-210 — C3 trial 1: aSOPR's low tail as a re-entry` (69 characters by `printf '%s' <it> | wc -m`, under the cap), its own commit.
- [ ] **Step 2: The read** — the `pre-review` of Tasks 5–6's commits and the row's, then `review` over `<the tip the last read names>..HEAD`, and `re-review` over a fix of it within the branch's two, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated case and the replays the messages record run with both sets linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 3: The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the verdict or the stop and what it leaves the owner to pick, the pre-flight's output quoted whole in a fenced block (`.tmp/plan-00165/c3-asopr-reentry-preflight.out`), every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the owner's words the trial runs under — the pick of trial 1's spec and the seven picks of 2026-11-24, each quoted with its stamp as the decisions log's `[iter-210]` entries carry them — and the session transcript named as their source, this plan's spec amendments under `## Spec deviations`, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the last read names. Merged through `merge-pr`; before it, `git status --short --ignored` read, `.tmp/plan-00165` collected and removed, and each link removed with `test -L <the checkout>/data/<set> && unlink <the checkout>/data/<set>` in this worktree and in each reader's checkout whose `data/` holds it; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows `ohlc-full` and `btc-onchain-20261124T162656Z` still there.

Decisions log: the owner's pick of trial 1's spec and the seven picks on its open decisions, entered before this plan (`docs/research/10.phase4-decisions.md:1136-1173`); the verdict or instrument-finding entry (Task 5 step 6), in its record's commit; C3's next step after the verdict is the owner's, its entry a later branch's (T0228's and T0016's trigger, Task 6).
