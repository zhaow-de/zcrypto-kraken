---
status: open
---

# The quarantined-rows counter is blind to the spill that happens as the process dies

## Context — what

`zcrypto-capture-rows-quarantined` watches `increase(zcrypto_capture_rows_quarantined_total{host=~"zcrypto|zcrypto-red"}[6h]) > 0` (`for: 15m`, warning). The counter has **two** increment sites in `cli/capture/segment_writer.py`, and they do not behave alike:

- `_hold()` — the live path. The process keeps running, the next scrape publishes the step, and `increase()` reads it correctly. **This half of the detector works.**
- `close()` — the shutdown path. The increment lands in a process that is exiting. Scrapes are 60 s apart and `stop_grace_period` is set nowhere under `infra/`, so Docker's default applies and the process is normally gone before the next scrape. **A value that is never published cannot be read by any expression, absolute or windowed.**

Spec `00109` D3 excluded this rule from that spec's fix on purpose: D2's absolute-value change repairs `increase()`-blindness for start-correlated counters, and it does **not** repair a counter whose sample never leaves the process. The spec states in terms that the deferral is not registered by it, which is why this file exists.

## Why this matters

The `.held` sidecar is the quarantine for rows the oracle never corroborated. Its own alert summary says the baseline is zero and any firing is a real event. A shutdown-time spill is exactly the case an operator most wants to know about — it is the one correlated with a capture process stopping near an hour boundary, which is also when a re-pin, a converge or a crash happens.

The failure is silent in the worst direction: the rule reads healthy, so the surface asserts coverage it does not have. This is the same class as [[T0034]] and as the defect `00109` D2 fixed — an instrument that cannot report the thing it names.

Scope, stated so nobody over-reads this: the metric is **not** wholly blind. `_hold()` spills are seen. Only the `close()` path is lost.

## Findings so far

- Two increment sites, measured: `cli/capture/segment_writer.py:407` inside `close()`, and `:562` inside `_hold()`. Published by `cli/capture/command.py` as a sum over the live writers.
- `stop_grace_period` does not appear anywhere under `infra/` — checked, not assumed. Nothing widens the shutdown window today.
- The CRITICAL log line the writer emits on a spill is unaffected by any of this: it is written before the process exits and reaches Loki through the log path, not the metric path.
- Registered on the owner's explicit word, 2026-09-02, during `00109`'s execution.

## Suggested next steps

Decide between three fixes; they differ in cost, and the cheapest needs no converge at all.

- **Rule that the CRITICAL log line is the real detector and the metric is decoration.** Re-point the alert at the log line, and say so on the rule and in `capture.md`. Costs a Grafana push and a runbook edit; **no capture converge**, so it can land without touching the unbackfillable path. Evaluate this one first, precisely because it is the only option that does not put the capture pair through a deploy.
- **Persist the count across restart** so the step survives the process that made it. Correct but the largest change, and it owes a capture converge.
- **Widen the shutdown grace** so the final scrape lands. Smallest code change, but it is a timing bet against a 60 s scrape rather than a fix, and it too owes a capture converge.

**Whichever is chosen, it must not ride the `00109` capture converge**: that converge carries no design for this, and a converge carrying an undesigned change is the thing the capture pair's discipline exists to prevent.

To decide against evidence rather than reasoning, read the pair on both capture hosts: a `.held` file whose hour has no corresponding non-zero sample is a `close()`-path spill that the metric lost. If production has never produced one, that is itself an argument for the cheap option.
