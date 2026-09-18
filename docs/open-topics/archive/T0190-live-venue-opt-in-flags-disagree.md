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

The `documented` column is as of 2026-09-08. The rename below never depended on the rule being
written down — the owner's ruling names the surviving flag on its own — but the argument in the next
section did, and reads in the past tense for that reason.

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

- **The two literals renamed** (`d4b34a260`, branch `fix/t0190-live-venue-opt-in`). `test_engine_flatten.py`'s constant moved with its value — `_VENUE_CONTRACT_OPT_IN` → `_LIVE_OPT_IN`, the spelling the other two files already use — because a constant named for a retired flag is the same reading error this topic exists to end. Each file's `skipif` reason interpolates its constant, so both reasons re-rendered themselves and nothing else in either file changed. After the rename, no live instruction anywhere tells a reader to set either retired name. Every
surviving occurrence is a record of what they WERE, in four FILES, measured with `git grep -l`:
 this file; `docs/plans/00106-engine-flatten.md:4104`, a committed plan;
`docs/open-topics/T0159-*.md:33`, whose clause is re-trued here; and `tests/test_live_venue_opt_in.py`,
whose module docstring names both as the history the guard exists to prevent repeating. That last one
is why the narrower sweep is not empty either: `git grep 'ZCRYPTO_VENUE_CONTRACT\|ZCRYPTO_E1B_LIVE' --
tests/ cli/ infra/ .claude/ CLAUDE.md` returns ONE hit, the guard's own docstring -- a guard that
names what it forbids is inside its own corpus, and that hit is expected rather than a regression.
`d4b34a260`'s message says "Nothing outside `tests/` referenced either old name", and that is one
sentence with one error: three files outside `tests/` do carry `ZCRYPTO_VENUE_CONTRACT`. An earlier
version of this paragraph attributed a `git grep` command to that message and called the sentence
wrong in both halves; the message contains no command -- the quoted sweep is this file's own, three
paragraphs above -- and the one hit it returns is INSIDE `tests/`, so it cannot falsify a claim about
what lies outside it. `docs/plans/00106-engine-flatten.md:4104` is a committed plan and
a frozen record of the change that introduced the flag, and stays. `docs/open-topics/T0159-*.md:33` was
NOT frozen — a live `partial` topic whose `ripe_when` sends someone to an attended session — and it is
re-trued in the same commit as this one, because a live topic telling a reader to set a flag that gates
nothing is the defect this topic is about.

- **The behaviour re-measured under the new name**, since the rename could have moved it: `unshare -rn env ZCRYPTO_LIVE_VENUE_TESTS=1 uv run pytest` on the flatten venue pin gives **1 failed** with a DNS `RuntimeError`; unset, it skips and names the surviving flag. The e1b sweep was deliberately NOT run with the flag set — it places orders.

- **The guard**, `tests/test_live_venue_opt_in.py`. What SHIPPED is `bfab0df7e`, which REPLACED the recognition engine rather than widening it: it reduces each guard expression to a reading and REFUSES what it cannot reduce, so an unrecognised shape fails by construction. `a96438b6c` wrote the first shape and `b8ae6368b`, `99f96fb0f` and `7959a5f13` widened it three times first. Naming only the early commits, which an earlier version of this bullet did, sends a reader who checks one out to a walker missing most of what shipped. TWO assertions over every skip gate in `tests/`, keyed on the shape of a gate and not on the names of the day: every gate whose guards read the environment reads `ZCRYPTO_LIVE_VENUE_TESTS` and no other name, and no gate is decided by something the guard cannot read — an unresolvable helper or a run-time-assembled key fails rather than passes.

  **A third assertion was written and did not ship on that branch.** "No gate's guards reach the venue" was asserted from `a96438b6c` to `bfab0df7e` and removed in `7b920d00c` on the owner's ruling of 2026-09-11, because four review rounds could not make it hold. It was this topic's one open sub-item until spec 00114, and nothing above this paragraph should be read as delivering it — the closing paragraph of this section is what does.

- **The first shape of that guard was wrong in three ways and the branch read found all three**, each demonstrated by planting the real defect and watching `pytest -q` report 7 passed: an environment read spelled `getenv(NAME)` or `NAME in os.environ` was counted as reading nothing; a `pytest.skip()` in an `else:` or an `except:` produced no gate at all, so `try: urlopen(...) except OSError: pytest.skip(...)` — the commonest reachability skip, which has no condition anywhere — was invisible; and a decision one module away was unreadable and therefore clean. It reads GUARDS now rather than conditions: a `skipif` condition, the test of every enclosing `if` whichever branch the skip sits in, and the BODY of an enclosing `try` when the skip sits in a handler.

- **One of those three had already been handed to me and I closed it.** A fourth mutation probe came back SURVIVED; its mutation called a helper that exists nowhere, so the walker followed nothing and the gate read clean. That reasoning is right about the probe and the conclusion drawn from it was wrong — the finding was not "the probe measured an absence" but "a call this walker cannot resolve is treated as clean", the same hole whether the name is absent or one file over. The two halves are separable and only one of them was examined.

- **Which reading of "carries a fail-when-set arm" the guard took: the behaviour, not an explicit `pytest.fail` call.** This topic's own measurement is what settles it — the table's `no — skipif only` column was written by reading the gates rather than running them, and run, all three fail. Requiring a literal `pytest.fail` would mean adding a reachability probe to two tests that already fail correctly, a design change the owner's ruling did not authorise.

- **Proven with `infra/scripts/mutate-probe.sh`: twelve probes**, and three discarded as badly built. Ten KILLED when run, and one of the ten — reachability folded into a real opt-in gate — SURVIVES at the tip, because the assertion it proved was deleted with the reachability claim. A probe verdict is true of the commit that ran it and not of the branch. Eight mutate a file under test — a fourth flag name that has never existed in this tree, which is the anti-staleness property measured rather than argued; reachability folded into a real opt-in gate; a flag read moved one call away into a helper three real gates call; that read written as a membership test; the same read through `os.environ.copy()`; that helper re-imported from a module that cannot be read, so three real gates lose their whole decision; a decision reached as an attribute of a module that will not read; and a membership read inside the same helper. Two mutate the guard's own resolution rule, one with a control of a different shape from its mutation. A control touching the guard's own `OPT_IN` was run deliberately to settle whether it is a valid control: it is — it goes red, because `OPT_IN` is a literal here and the tree's flag names are literals in the test files. It is the weaker choice because it would fail identically for a guard that found no gate at all, which is a different thing from proving nothing.

- **Three shapes are proven by planted worktrees rather than by probes**, because a sed expression cannot restructure a statement into a branch: a skip in an `else`, one in an `except` handler with no condition anywhere, and one under a `match` case. Planting the first read's three defects gave `7 passed` on the walker that was supposed to catch them; the second read's eleven gave `10 passed`. Both now fail and name every planted gate by line and by guard.

- **The class has an opt-OUT member, which the table lists without distinguishing.** `test_kraken_fixture_mint.py` is named in row 1, so the file was never missing; what the table does not say is that its gate at line 667 has inverted polarity — it skips *when the flag is set*, because it asserts the live doors are shut and setting the flag deliberately opens them. "Every gate keyed on the opt-in carries a fail-when-set arm" is false for it by design, and row 1's `yes — pytest.fail` cell is the place that reads otherwise. It needed no special case in the guard: every assertion there is about what a gate's guards read, not which way they point.

- **The census the guard walks** is whatever `_tree_gates()` returns; take it from a run, never from here. **The breakdown of the gates that read no environment is not given, because three successive versions of it were wrong in the same direction** — "an absent dataset, a uid or a missing binary" for all of them; then 1 binary and 15 others; then 7 and 9, where a reviewer re-derived 8 and 8. Every version was hand-classified from the guards' surface text and every version missed binaries hiding as `bash is None`, the RESULT of a `shutil.which` two lines up. A number wrong three times in one direction is a fact about the method rather than about the tree: run `_tree_gates()` and classify on what each gate REACHES, which is what the guard does and what no hand pass managed.

- **Where the rule lives**: `CLAUDE.md`'s guards-and-proofs entries since `73885594c` (2026-09-12) — one holding the one-name half through `infra/scripts/count-list.sh skip-gate-contract`, one stating that nothing holds the reachability half — beside the guard's module docstring and this file. Between `deaa3e7c7` (2026-09-10) and that commit no surface a session loads carried it.

- **Resolved by spec 00114's matcher**, branch `spec/00114-skip-gate-matcher`: `18bba7770` added the registry `tests/skip_gates.py`, held closed by its own test; `9f210e8ca` rewrote the 35 gates that read a helper, a `shutil.which` result, a bare local or an unrooted operand, so each says what it reads; `c0b00abe5` replaced the reducer's recognition with a matcher, every guard matching one of six forms or refused with the remedy; `641eda4e6` made `unittest`'s decorator and method forms gates the walker finds; and `649f395c8` deleted the reducer's resolution. That closes this topic's one open sub-item: the reachability half is held by CONSTRUCTION rather than asserted, because a skip is now decided only by a form's reading or by a call into a registry that can neither import a module opening a socket nor launch a `git` whose argv leaves this checkout. The census at the close, from `_tree_gates()`: 65 gates under `tests/`, none opaque, 30 of them declaring what they read through the registry, 6 reading the environment and all 6 naming `ZCRYPTO_LIVE_VENUE_TESTS`. Three residuals are parked as topics of their own rather than left in this file: the provenance of a registry call's argument (T0206), gate discovery beyond the fixture's positions (T0207), and the five `CLAUDE.md` clauses this change falsifies (T0208).
