# General

*The working discipline for every task; the rules beside this file scope it.*

- **State every assumption and mark it** — *validated* (by which command), *assumed*, or *unknown*; a premise about the tree, a library, a runtime or a venue is validated by a command before anything is built on it.
- **Two or three readings that lead to different work are presented with their tradeoffs, never picked silently**; a symptom is named apart from its cause before either is fixed.
- **Unclear is a stop, not a guess** — name what is confusing and ask the session's authority: the owner attended, `zcrypto-marco` for a payload session; an unattended `zcrypto-auto-exec` run decides reversible forks itself and parks only irreversible steps.
- **The minimum mechanism that solves the problem** — nothing beyond what was asked, no abstraction for single-use code, no speculative flexibility or configurability, no "while I'm here"; a mechanism four times the size it needs is rewritten. The proofs the rules require — tests, guards, refusals over silent defaults — are part of the problem, never extras to trim.
- **Touch only what the request or a rule requires** — no improving adjacent code, comments or formatting, no refactoring what is not broken; match the existing style and copy the sibling that already solves the mechanism before writing your own; remove what your change made unused, and name pre-existing dead code rather than deleting it. Every changed line traces to the request or to a rule.
- **Done is an outcome that can be told, never a merge** — a vague task becomes a verifiable goal (a failing test that reproduces the bug, then passes; tests identical before and after a refactor; a real flow completing end to end), confirmed on the surface it lands on after the step that makes it live; multi-step work states its plan as `step → verify` lines first.
