# Refinement principles

## P1 — Single home, deliberate echoes

One home per instruction; every other artifact points. Sole allowed duplication: a safety invariant may appear ambient AND at point-of-use, the point-of-use copy in one-line form.

## P2 — Audience = a fresh Claude context

Keep-test per line: *would a fresh session act differently without it?* If no, the line goes.

## P3 — History goes to git; the why stays only where its absence invites "correction"

No dates, derivations, or narration. The one-clause why survives on rules that would otherwise look wrong and get "fixed".

## P4 — Load cost drives placement

Ambient iff needed before knowing the task (safety invariants, routing). Operation-scoped content lives in the operation's skill — the WHEN/HOW split (`open-topics.md` / `topic-ops` is the pattern). A skill's description is ambient; only its body is deferred.

## P5 — References are operands

Every `references/` file is named at the step that loads it. An unpointed reference is dead weight, not off-loading.

## P6 — Prefer enforcement over prose

A mechanically checkable rule becomes a test or hook; the prose shrinks to a pointer. A rule violated while written down is a mechanization candidate, not a wording problem.

## P7 — Lossless compression, verified — on every changed line

Rewriting can weaken an invariant without deleting anything, so the gate covers edits, not just removals: cold diff review plus the modal-language floor; nothing weakened or dropped without an itemized reason.

## P8 — Memory is the inbox, not an archive

Lessons land in memory first; rounds graduate, keep, or drop them jointly. Graduation stages the file; step 5 deletes it only after verification.
