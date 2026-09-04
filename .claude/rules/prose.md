# Prose — comments, docstrings, docs, rules

**A durable file holds STATE and DECISIONS; an EVENT goes to git.** State is what is true now; a decision is what was chosen and its one-clause why; what happened, was measured, read, found or corrected is an event, and its home is the message of the commit that carried it. The one test, at write time and at every review, for every sentence on every surface: *would it be false or pointless after the next change to what it describes?* Then it is an event in the wrong place — the evidence is wanted, the file is the wrong home. Length is not the test: a long sentence that names its own guard's limit is the standard working.

## Every surface

- **Necessity first**: a sentence that changes no reader's action does not belong, however correct — a point-in-time record that helps no cold reader is deleted, not corrected. Revising a sentence runs the same test before precision.
- **A claim that can be an assertion, a test or a hook becomes one, and the sentence goes** — the interpreter checks code for free; nothing checks prose but a second reader.
- **No coverage claims.** What a guard catches is what its assertions assert, and what it does not catch is never written — an enumerated blind spot is a completeness claim by omission; a blind spot that matters gets a test or a topic.
- **A number only where the reader needs a VALUE to act**, with the command that produced it and an it-drifts note — the latest value, never superseded ones stacked beside it; a property ("costs per inode") is stated and its measurement named, never quantified.
- **Every citation resolves from the repo alone** — a symbol, a test name, `T<NNNN>`, `spec NNNNN`, a path; a plan-task number carries its serial on the same line or the one it wraps from (`tests/test_code_prose_citations.py`); a hash is copied from git output, only for a commit that will not be rewritten — before push, cite by subject. **A closed citation is re-tensed, never deleted.**
- **Never describe live host state** — config prose says what a setting does, not what a host currently is.

## Code (`cli/`, `tests/`, `infra/`)

- **Prose says only what the code cannot**: a decision, an invariant the types do not hold, a refusal's reason — one sentence each. A docstring is one sentence of contract; a test's docstring is the one claim its assertions make, re-read when the red phase's fix lands. Status ("planned in `T<NNNN>`") lives in the topic — point at it.
- **Deduplicate within one artifact; a deployed artifact stands alone** — never a pointer across rendered files or hosts.
- **Pruning has four dispositions**: cut (false or stale), condense (true but long — prefer it to cutting), keep (load-bearing, or unverifiable but valuable), relocate (true but about another symbol — check the target first; it is often already there). Ask *is this about this symbol?* before *is this true?* A preceding block describes what follows it; only a same-line trailing comment binds to its line. Findings agreed per file before editing, false-or-stale first; a config file's non-comment lines extracted before and after, byte-identical.
- Internal tokens are fine in code prose except `WP<N>`, banned repo-wide (`operator-facing-text.md`).
- **`infra/scripts/prose-tripwire.py` flags the block, file, row, section or entry over its threshold** — a flagged one passes the necessity gate at review or is cut; the thresholds are the script's, not this file's.

## Docs (`docs/`, runbooks)

- **A living reference records current state; the event goes to the updating commit's message**, so the file never contradicts itself and `git log --follow` is its chronicle. A table row is its cells plus one clause; a topology doc carries paths, endpoints and access, nothing dated.
- **A changelog entry is one-line bullets, one per surface that changed, each saying what an operator or agent now does differently** — no code detail, counts, measurements or review narrative. Owed whenever such a surface changed (`spec-plan-locations.md`'s test), as the plan's final task; the file mechanics are the `iteration-closeout` skill's.
- **A completed-work sentence flips with the step that makes it true** — the push, the converge — never the merge: until that step runs, the old sentence is still true of the live stack. On a long-lived branch closeout is the branch's END: re-verify every status claim against the full branch log immediately before PR-open. A plan lists these as closeout tasks, never as edits made while planning; rule or doc text describing a not-yet-landed feature's behaviour lands with the feature. Codifying a convention already in practice is not a completion claim.
- Markdown: one line per paragraph or bullet, never hard-wrapped; escape `|` as `\|` inside a table's code spans — GFM otherwise splits the row and silently drops cells, and `docs/reference/` is outside mdformat's reach — check the rendered cell count after editing such a table.

## Rules and CLAUDE.md

- The shortest imperative of what to DO or NOT do, one line each; no narration — history, derivations, measurements, dates and rationale beyond one clause belong in specs and topics; the one-clause why only where the instruction would otherwise look wrong and get "corrected".
- **No references except operands** — a path you open, a script you run, a rule or skill you load; never a spec serial, a topic id or a line number — if a code pointer is needed, name the symbol.
- **CLAUDE.md carries only what changes Claude's behaviour; a config's mechanics live in the config.** A config CLAUDE.md does not mention is not touched without an explicit instruction, and a permission grant just proven too wide is proposed to the owner in that turn — never narrowed unilaterally, never worked around by a second entry point.
