---
status: resolved
---

# One Alloy version across the fleet

## Context — what

Each host that ships telemetry runs Grafana Alloy: seven as a digest-pinned `grafana/alloy` container (the capture pair, ops, the NAS and the three cache nodes) and two as the apt package from `apt.grafana.com` (the bridgehead `zaccess` and the observability node `zcrypto-mon`), and `docs/specs/00122-self-hosted-dead-man-design.md` plans a third apt host, the dead-man node. The owner's rulings of 2026-10-05: the fleet runs one Alloy version; the roles' Alloy tasks share one `alloy` tag, so `--tags alloy` is a host's one Alloy converge; on the apt hosts `alloy` is held out of upgrades and `--tags alloy` installs the fleet's version; a bump goes to the newest version that the image registry and the apt repository both carry.

## Why this matters

The fleet runs three Alloy versions: v1.19.2 on the containers, `1.20.0-1` on the bridgehead and `1.20.1-1` on the node, each as the tree last recorded it on 2026-10-03. A config change is dry-started against each version it will run on, behaviour that differs between nodes has to be ruled out version by version when something is troubleshot, and the bump skill's canary order leaves the apt hosts outside it.

## Findings so far

- Before this package the apt hosts followed apt with Alloy unheld: the access role cleared Alloy's `dpkg` hold in commit 2b54bd236 (2026-08-20), after a forced version refused a downgrade, dropped the bridgehead from the play and took the client-certificate revocation path with it, and the mon role took the same stance. The owner reversed it for Alloy on 2026-10-05: it was taken while Alloy was not a separately deployable object, and now it is.
- The design is `docs/specs/00123-one-alloy-version-design.md` and the plan `docs/plans/00123-one-alloy-version.md`; the owner's rulings of 2026-10-06 on the spec's seven open questions, each as recommended, shaped it: the wave may run inside rung 2's box, the primary included; the shipper-stop drill follows the wave on a later day; a split fleet pages from the observability node; the dead-man node's sitting follows the wave; the container roles recreate Alloy inside the converge; the apt hosts take a hold and a pin; the NAS's narrow `--tags alloy` run writes its own image line.

## Resolution

Delivered by the pull request from `feat/t0219-one-alloy-version`, one package:

- One version in one file: `infra/ansible/group_vars/observed/alloy.yml` names `alloy_version`, `alloy_image_digest` and `alloy_deb_version` (0113fdfc2), moved by the gate's reading of the branch to 1.20.1, `2aa2099af76c` and `1.20.1-1` (ccba6587e); `infra/ansible/scripts/converge.sh` takes `alloy_override` with an apt host's version beside it.
- Each role's Alloy part runs under the `alloy` tag. The capture, ops and cache roles refuse a digest other than the one committed for the host unless `alloy_override` gives a reason, bring the container to it and read the image it runs (5cbe8dece, a2525ef47, 0d68212fc); the NAS's narrow `--tags alloy` run writes its stack's Alloy pin line and, under the apply flag, recreates Alloy alone and reads its image (005ffa179, 779ee430e); the access and mon roles install the deb version through the shared `alloy_apt` role, held, pinned at 1001 and restarted when the process does not run the installed binary (637437d0f, 753ddb4fd); `converge.sh` refuses an `alloy` run on a host no play reaches with an `alloy` task (595ec78dc).
- The gate and the count: `infra/scripts/alloy-version.py gate` reads the newest version Docker Hub and apt.grafana.com both carry, and `off-fleet` the `observed` hosts whose `alloy` row in `docs/reference/fleet-pins.md` is off the fleet file, counted by `infra/scripts/count-list.sh hosts-off-the-fleets-alloy-version`; the apt Alloys take rows in that file's package table (823108a02).
- The observability node pages a split fleet, `zcrypto-mon-alloy-versions-split`, warning after 24 h (504fcde50); the NAS and the capture pair ship to the node beside Grafana Cloud, plan 00121's Tasks 7 and 8 on this branch (1408962dc, 360671a86).
- The pages follow: the runbooks, `docs/reference/fleet.md`, `.claude/rules/fleet-deploys.md`, and `.claude/skills/zcrypto-bump-alloy/SKILL.md` rewritten as one wave, host by host under `--tags alloy` in canary order (ac8e5ddc8).

At resolution the count reads 9: the record still names v1.19.2 for the seven containers and no `alloy` row for the two apt hosts. The wave that brings it to 0 is the fleet's attended work after the merge, as `CLAUDE.md` places a converge a solution still needs: the bump skill's wave, run as the plan's Rollout R2 to R12. Plan 00121 takes from it the capture pair's dual shipping, the shipper-stop drill's timing and the comparison's earliest day; the dead-man node's Alloy joins the tag by plan 00122's Task 9, in the sitting that follows the wave.
