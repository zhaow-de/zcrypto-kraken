---
status: open
ripe_when: 'a milestone: Rung 1 has its verdict, which §6 item 9 of the `engine-probe-window` procedure in `infra/runbooks/engine-procedures.md` records in `docs/research/14.phase6-decisions.md` — after which Rung 2''s design point opens the engine-side spec and plan of 00118'
---

# The engine's cache — the engine-side half of spec 00118

## Context — what

Spec `00118` decides a persistent cache for the engine — three Valkey nodes under Sentinel on a WireGuard mesh — and its plan `docs/plans/00118-engine-cache-infra.md` delivers the infrastructure half only: the nodes, the mesh, Valkey and Sentinel, their telemetry, and a compatibility probe of the pinned library's client. The engine-side half is a second spec and plan, written at Rung 2's design point on the owner's word of 2026-09-24. The plan's *Resolution* holds the one list of what it carries, from the proxy in the engine's compose project to D1's live proof — the restart with a margin position open whose boot reads the position at Kraken's entry price from the cache.

## Why this matters

The operating rule of 2026-09-23 — no engine converge or restart while a Kraken margin position is open — stands until a pin carries the entry-price fix upstream or this cache's live proof reads clean; Rung 1 runs under the rule, and every engine converge during it first closes its positions. The infrastructure plan leaves the nodes running and proven against the client, but nothing attaches them to the engine: without this half the rule has one lift left, the upstream fix that is on hold. The half is held back deliberately — Rung 1 enters without it, and the second plan is designed once Rung 1's readings say what a restart with a position open must recover.

## Findings so far

- The library fact that shapes the half: nautilus's Redis backing connects to one fixed `host:port` with no Sentinel lookup (measured in the stub and the binary, 2026-09-24), so the proxy is the engine's only view of the set.
- The procedure writes no tag a grep could key on, so the trigger is read from the verdict entry itself.
- **The kept reducer's intent after a restart is the engine half's** (spec `00119` D14, 2026-09-26): the startup pass's sweep settles every `pending` intent of the window from its rows except one with an open row the pass sent no cancel for — the reducer it keeps resting among them — since no process runs that plan and the row is the live record; the case is unreachable under the operating rule above and becomes reachable when this half lifts it, so the startup pass this half redesigns (00118 D11) settles that intent, at the reducer's terminal or by a rule of its own.
- **The engine image this half's rollout builds carries spec `00119`'s change** — the reprice ladder, the ledger reader, the startup sweep and the Cache handles the executor reads through, T0018's build-list item of 2026-09-26, and its two drill-day lines: the re-read pass, a socket-state subscription in `ShadowStrategy.on_start`, `_cached_order` withholding an order a minted terminal closed and the startup sweep re-run on the executor's tick with a bare-client cancel by txid, which this half's redesign of the startup pass keeps working, and the gate's idle refresh, a `SystemStatus` GET a minute while no plan runs — on the owner's word of 2026-09-26; if this half's plan is not converged within a week of that pair's merge, the pair takes its own rollout through `.claude/skills/zcrypto-rollout-image/SKILL.md`'s engine section, and that date is an arm on T0018's trigger from the pair's closeout.

## Suggested next steps

- **(design, after the trigger)** Write the engine-side spec and plan under `00118`'s decisions: read the infrastructure plan's *Resolution* and, in `docs/specs/00118-engine-cache-design.md`, each decision it lists as the engine half's, then brainstorm the second pair with the owner and take it through `zcrypto-plan-review` before Task 1.
- **(read, at the trigger)** Read Rung 1's verdict entry and its `unmatched` and reconciliation readings in `docs/reference/adapter-verification/2.0.0rc6.dev20260921.md`: what a restart with a position open must recover is what the engine half's D11 startup pass is designed against.
- **(design, with the spec)** Re-gate the engine host's cache-link converge behind the engine window once the engine routes the cache through zcache0 — the role's handler restarts wg-quick@zcache0 on any conf change.
