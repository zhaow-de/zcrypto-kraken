---
status: open
ripe_when: 'any one arm: RUNG 2 starts — the memo''s `**RUNG 2 — concentrated, time-boxed` entry records a start and not only its `DependsOn`; or an engine restart is planned while a position is open with nobody attending it; or `zcrypto-engine-cycle-stale` stops covering darkness on its own — `grep -c "uid: zcrypto-engine-cycle-stale" infra/grafana/alerts.yaml` reads 0, its `severity:` is no longer `critical`, or it gains a `zcrypto_exec_position` reference.'
---

# The position gauge lags a hand act until the next venue read

## Context — what

`zcrypto_exec_position` carries a position the engine did not trade — a hand trade or settle on Kraken's page while the engine runs, or a fill while the engine is down — only from spec `00119`'s D28 venue read on: the startup pass's first tick, or the re-read pass a socket's return or a mint arms, about hourly on this wheel. Between the act and that read the gauge shows the engine's own figure, so `zcrypto-engine-dark-with-exposure` reads that figure, not the account's, if the engine goes dark inside the span.

## Why this matters

It is the quiet direction of the gauge's error: a hand-opened position the engine goes dark beside reads as no exposure until the next read, and the dark-with-exposure page loses its *and money is exposed* half for that span. Detection does not depend on it — `zcrypto-engine-cycle-stale` reads no position and pages any dark engine at `critical` — so the cost is urgency, at the stakes of the rung that is running.

## Findings so far

- Split out of `T0187` at its resolution: this span is the staleness its acceptance of 2026-09-09 priced.
- The acceptance's other grounds: a hand act during an armed window is the owner's attended act; and the alert-layer alternative, a presence-aware node A, pages on a book the engine reported flat (`T0187`'s replay, `tests/test_infra_alert_rules.py`).
- The WARNING `the venue holds <qty> <symbol> where the Cache reads <qty>` marks each read that moved the gauge.

## Suggested next steps

- At the trigger, measure the span on the account's record: from the rung's ledger, the hand acts and the time each took to reach the gauge (the WARNING line's stamp against Kraken's trade time), and decide whether a shorter re-read interval while armed, or a read on each external order event, is owed.
