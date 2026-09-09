---
status: open
---

# Several journal readers never validate the record they read

## Context — what

`from_json` (`cli/engine/journal.py`) parses a journal artifact and stops there: its docstring says schema and the boundary invariant *"stay the caller's separate concern"*. The file records the consequence twice in its own comments — `:59` coerces a journaled `nav` at read time *"since several callers read a record without ever calling `validate_record`"*, and `:268` refuses a corrupt `closes` at load because *"several callers never call `validate_record`"*.

So the finiteness and schema guarantees `validate_record` provides are a property of each call site's discipline, not of the read. Which readers have that discipline has never been enumerated.

## Why this matters

A record reaching a consumer by a route that skips `validate_record` carries no guarantee about its `final_targets`, its snapshot metadata, or its optional `nav`/`held`/`closes` beyond the two hand-placed coercions above. What stands between the fleet and that today is the WRITER: `cli/engine/cycle.py:686` validates before journaling, so an artifact this engine wrote is guarded — and an artifact arriving by any other route is not.

`T0188` is one measured consequence: `cli/engine/soak.py:1679` loads every record with a bare `from_json` and `realized_internals` compares their journaled `final_targets` against a rebuilt row, so an unvalidated non-finite value produced a wrong answer in the soak report. Spec `00113` closed that at the comparison — a non-finite `diff` is counted unmeasurable rather than compared, and voids the run — deliberately without widening here, so the read still carries no guarantee and every other consumer of those records is where this topic left it.

## Findings so far

- **The census.** `validate_record` has exactly four production call sites: `cli/engine/concordance.py:78`, `cli/engine/cycle.py:686` (the writer), `cli/engine/feeders.py:84`, and `cli/engine/soak.py:825` — the last on `latest_record` alone, never on the scored records it compares against.
- The readers are not enumerated anywhere, so "several callers" in `journal.py`'s comments is a claim about a set nobody has listed.
- Moving validation into the read would reverse a documented design decision rather than fill a gap, and its blast radius is every consumer of a journal artifact on the live trade path: an artifact that loads today would start raising.

## Suggested next steps

- **Enumerate every reader of a journal artifact** — the call sites of `from_json` and of whatever loaders wrap it — and adjudicate one row per site: does this reader need the guarantee, and does it have it?
- **Then decide the layer**, with the enumeration in hand: validation inside the read (reversing `from_json`'s stated position, and refusing artifacts that load today), or per-caller with the readers that need it named and made to call it. Do not decide it from the two comments alone; they describe a set that has not been listed.
- Whichever way it lands, `journal.py`'s two comments describe the state at the time they were written and are re-read against the enumeration.
