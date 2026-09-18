---
status: resolved
---

# Guidance clauses the skip-gate matcher falsifies

## Context — what

Spec 00114 replaced the reducer that `CLAUDE.md`'s two venue-opt-in entries describe with a matcher, and five of their clauses read false once it merges.

The edit is the owner's and rides its own guidance branch (spec 00114 D5), so the branch that falsified them records them here rather than in its PR body: `.claude/skills/open-pr/SKILL.md` is explicit that `## Follow-ups` may only reference a registered topic, because a PR description is never re-read after merge.

A sixth carrier is NOT here: the same reducer clauses stood as a comment above `c_skip_gate_contract` in `infra/scripts/count-list.sh`, and a comment is not guidance, so this branch re-trued it in place rather than parking it (`649f395c8`).

## Why this matters

A false guidance clause is read and acted on before anyone checks it against the tree, and one of these five tells a session to do something the guard now refuses.

"A computed key, or a call it can neither resolve in this repo nor attribute to a library, refused; a library call attributed, not walked" reads as a licence to gate a test on a helper in its own file, which is exactly the shape the matcher refuses: under spec 00114 D2 and D3 every call but a call into `tests/skip_gates.py` is refused, a resolvable local call and a library call included.
A session that follows the clause writes the gate, meets a red `infra/scripts/count-list.sh skip-gate-contract`, and has no line of guidance telling it why.

"No count command: nothing asserts it" is the reachability entry's own account of its status, and it is the clause this whole change was about: the property is held now, and the entry still says nothing holds it.

## Findings so far

- `CLAUDE.md`'s reachability entry (line 33 at this registration) carries two of the five.
  - "no count command: nothing asserts it" — the count is now `infra/scripts/count-list.sh skip-gate-contract`, over what a gate is written and bound to. One reading is left over rather than claimed closed: the provenance of a registry call's argument, which spec 00114 D5 names and T0206 carries.
  - "`tests/test_live_venue_opt_in.py`'s docstring records that it takes a static analyser" — that docstring was rewritten on this branch (`649f395c8`) and no longer says so.
- `CLAUDE.md`'s one-name entry (line 32 at this registration) carries the other three, and this branch is the count entry behind it.
  - "its gate a plain module-level reading the guard reduces" — the matcher matches each guard against six forms and refuses what matches none; it reduces nothing, and the reducer's resolution is deleted.
  - "a computed key, or a call it can neither resolve in this repo nor attribute to a library, refused; a library call attributed, not walked" — false in both halves, as the section above sets out.
  - "its docstring lists the five binding shapes and two `unittest` forms that pass it uncaught and unrefused" — spec 00114 D2 refuses the five binding shapes and D6 makes the two `unittest` forms gates the walker finds, so the docstring sections that listed them were deleted with the holes they described.
- What the entries can truthfully say instead is in the tree already: the six forms and the refusal are stated in the comment above `c_skip_gate_contract` in `infra/scripts/count-list.sh`, and the remedy a refusal prints is `_REFUSAL_REMEDY` in the guard.

## Resolution

Refine round 13, on `claude/ledger-pre-read-by-tip`: `ebae58c02` rewrote both `CLAUDE.md` entries — the one-name entry names the six forms `tests/test_live_venue_opt_in.py` matches and the refusal it prints, the reachability entry carries the count `infra/scripts/count-list.sh skip-gate-contract` and the reason the count holds it, no form reaching a venue — and `8bbe0edbf`'s condensation left what the guard does not hold to the guard's docstring, which names T0206 and T0207, rather than repeating them in the entry. The five false clauses are gone; `sed -n '33,34p' CLAUDE.md`, the guard's docstring and the comment above `c_skip_gate_contract` say one thing.
