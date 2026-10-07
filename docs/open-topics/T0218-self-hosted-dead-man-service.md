---
status: partial
ripe_when: the pull request from `feat/t0218-dead-man-tasks-8-10` is merged into `develop` — check `git fetch -q origin && git log origin/develop --first-parent --merges --oneline --grep='from zhaow-de/feat/t0218-dead-man-tasks-8-10'` prints its merge commit
---

# Self-hosting the dead-man service: a tailor-made healthchecks.io replacement

## Context — what

Every dead-man check the fleet relies on lives on healthchecks.io: pinged from five hosts through vaulted ping URLs, read by the daily pass through the v3 management API, scraped by the ops Alloy for the `zcrypto-hcio-watchdog` rule, and notifying Slack through healthchecks.io's own integration. The owner has read healthchecks.io's source, judged its quality, security and resilience insufficient, and built a hard fork: a dead-man ping service with near-complete API compatibility and higher security and reliability standards, intended as a drop-in replacement, with the freedom to change the fleet where the drop-in does not hold. This topic is the iteration that moves the fleet onto it, in the shape of T0217's self-hosting of the observability stack but without a dual-shipping stage: one cutover, every ping URL re-minted, which is also the rotation T0085 has carried as its last step.

## Why this matters

The dead-man checks are the fleet's last line: they page when a host, a daemon or Grafana itself is gone, and a weak service there is a silent fleet. Owning the service closes the external dependency and its security surface, and the cutover is the one time every ping URL changes.

## Findings so far

- The surface and the command that reads each part of it are spec 00122's measured basis.
- T0085 names the eleven ping URLs as in scope for the pre-go-live rotation and the two API keys' shapes; T0083 (archived) set the mutual watchdog between Grafana and healthchecks.io.
- Spec 00123 (one Alloy version across the fleet, T0219; on `feat/t0219-one-alloy-version` until it merges) asks of Task 9, under *What this asks of plans 00121 and 00122*: the node's Alloy installed at the fleet file's version, held and pinned, dry-started at that version, under the `alloy` tag, with a `fleet-pins.md` row.

## Done so far

The first pull request, from `docs/t0218-self-hosted-deadman`, carries the pair and the plan's Tasks 1 to 7.

- The spec `docs/specs/00122-self-hosted-dead-man-design.md` and the plan `docs/plans/00122-self-hosted-dead-man.md`: written in 47c48d4dd, reviewed by the `zcrypto-plan-review` loop from d06564503 to its exit at 47a1660e0; the branch's pre-review folded ca1d26578 and 37cf2c7ca into them.
- Task 1, the shared test helpers `tests/role_render.py` and `tests/selfcheck_driver.py`: a7bba5992, 9d53cdb3e.
- Task 2, the `edge` role, the `mon` role's Caddy block its include: 4f2f7f8ce, c70d4ad0d, 594723685.
- Task 3, `node_common`'s secrets preflight and reboot check: abc569762, b20a8b220, ca38e262a, 3475010b0.
- Task 4, `node_common`'s self-check pattern: 692b71d25, 54eae9578, 0df029c1c, 576659f0a, cce4987fc, 5f4252b7d, e667a2360.
- Task 5, `node_common`'s SQLite backup timer and the Fleet health backup panel: 8c43c7146, 729e4a3ba, 3a2dfa855, a414defe5, 7e3c03bf0, 563e4da6c.
- Task 6, `infra/scripts/vault-append-secret.sh`: d5d0463a4, 25f6da7ff, e4941358d, 5b9efc6d2.
- Task 7, the push's node-only groups and the daily pass's patch-pass table, with the `zcrypto-grafana-push` skill's default skip: 495551a3a, 0ae529df3, fd8cff1df, a732953b6, d5186872a, f900520f1.
- Folds spanning several tasks: e77b0f642 and 76b5cc32e, the pre-review's comment rows over Tasks 1 to 5; 2e861a143, the fix range's prose over Tasks 4 and 5.

The second pull request is from `feat/t0218-dead-man-tasks-8-10`; the first merged as #663.

- R-X, 2026-10-06: the owner's converge of the observability node onto the shared code from `develop` 414097c23; its deploy-log rows 2a4c549e7.
- P1, 2026-10-06: the owner's deploy keypair `deploy_zcrypto-hc_ed25519`, committed by 556a1a5bf.
- Task 8, 2026-10-06, the node joins the fleet: 556a1a5bf.
- Task 9, 2026-10-06, the `hc` role: 6fd834b1d.
- Task 10, 2026-10-06, the clone's self-check: 684029416.
- The final fix over Tasks 8 to 10, 2026-10-06: 32e65f036, 69d27943f, cdf501fc6; the owner's rider, the bridgehead reached as `ssh access`: 0a4314b16, 362a299f6.
- P2, 2026-10-06, the two generated vault values: 16079f87b.
- P3, 2026-10-06, the SES SMTP credential, vaulted, and its endpoint: 0fbd2df88.
- The release the node deploys moved from `v6.1.0` to `v6.2.0`, the clone's newest, 2026-10-07, the owner's word; its static reads are the spec's measured-basis amendment: e06b8719f, 8bdd8927e, 5eda879f1, ca2cf8e2f.

## Suggested next steps

- After the second pull request merges: R0 to R7, the node built and read, and P4 (the owner's first sign-in and the project).
- The third pull request: P5 (the three keys and the uuid) before Task 12; Task 11 (`hc-provision.py`), Task 12 (the pingers' URL scheme), Task 13 (the readers), Task 14 (the node's rule group, its runbook page, its Fleet health row and the observability node's Grafana error-log rule), Task 16 (four skills take the service and its node) and Task 17 (the backup's off-host copy), P6 (the NAS's pull key) before Task 17; the gate re-reads the cutover's release before it opens, and R8's provisioning runs from its branch before it merges.
- The cutover sitting, after the third merge and spec 00123's Alloy wave: the rest of R8, R9 (ops), R10 (the observability node), R11 (the NAS), R12 (the capture pair), R13 (the checks' first clean read, again the next morning), the Rollback as needed, then R-records-1.
- The fourth pull request: Task 15 (the drills and the surfaces' sweep), opened once R13 reads clean and merged before R15.
- After the box closes, 2026-11-01 or a week later: R14 (the engine's move at the box's deferred disarm converge, inside the inter-cycle gap), R15 (the three drills), R16 (retirement, after R14's first clean day and R15's three drill entries) and R-records-2.
