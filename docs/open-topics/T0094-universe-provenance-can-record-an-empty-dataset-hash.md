---
status: open
ripe_when: NOW — autonomous, independent of every human-gated decision, and a precondition for trusting any universe artifact's provenance. Take it with the next `cli/data/rebuild.py` touch, or before [[T0025]]'s pre-live refresh, whichever comes first
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

## Suggested next steps

- **(Decide, then implement — small)** Which shape is right for "no manifest": (a) **fail closed** with `DataSyncError`, treating a missing manifest as a broken set — consistent with T0093's staleness guard and with the project's fail-closed stance, and the recommended option; (b) **omit the key** entirely, so its absence is unambiguous rather than an empty value that reads as one; (c) keep `""` and document it, which is the status quo and the weakest — it leaves the artifact asserting a hash it does not have.
- **(If (a))** Update the two manifest-less fixtures in `tests/test_data_rebuild.py`, and add a test pinning that a missing manifest raises rather than writing a file.
