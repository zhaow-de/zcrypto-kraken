---
status: open
ripe_when: 'a milestone: rung 3''s first attended week closes; check: `git log --oneline origin/develop --merges --grep=records/rung3-week-1` prints a line'
---

# The engine publishes the gate's bare level before the boundary folds its holds

## Context — what

At a boundary the engine's metrics sink (`cli/engine/command.py`, `_make_exec_sink`) publishes the gate's own level before `on_boundary` (`cli/engine/executor.py`) republishes it with the three folded holds. A scrape landing between the two reads `zcrypto_exec_gate_level` at 2 under a folded hold, and an `on_boundary` that raises leaves that bare 2 standing for up to 60 s.

## Why this matters

`zcrypto-engine-exec-disarmed-boundary`, the rule #834 lands, reads that level over a span, so a bare 2 under a hold makes it wait one more span before it pages. Spec 00092's D6 has the gate level, D11's rule and the board read one figure, and for that scrape they read two. The fix is the sink's, an engine change on a new image.

## Findings so far

- Found by #834's pre-review and named in its body as an ask; registered on the owner's word of 2026-11-08, "Register T0227 (Recommended)", ripe beside [[T0226]], whose engine fix rolls on an image after the same week.

## Suggested next steps

- Publish the gate level once per boundary, after `on_boundary` folds the holds, and on a raise publish the gate's level with its holds rather than leave the bare one; prove it with a case whose sink is scraped between the two publishes today and reads the folded level, probed by `infra/scripts/mutate-probe.sh`.
- Ship it on the image that carries [[T0226]]'s fix, so one engine converge takes both.
