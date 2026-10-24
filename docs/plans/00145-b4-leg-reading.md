# B4's leg reading — trial 58's books by leg and by cost on frozen ohlc-full: the reading subject, its data-gated basis test, the loop's pick and the conventions before the hash, its run, its line, its entry and its retirement — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt tests/test_research_b4_leg_reading_basis.py docs/research/10.phase4-decisions.md docs/reference/reading-ledger.jsonl tests/retired_subjects.py docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/README.md docs/reference/change-index.md docs/specs/00145-b4-leg-reading-design.md docs/plans/00145-b4-leg-reading.md` prints `tier: full`, for `tests/test_research_command.py` "a test importing cli.alpha" and, once Task 2 has created it, `tests/test_research_b4_leg_reading_basis.py` "a test importing cli.registry.observed").

**Goal:** B4's leg reading (spec 00145) — one reading subject, `b4-leg-reading`, in `cli/research/subjects.py`: each ratio leg alone beside the ten EUR assets in the adopted A2 arms, as trial 58 costed arm B and held to the book's own BTC, read against arm A from the leg's first weight, and trial 58's arm B read against arm A by cost layer; the data-gated test of its inputs half; the loop's pick and the reading's conventions in the decisions log before the hash; the reading's one run, kept on the reading ledger and replayed; its finding, T0016 and the subject's retirement.

**Architecture:** no new module and no change to `cli/alpha/`. `cli/research/subjects.py` gains one block before `SUBJECTS` — `_B4LegInputs`, `_b4_leg_inputs`, `_b4_leg_engagement`, `_b4_cost_layers`, `_b4_leg_metrics`, `_build_b4_leg_reading` and `_B4_LEG_KEYS` — and one `SUBJECTS` entry; trial 58's `_b4_reads`, `_b4_inputs`, `_b4_ensemble`, `_b4_limited`, `_b4_shortfall` and `_b4_net` and `cli/alpha/b4.py`'s functions are read as they are, and no import is added. Nothing writes a dataset.

**Tech Stack:** Python 3.14 through uv; polars; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00145-b4-leg-reading-design.md` — binding; D1–D8 are cited by name and the values below are copied from it. It reads spec 00144's instrument, books, costing, carry, limits and twin, frozen by record 58's `spec_hash`. **Iteration:** iter-190. **Topic:** T0016, its B4 arm. **Branch:** `research/iter-190-b4-leg-reading`, worktree `.claude/worktrees/iter190`, `data/ohlc-full` linked read-only from the main checkout, and no other set. A choice this plan makes that the spec leaves open is marked **Author's call**. Every code fence below was cut from the files the author ran: the code and tests of Tasks 1–2 were written in this worktree beside the staged spec; Task 1's new cases measured red against the base module, in a detached scratch worktree at the base with the test file alone applied (`9 failed, 815 deselected`, each at its call), and green with the code (`9 passed, 824 deselected`), the shared rows the subject adds green (`9 passed, 824 deselected in 96.48s`); Task 1 step 7's four gate parts green; Task 2's data-gated case `1 passed` with a call of 359.69 s; the slow cases timed; Task 1's 52 probe rows run in a detached scratch worktree on Task 1's tree, committed there, 52 of 52 `KILLED`; Task 2's two decisions-log entries appended there over Tasks 1–2's tree and run through the decisions-log tests; Task 5's T0016 edits, the index and the retirement tried there; and Task 3's two check programs run over a synthetic ledger line and print. The fences applied to the base as the steps say reproduce every authoring file; the files were restored to the base before this plan was committed. Not run: the reading itself and its replay (Task 4), the topic edits as committed (Task 5) and the PR (Task 6).

## Global Constraints

- **The books and the costing** (D2, D3): trial 58's reads `_b4_reads("b4-leg-reading", reader, dataset, window, accept_holes)` and its books `_b4_inputs(reads)`, unchanged; each leg's `raw = _b4_ensemble(fed | {leg: ratios[leg]})`, `fed = _ffill_btc(h4_prices)`, its `carried` book `_b4_limited(raw)` and its `no_borrow` book `_b4_limited(borrow_unavailable(raw, _B4_LEGS, "BTC"))`, keyed `{leg: {funding: …}}`; each leg's first weight the first return index of `_inverse_vol_weights(fed | {leg: ratios[leg]}, lookback=180)` holding it; every book costed by `_b4_net(book, returns, stress=1.0)`, `returns` trial 58's.
- **The reads** (D4, D5): every head-to-head `net_of_cost_verdict(<book>[first:], <bench>[first:], mean_block=30, seed=42, n_resamples=2000)` — per cell at its leg's first weight and at 0, against `net_a = _b4_net(arm_a, returns, stress=1.0)`; trial 58's cost layers at `min(trial 58's first weights)`, 5,442, `gross` `net_of_cost(book, returns, cost_per_side=0.0)`, `net_of_trading` `net_of_cost(book, returns, cost_per_side=0.006)` and `net` `_b4_net(book, returns, stress=1.0)`, each for arm B and for arm A; per cell `sharpe` at 2,190 periods a year and `max_drawdown` over both windows beside arm A's, and per close year the mean outperformance; trial 58's carry apportioned to its legs pro rata to their positions at each bar; refused before any head-to-head: fewer than 2 return indices from a leg's first weight.
- **The keys** (D6): 31 — per cell, `{leg: {funding: value}}`, `head_to_head_mean_outperf_primary`, `head_to_head_spa_p_primary`, `head_to_head_mean_outperf_full`, `head_to_head_spa_p_full`, `mean_outperf_per_year`, `ann_sharpe_noc_primary`, `ann_sharpe_noc_full`, `max_drawdown_primary`, `max_drawdown_full`, `held_per_year`, `positions_differ_per_year`, `turnover`, `shortfall_stamps_per_year`, `shortfall_mean_per_year`, `carry_per_year`, `limit_engaged`; per leg, `first_weight`, `primary_returns`, `arm_a_ann_sharpe_noc_primary`, `arm_a_max_drawdown_primary`; `arm_a_ann_sharpe_noc_full`, `arm_a_max_drawdown_full`, `turnover_a`, `turnover_b`; `context_head_to_head_mean_outperf` and `context_head_to_head_spa_p` over `gross`, `net_of_trading` and `net`, `context_carry_by_leg`, `context_turnover_by_leg` over `ETH/BTC`, `SOL/BTC` and `EUR`; `mean_block` 30, `seed` 42, `n_resamples` 2000; the engagement the measured basis's (Task 2's literals).
- **The criterion** (D7): read by Task 4's entry off the cells print, never by code; the subject has no rule, and no program of this plan judges a cell. Its floor and three legs are written in words in two places beside D7, which a read against D7 alone checks — the conventions entry (Task 2 step 5) and the run's notes (Task 4 step 2) — and the cells print (Task 3 step 5) carries every figure the floor and the legs read: each cell's holding, its primary mean outperformance and SPA p, and its drawdown from its leg's first weight beside arm A's.
- **The hash rule** (D8): before Task 3 step 2 takes the spec's sha256, nobody reads or computes any cell's returns or net-of-cost series, any head-to-head, or the cost layers' gross or trading split — through the subject's code, through a program, or by D7's arithmetic over record 58's stored net head-to-head, turnover and carry — nor runs `b4-leg-reading` over the real set; positions, weights, exposures, the shortfall, the carry it implies, limit engagement and turnover are allowed — what the data-gated test (Task 2) computes, and no return of a book. `a2_book_returns` computes each book's base returns internally to size its positions; nothing reads them. No reader, reviewer or plan-review dispatch runs the subject over the real set before the hash, and every read's dispatch carries this rule. The subject is evaluated over the real set once, by Task 4's `--reading` run, never as a plain eval; after that run it is rebuilt over it only by its replay case in `tests/test_registry_replay.py`, wherever that case runs with the set linked, as Task 4 step 5 and Task 6 step 2's reads run it.
- **Unchanged** (D6): every existing function of `cli/research/subjects.py` — trial 58's machinery among them — `cli/alpha/*`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/risk/*`, `cli/costs/*`, `cli/validation/*` and `cli/engine/*`; trial 58's subjects and record 58; any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-only $(git merge-base HEAD origin/develop) -- cli/` prints `cli/research/subjects.py` from Task 1 on, nothing else; from Task 1 on, `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@')" = 2` and `test "$(git diff -U0 $(git merge-base HEAD origin/develop) -- cli/research/subjects.py | grep -c '^@@ -[0-9]*,0 ')" = 2` each exit 0 — two hunks, each a pure insertion, so a line changed or added anywhere but at Task 1 step 3's two sites is a third hunk or an impure one. Measured on the authoring tree: `@@ -3778,0 +3779,188 @@` and `@@ -4158,0 +4347,9 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00145-b4-leg-reading-design.md` after Task 3 step 2, nor specs 00141, 00142 and 00144, nor the spec before then except a fix commit a read of Task 2 step 6 asks for; never write `docs/reference/trial-registry.jsonl`, nor run `--register`; never write `docs/reference/reading-ledger.jsonl`, nor run `--reading`, except where Task 4 names it. Never `git stash`; no amend; never `--no-verify`; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-full`, a read-only link, never written under. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/`, a fleet host, docker, `kraken-cli`, the vault, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`. The reading, every test and every implementer step make no network call and no ssh connection; the controller's `git fetch origin develop` (Task 3 step 3, Task 4 step 1) and Task 6's `gh` calls, push and `merge-pr` are the exceptions. A data link is removed with `test -L <its absolute path> && unlink <its absolute path>`, never `rm`.
- **Research only**: nothing is armed, deployed, converged, pinned, rolled out or dropped — no fleet host, image, unit, alert rule or dashboard is touched, and no step of this plan waits on a maintenance window or a converge gap.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 2 step 6's reads, Tasks 3–4 and Task 6, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the data test, the reading, the replay), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1 and 5 and Task 2's steps 1–5.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00145 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00145/pt` (or a file, or `-k`): every `--basetemp` under `.tmp/plan-00145/` follows `mkdir -p .tmp/plan-00145 &&` in the same command, since pytest creates the base temp's leaf and never its parents. An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file, node id or `-k` selection into parts that cannot, each its own `--basetemp=.tmp/plan-00145/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `T=$(bash infra/scripts/consumers.sh --direct <each changed path> | sort -u)` and `[ -n "$T" ] && mkdir -p .tmp/plan-00145 && uv run pytest $T -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00145/pt`, never a bare `uv run pytest` and never `consumers.sh` with `2>/dev/null`, whose stderr is where a refusal speaks; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. Every file a commit carries is staged by explicit path — the ledger's line by `--reading` among them, whose one commit is Task 4 step 5's — since the commit and the probe setup's `git write-tree` read the index while `T` reads the working tree. Every `T` holding `tests/test_research_command.py` runs it in four parts, each one plain blocking call under `-m "not slow and not data"`, `timeout` 600000 ms, so that none can pass 600 s: `tests/test_research_command.py -k "not reentry and not b2"` (`--basetemp=.tmp/plan-00145/pt-1`, measured on the authoring tree, Tasks 1–2's code in it, `430 passed, 403 deselected in 195.08s`), `tests/test_research_command.py -k "b2 and not reentry"` (`pt-2`, measured `227 passed, 606 deselected in 312.88s`), `tests/test_research_command.py -k reentry` (`pt-3`, measured `71 passed, 762 deselected in 88.20s`) and the rest of `T` (`pt-4`). Every commit message carries the result line of each test command its gate ran, a run over that commit's own tree, and the two trailer lines exactly as the executing session's attribution gives them — `Co-Authored-By:` naming the model that ran the step, and `Claude-Session:`.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
mkdir -p .tmp/plan-00145 &&
  test ! -e .tmp/plan-00145/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00145/probe HEAD &&
  git -C .tmp/plan-00145/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00145/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00145/probe/.tmp
```

  Then, from `.tmp/plan-00145/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, so it fails at import or at its call. A mutation whose text also stands in an existing function — trial 58's books and metrics share several lines with the new ones — carries the address of its own function's range, `/^def <name>(/,/^def /`, or of its entry's or key set's, `/"b4-leg-reading": Subject(/,/^    ),/` or `/^_B4_LEG_KEYS = frozenset($/,/^)$/`, so its dry run changes one line; a pattern that holds `'` writes it as `.`. After the last verdict, `git worktree remove --force .tmp/plan-00145/probe` — a data link in it unlinked first with `test -L <its absolute path> && unlink <its absolute path>`, each removal of one that held a link followed by `ls -la /home/zhaow/Projects/zcrypto-kraken/data`, `ohlc-full` still listed. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <the hash the setup printed>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.
- **The subject's name** (D2): `b4-leg-reading`, which no registered or retired subject's name equals or opens with a hyphen, and which opens none (the spec's basis). Every new test function's name carries `b4_leg`, which no hyphenated id and no other test's name carries, so `-k b4_leg` selects them alone; the shared rows the subject adds carry the hyphenated `b4-leg-reading` in their ids.

## Task 1: the reading subject in `cli/research/subjects.py` (D2–D6)

**Files:** Modify `cli/research/subjects.py`, `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`.

**Interfaces:** Consumes `cli/research/subjects.py`'s `_b4_reads`, `_B4Reads`, `_b4_inputs`, `_B4Inputs`, `_b4_ensemble`, `_b4_limited`, `_b4_shortfall`, `_b4_net`, `_B4_LEGS`, `_B4_CARRY_RATE`, `_ffill_btc`, `_inverse_vol_weights`, `_B2_LOOKBACK`, `_B2_COST_PER_SIDE`, `PPY_4H`, `_N_RESAMPLES`, `borrow_unavailable`, `per_year_counts`, `per_year_means`, `per_year_sums`, `per_year_positions_differ`, `shortfall_carry`, `book_turnover`, `net_of_cost`, `net_of_cost_verdict`, `sharpe`, `max_drawdown`, `_b2_over`, `_ASSETS`, `Subject`, `SubjectError`, `ObservedReader` and the error classes it imports, each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; in the tests, `_b4_built_inputs`, `_b4_dataset`, `_B4_LEGS`, `_B2_ASSETS`, `_B2_START`, `_recording`, `_fake_head_to_head`, `_fake_kill_bar`, `_fake_benchmark`, `_anchor`, `_rolling_set`, `_CONTRACT_DATASETS`, `runner` and `app`. Produces the subject, `_B4LegInputs`, `_b4_leg_inputs` and `_b4_leg_engagement`, which Task 2's test reads.

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - `test_each_subject_declares_the_metric_keys_its_build_returns` gains, after its `assert subjects.SUBJECTS["b4-ratio-legs-preflight"].metric_keys == _B4_PREFLIGHT_KEYS` line, `    assert subjects.SUBJECTS["b4-leg-reading"].metric_keys == _B4_LEG_SPEC_KEYS`;
  - after `test_a_b4_subject_refuses_a_ratio_legs_file_it_cannot_read_naming_it` and before `def _ruled_signal(`, two blank lines either side:

```python
_B4_LEG_SPEC = "docs/specs/00145-b4-leg-reading-design.md"
# Spec 00145 D6's keys, typed from the spec, never read off the subject.
_B4_LEG_SPEC_KEYS = frozenset(
    {
        "head_to_head_mean_outperf_primary",
        "head_to_head_spa_p_primary",
        "head_to_head_mean_outperf_full",
        "head_to_head_spa_p_full",
        "mean_outperf_per_year",
        "ann_sharpe_noc_primary",
        "ann_sharpe_noc_full",
        "max_drawdown_primary",
        "max_drawdown_full",
        "arm_a_ann_sharpe_noc_primary",
        "arm_a_ann_sharpe_noc_full",
        "arm_a_max_drawdown_primary",
        "arm_a_max_drawdown_full",
        "context_head_to_head_mean_outperf",
        "context_head_to_head_spa_p",
        "context_carry_by_leg",
        "context_turnover_by_leg",
        "first_weight",
        "primary_returns",
        "held_per_year",
        "positions_differ_per_year",
        "turnover",
        "shortfall_stamps_per_year",
        "shortfall_mean_per_year",
        "carry_per_year",
        "limit_engaged",
        "turnover_a",
        "turnover_b",
        "mean_block",
        "seed",
        "n_resamples",
    }
)
_B4_FUNDINGS = ("carried", "no_borrow")


@pytest.mark.parametrize("name", ["b4-leg-reading"])
def test_the_b4_leg_reading_declares_the_4h_grid_its_keys_and_no_rule(name):
    reading = subjects.SUBJECTS[name]
    assert len(_B4_LEG_SPEC_KEYS) == 31
    assert (reading.name, reading.intervals, reading.assets, reading.spec, reading.seeds) == (
        name,
        (240,),
        _B2_ASSETS,
        _B4_LEG_SPEC,
        (42,),
    )
    assert reading.build is subjects._build_b4_leg_reading and reading.metric_keys == _B4_LEG_SPEC_KEYS
    assert (reading.verdict, reading.no_verdict, reading.incumbent, reading.family, reading.n_trials) == (None,) * 5


def _b4_leg_short_reads(n: int = 480) -> tuple[list[datetime], dict, dict]:
    """`_b4_short_reads`' union with BTC's drift taken out, so that each leg alone outweighs the book's BTC at some stamps:
    BTC missing one stamp, ETH/BTC their cross from the first stamp with one missing, SOL/BTC from stamp 150."""
    h4_ts = [datetime(2017, 1, 1, tzinfo=UTC) + timedelta(hours=4 * k) for k in range(n)]
    shapes = {"BTC": (100.0, 1.0, 0.05, 7.0, 0.0), "ETH": (50.0, 1.002, 0.06, 5.0, 1.0), "SOL": (20.0, 1.0005, 0.08, 9.0, 2.0)}
    h4_prices = {
        a: [level * growth**k * (1 + depth * math.sin(k / period + phase)) for k in range(n)]
        for a, (level, growth, depth, period, phase) in shapes.items()
    }
    ratios = {leg: [p / q for p, q in zip(h4_prices[base], h4_prices["BTC"])] for leg, base in _B4_LEGS.items()}
    ratios["ETH/BTC"][400] = None
    ratios["SOL/BTC"][:150] = [None] * 150
    h4_prices["BTC"][300] = None
    return h4_ts, h4_prices, ratios


def _b4_own_leg_books(h4_ts: list[datetime], h4_prices: dict, ratios: dict) -> dict:
    """Each leg alone beside the reads' EUR assets, built here, never through the reading's halves: its first weight, and
    its book as trial 58 costed arm B and as the borrow-free twin, each limited, with the limits' engaged bars."""
    n = len(h4_ts) - 1
    fed = _ffill_btc(h4_prices)
    configs = [
        A2Config(lookbacks=lb, short="off", target_vol=tv, vol_lookback=180, basket_lookback=180, periods_per_year=2190)
        for lb, tv in (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))
    ]
    legs = {leg: (base, "BTC") for leg, base in _B4_LEGS.items()}

    def limited(positions):
        factors, engaged = limit_factors(base_exposures(positions, legs))
        return {i: [p * f for p, f in zip(v, factors)] for i, v in positions.items()}, engaged

    own = {}
    for leg in _B4_LEGS:
        priced = fed | {leg: ratios[leg]}
        books = [a2_book_returns(priced, config=c)["asset_positions"] for c in configs]
        raw = {i: [statistics.mean(book[i][k] for book in books) for k in range(n)] for i in priced}
        covered = [1.0 if raw[leg][k] == 0 else min(1.0, max(0.0, raw["BTC"][k]) / raw[leg][k]) for k in range(n)]
        weights = _inverse_vol_weights(priced, lookback=180)
        own[leg] = {
            "first": next((k for k, w in enumerate(weights) if leg in w), n),
            "carried": limited(raw),
            "no_borrow": limited(raw | {leg: [p * c for p, c in zip(raw[leg], covered)]}),
        }
    return own


@pytest.mark.parametrize("name", ["b4-leg-reading"])
def test_the_b4_leg_inputs_hold_trial_58s_books_and_each_legs_two_beside_them(monkeypatch, name):
    reads = _b4_leg_short_reads()
    own = _b4_own_leg_books(*reads)
    # The short union moves each leg's two books: the leg held, its carried book short of BTC at some stamps, so the
    # borrow-free book differs from it.
    assert all(any(p != 0 for p in own[leg]["carried"][0][leg]) for leg in _B4_LEGS)
    assert all(own[leg]["no_borrow"][0] != own[leg]["carried"][0] for leg in _B4_LEGS)
    trial = subjects._b4_inputs(subjects._B4Reads(*reads))
    limited = _recording(monkeypatch, "_b4_limited", lambda arguments, result: result)

    inputs = subjects._b4_leg_inputs(subjects._B4Reads(*reads))

    assert inputs.trial == trial
    assert inputs.first_weight == {leg: own[leg]["first"] for leg in _B4_LEGS}
    assert inputs.books == {leg: {funding: own[leg][funding][0] for funding in _B4_FUNDINGS} for leg in _B4_LEGS}
    assert inputs.engaged == {leg: {funding: own[leg][funding][1] for funding in _B4_FUNDINGS} for leg in _B4_LEGS}
    # After trial 58's three books, each book and its engaged bars are its own pass through the limits, in the legs' order.
    cells = [(leg, funding) for leg in _B4_LEGS for funding in _B4_FUNDINGS]
    assert len(limited) == 3 + len(cells)
    for (leg, funding), (_, (book, engaged)) in zip(cells, limited[3:]):
        assert inputs.books[leg][funding] is book and inputs.engaged[leg][funding] is engaged


@pytest.mark.parametrize("name", ["b4-leg-reading"])
def test_the_b4_leg_books_are_arm_as_before_their_legs_first_weight_and_eth_btcs_are_trial_58s_before_sol_btcs(name):
    inputs = subjects._b4_leg_inputs(subjects._B4Reads(*_b4_leg_short_reads()))
    trial, n = inputs.trial, len(inputs.trial.close)
    sol = inputs.first_weight["SOL/BTC"]

    def first_differ(book: dict, other: dict) -> int:
        return next((k for k in range(n) if any(book[i][k] != other.get(i, [0.0] * n)[k] for i in book)), n)

    assert 0 < inputs.first_weight["ETH/BTC"] < sol < n
    for leg, first in inputs.first_weight.items():
        for book in inputs.books[leg].values():
            assert first <= first_differ(book, trial.arm_a) < n
    for funding, trial_book in (("carried", trial.arm_b), ("no_borrow", trial.no_borrow)):
        assert sol <= first_differ(inputs.books["ETH/BTC"][funding], trial_book) < n
        assert not any(trial_book["SOL/BTC"][:sol])


def _b4_leg_built_inputs(n: int = 1_400) -> subjects._B4LegInputs:
    """`_b4_built_inputs`' trial and, per leg, two books made by hand — arm A with the leg at trial 58's arm B's
    position, short of BTC wherever the leg outweighs it, and the same with the leg halved — each limit engaged at a count
    of stamps of its own in each book, for the metrics alone."""
    trial = _b4_built_inputs(n)
    books, engaged = {}, {}
    for j, leg in enumerate(_B4_LEGS):
        carried = trial.arm_a | {leg: trial.arm_b[leg]}
        books[leg] = {"carried": carried, "no_borrow": carried | {leg: [0.5 * p for p in carried[leg]]}}
        engaged[leg] = {
            funding: {limit: [k < 1 + 3 * (2 * j + f) + m for k in range(n)] for m, limit in enumerate(("gross", "net", "margin"))}
            for f, funding in enumerate(_B4_FUNDINGS)
        }
    # Each leg's first weight past trial 58's, so a read from the one where the other belongs moves its slice.
    return subjects._B4LegInputs(trial, {"ETH/BTC": 210, "SOL/BTC": 650}, books, engaged)


def _b4_own_leg_net(trial: subjects._B4Inputs, book: dict) -> list[float]:
    """Net of each instrument's turnover at 0.006 a side and of the carry on the BTC the book's legs outweigh."""
    net = net_of_cost(book, {i: trial.returns[i] for i in book}, cost_per_side=0.006)
    btc = list(book["BTC"])
    for leg in (leg for leg in _B4_LEGS if leg in book):
        btc = [x - p for x, p in zip(btc, book[leg])]
    short = [max(0.0, -x) for x in btc]
    carry = [0.0002 * (s + max(0.0, s - p)) for s, p in zip(short, [0.0, *short[:-1]])]
    return [x - c for x, c in zip(net, carry)]


def _b4_own_leg_engagement(inputs: subjects._B4LegInputs) -> dict:
    trial, close, n = inputs.trial, inputs.trial.close, len(inputs.trial.close)
    keys = ("held_per_year", "positions_differ_per_year", "turnover", "shortfall_stamps_per_year", "shortfall_mean_per_year")
    out = {key: {leg: {} for leg in _B4_LEGS} for key in (*keys, "carry_per_year", "limit_engaged")}
    for leg in _B4_LEGS:
        for funding, book in inputs.books[leg].items():
            short = [max(0.0, -(b - p)) for b, p in zip(book["BTC"], book[leg])]
            carry = [0.0002 * (s + max(0.0, s - p)) for s, p in zip(short, [0.0, *short[:-1]])]
            out["held_per_year"][leg][funding] = per_year_counts([p != 0 for p in book[leg]], close)
            out["positions_differ_per_year"][leg][funding] = per_year_positions_differ(trial.arm_a | {leg: [0.0] * n}, book, close)
            out["turnover"][leg][funding] = book_turnover(book)
            out["shortfall_stamps_per_year"][leg][funding] = per_year_counts([s > 0 for s in short], close)
            out["shortfall_mean_per_year"][leg][funding] = per_year_means(short, close)
            out["carry_per_year"][leg][funding] = per_year_sums(carry, close)
            out["limit_engaged"][leg][funding] = {limit: sum(flags) for limit, flags in inputs.engaged[leg][funding].items()}
    arm_b = trial.arm_b
    short_b = [max(0.0, -(arm_b["BTC"][k] - arm_b["ETH/BTC"][k] - arm_b["SOL/BTC"][k])) for k in range(n)]
    carry_b = [0.0002 * (s + max(0.0, s - p)) for s, p in zip(short_b, [0.0, *short_b[:-1]])]
    legs_held = [arm_b["ETH/BTC"][k] + arm_b["SOL/BTC"][k] for k in range(n)]
    return {
        "first_weight": inputs.first_weight,
        "primary_returns": {leg: n - first for leg, first in inputs.first_weight.items()},
        **out,
        "turnover_a": book_turnover(trial.arm_a),
        "turnover_b": book_turnover(arm_b),
        "context_carry_by_leg": {
            leg: math.fsum(c * arm_b[leg][k] / legs_held[k] if legs_held[k] else 0.0 for k, c in enumerate(carry_b))
            for leg in _B4_LEGS
        },
        "context_turnover_by_leg": {leg: book_turnover({leg: arm_b[leg]}) for leg in _B4_LEGS}
        | {"EUR": book_turnover({a: arm_b[a] for a in trial.arm_a})},
    }


@pytest.mark.parametrize("name", ["b4-leg-reading"])
def test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg(name):
    inputs = _b4_leg_built_inputs()
    own = _b4_own_leg_engagement(inputs)
    # Every book the reading counts moves its own figures: each carried book short of BTC, its twin less so, and trial
    # 58's carry shared by both legs.
    assert all(sum(own["carry_per_year"][leg]["carried"].values()) > 0 for leg in _B4_LEGS)
    assert all(own["turnover"][leg]["carried"] != own["turnover"][leg]["no_borrow"] for leg in _B4_LEGS)
    assert all(v > 0 for v in own["context_carry_by_leg"].values())

    assert subjects._b4_leg_engagement(inputs) == own


@pytest.mark.parametrize("name", ["b4-leg-reading"])
def test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call(monkeypatch, name):
    inputs = _b4_leg_built_inputs()
    trial, close = inputs.trial, inputs.trial.close
    start = min(trial.first_weight.values())
    net_a = _b4_own_leg_net(trial, trial.arm_a)
    nets = {leg: {funding: _b4_own_leg_net(trial, book) for funding, book in inputs.books[leg].items()} for leg in _B4_LEGS}
    returns_b, returns_a = ({i: trial.returns[i] for i in book} for book in (trial.arm_b, trial.arm_a))
    layers = {
        "gross": (net_of_cost(trial.arm_b, returns_b, cost_per_side=0.0), net_of_cost(trial.arm_a, returns_a, cost_per_side=0.0)),
        "net_of_trading": (
            net_of_cost(trial.arm_b, returns_b, cost_per_side=0.006),
            net_of_cost(trial.arm_a, returns_a, cost_per_side=0.006),
        ),
        "net": (_b4_own_leg_net(trial, trial.arm_b), net_a),
    }
    # The three layers part, and each leg's carry moves its carried book's net.
    assert layers["gross"][0] != layers["net_of_trading"][0] != layers["net"][0]
    for leg in _B4_LEGS:
        carried = inputs.books[leg]["carried"]
        assert nets[leg]["carried"] != net_of_cost(carried, {i: trial.returns[i] for i in carried}, cost_per_side=0.006)
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    metrics = subjects._b4_leg_metrics(inputs)

    reads = {"mean_block": 30, "seed": 42, "n_resamples": 2000}
    calls = []
    for leg in _B4_LEGS:
        first = inputs.first_weight[leg]
        for funding in _B4_FUNDINGS:
            net = nets[leg][funding]
            calls += [
                reads | {"book_net_of_cost": net[first:], "benchmark_net_of_cost": net_a[first:]},
                reads | {"book_net_of_cost": net, "benchmark_net_of_cost": net_a},
            ]
    calls += [reads | {"book_net_of_cost": b[start:], "benchmark_net_of_cost": a[start:]} for b, a in layers.values()]
    assert [arguments for arguments, _ in heads] == calls
    results = iter(result for _, result in heads)
    cells = {}
    for leg in _B4_LEGS:
        first = inputs.first_weight[leg]
        for funding in _B4_FUNDINGS:
            net, primary, full = nets[leg][funding], next(results), next(results)
            cell = {
                "head_to_head_mean_outperf_primary": primary["mean_outperformance"],
                "head_to_head_spa_p_primary": primary["spa_p_value"],
                "head_to_head_mean_outperf_full": full["mean_outperformance"],
                "head_to_head_spa_p_full": full["spa_p_value"],
                "mean_outperf_per_year": per_year_means([x - a for x, a in zip(net, net_a)], close),
                "ann_sharpe_noc_primary": sharpe(net[first:], periods_per_year=2190),
                "ann_sharpe_noc_full": sharpe(net, periods_per_year=2190),
                "max_drawdown_primary": max_drawdown(net[first:]),
                "max_drawdown_full": max_drawdown(net),
            }
            for key, value in cell.items():
                cells.setdefault(key, {}).setdefault(leg, {})[funding] = value
    context = {layer: next(results) for layer in layers}
    assert metrics == {
        **cells,
        "arm_a_ann_sharpe_noc_primary": {
            leg: sharpe(net_a[first:], periods_per_year=2190) for leg, first in inputs.first_weight.items()
        },
        "arm_a_ann_sharpe_noc_full": sharpe(net_a, periods_per_year=2190),
        "arm_a_max_drawdown_primary": {leg: max_drawdown(net_a[first:]) for leg, first in inputs.first_weight.items()},
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        "context_head_to_head_mean_outperf": {layer: result["mean_outperformance"] for layer, result in context.items()},
        "context_head_to_head_spa_p": {layer: result["spa_p_value"] for layer, result in context.items()},
        **_b4_own_leg_engagement(inputs),
        "mean_block": 30,
        "seed": 42,
        "n_resamples": 2000,
    }


@pytest.mark.parametrize("name", ["b4-leg-reading"])
def test_the_b4_leg_readings_cost_layers_take_trial_58s_head_to_head_apart_into_its_gross_trades_and_carry(monkeypatch, name):
    inputs = _b4_leg_built_inputs()
    trial, n = inputs.trial, len(inputs.trial.close)
    start = min(trial.first_weight.values())
    monkeypatch.setattr(subjects, "a1_kill_bar", _fake_kill_bar)
    monkeypatch.setattr(subjects, "benchmark_4h_net_of_cost", _fake_benchmark)
    trial_58 = subjects._b4_metrics(trial, n_trials=1)

    metrics = subjects._b4_leg_metrics(inputs)

    def traded(book: dict) -> list[float]:
        return [0.006 * sum(abs(v[k] - (v[k - 1] if k else 0.0)) for v in book.values()) for k in range(n)]

    arm_b = trial.arm_b
    short = [max(0.0, -(arm_b["BTC"][k] - arm_b["ETH/BTC"][k] - arm_b["SOL/BTC"][k])) for k in range(n)]
    carry = [0.0002 * (s + max(0.0, s - p)) for s, p in zip(short, [0.0, *short[:-1]])]
    trades = [b - a for b, a in zip(traded(arm_b), traded(trial.arm_a))]
    mean, spa = metrics["context_head_to_head_mean_outperf"], metrics["context_head_to_head_spa_p"]
    assert (mean["net"], spa["net"]) == (trial_58["head_to_head_mean_outperf_primary"], trial_58["head_to_head_spa_p_primary"])
    assert statistics.fmean(trades[start:]) != 0 and statistics.fmean(carry[start:]) > 0
    assert math.isclose(mean["gross"] - mean["net_of_trading"], statistics.fmean(trades[start:]), rel_tol=1e-9)
    assert math.isclose(mean["net_of_trading"] - mean["net"], statistics.fmean(carry[start:]), rel_tol=1e-9)


@pytest.mark.parametrize("name", ["b4-leg-reading"])
def test_the_b4_leg_reading_refuses_fewer_than_2_returns_from_a_legs_first_weight_before_any_head_to_head(monkeypatch, name):
    built = _b4_leg_built_inputs()
    n = len(built.trial.close)
    inputs = built._replace(first_weight={"ETH/BTC": 200, "SOL/BTC": n - 1})
    heads = _recording(monkeypatch, "net_of_cost_verdict", lambda arguments, result: result)

    with pytest.raises(ValidationError) as refused:
        subjects._b4_leg_metrics(inputs)

    assert str(refused.value) == "1 of its return indices follow SOL/BTC's first weight, and the head-to-head from it needs 2"
    assert heads == []
    monkeypatch.setattr(subjects, "net_of_cost_verdict", _fake_head_to_head)
    admitted = subjects._b4_leg_metrics(built._replace(first_weight={"ETH/BTC": 200, "SOL/BTC": n - 2}))
    assert admitted["primary_returns"]["SOL/BTC"] == 2


@pytest.mark.parametrize("name", ["b4-leg-reading"])
def test_the_b4_leg_reading_refuses_as_of_before_any_read(tmp_path, monkeypatch, name):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the reading read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)
    args = ["research", "eval", "--subject", name, "--dataset", "ohlc-rolling", "--as-of", "2026-10-03"]

    result = runner.invoke(app, args)

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        f"{name} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen "
        "--dataset"
    ) in result.output
```

  - `_CONTRACT_DATASETS` gains, after its `"b4-ratio-legs-preflight"` entry, `    "b4-leg-reading": lambda tmp_path, subject: (_b4_dataset(tmp_path), _B2_START),` — the fixture trial 58's two subjects read.

  **Author's call** — each half on the fixture that moves it, every case but the shared rows in seconds, so each is a probe's target: the inputs on `_b4_leg_short_reads`, `_b4_short_reads`' 480-stamp union with BTC's drift taken out, so that each leg alone outweighs the book's BTC wherever it is held (measured on the authoring tree: ETH/BTC held and short at 218 stamps, SOL/BTC at 126) and each borrow-free book differs from its carried one — `_b4_short_reads`' own BTC covers either leg alone at every stamp, so on it the two fundings are one book — every field of `_b4_leg_inputs` held to `_b4_own_leg_books`, the test's own build through `a2_book_returns` and `cli/alpha/b4.py`'s functions, never the subject's halves, trial 58's books to `_b4_inputs`' own, and each book and its engaged bars held by identity to its own pass through `_b4_limited`, after trial 58's three; the spans on the same union, each book arm A's until its leg's first weight and ETH/BTC's trial 58's until SOL/BTC's, each differing after; the engagement, the reads and the cost layers on `_b4_leg_built_inputs` — `_b4_built_inputs`' trial and two books per leg made by hand, each carried book short of BTC, each borrow-free one its leg halved, each limit engaged at a count of stamps of its own in each book, and each leg's first weight set past trial 58's so that a read from the one where the other belongs moves its slice — every key held to `_b4_own_leg_engagement` and `_b4_own_leg_net`, the test's own expressions, and every head-to-head's arguments read off `_fake_head_to_head`; the decomposition on the same inputs under the real `net_of_cost_verdict`, the net layer's pair held to `_b4_metrics`' own primary head-to-head to the bit — the bars and the benchmark stood in for by `_fake_kill_bar` and `_fake_benchmark` — and each layer's step to the per-bar trading cost and carry written out; the refusal, its bound held from each side, and `--as-of` each on their own; a leg's file the build cannot read has no case of this subject — it is `_b4_reads`' refusal, unchanged (D6), which the existing leg-file case holds for trial 58's two subjects: an explicit drop. Every new function is parametrised by the subject's name, so `tests/retired_subjects.py`'s hook marks each case `retired` once Task 5 retires it. The shared rows — the contract, tracked-spec and shared-defaults rows, which `_CONTRACT_DATASETS` reaches — run the subject end to end on `_b4_dataset`, its eleven head-to-heads among them.
- [ ] **Step 2: Run them to verify they fail** — `mkdir -p .tmp/plan-00145 && uv run pytest tests/test_research_command.py -k "b4_leg or declares_the_metric_keys" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00145/pt`: collection completes and every selected case fails at its call, on a key `SUBJECTS` lacks, a name `subjects` lacks or a subject the CLI does not know (measured on the base module: `9 failed, 815 deselected`).
- [ ] **Step 3: Implement in `cli/research/subjects.py`** — after `_B4_PREFLIGHT_KEYS`' closing `)` and before `SUBJECTS: dict[str, Subject] = {`, two blank lines on each side:

```python
# docs/specs/00145 D2-D6: B4's leg reading, trial 58's books taken apart on a frozen set's full history — each ratio leg
# alone beside the ten EUR assets, as trial 58 costed arm B and as its borrow-free twin, and arm B's head-to-head by cost;
# no rule, no slot.
class _B4LegInputs(NamedTuple):
    trial: _B4Inputs
    first_weight: dict[str, int]
    books: dict[str, dict[str, dict[str, list[float]]]]
    engaged: dict[str, dict[str, dict[str, list[bool]]]]


def _b4_leg_inputs(reads: _B4Reads) -> _B4LegInputs:
    """Trial 58's books and each leg's two, keyed `carried` and `no_borrow`: positions, and no return of a book."""
    trial = _b4_inputs(reads)
    fed = _ffill_btc(reads.h4_prices)
    first_weight: dict[str, int] = {}
    books: dict[str, dict[str, dict[str, list[float]]]] = {}
    engaged: dict[str, dict[str, dict[str, list[bool]]]] = {}
    for leg in _B4_LEGS:
        priced = fed | {leg: reads.ratios[leg]}
        raw = _b4_ensemble(priced)
        weights = _inverse_vol_weights(priced, lookback=_B2_LOOKBACK)
        first_weight[leg] = next((k for k, w in enumerate(weights) if leg in w), len(weights))
        carried, engaged_carried = _b4_limited(raw)
        no_borrow, engaged_no_borrow = _b4_limited(borrow_unavailable(raw, _B4_LEGS, "BTC"))
        books[leg] = {"carried": carried, "no_borrow": no_borrow}
        engaged[leg] = {"carried": engaged_carried, "no_borrow": engaged_no_borrow}
    return _B4LegInputs(trial, first_weight, books, engaged)


def _b4_leg_engagement(inputs: _B4LegInputs) -> dict:
    trial, close = inputs.trial, inputs.trial.close
    n = len(close)
    cells: dict[str, dict] = {}
    for leg, by_funding in inputs.books.items():
        flat = trial.arm_a | {leg: [0.0] * n}
        for funding, book in by_funding.items():
            shortfall = _b4_shortfall(book)
            cell = {
                "held_per_year": per_year_counts([p != 0 for p in book[leg]], close),
                "positions_differ_per_year": per_year_positions_differ(flat, book, close),
                "turnover": book_turnover(book),
                "shortfall_stamps_per_year": per_year_counts([s > 0 for s in shortfall], close),
                "shortfall_mean_per_year": per_year_means(shortfall, close),
                "carry_per_year": per_year_sums(shortfall_carry(shortfall, rate=_B4_CARRY_RATE), close),
                "limit_engaged": {name: sum(flags) for name, flags in inputs.engaged[leg][funding].items()},
            }
            for key, value in cell.items():
                cells.setdefault(key, {}).setdefault(leg, {})[funding] = value
    carry = shortfall_carry(_b4_shortfall(trial.arm_b), rate=_B4_CARRY_RATE)
    legs_held = [sum(trial.arm_b[leg][k] for leg in _B4_LEGS) for k in range(n)]
    return {
        "first_weight": inputs.first_weight,
        "primary_returns": {leg: n - first for leg, first in inputs.first_weight.items()},
        **cells,
        "turnover_a": book_turnover(trial.arm_a),
        "turnover_b": book_turnover(trial.arm_b),
        # docs/specs/00145 D5: trial 58's one BTC shortfall apportioned to its legs pro rata to their positions at each bar.
        "context_carry_by_leg": {
            leg: math.fsum(c * p / held if held else 0.0 for c, p, held in zip(carry, trial.arm_b[leg], legs_held))
            for leg in _B4_LEGS
        },
        "context_turnover_by_leg": {leg: book_turnover({leg: trial.arm_b[leg]}) for leg in _B4_LEGS}
        | {"EUR": book_turnover({a: trial.arm_b[a] for a in trial.arm_a})},
    }


def _b4_cost_layers(trial: _B4Inputs) -> dict[str, tuple[list[float], list[float]]]:
    """Arm B's book and arm A's, gross, net of their trading cost alone, and net of it and the carry, as trial 58 costed
    them (docs/specs/00145 D5)."""

    def trading(book: dict[str, list[float]], cost_per_side: float) -> list[float]:
        return net_of_cost(book, {i: trial.returns[i] for i in book}, cost_per_side=cost_per_side)

    return {
        "gross": (trading(trial.arm_b, 0.0), trading(trial.arm_a, 0.0)),
        "net_of_trading": (trading(trial.arm_b, _B2_COST_PER_SIDE), trading(trial.arm_a, _B2_COST_PER_SIDE)),
        "net": (_b4_net(trial.arm_b, trial.returns, stress=1.0), _b4_net(trial.arm_a, trial.returns, stress=1.0)),
    }


def _b4_leg_metrics(inputs: _B4LegInputs) -> dict:
    trial, close = inputs.trial, inputs.trial.close
    n = len(close)
    for leg, first in inputs.first_weight.items():
        if n - first < 2:
            raise ValidationError(
                f"{n - first} of its return indices follow {leg}'s first weight, and the head-to-head from it needs 2"
            )
    net_a = _b4_net(trial.arm_a, trial.returns, stress=1.0)
    cells: dict[str, dict] = {}
    for leg, by_funding in inputs.books.items():
        first = inputs.first_weight[leg]
        for funding, book in by_funding.items():
            net = _b4_net(book, trial.returns, stress=1.0)
            primary = net_of_cost_verdict(net[first:], net_a[first:], mean_block=30, seed=42, n_resamples=_N_RESAMPLES)
            full = net_of_cost_verdict(net, net_a, mean_block=30, seed=42, n_resamples=_N_RESAMPLES)
            cell = {
                "head_to_head_mean_outperf_primary": primary["mean_outperformance"],
                "head_to_head_spa_p_primary": primary["spa_p_value"],
                "head_to_head_mean_outperf_full": full["mean_outperformance"],
                "head_to_head_spa_p_full": full["spa_p_value"],
                "mean_outperf_per_year": per_year_means([x - a for x, a in zip(net, net_a, strict=True)], close),
                "ann_sharpe_noc_primary": sharpe(net[first:], periods_per_year=PPY_4H),
                "ann_sharpe_noc_full": sharpe(net, periods_per_year=PPY_4H),
                "max_drawdown_primary": max_drawdown(net[first:]),
                "max_drawdown_full": max_drawdown(net),
            }
            for key, value in cell.items():
                cells.setdefault(key, {}).setdefault(leg, {})[funding] = value
    start = min(trial.first_weight.values())
    context: dict[str, dict] = {"context_head_to_head_mean_outperf": {}, "context_head_to_head_spa_p": {}}
    for layer, (book, bench) in _b4_cost_layers(trial).items():
        verdict = net_of_cost_verdict(book[start:], bench[start:], mean_block=30, seed=42, n_resamples=_N_RESAMPLES)
        context["context_head_to_head_mean_outperf"][layer] = verdict["mean_outperformance"]
        context["context_head_to_head_spa_p"][layer] = verdict["spa_p_value"]
    return {
        **cells,
        "arm_a_ann_sharpe_noc_primary": {
            leg: sharpe(net_a[first:], periods_per_year=PPY_4H) for leg, first in inputs.first_weight.items()
        },
        "arm_a_ann_sharpe_noc_full": sharpe(net_a, periods_per_year=PPY_4H),
        "arm_a_max_drawdown_primary": {leg: max_drawdown(net_a[first:]) for leg, first in inputs.first_weight.items()},
        "arm_a_max_drawdown_full": max_drawdown(net_a),
        **context,
        **_b4_leg_engagement(inputs),
        "mean_block": 30,
        "seed": 42,
        "n_resamples": _N_RESAMPLES,
    }


def _build_b4_leg_reading(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    subject = "b4-leg-reading"
    if as_of is not None:
        raise SubjectError(
            f"{subject} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a "
            "frozen --dataset"
        )
    try:
        return _b4_leg_metrics(_b4_leg_inputs(_b4_reads(subject, reader, dataset, window, accept_holes)))
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, RiskError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


# docs/specs/00145 D6's keys of the reading.
_B4_LEG_KEYS = frozenset(
    {
        "head_to_head_mean_outperf_primary",
        "head_to_head_spa_p_primary",
        "head_to_head_mean_outperf_full",
        "head_to_head_spa_p_full",
        "mean_outperf_per_year",
        "ann_sharpe_noc_primary",
        "ann_sharpe_noc_full",
        "max_drawdown_primary",
        "max_drawdown_full",
        "arm_a_ann_sharpe_noc_primary",
        "arm_a_ann_sharpe_noc_full",
        "arm_a_max_drawdown_primary",
        "arm_a_max_drawdown_full",
        "context_head_to_head_mean_outperf",
        "context_head_to_head_spa_p",
        "context_carry_by_leg",
        "context_turnover_by_leg",
        "first_weight",
        "primary_returns",
        "held_per_year",
        "positions_differ_per_year",
        "turnover",
        "shortfall_stamps_per_year",
        "shortfall_mean_per_year",
        "carry_per_year",
        "limit_engaged",
        "turnover_a",
        "turnover_b",
        "mean_block",
        "seed",
        "n_resamples",
    }
)
```

  and `SUBJECTS` gains, after its `"b4-ratio-legs-preflight"` entry and before its closing `}`:

```python
    "b4-leg-reading": Subject(
        "b4-leg-reading",
        (240,),
        _ASSETS,
        _build_b4_leg_reading,
        spec="docs/specs/00145-b4-leg-reading-design.md",
        metric_keys=_B4_LEG_KEYS,
        seeds=(42,),
    ),
```

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row: `` ) or `b4-ratio-legs-preflight` ( `` becomes `` ), `b4-ratio-legs-preflight` ( ``, and the row's closing `` with no return of the twelve-instrument book; it has no rule, so its run is kept with `--reading`). | `` becomes:

```markdown
with no return of the twelve-instrument book; it has no rule, so its run is kept with `--reading`) or `b4-leg-reading` (a reading rather than a comparison: each of those two ratio pairs alone beside the ten EUR assets in the same three arms, once with the BTC it sells beyond the book's own borrowed as that comparison borrows it and once held to the book's own BTC, each against the A2 4h ensemble from the close its pair first takes basket weight; and that comparison's twelve-instrument book against the ensemble before any cost, net of its trades alone and net of its trades and its borrow; the 4h series of `--dataset`, a frozen set only, its two ratio pairs among them; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: `tests/slow-cases.txt`** — gains at their `sorted()` places the shared rows measured at 10 s or more on the authoring tree (call time: the shared-defaults row 63.08 s, the evaluate row 31.96 s):

```text
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b4-leg-reading-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b4-leg-reading]
```

  A case that times at 10 s or more on the implementer's own run and is not listed joins the list; a listed one under 10 s stays (`tests/test_slow_cases.py` passes).
- [ ] **Step 6: Run them to verify they pass** — step 2's command, measured `9 passed, 824 deselected` (about 11 s); then the shared rows, `mkdir -p .tmp/plan-00145 && uv run pytest tests/test_research_command.py -k "b4-leg-reading and not b4_leg" -m "not data" --durations=0 -q -p no:cacheprovider --basetemp=.tmp/plan-00145/pt`, one plain blocking call, `timeout` 600000 ms (measured `9 passed, 824 deselected in 96.48s`, the shared-defaults row 63.08 s and the evaluate row 31.96 s, every other under 1 s).
- [ ] **Step 7: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the Global Constraints' `T` over the four paths in its four parts (measured on the authoring tree: `430 passed, 403 deselected in 195.08s`, `227 passed, 606 deselected in 312.88s`, `71 passed, 762 deselected in 88.20s`; the other thirty-seven direct readers `4116 passed, 64 deselected in 122.20s`); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 8: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED` (measured on the authoring tree, 52 of 52); the metric-keys line and the contract, shared-defaults and tracked-spec rows are new rows of existing tests, not new guards, and are not probed:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_leg_reading(/def _build_b4_leg_reading_gone(/' --mutation '/"b4-leg-reading": Subject(/,/^    ),/s/        seeds=(42,),/        seeds=(42, 7),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_declares_the_4h_grid_its_keys_and_no_rule[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_leg_reading(/def _build_b4_leg_reading_gone(/' --mutation '/"b4-leg-reading": Subject(/,/^    ),/s/00145-b4-leg-reading-design/00144-b4-ratio-legs-design/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_declares_the_4h_grid_its_keys_and_no_rule[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_leg_reading(/def _build_b4_leg_reading_gone(/' --mutation '/"b4-leg-reading": Subject(/,/^    ),/s/        (240,),/        (1440,),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_declares_the_4h_grid_its_keys_and_no_rule[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_leg_reading(/def _build_b4_leg_reading_gone(/' --mutation '/^_B4_LEG_KEYS = frozenset($/,/^)$/s/        "context_carry_by_leg",/        "carry_by_leg",/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_declares_the_4h_grid_its_keys_and_no_rule[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_inputs(/def _b4_leg_inputs_gone(/' --mutation 's/^    fed = _ffill_btc(reads\.h4_prices)$/    fed = dict(reads.h4_prices)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_inputs_hold_trial_58s_books_and_each_legs_two_beside_them[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_inputs(/def _b4_leg_inputs_gone(/' --mutation 's/^        priced = fed | {leg: reads\.ratios\[leg\]}$/        priced = fed | reads.ratios/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_inputs_hold_trial_58s_books_and_each_legs_two_beside_them[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_inputs(/def _b4_leg_inputs_gone(/' --mutation '/^def _b4_leg_inputs(/,/^def /s/        weights = _inverse_vol_weights(priced, /        weights = _inverse_vol_weights(fed, /' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_inputs_hold_trial_58s_books_and_each_legs_two_beside_them[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_inputs(/def _b4_leg_inputs_gone(/' --mutation 's/        first_weight\[leg\] = next((k for k, w in enumerate(weights) if leg in w), len(weights))/        first_weight[leg] = next((k for k, w in enumerate(weights) if w), len(weights))/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_inputs_hold_trial_58s_books_and_each_legs_two_beside_them[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_inputs(/def _b4_leg_inputs_gone(/' --mutation 's/        no_borrow, engaged_no_borrow = _b4_limited(borrow_unavailable(raw, _B4_LEGS, "BTC"))/        no_borrow, engaged_no_borrow = _b4_limited(raw)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_inputs_hold_trial_58s_books_and_each_legs_two_beside_them[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_inputs(/def _b4_leg_inputs_gone(/' --mutation 's/        books\[leg\] = {"carried": carried, "no_borrow": no_borrow}/        books[leg] = {"carried": no_borrow, "no_borrow": carried}/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_inputs_hold_trial_58s_books_and_each_legs_two_beside_them[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_inputs(/def _b4_leg_inputs_gone(/' --mutation 's/        engaged\[leg\] = {"carried": engaged_carried, "no_borrow": engaged_no_borrow}/        engaged[leg] = {"carried": engaged_no_borrow, "no_borrow": engaged_no_borrow}/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_inputs_hold_trial_58s_books_and_each_legs_two_beside_them[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_inputs(/def _b4_leg_inputs_gone(/' --mutation 's/^        priced = fed | {leg: reads\.ratios\[leg\]}$/        priced = fed | reads.ratios/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_books_are_arm_as_before_their_legs_first_weight_and_eth_btcs_are_trial_58s_before_sol_btcs[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_inputs(/def _b4_leg_inputs_gone(/' --mutation 's/^        raw = _b4_ensemble(priced)$/        raw = _b4_ensemble(fed | reads.ratios)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_books_are_arm_as_before_their_legs_first_weight_and_eth_btcs_are_trial_58s_before_sol_btcs[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation 's/"held_per_year": per_year_counts(\[p != 0 for p in book\[leg\]\], close),/"held_per_year": per_year_counts([p != 0 for p in book["BTC"]], close),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation 's/"positions_differ_per_year": per_year_positions_differ(flat, book, close),/"positions_differ_per_year": per_year_positions_differ(flat, flat, close),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation 's/^                "turnover": book_turnover(book),$/                "turnover": book_turnover(trial.arm_a),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation 's/^            shortfall = _b4_shortfall(book)$/            shortfall = _b4_shortfall(trial.arm_b)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation '/^def _b4_leg_engagement(/,/^def /s/"shortfall_stamps_per_year": per_year_counts(\[s > 0 for s in shortfall\], close),/"shortfall_stamps_per_year": per_year_counts([s >= 0 for s in shortfall], close),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation '/^def _b4_leg_engagement(/,/^def /s/"shortfall_mean_per_year": per_year_means(shortfall, close),/"shortfall_mean_per_year": per_year_sums(shortfall, close),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation '/^def _b4_leg_engagement(/,/^def /s/"carry_per_year": per_year_sums(shortfall_carry(shortfall, rate=_B4_CARRY_RATE), close),/"carry_per_year": per_year_sums(shortfall_carry(shortfall, rate=2 * _B4_CARRY_RATE), close),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation 's/"limit_engaged": {name: sum(flags) for name, flags in inputs\.engaged\[leg\]\[funding\]\.items()},/"limit_engaged": {name: sum(flags) for name, flags in inputs.engaged[leg]["carried"].items()},/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation 's/^        "first_weight": inputs\.first_weight,$/        "first_weight": inputs.trial.first_weight,/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation 's/"primary_returns": {leg: n - first for leg, first in inputs\.first_weight\.items()},/"primary_returns": {leg: n - first - 1 for leg, first in inputs.first_weight.items()},/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation 's/^        "turnover_b": book_turnover(trial\.arm_b),$/        "turnover_b": book_turnover(trial.no_borrow),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation 's/^    carry = shortfall_carry(_b4_shortfall(trial\.arm_b), rate=_B4_CARRY_RATE)$/    carry = shortfall_carry(_b4_shortfall(trial.no_borrow), rate=_B4_CARRY_RATE)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation 's/leg: math\.fsum(c \* p \/ held if held else 0\.0 for c, p, held in/leg: math.fsum(c \/ 2 if held else 0.0 for c, p, held in/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation 's/"context_turnover_by_leg": {leg: book_turnover({leg: trial\.arm_b\[leg\]}) for leg in _B4_LEGS}/"context_turnover_by_leg": {leg: book_turnover({leg: trial.no_borrow[leg]}) for leg in _B4_LEGS}/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_engagement(/def _b4_leg_engagement_gone(/' --mutation 's/        | {"EUR": book_turnover({a: trial\.arm_b\[a\] for a in trial\.arm_a})},/        | {"EUR": book_turnover({a: trial.arm_a[a] for a in trial.arm_a})},/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_engagement_counts_each_books_holding_shortfall_carry_and_limits_and_trial_58s_by_leg[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation '/^def _b4_leg_metrics(/,/^def /s/^    net_a = _b4_net(trial\.arm_a, trial\.returns, stress=1\.0)$/    net_a = _b4_net(trial.arm_a, trial.returns, stress=1.5)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/^            net = _b4_net(book, trial\.returns, stress=1\.0)$/            net = _b4_net(book, trial.returns, stress=0.0)/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation '/^def _b4_leg_metrics(/,/^def /s/^        first = inputs\.first_weight\[leg\]$/        first = min(trial.first_weight.values())/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/^            full = net_of_cost_verdict(net, net_a, /            full = net_of_cost_verdict(net[first:], net_a[first:], /' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/primary = net_of_cost_verdict(net\[first:\], net_a\[first:\], mean_block=30, /primary = net_of_cost_verdict(net[first:], net_a[first:], mean_block=102, /' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/"head_to_head_spa_p_primary": primary\["spa_p_value"\],/"head_to_head_spa_p_primary": full["spa_p_value"],/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation '/^def _b4_leg_metrics(/,/^def /s/"head_to_head_mean_outperf_full": full\["mean_outperformance"\],/"head_to_head_mean_outperf_full": primary["mean_outperformance"],/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/"mean_outperf_per_year": per_year_means(\[x - a for x, a in zip(net, net_a, strict=True)\], close),/"mean_outperf_per_year": per_year_sums([x - a for x, a in zip(net, net_a, strict=True)], close),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/"ann_sharpe_noc_primary": sharpe(net\[first:\], periods_per_year=PPY_4H),/"ann_sharpe_noc_primary": sharpe(net, periods_per_year=PPY_4H),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/"max_drawdown_primary": max_drawdown(net\[first:\]),/"max_drawdown_primary": max_drawdown(net_a[first:]),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/^            leg: sharpe(net_a\[first:\], periods_per_year=PPY_4H) for leg, first in inputs\.first_weight\.items()$/            leg: sharpe(net_a, periods_per_year=PPY_4H) for leg, first in inputs.first_weight.items()/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/"arm_a_max_drawdown_primary": {leg: max_drawdown(net_a\[first:\]) for/"arm_a_max_drawdown_primary": {leg: max_drawdown(net_a[first + 600 :]) for/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation '/^def _b4_leg_metrics(/,/^def /s/^    start = min(trial\.first_weight\.values())$/    start = min(inputs.first_weight.values())/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/^        context\["context_head_to_head_spa_p"\]\[layer\] = verdict\["spa_p_value"\]$/        context["context_head_to_head_spa_p"][layer] = verdict["mean_outperformance"]/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/^        "gross": (trading(trial\.arm_b, 0\.0), trading(trial\.arm_a, 0\.0)),$/        "gross": (trading(trial.arm_b, 0.0), trading(trial.arm_a, _B2_COST_PER_SIDE)),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/^        "net": (_b4_net(trial\.arm_b, trial\.returns, stress=1\.0), /        "net": (_b4_net(trial.no_borrow, trial.returns, stress=1.0), /' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation '/^def _b4_leg_metrics(/,/^def /s/^        "seed": 42,$/        "seed": 7,/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/verdict = net_of_cost_verdict(book\[start:\], bench\[start:\], mean_block=30, seed=42, /verdict = net_of_cost_verdict(book[start:], bench[start:], mean_block=30, seed=7, /' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_reads_each_cell_and_each_cost_layer_from_its_own_call[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_cost_layers(/def _b4_cost_layers_gone(/' --mutation 's/^        "gross": (trading(trial\.arm_b, 0\.0), trading(trial\.arm_a, 0\.0)),$/        "gross": (trading(trial.arm_b, _B2_COST_PER_SIDE), trading(trial.arm_a, _B2_COST_PER_SIDE)),/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_readings_cost_layers_take_trial_58s_head_to_head_apart_into_its_gross_trades_and_carry[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_cost_layers(/def _b4_cost_layers_gone(/' --mutation 's/^        "net_of_trading": (trading(trial\.arm_b, _B2_COST_PER_SIDE), /        "net_of_trading": (_b4_net(trial.arm_b, trial.returns, stress=1.0), /' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_readings_cost_layers_take_trial_58s_head_to_head_apart_into_its_gross_trades_and_carry[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_cost_layers(/def _b4_cost_layers_gone(/' --mutation 's/^        "net": (_b4_net(trial\.arm_b, trial\.returns, stress=1\.0), /        "net": (_b4_net(trial.arm_b, trial.returns, stress=1.5), /' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_readings_cost_layers_take_trial_58s_head_to_head_apart_into_its_gross_trades_and_carry[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/^        if n - first < 2:$/        if n - first < 1:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_refuses_fewer_than_2_returns_from_a_legs_first_weight_before_any_head_to_head[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b4_leg_metrics(/def _b4_leg_metrics_gone(/' --mutation 's/^        if n - first < 2:$/        if n - first < 3:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_refuses_fewer_than_2_returns_from_a_legs_first_weight_before_any_head_to_head[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b4_leg_reading(/def _build_b4_leg_reading_gone(/' --mutation '/^def _build_b4_leg_reading(/,/^def /s/^    if as_of is not None:$/    if False:/' -- uv run pytest 'tests/test_research_command.py::test_the_b4_leg_reading_refuses_as_of_before_any_read[b4-leg-reading]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  Each row moves one clause D2–D6 gives the new code. The declaration: the seeds, the spec, the grid and a key (the four declaration rows). The inputs: the BTC fill (the `dict(reads.h4_prices)` row), the leg alone in its book (the `reads.ratios` row), its first weight read off its own book's path and for itself (the `fed` and `if w` rows), the borrow-free book scaled to the BTC (the `_b4_limited(raw)` row), each book and its engaged bars under its own funding (the two swap rows); the spans, the leg alone in the book and in the ensemble (the two span rows). The engagement: each key read off the cell's own book, flags, shortfall and funding (the `book["BTC"]`, `flat, flat`, `trial.arm_a`, `trial.arm_b`, `s >= 0`, `per_year_sums`, `2 * _B4_CARRY_RATE` and `["carried"]` rows), the leg's own first weight and returns from it (the `inputs.trial.first_weight` and `- 1` rows), trial 58's turnover, carry and shares read off its arm B (the `no_borrow` rows, the `c / 2` row and the `trial.arm_a[a]` row). The reads: arm A's net and each cell's at trial 58's costing (the two `stress` rows), each cell from its own leg's first weight (the `min(trial.first_weight…)` row), the full window whole (the `net[first:]` row), the head-to-heads' block and seed (the `mean_block=102` and `seed=7` rows), each key off its own call (the `full["spa_p_value"]` and `primary["mean_outperformance"]` rows), the per-year mean, the primary Sharpe and drawdown and arm A's (the `per_year_sums`, `sharpe(net,`, `net_a[first:]`, `sharpe(net_a,` and `first + 600` rows), the cost layers from trial 58's own start (the `min(inputs.first_weight…)` row) with each key off its own field (the `verdict["mean_outperformance"]` row), arm A's gross uncosted and the net layer arm B's (the `trading(trial.arm_a, _B2_COST_PER_SIDE)` and `trial.no_borrow` rows), and the seed recorded (the `"seed": 7` row). The decomposition: the gross layer uncosted, the trading layer without the carry and the net layer at trial 58's costing (the three cost-layer rows). The refusal's bound from each side (the `< 1` and `< 3` rows) and the as-of refusal's condition (the last row).
- [ ] **Step 9: Commit** — `feat(research): B4's leg reading — each ratio leg alone on the A2 ensemble, carried and borrow-free, against arm A from its first weight, and trial 58's head-to-head by cost, on a frozen set's full history`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 2: the data-gated basis test, the decisions-log entries before the hash, the reads (D1, D7, D8)

**Files:** Create `tests/test_research_b4_leg_reading_basis.py` (module-marked `data`); modify `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 5's own commit.

**Interfaces:** Consumes Task 1's `_b4_leg_inputs` and `_b4_leg_engagement`, and `cli/research/subjects.py`'s `_b4_reads`, `_b4_engagement` and `_B4_ENGAGEMENT_KEYS`; `cli.registry.observed.ObservedReader`, `cli.registry.record.compute_hash` and `cli.research.command._DATA_ROOT`; `tests.skip_gates.nothing_found_under`; `tests.test_trial_registry_provenance._trials`. Produces one test and the module names `BLOCK`, `VOUCHED`, `RETURN_INDICES`, `FIRST_WEIGHT`, `ENGAGEMENT` and `CARRY_PER_YEAR`, of which Task 3's check program imports `BLOCK`, `VOUCHED`, `ENGAGEMENT` and `CARRY_PER_YEAR`. No test computes a return of a book.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis, record 58's figures read off the committed record:

```python
"""B4's leg reading's inputs half against spec 00145's measured basis: positions, the shortfall, its carry, the limits and
turnover, and no return of a book."""

from __future__ import annotations

from pathlib import Path

import pytest

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
# Copied from the spec's measured basis, never from a run.
BLOCK = "9e0fc8e51ace8ac710c08ea3381eb930e2ca43cbedb258e9b5a155f39182d7df"
VOUCHED = {"ohlc-full": "checked (36 vouched hashes)"}
RETURN_INDICES = 27_337
FIRST_WEIGHT = {"ETH/BTC": 5_442, "SOL/BTC": 17_079}
ENGAGEMENT = {
    "first_weight": FIRST_WEIGHT,
    "primary_returns": {"ETH/BTC": 21_895, "SOL/BTC": 10_258},
    "held_per_year": {
        "ETH/BTC": {
            "carried": _YEARS
            | {
                "2016": 644,
                "2017": 1_443,
                "2018": 696,
                "2019": 1_010,
                "2020": 1_376,
                "2021": 1_582,
                "2022": 1_141,
                "2023": 1_115,
                "2024": 939,
                "2025": 1_127,
                "2026": 324,
            },
            "no_borrow": _YEARS
            | {
                "2016": 527,
                "2017": 1_196,
                "2018": 505,
                "2019": 672,
                "2020": 1_099,
                "2021": 970,
                "2022": 685,
                "2023": 648,
                "2024": 655,
                "2025": 726,
                "2026": 298,
            },
        },
        "SOL/BTC": {
            "carried": _YEARS | {"2021": 764, "2022": 920, "2023": 1_401, "2024": 1_240, "2025": 1_072, "2026": 285},
            "no_borrow": _YEARS | {"2021": 514, "2022": 566, "2023": 1_104, "2024": 981, "2025": 705, "2026": 234},
        },
    },
    "positions_differ_per_year": {
        "ETH/BTC": {
            "carried": _YEARS
            | {
                "2016": 1_434,
                "2017": 2_160,
                "2018": 1_432,
                "2019": 2_001,
                "2020": 2_060,
                "2021": 2_097,
                "2022": 1_820,
                "2023": 2_155,
                "2024": 1_997,
                "2025": 1_926,
                "2026": 395,
            },
            "no_borrow": _YEARS
            | {
                "2016": 1_428,
                "2017": 2_115,
                "2018": 1_401,
                "2019": 1_902,
                "2020": 2_042,
                "2021": 1_958,
                "2022": 1_757,
                "2023": 2_058,
                "2024": 1_871,
                "2025": 1_832,
                "2026": 395,
            },
        },
        "SOL/BTC": {
            "carried": _YEARS | {"2021": 934, "2022": 1_867, "2023": 2_100, "2024": 1_964, "2025": 1_880, "2026": 397},
            "no_borrow": _YEARS | {"2021": 891, "2022": 1_830, "2023": 2_058, "2024": 1_871, "2025": 1_832, "2026": 395},
        },
    },
    "shortfall_stamps_per_year": {
        "ETH/BTC": {
            "carried": _YEARS
            | {
                "2016": 192,
                "2017": 582,
                "2018": 544,
                "2019": 582,
                "2020": 903,
                "2021": 1_255,
                "2022": 983,
                "2023": 727,
                "2024": 477,
                "2025": 621,
                "2026": 292,
            },
            # Float rounding: the twin's shortfall is at most 1.39e-17 (the basis).
            "no_borrow": _YEARS
            | {
                "2016": 1,
                "2017": 9,
                "2018": 23,
                "2019": 4,
                "2020": 30,
                "2021": 30,
                "2022": 26,
                "2023": 9,
                "2024": 16,
                "2025": 6,
                "2026": 24,
            },
        },
        "SOL/BTC": {
            "carried": _YEARS | {"2021": 330, "2022": 591, "2023": 370, "2024": 620, "2025": 482, "2026": 173},
            "no_borrow": _YEARS | {"2021": 3, "2022": 14, "2023": 1, "2024": 14, "2025": 6, "2026": 8},
        },
    },
    "limit_engaged": {
        leg: {funding: dict.fromkeys(("gross", "net", "margin"), 0) for funding in ("carried", "no_borrow")} for leg in FIRST_WEIGHT
    },
    "turnover": {
        "ETH/BTC": {"carried": 156.66817821488746, "no_borrow": 145.97954113038912},
        "SOL/BTC": {"carried": 147.95819177005933, "no_borrow": 146.4464868776143},
    },
    "context_carry_by_leg": {"ETH/BTC": 0.06755582258742332, "SOL/BTC": 0.015580070714425956},
    "context_turnover_by_leg": {"ETH/BTC": 23.912564023957138, "SOL/BTC": 6.077390770007466, "EUR": 127.65832014316521},
}
# Each carried book's carry per close year at six decimals; the twins' rounds to none.
CARRY_PER_YEAR = {
    "ETH/BTC": {
        "carried": {
            "2016": 0.001688,
            "2017": 0.003143,
            "2018": 0.006144,
            "2019": 0.006081,
            "2020": 0.007869,
            "2021": 0.008174,
            "2022": 0.007188,
            "2023": 0.012772,
            "2024": 0.006037,
            "2025": 0.004446,
            "2026": 0.003996,
        },
        "no_borrow": {},
    },
    "SOL/BTC": {
        "carried": {"2021": 0.001128, "2022": 0.003365, "2023": 0.001298, "2024": 0.004224, "2025": 0.002188, "2026": 0.00119},
        "no_borrow": {},
    },
}


def reading_inputs():
    """The reading's inputs half over the real set, with the reader that read it."""
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b4_leg_inputs(subjects._b4_reads("b4-leg-reading", reader, "ohlc-full", None, False))


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "ohlc-full/*/BTC/240.parquet"),
    reason="the frozen ohlc-full set or its two ratio legs are absent under data/",
)
def test_the_leg_readings_inputs_reproduce_the_measured_basis_and_record_58s_books():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = reading_inputs()
    assert compute_hash(reader.block()) == BLOCK and reader.vouched_status() == VOUCHED
    trial, n = inputs.trial, len(inputs.trial.close)
    assert n == RETURN_INDICES
    # Trial 58's books are record 58's: every key its engagement stores, to the last bit.
    record = _trials()[58]["metrics"]
    assert subjects._b4_engagement(trial) == {key: record[key] for key in subjects._B4_ENGAGEMENT_KEYS}
    assert inputs.first_weight == trial.first_weight == FIRST_WEIGHT

    def first_differ(book: dict, other: dict) -> int:
        return next((k for k in range(n) if any(book[i][k] != other.get(i, [0.0] * n)[k] for i in book)), n)

    # Each leg's two books are arm A's until the leg takes weight, and ETH/BTC's trial 58's until SOL/BTC does.
    for leg, first in FIRST_WEIGHT.items():
        assert [first_differ(book, trial.arm_a) for book in inputs.books[leg].values()] == [first, first]
    sol = FIRST_WEIGHT["SOL/BTC"]
    for funding, trial_book in (("carried", trial.arm_b), ("no_borrow", trial.no_borrow)):
        assert first_differ(inputs.books["ETH/BTC"][funding], trial_book) == sol and not any(trial_book["SOL/BTC"][:sol])
    engagement = subjects._b4_leg_engagement(inputs)
    assert {key: engagement[key] for key in ENGAGEMENT} == ENGAGEMENT
    assert (engagement["turnover_a"], engagement["turnover_b"]) == (record["turnover_a"], record["turnover_b"])
    carry = {
        leg: {funding: {year: round(v, 6) for year, v in years.items() if round(v, 6)} for funding, years in by_funding.items()}
        for leg, by_funding in engagement["carry_per_year"].items()
    }
    assert carry == CARRY_PER_YEAR
```

  **Author's call** — the case holds the reading's inputs half to the spec's two programs, which built the books by their own expression, so the measured figures and the subject's code are two derivations that must agree; trial 58's books to record 58 by its twelve stored engagement keys and its two turnovers, the stored figures, never a second typing; the spans as each book's first difference, exactly at the first weight it names; the integer engagement and the turnover exactly, as the programs printed them, the carry at the six decimals they printed.
- [ ] **Step 2: Run it** — with `data/ohlc-full` linked in this worktree: `mkdir -p .tmp/plan-00145 && uv run pytest tests/test_research_b4_leg_reading_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00145/pt`, one plain blocking call, `timeout` 600000 ms: `1 passed`, never a skip (measured on the authoring tree, a call of 359.69 s). The case joins `tests/slow-cases.txt` at its `sorted()` place:

```text
tests/test_research_b4_leg_reading_basis.py::test_the_leg_readings_inputs_reproduce_the_measured_basis_and_record_58s_books
```

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b4_leg_reading_basis.py tests/slow-cases.txt`; the Global Constraints' `T` over the two paths (measured `18 passed, 1 deselected in 18.35s`); the two tree walkers its skip gate and data mark meet, `mkdir -p .tmp/plan-00145 && uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00145/pt` (measured `328 passed`); `uv run pre-commit run -a` until clean. No probe: the case is slow, recorded `probe skipped: slow case`.
- [ ] **Step 4: Commit** — `test(research): B4's leg reading's inputs half against the measured basis — the block, the first weights, the spans, each cell's holding, BTC shortfall, carry, limits and turnover, and record 58's books`, the message carrying the gate's result line, `probe skipped: slow case — tests/test_research_b4_leg_reading_basis.py::test_the_leg_readings_inputs_reproduce_the_measured_basis_and_record_58s_books`, the line `It reads data/ohlc-full: re-run it with the set linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.` and the two trailer lines.
- [ ] **Step 5: The decisions-log entries, before the hash** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`, after one blank line, the loop's pick (spec 00145 D1) and then **Author's call** the reading's conventions, plan 00142's shape, so that the criterion stands in the log before any return of a book is read:

```markdown
[iter-190] B4's next step after trial 1 — a no-slot reading of trial 58's books by leg and by cost, the loop's pick under the owner's run instruction (Decision: 1)
  Said, attended, 2026-10-23, after B2's close, asked which family comes next: "B4-legs (Recommended)" (the `[iter-188]` entry above). Then, launching this unattended run: "continue working on B4-legs and other research strates. Ignore the wall time clock gate, but do not pick up new topics after 09:00Z". B4 trial 1 (registry trial 58) was rejected: arm B passed the kill bar, but its head-to-head against arm A from the first ratio weight was −4.700758514095985e-06/bar (SPA p 0.8500749625187406), and its borrow-unavailable twin's −1.4398882599350185e-06 (p 0.6421789105447276) at a net Sharpe 1.4721 above arm A's 1.4050 (the `[iter-189] Verdict — B4 trial 1 REJECT` entry above). The run closes no family — closing is the owner's — so B4's next step after trial 1, T0016's B4 arm, is the loop's pick under that instruction. Standing and unchanged: the instrument ruling "Frozen ohlc-full (Recommended)" and the two `[iter-176]` rulings.
  1. **A no-slot reading of trial 58's books by leg and by cost** — each leg alone on the A2 ensemble, as trial 58 costed it and as its borrow-free twin, and trial 58's arm B taken apart into its gross, its trading cost and its carry; it screens the untried variants before a slot is spent, as iter-186 did for B2, and spends none of bucket B's 12. Spec 00145: alone, ETH/BTC holds a position at 11,397 return indices and its book borrows BTC at 7,158, SOL/BTC holds at 5,682 and borrows at 2,566; held to the book's own BTC, they hold at 7,981 and 4,104 (spec 00145's measured basis). Chosen.
  2. **Trial 2 on ETH/BTC alone** — the author's park variant of spec 00144; one slot, with no evidence that ETH/BTC carries what trial 1 lost.
  3. **Trial 2 on the symmetric legs** — short the pairs as well, at an ETH or SOL borrow of 0.0004 per 4h (about 88 % a year) on any shortfall, where trial 1's BTC carry, `carry_per_year` summed, was 0.0831 of NAV over the window beside its head-to-head of −4.700758514095985e-06/bar from the first ratio weight; one slot.
  4. **Closing B4** — the owner's call, never the loop's.

[iter-190] B4's leg reading's conventions, pinned by spec 00145 before its hash (Decision: 1)
  The reading's details are fixed in the spec, reviewed, and frozen by its sha256, the reading's `spec_hash`, before any return of a cell or of trial 58's books is computed over the data — no net-of-cost series, head-to-head or cost layer; each call below is one the spec pins, the author's unless it names the ruling or the spec it carries, every value the owner or specs 00141, 00142 and 00144 fixed staying theirs.
  1. **As the spec pins them** — one reading subject, `b4-leg-reading`, named so that no registered or retired subject's name opens it and it opens none, with no rule, family or count, kept with `--reading` and spending no B slot, over frozen `ohlc-full`'s full history through trial 58's reads, its block record 58's (D2); trial 58's three books by its own inputs half, unchanged, and each ratio leg alone beside the ten EUR assets in the three adopted A2 arms, once as trial 58 costed arm B — 0.006 a side on each instrument's own turnover, the BTC it sells beyond the book's own borrowed at 0.0002 per 4h with the opening charge, §10's limits as one factor per bar — and once held to the book's own BTC as trial 58's twin was, each leg's first weight read off its own book's weight path, each book arm A's to the bit before its leg's first weight and ETH/BTC's trial 58's to the bit before SOL/BTC's (D3); per cell, the head-to-head against arm A from its leg's first weight and over the full window, `net_of_cost_verdict` at mean block 30, seed 42 and 2,000 resamples, the net Sharpe and maximum drawdown beside arm A's over both windows, the mean outperformance per close year, and no kill bar (D4); trial 58's arm B against arm A from its first ratio weight gross, net of its trading cost alone and net of both, the last record 58's to the bit, its carry apportioned to the legs pro rata to their positions at each bar and its turnover by leg (D5); 31 keys, the cells nested by leg and funding, the engagement read from positions alone, trial 58's refusals and an `--as-of` refusal (D6); the potential criterion — read first, a floor of the leg held at 2,190 return indices or more; then the primary mean outperformance above 0, its SPA p below 0.05/4, Bonferroni over the four cells, and the cell's maximum drawdown from its leg's first weight not above arm A's over the same closes — read by the closeout's pick and never by code, the contamination stated in full — trial 58's instrument and books, its result known, the cost layers' means arithmetic of record 58's stored figures, ETH/BTC alone trial 58's arm B on 11,637 of its 21,895 primary returns, a trial it justifies carrying the reading's id and record 58's and counting B4's true trials — a cell with potential naming its trial and none the evidence for the owner's family call (D7); one run after the hash, no plain eval before or after it, the subject retired after it (D8). Chosen.
  2. **The alternatives each weighed** — each leg's first weight read off trial 58's twelve-instrument path, which agrees on this set but is not the path the leg's own book reads; the drawdown over the full window, where before the leg's first weight a cell's drawdown is arm A's own; a floor on the closes at which the books differ, which counts the EUR legs' reweighting where the leg is held flat; no floor; the carry apportioned by each leg's own single-leg carry, which does not sum to trial 58's; the twins' shortfall counted with a tolerance in place of their float rounding; a kill bar per cell, which a reading does not run; a correction over B4's five looks, record 58 and the four cells, in place of the four cells'; a trial spent on a park variant in the reading's place (the pick above).
  Source: spec 00145 (D1–D8), its **Author's call**s and the calls it carries from the owner and specs 00141, 00142 and 00144; the owner's words quoted in the pick above.
```

  staged alone, its gate `mkdir -p .tmp/plan-00145 && uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00145/pt` (measured in a scratch worktree over Tasks 1–2's tree, the two entries appended, `50 passed`) and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-190] B4's next step after trial 1 — the loop's pick, a no-slot reading of trial 58's books by leg and by cost — and its conventions, pinned by spec 00145 before its hash`. The pick's header is what T0016's B4 `ripe_when` greps for (`^\[iter-[0-9]+\] B4.s next step after trial 1`; measured in the scratch worktree, the check prints 1 once the entry stands), so T0016's B4 arm reads ripe until Task 5 gives it its next trigger, which prints 0 (measured).
- [ ] **Step 6 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–2 and the two entries — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing computes or reads any cell's or trial 58's net-of-cost series, head-to-head or cost layer — through the code, a program or arithmetic over record 58's stored figures — or runs the reading over the real data, before the spec's hash, and the data-gated case runs with the frozen full set linked into the reader's worktree and unlinked by the reader before its report, since unlinked it skips. Each report names the tip it read, the tip Task 3 step 1 diffs from. Task 3 waits until the trio has closed with no open Critical or Important.

## Task 3 (the controller's): the gate, the spec hash, the develop check, the data test and the check programs (D8)

- [ ] **Step 1: The gate** — each check its own call, each read before the next: the reads through Task 2 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00145-b4-leg-reading-design.md docs/research/10.phase4-decisions.md` exits 0; the conventions entry against the spec at that tip, each item where the spec pins it and each call the spec carries under the ruling or spec it names; trial 58's code path since record 58's run — the spec's basis lists it from that run's commit to the branch's cut — `git log --oneline 93c0ec7af12323c3cda294481854e9cf878802d6..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/risk cli/costs cli/data uv.lock pyproject.toml .python-version`, lists Task 1's commit and its fixes alone (measured at the base: nothing); any other commit is named, step 4 deciding whether it moved trial 58's figures: its data test the inputs half, record 58's replay the computes half.
- [ ] **Step 2: D8 (1), the spec hash** — `sha256sum docs/specs/00145-b4-leg-reading-design.md`; its value, pasted from that call, is the run's `--spec-hash` and the reading's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D8 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0. A non-zero exit stops before the run: the controller reads which line moved, the same `git diff` without `--quiet`, and only for a line another writer appended legitimately — a registry record another branch's merged PR carries; the operating model gives the reading ledger no other writer while this branch is open, so a line there stops the task, T0016's — merges develop, alone (`git merge --no-edit origin/develop`) — a conflict confined to `docs/research/10.phase4-decisions.md` or `tests/slow-cases.txt` resolved keeping both sides' lines, in the decisions log develop's entries above this branch's and in the slow-cases file each line at its `sorted()` place, and committed as the merge; a conflict in any other file aborted with `git merge --abort`, which stops the task, T0016's — then takes a delta read of the merge in place of re-running step 1: step 1's trial-58 log over `<the tip the last read names>..HEAD`, then `pre-review`, then `review` over that range and `re-review` over a fix of it within the branch's two, each `drive` carrying Task 2 step 6's sentence with its "before the spec's hash" read "before Task 4's run", the commits the log lists, and one sentence more: develop's commits were each read on their own PR, so the read judges the merge's resolution and each listed commit's effect on the reading — whose tip becomes the tip the last read names, and step 4 runs on the merged tree. The check has two sites, this step and Task 4 step 1, and both take this path.
- [ ] **Step 4: D8 (3), the data test on the run's tree, with the subject's two fixture rows and record 58's replay** — `mkdir -p .tmp/plan-00145 && ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b4_leg_reading_basis.py 'tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b4-leg-reading-evaluates]' 'tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b4-leg-reading]' 'tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[trial-58]' -q -p no:cacheprovider --basetemp=.tmp/plan-00145/pt > .tmp/plan-00145/basis.out 2>&1`, one background call: `4 passed`, never a skip or an xfail — the fixture rows run the build end to end on the tree a fix of the reads may have changed, and record 58's replay rebuilds trial 58's stored figures — its net head-to-head, Sharpe ratios, drawdowns and turnovers — through the costing and head-to-head code the reading's computes half shares with it (measured at `65e7d6024`, a call of 315.46 s); a failure is a finding before the run — the data test's an instrument finding, a fixture row's a defect in the code, the replay's a moved computes half — T0016's, and the run waits.
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00145/reading_check.py`, the ledger line's checks, its one argument the spec's sha256:

```python
"""Spec 00145's reading, read off the ledger's last line against the run's print, record 58 and the measured basis: exit
0 when every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b4_leg_reading_basis import BLOCK, CARRY_PER_YEAR, ENGAGEMENT, VOUCHED

spec_hash = sys.argv[1]
r = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(".tmp/plan-00145/b4-leg-reading.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
record = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[57])["metrics"]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
# Spec 00145 D6's keys read per cell, each nested by leg and funding.
per_cell = (
    "head_to_head_mean_outperf_primary",
    "head_to_head_spa_p_primary",
    "head_to_head_mean_outperf_full",
    "head_to_head_spa_p_full",
    "mean_outperf_per_year",
    "ann_sharpe_noc_primary",
    "ann_sharpe_noc_full",
    "max_drawdown_primary",
    "max_drawdown_full",
    "held_per_year",
    "positions_differ_per_year",
    "turnover",
    "shortfall_stamps_per_year",
    "shortfall_mean_per_year",
    "carry_per_year",
    "limit_engaged",
)
carry = {
    leg: {funding: {year: round(v, 6) for year, v in years.items() if round(v, 6)} for funding, years in by_funding.items()}
    for leg, by_funding in m["carry_per_year"].items()
}
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "invocation": invocation
    == {
        "subject": "b4-leg-reading",
        "dataset": "ohlc-full",
        "window": None,
        "as_of": None,
        "accept_holes": False,
        "comparator_trial": None,
    },
    "labels": (r["iteration"], r["outcome"], r["attempt"]) == ("iter-190", None, None),
    "keys": set(m) == SUBJECTS["b4-leg-reading"].metric_keys,
    "printed": printed["metrics"] == m,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == BLOCK and printed["vouched"] == VOUCHED,
    "engagement": {key: m[key] for key in ENGAGEMENT} == ENGAGEMENT and carry == CARRY_PER_YEAR,
    "record 58": (
        m["context_head_to_head_mean_outperf"]["net"],
        m["context_head_to_head_spa_p"]["net"],
        m["turnover_a"],
        m["turnover_b"],
        m["arm_a_ann_sharpe_noc_full"],
        m["arm_a_max_drawdown_full"],
    )
    == (
        record["head_to_head_mean_outperf_primary"],
        record["head_to_head_spa_p_primary"],
        record["turnover_a"],
        record["turnover_b"],
        record["arm_a_ann_sharpe_noc"],
        record["arm_a_max_drawdown"],
    ),
    "cells": all(
        set(m[key]) == {"ETH/BTC", "SOL/BTC"} and all(set(by) == {"carried", "no_borrow"} for by in m[key].values())
        for key in per_cell
    ),
    "layers": set(m["context_head_to_head_mean_outperf"])
    == set(m["context_head_to_head_spa_p"])
    == {"gross", "net_of_trading", "net"},
    "constants": (m["mean_block"], m["seed"], m["n_resamples"]) == (30, 42, 2000),
}
print(r["reading_id"], checks)
sys.exit(0 if all(checks.values()) else 1)
```

  and `.tmp/plan-00145/cells_print.py`, the print Task 4's entry reads the criterion off:

```python
"""The reading's four cells and trial 58's three cost layers off the ledger's last line, one a line — each cell's floor
count, its primary mean outperformance and SPA p, its full-window pair and its drawdown and Sharpe from its leg's first
weight beside arm A's; then each layer's mean outperformance and SPA p, and the carry and turnover by leg; it judges none
of them."""

import json
from pathlib import Path

m = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])["metrics"]
for leg in ("ETH/BTC", "SOL/BTC"):
    for funding in ("carried", "no_borrow"):
        print(
            leg,
            funding,
            "first weight",
            m["first_weight"][leg],
            "held",
            sum(m["held_per_year"][leg][funding].values()),
            "primary",
            m["head_to_head_mean_outperf_primary"][leg][funding],
            m["head_to_head_spa_p_primary"][leg][funding],
            "full",
            m["head_to_head_mean_outperf_full"][leg][funding],
            m["head_to_head_spa_p_full"][leg][funding],
            "drawdown",
            m["max_drawdown_primary"][leg][funding],
            "arm A",
            m["arm_a_max_drawdown_primary"][leg],
            "Sharpe",
            m["ann_sharpe_noc_primary"][leg][funding],
            "arm A",
            m["arm_a_ann_sharpe_noc_primary"][leg],
        )
for layer in ("gross", "net_of_trading", "net"):
    print("trial 58", layer, m["context_head_to_head_mean_outperf"][layer], m["context_head_to_head_spa_p"][layer])
print("carry by leg", m["context_carry_by_leg"], "turnover by leg", m["context_turnover_by_leg"], "arm A", m["turnover_a"])
```

  Each is written with `mkdir -p .tmp/plan-00145 && cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00145/reading_check.py .tmp/plan-00145/cells_print.py`. Measured on the authoring tree, with their two input paths pointed at a synthetic ledger line and run print shaped as the reading's — the subject's metrics over `_b4_dataset`, the engagement keys, the carry and the record-58 figures set to the basis's and record 58's, record 58's block — `reading_check.py` printed every check true and exited 0, and with a wrong spec hash exited 1; `cells_print.py` printed its eight lines. **Author's call — the `record 58` check**: the net layer's pair, arm A's full-window Sharpe and drawdown and both turnovers are record 58's own figures recomputed, so each must equal its stored value to the bit, the reproduction D5 and D6 name. **Author's call — the `cells` check reads the nesting**: every per-cell key holds both legs and each leg both fundings, so a line keyed another way fails before any figure is read.

## Task 4 (the controller's): the reading — its run, its line, its replay and its entry (D7, D8)

`<H>` is Task 3 step 2's sha256.

- [ ] **Step 1: The develop check** — Task 3 step 3 whole, its stop, its merge path and Task 3 step 4 after a merge with it; `git status --short` prints nothing.
- [ ] **Step 2: The run** — one run, no plain eval before or after it: `mkdir -p .tmp/plan-00145 && uv run zcrypto research eval --subject b4-leg-reading --dataset ohlc-full --reading --iteration iter-190 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00145/b4-leg-reading.out 2>&1`, about seven minutes (the spec's basis: the inputs half 359.69 s, the computes half 49.6 s), one background call, `cat` at its notification. The notes, written before the run, name only what is fixed before it: `subject b4-leg-reading over ohlc-full, full history, no as-of; descriptive, no bar, no verdict, no B slot, changing no verdict of B4 trial 1 (registry trial 58); trial 58's books unchanged - arm A the adopted equal-weight A2 4h ensemble on the ten EUR assets, arm B the same three arms with the venue's ETH/BTC and SOL/BTC 4h pairs beside them, and its borrow-unavailable twin; four cells, each ratio leg alone beside the ten EUR assets in the same three arms, once as trial 58 costed arm B - every instrument charged 0.006 per side on its own turnover, the BTC the leg sells netted against the book's own BTC/EUR position and the shortfall borrowed at 0.0002 per 4h rollover plus the opening charge on each increase, the section 10 limits as one factor per bar - and once with the leg scaled each bar to the book's own BTC; per cell, its head-to-head against arm A from its leg's first weight (ETH/BTC return index 5442, SOL/BTC 17079) and over the full window, net_of_cost_verdict at mean block 30, seed 42 and 2000 resamples, its net Sharpe and maximum drawdown beside arm A's over both windows, and its mean outperformance per close year; trial 58's arm B against arm A from return index 5442 gross, net of its trading cost alone and net of both, the last record 58's own, its carry apportioned to the legs pro rata to their positions at each bar and its turnover by leg; the potential criterion - read first, a floor of the cell's leg held at 2190 return indices or more; then the primary mean outperformance above 0, its SPA p below 0.05/4, Bonferroni over the four cells, and the cell's maximum drawdown from its leg's first weight not above arm A's over the same closes - read by the closeout's pick, never by code; pre-registered by the spec's sha256 <H>`. A refused build — exit 1 with no traceback, naming `b4-leg-reading over the full history: …` or a file of either leg — keeps no reading and is recorded in T0016 with its line quoted (Task 5), the reading's design standing unrun; a refusal before the build reads anything — the tree (`… has uncommitted changes …`), the spec hash (`--spec-hash … is not …`) or the dataset's presence (`dataset 'ohlc-full' is absent …`, `… is missing N series …`) — keeps nothing and computes nothing: its cause fixed, the same command runs again, still the one run; any other end — a traceback, a signal or another refusal (the ledger's, a tree changed during the fit, the build's keys or metrics refused) — stops the task, T0016's with the end of the run's output quoted whole, any line the run appended left uncommitted in the worktree, neither committed nor reverted, for the owner's ruling, on which Tasks 5–6 wait.
- [ ] **Step 3: The reading's checks** — `uv run python .tmp/plan-00145/reading_check.py <H>` exits 0; a failed check stops the task before step 4 as step 2's other ends do, its printed line quoted whole.
- [ ] **Step 4: The cells print** — `uv run python .tmp/plan-00145/cells_print.py`, its eight lines the entry's source.
- [ ] **Step 5: The records commit** — (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-190] B4's ratio legs read alone and trial 58's head-to-head read by cost on frozen ohlc-full (reading <its reading_id>)`, its header to its first `. ` holding no verdict word; the body: the subject, the set and the block `9e0fc8e5…82d7df`; that the reading is descriptive, spends no slot and changes no verdict of trial 58 (D2, D7); record 58's figures reproduced — the net layer's pair to the bit; the floor, each cell's holding against 2,190, and for each of the criterion's three legs the cells the floor admits that meet it, read off step 4's print; the four cells' rows, each figure unrounded off the reading's ledger line — the primary mean outperformance and SPA p, the full-window pair, the drawdown and Sharpe from the leg's first weight beside arm A's; the cells with potential, each with the trial it names — that leg alone at that funding, how it differs from trial 58 — or, where none has potential, that no cell has it and that this is the evidence the owner's family call reads; the context rows — each layer's mean outperformance and SPA p, the steps between them as trial 58's trading cost and carry per bar, and the carry and turnover by leg — named as rows no criterion reads; the caveats — the twins' shortfall counts float rounding, the per-year means counting every close of a year — and the contamination D7 states, ETH/BTC alone trial 58's arm B on 11,637 of its 21,895 primary returns and the correction over the four cells and not B4's five looks among it; in the form of reading 5's `[iter-186]` entry; (ii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-<its id>]` at its `sorted()` place, the replay rebuilding the whole reading. Then `git add` by path of the ledger, the decisions log and the slow-cases file; `T` over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path; `uv run pre-commit run -a` until clean, its rewrites staged. In the probe worktree, which the Global Constraints' probe setup creates from that index and whose tree it prints, `data/ohlc-full` linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/ohlc-full /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter190/.tmp/plan-00145/probe/data/ohlc-full`, unlinked after the replay with `test -L /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter190/.tmp/plan-00145/probe/data/ohlc-full && unlink /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter190/.tmp/plan-00145/probe/data/ohlc-full` and the worktree removed as the Global Constraints' probe paragraph removes one that held a link: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'reading-<its id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt`, one background call: `1 passed`, never a skip, its result line and call time for the message — a difference stops the task before the commit as step 2's other ends do, the replay's output quoted whole. Commit that index, with no `git add` after the setup, as `docs(research): B4's leg reading — each ratio leg alone and trial 58's head-to-head by cost on ohlc-full, kept as reading <id>; no trial spent`, the message carrying the tie tests' result line, the replay's with its call time, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-<id>]`, the line `The replay reads data/ohlc-full: re-run it with the set linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.`, and the two trailer lines; after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes. The entry adds no guard: no probe.

## Task 5: T0016, the index and the retirement of the subject (D7)

**Files:** `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/retired_subjects.py`.

On a refused build (Task 4 step 2) no reading exists: Task 4's steps 3–5 do not run, so no finding entry lands, and this task runs without a reading; on Task 4's other stops once its run has started — step 2's other ends, a failed check (step 3), a replay difference (step 5) — it waits on the owner's ruling (Task 4 step 2). On a refused build every sentence of Tasks 5–6 that assumes a reading changes, and these are all of them: step 1's figures are read off the refused line and the count; its Findings bullet, headed `**B4's leg reading (iter-190, spec 00145).**`, quotes the refused line whole from `.tmp/plan-00145/b4-leg-reading.out`; its Done-so-far sentence names no reading and ends `no slot spent, the subject kept.`; its next-step bullet keeps every candidate it lists, its words from `reading spec 00145's potential criterion` through `beside the criterion` reading `reading the refused build, quoted in Findings, the design unrun: a trial on one leg alone (ETH/BTC or SOL/BTC, carried or held to the book's own BTC) or the owner's family call, hold or close B4; beside it`, with no arm for a reading in which no cell has potential, and its trigger's `reading spec 00145''s potential criterion` becomes `reading the refusal`, its check unchanged; step 3 does not run, since a later run still evaluates the subject (`tests/retired_subjects.py`'s own rule), so step 4 stages the two `docs/open-topics/` paths alone and its message ends `the reading refused, its subject kept`; Task 6 step 2's `pre-review` reads Task 5's commits and the row's, and its `drive` names the data-gated case alone, no replay; and Task 6 step 3's body quotes the refused line in place of the cells print and names no cell.

- [ ] **Step 1: T0016**, per `topic-ops`, every figure read off the committed reading and its entry:
  - `## Findings so far`: the budget bullet's figures read off the count the bucket refusal reads, every orphan in it, `uv run python -c 'import json; from pathlib import Path; from cli.registry import attempts, budget; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2", "B4")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])'` — the reading spends none (measured at this branch's base: `{'B1': 5, 'B2': 7, 'B4': 1} remain 12 []`, T0016's line `B1 spent 5, B2 spent 7, B4 spent 1, 12 remain`): the line reads `B1 spent <its B1>, B2 spent <its B2>, B4 spent <its B4>, <its remain> remain`, each orphan it lists named there; and after the `**B4 trial 1 REJECT (iter-189, spec 00144, registry trial 58).**` bullet, one bullet `**B4's leg reading (iter-190, spec 00145, reading <N>).**` — in one or two sentences, the cells with potential and the trial each names, or that none has potential, and where trial 58's loss sat among its gross, its trading cost and its carry, pointing at its decisions-log entry for the figures; or, on a refused build, its line quoted whole.
  - `## Done so far`: the **B4 opened** bullet's last sentence, `Trial 1 (registry trial 58) REJECT.`, gains after it ``The leg reading (iter-190, spec/plan `00145`, reading <N>): the subject `b4-leg-reading` and its data-gated basis test `tests/test_research_b4_leg_reading_basis.py`, no slot spent, the subject retired.``
  - `## Suggested next steps`: `- (owner) B4's next step after trial 1's REJECT — a further trial (ETH/BTC alone; the symmetric legs, short the pairs at an ETH or SOL borrow; a further leg or pair; the legs' own vol target or weight cap) or closing the family — recorded as a `[iter-NNN] B4's next step after trial 1` entry; then per §5 ranking: B3 → C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism).` becomes ``- (the loop's pick under a run instruction, else the owner's; a close is the owner's) B4's next step after the leg reading — reading spec 00145's potential criterion: a trial a cell with potential names (that leg alone, that funding), its own pre-registration against the shared B budget carrying D7's contamination, or, with none, the owner's family call, hold or close B4; beside the criterion the pick reads every candidate still untried — the symmetric legs, short the pairs at an ETH or SOL borrow; a further leg or pair; the legs' own vol target or weight cap — recorded as a `[iter-NNN] B4's next step after the leg reading` entry; then per §5 ranking: B3 → C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism).``
  - `ripe_when`: its B4 arm ``B4: an activity, the owner picks B4''s next step after trial 1 — a further trial or closing the family — recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] B4.s next step after trial 1'' docs/research/10.phase4-decisions.md` prints at least 1;`` becomes ``B4: an activity, B4''s next step after the leg reading is picked — the loop''s pick under a run instruction, else the owner''s, a close the owner''s — reading spec 00145''s potential criterion, recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] B4.s next step after the leg reading'' docs/research/10.phase4-decisions.md` prints at least 1;`` — in the frontmatter's single quotes, each `'` inside it doubled as written here, the check kept in its own backticks; the other families' arms unchanged. Measured in the scratch worktree: the frontmatter parses to the intended text, the check run as written prints 0, and `tests/test_open_topics_frontmatter.py tests/test_topics_index.py tests/test_retired_subjects.py` pass (`1116 passed`) with steps 2–3 applied.
- [ ] **Step 2: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 3: The retirement** — **Author's call**, `tests/retired_subjects.py`'s own rule: no trial still to run evaluates the reading's subject, so `RETIRED_SUBJECTS` gains `"b4-leg-reading",` after `"b4-ratio-legs-preflight",`, and the comment above B4's names, `# B4's finished trials.`, becomes `# B4's finished trials and the reading beside them.`, B2's form. Every test function Task 1 adds is parametrised by the subject's name, so the hook marks each case and no function carries the mark by hand; `test_each_subject_declares_the_metric_keys_its_build_returns` keeps its new line, the subject staying in `SUBJECTS`. `uv run pytest tests/test_research_command.py -m "not retired" --collect-only -q -p no:cacheprovider | grep -c -E "b4-leg-reading|b4_leg"` prints 0 and the same under `-m retired` prints 17 (measured in the scratch worktree), and `mkdir -p .tmp/plan-00145 && uv run pytest tests/test_retired_subjects.py -q -p no:cacheprovider --basetemp=.tmp/plan-00145/pt` passes (measured `5 passed`).
- [ ] **Step 4: Gate and commit** — `git add` the three paths; `T` over them with `tests/test_open_topics_frontmatter.py` and `tests/test_retired_subjects.py` by path; `uv run pre-commit run -a` until clean; committed as `docs(open-topics): T0016 after B4's leg reading; the reading's subject retired`.

## Task 6 (the controller's): the change-index row, the read and the PR

- [ ] **Step 1: The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-190 — B4 leg reading: each leg alone and by cost` (69 characters by `printf '%s' <it> | wc -m`, under the cap), its own commit.
- [ ] **Step 2: The read** — the `pre-review` of Tasks 4–5's commits and the row's, then `review` over `<the tip the last read names>..HEAD`, and `re-review` over a fix of it within the branch's two, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated case and the replay the messages record run with the frozen full set linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 3: The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the cells print as Task 4 step 4 printed it, in a fenced block, with the cells under the floor, the cells the floor admits meeting each leg of the criterion and those with potential, or none; every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the last read names. Merged through `merge-pr`; before it, `git status --short --ignored` read, `.tmp/plan-00145` collected and removed, and the link removed with `test -L <the checkout>/data/ohlc-full && unlink <the checkout>/data/ohlc-full` in this worktree and in each reader's checkout whose `data/` holds it; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows `ohlc-full` still there.

Decisions log: the loop's pick and the conventions entry (Task 2 step 5), before the hash; the reading's finding entry (Task 4 step 5), in its line's commit; B4's next step after the leg reading is a later branch's, its entry T0016's trigger.
