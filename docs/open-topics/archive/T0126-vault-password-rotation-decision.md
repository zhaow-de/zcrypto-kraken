---
status: resolved
---

# Vault password rotation after the red-phase transcript exposure

## Context — what

During iter-125's vault-pass.sh guard work (2026-08-04), the TDD red phase ran the then-unguarded script with the real sops path — four failing tests displayed decrypted bytes in their pytest failure diffs, plus one deliberately output-discarded verification run — putting the vault password into the implementer subagent's local session transcript under `~/.claude/`. An independent review swept every branch commit, workspace file, and cache with entropy and context patterns: nothing committed carries secret material and the branch was not on the remote at the time. The exposure surface is the local transcript file(s) and any terminal scrollback that streamed those diffs, on this workstation only; the exact extent was taken from the implementer's account, not independently exhumed.

## Why this matters

The vault password decrypts every fleet secret including the live Kraken trade key. A defense-in-depth posture would rotate it after any exposure event, however contained; the weight of the counter-argument depends on the sops backend's key protection: the vault uses a **PGP** recipient, so if that key is passphrase- or hardware-protected, file-read access does NOT decrypt the vault — the plaintext transcript is then strictly weaker-protected than the vault itself, which strengthens the rotation case rather than weakening it. Only if the PGP key is usable without a passphrase on this workstation does "rotation buys little" hold. This is the owner's risk call, not an autonomous one.

## Findings so far

- Exposure event and containment evidence: iter-125's Task-2 review (independent entropy sweep across all branch commits, all SDD workspace files, both touched files, the pytest cache — zero secret-shaped bytes; every `vault_password` hit is the sops `--extract` key-path literal).
- Rotation mechanics if chosen: re-encrypt `infra/ansible/vault-password.sops.yaml`'s `vault_password` value with a new password, then `ansible-vault rekey` every vaulted file with the old/new pair — attended, since it touches the live trade key's vault.
- The guard that prevents recurrence landed in the same iteration: `vault-pass.sh` now refuses `ansible-inventory --host/--list/--vars` ancestries, and future red phases stub sops via `ZCRYPTO_SOPS_BIN` (the test harness already does).

## Resolution

**Accepted, not rotated — owner's decision, 2026-08-04.** The residual is carried rather than acted on, because a **comprehensive credential rotation round** is planned for the run-up to go-live, and rotating this one secret now would be redone there anyway. Rotating early and then continuing to develop re-opens the same class of exposure with a fresh secret, so one late round is the stronger posture.

The deferred action is **registered, not merely mentioned**: the rotation round is a sub-item of [[T0085]] (rescoped in the same change from an arm64-only topic into the pre-go-live carrier), ripe as the **very last step before final go-live**, with the full credential inventory enumerated there.

**What would re-open this decision.** The acceptance rests entirely on that round happening. If T0085's rotation sub-item is dropped, deferred past go-live, or narrowed to exclude the vault password, this judgement does not carry over — it must be re-decided against the exposure recorded above, not inherited. That conditional is the reason this file is archived rather than deleted.
