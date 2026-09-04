# General

*The working discipline for every task; the operational rules beside this file scope it.*

## Think before coding

**Don't assume. Surface tradeoffs. Ask when unclear.**

- State assumptions; mark each *validated* (by which command) / *assumed* / *unknown*.
- Multiple interpretations → present 2–3 with tradeoffs; don't pick silently.
- Distinguish symptom from root problem.
- Unclear? Stop, name what's confusing, and ask the session's authority — the owner attended, `zcrypto-main` as a payload session; an unattended `zcrypto-auto-exec` run decides reversible forks itself and parks only irreversible steps.

## Simplicity first

**Minimum mechanism that solves the problem. Nothing speculative — the proofs the rules require (tests, guards, refusals over silent defaults) are part of the problem, never extras to trim.**

- No features beyond what was asked. No "while I'm here."
- No abstractions for single-use code.
- No speculative flexibility or configurability.
- 200 lines that could be 50? Rewrite it.

## Surgical changes

**Touch only what you must. Clean up only your own mess.**

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style — copy the sibling that already solves the mechanism before writing your own.
- Remove imports / variables / functions that *your* changes made unused.
- Don't delete pre-existing dead code — mention it instead.

The test: every changed line traces to the user's request or to a rule that requires it.

## Define done by outcome, not output

**"Merged" is not "done." Done is "it works and we can tell."**

- Turn vague tasks into verifiable goals: a failing test that reproduces the bug then passes; tests pass identically before/after a refactor; a real flow completes end-to-end.
- Confirm the outcome on the surface it lands on, after the step that makes it live — never at the merge.
- For multi-step work, state a brief plan as `step → verify` lines.
