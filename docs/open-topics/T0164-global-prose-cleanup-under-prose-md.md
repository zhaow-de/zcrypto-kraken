---
status: partial
ripe_when: 'refine-rules round 8 is on develop: `git log origin/develop --grep="^Refine-Round-Closed: 2026-09-04T23:52:07Z" --format=%h` is non-empty'
---

# The global prose cleanup under `prose.md`

## Context — what

Round 8 landed one prose rule (`.claude/rules/prose.md`: a durable file holds state and decisions, an event goes to git) and the tripwire that holds its thresholds (`infra/scripts/prose-tripwire.py`, PR #397). The rule stops new prose over the bar from entering; nothing yet removes what exists. The owner's word (2026-09-04): right after the round, a global scan of every existing comment, docstring and living doc under that rule — the third such cleanup, the first with a written bar.

## Why this matters

The retro study of 2026-09-04 measured the prose layer as the day's cost: 26 of 30 Critical or Important review findings were prose stronger than the mechanism beside it, and half of every component's wall-clock went into the review loop that found them. Comments and docstrings are a second, untyped layer only a second reader checks; the docs half (the phase changelogs, `fleet-pins.md`, `fleet.md`) had become a commit log and a story board respectively, reviewed like code.

## Findings so far

- Baseline on develop `f5400d19`, `.local/retro/2026-09-04/study/prose-ratio.py` (tokenizer count of comment + docstring lines): `cli/` 29%, `tests/` 21%, `infra/scripts/` 24%, total 27,479 prose lines of 112,950 (24%). Re-run the script for the after-number; never carry the figure.
- Tripwire census at `b655d00e`, `uv run python infra/scripts/prose-tripwire.py`: comment-block 1909, file-prose 183, table-row 98, section 352 (in 51 files), changelog-entry 135 — 2,677 offenders, exit 1. `--since origin/develop` reports 0, so the tool gates new prose while this topic is open.
- The docs half, measured 2026-09-04 on develop: `docs/iterations-history-phase6.md` 1,232 lines / 620 KB with entries of 1.9–7.5 KB; `docs/reference/fleet-pins.md` 45 lines / 14.5 KB with rows of 1,400–1,500 characters rewritten 38 times; `docs/reference/fleet.md` 80 lines / 20 KB.

## Done so far

The first `tests/` + `infra/` batch (PR by `zcrypto-bravo`, 2026-09-05): `tests/test_engine_executor.py`, `tests/test_infra_alert_rules.py`, `tests/test_engine_flatten.py` and `infra/grafana/alerts.yaml` under the bar — every block dispositioned against its code, the Python files AST-identical with docstrings stripped, the YAML's non-comment lines and parsed content byte-identical, one whole-branch and three scoped Fable reviews. Twelve sentences that claimed what nothing asserts became T0165, T0166 and T0167. Consciously left: the six sops `vault.yml` files (encrypted; a prose pass never edits them) and the two vaulted-key wrappers whose bodies `tests/test_kraken_fixture_mint.py` pins by sha256. Measured at the batch's tip: the tripwire over `tests infra` 1,501 → 1,413 offenders; `tests/` 16,235 → 15,688 prose lines.

The second `tests/` + `infra/` batch (2026-09-05, `zcrypto-bravo`): eight more files — the continuity, converge-guard, soak, node, capture-writer and daily-pass tests, the daily pass itself and the ops role's task file — under the bar, each proven prose-only (Python AST-identical with docstrings stripped; the YAML's non-comment lines and parsed content byte-identical); one whole-branch and one scoped Fable review. The tripwire over `tests infra` 1,412 → 1,272 offenders; `tests/` 15,739 → 15,076 prose lines. What the batch found asserted only in prose is T0168; what a prose commit cannot carry is T0169.

The docs batch (branch `cleanup/prose-docs`, 2026-09-05, `zcrypto-bravo`): `fleet-pins.md`, `fleet.md` and the seven phase changelogs under the bar, every heading, divider, rule, table cell, digest and commit hash proven identical (`parse_pins_table` equal); tripwire on the nine files 334 → 16 — the remainder is fleet.md's twelve enumeration rows and two sections and fleet-pins' agentboard row and Standing constraints, whose operator instructions await runbook homes; one whole-branch Fable review and a scoped re-review of its fix.

## Suggested next steps

- **The remaining scope, one PR per batch, dispatched by `zcrypto-main`** — `cli/` (in flight), the rest of `tests/` + `infra/` beyond the two batches (the tripwire's report is the worklist; a dozen sub-threshold soak blocks still carry event residue the tripwire cannot see), the three docs. Worklist per assignment: the tripwire's report for that scope, the files that can complete first (fewest offenders, one review round) under a hard clock, otherwise the churn order (`.local/retro/2026-09-04/study/churn.md`, most-changed first) with `.claude/*`, `docs/specs/*` and `docs/plans/*` excluded — the refine-rules round owns the first, and a spec/plan pair is a different kind of document with its own treatment.
- **Per file, `prose.md`'s four dispositions** (cut, condense, keep, relocate), findings agreed before editing, false-or-stale first; a config file's non-comment lines extracted before and after and byte-identical; a test docstring re-read against its assertions.
- **The docs half**: each changelog entry collapses to one-line bullets naming what an operator or agent now does differently, with `git log` as the chronicle it collapses into; each `fleet-pins.md` row to its cells plus one clause of payload; `fleet.md` to topology, paths, endpoints and access, nothing dated.
- **Two runbook sentences stale since the 2026-09-04 converge, for the infra batch**: `engine-procedures.md`'s NAV-disarm step (hazard closed by T0150's journaled `nav`; delete, or a one-clause residue for older records) and `drills-order-path.md`'s "neither of the two is deployed" (rewrite as state).
- **The tripwire hook's residuals**: the 2026-09-05 T0170 entry, fleet.md's twelve rows and two sections, the agentboard pins row and Standing constraints.
- **Measured before and after**: the tripwire's summary line and `prose-ratio.py` on the merge-base and on the tip of each PR, quoted in the PR body; the pre-commit hook for the tripwire lands with the last PR, once `--since` is no longer needed to make the tool pass.
