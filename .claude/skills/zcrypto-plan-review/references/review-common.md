# Common block — appended to every reviewing prompt (pin, lenses, executability, blind, scoped)

## Severity — the rule every count depends on

A finding is **Critical or Important only if a concrete failure scenario can be stated in which it changes what ships, what an operator does, or what a number says.** Write that scenario out. If one cannot be written, the finding is Minor — by construction, regardless of how wrong it feels.

**Critical** — the scenario reaches production, is irreversible, loses data, or defeats a safety guard. **Important** — meets that bar but is recoverable. **Minor** — everything else.

The blast radius of this pair — anything outside these is Minor by construction:

{BLAST_RADIUS}

## Evidence

A finding that cannot quote the line it judges is not a finding. Verify every claim against the real file before writing it. A claim about runtime behaviour is verified by running it, never by reading it: an introspection predicate, a docstring and a name are claims, not behaviour. A docstring that names a function's callers is not an enumeration of its callers.

## Report shape — `{OUT}`

One block per finding, nothing else under a `###`. Copy this heading **literally**, square brackets included — they are part of the text, not a choose-one notation; substitute only the severity word, the origin word and the path (a script clusters on it):

```
### [Important] · [in-original] · docs/plans/00042-example.md:117
**Quote:** `<the line, verbatim>`
**Defect:** <what is wrong>
**Scenario:** <the concrete failure — required for Critical and Important>
**Consequence:** <what ships / what an operator does / what a number says — one line, present on every finding>
**Fix:** <the smallest change that closes it; if it has a family, name the family and every member you found>
```

- Origin is a claim about PROVENANCE, and `git blame` on the line you quote settles it — use it rather than guessing: `in-original` means the line predates every fix commit on this branch; `last-fix` means the commit named in the prior fix report wrote it; `earlier-fix` means an older fix did. Measured on one run, reviewers guessing without checking were right three times in sixteen. If you are given no prior fix report and cannot run `git blame`, say so in the finding rather than defaulting — a wrong origin makes the loop's own damage look like the author's.
- Write `<path>:<line>` exactly as the file is named in the tree — two reports naming one line the same way are clustered; two ways of naming it are two findings.
- Nothing is "noted" or "worth mentioning" outside a finding block; a remark that is not a finding is not written.

Final message, at most three lines: the report path, and its counts **derived by re-reading the report's headings** — not from memory of what was written.
