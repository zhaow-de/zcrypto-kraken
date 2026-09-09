---
status: open
---

# The dark-with-exposure page reads no exposure over a position it never observed

## Context — what

`infra/grafana/alerts.yaml`'s `zcrypto-engine-dark-with-exposure` pairs *the engine is not reporting* with *money is exposed*, and fires on `$A > 0 && $B < 1`. Its exposure half is

```
max(abs(last_over_time(zcrypto_exec_position{host="zcrypto"}[24h]))) or on() vector(0)
```

With no `zcrypto_exec_position` sample anywhere in the window, `last_over_time` returns nothing, the fallback supplies 0, and `$A > 0` is false. 0 is a value the position genuinely takes — flat — and it is the quiet direction at the same time, so the rule reads *no exposure* over an observation that was never made, and the one page it exists for cannot fire.

## Why this matters

The series is not eagerly born. `zcrypto_exec_position` is a labelled `Gauge` in `cli/engine/command.py`'s `_ExecutionMetrics`, and its only setter is the executor's fill hook — `_metrics.set_position(...)` on a fill event in `cli/engine/executor.py`. One child per symbol, created at that symbol's first fill in the process's life. `_ExecutionMetrics`' own docstring states the principle the rule then leans on and does not get: *a Counter's zero is a MEASURED fact where a Gauge's would be an unmeasured claim* — which is why `realized_pnl` is eager at 0 and a labelled position gauge cannot be.

So an engine restarted while a position is open publishes nothing about that position until its next fill. If it then goes dark, node A reads 0 through the fallback and the page stays quiet with money at the venue: the state the rule was built for.

`T0018` records that nothing has been armed and no order has ever been submitted, so no fill has ever created the series — the exposure half has never yet read a measurement, and there is no production history to check a fix against.

The rule's own comment already names the neighbouring case: past the 24h lookback the page self-resolves while the engine may still be dark and the position still open, and the runbook says in those words that a resolve is not an all-clear. That is the same blindness with a clock in front of it, documented and accepted. The unseeded case has neither a clock nor a note.

## Findings so far

- **The ruling, to be recorded rather than re-derived: the fix is not an edit to node A's expression.** The same `or on() vector(0)` on node B is load-bearing — it is what makes the rule page on BOTH darkness routes (a dead exporter leaving `up` present at 0, and the primary's Alloy taking the series away entirely) and what lets `noDataState: Alerting` mean *the datasource is gone* rather than *the fleet is*. The rule's comment defends that at length. The fix that preserves it is a separate presence check, so the blindness is itself visible instead of being folded into the quiet arm.
- `tests/test_infra_alert_rules.py`'s `_replay_dark_with_exposure` already models the fallback exactly — its `a(t)` returns `0.0` when the window holds no sample — and it exercises a genuinely flat position (`flat_then_dark`) as a quiet case. Nothing in it distinguishes flat-and-observed from never-observed, so the work needs a new history in that harness, not a new harness.
- An alert-rule change reaches Grafana only through `grafana-push.sh` run from merged `develop`, on the owner's word (`fleet-deploys.md`). That is why this is a topic and not a commit on the branch that found it; the rule carries `severity: critical` and sits on the live trade path.
- It is `T0183`'s family by shape, and is recorded there as *Excluded by transfer* to this topic — `T0183`'s arm (a) holds no earlier than this lands.

## Suggested next steps

- **Widen the replay first**, before any rule edit: a `(position, scrape)` history that publishes no position sample at all, asserted quiet under today's expression and firing under the fix. Restoring the current node A must turn it red, and `flat_then_dark` must stay quiet under both — a check that pages on a legitimately flat book has replaced one blindness with a false page.
- **Design the presence check.** A query node reading whether any `zcrypto_exec_position{host="zcrypto"}` sample exists in the window, and a page when the engine is dark and the exposure is *unknown*. Whether that is a second rule or a third arm of this one is the open design question: `$A > 0 && $B < 1` cannot express *unknown* without changing what the existing page means, and its summary is wording two reviews argued into place (`test_the_dark_with_exposure_page_keeps_the_wording_two_reviews_argued_into_it`).
- **Then decide whether the source should be fixed instead.** Seeding the position gauge at engine startup from a venue read would close the blindness where it starts rather than at the alert. That is a change on the live trade path with a different owner from this rule — decide which layer owns it before writing either, so the alert is not built around a gap that is about to close.
- Land the rule change in a PR into `develop`, merge, then push and verify the new node's first sample **by value** before anything is pruned (`fleet-deploys.md`'s alert-rule lifecycle).
