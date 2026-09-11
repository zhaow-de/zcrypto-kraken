---
status: partial
ripe_when: 'the next branch that adds a venue-reaching test, or any change to `tests/test_live_venue_opt_in.py` — either is a moment someone is already holding this context'
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

## Done so far

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

  **A third assertion was written and does not ship.** "No gate's guards reach the venue" was asserted from `a96438b6c` to `bfab0df7e` and removed in `7b920d00c` on the owner's ruling of 2026-09-11, because four review rounds could not make it hold. It is this topic's one open sub-item and `## Suggested next steps` carries it. Nothing in `## Done so far` should be read as delivering it.

- **The first shape of that guard was wrong in three ways and the branch read found all three**, each demonstrated by planting the real defect and watching `pytest -q` report 7 passed: an environment read spelled `getenv(NAME)` or `NAME in os.environ` was counted as reading nothing; a `pytest.skip()` in an `else:` or an `except:` produced no gate at all, so `try: urlopen(...) except OSError: pytest.skip(...)` — the commonest reachability skip, which has no condition anywhere — was invisible; and a decision one module away was unreadable and therefore clean. It reads GUARDS now rather than conditions: a `skipif` condition, the test of every enclosing `if` whichever branch the skip sits in, and the BODY of an enclosing `try` when the skip sits in a handler.

- **One of those three had already been handed to me and I closed it.** A fourth mutation probe came back SURVIVED; its mutation called a helper that exists nowhere, so the walker followed nothing and the gate read clean. That reasoning is right about the probe and the conclusion drawn from it was wrong — the finding was not "the probe measured an absence" but "a call this walker cannot resolve is treated as clean", the same hole whether the name is absent or one file over. The two halves are separable and only one of them was examined.

- **Which reading of "carries a fail-when-set arm" the guard took: the behaviour, not an explicit `pytest.fail` call.** This topic's own measurement is what settles it — the table's `no — skipif only` column was written by reading the gates rather than running them, and run, all three fail. Requiring a literal `pytest.fail` would mean adding a reachability probe to two tests that already fail correctly, a design change the owner's ruling did not authorise.

- **Proven with `infra/scripts/mutate-probe.sh`: twelve probes**, and three discarded as badly built. Ten KILLED when run, and one of the ten — reachability folded into a real opt-in gate — SURVIVES at the tip, because the assertion it proved was deleted with the reachability claim. A probe verdict is true of the commit that ran it and not of the branch. Eight mutate a file under test — a fourth flag name that has never existed in this tree, which is the anti-staleness property measured rather than argued; reachability folded into a real opt-in gate; a flag read moved one call away into a helper three real gates call; that read written as a membership test; the same read through `os.environ.copy()`; that helper re-imported from a module that cannot be read, so three real gates lose their whole decision; a decision reached as an attribute of a module that will not read; and a membership read inside the same helper. Two mutate the guard's own resolution rule, one with a control of a different shape from its mutation. A control touching the guard's own `OPT_IN` was run deliberately to settle whether it is a valid control: it is — it goes red, because `OPT_IN` is a literal here and the tree's flag names are literals in the test files. It is the weaker choice because it would fail identically for a guard that found no gate at all, which is a different thing from proving nothing.

- **Three shapes are proven by planted worktrees rather than by probes**, because a sed expression cannot restructure a statement into a branch: a skip in an `else`, one in an `except` handler with no condition anywhere, and one under a `match` case. Planting the first read's three defects gave `7 passed` on the walker that was supposed to catch them; the second read's eleven gave `10 passed`. Both now fail and name every planted gate by line and by guard.

- **The class has an opt-OUT member, which the table lists without distinguishing.** `test_kraken_fixture_mint.py` is named in row 1, so the file was never missing; what the table does not say is that its gate at line 667 has inverted polarity — it skips *when the flag is set*, because it asserts the live doors are shut and setting the flag deliberately opens them. "Every gate keyed on the opt-in carries a fail-when-set arm" is false for it by design, and row 1's `yes — pytest.fail` cell is the place that reads otherwise. It needed no special case in the guard: every assertion there is about what a gate's guards read, not which way they point.

- **The census the guard walks**: 61 skip gates in `tests/`, of which 6 read the environment and all 6 name `ZCRYPTO_LIVE_VENUE_TESTS`. **The breakdown of the other 55 is not given here, because three successive versions of it were wrong in the same direction** — "an absent dataset, a uid or a missing binary" for all 55; then 1 binary and 15 others; then 7 and 9, where a reviewer re-derived 8 and 8. Every version was hand-classified from the guards' surface text and every version missed binaries hiding as `bash is None`, the RESULT of a `shutil.which` two lines up. A number wrong three times in one direction is a fact about the method rather than about the tree: run `_tree_gates()` and classify on what each gate REACHES, which is what the guard does and what no hand pass managed. So the degeneracy control lives in the tree rather than only in a fixture: a third test requires a non-environment gate to be present, which 55 of the 61 are, so the one-name assertion cannot pass vacuously on an empty set.

- **Where the rule lived at the moment this closed**, measured rather than assumed: in `tests/test_live_venue_opt_in.py`'s module docstring, in this file, and in no surface a session loads — `deaa3e7c7` deleted the corpus paragraph on 2026-09-10 and nothing replaced it. That is a statement about the tree on this date and not a task parked here; the guidance line is `zcrypto-marco`'s, and the PR that carries this resolution records what became of it.

## Suggested next steps

- **The reachability guard: a skip decided by whether the venue ANSWERS.** Not delivered, and the
  owner ruled on 2026-09-11 that it is its own piece of work rather than a fifth round on this branch.
  The property is real and the repo asserts it nowhere: `tests/test_live_venue_opt_in.py` holds the one
  flag name and refuses what it cannot read, and says in its docstring that it does not hold this.

  **Start from the diagnosis rather than from the current code.** A MATCHER matches a guard against
  enumerated forms and fails when none match, so it has no branch that can leak. A REDUCER walks an
  expression asking what it reads, and at every node it cannot classify it must choose between
  refusing and permitting — so closed-world is a property of every branch, not of the design. The
  shipped guard is a reducer; four rounds of widening one, and one round of a reducer claiming a
  matcher's property in its own docstring, left thirteen of twenty-seven planted defects passing.

  **The measured cost, which is why it was not paid here:** 18 of the tree's 61 guard expressions have
  no form a matcher could accept, because their meaning is not readable off their shape — `not
  X.exists()` is manifest whatever `X` is, `not rows` is not. Three are calls to one module-private
  helper; fifteen are bare locals, seven of those a `shutil.which` result read one line later. Each
  needs its predicate inlined or declared. Re-derive that number with the blanking transform over
  `_tree_gates()` before acting on it; four hand counts on this branch were wrong.

  **What it would have caught, so the value is not theoretical:** `tests/test_tape_bars_rest_control.py`
  skipped on a truncated Kraken answer with the opt-in set. It took a census, a guard, four review
  rounds and a ruling to surface; a matcher would have refused that gate on day one and made someone
  say what it reads.

- **What the two surviving assertions miss, measured by planting each shape at the tip.** A second
  opt-in name reaches a gate uncaught through five bindings — an annotated module constant, a binding
  inside a module-level `if` or `try`, a class attribute read as `self.K`, and a name arriving by
  star-import; only a plain module-level `K = ...` is caught, and none of the five is refused either.
  `unittest` is half in scope: `raise unittest.SkipTest` yields a gate, `@unittest.skipIf(...)` and
  `self.skipTest(...)` yield none. Gate DISCOVERY is asserted by nothing and cannot be asserted from
  inside the guard — any set it computes to check the walker is computed by the walker. And six
  mutation probes reverting the guard's most recent recognition additions all SURVIVED: the fixture
  carries the shapes, but no assertion fails when the code stops seeing them.

  These are edges of the property that DID ship, not of the one that did not, and they are listed so
  the next attempt inherits them measured rather than rediscovering them.
