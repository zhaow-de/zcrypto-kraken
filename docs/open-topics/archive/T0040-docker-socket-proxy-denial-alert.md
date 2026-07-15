---
status: resolved
---

# Alert on docker-socket-proxy denials and non-routine calls

> **Closed 2026-07-14 without being built — the subject no longer exists.** The `docker-socket-proxy` was removed from the NAS stack on the same day (owner's decision): its HAProxy `timeout client/server 10m` was severing Docker's long-lived log stream and causing every line on a quiet container to be re-ingested into Loki every 10 minutes. Alloy now reads the Docker socket directly, so there is no proxy, no denial stream, and nothing for this alert to watch. The security residual that replaces it — Alloy now holds root-equivalent Docker access — is tracked in [[T0042-alloy-holds-root-equivalent-docker-access]], which also records how to restore the boundary (a two-line patch to the proxy's HAProxy template) if that residual is ever judged unacceptable. The detection idea below is preserved because it becomes live again the moment the proxy returns.

## Context — what

`infra/nas/config.alloy` now drops the proxy's routine discovery polls at ingest (`socket_proxy_routine_discovery`), keyed on the four calls Alloy actually makes. Everything else — 403 denials, non-2xx, and any allowed-but-non-routine `/containers/**` call such as `/archive`, `/export`, `/top`, `/attach` — still reaches Loki. In steady state the `docker-socket-proxy` stream is therefore *silent*: measured at zero lines while ~30 routine polls ran. Nothing alerts on it; the signal is only visible if a human happens to look at the logs dashboard.

## Why this matters

The proxy is the security boundary between Alloy and the Docker socket (`POST=0`, `VOLUMES=0`, `SECRETS=0`, …). A 403 is the only trace that something probed a forbidden endpoint, and a 200 on `/containers/<id>/archive` is the only trace that something tarred files *out* of a container — `archive-pull` mounts the 0600 rrsync SSH keys, so that path is the concrete exfiltration route the boundary exists to constrain. A stream that is empty in steady state and never alerted on is a detector nobody reads. This is cheap to alert on precisely *because* it is silent: any line at all is, by construction, worth a look.

## Findings so far

- The drop rule and its rationale live in `infra/nas/config.alloy` (the `stage.match` on `{container="docker-socket-proxy"}`); see the comment block for why the image's `LOG_LEVEL` was rejected — raising it to `warning` silenced the 403s too (verified live 2026-07-14: `GET /volumes` returned 403 and the proxy logged nothing at all).
- Verified live 2026-07-14 in steady state: a fired 403 (`GET /volumes`) and a fired allowed-but-non-routine 200 (`GET /containers/<id>/changes`) both reached Loki, while ~30 routine polls were dropped.
- The container-log tailer's own `GET /containers/<id>/logs?follow=1` streams DO ship (they terminate `CD--`, not `----`). They appear on every Alloy restart, so an alert must tolerate them or exclude them explicitly — otherwise every restart pages.
- `infra/grafana/alerts.yaml`'s only log-based rule is scoped to `container="archive-pull"`, so nothing currently covers this stream.

## Suggested next steps

- Add a Loki alert rule to `infra/grafana/alerts.yaml`, alongside the existing `zcrypto-nas-archive-pull-errors` rule, of roughly the form `sum(count_over_time({container="docker-socket-proxy"} != "/logs?follow=1" [15m])) or on() vector(0)`, firing on `> 0`. Exclude the tailer-reattach lines (see above) or it will fire on every Alloy restart; confirm the exclusion against a real restart before arming it.
- Decide the severity: this should be a low-frequency, high-signal alert (expected rate: zero). It is a security detector, not an ops one — route it wherever a genuine "someone probed the Docker socket" signal should land, not into the noisy ops channel.
- Push with `infra/scripts/grafana-push.sh` (needs `GRAFANA_SA_TOKEN` from the vault) and verify by firing a real denial on the NAS: `ssh nas`, then `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:2375/volumes` — expect `403`, and expect the rule to transition to Alerting within its evaluation window. Confirm it resolves afterward.
