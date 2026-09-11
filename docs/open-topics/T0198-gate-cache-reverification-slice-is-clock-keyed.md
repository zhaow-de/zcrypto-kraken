---
status: open
ripe_when: "Ripe now, and stays ripe until the key moves: `grep -c 'now.hour % _ROTATION_SLICES' cli/engine/gate_cache.py` is non-zero while `grep -c -- '--slice' infra/nas/pull-entrypoint.sh` is non-zero — the sibling loop is counter-keyed and this one is not."
---

# Gate cache reverification slice is clock keyed

## Context — what

`cli/engine/gate_cache.py`'s `due_for_reverification` decides which cached cycles get their parquet
bytes re-hashed on a given run:

```python
def due_for_reverification(cycle_ts: datetime, now: datetime) -> bool:
    return slice_of(cycle_ts) == now.hour % _ROTATION_SLICES
```

A cycle's slice is a permanent property of the cycle (`sha256(cycle_ts) % 24`), and the run
re-verifies whichever slice matches the hour the run started. `gate-export` runs inside the NAS
pull loop, whose period is `ARCHIVE_PULL_INTERVAL` (3600 s) **plus the work of that cycle**, so the
hour it samples drifts every cycle.

`docs/specs/00102-nas-pull-incremental-verify-design.md:54` (D3) analysed exactly this loop and
ruled the clock key out:

> **Not the clock.** The obvious key, `now.hour % 24` (spec `00062`'s shape), is wrong for THIS
> loop: the period is `3600 + work`, so the hour the verify samples drifts every cycle, and
> whenever the period divides 24 h the loop lands on the same hours forever. Simulated over 400
> days: at a 65-minute period the worst gap between two re-hashes of one slice is ~48 h; at 72, 80
> and 90 minutes a fixed set of 4, 6 and 8 slices is **never visited**. […] a cycle-keyed slice
> gives `24 × period` […] regardless of drift; a clock-keyed one gives no bound at all.

`infra/nas/pull-entrypoint.sh:37-47` acted on that ruling and moved its own slice to a counter,
citing the decision by name. `gate-export` takes no `--slice` — its options are `--textfile`,
`--journal-dir`, `--healthcheck-url`, `--lag-fail-seconds` and `--cache` — so the rotation beside
the counter-keyed one is still clock-keyed. It was left behind.

## Why this matters

The rotation is the only thing that re-reads the journal's bytes at all. The cache's fingerprint
digests the `content_hash` each record **claims**, so without the rotation a corrupted segment is
served as a PASS forever. The gate this feeds is what authorises real-money trading.

`zcrypto-gate-cache-reverify-stalled` pages when the oldest verification age passes three days. Its
bar was set against an assumed daily sweep; under a clock key there is no bound, so at some periods
a fixed set of slices is never sampled and the age for those cycles climbs without limit — the
rule fires, but the page's explanation of why does not include the cause.

The severity today depends on the loop's real period, which is measurable and is step 1 below. At
~65 min the worst gap is ~48 h, inside the alert bar. The exposure is the period drifting into the
band where slices starve, with nothing watching for it.

Note that `cli/engine/gate_cache.py:31` already carries an assert against the **adjacent** failure —
`_ROTATION_SLICES > 24` leaving high slices unreachable — and names D2/D3 while doing it. Someone
reasoned about starvation in this exact spot and about a different mechanism.

## Findings so far

- All four legs verified against the tree on 2026-09-11: the clock key, the spec's ruling, the
  sibling's counter, and the absent `--slice`. `gate_cache.py` is inside its own
  `replay_fingerprint` closure (81 files, measured), so any fix invalidates every cache and buys
  one cold full-journal replay on the NAS.
- Found by the W15 census of `infra/runbooks/gate.md`, which stated the bound as "about daily" and
  "roughly three sweeps of slack". That page is corrected in the same PR that files this topic: it
  now says the bar means some part of the journal has gone three days unread, and its mechanism
  list gains the case an operator would actually hit — a rotation running (`replayed` above 0, run
  after run) while the age climbs anyway.
- The design question is real rather than mechanical. The archive-pull loop's counter lives in its
  shell process and resets on restart, which spec 00102 accepted. The only place a counter could
  persist here is the cache file, which is discarded on a container recreate, so the obvious fix
  reintroduces a weaker form of the same reset.

## Suggested next steps

1. **Measure the loop's real period** from the NAS, which decides how bad this is today. Read
   consecutive `pull complete` timestamps from the archive-pull container's logs over a day and
   take the distribution, not one gap. Under ~65 min the worst-case gap is ~48 h and inside the
   alert bar; in the 72-90 min band a fixed set of slices is never visited.
2. **Decide where the counter lives.** A counter in the cache file resets on a recreate; a counter
   derived from a persisted run ordinal does not, at the cost of another field in the cache schema
   (`CACHE_SCHEMA_VERSION` is 2 today). Weigh against simply keying the slice on a monotonic run
   count stored beside the checkpoint the verify-replay runner already keeps.
3. **Write the guard before the fix.** The property is that over N consecutive runs at a given
   period every slice is visited at least once. That is testable with a simulated clock and no NAS,
   and it is the check the current code has never had — its existing assert covers a different
   failure.
4. **Cost the cold replay into the change.** Editing `gate_cache.py` invalidates every cache
   (`zcrypto_gate_cache_invalidated` goes to 1) and the next run replays the whole journal, which
   `infra/runbooks/gate.md` records as the better part of an hour and growing. Schedule it where
   that is acceptable and expect `zcrypto-gate-exporter-stale` to be close to its bar on that run.
