---
status: open
ripe_when: per sub-item — the arm64 re-enable ahead of the final go-live (never on go-live day itself); the credential rotation round as the VERY LAST step before it, once every other pre-live change has landed
---

# Final pre-go-live steps — arm64 image re-enable, and the credential rotation round

## Context — what

Two things must happen in the run-up to the Stage-6b live-capital step that belong to no other iteration, and whose *timing* is most of the point: a build lane disabled for development speed has to come back, and every credential the fleet holds gets rotated once, after everything else has stopped changing. The two are unrelated in subject and deliberately staggered in time; they are carried together because they share a trigger no other topic owns — the run-up to go-live — and an item with no owner at that moment is one nobody remembers.

## Why this matters

Both are silent until the moment they are not. A disabled build lane is invisible until something needs arm64 — the silent-drift shape the fleet's pins-and-labels discipline exists to prevent, and a first multi-arch build can surface QEMU/buildx issues that must not be debugged inside a go-live window. Credentials are worse, because exposure accumulates quietly across a whole development period — test runs, agent transcripts, terminal scrollback, screen shares — and no single incident justifies the disruption of a rekey. The clean line is one round, late: rotate everything after the last change that could leak something new. Rotating early and continuing to develop simply re-opens the same exposure with fresh secrets.

## Findings so far

- **arm64**: the workflow builds `default` and `-compat` variants for `linux/amd64` today; arm64 is **commented out, not removed** — `.github/workflows/capture-image.yml` carries the owner's 2026-07-15 note and the exact restore line (`platforms: linux/amd64,linux/arm64`), and the QEMU binfmt step is what makes the cross-build work on the amd64 runner. Re-enabling is uncommenting plus verifying, not re-engineering.
- **Rotation scope, enumerated from repo structure rather than by decrypting anything** — the sops-encrypted vault password (a **PGP** recipient, not age) and the material the vault carries: `kraken_trade_api_key` + `kraken_trade_api_secret` (the live trade credentials), `grafana_prom_token` / `grafana_loki_token` / `logship_loki_token` / `grafana_sa_token`, `healthchecks_api_key` plus **15** distinct `*_healthcheck_url` ping endpoints, `coinalyze_api_key`, the **five** per-machine Ansible deploy keys under `infra/ansible/files/` (`zcrypto`, `zcrypto-red`, `zcrypto-ops`, `nas`, `zaccess`), and the mTLS client leaves pinned on the access edge. Decided by the owner 2026-08-04.
- **One known exposure this round subsumes**, from [[T0126]] — accepted rather than acted on: iter-125's vault-guard TDD red phase put the vault password into local subagent transcript(s) and terminal scrollback on the workstation. Nothing was committed, the branch was not on the remote, and the workstation already holds the sops key material, so the marginal risk did not warrant an immediate standalone rekey. **That judgement is sound only because this round is coming** — if the rotation sub-item is ever dropped or deferred past go-live, T0126's acceptance must be re-decided, not inherited.

## Suggested next steps

- **(arm64 — ripe ahead of go-live, deliberately not on the day)** Re-enable the arm64 platform in `capture-image.yml`; verify one full multi-arch build publishes and both digests carry the expected labels (`revision`, `polars-runtime`). Confirm no consumer pins assume single-arch manifest digests (the NAS pin comment's "ONE IMAGE, THREE IDENTIFIERS" note covers the manifest-list case).
- **(rotation — ripe as the VERY LAST step before go-live)** Rotate everything listed above in one round, once the final pre-live change has landed. Order matters: rotate the **vault password last**, since re-keying it while other secrets are still being replaced means doing it twice. Re-converge each host carrying a rotated secret and verify **by outcome**, not by exit code — `up` still 1 for every host in Cloud, every dead-man still pinging, and the new trade key exercised by a real paper round-trip rather than assumed working. Record the round's date in `docs/reference/fleet.md`, so the next exposure question has a "last rotated" date to reason from instead of a guess.
