---
status: resolved
---

# Several journal readers never validate the record they read

## Context — what

`from_json` (`cli/engine/journal.py`) parses a journal artifact and stops there: its docstring says schema and the boundary invariant *"stay the caller's separate concern"*. The file recorded the consequence twice in its own comments: `_as_positive_float` coerces a journaled `nav` at read time, and the `closes` branch refuses a list or a scalar at load, both of them justified at the time by callers that read a record without calling `validate_record`.

So the finiteness and schema guarantees `validate_record` provides are a property of each call site's discipline, not of the read. Which readers had that discipline was not enumerated anywhere when this topic was opened.

## Why this matters

A record reaching a consumer by a route that skipped `validate_record` carried no guarantee about its `final_targets`, its snapshot metadata, or its optional `nav`/`held`/`closes` beyond the two hand-placed coercions above. All that stood between the fleet and that was the WRITER: `cli/engine/cycle.py` validates before journaling, so an artifact this engine wrote was guarded — and an artifact arriving by any other route was not.

`T0188` is one measured consequence: `soak_report` loaded every record with a bare `from_json` and `realized_internals` compares their journaled `final_targets` against a rebuilt row, so an unvalidated non-finite value produced a wrong answer in the soak report. Spec `00113` closed that at the comparison — a non-finite `diff` is counted unmeasurable rather than compared, and voids the run — deliberately without widening the read, which is the gap this topic then closed per-caller.

## Findings so far

- **The census at the time.** `validate_record` had four production call sites: `cli/engine/concordance.py`, `cli/engine/cycle.py` (the writer, before journaling), `cli/engine/feeders.py`, and `cli/engine/soak.py` — the last on `latest_record` alone, never on the scored records it compares against.
- **The enumeration, by an `ast` walk of `cli/` rather than by grep: seven production readers call `from_json`.** Four were unguarded — `command.py`'s `_window_records`, `cycle.py`'s `_previous_success`, `executor.py`'s `_cycle_records_through`, `soak.py`'s `soak_report`, two of them on the live trade path. Two replay each record through `concordance.replay_cycle`, which validates. One reads `completed_at` alone, for a startup gauge.
- Moving validation into the read would reverse a documented design decision rather than fill a gap, and its blast radius is every consumer of a journal artifact on the live trade path: an artifact that loads today would start raising. That is what settled the layer.

## Resolution

The layer is **per-caller** (the owner's ruling, 2026-09-12): the readers that need the record's guarantee ask for it, and `from_json` keeps its contract, so every artifact that loads today still loads.

- **The four unguarded readers validate** (`e1f823ae6`). What each does with a refusal differs, and that is the part worth reading: `_previous_success` RAISES, because its caller reads `None` as "first cycle, the shadow book starts flat", so degrading a refusal to `None` would turn every delta into a full buy off a record just refused; `_window_records` aborts, every number in a tracking report aggregating the whole window; `_cycle_records_through` and `soak_report` propagate, their contracts already carrying an unreadable record. Spec `00113`'s arm at the soak comparison stays the last line rather than the only one.
- **The enumeration is a test, not a table in this file** (`a025438d6`): `tests/test_engine_journal_readers.py` finds every `from_json` site with its enclosing function and holds one row per site — `validates`, `replays`, or the reason it needs neither. A new reader fails until it is adjudicated, a deleted one fails until its row goes, each row is checked against the site's own code so the table cannot drift into a promise, and the two `replays` rows rest on `replay_cycle`'s own `validate_record`, which the last case holds. Three mutations through `infra/scripts/mutate-probe.sh` were killed; a fourth, which neutered the test's own assertion, survived and is recorded in that commit as the shape to avoid.
- **`journal.py`'s two comments were re-read against the enumeration** (`d94250415`), the third next step: the plural was wrong once the set existed, so each comment keeps only the reason a reader would act on.
