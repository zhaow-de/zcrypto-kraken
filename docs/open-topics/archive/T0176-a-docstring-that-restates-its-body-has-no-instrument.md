---
status: resolved
---

# T0176 — a docstring that restates its body has no instrument

## Context — what

`prose.md`'s bar for code prose — a docstring is one sentence of contract, saying only what the code cannot — has no guard. The ratchet measures size, the citation test resolves names, the walker checks vocabulary; a true, short, well-cited docstring that narrates its own function body passes all three, and the review cadence ranks prose Minor by design.

## Why this matters

The owner spotted one at random in a file the T0164 wave never opened, and a fold-in extended it faithfully the same morning. Prose that restates code is a second copy of the logic that drifts on the next edit, and nothing will find the next one either.

## Findings so far

- `cli/xcheck/binance.py` sat outside the T0164 REVISE wave (83 of 167 `cli/` files opened; zero commits touched this one in the window), so its docstrings were never read for content.
- A crude finder flagged 158 of 717 function docstrings under `cli/` (at `a0f144a3`), later 153 of 716 (at `bf6dce0c`). Its rule was NOT the AST reading first written here: it tested each backticked token longer than three characters as a SUBSTRING of the function body's source text, comments and string contents included, so it matched inside longer words and inside prose. The script is `.local/refine-round9/t0176-crude-finder.py` (gitignored, kept for the record). Those two counts are superseded as coordinates by the population below, which is what the labelling ran over.
- Round 9 eliminated the class by hand in the `.py` files it touched (`cli/xcheck/binance.py`, `cli/liquidations/coinalyze.py`, their tests, `tests/test_open_topics_frontmatter.py`, the tripwire and the lesson helper) — the owner's word, 2026-09-07.

- **The population, defined so it regenerates.** A function docstring's backticked tokens intersected with its body's `Name` identifiers, attribute names and the words inside its string literals, minus the function's own parameter names, at three or more shared tokens: **251 of 716** function docstrings under `cli/` at `bf6dce0c`. Two backtick conventions coexist in this tree, and a pattern that reads `` `x` `` without reading ``` ``x`` ``` first pairs the second backtick of a double span with the first of the next, capturing the prose between them — that alone scored one docstring at 87 shared tokens on words like `The` and `and`, against a corrected maximum of 22 across the population.
- **The labelled sample.** Fifty drawn from those 251 by a fixed stride over the population sorted by path and line, so the draw needs no seed, spanning 35 files; labelled by hand against `prose.md`'s bar with a one-clause reason each: **14 NARRATES, 36 CONTRACT**. The sheet and the reasons were kept outside the repo under `.tmp/` — a 55 KB rendering of each docstring beside the first lines of its body, and 1.2 KB of labels — because they are working notes for one measurement, not a record anything later reads.
- **The measurement, three feature families, none separating.** Token-count intersection over every combination of {locals assigned, callees, attribute names, string-literal words, all names} at thresholds two to eight — 217 settings — peaks at **F1 0.49, precision 0.33, recall 0.93**: it flags 39 of the fifty to catch 13 of the 14. Ranked by precision instead, the ceiling is **0.40 at recall 0.29**. An inward-versus-outward citation ratio, on the hypothesis that a contract cites outward and a narration inward, does not discriminate at all — median ratio **1.00 and median outward tokens 0 in BOTH classes**. Order correspondence, on the hypothesis that a narration walks its body, is not computable: only four of the fifty carry three or more ordered citations, and none of those is a NARRATES.
- **Why it fails, from the labels rather than from theory.** The best contract docstrings in this tree cite REJECTED ALTERNATIVES and siblings — why not `read_text().splitlines()` in `cli/archive/command.py`'s ledger reader, why not `CacheEntry(**raw)` in `cli/archive/scan_cache.py`, why `_required`'s `None`-only check is insufficient in `cli/engine/flatten.py` — so they name many identifiers that appear in or beside their bodies and score at the top of the distribution. The feature measures citation density; the defect is structural correspondence between prose and statements. The class is real and can be labelled consistently — `cli/engine/store.py`'s `_reconcile` restates "join on `ts`, enforce the guards, return the triple", `cli/ohlc/qa.py`'s `wick_outliers` restates its own `(high - low) / close` comparison, `cli/capture/ws_client.py`'s `build_subscribe_message` restates the literal dict its body builds — but not by this feature.

## Resolution

**No kind ships, on the measurement.** No cheap instrument in the designed family separates a docstring that restates its body from one that states its contract: at the best setting the guard would be wrong two times in three, and under the ratchet it would record roughly two hundred `cli/` rows as conscious keeps whose adjudication is mostly noise. A guard that costs more attention than the class it finds is worse than the bar it was meant to mechanise.

The class stays under `prose.md`'s existing bar, applied by the whole-branch reader — which is where it was found in the first place, twice, by a human and by a review. The drain wave is consciously DROPPED as a tooling-led campaign: without an instrument there is no baseline to drain, and a file-by-file sweep for this class is the ordinary prose pass, not a project of its own.

What the round did keep is the hand-cut instance: round 9 eliminated the class in every `.py` file it touched, and that work stands.
