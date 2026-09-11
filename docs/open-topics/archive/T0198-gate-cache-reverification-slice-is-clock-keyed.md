---
status: resolved
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
rule fires while its own bar was set against a sweep the loop does not perform. (The runbook page that stated the wrong bound is corrected in the PR that files this topic; the code is not.)

The severity today depends on the loop's real period, which is measurable and is step 1 below. At
~65 min the worst gap is ~48 h, inside the alert bar. The exposure is the period drifting into the
band where slices starve, with nothing watching for it.

Note that `cli/engine/gate_cache.py:34` already carries an assert against the **adjacent** failure —
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

## Resolution

Fixed on branch `fix/t0198-gate-cache-slice-counter` — `f7a148f1f` the guard, `c5c1b388e` the fix,
three carrier commits after it. The re-verification slice is the
caller's run counter, `due_for_reverification(cycle_ts, slice_index)`, and `now` has left the
signature. `gate-export` gained `--slice`, validated `[0, 24)` and required with `--cache` (either
flag alone is refused); `infra/nas/pull-entrypoint.sh` passes `--slice "$slice"` — the same
`slice=$((cycle % 24))` the five `archive pull` calls in the same loop body already read, so this is
a sixth reader of one variable rather than a second rotation.

**Step 1, the measurement, as the baseline this was fixed against.** Read from the NAS on
2026-09-11 over 67 consecutive cycles: the loop's period is **64.3 min mean**, and the worst gap
between two re-verifications of one slice was **48.3 h** — inside the alert's 3-day bar, which is
why nothing had ever fired. 64 min is not one of the periods that starve a slice outright, so the
exposure was latent rather than active: a change to the pull interval, or enough extra work per
cycle to drift the period into the 72-90 min band, would have starved a fixed set of slices with
every signal green. The guard now reproduces that band and names the starved slices per period, so
the defect is held rather than remembered.

**A least-recently-verified key was designed, simulated, and withdrawn before it was proposed.**
The idea was to drop the rotation index entirely and re-verify whichever cached cycle carried the
oldest `verified_at` — appealing because the cache already stores that stamp for the staleness
metric, so it looked like a key with no new state.

It dies on a clock step. `verified_at` is written from the run's `now`; a container that starts with
a wrong clock, or an NTP correction that steps forward, stamps whatever slice it touched with a time
far in the future. That slice is then never the oldest again and is never re-verified — and the one
rule that would notice, `zcrypto-gate-cache-reverify-stalled`, computes an age from the same stamps,
so a future stamp reads as a *young* entry and the alert stays quiet. The starvation is invisible to
its only witness, which is the precise failure this topic exists to close, reintroduced through a
different door.

It dies a second time on a save failure. `save_cache` logs a warning and continues, by design, so a
full disk presents as a working cache — the runbook already names that shape. Under an LRU key the
on-disk stamps then stop advancing, the same entry is "oldest" on every subsequent run, and the
rotation re-verifies that one slice forever while every other entry ages without bound.
`zcrypto_gate_cache_replayed` stays above 0 run after run, which is exactly the shape an operator
reads as a healthy rotation.

The advantage claimed for it was not real either. LRU was argued to give a tighter worst-case age
than a fixed rotation; in the healthy case its bound is also 24 runs, because 24 slices each get
their turn, and in the two unhealthy cases above it has no bound at all. It was more state, one
extra failure mode per piece of that state, and no better bound — so the counter was ruled instead.

**What the fix costs, stated rather than paid here.** `gate_cache.py` sits inside its own
`replay_fingerprint` closure (81 files), so this change invalidates every cache:
`zcrypto_gate_cache_invalidated` goes to 1 on the first run after the deploy and that run replays
the whole journal — the better part of an hour and growing. Expect `zcrypto-gate-exporter-stale` to
sit near its bar on that run. The converge is the fleet's concern, not this topic's, and it has one
ordering constraint worth carrying into it: the NAS image pin and the entrypoint land in the SAME
converge, because a new image with an old entrypoint means `--cache` with no `--slice`, which the
CLI refuses and which fails gate-export outright.
