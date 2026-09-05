# Floor passes — rendered once the union carries no Critical and no Important

Each section below is one prompt. `{SPEC_PINNED}` is the same clause `fixer.md` renders.

## minor-sweep

You are folding the remaining Minor findings into a spec+plan pair in {WORKTREE} (branch {BRANCH}). You have no prior context.

Read `{UNION}` — only its Minor blocks concern you — then {SPEC} (the binding authority), {PLAN}, `{REPORT_DIR}/pin-facts.md`, the fix reports {PRIOR_FIX} (so an origin label is a fact you can check rather than a guess), and every file a finding cites.{TOPIC_LINE} Do not read `.local/memo.md`.

**Fold every Minor whose fix is one local hunk that adds no mechanism and moves no cross-reference.** Leave every other Minor, and every one you verify wrong, with a one-clause reason **in the commit message body** — that message is the durable record of what was consciously left; nothing else records it. With nothing to fold, commit `--allow-empty` carrying the reasons. Your cwd resets between commands: prefix each with `cd {WORKTREE} &&`. No edit outside a Minor's own hunk: a sweep that starts extending is a fix round, and this is not one.

{SPEC_PINNED} Under the pinned clause a Minor whose hunk is in {SPEC} goes under `## Left` with the reason `pinned` — this report has no `## Spec-blocked`.

Before committing, `grep` the pair for every value you changed, and re-run every `--collect-only` a touched filter affects. Stage by explicit path; `Co-Authored-By: <your own model, exactly as your system prompt names it> <noreply@anthropic.com>`; no `Reviewed-by:`; no `Claude-Session:`; `uv run pre-commit run -a` until clean; never `--no-verify`. Do not push.

Report `{OUT}`: `## Folded`, `## Left` (key + reason) and `## Spec amendments` (quoted before/after, or `none`) — counts derived by re-reading it. Final message: the commit hash and the two counts. Run everything as plain blocking commands; background nothing; no subagents; do not end your turn before the commit exists.

## exec

You are the executability pass for a spec+plan pair. Work in the detached worktree {EXEC_WT} — a throwaway copy at the branch's HEAD; write and commit there freely, it is removed afterwards. You have no prior context.

Read {SPEC}, {PLAN}, `{REPORT_DIR}/pin-facts.md` and the fix reports {PRIOR_FIX} — they live under the branch's own worktree, which you read and never write. The fix reports are what make an origin label checkable; without them every finding looks like the author's.{TOPIC_LINE} Do not read `.local/memo.md`. Every write, command and commit is in {EXEC_WT}: your cwd resets between commands, so prefix each with `cd {EXEC_WT} &&`; `{OUT}` is an absolute path outside it. Before the first verdict run `cd {EXEC_WT} && uv run python -c 'import cli; print(cli.__file__)'` and record the output as the first row of `## Executed` — it must start with {EXEC_WT}, or every verdict measures the wrong tree.

The semantic reviews are done and their findings fixed. **Do not review what the documents say. Your subject is whether the plan CAN BE EXECUTED against this tree, task by task, by an implementer who sees only the task's text and the Global Constraints.** A plan built of complete code fences is a program; run it.

For every task, in order, in {EXEC_WT}:

1. Apply what the task says to write — create and modify the files with the fenced content, verbatim.
1. Run every `Run:` line and compare its output to the task's `Expected:` — the failure text, not the exit code.
1. Run the **whole** test file the task touches, not only its `-k` selection — an arity change or a missing default breaks a neighbour the selection hides — and `uv run pytest --collect-only -q` for every stated count.
1. Apply every mutation probe the task specifies and read **which** failure fired: a KILLED whose assertion text names a different reason is a control that bit for the wrong reason. Occurrence-count every `sed` pattern.
1. Render every template through **every** publishing path the tree has, not the one the plan names.
1. `uv run pre-commit run --files <the task's files>` — the lint gate the implementer will face.
1. Commit locally in {EXEC_WT} so a later task's failure is attributable to the task that caused it.

Where a step cannot be performed as written — a missing fixture, a symbol from a later task, an unstated default, a command that assumes a file nothing created — that is the finding, at the severity of what it blocks; the Scenario is what the implementer does next.

Report `{OUT}` in the shape below, preceded by an `## Executed` table — one row per task: commands run, outcome, files committed — so a clean pass is distinguishable from a skipped one. A task with no row was not executed, and the report says so.

{COMMON}

Run everything as plain blocking commands; background nothing; no subagents. Do not end your turn before the report exists.

## blind

You are adjudicating a spec+plan pair at {WORKTREE} HEAD (branch {BRANCH}). You have no prior context, and you must acquire none: **do not read anything under `{REPORT_DIR}` other than the prompt you were handed and the file you write, do not read this branch's commit messages (`git log` bodies), do not read `.local/memo.md`.** Assume nothing has been caught.

Read {SPEC} — the binding authority — then {PLAN}, then every file either cites.{TOPIC_LINE} Your cwd resets between commands: prefix each with `cd {WORKTREE} &&`.

The implementer of each task will see ONLY that task's text plus the plan's Global Constraints. Review from that seat, across the whole pair: coverage, consistency, whether every guard's fixture can move, whether every premise about the tree holds (verify by running, never by reading), whether every deferral names a registered `T<NNNN>` topic, whether the operator-visible text is clean. Where a claim is about runtime behaviour, run it in a scratch interpreter; where it is about the tree, search the tree.

{COMMON}

Read-only: change nothing in the tree. Run everything as plain blocking commands; background nothing; no subagents. Do not end your turn before the report exists.

## scoped

You are reviewing ONE fix commit on a spec+plan pair in {WORKTREE} (branch {BRANCH}). You have no prior context.

Read `{FIX_REPORT}` first, then `git diff {PRE_FIX}..HEAD`, then {SPEC} and {PLAN} around every hunk, then every file a hunk cites. Your cwd resets between commands: prefix each with `cd {WORKTREE} &&`.

Your subject is the fix and nothing else: (1) did each hunk close the finding it names without making a claim false elsewhere in the pair — grep the pair for every value the hunk changed; (2) for every entry in the report's `## New mechanisms`, that mechanism's **own** failure modes — what happens when it fires twice, never fires, fires late, or fires on a healthy path — which the review that asked for it never examined; (3) for every entry in `## Claims written`, that the cited evidence says what the claim says.

{COMMON}

Read-only. Run everything as plain blocking commands; background nothing; no subagents. Do not end your turn before the report exists.
