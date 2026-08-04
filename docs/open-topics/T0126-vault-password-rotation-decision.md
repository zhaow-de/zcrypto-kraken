---
status: open
ripe_when: now — the decision is the work; one attended answer disposes of it
---

# Vault password rotation after the red-phase transcript exposure

## Context — what

During iter-125's vault-pass.sh guard work (2026-08-04), the TDD red phase ran the then-unguarded script once with the real sops path, decrypting the vault password into the implementer subagent's local session transcript under `~/.claude/`. An independent review swept every branch commit, workspace file, and cache with entropy and context patterns: nothing committed carries secret material, the branch was not on the remote at the time, and the workstation already holds the sops age key — so no new trust boundary was crossed. The exposure surface is exactly one local transcript file.

## Why this matters

The vault password decrypts every fleet secret including the live Kraken trade key. A defense-in-depth posture would rotate it after any exposure event, however contained; the counter-argument is that the transcript lives on the same workstation as the sops key itself, so rotation buys nothing against an attacker who can read that file. This is the owner's risk call, not an autonomous one.

## Findings so far

- Exposure event and containment evidence: iter-125's Task-2 review (independent entropy sweep across all branch commits, all SDD workspace files, both touched files, the pytest cache — zero secret-shaped bytes; every `vault_password` hit is the sops `--extract` key-path literal).
- Rotation mechanics if chosen: re-encrypt `infra/ansible/vault-password.sops.yaml`'s `vault_password` value with a new password, then `ansible-vault rekey` every vaulted file with the old/new pair — attended, since it touches the live trade key's vault.
- The guard that prevents recurrence landed in the same iteration: `vault-pass.sh` now refuses `ansible-inventory --host/--list/--vars` ancestries, and future red phases stub sops via `ZCRYPTO_SOPS_BIN` (the test harness already does).

## Suggested next steps

- Owner decides: rotate (attended session runs the rekey, ~30 min, no fleet converge needed — the vault files are controller-side), or accept the residual with the containment evidence above as the recorded reason and archive this topic as a conscious drop.
