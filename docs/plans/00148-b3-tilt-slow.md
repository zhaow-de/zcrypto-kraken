# B3 trial 2 — the rank tilt of the A2-4h ensemble's long weights on a 540-close momentum score, on frozen ohlc-full: the trial subject and its twin, the data-gated basis test, the owner's word and the loop's pick before the hash, the gated run and the record, T0016 — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt tests/test_research_b3_tilt_slow_basis.py docs/research/10.phase4-decisions.md docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl tests/test_trial_registry_provenance.py docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/T0123-sleeve-promotion-path.md docs/open-topics/README.md docs/reference/change-index.md docs/specs/00148-b3-tilt-slow-design.md docs/plans/00148-b3-tilt-slow.md` prints `tier: full`, for `tests/test_research_command.py` "a test importing cli.alpha", `tests/test_research_b3_tilt_slow_basis.py` "a test importing cli.alpha.b1" once Task 2 has created it, `docs/reference/trial-registry.jsonl`, and `tests/test_trial_registry_provenance.py` "a test importing cli.registry").

**Goal:** B3's trial 2 (spec 00148) — trial 1's rank tilt of the adopted A2-4h ensemble's long weights, its strength 0.5 and its 8-asset floor unchanged, on the trailing 540-close simple return in place of the 180-close one, against the untilted ensemble, on frozen `ohlc-full`: two research subjects in `cli/research/subjects.py`, the trial and its evaluate-only pre-flight twin, reading trial 1's halves where they take no score window; the data-gated test of their inputs half; the owner's word on B3's next step, the loop's pick of the variant and the trial's conventions in the decisions log before the hash; the trial run through spec 00133's trial-attempts log at B3's count 2, its verdict or stop in the registry and the decisions log; then T0016, its B3 arm on trial 3, the owner's sequence.

**Architecture:** no new module and no change to `cli/alpha/` or `cli/registry/`. `cli/research/subjects.py` gains two insertions and changes no existing line: the block before `SUBJECTS` — `_B3_SLOW_SCORE_LOOKBACK`, `_B3_SLOW_N_TRIALS`, `_b3_slow_ensemble`, `_b3_slow_inputs`, `_b3_slow_build` and the two builders, each of the first three trial 1's `_b3_ensemble`, `_b3_inputs` and `_b3_build` in form, on the 540-close score and the count 2 — and two `SUBJECTS` entries. Trial 1's `_B3Inputs`, `_b3_reads`, `_b3_first_engaged`, `_b3_engagement`, `_b3_metrics`, `_b3_preflight_metrics`, `_b3_rank_tilt_verdict`, `_B3_STRENGTH`, `_B3_FLOOR`, `_B3_METRIC_KEYS` and `_B3_PREFLIGHT_KEYS`, `cli/alpha/b3.py`'s `b3_book_returns` and trial 58's `_b4_ensemble`, `_b4_limited`, `_b4_net` and `_b4_arm_a_bar` are read as they are, and no import is added. The family key `B3` is in `BUCKET_OF` already. Nothing writes a dataset.

**Tech Stack:** Python 3.14 through uv; polars; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00148-b3-tilt-slow-design.md` — binding; D1–D10 are cited by name and the values below are copied from it. It reads spec 00147's tilt, arm A, costing, limits, bar, matrix and rule, frozen by record 60's `spec_hash`. **Iteration:** iter-193. **Topic:** T0016, its B3 arm. **Branch:** `research/iter-193-b3-tilt-slow`, worktree `.claude/worktrees/iter193`, `data/ohlc-full` linked read-only from the main checkout, and no other set. A choice this plan makes that the spec leaves open is marked **Author's call**. Every code fence below was cut from the files the author ran: Tasks 1–2's code and tests were written in this worktree, then carried into a detached scratch worktree at the base, `22c220677`; Task 1's new cases measured red there with the test file alone applied (`22 failed, 922 deselected`, each at its call) and green with Task 1's code (`22 passed, 940 deselected`), the shared rows the two subjects add green (`19 passed, 943 deselected in 113.59s`); Task 1 step 7's four gate parts green on Task 1's tree committed there; Task 1's 39 probe rows run on that commit, 39 of 39 `KILLED`; Task 2's data-gated case `1 passed` with a call of 136.75 s on the authoring tree; the slow cases timed; on Task 2's tree committed in the scratch worktree, Task 2's gate, its three decisions-log entries appended and run through the decisions-log tests, Task 3 step 4's data test and fixture rows (`3 passed in 166.04s`) and record 60's replay (`1 passed`, a call of 266.95 s) with `ohlc-full` linked, Task 3 step 5's pre-flight check run over synthetic pre-flight prints carrying the real block, and Task 5's T0016 edits and index tried on each outcome's arm, then reverted. The fences applied to the base as the steps say reproduce every authoring file, three later edits of Task 1 step 1's fence aside — the bit-identity case's first engagement and basket sizes, the fixture's docstring cut to what they hold, the plain-eval case's read record cut — whose cases run green on the plan's code in memory and red on the base, the probe rows that target them, 24, 38 and 39, killed as before; the files were restored to the base before this plan was committed. Not run: any `zcrypto research eval` of the two subjects (Task 4), the record's check program beyond a parse, the record's replay and the literal's probe (Task 4), the topic edits as committed (Task 5) and the PR (Task 6).

## Global Constraints

- **The books and the costing** (D2–D5): the union `_capturing_union(reader, dataset, 240, window, None, accept_holes)` of the ten EUR assets through trial 1's `_b3_reads`, no other pair, refused before any book below `_DECISIVE_START` + 2 return indices or with no return index closing outside the stub years, and `--as-of` refused before any read; arm A `_b4_limited(_b4_ensemble(fed))`, arm B `_b4_limited(<the mean of the three arms' b3_book_returns positions>)`, `fed = _ffill_btc(h4_prices)`, the three adopted arms `_B2_A2_ARMS` at `short="off"`, vol and basket lookback 180, 2,190 periods a year, each arm's book `b3_book_returns(fed, config=<its A2Config>, score_lookback=540, strength=0.5, floor=8)`; the tilt at a close spec 00147 D3's, its score `p[k] / p[k − 540] − 1`; every book costed by `_b4_net(positions, returns, stress=…)`, `returns = {a: _asset_returns(fed[a])}`, no carry; §10's limits through `_b4_limited`, one factor per bar.
- **The bars** (D7): trial 1's `_b3_metrics` at `n_trials=2` — every `a1_kill_bar` call `n_trials=2, var_trials=0.0, mean_block=<30 or 102>, seed=<42, 7 or 1234>, cost_stressed_returns=<×1.5 series>, regime_slices=calendar_year_slices(<series>, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000`, `bench = benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)`, the headline (30, 42); arm A's bar `_b4_arm_a_bar` at (30, 42); the head-to-heads `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)` at `first` 0 and at the tilt's first engagement, `tilt_first_engaged`, the first return index at which arm B's positions differ from arm A's (15,672); refused before any bar: fewer than 2 return indices from the first engagement.
- **The count** (D7): `_B3_SLOW_N_TRIALS = 2`, `required_n("B3")` as the spec measured it, fixed by the spec's hash; at `var_trials` 0.0 the DSR leg is the PSR against 0.
- **The rule** (D7): trial 1's `_b3_rank_tilt_verdict`, unchanged — `None` when `arm_a_passes` is 0 or `stamps_positions_differ` is 0, `reject` on a failed bar, `adopt` on `head_to_head_mean_outperf_primary > 0` with `head_to_head_spa_p_primary < 0.05`, `park` on the first with the p at or above 0.05, `reject` otherwise; the park row names no variant, the owner's sequence going on to trial 3.
- **The record** (D8): family `B3`; `n_trials_in_family` 2; variant `B3-tilt-slow-a2eq-full-v1`; iteration `iter-193`; seeds (42, 7, 1234); 44 metric keys, trial 1's; the block `ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69`; no `--verdict`.
- **The pre-flight read** (D9), in this order: (a) the block and `ohlc-full`'s vouched status (Task 2's `BLOCK` and `VOUCHED`); (b) arm A's seven anchors record 60's stored figures to the last digit — `arm_a_ann_sharpe_noc`, `arm_a_ann_sharpe_noc_decisive`, `arm_a_max_drawdown_full` against its `arm_a_max_drawdown`, `turnover_a`, `benchmark_ann_sharpe_noc`, `benchmark_ann_sharpe_noc_decisive`, and `arm_a_spot_drag_pct_yr` against `turnover_a / 27,337 × 0.006 × 2,190`; (c) the dead knob — `stamps_positions_differ` above 0, read before the engagement; (d) the engagement the measured basis's — Task 2's `ENGAGEMENT`; (e) arm A's `passes` 1.
- **The hash rule** (D9): before Task 3 step 2 takes the spec's sha256, nobody reads or computes trial 2's arm B returns or net-of-cost series, a head-to-head or a bar leg of it — by code, a program or arithmetic over a stored figure — nor runs `b3-tilt-slow` or `b3-tilt-slow-preflight` over the real set; weights, ranks, positions, exposures, limit engagement and turnover are allowed — what the data-gated test (Task 2) computes, and no return of a book. `a2_book_returns` and `b3_book_returns` compute each book's base returns, and from them its uncosted `net_returns` and `metrics`, internally on every call that sizes its positions; nothing reads them. Record 60's replay rebuilds trial 1's stored figures and reads no book on a 540-close score. No reader, reviewer or plan-review dispatch runs either new subject over the real set before the hash, and every read's dispatch carries this rule. No return of trial 2's arm B is computed over the real data before the trial's `--register` run, and the trial subject is never run as a plain eval; after it, only by its replay case in `tests/test_registry_replay.py`, wherever that case runs with the set linked.
- **Unchanged** (D8): every existing function and subject of `cli/research/subjects.py` — trial 1's and trial 58's machinery among them — `cli/alpha/*`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/risk/*`, `cli/costs/*`, `cli/validation/*` and `cli/engine/*`; record 60; any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-only $(git merge-base HEAD origin/develop) -- cli/` prints `cli/research/subjects.py` from Task 1 on, nothing else; from Task 1 on, `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@')" = 2` and `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@ -[0-9]*,0 ')" = 2` each exit 0 — two hunks, each a pure insertion, so a line changed or added anywhere but at Task 1 step 3's two sites is a third hunk or an impure one. Measured on the authoring tree: `@@ -4491,0 +4492,83 @@` and `@@ -4930,0 +5014,25 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00148-b3-tilt-slow-design.md` after Task 3 step 2, nor specs 00128, 00133, 00137, 00144 and 00147, nor the spec before then except a fix commit a read of Task 2 step 6 asks for; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Task 4 names it. Never `git stash`; no amend; never `--no-verify`; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-full`, a read-only link, never written under. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/`, a fleet host, docker, `kraken-cli`, the vault, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`. The trial, every test and every implementer step make no network call and no ssh connection; the controller's `git fetch origin develop` (Task 3 step 3, Task 4 step 1) and Task 6's `gh` calls, push and `merge-pr` are the exceptions. A data link is removed with `test -L <its absolute path> && unlink <its absolute path>`, never `rm`.
- **Research only**: nothing is armed, deployed, converged, pinned, rolled out or dropped — no fleet host, image, unit, alert rule or dashboard is touched, and no step of this plan waits on a maintenance window or a converge gap.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 2 step 6's reads, Tasks 3–4 and Task 6, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the data test, the pre-flight, the register, the replay), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1 and 5 and Task 2's steps 1–5.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00148 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00148/pt` (or a file, or `-k`): every `--basetemp` under `.tmp/plan-00148/` follows `mkdir -p .tmp/plan-00148 &&` in the same command, since pytest creates the base temp's leaf and never its parents. An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file, node id or `-k` selection into parts that cannot, each its own `--basetemp=.tmp/plan-00148/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `mkdir -p .tmp/plan-00148 && bash infra/scripts/consumers.sh --direct <each changed path> 2> .tmp/plan-00148/T.err | sort -u > .tmp/plan-00148/T.txt`, `.tmp/plan-00148/T.err` read before the list is used — never `2>/dev/null`, whose stderr is where a refusal speaks — and `test -s .tmp/plan-00148/T.txt && uv run pytest $(cat .tmp/plan-00148/T.txt) -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00148/pt`, so that an empty list fails closed and never becomes a bare `uv run pytest`; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. Every file a commit carries is staged by explicit path — the registry's line by `--register`, the ledger's by `--reading` or by a stop under `--register`, among them, whose one commit is Task 4 step 6's — since the commit and the probe setup's `git write-tree` read the index while the list reads the working tree. Every list holding `tests/test_research_command.py` runs it in four parts, each one plain blocking call under `-m "not slow and not data"`, `timeout` 600000 ms, so that none can pass 600 s: `tests/test_research_command.py -k "not reentry and not b2"` (`--basetemp=.tmp/plan-00148/pt-1`, measured on Task 1's tree in the scratch worktree, `544 passed, 418 deselected in 231.17s`), `tests/test_research_command.py -k "b2 and not reentry"` (`pt-2`, measured `227 passed, 735 deselected in 311.45s`), `tests/test_research_command.py -k reentry` (`pt-3`, measured `71 passed, 891 deselected in 89.26s`) and the rest of the list, read off `.tmp/plan-00148/T.txt` with that file's line left out (`pt-4`). Every commit message carries the result line of each test command its gate ran, a run over that commit's own tree, and the two trailer lines exactly as the executing session's attribution gives them — `Co-Authored-By:` naming the model that ran the step, and `Claude-Session:`.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
mkdir -p .tmp/plan-00148 &&
  test ! -e .tmp/plan-00148/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00148/probe HEAD &&
  git -C .tmp/plan-00148/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00148/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00148/probe/.tmp
```

  Then, from `.tmp/plan-00148/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, so it fails at import or at its call. A mutation whose text also stands in an existing function — trial 1's ensemble, inputs and build share most of their lines with the new ones — carries the address of its own function's range, `/^def <name>(/,/^def /`, or of its entry's, `/"<subject>": Subject(/,/^    ),/`, so its dry run changes one line; a pattern that holds `'` writes it as `.`. After the last verdict, `git worktree remove --force .tmp/plan-00148/probe` — each data link in it unlinked first with `test -L <its absolute path> && unlink <its absolute path>`, each removal of one that held a link followed by `ls -la /home/zhaow/Projects/zcrypto-kraken/data`, `ohlc-full` still listed. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <the hash the setup printed>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.
- **The subjects' names** (D8): `b3-tilt-slow` and `b3-tilt-slow-preflight`, which no registered or retired subject's name equals or opens with a hyphen, and which open none (the spec's basis). Every new test function in `tests/test_research_command.py` carries `b3_slow` in its name, which no hyphenated id and no other test's name there carries, so `-k b3_slow` selects them alone; the rows trial 1's functions gain and the shared rows the two subjects add carry the hyphenated `b3-tilt-slow` in their ids.

## Task 1: the trial subject and its pre-flight twin in `cli/research/subjects.py` (D2–D8)

**Files:** Modify `cli/research/subjects.py`, `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`.

**Interfaces:** Consumes `cli/research/subjects.py`'s `_B3Inputs`, `_b3_reads`, `_b3_metrics`, `_b3_preflight_metrics`, `_b3_rank_tilt_verdict`, `_B3_STRENGTH`, `_B3_FLOOR`, `_B3_METRIC_KEYS`, `_B3_PREFLIGHT_KEYS`, `b3_book_returns`, `_b4_ensemble`, `_b4_limited`, `_ffill_btc`, `_asset_returns`, `close_grid`, `A2Config`, `_B2_A2_ARMS`, `_B2_LOOKBACK`, `PPY_4H`, `_b2_over`, `_ASSETS`, `Subject`, `SubjectError`, `ObservedReader` and the error classes it imports, each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; in the tests, trial 1's `_B3_NO_VERDICT`, `_B3_METRIC_KEYS`, `_B3_PREFLIGHT_KEYS`, `_B3_ADOPTING` and `_b3_own_books`, and `_b2_dataset`, `_B2_START`, `_B2_ASSETS`, `_recording`, `_anchor`, `_as_trial`, `_rolling_set`, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `_CONTRACT_DATASETS`, `runner` and `app`. Produces the two subjects, `_b3_slow_inputs` and `_B3_SLOW_N_TRIALS`, which Task 2's test and Task 4's literal read.

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - `test_each_subject_declares_the_metric_keys_its_build_returns` gains, after its `assert subjects.SUBJECTS["b3-rank-tilt-preflight"].metric_keys == _B3_PREFLIGHT_KEYS` line:

```python
    assert subjects.SUBJECTS["b3-tilt-slow"].metric_keys == _B3_METRIC_KEYS
    assert subjects.SUBJECTS["b3-tilt-slow-preflight"].metric_keys == _B3_PREFLIGHT_KEYS
```

  - the `name` parametrization of `test_the_b3_rule_maps_its_metrics_to_a_verdict_or_a_stop`, `@pytest.mark.parametrize("name", ["b3-rank-tilt"])` directly above its `("change", "verdict")` parametrization, becomes `@pytest.mark.parametrize("name", ["b3-rank-tilt", "b3-tilt-slow"])`; the one of `test_a_b3_subject_refuses_as_of_before_any_read`, `@pytest.mark.parametrize("name", ["b3-rank-tilt", "b3-rank-tilt-preflight"])`, becomes `@pytest.mark.parametrize("name", ["b3-rank-tilt", "b3-rank-tilt-preflight", "b3-tilt-slow", "b3-tilt-slow-preflight"])`;
  - `_b3_own_books`' signature `def _b3_own_books(h4_ts: list[datetime], h4_prices: dict) -> dict:` becomes `def _b3_own_books(h4_ts: list[datetime], h4_prices: dict, *, score_lookback: int = 180) -> dict:`, and its line `    tilted = [b3_book_returns(fed, config=c, score_lookback=180, strength=0.5, floor=8) for c in configs]` becomes `    tilted = [b3_book_returns(fed, config=c, score_lookback=score_lookback, strength=0.5, floor=8) for c in configs]`;
  - after `test_the_b3_trial_refuses_a_plain_eval_and_another_count_before_any_read` and before `def _ruled_signal(`, two blank lines either side:

```python
_B3_SLOW_SPEC = "docs/specs/00148-b3-tilt-slow-design.md"


@pytest.mark.parametrize("name", ["b3-tilt-slow"])
def test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score(name):
    trial, preflight = subjects.SUBJECTS[name], subjects.SUBJECTS[f"{name}-preflight"]
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        name,
        (240,),
        _B2_ASSETS,
        _B3_SLOW_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is subjects._build_b3_tilt_slow and trial.metric_keys == _B3_METRIC_KEYS
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b3_rank_tilt_verdict, _B3_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B3", 2) == ("B3", subjects._B3_SLOW_N_TRIALS)
    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        f"{name}-preflight",
        (240,),
        _B2_ASSETS,
        _B3_SLOW_SPEC,
        (42,),
    )
    assert preflight.build is subjects._build_b3_tilt_slow_preflight and preflight.metric_keys == _B3_PREFLIGHT_KEYS
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5
    assert (subjects._B3_SLOW_SCORE_LOOKBACK, subjects._B3_STRENGTH, subjects._B3_FLOOR) == (540, 0.5, 8)


@pytest.mark.parametrize(
    ("name", "compute"), [("b3-tilt-slow", "_b3_metrics"), ("b3-tilt-slow-preflight", "_b3_preflight_metrics")]
)
def test_a_b3_slow_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count(monkeypatch, name, compute):
    reader, window, reads, inputs = object(), ("2021-01-01", "2025-12-31"), object(), object()
    calls = []

    def read(*args, **kwargs):
        calls.append(("_b3_reads", args, kwargs))
        return reads

    def build(*args, **kwargs):
        calls.append(("_b3_slow_inputs", args, kwargs))
        return inputs

    def computed(*args, **kwargs):
        calls.append((compute, args, kwargs))
        return {"built": name}

    monkeypatch.setattr(subjects, "_b3_reads", read)
    monkeypatch.setattr(subjects, "_b3_slow_inputs", build)
    monkeypatch.setattr(subjects, compute, computed)

    built = subjects.SUBJECTS[name].build(reader, "ohlc-test", window, None, True)

    assert built == {"built": name}
    assert calls == [
        ("_b3_reads", (name, reader, "ohlc-test", window, True), {}),
        ("_b3_slow_inputs", (reads,), {}),
        (compute, (inputs,), {"n_trials": 2}),
    ]


def _b3_slow_short_reads(n: int = 640) -> tuple[list[datetime], dict]:
    """A 640-stamp union of the ten assets, BTC missing one stamp, DOT listing at 20, SOL at 250 and AVAX at 330: on a
    540-close score the basket holds exactly 7 from return index 540 to 559 and 8 from 560, where the tilt first moves a
    position."""
    h4_ts = [datetime(2017, 1, 1, tzinfo=UTC) + timedelta(hours=4 * k) for k in range(n)]
    h4_prices = {
        a: [
            10.0 * (i + 1) * (1 + 0.0004 * (i % 4 + 1)) ** k * (1 + (0.04 + 0.01 * (i % 5)) * math.sin(k / (5 + i) + 0.7 * i))
            for k in range(n)
        ]
        for i, a in enumerate(_B2_ASSETS)
    }
    h4_prices["BTC"][600] = None
    h4_prices["DOT"][:20] = [None] * 20
    h4_prices["SOL"][:250] = [None] * 250
    h4_prices["AVAX"][:330] = [None] * 330
    return h4_ts, h4_prices


@pytest.mark.parametrize("name", ["b3-tilt-slow"])
def test_the_b3_slow_arms_agree_bit_for_bit_until_the_tilt_first_moves_a_position(monkeypatch, name):
    reads = _b3_slow_short_reads()
    n = len(reads[0]) - 1
    untilted = _recording(monkeypatch, "_b4_ensemble", lambda arguments, result: result)
    tilted = _recording(monkeypatch, "_b3_slow_ensemble", lambda arguments, result: result)

    inputs = subjects._b3_slow_inputs(reads)

    ((_, raw_a),), ((_, (raw_b, _, longs)),) = untilted, tilted
    differ = [k for k in range(n) if any(raw_b[a][k] != raw_a[a][k] for a in raw_a)]
    first_tilted = min(next(k for k, c in enumerate(counts) if c) for counts in longs.values())
    assert differ and first_tilted <= differ[0] == subjects._b3_first_engaged(inputs) == 560 < n - 2
    assert all(raw_b[a][:first_tilted] == raw_a[a][:first_tilted] for a in raw_a)
    assert all(sizes == [0] * 540 + [7] * 20 + [8] * (n - 560) for sizes in inputs.ranked.values())


@pytest.mark.parametrize("name", ["b3-tilt-slow"])
def test_the_b3_slow_inputs_build_arm_a_untilted_and_arm_b_tilted_on_the_540_close_score_each_through_the_limits(name):
    reads = _b3_slow_short_reads()
    own = _b3_own_books(*reads, score_lookback=540)
    # Non-vacuity: the fixture tilts every arm, so the equalities below compare moved books.
    assert all(max(counts) >= 2 for counts in own["tilted"].values()) and own["limited_b"][0] != own["limited_a"][0]

    inputs = subjects._b3_slow_inputs(reads)

    assert (inputs.h4_ts, inputs.h4_prices, inputs.close) == (reads[0], reads[1], [t + timedelta(hours=4) for t in reads[0][:-1]])
    assert inputs.returns == own["returns"] and (inputs.ranked, inputs.tilted) == (own["ranked"], own["tilted"])
    assert (inputs.arm_a, inputs.engaged_a) == own["limited_a"] and (inputs.arm_b, inputs.engaged_b) == own["limited_b"]


@pytest.mark.parametrize("name", ["b3-tilt-slow"])
def test_the_b3_slow_inputs_pass_both_arms_through_the_limits(monkeypatch, name):
    reads = _b3_slow_short_reads()
    untilted = _recording(monkeypatch, "_b4_ensemble", lambda arguments, result: result)
    tilted = _recording(monkeypatch, "_b3_slow_ensemble", lambda arguments, result: result)
    # A factor below 1 at every bar, so a book the limits never scale keeps its raw positions and fails the comparison.
    _recording(monkeypatch, "limit_factors", lambda arguments, result: ([0.5] * len(result[0]), result[1]))

    inputs = subjects._b3_slow_inputs(reads)

    ((_, raw_a),), ((_, (raw_b, _, _)),) = untilted, tilted
    halved = [{i: [p * 0.5 for p in v] for i, v in book.items()} for book in (raw_a, raw_b)]
    assert [inputs.arm_a, inputs.arm_b] == halved


@pytest.mark.parametrize("name", ["b3-tilt-slow"])
@pytest.mark.parametrize("plain", [True, False], ids=["plain-eval", "another-count"])
def test_the_b3_slow_trial_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, name, plain):
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    flags = [] if plain else ["--register", "--iteration", "iter-193", "--family", "B3", "--n-trials", "1"]
    refused = (
        f"{name} declares a verdict rule, so every run of it is a trial: run it with --register"
        if plain
        else f"--n-trials 1 is not 2, the count {name} declares and deflates at: pass --n-trials 2"
    )

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output
```

  - `_RULED_FIXTURES` gains `"b3-tilt-slow": _b2_dataset,` after `"b3-rank-tilt": _b2_dataset,`; `_DECLARED_COUNT` gains `"b3-tilt-slow": "_B3_SLOW_N_TRIALS",` after `"b3-rank-tilt": "_B3_N_TRIALS",`; the literal of `test_the_ruled_subjects_declare_their_families_and_trial_counts` gains `"b3-tilt-slow": ("B3", 2),` after `"b3-rank-tilt": ("B3", 1),`; `_CONTRACT_DATASETS` gains, after its `"b3-rank-tilt-preflight"` entry:

```python
    "b3-tilt-slow": lambda tmp_path, subject: (_b2_dataset(tmp_path), _B2_START),
    "b3-tilt-slow-preflight": lambda tmp_path, subject: (_b2_dataset(tmp_path), _B2_START),
```

  **Author's call** — trial 1's guards where the code is trial 1's, new ones where it is not, every new case in seconds so each is a probe's target: the rule and the `--as-of` refusal read the subject by name through `SUBJECTS` and the command, so trial 1's two functions take the new names as rows — the rule is trial 1's own function, its rows `_B3_ADOPTING`'s, and the `--as-of` rows reach `_b3_slow_build`'s own check; the declaration, its spec, seeds, keys, rule, `no_verdict`, family, count and `M`, `k` and the floor; the builders on stand-ins for trial 1's reads, the new inputs and trial 1's computes, so the subject name each passes, its arguments in order, the inputs half it builds and the compute and count it calls are each seen; the books on `_b3_slow_short_reads`, a 640-stamp union of the ten assets the reads would refuse, BTC missing one stamp, DOT listing at 20, SOL at 250 and AVAX at 330, so that on a 540-close score the basket holds exactly 7 from return index 540 to 559 and 8 from 560 to the end — a floor read off 7 or 9 starts the tilt elsewhere or never — and on trial 1's 180-close score the tilt would first move a position at 200, so a book on the wrong score window is seen (measured on the fixture through `_b3_slow_inputs` and `_b3_inputs`: first engagement 560 and 200, 79 and 439 closes moved); the bit-identity read off the two ensembles the inputs build, the first engagement at 560 and the basket's sizes held there, and every field of `_b3_slow_inputs` held to `_b3_own_books` at `score_lookback=540`, the test's own build through `a2_book_returns`, `b3_book_returns` and `limit_factors`, never the subject's halves — the helper gains the keyword at trial 1's value, so trial 1's call reads as it did; the limits' wiring with the factor rewritten at every bar; the plain eval and the count refused before any read, the refusal's text alone holding it — the root holds no data, so a refusal moved past the dataset's check would print that check's refusal in place of its own. The metrics, the pre-flight's metrics, the engagement, the reads and the first engagement are trial 1's functions, guarded by trial 1's cases on `_b3_built_inputs`, `_b4_dataset` and `_b2_dataset`, which these subjects call unchanged. Every new function is parametrised by the subject's name, so `tests/retired_subjects.py`'s hook marks each case `retired` once B3's closing branch retires the names. The shared rows — the contract, tracked-spec, shared-defaults and deflation rows, which `_RULED_FIXTURES`, `_DECLARED_COUNT` and `_CONTRACT_DATASETS` reach — run both subjects end to end on `_b2_dataset`, the trial's arm B and bars among them.
- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00148 && uv run pytest tests/test_research_command.py -k "b3_slow or ruled_subjects_declare or declares_the_metric_keys or (b3_rule and b3-tilt-slow) or (b3_subject_refuses_as_of and b3-tilt-slow)" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00148/pt`: collection completes and every selected case fails at its call — on a key `SUBJECTS` lacks, a name `subjects` lacks or a subject the CLI does not know (measured on the base module: `22 failed, 922 deselected`).
- [ ] **Step 3: Implement in `cli/research/subjects.py`** — after `_B3_PREFLIGHT_KEYS`' closing `)` and before `SUBJECTS: dict[str, Subject] = {`, two blank lines on each side:

```python
# docs/specs/00148 D2-D8: B3's trial 2, trial 1's tilt on a 540-close momentum score, its strength and floor trial 1's:
# trial 1's reads, metrics, engagement and rule, trial 58's arm A, limits, costing and bar.
_B3_SLOW_SCORE_LOOKBACK = 540  # docs/specs/00148 D3: M, 90 days of 4h closes; another value is a new trial
_B3_SLOW_N_TRIALS = 2  # docs/specs/00148 D7: B3's true count with this trial, fixed by the spec's hash; another is a new subject


def _b3_slow_ensemble(
    prices: dict[str, list[float | None]],
) -> tuple[dict[str, list[float]], dict[str, list[int]], dict[str, list[int]]]:
    """`_b3_ensemble` on the 540-close score."""
    books = {
        f"{'-'.join(map(str, lookbacks))}@{target_vol}": b3_book_returns(
            prices,
            config=A2Config(
                lookbacks=lookbacks,
                short="off",
                target_vol=target_vol,
                vol_lookback=_B2_LOOKBACK,
                basket_lookback=_B2_LOOKBACK,
                periods_per_year=PPY_4H,
            ),
            score_lookback=_B3_SLOW_SCORE_LOOKBACK,
            strength=_B3_STRENGTH,
            floor=_B3_FLOOR,
        )
        for lookbacks, target_vol in _B2_A2_ARMS
    }
    arms = [book["asset_positions"] for book in books.values()]
    positions = {i: [statistics.mean(arm[i][k] for arm in arms) for k in range(len(prices["BTC"]) - 1)] for i in prices}
    return positions, {arm: book["ranked"] for arm, book in books.items()}, {arm: book["tilted"] for arm, book in books.items()}


def _b3_slow_inputs(reads: tuple[list[datetime], dict[str, list[float | None]]]) -> _B3Inputs:
    """`_b3_inputs` with arm B on the 540-close score: both arms' positions and the returns, and no return of a book."""
    h4_ts, h4_prices = reads
    fed = _ffill_btc(h4_prices)
    arm_a, engaged_a = _b4_limited(_b4_ensemble(fed))
    raw_b, ranked, tilted = _b3_slow_ensemble(fed)
    arm_b, engaged_b = _b4_limited(raw_b)
    returns = {a: _asset_returns(fed[a]) for a in h4_prices}
    return _B3Inputs(h4_ts, h4_prices, close_grid(h4_ts), returns, arm_a, arm_b, engaged_a, engaged_b, ranked, tilted)


def _b3_slow_build(
    subject: str,
    compute: Callable[..., dict],
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
        return compute(_b3_slow_inputs(_b3_reads(subject, reader, dataset, window, accept_holes)), n_trials=_B3_SLOW_N_TRIALS)
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, RiskError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


def _build_b3_tilt_slow(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b3_slow_build("b3-tilt-slow", _b3_metrics, reader, dataset, window, as_of, accept_holes)


def _build_b3_tilt_slow_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b3_slow_build("b3-tilt-slow-preflight", _b3_preflight_metrics, reader, dataset, window, as_of, accept_holes)
```

  `SUBJECTS` gains, after its `"b3-rank-tilt-preflight"` entry and before its closing `}`:

```python
    "b3-tilt-slow": Subject(
        "b3-tilt-slow",
        (240,),
        _ASSETS,
        _build_b3_tilt_slow,
        spec="docs/specs/00148-b3-tilt-slow-design.md",
        metric_keys=_B3_METRIC_KEYS,
        seeds=(42, 7, 1234),
        verdict=_b3_rank_tilt_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the tilt moves no position at any stamp; no "
            "verdict, the trial unspent"
        ),
        family="B3",
        n_trials=_B3_SLOW_N_TRIALS,
    ),
    "b3-tilt-slow-preflight": Subject(
        "b3-tilt-slow-preflight",
        (240,),
        _ASSETS,
        _build_b3_tilt_slow_preflight,
        spec="docs/specs/00148-b3-tilt-slow-design.md",
        metric_keys=_B3_PREFLIGHT_KEYS,
        seeds=(42,),
    ),
```

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row: `` ) or `b3-rank-tilt-preflight` ( `` becomes `` ), `b3-rank-tilt-preflight` ( ``, and the row's closing `` with no return of the tilted book; it has no rule, so its run is kept with `--reading`). | `` becomes:

```markdown
with no return of the tilted book; it has no rule, so its run is kept with `--reading`), `b3-tilt-slow` (`b3-rank-tilt`'s comparison with the rank taken on the trailing 90-day return in place of the 30-day one, among the weighted assets holding one, the tilt's strength and its 8-asset floor unchanged; the 4h series of `--dataset`, a frozen set only) or `b3-tilt-slow-preflight` (that comparison's instrument check, the figures `b3-rank-tilt-preflight` reads; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: `tests/slow-cases.txt`** — gains at their `sorted()` places the shared rows measured at 10 s or more on the authoring tree (call time: the shared-defaults rows 34.53 s and 29.01 s, the evaluate rows 17.40 s and 14.74 s, the deflation row 14.85 s):

```text
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b3-tilt-slow]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b3-tilt-slow-evaluates]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b3-tilt-slow-preflight-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b3-tilt-slow-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b3-tilt-slow]
```

  A case that times at 10 s or more on the implementer's own run and is not listed joins the list; a listed one under 10 s stays (`tests/test_slow_cases.py` passes).
- [ ] **Step 6: Run them to verify they pass** — step 2's command, measured `22 passed, 940 deselected` (about 13 s; the new inputs cases 6.05 s, 3.11 s and 3.02 s, every other under 1 s); then the shared rows, `mkdir -p .tmp/plan-00148 && uv run pytest tests/test_research_command.py -k "b3-tilt-slow and not b3_" -m "not data" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00148/pt`, one plain blocking call, `timeout` 600000 ms (measured `19 passed, 943 deselected in 113.59s`, every row but the five step 5 lists under 1 s).
- [ ] **Step 7: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the Global Constraints' list over the four paths in its four parts (measured on Task 1's tree in the scratch worktree: `544 passed, 418 deselected in 231.17s`, `227 passed, 735 deselected in 311.45s`, `71 passed, 891 deselected in 89.26s`; the other forty direct readers `4138 passed, 70 deselected in 124.14s`); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 8: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured in the scratch worktree on Task 1's tree, 39 of 39); the metric-keys lines, the ruled-subjects literal, the rule's ten new rows — trial 1's function on trial 1's rows, whose guard is trial 1's probe block and this subject's declaration of it — and the contract, shared-defaults, deflation and tracked-spec rows are new rows of existing tests, not new guards, and are not probed; the two `--as-of` rows, new rows of an existing test, reach `_b3_slow_build`'s own check and are probed (rows 22–23):

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation 's/^_B3_SLOW_N_TRIALS = 2\b/_B3_SLOW_N_TRIALS = 3/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation 's/^_B3_SLOW_SCORE_LOOKBACK = 540 /_B3_SLOW_SCORE_LOOKBACK = 180 /' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation '/"b3-tilt-slow": Subject(/,/^    ),/s/00148-b3-tilt-slow-design/00147-b3-rank-tilt-design/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation '/"b3-tilt-slow-preflight": Subject(/,/^    ),/s/00148-b3-tilt-slow-design/00147-b3-rank-tilt-design/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation '/"b3-tilt-slow": Subject(/,/^    ),/s/seeds=(42, 7, 1234),/seeds=(42,),/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation '/"b3-tilt-slow": Subject(/,/^    ),/s/verdict=_b3_rank_tilt_verdict,/verdict=_b4_ratio_legs_verdict,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation '/"b3-tilt-slow": Subject(/,/^    ),/s/family="B3",/family="B4",/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation '/"b3-tilt-slow": Subject(/,/^    ),/s/metric_keys=_B3_METRIC_KEYS,/metric_keys=_B3_PREFLIGHT_KEYS,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation '/"b3-tilt-slow-preflight": Subject(/,/^    ),/s/metric_keys=_B3_PREFLIGHT_KEYS,/metric_keys=_B3_METRIC_KEYS,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation '/"b3-tilt-slow": Subject(/,/^    ),/s/^        _build_b3_tilt_slow,$/        _build_b3_rank_tilt,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation '/"b3-tilt-slow-preflight": Subject(/,/^    ),/s/^        _build_b3_tilt_slow_preflight,$/        _build_b3_rank_tilt_preflight,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation '/"b3-tilt-slow": Subject(/,/^    ),/s/the tilt moves no position at any stamp; no /the tilt moves no position; no /' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_pair_declares_trial_1s_keys_seeds_and_rule_its_own_spec_and_count_and_the_540_close_score[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_build(/def _b3_slow_build_gone(/' --mutation 's/return _b3_slow_build("b3-tilt-slow", _b3_metrics,/return _b3_slow_build("b3-rank-tilt", _b3_metrics,/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_slow_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-tilt-slow-_b3_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_build(/def _b3_slow_build_gone(/' --mutation 's/return _b3_slow_build("b3-tilt-slow", _b3_metrics,/return _b3_slow_build("b3-tilt-slow", _b3_preflight_metrics,/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_slow_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-tilt-slow-_b3_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_build(/def _b3_slow_build_gone(/' --mutation 's/return _b3_slow_build("b3-tilt-slow-preflight", _b3_preflight_metrics,/return _b3_slow_build("b3-tilt-slow", _b3_preflight_metrics,/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_slow_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-tilt-slow-preflight-_b3_preflight_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_build(/def _b3_slow_build_gone(/' --mutation 's/return _b3_slow_build("b3-tilt-slow-preflight", _b3_preflight_metrics,/return _b3_slow_build("b3-tilt-slow-preflight", _b3_metrics,/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_slow_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-tilt-slow-preflight-_b3_preflight_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_build(/def _b3_slow_build_gone(/' --mutation 's/, n_trials=_B3_SLOW_N_TRIALS)$/, n_trials=_B3_N_TRIALS)/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_slow_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-tilt-slow-_b3_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_build(/def _b3_slow_build_gone(/' --mutation 's/, n_trials=_B3_SLOW_N_TRIALS)$/, n_trials=_B3_N_TRIALS)/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_slow_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-tilt-slow-preflight-_b3_preflight_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_build(/def _b3_slow_build_gone(/' --mutation 's/return compute(_b3_slow_inputs(_b3_reads(/return compute(_b3_inputs(_b3_reads(/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_slow_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-tilt-slow-_b3_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_build(/def _b3_slow_build_gone(/' --mutation 's/_b3_reads(subject, reader, dataset, window, accept_holes)), n_trials=_B3_SLOW_N_TRIALS)/_b3_reads(subject, reader, dataset, window, False)), n_trials=_B3_SLOW_N_TRIALS)/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_slow_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-tilt-slow-_b3_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_build(/def _b3_slow_build_gone(/' --mutation 's/_b3_reads(subject, reader, dataset, window, accept_holes)), n_trials=_B3_SLOW_N_TRIALS)/_b3_reads(subject, reader, dataset, None, accept_holes)), n_trials=_B3_SLOW_N_TRIALS)/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_slow_subject_reads_through_trial_1s_reads_builds_its_own_inputs_and_computes_at_its_count[b3-tilt-slow-_b3_metrics]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_build(/def _b3_slow_build_gone(/' --mutation '/^def _b3_slow_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_subject_refuses_as_of_before_any_read[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_build(/def _b3_slow_build_gone(/' --mutation '/^def _b3_slow_build(/,/^def /s/    if as_of is not None:/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_a_b3_subject_refuses_as_of_before_any_read[b3-tilt-slow-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_inputs(/def _b3_slow_inputs_gone(/' --mutation '/^def _b3_slow_inputs(/,/^def /s/    arm_a, engaged_a = _b4_limited(_b4_ensemble(fed))/    arm_a, engaged_a = _b4_limited(_b3_slow_ensemble(fed)[0])/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_arms_agree_bit_for_bit_until_the_tilt_first_moves_a_position[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_inputs(/def _b3_slow_inputs_gone(/' --mutation '/^def _b3_slow_inputs(/,/^def /s/    fed = _ffill_btc(h4_prices)/    fed = dict(h4_prices)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_build_arm_a_untilted_and_arm_b_tilted_on_the_540_close_score_each_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_inputs(/def _b3_slow_inputs_gone(/' --mutation '/^def _b3_slow_inputs(/,/^def /s/    returns = {a: _asset_returns(fed\[a\]) for a in h4_prices}/    returns = {a: _asset_returns(h4_prices[a]) for a in h4_prices}/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_build_arm_a_untilted_and_arm_b_tilted_on_the_540_close_score_each_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_inputs(/def _b3_slow_inputs_gone(/' --mutation '/^def _b3_slow_inputs(/,/^def /s/    raw_b, ranked, tilted = _b3_slow_ensemble(fed)/    raw_b, ranked, tilted = _b3_ensemble(fed)/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_build_arm_a_untilted_and_arm_b_tilted_on_the_540_close_score_each_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_ensemble(/def _b3_slow_ensemble_gone(/' --mutation 's/^            score_lookback=_B3_SLOW_SCORE_LOOKBACK,/            score_lookback=_B3_SCORE_LOOKBACK,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_build_arm_a_untilted_and_arm_b_tilted_on_the_540_close_score_each_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_ensemble(/def _b3_slow_ensemble_gone(/' --mutation '/^def _b3_slow_ensemble(/,/^def /s/^            strength=_B3_STRENGTH,/            strength=0.25,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_build_arm_a_untilted_and_arm_b_tilted_on_the_540_close_score_each_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_ensemble(/def _b3_slow_ensemble_gone(/' --mutation '/^def _b3_slow_ensemble(/,/^def /s/^            floor=_B3_FLOOR,/            floor=9,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_build_arm_a_untilted_and_arm_b_tilted_on_the_540_close_score_each_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_ensemble(/def _b3_slow_ensemble_gone(/' --mutation '/^def _b3_slow_ensemble(/,/^def /s/^            floor=_B3_FLOOR,/            floor=7,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_build_arm_a_untilted_and_arm_b_tilted_on_the_540_close_score_each_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_ensemble(/def _b3_slow_ensemble_gone(/' --mutation '/^def _b3_slow_ensemble(/,/^def /s/statistics\.mean(arm\[i\]\[k\] for arm in arms) for k/statistics.mean(arm[i][k] for arm in arms[:2]) for k/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_build_arm_a_untilted_and_arm_b_tilted_on_the_540_close_score_each_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_ensemble(/def _b3_slow_ensemble_gone(/' --mutation '/^def _b3_slow_ensemble(/,/^def /s/^        f"{.-.\.join(map(str, lookbacks))}@{target_vol}": b3_book_returns(/        f"{lookbacks}": b3_book_returns(/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_build_arm_a_untilted_and_arm_b_tilted_on_the_540_close_score_each_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_ensemble(/def _b3_slow_ensemble_gone(/' --mutation '/^def _b3_slow_ensemble(/,/^def /s/{arm: book\["tilted"\] for arm, book in books\.items()}/{arm: book["ranked"] for arm, book in books.items()}/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_build_arm_a_untilted_and_arm_b_tilted_on_the_540_close_score_each_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_ensemble(/def _b3_slow_ensemble_gone(/' --mutation '/^def _b3_slow_ensemble(/,/^def /s/                basket_lookback=_B2_LOOKBACK,/                basket_lookback=120,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_build_arm_a_untilted_and_arm_b_tilted_on_the_540_close_score_each_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_inputs(/def _b3_slow_inputs_gone(/' --mutation '/^def _b3_slow_inputs(/,/^def /s/^    arm_b, engaged_b = _b4_limited(raw_b)$/    arm_b, engaged_b = raw_b, _b4_limited(raw_b)[1]/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_pass_both_arms_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b3_slow_inputs(/def _b3_slow_inputs_gone(/' --mutation '/^def _b3_slow_inputs(/,/^def /s/^    arm_a, engaged_a = _b4_limited(_b4_ensemble(fed))$/    arm_a, engaged_a = _b4_ensemble(fed), _b4_limited(_b4_ensemble(fed))[1]/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_inputs_pass_both_arms_through_the_limits[b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation '/"b3-tilt-slow": Subject(/,/^    ),/s/verdict=_b3_rank_tilt_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation '/"b3-tilt-slow": Subject(/,/^    ),/s/n_trials=_B3_SLOW_N_TRIALS,/n_trials=1,/' -- uv run pytest 'tests/test_research_command.py::test_the_b3_slow_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b3-tilt-slow]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  Each row moves one clause D3, D7 and D8 give the new code. The declaration: the count, `M`'s literal, each subject's spec, the seeds, the rule, the family, each subject's keys, each builder and the `no_verdict` text (rows 1–12). The builders: each passing its own subject's name and its own compute, the count each passes, the inputs half the build calls, and the window and the holes flag reaching the reads (rows 13–21). The `--as-of` refusal on both subjects (rows 22–23). The inputs: arm A untilted (row 24), the BTC fill, the assets' returns on the filled BTC, the ensemble the inputs call, the score window, the strength, the floor from each side, the arms' mean, the arms' keys, the tilted counts and the basket lookback (rows 25–35), and both arms through the limits (rows 36–37). The plain eval and the count (rows 38–39). **Author's call — the clauses no row moves.** Of `_b3_slow_ensemble`'s six `A2Config` clauses, `basket_lookback` takes row 35; `lookbacks` and `short` move the fixture's positions, so the case rows 25–35 target fails on either moved and they take no row; `vol_lookback`, `target_vol` and `periods_per_year` take none: the fixture's vol target sits at its leverage cap, so moving the vol lookback (to 120) or raising the per-period target (`target_vol` 0.12 at every arm, `periods_per_year` 365) moves no position on it, while lowering the target (`target_vol` halved, `periods_per_year` 8,760) moves positions that case sees (each measured with the line moved inside `_b3_slow_ensemble`, on the fixture); the three lines are trial 1's, and Task 2's data-gated case, whose turnover and engagement the measured basis built at a vol lookback of 180, each arm's own target vol and 2,190 periods a year, holds them on the real set. `_b3_slow_build`'s compute-error clause, D8's `SubjectError` naming the subject and its window, takes none either: the contract rows' spoilt fixtures raise through it — an `AlphaError` or a `FeatureError` from the inputs half — but their check, `<name> over the full history`, holds as well against the command's own refusal of an evaluation error (measured on the zero-close fixture with the clause narrowed), so no case fails with the clause dropped or narrowed; either way the run exits 1, an open attempt ending failed and counting 0, and Task 4 steps 2 and 4 quote the line into T0016.
- [ ] **Step 9: Commit** — `feat(research): B3 trial 2's subjects — trial 1's rank tilt of the A2 ensemble's long weights on a 540-close momentum score and its pre-flight twin, on a frozen set's full history`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 2: the data-gated basis test, the decisions-log entries before the hash, the reads (D1, D9)

**Files:** Create `tests/test_research_b3_tilt_slow_basis.py` (module-marked `data`); modify `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 5's own commit.

**Interfaces:** Consumes Task 1's `_b3_slow_inputs` and trial 1's `_b3_reads` and `_b3_engagement`; `cli.alpha.b1.book_turnover`; `cli.registry.observed.ObservedReader`, `cli.registry.record.compute_hash` and `cli.research.command._DATA_ROOT`; `tests.skip_gates.nothing_found_under`; `tests.test_trial_registry_provenance._trials`. Produces one test, its own `trial_inputs()`, and the module names `BLOCK`, `VOUCHED`, `RETURN_INDICES` and `ENGAGEMENT` (with `HISTOGRAM` inside it), which Task 3's check programs import. No test computes a return of a book.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis, records 58's and 60's figures read off the committed records:

```python
"""B3 trial 2's inputs half against spec 00148's measured basis: positions, the ranked basket, the tilted closes, the
limits and turnover, and no return of a book."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _trials

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_YEARS = dict.fromkeys(map(str, range(2013, 2027)), 0)
_SHORT = "20-50-100@0.12"
_LONG = ("60-120-240@0.1", "60-120-240@0.12")
# Copied from the spec's measured basis, never from a run.
BLOCK = "ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69"
VOUCHED = {"ohlc-full": "checked (36 vouched hashes)"}
RETURN_INDICES = 27_337
_ARMS = (_SHORT, *_LONG)
# The basket is the same at every arm: its weights and scores read no direction.
HISTOGRAM = dict.fromkeys(
    _ARMS,
    {
        "0": 540,
        "1": 4_124,
        "2": 3_062,
        "3": 1_098,
        "4": 2_790,
        "5": 2_596,
        "6": 1_401,
        "7": 249,
        "8": 1_714,
        "9": 1_303,
        "10": 8_460,
    },
)
ENGAGEMENT = {
    "tilt_first_engaged": 15_672,
    "primary_returns": 11_665,
    "stamps_positions_differ": 9_687,
    "positions_differ_per_year": _YEARS
    | {"2020": 171, "2021": 1_904, "2022": 1_762, "2023": 1_940, "2024": 1_805, "2025": 1_717, "2026": 388},
    "tilted_per_year": {
        _SHORT: _YEARS | {"2020": 144, "2021": 1_597, "2022": 1_286, "2023": 1_634, "2024": 1_415, "2025": 1_343, "2026": 315},
        **dict.fromkeys(
            _LONG, _YEARS | {"2020": 170, "2021": 1_684, "2022": 1_215, "2023": 1_661, "2024": 1_444, "2025": 1_304, "2026": 342}
        ),
    },
    "ranked_assets_histogram": HISTOGRAM,
    "ranked_assets_mean": {
        arm: math.fsum(int(m) * c for m, c in counts.items()) / RETURN_INDICES for arm, counts in HISTOGRAM.items()
    },
    "turnover_b": 171.84195562051642,
    "limit_engaged_per_year": dict.fromkeys(("gross", "net", "margin"), _YEARS),
    "arm_a_limit_engaged": dict.fromkeys(("gross", "net", "margin"), 0),
}


def trial_inputs():
    """The trial's inputs half over the real set, with the reader that read it."""
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b3_slow_inputs(subjects._b3_reads("b3-tilt-slow", reader, "ohlc-full", None, False))


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet"),
    reason="the frozen ohlc-full set is absent under data/",
)
def test_the_tilt_slow_inputs_reproduce_the_measured_basis_and_record_58s_arm_a():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = trial_inputs()
    block = reader.block()
    assert compute_hash(block) == BLOCK == _trials()[60]["dataset_hash"] and reader.vouched_status() == VOUCHED
    assert len(inputs.close) == RETURN_INDICES
    record = _trials()[58]
    assert block["ohlc-full"]["files"] == {p: h for p, h in record["datasets"]["ohlc-full"]["files"].items() if "/EUR/" in p}
    assert book_turnover(inputs.arm_a) == record["metrics"]["turnover_a"]
    engagement = subjects._b3_engagement(inputs)
    assert {key: engagement[key] for key in ENGAGEMENT} == ENGAGEMENT
    assert {arm: round(mean, 4) for arm, mean in engagement["ranked_assets_mean"].items()} == dict.fromkeys(_ARMS, 5.775)
```

  **Author's call** — the case holds the subject's inputs half to the spec's books program, which built arm B's three arms by its own expression of `a2_book_returns` with the tilt written out and was itself held to record 60 at trial 1's score window, so the measured figures and the subject's code are two derivations that must agree; the block to record 60's `dataset_hash` and to record 58's ten EUR files, arm A to record 58 by its turnover to the last bit, the stored figures, never a second typing; the integer engagement, arm B's turnover and the ranked means exactly — the means as the histogram's own arithmetic — and the means at the four decimals the basis printed.
- [ ] **Step 2: Run it** — with `data/ohlc-full` linked in this worktree: `mkdir -p .tmp/plan-00148 && uv run pytest tests/test_research_b3_tilt_slow_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00148/pt`, one plain blocking call, `timeout` 600000 ms: `1 passed`, never a skip (measured on the authoring tree, a call of 136.75 s). The case joins `tests/slow-cases.txt` at its `sorted()` place:

```text
tests/test_research_b3_tilt_slow_basis.py::test_the_tilt_slow_inputs_reproduce_the_measured_basis_and_record_58s_arm_a
```

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b3_tilt_slow_basis.py tests/slow-cases.txt`; the Global Constraints' list over the two paths (measured on Task 2's tree in the scratch worktree, `18 passed, 1 deselected in 18.82s`); the two tree walkers its skip gate and data mark meet, `mkdir -p .tmp/plan-00148 && uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00148/pt` (measured `332 passed`); `uv run pre-commit run -a` until clean. No probe: the case is slow, recorded `probe skipped: slow case`.
- [ ] **Step 4: Commit** — `test(research): B3 trial 2's inputs half against the measured basis — the block, the first engagement, the ranked basket on a 540-close score, the tilted closes per arm, the closes where the books differ, the limits and arm B's turnover, and record 58's arm A`, the message carrying the gate's result line, `probe skipped: slow case — tests/test_research_b3_tilt_slow_basis.py::test_the_tilt_slow_inputs_reproduce_the_measured_basis_and_record_58s_arm_a`, the line `It reads data/ohlc-full: re-run it with the set linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.` and the two trailer lines.
- [ ] **Step 5: The decisions-log entries, before the hash** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`, after one blank line, the owner's word on B3's next step (the spec's Ruling), the loop's pick of the variant (D1) and then **Author's call** the trial's conventions, plan 00147's form — one commit, the three entries — so that all three stand in the log before any return of trial 2's arm B is read:

```markdown
[iter-193] B3's next step after trial 1 — the owner's word of 2026-10-25: the tilt at another M or k, then the A1-short overlay, then B3 closed (Decision: 1)
  Asked, attended, 2026-10-25, after B3 trial 1's verdict (registry trial 60, the `[iter-192] Verdict — B3 trial 1 REJECT` entry above), which step B3 takes next, offered three options — 1 a park variant (the tilt at another M or k), 2 the A1-short BTC overlay (master plan §5's B3 whole), 3 closing B3 — answered, at 2026-10-25T15:32:38Z: "let's wait for the round-23 review and PR first. after its PR merge, sequentially Option 1 -> 2 -> 3"; and stated the same sequence a second time at the session's restart, 2026-10-25T16:23:14Z: "session restarted, continue the work until all the 3 options finished". Read as: B3 trial 2 the park variant, then B3 trial 3 the overlay, then B3 closed, in that order whatever trial 2's verdict; the round-23 PR merged into develop as `22c220677` before trial 2's branch was cut. Standing and unchanged: the owner's family pick "B3 (Recommended)", the instrument ruling "Frozen ohlc-full (Recommended)" and the two `[iter-176]` rulings.
  1. **A park variant — the tilt at another M or k** — spec 00147 D7's named variant and D10's first next step, one B slot, 10 to 9; which M or k is the loop's pick (the entry below). Chosen, first in the owner's sequence 1 → 2 → 3.
  2. **The A1-short BTC overlay** — master plan §5's B3 whole, the tilt hedged episodically by the A1 short state; it carries the borrow the A family measured as a structural ~5 %/yr drag and §12's borrow-unavailable stress rung; one B slot. Second in the owner's sequence, B3 trial 3.
  3. **Close B3** — B3 closes on trial 1 alone, the master plan's "kill quickly if so" read at one slot. Third in the owner's sequence, after trial 3.

[iter-193] B3 trial 2's variant — the tilt on a 540-close score, its strength and floor trial 1's, the loop's pick under the owner's word (Decision: 1)
  The owner's sequence opens with the tilt at another M or k (the entry above); which cell is the loop's pick, made before spec 00148's hash. Record 60's stored turnovers put trial 1's added trading cost from its first engagement at 2.171062550568289e-05/bar (the turnover difference 42.20907442063182 at 0.006 a side over 11,665 returns) and its stored net head-to-head at -1.918138730849262e-05/bar, so the tilt's gross outperformance was about +2.53e-06/bar — arithmetic over record 60's stored figures, read after its run: the cost is the lever, and a slower score moves the ranks less.
  1. **The score at M = 540 closes (90 days), k and the floor unchanged** — one knob moves, the score window; spec 00148, count 2: the tilt first moves a position at return index 15,672 (close 2020-12-03 12:00), trial 1's, 11,665 return indices from it; the books differ at 9,687, and arm B trades 17.55 % more than arm A against trial 1's 28.87 %, an added cost of 1.32e-05/bar over the primary read, 0.6078 of trial 1's (spec 00148's measured basis); one B slot, 10 to 9. Chosen.
  2. **k = 0.25 at M = 180** — halves the tilt, its edge and its cost together, the ratio unchanged and the net still negative by the same arithmetic.
  3. **M = 1,080 (180 days)** — slower still, a half-year score; the slower the score the closer the tilt comes to the inverse-vol weights it tilts, and one slot buys one cell.

[iter-193] B3 trial 2's conventions, pinned by spec 00148 before its hash (Decision: 1)
  The trial's details are fixed in the spec, reviewed, and frozen by its sha256, its record's `spec_hash`, before any return of trial 2's arm B is read, or a net-of-cost series, head-to-head or bar leg of it computed, over the data; each call below is one the spec pins, the loop's or the author's as the spec marks it, every value the owner or specs 00128, 00133, 00137, 00144 and 00147 fixed staying theirs.
  1. **As the spec pins them, trial 1's tilt on a 540-close score, k = 0.5 and a basket of 8** — the owner's sequence, its first step the loop's pick (D1); frozen `ohlc-full`, full history, the ten EUR assets' 4h union as records 45–60 read it, no other pair, no as-of, trial 1's reads (D2); arm A the adopted ensemble, record 58's arm A to the bit; arm B trial 1's arm B with its score window 540 closes in place of 180, every clause of spec 00147 D3's tilt unchanged — the basket every asset with a weight and a score ranked, z its centred rank, at 8 or more each long's weight times 1 + k·z, the longs rescaled to their untilted sum — the clause that leaves a weighted asset without a score out of the basket deciding 2,649 return indices; `b3_book_returns` called unchanged and trial 1's halves read where they take no score window, a block of trial 1's form where they do, k and the floor read through trial 1's constants (D3); trial 58's costing, no borrow and so no carry (D4); §10's limits as trial 58 wired them, engaging no bar (D5); the contamination stated in full — trial 2 designed after trial 1's REJECT, M chosen to answer trial 1's cost on arithmetic over record 60's stored figures, the measured hurdle 1.32e-05/bar about 5.2 times trial 1's gross figure, the variant named by spec 00147 before trial 1's result and its value chosen after it, the instrument, window, arm A, costing, limits and bar records 45–60's, the primary read trial 1's span to the return index, the DSR counting B3's true trials (D6); trial 1's bar at count 2 and `var_trials` 0.0, the head-to-head from the tilt's first engagement, return index 15,672, deciding, trial 1's matrix through its own rule `_b3_rank_tilt_verdict`, the park row naming no variant (D7); trial 1's engagement and keys, 44 and 28, the subjects `b3-tilt-slow` and `b3-tilt-slow-preflight`, the variant `B3-tilt-slow-a2eq-full-v1`, the family key `B3` already in bucket B, the build in three halves (D8); no `--verdict`, notes naming only what is fixed before the run (D9); an adopt recorded, never deployed, the owner's sequence going on to trial 3 after any verdict, a stop the owner's, the subjects kept (D10). Chosen.
  2. **The alternatives each weighed** — trial 1's `_b3_ensemble`, `_b3_inputs` and `_b3_build` given the score window as an argument, a change to functions record 60's replay reads; trial 1's subjects re-run at M = 540 under their own names, a second record of one subject at another count; a rule of the trial's own, trial 1's five rows typed again; a park row naming a variant, which the owner's sequence already names; a count other than B3's true one; the subjects retired after the verdict, while trial 3 may still build on their halves.
  Source: spec 00148 (D1–D10), its **Author's call**s and the calls it carries from the owner and specs 00128, 00133, 00137, 00144 and 00147; the owner's words quoted in the first entry above.
```

  **Author's call — the owner's entry's heading says "the tilt at another M or k" where the owner's option said "a park variant"**: `tests/test_decisions_log_ties.py` reads a heading holding a verdict word in any case beside the word `trial` as a verdict on a trial with no tie (measured: the "park variant" heading prints that finding, this one none). Staged alone, its gate the Global Constraints' list over the staged path with `tests/test_decisions_log_shape.py` and `tests/test_decisions_log_ties.py` by path (measured in the scratch worktree over Task 2's tree, the three entries appended, `50 passed`) — `consumers.sh --direct` names no test reader of the log, its stderr saying `(none -- …)`, so those two are the whole list — and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-193] B3's next step after trial 1, the owner's word — the tilt at another M or k, then the A1-short overlay, then B3 closed — the loop's pick of trial 2's 540-close score, and B3 trial 2's conventions, pinned by spec 00148 before its hash`. The first entry's heading is the one T0016's B3 arm checks for: `grep -c -E '^\[iter-[0-9]+\] B3.s next step after trial 1' docs/research/10.phase4-decisions.md` prints 1 with the entries appended (0 before, measured in the scratch worktree), so the arm reads ripe from this commit until Task 5 rewrites it.
- [ ] **Step 6 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–2 and the three entries — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing computes or reads trial 2's arm B returns or net-of-cost series, a head-to-head or a bar leg of it — through the code, a program or arithmetic over a stored figure — or runs either new subject over the real data, before the spec's hash, and the data-gated case runs with `ohlc-full` linked into the reader's worktree and unlinked by the reader before its report, since unlinked it skips. Each report names the tip it read, the tip Task 3 step 1 diffs from. Task 3 waits until the trio has closed with no open Critical or Important.

## Task 3 (the controller's): the gate, the spec hash, the develop check, the data test and the check programs (D9)

- [ ] **Step 1: The gate** — each check its own call, each read before the next: the reads through Task 2 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00148-b3-tilt-slow-design.md docs/research/10.phase4-decisions.md` exits 0; the conventions entry against the spec at that tip, each item where the spec pins it and each call the spec carries under the ruling or spec it names; the code path since record 60's run — the spec's basis lists it from that run's commit to the branch's cut — `git log --oneline cd467546499090509ace16951b2c6b5929c5d0f0..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version`, lists Task 1's commit and its fixes alone (measured at the base: nothing); any other commit is named, step 4 deciding whether it moved the inputs half or trial 1's computes.
- [ ] **Step 2: D9 (1), the spec hash** — `sha256sum docs/specs/00148-b3-tilt-slow-design.md`; its value, pasted from that call, is the run's `--spec-hash` and the record's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D9 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0. A non-zero exit stops before the run: the controller reads which line moved, the same `git diff` without `--quiet`, and only for a line another writer appended legitimately — a registry record or a reading another branch's merged PR carries — merges develop, alone (`git merge --no-edit origin/develop`) — a conflict confined to `docs/research/10.phase4-decisions.md` or `tests/slow-cases.txt` resolved keeping both sides' lines, in the decisions log develop's entries above this branch's and in the slow-cases file each line at its `sorted()` place, and committed as the merge; a conflict in any other file aborted with `git merge --abort`, which stops the task, T0016's — then takes a delta read of the merge in place of re-running step 1: step 1's code-path log over `<the tip the last read names>..HEAD`, then `pre-review`, then `review` over that range and `re-review` over a fix of it within the branch's two, each `drive` carrying Task 2 step 6's sentence with its "before the spec's hash" read "before Task 4's run, record 60's replay excepted", the commits the log lists, and one sentence more: develop's commits were each read on their own PR, so the read judges the merge's resolution and each listed commit's effect on the trial — whose tip becomes the tip the last read names, and step 4 runs on the merged tree. A B3 record another branch landed raises `required_n("B3")` above 2, and the run is then refused before its fit (D7): the trial stops, T0016's. The check has two sites, this step and Task 4 step 1, and both take this path.
- [ ] **Step 4: D9 (3), the data test on the run's tree, with the subjects' two fixture rows and record 60's replay** — with `data/ohlc-full` linked: `mkdir -p .tmp/plan-00148 && ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b3_tilt_slow_basis.py 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b3-tilt-slow-evaluates]' 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b3-tilt-slow-preflight-evaluates]' 'tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-60]' -q -p no:cacheprovider --basetemp=.tmp/plan-00148/pt > .tmp/plan-00148/basis.out 2>&1`, one background call: `4 passed`, never a skip or an xfail — the fixture rows run the build end to end on the tree a fix of the reads may have changed, and record 60's replay rebuilds trial 1's stored figures through the reads, arm A, costing, bar, head-to-head and rule this trial's computes half shares with it (measured on Task 2's tree in the scratch worktree, the first three `3 passed in 166.04s`, the replay `1 passed`, a call of 266.95 s); a failure is a finding before the run — the data test's an instrument finding, a fixture row's a defect in the code, the replay's a moved computes half — T0016's, and the run waits.
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00148/preflight_check.py`, D9's (a)–(e) in order, the dead knob read before the engagement, exit 0 on a pass, else one `sys.exit` naming the step that stopped:

```python
"""Spec 00148 D9's pre-flight read, (a) to (e) in order: exit 0 on a pass, else the one sys.exit naming what stopped it."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from tests.test_research_b3_tilt_slow_basis import BLOCK, ENGAGEMENT, RETURN_INDICES, VOUCHED
from tests.test_trial_registry_provenance import _trials

out = Path(".tmp/plan-00148/b3-tilt-slow-preflight.out").read_text()
run = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
m, block = run["metrics"], run["datasets"]
print("block", compute_hash(block), run["vouched"])
if compute_hash(block) != BLOCK:
    sys.exit("(a) the inputs' block differs from the spec's")
if run["vouched"] != VOUCHED:
    sys.exit("(a) the set is not vouched as the spec reads it")
record = _trials()[60]["metrics"]
anchors = {
    "arm_a_ann_sharpe_noc": record["arm_a_ann_sharpe_noc"],
    "arm_a_ann_sharpe_noc_decisive": record["arm_a_ann_sharpe_noc_decisive"],
    "arm_a_max_drawdown_full": record["arm_a_max_drawdown"],
    "turnover_a": record["turnover_a"],
    "arm_a_spot_drag_pct_yr": record["turnover_a"] / RETURN_INDICES * 0.006 * 2190,
    "benchmark_ann_sharpe_noc": record["benchmark_ann_sharpe_noc"],
    "benchmark_ann_sharpe_noc_decisive": record["benchmark_ann_sharpe_noc_decisive"],
}
off = {key: (m[key], value) for key, value in anchors.items() if m[key] != value}
if off:
    sys.exit(f"(b) arm A does not reproduce record 60's arm A: {off}")
print("first engaged", m["tilt_first_engaged"], "primary", m["primary_returns"], "differ", m["stamps_positions_differ"], "turnover_b", m["turnover_b"])
if not m["stamps_positions_differ"]:
    sys.exit("(c) the tilt moves no position: the dead knob")
off = [key for key, value in ENGAGEMENT.items() if m[key] != value]
if off:
    sys.exit(f"(d) the engagement differs from the measured basis: {off}")
print({key: m[key] for key in ("dsr", "dsr_pass", "spa_p_value", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes")})
sys.exit(0 if m["passes"] == 1 else "(e) arm A fails its bar")
```

  and `.tmp/plan-00148/record_check.py`, the record's checks, its one argument the spec's sha256:

```python
"""Spec 00148 D8's record, read off the registry's last line against the run's print, its pre-flight's block and the
measured basis: exit 0 when every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b3_tilt_slow_basis import BLOCK, ENGAGEMENT

name, spec_hash = "b3-tilt-slow", sys.argv[1]
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(f".tmp/plan-00148/{name}.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]
before = Path(f".tmp/plan-00148/{name}-preflight.out").read_text()
preflight_block = compute_hash(json.JSONDecoder().raw_decode(before, before.index("{"))[0]["datasets"])
subject = SUBJECTS[name]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == preflight_block == BLOCK,
    "invocation": invocation
    == {"subject": name, "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"])
    == ("B3", 2, "B3-tilt-slow-a2eq-full-v1", "iter-193", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "engagement": {key: m[key] for key in ENGAGEMENT} == ENGAGEMENT,
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
```

  Each is written with `mkdir -p .tmp/plan-00148 && cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00148/preflight_check.py .tmp/plan-00148/record_check.py`. The pre-flight check was run in the scratch worktree over a synthetic pre-flight print carrying the real block, read by `_b3_reads` with no compute, the basis's engagement and record 60's arm A figures: it printed the block, the first engagement, the primary count, the differing stamps, arm B's turnover and the bar's flags and exited 0; with `passes` 0 it exited 1 on `(e) arm A fails its bar`, and with `stamps_positions_differ` 0 on `(c) the tilt moves no position: the dead knob`.

## Task 4 (the controller's): trial 2 — its pre-flight, its run and its record (D7–D9)

`<H>` is Task 3 step 2's sha256.

**The notes rule**: every free-text `--notes` this plan passes is written first, in a call of its own, to its own file under `.tmp/plan-00148/` by a quoted heredoc — `mkdir -p .tmp/plan-00148 && cat > <its file> <<'EOF'`, the text on the lines after it, `EOF` alone on the last — and passed as `--notes "$(cat <its file>)"` behind `test -s <its file> &&` in the run's own line: no `'` or `"` in the text can end the argument, and an absent or empty file stops the line before `uv run` starts, never a run with empty notes — its output file not written, nothing spent, the file written again before the line runs again. The sites, the whole of them: step 3's reading, `.tmp/plan-00148/b3-tilt-slow-reading-notes.txt`, and step 4's trial, `.tmp/plan-00148/b3-tilt-slow-notes.txt` — the two `--notes` spec 00148 D9 names, in its steps (4) and (5); no other step of this plan passes one.

- [ ] **Step 1: The develop check** — Task 3 step 3 whole, its stop, its merge path and Task 3 step 4 after a merge with it; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `mkdir -p .tmp/plan-00148 && uv run zcrypto research eval --subject b3-tilt-slow-preflight --dataset ohlc-full > .tmp/plan-00148/b3-tilt-slow-preflight.out 2>&1`, a plain eval of a subject with no rule — the inputs half and one bar, about two and a half minutes (the spec's basis: the inputs half 136.75 s, one bar 11.16 s) — one background call; at its notification and on its exit 0, `uv run python .tmp/plan-00148/preflight_check.py`. Exit 0: step 4. A `sys.exit` message naming one of (a)–(e): D9's instrument finding, step 3. A traceback, or a refusal before the build, is a code or environment fault, the step stopped and T0016's with its line; a refused build — exit 1 with no traceback, its output naming `b3-tilt-slow-preflight over the full history: …` — prints no metrics, keeps no reading, and is recorded in Task 5's T0016 findings with its line quoted, the trial unspent.
- [ ] **Step 3: On a stop, the reading** — its notes, by the notes rule, in `.tmp/plan-00148/b3-tilt-slow-reading-notes.txt`: `B3 trial 2's pre-flight (spec 00148 D9): <the check's sys.exit line, whole, between single quotes, never a double quote>; no verdict, the trial unspent`; then `mkdir -p .tmp/plan-00148 && test -s .tmp/plan-00148/b3-tilt-slow-reading-notes.txt && uv run zcrypto research eval --subject b3-tilt-slow-preflight --dataset ohlc-full --reading --iteration iter-193 --spec-hash <H> --notes "$(cat .tmp/plan-00148/b3-tilt-slow-reading-notes.txt)" > .tmp/plan-00148/b3-tilt-slow-reading.out 2>&1`, one background call; then step 6's stop arm.
- [ ] **Step 4: The trial** — one run: `mkdir -p .tmp/plan-00148 && test -s .tmp/plan-00148/b3-tilt-slow-notes.txt && uv run zcrypto research eval --subject b3-tilt-slow --dataset ohlc-full --register --iteration iter-193 --family B3 --n-trials 2 --variant B3-tilt-slow-a2eq-full-v1 --spec-hash <H> --notes "$(cat .tmp/plan-00148/b3-tilt-slow-notes.txt)" > .tmp/plan-00148/b3-tilt-slow.out 2>&1`, about four minutes (the spec's basis: the inputs half, seven bars and two head-to-heads, about 226 s; record 60's run 264 s), one background call, `cat` at its notification. No `--verdict` and no plain eval, before or after. The notes, written before the run to `.tmp/plan-00148/b3-tilt-slow-notes.txt` by the notes rule, name only what is fixed before it: `subject b3-tilt-slow over ohlc-full, full history, no as-of; B3 trial 2, the first step of the owner's sequence of 2026-10-25 after trial 1's reject - the tilt at another M or k, then the A1-short overlay, then B3 closed; arm A the adopted equal-weight A2 4h ensemble on the ten EUR assets, arm B trial 1's arm B on a 540-close score: each arm's inverse-vol weights of the assets it holds long tilted at every 4h close by their centred rank in the whole basket, every weighted asset with a score whatever its direction, on the trailing 540-close (90-day) simple return, each long times 1 + 0.5 z, 1.5 at the basket's top and 0.5 at its bottom, the longs rescaled to their untilted sum, the flat assets untouched, at the closes where the basket ranks 8 assets or more, long-only, A2's configuration otherwise unchanged; every asset charged 0.006 per side on its own turnover, no borrow and no carry; the section 10 gross cap, net band and margin floor, one factor per bar; the hypothesis: the tilted book has a higher mean net-of-cost return than the untilted ensemble from the first close the tilt moves a position; n_trials 2, B3's true count, var_trials 0.0, the DSR leg binding; the head-to-head from return index 15672 (close 2020-12-03 12:00), the tilt's first engagement, decides, the full-window read beside it; the contamination: designed after trial 1's reject (registry trial 60), M chosen to answer trial 1's cost, its added cost 2.17e-05 per bar against a gross outperformance of about +2.53e-06 per bar on arithmetic over record 60's stored figures, arm B here trading 17.55 % more than arm A against trial 1's 28.87 %, an added cost of 1.32e-05 per bar over the primary read, about 5.2 times trial 1's gross figure; the variant named by spec 00147 before trial 1's result, its value chosen after it; the instrument, arm A, costing, limits and bar records 45-60's, the primary read trial 1's span; pre-flight: block ff2e5700..., arm A <the seven anchors>, the bar's dsr <its dsr> and SPA p <its spa_p_value>, passes 1, the tilt engaged from return index 15672 with positions differing at 9687 return indices, no limit engaged, turnover_b <its value>; the park row names no variant, the owner's sequence going on to trial 3, the A1-short BTC overlay; the matrix pre-registered by the spec's sha256 <H>`. A refusal from the count — an orphan, a B3 record landed elsewhere, or bucket B spent — comes before the fit or after the print, naming each orphan, the count or the bucket's figure: no record, no reading; T0016 carries it (Task 5). A stop by the rule writes a reading carrying its attempt, which counts 0: step 6's stop arm. On any other exit — a refused build, a traceback, a signal, a refusal after the print — the attempt check runs, `uv run python -c 'import json; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; a = [x for x in lines if x["kind"] == "begin" and x["invocation"]["subject"] == "b3-tilt-slow"][-1]["attempt"]; print(a, [x["failed"] for x in lines if x["kind"] == "end" and x["attempt"] == a] or "open")'`: a refused build ends its attempt failed, counting 0, recorded in T0016 with its line, the trial unspent; any other `failed` text, `open`, or `<id> [None]` stops the task, T0016's with the end of the run's output quoted whole.
- [ ] **Step 5: The record's checks** — on a record: `uv run python .tmp/plan-00148/record_check.py <H>` exits 0; its printed `counted` is read, never checked: T0016's line takes every orphan off the count (Task 5 step 1). A failed check — this one, the record's replay in step 6, or on step 6's stop arm the reading's line check and its replay — stops the task where it stands: what the run appended, the record or the reading, stays in place uncommitted and nothing is committed; the controller hands the owner the failing check's output quoted whole, and what becomes of the record or reading is the owner's word, Task 5 waiting on it.
- [ ] **Step 6: The records commit** — on a record: (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-193] Verdict — B3 trial 2 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family B3 n=2)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry, its text to its first `. ` holding no other verdict word; the body: the matrix row that fired, read off the record's stored keys beside its stored verdict with D7's table (`sed -n '/^| Arm A.s bar and the tilt/,/^  Every quantity the matrix reads/p' docs/specs/00148-b3-tilt-slow-design.md`), with `arm_a_passes`, `passes`, `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary` unrounded, the full-window pair beside them; `n_trials` 2, `var_trials` 0.0 and the DSR leg (`dsr_corrected`, `dsr_pass`); `max_drawdown` beside `arm_a_max_drawdown`; the pre-flight's block, anchors and `passes` from `.tmp/plan-00148/b3-tilt-slow-preflight.out`; the engagement — `tilt_first_engaged`, `primary_returns`, `stamps_positions_differ`, `ranked_assets_mean`, `turnover_a` beside `turnover_b`, `limit_engaged_per_year`'s totals; beside trial 1's record 60, `head_to_head_mean_outperf_primary` and `turnover_b`, both stored; the contamination D6 states, pointing at the conventions entry above; on an adopt D10's path in its order; on any verdict the owner's sequence going on to trial 3; on a reject the hypothesis as the notes word it, archived — in the form of `[iter-192] Verdict — B3 trial 1 REJECT`; (ii) in `tests/test_trial_registry_provenance.py`, `LANDED_N_TRIALS` and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts each gain `"b3-tilt-slow": 2,` after `"b3-rank-tilt": 1,`; (iii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<its trial_id>]` at its `sorted()` place; on an adopt, (iv) T0123's `ripe_when` gains `— registry trial <N>, B3 trial 2's ADOPT on the A2 ensemble alone, ripens this only once the P1 combination trial over record 47's book that carries its tilt adopts` (D10), and `uv run python infra/scripts/topics-index.py` re-renders `docs/open-topics/README.md`. Then `git add` by path of `docs/reference/trial-registry.jsonl`, the record step 4's run appended, `docs/research/10.phase4-decisions.md`, `tests/test_trial_registry_provenance.py` and `tests/slow-cases.txt`, and on an adopt `docs/open-topics/T0123-sleeve-promotion-path.md` and `docs/open-topics/README.md`; the list over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path — `tests/test_open_topics_frontmatter.py` among the index's readers on an adopt; `uv run pre-commit run -a` until clean, its rewrites staged. In the probe worktree, which the Global Constraints' probe setup creates from that index and whose tree it prints, the set linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/ohlc-full /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter193/.tmp/plan-00148/probe/data/ohlc-full`, unlinked after the replay and the probe with `test -L <its absolute path> && unlink <its absolute path>` and the worktree removed as the Global Constraints' probe paragraph removes one that held a link: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'trial-<its trial_id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt`, one background call: `1 passed`, never a skip, its result line and call time for the message — a difference or a skip is a failed check, step 5's stop; then the literal's probe, expected `KILLED` (its two seds dry-run on the authoring tree, each changing one line): `infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b3_tilt_slow(/def _build_b3_tilt_slow_gone(/' --mutation 's/^_B3_SLOW_N_TRIALS = 2\b/_B3_SLOW_N_TRIALS = 3/' -- uv run pytest tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal -q -p no:cacheprovider --basetemp=.tmp/pt`. Commit that index, with no `git add` after the setup, as `docs(research): B3 trial 2 registered — <verdict>, the A2 ensemble's long weights tilted by a cross-sectional momentum rank on a 540-close score, registry trial <N>`, the message carrying the tie and provenance tests' result line, the replay's with its call time, `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):`, the literal's `infra/scripts/mutate-probe.sh` command and its verdict line, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<N>]`, the line `The replay reads data/ohlc-full: re-run it with the set linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.`, and the two trailer lines; after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.

  On a stop (step 3, or the rule's stop under `--register`): the ledger's last line is checked — its subject `b3-tilt-slow-preflight` with outcome `null`, or `b3-tilt-slow` with the `no_verdict` text and a non-null `attempt`; its `spec_hash` `<H>`; its metrics the run's printed ones, a line off any of them a failed check, step 5's stop — the entry is `[iter-193] B3 trial 2 — instrument finding, the trial unspent (reading <its reading_id>)`, naming what failed, quoted; no literal; the slow row `[reading-<its id>]` at its `sorted()` place, the replay rebuilding the run over the real set, as (iii) adds the record's; `git add` by path of `docs/reference/reading-ledger.jsonl`, the reading the run appended, `docs/research/10.phase4-decisions.md` and `tests/slow-cases.txt`, then the record arm's list, pre-commit, probe worktree and replay, with `-k 'reading-<its id>'`, `1 passed`, never a skip; committed as `docs(research): B3 trial 2 — instrument finding, kept as reading <id>; no trial spent` with no literal's probe. On a refusal from the count or a refused build: no commit here; Task 5 records it.

## Task 5: T0016 and the index (D10)

**Files:** `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`.

Every figure is read off the committed record or reading and its entry. Task 4's outcome picks the arm: a verdict other than an adopt — park or reject — takes the verdict arm; an adopt the adopt arm; no verdict — a stop kept as a reading, a refused build, a refusal from the count, a merge aborted at a develop check, the data test failing or skipping, or any other end Task 4 sends to T0016 — the stop arm. **Author's call — no retirement in any arm** (D10): trial 3 may build on `_b3_reads`, `_b3_metrics`, `_b3_engagement` and `b3_book_returns`, whose cases trial 1's and trial 2's subjects carry, so `tests/retired_subjects.py` is not touched and all four subjects' cases stay in CI until B3's closing branch.

- [ ] **Step 1: T0016**, per `topic-ops`, each anchor counted unique with `grep -c` before its edit and the heading set (`grep '^#'`) compared before and after:
  - `## Findings so far`: the budget bullet's figures read off the count the bucket refusal reads, every orphan in it, `uv run python -c 'import json; from pathlib import Path; from cli.registry import attempts, budget; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2", "B3", "B4")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])'` (at this branch's base it printed `{'B1': 5, 'B2': 7, 'B3': 1, 'B4': 2} remain 10 []`; on trial 2's record, with no orphan, it prints `{'B1': 5, 'B2': 7, 'B3': 2, 'B4': 2} remain 9 []`): `(B1 spent 5, B2 spent 7, B3 spent 1, B4 spent 2, 10 remain)` reads `(B1 spent <its B1>, B2 spent <its B2>, B3 spent <its B3>, B4 spent <its B4>, <its remain> remain)`, each orphan it lists named there; after the `**B3 trial 1 REJECT (iter-192, spec 00147, registry trial 60).**` bullet, one bullet `**B3 trial 2 <VERDICT> (iter-193, spec 00148, registry trial <N>).**` — the row that fired and the tilt's engagement on the 540-close score in one or two sentences, pointing at its decisions-log entry for the figures — or, on the stop arm, `**B3 trial 2, no verdict (iter-193, spec 00148).**`, naming the reading by id where one was kept and quoting whole the line that stopped it — the check's `sys.exit` line, the conflict `git merge` printed, which stands in no file, only in the controller's call, and so reaches this task quoted whole in the controller's dispatch of it, the failure or skip line in `.tmp/plan-00148/basis.out`, the line in `.tmp/plan-00148/b3-tilt-slow-preflight.out` or `.tmp/plan-00148/b3-tilt-slow.out`, or that run's output's end as Task 4 step 4 quotes it — the trial unspent unless the count lists its attempt as an orphan, which spends the slot.
  - `## Done so far`: the **B3 opened** bullet's last sentence, `` Trial 1 (registry trial 60) REJECT; the subjects kept until the owner's call on B3's next step. ``, becomes `` Trial 1 (registry trial 60) REJECT. Trial 2 (iter-193, spec/plan `00148`, registry trial <N>) <VERDICT>, the tilt on a 540-close score, the first of the owner's sequence of 2026-10-25: the subjects `b3-tilt-slow` and `b3-tilt-slow-preflight` and the data-gated basis test `tests/test_research_b3_tilt_slow_basis.py`; every B3 subject kept until B3 closes. ``; on the stop arm its second sentence reads `` Trial 2 (iter-193, spec/plan `00148`), the tilt on a 540-close score, the first of the owner's sequence of 2026-10-25: the subjects `b3-tilt-slow` and `b3-tilt-slow-preflight` and the data-gated basis test `tests/test_research_b3_tilt_slow_basis.py`; no verdict, no slot spent, its subjects kept. ``, or, where the budget bullet's count lists trial 2's attempt as an orphan, `` …; no verdict, one slot spent by its orphaned attempt, its subjects kept. ``
  - `## Suggested next steps`: its one bullet, `` - (owner) B3's next step after trial 1 — a park variant (the tilt at another M or k), the A1-short BTC overlay (master plan §5's B3 whole) or closing B3 — recorded as a `[iter-NNN] B3's next step after trial 1` entry; then per §5 ranking: C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism). ``, becomes on the verdict arm and the adopt arm `` - B3 trial 3, the A1-short BTC overlay (master plan §5's B3 whole), the next step of the owner's sequence of 2026-10-25 (the `[iter-193] B3's next step after trial 1` entry), opening in a later iteration with its own brainstorm, spec and plan against the shared B budget (<its remain> remain); then B3 closed, the sequence's last step; then per §5 ranking: C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism). ``; on the adopt arm a bullet after it, `` - (owner) B3 trial 2's ADOPT (registry trial <N>), recorded, never deployed: its path in order — a P1 combination trial over record 47's book carrying the tilt on a 540-close score, outside every bucket's budget, then T0123's promotion path (spec 00148 D10). ``; on the stop arm the bullet becomes instead `` - (owner) B3's next step after trial 2's stop — trial 2 run again once its cause, quoted in Findings, is fixed, or the owner's sequence moved on to trial 3 — recorded as a `[iter-NNN] B3's next step after trial 2` entry; then B3 trial 3 and B3's close, the owner's sequence of 2026-10-25; then per §5 ranking: C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism). ``
  - `ripe_when`: its B3 arm, `` B3: an activity, the owner picks B3''s next step after trial 1, recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] B3.s next step after trial 1'' docs/research/10.phase4-decisions.md` prints at least 1; `` (the trailing space included), becomes on the verdict arm and the adopt arm alike — D10's sequence after any verdict — `` B3: an activity, B3 trial 3 — the A1-short BTC overlay, the next step of the owner''s sequence of 2026-10-25 — opened in an iteration, recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] (Verdict — )?B3 trial 3( |.s )'' docs/research/10.phase4-decisions.md` prints at least 1; `` and on the stop arm `` B3: an activity, the owner''s call on trial 2''s stop — the trial run again once its cause is fixed, or the sequence moved on to trial 3 — recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] B3.s next step after trial 2'' docs/research/10.phase4-decisions.md` prints at least 1; `` — in the frontmatter's single quotes, each `'` inside it doubled as written here, the check kept in its own backticks, its `.` standing for the apostrophe a shell's single quotes cannot hold; the other families' arms unchanged.
  **Author's call — trial 3's check reads any of its headings**: the trial's conventions entry, its verdict and an instrument finding are the three forms a B3 trial's headings take (`[iter-192] B3 trial 1's conventions…`, `[iter-192] Verdict — B3 trial 1 REJECT…`, plan 00147's `[iter-192] B3 trial 1 — instrument finding…`); measured in the scratch worktree, the check prints 0 on the log with Task 2's entries appended and matches a sample of each of the three forms for trial 3 and none for trial 2 or a trial 30. Measured there too, each arm applied to the base's T0016 with sample figures and then reverted: the heading set unchanged, the frontmatter parsing to the intended text, the stop arm's check printing 0 with Task 2's entries appended, and `tests/test_open_topics_frontmatter.py tests/test_topics_index.py` passing (`1111 passed`) with step 2 applied.
- [ ] **Step 2: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 3: Gate and commit** — `git add` the two paths; the list over them with `tests/test_open_topics_frontmatter.py` by path; `uv run pre-commit run -a` until clean; committed as `docs(open-topics): T0016 after B3 trial 2 — <its verdict or no verdict>, B3 trial 3 next on the owner's sequence; its subjects kept`.

## Task 6 (the controller's): the change-index row, the read and the PR

- [ ] **Step 1: The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-193 — B3 trial 2: the rank tilt on a 90-day score` (70 characters by `printf '%s' <it> | wc -m`, under the cap), its own commit.
- [ ] **Step 2: The read** — the `pre-review` of Tasks 4–5's commits and the row's, then `review` over `<the tip the last read names>..HEAD`, and `re-review` over a fix of it within the branch's two, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated case and the replay the messages record run with `ohlc-full` linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 3: The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the verdict or the stop, the pre-flight's output quoted whole in a fenced block (`.tmp/plan-00148/b3-tilt-slow-preflight.out`), every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the owner's two statements of the sequence the trial runs under, each quoted with its stamp as the first decisions-log entry of Task 2 step 5 carries them, and the session transcript named as the source of both quotes and their stamps, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the last read names. Merged through `merge-pr`; before it, `git status --short --ignored` read, `.tmp/plan-00148` collected and removed, and the link removed with `test -L <the checkout>/data/ohlc-full && unlink <the checkout>/data/ohlc-full` in this worktree and in each reader's checkout whose `data/` holds it; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows `ohlc-full` still there.

Decisions log: the owner's word on B3's next step after trial 1, the loop's pick of trial 2's variant and the conventions entry (Task 2 step 5), before the hash; the verdict or instrument-finding entry (Task 4 step 6), in its record's commit; after a verdict B3's next step is already the owner's word — trial 3, then B3's close — and on a stop it is the owner's, its entry a later branch's (T0016's trigger).
