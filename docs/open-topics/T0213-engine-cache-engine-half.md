---
status: open
ripe_when: 'a milestone: Rung 1 has its verdict, which the `engine-probe-window` procedure in `infra/runbooks/engine-procedures.md` records in `docs/research/14.phase6-decisions.md` at its §6 item 9 — after which Rung 2''s design point opens the engine-side spec and plan of 00118'
---

# The engine's cache — the engine-side half of spec 00118

## Context — what

Spec `00118` decides a persistent cache for the engine — three Valkey nodes under Sentinel on a WireGuard mesh — and its plan `docs/plans/00118-engine-cache-infra.md` delivers the infrastructure half only: the nodes, the mesh, Valkey and Sentinel, their telemetry, and a compatibility probe of the pinned library's client. The engine-side half is a second spec and plan, written at Rung 2's design point on the owner's word of 2026-09-24. The plan's *Resolution* holds the one list of what it carries, from the proxy in the engine's compose project to D1's live proof — the restart with a margin position open whose boot reads the position at Kraken's entry price from the cache.

## Why this matters

The operating rule of 2026-09-23 — no engine converge or restart while a Kraken margin position is open — stands until a pin carries the entry-price fix upstream or this cache's live proof reads clean; Rung 1 runs under the rule, and every engine converge during it first closes its positions. The infrastructure plan leaves the nodes running and proven against the client, but nothing attaches them to the engine: without this half the rule has one lift left, the upstream fix that is on hold. The half is held back deliberately — Rung 1 enters without it, and the second plan is designed once Rung 1's readings say what a restart with a position open must recover.

## Findings so far

- The plan's *Resolution* lists which of spec `00118`'s decisions, and which parts of them, are the engine half's, and names this topic as the half's home; the plan's Global Constraints keep every task off `cli/`.
- The library fact that shapes the half: nautilus's Redis backing connects to one fixed `host:port` with no Sentinel lookup (measured in the stub and the binary, 2026-09-24), so the proxy is the engine's only view of the set.
- The trigger is the verdict entry the `engine-probe-window` procedure writes into `docs/research/14.phase6-decisions.md` at its §6 item 9, read from the entry itself, since the procedure writes no tag a grep could key on.

## Suggested next steps

- **(design, after the trigger)** Write the engine-side spec and plan under `00118`'s decisions: read the infrastructure plan's *Resolution* and, in `docs/specs/00118-engine-cache-design.md`, each decision it lists as the engine half's, then brainstorm the second pair with the owner — the proxy's compose service, caps and health checks; the library's `RedisCacheConfig` fields against the proxy's address; the startup pass; the harness and its CI service; the live proof's window under the operating rule — and take it through `zcrypto-plan-review` before Task 1.
- **(read, at the trigger)** Read Rung 1's verdict entry and its `unmatched` and reconciliation readings in `docs/reference/adapter-verification/2.0.0rc6.dev20260921.md`: what a restart with a position open must recover is what the engine half's D11 startup pass is designed against.
