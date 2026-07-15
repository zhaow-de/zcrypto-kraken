---
status: resolved
---

# The NAS mirror accumulates stale part files, so a `*.parquet` glob double-counts every hour

## Context — what

Role A pulls the capture archive with a plain `rsync -a` (`cli/archive/command.py:51`):

```python
argv = ["rsync", "-a", "--chmod=D0775,F0664", "-e", ssh_command, source, str(dest)]
```

There is **no `--delete` and no `--exclude`**. The VPS writes an hour as numbered part files
(`<HH>.part{NNNN}.parquet`), merges them into `<HH>.parquet` at the boundary, and **unlinks the
parts**. The NAS pull copies the parts while the hour is open — and then never removes them, because
rsync without `--delete` only ever adds.

So on the NAS, for a given hour, the finalized `<HH>.parquet` and **all of its already-merged part
files** coexist. Measured 2026-07-14: **2,611 finals and 7,824 stale part files.**

## Why this matters

**Every row in a stale part is also in the final.** Any consumer that reads the archive with the
obvious glob —

```python
pl.scan_parquet(root / "**" / "*.parquet")     # matches 07.parquet AND 07.part0003.parquet
```

— silently reads a large fraction of the archive **twice**. For L2 book deltas that is not a
cosmetic error: the rows carry **absolute quantities** and a duplicated delta stream reconstructs a
different book. A duplicate is as corrupting as a loss here, and it is completely silent.

The first consumer to point at this tree is [[T0014]] (captured-spread cost calibration, the missing
spread term in the Phase-2 cost model, ripe ≈2026-07-22), followed by [[T0024]]'s universe spread-cap
criterion. A silently doubled book would feed straight into the cost model — precisely the class of
"measurement bug producing plausible numbers" the master plan's §9 QA discipline exists to prevent.

`verify_tree` (`cli/archive/pull.py:34`) explicitly **skips** `.part` names, so the archive's own
integrity check is blind to this by design — it will report the tree perfectly clean.

Secondary: unbounded junk growth on the NAS (7,824 files and climbing; parts are ~50 KB each).

## Findings so far

- Root cause read directly: `rsync -a` with no `--delete`/`--exclude` (`cli/archive/command.py:29-51`).
- Confirmed on the live NAS (`/volume1/ZhaoCrypto/capture-segments`): 2,611 finals, 2,611 manifests,
  **7,824 stale `*.part*.parquet`**, spread across essentially every hour pulled since Role A landed.
- Discovered while checking whether the NAS held pre-crash parts that could recover the L2 destroyed
  by [[T0036]]'s restart clobber. **It did not** — rsync had overwritten them with the post-restart
  parts of the same name (NAS hour-07 parts start at `07:04:30.615836`, exactly the truncation point).
  So this accumulation is *not* a usable backup of pre-merge state; it is only junk plus a hazard.
- Related but distinct from [[T0036]] (which is about the *writer*): this is about the *mirror*.

## Done so far

The prune-after-verified fix landed (commit on `fix/engine-host-split`): `verify_tree` now reports which finals verified (`VerifyResult.verified`), and the pull command drains each verified hour's `<HH>.part####.parquet` via `prune_stale_parts` — deleting a part ONLY where its hour has a final that verified against its manifest, strict `<HH>.part<digits>.parquet` only (a non-daemon name like `…-copy.parquet` is left alone), `unlink` hardened against a failed delete, NAS-only by construction. Regression tests cover: a verified hour pruned to just its final; an hour with no final untouched; a corrupt final's parts untouched; an *erroring* (missing-manifest) final's parts untouched; a `.held` spill never matched; a non-standard part-like name left alone.

The reader-side half is already closed by Task 7's `canonical_segments` (`cli/archive/reader.py`), which globs `*/*/<kind>/*/*/*/*.parquet` + a strict `^\d{2}\.parquet` match, so a consumer using it cannot double-count.

**Deploy verified — CLOSED (2026-07-15 23:41 UTC).** The NAS `archive-pull` container was re-pinned to an image carrying the prune (during the 00051/00052 deploys), and the backlog drained: measured live, both mirrors together hold **109** part files — 108 in the in-progress hour and one in the immediately-preceding hour awaiting its next verified pull cycle — down from ~13.5k. Every hour with a verified final is clean.

## Suggested next steps

_(All adopted and delivered — the record below is the design rationale that shaped the fix.)_

- **Do NOT simply add `--delete`.** It would fix the symptom and destroy the mirror's value: the NAS
  is the only backup of an unbackfillable dataset, and `--delete` makes any loss on the VPS propagate
  to the NAS on the next pull. The backup must never be a mirror of a mistake.
- **Preferred: prune-after-verified.** Keep pulling parts (they give ≤1 h of durability for the hour
  still in progress, which matters now that a graceful stop deliberately leaves an hour unpublished —
  see [[T0036]]), then, after `verify_tree` confirms a `<HH>.parquet` verifies against its manifest,
  delete that hour's `<HH>.part*.parquet` **on the NAS only**. Never delete a part for an hour with no
  verified final.
- Add a regression test: an hour with a verified final plus stale parts is pruned to just the final;
  an hour with parts and **no** final (or an unverifiable one) is left completely alone.
- One-off cleanup of the 7,824 existing stale parts, using the same rule (only where a verified final
  exists).
- Consider making the double-count structurally impossible for readers as well — e.g. a documented
  `archive_segments()` helper that globs `[0-9][0-9].parquet` rather than `*.parquet`, so no future
  consumer can trip over this by writing the obvious thing.
