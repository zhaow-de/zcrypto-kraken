---
status: partial
ripe_when: 'any one arm: rung 2''s exit report is recorded with spec `00092`''s slot S4 read — check: `docs/research/14.phase6-decisions.md` carries the exit report entry, due by Fri 2026-11-06 (`engine-rung-2-box` step 9 in `infra/runbooks/engine-procedures.md`); or the first hand act on a basket coin under rung 3 — check: `uv run python infra/scripts/grafana-query.py ''increase(zcrypto_exec_external_events_total{host="zcrypto",disposition="unmatched"}[7d])''` reads above 0 over a week after rung 3''s entry — a coarse proxy, which a cancel, a non-basket coin or an attended pass moves too, read against the engine''s log line `external order event ignored: OrderFilled for … on <basket>/EUR.KRAKEN`; or `zcrypto-engine-cycle-stale` stops covering darkness on its own — `grep -c "uid: zcrypto-engine-cycle-stale" infra/grafana/alerts.yaml` reads 0, its `severity:` is no longer `critical`, or it gains a `zcrypto_exec_position` reference'
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

## Done so far

- **The read on each unmatched external fill — spec `00092` D12, its plan's Task 7 (iter-174, PR #666)**: `_on_external_event`'s unmatched branch in `cli/engine/executor.py` arms the re-read pass (`_arm_reread_after_mint`) for an `OrderFilled` alone, so the pass runs at the first tick with nothing in flight, holds no row for the hand act and settles the holdings: the gauge takes the venue's figure within a tick of the act plus the pass's one read, where it waited for the next socket return (commit `0824f5360`). A cancel or any other unmatched event arms nothing.
- **Only while the engine is armed** (`_gate_armed`, both keys up at the newest gate evaluation): a fill while disarmed is the operator's — the attended passes that sign on the engine's key run disarmed, and a holdings read beside their fills would race their nonce — and a later pass's read settles the gauge (commit `1c6ca1613`); the orchestrator's ruling, recorded in `[iter-174]` as provisional, pending the owner's word. Under rung 3 the boundary's book read settles the gauge every four hours besides (`00092` D2).

## Suggested next steps

- **(measurement — rung 2's exit report, slot S4)** If the box held a hand act: the span from its Kraken trade time (the ledger export's `time`) to the WARNING `the venue holds <qty> <symbol> where the Cache reads <qty>` that moved the gauge — the frozen image's lag, before the read above; the exit report records it, or that the box held none (rung 2 forbids one).
- **(measurement — rung 3's first hand act on a basket coin)** The same span on the image carrying the read, the engine armed: within a tick plus one holdings read of the act, and the topic resolves on that reading; past it, the engine's log names why (the arm, the pass's tries, a socket held down) before a shorter standing read is weighed again.
