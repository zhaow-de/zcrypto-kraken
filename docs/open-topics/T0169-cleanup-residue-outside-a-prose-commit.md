---
status: open
---

# Cleanup residue outside a prose commit

## Context — what

The prose cleanup (T0164) edits comments and docstrings only. Its batches surface what a prose commit cannot carry: test names that state the opposite of their assertions, a source module whose own comments disagree with each other, a template comment describing live host state, deferrals that lived only in a comment, a blind spot in the tripwire itself, and host actions no role enforces.

## Why this matters

A test name is read before its body, a live-host claim in a template is a claim no reader can verify from the repo, and a deferral with no topic dies with the comment that carried it.

## Findings so far

- `tests/test_engine_soak.py`: `test_offbyone_shifted_store_breaks_chain` asserts the chain holds; `test_instrument_expectations_reads_record_44` reads record 47.
- `cli/capture/segment_writer.py`: its comments say "12 pairs", "the other 19 streams" and "20 streams" at different lines; the numbers cannot all describe one universe.
- `infra/ansible/roles/ops/templates/alloy-compose.yaml.j2` says ops holds a live private key today; the ops task file's retired claim said the opposite, and `prose.md` forbids describing live host state in either direction.
- The ops task file said renaming the `zcrypto-archive-pull` unit and the `ops_archive_pull_*` metrics to match the overlay-writer job "is registered follow-up cleanup"; no topic registers it. The comment's own decision was that the names stay because the alert rules are provisioned against them.
- `infra/scripts/prose-tripwire.py` counts a triple-quoted string that is a child-interpreter probe's SOURCE as a docstring (eight blocks in `tests/test_engine_node.py`).
- `infra/ansible/roles/base/tasks/main.yml`: the docker json-log logrotate policy is held `state: absent` rather than deleted, because the file persists on every host that already has it and a deleted task would leave it rotating forever. Deleting the task is gated on host state, and that trigger lived only in the comment.
- `infra/ansible/roles/capture/tasks/main.yml`: the admin account's old capture key is removed by hand after the NAS repoints, never by the role. The stated precondition may already have fired — archived `T0068` records the NAS repointing capture/capture-red/journal to `zcrypto-data@` (resolved 2026-07-19) and `T0067` records `deploy`'s four hand-installed keys dropped — so this is a check before it is a removal.
- `infra/ansible/roles/nas/tasks/main.yml`: the old hot-push pubkey on the admin account is dropped by a one-time manual step once the `zcrypto-data` path is verified, and the workstation's `nas-hot` ssh alias repoints from `zcrypto-deploy` to `zcrypto-data` in the SAME change. That alias is configured only in the operator's own `~/.ssh/config` — `infra/external-systems.md` carries `Host` blocks for zcrypto, red, ops and nas and none for `nas-hot` — so nothing in this repo can check that half.

## Suggested next steps

- Rename the two soak tests to what they assert, in the same PR as the next change to that file.
- Reconcile the segment writer's counts against `cli/capture/` 's configured universe and keep one property statement, not three numbers — `cli/` is the running cleanup's scope.
- Cut the template's live-host sentence; what the compose file mounts is what it says.
- **Owner's decision**: the archive-pull → overlay-writer rename is either owed (then its own topic, a converge and a re-provision of every alert that names the metrics) or not (then the names stay, and this line is the record of that).
- Tripwire: exclude a string literal assigned to a variable or passed as an argument from the docstring count, with a fixture that trips on a real docstring and passes on a probe source.
- **Host-state-gated**: delete the logrotate task once `/etc/logrotate.d/zcrypto-capture-docker` is absent on every capture host and on the engine host. Nothing in `tests/` reads it (`git grep -ln logrotate -- tests/` is empty).
- **Host action**: read the admin account's `~/.ssh/authorized_keys` on each capture host for the old capture key and remove it if present; `T0068`'s repoint, the precondition the comment names, is already recorded resolved.
- **Host action, one change**: remove the old hot-push pubkey from `~zcrypto-deploy/.ssh/authorized_keys` on the NAS once the `zcrypto-data` path is verified, AND repoint the workstation's `nas-hot` alias to `zcrypto-data` in the same change.
