# B2 trial 8 — the daily long-side liquidation de-risk at threshold 3.0 on frozen ohlc-full: the trial subject and its twin, the data-gated basis test, the owner's pick before the hash, the gated run and the record — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt tests/test_research_b2_liq_derisk_threshold_basis.py docs/research/10.phase4-decisions.md docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl tests/test_trial_registry_provenance.py tests/retired_subjects.py docs/open-topics/T0023-b2-derivatives-data-sourcing.md docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/T0123-sleeve-promotion-path.md docs/open-topics/README.md docs/reference/change-index.md docs/specs/00143-b2-liq-derisk-threshold-design.md` prints `tier: full`, for `tests/test_research_command.py` "a test importing cli.alpha", `docs/reference/trial-registry.jsonl`, `tests/test_trial_registry_provenance.py` "a test importing cli.registry", and, once Task 2 has created it, `tests/test_research_b2_liq_derisk_threshold_basis.py` "a test importing cli.registry.observed").

**Goal:** B2's trial 8 (spec 00143) — record 54's daily long-side liquidation de-risk one threshold step up, at 3.0: two research subjects in `cli/research/subjects.py`, the trial and its evaluate-only pre-flight twin, on the overlay machinery unchanged; the data-gated test of their inputs half; the owner's pick and the trial's conventions in the decisions log before the hash; the trial run through spec 00133's trial-attempts log, its verdict or stop in the registry and the decisions log; then T0023 and T0016.

**Architecture:** no new module and no new function body. `cli/research/subjects.py` gains the constants `_B2_LIQ_Z3_THRESHOLD` (3.0) and `_B2_LIQ_Z3_N_TRIALS` (7), two thin wrappers — `_build_b2_liq_z3_derisk` and `_build_b2_liq_z3_derisk_preflight` — over `_b2_overlay_build` with `_b2_liq_signal`, the constant, `_b2_overlay_metrics` or `_b2_overlay_preflight_metrics` and the count, and two `SUBJECTS` entries whose rule is `_b2_overlay_verdict` itself. Nothing writes a dataset.

**Tech Stack:** Python 3.14 through uv; polars; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00143-b2-liq-derisk-threshold-design.md` — binding; D1–D7 are cited by name and the values below are copied from it. It carries spec 00138's instrument, signal, bar, arms, costing and matrix, frozen (records 52–54's and reading 2's `spec_hash`). **Iteration:** iter-187. **Topic:** T0023 under T0016. **Branch:** `research/iter-187-b2-liq-derisk-threshold`, worktree `.claude/worktrees/iter187`, `data/ohlc-full` and `data/liquidations-daily` linked read-only from the main checkout (`data/derivatives-funding` and `data/derivatives-oi` linked too, which nothing here reads). A choice this plan makes that the spec leaves open is marked **Author's call**. Every code fence below was cut from the files the author ran: Tasks 1–2's code and tests were written in this worktree beside the staged spec, Task 1's new cases measured red against the base module (`10 failed, 737 deselected`) and green with it (`10 passed, 755 deselected`), the shared rows the two subjects add green (`19 passed, 746 deselected` in 96.79 s), Task 1 step 7's three gate parts green, Task 2's data-gated case `1 passed` in 70.77 s, the slow cases timed, and Task 1's twelve probe rows run in a detached scratch worktree on that tree, twelve of twelve `KILLED`; Task 5's retirement was collected there, the two decisions-log entries of Task 2 step 5 appended in a second scratch worktree and run through the decisions-log tests, and Task 3's pre-flight check run over a synthetic pre-flight print; the files were then restored to the base before this plan was committed, and the fences applied to the base as the steps say reproduce every authoring file. Not run: any `zcrypto research eval` (Tasks 3–4), the record's check program beyond a parse, the replay and the literal probe (Task 4), the topic edits (Task 5) and the PR (Task 6).

## Global Constraints

- **The signal and the threshold** (D3): `_b2_liq_signal(reader, h4_ts)` per coin over `liquidations-daily/<COIN>/daily.parquet`, key `binperp_liq_long_z30d`, record 54's signal unchanged; the threshold `_B2_LIQ_Z3_THRESHOLD = 3.0`, a pre-registered constant, never `_b2_engagement_threshold`; the scales `derisk_scales(signal, config=B2Config(z_threshold=3.0))`, arm B `scale_positions(arm_a, scales)`, the scale 0.5 `B2Config`'s default.
- **The bars** (D2, D4): every `a1_kill_bar` call `n_trials=7, var_trials=0.0, mean_block=<30 or 102>, seed=<42, 7 or 1234>, cost_stressed_returns=<×1.5 series>, regime_slices=calendar_year_slices(<series>, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000`, the headline (30, 42); arm A's bar the same call at (30, 42) on `net_a`; the head-to-heads `net_of_cost_verdict(net_b[first:], net_a[first:], mean_block=30, seed=42, n_resamples=2000)` for `("full", 0)` and `("primary", start)`, `start` `_b2_overlay_start(inputs)`, 19,731; the drawdown pair from `start`; refused before any bar: fewer than 2 return indices from `start`, or arm A never drawing down from it — `_b2_overlay_metrics`, unchanged.
- **The count** (D4): `_B2_LIQ_Z3_N_TRIALS = 7`, `required_n("B2")` as the spec measured it, fixed by the spec's hash; at `var_trials` 0.0 it moves no figure of the bar.
- **The rule** (D4): `_b2_overlay_verdict`, record 54's, unchanged — `None` when `arm_a_passes` is 0 or no year holds an engaged stamp, `reject` on a failed bar, `adopt` on `head_to_head_mean_outperf_primary > 0`, `max_drawdown_reduction_pct > 1e-6` and `head_to_head_spa_p_primary < 0.05`, `park` on the first two with the p at or above 0.05, `reject` otherwise; the park variants the scale 0.25 at 3.0 and the threshold 3.5.
- **The record** (D5): family `B2`; `n_trials_in_family` 7; variant `B2-liq-z3-derisk-a2eq-full-v1`; iteration `iter-187`; seeds (42, 7, 1234); 42 metric keys, `threshold` 3.0 among them; the block `816f62f931468b96f39f6fcbbdbfeee5124fa64fb062a98554895870de30474f`, record 54's; no `--verdict`.
- **The pre-flight read** (D6), in this order: (a) the block and `liquidations-daily`'s vouched status (Task 2's `BLOCK` and `VOUCHED`); (b) arm A's seven anchors at record 45's precision — `arm_a_ann_sharpe_noc` 1.405, `arm_a_ann_sharpe_noc_decisive` 1.3716, `arm_a_max_drawdown_full` 0.2154, `arm_a_spot_drag_pct_yr` 0.0703, the benchmark's 1.2128 and 1.2447 at four decimals, `turnover_a` 146.19 at two; (c) `engaged_per_asset`, `engaged_per_year`, `primary_returns` and `threshold` the measured basis's (Task 2's literals) and the signal's coverage record 54's stored one; (d) the engaged total above 0; (e) arm A's `passes` 1.
- **The hash rule** (D6): before Task 3 step 2 takes the spec's sha256, nobody computes arm B's returns, a head-to-head or any bar leg of arm B over the real data, nor runs `b2-liq-z3-derisk` or `b2-liq-z3-derisk-preflight` over the real sets; positions, scales, engagement counts and turnover are allowed — what the data-gated test (Task 2) computes, beside record 54's own threshold over the same positions, and no return; no reader, reviewer or plan-review dispatch runs either subject over the real sets before the hash, and every read's dispatch carries this rule. No return of arm B is computed over the real data before the trial's `--register` run, and the trial subject is never run as a plain eval.
- **Unchanged** (D5): every existing function of `cli/research/subjects.py`, `cli/alpha/*`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/validation/*`, `cli/engine/*` and `cli/liquidations/*`; the subjects of trials 1–7 and of readings 1–5; any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-only $(git merge-base HEAD origin/develop) -- cli/` prints `cli/research/subjects.py` from Task 1 on, nothing else; `git diff -U0 $(git merge-base HEAD origin/develop) -- cli/ | grep -c '^-[^-]'` prints 0 — the file gains lines and loses none. Measured on the authoring tree, the hunks: `@@ -2459,0 +2460,49 @@` and `@@ -3696,0 +3746,25 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00143-b2-liq-derisk-threshold-design.md` after Task 3 step 2, nor specs 00128, 00133, 00137 and 00138, nor the spec before then except a fix commit a read of Task 2 step 6 asks for; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Task 4 names it. Never `git stash`; no amend; never `--no-verify`; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-full` and `data/liquidations-daily`, read-only links, never written under. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/`, a fleet host, docker, `kraken-cli`, the vault, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`. The trial, every test and every implementer step make no network call and no ssh connection; the controller's `git fetch origin develop` (Task 3 step 3, Task 4 step 1) and Task 6's `gh` calls, push and `merge-pr` are the exceptions.
- **Research only**: nothing is armed, deployed, converged, pinned, rolled out or dropped — no fleet host, image, unit, alert rule or dashboard is touched, and no step of this plan waits on a maintenance window or a converge gap.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 2 step 6's reads, Tasks 3–4 and Task 6, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the data test, the pre-flight, the register, the replay), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1 and 5 and Task 2's steps 1–5.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00143 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00143/pt` (or a file, or `-k`): every `--basetemp` under `.tmp/plan-00143/` follows `mkdir -p .tmp/plan-00143 &&` in the same command, since pytest creates the base temp's leaf and never its parents. An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file, node id or `-k` selection into parts that cannot, each its own `--basetemp=.tmp/plan-00143/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `T=$(bash infra/scripts/consumers.sh --direct <each changed path> | sort -u)` and `[ -n "$T" ] && mkdir -p .tmp/plan-00143 && uv run pytest $T -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00143/pt`, never a bare `uv run pytest` and never `consumers.sh` with `2>/dev/null`; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. Every `T` holding `tests/test_research_command.py` runs it in three parts, each one plain blocking call under `-m "not slow and not data"`, `timeout` 600000 ms: `tests/test_research_command.py -k "not reentry"` (`--basetemp=.tmp/plan-00143/pt-1`, measured on the authoring tree, Tasks 1–2's code in it, `596 passed, 169 deselected in 493.23s`), `tests/test_research_command.py -k reentry` (`pt-2`, measured `71 passed, 694 deselected in 89.48s`) and the rest of `T` (`pt-3`). A commit message's test result line is a run over that commit's own tree.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
mkdir -p .tmp/plan-00143 &&
  test ! -e .tmp/plan-00143/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00143/probe HEAD &&
  git -C .tmp/plan-00143/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00143/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00143/probe/.tmp
```

  Then, from `.tmp/plan-00143/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, so it fails at import or at its call. A mutation whose text also stands in another wrapper — the two new wrappers share most of their lines with each other and with record 54's — carries the address of its own function's or entry's range, `/^def <name>(/,/^def /` or `/"<subject>": Subject(/,/^    ),/`, so its dry run changes one line. After the last verdict, `git worktree remove --force .tmp/plan-00143/probe` — a data link in it unlinked first, each removal of one that held a link followed by `ls -la /home/zhaow/Projects/zcrypto-kraken/data`, each set it linked still listed. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <the hash the setup printed>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.
- **The subjects' names** (D5): `b2-liq-z3-derisk` and `b2-liq-z3-derisk-preflight`, which no registered or retired subject's name equals or opens with a hyphen, and which open none (the spec's basis). The new functions' names carry `liq_z3`, which no hyphenated id carries, so `-k liq_z3` selects them alone; the shared rows the two subjects add carry the hyphenated `b2-liq-z3-derisk` in their ids.

## Task 1: the trial subject and its pre-flight twin in `cli/research/subjects.py` (D3–D5)

**Files:** Modify `cli/research/subjects.py`, `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`.

**Interfaces:** Consumes `cli/research/subjects.py`'s `_b2_overlay_build`, `_b2_liq_signal`, `_b2_overlay_metrics`, `_b2_overlay_preflight_metrics`, `_b2_overlay_verdict`, `_b2_overlay_metric_keys`, `_b2_overlay_preflight_keys`, `_b2_overlay_inputs`, `derisk_scales`, `scale_positions`, `_b2_engagement_threshold`, `a1_kill_bar`, `benchmark_4h_net_of_cost`, `_capturing_union`, `_ASSETS`, `Subject` and `ObservedReader`, each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; in the tests, `_anchor`, `_as_trial`, `_rolling_set`, `_recording`, `_fake_kill_bar`, `_fake_benchmark`, `_b2_overlay_dataset`, `_B2_START`, `_B2_ASSETS`, `_B2_NEVER_SPIKES`, `_B2_OVERLAY_NO_VERDICT`, `_overlay_metric_keys`, `_overlay_preflight_keys`, `_RULED_FIXTURES`, `_DECLARED_COUNT`, `_CONTRACT_DATASETS`, `B2Config`, `runner` and `app`. Produces the two subjects and the constants `_B2_LIQ_Z3_THRESHOLD` and `_B2_LIQ_Z3_N_TRIALS`, which Task 2's data-gated test and Task 4's literal read.

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - `test_each_subject_declares_the_metric_keys_its_build_returns` gains, after its `for name, (signal_key, *_) in _B2_REENTRIES.items():` loop and before its `assert subjects.SUBJECTS["b2-liq-tape-reading"]` line:

```python
    for name, (signal_key, *_) in _B2_LIQ_Z3.items():
        assert subjects.SUBJECTS[name].metric_keys == _overlay_metric_keys(signal_key)
        assert subjects.SUBJECTS[f"{name}-preflight"].metric_keys == _overlay_preflight_keys(signal_key)
```

  - after `test_the_rerisk_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it` and before `def _ruled_signal(`:

```python
_B2_LIQ_Z3_SPEC = "docs/specs/00143-b2-liq-derisk-threshold-design.md"
# Spec 00143's trial: its signal's key, threshold and count, typed from the spec, never read off a subject.
_B2_LIQ_Z3 = {"b2-liq-z3-derisk": ("binperp_liq_long_z30d", 3.0, 7)}


@pytest.mark.parametrize("name", sorted(_B2_LIQ_Z3))
def test_the_b2_liq_z3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count(name):
    signal_key, _, count = _B2_LIQ_Z3[name]
    trial, preflight = subjects.SUBJECTS[name], subjects.SUBJECTS[f"{name}-preflight"]
    builder = f"_build_{name.replace('-', '_')}"
    assert (trial.name, trial.intervals, trial.assets, trial.spec, trial.seeds) == (
        name,
        (240,),
        _B2_ASSETS,
        _B2_LIQ_Z3_SPEC,
        (42, 7, 1234),
    )
    assert trial.build is getattr(subjects, builder) and trial.metric_keys == _overlay_metric_keys(signal_key)
    assert (trial.verdict, trial.no_verdict, trial.incumbent) == (subjects._b2_overlay_verdict, _B2_OVERLAY_NO_VERDICT, None)
    assert (trial.family, trial.n_trials) == ("B2", count)
    assert (preflight.name, preflight.intervals, preflight.assets, preflight.spec, preflight.seeds) == (
        f"{name}-preflight",
        (240,),
        _B2_ASSETS,
        _B2_LIQ_Z3_SPEC,
        (42,),
    )
    assert preflight.build is getattr(subjects, f"{builder}_preflight")
    assert preflight.metric_keys == _overlay_preflight_keys(signal_key)
    assert (preflight.verdict, preflight.no_verdict, preflight.incumbent, preflight.family, preflight.n_trials) == (None,) * 5


@pytest.mark.parametrize("name", sorted({*_B2_LIQ_Z3, *(f"{name}-preflight" for name in _B2_LIQ_Z3)}))
def test_each_b2_liq_z3_subject_builds_on_the_specs_signal_threshold_and_count(monkeypatch, name):
    trial = name.removesuffix("-preflight")
    signal_key, threshold, count = _B2_LIQ_Z3[trial]
    compute = subjects._b2_overlay_metrics if name == trial else subjects._b2_overlay_preflight_metrics
    builds = []
    monkeypatch.setattr(subjects, "_b2_overlay_build", lambda *arguments: builds.append(arguments) or {})
    reader, window = object(), ("2024-01-01", "2024-06-30")

    subjects.SUBJECTS[name].build(reader, "ohlc-test", window, as_of="2026-10-03", accept_holes=True)

    instrument = (name, signal_key, subjects._b2_liq_signal, threshold, compute, count)
    assert builds == [(*instrument, reader, "ohlc-test", window, "2026-10-03", True)]
    assert type(builds[0][3]) is float


@pytest.mark.parametrize("name", sorted(_B2_LIQ_Z3))
def test_the_b2_liq_z3_preflight_halves_above_its_threshold_and_never_builds_arm_b(tmp_path, monkeypatch, name):
    signal_key, threshold, count = _B2_LIQ_Z3[name]
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)

    def refused(*args, **kwargs):
        raise AssertionError("the pre-flight built arm B's positions or read the engagement rule")

    monkeypatch.setattr(subjects, "scale_positions", refused)
    monkeypatch.setattr(subjects, "_b2_engagement_threshold", refused)
    scalings = _recording(monkeypatch, "derisk_scales", lambda arguments, result: result)
    bars = _recording(monkeypatch, "a1_kill_bar", lambda arguments, result: result)

    metrics = subjects.SUBJECTS[f"{name}-preflight"].build(ObservedReader(_b2_overlay_dataset(tmp_path)), "ohlc-test", None)

    ((scaled, _),) = scalings
    assert scaled["config"] == B2Config(z_threshold=threshold) and metrics["threshold"] == threshold
    assert [arguments["n_trials"] for arguments, _ in bars] == [count]
    assert set(metrics) == _overlay_preflight_keys(signal_key)
    assert metrics["engaged_per_asset"][_B2_NEVER_SPIKES] == 0 < sum(metrics["engaged_per_asset"].values())
    assert sum(metrics["engaged_per_asset"].values()) == sum(metrics["engaged_per_year"].values())


@pytest.mark.parametrize("name", sorted({*_B2_LIQ_Z3, *(f"{name}-preflight" for name in _B2_LIQ_Z3)}))
def test_a_b2_liq_z3_subject_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
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


@pytest.mark.parametrize("name", sorted(_B2_LIQ_Z3))
@pytest.mark.parametrize("plain", [True, False], ids=["plain-eval", "another-count"])
def test_the_b2_liq_z3_trial_refuses_a_plain_eval_and_another_count_before_any_read(tmp_path, monkeypatch, name, plain):
    count = _B2_LIQ_Z3[name][2]
    _anchor(monkeypatch, tmp_path / "no-data", tmp_path / "registry.jsonl")
    reads = _recording(monkeypatch, "_b2_overlay_inputs", lambda arguments, result: result)
    flags = [] if plain else ["--register", "--iteration", "iter-187", "--family", "B2", "--n-trials", str(count + 1)]
    refused = (
        f"{name} declares a verdict rule, so every run of it is a trial: run it with --register"
        if plain
        else f"--n-trials {count + 1} is not {count}, the count {name} declares and deflates at: pass --n-trials {count}"
    )

    result = runner.invoke(app, ["research", "eval", "--subject", name, "--dataset", "ohlc-test", *flags])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert refused in result.output and reads == []
```

  - `_RULED_FIXTURES` gains `"b2-liq-z3-derisk": _b2_overlay_dataset,` after `"b2-liq-reentry": _b2_reentry_dataset,`; `_DECLARED_COUNT` gains `"b2-liq-z3-derisk": "_B2_LIQ_Z3_N_TRIALS",` after `"b2-liq-reentry": "_B2_LIQ_REENTRY_N_TRIALS",`; the literal of `test_the_ruled_subjects_declare_their_families_and_trial_counts` gains `"b2-liq-z3-derisk": ("B2", 7),` after `"b2-liq-reentry": ("B2", 5),`; `_CONTRACT_DATASETS` gains, after its `"b2-rerisk-reading"` entry:

```python
    "b2-liq-z3-derisk": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
    "b2-liq-z3-derisk-preflight": lambda tmp_path, subject: (_b2_overlay_dataset(tmp_path), _B2_START),
```

  **Author's call** — the tests hold the wrappers, not the machinery: `_b2_overlay_build`, `_b2_overlay_inputs`, `_b2_overlay_metrics`, `_b2_overlay_preflight_metrics` and `_b2_overlay_verdict` are record 54's, their own tests spec 00138's plan's (retired with record 54's subjects, run nightly), and spec 00143 D5 changes none of them. So the builds test records `_b2_overlay_build`'s arguments and holds each wrapper, trial and twin alike, to the spec's instrument — its name, key, signal reader, threshold, compute and count — the threshold a `float` equal to 3.0, so the engagement rule, a callable, cannot stand in its place; the pre-flight test runs the twin end to end over `_b2_overlay_dataset` under argument-derived stand-ins for the bars and the benchmark, with `scale_positions` and `_b2_engagement_threshold` refusing to be called, and reads the recorded `derisk_scales` config, so 3.0 reaching the scales is proven through the build the twin runs; the shared rows — the contract, tracked-spec, shared-defaults and deflation rows, which `_RULED_FIXTURES`, `_DECLARED_COUNT` and `_CONTRACT_DATASETS` reach — run both subjects end to end on the fixture, the trial's arm B and bar among them. Every new function is parametrised by the subject's name, so `tests/retired_subjects.py`'s hook marks each case `retired` once Task 5 retires the two names, and no function needs the mark by hand. The instrument a subject runs on — its signal reader, threshold, compute and count — is fixed by the spec's D3–D5 and written in this plan's code in three places: the two `_build_` wrappers, the tests' `_B2_LIQ_Z3` and Task 2's `THRESHOLD`; the builds test holds the wrappers to `_B2_LIQ_Z3`, Task 2's case holds `THRESHOLD` to the measured basis, and the pre-flight's (c) holds the twin's wrapper, and through the builds test its trial's, to the same basis before the trial's `--register`. Its threshold is written in words in five more, which no test, data case or pre-flight step holds, a read against D3 their only check: the Global Constraints' first item, the README row (step 4), the conventions entry (Task 2 step 5), the trial's notes (Task 4 step 4), its record's `notes` once the run appends it.

- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00143 && uv run pytest tests/test_research_command.py -k "liq_z3 or ruled_subjects_declare or declares_the_metric_keys" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00143/pt`: collection completes and every selected case fails at its call — on a key `SUBJECTS` lacks, a subject the CLI does not know, or the families literal `SUBJECTS` does not yet hold (measured on the authoring tree against the base module: `10 failed, 737 deselected`).
- [ ] **Step 3: Implement in `cli/research/subjects.py`** — after `_b2_overlay_preflight_keys` and before the comment `# docs/specs/00139 D3-D6: B2's trials 6-7.`, two blank lines either side, as between the module's top-level blocks:

```python
# docs/specs/00143 D3-D5: B2's trial 8, trial 5's daily long-side liquidation de-risk at the threshold one step up.
_B2_LIQ_Z3_THRESHOLD = 3.0
_B2_LIQ_Z3_N_TRIALS = 7  # docs/specs/00143 D4: fixed by the spec's hash; a different count is a new subject


def _build_b2_liq_z3_derisk(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-liq-z3-derisk",
        "binperp_liq_long_z30d",
        _b2_liq_signal,
        _B2_LIQ_Z3_THRESHOLD,
        _b2_overlay_metrics,
        _B2_LIQ_Z3_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )


def _build_b2_liq_z3_derisk_preflight(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    return _b2_overlay_build(
        "b2-liq-z3-derisk-preflight",
        "binperp_liq_long_z30d",
        _b2_liq_signal,
        _B2_LIQ_Z3_THRESHOLD,
        _b2_overlay_preflight_metrics,
        _B2_LIQ_Z3_N_TRIALS,
        reader,
        dataset,
        window,
        as_of,
        accept_holes,
    )
```

  and `SUBJECTS` gains, after its `"b2-rerisk-reading"` entry and before its closing `}`:

```python
    "b2-liq-z3-derisk": Subject(
        "b2-liq-z3-derisk",
        (240,),
        _ASSETS,
        _build_b2_liq_z3_derisk,
        spec="docs/specs/00143-b2-liq-derisk-threshold-design.md",
        metric_keys=_b2_overlay_metric_keys("binperp_liq_long_z30d"),
        seeds=(42, 7, 1234),
        verdict=_b2_overlay_verdict,
        no_verdict=(
            "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, "
            "the trial unspent"
        ),
        family="B2",
        n_trials=_B2_LIQ_Z3_N_TRIALS,
    ),
    "b2-liq-z3-derisk-preflight": Subject(
        "b2-liq-z3-derisk-preflight",
        (240,),
        _ASSETS,
        _build_b2_liq_z3_derisk_preflight,
        spec="docs/specs/00143-b2-liq-derisk-threshold-design.md",
        metric_keys=_b2_overlay_preflight_keys("binperp_liq_long_z30d"),
        seeds=(42,),
    ),
```

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row: `) or \`b2-rerisk-reading\` (` becomes `), \`b2-rerisk-reading\` (`, and the row's closing `` `--reading`). | `` becomes:

```markdown
`--reading`), `b2-liq-z3-derisk` (the A2 4h ensemble against the same ensemble halved per asset while the 30-day z-score of that asset's daily long-side liquidated notional, a day read once it has ended, exceeds 3; the 4h series of `--dataset`, a frozen set only, and the `liquidations-daily` set read whole) or `b2-liq-z3-derisk-preflight` (that comparison's instrument check: the unconditioned ensemble's figures and bar and the stamps the halving engages, with no return of the halved book; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: `tests/slow-cases.txt`** — gains at their `sorted()` places the shared rows measured at 10 s or more on the authoring tree (call time; the twin's evaluates row measured 9.92 s and is left off, as record 54's twin's is):

```text
tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b2-liq-z3-derisk]
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-liq-z3-derisk-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-liq-z3-derisk-preflight]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-liq-z3-derisk]
```

  A case that times at 10 s or more on the implementer's own run and is not listed joins the list; a listed one under 10 s stays (`tests/test_slow_cases.py` passes).
- [ ] **Step 6: Run them to verify they pass** — step 2's command, measured `10 passed, 755 deselected` (about 7 s); then the shared rows, `mkdir -p .tmp/plan-00143 && uv run pytest tests/test_research_command.py -k "b2-liq-z3-derisk and not liq_z3" -m "not data" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00143/pt`, one plain blocking call, `timeout` 600000 ms (measured `19 passed, 746 deselected` in 96.79 s, the shared-defaults rows 31.78 s and 19.72 s, the trial's evaluates row 17.02 s, its deflation row 13.67 s, every other under 10 s).
- [ ] **Step 7: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the Global Constraints' `T` over the four paths in its three parts (measured on the authoring tree: `596 passed, 169 deselected in 493.23s`, `71 passed, 694 deselected in 89.48s`, and the other thirty-five direct readers `4114 passed, 61 deselected in 114.68s`, Task 2's data-gated case among the deselected); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 8: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured on the authoring tree, twelve of twelve); the shared-defaults, evaluate, deflate, contract, tracked-spec and metric-keys rows and the ruled-subjects literal are new rows of existing tests, not new guards, and are not probed:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_z3_derisk(/def _build_b2_liq_z3_derisk_gone(/' --mutation '/"b2-liq-z3-derisk-preflight": Subject(/,/^    ),/s/metric_keys=_b2_overlay_preflight_keys("binperp_liq_long_z30d"),/metric_keys=_b2_overlay_metric_keys("binperp_liq_long_z30d"),/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_liq_z3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b2-liq-z3-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_z3_derisk(/def _build_b2_liq_z3_derisk_gone(/' --mutation 's/^_B2_LIQ_Z3_N_TRIALS = 7 /_B2_LIQ_Z3_N_TRIALS = 6 /' -- uv run pytest 'tests/test_research_command.py::test_the_b2_liq_z3_pair_declares_the_4h_grid_the_specs_keys_and_seeds_and_the_trial_alone_a_rule_and_a_count[b2-liq-z3-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_z3_derisk(/def _build_b2_liq_z3_derisk_gone(/' --mutation 's/^_B2_LIQ_Z3_THRESHOLD = 3.0$/_B2_LIQ_Z3_THRESHOLD = 2.5/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_liq_z3_subject_builds_on_the_specs_signal_threshold_and_count[b2-liq-z3-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_z3_derisk(/def _build_b2_liq_z3_derisk_gone(/' --mutation '/^def _build_b2_liq_z3_derisk(/,/^def /s/        _B2_LIQ_Z3_THRESHOLD,/        _b2_engagement_threshold,/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_liq_z3_subject_builds_on_the_specs_signal_threshold_and_count[b2-liq-z3-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_z3_derisk(/def _build_b2_liq_z3_derisk_gone(/' --mutation '/^def _build_b2_liq_z3_derisk(/,/^def /s/        _B2_LIQ_Z3_N_TRIALS,/        _B2_LIQ_N_TRIALS,/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_liq_z3_subject_builds_on_the_specs_signal_threshold_and_count[b2-liq-z3-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_z3_derisk_preflight(/def _build_b2_liq_z3_derisk_preflight_gone(/' --mutation '/^def _build_b2_liq_z3_derisk_preflight(/,/^def /s/        _b2_overlay_preflight_metrics,/        _b2_overlay_metrics,/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_liq_z3_subject_builds_on_the_specs_signal_threshold_and_count[b2-liq-z3-derisk-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_z3_derisk_preflight(/def _build_b2_liq_z3_derisk_preflight_gone(/' --mutation '/^def _build_b2_liq_z3_derisk_preflight(/,/^def /s/        _b2_liq_signal,/        _b2_oi_signal,/' -- uv run pytest 'tests/test_research_command.py::test_each_b2_liq_z3_subject_builds_on_the_specs_signal_threshold_and_count[b2-liq-z3-derisk-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_z3_derisk_preflight(/def _build_b2_liq_z3_derisk_preflight_gone(/' --mutation '/^def _build_b2_liq_z3_derisk_preflight(/,/^def /s/        _B2_LIQ_Z3_THRESHOLD,/        2.5,/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_liq_z3_preflight_halves_above_its_threshold_and_never_builds_arm_b[b2-liq-z3-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_z3_derisk(/def _build_b2_liq_z3_derisk_gone(/' --mutation '/^def _build_b2_liq_z3_derisk(/,/^def /s/        as_of,/        None,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_liq_z3_subject_refuses_as_of_before_any_read[b2-liq-z3-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_z3_derisk_preflight(/def _build_b2_liq_z3_derisk_preflight_gone(/' --mutation '/^def _build_b2_liq_z3_derisk_preflight(/,/^def /s/        as_of,/        None,/' -- uv run pytest 'tests/test_research_command.py::test_a_b2_liq_z3_subject_refuses_as_of_before_any_read[b2-liq-z3-derisk-preflight]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_z3_derisk(/def _build_b2_liq_z3_derisk_gone(/' --mutation '/"b2-liq-z3-derisk": Subject(/,/^    ),/s/verdict=_b2_overlay_verdict,/verdict=None,/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_liq_z3_trial_refuses_a_plain_eval_and_another_count_before_any_read[plain-eval-b2-liq-z3-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_liq_z3_derisk(/def _build_b2_liq_z3_derisk_gone(/' --mutation '/"b2-liq-z3-derisk": Subject(/,/^    ),/s/n_trials=_B2_LIQ_Z3_N_TRIALS,/n_trials=8,/' -- uv run pytest 'tests/test_research_command.py::test_the_b2_liq_z3_trial_refuses_a_plain_eval_and_another_count_before_any_read[another-count-b2-liq-z3-derisk]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

- [ ] **Step 9: Commit** — `feat(research): B2 trial 8's subjects — the daily long-side liquidation de-risk at threshold 3.0 and its pre-flight twin on a frozen set's full history`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 2: the data-gated basis test, the decisions-log entries before the hash, the reads (D1, D6)

**Files:** Create `tests/test_research_b2_liq_derisk_threshold_basis.py` (module-marked `data`); modify `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 5's own commit.

**Interfaces:** Consumes Task 1's subject name and `_b2_overlay_inputs`, `_b2_liq_signal`, `_b2_overlay_start`, `_b2_overlay_engagement` and `book_turnover`; `cli.alpha.b2`'s `B2Config`, `derisk_scales`, `per_year_engaged_counts`, `per_year_positions_differ` and `scale_positions`; `tests.skip_gates.nothing_found_under`; `tests.test_trial_registry_provenance._trials`. Produces one test and the module names `BLOCK`, `VOUCHED`, `START`, `THRESHOLD`, `SIGNAL_KEY`, `ENGAGED_PER_ASSET`, `ENGAGED_PER_YEAR`, `POSITIONS_DIFFER`, `TURNOVER_B`, `trial_inputs()` and `coverage()`, which Task 3's check programs import. No test computes a bar or a return of either arm.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis, the coverage read off record 54:

```python
"""B2 trial 8's inputs half against spec 00143's measured basis: positions, scales and turnover, and no return of either
arm."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.alpha.b2 import B2Config, derisk_scales, per_year_engaged_counts, per_year_positions_differ, scale_positions
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _trials

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
# Copied from the spec's measured basis, never from a run.
_RETURN_INDICES = 27_337
BLOCK = "816f62f931468b96f39f6fcbbdbfeee5124fa64fb062a98554895870de30474f"
VOUCHED = {"liquidations-daily": "checked (10 vouched hashes)"}
# The signal's own start: its return index and close, and the returns from it.
START = (19_731, datetime(2022, 10, 11, tzinfo=UTC), 7_606)
THRESHOLD = 3.0
SIGNAL_KEY = "binperp_liq_long_z30d"
ENGAGED_PER_ASSET = {
    "ADA": 102,
    "AVAX": 109,
    "BTC": 109,
    "DOGE": 155,
    "DOT": 84,
    "ETH": 78,
    "LINK": 109,
    "LTC": 106,
    "SOL": 108,
    "XRP": 120,
}
ENGAGED_PER_YEAR = dict.fromkeys(map(str, range(2013, 2022)), 0) | {"2022": 67, "2023": 362, "2024": 363, "2025": 252, "2026": 36}
# Arm B's positions: the threshold moves both, never the counts above.
POSITIONS_DIFFER = 566
TURNOVER_B = 150.32


def trial_inputs():
    """The trial's inputs half over the real sets, with the reader that read them."""
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b2_overlay_inputs(
        "b2-liq-z3-derisk", subjects._b2_liq_signal, THRESHOLD, reader, "ohlc-full", None, False
    )


def coverage() -> dict[str, dict[str, list[int]]]:
    """The signal's per-asset, per-close-year coverage as record 54 stored it: the same block and signal."""
    return _trials()[54]["metrics"][f"{SIGNAL_KEY}_coverage"]


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-daily/*/daily.parquet"),
    reason="the frozen ohlc-full set or the frozen daily liquidations block is absent under data/",
)
def test_the_de_risk_at_3_0_reproduces_the_measured_basis_and_record_54_at_2_5():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = trial_inputs()
    assert compute_hash(reader.block()) == BLOCK
    assert {d: s for d, s in reader.vouched_status().items() if d != "ohlc-full"} == VOUCHED
    index, first, returns = START
    assert (len(inputs.close), inputs.close[index], subjects._b2_overlay_start(inputs)) == (_RETURN_INDICES, first, index)
    assert subjects._b2_overlay_engagement(inputs, SIGNAL_KEY) == {
        "engaged_per_asset": ENGAGED_PER_ASSET,
        "engaged_per_year": ENGAGED_PER_YEAR,
        f"{SIGNAL_KEY}_coverage": coverage(),
        "primary_returns": returns,
        "threshold": THRESHOLD,
    }
    arm_b = scale_positions(inputs.arm_a, inputs.scales)
    differ = per_year_positions_differ(inputs.arm_a, arm_b, inputs.close)
    assert (sum(differ.values()), round(subjects.book_turnover(arm_b), 2)) == (POSITIONS_DIFFER, TURNOVER_B)
    # Record 54's threshold over the same inputs gives its stored engagement, closes and turnovers.
    record_54 = _trials()[54]["metrics"]
    scales = derisk_scales(inputs.signal, config=B2Config(z_threshold=2.5))
    arm_b_54 = scale_positions(inputs.arm_a, scales)
    assert (
        per_year_engaged_counts(inputs.arm_a, scales, inputs.close),
        sum(per_year_positions_differ(inputs.arm_a, arm_b_54, inputs.close).values()),
        subjects.book_turnover(inputs.arm_a),
        subjects.book_turnover(arm_b_54),
    ) == tuple(record_54[key] for key in ("engaged_per_year", "stamps_positions_differ", "turnover_a", "turnover_b"))
```

  **Author's call** — the case holds the trial's inputs half to the basis at 3.0 and the same positions to record 54's stored figures at 2.5 — its `engaged_per_year`, `stamps_positions_differ`, `turnover_a` and `turnover_b`, each read off the committed record, never typed — so a change to the inputs half since record 54's run fails it whatever the 3.0 literals read; the coverage is record 54's stored one, the same block and signal, rather than a second typing of its 140 pairs.
- [ ] **Step 2: Run it** — with `data/ohlc-full` and `data/liquidations-daily` linked in this worktree: `mkdir -p .tmp/plan-00143 && uv run pytest tests/test_research_b2_liq_derisk_threshold_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00143/pt`, one plain blocking call, `timeout` 600000 ms: `1 passed`, never a skip (measured on the authoring tree, 70.77 s). The case joins `tests/slow-cases.txt` at its `sorted()` place:

```text
tests/test_research_b2_liq_derisk_threshold_basis.py::test_the_de_risk_at_3_0_reproduces_the_measured_basis_and_record_54_at_2_5
```

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b2_liq_derisk_threshold_basis.py tests/slow-cases.txt`; the Global Constraints' `T` over the two paths; the two tree walkers its skip gate and data mark meet, `mkdir -p .tmp/plan-00143 && uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00143/pt` (measured `325 passed`); `uv run pre-commit run -a` until clean. No probe: the case is slow, recorded `probe skipped: slow case`.
- [ ] **Step 4: Commit** — `test(research): B2 trial 8's inputs half against the measured basis — the block, the signal's start, the engagement at 3.0, arm B's positions and turnover, and record 54's figures at 2.5`, the message carrying the gate's result line, `probe skipped: slow case — tests/test_research_b2_liq_derisk_threshold_basis.py::test_the_de_risk_at_3_0_reproduces_the_measured_basis_and_record_54_at_2_5`, the line `It reads data/ohlc-full and data/liquidations-daily: re-run it with the two sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.` and the two trailer lines.
- [ ] **Step 5: The decisions-log entries, before the hash** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`, after one blank line, the owner's pick (spec 00143's ruling, D1) and then **Author's call** the trial's conventions, plan 00142's shape, so that both stand in the log before any return of arm B is read:

```markdown
[iter-187] B2's next step after the re-risk reading — hold B2 and the long-side liquidation de-risk one threshold step up, the owner's pick, attended, 2026-10-23 (Decision: 1)
  Said, attended, 2026-10-23, after reading 5 found no cell with potential, as readings 3 and 4 had before it: "hold B2, try the de-risk variant next". Asked which signal — the long-side liquidations of record 54, the funding of record 51, the open interest of record 52 or the ratios' maximum of record 53, each offered with its record's net, cost and gross loss — answered: "Long-side liq (Recommended)". Asked which knob — the four options below — answered: "Threshold up (Recommended)". The questions as first put misstated record 54's threshold as 2.0; record 54's metrics carry `threshold` 2.5, where spec 00138 D3's rule landed, so one step up is 3.0, not 2.5. Asked again with the step from 2.5, confirmed: "3.0, scale 0.5 (Recommended)". B2 is held and its close set aside. Standing and unchanged: the instrument ruling "Frozen ohlc-full (Recommended)".
  1. **The threshold one step up, the scale kept at 0.5** — spec 00143: record 54's de-risk at 3.0 on its instrument, signal, bar and matrix, count 7. It halves 1,080 of record 54's 1,750 engaged long asset-stamps and adds 2.83 % to arm A's turnover where record 54 added 4.45 % (spec 00143's measured basis); one B slot, 14 to 13. Chosen.
  2. **The scale 0.25 at record 54's 2.5** — the same 1,750 stamps cut to a quarter of arm A's position, each de-risk and re-risk a larger trade; one B slot.
  3. **Both knobs at once** — 3.0 and 0.25 together; one B slot, but a result that cannot say which knob moved it.
  4. **Two trials under one spec** — the threshold and the scale each its own trial under one review cycle; two B slots, 14 to 12.

[iter-187] B2 trial 8's conventions, pinned by spec 00143 before its hash (Decision: 1)
  The trial's details are fixed in the spec, reviewed, and frozen by its sha256, its record's `spec_hash`, before any return of arm B, head-to-head or bar leg of arm B is computed over the data; each call below is one the spec pins, the author's unless it names the ruling or the spec it carries, every value the owner or specs 00128, 00133, 00137 and 00138 fixed staying theirs.
  1. **As the spec pins them** — one trial, record 54's daily long-side liquidation de-risk one threshold step up, and its pre-flight twin, the owner's pick (D1); record 54's instrument, bar, arms and costing (D2); arm B at half arm A's position where `_b2_liq_signal`, record 54's signal unchanged, is strictly above 3.0, a pre-registered constant rather than spec 00138 D3's rule, which picks 2.5 on this block, the scale 0.5 the owner's (D3); the head-to-head and the drawdown pair from the signal's own start, record 54's index 19,731, spec 00138 D8's matrix through `_b2_overlay_verdict` itself, its park variants the scale 0.25 at 3.0 and the threshold 3.5, and the count 7, the family's true count with this trial, fixed by the hash (D4); the subjects `b2-liq-z3-derisk` and `b2-liq-z3-derisk-preflight`, named so that no registered or retired subject's name equals or opens either and neither opens one, the variant `B2-liq-z3-derisk-a2eq-full-v1`, the overlays' 42 and 22 keys, and the build two wrappers on the overlay machinery unchanged (D5); no `--verdict`, and notes naming only what is fixed before the run, spec 00133 D7's and spec 00137 D10's (D6); an adopt deployed on spec 00138 D11's B1 precedent (D7); the contamination stated — the trial reads record 54's instrument and signal, its engaged stamps a subset of record 54's, and was picked with record 54's REJECT and readings 3–5 known. Chosen.
  2. **The alternatives each weighed** — spec 00138 D3's engagement rule re-applied, which re-runs record 54; the scale 0.25, both knobs at once, or two trials under one spec (the pick above); a count raised in place; the name `b2-liq-derisk-z3`, which the retired `b2-liq-derisk` opens; a compute of the trial's own in place of the overlay machinery; metric keys of the trial's own.
  Source: spec 00143 (D1–D7), its **Author's call**s and the calls it carries from the owner and specs 00133, 00137 and 00138; the owner's words quoted in the pick above.
```

  staged alone, its gate `mkdir -p .tmp/plan-00143 && uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00143/pt` (measured in a scratch worktree, the two entries appended, `50 passed`) and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-187] B2's next step after the re-risk reading — the owner's pick, the long-side liquidation de-risk one threshold step up — and B2 trial 8's conventions, pinned by spec 00143 before its hash`. The pick's header is what T0023's `ripe_when` greps for (`B2.s next step after the re-risk reading`; measured in the scratch worktree, the check prints 1 once the entry stands); Task 5 gives T0023 its next trigger.
- [ ] **Step 6 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–2 and the two entries — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing computes arm B's returns, a head-to-head or a bar leg of arm B, or runs either subject over the real data, before the spec's hash, and the data-gated case runs with the frozen full set and the daily liquidation block linked into the reader's worktree and unlinked by the reader before its report, since unlinked it skips. Each report names the tip it read, the tip Task 3 step 1 diffs from. Task 3 waits until the trio has closed with no open Critical or Important.

## Task 3 (the controller's): the gate, the spec hash, the develop check, the data test and the check programs (D6)

- [ ] **Step 1: The gate** — each check its own call, each read before the next: the reads through Task 2 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00143-b2-liq-derisk-threshold-design.md docs/research/10.phase4-decisions.md` exits 0; the conventions entry against the spec at that tip, each item where the spec pins it and each call the spec carries under the ruling or spec it names; arm A's code path since this branch's cut — the spec's basis lists it from record 54's run to the cut — `git log --oneline 53e0b98c4..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/derivatives cli/liquidations cli/data uv.lock pyproject.toml .python-version`, lists Task 1's commit and its fixes alone; any other commit is named, step 4's data test deciding whether it moved the inputs half.
- [ ] **Step 2: D6 (1), the spec hash** — `sha256sum docs/specs/00143-b2-liq-derisk-threshold-design.md`; its value, pasted from that call, is the run's `--spec-hash` and the record's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D6 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0. A non-zero exit stops before the run: the controller reads which line moved, the same `git diff` without `--quiet`, and only for a line another writer appended legitimately — a registry record or a reading another branch's merged PR carries — merges develop, alone (`git merge --no-edit origin/develop`) — a conflict confined to `docs/research/10.phase4-decisions.md` or `tests/slow-cases.txt` resolved keeping both sides' lines, in the decisions log develop's entries above this branch's and in the slow-cases file each line at its `sorted()` place, and committed as the merge; a conflict in any other file aborted with `git merge --abort`, which stops the task, T0023's — then takes a delta read of the merge in place of re-running step 1: step 1's arm-A log over `<the tip the last read names>..HEAD`, then `pre-review`, then `review` over that range and `re-review` over a fix of it within the branch's two, each `drive` carrying Task 2 step 6's sentence with its "before the spec's hash" read "before Task 4's run", the commits the log lists, and one sentence more: develop's commits were each read on their own PR, so the read judges the merge's resolution and each listed commit's effect on the trial — whose tip becomes the tip the last read names, and step 4 runs on the merged tree. A B2 record another branch landed raises `required_n("B2")` above 7, and the run is then refused before its fit (D4): the trial stops, T0023's, a further count a new subject under a new spec. The check has two sites, this step and Task 4 step 1, and both take this path.
- [ ] **Step 4: D6 (3), the data test on the run's tree** — `mkdir -p .tmp/plan-00143 && ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b2_liq_derisk_threshold_basis.py -q -p no:cacheprovider --basetemp=.tmp/plan-00143/pt > .tmp/plan-00143/basis.out 2>&1`, one background call: `1 passed`, never a skip; a failure is an instrument finding before the pre-flight, T0023's.
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00143/preflight_check.py`, D6's (a)–(e) in order, exit 0 on a pass, else one `sys.exit` naming the step that stopped:

```python
"""Spec 00143 D6's pre-flight read, (a) to (e) in order: exit 0 on a pass, else the one sys.exit naming what stopped it."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from tests.test_research_b2_liq_derisk_threshold_basis import (
    BLOCK,
    ENGAGED_PER_ASSET,
    ENGAGED_PER_YEAR,
    SIGNAL_KEY,
    START,
    THRESHOLD,
    VOUCHED,
    coverage,
)

out = Path(".tmp/plan-00143/b2-liq-z3-derisk-preflight.out").read_text()
run = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
m, block = run["metrics"], run["datasets"]
print("block", compute_hash(block), run["vouched"])
if compute_hash(block) != BLOCK:
    sys.exit("(a) the inputs' block differs from the spec's")
if {d: s for d, s in run["vouched"].items() if d != "ohlc-full"} != VOUCHED:
    sys.exit("(a) the signal's set is not vouched as the spec reads it")
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
basis = {
    "engaged_per_asset": ENGAGED_PER_ASSET,
    "engaged_per_year": ENGAGED_PER_YEAR,
    f"{SIGNAL_KEY}_coverage": coverage(),
    "primary_returns": START[2],
    "threshold": THRESHOLD,
}
off = [key for key, value in basis.items() if m[key] != value]
if off:
    sys.exit(f"(c) the engagement, the coverage, the start or the threshold differs from the measured basis: {off}")
print("engaged", sum(m["engaged_per_asset"].values()), m["engaged_per_year"], "primary_returns", m["primary_returns"], "threshold", m["threshold"])
if not any(m["engaged_per_asset"].values()):
    sys.exit("(d) the overlay engages no stamp: the dead knob")
print({key: m[key] for key in ("dsr", "dsr_pass", "spa_p_value", "spa_pass", "cost_stress_pass", "worst_slice_pass", "passes")})
sys.exit(0 if m["passes"] == 1 else "(e) arm A fails its bar")
```

  and `.tmp/plan-00143/record_check.py`, the record's checks, its one argument the spec's sha256:

```python
"""Spec 00143 D5's record, read off the registry's last line against the run's print, its pre-flight's block and the
measured basis: exit 0 when every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b2_liq_derisk_threshold_basis import (
    ENGAGED_PER_YEAR,
    POSITIONS_DIFFER,
    SIGNAL_KEY,
    START,
    THRESHOLD,
    TURNOVER_B,
    coverage,
)

name, spec_hash = "b2-liq-z3-derisk", sys.argv[1]
r = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(f".tmp/plan-00143/{name}.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]["metrics"]
before = Path(f".tmp/plan-00143/{name}-preflight.out").read_text()
preflight_block = compute_hash(json.JSONDecoder().raw_decode(before, before.index("{"))[0]["datasets"])
subject = SUBJECTS[name]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
expected = (ENGAGED_PER_YEAR, coverage(), START[2], THRESHOLD, POSITIONS_DIFFER, TURNOVER_B)
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == preflight_block,
    "invocation": invocation
    == {"subject": name, "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["family"], r["n_trials_in_family"], r["variant"], r["iteration"], r["seeds"])
    == ("B2", 7, "B2-liq-z3-derisk-a2eq-full-v1", "iter-187", [42, 7, 1234]),
    "keys": set(m) == subject.metric_keys,
    "verdict": r["verdict"] == subject.verdict(m),
    "printed": printed == m,
    "engagement": (
        m["engaged_per_year"],
        m[f"{SIGNAL_KEY}_coverage"],
        m["primary_returns"],
        m["threshold"],
        m["stamps_positions_differ"],
        round(m["turnover_b"], 2),
    )
    == expected,
    "attempt": r["attempt"]["absorbs"] == [],
}
print(r["trial_id"], r["verdict"], checks, "counted", r["attempt"]["counted"])
sys.exit(0 if all(checks.values()) else 1)
```

  Each is written with `mkdir -p .tmp/plan-00143 && cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00143/preflight_check.py .tmp/plan-00143/record_check.py`.

## Task 4 (the controller's): trial 8 — its pre-flight, its run and its record (D3–D6)

`<H>` is Task 3 step 2's sha256.

- [ ] **Step 1: The develop check** — Task 3 step 3 whole, its stop, its merge path and Task 3 step 4 after a merge with it; `git status --short` prints nothing.
- [ ] **Step 2: The pre-flight** — `mkdir -p .tmp/plan-00143 && uv run zcrypto research eval --subject b2-liq-z3-derisk-preflight --dataset ohlc-full > .tmp/plan-00143/b2-liq-z3-derisk-preflight.out 2>&1`, a plain eval of a subject with no rule, under the trial's 242 s (the spec's basis), one background call; at its notification and on its exit 0, `uv run python .tmp/plan-00143/preflight_check.py`. Exit 0: step 4. A `sys.exit` message naming one of (a)–(e): D6's instrument finding, step 3. A traceback, or a refusal before the build, is a code or environment fault, the step stopped and T0023's with its line; a refused build — exit 1 with no traceback, its output naming `b2-liq-z3-derisk-preflight over the full history: …` or a file of `liquidations-daily` — prints no metrics, keeps no reading, and is recorded in Task 5's T0023 findings with its line quoted, the trial unspent.
- [ ] **Step 3: On a stop, the reading** — `mkdir -p .tmp/plan-00143 && uv run zcrypto research eval --subject b2-liq-z3-derisk-preflight --dataset ohlc-full --reading --iteration iter-187 --spec-hash <H> --notes "B2 trial 8's pre-flight (spec 00143 D6): <the check's sys.exit line, quoted>; no verdict, the trial unspent" > .tmp/plan-00143/b2-liq-z3-derisk-reading.out 2>&1`, one background call; then step 6's stop arm.
- [ ] **Step 4: The trial** — one run: `mkdir -p .tmp/plan-00143 && uv run zcrypto research eval --subject b2-liq-z3-derisk --dataset ohlc-full --register --iteration iter-187 --family B2 --n-trials 7 --variant B2-liq-z3-derisk-a2eq-full-v1 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00143/b2-liq-z3-derisk.out 2>&1`, about four minutes (record 54's run took 242 s, the spec's basis), one background call, `cat` at its notification. No `--verdict` and no plain eval, before or after. The notes, written before the run, name only what is fixed before it: `subject b2-liq-z3-derisk over ohlc-full, full history, no as-of; arm A the adopted equal-weight A2 4h ensemble, arm B the same ensemble at half its position on an asset while the 30-day z-score of that asset's daily long-side liquidated notional (Coinalyze's daily history of <COIN>USDT_PERP.A, frozen as liquidations-daily, a day read from the first close at or after its end) exceeds 3.0, a pre-registered constant one step up from record 54's 2.5, no hold-through, every position change charged 0.006 per side; the hypothesis: the half-scale improves the ensemble's net-of-cost performance through a lower drawdown at the engaged stamps, against the unconditioned ensemble; n_trials 7, var_trials 0.0, the DSR leg binding; the head-to-head from the first close every asset's signal holds (index 19731, 2022-10-11 00:00) decides, the full-window read beside it; pre-flight: block 816f62f9…, arm A <the seven anchors>, passes 1, engaged <the total> (<the per-year counts>); park variants, pre-registered: scale 0.25 at 3.0, threshold 3.5; the matrix pre-registered by the spec's sha256 <H>`. A refusal from the count — an orphan, a B2 record landed elsewhere, or bucket B spent — comes before the fit or after the print, naming each orphan, the count or the bucket's figure: no record, no reading; T0023 carries it (Task 5). A stop by the rule writes a reading carrying its attempt, which counts 0: step 6's stop arm. On any other exit — a refused build, a traceback, a signal, a refusal after the print — the attempt check runs, `uv run python -c 'import json; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; a = [x for x in lines if x["kind"] == "begin" and x["invocation"]["subject"] == "b2-liq-z3-derisk"][-1]["attempt"]; print(a, [x["failed"] for x in lines if x["kind"] == "end" and x["attempt"] == a] or "open")'`: a refused build ends its attempt failed, counting 0, recorded in T0023 with its line, the trial unspent; any other `failed` text, `open`, or `<id> [None]` stops the task, T0023's with the end of the run's output quoted whole.
- [ ] **Step 5: The record's checks** — on a record: `uv run python .tmp/plan-00143/record_check.py <H>` exits 0; its printed `counted` is read, never checked: T0016's line takes every orphan off the count (Task 5 step 2). A failed check stops the task before step 6.
- [ ] **Step 6: The records commit** — on a record: (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-187] Verdict — B2 trial 8 <ADOPT, PARK or REJECT> (registry trial <its trial_id>, family B2 n=7)`, plus `(attempts counted: <log8>#<id>, …)` when the record's `attempt.counted` lists an entry, its text to its first `. ` holding no other verdict word; the body: the matrix row that fired, read off the record's stored keys beside its stored verdict with D4's table (`sed -n '/^| Kill bar/,/^  The rows are disjoint/p' docs/specs/00143-b2-liq-derisk-threshold-design.md`), with `passes`, `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary` and `max_drawdown_reduction_pct` unrounded, `max_drawdown` beside `arm_a_max_drawdown`, the full-window pair beside them; `n_trials` 7, `var_trials` 0.0 and the DSR leg (`dsr_corrected`, `dsr_pass`); the pre-flight's block, anchors and `passes` from `.tmp/plan-00143/b2-liq-z3-derisk-preflight.out`; the engagement proof — `engaged_per_year`, `primary_returns`, `threshold`, `stamps_positions_differ`, `turnover_a` beside `turnover_b`; on a park its variants; on an adopt D7's path in its order; on a reject the hypothesis as the notes word it, archived — in the form of `[iter-182] Verdict — B2 trial 5 REJECT`; (ii) in `tests/test_trial_registry_provenance.py`, `LANDED_N_TRIALS` and the literal `test_each_landed_subjects_n_trials_is_frozen_at_its_literal` asserts each gain `"b2-liq-z3-derisk": 7,` after `"b2-funding-reentry": 6,`; (iii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<its trial_id>]` at its `sorted()` place; on an adopt, (iv) T0123's `ripe_when` gains `— registry trial <N>, B2 trial 8's ADOPT on the A2 ensemble alone, ripens this only once the P1 combination trial over record 47's book that carries it adopts` (D7), and `uv run python infra/scripts/topics-index.py` re-renders `docs/open-topics/README.md`, staged with it. Then `T` over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path — `tests/test_open_topics_frontmatter.py` among the index's readers on an adopt; `uv run pre-commit run -a` until clean, its rewrites staged. In the probe worktree, which the Global Constraints' probe setup creates from that index and whose tree it prints, `data/ohlc-full` and `data/liquidations-daily` linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/<set> .tmp/plan-00143/probe/data/<set>`, unlinked after the replay and the probe and the worktree removed as the Global Constraints' probe paragraph removes one that held a link: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'trial-<its trial_id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt` passes, one background call, its result line and call time for the message — a difference stops the task; then the literal's probe, expected `KILLED` (its two seds dry-run on the authoring tree, each changing one line): `infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_overlay_verdict(/def _b2_overlay_verdict_gone(/' --mutation 's/^_B2_LIQ_Z3_N_TRIALS = 7 /_B2_LIQ_Z3_N_TRIALS = 8 /' -- uv run pytest tests/test_trial_registry_provenance.py::test_each_landed_subjects_n_trials_is_frozen_at_its_literal -q -p no:cacheprovider --basetemp=.tmp/pt`. Commit that index, with no `git add` after the setup, as `docs(research): B2 trial 8 registered — <verdict>, the daily long-side liquidation de-risk at threshold 3.0 on the A2 ensemble, registry trial <N>`, the message carrying the tie and provenance tests' result line, the replay's with its call time, `Probed on this commit's tree, committed in a detached scratch worktree (tree <T>):`, the literal's `infra/scripts/mutate-probe.sh` command and its verdict line, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-<N>]`, the line `The replay reads data/ohlc-full and data/liquidations-daily: re-run it with the two sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.`, and the two trailer lines; after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.

  On a stop (step 3, or the rule's stop under `--register`): the ledger's last line is checked — its subject `b2-liq-z3-derisk-preflight` with outcome `null`, or `b2-liq-z3-derisk` with the `no_verdict` text and a non-null `attempt`; its `spec_hash` `<H>`; its metrics the run's printed ones — the entry is `[iter-187] B2 trial 8 — instrument finding, the trial unspent (reading <its reading_id>)`, naming what failed, quoted; no literal; the slow row `[reading-<its id>]` when its replay's call runs 10 s or more; the replay `-k 'reading-<its id>'`; committed as `docs(research): B2 trial 8 — instrument finding, kept as reading <id>; no trial spent` with no probe. On a refusal from the count or a refused build: no commit here; Task 5 records it.

## Task 5: T0023, T0016, the index and the retirement of both subjects (D7)

**Files:** `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/retired_subjects.py`.

On an outcome with no line in the registry or the ledger — a refusal from the count or a refused build (Task 4 steps 2 and 4) — step 1's Findings bullet quotes the refused line whole from `.tmp/plan-00143/b2-liq-z3-derisk-preflight.out` or `.tmp/plan-00143/b2-liq-z3-derisk.out`, the trial unspent; step 2's B2 line names trial 8 not run, with no record; and step 4 does not run, since a later run still evaluates the subjects (`tests/retired_subjects.py`'s own rule), so step 5 stages the three `docs/open-topics/` paths alone and its message ends `trial 8 not run, its subjects kept`.

- [ ] **Step 1: T0023**, per `topic-ops`, every figure read off the committed record or reading and its entry: `## Findings so far` gains one bullet — `**B2 trial 8 <VERDICT> (iter-187, spec 00143, registry trial <N>).**` — with the row that fired and the engagement in one or two sentences, pointing at its decisions-log entry for the figures, or the instrument finding, or the refused line, the trial unspent; `## Done so far` gains **B2 trial 8 (iter-187, spec/plan 00143)**, naming the subjects `b2-liq-z3-derisk` and `b2-liq-z3-derisk-preflight` on the overlay machinery and the data-gated basis test `tests/test_research_b2_liq_derisk_threshold_basis.py`, and the record by id; `## Suggested next steps` replaces `(the loop's pick under a run instruction, else the owner's; a close is the owner's) B2's next step after the re-risk reading` with `(owner) B2's next step after trial 8` — the owner's family call, hold B2 with a further trial or close it, reading trial 8's verdict beside trials 2–7's and readings 3–5's: a park's variants (the scale 0.25 at 3.0, the threshold 3.5), the other de-risks' variants, the de-risks' and the re-entries' further legs, the re-entries' park variants (the threshold one step toward 0, the size halved), a trial on the tape, a follow-up reading 2's figures invite (the daily history reconciled with the tape, the reading at a later as-of or over a longer span, a per-side reading), a reading at another threshold, signal, horizon or state split, and a close of B2 — recorded as a `[iter-NNN] B2's next step after trial 8` entry; on an adopt, D7's path; `ripe_when` — on no adopt: ``an activity: the owner picks B2's next step after trial 8 — a further trial or closing the family — recorded in the decisions log; check: `grep -c -E '^\[iter-[0-9]+\] B2.s next step after trial 8' docs/research/10.phase4-decisions.md` prints at least 1``; on an adopt: ``an activity: the P1 combination trial over record 47's book carrying B2 trial 8's arm B is picked for an iteration; check: `cat docs/research/10.phase4-decisions.md docs/research/13.phase5-decisions.md | grep -c -E '^\[iter-[0-9]+\] [^.]*combination trial over record 47.s book'` prints at least 1``, each in the frontmatter's quoting, the check kept in its own backticks. The check is run as committed and prints 0.
- [ ] **Step 2: T0016** — its budget line's figures read off the count the bucket refusal reads, every orphan in it, `uv run python -c 'import json; from pathlib import Path; from cli.registry import attempts, budget; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])'` (at this branch's base it printed `{'B1': 5, 'B2': 6} remain 14 []`; on trial 8's record, with no orphan, it prints `{'B1': 5, 'B2': 7} remain 13 []`): the line reads `B1 spent <its B1>, B2 spent <its B2>, <its remain> remain`, each orphan it lists named on that line; its B2 line under `## Done so far` names trial 8 (iter-187, spec/plan `00143`) with its record and verdict.
- [ ] **Step 3: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 4: The retirement** — **Author's call**, `tests/retired_subjects.py`'s own rule: no trial still to run evaluates the two subjects, so `RETIRED_SUBJECTS` gains `"b2-liq-z3-derisk",` and `"b2-liq-z3-derisk-preflight",` after `"b2-rerisk-reading",`, its comment `# B2's finished trials and the readings beside them.` unchanged. Every test function Task 1 adds is parametrised by the subject's name, so the hook marks each case and no function carries the mark by hand; `test_each_subject_declares_the_metric_keys_its_build_returns` keeps its new lines, the subjects staying in `SUBJECTS`. `uv run pytest tests/test_research_command.py -m "not retired" --collect-only -q -p no:cacheprovider | grep -c -E "liq-z3|liq_z3"` prints 0 and the same under `-m retired` prints 27 (measured in the scratch worktree), and `mkdir -p .tmp/plan-00143 && uv run pytest tests/test_retired_subjects.py -q -p no:cacheprovider --basetemp=.tmp/plan-00143/pt` passes (measured `5 passed`).
- [ ] **Step 5: Gate and commit** — `git add` the four paths; `T` over them with `tests/test_open_topics_frontmatter.py` and `tests/test_retired_subjects.py` by path, in its three parts; `uv run pre-commit run -a` until clean; committed as `docs(open-topics): T0023 and T0016 after B2 trial 8; its two subjects retired`.

## Task 6 (the controller's): the change-index row, the read and the PR

- [ ] **Step 1: The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-187 — B2 trial 8: liquidation de-risk at 3.0` (65 characters by `printf '%s' <it> | wc -m`, under the cap), its own commit.
- [ ] **Step 2: The read** — the `pre-review` of Tasks 4–5's commits and the row's, then `review` over `<the tip the last read names>..HEAD`, and `re-review` over a fix of it within the branch's two, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated case and the replay the messages record run with the frozen full set and the daily liquidation block linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 3: The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the verdict or the stop, the pre-flight's output quoted whole in a fenced block (`.tmp/plan-00143/b2-liq-z3-derisk-preflight.out`), every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the last read names. Merged through `merge-pr`; before it, `git status --short --ignored` read, `.tmp/plan-00143` collected and removed, and `unlink data/ohlc-full`, `unlink data/liquidations-daily`, `unlink data/derivatives-funding` and `unlink data/derivatives-oi` run in this worktree and in each reader's checkout whose `data/` holds the link; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows the four sets still there.

Decisions log: the owner's pick and the conventions entry (Task 2 step 5), before the hash; the verdict or instrument-finding entry (Task 4 step 6), in its record's commit; B2's next step after trial 8 is the owner's, its entry a later branch's (T0023's trigger).
