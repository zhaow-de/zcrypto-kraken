---
status: resolved
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

**The measurement trap, recorded because it produced the opposite answer first — and because the first write-up got the MECHANISM wrong too.** A `count_over_time` range query over this stream reads back as "every hour has lines", i.e. a continuous emitter. That reading was taken, believed, written down, and only then overturned by raw entries. The first explanation offered for it — "Loki forces ~240 min spacing regardless of the `step` requested" — is **false**, and was corrected at review after being tested directly: `step=600` returns 600 s spacing, so no step is being forced. **The real mechanism**: `count_over_time` emits *no sample at all* for a step whose range window is empty, so on a burst emitter only the burst hours survive and they sit one cycle apart. The cheap fix is the `or on() vector(0)` the rule already carries — with it, `step=1h` returns the zero hours (`11,0,0,0,11,0,0,0,21,…`). Loki was behaving correctly throughout; the wrong story would have sent the next reader to page raw entries and to distrust a working tool.

**Window: 6 h = the measured 4.00 h period + the fleet's own 2 h margin** (its ops timer canaries use 26 h for a daily emitter, i.e. 24 h + 2 h). Minimum lines observed in any 6 h window: **11**; max 34. `level=~".+"` confirmed present on the stream (values: `INFO`) before being relied on — an absent label would match nothing and park the rule permanently firing.

**Retention is not the binding constraint** this topic assumed it might be — the selector serves **12.6 days** (974 lines, back to 2026-07-26T13:35Z). The first cadence read spanned only 72 h of that, which is short of this topic's own `ripe_when` ("take the whole of it rather than assuming a span"); the full 12.6 days was then read at review and the characterisation is unchanged — rolling 6 h count still 11–34, no gap anywhere above 4.5 h, every one of ~76 cycle boundaries produced a burst.


- Verified 2026-08-05 while adding the ERROR rule: a repo-wide grep for `container="engine"` returned **zero** hits in `infra/grafana/alerts.yaml` before that change. Enumerating every `container=` selector in the file gives `capture`, `archive-pull`, `zcrypto-archive-pull`, `alloy`, `liquidations`, and `zcrypto-.*` — none reaches the engine.
- The engine ships via the same direct-to-Loki path as the capture daemon (`ZCRYPTO_LOG_SERVICE: engine` in `roles/engine/templates/compose.yaml.j2`), so the regression modes are shared: a formatter change, a shipper failure, or a label change all produce the same silent zero.
- **The owner considered and deliberately deferred this**, 2026-08-05, when approving the ERROR rule: the offered option was "add the rule and a log-dead canary for it", and the stated reason for declining was that the engine logs far less than capture, so the canary window needs measuring before it can be trusted. That reason is the whole content of this topic — the work is blocked on a measurement, not on a decision.
- Why a borrowed threshold will not do: the capture canaries use a 6 h window because both capture daemons emit continuously at hundreds of lines an hour. The engine emits per 4-hourly cycle, so its natural quiet periods are longer than capture's alarm threshold by construction. A canary copied from capture would page on every healthy inter-cycle gap; one guessed too wide would never fire. The same trap was measured on `ops-log-pipeline-dead` this iteration, whose 14-day floor turned out to be ~1.5 lines an hour against a summary implying far more.

## Resolution

**Resolved 2026-08-08 — the canary is live and verified by value.** `zcrypto-engine-log-dead` pushed via `infra/scripts/grafana-push.sh`; the folder went **63 → 64 rules** and the push reported **no orphaned rules**, confirming it was purely additive with nothing to prune.

**Verified by VALUE, not presence** — the distinction this repo insists on, because a rule reading 0 through a wrong selector looks identical to one that is healthy and quiet. The rule's own query returned **32** against the measured 11–34 band, far above its `< 1` threshold. And it is evaluating, not merely stored: `state=inactive health=ok lastError=none`, last evaluated 2026-08-08T04:23:30Z in 0.12 s.

**The panel half landed too** — `Logs` board panel 103 gains the engine's own dead-man series (refId `I`) with the same right-axis + threshold-at-1 override its seven siblings carry, so the `__panelId__` pointer now leads to a chart that actually plots what the rule evaluates. The panel's description gained the warning that makes it readable: the engine sits at 11–34 where capture sits at 747–1348, so on a shared linear axis a healthy engine renders near the floor — **read the threshold line at 1, not the height**.

The design and the measurement that produced it are in `## Findings so far` above; the window (6 h) and the reason it is not the 15 m of the ERROR rule it protects are recorded in the rule's own comment in `infra/grafana/alerts.yaml`, where the next reader will be standing.
