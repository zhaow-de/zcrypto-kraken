---
status: resolved
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
- **The engine image this half's rollout builds carries spec `00119`'s change** — the reprice ladder, the ledger reader, the startup sweep and the Cache handles the executor reads through, T0018's build-list item of 2026-09-26, and its two drill-day lines: the re-read pass, a socket-state subscription in `ShadowStrategy.on_start`, `_cached_order` withholding an order a minted terminal closed and the startup sweep re-run on the executor's tick with a bare-client cancel by txid, which this half's redesign of the startup pass keeps working, the gate's idle refresh, a `SystemStatus` GET a minute while no plan runs, and the position gauge's startup seed carried forward through the journal's fills after its venue record and settled from the venue's own holdings at the startup and re-read passes — on the owner's word of 2026-09-26; if this half's plan is not converged within a week of that pair's merge, the pair takes its own rollout through `.claude/skills/zcrypto-rollout-image/SKILL.md`'s engine section, and that date is an arm on T0018's trigger from the pair's closeout.

## Resolution

Delivered by spec `00120` (`docs/specs/00120-engine-cache-engine-half-design.md`) and its plan `docs/plans/00120-engine-cache-engine-half.md`, the branch `spec/00120-engine-cache-engine-half`: the cache table and the Kraken currency registration, the backing wired behind the config with the boot line, the two-process restart harness, the startup pass under a restored Cache, the engine role's proxy and the secrets' move, and the telemetry and pages. The rollout and the live proof are the plan's Rollout section, attended; the operating rule is the test `engine-restart-margin-position` in `infra/runbooks/engine-procedures.md` now states, and its other lift, upstream #5065, stands on T0158's re-keyed trigger. The cache-link converge on the engine host takes the engine window from this branch on.
