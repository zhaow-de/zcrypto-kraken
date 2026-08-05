---
status: open
ripe_when: a 30-day `count_over_time({host="zcrypto", container="engine"}[…])` read exists — the engine's real log cadence is the one input the canary window cannot be chosen without, and it is a single Grafana query against data that is already being collected
---

# The engine's ERROR-log rule can read zero forever and nothing notices

## Context — what

The trading engine ships its logs straight to Loki as `container="engine"` on the capture primary. Until this iteration nothing alerted on them at all; `Engine · ERROR logs` (`zcrypto-engine-error-logs`) now does, mirroring the capture daemon's rule.

That rule is **presence-fired**: it fires when ERROR or CRITICAL lines appear. It is therefore silent in exactly two situations that look identical from outside — the engine is healthy, or the engine's log-shipping path has regressed and no line is arriving to be matched. Every other shipping stream on the fleet is protected against the second case by a paired dead-man canary (`zcrypto-capture-log-dead-primary`, `-secondary`, and the four ops variants), which fires when a stream that should always carry lines goes quiet. The engine has no such sibling.

## Why this matters

The engine holds the live Kraken trade key and is the only component that can move money. Its ERROR rule is the sole log-side signal covering it, and a presence-fired rule with no canary behind it degrades silently: the ship path breaks, the rule reads zero, the board shows a flat line, and the absence of pages reads exactly like health. That is the failure class the capture canaries exist to prevent, and the reason the fleet added them — a parse or transport regression makes every ERROR rule's silence meaningless, which is why `Logs · lines dropped before reaching Loki` and the per-host canaries were built.

The gap was closed for capture and for ops. The engine is the one stream where it was never closed, and it is the highest-consequence one.

## Findings so far

- Verified 2026-08-05 while adding the ERROR rule: a repo-wide grep for `container="engine"` returned **zero** hits in `infra/grafana/alerts.yaml` before that change. Enumerating every `container=` selector in the file gives `capture`, `archive-pull`, `zcrypto-archive-pull`, `alloy`, `liquidations`, and `zcrypto-.*` — none reaches the engine.
- The engine ships via the same direct-to-Loki path as the capture daemon (`ZCRYPTO_LOG_SERVICE: engine` in `roles/engine/templates/compose.yaml.j2`), so the regression modes are shared: a formatter change, a shipper failure, or a label change all produce the same silent zero.
- **The owner considered and deliberately deferred this**, 2026-08-05, when approving the ERROR rule: the offered option was "add the rule and a log-dead canary for it", and the stated reason for declining was that the engine logs far less than capture, so the canary window needs measuring before it can be trusted. That reason is the whole content of this topic — the work is blocked on a measurement, not on a decision.
- Why a borrowed threshold will not do: the capture canaries use a 6 h window because both capture daemons emit continuously at hundreds of lines an hour. The engine emits per 4-hourly cycle, so its natural quiet periods are longer than capture's alarm threshold by construction. A canary copied from capture would page on every healthy inter-cycle gap; one guessed too wide would never fire. The same trap was measured on `ops-log-pipeline-dead` this iteration, whose 14-day floor turned out to be ~1.5 lines an hour against a summary implying far more.

## Suggested next steps

- **(autonomous)** Measure the engine's log cadence: `count_over_time({host="zcrypto", container="engine"}[1h])` and `[6h]` minima over 30 days, and separately the longest observed gap. The engine's 4-hourly cycle means the distribution is bimodal — a burst at each boundary, near-silence between — so the minimum over a window shorter than the cycle is the wrong statistic; take the minimum over a window that spans at least one boundary.
- **(autonomous)** Derive the canary window from the longest healthy gap with the same margin the fleet's other dead-men use, and add `Engine · log pipeline dead` in the shape of `zcrypto-capture-log-dead-primary` — `lt 1` on the `or on() vector(0)` arm, `noDataState: Alerting`, host and container written into the summary as literal words (the arm carries no labels, so interpolation renders empty at exactly fire time).
- **(autonomous, same change)** Give it a panel on the `Logs` board's by-machine rate panel and a `__dashboardUid__`/`__panelId__` pointer, matching how the other canaries are wired.
- **(check first)** Confirm the engine actually emits at every cycle rather than only on state changes — if it can legitimately log nothing across a whole cycle, a line-count canary is the wrong instrument and the right one is a staleness read on `zcrypto_engine_cycle_completed_at_seconds`, which is already alerted. In that case this topic resolves as a measured non-issue rather than a rule.
