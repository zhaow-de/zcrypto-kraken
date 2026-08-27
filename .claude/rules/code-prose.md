# Code prose (comments & docstrings in `cli/`, `tests/`, `infra/`)

Two gates at write time, in order. **Necessity**: a source file is not a story board — every sentence must answer "what could the next editor get wrong HERE?"; correct-but-idle narrative belongs in the commit message, the topic, or nowhere. **The rot test**: can this sentence become false without this file changing? A claim about the code beside it cannot drift; a claim about anything outside it will. Length is neither test — a long comment that names its own guard's limit is the standard working, not a defect.

- **State decisions and invariants, never statuses or schedules.** "Deliberately absent (`T<NNNN>` dropped it)" survives; "planned in `T<NNNN>`" / "acted on by nothing yet" rot the moment the work moves. Status lives in the topic — point at it.
- **Every citation resolves from the repo alone**: a symbol, a test name, `T<NNNN>`, `spec NNNNN`, a path. A plan-task number carries its 5-digit serial on the same line, or the line it wraps from (enforced by `tests/test_code_prose_citations.py`); a hash is copied from git output, never from memory; no blanket provenance stamp over independent facts.
- **Record a number only where the reader needs a VALUE to act** (sizing a window) — then the latest measurement plus an it-drifts note, never superseded values stacked beside it. Where a PROPERTY answers the question ("costs per inode"), record no figure; say how to measure instead.
- **Never describe live host state** — config prose says what the setting does, not what the host currently is.
- **A closed citation is RE-TENSED, never deleted** — "(`T<NNNN>`, resolved, records why)". Internal tokens are fine in code prose — except `WP<N>`, banned repo-wide; the rest are barred only from operator-visible surfaces (`operator-facing-text.md`).
- **Deduplicate only within one artifact.** A deployed artifact stands alone — never a pointer across rendered files or hosts. Within one file, explain once and point.
- **A test docstring is a claim about the assertions below it** — re-read it when the red phase's fix lands, or "Today X is broken" ships as prose describing the world the test just disproved.
