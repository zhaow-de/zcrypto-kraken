---
status: resolved
---

# The soak report re-caps the book with module defaults while the builder used the configured caps

## Context — what

`cli/engine/soak.py` rebuilds the combined book twice to cross-check the builder against itself. One of those rebuilds still caps it with `apply_position_caps(combined)` — no cap arguments: `realized_internals`. `apply_position_caps` (`cli/risk/limits.py`) defaults `long_cap=0.20, short_cap=0.10`. The builder caps the same book with `long_cap=c.long_cap, short_cap=c.short_cap` off `CrossfreqSystemConfig`, whose own field defaults are those same two literals.

So that rebuild and the builder agree by a coincidence of two independent defaults, not by construction. Every other call site in the tree states the caps explicitly — `cli/portfolio/builder.py`, `cli/portfolio/crossfreq_system.py`, `cli/portfolio/record43_book.py`, `cli/engine/cycle.py`, `cli/engine/feeders.py`, and now `soak.py`'s own `_net_live_from_result`; `realized_internals` is the one site left.

## Why this matters

`realized_internals`' cap disagreement feeds a void reason. Its `breach` array is summed into `completed_breaches`, `cap_consistent` is `completed_breaches == result.cap_breach_bars`, and `soak_report` appends `cap-breach inconsistent` to `void_reasons` when that is false. A rebuild capping at a different level than the builder therefore VOIDS a healthy soak window — on the instrument the go-live decision reads, for a disagreement the report manufactured.

It was not reachable on the tree as it stood: `realized_internals` built with a default `CrossfreqSystemConfig()`, so the two default sets agreed. The defect would have fired the moment either literal moved, or a caller threaded a config through — which is what a config parameter exists for, and which the Resolution below does.

## Findings so far

- The call reads correct at the site. `apply_position_caps(combined)` looks like *cap it the way the system caps it*, and it does, but only because two literals in two modules happen to match.
- Found while closing `T0183`'s census; out of that branch's scope under `general.md` — it is not an empty-denominator defect, and the branch changed neither the caps nor the void gate's inputs. Named rather than fixed.

## Resolution

- **`_net_live_from_result` threads the configured caps** — `capped = apply_position_caps(combined, long_cap=long_cap, short_cap=short_cap)`, with `build_null` passing `long_cap=config.long_cap, short_cap=config.short_cap`. Landed in PR #462, whose commit names this defect and reasons about it; it was not taken as this topic's work, so it carries no guard of its own. The site's own consequence — a mis-measured `NullSystem.cap_breach` feeding `analyze_soak`'s `cap_breach` verdict — is closed with it.

- **The remaining site threads the caps** — `realized_internals` takes a `config` and caps with its `long_cap`/`short_cap`, so the rebuild and the builder agree by construction rather than by a coincidence of two defaults in two modules. The guard is written so it cannot be degenerate, which is what the step asked for: the fixture's combined position is 0.09, which breaches a configured 0.05 cap and not the 0.20 default, and the default-capped control is asserted in the same case. Restoring the bare call is KILLED by `infra/scripts/mutate-probe.sh`.
- **The defaults stay, and the decision is a check.** Measured first: after the fix all nine production call sites state both caps, and every bare call left in the tree is a test — six in `tests/test_risk_limits.py`, which document the defaults, and two in `tests/test_engine_soak.py`, which build fixture books. So removing the defaults would push the same two literals into every one of those cases — the same duplication moved rather than removed. What went wrong here was not that defaults exist but that a call site could take them silently while its own config said otherwise, and that is now refused: a bare `apply_position_caps(x)` anywhere under `cli/` fails `tests/test_risk_limits.py`.
