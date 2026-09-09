---
status: partial
---

# Three flags gate the live-venue tests, `CLAUDE.md` documents one, and only one fails on an outage

## Context — what

`CLAUDE.md` tells an agent to gate a venue-reaching test on the explicit opt-in `ZCRYPTO_LIVE_VENUE_TESTS=1`, *"so a skip is a decision and never an outage read as coverage; with the flag set, every venue answer short of the expected one fails."* Three flags implement that class and they disagree twice over.

| flag | read by | documented | fails when set and the venue is unreachable |
| --- | --- | --- | --- |
| `ZCRYPTO_LIVE_VENUE_TESTS` | `test_engine_node.py`, `test_kraken_fixture_mint.py`, `test_tape_bars_rest_control.py` | yes, in `CLAUDE.md` | yes — `pytest.fail` |
| `ZCRYPTO_VENUE_CONTRACT` | `test_engine_flatten.py` | no | no — `skipif` only |
| `ZCRYPTO_E1B_LIVE` | `test_e1b_order_visibility_probe.py` | no | no — `skipif` only |

Measured with `git grep -hoE 'ZCRYPTO_[A-Z0-9_]+' -- cli/ tests/ infra/ | sort -u`, then each flag's readers listed and its skip arm opened. That sweep returns 25 distinct `ZCRYPTO_*` variables in all; the rest are configuration and deployment, not test control, and are out of this topic's scope.

## Why this matters

**The name divergence defeats the rule as written.** An agent doing what `CLAUDE.md` says — set `ZCRYPTO_LIVE_VENUE_TESTS=1`, run the suite — gets the two undocumented tests **silently skipped**. A skip is indistinguishable from a pass in a summary line, so the run reads as coverage of a venue contract nobody exercised. That is the precise outcome the rule exists to prevent, arriving through the rule being followed.

**The semantic divergence is the sharper half and survives even a correct flag.** `CLAUDE.md` requires that with the flag set, an unreachable venue **fails**. Only `ZCRYPTO_LIVE_VENUE_TESTS`' readers implement that arm. The other two are `skipif` alone, so setting their own flag and losing the venue still yields a skip — an outage read as coverage, which is the same defect one layer in. `test_e1b_order_visibility_probe.py:146` states the principle in its own comment (*"a skip on an unreachable venue reads as coverage"*) and then does not implement the failing half.

## Findings so far

- Found by a blind reader on the `test_engine_flatten.py` docstring batch, as a Minor about a constant's name; the semantic half came out of the tree-wide sweep that followed, not from the finding.
- The fix cannot ride a docstring-pass branch: renaming a constant moves the AST, and those branches carry proven inertness as their whole value.
- `ZCRYPTO_E1B_LIVE`'s probe is an attended live-order path, so its opt-in is doing more work than a read-only contract check — whether one flag should cover both is part of the decision, not settled here.

## Done so far

- **Decided by the owner, 2026-09-09: one flag covers the class.** `ZCRYPTO_LIVE_VENUE_TESTS` is the opt-in for every venue-reaching test, including the order-placing probe — no second flag on blast-radius grounds, because the granularity buys nothing a reader can act on. So `ZCRYPTO_VENUE_CONTRACT` and `ZCRYPTO_E1B_LIVE` are renames, not a design question, and `CLAUDE.md`'s sentence already names the surviving flag and needs no change.

## Suggested next steps
- **Give every flag in the class the failing arm**, so that with the flag set an unreachable venue fails rather than skips. That is the half `CLAUDE.md` already requires and two of three readers omit.
- **The guard, and its degeneracy.** A test asserting that every `skipif`/`skip` gate in `tests/` keyed on a venue opt-in also carries a fail-when-set arm — constructed so that removing the arm from any one of them turns it red, with a gate that legitimately has no venue dependency passing beside it. A guard that only enumerates today's three flag names goes stale the moment a fourth is added; key it on the shape, not the list.
- **Then reconcile `CLAUDE.md`'s sentence with whatever lands**, in the same change — the rule names one flag today and would name the wrong set the moment a second is sanctioned.
