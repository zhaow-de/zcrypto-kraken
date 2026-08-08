---
status: partial
ripe_when: **the measurement and the rule are DONE (2026-08-08); what remains is the PUSH.** `infra/scripts/grafana-push.sh` upserts `zcrypto-engine-log-dead` into the folder, then verify the first sample BY VALUE, not presence — read the count the rule computes and confirm it is the expected ~11-34, never merely that the rule exists. Additive, so **no prune is owed**. Ripe at any window where an alert-rule push is acceptable
---

# The engine's ERROR-log rule can read zero forever and nothing notices

## Context — what

The trading engine ships its logs straight to Loki as `container="engine"` on the capture primary. Until this iteration nothing alerted on them at all; `Engine · ERROR logs` (`zcrypto-engine-error-logs`) now does, mirroring the capture daemon's rule.

That rule is **presence-fired**: it fires when ERROR or CRITICAL lines appear. It is therefore silent in exactly two situations that look identical from outside — the engine is healthy, or the engine's log-shipping path has regressed and no line is arriving to be matched. Every other shipping stream on the fleet is protected against the second case by a paired dead-man canary (`zcrypto-capture-log-dead-primary`, `-secondary`, and the four ops variants), which fires when a stream that should always carry lines goes quiet. The engine has no such sibling.

## Why this matters

The engine holds the live Kraken trade key and is the only component that can move money. Its ERROR rule is the sole log-side signal covering it, and a presence-fired rule with no canary behind it degrades silently: the ship path breaks, the rule reads zero, the board shows a flat line, and the absence of pages reads exactly like health. That is the failure class the capture canaries exist to prevent, and the reason the fleet added them — a parse or transport regression makes every ERROR rule's silence meaningless, which is why `Logs · lines dropped before reaching Loki` and the per-host canaries were built.

The gap was closed for capture and for ops. The engine is the one stream where it was never closed, and it is the highest-consequence one.

## Findings so far

**(2026-08-08) The engine's log cadence, measured — and it is a BURST emitter, which decides the whole design.** Over 72 h of **raw** Loki entries (230 lines, bucketed locally): **50 of 69 hours carry zero lines**, and the five largest inter-line gaps are all **exactly 4.00 h** — the engine's cycle period. Median inter-line gap is 0 s: it emits in bursts at cycle boundaries and nothing between. So the check-first question resolves **yes, a line-count canary is the right instrument**, but only with a window clearing 4.00 h; anything at or under that false-fires on every healthy inter-cycle gap.

**The measurement trap, recorded because it produced the opposite answer first.** Loki's `query_range` here forces **~240 min spacing regardless of the `step` requested** — which aliases exactly against the 4-hourly cycle. Sampled that way the series reads "every hour has lines, minimum 2/hour", i.e. a continuous emitter. That reading was taken, believed, and then overturned by fetching raw entries and bucketing locally. **Do not derive this window from a `count_over_time` range query.**

**Window: 6 h = the measured 4.00 h period + the fleet's own 2 h margin** (its ops timer canaries use 26 h for a daily emitter, i.e. 24 h + 2 h). Minimum lines observed in any 6 h window: **11**; max 34. `level=~".+"` confirmed present on the stream (values: `INFO`) before being relied on — an absent label would match nothing and park the rule permanently firing.

**Retention is not the binding constraint** the topic assumed it might be: the selector serves back to at least 2026-08-01 (7 days) at full rate, well beyond the 72 h the cadence question needed.


- Verified 2026-08-05 while adding the ERROR rule: a repo-wide grep for `container="engine"` returned **zero** hits in `infra/grafana/alerts.yaml` before that change. Enumerating every `container=` selector in the file gives `capture`, `archive-pull`, `zcrypto-archive-pull`, `alloy`, `liquidations`, and `zcrypto-.*` — none reaches the engine.
- The engine ships via the same direct-to-Loki path as the capture daemon (`ZCRYPTO_LOG_SERVICE: engine` in `roles/engine/templates/compose.yaml.j2`), so the regression modes are shared: a formatter change, a shipper failure, or a label change all produce the same silent zero.
- **The owner considered and deliberately deferred this**, 2026-08-05, when approving the ERROR rule: the offered option was "add the rule and a log-dead canary for it", and the stated reason for declining was that the engine logs far less than capture, so the canary window needs measuring before it can be trusted. That reason is the whole content of this topic — the work is blocked on a measurement, not on a decision.
- Why a borrowed threshold will not do: the capture canaries use a 6 h window because both capture daemons emit continuously at hundreds of lines an hour. The engine emits per 4-hourly cycle, so its natural quiet periods are longer than capture's alarm threshold by construction. A canary copied from capture would page on every healthy inter-cycle gap; one guessed too wide would never fire. The same trap was measured on `ops-log-pipeline-dead` this iteration, whose 14-day floor turned out to be ~1.5 lines an hour against a summary implying far more.

## Suggested next steps

- **(the remainder — everything else is built)** Push `zcrypto-engine-log-dead` with `infra/scripts/grafana-push.sh`, then **verify the first sample BY VALUE**: read the count the rule actually computes and confirm it lands in the measured 11–34 band. `delta()`/presence checks are blind to a fault already present in a series' first sample, and a rule that reads 0 because its selector is wrong looks identical to one that is simply healthy-and-quiet. The push is **additive — no prune is owed**, and `grafana-push.sh` never deletes.
- **(after the first sample)** Resolve this topic, recording the verified value.
