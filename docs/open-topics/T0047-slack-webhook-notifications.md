---
status: partial
ripe_when: now — the webhook is minted and vaulted (2026-07-15), so the remaining Grafana wiring is autonomous work
---

# Slack incoming-webhook notifications for Grafana + healthchecks.io

## Context — what

Replace (or complement) the email notification channel with Slack, via a classic **incoming webhook** delivered by a Slack app. Investigated 2026-07-15: the owner's assumption holds — an **app manifest is enough and no coding is needed** — with one nuance: the webhook URL is not part of the manifest; it is minted at install time when Slack prompts for the target channel (one URL = one fixed channel; each extra channel = one more "Add New Webhook to Workspace" click).

## Why this matters

Email is the only paging path today for both Grafana alerts and the healthchecks.io dead-men. Slack delivery is faster to notice, supports a dedicated channel history for alert forensics, and both receiving systems in this stack support it natively — Grafana as a first-class Slack contact point (webhook-URL mode, no bot token), healthchecks.io as a built-in integration. Rate limit ~1 msg/sec per webhook is far above this project's alert volume.

## Findings so far

- **Manifest** (create at api.slack.com/apps → "From a manifest"): `oauth_config.scopes.bot: [incoming-webhook]` is the only scope; no bot-user config, no socket mode, no token rotation. Install-to-workspace mints the URL after a channel picker.
- **The URL is a credential** (anyone holding it posts to the channel) → belongs in the ansible vault (e.g. `slack_webhook_url` in `group_vars/capture_host/vault.yml` or a shared location), never committed plaintext.
- **Grafana Cloud**: contact points are provisionable on the same alerting provisioning API `infra/scripts/grafana-push.sh` already drives (`/api/v1/provisioning/alert-rules` → add `/api/v1/provisioning/contact-points` + `/api/v1/provisioning/policies`). So the Slack contact point + routing policy can be committed-as-code with the URL injected via env (like `GRAFANA_SA_TOKEN`). Unlike legacy webhooks, per-message username/icon overrides are ignored (posts as the app) — cosmetic only.
- **healthchecks.io**: integrations cannot be created via the Management API (the channels endpoint is list-only) — adding the Slack integration is a one-time UI step; attaching it to the five existing checks afterwards is the same Management-API `channels` PATCH used when the email channel was attached (2026-07-14).

## Done so far

- **The Slack app + webhook exist** (owner, 2026-07-15): app created from the manifest, webhook minted, and the URL delivered pre-encrypted — now vaulted as `slack_webhook_url` in `infra/ansible/group_vars/capture_host/vault.yml` beside the other `grafana_*` secrets (decryption + `hooks.slack.com/services/…` shape verified in-memory).
- **healthchecks.io is DONE via its native Slack integration** (owner, 2026-07-15, connected in the UI — in addition to email, not replacing it). No webhook or API work needed there; that whole sub-item drops out.
- **Scope narrows to Grafana alerts only.**

## Suggested next steps

- **(autonomous, ripe now)** Extend `infra/scripts/grafana-push.sh` with a contact-points + notification-policy section on the same provisioning API (`/api/v1/provisioning/contact-points`, `/api/v1/provisioning/policies`), upsert-by-uid like the rules; the URL arrives via env (`GRAFANA_SLACK_WEBHOOK_URL`, sourced from the vaulted `slack_webhook_url`) exactly like `GRAFANA_SA_TOKEN`. Run Slack **alongside** email first; test-fire a rule; flip the default route only after a proven delivery.
- **(human, later)** After a soak with both channels: decide email's fate (keep as fallback vs drop) — for healthchecks.io too, where Slack currently runs in addition to email.
