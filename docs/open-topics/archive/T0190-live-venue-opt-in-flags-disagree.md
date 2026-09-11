---
status: resolved
---

# Three flags implement the one live-venue opt-in

## Context — what

`CLAUDE.md` told an agent to gate a venue-reaching test on the explicit opt-in `ZCRYPTO_LIVE_VENUE_TESTS=1`, *"so a skip is a decision and never an outage read as coverage; with the flag set, every venue answer short of the expected one fails."* Three flags implement that class and they disagree twice over.

| flag | read by | documented | fails when set and the venue is unreachable |
| --- | --- | --- | --- |
| `ZCRYPTO_LIVE_VENUE_TESTS` | `test_engine_node.py`, `test_kraken_fixture_mint.py`, `test_tape_bars_rest_control.py` | yes, in `CLAUDE.md` | yes — `pytest.fail` |
| `ZCRYPTO_VENUE_CONTRACT` | `test_engine_flatten.py` | no | no — `skipif` only |
| `ZCRYPTO_E1B_LIVE` | `test_e1b_order_visibility_probe.py` | no | no — `skipif` only |

The `documented` column is as of 2026-09-08 and **is no longer true of any row**: `deaa3e7c7`,
the zero-base of the guidance corpus on 2026-09-10, deleted the paragraph quoted above along with
eleven rule files, and `git grep -n 'ZCRYPTO_LIVE_VENUE_TESTS' -- CLAUDE.md .claude/` returns nothing
at `608f3cc4e`. Nothing replaced it, so between that commit and this topic's resolution the rule was
carried by no surface a session loads. The rename below never depended on it — the owner's ruling
names the surviving flag on its own — but the argument in the next section did, and reads in the past
tense for that reason.

Measured with `git grep -hoE 'ZCRYPTO_[A-Z0-9_]+' -- cli/ tests/ infra/ | sort -u`, then each flag's readers listed and its skip arm opened. That sweep returns 25 distinct `ZCRYPTO_*` variables in all; the rest are configuration and deployment, not test control, and are out of this topic's scope.

## Why this matters

**The name divergence defeated the rule as written.** An agent doing what the rule said — set `ZCRYPTO_LIVE_VENUE_TESTS=1`, run the suite — got the two undocumented tests **silently skipped**. A skip is indistinguishable from a pass in a summary line, so the run reads as coverage of a venue contract nobody exercised. That is the precise outcome the rule exists to prevent, arriving through the rule being followed.

**There is no semantic divergence — this topic claimed one and it is false.** The original text held that only `ZCRYPTO_LIVE_VENUE_TESTS`' readers fail on an unreachable venue while the other two skip. Measured, every one of them fails: `unshare -rn env ZCRYPTO_VENUE_CONTRACT=1 uv run pytest tests/test_engine_flatten.py::test_a_client_call_inside_a_loop_answers_with_an_awaitable_the_module_must_await` gives **1 failed** with a DNS `RuntimeError`, not a skip, and `ZCRYPTO_E1B_LIVE=1` on the e1b sweep likewise fails where the unset flag skips. Every `skipif` in the class keys on the FLAG, never on reachability, so with the flag set an unreachable venue raises rather than skipping. `test_e1b_order_visibility_probe.py:146`'s comment — *"Gated on a variable, never on reachability"* — describes what the code does; the claim read it as an unfulfilled aspiration.

The claim was written by reading the `skipif` rather than running it, and it survived into this file because the surrounding argument about the names is correct. What remains is the name divergence alone.

## Findings so far

- Found by a blind reader on the `test_engine_flatten.py` docstring batch, as a Minor about a constant's name; the semantic half came out of the tree-wide sweep that followed, not from the finding.
- The fix cannot ride a docstring-pass branch: renaming a constant moves the AST, and those branches carry proven inertness as their whole value.
- `ZCRYPTO_E1B_LIVE`'s probe is an attended live-order path, so its opt-in is doing more work than a read-only contract check — whether one flag should cover both is part of the decision, not settled here.

## Resolution

- **Decided by the owner, 2026-09-09: one flag covers the class.** `ZCRYPTO_LIVE_VENUE_TESTS` is the opt-in for every venue-reaching test, including the order-placing probe — no second flag on blast-radius grounds, because the granularity buys nothing a reader can act on. So `ZCRYPTO_VENUE_CONTRACT` and `ZCRYPTO_E1B_LIVE` are renames, not a design question.

- **The two literals renamed** (`d4b34a260`, branch `fix/t0190-live-venue-opt-in`). `test_engine_flatten.py`'s constant moved with its value — `_VENUE_CONTRACT_OPT_IN` → `_LIVE_OPT_IN`, the spelling the other two files already use — because a constant named for a retired flag is the same reading error this topic exists to end. Each file's `skipif` reason interpolates its constant, so both reasons re-rendered themselves and nothing else in either file changed. Nothing outside `tests/` referenced either old name.

- **The behaviour re-measured under the new name**, since the rename could have moved it: `unshare -rn env ZCRYPTO_LIVE_VENUE_TESTS=1 uv run pytest` on the flatten venue pin gives **1 failed** with a DNS `RuntimeError`; unset, it skips and names the surviving flag. The e1b sweep was deliberately NOT run with the flag set — it places orders.

- **The guard** (`14ac33606`), `tests/test_live_venue_opt_in.py`. Two assertions over every skip gate in `tests/`, keyed on the shape of a gate and not on the names of the day: every gate whose condition reads the environment reads `ZCRYPTO_LIVE_VENUE_TESTS` and no other name, a key assembled at run time being refused rather than read; and no gate's condition reaches a network call, directly or through a helper in its own module. Together they are the fail-when-set arm as a property — with the opt-in set, a venue that does not answer can only FAIL, because nothing in the tree can turn its silence into a skip. A `pytest.fail` MAY read reachability, and that asymmetry is the point rather than an exception to it.

- **Which reading of "carries a fail-when-set arm" the guard took: the behaviour, not an explicit `pytest.fail` call.** This topic's own measurement is what settles it — the table's `no — skipif only` column was written by reading the gates rather than running them, and run, all three fail. Requiring a literal `pytest.fail` would mean adding a reachability probe to two tests that already fail correctly, a design change the owner's ruling did not authorise.

- **Both assertions proven with `infra/scripts/mutate-probe.sh`**, one run each, every control mutating a file under test rather than the guard's own constant — a control that moved `OPT_IN` would move both sides of the comparison and prove nothing. On `test_e1b_order_visibility_probe.py`: control the retired `ZCRYPTO_E1B_LIVE`, mutation `ZCRYPTO_LIVE_ORDER_TESTS`, **a fourth name that has never existed in this tree** — KILLED, which is the anti-staleness property measured rather than argued. On `test_engine_node.py`: control `pytest.fail` → `pytest.skip`, the arm literally removed; mutation `or not _kraken_public_reachable()` folded into the opt-in gate — KILLED.

- **The class has a member this topic's table does not list, and it is an opt-OUT.** `test_kraken_fixture_mint.py:667` gates on the same flag with inverted polarity: it skips *when the flag is set*, because it asserts the live doors are shut and setting the flag deliberately opens them. "Every gate keyed on the opt-in carries a fail-when-set arm" is false for it by design. It needed no special case — both assertions are about what a condition reads, not which way it points.

- **The census the guard walks**: six skip gates in `tests/` read the environment and all six are venue opt-ins; fifty-five others skip on an absent dataset, a uid or a missing binary. So the degeneracy control lives in the tree rather than only in a fixture, and a third test requires both counter-shapes to be present — a non-environment gate, and a reachability-keyed `pytest.fail` — so neither main assertion can pass vacuously on an empty set.

- **Where the rule lived at the moment this closed**, measured rather than assumed: in `tests/test_live_venue_opt_in.py`'s module docstring, in this file, and in no surface a session loads — `deaa3e7c7` deleted the corpus paragraph on 2026-09-10 and nothing replaced it. That is a statement about the tree on this date and not a task parked here; the guidance line is `zcrypto-marco`'s, and the PR that carries this resolution records what became of it.
