---
status: open
ripe_when: the PR #191 closeout — rollout Step 8's `GRAFANA_PRUNE=1` push confirms `zcrypto-alloy-docker-sd-wedged` deleted from Grafana (the orphan was reported, correctly undeleted, by the 2026-07-22 upsert push); then rewrite the Defect-1 diagnostic section IN PLACE (never append a retraction — `.claude/rules/agent-ops.md`) to the retired reality and ARCHIVE. All other former triggers are dead: the defect surface (`discovery.docker` + `loki.source.docker`) is deleted fleet-wide by 00068 D6/D8, the repo-side cleanup (keep-lists purged of `prometheus_sd_*`, the alerts.yaml rule removed, the series test inverted to pin ABSENCE) landed in 00068/00069, and the upstream trackers were dropped 2026-07-23 (owner's tecnativa-precedent ruling; see Findings)
---

# Alloy's docker tailer does not survive container recreation

## Context — what

When a NAS compose service is **recreated** (`docker compose up -d` after a compose/env change — new container ID), Alloy's `loki.source.docker` tailer keeps retrying the **dead** container ID every ~5 s (`error inspecting Docker container … No such container`) and never begins tailing the replacement. Log shipping for that service goes dark while everything else looks healthy. First observed 2026-07-15/16: two archive-pull recreations (16:46 Z re-pin, 21:36 Z panel-channel activation) left Loki blind for hours until the `NAS · archive-pull stalled` dead-man fired at ~22:1x Z — **the alert working exactly as designed** (it is the one rule that fires on monitoring-pipeline death, and this was the first real fire through the new Slack-only path).

## Why this matters

Every future NAS deploy that recreates a container silently kills its log shipping — the ERROR-log alert goes green-because-blind, dashboards stop, and only the dead-man (3 h window) eventually notices. The failure is quiet, recurring, and operator-induced, which is exactly the class that erodes trust in the instrument.

## Findings so far

**CORRECTION (2026-07-20): this topic's original root cause was wrong, and backwards.** It read:

> Root cause is in Alloy's tailer lifecycle, not discovery: `discovery.docker` refreshes targets, but the running `loki.source.docker` tailer set doesn't reap the dead ID or adopt the new one.

It is **discovery, not the tailer**. This topic's own recorded evidence already contradicted the tailer theory — it notes *"zero mentions of the new container ID in Alloy's own logs post-recreate"*. Had discovery surfaced the new container, the tailer would have started it and logged so. **Silence means the new container never reached `loki.source.docker` at all.** Established by a separate session with the Alloy source checked out; the details below are not re-derivable from this repo, so treat them as given and do not extend them by inference.

**`loki.source.docker` reconciles correctly, and has since Alloy 1.0** (proven two ways): a test simulating a recreate — targets changing from container ID A to ID B — passes, stopping the dead tailer and scheduling the replacement; and our pinned digest `sha256:4f6ddc56…` is **Alloy v1.17.1**, whose component source is byte-identical to Alloy `main`, so that result applies to exactly what we run. The only reap bug this component ever had was a Grafana Agent–era one fixed in December 2023, before Alloy 1.0 — it never shipped in any Alloy 1.x.

The single reported problem is really **three separate defects**.

### Defect 1 — `discovery.docker` can freeze permanently (the leading explanation for the July 15/16 incident, NOT proven)

Two upstream gaps combine so the target list can freeze forever:

- Prometheus's Docker service discovery attaches an HTTP client timeout **only** when the host scheme is `http`/`https`. For a `unix://` socket — what we use — it falls through to a bare Docker client with **no request timeout at any layer**.
- The refresh loop calls the refresh function synchronously with a long-lived context and **no per-call deadline**.

So one stalled Docker API call on the socket wedges discovery permanently. The cached target list stays frozen at the last-good snapshot — which still holds the **dead** container ID and lacks the **new** one — and `loki.source.docker` faithfully keeps tailing what it was last told, retrying the dead ID every 5 s. Only an Alloy restart recovers. That accounts for every observed symptom: intermittent, indefinite, nothing logged (a hang is not an error), everything else healthy, restart-only recovery.

**This is the leading explanation, not a confirmed fact.** The code makes it possible and it is consistent with what we saw, but no wedged instance has ever been caught in the act. A **competing explanation produces an identical symptom**: a persistently *erroring* refresh also freezes the target list, and that is deliberate — the refresh loop withholds updates on error so a transient blip does not drop every target.

**The diagnostic that separates them** — read Alloy's local metrics endpoint on port 12345 *while it is happening* (or proactively, since it may be latent):

| observation | conclusion |
|---|---|
| `prometheus_sd_refresh_duration_seconds_count{mechanism="docker"}` **frozen** | hung refresh — defect 1 confirmed |
| that counter incrementing while `prometheus_sd_refresh_failures_total{mechanism="docker"}` climbs | persistent error instead |
| counter incrementing, no failures, targets still stale | neither — the diagnosis is wrong |

**These were invisible in Grafana Cloud until 2026-07-20** — and for two reasons, only one of which was originally recorded: the keep-list omitted them, AND nothing scraped Alloy's own `/metrics` endpoint, so they never reached the pipeline to be kept or dropped. Both are now fixed (see *Suggested next steps*). Reading port 12345 on the host remains the way to capture them **while an instance is wedged**, since that is the state a restart destroys.

**Upstream status:** tracked as grafana/alloy#3054, open since March 2025, no fix. The root cause is in `prometheus/prometheus`, not Alloy, and **nothing has been filed there** — an Alloy maintainer explicitly declined to act *because* no upstream report existed. Alloy pins Prometheus with no `replace` directive, so a real fix must land upstream first and reach us via a version bump.

### Defect 2 — the tailer retries a deleted container forever (narrow, low priority)

The 5 s `error inspecting Docker container … No such container` spam is a second, separate defect: the tailer's inspect loop swallows every error and retries forever instead of giving up. Open, unreviewed upstream PR: grafana/alloy#6309. It only silences the noise — it does **not** restore log shipping — and it is reachable only *after* defect 1 has already fired.

### Defect 3 — running tailers never pick up label changes (NEW, affects us, fixed by us upstream)

Unreported anywhere before this investigation. A regression introduced in Alloy **v1.13.0**, present in our pinned **v1.17.1**.

`loki.source.docker` keys its tailers on container ID alone, and the reconciler skips any key already running — so for a container already being tailed, **the label set is frozen for the life of the tailer**. Silently ignored until Alloy restarts: the component's own `labels` argument, its `relabel_rules` argument, and any `discovery.relabel` output change that does not also change the container ID. No error, no warning, no health change. **Logs keep flowing, just labelled with stale values.**

**We were exposed and dodged it by luck.** The 2026-07-19 `container_name` rollout changed how the `container` label is derived in `discovery.relabel`. Any container whose ID did not change would have kept shipping under the **old** label until restart — silently breaking the `container="archive-pull"` selectors the logs dashboard and the NAS alert rules depend on. We restarted Alloy on all four hosts during that rollout, so it never bit. This is a third, independent, code-level reason the "restart Alloy after any compose change" runbook line exists — and unlike the other two, **this one produces *wrong* data rather than *no* data**, which is worse: a dead-man notices silence, nothing notices a mislabel.

Filed and fixed upstream: issue grafana/alloy#6714, PR grafana/alloy#6716 (open, awaiting review).

**Also affects `loki.source.kubernetes_events`** (its `job_name` and `log_format` freeze for already-running namespaces) but **not** `loki.source.file`. Irrelevant today — we use neither — but relevant if we ever adopt them.

### What still holds unchanged

Nothing in this correction weakens the existing mitigations; it explains **why** they are needed, and the codified NAS restart happens to cover all three defects.

- **Remediation is still a plain `docker restart` of the Alloy container**: fresh discovery adopts the live container, the fresh position re-ships its whole (small) log with ingest-time-stamped **original** timestamps, so the dead-man's window repopulates and the alert self-resolves within an evaluation cycle (proven live 2026-07-16 22:25 Z).
- The **dead-man alert working as designed is still the correct read** of the July incident.
- Related-but-distinct earlier lesson (from the spec-00050 Task-10 deploy): `compose up -d` does not restart Alloy when only its *mounted config* changed, silently dropping every new metric series at remote_write. The runbook line covers both cases: **restart Alloy after any NAS compose change**.

**Scope (2026-07-19): this is a FLEET topic, and the NAS control is codified.** The fleet runs four Alloy instances (NAS, ops, both capture hosts since iter-105). On the **NAS** the restart is baked into the role — `roles/nas/tasks/main.yml` restarts alloy under every `nas_apply_compose=true` apply ("T0048 CODIFIED"), so the runbook line is no longer the control there. The **ops and capture roles are render-only** (no apply flag), so on those three hosts the restart after any container recreation remains a **manual attended-deploy step** — exercised correctly at the 2026-07-19 container_name rollout (Alloy restarted on all four hosts).

**Retirement (2026-07-22/23, specs 00068/00069 — verified in repo and on the hosts):** the defect surface itself is gone. `discovery.docker` + `loki.source.docker` are deleted from every config (each remaining grep hit is a retirement comment, not a live block); the docker socket is unmounted (measured 0 mounts on ops, NAS, and both `zcrypto-red` containers; primary clears at rollout Step 6); app logs direct-ship and never transit Alloy. Repo-side, the Minor-5 cleanup already landed inside 00068/00069: no keep-list admits `prometheus_sd_*`, the wedge rule is out of `alerts.yaml`, and `tests/test_infra_alloy_series.py` keeps the two series names only to pin their **absence**. Cloud-side, the orphan `zcrypto-alloy-docker-sd-wedged` rule survives until Step 8's `GRAFANA_PRUNE=1` push (reported, correctly undeleted, by the 2026-07-22 upsert push). **Upstream disposition (owner ruling 2026-07-23, the [[T0042]] tecnativa precedent — drop whichever is simpler): both trackers dropped.** Our PR grafana/alloy#6716 (defect 3) stays open upstream on its own merits, with this file as the durable pointer; the `prometheus/prometheus` report for defect 1 (never filed) will not be filed by us — the component is out of our fleet, no repro environment remains, and this repo has no stake in the fix.

## Suggested next steps

- **(the one remaining action — at the PR #191 closeout, gated on rollout Step 8)** Confirm `zcrypto-alloy-docker-sd-wedged` deleted from Grafana by the prune push, rewrite the Defect-1 diagnostic section above IN PLACE to the retired reality (its port-12345 procedure and counter table describe instrumentation that no longer exists), and **archive the topic**. Fold one decision into that rewrite: the former "codify the restart for render-only hosts" item's premise is halved post-00068 (app logs never transit Alloy, so a missed restart stales metrics config at worst, and a dead Alloy is caught by T0079's `Fleet · Alloy dark` rules; the generic config-change-restart lesson already lives in the NAS role's codified restart and [[T0084]]'s runbook) — drop it or keep a residue, decided with Step 8's evidence in hand.
- ~~The upstream trackers~~ — **dropped (owner ruling 2026-07-23; see the Retirement finding)**: no Alloy-bump check on grafana/alloy#6716, no `prometheus/prometheus` filing. Recorded here so the deferral exits explicitly rather than evaporating.
