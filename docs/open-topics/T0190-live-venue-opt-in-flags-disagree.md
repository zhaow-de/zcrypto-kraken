---
status: partial
---

# Three flags gate the live-venue tests and `CLAUDE.md` documents one

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

**There is no semantic divergence — this topic claimed one and it is false.** The original text held that only `ZCRYPTO_LIVE_VENUE_TESTS`' readers fail on an unreachable venue while the other two skip. Measured, every one of them fails: `unshare -rn env ZCRYPTO_VENUE_CONTRACT=1 uv run pytest tests/test_engine_flatten.py::test_a_client_call_inside_a_loop_answers_with_an_awaitable_the_module_must_await` gives **1 failed** with a DNS `RuntimeError`, not a skip, and `ZCRYPTO_E1B_LIVE=1` on the e1b sweep likewise fails where the unset flag skips. Every `skipif` in the class keys on the FLAG, never on reachability, so with the flag set an unreachable venue raises rather than skipping. `test_e1b_order_visibility_probe.py:146`'s comment — *"Gated on a variable, never on reachability"* — describes what the code does; the claim read it as an unfulfilled aspiration.

The claim was written by reading the `skipif` rather than running it, and it survived into this file because the surrounding argument about the names is correct. What remains is the name divergence alone.

## Findings so far

- Found by a blind reader on the `test_engine_flatten.py` docstring batch, as a Minor about a constant's name; the semantic half came out of the tree-wide sweep that followed, not from the finding.
- The fix cannot ride a docstring-pass branch: renaming a constant moves the AST, and those branches carry proven inertness as their whole value.
- `ZCRYPTO_E1B_LIVE`'s probe is an attended live-order path, so its opt-in is doing more work than a read-only contract check — whether one flag should cover both is part of the decision, not settled here.

## Done so far

- **Decided by the owner, 2026-09-09: one flag covers the class.** `ZCRYPTO_LIVE_VENUE_TESTS` is the opt-in for every venue-reaching test, including the order-placing probe — no second flag on blast-radius grounds, because the granularity buys nothing a reader can act on. So `ZCRYPTO_VENUE_CONTRACT` and `ZCRYPTO_E1B_LIVE` are renames, not a design question, and `CLAUDE.md`'s sentence already names the surviving flag and needs no change.

## Suggested next steps
- **Rename the two divergent literals** to `ZCRYPTO_LIVE_VENUE_TESTS`: `tests/test_engine_flatten.py`'s `_VENUE_CONTRACT_OPT_IN` and `tests/test_e1b_order_visibility_probe.py`'s `LIVE_OPT_IN`. Both surrounding comments interpolate the constant, so nothing else in either file changes, and `CLAUDE.md` needs no edit — the owner's ruling already names the surviving flag.
- **The guard, and its degeneracy.** A test asserting that every `skipif`/`skip` gate in `tests/` keyed on a venue opt-in also carries a fail-when-set arm — constructed so that removing the arm from any one of them turns it red, with a gate that legitimately has no venue dependency passing beside it. A guard that only enumerates today's three flag names goes stale the moment a fourth is added; key it on the shape, not the list.
