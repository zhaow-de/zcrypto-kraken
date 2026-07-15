---
status: open
ripe_when: the owner creates the Slack app + webhook (a ~10-minute workspace-admin action, steps below) — everything downstream is autonomous once the URL is vaulted
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

## Suggested next steps

- **(human, ~10 min)** Create the app: api.slack.com/apps → Create New App → From a manifest → workspace → paste the manifest below → Create → Install to Workspace → pick the alerts channel (e.g. `#zcrypto-alerts`) → copy the `https://hooks.slack.com/services/…` URL. Then either vault it directly (`uv run ansible-vault encrypt_string --stdin-name slack_webhook_url`, value on stdin) or hand it to an interactive session to vault.

  ```yaml
  display_information:
    name: zcrypto-alerts
    description: Grafana + healthchecks.io notifications
  oauth_config:
    scopes:
      bot: [incoming-webhook]
  settings:
    org_deploy_enabled: false
    socket_mode_enabled: false
    token_rotation_enabled: false
  ```

- **(human, ~2 min)** healthchecks.io → Integrations → Slack → connect the same channel (their UI flow; API cannot do this step).
- **(autonomous, once the URL is vaulted)** Extend `grafana-push.sh` with a contact-points + notification-policy section (same upsert-by-uid pattern, URL via env); test-fire; run Slack **alongside** email first and flip the default route only after a proven delivery. Then PATCH the five healthchecks.io checks to the new channel via the Management API. Decide email's fate (keep as fallback vs drop) after a soak.
