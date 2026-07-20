# Spec 00061 — soak-check: the secondary block-bootstrap null and instrument-fragility detection (T0073)

## Goal

Judge every soak-check metric under **two independently-constructed nulls** and surface the cases where the verdict depends on *which null you built* rather than on the data. Completes spec `00058` D3, descoped in v1.

## Why

`00058` builds its reference from a single **windowed** null: all overlapping L-bar windows of the metric series. Overlapping windows share observations, so that null understates the true sampling variance — a known, one-directional bias. The **stationary block bootstrap** (Politis–Romano) resamples independent paths and therefore has a different, largely uncorrelated bias.

The valuable output is not a second number. It is the **disagreement**: a metric whose verdict flips between the two constructions is not telling you about the strategy, it is telling you about the instrument. `00058` already refuses to over-claim in several ways (the vacuous-band `n/a`, the near-redundancy disclosure, the structural-conformance footer); this adds the missing one — *"this verdict is not robust to how the null was built."*

Cost is negligible: measured 0.15 s for n=10000 paths against a 27,997-bar series, vs 0.01 s for the windowed null. No sampling reduction is warranted.

## Decisions

- **D1 — every metric is judged under both nulls, and the two verdicts are reconciled by an explicit severity rule.** Order the labels by severity: `consistent` (0) < `weakly-consistent` (1) < `inconsistent` (2); `n/a` is outside the order.
  - **Both `n/a`** ⇒ `n/a` (neither null could discriminate).
  - **Exactly one `n/a`** ⇒ take the discriminating null's label, and **disclose** that only one construction had power here.
  - **Same label** ⇒ that label.
  - **Adjacent labels** (severity differs by 1) ⇒ take the **milder** one — the reading less likely to cry wolf — and disclose the disagreement. This follows `00058` D3's "prefer the more conservative on disagreement", where *conservative* means conservative about **claiming a divergence**.
  - **Opposite extremes** (`consistent` vs `inconsistent`, severity differs by 2) ⇒ **`indeterminate (instrument-fragile)`**. The two constructions contradict each other outright; reporting either label would be asserting more than the evidence supports.

- **D2 — the reported row keeps the primary null's statistics; the secondary contributes a verdict, not numbers.** The fingerprint table's `live / median / band / pctile / eff-n / width` columns stay the **windowed** null's (unchanged from `00058`, so existing readings remain comparable). The verdict itself renders as **three** columns, not one: `verdict` (the reconciled label `summarize_panel` counts), `primary` (the windowed null's own raw label), `secondary` (the bootstrap's own raw label). A `verdict`/`secondary`-only rendering makes a genuine disagreement print as two *identical* strings on 3 of D1's 5 reconciliation branches, with the primary's own raw label appearing nowhere in the table — the exact failure mode this decision's intent (numbers stay the primary's, the secondary contributes only a verdict) is meant to prevent; showing all three closes that gap. Mixing two nulls' numbers into one row would still be unreadable and would invite comparing incommensurable bands.

  Under a **single-null** mode the same three columns are rendered, with the construction that did not run showing `-`. The `-`/`n/a` distinction is load-bearing and must not be collapsed: `-` means **not computed** (that null never ran), `n/a` means **computed but undiscriminating** (a real `metric_verdict` call whose band had no power, per `00059` D8). Rendering `n/a` for a construction that never ran would assert a result that does not exist — the same over-claim this instrument exists to avoid.

- **D3 — multiplicity counts an `indeterminate` metric as discriminating but never as an outlier.** `n_metrics` includes it (both nulls *did* discriminate — they simply disagreed), `n_outside` does not (there is no agreed finding to count). Indeterminate metrics are reported on their own line, e.g. *"1 of 6 indeterminate — the verdict depends on how the null was constructed"*, so a reader cannot mistake an unresolved metric for a clean one.

- **D4 — `--null [windows|block-bootstrap|both]`, default `both`.** With a single null selected there is no reconciliation and that null's verdict stands unmodified; the report states which construction was used. `both` is the default because the disagreement is the point.

- **D5 — `--path [fast|verified]`, default `fast`.** Threaded to the null build and the identity self-check. `verified` runs the oracle builder (`build_crossfreq_system`, ~111 s vs ~1.9 s) and exists so a suspicious result can be re-read on the slow path without editing code. The report states which path produced the null.

- **D6 — determinism.** The block bootstrap is seeded (`numpy.random.default_rng(seed)`), so two runs over the same inputs produce identical verdicts. The seed is fixed, not exposed as an option — a user-tunable seed on gate-adjacent evidence invites shopping for a friendlier null.

## Non-goals

- The report's **"regime context"** section (`00058` report-shape item 9) stays deferred: `00058` named it without defining what it should contain, and inventing a definition here would be worse than leaving [[T0073]] open on that point.
- No change to the metric set, the windowed null's construction, the honesty banner, the vocabulary lock, or the gate itself.
- Consumes no holdout budget.

## Test list (TDD)

1. **Reconciliation table** — one test per branch of D1: both `n/a`; one `n/a` (discriminating one wins + disclosure); identical labels; adjacent labels (milder wins + disclosure); opposite extremes ⇒ `indeterminate (instrument-fragile)`.
2. **The fragility flag genuinely fires** — a constructed case where the windowed null says `inconsistent` and the bootstrap says `consistent` yields `indeterminate`, and the test fails if the reconciliation is dropped.
3. **Both nulls agree on planted-consistent and planted-inconsistent** — the ordinary cases stay stable under the second construction (no spurious fragility).
4. **D3 multiplicity** — an `indeterminate` metric counts in `n_metrics`, not in `n_outside`, and its own line appears.
5. **D4** — `--null windows` reproduces today's verdicts byte-for-byte (no reconciliation applied); `--null block-bootstrap` uses only the bootstrap; `--null both` reconciles.
6. **D6 determinism** — two runs give identical verdicts and identical bootstrap-derived labels.
7. **Vocabulary lock + banner** still hold over the new column, the new disclosures, and the `indeterminate` label.
8. **Real-journal (data-gated)** — on the ops mirror all seven metrics report both verdicts, and the run stays within a couple of seconds of the current runtime.
