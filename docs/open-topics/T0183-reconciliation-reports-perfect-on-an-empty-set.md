---
status: partial
---

# A reconciliation reports a perfect score when it compared nothing

## Context — what

A summary statistic whose empty-input branch returns the value that also means success. `cli/tick/reconcile.py`'s `reconcile` returned `pct_within_tol: 100.0` with no intervals, and `cli/backfill/reconcile.py`'s `reconcile_series` returned `ohlc_match_rate: 1.0`, `volume_rel_diff_max: 0.0` and `vwap_mean_abs_rel_diff: 0.0` with no overlap: the two members the topic was opened for. In each, the value a reader acts on says *everything agreed* when the truthful answer is *nothing was compared*.

The family is defined by that shape, not by a literal. A `1.0`, a `100.0` and a `0.0` are all members when the metric's good direction points that way, so `grep 'return 1.0'` is the wrong instrument twice over — it finds a sign function in `cli/features/trend_agreement.py` that is not a member, and it misses `volume_rel_diff_max: 0.0` that is.

**The tell that finds them fastest is a file that applies a polarity decision to some of its fields and not others.** `cli/xcheck/binance.py`'s `crosscheck_dataset` returned `None` for `min_close_corr` and `0.0` for `max_abs_rel_diff_overall`, one line apart; `cli/backfill/reconcile.py`'s `reconcile_dataset` has the same pair and made the same split. A member beside a non-member in the same dict is the readable signature of the defect, and it is what a sweep by shape alone reads past.

## Why this matters

A reconciliation exists to answer whether two sources agree, and its empty case is the one where a caller most needs to know it got no answer. `agent-ops.md` already names the class for queries — *an empty filtered query is not an absent event; require a positive trace and print the input's line count before trusting any zero* — and these are the same failure inside the code that computes the number rather than in a shell reading it.

**Who reads the number, verified against the tree rather than assumed.** None of the four reconcilers has a production caller: every reference to `reconcile_dataset`, `reconcile_15m_vs_ticks`, `seam_15m_to_1h` and `crosscheck_dataset` in the tracked tree is the module itself, an `__init__` re-export, a test, or a doc — no CLI subcommand, no daemon, no timer, nothing under `infra/` or `.github/`. `docs/plans/00044-15m-substrate.md:48` records their real run as *"a `python -c`/script invocation in the task report, not committed"*. They are hand-run analysis tools, so nothing acts on a false number unattended; the reader a vacuous 100% misleads is a human validating a dataset.

**It has misled one already.** `docs/iterations-history-phase6.md:863`: a millisecond-stamped tick file parsed into the far future, and `reconcile_15m_vs_ticks` reported *0% coverage beside 100% within-tolerance*, which an operator read as a contradiction rather than a bad input. The fix landed upstream — `read_trades_csv` now refuses a `ts` outside plausible epoch seconds (`cli/tick/read.py:121`) — and left the vacuous 100% standing, so the same pair is still produced by every other route to an empty join.

The members do not share one blast radius. The four reconcilers are hand-run. `cli/engine/soak.py` is a tier up: `soak_report` is reached only by the offline `soak-check` command, the shadow node's `run()` never references it and the file places no order, so its floor is ordinary — but it is the instrument the go-live decision reads, and a fabricated number there cannot place a trade while it can still steer whether trades are placed at all. And `cli/capture/gap_monitor.py` is the one member with a production caller: it gates the healthchecks.io ping on the unbackfillable capture path, which is a different floor again and is why it is held rather than fixed here.

## Findings so far

**The family is an empty DENOMINATOR, not an empty input, and an exclusion is what establishes that.** `cli/engine/concordance.py`'s `compare_targets` returns `passed=True, worst_abs_diff=0.0` on empty and is CORRECT: its `set(a) != set(b)` guard has already returned, so reaching `not a` means both sides are empty and their key sets agree — two environments each reporting no positions genuinely concur. It is on the live trade path, so a fix refusing every empty input would have turned a legitimate both-flat agreement into an error there.

**The sweep** ran over `cli/` in two AST passes: every early return guarded by an emptiness test, and every conditional expression whose true arm contains a division, `max(`, `mean` or `sum(`. The second pass is where the members concentrate — a guarded division on one line has no `if` statement for the first pass to see. Every row below was opened and read.

**One member the sweep missed, and why.** `crosscheck_series`'s guard reads `if overlap_rows < 2`, and the first pass's emptiness predicate enumerated the spellings already seen — `not `, `== 0`, `is_empty`, `height`, `len(`, `< 1`, `<= 0`. A predicate built from the members already found finds the members that look like them. It was caught by a reviewer, in the same file and seven lines above a member already fixed, and it defeated that fix for the case that actually happens: with one symbol whose Binance window does not reach Kraken's, the dataset maximum was still taken over a `0.0`.

**The tick instance was documented and pinned, not overlooked.** Its docstring said zero overlap reports the percentage "vacuously" and shipped it, and a test named `test_reconcile_zero_overlap_reports_vacuous_full_match` held it in place. The prose was correct and the code was wrong; only reading them against each other surfaced it, and the test made the defect harder to remove by making its removal look like a regression.

**Why `None` rather than a field, a sentinel or a raise.** Both original members already returned their denominator — `n_intervals: 0`, `overlap_rows: 0` — beside the value that lied, so reporting the emptiness in a field is the fix that had already lost here, twice, because the headline is what gets read. `math.nan` survives arithmetic silently and is truthy under `bool()`. Raising is wrong for a report function called per-pair in a sweep, where one empty window must not abort the run.

Excluded, with the reason:

- `cli/trades/gaps.py` — counts, not ratios: zero gaps in zero rows is a true count, and `rows` sits in the same struct and is read by `backfill.py`.
- `cli/ohlc/qa.py`, `cli/alpha/killbar.py` — same shape, opposite polarity; 0 % coverage and a 0.0 hit rate are the failure direction.
- `cli/engine/soak.py`'s `eff_n` family — 0 is the degenerate direction `degenerate()` also reports.
- `cli/engine/feeders.py` (`math.nan` at its ratio guards), `cli/engine/tracking.py` (`None` for its three rate fields, `"insufficient-data"` for its gate verdict — it contains no `nan`), and `crosscheck_dataset`'s `min_close_corr` (`None`) — all already refuse to invent a value; `min_close_corr` set the convention this fix adopted.
- `cli/validation/dsr.py` — success direction, but `0.0` is the formula's limit at `n_trials == 1` or zero dispersion, not a guard over an unmade comparison.
- `cli/risk/limits.py` — `math.inf` headroom on zero use is correct.
- `cli/alpha/b1.py`, `cli/features/{channel,derivatives,momentum}.py` — neutral defaults for a feature, not summaries of a comparison.

**The two flagged sites, adjudicated once `cli/engine/soak.py` came into scope.** Neither is a member.

- `_mean` is a generic helper with no polarity of its own, so its empty case belongs to its five callers. Three — the gating-metric loop, `cap_live` and `pnl_mean` — feed `_judge_dual`, which returns `"n/a"` whatever the live value once the window is non-positive: `windowed_null` gives `[]` and `metric_verdict` returns `"n/a"` under `len(null_values) < 2`. `d4_gap_bps` is a signed mean of differences whose `0.0` is neutral rather than a success value, and it is rendered beside a bias flag that is inactive on the same empty null. The one caller that was a member, `null_gov_rate`, is guarded at its own call site.
- `analyze_soak`'s `gov_live` has no success direction at all: it is one side of a comparison, not a score. Its `0.0` also cannot reach a substantive verdict — with no realized days, both the window and `effective_n` are zero, and `metric_verdict` returns `"n/a"` on either arm. It reaches the report only as the `live` figure beside an `"n/a"`, and `MetricVerdict.live` is typed `float`, so a `None` there would be mechanism out of proportion to a number already marked unjudged.

**`structural_metrics`' `bar_hhi` looks like a member and is not one — the defect is one level up, in what averages it.** Its `0.0` is a specified out-of-range sentinel rather than a success value: `docs/plans/00058-soak-check-oos-report.md:52` records the branch as the design (`hhi = Σ_a (|w_a|/gross)^2` if `gross>1e-12` else `0.0`), and `docs/specs/00059-soak-check-realized-governor-cap-design.md:49` states that HHI's lower bound is `1/n > 0`. No measured value can collide with `0.0`, so a reader of one bar can always tell the unmeasurable from the measured — which is exactly what the family's other members cannot offer, `pct_within_tol: 100.0` being indistinguishable from a genuine perfect reconciliation.

**What consumes the sentinel is where it goes wrong.** `analyze_soak` takes `_mean` over the per-bar list and hands the null's list to `windowed_null` and `block_bootstrap_null`, so a flat bar's sentinel is averaged as though it were data and pulls the concentration figure toward *better diversified than anything measured*. `hhi` is one of the seven gating verdicts under spec `00059` D6, so that figure is one a go-live decision reads. The fix belongs at the aggregation — exclude out-of-range bars rather than average them — which leaves the specified sentinel untouched and moves only that metric's window and `effective_n`. `test_analyze_soak_degenerate_zero_exposure` drives six all-zero-weight bars through the branch, so it is live and covered.

**A fix that adds a filter has added a guard, and a guard is unproven until the tree without it is seen to break.** This family recurred inside its own repair three times: the first fix shipped guards no assertion could fail, the second shipped a guard that passed because no fixture discriminated, and the third — the `is not None` filters keeping a `None` out of `min()` and `max()` — was itself deletable with the suite green, because every fixture was either all-measured or all-empty. The dataset that breaks it is the one the topic's own argument is about: a universe where SOME symbols reach.

**The general form, because it decides where a fix goes.** An empty-input branch that returns a value the metric's own range EXCLUDES is a sentinel, and it is sound at the site that produces it; one that returns a value the metric can genuinely take is a member, because nothing downstream can tell the two apart. A sentinel still produces this family's failure the moment something aggregates it without knowing it is one — so the question at each site is not only *what does the empty branch return* but *does every consumer know that value is out of range*.

**Two things recorded rather than fixed.** `_match_stats`'s `else None` arm is unreachable — `reconcile`'s own empty-intervals return fires first, proven by a `12345.0` mutation of that arm surviving the suite — so its census row below is the family's shape stated where the shape belongs, not a live defect removed. And `all_match: False` on an empty join still conflates *nothing was compared* with *compared and disagreed*; it is the fail-safe direction and the only other one a boolean has, so a caller that needs to tell them apart reads `n_joined` beside it.

## Done so far

| site | computes | was | now |
|---|---|---|---|
| `cli/tick/reconcile.py` · `_match_stats` | the within-tolerance pct | `100.0` | `None` — unreachable arm, no test can drive it (Findings) |
| `cli/tick/reconcile.py` · `reconcile` | `pct_within_tol`, `pct_within_tol_loose` | `100.0` | `None` |
| `cli/backfill/substrate15m.py` · `reconcile_15m_vs_ticks` | `coverage_pct` | `100.0` | `None` |
| `cli/backfill/substrate15m.py` · `seam_15m_to_1h` | `max_price_rel_diff`, `max_volume_rel_diff` | `0.0` | `None` |
| `cli/backfill/substrate15m.py` · `seam_15m_to_1h` | `all_match` | `True` | requires a non-empty join |
| `cli/xcheck/binance.py` · `crosscheck_series` | `max_abs_rel_diff` | `0.0` | `None`, rendered `n/a` |
| `cli/xcheck/binance.py` · `crosscheck_dataset` | `max_abs_rel_diff_overall` | `0.0` | `None`, rendered `n/a` |
| `cli/backfill/reconcile.py` · `reconcile_series` | `ohlc_match_rate` | `1.0` | `None`, rendered `n/a` |
| `cli/backfill/reconcile.py` · `reconcile_series` | `volume_rel_diff_max` | `0.0` | `None`, rendered `n/a` |
| `cli/backfill/reconcile.py` · `reconcile_series` | `vwap_mean_abs_rel_diff` | `0.0` | `None`, rendered `n/a` |
| `cli/backfill/reconcile.py` · `reconcile_dataset` | `min_ohlc_match_rate` | `1.0` | `None`, rendered `n/a` |
| `cli/engine/soak.py` · `analyze_soak` | `null_cap_rate` | `0.0` | `None` |
| `cli/engine/soak.py` · `analyze_soak` | `null_gov_rate` | `0.0` | `None` |

`reconcile_series`'s three fields are one branch but three decisions: a rate whose success value is `1.0` beside two deviation measures whose success value is `0.0`. Listing them as one row is how a reader stops seeing a `0.0` as a member at all.

Each fix carries a test whose empty case fails against the pre-fix literal, and beside it a populated-input control asserting the measured value, so a guard that answered `None` or `n/a` unconditionally cannot pass either. Several of those controls exist only because `infra/scripts/mutate-probe.sh` reported the corresponding mutation SURVIVED first, so the count of them is a record of what the tests missed rather than of what was planned.

Two properties of the result, stated rather than inherited. `crosscheck_series` returns `None` for the whole `< 2` branch, so a single shared day's deviation is discarded even though it is measurable: the threshold is the correlation's, and reporting one day's difference beside a null correlation would put a number in the dataset maximum that no distribution backs. And both filters test `is not None` alone, so a non-finite value passes — a zero Binance close would put `inf` or `nan` into the maximum. That is left as-is deliberately: `nan` renders as `nan` and announces itself, which is the sentinel case above and not this family's silent one.

## Suggested next steps

**The topic resolves when both hold**: (a) the census is closed over `cli/` and `infra/` — every site matching the family's definition, an empty-denominator branch returning a value the metric can genuinely take, is either fixed or listed under *Excluded* with its reason — and (b) every member carries a test whose empty case fails against the pre-fix literal, with a populated control beside it. Nothing else gates resolution; in particular the `hhi` aggregation below does not, because it is not a member.

- **Fix `_net_live_from_result`'s `reconcile_ok`** (`cli/engine/soak.py:299`). A member: `all(...)` over `assets` is `True` with no assets, and a vacuous `True` means the soak self-test passes its reconciliation arm without reconciling anything — `soak.py:625` and `:1585-1586` read it as a VOID trigger. Fix: `bool(assets) and all(...)`. Test: empty `final_targets` → `False`; a populated matching result → `True`; a populated mismatching one → `False`. **Held by no floor** — `soak.py` is off the live trade path (Findings) and `null_gov_rate` was fixed in the same file on this branch; only the current stand-down holds it.
- **Fix `GapMonitor.is_healthy`** (`cli/capture/gap_monitor.py:143`) — the one member on the capture path, so it takes that path's review floor and its own branch. `not any(...)` over `pairs` is `True` over an empty list, and it gates the healthchecks.io ping at `cli/capture/command.py:301`, where `client.connected` is independent of `pairs`: with no pairs the daemon captures nothing and keeps the dead-man switch green. **The reachable radius is narrower, and a floor decision needs the real one**: `_default_pairs` refuses a missing or unparseable universe file, and a non-empty `selected` naming no `/EUR` symbol logs an ERROR that `alerts.yaml`'s `Capture · daemon ERROR logs` rule selects (`command.py:113-120`; `configure()` runs in the Typer callback before `_default_pairs`, so the line is shipped rather than lost). Only a fully empty `selected` reaches an empty `pairs` silently. **Two fix shapes, and the decision is which**: (i) `is_healthy` returns `False` on empty `pairs` — the daemon keeps running, stops pinging, the switch goes red; or (ii) `_default_pairs` refuses an empty result the way it already refuses an unparseable file — the daemon does not start, and the refusal is an ERROR the same rule pages. (ii) is recommended: an empty pair list is a misconfiguration, and a daemon running while capturing nothing is the state the switch exists to expose, not one to keep alive. Either takes a test whose empty case fails against today's code, with a populated control beside it.
- **Adjudicate `infra/scripts/continuity.py:250`**: `pct = 100.0 * gap / covered if covered else 0.0` — a gap percentage reporting 0% gap on zero coverage, the family's shape. Its reachability is not established: the line runs only after the `measured` guard, and `measured` requires `n >= MIN_POOL` samples, which may make `covered == 0` impossible there. Establish it by construction. Reachable → `None`, with the table row showing it and a test; unreachable → *Excluded* with the proof, as `_match_stats`'s arm was.
- **Close the census over `infra/`.** The sweep in Findings covered `cli/` only. The same shapes over `infra/**/*.py` return five candidates; four adjudicate to non-members on opening and the fifth is the item above. Record the four under *Excluded*: `continuity.py:138` is a count of hours spanned; `continuity.py:230`'s `thresh` is computed only after an `UNMEASURED` row has already been printed and the loop has moved on; `ops_daily.py:1216` and `:1240` are `all(...)` over paths and are guarded — a first-stage head with no paths and a resolver answering fewer paths than operands both return `False` first — with the empty case pinned by `tests/test_ops_daily.py:2345`. A future sweep builds its predicate from the family's definition, never from the spellings of members already found — that enumeration is how `crosscheck_series` was missed.
- **The `hhi` aggregation is not a member and lives in `T0184`.** `T0183` does not wait on it.
- **Recurrence is a separate question.** Every test on this branch is per-symptom; none would catch a new member being written. That is the natural follow-on and is deliberately not a resolution criterion here, or the topic could never close.
