---
status: partial
ripe_when: "an evaluation statement: daily-pass journal entries on seven consecutive days from 2026-10-10, each carrying the pass's comparison line at `compare: <n> nodes × 24 instants, 0 differences` — check: `git fetch -q origin && git grep -h -e '^## 20' -e 'compare: ' origin/ops-journal -- 'docs/reference/ops-journal/20*.md'` lists entries on seven consecutive days from 2026-10-10 on, each followed by its `compare: … 0 differences` line"
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
- **R4's db1**: the command count, `job="valkey"`, 38 distinct commands by `redis_commands_total`, seven families answering, 258 for the latency buckets.
- **R4's db2 and db3, 2026-10-05**: `db1`'s day read of its Alloy headroom came first, 0.171 against the bar of 0.9; then `db2` converged at 20:48:54Z and `db3` at 21:03:31Z, Valkey and Sentinel untouched on each, each node's hour of log lines equal on both stacks.
- **The Alloy wave, 2026-10-07**: every `observed` host moved to v1.20.1, the NAS and the capture pair dual-shipping in it, the primary's Alloy recreated last at 12:14:42Z. At 2026-10-08T15:54:01Z the node read `v1.20.1` alone in `alloy_build_info`, and every job Cloud reads for each host on the node too, each above Cloud's count; its head read 25,189 on 2026-10-07 and 26,373 then, against 10,222 alone — above the plan's 21,022 to 22,222, under the bar of 40,000. The boundary reading is Cloud 5 and the node 6, off by the sample at `t`, written into the spec's measured basis.
- **The comparison's earliest day is 2026-10-10**: the primary's recreate plus 50 h is 2026-10-09T14:14:42Z.

## Done so far

- Phase 1, the node taking a shadow push: spec `docs/specs/00121-self-hosted-observability-design.md` and plan `docs/plans/00121-mon-node.md`, merged as PR #652 and rolled out 2026-10-03; the node `zcrypto-mon` (`docs/reference/fleet.md`) carries every rule at `https://zcrypto-mon.zhaow.me`, paging the shadow channel, and its acceptance's two findings were fixed as PRs #653 and #654.
- Phase 2 inside the box: plan `docs/plans/00121-dual-shipping.md`; PR #656 (the bridgehead dual-ships, the comparison script, the drill sections, the push's orphan line naming a skipped group's live rule), PR #657 (ops dual-ships, the node pings its own dead-man, the self-check naming the series it did not find), PR #658 (the cache nodes dual-ship) and PR #659 (`prometheus$` out of the node's blacklist, W1's reading); R1, the bridgehead, and R2, ops, on 2026-10-04; R3, the three node drills W1, W2 and W3, the same day, each an entry in `docs/reference/drill-log.md`; R4, the three cache nodes, `db1` on 2026-10-04 and `db2` and `db3` on 2026-10-05.
- The Alloy wave: spec `docs/specs/00123-one-alloy-version-design.md` and plan `docs/plans/00123-one-alloy-version.md`, merged as PR #670 (T0219), and its wave of 2026-10-07, which carried phase 2's NAS and capture-pair steps inside the box: every `observed` host's Alloy at v1.20.1 (`docs/reference/fleet-pins.md`), the NAS, `zcrypto-red` and `zcrypto` dual-shipping, the primary last and attended.
- W4, the shipper-stop drill on the secondary (plan 00123's R11), on 2026-10-08, its entry in `docs/reference/drill-log.md`: both copies of the Alloy-dark rule `Alerting` 15 min 16 s from the stop against about 16 minutes, the node reading `up{host="zcrypto-red"}` absent and not 0; the secondary's Alloy `since` cell re-trued in `docs/reference/fleet-pins.md`.

## Suggested next steps

- R12's pull request of its own: `COMPARISON_FROM = date(2026, 10, 10)` in `infra/scripts/ops_daily.py`, without which no pass compares and the trigger cannot fire.
- Then phase 3, the cutover of paging, by its own design, and phase 4, the retirement of the Grafana Cloud leg and the keep-alive: each takes its own plan once the phase before it has been read.
