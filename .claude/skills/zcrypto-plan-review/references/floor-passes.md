# Floor passes — each section is rendered where `SKILL.md`'s procedure names it

Each section below is one prompt. `{SPEC_PINNED}` is the same clause `fixer.md` renders.

## exec

You are the executability pass for a spec+plan pair. Work in the detached worktree {EXEC_WT} — a throwaway copy at the branch's HEAD; write and commit there freely, it is removed afterwards. You have no prior context.

Read {SPEC}, {PLAN}, `{REPORT_DIR}/pin-facts.md` and the fix reports {PRIOR_FIX} — they live under the branch's own worktree, which you read and never write. The fix reports are what make an origin label checkable; without them every finding looks like the author's.{TOPIC_LINE} Do not read `.local/memo.md`. Every write, command and commit is in {EXEC_WT}: your cwd resets between commands, so prefix each with `cd {EXEC_WT} &&`; `{OUT}` is an absolute path outside it. Before the first verdict run `cd {EXEC_WT} && uv run python -c 'import cli; print(cli.__file__)'` and record the output as the first row of `## Executed` — it must start with {EXEC_WT}, or every verdict measures the wrong tree.

The semantic reviews are done and their findings fixed. **Do not review what the documents say. Your subject is whether the plan CAN BE EXECUTED against this tree, task by task, by an implementer who sees only the task's text and the Global Constraints.** A plan built of complete code fences is a program. Your mode is **{EXEC_MODE}** — `full` runs the program; `form` checks its form and runs none of it, because the plan goes to the SDD task loop, whose per-task review is the run. Do the one list your mode names; the other is not yours.

In mode `form`, for every task, in order, in {EXEC_WT}:

1. Apply what the task says to write — create and modify the files with the fenced content, verbatim — so the checks below read the tree as the task leaves it; run nothing it writes.
1. Every stated command parses — `zsh -n` over each `bash` fence, `python -c 'import ast,sys; ast.parse(sys.stdin.read())'` over each Python one — and every path, fixture and symbol it names exists in {EXEC_WT} at that point of the task order; a name a later task defines is the finding.
1. Every `-k` filter collects its stated count: `uv run pytest --collect-only -q -m "not slow" <path> -k "<expr>"` — collection imports the file, it runs no test.
1. Every mutation `sed` matches exactly one occurrence of the code the plan's fences write — occurrence-count the pattern over the file as the task leaves it; zero or two is the finding.
1. Every template renders through every publishing path the tree has.
1. Do not run a `Run:` line, a test file, a probe or `pre-commit`: the SDD loop's implementer and task reviewer run them, task by task.
1. Commit locally in {EXEC_WT} so a later task's failure is attributable to the task that caused it.

In mode `full`, for every task, in order, in {EXEC_WT} — the stated commands, the test file and the probes; never the suite, which is CI's, and never a pytest over the whole `tests/` tree:

1. Apply what the task says to write — create and modify the files with the fenced content, verbatim.
1. Run every `Run:` line and compare its output to the task's `Expected:` — the failure text, not the exit code. A measurement — a formatter shift, a coordinate — is taken from {EXEC_WT}'s root with every file an earlier task created present; a scratch root or a missing file measures a different plan.
1. Run the **whole** test file the task touches with `-m "not slow"`, not only its `-k` selection — an arity change or a missing default breaks a neighbour the selection hides — beside the `infra/scripts/consumers.sh --direct` readers of each file the task touches, and `uv run pytest --collect-only -q -m "not slow"` for every stated count.
1. Apply every mutation probe the task specifies and read **which** failure fired: a KILLED whose assertion text names a different reason is a control that bit for the wrong reason. Occurrence-count every `sed` pattern.
1. Render every template through **every** publishing path the tree has, not the one the plan names.
1. `uv run pre-commit run --files <the task's files>` — the lint gate the implementer will face.
1. Commit locally in {EXEC_WT} so a later task's failure is attributable to the task that caused it.

Where a step cannot be performed as written — a missing fixture, a symbol from a later task, an unstated default, a command that assumes a file nothing created — that is the finding, at the severity of what it blocks; the Scenario is what the implementer does next.

Report `{OUT}` in the shape below, preceded by an `## Executed` table — one row per task: the mode, commands run or checks made, outcome, files committed — so a clean pass is distinguishable from a skipped one. A task with no row was not executed, and the report says so.

{COMMON}

Run everything as plain blocking commands; background nothing; no subagents; no agent tools (`ListAgents`, `SendMessage`). Do not end your turn before the report exists.

## blind

You are adjudicating a spec+plan pair at {WORKTREE} HEAD (branch {BRANCH}). You have no prior context, and you must acquire none: **do not read anything under `{REPORT_DIR}` other than the prompt you were handed and the file you write, do not read this branch's commit messages (`git log` bodies), do not read `.local/memo.md`.** Assume nothing has been caught.

Read {SPEC} — the binding authority — then {PLAN}, then every file either cites.{TOPIC_LINE} Your cwd resets between commands: prefix each with `cd {WORKTREE} &&`.

The implementer of each task will see ONLY that task's text plus the plan's Global Constraints. Review from that seat, across the whole pair: coverage, consistency, whether every guard's fixture can move, whether every premise about the tree holds (verify by running, never by reading), whether every deferral names a registered `T<NNNN>` topic, a trigger arm on an existing topic, or an explicit drop with its reason, whether the operator-visible text is clean. Where a claim is about runtime behaviour, run it in a scratch interpreter; where it is about the tree, search the tree.

{COMMON}

Read-only: change nothing in the tree. Run everything as plain blocking commands; background nothing; no subagents; no agent tools (`ListAgents`, `SendMessage`). Do not end your turn before the report exists.

## scoped

You are reviewing ONE fix commit on a spec+plan pair in {WORKTREE} (branch {BRANCH}). You have no prior context.

Read `{FIX_REPORT}` first, then `git diff {PRE_FIX}..HEAD`, then {SPEC} and {PLAN} around every hunk, then every file a hunk cites. Your cwd resets between commands: prefix each with `cd {WORKTREE} &&`.

Your subject is the fix and nothing else: (1) did each hunk close the finding it names without making a claim false elsewhere in the pair — grep the pair for every value the hunk changed; (2) for every entry in the report's `## New mechanisms`, that mechanism's **own** failure modes — what happens when it fires twice, never fires, fires late, or fires on a healthy path — which the review that asked for it never examined; (3) for every entry in `## Claims written`, that the cited evidence says what the claim says.

{COMMON}

Read-only. Run everything as plain blocking commands; background nothing; no subagents; no agent tools (`ListAgents`, `SendMessage`). Do not end your turn before the report exists.
