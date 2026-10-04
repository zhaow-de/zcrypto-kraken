---
status: partial
ripe_when: "the day read of zcrypto-valkey1's Alloy headroom under its bar, then db2 and db3; the NAS and the capture pair once the box closes, 2026-11-01 or a week later"
---

# Self-hosting the metrics, logs and alerting stack in place of Grafana Cloud's free tier

## Context — what

The fleet ships metrics and logs with Grafana Alloy to Grafana Cloud's free tier, where the dashboards and the alert rules of `infra/grafana/` evaluate and page Slack. This topic is the move of that stack onto one self-hosted node the project runs itself: one additional 4 GB Linode, no HA, Docker-free, native apt packages.

## Why this matters

- The free tier has no ticket support, only a community forum, and no SLA remedy.
- Its faults reach the pager and nothing in the repo can fix them: the rule evaluator timing out against its own Prometheus (2026-09-28 to 09-30, `docs/reference/ops-journal/2026-09.md`), `/api/health` answering 404 in bursts, and hibernation (`docs/open-topics/archive/T0181-a-503-cannot-separate-hibernation-from-outage.md`).
- The rules that watch a held position, the engine dark with exposure and the stale cycle among them, evaluate there.

## Findings so far

The assessment of 2026-10-01 is `docs/research/92.self-hosted-observability-assessment.md`; its conclusions follow, and its figures are the spec's to re-derive.

- **The stores are the choice, not Grafana.** Grafana holds no metrics or logs. Keeping Grafana as the evaluator keeps the rule file, the dashboards and the push script in their present shape.
- **Recommended: Grafana OSS on SQLite, one Prometheus as the remote_write receiver, single-binary Loki.** No alert expression is rewritten, and the evaluator's call to its store becomes a local one.
- **OSS, not the unlicensed Enterprise build**: every Enterprise feature is licence-gated, so unlicensed it adds nothing here.
- **SQLite, not PostgreSQL**: the database holds Grafana's own state alone. A second Grafana instance, or `database is locked` errors, would force PostgreSQL.
- **Prometheus, not Mimir**: Mimir buys scale, replication and object-store retention, none of which one small node needs. A second node, or retention moved to object storage, would flip it.
- **VictoriaMetrics and VictoriaLogs are rejected**: VictoriaLogs has no apt package and its query language would force a rewrite of every log rule; VictoriaMetrics computes `increase`, `delta` and `changes` differently at a series' first sample and after a gap, which changes what some rules page on.
- **It does not help rung 2's box.** Its pre-entry gates come first, through Sun 2026-10-04; Grafana Cloud stays the alert evaluator through the box, and nothing from this work converges `zcrypto` inside it.
- **What gets worse**: one more host to patch and repair, with no HA; while it is down, nothing evaluates the rules; its history is lost with the host unless backups are bought; a monthly cost where there was none.
- **Size**: a new host and role, dual-shipping in every Alloy config, a cutover and a retirement — large, with many attended converges.
- **Not verified by the assessment**: the Prometheus engine version Grafana Cloud runs, which decides whether range selectors read identically on both stacks; the memory Prometheus and Loki need at this scale; the unlicensed Enterprise build's licence text.
- **R0, 2026-10-04T09:36:02Z**: the node alone held 10222 head series, `prometheus_tsdb_head_series{host="zcrypto-mon"}`; the instant is what the deploy-log audit's `--since` takes from here.
- **R1, the bridgehead, complete**: after the converge the node read `zaccess` at self 389 and unix 167 against Grafana Cloud's unix 37 and self 1, the one admitted addition; the head 10804; `samples_failed_total` 0 for both urls; the shipper-loss row 0 after an hour.
- **R2, ops, complete**: the converge `changed=3`, the recreate at 13:38:42Z on the same digest with 0 restarts; at +63 min the node read `ops` at liquidations_app 18, self 573, healthchecks 67, unix 493 against Cloud's 14, 7, 13, 331, its log streams equal to Cloud's less the 7 lines drill W1 dropped; the flush resolved the node's two copies of the ops log rules.
- **P2, the log fan-out**: 900 of 900 lines reached the Cloud leg over 15 min with the mon leg dead, the mon leg's first give-up at `level=error` 7 min 26 s in — the premise true, written into the spec's measured basis.
- **W1**: four bare Prometheus restarts of 349 to 391 ms and one Loki restart of 948 ms paged nothing, so `prometheus$` left the blacklist in PR #659; the ordered restart paged nothing; the edge stop paged `zcrypto-mon-ingest-dark` at +11:24, about 80 s after the seven node copies, and the Alloy-dark pair at +15:59.
- **W2**: the check paged at its last ping + 20 min 02 s, the watchdog 6 min 09 s behind it; the WAL replayed the outage whole, 120 and 120 on both stacks; 23 lines lost, `mon-dark`'s first figure.
- **W3**: 38 min 59 s from the firewall step to the first evaluated rule, `mon-dark`'s second figure; the check at its last ping + 20 min 02 s, the watchdog 6 min 29 s behind it; the four must-holds held.
- **R4's db1, 2026-10-04 20:45:20Z**: the converge `changed=3`, Alloy recreated on the same digest; at +2 min the node read `zcrypto-valkey1` at valkey 864, self 564, sentinel 112, unix 229 against Cloud's 17, 3, 11, 54; the command count, `job="valkey"`, 38 distinct commands by `redis_commands_total`, seven families answering, 258 for the latency buckets.

## Done so far

- Phase 1, the node taking a shadow push: spec `docs/specs/00121-self-hosted-observability-design.md` and plan `docs/plans/00121-mon-node.md`, merged as PR #652 and rolled out 2026-10-03; the node `zcrypto-mon` (`docs/reference/fleet.md`) carries every rule at `https://zcrypto-mon.zhaow.me`, paging the shadow channel, and its acceptance's two findings were fixed as PRs #653 and #654.
- Phase 2 inside the box: plan `docs/plans/00121-dual-shipping.md`; PR #656 (the bridgehead dual-ships, the comparison script, the drill sections), PR #657 (ops dual-ships, the node pings its own dead-man), PR #658 (the cache nodes dual-ship) and PR #659 (`prometheus$` out of the node's blacklist, W1's reading); the three node drills W1, W2 and W3 run 2026-10-04, each an entry in `docs/reference/drill-log.md`; the first cache node converged the same day.

## Suggested next steps

- Phase 2's remainder: `zcrypto-valkey1`'s day read, then `db2` and `db3`; after the box, the NAS and the capture pair, the primary last and attended, then the after-box records. Two items the rollout left are its to carry: `zcrypto-mon-selfcheck.py`'s "no scheduler tick" naming the absent series; `grafana-push.sh`'s `ORPHAN` line for a rule of a skipped group.
- Phase 3, the cutover of paging, and phase 4, the retirement of the Grafana Cloud leg and the keep-alive: each takes its own plan once the phase before it has been read.
