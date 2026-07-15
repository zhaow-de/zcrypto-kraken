---
status: resolved
ripe_when: n/a — resolved 2026-07-15 (Slack sole target; email removed after the proving call)
---

# Slack incoming-webhook notifications for Grafana + healthchecks.io

## Context — what

Replace (or complement) the email notification channel with Slack, via a classic **incoming webhook** delivered by a Slack app. Investigated 2026-07-15: the owner's assumption holds — an **app manifest is enough and no coding is needed** — with one nuance: the webhook URL is not part of the manifest; it is minted at install time when Slack prompts for the target channel (one URL = one fixed channel; each extra channel = one more "Add New Webhook to Workspace" click).

## Why this matters

Email is the only paging path today for both Grafana alerts and the healthchecks.io dead-men. Slack delivery is faster to notice, supports a dedicated channel history for alert forensics, and both receiving systems in this stack support it natively — Grafana as a first-class Slack contact point (webhook-URL mode, no bot token), healthchecks.io as a built-in integration. Rate limit ~1 msg/sec per webhook is far above this project's alert volume.

## Findings so far

- **Manifest** (create at api.slack.com/apps → "From a manifest"): `oauth_config.scopes.bot: [incoming-webhook]` is the only scope; no bot-user config, no socket mode, no token rotation. Install-to-workspace mints the URL after a channel picker.
- **The URL is a credential** (anyone holding it posts to the channel) → belongs in the ansible vault (e.g. `slack_webhook_url` in `group_vars/capture_host/vault.yml` or a shared location), never committed plaintext.
- **Grafana Cloud**: contact points are provisionable on the same alerting provisioning API `infra/scripts/grafana-push.sh` already drives (`/api/v1/provisioning/alert-rules` → add `/api/v1/provisioning/contact-points` + `/api/v1/provisioning/policies`). So the Slack contact point + routing policy can be committed-as-code with the URL injected via env (like `GRAFANA_SA_TOKEN`). *(Phase one ships contact-point-only — attach-to-existing-receiver, no policy-tree changes; policies stay unmanaged.)* Unlike legacy webhooks, per-message username/icon overrides are ignored (posts as the app) — cosmetic only.
- **healthchecks.io**: integrations cannot be created via the Management API (the channels endpoint is list-only) — adding the Slack integration is a one-time UI step; attaching it to the five existing checks afterwards is the same Management-API `channels` PATCH used when the email channel was attached (2026-07-14).

## Done so far

- **The Slack app + webhook exist** (owner, 2026-07-15): app created from the manifest, webhook minted, and the URL delivered pre-encrypted — now vaulted as `slack_webhook_url` in `infra/ansible/group_vars/capture_host/vault.yml` beside the other `grafana_*` secrets (decryption + `hooks.slack.com/services/…` shape verified in-memory).
- **healthchecks.io is DONE via its native Slack integration** (owner, 2026-07-15, connected in the UI — in addition to email, not replacing it). No webhook or API work needed there; that whole sub-item drops out.
- **Scope narrows to Grafana alerts only.**
- **`infra/scripts/grafana-push.sh` extended with a Slack contact-point section** (as code): upserts a Slack integration (stable uid `zcrypto-slack-webhook`) onto the receiver named by `GRAFANA_SLACK_RECEIVER`, sourced via `/api/v1/provisioning/contact-points` (GET the full list → PUT-by-uid if present, else POST — that endpoint has no GET-by-uid, unlike alert-rules). `GRAFANA_SLACK_WEBHOOK_URL` unset/empty skips the section cleanly; `GRAFANA_SLACK_RECEIVER` unset (with the webhook set) lists the live contact points and stops instead of guessing a receiver name (T0034 lesson generalized — no notification-policy/routing-tree changes, so this only ever adds Slack delivery to whatever the existing rules already route to). Read-back-verifies the upsert by uid/type/name (Grafana redacts the secret `settings.url` on read-back, so that field is never asserted on). Env-contract documented in `infra/nas/README.md`'s "Grafana dashboard + alerts" section.

## Resolution (2026-07-15)

Slack is the **sole** notification target for both systems, proven end-to-end before the flip:

- **Grafana**: the `zcrypto-slack-webhook` integration was pushed as-code (`grafana-push.sh`, guarded upsert + read-back), a test message was delivered and read back from `#zcrypto` via the Slack API, and after the owner's proving call the original email integration (`afrxh6bhgodtsc`) was deleted via the provisioning API — the receiver (still named `email`, a cosmetic residue; routing untouched) now holds only Slack.
- **healthchecks.io**: the owner had already removed the email channel when connecting the native Slack integration; all 9 checks are now explicitly pinned to the `#zcrypto` channel via the Management API.

Cosmetic residue, deliberately accepted: the Grafana receiver keeps its historical name `email` — renaming would require notification-policy edits for zero functional gain. Revisit only if a second receiver ever makes the name genuinely confusing.
