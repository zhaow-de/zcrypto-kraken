---
status: open
ripe_when: live now — every restart, reboot, crash and deploy destroys data until this is fixed
---

# A restart silently truncates the hour it lands in (segment-writer part clobber)

## Context — what

`SegmentWriter` (`cli/capture/segment_writer.py`) buffers events and flushes them to numbered part
files `<HH>.part{NNNN}.parquet`, merging them into the final `<HH>.parquet` at the hour boundary. The
part bookkeeping — `_part_paths` and `_part_seq` — is **instance state initialised in `__init__`**
(`_part_paths = []`, `_part_seq = 0`) and the writer **never scans the hour directory**. So when the
capture process restarts mid-hour:

1. The new writer starts numbering at `part0000` again and **overwrites** the pre-restart part files.
2. `_finalize_hour` merges only the paths in its *own* `_part_paths` list, so any pre-restart part it
   did not write is invisible to it and never reaches `<HH>.parquet`.
3. The `<HH>.parquet.sha256` manifest is regenerated over the truncated file — so the loss is
   **hash-invisible**: the archive verifies clean.

A second, related path: a *graceful* stop calls `close()` → `_finalize_hour(current_hour)`, which
finalizes the **partial** hour into `<HH>.parquet` + manifest. The restarted process then writes fresh
parts for that same hour and finalizes again at the true boundary, **overwriting** that file with only
the post-restart rows. Either way the hour is truncated to whatever happened after the restart.

## Why this matters

**Every restart in this system's history has destroyed data, and none of it was visible.** L2 is
unbackfillable — these are permanent holes in the project's only proprietary dataset (master-plan §1's
"own captured L2 books" bucket).

Measured over the live archive on 2026-07-13 (1,250 finalized book segments scanned; a segment counts
as truncated when its first row lands >5 s into its own hour):

| Hour (UTC)  | Pairs | Lost per pair | Cause                              |
| ----------- | ----- | ------------- | ---------------------------------- |
| 07-08 13:00 | 10/10 | 2,852 s       | capture's first hour — *not* loss   |
| 07-08 14:00 | 10/10 | ~127 s        | launch-day restart                 |
| 07-08 19:00 | 10/10 | 3,276 s       | stuck-desync recovery restart      |
| 07-08 20:00 | 10/10 | **1,988 s**   | containerization restart           |
| 07-08 21:00 | 10/10 | **1,889 s**   | containerization restart           |
| 07-11 04:00 | 10/10 | 83 s          | kernel auto-reboot                 |
| 07-13 07:00 | 10/10 | **270 s**     | Kraken WS 503 crash ([[T0035]])    |

**70 truncated pair-hours; ~1,748 pair-minutes of L2 destroyed.**

It also **corrupts the Phase-1 exit-bar measurement**. The bar is "≥7 consecutive days with \<0.1 % gap
time" — a 605 s budget over 7 days. The daemon's `GapMonitor` measures *WebSocket downtime*, so it
scored the 2026-07-13 crash at **~5.5 s**; the hour it clobbered actually lost **270 s** — a ~50×
undercount. Restart damage is invisible to the very instrument that certifies the bar.

And it is a **standing tax on operations**: it makes every deploy, every kernel reboot, and every crash
cost up to a full hour of L2 across all 10 pairs. It blocked the T0008 rollout on 2026-07-13 (a
mid-hour restart would have cost ~600 s and taken the run to ~0.157 %, failing the bar outright).

## Findings so far

- Root cause read directly from the code: `__init__` (`segment_writer.py:72–73`) resets `_part_paths`
  / `_part_seq`; `_flush_buffer` (`:102`) names parts from the in-process counter; `_finalize_hour`
  (`:114`) merges `self._part_paths` only, never globbing the hour directory.
- Confirmed empirically by natural experiment: the 07:04:51 crash-restart left the 07:00 book segment
  starting at **07:04:30**, while 05:00/06:00/08:00 all start at `:00:00.0x`.
- Not caused by [[T0008]] (book depth) or [[T0035]] (the WS-503 crash) — those *trigger* restarts;
  this bug is what makes a restart expensive.
- Closely related to [[T0026]] (a reconnect's trade snapshot overwrites finalized past-hour segments,
  manifest regenerated → hash-invisible). Same "overwrite + re-manifest" pathology; T0026's claim that
  **books are unaffected** is true only for in-process reconnects, not for restarts.
- No stale part files from past hours currently exist on the VPS (only the live hour's), so there is no
  orphaned data to recover — the losses above are already merged away and unrecoverable.

## Deploy migration — MUST run on the VPS before the new binary starts

The fix rests on one invariant: **`<HH>.parquet` on disk is always a committed, complete final.** The
old writer breaks it (its `close()` publishes the open hour), so the on-disk state has to be migrated
**once**, by hand, while the daemon is stopped. Skipping it is not catastrophic — the new writer
refuses to write to an hour that already has a final, and refuses to touch parts sitting beside one —
but the stop hour then loses its remaining rows and stays half-published.

Run on the capture VPS, with `SEG=/var/lib/zcrypto-capture/segments`:

1. **Stop the old daemon gracefully and confirm it finished.** `systemctl stop zcrypto-capture`, then
   `systemctl is-active zcrypto-capture` must print `inactive`, and
   `journalctl -u zcrypto-capture -n 100 | grep -c 'segment written'` must show 20 (one per
   pair×kind). A graceful stop runs the old `close()`, which finalizes the open hour and unlinks its
   parts — that is the state step 2 expects.
2. **Demote each stream's stop-hour final back to a part**, so the new writer resumes the hour instead
   of treating it as closed. For every `<pair>/<kind>` whose newest `<H>.parquet` has **no**
   `<H>.part*.parquet` beside it:
   `mv $D/<H>.parquet $D/<H>.part0000.parquet && rm -f $D/<H>.parquet.sha256`
   Expected result: the hour dir holds `<H>.part0000.parquet` and no `<H>.parquet`.
3. **Resolve any hour that has BOTH a `<H>.parquet` and `<H>.part*.parquet`** — this means the stop was
   *not* graceful (SIGKILL / OOM / power loss), and the state is genuinely ambiguous: the old writer
   sank the final **before** unlinking its parts, so the parts may be rows the final already holds
   (re-merging duplicates the hour) *or* rows flushed after an earlier `close()` (dropping them loses
   the hour). The new writer will log `parts beside a readable final — ambiguous, left untouched` and
   do nothing. Resolve by reading the rows:
   `uv run python -c "import polars as pl,sys; f,ps=sys.argv[1],sys.argv[2:]; a=pl.read_parquet(f); b=pl.concat([pl.read_parquet(p) for p in ps]); print('ALREADY MERGED' if a.height>=b.height and a.tail(b.height).equals(b) else 'DISJOINT')" $D/<H>.parquet $D/<H>.part*.parquet`
   - `ALREADY MERGED` → the parts are inside the final: `rm $D/<H>.part*.parquet`, then go to step 2.
   - `DISJOINT` → the final is a partial hour and the parts are its continuation: rebuild the hour in
     order (final first), `rm` the parts, and rewrite the sidecar with `sha256sum`.
4. **Backfill any missing or empty sidecar** (the new writer no longer blesses finals it did not
   produce): `find $SEG -name '*.parquet' ! -name '*.part*' | while read -r f; do [ -s "$f.sha256" ] || (cd "$(dirname "$f")" && sha256sum "$(basename "$f")" > "$(basename "$f").sha256"); done`
   Expected result — this prints nothing:
   `find $SEG -name '*.parquet' ! -name '*.part*' | while read -r f; do (cd "$(dirname "$f")" && sha256sum -c --quiet "$(basename "$f").sha256"); done`
5. Start the new binary. First-hour check: `journalctl -u zcrypto-capture | grep -E 'dropping late event|ambiguous|merge failed'` must be empty.

## Suggested next steps

- Make the **on-disk state the source of truth**, not process memory:
  - derive the next part sequence by scanning the hour directory for existing `<HH>.part*.parquet`
    (resume at `max(seq) + 1`) instead of always starting at `0000`;
  - have `_finalize_hour` **glob every** `<HH>.part*.parquet` for the hour and merge them in sequence
    order, rather than merging only `self._part_paths`;
  - if a `<HH>.parquet` already exists (a previous `close()` finalized the hour early), merge it in as
    the earliest input rather than overwriting it; write to a temp file and atomically rename, since
    the destination may also be a scan input.
  - **Never sort by `ts` when merging** — intra-timestamp order is load-bearing for book deltas
    (absolute quantities). Concatenate in file order only.
- Add a **startup sweep**: finalize any hour directory that still holds parts for an hour strictly
  before the current one (a crash spanning an hour boundary would otherwise orphan them forever).
- Regression tests for each restart shape: crash mid-hour (parts, no final), graceful stop mid-hour
  (final + parts), restart crossing an hour boundary, and two restarts within one hour. Each must end
  with a complete `<HH>.parquet` whose first row is at `:00:00`.
- Re-derive the exit-bar gap from **segment-timestamp continuity** (per [[T0003]]), not from
  `GapMonitor`, which cannot see restart truncation.
