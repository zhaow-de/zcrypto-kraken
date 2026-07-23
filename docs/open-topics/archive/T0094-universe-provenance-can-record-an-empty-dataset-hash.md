---
status: resolved
---

# A universe rebuild can emit `ohlc_dataset_hash: ""` instead of failing closed

## Context — what

`cli/data/rebuild.py::_refresh_universe` records the OHLC set's identity like this:

```python
manifest_path = ohlc_root / "manifest.json"
ohlc_dataset_hash = json.loads(manifest_path.read_text())["basket_sha256"] if manifest_path.exists() else ""
```

When the manifest is absent the artifact is still written, carrying `ohlc_dataset_hash: ""`.

## Why this matters

[[T0093]] added `ohlc_dataset_dir` so an artifact names the set it was built from. But a **directory name is not an identity** — `data/ohlc` was a name too, and it was retired, which is precisely T0093's story. What makes a citation resolvable is the **hash**. With an empty hash the artifact names a mutable slot and identifies nothing, which is the T0093 defect in a new costume.

An empty string is also the wrong shape for "unknown": it reads as a value, sorts as a value, and compares equal across two entirely different builds. Two artifacts built from two different broken sets would agree on their provenance hash.

The condition is not benign. `backfill_basket` always writes `manifest.json` (`cli/backfill/backfill.py`), and the live `data/ohlc-full/manifest.json` exists — so a **missing manifest means a broken or half-written set**, which is exactly when failing closed is right and exactly when a silent empty hash is most harmful.

Split out of [[T0093]] rather than parked inside it: T0093's remainder is blocked on a live-tailed volume source and its `ripe_when` points at [[T0025]], whereas this sub-item is autonomous and independent, so leaving it there would have hidden it behind an unrelated blocker and blocked T0093's eventual close.

## Findings so far

- Measured 2026-07-22: the fallback is reachable only via a missing `manifest.json`; the sibling fallback for an empty basket (`last_bars` empty) was removed as unreachable, since `quote_volume_in_eur` raises on a short frame first.
- Two tests in `tests/test_data_rebuild.py` deliberately omit the manifest, so a fail-closed change needs those fixtures updated — that is the whole cost.
- `cli/universe/build.py::render_markdown` renders provenance generically, so no renderer change is implied either way.

## Resolution (2026-07-23)

**Option (a) taken — fail closed.** `_refresh_universe` now raises `DataSyncError` when `ohlc-full/manifest.json` is absent, instead of writing an artifact carrying `ohlc_dataset_hash: ""`. This matches the module's existing stance (`_require_ohlc_full` and T0093's staleness guard both raise `DataSyncError` on an unusable set) rather than inventing a new failure shape.

The reasoning that picked (a) over (b) *omit the key*: an absent key and an absent manifest are both "no identity", so (b) would still publish an artifact built from a set the code has just discovered is broken. `backfill_basket` always writes a manifest, so its absence is not a benign gap — it is evidence of a half-written set, and the right response to that is to refuse, not to annotate.

The guard fires **before** anything is written, and the test pins that too (`assert not (out_root / "point-in-time-universe.json").exists()`) — a half-written artifact is the same failure in a slower costume.

- **Blast radius measured, not estimated**: exactly **two** fixtures omitted the manifest (`test_refresh_universe_actually_applies_the_spread_cap`, `test_refresh_universe_accepts_an_ohlc_set_inside_the_staleness_budget`), matching this topic's own count. Both now seed one. *(A `grep` for "manifest" found only the one test that WRITES it and would have suggested a smaller cost — the failing run is what measured it.)*
- **Mutation-verified**: replacing the guard's condition with `if False:` fails the new test; restored, all tests pass.
- **Review extended the fix one step** (2026-07-23): a manifest that *exists but cannot be read* — invalid JSON, or missing `basket_sha256` — was still raising an untyped `KeyError`/`JSONDecodeError` from deep in the call stack, with no path in the message. It failed closed in effect but not in kind, and inconsistently with every other guard in this module. Both cases now raise `DataSyncError` naming the path, pinned by a parametrised test over both malformed shapes and mutation-verified. `README.md`'s `data` exit-1 enumeration gained the new cause.
- **Considered and declined**: moving the guard earlier, next to `_require_ohlc_full`, so a known-missing manifest short-circuits before two public-API fetches and the parquet reads. Correct but it splits knowledge of `manifest.json` across two places to save latency on a path that should never fire in production; the current placement is correctness-safe because the function's only write comes after it.
