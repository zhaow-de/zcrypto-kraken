---
status: open
ripe_when: 'the next prose-cleanup wave over `cli/` is planned — `.local/memo.md` carries a queue item naming one, or the owner names one'
---

# T0176 — a docstring that restates its body has no instrument

## Context — what

`prose.md`'s bar for code prose — a docstring is one sentence of contract, saying only what the code cannot — has no guard. The ratchet measures size, the citation test resolves names, the walker checks vocabulary; a true, short, well-cited docstring that narrates its own function body passes all three, and the review cadence ranks prose Minor by design.

## Why this matters

The owner spotted one at random in a file the T0164 wave never opened, and a fold-in extended it faithfully the same morning. Prose that restates code is a second copy of the logic that drifts on the next edit, and nothing will find the next one either.

## Findings so far

- `cli/xcheck/binance.py` sat outside the T0164 REVISE wave (83 of 167 `cli/` files opened; zero commits touched this one in the window), so its docstrings were never read for content.
- A crude finder — a function docstring sharing at least three backticked identifiers with its own body — flags 158 of 717 function docstrings under `cli/` (measured 2026-09-07 at develop `a0f144a3` with an `ast` walk; the script is in the round-9 ledger's transcript). It over-counts: a contract sentence legitimately names the parameters it constrains. The shape is real.
- Round 9 eliminated the class by hand in the `.py` files it touched (`cli/xcheck/binance.py`, `cli/liquidations/coinalyze.py`, their tests, `tests/test_open_topics_frontmatter.py`, the tripwire and the lesson helper) — the owner's word, 2026-09-07.

## Suggested next steps

- Design the finder as a tripwire kind, `docstring-restates-body`: the docstring's backticked tokens intersected with the body's identifiers, string literals and path templates, minus the function's own parameter names (a contract may name what it constrains); tune the threshold on a labelled sample of fifty docstrings from the 158 so that a contract sentence passes and a narration trips — record precision and recall in the commit body.
- Land it in `infra/scripts/prose-tripwire.py` under the ratchet: today's offenders into the baseline as conscious keeps, growth refused; the kind's own constructed defect (a narrating docstring that must trip) and true positive (a contract sentence that must pass) in `tests/test_prose_tripwire.py`.
- Drain the baseline in the next `cli/` wave, file by file, under `prose.md`'s dispositions.
