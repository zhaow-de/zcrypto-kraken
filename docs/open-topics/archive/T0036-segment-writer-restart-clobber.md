---
status: resolved
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


## Done so far

- **The fix is complete on `fix/t0036-segment-writer-restart-clobber`** — five adversarial
  rounds (10 reproduced criticals across them, every one found by execution), ending in the
  committed-final invariant: parts are written atomically (tmp+fsync+rename), `close()` flushes but
  never publishes, finalization commits via `<HH>.parquet.merging` → sidecar → unlink → rename, and
  recovery validates everything it trusts (a torn/bit-rotted `.merging` or final is quarantined,
  never deleted; parts are merged instead). `<HH>.parquet` on disk now always means "committed and
  complete". Hour rotation is corroborated across streams (see [[T0037]]) so no single stamp can
  publish early.
- **Deploy migration validated by execution**: the runbook was itself adversarially tested (10
  defects found and corrected — including a wrong `SEG`, a clobbering `mv`, and a circular sidecar
  check), then the final `migrate_stop_hour.py` dry-ran against a 2.7 GB copy of the real
  production tree: 840,000 pre-stop rows + post-restart rows all present, in order, exactly once;
  demoted=10, refused=0, idempotent second pass.
- Full suite green throughout (1,395 at branch tip); every fix TDD'd with tests that failed first.
- **The exit-bar gap is re-derived from segment-timestamp continuity** (the [[T0003]] requirement this
  topic exposed — `GapMonitor` undercounts restart damage ~50×): `infra/scripts/continuity.py`,
  committed with this iteration. Measured baseline on the real archive since 2026-07-09: worst stream
  0.0890% of the \<0.1% bar (the two truncation events consumed 86% of the budget). The full ≥7-day
  verification run rides the clean-run gate (~2026-07-15).

## Deploy migration — MUST run on the VPS before the new binary starts

The fix rests on one invariant: **`<HH>.parquet` on disk is always a committed, complete final.** The
old writer breaks it (its `close()` publishes the open hour), so the on-disk state has to be migrated
**once**, by hand, while the daemon is stopped.

**Skipping the migration is not catastrophic, but it is not cheap either.** Measured against a replica
built with the actual old writer (10 pairs × {book,trades}, 6 days, 2,797 finals, 12,141,620 events):
skipping it loses **1,361,359 events (9.4 %)** — zero duplicates, zero corruption, every loss loudly
logged, but it is *the entire rest of the stop hour*. Deploy at :05 past and you lose ~55 min × 20
streams: the same magnitude as the bug being fixed. Run the migration.

The runbook below was **verified by executing it** against that replica (idempotent across 3 runs;
14,527,197 rows in / 14,527,197 out / 0 missing / 0 duplicates / stop hour's first ts `08:00:00`).
Note `SEG` — the tree is `<root>/BTC/EUR/book/2026/07/13/08.parquet`; there is **no `segments/`
directory** (`capture_data_dir` in `infra/ansible/group_vars/capture_host/vars.yml`).

````bash
SEG=/var/lib/zcrypto-capture; DAY=2026/07/13; H=08   # H = the UTC hour the daemon was STOPPED in
test -d "$SEG/BTC/EUR/book" || { echo "WRONG SEG"; exit 1; }        # expect: no output

# 1. stop
systemctl stop zcrypto-capture
systemctl is-active zcrypto-capture                                  # expect: inactive
journalctl -u zcrypto-capture -n 200 | grep -c 'segment written'     # expect: 20

# 2. demote ONLY the stop hour. guarded (never clobbers a part), idempotent.
find "$SEG" -mindepth 3 -maxdepth 3 -type d | sort | while read -r s; do
  D="$s/$DAY"; [ -f "$D/$H.parquet" ] || continue
  if ls "$D/$H".part*.parquet >/dev/null 2>&1; then echo "AMBIGUOUS -> step 3: $D/$H"; continue; fi
  mv -n "$D/$H.parquet" "$D/$H.part0000.parquet" && rm -f "$D/$H.parquet.sha256"
done
# expect: one "AMBIGUOUS" line per non-graceful stream, nothing else.

# 3. ONLY for streams step 2 flagged AMBIGUOUS. Verdict first:
uv run python -c "import polars as pl,sys; f,ps=sys.argv[1],sys.argv[2:]; a=pl.read_parquet(f); b=pl.concat([pl.read_parquet(p) for p in ps]); print('ALREADY MERGED' if a.height>=b.height and a.tail(b.height).equals(b) else 'DISJOINT')" $D/$H.parquet $D/$H.part*.parquet
#   ALREADY MERGED -> rm -f $D/$H.part*.parquet && mv -n $D/$H.parquet $D/$H.part0000.parquet && rm -f $D/$H.parquet.sha256
#   DISJOINT       -> merge final+parts into ONE part0000 (NOT a final), checking order first:
uv run python -c "
import polars as pl, sys, pathlib
d=pathlib.Path(sys.argv[1]); h=sys.argv[2]
ins=[d/f'{h}.parquet']+sorted(d.glob(f'{h}.part*.parquet'), key=lambda p:int(p.name.split('.part')[1].split('.')[0]))
df=pl.concat([pl.read_parquet(p) for p in ins])
ts=df['ts'].to_list(); inv=sum(1 for i in range(1,len(ts)) if ts[i]<ts[i-1])
if inv: sys.exit(f'STOP: {inv} ts inversions - mixed-provenance parts, do NOT merge blindly')
tmp=d/f'{h}.part0000.parquet.new'; df.write_parquet(tmp, compression='zstd')
for p in ins: p.unlink()
tmp.rename(d/f'{h}.part0000.parquet')" "$D" "$H"
rm -f $D/$H.parquet.sha256
#   a torn file raises here -> leave it; the new writer quarantines it and rebuilds the hour correctly.

# 4. backfill sidecars — ONLY for finals that actually DECODE
find "$SEG" -name '*.parquet' ! -name '*.part*' | while read -r f; do
  [ -s "$f.sha256" ] && continue
  if uv run python -c "import polars as pl,sys; pl.scan_parquet(sys.argv[1]).select(pl.all().null_count()).collect(engine='streaming')" "$f" 2>/dev/null
  then (cd "$(dirname "$f")" && sha256sum "$(basename "$f")" > "$(basename "$f").sha256")
  else echo "REFUSED (unreadable, leave for the writer to quarantine): $f"; fi
done
# verify — expect: no output, AND a non-zero count
find "$SEG" -name '*.parquet' ! -name '*.part*' | while read -r f; do (cd "$(dirname "$f")" && sha256sum -c --quiet "$(basename "$f").sha256"); done
find "$SEG" -name '*.parquet' ! -name '*.part*' | wc -l              # expect: ~2797, NOT 0

# 5. pre-start gate — expect: no output
find "$SEG" -mindepth 3 -maxdepth 3 -type d | while read -r s; do [ -f "$s/$DAY/$H.parquet" ] && echo "!! $s still has $H.parquet"; done

systemctl start zcrypto-capture

# 6. post-start success gate — a POSITIVE check, not an empty-grep
for s in $(find "$SEG" -mindepth 3 -maxdepth 3 -type d); do
  f="$s/$DAY/$H.parquet"; [ -f "$f" ] && uv run python -c "
import polars as pl,sys; print(pl.read_parquet(sys.argv[1])['ts'][0], sys.argv[1])" "$f"
done   # every line must read <H>:00:00 — that IS the fix
````

### Reading the logs after the start — what is healthy

- **`dropping late event` lines are EXPECTED and HEALTHY.** On every (re)connect `ws_client`
  resubscribes with `snapshot=True` and Kraken **replays** prints it has already sent (T0026). Those
  belong to an hour that is now committed, and the writer correctly refuses to write them beside a
  committed final. On the verified migration run they printed **120 lines while the result was
  measurably perfect** (0 missing, 0 duplicates). They are not a failure signal, and an
  "must be empty" grep over them would roll back a good deploy.
- `ambiguous — left untouched` after the start means a stream step 3 was supposed to resolve was
  missed. No data is at risk (the writer touches nothing), but go back and resolve it.
- `merge failed`, `quarantined unreadable file`, `ignoring a future-dated segment` and
  `could not remove a stale tmp` are the ones to actually read.
- The daemon now takes an **exclusive `flock`** on `$SEG/.capture.lock` at startup: a second writer
  (an overlapping restart, or a human running `zcrypto capture` by hand beside the service) refuses
  to start rather than race. Two writers derive the same part sequence from the same directory and
  destroy each other's rows — do not try to defeat this lock.

- **Deployed and verified in production, 2026-07-14.** PR #122 merged; image
  `sha256:63708539…` rolled to the primary at 04:00:42 UTC with **1 s downtime** (stop → validated
  `migrate_stop_hour.py` demoted 17 stop-hour finals, 0 refused → start). Post-deploy verification
  at the 05:00 boundary: **all 10 book streams' hour-04 finals begin at `04:00:00.0x`** (the
  assertion that is this fix), every pre-stop row preserved (all 7 demoted trades finals show
  pre-stop first rows), manifests verify, 0 error-class log lines, **0 desyncs at T+1h** (T0008,
  baseline ~16/h), and the spliced hour CRC-replays perfectly through the production book
  (**210,856 messages from the first snapshot on, 0 failures**). Segment-continuity measurement:
  truncated-hours count unchanged at 20 (no new truncation), worst stream 0.0856 % — the deploy
  cost ≈ 1 s of gap. The restart-clobber class is closed.
