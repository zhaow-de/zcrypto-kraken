---
status: open
---

# Cleanup residue outside a prose commit

## Context — what

The prose cleanup (T0164) edits comments and docstrings only. Its second `tests/` + `infra/` batch surfaced five things a prose commit cannot carry: two test names that state the opposite of their assertions, a source module whose own comments disagree with each other, a template comment describing live host state, a deferral that lived only in a comment, and a blind spot in the tripwire itself.

## Why this matters

A test name is read before its body, a live-host claim in a template is a claim no reader can verify from the repo, and a deferral with no topic dies with the comment that carried it.

## Findings so far

- `tests/test_engine_soak.py`: `test_offbyone_shifted_store_breaks_chain` asserts the chain holds; `test_instrument_expectations_reads_record_44` reads record 47.
- `cli/capture/segment_writer.py`: its comments say "12 pairs", "the other 19 streams" and "20 streams" at different lines; the numbers cannot all describe one universe.
- `infra/ansible/roles/ops/templates/alloy-compose.yaml.j2` says ops holds a live private key today; the ops task file's retired claim said the opposite, and `prose.md` forbids describing live host state in either direction.
- The ops task file said renaming the `zcrypto-archive-pull` unit and the `ops_archive_pull_*` metrics to match the overlay-writer job "is registered follow-up cleanup"; no topic registers it. The comment's own decision was that the names stay because the alert rules are provisioned against them.
- `infra/scripts/prose-tripwire.py` counts a triple-quoted string that is a child-interpreter probe's SOURCE as a docstring (eight blocks in `tests/test_engine_node.py`).

## Suggested next steps

- Rename the two soak tests to what they assert, in the same PR as the next change to that file.
- Reconcile the segment writer's counts against `cli/capture/` 's configured universe and keep one property statement, not three numbers — `cli/` is the running cleanup's scope.
- Cut the template's live-host sentence; what the compose file mounts is what it says.
- **Owner's decision**: the archive-pull → overlay-writer rename is either owed (then its own topic, a converge and a re-provision of every alert that names the metrics) or not (then the names stay, and this line is the record of that).
- Tripwire: exclude a string literal assigned to a variable or passed as an argument from the docstring count, with a fixture that trips on a real docstring and passes on a probe source.
