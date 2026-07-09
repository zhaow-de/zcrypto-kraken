---
status: resolved
ripe_when: the next registry-hardening iteration (pairs naturally with any future schema bump)
---

# Trial-registry per-schema-version exact key-set validation

## Context — what

The v3 review (iter-056) found a pre-existing acceptance gap: `validate_caller_fields` / `validate_stored_record` never reject **unknown keys** — a stored record carrying e.g. a misspelled `"variannt": "x"`, rehashed and rechained, loads clean. The new v2-must-not-carry-`variant` check patches exactly one instance of this class; a per-schema-version **exact key-set** check would subsume it and close the class.

## Why this matters

The registry is the append-only audit of record; unknown-key tolerance is a (small) forgery/typo surface. Exploitability is confined to the documented tail-rewrite residual (`docs/specs/00012-registry-hash-chain-design.md` non-goal), so this is hardening, not a live hole.

## Findings so far

- Probe evidence in the iter-056 review: an extra-key record with correct hashes loads clean at any position.
- Related explicit drops (logged, iter-056): whitespace-only `variant` accepted (consistent with all str fields), no length cap (same as `notes`), lone-surrogate str raises `UnicodeEncodeError` pre-write (file untouched) — all pre-existing, uniform across fields, not variant-specific.

## Suggested next steps

- Define `EXPECTED_KEYS = {2: {...}, 3: {...}}` (store-owned + caller fields ± `variant`) and reject any surplus key in `validate_stored_record` with `RegistryCorruptionError` (planted-corruption test: the `"variannt"` forge).
- Keep loader acceptance for both versions; TDD per the registry conventions.
