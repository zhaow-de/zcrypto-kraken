---
status: resolved
---

# Engine trading telemetry — the egress ruling + order/position/PnL metrics

## Context — what

Split from [[T0042]] (2026-07-23 grooming) so the socket topic can archive cleanly at the 00068/00069 closeout. The engine ships its own logs to Grafana Cloud (`ZCRYPTO_SHIP_LOGS` → `--ship-logs`, spec 00068 D3/T4 — live on the engine after rollout Step 7) and serves `/metrics` (spec 00069). This topic carries the standing ruling on trading-data egress and the deferred positive work: emitting order/position/PnL detail as first-class metrics.

## Why this matters

The T0042-era sub-item treated "engine logs leave the trade-key host to a third-party SaaS" as a go-live gate, because live logs may carry order/position/PnL detail. The ruling below dissolves the gate; what remains is the constructive half — the same detail is *wanted* on dashboards, and a ruling recorded only in a session transcript is not durable.

## Findings so far

- **Owner ruling (2026-07-23): the egress is accepted, live trading included.** Order/position/PnL detail in logs shipped to Grafana Cloud is fine; no redaction or drop gate before 6b. The T0042-era alternatives (withhold `ZCRYPTO_SHIP_LOGS` from the engine service, or redact/parse before shipping) are consciously not taken.
- The transport for the future metrics is already live: the engine serves `/metrics` (00069, `cli/obs/metrics.py` + the engine's cycle gauges), so adding trading gauges is registry work, not infrastructure work.

## Resolution

**Resolved 2026-07-28 by redistribution, not by building.** The topic bundled a *ruling* with two pieces of *work* that belong to different owners and different times; splitting them is what makes each actionable, and the bundle is what kept all three stalled.

- **The egress ruling stays here, and this file is its durable home.** Owner ruling 2026-07-23: order/position/PnL detail in logs shipped to Grafana Cloud is **accepted, live trading included** — no redaction or drop gate before 6b, and the T0042-era alternatives (withhold `ZCRYPTO_SHIP_LOGS` from the engine, or redact before shipping) are consciously not taken. Nothing further is owed on it; an archived topic is the right resting place for a settled decision.
- **Emitting the metrics → [[T0018]]**, as a named `(autonomous)` bullet in the 6b executor's build list. It belongs there because it cannot be built until the order state machine exists to instrument, and because instrumenting *as* the state machine is written is what avoids the bolt-on that the capture daemon's own counters demonstrate the value of. Written as an explicit line rather than an implicit assumption, so it is visible among 6b's higher-stakes items.
- **Charting them → [[T0020]]**, whose scope is presentation and which is the one place that sees the fleet's whole telemetry picture. Recorded there as blocked on the executor — the only item in that package whose metrics do not yet exist.

Both landing sites also carry the keep-list requirement (the T0051 trap, both directions), so the requirement survives in the file that will act on it rather than only here.
