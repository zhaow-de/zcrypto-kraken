---
status: open
ripe_when: the dashboards/alerting design iteration (00069's declared out-of-scope successor) — or any earlier iteration that adds live-order execution telemetry
---

# Engine trading telemetry — the egress ruling + order/position/PnL metrics

## Context — what

Split from [[T0042]] (2026-07-23 grooming) so the socket topic can archive cleanly at the 00068/00069 closeout. The engine ships its own logs to Grafana Cloud (`ZCRYPTO_SHIP_LOGS` → `--ship-logs`, spec 00068 D3/T4 — live on the engine after rollout Step 7) and serves `/metrics` (spec 00069). This topic carries the standing ruling on trading-data egress and the deferred positive work: emitting order/position/PnL detail as first-class metrics.

## Why this matters

The T0042-era sub-item treated "engine logs leave the trade-key host to a third-party SaaS" as a go-live gate, because live logs may carry order/position/PnL detail. The ruling below dissolves the gate; what remains is the constructive half — the same detail is *wanted* on dashboards, and a ruling recorded only in a session transcript is not durable.

## Findings so far

- **Owner ruling (2026-07-23): the egress is accepted, live trading included.** Order/position/PnL detail in logs shipped to Grafana Cloud is fine; no redaction or drop gate before 6b. The T0042-era alternatives (withhold `ZCRYPTO_SHIP_LOGS` from the engine service, or redact/parse before shipping) are consciously not taken.
- The transport for the future metrics is already live: the engine serves `/metrics` (00069, `cli/obs/metrics.py` + the engine's cycle gauges), so adding trading gauges is registry work, not infrastructure work.

## Suggested next steps

- **(at the dashboards iteration)** Design and emit order/position/PnL metrics from the engine's `/metrics` endpoint — gauges for position/PnL state, counters for orders/fills — inside the active-series budget, and admit every new family through the Alloy keep-lists in the same change (both directions of the T0051 trap: published-but-unadmitted and admitted-but-unpublished).
- **(same iteration)** The dashboard panels over them — dashboards are that iteration's whole subject; this topic only guarantees the metrics exist by then.
