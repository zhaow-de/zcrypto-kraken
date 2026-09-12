---
status: resolved
---

# Trial-registry schema — first-class family-vs-variant field

## Resolution

Resolved in **iter-056** (commit `98ef930`): `SCHEMA_VERSION = 3` adds optional `variant: str | None` (hash-covered; key omitted when None so canonical JSON stays clean); loader accepts v2+v3 in one file with the hash chain intact across the boundary; a v2 record carrying `variant` is corruption; budget accounting stays keyed on `family` only; records 25–32's notes-encoding documented in `record.py`'s docstring (deliberately not backfilled — append-only). 13 planted-corruption-style tests; adversarial review APPROVED (all forges repelled incl. the tail-position v2+variant forge; torn-tail self-heal and concurrent flock verified). Follow-up hardening registered as **T0015**.

**The three steps this topic listed are answered by that change** — PR #75, the iter-056 row of `docs/reference/change-index.md`, no committed spec. The schema-3 design shipped and has since been extended rather than revisited: `cli/registry/record.py` reads `SCHEMA_VERSION = 4` with `_LOADABLE_SCHEMA_VERSIONS = {2, 3, 4}` and `variant` in the v3-and-later stored-key sets, `cli/registry/store.py` omits the key when it is None, and the budget check is still the monotone `n_trials_in_family` there. The mapping for the notes-encoded records is documented, not backfilled, in `TrialRecord`'s own docstring — *"Trials 25-32 (family A1, schema_version 2) predate the field and carry theirs in free-text `notes`"*. The TDD is `tests/test_registry_record.py` and `tests/test_registry_store.py` (23 and 46 tests today). Nothing of the three was left for a successor; the hardening that was is **T0015**, itself resolved (PR #81).

**The steps this topic carried at its close, kept verbatim with what answered each:**

- Design `schema_version: 3` adding an optional `variant: str` field; budget enforcement stays keyed on `family`; loader accepts v2 and v3 rows in one file. — **ANSWERED:** the schema-3 design shipped in iter-056 and has since been extended rather than revisited — `cli/registry/record.py` reads `SCHEMA_VERSION = 4` with `_LOADABLE_SCHEMA_VERSIONS = {2, 3, 4}` and `variant` in the v3-and-later stored-key sets, `cli/registry/store.py` omits the key when it is None, and the budget check is still the monotone `n_trials_in_family` there.
- Document the mapping for the existing notes-encoded records (25–32) in the design — no backfill (append-only). — **ANSWERED:** documented, never backfilled, in `TrialRecord`'s own docstring: *"Trials 25-32 (family A1, schema_version 2) predate the field and carry theirs in free-text `notes` (`variant=A2-donchian`), never backfilled because the registry is append-only, so a reader selecting on `variant` misses them."*
- TDD per the registry's planted-corruption test conventions. — **ANSWERED:** `tests/test_registry_record.py` and `tests/test_registry_store.py` (23 and 46 tests today); the Resolution's "13 planted-corruption-style tests" is the iter-056 figure and both files have grown since.

## Context — what

iters 052–053 recorded the A2 trials under `family="A1"` with `variant=A2-donchian` in free-text `notes`, because the registry enforces the shared A=40 budget via the **monotone per-key `n_trials_in_family`** counter — a new key would have restarted the counter and silently un-capped the budget. Correct invariant, ugly encoding.

## Why this matters

Family-level budget accounting and variant-level attribution are both needed; free-text notes are not queryable and invite drift the next time a family hosts a variant (every Bucket-B family will).

## Findings so far

Registry at 32 records, `schema_version: 2`, hash-chained append-only — so any change is a **new schema_version for new records only** (no rewrite of existing rows; the chain is inviolable). Records 25–32 carry the variant in notes.
