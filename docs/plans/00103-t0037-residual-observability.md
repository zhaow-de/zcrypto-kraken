# Spec 00103 — make T0037's accepted residuals observable: implementation plan

Spec: `docs/specs/00103-t0037-residual-observability-design.md`. Topic: [[T0037]].

Tasks 1–5 are code and config, executed by subagents. Tasks 6–10 are **ATTENDED, main loop** — every host-touching step (converge, image pull, Grafana push) dies in a subagent where nobody sees the permission prompt (`agent-ops.md`).

## Global Constraints

- **The hot path is observed, never redirected.** No decision in `append()`, `_admit`, `_hold`, `_enter_hour` or `HourOracle` may change. The two existing baselines are what prove it: `oracle=None` byte-for-byte equivalence, and the lagging-clock set-equality against that baseline. Both must stay green **unchanged** — editing either to accommodate a diff is a failed task.
- **The 16 `test_t0037_*` cases and `test_verify_tree_skips_held_spills` stay green unchanged**, same rule.
- **Every new guard needs a constructed defect that trips it AND a healthy control that stays silent** (`agent-ops.md`). A control that cannot bite proves nothing; assert on what the defect moves, never on a headline.
- Python 3.14, uv. Metric families are built in `cli/capture/command.py`'s collector at scrape time from writer attributes — follow the existing `CounterMetricFamily` idiom, including `labels=[...]` + `add_metric([...], value)` as `zcrypto_capture_gap_seconds_total` already does.
- **No behaviour may depend on a counter.** These are observations; if a counter is removed the capture path must still be correct.

### Constants this plan uses verbatim

- `MAX_TS_AHEAD = timedelta(minutes=5)` — the band split (D1).
- `CLOCK_WITNESS_MARGIN = MAX_TS_AHEAD` — referenced by the runbook text, never re-hardcoded.
- Clock-skew alert threshold: **10 s** (D4).

______________________________________________________________________

### Task 1: an early finalization is counted, at BOTH publish paths

**Red first.** Add to `tests/test_capture_segment_writer.py`:

- `test_t0037_early_finalize_counted_on_rotation` — two streams stamped bogus inside one closing window (residual (a)); assert the counter reads 1.
- `test_t0037_early_finalize_counted_on_the_sweep_path` — residual (a) with `_current_hour is None`, so `_sweep` publishes the truncated hour. `_sweep` calls `_merge_hour` **directly** and never `_finalize_hour`, so a rotation-only instrumentation leaves this at 0. This test is the one that fails if only one call site is instrumented.
- `test_t0037_genuine_boundary_counts_no_earliness` — **control**: genuine two-stream boundary, healthy clock; counter 0.
- `test_t0037_swept_past_hour_counts_no_earliness` — **control**: a sweep republishing a genuinely past hour; negative earliness, counter 0. Note this control is only meaningful once the sweep path is instrumented — before that it passes vacuously, which is why it is paired with the sweep test above and never quoted alone.
- `test_t0037_lagging_clock_counts_early_by_design` — a clock lagging 3 min with genuine traffic; counter fires. Docstring states this is spec 00103 D3, intended, and why it cannot be engineered away (any wall-clock-referenced test inherits the clock's error; T0036 forbids giving the clock a veto).

**Do NOT write a `beyond_window` test.** Spec D1 proves earliness ≤ `MAX_TS_AHEAD` structurally, so such a test would sit red forever.

**Then implement.** In `cli/capture/segment_writer.py`:

- One attribute beside `rows_held` / `rows_quarantined`: `self.hour_finalized_early = 0`.
- One helper, called from **both** publish paths:

```python
def _count_if_early(self, hour: datetime) -> None:
    """Count an hour finalized before our own clock said it was over (spec 00103 D1/D2).

    This is the visible signature of T0037's residual (a). Earliness is
    structurally bounded by MAX_TS_AHEAD -- every oracle witness is clamped at now + MAX_TS_AHEAD
    and `append()` holds anything above the confirmed hour -- so there is no second band to split.
    It does NOT see a LEADING clock's truncation: that measurement is taken with the same wrong
    clock, which subtracts its own lead back out (D1b). The skew alert covers that case, not this.
    A genuinely past hour yields a negative earliness, so the sweep's ordinary republishing is
    excluded by the arithmetic rather than by a special case.
    """
    earliness = (hour + timedelta(hours=1)) - _utcnow()
    if earliness > timedelta(0):
        self.hour_finalized_early += 1
        logger.warning(
            "hour finalized early pair=%s kind=%s hour=%s early_s=%.1f",
            self._pair, self._kind, hour, earliness.total_seconds(),
        )
```

Call it as the first statement of `_finalize_hour`, and in `_sweep`'s loop immediately before its `self._merge_hour(hour_dir, hh)` — the sweep already has the hour in hand as it iterates; pass that value, do not re-parse it from the path.

**Verify**: the five tests; then the whole file. The `oracle=None` equivalence and the lagging-clock set-equality baselines are what catch an accidental behaviour change.

______________________________________________________________________

### Task 2: a past-dated FIRST stamp is counted, in the startup window

Spec D5. The mid-stream case needs nothing: `append()` computes `floor = self._current_hour or self._floor`, so once an hour is open a past-hour stamp is **already dropped** by the late-event guard. Only a process's first event can open a past hour.

**There is no `_advance_witness` helper and no extraction from `_admit`/`_hold`.** An earlier draft counted every `ts` that regressed against `_max_ts`; that fires on drained held rows (the drain re-admits rows whose `ts` already advanced the witness), on T0026 reconnect replays, and on genuine rows following a neutralized future stamp. The hot path keeps its current shape.

**Red first.**

- `test_t0037_past_dated_first_stamp_counted` — a fresh writer whose first event is stamped into an un-published past hour above the recovery floor; assert the counter reads 1.
- `test_t0037_normal_start_counts_no_past_dated_hour` — **control**: first stamp current; 0.
- `test_t0037_draining_held_rows_counts_no_past_dated_hour` — **control with teeth**: ≥2 held rows carrying **distinct** timestamps, then drained. One held row would stay silent under the rejected design and prove nothing; two is the minimum that bites.
- `test_t0037_lone_bogus_future_stamp_counts_no_past_dated_hour` — **control**: the existing pinned-healthy lone-in-window-bogus-stamp scenario, which the rejected design would have paged on. Must read 0.

**Then implement.** `self.ts_past_dated_hour = 0` in `__init__`, and in `_enter_hour`'s first-event branch only:

```python
if self._current_hour is None:
    # Spec 00103 D5. The first event's hour is exchange time, and it is the ONLY event that can
    # open an hour behind the wall clock: from here on `floor` is `_current_hour`, so the
    # late-event guard refuses a past-dated stamp before it reaches us. An hour opened materially
    # behind our clock is the past-dated residual (T0037) -- it can commit a
    # final for an hour that was never captured, and redeem a quarantined `.held` spill on the way.
    if hour < _hour_start(_utcnow()):
        self.ts_past_dated_hour += 1
        logger.warning("first stamp opened a past hour pair=%s kind=%s hour=%s", self._pair, self._kind, hour)
    self._sweep(hour)
    self._open_hour(hour)
```

A normal restart mid-hour opens the CURRENT hour, so `hour < _hour_start(now)` is false and nothing counts. A restart that legitimately straddles a boundary is the one benign case that can count; the runbook says so, and Task 8's baseline read is what establishes its real rate.

**Verify**: the four tests, plus the whole file.

______________________________________________________________________

### Task 3: publish both families from the metrics tap

In `cli/capture/command.py`'s collector, beside `zcrypto_capture_rows_quarantined_total`:

```python
yield CounterMetricFamily(
    "zcrypto_capture_hour_finalized_early_total",
    # Spec 00103 D1: T0037's residual (a), made visible. Unlabelled on purpose -- earliness is
    # bounded by MAX_TS_AHEAD by construction, so there is no second band. A LEADING clock's
    # truncation is NOT here (D1b); zcrypto-capture-clock-skew is that case's only detector.
    "Hours FINALIZED before the wall clock said they were over, summed across every pair and kind.",
    value=sum(w.hour_finalized_early for w in writers),
)
yield CounterMetricFamily(
    "zcrypto_capture_ts_past_dated_hour_total",
    "Processes whose first event for a stream opened an hour already behind the wall clock.",
    value=sum(w.ts_past_dated_hour for w in writers),
)
```

**Verify**: extend the collector test to assert both families are present as **series** with the summed value — never a substring match on the exposition text, which passes on a present-but-wrong metric.

______________________________________________________________________

### Task 4: admit the clock offset to the shipper

`infra/ansible/roles/capture/files/config.alloy` — the keep-regex is an allowlist on `__name__`. Add `node_timex_offset_seconds` and `node_timex_sync_status`.

Also admit the two new capture families if the capture-app job's keep-regex enumerates names rather than passing the `zcrypto_capture_*` prefix — **check before editing**; a new family silently dropped at the shipper is the T0051 trap, and step 4 of the deploy sequence is where it would surface as `(no series)`.

**Verify**: `--check --diff` renders the expected regex; the rendered file is valid Alloy syntax. The real proof is Task 8's by-value read — a keep-regex is only ever proven on the host.

______________________________________________________________________

### Task 5: the alert rules, the corrected `.held` prose, and the runbook

**`infra/grafana/alerts.yaml`** — three new rules. **Uids must match the runbook headings exactly** (D7: the uid is the only join key from a phone notification to the response):

| uid | expr | severity |
| --- | --- | --- |
| `zcrypto-capture-hour-finalized-early` | `increase(zcrypto_capture_hour_finalized_early_total{host=~"zcrypto\|zcrypto-red"}[6h]) > 0` | warning |
| `zcrypto-capture-ts-past-dated-hour` | `increase(zcrypto_capture_ts_past_dated_hour_total{host=~"zcrypto\|zcrypto-red"}[6h]) > 0` | critical |
| `zcrypto-capture-clock-skew` | `abs(node_timex_offset_seconds{host=~"zcrypto\|zcrypto-red"}) > 10 or node_timex_sync_status{host=~"zcrypto\|zcrypto-red"} == 0` | **critical** |

Three rules, not four — spec D1 retires the `beyond_window` rule as unreachable. **`zcrypto-capture-clock-skew` is critical because D1b makes it residual (b)'s only detector**, not because a drifting clock is itself an emergency. Its second leg needs the host matcher spelled out; an unqualified `node_timex_sync_status` spans every host in the fleet.

`zcrypto-capture-hour-finalized-early` is a **warning**: D3 means a lagging clock fires it legitimately, at up to ~576/day/host summed across 24 writers. Size `for:` and any threshold against that rate, not against the ~24 an earlier draft assumed.

Escape `|` as `\|` inside the table's code spans (`docs-style.md`). Summaries carry no internal tokens — no `T0037`, no `spec 00103` (`operator-facing-text.md`); the semantic content stays and the token moves to the adjacent YAML comment.

The `within_window` summary must say, in operator words, that it does **not** on its own distinguish a bogus-stamp truncation from a lagging clock, and to read the clock-skew signal beside it. A summary that names one cause is the defect this task also fixes elsewhere.

**Correct `zcrypto-capture-rows-quarantined`** (D6): its inline comment and `summary` currently say the metric counts rows that *"arrived after their hour was finalized"*. Rewrite both to say it counts held rows spilled for an hour the oracle never **confirmed**, and point the operator at the real causes — a lone stream in a sparse hour, or a process stop inside `CLOCK_WITNESS_MARGIN` of a boundary. Keep its "baseline is zero" line: measured 0 on both hosts, 2026-08-29.

**`infra/runbooks/capture.md`** — five entries in the file's existing shapes (What you are seeing / What it means / What to do / Retire when):

- `## bogus-timestamp-hour-rotation — KNOWN LIMITATION`, modelled on `cross-hour-straddle`: the three residuals, the band table, which knob would close each and what it starves, **the truncation is permanent by design — do not attempt repair**, how to name the residual by reading band against clock offset, and a `Retire when` that is a structural condition, not a date. Cite the archived topic as `cross-hour-straddle` cites `T0103`.
- One `## <uid> — ALERT` entry per new rule, headings matching the uids above. The `hour-finalized-early` entry must state that it does NOT see a leading clock's truncation (spec D1b) and that `zcrypto-capture-clock-skew` is that case's only detector — an operator who reads it as total coverage of the residuals is being misled.
- `## zcrypto-capture-rows-quarantined — ALERT` — the entry it never had.

**Verify**: `uv run pytest tests/test_internal_terms_not_operator_visible.py` (it enforces the alert-summary surface); every new uid appears both in `alerts.yaml` and as a runbook heading — assert that by grep in both directions, since a one-way check passes on an orphan.

______________________________________________________________________

### Task 6: build the image (ATTENDED, main loop)

Push the branch; take the CI-built digest. Pre-stage per `zcrypto-rollout-image` Phase 0: pull on both capture hosts, prove the change is **in** the pulled image by running the image's own surface, record the rollback operand and confirm it is still resident on both.

### Task 7: roll out under `zcrypto-rollout-image` (ATTENDED, main loop)

Full canary discipline — **nothing here is exempt**: secondary converge → the bake gate's three events (a prune with its `deleted=N` form quoted, ≥3 full rotation hours, every abort signal clear) → the eight Phase-3 reads quoted → primary on the user's word. Check the Kraken maintenance feed at planning time and again immediately before. Phase 5 runs after **each** converge, re-truing `docs/reference/fleet-pins.md` from `deploy-log.jsonl`'s line with the evidence in the commit message.

### Task 8: the Alloy converge and the by-value reads (ATTENDED, main loop)

Converge the capture Alloy config pinned to the **currently-running** Alloy digest (config-only, no bake). Then read on both hosts, by value:

1. `zcrypto_capture_hour_finalized_early_total` present and zero.
2. `zcrypto_capture_ts_past_dated_hour_total` present and zero **over a window containing at least one process restart** — its only reachable path is a process's first event, so a restart-free window never exercises it and is not a baseline. A capture converge supplies the restart.
3. `node_timex_offset_seconds` and `node_timex_sync_status` present, offset within 10 s.

`(no series)` is a FAIL and stops Task 9 — it is never a zero. **If the offset reads outside 10 s, that is a finding to act on in this branch** (fix the discipline, or re-derive the threshold against measured reality and record why) — not a deferral, not a new topic.

### Task 9: push the alert rules (ATTENDED, main loop)

Only after Task 8's reads pass — a rule pushed ahead of its metric's first record pages a spurious no-data alert. `infra/scripts/grafana-push.sh` (its header carries the vault-token recipe; never improvise the decrypt). Confirm each of the three rules evaluates, and that the corrected `rows-quarantined` rule still evaluates after its edit.

### Task 10: closeout — resolve T0037, and the history entry

**Only now, and only if Tasks 1–9 all passed with their controls silent** (spec: archiving removes the only other record of the residual, so an unproven detector must not be archived over).

- `topic-ops`: T0037 → `status: resolved`, **delete `ripe_when:`**, `git mv` to `archive/`, `git add` the new path, move and re-point the index bullet to the archived path in the same change.
- Its `## Resolution` in the T0025 shape — *the trigger is retired rather than waited on* — naming the three alert uids, the runbook entries, this spec, and the by-value readings from Task 8. State plainly that the **mechanisms remain accepted design limits** and only the deferral is discharged.
- Re-tense the `T0037` citations in `cli/capture/segment_writer.py` to `(T0037, resolved, records why)` — never delete them (`code-prose.md`).
- Append the iterations-history entry via the `iteration-closeout` skill (phase routing, dataset-catalog sync). Re-verify every status claim against the full branch log immediately before PR-open.

______________________________________________________________________

## Sequencing note

This branch was cut from `28d32463` and carries **26 commits `develop` lacks** — all of T0028's. Its PR opens only after T0028 merges, then rebases onto `develop`. Opening earlier drags leg A/B's work into this PR.
