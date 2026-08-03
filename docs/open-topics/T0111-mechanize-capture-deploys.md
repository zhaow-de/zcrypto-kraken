---
status: partial
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

## Done so far

- **Wave 1 landed in full — spec `00082`, iter-124** (branch `feat/t0111-wave1-converge-guards`): all nine wave-1 role asserts plus both M-asserts (canary digest-parity, fleet-pins recording — controller-tree read) across the capture/engine/ops/docker roles, `site.yml`, and `bootstrap.yml`, each TDD'd against a constructed violation through Ansible's own Templar (82 tests). Override semantics per the owner's ruling: reason-required free text (`-e <name>_override="<reason>"`, ≥9 chars, boolean-like values refused, accepted reason echoed into the play log).
- **The window re-assert** (the 2026-08-03 backgrounded-converge lesson) is in: `site.yml` reads the clock at task execution time and refuses outside `[B+30 min, next−10 min]`, `tags: [engine]` so capture-only primary runs are unaffected.
- **`infra/scripts/mutate-probe.sh`** collapsed four `agent-ops.md` mutation bullets into one enforced script (11 tests: sandbox seeding, pytest-refusal, stale-`.pyc` purge, unmutated-baseline gate, mandatory failing control, no-op abort, signal-safe restore).
- **The `git mv` PostToolUse hook** (`.claude/hooks/git-mv-guard.sh`) warns the moment the RM-state trap forms; the network-timeout hook was considered and dropped by the owner.
- The corresponding `capture-deploys.md` lines shrank to pointers in the same PR (per-edit owner sign-offs).

## Suggested next steps

- Implement wave 2 as a second iteration — `converge.sh`, `zcrypto-panel-regenerate`, `infra/scripts/ops-postverify.sh`, `continuity.py` genesis annotation, `vault-pass.sh` ancestor check; `converge.sh` and `zcrypto-panel-regenerate` get drills on the ops host in a maintenance window.
- Wave-2 candidates recorded during wave-1 execution: the window guard's floor holds to B+30 even when the cycle finished early (probe the journal's `completed_at` instead of the fixed floor); guard 4 accepts any non-empty `--skip-tags` (tighten to name engine/capture explicitly).
- Wave-2 candidates recorded at wave-1's final whole-branch review — each a gap in what wave 1 actually mechanized:
  - **Engine re-pin canary parity.** The parity assert lives in the capture role and fires on capture re-pins only, so an engine-only converge — or a combined `--tags capture,engine` run — carrying a new `engine_image_digest` gets no mechanical parity check against the secondary's bake. M-1's mechanization narrowed the guard's reach without saying so; `capture-deploys.md`'s prose (the gate is that digest running as *capture* on the secondary, there being no engine secondary) is the only thing covering engine re-pins until wave 2 mirrors the assert in the engine role.
  - **`mutate-probe.sh` exit-code hermeticity.** A seeding failure (`git archive` / `tar`) surfaces as the pipeline's own status, colliding with the usage code 2; a failing `cp` inside `restore`/`cleanup` both leaks the temporaries and reports a code that does not name what went wrong; the no-op-abort message says "mutation" even when the control sed is the one that failed to match.
  - **The liquidations pin-probe's rc classification.** `grep` answers 2 for an absent compose file *and* for a present-but-unreadable one, so the guard's `rc != 2` gate takes the "first provision, nothing deployed to repin" stand-down on a permission fault too — the one state it must not skip silently. Only rc 1 (file there, no `@sha256:` line) is distinguished today.
  - **The `git mv` hook's coverage limits.** It matches the `git mv` route only, so a `mv` + `git add` sequence forms the same `RM` state unwatched; and it reads the hook process's cwd, not the cwd the guarded call itself ran in, so a `git -C <dir> mv` or a `cd`-prefixed command is judged against the wrong repo.
