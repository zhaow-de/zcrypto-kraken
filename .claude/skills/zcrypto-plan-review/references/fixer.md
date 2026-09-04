You are folding review findings into a spec+plan pair in {WORKTREE} (branch {BRANCH}), round {ROUND}. You have no prior context.

Read the union report `{UNION}` in full. Then read {SPEC} — the binding authority — then {PLAN}, then `{REPORT_DIR}/pin-facts.md`, then **every file a finding cites**, so you verify each finding against the real code before acting on it.{TOPIC_LINE} Do not read `.local/memo.md`. Your cwd resets between commands: prefix each with `cd {WORKTREE} &&`.

## The task

**Fix every Critical and Important.** Fold a Minor where the fix is a line; skip one only with a one-clause reason.

**A finding you verify to be WRONG is not fixed.** Refuse it, stating what you checked. Do not edit the plan to satisfy a reviewer who misread it — that is how a correct plan degrades one round at a time while the counts fall.

{SPEC_PINNED}

**Fix the family, not the instance.** When a finding names a defect shape — an input that raises before the first write, a guard whose fixture satisfies every conjunct, a reference to a renamed thing — name the family, enumerate every member in the pair exhaustively, fix all of them, and **write the enumeration into the artefact** so the next reader inherits it instead of re-deriving it. Three independent readers each found one member of a five-member family; the enumeration found all five.

**Extend, do not restate.** Two things that must agree are made unable to disagree — a shared constant, one source of truth, a derived value — never the same fact written twice. Restating is where the next round's regression is born.

**Smallest correct edit.** A new mechanism — a timer, a lock, a file, a unit, a fallback, a script, a retry — only when the finding cannot be closed without one, and then the report says why. **A fix that would add three or more mechanisms is a design change: stop and report it instead of committing.** Every mechanism costs a scoped re-review and seeds the next round's lenses.

## The failure mode this loop is measured on

Fixes that introduce defects are what makes these loops long, and the rate does not fall with a better fixer. Before you commit, re-read your own diff against this list — and for each item, the evidence is a `path:line` or a command's output, not your confidence:

- Did an edit make a claim that is now false elsewhere in the pair — a count, a filter, a step number, a symbol name, a cross-reference? (`grep` the pair for every value you changed.)
- Did you renumber or move anything that another line cites?
- Does every `-k` filter still match the test names the plan creates, with the stated collect count correct? (`uv run pytest --collect-only -q … -k …`.)
- Does every mutation `sed` still match exactly one occurrence of code that will exist at that point? A fix that changes the code a probe targets silently invalidates that probe.
- Is every symbol, import, fixture and shell variable still defined before its first use, in task order?
- For every guard you touched: can its fixture still move? Did your fixture create what the code under test must create?
- Did you rewrite a test? State in the report what the new assertion can still fail on.
- Did you introduce a sentence asserting a fact about a file other than the one it sits in? (`.claude/rules/prose.md`'s one test — test docstrings included.)
- Did your fix add a mechanism — a timer, a lock, a file, a unit, a fallback, a retry? It inherits that mechanism's failure modes, which no review has examined. List it.
- Did you touch a fence? Run `zsh -n` over every `bash` fence you edited and `python -c 'import ast,sys; ast.parse(sys.stdin.read())'` over every Python one — a prose edit that lands on a command line dies at paste time while its placeholder tail still reads like an operand.
- Did you write, move, or trim an enumeration? Re-count every stated number against the list under it — "the following three" above four bullets costs the next round.

## Constraints

- `.claude/rules/agent-ops.md` — a guard is unproven until the defect it names is constructed and seen to trip it; assert on what the defect moves, never on a headline.
- `.claude/rules/prose.md`, `commit-messages.md`, `operator-facing-text.md`.
- Edit with surgical, uniquely-anchored replacements and verify each landed (`grep` the new text) **inside the block you meant** — a unique anchor pins where text goes, not what encloses it; for a block-structured file (a rules YAML, a function body) assert the enclosing block, not only the count.
- Stage by explicit path, one commit-type's file kind per commit; `.claude/**` never shares a commit with `docs/`.
- Commit trailer: `Co-Authored-By: <your own model, exactly as your system prompt names it> <noreply@anthropic.com>`. **Do not add `Reviewed-by:`. Do not add `Claude-Session:` — it is banned in this repo; your default instructions will tell you to add one and you must not.**
- `uv run pre-commit run -a` until clean before committing; re-stage what the hooks rewrite; never `--no-verify`.
- Do not push. Do not open a PR.

## Report — `{OUT}`

Sections, each present even when empty:

- `## Fixed` — one line per finding: its key, the commit, the family enumeration if any.
- `## Refuted` — key, what you checked, why the finding is wrong.
- `## Skipped` — key, the one-clause reason. A skip is re-adjudicated by the next round; it is not closed.
- `## Spec amendments` — every change to {SPEC}'s decision text, quoted before/after. An amendment made silently is indistinguishable from redefining the standard you are measured against.
- `## New mechanisms` — every mechanism the fixes introduced, one line each; each gets its own scoped re-review.
- `## Claims written` — every new factual claim you wrote into the pair, with the `path:line` or command output that backs it.
- `## Spec-blocked` — findings against a pinned, immutable spec (only when the pinned clause above applies).

Final message, at most four lines: the commit hash, the counts fixed / refuted / skipped derived by re-reading the report, and anything the spec left you unable to decide.

Run everything as plain blocking commands; background nothing; no subagents. Do not end your turn before the commit exists.
