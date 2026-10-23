# B2's re-risk reading — the twelve crowding signals' forward returns on frozen ohlc-full where arm A is long below its full-long size: the inputs with the full-long size, the reading subject, its run and its entry — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt tests/test_research_b2_rerisk_reading_basis.py docs/reference/reading-ledger.jsonl tests/retired_subjects.py docs/research/10.phase4-decisions.md docs/open-topics/T0023-b2-derivatives-data-sourcing.md docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/README.md docs/reference/change-index.md docs/specs/00142-b2-rerisk-reading-design.md docs/plans/00142-b2-rerisk-reading.md` prints `tier: full`, for `tests/test_research_command.py` "a test importing cli.alpha" and, once Task 3 has created it, `tests/test_research_b2_rerisk_reading_basis.py` "a test importing cli.registry.observed").

**Goal:** B2's re-risk reading (spec 00142) — arm A's full-long size rebuilt beside reading 3's arm A, and the flags and counts of the one state below it, in `cli/research/subjects.py`; one reading subject, `b2-rerisk-reading`, over readings 3's and 4's twelve signals; the data-gated test of its inputs; the loop's pick and the reading's conventions in the decisions log before the hash; the reading's one run, kept on the reading ledger and replayed; its finding, T0023, T0016 and the subject's retirement.

**Architecture:** no new module and no change to `cli/alpha/`. `cli/research/subjects.py` gains one reading machinery — the constants `_B2_RERISK_STATE`, `_B2_RERISK_TOLERANCE`, `_B2_RERISK_SIGNALS` and `_B2_RERISK_FAR`, `_B2ReriskInputs`, `_b2_full_long`, `_b2_rerisk_inputs`, `_b2_rerisk_flags`, `_b2_rerisk_counts`, `_b2_rerisk_metrics`, `_build_b2_rerisk_reading` and `_B2_RERISK_KEYS` — and one `SUBJECTS` entry; readings 3's and 4's readers, `_b2_overlay_inputs`, `full_long_sizes`, `_inverse_vol_weights`, `a2_book_returns`, `_b2_reading_forwards`, `stationary_bootstrap_blocks` and `event_contrast_blocks` are read as they are, and no import is added. Nothing writes a dataset.

**Tech Stack:** Python 3.14 through uv; polars; numpy; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00142-b2-rerisk-reading-design.md` — binding; D1–D9 are cited by name and the values below are copied from it. It reads spec 00139's full-long size, spec 00140's instrument, arm A, signals, tails and forwards, and spec 00141's signals, draw, block contrast and criterion, all frozen (records 55–56's and readings 3–4's `spec_hash`). **Iteration:** iter-186. **Topic:** T0023 under T0016. **Branch:** `research/iter-186-b2-rerisk-reading`, worktree `.claude/worktrees/iter186`, `data/ohlc-full`, `data/derivatives-funding`, `data/derivatives-oi` and `data/liquidations-daily` linked read-only from the main checkout. A choice this plan makes that the spec leaves open is marked **Author's call**. Every code fence below was cut from the files the author ran: the code and tests of Tasks 1–3 were written in this worktree and run green (`5 passed, 718 deselected` for Task 1's new cases, `7 passed, 731 deselected` for Task 2 step 6's selection and `2 passed` for its two fixture rows, `1 passed` for Task 3's data-gated case in 357 s), the gates and the cli diff measured, the slow cases timed; then each task's tree was rebuilt from the base and these fences and committed in turn in a detached scratch worktree, where the red readings were taken (Task 1 `5 failed, 718 deselected`, each on a name `subjects` lacks; Task 2 `7 failed, 722 deselected` over Task 1's code), Tasks 1–2's fifty-five probe rows ran, fifty-five of fifty-five `KILLED`, Task 3 step 5's two entries ran through the decisions-log tests (`50 passed`), Task 6 step 4's retirement was collected (no case of the subject under `-m "not retired"`, 20 under `-m retired`, `tests/test_retired_subjects.py` `5 passed`), and Task 4's two programs were parsed and run with their two input paths pointed at a synthetic ledger line and run print shaped as the reading's (every check true and exit 0, a wrong spec hash exit 1; the print 72 lines, nine `no row`); the files were then restored to the base before this plan was committed. Not run: the reading itself and its replay (Task 5), the topic edits (Task 6 steps 1–3) and the PR (Task 7).

## Global Constraints

- **The signals, the state, the tails and the forwards** (D3–D5): `_b2_rerisk_inputs` runs `_b2_overlay_inputs(subject, _b2_funding_signal, 2.0, reader, dataset, window, accept_holes)` for the union, its two window refusals and arm A; then `_b2_full_long(overlay.h4_prices)`, spec 00139 D3's size — `full_long_sizes(_inverse_vol_weights(fed, lookback=180), levels, _ASSETS)`, `levels` the three books' `vol_target_positions` from `a2_book_returns` over `fed = _ffill_btc(h4_prices)` with `_B2_A2_ARMS`' configs, `_b2_reentry_inputs`' own calls; then `_b2_oi_signal`, `_b2_ratio_signal`, `_b2_liq_signal`, `_b2_oi_log_delta_signal`, `_b2_oi_momentum_signal`, `_b2_ratio_signals` and `_b2_liq_side_signals` over its `h4_ts`, each unchanged, keyed in this order `binperp_funding_z30d`, `binperp_oi_z30d`, `binperp_ratio_max_z30d`, `binperp_liq_long_z30d`, `binperp_oi_log_delta_z30d`, `binperp_oi_momentum_z30d`, `binperp_count_toptrader_long_short_ratio_z30d`, `binperp_sum_toptrader_long_short_ratio_z30d`, `binperp_count_long_short_ratio_z30d`, `binperp_sum_taker_long_short_vol_ratio_z30d`, `binperp_liq_short_z30d` and `binperp_liq_total_z30d`; the state one, `below_full` — arm A's position `p` and its full-long size `f` with `0 < p < f − 1e-12`, `_B2_RERISK_TOLERANCE` — through `_b2_rerisk_flags` (an event past the tail below the size, another close where the signal is read, not past it, below the size, `None` elsewhere); the tails readings 3's at `_B2_READING_THRESHOLD = 2.0` (above, z > 2.0; below, z < −2.0); the forwards `_b2_reading_forwards` (`fwd_logret_4h`, `fwd_logret_24h`, `fwd_logret_96h`, `fwd_sumret_4h`, `fwd_sumret_24h`, `fwd_sumret_96h`), unchanged.
- **The contrast** (D6): one draw, `stationary_bootstrap_blocks(len(inputs.close), mean_block=102, n_resamples=40_000, seed=42)` — reading 4's own — then per signal and tail one `event_contrast_blocks(flags, forwards, blocks, far=(2.5 / 72, 100 - 2.5 / 72))` call over the six forward series, 24 in all; a row is `[events, others, mean after the events, mean after the others, difference, 2.5 %, 97.5 %, far low, far high]`, its first five entries `event_contrast_chunked`'s to the bit and its four bounds that contrast's to rounding.
- **The keys** (D7): 79 — `<signal key>_fwd_logret_<4·H>h` and `<signal key>_fwd_sumret_<4·H>h` for each signal and horizon, each `{tail: {"below_full": rows}}`, `events_per_asset`, `others_per_asset`, `threshold` 2.0, `full_long_tolerance` 1e-12, `mean_block` 102, `n_resamples` 40000, `far_percentiles` `[2.5 / 72, 100 - 2.5 / 72]`; the counts the measured basis's (Task 3's literals).
- **The criterion** (D8): read by Task 5's entry off the pooled rows, never by code; the subject has no rule, and no program of this plan judges a cell. Its floor and four legs are written in words in two places beside D8, which a read against D8 alone checks — the conventions entry (Task 3 step 5) and the run's notes (Task 5 step 2) — and the pooled-rows print (Task 4 step 5) carries every entry the floor and the legs read — the log forward's kept assets and events, its far bounds and difference, and the summed returns' mean after the events — beside the others. Every statement of a bound names its family, the log forward's or the summed returns'.
- **The hash rule** (D9): before Task 4 step 2 takes the spec's sha256, nobody computes a forward return over the real data or runs `b2-rerisk-reading` over the real sets; the data-gated test (Task 3) computes positions, the full-long size, signals, counts and the block, and no forward; no reader, reviewer or plan-review dispatch runs the subject over the real sets before the hash, and every read's dispatch carries this rule. The subject is evaluated over the real sets once, by Task 5's `--reading` run, never as a plain eval; after that run it is rebuilt over them only by its replay case in `tests/test_registry_replay.py`, wherever that case runs with the sets linked, as Task 5 step 5 and Task 7 step 2's reads run it.
- **Unchanged** (D7): every existing function of `cli/research/subjects.py` — readings 3's and 4's machinery among them — `cli/alpha/*`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/validation/*`, `cli/engine/*` and `cli/liquidations/*`; the subjects of trials 1–7 and of readings 1–4; any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-only $(git merge-base HEAD origin/develop) -- cli/` prints `cli/research/subjects.py` from Task 1 on, nothing else; `git diff -U0 $(git merge-base HEAD origin/develop) -- cli/ | grep -c '^-[^-]'` prints 0 — the file gains lines and loses none. Measured on the tasks' trees, the hunks: after Task 1 `@@ -3217,0 +3218,82 @@`; after Task 2 `@@ -3217,0 +3218,149 @@` and `@@ -3538,0 +3688,9 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00142-b2-rerisk-reading-design.md` after Task 4 step 2, nor specs 00128, 00131 and 00137–00141, nor the spec before then except a fix commit a read of Task 3 step 6 asks for; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Task 5 names it — and this plan never runs `--register`. Never `git stash`; no amend; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-full`, `data/derivatives-funding`, `data/derivatives-oi` and `data/liquidations-daily`, read-only links, never written under. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/`, a fleet host, docker, `kraken-cli`, the vault, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`. The reading, every test and every implementer step make no network call and no ssh connection; the controller's `git fetch origin develop` (Task 4 step 3, Task 5 step 1) and Task 7's `gh` calls, push and `merge-pr` are the exceptions.
- **Research only**: nothing is armed, deployed, converged, pinned, rolled out or dropped — no fleet host, image, unit, alert rule or dashboard is touched, and no step of this plan waits on a maintenance window or a converge gap.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 3 step 6's reads, Tasks 4–5 and Task 7, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the data test, the reading, the replay), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1, 2 and 6 and Task 3's steps 1–5.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00142 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00142/pt` (or a file, or `-k`): every `--basetemp` under `.tmp/plan-00142/` follows `mkdir -p .tmp/plan-00142 &&` in the same command, since pytest creates the base temp's leaf and never its parents. An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file, node id or `-k` selection into parts that cannot, each its own `--basetemp=.tmp/plan-00142/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `T=$(bash infra/scripts/consumers.sh --direct <each changed path> | sort -u)` and `[ -n "$T" ] && mkdir -p .tmp/plan-00142 && uv run pytest $T -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00142/pt`, never a bare `uv run pytest` and never `consumers.sh` with `2>/dev/null`; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. Every `T` holding `tests/test_research_command.py` runs it in three parts, each one plain blocking call under `-m "not slow and not data"`, `timeout` 600000 ms: `tests/test_research_command.py -k "not reentry"` (`--basetemp=.tmp/plan-00142/pt-1`, measured on the authoring tree, Tasks 1–3's code in it, `573 passed, 165 deselected in 466.78s`), `tests/test_research_command.py -k reentry` (`pt-2`, measured `71 passed, 667 deselected in 90.70s`) and the rest of `T` (`pt-3`). A commit message's test result line is a run over that commit's own tree.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
mkdir -p .tmp/plan-00142 &&
  test ! -e .tmp/plan-00142/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00142/probe HEAD &&
  git -C .tmp/plan-00142/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00142/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00142/probe/.tmp
```

  Then, from `.tmp/plan-00142/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, so it fails at import or at its call. A mutation whose text also stands in an existing function — readings 3's and 4's inputs and metrics share several lines with the new ones — carries the address of its own function's range, `/^def <name>(/,/^def /`, so its dry run changes one line. After the last verdict, `git worktree remove --force .tmp/plan-00142/probe` — a data link in it unlinked first, each removal of one that held a link followed by `ls -la /home/zhaow/Projects/zcrypto-kraken/data`, each set it linked still listed. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <the hash the setup printed>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.
- **The subject's name** (D2): `b2-rerisk-reading`, so its case ids open with a name no other subject's opens. Its parametrised rows' ids carry `b2-rerisk-reading`, hyphenated, so a bare `-k rerisk` selects them too; every selection of this plan keys on the underscored words of its own functions' names (`rerisk_reading_`, `rerisk_readings_`, `rerisk_flag`, `full_long_size_is_the_reentries`), which no hyphenated id carries, and names a parametrised row by its node id.

## Task 1: the inputs with the full-long size, and the flags and counts of the state below it, in `cli/research/subjects.py` (D3, D4, D7)

**Files:** Modify `cli/research/subjects.py`, `tests/test_research_command.py`.

**Interfaces:** Consumes `cli/research/subjects.py`'s `_b2_overlay_inputs`, `_B2OverlayInputs`, `_b2_funding_signal`, `_b2_oi_signal`, `_b2_ratio_signal`, `_b2_liq_signal`, `_b2_oi_log_delta_signal`, `_b2_oi_momentum_signal`, `_b2_ratio_signals`, `_b2_liq_side_signals`, `_B2_READING_THRESHOLD`, `_B2_READING_TAILS`, `_B2_A2_ARMS`, `_B2_LOOKBACK`, `PPY_4H`, `_ASSETS` and the names it imports (`a2_book_returns`, `A2Config`, `_inverse_vol_weights`, `full_long_sizes`, `_ffill_btc`), each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; in the tests, `_recording`, `_B2_ASSETS`, `_B2_READING_SIGNAL_KEYS` and `_B2_READING_2_SIGNAL_KEYS`. Produces `_B2ReriskInputs(h4_ts, h4_prices, close, arm_a, full_long, signals)`, `_b2_full_long(h4_prices) -> dict[str, list[float]]`, `_b2_rerisk_inputs(subject, reader, dataset, window, accept_holes) -> _B2ReriskInputs`, which Task 3's data-gated test reads, `_b2_rerisk_flags(signal, arm_a, full_long, tail) -> dict[str, list[bool | None]]` and `_b2_rerisk_counts(inputs) -> dict`, which Task 2 reads.

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`, after `test_the_second_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it` and before `def _ruled_signal(`:

```python
# Spec 00142's twelve signals, reading 3's four and then reading 4's eight, in the order its keys and its contrasts take them.
_B2_RERISK_SIGNAL_KEYS = (*_B2_READING_SIGNAL_KEYS, *_B2_READING_2_SIGNAL_KEYS)


def test_the_rerisk_readings_inputs_are_the_overlays_union_and_arm_a_its_full_long_size_and_each_signal_by_its_reader(monkeypatch):
    calls = []
    overlay = subjects._B2OverlayInputs(["ts"], {"BTC": [1.0]}, ["close"], {"BTC": [0.0]}, {"BTC": [-3.0]}, {"BTC": [0.5]}, 2.0)
    monkeypatch.setattr(subjects, "_b2_overlay_inputs", lambda *arguments: calls.append(arguments) or overlay)
    monkeypatch.setattr(subjects, "_b2_full_long", lambda h4_prices: calls.append(("_b2_full_long", h4_prices)) or "full long")
    ratios = {key: f"ratio {key}" for key in _B2_READING_2_SIGNAL_KEYS[2:6]}
    sides = {key: f"side {key}" for key in _B2_READING_2_SIGNAL_KEYS[6:]}
    singles = ("_b2_oi_signal", "_b2_ratio_signal", "_b2_liq_signal", "_b2_oi_log_delta_signal", "_b2_oi_momentum_signal")
    readers = {name: name for name in singles} | {"_b2_ratio_signals": ratios, "_b2_liq_side_signals": sides}
    for name, out in readers.items():
        monkeypatch.setattr(subjects, name, lambda reader, h4_ts, name=name, out=out: calls.append((name, reader, h4_ts)) or out)
    reader, window = object(), ("2024-01-01", "2024-06-30")

    inputs = subjects._b2_rerisk_inputs("b2-rerisk-reading", reader, "ohlc-test", window, True)

    assert calls == [
        ("b2-rerisk-reading", subjects._b2_funding_signal, 2.0, reader, "ohlc-test", window, True),
        ("_b2_full_long", overlay.h4_prices),
        *((name, reader, ["ts"]) for name in readers),
    ]
    signals = dict(zip(_B2_RERISK_SIGNAL_KEYS[:6], (overlay.signal, *singles))) | ratios | sides
    assert inputs == subjects._B2ReriskInputs(overlay.h4_ts, overlay.h4_prices, overlay.close, overlay.arm_a, "full long", signals)
    assert list(inputs.signals) == list(_B2_RERISK_SIGNAL_KEYS)


def test_the_rerisk_readings_full_long_size_is_the_reentries_own_over_rebuilt_books(monkeypatch):
    # Three assets over 420 closes, each swinging on its own period; BTC misses close 200, which the arms' BTC fill bridges,
    # and SOL opens at close 60.
    prices = {
        a: [100.0 * (1 + 0.1 * i) * math.exp(0.002 * k + 0.08 * math.sin(k / (9 + 4 * i))) for k in range(420)]
        for i, a in enumerate(("BTC", "ETH", "SOL"))
    }
    prices["BTC"][200] = None
    prices["SOL"][:60] = [None] * 60
    sizes = _recording(monkeypatch, "full_long_sizes", lambda arguments, result: result)

    full_long = subjects._b2_full_long(prices)

    fed = _ffill_btc(prices)
    levels = [
        a2_book_returns(
            fed,
            config=A2Config(
                lookbacks=lookbacks,
                short="off",
                target_vol=target_vol,
                vol_lookback=180,
                basket_lookback=180,
                periods_per_year=2190,
            ),
        )["vol_target_positions"]
        for lookbacks, target_vol in (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
    ]
    ((arguments, result),) = sizes
    assert arguments == {"weights": _inverse_vol_weights(fed, lookback=180), "levels": levels, "assets": _B2_ASSETS}
    assert full_long == result and all(any(v > 0 for v in full_long[a]) for a in prices)


# Arm A's full-long size 0.4 throughout; arm A below it by more than 1e-12 at 0-2 and 6-9, at it at 3, below it by 1e-13
# at 4 and flat at 5; the signal past +2 at 0, 3, 5 and 9, past -2 at 1 and 4, on +2 at 2, on -2 at 7, and unread
# at 6 and 8.
_RERISK_FULL_LONG = [0.4] * 10
_RERISK_ARM_A = [0.3, 0.2, 0.1, 0.4, 0.4 - 1e-13, 0.0, 0.3, 0.25, 0.35, 0.4 - 1e-11]
_RERISK_SIGNAL = [2.5, -2.5, 2.0, 3.0, -3.0, 2.5, None, -2.0, None, 2.5]


@pytest.mark.parametrize(
    ("tail", "expected"),
    [
        pytest.param("above", [True, False, False, None, None, None, None, False, None, True], id="above"),
        pytest.param("below", [False, True, False, None, None, None, None, False, None, False], id="below"),
    ],
)
def test_a_rerisk_flag_is_an_event_past_its_tail_below_full_long_another_read_close_below_it_and_none_elsewhere(tail, expected):
    flags = subjects._b2_rerisk_flags({"BTC": _RERISK_SIGNAL}, {"BTC": _RERISK_ARM_A}, {"BTC": _RERISK_FULL_LONG}, tail)

    assert flags == {"BTC": expected}


def test_the_rerisk_reading_counts_each_assets_events_and_others_below_full_long_per_signal_and_tail():
    # ETH's full-long size 0.26 leaves it below that size at 1, 2 and 7 alone.
    arm_a, full_long = {"BTC": _RERISK_ARM_A, "ETH": _RERISK_ARM_A}, {"BTC": _RERISK_FULL_LONG, "ETH": [0.26] * 10}
    signal = {"BTC": _RERISK_SIGNAL, "ETH": [2.5, 2.5, 3.0, 0.0, 0.0, 0.0, 0.0, -2.5, 0.0, 0.0]}
    inputs = subjects._B2ReriskInputs([], {}, [], arm_a, full_long, {"binperp_oi_z30d": signal})

    counts = subjects._b2_rerisk_counts(inputs)

    assert counts == {
        "events_per_asset": {
            "binperp_oi_z30d": {"above": {"below_full": {"BTC": 2, "ETH": 2}}, "below": {"below_full": {"BTC": 1, "ETH": 1}}}
        },
        "others_per_asset": {
            "binperp_oi_z30d": {"above": {"below_full": {"BTC": 3, "ETH": 1}}, "below": {"below_full": {"BTC": 4, "ETH": 2}}}
        },
    }
```

  **Author's call** — the inputs test runs `_b2_rerisk_inputs` under stand-ins for `_b2_overlay_inputs`, `_b2_full_long` and the seven later readers, reading the calls' order and arguments and the inputs' fields off sentinels, since the real inputs over the fixture take seconds a reader and the readers are readings 3's and 4's own, proven by their retired cases; the full-long test runs `_b2_full_long` itself over three synthetic assets' 420 closes — in under a second, where the fixture's union takes about 14 s and would make it a slow case no probe reaches — against the books and weights rebuilt from spec 00139's literals, the re-entry test's own oracle; the flags and counts tests read hand-built rows, their fixture placing arm A at 1e-13 and 1e-11 below its size so that the tolerance's two directions part.
- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00142 && uv run pytest tests/test_research_command.py -k "rerisk_readings_inputs or full_long_size_is_the_reentries or rerisk_flag or rerisk_reading_counts" -q -p no:cacheprovider --basetemp=.tmp/plan-00142/pt`: collection completes and every selected case fails at its call on a name `subjects` lacks — `_b2_full_long`, `_b2_rerisk_flags`, `_B2ReriskInputs` (measured on the base: `5 failed, 718 deselected`).
- [ ] **Step 3: Implement** — in `cli/research/subjects.py`, after `_B2_READING_2_KEYS` and before `SUBJECTS: dict[str, Subject] = {`, two blank lines on each side:

```python
# docs/specs/00142 D2-D7: B2's re-risk reading, the twelve crowding signals of readings 3 and 4 where arm A is long below
# its full-long size, by their tails and forwards; no rule, no slot.
_B2_RERISK_STATE = "below_full"
# Arm A equals its full-long size to rounding where every arm is long, so "below" is below it by more than this.
_B2_RERISK_TOLERANCE = 1e-12


class _B2ReriskInputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    close: list[datetime]
    arm_a: dict[str, list[float]]
    full_long: dict[str, list[float]]
    signals: dict[str, dict[str, list[float | None]]]


def _b2_full_long(h4_prices: dict[str, list[float | None]]) -> dict[str, list[float]]:
    """`_b2_reentry_inputs`' full-long size, its books rebuilt over the union's prices, since `_b2_overlay_inputs` returns
    arm A and never its books (docs/specs/00142 D3)."""
    fed = _ffill_btc(h4_prices)
    levels = [
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
        )["vol_target_positions"]
        for lookbacks, target_vol in _B2_A2_ARMS
    ]
    return full_long_sizes(_inverse_vol_weights(fed, lookback=_B2_LOOKBACK), levels, _ASSETS)


def _b2_rerisk_inputs(
    subject: str, reader: ObservedReader, dataset: str, window: tuple[str, str] | None, accept_holes: bool
) -> _B2ReriskInputs:
    """Reading 3's arm A beside its full-long size, and readings 3's and 4's twelve signals: never a forward return, so the
    basis test reads no forward (docs/specs/00142 D3, D4, D7)."""
    overlay = _b2_overlay_inputs(subject, _b2_funding_signal, _B2_READING_THRESHOLD, reader, dataset, window, accept_holes)
    full_long = _b2_full_long(overlay.h4_prices)
    signals = {
        "binperp_funding_z30d": overlay.signal,
        "binperp_oi_z30d": _b2_oi_signal(reader, overlay.h4_ts),
        "binperp_ratio_max_z30d": _b2_ratio_signal(reader, overlay.h4_ts),
        "binperp_liq_long_z30d": _b2_liq_signal(reader, overlay.h4_ts),
        "binperp_oi_log_delta_z30d": _b2_oi_log_delta_signal(reader, overlay.h4_ts),
        "binperp_oi_momentum_z30d": _b2_oi_momentum_signal(reader, overlay.h4_ts),
        **_b2_ratio_signals(reader, overlay.h4_ts),
        **_b2_liq_side_signals(reader, overlay.h4_ts),
    }
    return _B2ReriskInputs(overlay.h4_ts, overlay.h4_prices, overlay.close, overlay.arm_a, full_long, signals)


def _b2_rerisk_flags(
    signal: dict[str, list[float | None]], arm_a: dict[str, list[float]], full_long: dict[str, list[float]], tail: str
) -> dict[str, list[bool | None]]:
    """`_b2_reading_flags` in the one state a re-risk acts in, arm A long below its full-long size (docs/specs/00142
    D3)."""
    threshold = _B2_READING_THRESHOLD
    past = {"above": lambda z: z > threshold, "below": lambda z: z < -threshold}[tail]
    return {
        a: [None if z is None or not 0 < p < f - _B2_RERISK_TOLERANCE else past(z) for z, p, f in zip(zs, arm_a[a], full_long[a])]
        for a, zs in signal.items()
    }


def _b2_rerisk_counts(inputs: _B2ReriskInputs) -> dict:
    """Per signal and tail, each asset's events and others below full-long, read before any forward (docs/specs/00142
    D7)."""
    counts: dict[str, dict] = {"events_per_asset": {}, "others_per_asset": {}}
    for key, signal in inputs.signals.items():
        for tail in _B2_READING_TAILS:
            flags = _b2_rerisk_flags(signal, inputs.arm_a, inputs.full_long, tail)
            counts["events_per_asset"].setdefault(key, {})[tail] = {_B2_RERISK_STATE: {a: f.count(True) for a, f in flags.items()}}
            counts["others_per_asset"].setdefault(key, {})[tail] = {_B2_RERISK_STATE: {a: f.count(False) for a, f in flags.items()}}
    return counts
```

- [ ] **Step 4: Run them to verify they pass** — step 2's command (measured `5 passed, 718 deselected`).
- [ ] **Step 5: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py`; the Global Constraints' `T` over the two paths in its three parts (the rest of `T`, the other sixteen direct readers, measured on Task 1's tree `106 passed, 57 deselected in 9.39s`); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 6: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED`:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_inputs(/def _b2_rerisk_inputs_gone(/' --mutation '/^def _b2_rerisk_inputs(/,/^def /s/    overlay = _b2_overlay_inputs(subject, _b2_funding_signal, /    overlay = _b2_overlay_inputs(subject, _b2_oi_signal, /' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_inputs_are_the_overlays_union_and_arm_a_its_full_long_size_and_each_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_inputs(/def _b2_rerisk_inputs_gone(/' --mutation 's/    full_long = _b2_full_long(overlay.h4_prices)/    full_long = _b2_full_long(overlay.h4_ts)/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_inputs_are_the_overlays_union_and_arm_a_its_full_long_size_and_each_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_inputs(/def _b2_rerisk_inputs_gone(/' --mutation '/^def _b2_rerisk_inputs(/,/^def /s/        "binperp_funding_z30d": overlay.signal,/        "binperp_funding_z30d": overlay.scales,/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_inputs_are_the_overlays_union_and_arm_a_its_full_long_size_and_each_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_inputs(/def _b2_rerisk_inputs_gone(/' --mutation '/^def _b2_rerisk_inputs(/,/^def /s/        "binperp_oi_z30d": _b2_oi_signal(reader, overlay.h4_ts),/        "binperp_oi_z30d": _b2_oi_log_delta_signal(reader, overlay.h4_ts),/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_inputs_are_the_overlays_union_and_arm_a_its_full_long_size_and_each_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_inputs(/def _b2_rerisk_inputs_gone(/' --mutation '/^def _b2_rerisk_inputs(/,/^def /s/        "binperp_ratio_max_z30d": _b2_ratio_signal(reader, overlay.h4_ts),/        "binperp_ratio_max_z30d": _b2_oi_momentum_signal(reader, overlay.h4_ts),/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_inputs_are_the_overlays_union_and_arm_a_its_full_long_size_and_each_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_inputs(/def _b2_rerisk_inputs_gone(/' --mutation '/^def _b2_rerisk_inputs(/,/^def /s/        "binperp_liq_long_z30d": _b2_liq_signal(reader, overlay.h4_ts),/        "binperp_liq_long_z30d": _b2_oi_signal(reader, overlay.h4_ts),/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_inputs_are_the_overlays_union_and_arm_a_its_full_long_size_and_each_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_inputs(/def _b2_rerisk_inputs_gone(/' --mutation 's/        "binperp_oi_log_delta_z30d": _b2_oi_log_delta_signal(reader, overlay.h4_ts),/        "binperp_oi_log_delta_z30d": _b2_oi_momentum_signal(reader, overlay.h4_ts),/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_inputs_are_the_overlays_union_and_arm_a_its_full_long_size_and_each_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_inputs(/def _b2_rerisk_inputs_gone(/' --mutation '/^def _b2_rerisk_inputs(/,/^def /s/        "binperp_oi_momentum_z30d": _b2_oi_momentum_signal(reader, overlay.h4_ts),/        "binperp_oi_momentum_z30d": _b2_oi_log_delta_signal(reader, overlay.h4_ts),/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_inputs_are_the_overlays_union_and_arm_a_its_full_long_size_and_each_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_inputs(/def _b2_rerisk_inputs_gone(/' --mutation '/^def _b2_rerisk_inputs(/,/^def /s/        \*\*_b2_ratio_signals(reader, overlay.h4_ts),/        **_b2_liq_side_signals(reader, overlay.h4_ts),/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_inputs_are_the_overlays_union_and_arm_a_its_full_long_size_and_each_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_inputs(/def _b2_rerisk_inputs_gone(/' --mutation 's/overlay.h4_prices, overlay.close, overlay.arm_a, full_long, signals)/overlay.h4_prices, overlay.close, overlay.scales, full_long, signals)/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_inputs_are_the_overlays_union_and_arm_a_its_full_long_size_and_each_signal_by_its_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_long(/def _b2_full_long_gone(/' --mutation '/^def _b2_full_long(/,/^def /s/^    fed = _ffill_btc(h4_prices)$/    fed = dict(h4_prices)/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_full_long_size_is_the_reentries_own_over_rebuilt_books -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_long(/def _b2_full_long_gone(/' --mutation '/^def _b2_full_long(/,/^def /s/                short="off",/                short="on",/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_full_long_size_is_the_reentries_own_over_rebuilt_books -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_long(/def _b2_full_long_gone(/' --mutation '/^def _b2_full_long(/,/^def /s/                vol_lookback=_B2_LOOKBACK,/                vol_lookback=_B2_LOOKBACK - 1,/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_full_long_size_is_the_reentries_own_over_rebuilt_books -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_long(/def _b2_full_long_gone(/' --mutation '/^def _b2_full_long(/,/^def /s/                basket_lookback=_B2_LOOKBACK,/                basket_lookback=_B2_LOOKBACK - 1,/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_full_long_size_is_the_reentries_own_over_rebuilt_books -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_long(/def _b2_full_long_gone(/' --mutation '/^def _b2_full_long(/,/^def /s/                periods_per_year=PPY_4H,/                periods_per_year=PPY_4H * 2,/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_full_long_size_is_the_reentries_own_over_rebuilt_books -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_long(/def _b2_full_long_gone(/' --mutation '/^def _b2_full_long(/,/^def /s/        )\["vol_target_positions"\]$/        )["book_base_returns"]/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_full_long_size_is_the_reentries_own_over_rebuilt_books -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_long(/def _b2_full_long_gone(/' --mutation '/^def _b2_full_long(/,/^def /s/        for lookbacks, target_vol in _B2_A2_ARMS$/        for lookbacks, target_vol in _B2_A2_ARMS[:2]/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_full_long_size_is_the_reentries_own_over_rebuilt_books -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_long(/def _b2_full_long_gone(/' --mutation 's/    return full_long_sizes(_inverse_vol_weights(fed, lookback=_B2_LOOKBACK), levels, _ASSETS)/    return full_long_sizes(_inverse_vol_weights(fed, lookback=_B2_LOOKBACK - 1), levels, _ASSETS)/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_full_long_size_is_the_reentries_own_over_rebuilt_books -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_long(/def _b2_full_long_gone(/' --mutation 's/    return full_long_sizes(_inverse_vol_weights(fed, lookback=_B2_LOOKBACK), levels, _ASSETS)/    return full_long_sizes(_inverse_vol_weights(h4_prices, lookback=_B2_LOOKBACK), levels, _ASSETS)/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_full_long_size_is_the_reentries_own_over_rebuilt_books -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_full_long(/def _b2_full_long_gone(/' --mutation 's/    return full_long_sizes(_inverse_vol_weights(fed, lookback=_B2_LOOKBACK), levels, _ASSETS)/    return full_long_sizes(_inverse_vol_weights(fed, lookback=_B2_LOOKBACK), levels, _ASSETS[:9])/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_readings_full_long_size_is_the_reentries_own_over_rebuilt_books -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_flags(/def _b2_rerisk_flags_gone(/' --mutation 's/^_B2_RERISK_TOLERANCE = 1e-12$/_B2_RERISK_TOLERANCE = 1e-14/' -- uv run pytest 'tests/test_research_command.py::test_a_rerisk_flag_is_an_event_past_its_tail_below_full_long_another_read_close_below_it_and_none_elsewhere[above]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_flags(/def _b2_rerisk_flags_gone(/' --mutation 's/^_B2_RERISK_TOLERANCE = 1e-12$/_B2_RERISK_TOLERANCE = 1e-10/' -- uv run pytest 'tests/test_research_command.py::test_a_rerisk_flag_is_an_event_past_its_tail_below_full_long_another_read_close_below_it_and_none_elsewhere[above]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_flags(/def _b2_rerisk_flags_gone(/' --mutation 's/None if z is None or not 0 < p < f - _B2_RERISK_TOLERANCE else past(z)/None if z is None or not 0 <= p < f - _B2_RERISK_TOLERANCE else past(z)/' -- uv run pytest 'tests/test_research_command.py::test_a_rerisk_flag_is_an_event_past_its_tail_below_full_long_another_read_close_below_it_and_none_elsewhere[above]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_flags(/def _b2_rerisk_flags_gone(/' --mutation 's/None if z is None or not 0 < p < f - _B2_RERISK_TOLERANCE else past(z)/None if z is None or not 0 < p < f + _B2_RERISK_TOLERANCE else past(z)/' -- uv run pytest 'tests/test_research_command.py::test_a_rerisk_flag_is_an_event_past_its_tail_below_full_long_another_read_close_below_it_and_none_elsewhere[above]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_flags(/def _b2_rerisk_flags_gone(/' --mutation 's/None if z is None or not 0 < p < f - _B2_RERISK_TOLERANCE else past(z)/None if z is None or not 0 < p else past(z)/' -- uv run pytest 'tests/test_research_command.py::test_a_rerisk_flag_is_an_event_past_its_tail_below_full_long_another_read_close_below_it_and_none_elsewhere[above]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_flags(/def _b2_rerisk_flags_gone(/' --mutation '/^def _b2_rerisk_flags(/,/^def /s/    threshold = _B2_READING_THRESHOLD/    threshold = 2.5/' -- uv run pytest 'tests/test_research_command.py::test_a_rerisk_flag_is_an_event_past_its_tail_below_full_long_another_read_close_below_it_and_none_elsewhere[above]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_flags(/def _b2_rerisk_flags_gone(/' --mutation '/^def _b2_rerisk_flags(/,/^def /s/"above": lambda z: z > threshold, /"above": lambda z: z >= threshold, /' -- uv run pytest 'tests/test_research_command.py::test_a_rerisk_flag_is_an_event_past_its_tail_below_full_long_another_read_close_below_it_and_none_elsewhere[above]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_flags(/def _b2_rerisk_flags_gone(/' --mutation '/^def _b2_rerisk_flags(/,/^def /s/"below": lambda z: z < -threshold}/"below": lambda z: z <= -threshold}/' -- uv run pytest 'tests/test_research_command.py::test_a_rerisk_flag_is_an_event_past_its_tail_below_full_long_another_read_close_below_it_and_none_elsewhere[below]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_counts(/def _b2_rerisk_counts_gone(/' --mutation 's/for z, p, f in zip(zs, arm_a\[a\], full_long\[a\])/for z, p, f in zip(zs, arm_a[a], full_long["BTC"])/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_counts_each_assets_events_and_others_below_full_long_per_signal_and_tail -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_counts(/def _b2_rerisk_counts_gone(/' --mutation 's/^_B2_RERISK_STATE = "below_full"$/_B2_RERISK_STATE = "long"/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_counts_each_assets_events_and_others_below_full_long_per_signal_and_tail -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_counts(/def _b2_rerisk_counts_gone(/' --mutation '/^def _b2_rerisk_counts(/,/^def /s/            flags = _b2_rerisk_flags(signal, inputs.arm_a, inputs.full_long, tail)/            flags = _b2_rerisk_flags(signal, inputs.arm_a, inputs.full_long, "above")/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_counts_each_assets_events_and_others_below_full_long_per_signal_and_tail -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_counts(/def _b2_rerisk_counts_gone(/' --mutation 's/{_B2_RERISK_STATE: {a: f.count(True) for a, f in flags.items()}}/{_B2_RERISK_STATE: {a: f.count(False) for a, f in flags.items()}}/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_counts_each_assets_events_and_others_below_full_long_per_signal_and_tail -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_counts(/def _b2_rerisk_counts_gone(/' --mutation 's/counts\["others_per_asset"\].setdefault(key, {})\[tail\] = {_B2_RERISK_STATE: {a: f.count(False)/counts["others_per_asset"].setdefault(key, {})[tail] = {_B2_RERISK_STATE: {a: f.count(None)/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_counts_each_assets_events_and_others_below_full_long_per_signal_and_tail -q -p no:cacheprovider --basetemp=.tmp/pt
```

  Each row moves one clause D3, D4 or D7 gives the new code. The inputs: the reader handed to the overlay (the `_b2_oi_signal` row), the full-long size read off the union's prices (the `overlay.h4_ts` row), the funding signal taken from the overlay (the `overlay.scales` signal row), each later signal by its own reader (the five reader-swap rows and the `_b2_liq_side_signals` row in the ratio readers' place) and arm A the overlay's (the `overlay.scales` arm row). The full-long size: the arms' BTC fill (the `dict(h4_prices)` row, the fixture's BTC missing close 200), each config field the books are built with (the `short="on"`, `vol_lookback`, `basket_lookback` and `periods_per_year` rows), the books' vol-target levels (the `book_base_returns` row), all three arms (the `[:2]` row), the weights' lookback and prices (the two weights rows) and every asset (the `[:9]` row). The flags: the tolerance in each direction (the `1e-14` and `1e-10` rows, read by the fixture's gaps of 1e-13 and 1e-11), the flat closes kept out (the `0 <=` row), the closes at the size kept out (the `f +` row) and the size read at all (the `not 0 < p` row), the threshold and each tail's strict comparison (the `2.5`, `>=` and `<=` rows). The counts: each asset read against its own size (the `full_long["BTC"]` row, read by ETH's 0.26), the state's key (the `"long"` row), each tail's own flags (the `"above"` row) and events and others counted as such (the two `count(...)` rows).

- [ ] **Step 7: Commit** — `feat(research): arm A's full-long size rebuilt beside reading 3's arm A, and the flags and counts of the state below it, for B2's re-risk reading`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 2: the reading subject in `cli/research/subjects.py` (D2, D5–D7)

**Files:** Modify `cli/research/subjects.py`, `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`.

**Interfaces:** Consumes Task 1's `_B2ReriskInputs`, `_b2_rerisk_inputs`, `_b2_rerisk_flags`, `_b2_rerisk_counts`, `_B2_RERISK_STATE` and `_B2_RERISK_TOLERANCE`; `cli/research/subjects.py`'s `_b2_reading_forwards`, `stationary_bootstrap_blocks`, `event_contrast_blocks`, `_B2_READING_SIGNALS`, `_B2_READING_2_SIGNALS`, `_B2_READING_THRESHOLD`, `_B2_READING_TAILS`, `_B2_READING_HORIZONS`, `_B2_READING_BLOCK`, `_B2_READING_2_RESAMPLES`, `_b2_over`, `_ASSETS`, `SubjectError`, `Subject` and the error classes it imports, each called through the module's name; in the tests, `_anchor`, `_rolling_set`, `_not_parquet`, `_b2_reentry_dataset`, `_B2_START`, `_B2_ASSETS`, `_B2_SPOILT`, `_CONTRACT_DATASETS` and Task 1's `_B2_RERISK_SIGNAL_KEYS`. Produces the subject.

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - `test_each_subject_declares_the_metric_keys_its_build_returns` gains, as its last line, `    assert subjects.SUBJECTS["b2-rerisk-reading"].metric_keys == _B2_RERISK_SPEC_KEYS`;
  - after Task 1's `test_the_rerisk_reading_counts_each_assets_events_and_others_below_full_long_per_signal_and_tail` and before `def _ruled_signal(`:

```python
_B2_RERISK_SPEC = "docs/specs/00142-b2-rerisk-reading-design.md"
_B2_RERISK_SPEC_KEYS = frozenset(
    {
        *(f"{key}_fwd_{kind}_{hours}h" for key in _B2_RERISK_SIGNAL_KEYS for kind in ("logret", "sumret") for hours in (4, 24, 96)),
        "events_per_asset",
        "others_per_asset",
        "threshold",
        "full_long_tolerance",
        "mean_block",
        "n_resamples",
        "far_percentiles",
    }
)


def test_the_rerisk_reading_declares_the_4h_grid_its_keys_and_no_rule():
    reading = subjects.SUBJECTS["b2-rerisk-reading"]
    assert (reading.name, reading.intervals, reading.assets, reading.spec, reading.seeds) == (
        "b2-rerisk-reading",
        (240,),
        _B2_ASSETS,
        _B2_RERISK_SPEC,
        (42,),
    )
    assert reading.build is subjects._build_b2_rerisk_reading and reading.metric_keys == _B2_RERISK_SPEC_KEYS
    assert (reading.verdict, reading.no_verdict, reading.incumbent, reading.family, reading.n_trials) == (None,) * 5


def test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows(monkeypatch):
    # Thirty closes on every asset; arm A at its full-long size at every third index, below it at the others but every
    # fourth, flat at every fourth; each signal read from its own index and swinging through both tails.
    prices = {a: [100.0 * (1 + 0.01 * i) * 1.003**k for k in range(30)] for i, a in enumerate(_B2_ASSETS)}
    full_long = {a: [0.2] * 29 for a in _B2_ASSETS}
    arm_a = {a: [0.0 if k % 4 == 0 else 0.2 if k % 3 == 0 else 0.1 for k in range(29)] for a in _B2_ASSETS}
    signals = {
        key: {a: [None if k < j else 3.0 * math.sin(k + i + j) for k in range(29)] for i, a in enumerate(_B2_ASSETS)}
        for j, key in enumerate(_B2_RERISK_SIGNAL_KEYS)
    }
    inputs = subjects._B2ReriskInputs([], prices, ["close"] * 29, arm_a, full_long, signals)
    draws, calls = [], []
    monkeypatch.setattr(subjects, "stationary_bootstrap_blocks", lambda n_obs, **kwargs: draws.append((n_obs, kwargs)) or "draw")

    def contrast(flags, forwards, blocks, **kwargs):
        calls.append((flags, forwards, blocks, kwargs))
        return {series: {"pooled": [len(calls), index]} for index, series in enumerate(forwards)}

    monkeypatch.setattr(subjects, "event_contrast_blocks", contrast)

    metrics = subjects._b2_rerisk_metrics(inputs)

    assert draws == [(29, {"mean_block": 102, "n_resamples": 40_000, "seed": 42})]
    forwards = subjects._b2_reading_forwards(inputs.h4_prices)
    cells = [(key, tail) for key in _B2_RERISK_SIGNAL_KEYS for tail in ("above", "below")]
    far = (2.5 / 72, 100 - 2.5 / 72)
    assert calls == [
        (subjects._b2_rerisk_flags(inputs.signals[key], arm_a, full_long, tail), forwards, "draw", {"far": far})
        for key, tail in cells
    ]
    for call, (key, tail) in enumerate(cells, start=1):
        for index, series in enumerate(f"fwd_{kind}_{hours}h" for kind in ("logret", "sumret") for hours in (4, 24, 96)):
            assert metrics[f"{key}_{series}"][tail] == {"below_full": {"pooled": [call, index]}}
    assert set(metrics) == _B2_RERISK_SPEC_KEYS
    assert (metrics["threshold"], metrics["full_long_tolerance"], metrics["mean_block"], metrics["n_resamples"]) == (
        2.0,
        1e-12,
        102,
        40_000,
    )
    assert metrics["far_percentiles"] == list(far)
    counts = subjects._b2_rerisk_counts(inputs)
    assert (metrics["events_per_asset"], metrics["others_per_asset"]) == (counts["events_per_asset"], counts["others_per_asset"])


def test_the_rerisk_reading_refuses_as_of_before_any_read(tmp_path, monkeypatch):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the reading read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)
    args = ["research", "eval", "--subject", "b2-rerisk-reading", "--dataset", "ohlc-rolling", "--as-of", "2026-10-03"]

    result = runner.invoke(app, args)

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        "b2-rerisk-reading evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a "
        "frozen --dataset"
    ) in result.output


@pytest.mark.parametrize(
    ("relpath", "spoil", "cause"),
    [
        pytest.param(f"derivatives-funding/{_B2_SPOILT}/funding.parquet", _not_parquet, "File out of specification", id="funding"),
        pytest.param(f"derivatives-oi/{_B2_SPOILT}/oi.parquet", _not_parquet, "File out of specification", id="oi"),
        pytest.param(
            "liquidations-daily/SOL/daily.parquet",
            lambda path: pl.read_parquet(path).drop("short_usd").write_parquet(path),
            '"short_usd" not found',
            id="liquidation-short",
        ),
    ],
)
def test_the_rerisk_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it(tmp_path, monkeypatch, relpath, spoil, cause):
    root = _b2_reentry_dataset(tmp_path)
    spoil(root / relpath)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", "b2-rerisk-reading", "--dataset", "ohlc-test"])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{relpath}: " in result.output and cause in result.output
```

  - `_CONTRACT_DATASETS` gains, after its `"b2-second-signal-reading"` entry, `    "b2-rerisk-reading": lambda tmp_path, subject: (_b2_reentry_dataset(tmp_path), _B2_START),` — `_b2_reentry_dataset` holds the funding, OI and daily liquidation sets the reading reads beside `ohlc-test`.

  **Author's call** — the wiring test runs `_b2_rerisk_metrics` under stand-ins for the draw and the contrast, reading the cells' order, arguments and keys off sentinels, its arm A at its size, below it and flat so that the flags each cell is handed part the state from the long one; the file-refusal rows keep one per set and reader the build reaches first or last — the funding file, read by the overlay's reader before arm A; the OI file, by `_b2_oi_signal`, the first of its five readers; and the daily file's short side, by `_b2_liq_side_signals`, the last reader — since every reader's own refusal is its reading's retired case. The reading's instrument — its twelve readers, state, tolerance, threshold, tails, horizons, two forward families, block, resamples, far percentiles and seed — is written in this plan's code in three places: the subject's constants and calls (with the probe rows that match them); the tests' literals (`_B2_RERISK_SIGNAL_KEYS`, `_B2_RERISK_SPEC_KEYS`, the full-long oracle, the flags fixture and the wiring test's arguments and series); and the check programs (Task 4 step 5) — `reading_check.py`'s `constants`, its `cells`' tails, state and hours and its two families' keys, and `pooled_rows.py`'s signal keys, tails, state, hours and families — Task 3's data-gated counts holding the inputs half to the measured basis. It is written in words in five more, which a read against D3–D8 alone checks: the Global Constraints' first three items, the README row (step 4), the pick's option 2 and the conventions entry (Task 3 step 5) and the run's notes (Task 5 step 2).

- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00142 && uv run pytest tests/test_research_command.py -k "rerisk_reading_declares or rerisk_reading_hands or rerisk_reading_refuses or declares_the_metric_keys" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00142/pt`: collection completes and every selected case fails at its call, on a key `SUBJECTS` lacks, a name `subjects` lacks, or a subject the CLI does not know (measured over Task 1's code: `7 failed, 722 deselected`).
- [ ] **Step 3: Implement in `cli/research/subjects.py`** — after Task 1's `_b2_rerisk_counts` and before `SUBJECTS: dict[str, Subject] = {`, two blank lines on each side:

```python
_B2_RERISK_SIGNALS = (*_B2_READING_SIGNALS, *_B2_READING_2_SIGNALS)
# Bonferroni at 5 % two-sided over the 72 pooled cells: 12 signals, 2 tails, 1 state, 3 horizons.
_B2_RERISK_FAR = (2.5 / 72, 100 - 2.5 / 72)


def _b2_rerisk_metrics(inputs: _B2ReriskInputs) -> dict:
    forwards = _b2_reading_forwards(inputs.h4_prices)
    blocks = stationary_bootstrap_blocks(
        len(inputs.close), mean_block=_B2_READING_BLOCK, n_resamples=_B2_READING_2_RESAMPLES, seed=42
    )
    contrast: dict[str, dict] = {}
    for key, signal in inputs.signals.items():
        for tail in _B2_READING_TAILS:
            flags = _b2_rerisk_flags(signal, inputs.arm_a, inputs.full_long, tail)
            rows = event_contrast_blocks(flags, forwards, blocks, far=_B2_RERISK_FAR)
            for series, by_name in rows.items():
                contrast.setdefault(f"{key}_{series}", {})[tail] = {_B2_RERISK_STATE: by_name}
    return {
        **contrast,
        **_b2_rerisk_counts(inputs),
        "threshold": _B2_READING_THRESHOLD,
        "full_long_tolerance": _B2_RERISK_TOLERANCE,
        "mean_block": _B2_READING_BLOCK,
        "n_resamples": _B2_READING_2_RESAMPLES,
        "far_percentiles": list(_B2_RERISK_FAR),
    }


def _build_b2_rerisk_reading(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    subject = "b2-rerisk-reading"
    if as_of is not None:
        raise SubjectError(
            f"{subject} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a "
            "frozen --dataset"
        )
    try:
        return _b2_rerisk_metrics(_b2_rerisk_inputs(subject, reader, dataset, window, accept_holes))
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


# docs/specs/00142 D7's keys of the reading.
_B2_RERISK_KEYS = frozenset(
    {
        *(
            f"{key}_fwd_{kind}_{4 * horizon}h"
            for key in _B2_RERISK_SIGNALS
            for kind in ("logret", "sumret")
            for horizon in _B2_READING_HORIZONS
        ),
        "events_per_asset",
        "others_per_asset",
        "threshold",
        "full_long_tolerance",
        "mean_block",
        "n_resamples",
        "far_percentiles",
    }
)
```

  and `SUBJECTS` gains, after its `"b2-second-signal-reading"` entry:

```python
    "b2-rerisk-reading": Subject(
        "b2-rerisk-reading",
        (240,),
        _ASSETS,
        _build_b2_rerisk_reading,
        spec="docs/specs/00142-b2-rerisk-reading-design.md",
        metric_keys=_B2_RERISK_KEYS,
        seeds=(42,),
    ),
```

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row: `` `--reading`) or `b2-second-signal-reading` ( `` becomes `` `--reading`), `b2-second-signal-reading` ( ``, and the row's closing `` `--reading`). | `` becomes:

```markdown
`--reading`) or `b2-rerisk-reading` (the same reading over all twelve of those crowding signals, at the closes where the A2 4h ensemble holds the asset below its full-long size — the position it takes where every arm is long — the one state in which raising its position to that size acts, its far bounds at the Bonferroni percentiles over its 72 cells, from 40,000 resamples; the 4h series of `--dataset`, a frozen set only, and the `derivatives-funding`, `derivatives-oi` and `liquidations-daily` sets read whole; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: `tests/slow-cases.txt`** — gains at their `sorted()` places the cases measured at 10 s or more on the authoring tree (the evaluate and shared-default rows are the existing tests' new rows): the file refusal's `oi` row 15.2 s and `liquidation-short` row 39.5 s, the evaluate row 48.4 s and the shared-default row 96.4 s:

```text
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-rerisk-reading-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-rerisk-reading]
tests/test_research_command.py::test_the_rerisk_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it[liquidation-short]
tests/test_research_command.py::test_the_rerisk_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it[oi]
```

  A case that times at 10 s or more on the implementer's own run and is not listed joins the list; a listed one under 10 s stays (`tests/test_slow_cases.py` passes).
- [ ] **Step 6: Run them to verify they pass** — step 2's command, one plain blocking call, `timeout` 600000 ms (measured `7 passed, 731 deselected in 56.25s`); then the subject's two slow fixture rows, the cases that run its build end to end, which step 2's `-k` does not select and every commit gate's `-m "not slow and not data"` deselects, each reading the test fixture alone (`_anchor`): `mkdir -p .tmp/plan-00142 && ZCRYPTO_RERUN_SLOW=1 uv run pytest 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-rerisk-reading-evaluates]' 'tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-rerisk-reading]' -q -p no:cacheprovider --basetemp=.tmp/plan-00142/pt`, one plain blocking call, `timeout` 600000 ms (measured `2 passed in 145.55s`).
- [ ] **Step 7: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the Global Constraints' `T` over the four paths in its three parts (the rest of `T`, the other thirty-four direct readers, measured `4114 passed, 58 deselected in 121.17s`); `uv run pre-commit run -a` until clean; the Unchanged checks.
- [ ] **Step 8: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED`; the metric-keys line, the contract, shared-default and tracked-spec rows are new rows of existing tests, not new guards, and are not probed; the slow cases each recorded `probe skipped: slow case`:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_rerisk_reading(/def _build_b2_rerisk_reading_gone(/' --mutation '/^    "b2-rerisk-reading": Subject(/,/^    ),$/s/        seeds=(42,),/        seeds=(42, 7),/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_declares_the_4h_grid_its_keys_and_no_rule -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_rerisk_reading(/def _build_b2_rerisk_reading_gone(/' --mutation '/^    "b2-rerisk-reading": Subject(/,/^    ),$/s/        spec="docs\/specs\/00142-b2-rerisk-reading-design.md",/        spec="docs\/specs\/00141-b2-signal-reading-2-design.md",/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_declares_the_4h_grid_its_keys_and_no_rule -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_rerisk_reading(/def _build_b2_rerisk_reading_gone(/' --mutation '/^    "b2-rerisk-reading": Subject(/,/^    ),$/s/        (240,),/        (1440,),/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_declares_the_4h_grid_its_keys_and_no_rule -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_rerisk_reading(/def _build_b2_rerisk_reading_gone(/' --mutation 's/^_B2_RERISK_SIGNALS = (\*_B2_READING_SIGNALS, \*_B2_READING_2_SIGNALS)$/_B2_RERISK_SIGNALS = (*_B2_READING_SIGNALS, *_B2_READING_2_SIGNALS[:7])/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_declares_the_4h_grid_its_keys_and_no_rule -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_rerisk_reading(/def _build_b2_rerisk_reading_gone(/' --mutation '/^_B2_RERISK_KEYS = frozenset($/,/^)$/s/        "full_long_tolerance",/        "tolerance",/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_declares_the_4h_grid_its_keys_and_no_rule -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation 's/^_B2_RERISK_FAR = (2.5 \/ 72, 100 - 2.5 \/ 72)$/_B2_RERISK_FAR = (2.5 \/ 96, 100 - 2.5 \/ 96)/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation '/^def _b2_rerisk_metrics(/,/^def /s/        len(inputs.close), mean_block=_B2_READING_BLOCK, /        len(inputs.close) - 1, mean_block=_B2_READING_BLOCK, /' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation '/^def _b2_rerisk_metrics(/,/^def /s/        len(inputs.close), mean_block=_B2_READING_BLOCK, /        len(inputs.close), mean_block=30, /' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation '/^def _b2_rerisk_metrics(/,/^def /s/n_resamples=_B2_READING_2_RESAMPLES, seed=42$/n_resamples=_N_RESAMPLES, seed=42/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation '/^def _b2_rerisk_metrics(/,/^def /s/n_resamples=_B2_READING_2_RESAMPLES, seed=42$/n_resamples=_B2_READING_2_RESAMPLES, seed=7/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation '/^def _b2_rerisk_metrics(/,/^def /s/            flags = _b2_rerisk_flags(signal, inputs.arm_a, inputs.full_long, tail)/            flags = _b2_reading_flags(signal, inputs.arm_a, tail, "long")/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation '/^def _b2_rerisk_metrics(/,/^def /s/            flags = _b2_rerisk_flags(signal, inputs.arm_a, inputs.full_long, tail)/            flags = _b2_rerisk_flags(signal, inputs.arm_a, inputs.arm_a, tail)/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation 's/rows = event_contrast_blocks(flags, forwards, blocks, far=_B2_RERISK_FAR)/rows = event_contrast_blocks(flags, forwards, blocks, far=_B2_READING_2_FAR)/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation 's/contrast.setdefault(f"{key}_{series}", {})\[tail\] = {_B2_RERISK_STATE: by_name}/contrast.setdefault(f"{key}_{series}", {})[tail] = by_name/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation '/^def _b2_rerisk_metrics(/,/^def /s/        \*\*_b2_rerisk_counts(inputs),/        **_b2_reading_counts(inputs),/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation '/^def _b2_rerisk_metrics(/,/^def /s/        "threshold": _B2_READING_THRESHOLD,/        "threshold": 2.5,/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation 's/        "full_long_tolerance": _B2_RERISK_TOLERANCE,/        "full_long_tolerance": 1e-10,/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation '/^def _b2_rerisk_metrics(/,/^def /s/        "mean_block": _B2_READING_BLOCK,/        "mean_block": 30,/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation '/^def _b2_rerisk_metrics(/,/^def /s/        "n_resamples": _B2_READING_2_RESAMPLES,/        "n_resamples": _N_RESAMPLES,/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_metrics(/def _b2_rerisk_metrics_gone(/' --mutation 's/        "far_percentiles": list(_B2_RERISK_FAR),/        "far_percentiles": list(_B2_READING_2_FAR),/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_rerisk_reading(/def _build_b2_rerisk_reading_gone(/' --mutation '/^def _build_b2_rerisk_reading(/,/^def /s/    if as_of is not None:/    if as_of is None:/' -- uv run pytest tests/test_research_command.py::test_the_rerisk_reading_refuses_as_of_before_any_read -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_rerisk_inputs(/def _b2_rerisk_inputs_gone(/' --mutation '/^def _b2_rerisk_inputs(/,/^def /s/    overlay = _b2_overlay_inputs(subject, _b2_funding_signal, /    overlay = _b2_overlay_inputs(subject, _b2_liq_signal, /' -- uv run pytest 'tests/test_research_command.py::test_the_rerisk_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it[funding]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  The file refusal's `oi` and `liquidation-short` rows are slow cases, recorded `probe skipped: slow case`; the `funding` row has its own, the overlay handed another reader so that no funding file is read. Each declaration row moves one value the spec fixes — the seeds, the spec, the grid, the signals, a constant key; each wiring row one argument of the draw — its index count, block, resamples and seed — or of the flags or the contrast — the state's flags and not reading 3's, the size beside arm A, the far percentiles — or one key the metrics carry — the state level, the counts the state's, each constant; the as-of row the refusal's condition.

- [ ] **Step 9: Commit** — `feat(research): B2's re-risk reading — the twelve crowding signals' forward returns by tail where arm A is long below its full-long size, on a frozen set's full history`, the message carrying the test result lines, each probe's command and verdict, each `probe skipped: slow case` and the two trailer lines.

## Task 3: the data-gated basis test, the decisions-log entries before the hash, the reads (D1, D8, D9)

**Files:** Create `tests/test_research_b2_rerisk_reading_basis.py` (module-marked `data`); modify `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 5's own commit.

**Interfaces:** Consumes Task 1's `_b2_rerisk_inputs` and `_b2_rerisk_counts`; `tests.skip_gates.nothing_found_under`. Produces one test and the module names `BLOCK`, `VOUCHED`, `EVENTS`, `OTHERS` and `per_asset()`, which Task 4's check program imports. No test computes a forward return.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis:

```python
"""B2's re-risk reading's inputs against spec 00142's measured basis; no forward return."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
# Copied from the spec's measured basis, never from a run.
BLOCK = "ad140b62ac72cfd6b4931dbe4f529f29d4dd34ef49d86e791c37764d2cf8eee1"
VOUCHED = {
    "ohlc-full": "checked (36 vouched hashes)",
    "derivatives-funding": "checked (10 vouched hashes)",
    "derivatives-oi": "checked (10 vouched hashes)",
    "liquidations-daily": "checked (10 vouched hashes)",
}
_RETURN_INDICES = 27_337
_TOLERANCE = 1e-12
# Per signal, the first return index every asset's signal holds, and its close.
SIGNAL_FROM = {
    "binperp_funding_z30d": (15_419, datetime(2020, 10, 22, 8, tzinfo=UTC)),
    "binperp_oi_z30d": (18_026, datetime(2021, 12, 30, 20, tzinfo=UTC)),
    "binperp_ratio_max_z30d": (20_298, datetime(2023, 1, 13, 12, tzinfo=UTC)),
    "binperp_liq_long_z30d": (19_731, datetime(2022, 10, 11, tzinfo=UTC)),
    "binperp_oi_log_delta_z30d": (18_027, datetime(2021, 12, 31, tzinfo=UTC)),
    "binperp_oi_momentum_z30d": (18_206, datetime(2022, 1, 29, 20, tzinfo=UTC)),
    "binperp_count_toptrader_long_short_ratio_z30d": (20_298, datetime(2023, 1, 13, 12, tzinfo=UTC)),
    "binperp_sum_toptrader_long_short_ratio_z30d": (20_298, datetime(2023, 1, 13, 12, tzinfo=UTC)),
    "binperp_count_long_short_ratio_z30d": (18_324, datetime(2022, 2, 18, 12, tzinfo=UTC)),
    "binperp_sum_taker_long_short_vol_ratio_z30d": (18_994, datetime(2022, 6, 10, 4, tzinfo=UTC)),
    "binperp_liq_short_z30d": (19_731, datetime(2022, 10, 11, tzinfo=UTC)),
    "binperp_liq_total_z30d": (19_731, datetime(2022, 10, 11, tzinfo=UTC)),
}
# Arm A's long and flat asset-stamps, its long ones below its full-long size and at it, and below them each cell's events
# and others, per asset in `subjects._ASSETS`' order.
ARM_A_LONG = (8_938, 4_680, 17_169, 6_766, 6_640, 13_428, 7_954, 11_958, 6_024, 9_905)
ARM_A_FLAT = (18_399, 22_657, 10_168, 20_571, 20_697, 13_909, 19_383, 15_379, 21_313, 17_432)
BELOW_FULL = (6_075, 3_289, 10_781, 4_874, 4_884, 8_260, 5_483, 8_296, 4_104, 6_784)
AT_FULL = (2_863, 1_391, 6_388, 1_892, 1_756, 5_168, 2_471, 3_662, 1_920, 3_121)
EVENTS = {
    "binperp_funding_z30d": {
        "above": {"below_full": (98, 44, 97, 157, 102, 86, 97, 159, 58, 161)},
        "below": {"below_full": (130, 106, 151, 116, 80, 128, 145, 142, 85, 127)},
    },
    "binperp_oi_z30d": {
        "above": {"below_full": (272, 170, 292, 370, 279, 296, 261, 239, 219, 250)},
        "below": {"below_full": (24, 72, 134, 21, 73, 46, 68, 58, 123, 58)},
    },
    "binperp_ratio_max_z30d": {
        "above": {"below_full": (421, 472, 587, 512, 650, 369, 557, 491, 547, 430)},
        "below": {"below_full": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)},
    },
    "binperp_liq_long_z30d": {
        "above": {"below_full": (124, 150, 125, 181, 194, 128, 142, 162, 128, 149)},
        "below": {"below_full": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)},
    },
    "binperp_oi_log_delta_z30d": {
        "above": {"below_full": (88, 92, 98, 111, 75, 77, 94, 74, 92, 75)},
        "below": {"below_full": (67, 63, 102, 74, 72, 70, 69, 57, 72, 54)},
    },
    "binperp_oi_momentum_z30d": {
        "above": {"below_full": (196, 161, 306, 313, 257, 163, 249, 243, 169, 177)},
        "below": {"below_full": (94, 93, 96, 51, 84, 99, 116, 86, 131, 95)},
    },
    "binperp_count_toptrader_long_short_ratio_z30d": {
        "above": {"below_full": (185, 206, 253, 130, 206, 111, 164, 173, 154, 106)},
        "below": {"below_full": (62, 36, 72, 46, 51, 81, 102, 83, 144, 48)},
    },
    "binperp_sum_toptrader_long_short_ratio_z30d": {
        "above": {"below_full": (183, 220, 177, 289, 385, 170, 294, 241, 243, 217)},
        "below": {"below_full": (20, 30, 147, 24, 63, 90, 53, 59, 69, 23)},
    },
    "binperp_count_long_short_ratio_z30d": {
        "above": {"below_full": (193, 231, 303, 180, 165, 163, 196, 176, 210, 159)},
        "below": {"below_full": (159, 109, 67, 105, 144, 89, 161, 150, 131, 126)},
    },
    "binperp_sum_taker_long_short_vol_ratio_z30d": {
        "above": {"below_full": (105, 128, 184, 132, 137, 129, 152, 170, 172, 127)},
        "below": {"below_full": (0, 3, 1, 1, 1, 1, 2, 0, 2, 0)},
    },
    "binperp_liq_short_z30d": {
        "above": {"below_full": (167, 156, 116, 124, 196, 137, 208, 201, 106, 106)},
        "below": {"below_full": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)},
    },
    "binperp_liq_total_z30d": {
        "above": {"below_full": (106, 85, 69, 131, 129, 80, 134, 121, 92, 107)},
        "below": {"below_full": (0, 0, 0, 0, 0, 6, 0, 0, 0, 0)},
    },
}
OTHERS = {
    "binperp_funding_z30d": {
        "above": {"below_full": (4_902, 3_245, 5_031, 4_717, 4_775, 4_973, 5_223, 5_433, 4_021, 4_789)},
        "below": {"below_full": (4_870, 3_183, 4_977, 4_758, 4_797, 4_931, 5_175, 5_450, 3_994, 4_823)},
    },
    "binperp_oi_z30d": {
        "above": {"below_full": (2_711, 2_930, 3_733, 3_181, 3_180, 2_861, 3_190, 3_120, 3_136, 2_712)},
        "below": {"below_full": (2_959, 3_028, 3_891, 3_530, 3_386, 3_111, 3_383, 3_301, 3_232, 2_904)},
    },
    "binperp_ratio_max_z30d": {
        "above": {"below_full": (1_630, 1_802, 2_604, 1_854, 1_825, 1_832, 1_976, 2_032, 1_896, 1_786)},
        "below": {"below_full": (2_051, 2_274, 3_191, 2_366, 2_475, 2_201, 2_533, 2_523, 2_443, 2_216)},
    },
    "binperp_liq_long_z30d": {
        "above": {"below_full": (2_591, 2_577, 2_776, 2_801, 3_017, 2_689, 2_977, 2_899, 2_836, 2_608)},
        "below": {"below_full": (2_715, 2_727, 2_901, 2_982, 3_211, 2_817, 3_119, 3_061, 2_964, 2_757)},
    },
    "binperp_oi_log_delta_z30d": {
        "above": {"below_full": (2_892, 3_006, 3_923, 3_438, 3_381, 3_078, 3_354, 3_282, 3_262, 2_886)},
        "below": {"below_full": (2_913, 3_035, 3_919, 3_475, 3_384, 3_085, 3_379, 3_299, 3_282, 2_907)},
    },
    "binperp_oi_momentum_z30d": {
        "above": {"below_full": (2_579, 2_802, 3_280, 2_836, 2_841, 2_735, 2_952, 2_825, 2_841, 2_589)},
        "below": {"below_full": (2_681, 2_870, 3_490, 3_098, 3_014, 2_799, 3_085, 2_982, 2_879, 2_671)},
    },
    "binperp_count_toptrader_long_short_ratio_z30d": {
        "above": {"below_full": (2_041, 2_127, 2_981, 2_274, 2_426, 2_135, 2_405, 2_419, 2_363, 2_124)},
        "below": {"below_full": (2_164, 2_297, 3_162, 2_358, 2_581, 2_165, 2_467, 2_509, 2_373, 2_182)},
    },
    "binperp_sum_toptrader_long_short_ratio_z30d": {
        "above": {"below_full": (2_127, 2_223, 3_152, 2_289, 2_386, 2_301, 2_416, 2_486, 2_375, 2_184)},
        "below": {"below_full": (2_290, 2_413, 3_182, 2_554, 2_708, 2_381, 2_657, 2_668, 2_549, 2_378)},
    },
    "binperp_count_long_short_ratio_z30d": {
        "above": {"below_full": (2_804, 2_847, 3_768, 3_322, 3_231, 2_931, 3_196, 3_271, 3_183, 2_853)},
        "below": {"below_full": (2_838, 2_969, 4_004, 3_397, 3_252, 3_005, 3_231, 3_297, 3_262, 2_886)},
    },
    "binperp_sum_taker_long_short_vol_ratio_z30d": {
        "above": {"below_full": (2_686, 2_756, 3_794, 3_115, 3_043, 2_981, 3_187, 3_198, 3_114, 2_826)},
        "below": {"below_full": (2_791, 2_881, 3_977, 3_246, 3_179, 3_109, 3_337, 3_368, 3_284, 2_953)},
    },
    "binperp_liq_short_z30d": {
        "above": {"below_full": (2_548, 2_571, 2_785, 2_858, 3_015, 2_680, 2_911, 2_860, 2_858, 2_651)},
        "below": {"below_full": (2_715, 2_727, 2_901, 2_982, 3_211, 2_817, 3_119, 3_061, 2_964, 2_757)},
    },
    "binperp_liq_total_z30d": {
        "above": {"below_full": (2_609, 2_642, 2_832, 2_851, 3_082, 2_737, 2_985, 2_940, 2_872, 2_650)},
        "below": {"below_full": (2_715, 2_727, 2_901, 2_982, 3_211, 2_811, 3_119, 3_061, 2_964, 2_757)},
    },
}


def per_asset(cells: dict) -> dict:
    """A cell table keyed by asset, as `_b2_rerisk_counts` returns it."""
    return {
        key: {
            tail: {state: dict(zip(subjects._ASSETS, counts)) for state, counts in by_state.items()}
            for tail, by_state in by_tail.items()
        }
        for key, by_tail in cells.items()
    }


def reading_inputs():
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b2_rerisk_inputs("b2-rerisk-reading", reader, "ohlc-full", None, False)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-funding/*/funding.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-daily/*/daily.parquet"),
    reason="the frozen ohlc-full set, the derivatives-funding or derivatives-oi set or the frozen daily liquidations block is absent "
    "under data/",
)
def test_the_rerisk_readings_inputs_reproduce_the_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = reading_inputs()
    assert compute_hash(reader.block()) == BLOCK
    assert reader.vouched_status() == VOUCHED
    assert len(inputs.close) == _RETURN_INDICES
    assert list(inputs.signals) == list(SIGNAL_FROM)
    for key, (index, first) in SIGNAL_FROM.items():
        signal = inputs.signals[key]
        assert next(k for k in range(_RETURN_INDICES) if all(signal[a][k] is not None for a in subjects._ASSETS)) == index, key
        assert inputs.close[index] == first, key
    pairs = {a: list(zip(inputs.arm_a[a], inputs.full_long[a], strict=True)) for a in subjects._ASSETS}
    assert tuple(sum(p > 0 for p, _ in pairs[a]) for a in subjects._ASSETS) == ARM_A_LONG
    assert tuple(sum(p == 0 for p, _ in pairs[a]) for a in subjects._ASSETS) == ARM_A_FLAT
    assert tuple(sum(0 < p < f - _TOLERANCE for p, f in pairs[a]) for a in subjects._ASSETS) == BELOW_FULL
    assert tuple(sum(p > 0 and abs(f - p) <= _TOLERANCE for p, f in pairs[a]) for a in subjects._ASSETS) == AT_FULL
    assert not any(p > f + _TOLERANCE for a in subjects._ASSETS for p, f in pairs[a])
    assert subjects._b2_rerisk_counts(inputs) == {"events_per_asset": per_asset(EVENTS), "others_per_asset": per_asset(OTHERS)}
```

- [ ] **Step 2: Run it** — with the four sets linked in this worktree: `mkdir -p .tmp/plan-00142 && uv run pytest tests/test_research_b2_rerisk_reading_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00142/pt`, one plain blocking call, `timeout` 600000 ms: `1 passed`, never a skip (measured on the authoring tree, 357.49 s). The case joins `tests/slow-cases.txt` at its `sorted()` place:

```text
tests/test_research_b2_rerisk_reading_basis.py::test_the_rerisk_readings_inputs_reproduce_the_measured_basis
```

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b2_rerisk_reading_basis.py tests/slow-cases.txt`; the Global Constraints' `T` over the two paths (measured `18 passed, 1 deselected in 25.81s`); the two tree walkers its skip gate and data mark meet, `mkdir -p .tmp/plan-00142 && uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00142/pt` (measured `324 passed`); `uv run pre-commit run -a` until clean. No probe: the case is slow, recorded `probe skipped: slow case`.
- [ ] **Step 4: Commit** — `test(research): B2's re-risk reading's inputs against the measured basis — the block, the signals' starts, arm A's states and full-long split, and each cell's events and others`.
- [ ] **Step 5: The decisions-log entries, before the hash** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`, after one blank line, the loop's pick (spec 00142 D1) and then **Author's call** the reading's conventions, plan 00141's shape, so that the criterion stands in the log before any forward is read:

```markdown
[iter-186] B2's next step after the second signal reading — a third no-slot reading, the re-risk's own state below arm A's full-long size, the loop's pick under the owner's run instruction (Decision: 2)
  The owner launched an unattended run, verbatim: "continue pushing the Research strates forward, pick the most relevant tasks. override the wall clock time gate, but do not pick up new topics after 8:00Z. when closing out a research step, try the trials with potential and do not close any family too early." T0023's trigger after reading 4 — `[iter-185] B2's eight untested crowding signals read for forward returns by tail and by arm A's state on frozen ohlc-full (reading 4)`, in which no cell had potential under spec 00141's criterion, as none had in reading 3 under spec 00140's — named the pick of B2's next step; the run picked, a close of B2 being the owner's. Standing and unchanged: the instrument ruling "Frozen ohlc-full (Recommended)".
  1. **Variants of the trials already run** — a de-risk at another scale or threshold, the re-entries' park variants. Each spends a B slot (14 of 25 remain), and neither reading shows a de-risk or re-entry cell with potential.
  2. **A third no-slot reading over the re-risk's own state** — spec 00142: the twelve signals of readings 3 and 4 by tail where arm A is long below its full-long size, the one state a re-risk can act in, by reading 4's forwards, draw and criterion, its first leg at the Bonferroni bounds over 72 cells. Both readings' nearest cells are re-risks at 96 hours — the funding z-score (reading 3), the long side's liquidation z-score (reading 3, leg 4), the short side's and the total's (reading 4), each above +2.0 with arm A long — but 7,102 of those cells' 12,215 events fall where arm A already holds its full-long size, where no re-risk acts (spec 00142's measured basis). Spends no slot and screens the re-risk where it can engage before a slot is spent. Chosen.
  3. **A re-risk trial spent directly on a near-miss** — one of 14 slots on a cell neither reading admitted under its criterion.
  4. **The 1-minute tape, or a close of B2** — an instrument ruling and a family call, both the owner's.

[iter-186] B2's re-risk reading's conventions, pinned by spec 00142 before its hash (Decision: 1)
  The reading's details are fixed in the spec, reviewed, and frozen by its sha256, the reading's `spec_hash`, before any forward return is computed over the data; each call below is one the spec pins, the author's unless it names the ruling or the spec it carries, every value the owner or specs 00137–00141 fixed staying theirs.
  1. **As the spec pins them** — one reading subject, `b2-rerisk-reading`, named so that no registered or retired subject's name opens it and it opens none, with no rule, family or count, kept with `--reading` and spending no B slot, over frozen `ohlc-full`'s full history (D2); arm A by calling `_b2_overlay_inputs` itself on reading 3's funding reader, the funding z-score being one of the twelve signals, so the block is reading 3's; arm A's full-long size per asset and close spec 00139's — the arms' shared inverse-vol weight times the mean of their vol-target levels — from the three books rebuilt over the union's prices by `_b2_full_long`, since `_b2_overlay_inputs` returns arm A and never its books; one state, arm A long below that size by more than 1e-12, the one state a re-risk can act in, its others the other read closes in it, the closes at the size and the flat ones flagging nothing (D3); the twelve signals of readings 3 and 4, each by its reader, unchanged, and their one threshold for both tails, strictly above 2.0 and below −2.0 (D4); reading 3's forwards unchanged, the log return over 1, 6 and 24 closes and the simple returns summed over them (D5); per cell, the events against the other read closes below the size, per asset and pooled, reading 4's row with its far bounds at 2.5/72 % and 100 − 2.5/72 %, the Bonferroni percentiles over 72 cells, from reading 4's own draw — mean block 102, 40,000 resamples, seed 42, drawn once as its blocks and read by `event_contrast_blocks` — each far bound between the 14th and 15th most extreme resampled differences where every resample is usable (D6); 79 keys, the state kept as `below_full` and the tolerance recorded, and reading 3's refusals (D7); the potential criterion — read first, a floor of at least 2 kept assets and 100 events on the log return's pooled row, a cell under it unread, as the counts leave the taker ratio's and the total's lower tails; then on the log return's pooled row its far bounds excluding 0, Bonferroni over 72 cells though nine read no row and six fall under the floor, the difference at least 0.012 in size, positive a re-risk and negative a de-risk, and on the summed returns' pooled row the mean after the events, per unit of exposure added or removed, at least +0.012 for a re-risk and at most −0.012 for a de-risk — read by the closeout's pick and never by code, the contamination stated in full — the trials' instrument, readings 3's and 4's results known and the state chosen because their nearest cells were re-risks, its events part of theirs, its correction over its own 72 cells and not the three readings' 216, a trial it justifies carrying all three readings' ids — a cell with potential naming its trial and none the evidence for the owner's family call (D8); one run after the hash, no plain eval before or after it (D9). Chosen.
  2. **The alternatives each weighed** — `_b2_reentry_inputs` for arm A and its books, with an arm B no reading has; `_b2_overlay_inputs` changed to return its books; arm A below its full-long size with no tolerance, flagging rounding as a state; the long state whole, readings 3's and 4's; the closes at the full-long size as a second state, where no re-risk acts; the keys without the state level; 28,801 resamples, the least putting each far bound ten differences in; a Bonferroni count over the three readings' 216 cells; a rule over the criterion; a re-risk trial spent on a near-miss in the reading's place (the pick above).
  Source: spec 00142 (D1–D9), its **Author's call**s and the calls it carries from the owner and specs 00137–00141; the owner's run instruction quoted in the pick above.
```

  staged alone, its gate `mkdir -p .tmp/plan-00142 && uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00142/pt` (measured in a scratch worktree, the two entries appended, `50 passed`) and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-186] B2's next step after the second signal reading — the loop's pick, a third no-slot reading over the re-risk's own state — and its conventions, pinned by spec 00142 before its hash`. The pick's header is what T0023's `ripe_when` greps for (`B2.s next step after the second signal reading`; measured in the scratch worktree, the check prints 1 once the entry stands); Task 6 gives T0023 its next trigger.
- [ ] **Step 6 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–3 and the two entries — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing computes a forward return or runs the reading over the real data before the spec's hash, and the data-gated case runs with the frozen full set, the funding set, the OI set and the daily liquidation block linked into the reader's worktree and unlinked by the reader before its report, since unlinked it skips. Each report names the tip it read, the tip Task 4 step 1 diffs from. Task 4 waits until the trio has closed with no open Critical or Important.

## Task 4 (the controller's): the gate, the spec hash, the develop check, the data test and the check programs (D9)

- [ ] **Step 1: The gate** — each check its own call, each read before the next: the reads through Task 3 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00142-b2-rerisk-reading-design.md docs/research/10.phase4-decisions.md` exits 0; the conventions entry against the spec at that tip, each item where the spec pins it; arm A's code path since reading 4's run (its ledger line's `invocation.commit`, `973a06f4a`, after reading 3's), `git log --oneline 973a06f4a..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/derivatives cli/liquidations cli/data uv.lock pyproject.toml .python-version`, lists Tasks 1's and 2's commits and their fixes alone (measured at the base: nothing); any other commit is named, step 4's data test deciding whether it moved the inputs.
- [ ] **Step 2: D9 (1), the spec hash** — `sha256sum docs/specs/00142-b2-rerisk-reading-design.md`; its value, pasted from that call, is the run's `--spec-hash` and the reading's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D9 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0. A non-zero exit stops before the run: the controller reads which line moved, the same `git diff` without `--quiet`, and only for a line another writer appended legitimately — a registry record another branch's merged PR carries; the operating model gives the reading ledger no other writer while this branch is open, so a line there stops the task, T0023's — merges develop, alone (`git merge --no-edit origin/develop`) — a conflict confined to `docs/research/10.phase4-decisions.md` or `tests/slow-cases.txt` resolved keeping both sides' lines, in the decisions log develop's entries above this branch's and in the slow-cases file each line at its `sorted()` place, and committed as the merge; a conflict in any other file aborted with `git merge --abort`, which stops the task, T0023's — then takes a delta read of the merge in place of re-running step 1: step 1's arm-A log over `<the tip the last read names>..HEAD`, then `pre-review`, then `review` over that range and `re-review` over a fix of it within the branch's two, each `drive` carrying Task 3 step 6's sentence with its "before the spec's hash" read "before Task 5's run", the commits the log lists, and one sentence more: develop's commits were each read on their own PR, so the read judges the merge's resolution and each listed commit's effect on the reading — whose tip becomes the tip the last read names, and step 4 runs on the merged tree. The check has two sites, this step and Task 5 step 1, and both take this path.
- [ ] **Step 4: D9 (3), the data test on the run's tree, with the subject's two fixture rows** — `mkdir -p .tmp/plan-00142 && ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b2_rerisk_reading_basis.py` followed by Task 2 step 6's two quoted node ids, then `-q -p no:cacheprovider --basetemp=.tmp/plan-00142/pt > .tmp/plan-00142/basis.out 2>&1`, one background call: `3 passed`, never a skip — the fixture rows run the build end to end on the tree a fix of the reads may have changed; a failure is a finding before the run — the data test's an instrument finding, a fixture row's a defect in the code — T0023's, and the run waits.
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00142/reading_check.py`, the ledger line's checks:

```python
"""Spec 00142's reading, read off the ledger's last line against the run's print and the measured basis: exit 0 when
every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b2_rerisk_reading_basis import BLOCK, EVENTS, OTHERS, VOUCHED, per_asset

spec_hash = sys.argv[1]
r = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(".tmp/plan-00142/b2-rerisk-reading.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
events, others = per_asset(EVENTS), per_asset(OTHERS)
cells = [(key, tail, "below_full", hours) for key in EVENTS for tail in ("above", "below") for hours in (4, 24, 96)]
rows = {cell: m[f"{cell[0]}_fwd_logret_{cell[3]}h"][cell[1]][cell[2]] for cell in cells}
book = {cell: m[f"{cell[0]}_fwd_sumret_{cell[3]}h"][cell[1]][cell[2]] for cell in cells}
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "invocation": invocation
    == {"subject": "b2-rerisk-reading", "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["iteration"], r["outcome"], r["attempt"]) == ("iter-186", None, None),
    "keys": set(m) == SUBJECTS["b2-rerisk-reading"].metric_keys,
    "printed": printed["metrics"] == m,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == BLOCK and printed["vouched"] == VOUCHED,
    "constants": (m["threshold"], m["full_long_tolerance"], m["mean_block"], m["n_resamples"], m["far_percentiles"])
    == (2.0, 1e-12, 102, 40000, [2.5 / 72, 100 - 2.5 / 72]),
    "counts": (m["events_per_asset"], m["others_per_asset"]) == (events, others),
    "cells": len(cells) == 72 and all(set(m[key]) == {"above", "below"} and all(set(by) == {"below_full"} for by in m[key].values()) for key in m if "_fwd_" in key),
    "rows": all(len(row) == 9 for table in (rows, book) for by_name in table.values() for row in by_name.values()),
    "ordered": all(row[7] <= row[5] <= row[6] <= row[8] for table in (rows, book) for by_name in table.values() for row in by_name.values()),
    "paired": all(
        list(book[cell]) == list(by_name) and all(book[cell][name][:2] == row[:2] for name, row in by_name.items())
        for cell, by_name in rows.items()
    ),
    "bounded": all(
        by_name[a][0] <= events[key][tail][state][a] and by_name[a][1] <= others[key][tail][state][a]
        for (key, tail, state, _), by_name in rows.items()
        for a in by_name
        if a != "pooled"
    ),
    "pooled": {cell for cell, by_name in rows.items() if "pooled" in by_name}
    <= {cell for cell in cells if any(events[cell[0]][cell[1]][cell[2]].values())},
}
print(r["reading_id"], checks)
sys.exit(0 if all(checks.values()) else 1)
```

  and `.tmp/plan-00142/pooled_rows.py`, the print Task 5's entry reads the criterion off:

```python
"""The reading's 72 pooled cells off the ledger's last line, one a line: the signal, tail, state and horizon, then the
log forward's kept assets and its pooled row's events, others, difference and far low and far high bounds and the summed
returns' mean after the events, or `no row`; it judges none of them."""

import json
from pathlib import Path

m = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])["metrics"]
signals = (
    "binperp_funding_z30d",
    "binperp_oi_z30d",
    "binperp_ratio_max_z30d",
    "binperp_liq_long_z30d",
    "binperp_oi_log_delta_z30d",
    "binperp_oi_momentum_z30d",
    "binperp_count_toptrader_long_short_ratio_z30d",
    "binperp_sum_toptrader_long_short_ratio_z30d",
    "binperp_count_long_short_ratio_z30d",
    "binperp_sum_taker_long_short_vol_ratio_z30d",
    "binperp_liq_short_z30d",
    "binperp_liq_total_z30d",
)
for key in signals:
    for tail in ("above", "below"):
        for hours in (4, 24, 96):
            rows = m[f"{key}_fwd_logret_{hours}h"][tail]["below_full"]
            row = rows.get("pooled")
            book = m[f"{key}_fwd_sumret_{hours}h"][tail]["below_full"].get("pooled")
            print(key, tail, "below_full", f"{hours}h", "no row" if row is None else [len(rows) - 1, row[0], row[1], row[4], row[7], row[8], book[2]])
```

  Each is written with `mkdir -p .tmp/plan-00142 && cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00142/reading_check.py .tmp/plan-00142/pooled_rows.py`. **Author's call — the `pooled` check a subset, not an equality**: a cell whose events hold no asset with two events and two others whose forward is read keeps no pooled row, which the counts alone cannot decide before the run — two pairs, six cells, hold few events (spec 00142's basis) — so the check refuses a pooled row in a cell with no event, and the print shows any other cell reading `no row`, which Task 5's entry names. **Author's call — the `cells` check reads the state**: every forward key holds both tails and each tail the one state, so a line keyed under another state fails before any row is read.

## Task 5 (the controller's): the reading — its run, its line, its replay and its entry (D8, D9)

`<H>` is Task 4 step 2's sha256.

- [ ] **Step 1: The develop check** — Task 4 step 3 whole, its stop, its merge path and Task 4 step 4 after a merge with it; `git status --short` prints nothing.
- [ ] **Step 2: The run** — one run, no plain eval before or after it: `mkdir -p .tmp/plan-00142 && uv run zcrypto research eval --subject b2-rerisk-reading --dataset ohlc-full --reading --iteration iter-186 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00142/b2-rerisk-reading.out 2>&1`, about nine minutes (the spec's basis), one background call, `cat` at its notification. The notes, written before the run, name only what is fixed before it: `subject b2-rerisk-reading over ohlc-full, full history, no as-of; descriptive, no bar, no verdict, no B slot, changing no verdict of B2 trials 2-7 nor readings 3's and 4's findings; the twelve crowding signals readings 3 and 4 read, each by its reader - the 30-day funding z-score, the open-interest z-score, the long/short ratios' maximum z-score, the daily long-side liquidation z-score, the open-interest log-change and 30-day momentum z-scores, each of the four long/short-ratio z-scores singly, and the daily short-side and total liquidation z-scores; the one state of arm A at the close in which a re-risk acts, long below its full-long size by more than 1e-12; per signal and tail (above 2.0, below -2.0), per asset and pooled: the forward 1-, 6- and 24-close log returns on the arms' prices, and the simple returns summed over the same closes, after the closes past the tail, against the other closes where the signal is read in the same state; stationary-bootstrap 2.5/97.5 % bounds and far bounds at the Bonferroni percentiles over 72 cells, 2.5/72 % and 100 - 2.5/72 %, mean block 102, 40000 resamples, seed 42, one draw shared by every cell; the potential criterion - read first, a floor on the log returns' pooled row of at least 2 kept assets and 100 events, a cell under it unread; then on the log returns' pooled row the far bounds excluding 0, the difference at least 0.012 in size, positive a re-risk and negative a de-risk, and on the summed returns' pooled row the mean after the events, per unit of exposure added or removed, at least +0.012 for a re-risk and at most -0.012 for a de-risk - read by the closeout's pick, never by code; pre-registered by the spec's sha256 <H>`. A refused build — exit 1 with no traceback, naming `b2-rerisk-reading over the full history: …` or a file of `derivatives-funding`, `derivatives-oi` or `liquidations-daily` — keeps no reading and is recorded in T0023 with its line quoted (Task 6), the reading's design standing unrun; a refusal before the build reads anything — the tree (`… has uncommitted changes …`), the spec hash (`--spec-hash … is not …`) or the dataset's presence (`dataset 'ohlc-full' is absent …`, `… is missing N series …`) — keeps nothing and computes nothing: its cause fixed, the same command runs again, still the one run; a traceback, a signal or a ledger refusal stops the task, T0023's with the end of the run's output quoted whole.
- [ ] **Step 3: The reading's checks** — `uv run python .tmp/plan-00142/reading_check.py <H>` exits 0; a failed check stops the task before step 4.
- [ ] **Step 4: The pooled rows** — `uv run python .tmp/plan-00142/pooled_rows.py`, its 72 lines the entry's source.
- [ ] **Step 5: The records commit** — (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-186] B2's twelve crowding signals read for forward returns by tail where arm A is long below its full-long size on frozen ohlc-full (reading <its reading_id>)`, its header to its first `. ` holding no verdict word; the body: the subject, the set and the block `ad140b62…cf8eee1`; that the reading is descriptive, spends no slot and changes no verdict nor readings 3's and 4's findings (D2, D8); the cells under the floor, each unread — those step 4's print shows with fewer than 2 kept assets or 100 events, the six of the basis's two thin pairs among them — and for each of the criterion's four legs, the cells the floor admits that meet it — signal, tail and horizon — read off step 4's print, leg 3 naming each cell's action, a re-risk or a de-risk; the pooled rows, the log forward's and the summed returns', nine entries each unrounded, read off the reading's ledger line, of every such cell meeting the first leg, each bound named by its family; the cells with potential, each with the trial it names — the action on that signal past that tail, where arm A is long below its full-long size, held H closes, and, where the signal is a part of a trialled one or the action a rejected trial's, which — or, where none has potential, that no cell has it and that this is the evidence the owner's family call reads; the cells that read no row, the basis's nine and any other the print shows; the caveats — the far bounds between the 14th and 15th most extreme of 40,000 resampled differences where every resample is usable, a thin cell's usable count unrecorded, and equal to the chunked contrast's to rounding; the rows counting the closes with a forward and `events_per_asset` every flagged close; and the contamination D8 states, its events the part of readings 3's and 4's long-state events below the full-long size and its correction over this reading's 72 cells and not the three readings' 216 among it; in the form of reading 4's `[iter-185]` entry; (ii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-<its id>]` at its `sorted()` place, the replay rebuilding the whole reading. Then `git add` by path of the ledger, the decisions log and the slow-cases file; `T` over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path; `uv run pre-commit run -a` until clean, its rewrites staged. In the probe worktree, which the Global Constraints' probe setup creates from that index and whose tree it prints, the four sets linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/<set> .tmp/plan-00142/probe/data/<set>`, unlinked after the replay and the worktree removed as the Global Constraints' probe paragraph removes one that held a link: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'reading-<its id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt` passes, one background call, its result line and call time for the message — a difference stops the task. Commit that index, with no `git add` after the setup, as `docs(research): B2's re-risk reading — the twelve crowding signals' forward returns where arm A is long below its full-long size on ohlc-full, kept as reading <id>; no trial spent`, the message carrying the tie tests' result line, the replay's with its call time, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-<id>]`, the line `The replay reads data/ohlc-full, data/derivatives-funding, data/derivatives-oi and data/liquidations-daily: re-run it with the four sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.`, and the two trailer lines; after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes. The entry adds no guard: no probe.

## Task 6: T0023, T0016, the index and the retirement of the subject (D8)

**Files:** `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/retired_subjects.py`, `tests/test_research_command.py`.

On a refused build (Task 5 step 2) no reading exists: Task 5's steps 3–5 do not run, so no finding entry lands, and this task runs without a reading. Every sentence of Tasks 6–7 that assumes a reading changes, and these are all of them: step 1's Findings bullet, headed `**B2's re-risk reading (iter-186, spec 00142).**`, quotes the refused line; its Done-so-far bullet names no reading; its next-step bullet keeps every candidate it lists, its words from `reading spec 00142's potential criterion` through `beside the criterion` reading `reading the refused build, quoted in Findings, the design unrun; beside it`, with no arm for a reading in which no cell has potential, and its trigger's `reading spec 00142's potential criterion` becomes `reading the refusal`, its check unchanged; step 2's B2 line names the re-risk reading refused, with no reading id; step 4 does not run, since a later run still evaluates the subject (`tests/retired_subjects.py`'s own rule), so step 5 stages the three `docs/open-topics/` paths alone and its message ends `the reading refused, its subject kept`; Task 7 step 2's `drive` names the data-gated case alone, no replay; and Task 7 step 3's body quotes the refused line in place of the pooled rows and names no cell.

- [ ] **Step 1: T0023**, per `topic-ops`, every figure read off the committed reading and its entry: `## Findings so far` gains one bullet — `**B2's re-risk reading (iter-186, spec 00142, reading <N>).**` — in one or two sentences, the cells with potential and the trial each names, or that none has potential, pointing at its decisions-log entry for the figures; or, on a refused build, its line quoted whole from `.tmp/plan-00142/b2-rerisk-reading.out`; `## Done so far` gains **B2's re-risk reading (iter-186, spec/plan 00142)**, naming arm A's full-long size rebuilt beside reading 3's arm A (`_b2_full_long`), the flags of the state below it (`_b2_rerisk_flags`), the subject `b2-rerisk-reading` and the data-gated basis test `tests/test_research_b2_rerisk_reading_basis.py`, and the reading by id; `## Suggested next steps` replaces `(the loop's pick under a run instruction, else the owner's; a close is the owner's) B2's next step after the second signal reading` with `(the loop's pick under a run instruction, else the owner's; a close is the owner's) B2's next step after the re-risk reading` — reading spec 00142's potential criterion: a trial a cell with potential names, each its own pre-registration against the shared B budget carrying D8's contamination, or, with none, the owner's family call, hold or close B2; beside the criterion the pick reads every candidate still untried, and the bullet drops none but the one this reading read — the replaced bullet's own: a de-risk variant (scale 0.25, threshold 3.0), the de-risks' and the re-entries' further legs, a trial on the tape, a follow-up reading 2's figures invite (the daily history reconciled with the tape, the reading at a later as-of or over a longer span, a per-side reading), the re-entries' park variants (the threshold one step toward 0, the size halved), and a reading at another threshold, signal, horizon or state split, on another instrument, on the tape or at a later as-of, the full-long split of arm A's long state dropped as this reading's own; and the options this pick set aside (spec 00142 D1): a re-risk trial spent directly on a near-miss, the 1-minute tape and a close of B2 — recorded as a `[iter-NNN] B2's next step after the re-risk reading` entry; `ripe_when`: ``an activity: B2's next step after the re-risk reading is picked, reading spec 00142's potential criterion, recorded in the decisions log; check: `grep -c -E '^\[iter-[0-9]+\] B2.s next step after the re-risk reading' docs/research/10.phase4-decisions.md` prints at least 1``, in the frontmatter's quoting, the check kept in its own backticks. The check is run as committed and prints 0.
- [ ] **Step 2: T0016** — its budget line's figures read off the count the bucket refusal reads, every orphan in it, `uv run python -c 'import json; from pathlib import Path; from cli.registry import attempts, budget; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])'` — the reading spends none (measured at this branch's base: `{'B1': 5, 'B2': 6} remain 14 []`, T0016's line `B1 spent 5, B2 spent 6, 14 remain`): the line reads `B1 spent <its B1>, B2 spent <its B2>, <its remain> remain`, each orphan it lists named on that line; its B2 line names the re-risk reading (iter-186, spec/plan `00142`, reading <N>), no slot spent.
- [ ] **Step 3: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 4: The retirement** — **Author's call**, `tests/retired_subjects.py`'s own rule: no trial still to run evaluates the reading's subject, so `RETIRED_SUBJECTS` gains `"b2-rerisk-reading",` after `"b2-second-signal-reading",`, its comment `# B2's finished trials and the readings beside them.` unchanged; and every test function of `tests/test_research_command.py` specific to the subject and named by no parameter carries `@pytest.mark.retired` as its first decorator — all eight Tasks 1–2 add: `test_the_rerisk_readings_inputs_are_the_overlays_union_and_arm_a_its_full_long_size_and_each_signal_by_its_reader`, `test_the_rerisk_readings_full_long_size_is_the_reentries_own_over_rebuilt_books`, `test_a_rerisk_flag_is_an_event_past_its_tail_below_full_long_another_read_close_below_it_and_none_elsewhere`, `test_the_rerisk_reading_counts_each_assets_events_and_others_below_full_long_per_signal_and_tail`, `test_the_rerisk_reading_declares_the_4h_grid_its_keys_and_no_rule`, `test_the_rerisk_reading_hands_every_cell_one_shared_draw_and_keys_its_rows`, `test_the_rerisk_reading_refuses_as_of_before_any_read` and `test_the_rerisk_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it` — their functions read only the subject's own new code. `uv run pytest tests/test_research_command.py -m "not retired" --collect-only -q -p no:cacheprovider | grep -c -E "rerisk"` prints 0 and the same under `-m retired` prints 20 (measured in the scratch worktree), and `mkdir -p .tmp/plan-00142 && uv run pytest tests/test_retired_subjects.py -q -p no:cacheprovider --basetemp=.tmp/plan-00142/pt` passes (measured `5 passed`).
- [ ] **Step 5: Gate and commit** — `git add` the five paths; `T` over them with `tests/test_open_topics_frontmatter.py` and `tests/test_retired_subjects.py` by path, in its three parts; `uv run pre-commit run -a` until clean; committed as `docs(open-topics): T0023 and T0016 after B2's re-risk reading; the reading's subject retired`.

## Task 7 (the controller's): the change-index row, the read and the PR

- [ ] **Step 1: The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-186 — B2 re-risk reading: below full-long size` (67 characters by `printf '%s' <it> | wc -m`, under the cap), its own commit.
- [ ] **Step 2: The read** — the `pre-review` of Tasks 5–6's commits and the row's, then `review` over `<the tip the last read names>..HEAD`, and `re-review` over a fix of it within the branch's two, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated case and the replay the messages record run with the frozen full set, the funding set, the OI set and the daily liquidation block linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 3: The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the reading's pooled rows as step 4 of Task 5 printed them, in a fenced block, with the cells under the floor, the cells the floor admits meeting each leg of the criterion and those with potential, or none; every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the last read names. Merged through `merge-pr`; before it, `git status --short --ignored` read, `.tmp/plan-00142` collected and removed, and `unlink data/ohlc-full`, `unlink data/derivatives-funding`, `unlink data/derivatives-oi` and `unlink data/liquidations-daily` run in this worktree and in each reader's checkout whose `data/` holds the link; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows the four sets still there.

Decisions log: the loop's pick and the conventions entry (Task 3 step 5), before the hash; the reading's finding entry (Task 5 step 5), in its line's commit.
