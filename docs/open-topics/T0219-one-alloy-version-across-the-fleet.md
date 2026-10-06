---
status: open
ripe_when: the pull request from `feat/t0219-one-alloy-version` is merged into `develop` — check `git fetch -q origin && git log origin/develop --first-parent --merges --oneline --grep='from zhaow-de/feat/t0219-one-alloy-version'` prints its merge commit
---

# One Alloy version across the fleet

## Context — what

Every host that ships telemetry runs Grafana Alloy: seven as a digest-pinned `grafana/alloy` container (the capture pair, ops, the NAS and the three cache nodes) and two as the apt package from `apt.grafana.com` (the bridgehead `zaccess` and the observability node `zcrypto-mon`), and spec 00122 plans a third apt host, the dead-man node. The owner's rulings of 2026-10-05: every host runs the same Alloy version, always; every role's Alloy tasks share one `alloy` tag, so `--tags alloy` is the one Alloy converge on any host; on the apt hosts `alloy` is excluded from every upgrade, held, and `--tags alloy` installs the fleet's version; a bump goes to the newest version only when that same version is in both the image registry and the apt repository.

## Why this matters

The fleet runs three Alloy versions: v1.19.2 on the containers, `1.20.0-1` on the bridgehead and `1.20.1-1` on the node, each as the tree last recorded it on 2026-10-03. A config change is dry-started against each version it will run on, behaviour that differs between nodes has to be ruled out version by version when something is troubleshot, and the bump skill's canary order leaves the apt hosts outside it.

## Findings so far

- The apt hosts follow apt today and are never held: the access role clears a `dpkg` hold since commit 2b54bd236 (2026-08-20), after a forced version refused a downgrade, dropped the bridgehead from the play and took the client-certificate revocation path with it; the mon role follows the same stance and `tests/test_infra_mon_role.py` holds it. The owner reversed that stance on 2026-10-05: it was taken while Alloy was not a separately deployable object, and now it is.
- The capture role's share of the tag is built on branch `feat/t0217-capture-alloy-tag` and the NAS's Alloy-only apply form on `feat/t0217-phase-2-nas`; both move onto this topic's branch, which also carries plan 00121's Tasks 7 and 8, the NAS and the capture pair shipping to the observability node.
- The design is `docs/specs/00123-one-alloy-version-design.md`; the owner ruled its seven open questions on 2026-10-06, each as recommended, which discharged the trigger that waited on them. The plan is `docs/plans/00123-one-alloy-version.md`, and the package's one pull request resolves this topic, so the trigger now names that pull request's merge.

## Suggested next steps

- Plan 00123 on this branch, reviewed by `zcrypto-plan-review`; the task loop; one pull request for the whole package; then the first wave, host by host under `--tags alloy`, its records on branch `docs/t0217-phase-2-records`.
