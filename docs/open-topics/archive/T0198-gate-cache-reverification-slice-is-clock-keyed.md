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

Fixed on branch `fix/t0198-gate-cache-slice-counter`. Commits are named by subject rather than by
hash, because the branch's messages were rewritten before push and a hash here would have gone stale:
`test(engine): T0198 — the rotation's bound, against both keys` is the guard, `fix(engine): T0198 —
the re-verification slice is the run counter, not the clock` is the fix, and the carrier and
review-fix commits follow them.

The re-verification slice is the caller's run counter, `due_for_reverification(cycle_ts,
slice_index)`, and `now` has left the signature. `gate-export` gained `--slice`, validated `[0, 24)`
and required with `--cache` (either flag alone is refused); `infra/nas/pull-entrypoint.sh` passes
`--slice "$slice"` — the same `slice=$((cycle % 24))` the five `archive pull` calls in the same loop
body already read, so this is a sixth reader of one variable rather than a second rotation.

**The bound this delivers, exactly.** Every slice is re-verified within 24 runs while the container
runs uninterrupted. A restart keeps the cache (`/tmp` survives one; only a recreate discards it) and
sends the counter back to 0, so a restart k runs into a sweep re-visits the slices it just did and
reaches the rest up to k runs late: the worst per-slice gap across one restart is 24 + k, so 47. At
the measured period that is ~50 h against the alert's 3-day bar, and one restart mid-sweep reaches
that bar once the loop runs slower than ~92 min. Restarting more often than every 24 runs is the case
that loses slices outright, and the reverify-stalled rule is the witness for it.

**Step 1, the measurement, as the baseline this was fixed against — and how to re-derive it.** Read
from the NAS on 2026-09-11 ~20:05Z:

1. `ssh nas 'sudo /usr/local/bin/docker logs -t zcrypto-archive-pull --since 72h'` → 402 lines: 335
   `pull complete` (the five verified channels) and 67 `archive pull complete` (the journal, pulled
   `--no-verify`).
2. `grep 'pull complete' | grep -o 'source=[^ ]*' | sort | uniq -c` → zcrypto-red 67, zcrypto 134,
   z-home 201. The lowest-count source appears once per cycle, so its timestamps are the cycle clock.
3. Consecutive gaps of those 67 timestamps: **62.8 / 64.4 / 65.8 min** (min / median / max), mean
   **64.3**, advancing 4.34 min per cycle against the hour. **MEASURED.**
4. The UTC hour of each timestamp is the slice `now.hour % 24` would have picked; the largest gap
   between consecutive cycles landing in the same hour is **48.3 h** (hours 3 and 18), with all 24
   hours visited. **DERIVED**, and the proxy matters: `gate-export`'s own `now` is taken later in the
   same cycle, after the pulls, and it logs nothing to that container's stdout, so near an hour
   boundary its hour can differ from the pull line's by one. Spec 00102 D3's simulated ~48 h at
   ~65 min agrees, which is corroboration, not the source.

So the exposure was latent rather than active: 64 min is not one of the periods that starve a slice
outright, and 48.3 h sat inside the 3-day bar, which is why nothing ever fired. A change to the pull
interval, or enough extra work per cycle to drift the period into the 72-90 min band, would have
starved a fixed set of slices with every signal green. The guard re-derives that band and names the
starved slices per period — it is a simulation of the removed key, so it holds no present behaviour;
what holds the present behaviour is the pair beside it, the 24-run bound and the signature that
carries no clock.

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

**What the fix costs, and the crossing it opens.** `gate_cache.py` sits inside its own
`replay_fingerprint` closure (81 files), so the first run on a new image replays the whole journal —
the better part of an hour and growing. `zcrypto_gate_cache_invalidated` does **not** mark it: the
code reaches the NAS only through a re-pin, a re-pin recreates the container, `/tmp/gate-cache.json`
goes with it, and `load_cache` returns a non-rejected empty cache for an absent path, so the gauge
reads 0. `infra/ansible/host_vars/nas/vars.yml` already says so for the same reason. The signature of
the cold run is `zcrypto_gate_cache_hits` 0 with `zcrypto_gate_cache_replayed` at the full cycle
count. Expect `zcrypto-gate-exporter-stale` to sit near its bar on that run.

The crossing is the fleet's concern rather than this topic's, and it is stated at the pin, in
`infra/ansible/host_vars/nas/vars.yml`, because that is where the person who trips it will be
reading. The reachable order is a NEW ENTRYPOINT AGAINST AN OLD IMAGE: the entrypoint is a bind
mount that any nas-tagged converge copies from the tree, so an Alloy bump, a render-only converge
followed by any restart, or a pin rollback to a pre-T0198 image all produce it, and the old CLI
exits 2 on `No such option: --slice` every cycle until the image carrying `--slice` is pinned. It
fails loudly — the NAS ERROR rule inside 15 min, `zcrypto-gate-exporter-stale` at 2 h, the hc.io
dead-man stops — and no gate verdict is falsified, but the gate freezes and the rotation stops. The
reverse order, a new image with an old entrypoint, is refused by the CLI for the same reason and
cannot arise from an ordinary converge, since the pin and the entrypoint live in one tree.
