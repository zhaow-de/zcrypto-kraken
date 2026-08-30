---
status: open
---

# The go-live drill program — executing spec 00105

## Context — what

Spec `00105` (merged in PR #350, 2026-08-29) defines the drill program that [[T0049]] set out to build: twenty failure scenarios in three tiers, a seven-part PROCEDURE shape per drill with derived bounds, the ops drill log the master plan's Stage-6b artifact list names, one resilience alert, and the Grafana-dark procedure. A spec carries no status, so this topic is the program's git-tracked residual holder: what of `00105` has landed, what is executed, what is parked for rung 1, and what a run discovered that the spec did not foresee.

## Why this matters

The go/no-go clause in `docs/research/00.master-plan.md` §12 requires *ops drills passed (kill-switch, WS-loss, restart-reduce-only)*; the engine has never been armed, so every order-path drill has harness evidence at most, and the telemetry-tier paths have been proven only by whichever incidents happened to fire them. Without a topic, a drill that surfaces a defect mid-window has nowhere to register the remainder except a report nobody re-reads.

## Findings so far

- **The spec's own inventory** (`00105` D3/D4): the telemetry tier — C (ingest plane dark), C′ (Grafana watchdog), I (watermark), J′ (the `/fail` route), K (Alloy kill), O (timer death), P+R (the secondary), Q (phone push), plus the proven tier F/H/J/L/M/N/T with N due for re-verification because [[T0048]]'s fix changed its path after its proof; the order-path tier — A1, A2, B, D, E, E′, F2, G — written now, run at rung 1.
- **Nine of ten telemetry drills need no human at the keyboard**: under the owner's 2026-08-29 authorization (all Alloy actions; any container/unit/timer start–stop the loop can revert itself; only a converge forbidden), J′, K, O, I, both halves of C, C′'s staleness route, N and R run autonomously with the Kraken maintenance feed read immediately before each; P (its restore is a converge), C′'s `/fail` route (a converge) and Q's phone reading need a person.
- **The pushes come after the merge, never from the branch**: `infra/scripts/grafana-push.sh`'s header (lines 8–10) forbids pushing summaries that cite repo paths from an unmerged branch — the new alert is pushed from merged `develop`.
- **Drill I's throwaway healthchecks check must be created with `channels` naming the Slack integration** — a check made through the API inherits no notification integrations ([[T0085]]'s finding), so an unchannelled check breaches in silence and would record a false FAIL of the dead-man domain.
- **The four engine enhancements the order-path tier needs** — `00106` flatten ([[T0159]]), a `rest-hold` plan mode, cancel-on-stop (ruled only after drill G measures the venue's behaviour), re-cancel-on-reconnect — are registered as build-sequence items in [[T0018]].

## Suggested next steps

- **(autonomous)** ~~Cut the branch; write plan `00105`; cold spec+plan review~~ — **done**: `feat/00105-go-live-drill-program` carries the spec and a plan through four review-and-fix rounds (round 5's report is still owed; see the memo's Block B). What remains is to execute: `infra/runbooks/drills-telemetry.md`, `drills-order-path.md`, `docs/reference/drill-log.md` + its shape test and mutation probe, `zcrypto-engine-dark-with-exposure` pinned to `up{job="engine_app",host="zcrypto"}` + its `engine.md` section, `observability.md#grafana-cloud-dark`, the README rows, the master plan's artifact line naming `drill-log.md`.
- **(autonomous)** Execute J′ from the workstation — `engine_healthcheck_url` read through the vault resolver from `group_vars/engine_host/vault.yml`, `curl <url>/fail`, both pages read by value, the first drill-log entry, then a success ping to clear it.
- **(autonomous)** Execute the ops-node and secondary drills in this order, each reverted and verified by value before the next, the maintenance feed read immediately before each, the primary read by value before any secondary induction: K → O → I (channels explicit) → C ops half (2 h) → C secondary half (2 h) → C′ staleness route → N → R (cap = `capture-redundant`'s timeout + grace + one evaluation; the reconcile ledger read at the next booking tick shows the primary whole and the secondary's silence as `trade_deficit` at most) → Q's machine timestamps (rule `activeAt` and Slack message) for one `metrics`, one `logs`, one healthchecks-native page. Each: a drill-log entry and a section amendment, committed as it lands.
- **(autonomous)** Whole-branch cold review; closeout (the changelog entry; the master plan names the drill log); PR; merge on CI green; then push the new alert from merged `develop` and read its first sample by value.
- **(human)** P on the secondary — a nonexistent image reference in the rendered compose, the unit's `Restart=always` loop, the dead-man's time to page, **restore by a secondary converge with the command written down first**; C′'s `/fail` route — the probe-URL converge on ops and its revert; Q's phone timestamps added to the entries the autonomous run wrote. One window each, the maintenance feed read at planning and immediately before. A single-reviewer round; a PR of the entries and amendments; merge.
- **(human)** The order-path tier at rung 1 — E, E′, G, F2, A1, A2, D, B — after `00106` and `rest-hold` are built and converged; G's measurement rules cancel-on-stop; F2's result decides re-cancel-on-reconnect ([[T0018]]).
