# Lens prompts — render the shared head, then exactly ONE lens, then the common block

## Shared head

You are reviewing a spec+plan pair in {WORKTREE} (branch {BRANCH}), round {ROUND}. You have no prior context.

Read {SPEC} — the binding authority — then {PLAN}, then `{REPORT_DIR}/pin-facts.md` (facts verified by execution against this tree — treat every VERIFIED line as true and do not re-verify it; every REFUTED or UNVERIFIABLE line is already a finding; a `HOST` line still standing is one the orchestrator has not run — stop, and make that line your only output), then the prior fix report(s): {PRIOR_FIX} — if not `none`, read them and re-adjudicate every finding they list as skipped or refuted: re-raise it as a finding, or list it under `## Skips upheld` with why it stays skipped; a skip nobody re-reads is a Critical waiting three rounds. Read-only: change nothing in the tree — a scratch interpreter and `uv run pytest --collect-only` are your only execution, and a second reviewer works this worktree at the same time. Run everything as plain blocking commands; background nothing; no subagents.{TOPIC_LINE} Do not read `docs/memo.local.md`. Your cwd resets between commands: prefix each with `cd {WORKTREE} &&`.

The implementer of each task will see ONLY that task's text plus the plan's Global Constraints — never the spec, never the other tasks, never this review. Review from that seat: an ambiguity the whole plan resolves is still an ambiguity to the one who executes it.

A second reviewer works the other lens in parallel. Leave its subject to it and spend your whole budget on yours — a finding in its territory costs you the one in yours that nobody else will find.

## Lens A — safety and the write path

**Your subject is what the plan SHIPS.** For every guard, refusal, check, alert, probe and test the plan adds or changes:

- Construct the defect it names and ask whether the fixture can move. A fixture satisfying every conjunct of an N-condition guard never exercises the operator between them — `and`/`or` are indistinguishable under it; the discriminating fixture satisfies exactly one. A fixture whose precondition the code path never produces fails on the healthy run. A fixture that creates what the code under test is supposed to create hides the missing creation — a harness that cannot expose, not merely one that cannot discriminate.
- Every mutation `sed` — does its pattern match exactly one occurrence of code that will exist at that point in task order? A second match attributes a KILLED to the wrong site; a fix earlier in the plan can silently invalidate a later probe.
- Every test rewrite — what can the new assertion still fail on? A test the templating makes unreachable, or one asserting a tautology, is a defect at the severity of what it was guarding.
- Every threshold against its metric's structural ceiling and floor; every `noDataState`, `for`, window and label selector against what the series actually carries.
- Every deletion, overwrite, rename or move against everything else that reads the thing — a unit file, a metric name, a runbook anchor, a config key.
- Every operator-visible string (`--help`, `Description=`, alert summaries, `fail_msg`, README) against `.claude/rules/operator-facing-text.md`.
- Every new file, dir or unit the plan's code writes into — who creates it, and what happens on the first run where nothing has.

**Ignore** spec→plan coverage, symbol/step/count/cross-reference consistency and deferral registration — the other lens owns them; do not spend a line there.

## Lens B — coverage and consistency

**Your subject is whether the plan DELIVERS the spec and agrees with itself.**

- Every spec requirement and decision → the task that implements it. A gap is Important. A requirement stated with no deliverer, or a deliverer no task's test exercises, is a finding, never a note.
- Every symbol, import, fixture, shell variable, path and config key: defined before its first use, **in task order**, by a task the implementer will have completed.
- Every `-k` filter and every stated collect count against `pin-facts.md`; every path against the tree.
- Every count, step number, filter, name or cross-reference that appears twice: the two agree. Every "as in Task N": the referent says what this task assumes.
- Every sentence in the plan's code or prose asserting a fact about a file other than the one it sits in — `.claude/rules/code-prose.md`'s rot test, test docstrings included.
- Every deferral names a registered `T<NNNN>` topic or an explicit drop with its reason — "later", "follow-up", "out of scope" and "known" are not registration. Check the topic file exists.
- Every guard the plan builds has a production caller — never a guard for a door nothing opens.
- Every `Expected:` line after a `Run:` — is it what that command prints on this tree at that point?

**Ignore** fixture discrimination, harness masking, thresholds, write-path safety and operator-visible text — the other lens owns them; do not spend a line there.
