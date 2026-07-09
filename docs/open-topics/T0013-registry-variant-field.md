---
status: open
ripe_when: the next registry-schema-touching iteration (or fold into T0009's protocol revision if the schema is reopened there)
---

# Trial-registry schema — first-class family-vs-variant field

## Context — what

iters 052–053 recorded the A2 trials under `family="A1"` with `variant=A2-donchian` in free-text `notes`, because the registry enforces the shared A=40 budget via the **monotone per-key `n_trials_in_family`** counter — a new key would have restarted the counter and silently un-capped the budget. Correct invariant, ugly encoding.

## Why this matters

Family-level budget accounting and variant-level attribution are both needed; free-text notes are not queryable and invite drift the next time a family hosts a variant (every Bucket-B family will).

## Findings so far

Registry at 32 records, `schema_version: 2`, hash-chained append-only — so any change is a **new schema_version for new records only** (no rewrite of existing rows; the chain is inviolable). Records 25–32 carry the variant in notes.

## Suggested next steps

- Design `schema_version: 3` adding an optional `variant: str` field; budget enforcement stays keyed on `family`; loader accepts v2 and v3 rows in one file.
- Document the mapping for the existing notes-encoded records (25–32) in the design — no backfill (append-only).
- TDD per the registry's planted-corruption test conventions.
