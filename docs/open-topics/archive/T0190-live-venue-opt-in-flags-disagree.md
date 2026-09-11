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

The `documented` column is as of 2026-09-08 and **the one `yes` in it is no longer true**; the two
`no` cells still are. `deaa3e7c7`,
the zero-base of the guidance corpus on 2026-09-10, deleted the paragraph quoted above along with
eleven rule files, and `git grep -n 'ZCRYPTO_LIVE_VENUE_TESTS' -- CLAUDE.md .claude/` returns nothing
at `608f3cc4e`. Nothing replaced it, so between that commit and this topic's resolution the rule was
carried by no surface a session loads. The rename below never depended on it — the owner's ruling
names the surviving flag on its own — but the argument in the next section did, and reads in the past
tense for that reason.

Row 1's `fails when set` cell is wrong for one of its three files and stayed wrong until this
resolution: `test_kraken_fixture_mint.py`'s gate is an opt-OUT, skipping when the flag IS set, and it
carries no `pytest.fail` and correctly never will. The cell reads as a property of the flag where it
is a property of two of the three readers.

Measured with `git grep -hoE 'ZCRYPTO_[A-Z0-9_]+' -- cli/ tests/ infra/ | sort -u`, then each flag's readers listed and its skip arm opened. That sweep returned 25 distinct `ZCRYPTO_*` variables on 2026-09-08 and returns 26 at this topic's resolution, the new one being the second flag name in the guard's own fixture; the rest are configuration and deployment, not test control, and are out of this topic's scope.

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

- **The two literals renamed** (`d4b34a260`, branch `fix/t0190-live-venue-opt-in`). `test_engine_flatten.py`'s constant moved with its value — `_VENUE_CONTRACT_OPT_IN` → `_LIVE_OPT_IN`, the spelling the other two files already use — because a constant named for a retired flag is the same reading error this topic exists to end. Each file's `skipif` reason interpolates its constant, so both reasons re-rendered themselves and nothing else in either file changed. `git grep 'ZCRYPTO_VENUE_CONTRACT\|ZCRYPTO_E1B_LIVE' -- tests/ cli/ infra/ .claude/ CLAUDE.md` returns
nothing after the rename. `d4b34a260`'s message states that as "nothing outside `tests/` referenced
either old name", which is broader than the command under it: swept over the whole tree, two files
still carry `ZCRYPTO_VENUE_CONTRACT`. `docs/plans/00106-engine-flatten.md:4104` is a committed plan and
a frozen record of the change that introduced the flag, and stays. `docs/open-topics/T0159-*.md:33` was
NOT frozen — a live `partial` topic whose `ripe_when` sends someone to an attended session — and it is
re-trued in the same commit as this one, because a live topic telling a reader to set a flag that gates
nothing is the defect this topic is about.

- **The behaviour re-measured under the new name**, since the rename could have moved it: `unshare -rn env ZCRYPTO_LIVE_VENUE_TESTS=1 uv run pytest` on the flatten venue pin gives **1 failed** with a DNS `RuntimeError`; unset, it skips and names the surviving flag. The e1b sweep was deliberately NOT run with the flag set — it places orders.

- **The guard** (`a96438b6c` as first written, rewritten in `b8ae6368b`), `tests/test_live_venue_opt_in.py`. THREE assertions over every skip gate in `tests/`, keyed on the shape of a gate and not on the names of the day: every gate whose guards read the environment reads `ZCRYPTO_LIVE_VENUE_TESTS` and no other name; no gate's guards reach a network client library, directly or through a helper this repo owns; and no gate is decided by something the guard cannot read, so an unresolvable helper or a run-time-assembled key fails rather than passes. Together they are the fail-when-set arm as a property — with the opt-in set, a venue that does not answer can only FAIL, because nothing in the tree can turn its silence into a skip. A `pytest.fail` MAY read reachability, and that asymmetry is the point rather than an exception to it.

- **The first shape of that guard was wrong in three ways and the branch read found all three**, each demonstrated by planting the real defect and watching `pytest -q` report 7 passed: an environment read spelled `getenv(NAME)` or `NAME in os.environ` was counted as reading nothing; a `pytest.skip()` in an `else:` or an `except:` produced no gate at all, so `try: urlopen(...) except OSError: pytest.skip(...)` — the commonest reachability skip, which has no condition anywhere — was invisible; and a decision one module away was unreadable and therefore clean. It reads GUARDS now rather than conditions: a `skipif` condition, the test of every enclosing `if` whichever branch the skip sits in, and the BODY of an enclosing `try` when the skip sits in a handler.

- **One of those three had already been handed to me and I closed it.** A fourth mutation probe came back SURVIVED; its mutation called a helper that exists nowhere, so the walker followed nothing and the gate read clean. That reasoning is right about the probe and the conclusion drawn from it was wrong — the finding was not "the probe measured an absence" but "a call this walker cannot resolve is treated as clean", the same hole whether the name is absent or one file over. The two halves are separable and only one of them was examined.

- **Which reading of "carries a fail-when-set arm" the guard took: the behaviour, not an explicit `pytest.fail` call.** This topic's own measurement is what settles it — the table's `no — skipif only` column was written by reading the gates rather than running them, and run, all three fail. Requiring a literal `pytest.fail` would mean adding a reachability probe to two tests that already fail correctly, a design change the owner's ruling did not authorise.

- **Proven with `infra/scripts/mutate-probe.sh`: five probes, all KILLED**, every control mutating a file under test rather than the guard's own constant — a control that moved `OPT_IN` would move both sides of the comparison and prove nothing. A fourth name that has never existed in this tree (`test_e1b_order_visibility_probe.py`), which is the anti-staleness property measured rather than argued; reachability folded into a real opt-in gate (`test_engine_node.py`); a flag read moved one call away into a helper three real gates call (`test_count_list.py`); that same read written as `"X" not in os.environ` (`test_tape_bars_rest_control.py`); and that same helper re-imported from a module that cannot be read, so three real gates lose their whole decision (`test_count_list.py`). The last two survive the guard's first shape. The `else`/`except` half is proven by a planted worktree rather than a probe, because a sed expression cannot restructure a statement into a branch.

- **The class has an opt-OUT member, which the table lists without distinguishing.** `test_kraken_fixture_mint.py` is named in row 1, so the file was never missing; what the table does not say is that its gate at line 667 has inverted polarity — it skips *when the flag is set*, because it asserts the live doors are shut and setting the flag deliberately opens them. "Every gate keyed on the opt-in carries a fail-when-set arm" is false for it by design, and row 1's `yes — pytest.fail` cell is the place that reads otherwise. It needed no special case in the guard: every assertion there is about what a gate's guards read, not which way they point.

- **The census the guard walks**, re-derived at this resolution: 61 skip gates in `tests/`, of which 6 read the environment and all 6 name `ZCRYPTO_LIVE_VENUE_TESTS`. The other 55 are not one kind — 32 test a path on disk, 4 the effective uid, 3 whether a git ref resolves, 1 a binary on `PATH`, and 15 something else again, mostly whether a collection came back empty. An earlier wording here called all 55 "an absent dataset, a uid or a missing binary", which describes about three quarters of them. Two reachability-keyed `pytest.fail` gates exist, both in `test_engine_node.py`. So the degeneracy control lives in the tree rather than only in a fixture, and a fourth test requires both counter-shapes to be present — a non-environment gate, and a reachability-keyed `pytest.fail` — so no assertion can pass vacuously on an empty set.

- **Where the rule lived at the moment this closed**, measured rather than assumed: in `tests/test_live_venue_opt_in.py`'s module docstring, in this file, and in no surface a session loads — `deaa3e7c7` deleted the corpus paragraph on 2026-09-10 and nothing replaced it. That is a statement about the tree on this date and not a task parked here; the guidance line is `zcrypto-marco`'s, and the PR that carries this resolution records what became of it.
