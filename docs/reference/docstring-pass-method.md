# The docstring pruning pass

A periodic maintenance pass over a package's docstrings and comments: delete what the code already says, keep what only prose can say. Runs a few times a year, never continuously.

It is a **prose-only** pass: the branch changes no behaviour. That is not an axiom but a claim, proved per batch by the gate below — and on the batch this file is written from it held for 20 of 24 changed files, not all 24. Read the gate section before relying on it.

## The one test

For every sentence: **would it be false or pointless after the next change to what it describes?** Then it is an event in the wrong place. And before that: **can the types, an assertion, or a test hold this claim?** If they can, they do, and the sentence goes.

Prose says only what the code cannot — a decision, an invariant the types do not hold, a refusal's reason.

## What the pass pays on

**This is the page to read first.**

The pass pays on **narration**: sentences restating the code, restating a fact a named test already pins, or reproducing a figure from a report. Repeated argument folded to a single home is narration's most legible form and the single most productive edit on record — six docstrings framing the same two input series collapsed into one module docstring, supplying 68.7% of one batch's whole reduction (`cli/features/derivatives.py`, measured at `e96054eb`). It is an instance, not the mechanism.

**Repetition does not predict yield, and mass may.** Every column but the last is measured at that package's **own** base — the parent of the merge that cut it, which is not one shared revision. `outcome` is a delta and needs both ends: base to that package's own cut merge. It moves if the far end moves, which is why the end is named too — `cli/alpha` reads −48.37% at its cut and −48.32% at `e96054eb`. Raw docstring chars (`clean=False`), 8-gram shingles repeated in ≥3 docstrings:

| package | own base | docs | raw mass | shingles | tripwire rows | outcome |
|---|---|---:|---:|---:|---:|---:|
| `cli/alpha` | `0d1ccb78` | 24 | 14,370 | 0 | 8 | −48.37% |
| `cli/features` | `d17327c2` | 20 | 11,015 | 57 | 14 | −35.73% |
| `cli/data` | `f97e5a67` | 33 | 9,703 | 0 | 15 | −26.38% |
| `cli/tick` | `d17327c2` | 20 | 4,853 | 0 | 0 | −13.72% |
| `cli/ohlc` | `d17327c2` | 23 | 4,334 | 0 | 1 | −11.70% |
| `cli/validation` | `d17327c2` | 21 | 2,231 | 0 | 0 | −0.99% |

One package in six had any repetition, and the deepest cut ever made had none — so **repetition is falsified as a predictor**. Neither tripwire rows nor shingles order the outcomes: the package with the fewest rows of the top three yielded most.

**Base mass, however, ranks the six perfectly** — the ordering by mass and the ordering by yield are the same sequence. At n=6 that is a signal worth measuring before a batch, not a law: it is one batch of one pass, and no mechanism is offered for why a bigger package should give back a larger share. **The open question is whether mass predicts; the settled answer is that repetition does not.**

`cli/tick` and `cli/validation` read identically on rows and shingles — zero and zero — and yielded −13.72% and −0.99%, so those two columns do not separate the batch's second-best case from its worst. On mass the two differ by 2.2×, in the direction their outcomes went.

**Yield and damage are not opposite ends of one axis.** `cli/tick` was zero-signal, the batch's second-best yield, *and* supplied three of the four contracts a correction round had to restore. Best gain and worst damage, same package.

## What the record does support

The damage half, which is the useful half.

**Cutting is destructive where docstrings carry provenance and bounds.** `cli/validation` was cut −13.58% and ended −0.99% from base after three review rounds gave 92.74% of that cut back: three of its four restorations were spec pointers or contracts nothing else held, and one returned byte-identical to base. Its docstrings looked like narration and were the only path from code to a design.

**A package's RISK is judged by READING its docstrings, never by counting them.** Ask what they carry — provenance, a bound, a registered trial, a refusal's reason — not how many rows a tool flags. That judgement is about damage, it is made per package before starting, and it is a different question from yield, which is measured and is open above.

**Flagged prose that has already survived a pass is not backlog.** One package went through twice, across 17 of its 21 files, and still carries 163 tripwire rows and 159,418 raw docstring chars (`clean=False`, at `e96054eb`) — 9.2× that whole four-package batch at the same revision. Its four never-opened files carry zero rows between them. A row count cannot tell a cold reader whether a row is a conscious keep or the load-bearing shape the pass is worst at. **Count rows in files the pass has never opened; check that with `git log --merges` over the pass's own branches, never from memory.**

**Stopping is a valid outcome, but it is reported by its reason, per package, with the mass on both sides.** At one stop, 14 packages had never been opened. Four carried tripwire rows — 10, 7, 4 and 2 — of which two were excluded on risk and two on cost, the latter holding 3,378 raw chars. The remaining ten carried zero rows and zero shingles, and they hold **18,946 raw chars between them at `e96054eb`, 5.6× the pair excluded on cost**; four individually exceed the 2,231 base mass of the package that went on to yield −0.99%.

**No disposition was recorded for those ten, and the detector that grouped them is the one this document says does not order outcomes.** In this record zero rows is consistent with −13.72% and with −0.99% — the fourth-best outcome of six and the worst. So that stop rests on a group nobody examined, and the only mass it quoted was the small side that supported leaving. **State the count and the disposition for every group, and give the mass of the group you are declining as well as the one you inspected. Do not convert mass into an expected yield**, which needs the rate this document says is not established. A stop reported as "nothing is left" is stronger than the evidence, will not survive a reader's own `grep`, and hides the cost of what was deliberately left.

## The gate

A prose-only claim is worth nothing unless it is proved mechanically. Against the batch's base, for every changed file, compare:

1. **The stripped-AST dump** — parse, remove every docstring, fill emptied bodies with `ast.Pass()`, `ast.dump(..., include_attributes=False)` — **together with a per-scope count of non-docstring statements.**
2. **The `tokenize.COMMENT` token stream.** The AST is structurally blind to comments.

The statement count is not decoration. Without it, `docstring + pass` and `docstring alone` reduce to the same tree, so deleting a `pass` reads inert — and that fired four times in merged work, where deleting an exception class's docstring emptied its body and the class became `class XError(Exception): pass`. **The normalisation that makes two trees comparable modelled the exact transformation it was meant to detect.** Ask of every normalisation: what change does this make invisible, and can the pass produce that change? This one could, in its most routine operation.

The obvious repairs are worse. Dropping the fill, or swapping the docstring for a placeholder, both make *adding* a module docstring read as a statement change — a legitimate prose-only edit. **Six arms, and the last three are the ones a naive fix breaks**: `pass` deleted, comparison flipped, statement added must all differ; docstring text changed, docstring deleted **from a body it shares with another statement**, module docstring **added** must all compare equal.

**Prove the instruments bite, with every mutant anchor selected by a parser** — the statement arm from an AST node after the docstring `Expr`, the comparison arm from an `ast.Compare` outside every docstring span, the comment arm from a real `COMMENT` token. A regex anchor flips comparisons *inside docstrings*, the dump correctly does not move, and the arm reports a false BLIND.

A docstring is not a `#` comment, so adding one leaves the COMMENT stream identical — which is why the gate's comment arm cannot see a docstring appear or go.

### The per-file prose-only verdict

`uv run python infra/scripts/prove-inert.py <base-rev> <path>...` answers the neighbouring question: which files of a real change may be called prose-only, and on what grounds. It measures the same shape and the same comment stream, and adds the refusals the arms do not describe — a docstring that is program OUTPUT, a Typer command's `--help` body or a `__doc__` that an argparse script or a test reads. Run with no arguments it prints its exit-code contract, which is where an operator meets it.

**A verdict of INERT is not a claim that nothing observable changed.** `replay_fingerprint` digests whole files across the replay roots' import closure, so a docstring edited in one of them changes the gate's cache key and the next run pays a cold replay — an effect no arm can see. `prove-inert.py` refuses those files rather than certifying them, and needs an importable `cli`: run it through `uv run`. **The closure is not one directory** but the transitive `cli.*` import closure of the replay roots — size a `cli/` batch from `_replay_code_paths()`, never by guessing. `tests/` is outside it, which is why this pass's test-file batches are inert.

**Each verdict costs something different, so read which one fired rather than whether the run was green.** A 1 withdraws the prose-only claim for that file, and with it the licence that made the batch cheap to review. A 3 says a comment's position moved, which costs whichever guard reads that position — `tests/test_config_selectors_are_parsed.py` exempts a check by a `# config-selector-ok:` marker, and `test_the_exemption_window_is_the_comparisons_own` pins where one has to sit. The arm to fear is the silent one: a marker leaving a check it was exempting reddens that check, while a marker arriving above another exempts it with no signal at all. A 4 is not a failed run: it says the claim cannot be made from here, because a docstring that is program output changed, or a path — or the replay closure itself — could not be read.

## What the gate refuses, and what that costs

**The gate is committed, runnable code: `infra/scripts/docstring-gate.py`, which is now its home.** This document says why the arms exist and what the pass may not do because of them; the tool says what they are and drives them. Two people re-derived it from this prose in one week; both lost the same arm.

**A control set is not evidence of coverage.** The two-arm prover this replaced shipped with three controls, all written, run and passing, and none touched the fill: each came from a failure mode already thought of.

**Arm 5's qualifier is a constraint on the pass, not only on the gate.** A docstring that is a body's whole statement cannot be deleted at all — the suite left behind does not parse — and writing `pass` in its place moves the statement count, correctly. So **the pass may not delete a docstring that is a body's only statement and still call the edit prose-only.**

**That refusal is not rare, and a reader hitting it needs to know it is the design.** Over the last 400 non-merge commits on `develop`, every subject beginning `docs(` or `claude(`: 203 commits, of which 69 modified a `.py` at all, giving 202 modified pairs — 171 moved no arm, 18 comments only, **11 the statement count alone**, 2 structure. The eleven are `errors.py` files whose class body IS its docstring. A second census reached 11 and 2 independently; its totals differ because it counted `docs(` alone and did not separate comments-only.

**A mutant anchor is a BYTE offset, never a character one.** `ast` reports `col_offset` in UTF-8 bytes: `x = "— — —"; y = 1` gives `y.col_offset == 19` against a character index of 13. Prose here is em-dash dense, so a character splice over-consumes and builds a mutant that is not the one intended: measured, it either fails to parse or comes back identical, and the arm is lost rather than wrong.

## Review

**Prose-only is what makes review cheap, so it must be true before it is claimed.** Reviewers told a diff cannot change behaviour spend their whole budget on whether each sentence is true; a false premise spends it on the wrong thing.

What actually produced this file's material was not the cadence floor of one whole-branch read. It was **two blind arms per batch plus an independent sampling read on a cadence**. Both are load-bearing and they catch different things: the arms found a false containment claim by driving the function; the sampling read found that a batch had drifted from pruning into fact-checking, which no per-commit review sees because each commit looks correct. A session running one read at the end will not learn it has drifted until the mass delta says −0.4%.

**Brief a reader on what to test, not on what to accept**, and never bar it from where findings are registered — one reader reported a defect as registered nowhere because its brief excluded the file it was registered in, manufacturing a false finding of the class it was hunting. A reader that cannot see a place says **"not visible from here"** and names what it searched.

**A code defect the pass finds is not fixed here and is not deferred to a topic.** Prose-only forbids the first; the no-deferral rule forbids the second. It becomes its own work item on its own branch, handed to whoever owns that code, registered where the coordinator can see it — a commit message is not registration. This pass's headline failure mode was exactly such a defect.

## Standing procedures

**Run the ruling's grep before the ruling closes, not after the batch does.** Parse the region for the shape the ruling names, read every hit, record each disposition with its reason in the commit body. Two hits kept with reasons is a ruling; a count with no dispositions is a sweep.

**Run it before RESTORING, not only before cutting.** A restoration is a claim landing in the tree and takes the same proof as a cut.

**Sweep for the clause you are KEEPING, not only the one you are cutting.** In `cli/validation` at `e96054eb`, three docstrings were cut with `never NaN` preserved verbatim in each, while the same clause stood in six places across that package — every one already asserted by a named test. A rewrite decides what survives as much as what goes, and the surviving clause never gets the sweep.

**Sweep the argument, not just the ruling.** When a fix argues from uniformity or from "the only path to X", run that argument across the package before landing it. An argument justifying more edits than the fix makes is either incomplete or wrong.

**A figure carries its revision, its unit and its denominator in the same sentence as itself** — three axes of one rule, and each has produced a wrong number here. *Revision*: a package measured at a shared revision that post-dated its own cut reported the output of that cut as its input. *Unit*: raw (`clean=False`), cleaned and whitespace-collapsed mass are 159,418, 151,843 and 151,661 for one package. *Denominator*: 95 characters given back is +0.55% of surviving mass or 1.82% of the reduction, and a decision to keep running turns on the second. Each is right about something and wrong where it stands, and a numeral audit sees none of them. Report the per-package delta of every round, correction rounds included, positive included.

**Check the length of the docstrings the batch rewrote, and do not rewrap a line whose length is not the finding.** A rewritten docstring can exceed the wrap target with nothing to catch it, and a reflow with no word changed is still an edit. Run the length sweep as the batch's last step.

## Failure modes: what the prose claims

Each of these happened, and the instance is what makes the rule legible.

**A false containment claim.** A docstring said every failure raises the project's error type. Driven through a stub with a healthy control, six inputs escaped in two classes the handlers could not catch — one a sibling of the caught exception rather than a subclass of it, which is the trap that generalises. *Never state what a function contains without driving it.* And **do not write what escapes**: an enumerated blind spot is a completeness claim by omission. The containment sentence is earned back by the commit that makes it true.

**An enumeration is a completeness claim whichever direction it faces.** Told to state positively what the code *does* guarantee, the pass produced a six-item transcription of the function's own `raise` statements — narration *and* an implied completeness the code lacked, the same defect it had removed one file over. Restating a banned list from the other side is not compliance.

**When a cut changes how many of something there are, delete the count — do not correct it.** A module docstring headed "Two module-wide obligations" became "Three" in the same commit that folded six paragraphs into it: a completed enumeration written into the pass's best work. The reader counts the headed paragraphs.

**A surviving copy is a licence only when its line is quoted.** A contract was deleted because a nearby comment "already said it". It said something else. The failure is invisible from the deleting side — a plausible sibling is exactly what a hurried check finds: same function, same file, right level of detail, different claim. The error then recurred by checking *one* neighbour and not the other. **Name every candidate copy, and quote the line carrying the claim.**

**A cut that removes a refusal, a postcondition or a return shape is a transfer to the next reviewer.** Before deleting a sentence, ask whether the types hold it. If not it is contract — condense it or make it an assertion. The sentence that should go is the one restating the function's own name, almost always directly above the contract; deleting it is how a restored contract is paid for without growing the block.

**Naming a failure mode is not immunity from it.** Every mode above was written down before it was committed. The completed count landed in the flagship commit of the flagship batch, by the author who had named that mode; a scope claim was overstated in the paragraph after naming the mode it belongs to; two writers holding the same correction reproduced it in the next document each wrote. A reader who has just finished this list is at their most confident, and that is when the list stops protecting them. Run the check anyway.

## Failure modes: what the instruments report

An instrument reports independently of the thing it describes, and every one of these looked like a pass.

**A figure can be correct and about the wrong thing, and a numeral audit cannot see it.** A package was proposed as the largest remaining candidate with its row and character counts both exactly right; it had already been through the pass twice, so every number was true and the word *remaining* was false. The correction was then carried into a second document by a second writer who had already read it, and that document reproduced the same contradiction. **Remaining** is a word about a set, and neither writer was tracking the set — both were tracking the numbers attached to it. Auditing numerals establishes *nothing lost* and can never establish *nothing invented*, because the subject of a measurement is not a numeral. State what each figure is a measurement **of**, and verify the subject separately from the value.

**A filter that fails open returns the unfiltered set, and the answer keeps the right shape.** An exclusion meant to drop one already-finished package from a survey of fifteen matched nothing: the result listed fifteen names, right type, about the right length, with the excluded package's hits still in the total. It reports a true count of the wrong set — the mode above wearing a tool's clothes. **Print the excluded set beside the kept set**; an empty exclusion is invisible in the kept set alone, and a set operation belongs where the comparison is explicit rather than in shell pattern matching.

**Serials, versions and short numeric ids collide with data, so a hit count is not a reference count.** A five-digit spec serial grepped across a repo full of floats returned three confident hits that were a quantity, a drawdown and a timestamp; taking the counts would have inverted the ruling.

**A review is a producer, not an authority over a measurement** — two producers measuring the same thing independently are the check on each other, and their disagreement is the finding. When a dispatched review's figure contradicts a measured one, report both and name which is yours: deferring once would have shipped a fix that closed three symptoms and left the real defect untouched.

**Split CALL from ACCESS in any probe of what a function raises.** A probe touching a lazily-evaluated or converted value inside the same `try` as the call attributes the consumer's exception to the callee. Two phases, and report which raised.

**An empty selection exits 0.** A test selection matching nothing, a tool invoked with no arguments — both report success. Assert the selection and print its count before trusting any run. In one shell an unquoted variable holding many paths is a single word, which composes with this into a green that means nothing.

**A guard whose output nothing consumes is decoration.** Chain the destructive step to its check, or read the output before the next call; printing a refusal and continuing is worse than no check, because the transcript looks verified.

## Tooling

Two of the pass's tools are committed, and this document names each by its filename — with `prove-inert.py` in the tree, "the prover" resolves to either. `infra/scripts/docstring-gate.py` compares a file against the batch base on the three arms and drives the mutations that show they bite. `infra/scripts/prove-inert.py` returns the per-file prose-only verdict and the exit code that carries it.

The rest stay disposable, kept beside the pass rather than committed as machinery:

- the batch self-check: docstring mass before/after with its unit named, emitted from one invocation at one revision;
- a repetition detector, useful for *finding* a fold to make and useless for predicting whether a package will yield.

**Write them into an isolated subdirectory with the repo path pinned, never into a shared scratchpad under a generic name.** Two sessions both wrote `mass.py`; the file one of them read was the other's.
