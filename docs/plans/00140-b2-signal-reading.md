# B2's signal reading — the four trialled crowding signals' forward returns on frozen ohlc-full, by tail and by arm A's state: the chunked contrast, the reading subject, its run and its entry — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next, the controller's steps the Global Constraints' executors line names aside. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1, at the tier its tasks' paths decide: `full` (measured: `uv run python infra/scripts/tier.py --paths cli/alpha/b2.py tests/test_alpha_b2.py cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt tests/test_research_b2_signal_reading_basis.py docs/reference/reading-ledger.jsonl tests/retired_subjects.py docs/research/10.phase4-decisions.md docs/open-topics/T0023-b2-derivatives-data-sourcing.md docs/open-topics/T0016-bucket-b-c-alpha-families.md docs/open-topics/README.md docs/reference/change-index.md docs/specs/00140-b2-signal-reading-design.md` prints `tier: full`, for `tests/test_alpha_b2.py` "a test importing cli.alpha.b1", `tests/test_research_command.py` "a test importing cli.alpha", and, once Task 3 has created it, `tests/test_research_b2_signal_reading_basis.py` "a test importing cli.registry.observed").

**Goal:** B2's signal reading (spec 00140) — the chunked twin of `event_contrast` in `cli/alpha/b2.py`; one reading subject, `b2-signal-reading`, in `cli/research/subjects.py`; the data-gated test of its inputs; the loop's pick and the reading's conventions in the decisions log before the hash; the reading's one run, kept on the reading ledger and replayed; its finding, T0023, T0016 and the subject's retirement.

**Architecture:** no new module. `cli/alpha/b2.py` gains `_bootstrap_chunks`, which replays `stationary_bootstrap_indices`' draws a chunk at a time, and `event_contrast_chunked`, `event_contrast`'s rows from those draws with two far bounds after them, and the import `random`. `cli/research/subjects.py` gains one reading machinery — the constants, `_B2ReadingInputs`, `_b2_reading_inputs` (`_b2_overlay_inputs` on the funding reader, then the other three trialled readers), `_b2_reading_flags`, `_b2_reading_counts`, `_b2_reading_forwards`, `_b2_reading_metrics`, `_build_b2_signal_reading` and `_B2_READING_KEYS` — and one `SUBJECTS` entry. Nothing writes a dataset.

**Tech Stack:** Python 3.14 through uv; polars; numpy; pytest with typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`, `infra/scripts/topics-index.py`.

**Spec:** `docs/specs/00140-b2-signal-reading-design.md` — binding; D1–D9 are cited by name and the values below are copied from it. It reads spec 00138's instrument, arm A and three of its signals and spec 00139's funding reader, all frozen (records 52–56's and reading 2's `spec_hash`). **Iteration:** iter-184. **Topic:** T0023 under T0016. **Branch:** `research/iter-184-b2-signal-reading`, worktree `.claude/worktrees/iter184`, `data/ohlc-full`, `data/derivatives-funding`, `data/derivatives-oi` and `data/liquidations-daily` linked read-only from the main checkout. A choice this plan makes that the spec leaves open is marked **Author's call**. Every code fence below was cut from the files the author ran: the code and tests of Tasks 1–3 were written in this worktree and run green (`11 passed, 147 deselected` for Task 1's chunked cases and `158 passed` for its file, `15 passed, 682 deselected` for Task 2 step 6's selection, `1 passed` for Task 3's data-gated case in 163 s), their red readings taken in a detached worktree at the base (Task 1 an `ImportError` on `event_contrast_chunked` at collection, Task 2 `15 failed, 673 deselected` over Task 1's code), the gates and the cli diff measured, the slow cases timed, Task 6 step 4's retirement collected in a detached scratch worktree (no case naming the subject under `-m "not retired"`, `tests/test_retired_subjects.py` `5 passed`), Tasks 1–2's thirty-four probe rows run in a detached scratch worktree on that tree, thirty-four of thirty-four `KILLED`, and Task 4's two programs parsed and run over a synthetic ledger line in scratch; the files were then restored to the base before this plan was committed. Not run: the reading itself and its replay (Task 5), the topic edits (Task 6 steps 1–3) and the PR (Task 7).

## Global Constraints

- **The signals, tails, states and forwards** (D3–D5): `_b2_reading_inputs` runs `_b2_overlay_inputs(subject, _b2_funding_signal, 2.0, reader, dataset, window, accept_holes)` for the union, its two window refusals and arm A, then `_b2_oi_signal`, `_b2_ratio_signal` and `_b2_liq_signal` over its `h4_ts`, keyed `binperp_funding_z30d`, `binperp_oi_z30d`, `binperp_ratio_max_z30d` and `binperp_liq_long_z30d`; the tails `above` (z > 2.0) and `below` (z < −2.0) at `_B2_READING_THRESHOLD = 2.0`; the states `long` (arm A above 0) and `flat` (arm A at 0); the forwards `log(close[k + H] / close[k])` on `_ffill_btc`'s prices, H ∈ `_B2_READING_HORIZONS = (1, 6, 24)`, keyed `fwd_logret_4h`, `fwd_logret_24h` and `fwd_logret_96h`.
- **The contrast** (D6): per signal, tail and state one `event_contrast_chunked(flags, forwards, mean_block=30, n_resamples=2000, seed=42)` call at its default chunk of 10, sixteen in all; a row is `[events, others, mean after the events, mean after the others, difference, 2.5 %, 97.5 %, 0.05 %, 99.95 %]`, its first seven entries `event_contrast`'s to the bit.
- **The keys** (D7): 17 — `<signal key>_fwd_logret_<4·H>h` for each signal and horizon, `events_per_asset`, `others_per_asset`, `threshold` 2.0, `mean_block` 30, `n_resamples` 2000; the counts the measured basis's (Task 3's literals).
- **The criterion** (D8): read by Task 5's entry off the pooled rows, never by code; the subject has no rule, and no program of this plan judges a cell.
- **The hash rule** (D9): before Task 4 step 2 takes the spec's sha256, nobody computes a forward return over the real data or runs `b2-signal-reading` over the real sets; the data-gated test (Task 3) computes positions, signals, counts and the block, and no forward; no reader, reviewer or plan-review dispatch runs the subject over the real sets before the hash, and every read's dispatch carries this rule. The subject runs over the real sets once, Task 5's `--reading` run, never as a plain eval.
- **Unchanged** (D7): every existing function of `cli/alpha/b2.py` and `cli/research/subjects.py`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/validation/*`, `cli/engine/*` and `cli/liquidations/*`; the subjects of trials 1–7 and of readings 1–2; any adopted artifact. After every task, from the merge base with develop (moved to develop's tip by a merge of develop), each its own call: `git diff --name-only $(git merge-base HEAD origin/develop) -- cli/` prints `cli/alpha/b2.py` from Task 1 on and `cli/research/subjects.py` from Task 2 on, nothing else; `git diff -U0 $(git merge-base HEAD origin/develop) -- cli/ | grep -c '^-[^-]'` prints 0 — both files gain lines and lose none. Measured on the authoring tree, the hunks: `cli/alpha/b2.py`'s `@@ -3,0 +4 @@` and `@@ -425,0 +427,80 @@`; `cli/research/subjects.py`'s `@@ -61,0 +62 @@`, `@@ -2924,0 +2926,126 @@` and `@@ -3227,0 +3355,9 @@`. Code citations name a function, never a line.
- Never edit `docs/specs/00140-b2-signal-reading-design.md` after Task 4 step 2, nor specs 00128, 00137, 00138 and 00139, nor the spec before then except a fix commit a read of Task 3 step 6 asks for; never write `docs/reference/trial-registry.jsonl` or `docs/reference/reading-ledger.jsonl`, nor run `--register` or `--reading`, except where Task 5 names it — and this plan never runs `--register`. Never `git stash`; no amend; a state-changing git command runs alone, the probe setup below excepted.
- **Data**: `data/ohlc-full`, `data/derivatives-funding`, `data/derivatives-oi` and `data/liquidations-daily`, read-only links, never written under. Never `data/ohlc-holdout-*`, `/mnt/zhao-crypto/`, ssh or a fleet host, docker, `kraken-cli`, the vault, the network, a Grafana or Kraken endpoint, or `tests/test_grafana_push_sh.py`.
- **Executors**: the controller — the orchestrating session, in its own main loop, never a dispatched implementer — runs Task 3 step 6's reads, Tasks 4–5 and Task 7, since `.claude/skills/zcrypto-plan-review/references/implementer-contract.md`, carried by every task-loop dispatch, bars agent dispatches (the reads) and runs awaited in the background to a completion notification (the data test, the reading, the replay), and the steps around those runs gate, check or commit them. Every other step is an implementer dispatch under that contract: Tasks 1, 2 and 6 and Task 3's steps 1–5.
- **Tests**: every pytest run is `mkdir -p .tmp/plan-00140 && uv run pytest <file>::<test> -q -p no:cacheprovider --basetemp=.tmp/plan-00140/pt` (or a file, or `-k`). An implementer's runs are foreground: each run that can pass 120 s is one plain blocking call with the Bash tool's `timeout` at 600000 ms, and a run that could pass 600 s is split by file, node id or `-k` selection into parts that cannot, each its own `--basetemp=.tmp/plan-00140/pt-<n>`. The controller's runs that can pass 120 s each run as one Bash call with `run_in_background: true`, acted on only at that call's completion notification: no polling, no `sleep`, one such run at a time and no other command in this worktree while it lives; its output is read from its own file after the notification. Before each commit: new files staged first, then `T=$(bash infra/scripts/consumers.sh --direct <each changed path> | sort -u)` and `[ -n "$T" ] && uv run pytest $T -m "not slow and not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00140/pt`, never a bare `uv run pytest`; a slow case run on purpose takes `ZCRYPTO_RERUN_SLOW=1`. Every `T` holding `tests/test_research_command.py` runs it in three parts, each one plain blocking call under `-m "not slow and not data"`, `timeout` 600000 ms: `tests/test_research_command.py -k "not reentry"` (`--basetemp=.tmp/plan-00140/pt-1`, measured on the authoring tree, Tasks 1–2's code in it, `542 passed, 155 deselected in 435.26s`), `tests/test_research_command.py -k reentry` (`pt-2`, measured `71 passed, 626 deselected in 87.32s`) and the rest of `T` (`pt-3`). A commit message's test result line is a run over that commit's own tree.
- **Probes**: the tier is `full`, so each new guard — a test function, and each parametrised row a probe row names — is proven through its own node id with `infra/scripts/mutate-probe.sh`, before its commit and on the commit's own tree; never through a case `tests/slow-cases.txt` lists, whose commit records `probe skipped: slow case` with its node id. After the gate, with the task's files staged, as one call:

```bash
test ! -e .tmp/plan-00140/probe &&
  TREE=$(git write-tree) &&
  echo "probe tree $TREE" &&
  git worktree add --detach .tmp/plan-00140/probe HEAD &&
  git -C .tmp/plan-00140/probe read-tree -u --reset "$TREE" &&
  git -C .tmp/plan-00140/probe commit -q -m "test: probe $TREE" &&
  mkdir -p .tmp/plan-00140/probe/.tmp
```

  Then, from `.tmp/plan-00140/probe`, each row of the task's probe block, one at a time, each its own call after the previous verdict is read, every one expected to print `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Before each row, its dry run from the same directory: `sed -e '<mutation>' <file> | uv run python -c 'import ast, sys; ast.parse(sys.stdin.read())'` exits 0 and `diff <(sed -e '<mutation>' <file>) <file> | grep -c '^>'` prints 1, and the same two for the control. Every mutation substitutes and none deletes a line; every control renames a `def` the case reaches, so it fails at import or at its call. After the last verdict, `git worktree remove --force .tmp/plan-00140/probe` — a data link in it unlinked first, each removal of one that held a link followed by `ls -la /home/zhaow/Projects/zcrypto-kraken/data`, each set it linked still listed. The task's commit carries `Probed on this commit's tree, committed in a detached scratch worktree (tree <the hash the setup printed>):` and each row's command with its verdict line, `infra/scripts/mutate-probe.sh` named in both, and after the commit `test "$(git rev-parse HEAD^{tree})" = <the hash the setup printed>` passes.

## Task 1: the chunked contrast in `cli/alpha/b2.py` (D6)

**Files:** Modify `cli/alpha/b2.py`, `tests/test_alpha_b2.py`.

**Interfaces:** Produces `event_contrast_chunked(flags, forwards, *, mean_block, n_resamples, seed, chunk=10) -> dict[str, dict[str, list[float]]]` and the private generator `_bootstrap_chunks(n_obs, *, mean_block, n_resamples, seed, chunk)`; `event_contrast_chunked` refuses with `AlphaError` what it cannot pair, through the module's `_check_lengths` and `_check_paired`, and a chunk below 1, and with `stationary_bootstrap_indices`' own `ValidationError` the bootstrap arguments that function refuses.

- [ ] **Step 1: Write the failing tests** — in `tests/test_alpha_b2.py`, the `from cli.alpha.b2 import (` block gains `event_contrast_chunked,` after `event_contrast,`; `from cli.validation import stationary_bootstrap_indices` becomes `from cli.validation import ValidationError, stationary_bootstrap_indices`; and at the end of the file, after `test_event_contrast_refuses_a_forward_series_of_another_length`:

```python
# Sixteen indices and two series: ETH holds two events and two others after "ret", so that some resamples draw neither
# other, and one event after "late", which lacks its second event's forward, so the series keep different assets; DOT
# holds one event in either, LTC two events and one other, and neither series keeps them.
_CHUNKED_FLAGS = {
    "BTC": [True, False, False, True, None, False, True, False, False, False, True, False, False, True, False, False],
    "ETH": [False, None, False, None, True, None, None, None, None, None, None, True, None, None, None, None],
    "DOT": [True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    "LTC": [True, None, None, True, None, None, None, None, None, None, None, None, None, None, False, None],
}
_CHUNKED_RET = {
    "BTC": [0.03, 0.01, -0.02, 0.05, 9.0, 0.0, 0.04, 0.02, -0.01, 0.01, None, 0.0, 0.02, -0.03, 0.01, 0.0],
    "ETH": [0.01, -0.03, 0.02, 0.0, -0.02, 0.01, 9.0, -0.04, 0.03, 0.01, 0.02, -0.01, 0.0, 0.02, -0.02, 0.01],
    "DOT": [0.07, 0.01, 0.0, 0.01, 0.02, 0.0, 0.01, 0.0, 0.02, 0.01, 0.0, 0.03, 0.01, 0.0, 0.02, 0.01],
    "LTC": [0.04, 0.02, -0.01, 0.06, 0.01, 0.0, 0.03, -0.02, 0.01, 0.0, 0.02, 0.01, -0.01, 0.03, 0.05, 0.0],
}
_CHUNKED_LATE = {
    "BTC": [*_CHUNKED_RET["BTC"][1:], None],
    "ETH": [*_CHUNKED_RET["ETH"][1:12], None, *_CHUNKED_RET["ETH"][13:], None],
    "DOT": [*_CHUNKED_RET["DOT"][1:], None],
    "LTC": [*_CHUNKED_RET["LTC"][1:], None],
}


def _far_bounds(rows: list[tuple[list, list]], draws: list[list[int]]) -> list[float]:
    """The 0.05 % and 99.95 % percentiles, by hand, of the differences over the resamples holding an event and another."""
    diffs = []
    for idx in draws:
        ev = [values[k] for flags, values in rows for k in idx if flags[k] is True and values[k] is not None]
        ot = [values[k] for flags, values in rows for k in idx if flags[k] is False and values[k] is not None]
        if ev and ot:
            diffs.append(sum(ev) / len(ev) - sum(ot) / len(ot))
    diffs.sort()
    return [_percentile(diffs, 0.0005), _percentile(diffs, 0.9995)]


@pytest.mark.parametrize("chunk", [1, 7, 10, 200, 500], ids=lambda chunk: f"chunk-{chunk}")
def test_the_chunked_contrast_is_the_event_contrasts_rows_over_the_same_resamples_each_with_its_far_bounds_after_it(chunk):
    forwards = {"ret": _CHUNKED_RET, "late": _CHUNKED_LATE}

    out = event_contrast_chunked(_CHUNKED_FLAGS, forwards, mean_block=3, n_resamples=200, seed=7, chunk=chunk)

    whole = event_contrast(_CHUNKED_FLAGS, forwards, mean_block=3, n_resamples=200, seed=7)
    assert {series: {name: row[:7] for name, row in rows.items()} for series, rows in out.items()} == whole
    assert (list(out["ret"]), list(out["late"])) == (["BTC", "ETH", "pooled"], ["BTC", "pooled"])
    draws = stationary_bootstrap_indices(16, mean_block=3, n_resamples=200, seed=7)
    for name, members in (("ETH", ["ETH"]), ("pooled", ["BTC", "ETH"])):
        rows = [(_CHUNKED_FLAGS[a], _CHUNKED_RET[a]) for a in members]
        assert out["ret"][name][7:] == pytest.approx(_far_bounds(rows, draws)), name


@pytest.mark.parametrize(
    ("change", "error", "match"),
    [
        pytest.param({"chunk": 0}, AlphaError, "chunk must be an int >= 1, got 0", id="chunk-0"),
        pytest.param({"chunk": True}, AlphaError, "chunk must be an int >= 1, got True", id="chunk-bool"),
        pytest.param({"n_resamples": 0}, ValidationError, "n_resamples must be an int >= 1, got 0", id="no-resample"),
        pytest.param({"mean_block": 0.5}, ValidationError, "mean_block must be finite and >= 1, got 0.5", id="block-under-1"),
        pytest.param({"flags": {"BTC": []}, "forwards": {}}, ValidationError, "n_obs must be an int >= 1, got 0", id="no-index"),
        pytest.param(
            {"forwards": {"ret": {"BTC": [0.1, 0.2]}}},
            AlphaError,
            re.escape("forwards['ret']['BTC'] has length 2, expected 3"),
            id="forward-length",
        ),
    ],
)
def test_the_chunked_contrast_refuses_what_the_event_contrast_refuses_and_a_chunk_below_1(change, error, match):
    arguments = {"flags": {"BTC": [True, False, True]}, "forwards": {"ret": {"BTC": [0.1, 0.2, 0.3]}}}
    arguments |= {"mean_block": 2, "n_resamples": 10, "seed": 1} | change
    with pytest.raises(error, match=match):
        event_contrast_chunked(**arguments)
    if "chunk" not in change:
        with pytest.raises(error, match=match):
            event_contrast(**arguments)
```

- [ ] **Step 2: Run them to verify they fail** — `uv run pytest tests/test_alpha_b2.py -q -p no:cacheprovider --basetemp=.tmp/plan-00140/pt`: an `ImportError` on `event_contrast_chunked`, collection stopping.
- [ ] **Step 3: Implement** — in `cli/alpha/b2.py`, `import random` after `import math`, and after `event_contrast` and before `_check_lengths`:

```python
def _bootstrap_chunks(n_obs: int, *, mean_block: float, n_resamples: int, seed: int, chunk: int):
    """`stationary_bootstrap_indices`' resamples, `chunk` at a time as the rows of an index array: its generator's calls,
    in its order, from the same seed."""
    rng = random.Random(seed)
    p = 1 / mean_block
    for first in range(0, n_resamples, chunk):
        rows = np.empty((min(chunk, n_resamples - first), n_obs), dtype=np.int64)
        for row in rows:
            idx = [rng.randrange(n_obs)]
            for _ in range(n_obs - 1):
                idx.append(rng.randrange(n_obs) if rng.random() < p else (idx[-1] + 1) % n_obs)
            row[:] = idx
        yield rows


def event_contrast_chunked(
    flags: dict[str, list[bool | None]],
    forwards: dict[str, dict[str, list[float | None]]],
    *,
    mean_block: float,
    n_resamples: int,
    seed: int,
    chunk: int = 10,
) -> dict[str, dict[str, list[float]]]:
    """`event_contrast`'s rows over the same resamples, drawn and read `chunk` at a time so that memory holds `chunk` of
    them and never all, each row followed by its 0.05 % and 99.95 % bounds (docs/specs/00140 D6)."""
    n = _check_lengths({f"flags[{asset!r}]": values for asset, values in flags.items()})
    for series, by_asset in forwards.items():
        _check_paired("flags", flags, f"forwards[{series!r}]", by_asset, n)
    if not isinstance(chunk, int) or isinstance(chunk, bool) or chunk < 1:
        raise AlphaError(f"chunk must be an int >= 1, got {chunk!r}")
    # `stationary_bootstrap_indices`' own refusals of the arguments the draw shares with it: the index count's at the cost of
    # one resample of every index, the others' at the cost of n_resamples resamples of one index.
    stationary_bootstrap_indices(n, mean_block=1, n_resamples=1, seed=seed)
    stationary_bootstrap_indices(1, mean_block=mean_block, n_resamples=n_resamples, seed=seed)
    kept = {}
    for series, by_asset in forwards.items():
        for asset, flag in flags.items():
            values = by_asset[asset]
            event = np.array([f is True and v is not None for f, v in zip(flag, values)])
            other = np.array([f is False and v is not None for f, v in zip(flag, values)])
            if event.sum() >= 2 and other.sum() >= 2:
                kept[series, asset] = (event, other, np.array([0.0 if v is None else v for v in values]))
    counts = {key: np.empty((2, n_resamples), dtype=np.int64) for key in kept}
    sums = {key: np.empty((2, n_resamples)) for key in kept}
    first = 0
    for draws in _bootstrap_chunks(n, mean_block=mean_block, n_resamples=n_resamples, seed=seed, chunk=chunk):
        last = first + len(draws)
        for key, (event, other, x) in kept.items():
            e, o, v = event[draws], other[draws], x[draws]
            counts[key][:, first:last] = e.sum(axis=1), o.sum(axis=1)
            sums[key][:, first:last] = (v * e).sum(axis=1), (v * o).sum(axis=1)
        first = last
    out: dict[str, dict[str, list[float]]] = {}
    for series in forwards:
        assets = [asset for asset in flags if (series, asset) in kept]
        rows = {}
        for name, members in [*((asset, [asset]) for asset in assets), ("pooled", assets)]:
            if not members:
                continue
            read = [kept[series, asset] for asset in members]
            n_event = sum(int(event.sum()) for event, _, _ in read)
            n_other = sum(int(other.sum()) for _, other, _ in read)
            mean_event = sum(float(x[event].sum()) for event, _, x in read) / n_event
            mean_other = sum(float(x[other].sum()) for _, other, x in read) / n_other
            boot_events = sum(counts[series, asset][0] for asset in members)
            boot_others = sum(counts[series, asset][1] for asset in members)
            usable = (boot_events > 0) & (boot_others > 0)
            if not usable.any():
                continue
            boot_event_means = sum(sums[series, asset][0] for asset in members)[usable] / boot_events[usable]
            boot_other_means = sum(sums[series, asset][1] for asset in members)[usable] / boot_others[usable]
            low, high = np.percentile(boot_event_means - boot_other_means, [2.5, 97.5])
            far_low, far_high = np.percentile(boot_event_means - boot_other_means, [0.05, 99.95])
            diff = mean_event - mean_other
            rows[name] = [n_event, n_other, mean_event, mean_other, diff, float(low), float(high), float(far_low), float(far_high)]
        out[series] = rows
    return out
```

- [ ] **Step 4: Run them to verify they pass** — `uv run pytest tests/test_alpha_b2.py -k chunked -q -p no:cacheprovider --basetemp=.tmp/plan-00140/pt` (measured `11 passed, 147 deselected`), then the whole file (measured `158 passed`).
- [ ] **Step 5: Stage, consumers, gate** — `git add cli/alpha/b2.py tests/test_alpha_b2.py`; the Global Constraints' `T` over the two paths in its three parts (the rest of `T`, the other seven direct readers, measured `200 passed, 11 deselected in 2.59s`); `uv run pre-commit run -a` until clean, its rewrites staged; the Unchanged checks.
- [ ] **Step 6: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED`:

```bash
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation 's/else (idx\[-1\] + 1) % n_obs)/else idx[-1] % n_obs)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_is_the_event_contrasts_rows_over_the_same_resamples_each_with_its_far_bounds_after_it[chunk-7]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation 's/rows = np\.empty((min(chunk, n_resamples - first), n_obs), dtype=np\.int64)/rows = np.empty((chunk, n_obs), dtype=np.int64)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_is_the_event_contrasts_rows_over_the_same_resamples_each_with_its_far_bounds_after_it[chunk-7]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation 's/^    p = 1 \/ mean_block$/    p = 1 \/ (mean_block + 1)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_is_the_event_contrasts_rows_over_the_same_resamples_each_with_its_far_bounds_after_it[chunk-1]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation 's/^        first = last$/        first = last - 1/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_is_the_event_contrasts_rows_over_the_same_resamples_each_with_its_far_bounds_after_it[chunk-7]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation 's/counts\[key\]\[:, first:last\] = e\.sum(axis=1), o\.sum(axis=1)/counts[key][:, first:last] = o.sum(axis=1), e.sum(axis=1)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_is_the_event_contrasts_rows_over_the_same_resamples_each_with_its_far_bounds_after_it[chunk-10]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation 's/sums\[key\]\[:, first:last\] = (v \* e)\.sum(axis=1), (v \* o)\.sum(axis=1)/sums[key][:, first:last] = (v * o).sum(axis=1), (v * e).sum(axis=1)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_is_the_event_contrasts_rows_over_the_same_resamples_each_with_its_far_bounds_after_it[chunk-10]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation '/^def event_contrast_chunked(/,/^def /s/            if event.sum() >= 2 and other.sum() >= 2:/            if event.sum() >= 1 and other.sum() >= 2:/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_is_the_event_contrasts_rows_over_the_same_resamples_each_with_its_far_bounds_after_it[chunk-200]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation 's/\[0\.05, 99\.95\])/[0.5, 99.5])/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_is_the_event_contrasts_rows_over_the_same_resamples_each_with_its_far_bounds_after_it[chunk-500]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation 's/ or isinstance(chunk, bool) or chunk < 1:$/ or isinstance(chunk, bool) or chunk < 0:/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_refuses_what_the_event_contrast_refuses_and_a_chunk_below_1[chunk-0]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation 's/ or isinstance(chunk, bool) or chunk < 1:$/ or isinstance(chunk, str) or chunk < 1:/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_refuses_what_the_event_contrast_refuses_and_a_chunk_below_1[chunk-bool]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation 's/stationary_bootstrap_indices(1, mean_block=mean_block, n_resamples=n_resamples, seed=seed)/stationary_bootstrap_indices(1, mean_block=mean_block, n_resamples=1, seed=seed)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_refuses_what_the_event_contrast_refuses_and_a_chunk_below_1[no-resample]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation 's/stationary_bootstrap_indices(1, mean_block=mean_block, n_resamples=n_resamples, seed=seed)/stationary_bootstrap_indices(1, mean_block=1, n_resamples=n_resamples, seed=seed)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_refuses_what_the_event_contrast_refuses_and_a_chunk_below_1[block-under-1]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation 's/stationary_bootstrap_indices(n, mean_block=1, n_resamples=1, seed=seed)/stationary_bootstrap_indices(n + 1, mean_block=1, n_resamples=1, seed=seed)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_refuses_what_the_event_contrast_refuses_and_a_chunk_below_1[no-index]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/alpha/b2.py --control 's/^def event_contrast_chunked(/def event_contrast_chunked_gone(/' --mutation '/^def event_contrast_chunked(/,/^def /s/_check_paired("flags", flags, f"forwards\[{series!r}\]", by_asset, n)/_check_paired("flags", flags, f"forwards[{series!r}]", flags, n)/' -- uv run pytest 'tests/test_alpha_b2.py::test_the_chunked_contrast_refuses_what_the_event_contrast_refuses_and_a_chunk_below_1[forward-length]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  The known-answer test's five chunks each carry a row, and each moves a clause D6 gives the twin: the draws replayed from the seed (the `idx[-1]` and `mean_block + 1` rows), a last chunk shorter than the rest (the `np.empty((chunk, …))` row, chunk 7 against 200 resamples), the chunks' columns laid end to end (the `last - 1` row), events beside others and their sums beside each other (the two swap rows), an asset kept per series (the `>= 1` row, ETH's one event after `late`), and the far bounds (the `[0.5, 99.5]` row). Each refusal row has its own: the chunk's bound and its type, the resample count and the block — each refused once, by the second `stationary_bootstrap_indices` call alone — the index count, refused by the first alone, and the forwards' lengths.

- [ ] **Step 7: Commit** — `feat(alpha): the chunked event contrast — event_contrast's rows over the same resamples, a chunk at a time, with its far bounds`, the message carrying the test result lines, the probe block's commands and verdicts and the two trailer lines.

## Task 2: the reading subject in `cli/research/subjects.py` (D2–D7)

**Files:** Modify `cli/research/subjects.py`, `tests/test_research_command.py`, `README.md`, `tests/slow-cases.txt`.

**Interfaces:** Consumes Task 1's `event_contrast_chunked`; `cli/research/subjects.py`'s `_b2_overlay_inputs`, `_B2OverlayInputs`, `_b2_funding_signal`, `_b2_oi_signal`, `_b2_ratio_signal`, `_b2_liq_signal`, `_b2_over`, `_ffill_btc`, `_N_RESAMPLES`, `_ASSETS`, `SubjectError`, `Subject` and the names it imports, each called through the module's name so a test's `monkeypatch.setattr(subjects, …)` reaches it; in the tests, `_anchor`, `_rolling_set`, `_not_parquet`, `_b2_reentry_dataset`, `_B2_START`, `_B2_ASSETS`, `_B2_SPOILT` and `_CONTRACT_DATASETS`. Produces the subject, `_B2ReadingInputs`, `_b2_reading_inputs` and `_b2_reading_counts`, which Task 3's data-gated test imports.

- [ ] **Step 1: Write the failing tests** — in `tests/test_research_command.py`:
  - `test_each_subject_declares_the_metric_keys_its_build_returns` gains, as its last line, `    assert subjects.SUBJECTS["b2-signal-reading"].metric_keys == _B2_READING_SPEC_KEYS`;
  - after `test_each_b2_reentry_reads_its_signal_off_its_own_columns` and before `def _ruled_signal(`:

```python
_B2_READING_SPEC = "docs/specs/00140-b2-signal-reading-design.md"
# Spec 00140's four signals, in the order its keys and its contrasts take them, typed from the spec, never read off the
# subject.
_B2_READING_SIGNAL_KEYS = ("binperp_funding_z30d", "binperp_oi_z30d", "binperp_ratio_max_z30d", "binperp_liq_long_z30d")
_B2_READING_SPEC_KEYS = frozenset(
    {
        *(f"{key}_fwd_logret_{hours}h" for key in _B2_READING_SIGNAL_KEYS for hours in (4, 24, 96)),
        "events_per_asset",
        "others_per_asset",
        "threshold",
        "mean_block",
        "n_resamples",
    }
)


def test_the_signal_reading_declares_the_4h_grid_its_keys_and_no_rule():
    reading = subjects.SUBJECTS["b2-signal-reading"]
    assert (reading.name, reading.intervals, reading.assets, reading.spec, reading.seeds) == (
        "b2-signal-reading",
        (240,),
        _B2_ASSETS,
        _B2_READING_SPEC,
        (42,),
    )
    assert reading.build is subjects._build_b2_signal_reading and reading.metric_keys == _B2_READING_SPEC_KEYS
    assert (reading.verdict, reading.no_verdict, reading.incumbent, reading.family, reading.n_trials) == (None,) * 5


def test_the_signal_readings_inputs_are_the_overlays_union_and_arm_a_and_each_trials_signal_by_its_own_reader(monkeypatch):
    calls = []
    overlay = subjects._B2OverlayInputs(["ts"], {"BTC": [1.0]}, ["close"], {"BTC": [0.0]}, {"BTC": [-3.0]}, {"BTC": [1.0]}, 2.0)
    monkeypatch.setattr(subjects, "_b2_overlay_inputs", lambda *arguments: calls.append(arguments) or overlay)
    readers = ("_b2_funding_signal", "_b2_oi_signal", "_b2_ratio_signal", "_b2_liq_signal")
    for name in readers:
        monkeypatch.setattr(subjects, name, lambda reader, h4_ts, name=name: calls.append((name, reader, h4_ts)) or name)
    reader, window = object(), ("2024-01-01", "2024-06-30")

    inputs = subjects._b2_reading_inputs("b2-signal-reading", reader, "ohlc-test", window, True)

    assert calls == [
        ("b2-signal-reading", subjects._b2_funding_signal, 2.0, reader, "ohlc-test", window, True),
        *((name, reader, ["ts"]) for name in readers[1:]),
    ]
    signals = dict(zip(_B2_READING_SIGNAL_KEYS, (overlay.signal, *readers[1:])))
    assert inputs == subjects._B2ReadingInputs(overlay.h4_ts, overlay.h4_prices, overlay.close, overlay.arm_a, signals)


# Arm A long at 0-2 and 6, flat at 3-5 and 7; the signal past +2 at 0 and 3, past -2 at 1 and 4, on the thresholds
# themselves at 2 and 5, and read at neither 6 nor 7.
_READING_ARM_A = {"BTC": [0.3, 0.2, 0.4, 0.0, 0.0, 0.0, 0.1, 0.0]}
_READING_SIGNAL = {"BTC": [2.5, -2.5, 2.0, 3.0, -3.0, -2.0, None, None]}


@pytest.mark.parametrize(
    ("tail", "state", "expected"),
    [
        pytest.param("above", "long", [True, False, False, None, None, None, None, None], id="above-long"),
        pytest.param("above", "flat", [None, None, None, True, False, False, None, None], id="above-flat"),
        pytest.param("below", "long", [False, True, False, None, None, None, None, None], id="below-long"),
        pytest.param("below", "flat", [None, None, None, False, True, False, None, None], id="below-flat"),
    ],
)
def test_a_reading_flag_is_an_event_past_its_tail_in_its_state_another_read_close_in_it_and_none_elsewhere(tail, state, expected):
    assert subjects._b2_reading_flags(_READING_SIGNAL, _READING_ARM_A, tail, state) == {"BTC": expected}


def test_the_reading_counts_each_assets_events_and_others_per_signal_tail_and_state():
    arm_a = _READING_ARM_A | {"ETH": [0.0] * 8}
    signal = _READING_SIGNAL | {"ETH": [None, 2.5, 2.5, -2.5, 0.0, 0.0, 0.0, 0.0]}
    inputs = subjects._B2ReadingInputs([], {}, [], arm_a, {"binperp_oi_z30d": signal})

    counts = subjects._b2_reading_counts(inputs)

    assert counts == {
        "events_per_asset": {
            "binperp_oi_z30d": {
                "above": {"long": {"BTC": 1, "ETH": 0}, "flat": {"BTC": 1, "ETH": 2}},
                "below": {"long": {"BTC": 1, "ETH": 0}, "flat": {"BTC": 1, "ETH": 1}},
            }
        },
        "others_per_asset": {
            "binperp_oi_z30d": {
                "above": {"long": {"BTC": 2, "ETH": 0}, "flat": {"BTC": 2, "ETH": 5}},
                "below": {"long": {"BTC": 2, "ETH": 0}, "flat": {"BTC": 2, "ETH": 6}},
            }
        },
    }


def test_the_reading_forwards_are_the_log_return_from_close_k_to_the_close_h_indices_on_over_the_arms_filled_prices():
    # BTC misses its third close, which the arms' BTC fill bridges; ETH misses its fifth, which no fill bridges. Each asset
    # grows at its own rate, so no asset's forwards are another's.
    prices = {a: [100.0 * (1 + 0.01 * i) * (1.003 + 0.001 * i) ** k for k in range(30)] for i, a in enumerate(_B2_ASSETS)}
    prices["BTC"][2] = prices["ETH"][4] = None

    forwards = subjects._b2_reading_forwards(prices)

    assert sorted(forwards) == ["fwd_logret_24h", "fwd_logret_4h", "fwd_logret_96h"]
    assert {len(values) for series in forwards.values() for values in series.values()} == {29}
    btc, eth, sol = (forwards["fwd_logret_4h"][a] for a in ("BTC", "ETH", "SOL"))
    assert (btc[1], btc[2]) == (0.0, math.log(prices["BTC"][3] / prices["BTC"][1]))
    assert eth[2:6] == [math.log(prices["ETH"][3] / prices["ETH"][2]), None, None, math.log(prices["ETH"][6] / prices["ETH"][5])]
    assert sol == pytest.approx([math.log1p(r) for r in subjects._b2_returns(prices)["SOL"]], rel=1e-12)
    day, days = forwards["fwd_logret_24h"]["SOL"], forwards["fwd_logret_96h"]["SOL"]
    assert (day[23], day[24:]) == (math.log(prices["SOL"][29] / prices["SOL"][23]), [None] * 5)
    assert (days[5], days[6:]) == (math.log(prices["SOL"][29] / prices["SOL"][5]), [None] * 23)


def test_the_signal_reading_hands_each_signal_tail_and_state_to_the_chunked_contrast_and_keys_its_rows(monkeypatch):
    # Thirty closes on every asset, arm A long at the even indices, each signal read from its own index and swinging
    # through both tails.
    prices = {a: [100.0 * (1 + 0.01 * i) * 1.003**k for k in range(30)] for i, a in enumerate(_B2_ASSETS)}
    arm_a = {a: [0.1 if k % 2 == 0 else 0.0 for k in range(29)] for a in _B2_ASSETS}
    signals = {
        key: {a: [None if k < j else 3.0 * math.sin(k + i + j) for k in range(29)] for i, a in enumerate(_B2_ASSETS)}
        for j, key in enumerate(_B2_READING_SIGNAL_KEYS)
    }
    inputs = subjects._B2ReadingInputs([], prices, [], arm_a, signals)
    calls = []

    def contrast(flags, forwards, **kwargs):
        calls.append((flags, forwards, kwargs))
        return {series: {"pooled": [len(calls), index]} for index, series in enumerate(forwards)}

    monkeypatch.setattr(subjects, "event_contrast_chunked", contrast)

    metrics = subjects._b2_reading_metrics(inputs)

    forwards = subjects._b2_reading_forwards(inputs.h4_prices)
    cells = [(key, tail, state) for key in _B2_READING_SIGNAL_KEYS for tail in ("above", "below") for state in ("long", "flat")]
    assert calls == [
        (
            subjects._b2_reading_flags(inputs.signals[key], inputs.arm_a, tail, state),
            forwards,
            {"mean_block": 30, "n_resamples": 2000, "seed": 42},
        )
        for key, tail, state in cells
    ]
    for call, (key, tail, state) in enumerate(cells, start=1):
        for index, hours in enumerate((4, 24, 96)):
            assert metrics[f"{key}_fwd_logret_{hours}h"][tail][state] == {"pooled": [call, index]}
    assert set(metrics) == _B2_READING_SPEC_KEYS
    assert (metrics["threshold"], metrics["mean_block"], metrics["n_resamples"]) == (2.0, 30, 2000)
    counts = subjects._b2_reading_counts(inputs)
    assert (metrics["events_per_asset"], metrics["others_per_asset"]) == (counts["events_per_asset"], counts["others_per_asset"])


def test_the_signal_reading_refuses_as_of_before_any_read(tmp_path, monkeypatch):
    _anchor(monkeypatch, _rolling_set(tmp_path))

    def read(*args, **kwargs):
        raise AssertionError("the reading read a series before refusing --as-of")

    monkeypatch.setattr(subjects, "_capturing_union", read)
    args = ["research", "eval", "--subject", "b2-signal-reading", "--dataset", "ohlc-rolling", "--as-of", "2026-10-03"]

    result = runner.invoke(app, args)

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert (
        "b2-signal-reading evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a "
        "frozen --dataset"
    ) in result.output


@pytest.mark.parametrize(
    ("relpath", "spoil", "cause"),
    [
        pytest.param(f"derivatives-funding/{_B2_SPOILT}/funding.parquet", _not_parquet, "File out of specification", id="funding"),
        pytest.param(f"derivatives-oi/{_B2_SPOILT}/oi.parquet", _not_parquet, "File out of specification", id="oi"),
        pytest.param(
            f"derivatives-oi/{_B2_SPOILT}/oi.parquet",
            lambda path: pl.read_parquet(path).drop("count_long_short_ratio").write_parquet(path),
            '"count_long_short_ratio" not found',
            id="ratio",
        ),
        pytest.param("liquidations-daily/SOL/daily.parquet", _not_parquet, "File out of specification", id="liquidations-daily"),
    ],
)
def test_the_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it(tmp_path, monkeypatch, relpath, spoil, cause):
    root = _b2_reentry_dataset(tmp_path)
    spoil(root / relpath)
    _anchor(monkeypatch, root)

    result = runner.invoke(app, ["research", "eval", "--subject", "b2-signal-reading", "--dataset", "ohlc-test"])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert f"{relpath}: " in result.output and cause in result.output
```

  - `_CONTRACT_DATASETS` gains, after its `"b2-funding-reentry-preflight"` entry, `    "b2-signal-reading": lambda tmp_path, subject: (_b2_reentry_dataset(tmp_path), _B2_START),` — `_b2_reentry_dataset` holds all four sets the reading reads.

  **Author's call** — the inputs test proves `_b2_reading_inputs`' wiring under stand-ins for `_b2_overlay_inputs` and the four readers, since a run of the real ones over the fixture costs about 18 s and would make it a slow case no probe reaches; each reader's own columns are proven by the overlay and re-entry tests (`test_each_b2_overlay_reads_its_signal_off_its_own_columns`, `test_each_b2_reentry_reads_its_signal_off_its_own_columns`, retired cases CI deselects and the nightly `infra/scripts/data-gated-run.py` runs), and the file-refusal and contract rows run the real readers through the subject. The wiring test likewise runs `_b2_reading_metrics` on thirty hand-made closes under a stand-in contrast that returns a sentinel per call, so the cells' order, arguments and keys are read off the sentinels; `event_contrast_chunked` itself is Task 1's. The reading's instrument — its four readers, threshold, tails, states, horizons, block, resamples and seed — is written in this plan's code in two places, the subject's constants and calls and the tests' literals (`_B2_READING_SIGNAL_KEYS`, `_B2_READING_SPEC_KEYS`, the flags' fixture, the wiring test's arguments), Task 3's data-gated counts holding the inputs half to the measured basis; it is written in words in four more, which a read against D3–D6 alone checks: the Global Constraints' first two items, the README row (step 4), the conventions entry (Task 3 step 5) and the run's notes (Task 5 step 2).

- [ ] **Step 2: Run them to verify they fail** — `uv run pytest tests/test_research_command.py -k "signal_reading or a_reading_flag or reading_counts or reading_forwards or declares_the_metric_keys" -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00140/pt`: collection completes and every selected case fails at its call, on a name `subjects` lacks — `_b2_reading_flags`, `_B2ReadingInputs`, a key of `SUBJECTS` — or on a subject the CLI does not know (measured over Task 1's code: `15 failed, 673 deselected`).
- [ ] **Step 3: Implement in `cli/research/subjects.py`** — the `from cli.alpha.b2 import (` block gains `event_contrast_chunked,` after `event_contrast,`; after `_B2_TAPE_KEYS` and before `SUBJECTS: dict[str, Subject] = {`:

```python
# docs/specs/00140 D2-D7: B2's signal reading, the four trialled 4h-grid signals' forward returns by tail and by arm A's
# state, on a frozen set's full history; no rule, no slot.
_B2_READING_THRESHOLD = 2.0
_B2_READING_TAILS = ("above", "below")
_B2_READING_STATES = ("long", "flat")
_B2_READING_HORIZONS = (1, 6, 24)
_B2_READING_BLOCK = 30
_B2_READING_SIGNALS = ("binperp_funding_z30d", "binperp_oi_z30d", "binperp_ratio_max_z30d", "binperp_liq_long_z30d")


class _B2ReadingInputs(NamedTuple):
    h4_ts: list[datetime]
    h4_prices: dict[str, list[float | None]]
    close: list[datetime]
    arm_a: dict[str, list[float]]
    signals: dict[str, dict[str, list[float | None]]]


def _b2_reading_inputs(
    subject: str, reader: ObservedReader, dataset: str, window: tuple[str, str] | None, accept_holes: bool
) -> _B2ReadingInputs:
    """`_b2_overlay_inputs`' union, window refusals and arm A, run on trial 7's funding reader, and the other three trialled
    signals by their trials' readers over its union: no forward return (docs/specs/00140 D3, D4)."""
    overlay = _b2_overlay_inputs(subject, _b2_funding_signal, _B2_READING_THRESHOLD, reader, dataset, window, accept_holes)
    signals = {
        "binperp_funding_z30d": overlay.signal,
        "binperp_oi_z30d": _b2_oi_signal(reader, overlay.h4_ts),
        "binperp_ratio_max_z30d": _b2_ratio_signal(reader, overlay.h4_ts),
        "binperp_liq_long_z30d": _b2_liq_signal(reader, overlay.h4_ts),
    }
    return _B2ReadingInputs(overlay.h4_ts, overlay.h4_prices, overlay.close, overlay.arm_a, signals)


def _b2_reading_flags(
    signal: dict[str, list[float | None]], arm_a: dict[str, list[float]], tail: str, state: str
) -> dict[str, list[bool | None]]:
    """True where the signal is past `tail`'s threshold and arm A in `state`, False where it is defined and not past it in
    that state, None elsewhere (docs/specs/00140 D4, D6)."""
    threshold = _B2_READING_THRESHOLD
    past = {"above": lambda z: z > threshold, "below": lambda z: z < -threshold}[tail]
    held = {"long": lambda p: p > 0, "flat": lambda p: p == 0}[state]
    return {a: [None if z is None or not held(p) else past(z) for z, p in zip(zs, arm_a[a])] for a, zs in signal.items()}


def _b2_reading_counts(inputs: _B2ReadingInputs) -> dict:
    """Per signal, tail and state, each asset's events and others, read before any forward (docs/specs/00140 D7)."""
    counts: dict[str, dict] = {"events_per_asset": {}, "others_per_asset": {}}
    for key, signal in inputs.signals.items():
        events, others = counts["events_per_asset"].setdefault(key, {}), counts["others_per_asset"].setdefault(key, {})
        for tail in _B2_READING_TAILS:
            for state in _B2_READING_STATES:
                flags = _b2_reading_flags(signal, inputs.arm_a, tail, state)
                events.setdefault(tail, {})[state] = {a: flag.count(True) for a, flag in flags.items()}
                others.setdefault(tail, {})[state] = {a: flag.count(False) for a, flag in flags.items()}
    return counts


def _b2_reading_forwards(h4_prices: dict[str, list[float | None]]) -> dict[str, dict[str, list[float | None]]]:
    """Per horizon H, the log return from return index k's close to the close H indices on, over the prices the arms are
    charged on, None where either close is missing or the series ends first (docs/specs/00140 D5)."""
    fed = _ffill_btc(h4_prices)
    out: dict[str, dict[str, list[float | None]]] = {}
    for horizon in _B2_READING_HORIZONS:
        out[f"fwd_logret_{4 * horizon}h"] = {
            a: [
                None
                if k + horizon >= len(fed[a]) or fed[a][k] is None or fed[a][k + horizon] is None
                else math.log(fed[a][k + horizon] / fed[a][k])
                for k in range(len(fed[a]) - 1)
            ]
            for a in _ASSETS
        }
    return out


def _b2_reading_metrics(inputs: _B2ReadingInputs) -> dict:
    forwards = _b2_reading_forwards(inputs.h4_prices)
    contrast: dict[str, dict] = {}
    for key, signal in inputs.signals.items():
        for tail in _B2_READING_TAILS:
            for state in _B2_READING_STATES:
                flags = _b2_reading_flags(signal, inputs.arm_a, tail, state)
                rows = event_contrast_chunked(flags, forwards, mean_block=_B2_READING_BLOCK, n_resamples=_N_RESAMPLES, seed=42)
                for series, by_name in rows.items():
                    contrast.setdefault(f"{key}_{series}", {}).setdefault(tail, {})[state] = by_name
    return {
        **contrast,
        **_b2_reading_counts(inputs),
        "threshold": _B2_READING_THRESHOLD,
        "mean_block": _B2_READING_BLOCK,
        "n_resamples": _N_RESAMPLES,
    }


def _build_b2_signal_reading(
    reader: ObservedReader,
    dataset: str,
    window: tuple[str, str] | None,
    as_of: str | None = None,
    accept_holes: bool = False,
) -> dict:
    subject = "b2-signal-reading"
    if as_of is not None:
        raise SubjectError(
            f"{subject} evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a "
            "frozen --dataset"
        )
    try:
        return _b2_reading_metrics(_b2_reading_inputs(subject, reader, dataset, window, accept_holes))
    except (AlphaError, BacktestError, BenchmarkError, FeatureError, ValidationError) as exc:
        raise SubjectError(f"{_b2_over(subject, window)}: {exc}") from exc


# docs/specs/00140 D7's keys of the reading.
_B2_READING_KEYS = frozenset(
    {
        *(f"{key}_fwd_logret_{4 * horizon}h" for key in _B2_READING_SIGNALS for horizon in _B2_READING_HORIZONS),
        "events_per_asset",
        "others_per_asset",
        "threshold",
        "mean_block",
        "n_resamples",
    }
)
```

  and `SUBJECTS` gains, after its `"b2-funding-reentry-preflight"` entry:

```python
    "b2-signal-reading": Subject(
        "b2-signal-reading",
        (240,),
        _ASSETS,
        _build_b2_signal_reading,
        spec="docs/specs/00140-b2-signal-reading-design.md",
        metric_keys=_B2_READING_KEYS,
        seeds=(42,),
    ),
```

- [ ] **Step 4: `README.md`** — the `research eval` `--subject` row: `` ) or `b2-funding-reentry-preflight` ( `` becomes `` ), `b2-funding-reentry-preflight` ( ``, and the row's closing `` `--reading`). | `` becomes:

```markdown
`--reading`) or `b2-signal-reading` (a reading rather than a comparison: per asset and pooled, the forward 4-, 24- and 96-hour log returns after a 4h close at which one of the four crowding signals the B2 comparisons read — the funding, open-interest, long/short-ratio and daily long-side liquidation z-scores — lies above 2 or below -2, against the closes at which it does not, split by whether the A2 4h ensemble holds the asset or holds it flat, with stationary-bootstrap bounds; the 4h series of `--dataset`, a frozen set only, and the `derivatives-funding`, `derivatives-oi` and `liquidations-daily` sets read whole; it has no rule, so its run is kept with `--reading`). |
```

- [ ] **Step 5: `tests/slow-cases.txt`** — gains at their `sorted()` places the cases measured at 10 s or more on the authoring tree (setup counted with the call; the evaluate and shared-default rows are the existing tests' new rows): the file refusal's `ratio` row 16.4 s and `liquidations-daily` row 18.3 s, the evaluate row 24.7 s and the shared-default row 48.7 s:

```text
tests/test_research_command.py::test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit[b2-signal-reading-evaluates]
tests/test_research_command.py::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b2-signal-reading]
tests/test_research_command.py::test_the_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it[liquidations-daily]
tests/test_research_command.py::test_the_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it[ratio]
```

  A case that times at 10 s or more on the implementer's own run and is not listed joins the list; a listed one under 10 s stays (`tests/test_slow_cases.py` passes).
- [ ] **Step 6: Run them to verify they pass** — step 2's command, one plain blocking call, `timeout` 600000 ms (measured `15 passed, 682 deselected in 44.68s`).
- [ ] **Step 7: Stage, consumers, gate** — `git add cli/research/subjects.py tests/test_research_command.py README.md tests/slow-cases.txt`; the Global Constraints' `T` over the four paths in its three parts (the rest of `T`, the other thirty-two direct readers, measured `4114 passed, 54 deselected in 120.19s`); `uv run pre-commit run -a` until clean; the Unchanged checks.
- [ ] **Step 8: Probes** — on the staged tree, in the probe worktree, each row expected `KILLED`; the metric-keys line, the contract, shared-default and tracked-spec rows are new rows of existing tests, not new guards, and are not probed; the slow cases each recorded `probe skipped: slow case`:

```bash
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_signal_reading(/def _build_b2_signal_reading_gone(/' --mutation 's/^_B2_READING_HORIZONS = (1, 6, 24)$/_B2_READING_HORIZONS = (1, 6, 12)/' -- uv run pytest tests/test_research_command.py::test_the_signal_reading_declares_the_4h_grid_its_keys_and_no_rule -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_signal_reading(/def _build_b2_signal_reading_gone(/' --mutation '/^    "b2-signal-reading": Subject(/,/^    ),$/s/        seeds=(42,),/        seeds=(42, 7),/' -- uv run pytest tests/test_research_command.py::test_the_signal_reading_declares_the_4h_grid_its_keys_and_no_rule -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_inputs(/def _b2_reading_inputs_gone(/' --mutation 's/    overlay = _b2_overlay_inputs(subject, _b2_funding_signal, /    overlay = _b2_overlay_inputs(subject, _b2_liq_signal, /' -- uv run pytest tests/test_research_command.py::test_the_signal_readings_inputs_are_the_overlays_union_and_arm_a_and_each_trials_signal_by_its_own_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_inputs(/def _b2_reading_inputs_gone(/' --mutation '/^def _b2_reading_inputs(/,/^def /s/        "binperp_oi_z30d": _b2_oi_signal(reader, overlay\.h4_ts),/        "binperp_oi_z30d": _b2_ratio_signal(reader, overlay.h4_ts),/' -- uv run pytest tests/test_research_command.py::test_the_signal_readings_inputs_are_the_overlays_union_and_arm_a_and_each_trials_signal_by_its_own_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_inputs(/def _b2_reading_inputs_gone(/' --mutation '/^def _b2_reading_inputs(/,/^def /s/        "binperp_liq_long_z30d": _b2_liq_signal(reader, overlay\.h4_ts),/        "binperp_liq_long_z30d": _b2_oi_signal(reader, overlay.h4_ts),/' -- uv run pytest tests/test_research_command.py::test_the_signal_readings_inputs_are_the_overlays_union_and_arm_a_and_each_trials_signal_by_its_own_reader -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_flags(/def _b2_reading_flags_gone(/' --mutation 's/"above": lambda z: z > threshold/"above": lambda z: z >= threshold/' -- uv run pytest 'tests/test_research_command.py::test_a_reading_flag_is_an_event_past_its_tail_in_its_state_another_read_close_in_it_and_none_elsewhere[above-long]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_flags(/def _b2_reading_flags_gone(/' --mutation 's/"below": lambda z: z < -threshold/"below": lambda z: z <= -threshold/' -- uv run pytest 'tests/test_research_command.py::test_a_reading_flag_is_an_event_past_its_tail_in_its_state_another_read_close_in_it_and_none_elsewhere[below-flat]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_flags(/def _b2_reading_flags_gone(/' --mutation 's/"long": lambda p: p > 0,/"long": lambda p: p >= 0,/' -- uv run pytest 'tests/test_research_command.py::test_a_reading_flag_is_an_event_past_its_tail_in_its_state_another_read_close_in_it_and_none_elsewhere[below-long]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_flags(/def _b2_reading_flags_gone(/' --mutation 's/"flat": lambda p: p == 0}/"flat": lambda p: p >= 0}/' -- uv run pytest 'tests/test_research_command.py::test_a_reading_flag_is_an_event_past_its_tail_in_its_state_another_read_close_in_it_and_none_elsewhere[above-flat]' -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_counts(/def _b2_reading_counts_gone(/' --mutation 's/events\.setdefault(tail, {})\[state\] = {a: flag\.count(True)/events.setdefault(tail, {})[state] = {a: flag.count(False)/' -- uv run pytest tests/test_research_command.py::test_the_reading_counts_each_assets_events_and_others_per_signal_tail_and_state -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_forwards(/def _b2_reading_forwards_gone(/' --mutation '/^def _b2_reading_forwards(/,/^def /s/    fed = _ffill_btc(h4_prices)/    fed = dict(h4_prices)/' -- uv run pytest tests/test_research_command.py::test_the_reading_forwards_are_the_log_return_from_close_k_to_the_close_h_indices_on_over_the_arms_filled_prices -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_forwards(/def _b2_reading_forwards_gone(/' --mutation 's/                else math\.log(fed\[a\]\[k + horizon\] \/ fed\[a\]\[k\])/                else math.log(fed[a][k + horizon - 1] \/ fed[a][k])/' -- uv run pytest tests/test_research_command.py::test_the_reading_forwards_are_the_log_return_from_close_k_to_the_close_h_indices_on_over_the_arms_filled_prices -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_forwards(/def _b2_reading_forwards_gone(/' --mutation '/^def _b2_reading_forwards(/,/^def /s/        out\[f"fwd_logret_{4 \* horizon}h"\] = {/        out[f"fwd_logret_{horizon}h"] = {/' -- uv run pytest tests/test_research_command.py::test_the_reading_forwards_are_the_log_return_from_close_k_to_the_close_h_indices_on_over_the_arms_filled_prices -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_forwards(/def _b2_reading_forwards_gone(/' --mutation 's/                if k + horizon >= len(fed\[a\]) or/                if k + horizon > len(fed[a]) or/' -- uv run pytest tests/test_research_command.py::test_the_reading_forwards_are_the_log_return_from_close_k_to_the_close_h_indices_on_over_the_arms_filled_prices -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_metrics(/def _b2_reading_metrics_gone(/' --mutation 's/^_B2_READING_BLOCK = 30$/_B2_READING_BLOCK = 24/' -- uv run pytest tests/test_research_command.py::test_the_signal_reading_hands_each_signal_tail_and_state_to_the_chunked_contrast_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_metrics(/def _b2_reading_metrics_gone(/' --mutation 's/mean_block=_B2_READING_BLOCK, n_resamples=_N_RESAMPLES, seed=42)/mean_block=_B2_READING_BLOCK, n_resamples=_N_RESAMPLES, seed=7)/' -- uv run pytest tests/test_research_command.py::test_the_signal_reading_hands_each_signal_tail_and_state_to_the_chunked_contrast_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_metrics(/def _b2_reading_metrics_gone(/' --mutation '/^def _b2_reading_metrics(/,/^def /s/contrast\.setdefault(f"{key}_{series}", {})\.setdefault(tail, {})\[state\] = by_name/contrast.setdefault(f"{key}_{series}", {}).setdefault(state, {})[tail] = by_name/' -- uv run pytest tests/test_research_command.py::test_the_signal_reading_hands_each_signal_tail_and_state_to_the_chunked_contrast_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _b2_reading_metrics(/def _b2_reading_metrics_gone(/' --mutation 's/^_B2_READING_THRESHOLD = 2\.0$/_B2_READING_THRESHOLD = 2.5/' -- uv run pytest tests/test_research_command.py::test_the_signal_reading_hands_each_signal_tail_and_state_to_the_chunked_contrast_and_keys_its_rows -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_signal_reading(/def _build_b2_signal_reading_gone(/' --mutation '/^def _build_b2_signal_reading(/,/^def /s/    if as_of is not None:/    if as_of is None:/' -- uv run pytest tests/test_research_command.py::test_the_signal_reading_refuses_as_of_before_any_read -q -p no:cacheprovider --basetemp=.tmp/pt
infra/scripts/mutate-probe.sh --file cli/research/subjects.py --control 's/^def _build_b2_signal_reading(/def _build_b2_signal_reading_gone(/' --mutation 's/    overlay = _b2_overlay_inputs(subject, _b2_funding_signal, /    overlay = _b2_overlay_inputs(subject, _b2_liq_signal, /' -- uv run pytest 'tests/test_research_command.py::test_the_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it[funding]' -q -p no:cacheprovider --basetemp=.tmp/pt
```

  The file refusal's `oi` row carries no probe: the ratio reader reads the same `oi.parquet` and refuses it with the same name and cause, so no one-line change stops the set from being read; the `funding` row's mutation is the inputs test's first. Every flag row has its own: each tail's strict comparison at the threshold itself (indices 2 and 5), and each state's own test (the long state's `>= 0` reading a flat stamp, the flat state's `>= 0` a long one).

- [ ] **Step 9: Commit** — `feat(research): B2's signal reading — the four trialled crowding signals' forward returns by tail and by arm A's state on a frozen set's full history`, the message carrying the test result lines, each probe's command and verdict, each `probe skipped: slow case` and the two trailer lines.

## Task 3: the data-gated basis test, the decisions-log entries before the hash, the reads (D1, D8, D9)

**Files:** Create `tests/test_research_b2_signal_reading_basis.py` (module-marked `data`); modify `tests/slow-cases.txt`; `docs/research/10.phase4-decisions.md` in step 5's own commit.

**Interfaces:** Consumes Task 2's `_b2_reading_inputs` and `_b2_reading_counts`; `tests.skip_gates.nothing_found_under`. Produces one test and the module names `BLOCK`, `VOUCHED`, `EVENTS`, `OTHERS` and `per_asset()`, which Task 4's check program imports. No test computes a forward return.

- [ ] **Step 1: Write the test** — every literal copied from the spec's measured basis:

```python
"""B2's signal reading's inputs against spec 00140's measured basis: the block, the signals' starts, arm A's states and
each cell's events and others; no forward return."""

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
# Per signal, the first return index every asset's signal holds, and its close.
SIGNAL_FROM = {
    "binperp_funding_z30d": (15_419, datetime(2020, 10, 22, 8, tzinfo=UTC)),
    "binperp_oi_z30d": (18_026, datetime(2021, 12, 30, 20, tzinfo=UTC)),
    "binperp_ratio_max_z30d": (20_298, datetime(2023, 1, 13, 12, tzinfo=UTC)),
    "binperp_liq_long_z30d": (19_731, datetime(2022, 10, 11, tzinfo=UTC)),
}
# Arm A's long and flat asset-stamps, and below them each cell's events and others, per asset in `subjects._ASSETS`' order.
ARM_A_LONG = (8_938, 4_680, 17_169, 6_766, 6_640, 13_428, 7_954, 11_958, 6_024, 9_905)
ARM_A_FLAT = (18_399, 22_657, 10_168, 20_571, 20_697, 13_909, 19_383, 15_379, 21_313, 17_432)
EVENTS = {
    "binperp_funding_z30d": {
        "above": {"long": (372, 164, 402, 326, 347, 454, 336, 458, 210, 417), "flat": (56, 192, 14, 48, 5, 10, 42, 68, 62, 47)},
        "below": {
            "long": (159, 115, 191, 147, 85, 141, 184, 151, 101, 141),
            "flat": (397, 347, 279, 321, 335, 305, 386, 311, 396, 357),
        },
    },
    "binperp_oi_z30d": {
        "above": {
            "long": (455, 410, 586, 771, 351, 540, 604, 515, 380, 644),
            "flat": (362, 406, 283, 103, 616, 271, 179, 212, 426, 178),
        },
        "below": {"long": (64, 88, 219, 21, 147, 64, 68, 78, 129, 58), "flat": (310, 224, 319, 359, 129, 318, 328, 332, 156, 267)},
    },
    "binperp_ratio_max_z30d": {
        "above": {
            "long": (782, 827, 1_020, 816, 865, 550, 893, 817, 875, 748),
            "flat": (327, 290, 518, 301, 303, 439, 283, 409, 252, 400),
        },
        "below": {"long": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "flat": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)},
    },
    "binperp_liq_long_z30d": {
        "above": {
            "long": (226, 301, 236, 359, 298, 239, 254, 282, 270, 278),
            "flat": (157, 172, 171, 156, 241, 169, 165, 197, 179, 154),
        },
        "below": {"long": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "flat": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)},
    },
}
OTHERS = {
    "binperp_funding_z30d": {
        "above": {
            "long": (6_936, 4_516, 7_887, 6_401, 6_286, 7_723, 7_432, 7_449, 5_789, 6_777),
            "flat": (6_036, 7_046, 5_209, 5_589, 5_480, 5_325, 5_604, 5_487, 5_680, 6_239),
        },
        "below": {
            "long": (7_149, 4_565, 8_098, 6_580, 6_548, 8_036, 7_584, 7_756, 5_898, 7_053),
            "flat": (5_695, 6_891, 4_944, 5_316, 5_150, 5_030, 5_260, 5_244, 5_346, 5_929),
        },
    },
    "binperp_oi_z30d": {
        "above": {
            "long": (3_498, 3_805, 5_892, 3_778, 3_838, 3_951, 4_016, 4_066, 4_250, 3_425),
            "flat": (4_269, 4_148, 4_364, 4_117, 3_964, 3_827, 3_970, 3_777, 3_527, 4_342),
        },
        "below": {
            "long": (3_889, 4_127, 6_259, 4_528, 4_042, 4_427, 4_552, 4_503, 4_501, 4_011),
            "flat": (4_321, 4_330, 4_328, 3_861, 4_451, 3_780, 3_821, 3_657, 3_797, 4_253),
        },
    },
    "binperp_ratio_max_z30d": {
        "above": {
            "long": (2_040, 2_367, 4_439, 2_383, 2_118, 2_656, 2_504, 2_564, 2_705, 2_395),
            "flat": (2_810, 2_655, 2_717, 2_639, 2_673, 2_314, 2_459, 2_349, 2_307, 2_596),
        },
        "below": {
            "long": (2_822, 3_194, 5_459, 3_199, 2_983, 3_206, 3_397, 3_381, 3_580, 3_143),
            "flat": (3_137, 2_945, 3_235, 2_940, 2_976, 2_753, 2_742, 2_758, 2_559, 2_996),
        },
    },
    "binperp_liq_long_z30d": {
        "above": {
            "long": (3_560, 3_583, 4_352, 3_817, 3_714, 4_020, 3_938, 3_919, 4_121, 3_565),
            "flat": (3_669, 3_382, 2_847, 3_280, 3_455, 3_178, 3_255, 3_046, 3_048, 3_609),
        },
        "below": {
            "long": (3_786, 3_884, 4_588, 4_176, 4_012, 4_259, 4_192, 4_201, 4_391, 3_843),
            "flat": (3_826, 3_554, 3_018, 3_436, 3_696, 3_347, 3_420, 3_243, 3_227, 3_763),
        },
    },
}


def per_asset(cells: dict) -> dict:
    """A cell table keyed by asset, as `_b2_reading_counts` returns it."""
    return {
        key: {
            tail: {state: dict(zip(subjects._ASSETS, counts)) for state, counts in by_state.items()}
            for tail, by_state in by_tail.items()
        }
        for key, by_tail in cells.items()
    }


def reading_inputs():
    """The reading's inputs over the real sets, with the reader that read them."""
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b2_reading_inputs("b2-signal-reading", reader, "ohlc-full", None, False)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-funding/*/funding.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-daily/*/daily.parquet"),
    reason="the frozen ohlc-full set, the derivatives-funding or derivatives-oi set or the frozen daily liquidations block is absent "
    "under data/",
)
def test_the_signal_readings_inputs_reproduce_the_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = reading_inputs()
    assert compute_hash(reader.block()) == BLOCK
    assert reader.vouched_status() == VOUCHED
    assert len(inputs.close) == _RETURN_INDICES
    for key, (index, first) in SIGNAL_FROM.items():
        signal = inputs.signals[key]
        assert next(k for k in range(_RETURN_INDICES) if all(signal[a][k] is not None for a in subjects._ASSETS)) == index, key
        assert inputs.close[index] == first, key
    assert tuple(sum(p > 0 for p in inputs.arm_a[a]) for a in subjects._ASSETS) == ARM_A_LONG
    assert tuple(sum(p == 0 for p in inputs.arm_a[a]) for a in subjects._ASSETS) == ARM_A_FLAT
    assert subjects._b2_reading_counts(inputs) == {"events_per_asset": per_asset(EVENTS), "others_per_asset": per_asset(OTHERS)}
```

- [ ] **Step 2: Run it** — with the four sets linked in this worktree: `uv run pytest tests/test_research_b2_signal_reading_basis.py --durations=5 -q -p no:cacheprovider --basetemp=.tmp/plan-00140/pt`, one plain blocking call, `timeout` 600000 ms: `1 passed`, never a skip (measured on the authoring tree, 163 s). The case joins `tests/slow-cases.txt` at its `sorted()` place:

```text
tests/test_research_b2_signal_reading_basis.py::test_the_signal_readings_inputs_reproduce_the_measured_basis
```

- [ ] **Step 3: Stage, consumers, gate** — `git add tests/test_research_b2_signal_reading_basis.py tests/slow-cases.txt`; the Global Constraints' `T` over the two paths (measured `18 passed, 1 deselected in 17.66s`); the two tree walkers its skip gate and data mark meet, `uv run pytest tests/test_live_venue_opt_in.py::test_every_skip_gate_in_tests_matches_a_form tests/test_data_gated_marker.py -m "not data" -q -p no:cacheprovider --basetemp=.tmp/plan-00140/pt` (measured `322 passed`); `uv run pre-commit run -a` until clean. No probe: the case is slow, recorded `probe skipped: slow case`.
- [ ] **Step 4: Commit** — `test(research): B2's signal reading's inputs against the measured basis — the block, the signals' starts, arm A's states and each cell's events and others`.
- [ ] **Step 5: The decisions-log entries, before the hash** — with `iteration-closeout` loaded, at the end of `docs/research/10.phase4-decisions.md`, the loop's pick (spec 00140 D1) and then **Author's call** the reading's conventions, plans 00138's and 00139's shape, so that the criterion stands in the log before any forward is read:

```markdown
[iter-184] B2's next step after trial 7 — a no-slot reading of the crowding signals' forward returns before B2's next trial, the loop's pick under the owner's run instruction, 2026-10-22 (Decision: 2)
  The owner launched an unattended run, verbatim: "continue pushing the Research strates forward, pick the most relevant tasks. override the wall clock time gate, but do not pick up new topics after 8:00Z. when closing out a research step, try the trials with potential and do not close any family too early." T0023's trigger after trials 6–7 (records 55 and 56, each rejected) named the pick of B2's next step; master plan §12 lists no touchpoint for a family's next step, so the run picked, a close excluded by the instruction. Standing and unchanged: the instrument ruling "Frozen ohlc-full (Recommended)" and the head-to-head read "From-2021 primary (Recommended)". Derived from the records' stored keys (spec 00140's measured basis), over the full window: the four de-risks lost gross return as well as net — records 51–54 gross −0.046, −0.092, −0.033 and −0.023, in per-bar return summed over 27,337 return indices — and the two re-entries gained gross return and lost it, and more, to their extra trading — records 55–56 gross +0.107 and +0.346 against extra cost 0.160 and 0.710: the signs a positive drift alone gives, which the records cannot tell from information in the signals.
  1. **A re-risk mirror trial** — raise arm A's long position to its full-long size (spec 00139's `full_long_sizes`) where a crowding signal fires and arm A is long below that size. Evidence-led on its face, since every de-risk lost return; but the de-risks' gross losses and the re-entries' gross gains carry the signs the ensemble's drift alone gives, so the mirror most likely buys drift with extra turnover, spending a slot to learn little.
  2. **A reading, no slot: the four trialled 4h-grid signals' forward-return contrast, by tail and by arm A's state** — spec 00140: per signal, tail (above 2.0, below −2.0), arm A state (long, flat) and horizon (1, 6 and 24 closes), the forward log return after the closes past the tail against the other closes in the same state, per asset and pooled with stationary-bootstrap bounds, against a pre-registered potential criterion that names the trial a cell would justify. Chosen: it spends no B slot (14 of 25 remain) and decides whether any further B2 trial has potential before one is spent, the instruction's "try the trials with potential".
  3. **Park the pick to the owner** with the decomposition — B2 open, nothing run. Cheapest; but it leaves the instruction's "try the trials with potential" unexamined.

[iter-184] B2's signal reading's conventions, pinned by spec 00140 before its hash (Decision: 1)
  The reading's details are fixed in the spec, reviewed, and frozen by its sha256, the reading's `spec_hash`, before any forward return is computed over the data; each call below is one the spec pins, the author's unless it names the ruling or the spec it carries, every value the owner or specs 00137, 00138 and 00139 fixed staying theirs.
  1. **As the spec pins them** — one reading subject, `b2-signal-reading`, with no rule, family or count, kept with `--reading` and spending no B slot, over frozen `ohlc-full`'s full history, every close a signal and a forward are read, the From-2021 read left to trials (D2); arm A by calling `_b2_overlay_inputs` itself, its states long (above 0) and flat (0) at the signal's close (D3); the four trialled signals, each by its trial's reader, and one threshold for both tails, strictly above 2.0 and below −2.0, the lower of the trials' thresholds, for power (D4); the forward log return over 1, 6 and 24 closes on the arms' BTC-filled prices (D5); per cell, the events against the other read closes in the same state, per asset and pooled, `event_contrast`'s row with its 0.05 % and 99.95 % bounds after it, one stationary-bootstrap draw at mean block 30, 2000 resamples and seed 42, through `event_contrast_chunked` at a chunk of 10, equal to `event_contrast`'s rows to the bit (D6); 17 keys and the re-entry subjects' refusals (D7); the potential criterion — the pooled 0.05 %–99.95 % bounds excluding 0, Bonferroni over 48 cells though twelve read no row, the difference at least 0.012 in size, a sign a long/flat book can act on — read by the closeout's pick and never by code, the contamination stated, a cell with potential naming its trial and none the evidence for the owner's family call (D8); one run after the hash, no plain eval before or after it (D9). Chosen.
  2. **The alternatives each weighed** — a threshold of 2.5, or each trial's own per signal; the read from 2021; the raw prices for the forwards; `event_contrast` itself, about 6 GiB at this size; a larger chunk; a Bonferroni count of 36, the cells the basis shows able to read a row; a rule over the criterion; arm A's long state split at its full-long size; a re-risk mirror trial in the reading's place (the pick above).
  Source: spec 00140 (D1–D9), its **Author's call**s and the calls it carries from the owner and specs 00137–00139; the owner's run instruction quoted in its ruling.
```

  staged alone, its gate `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/plan-00140/pt` and `uv run pre-commit run -a` until clean, committed as `docs(research): [iter-184] B2's next step after trial 7 — the loop's pick, a no-slot signal reading — and its conventions, pinned by spec 00140 before its hash`. The pick's header is what T0023's `ripe_when` greps for; Task 6 gives T0023 its next trigger.
- [ ] **Step 6 (the controller's): The reads** — the trio over the whole branch, `develop..HEAD` — the spec, this plan, Tasks 1–3 and the two entries — `pre-review`, then `review`, then over each fix range — each fix its own commit, never an amend — `pre-review` and `re-review`, within the branch's two; every `review` and `re-review` `drive` carries the hash rule as one sentence in words: nothing computes a forward return or runs the reading over the real data before the spec's hash, and the data-gated case runs with the frozen full set, the funding set, the OI set and the daily liquidation block linked into the reader's worktree and unlinked by the reader before its report, since unlinked it skips. Each report names the tip it read, the tip Task 4 step 1 diffs from. Task 4 waits until the trio has closed with no open Critical or Important.

## Task 4 (the controller's): the gate, the spec hash, the develop check, the data test and the check programs (D9)

- [ ] **Step 1: The gate** — each check its own call, each read before the next: the reads through Task 3 have closed with no open Critical or Important, and nothing changed since: `git diff --quiet <the tip the last read names> -- cli/ tests/ pyproject.toml uv.lock docs/specs/00140-b2-signal-reading-design.md docs/research/10.phase4-decisions.md` exits 0; the conventions entry against the spec at that tip, each item where the spec pins it; arm A's code path since record 56's run, `git log --oneline c83497ba3..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/derivatives cli/data uv.lock pyproject.toml .python-version`, lists Tasks 1's and 2's commits and their fixes alone (measured at the base: nothing); any other commit is named, step 4's data test deciding whether it moved the inputs.
- [ ] **Step 2: D9 (1), the spec hash** — `sha256sum docs/specs/00140-b2-signal-reading-design.md`; its value, pasted from that call, is the run's `--spec-hash` and the reading's `spec_hash`. From here nobody edits the spec.
- [ ] **Step 3: D9 (2), the develop check** — `git fetch origin develop`, then `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` exits 0. A non-zero exit stops before the run: the controller reads which line moved, the same `git diff` without `--quiet`, and only for a line another writer appended legitimately — a registry record another branch's merged PR carries; the operating model gives the reading ledger no other writer while this branch is open, so a line there stops the task, T0023's — merges develop, alone (`git merge --no-edit origin/develop`), then takes a delta read of the merge in place of re-running step 1 — `pre-review`, then `review` over `<the tip the last read names>..HEAD` and `re-review` over a fix of it within the branch's two, each `drive` carrying Task 3 step 6's sentence with its "before the spec's hash" read "before Task 5's run" — whose tip becomes the tip the last read names, and step 4 runs on the merged tree. The check has two sites, this step and Task 5 step 1, and both take this path.
- [ ] **Step 4: D9 (3), the data test on the run's tree** — `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_research_b2_signal_reading_basis.py -q -p no:cacheprovider --basetemp=.tmp/plan-00140/pt > .tmp/plan-00140/basis.out 2>&1`, one background call: `1 passed`, never a skip; a failure is an instrument finding before the run, T0023's, and the run waits.
- [ ] **Step 5: The check programs** — written once, never committed: `.tmp/plan-00140/reading_check.py`, the ledger line's checks:

```python
"""Spec 00140's reading, read off the ledger's last line against the run's print and the measured basis: exit 0 when
every check holds."""

import json
import sys
from pathlib import Path

from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_research_b2_signal_reading_basis import BLOCK, EVENTS, OTHERS, VOUCHED, per_asset

spec_hash = sys.argv[1]
r = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
out = Path(".tmp/plan-00140/b2-signal-reading.out").read_text()
printed = json.JSONDecoder().raw_decode(out, out.index("{"))[0]
invocation = {key: r["invocation"][key] for key in ("subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial")}
events, others = per_asset(EVENTS), per_asset(OTHERS)
cells = [(key, tail, state, hours) for key in EVENTS for tail in ("above", "below") for state in ("long", "flat") for hours in (4, 24, 96)]
rows = {cell: m[f"{cell[0]}_fwd_logret_{cell[3]}h"][cell[1]][cell[2]] for cell in cells}
checks = {
    "spec_hash": r["spec_hash"] == spec_hash,
    "invocation": invocation
    == {"subject": "b2-signal-reading", "dataset": "ohlc-full", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None},
    "labels": (r["iteration"], r["outcome"], r["attempt"]) == ("iter-184", None, None),
    "keys": set(m) == SUBJECTS["b2-signal-reading"].metric_keys,
    "printed": printed["metrics"] == m,
    "block": compute_hash(r["datasets"]) == r["dataset_hash"] == BLOCK and printed["vouched"] == VOUCHED,
    "constants": (m["threshold"], m["mean_block"], m["n_resamples"]) == (2.0, 30, 2000),
    "counts": (m["events_per_asset"], m["others_per_asset"]) == (events, others),
    "rows": all(len(row) == 9 for by_name in rows.values() for row in by_name.values()),
    "bounded": all(
        by_name[a][0] <= events[key][tail][state][a] and by_name[a][1] <= others[key][tail][state][a]
        for (key, tail, state, _), by_name in rows.items()
        for a in by_name
        if a != "pooled"
    ),
    "pooled": {cell for cell, by_name in rows.items() if "pooled" in by_name}
    == {cell for cell in cells if any(events[cell[0]][cell[1]][cell[2]].values())},
}
print(r["reading_id"], checks)
sys.exit(0 if all(checks.values()) else 1)
```

  and `.tmp/plan-00140/pooled_rows.py`, the print Task 5's entry reads the criterion off:

```python
"""The reading's 48 pooled cells off the ledger's last line, one a line: the signal, tail, state and horizon, then the
pooled row's events, others, difference and 0.05 % and 99.95 % bounds, or `no row`; it judges none of them."""

import json
from pathlib import Path

m = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])["metrics"]
for key in ("binperp_funding_z30d", "binperp_oi_z30d", "binperp_ratio_max_z30d", "binperp_liq_long_z30d"):
    for tail in ("above", "below"):
        for state in ("long", "flat"):
            for hours in (4, 24, 96):
                row = m[f"{key}_fwd_logret_{hours}h"][tail][state].get("pooled")
                print(key, tail, state, f"{hours}h", "no row" if row is None else [row[0], row[1], row[4], row[7], row[8]])
```

  Each is written with `cat > <path> <<'EOF'` from its fence and checked with `uv run python -c 'import ast, sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]' .tmp/plan-00140/reading_check.py .tmp/plan-00140/pooled_rows.py`.

## Task 5 (the controller's): the reading — its run, its line, its replay and its entry (D8, D9)

`<H>` is Task 4 step 2's sha256.

- [ ] **Step 1: The develop check** — Task 4 step 3 whole, its stop, its merge path and the data test after a merge with it; `git status --short` prints nothing.
- [ ] **Step 2: The run** — one run, no plain eval before or after it: `uv run zcrypto research eval --subject b2-signal-reading --dataset ohlc-full --reading --iteration iter-184 --spec-hash <H> --notes "<the notes>" > .tmp/plan-00140/b2-signal-reading.out 2>&1`, about six minutes (the spec's basis), one background call, `cat` at its notification. The notes, written before the run, name only what is fixed before it: `subject b2-signal-reading over ohlc-full, full history, no as-of; descriptive, no bar, no verdict, no B slot, changing no verdict of B2 trials 2-7; the four signals the trials read, each by its trial's reader - the 30-day funding z-score (trials 2 and 7), the 180-mark open-interest z-score (trial 3), the four long/short-ratio z-scores' maximum (trial 4), the daily long-side liquidation z-score (trials 5 and 6); per signal, tail (above 2.0, below -2.0) and arm A state at the close (long, flat), per asset and pooled: the forward 1-, 6- and 24-close log returns on the arms' prices after the closes past the tail, against the other closes where the signal is read in the same state; stationary-bootstrap 2.5/97.5 % and 0.05/99.95 % bounds of the difference, mean block 30, 2000 resamples, seed 42, one draw shared by every cell; the potential criterion - the pooled 0.05/99.95 % bounds excluding 0, the difference at least 0.012 in size, a sign a long/flat book can act on - read by the closeout's pick, never by code; pre-registered by the spec's sha256 <H>`. A refused build — exit 1 with no traceback, naming `b2-signal-reading over the full history: …` or a file of `derivatives-funding`, `derivatives-oi` or `liquidations-daily` — keeps no reading and is recorded in T0023 with its line quoted (Task 6), the reading's design standing unrun; a traceback, a signal or a ledger refusal stops the task, T0023's with the end of the run's output quoted whole.
- [ ] **Step 3: The reading's checks** — `uv run python .tmp/plan-00140/reading_check.py <H>` exits 0; a failed check stops the task before step 4.
- [ ] **Step 4: The pooled rows** — `uv run python .tmp/plan-00140/pooled_rows.py`, its 48 lines the entry's source.
- [ ] **Step 5: The records commit** — (i) at the end of `docs/research/10.phase4-decisions.md`, with `iteration-closeout` loaded, the entry `[iter-184] B2's four crowding signals read for forward returns by tail and by arm A's state on frozen ohlc-full (reading <its reading_id>)`, its header to its first `. ` holding no verdict word; the body: the subject, the set and the block `ad140b62…cf8eee1`; that the reading is descriptive, spends no slot and changes no verdict (D2, D8); for each of the criterion's three legs, the cells that meet it — signal, tail, state and horizon — read off step 4's print; the pooled row, its nine entries unrounded, read off the reading's ledger line, of every cell meeting the first leg; the cells with potential, each with the trial it names — the action on that signal past that tail, in that state, held H closes, and, where the action on that signal and tail is a rejected trial's, which — or, where none has potential, that no cell has it and that this is the evidence the owner's family call reads; the twelve cells that read no row; the caveats — the far bounds coarse at 2000 resamples, the rows counting the closes with a forward and `events_per_asset` every flagged close, and the contamination D8 states; in the form of the `[iter-182]` entry that keeps reading 2; (ii) `tests/slow-cases.txt` gains `tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-<its id>]` at its `sorted()` place, the replay rebuilding the whole reading. Then `T` over the staged paths with `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py` and `tests/test_slow_cases.py` by path; `uv run pre-commit run -a` until clean. In the probe worktree, the four sets linked into it with `ln -sn /home/zhaow/Projects/zcrypto-kraken/data/<set> .tmp/plan-00140/probe/data/<set>` and unlinked before its removal: `ZCRYPTO_RERUN_SLOW=1 uv run pytest tests/test_registry_replay.py -k 'reading-<its id>' --durations=0 -q -p no:cacheprovider --basetemp=.tmp/pt` passes, one background call, its result line and call time for the message — a difference stops the task. Commit, `git add` by path of the ledger, the decisions log and the slow-cases file, as `docs(research): B2's signal reading — the four crowding signals' forward returns on ohlc-full, kept as reading <id>; no trial spent`, the message carrying the tie tests' result line, the replay's with its call time, `probe skipped: slow case — tests/test_registry_replay.py::test_every_record_past_47_replays_at_head[reading-<id>]`, the line `The replay reads data/ohlc-full, data/derivatives-funding, data/derivatives-oi and data/liquidations-daily: re-run it with the four sets linked into the worktree (ln -sn) and unlinked before its removal; unlinked, it skips.`, and the two trailer lines. The entry adds no guard: no probe.

## Task 6: T0023, T0016, the index and the retirement of the subject (D8)

**Files:** `docs/open-topics/T0023-b2-derivatives-data-sourcing.md`, `docs/open-topics/T0016-bucket-b-c-alpha-families.md`, `docs/open-topics/README.md`, `tests/retired_subjects.py`, `tests/test_research_command.py`.

On a refused build (Task 5 step 2) no reading exists: Task 5's steps 3–5 do not run, and this task runs without a reading — step 1's Findings bullet quotes the refused line, its Done-so-far bullet names no reading, and its next-step bullet and trigger stand, the pick reading the refusal, the design unrun, where the criterion's cells would be; step 2's B2 line names the signal reading refused, with no reading id; step 4 does not run, since a later run still evaluates the subject (`tests/retired_subjects.py`'s own rule), so step 5 stages the three `docs/open-topics/` paths alone; and Task 7 step 3's body quotes the refused line in place of the pooled rows.

- [ ] **Step 1: T0023**, per `topic-ops`, every figure read off the committed reading and its entry: `## Findings so far` gains one bullet — `**B2's signal reading (iter-184, spec 00140, reading <N>).**` — in one or two sentences, the cells with potential and the trial each names, or that none has potential, pointing at its decisions-log entry for the figures; or, on a refused build, its line quoted whole from `.tmp/plan-00140/b2-signal-reading.out`; `## Done so far` gains **B2's signal reading (iter-184, spec/plan 00140)**, naming `event_contrast_chunked` in `cli/alpha/b2.py`, the subject `b2-signal-reading` and the data-gated basis test `tests/test_research_b2_signal_reading_basis.py`, and the reading by id; `## Suggested next steps` replaces `(owner) B2's next step after trials 6–7` with `(the loop's pick under a run instruction, else the owner's; a close is the owner's) B2's next step after the signal reading` — reading spec 00140's potential criterion: a trial a cell with potential names, each its own pre-registration against the shared B budget carrying D8's contamination, or, with none, the owner's family call, hold or close B2; beside the criterion the pick reads every candidate still untried, and the bullet drops none — the replaced bullet's own: a de-risk variant (scale 0.25, threshold 3.0), the de-risks' and the re-entries' further legs, a trial on the tape, and a follow-up reading 2's figures invite (the daily history reconciled with the tape, the reading at a later as-of or over a longer span, a per-side reading); and the deferrals spec 00140 makes: the re-entries' park variants (the threshold one step toward 0, the size halved), the full-long split of arm A's long state that a re-risk reads (D3), and this reading at another threshold, signal, horizon or state split, on another instrument, on the tape or at a later as-of (its Out of scope, whose other items are trials these lists and the later-trials bullet carry, this topic's live feeds, T0016's families, or constraints of this reading) — recorded as a `[iter-NNN] B2's next step after the signal reading` entry; `ripe_when`: `an activity: B2's next step after the signal reading is picked, reading spec 00140's potential criterion, recorded in the decisions log; check: grep -c -E '^\[iter-[0-9]+\] B2.s next step after the signal reading' docs/research/10.phase4-decisions.md prints at least 1`, in the frontmatter's quoting. The check is run as committed and prints 0.
- [ ] **Step 2: T0016** — its budget line's figures read off the count the bucket refusal reads, every orphan in it, `uv run python -c 'import json; from pathlib import Path; from cli.registry import attempts, budget; lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]; c = attempts.reconcile(lines, attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl")), log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF); print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])'` — the reading spends none (T0016's line reads `B1 spent 5, B2 spent 6, 14 remain` at this branch's base): the line reads `B1 spent <its B1>, B2 spent <its B2>, <its remain> remain`, each orphan it lists named on that line; its B2 line names the signal reading (iter-184, spec/plan `00140`, reading <N>), no slot spent.
- [ ] **Step 3: The index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 4: The retirement** — **Author's call**, `tests/retired_subjects.py`'s own rule: no trial still to run evaluates the reading's subject, so `RETIRED_SUBJECTS` gains `"b2-signal-reading",` after `"b2-funding-reentry-preflight",`, its comment `# B2's finished trials and the reading between them.` becoming `# B2's finished trials and the readings beside them.`; and every test function of `tests/test_research_command.py` specific to the subject and named by no parameter carries `@pytest.mark.retired` as its first decorator — all eight Task 2 adds: `test_the_signal_reading_declares_the_4h_grid_its_keys_and_no_rule`, `test_the_signal_readings_inputs_are_the_overlays_union_and_arm_a_and_each_trials_signal_by_its_own_reader`, `test_a_reading_flag_is_an_event_past_its_tail_in_its_state_another_read_close_in_it_and_none_elsewhere`, `test_the_reading_counts_each_assets_events_and_others_per_signal_tail_and_state`, `test_the_reading_forwards_are_the_log_return_from_close_k_to_the_close_h_indices_on_over_the_arms_filled_prices`, `test_the_signal_reading_hands_each_signal_tail_and_state_to_the_chunked_contrast_and_keys_its_rows`, `test_the_signal_reading_refuses_as_of_before_any_read` and `test_the_signal_reading_refuses_a_file_of_a_signals_set_it_cannot_read_naming_it`; Task 1's chunked cases test a function of `cli/alpha/b2.py` and stay. `uv run pytest tests/test_research_command.py -m "not retired" --collect-only -q -p no:cacheprovider | grep -c -E "signal.reading|reading_flag|reading_counts|reading_forwards"` prints 0 and the same under `-m retired` prints 24 (measured on the authoring tree), and `uv run pytest tests/test_retired_subjects.py -q -p no:cacheprovider --basetemp=.tmp/plan-00140/pt` passes (measured `5 passed`).
- [ ] **Step 5: Gate and commit** — `git add` the five paths; `T` over them with `tests/test_open_topics_frontmatter.py` and `tests/test_retired_subjects.py` by path, in its three parts; `uv run pre-commit run -a` until clean; committed as `docs(open-topics): T0023 and T0016 after B2's signal reading; the reading's subject retired`.

## Task 7 (the controller's): the change-index row, the read and the PR

- [ ] **Step 1: The change-index row** — through `open-pr`'s Step 4, the PR title `feat(research): iter-184 — B2 signal reading: crowding forward returns` (70 characters by `printf '%s' <it> | wc -m`, under the cap), its own commit.
- [ ] **Step 2: The read** — the `pre-review` of Tasks 5–6's commits and the row's, then `review` over `<the tip the last read covered>..HEAD`, and `re-review` over a fix of it within the branch's two, each `review` and `re-review` `drive` carrying one sentence in words: the data-gated case and the replay the messages record run with the frozen full set, the funding set, the OI set and the daily liquidation block linked into the reader's worktree and unlinked by the reader before its report, since unlinked they skip.
- [ ] **Step 3: The PR and the merge** — the consumer union `open-pr` runs as the last step before the first push, then the push, its own call; the PR through `open-pr`, its body: the reading's pooled rows as step 4 of Task 5 printed them, in a fenced block, with the cells meeting each leg of the criterion and those with potential, or none; every probe verdict line naming `infra/scripts/mutate-probe.sh`, each `probe skipped: slow case`, the explicit drop of every case the consumer union and `open-pr`'s data-gated run skipped, read off their `-rs` skip lines, and the read line naming the tip the delta's read covered. Merged through `merge-pr` under the run's licence; before it, `git status --short --ignored` read, `.tmp/plan-00140` collected and removed, and `unlink data/ohlc-full`, `unlink data/derivatives-funding`, `unlink data/derivatives-oi` and `unlink data/liquidations-daily` run in this worktree and in each reader's checkout whose `data/` holds the link; after it, `ls -la /home/zhaow/Projects/zcrypto-kraken/data` shows the four sets still there.

Decisions log: the loop's pick and the conventions entry (Task 3 step 5), before the hash; the reading's finding entry (Task 5 step 5), in its line's commit.
