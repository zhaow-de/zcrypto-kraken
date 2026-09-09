---
status: open
---

# The soak report re-caps the book with module defaults while the builder used the configured caps

## Context — what

`cli/engine/soak.py` rebuilds the combined book twice to cross-check the builder against itself, and both rebuilds cap it with `apply_position_caps(combined)` — no cap arguments: `realized_internals` at `:784` and `_net_live_from_result` at `:296`. `apply_position_caps` (`cli/risk/limits.py`) defaults `long_cap=0.20, short_cap=0.10`. The builder caps the same book with `long_cap=c.long_cap, short_cap=c.short_cap` off `CrossfreqSystemConfig`, whose own field defaults are those same two literals.

So the rebuild and the builder agree by a coincidence of two independent defaults, not by construction. Every other call site in the tree states the caps explicitly — `cli/portfolio/builder.py`, `cli/portfolio/crossfreq_system.py`, `cli/portfolio/record43_book.py`, `cli/engine/cycle.py`, `cli/engine/feeders.py`; `cli/engine/soak.py` is the only file that does not.

## Why this matters

`realized_internals`' cap disagreement feeds a void reason. Its `breach` array is summed into `completed_breaches`, `cap_consistent` is `completed_breaches == result.cap_breach_bars`, and `soak_report` appends `cap-breach inconsistent` to `void_reasons` when that is false. A rebuild capping at a different level than the builder therefore VOIDS a healthy soak window — on the instrument the go-live decision reads, for a disagreement the report manufactured.

`_net_live_from_result` is the same call inside `build_null`, which threads `config` into the builder explicitly and then re-caps without it. Its `cap_breach` list becomes `NullSystem.cap_breach`, the null side of `analyze_soak`'s `cap_breach` gating verdict; there the consequence is a mis-measured null rather than a void.

Neither is reachable on today's tree: `realized_internals` builds with a default `CrossfreqSystemConfig()`, and no caller hands `build_null` a non-default one. The defect fires the moment either default literal moves, or a caller threads a config through — which is what a config parameter exists for.

## Findings so far

- The call reads correct at the site. `apply_position_caps(combined)` looks like *cap it the way the system caps it*, and it does, but only because two literals in two modules happen to match.
- Found while closing `T0183`'s census; out of that branch's scope under `general.md` — it is not an empty-denominator defect, and the branch changed neither the caps nor the void gate's inputs. Named rather than fixed.

## Suggested next steps

- Thread the caps through both call sites. `realized_internals` builds its own result, so the config is in hand; `_net_live_from_result` takes `result` plus the two fee arguments and would take the caps (or the config) the same way.
- **The guard, and its degeneracy.** A soak fixture built with a non-default `long_cap`/`short_cap` whose cap-breach count *differs* from the default-capped one, asserting `cap_consistent is True` and no `cap-breach inconsistent` in `void_reasons`; restoring the bare `apply_position_caps(combined)` must make it red. A fixture where both cap levels produce the same breach count passes under the defect and proves nothing.
- Decide whether `apply_position_caps`' keyword defaults should exist at all. `CrossfreqSystemConfig` already carries the caps, and a second set of defaults beside it is exactly what lets a call site look correct while ignoring the configured value.
