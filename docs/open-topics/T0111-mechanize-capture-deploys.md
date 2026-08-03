---
status: open
---

# Mechanize capture-deploys — converge discipline moves into role asserts and scripts

## Context — what

`capture-deploys.md` is the heaviest always-loaded rule (~8 KB), and a 2026-07-30 refine-rules sweep classified its content: almost nothing is shrinkable as prose, because nearly every bullet guards a hazard no mechanism enforces. The fix is not wording — it is building the guards, so each rule line can shrink to a pointer once its mechanism refuses at the point of use (principle P10 in `zcrypto-refine-rules/references/principles.md`). Capture/ops rollouts get rarer as the codebase matures, which makes ambient prose an increasingly bad home for converge discipline.

## Why this matters

L2 capture is unbackfillable — today the only thing between an operator and the recorded disasters (un-tagged primary runs, un-baked re-pins, secondary-first pair adds, `--pull never` timers exiting 125, the liquidations silent repin) is prose that a compacted context may not hold. An Ansible assert refuses at the moment of the mistake regardless of what the operator remembers.

## Findings so far

The full classification (guard-already-exists / new-ansible-guard / new-script / not-mechanizable, with per-item mechanisms) was produced by the 2026-07-30 refine-rules round-2 sweep. Buildable guards, each described enough to implement:

**Wave 1 — role asserts (XS/S):**

- Digest-resident preflight in the capture, engine, and ops roles: `docker image inspect` the pinned `repo@digest` before any compose render (`failed_when: false`, `changed_when: false`, `check_mode: false`), assert rc 0 — kills the "pull the digest on the host first" bullets on every `--pull never` tier.
- Un-tagged primary refusal: a `site.yml` capture-play `pre_task` (`tags: [always]`, scoped to `engine_host` members) asserting `ansible_run_tags`/`ansible_skip_tags` name capture/engine explicitly.
- Engine inter-cycle-window refusal: compute `since_boundary` from the target host's `ansible_date_time.epoch` (chrony-disciplined), refuse outside the gap unless `-e engine_window_override=true`; skip under check mode so `--check --diff` previews run anytime.
- Engine preflight: assert `/opt/zcrypto-capture/logship-secrets.env` present (absence crash-loops the engine) and read the `:9102` holder before restart.
- Pair-add order assert: on the secondary, delegate a read of the primary's deployed `CAPTURE_PAIRS`; refuse a pair the primary does not already carry (kills the primary-first footgun at any spacing).
- `daemon.json` change-ack in the shared docker role (protects capture hosts too — its handler bounces dockerd under live capture): render to a probe path first, refuse an unacknowledged diff.
- Liquidations repin decision: when `ops_image_digest` differs from the deployed compose pin, require `-e liquidations_decision=roll-after|defer` so the never-restarted compose repin is a conscious choice.
- Panel-timer hold: `-e ops_panel_timer_hold=true` makes the role leave the panel timer stopped (today the enable-and-start task silently re-arms it after a converge).
- Bootstrap re-bootstrap refusal: probe for the deploy user; an already-bootstrapped host refuses without `-e rebootstrap=true`.

**Wave 2 — scripts (S/M):**

- `infra/ansible/scripts/converge.sh` wrapping `run.sh`: require `--limit`, run and display the `--check --diff` pass before the real one.
- `zcrypto-panel-regenerate` (ops role installs it): sizes the window from the tree (~2.1 s/MB), refuses when the ETA crosses 02:25 UTC, deletes both copies, runs inside the unit, prints the hc.io pause/unpause checklist — collapses most of the panel section.
- `infra/scripts/ops-postverify.sh`: the next-tick outcome checks (`ops_archive_pull_exit_code`, `ops_panel_exit_code`, reconcile mtime/counters, `hc_checks_down_total`) through `grafana-query.py`.
- `continuity.py` genesis annotation: mark a stream's earliest-ever hour as `(genesis — expected)` so the carve-out sentence dies; the raw truncated count stays printed (T0003 exit-bar instrument — output contract unchanged).
- `vault-pass.sh` ancestor check: refuse when a `/proc` ancestor is `ansible-inventory --host/--list` (the two flags that decrypt the whole vault to stdout).

**M-sized, design first:** canary digest-parity (primary re-pin refused unless the secondary runs the candidate — needs a delegated read + an override for emergencies) and the `fleet-pins.md` recording assert (refuse to replace a digest the file does not record).

**Not mechanizable (prose stays):** the bake gate's event-coverage judgment, "mean it" wrong-recovery clauses, regeneration's point-of-no-return consent, post-hoc verify-by-outcome timing.

## Suggested next steps

- **(added 2026-08-03 from the refine round — a wave-1 assert, deliberately NOT rule prose)** Refuse a converge whose **time window has already passed**. A backgrounded converge executed **~3.5 h** after it was launched: aimed at the 00:00–04:00 inter-cycle gap, it ran at 04:45 and landed in the *next* valid gap after a clean cycle — by luck, not design, because every precondition had been verified at launch time and none was re-read at execution time. Prose cannot fix this (the operator did check, and was right when they checked); an assert that re-asserts the window **immediately before acting** can. This is exactly the trade this topic exists to make — a guard instead of another line on the heaviest always-loaded rule.
- Implement wave 1 as one iteration (spec + plan; each assert TDD'd against a constructed violation per `agent-ops.md`'s guard-proving rule — the named defect built and seen to trip it, failure mode read).
- Implement wave 2 as a second iteration; `converge.sh` and `zcrypto-panel-regenerate` get drills on the ops host in a maintenance window.
- Design pass for the two M asserts (digest-parity, fleet-pins recording) — decide override semantics with the owner before building.
- **Every guard's landing PR shrinks the corresponding `capture-deploys.md` line to a pointer in the same PR** (protected-set edits: owner sign-off per edit) — the rule file shrinks as the guards land, never before.
