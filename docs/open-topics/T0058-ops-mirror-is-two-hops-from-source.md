---
status: partial
ripe_when: the NFS migration is converged and verified — then resolve with the measured after-state
---

# The ops mirror is two hops from source, so the reconciler's view is an hour staler

## Context — what

Spec `00054` moved the overlay writer to the ops node. Custody and Role A stayed on the NAS (D3), so the raw mirrors still flow **VPS → NAS → ops**, each hop on its own hourly timer. The reconciler therefore now reasons from a mirror that is, by construction, **one full hourly hop staler** than when it ran on the NAS.

## Why this matters

Measured across the 2026-07-16 cutover:

| | before (reconciler on the NAS) | after (on ops) |
|---|---|---|
| `zcrypto_reconcile_source_lag_seconds` | 4072 s (1.13 h) | 6465 s (1.80 h) |

**Spec `00054`'s D10 predicted this would FALL, and it rose.** That criterion was written on a misunderstanding: it conflated the NAS's *loop-period* problem (the ~103-min cycle, which the move genuinely addresses) with *mirror lag* (which the move necessarily worsens, because it puts the consumer further downstream). The spec's own risk note anticipated exactly this class of error — that the after-picture's attribution was unmeasured.

The consequence was originally recorded here as "not incorrectness — a staler mirror delays healing, it does not produce wrong verdicts (the pull-failure gate still makes absence uninformative and skips)". **FALSIFIED by the 2026-07-17 branch review:** the post-cutover gate keyed on the NAS→ops rsync's exit codes, and that rsync **succeeds even when the NAS's own VPS capture pulls are broken** — so a frozen NAS mirror kept the gate open, and once an hour crossed the 6 h `LATE_MINT_HOURS` line the reconciler would ledger **permanent false `would_mint` verdicts**, polluting the [[T0039]] soak ledger. The original NAS-era gate consumed the actual pull outcomes; the cutover silently reduced it to "the NAS-to-ops rsync succeeded" — two hops from the truth. On top of that correctness hole, the lag **eats alert margin**: `Reconciler · capture mirror lagging` fires at `> 10800 s` (3 h) `for: 10m`; steady-state headroom shrank from ~1.9 h to ~1.2 h, one missed hourly cycle on *either* hop cost proportionally more, and the threshold was sized when the mirror was one hop from source.

## Findings so far

- Not firing: 1.80 h against a 3 h threshold, on both `source="primary"` and `source="secondary"`.
- The lag is structural, not a fault: ops pulls from the NAS at `:12`; the NAS pulls from the VPSes on its own loop (which was itself running ~103 min, i.e. *worse* than hourly — so the real figure moves as the NAS's loop period settles post-cutover).
- Nothing else consumes the ops mirror on a latency budget today; the panel and both replays are all downstream of the same copy and were already living with it.
- **The re-measurement (2026-07-17) settled it:** the NAS loop DID settle at **~67 min** (near its 60-min floor — the loop-period win was real), but `source_lag` kept **rising**: 4072 s → 6465 s → **7928 s**. The residual, growing lag is the mirror hop itself, not compute. Combined with the falsified gate claim above, this ruled out threshold re-derivation and both original options (a direct ops pull = a third puller on the capture hosts; a tighter cadence = more transfer against a growing archive) in favour of removing the second hop entirely.

## Done so far

- **The T0058 consensus, ratified by the owner 2026-07-17** (recorded in full in spec `00054`'s addendum "T0058 pivot — the NFS read path"; decision inputs: the 4072→6465→7928 s lag series, the ~67 min NAS loop, and the review-confirmed gate blindness above):
  1. The NAS exports `/volume1/ZhaoCrypto` **read-only** to the ops node over NFS; ops automounts it at `/mnt/zhao-crypto` (`ro,nfsvers=3,nolock,soft,timeo=100,retrans=3,noatime,nosuid,nodev,noauto,x-systemd.automount,x-systemd.mount-timeout=15` — `timeo` is deciseconds; `ro` makes `soft` categorically safe since the CLI treats an unreadable segment as a loud integrity fact, never as absence).
  2. Ops's hourly 3-tree rsync **retires** — the canonical trees are read through the mount; the write-back direction is unchanged (overlay + panel return via the NAS-initiated, hash-verified rrsync pulls).
  3. The reconcile gate consumes the NAS-written `.pull-status` (per-channel ok + timestamp) **through the mount**, fail-closed: the whole writer cycle (reconcile AND backfill) skips with a loud WARNING unless `capture_ok=1`, `secondary_ok=1`, and the status is younger than 4 h — restoring the actual-pull-outcome gate semantics, one NAS cycle delayed.
  4. The writer cadence doubles (`OnCalendar *:12,42`); alert thresholds stay as provisioned.
- **Implemented on `feat/ops5-offload`** (commits `1ac9ccd` NAS side, `a3e2182` ops side, `d100a6f` replay/panel read paths + watermark hardening), execution-verified against stubs; the D10 criterion corrected in place in spec `00054` (dated notes in D4/D10) and the [[T0039]] soak-window caveat recorded on that topic.

## Suggested next steps

- **Converge + verify the NFS migration** (attended): the NAS export + `.pull-status` live, the ops mount + writer-cycle converge, then verify by outcome — the gate visibly consuming the status file (a forced skip on a stale status), reconcile/panel/replays reading through the mount, overlay still returning to custody sha-identical.
- **In the same attended step, check the export's filesystem and record the answer here**: on the NAS run `mount | grep -w /volume1` (or `df -T /volume1`) and record whether `/volume1` is **btrfs** or **ext4**. Why (review 2026-07-17): the NFS pivot silently dropped the retired local mirror's "sorted prefix per directory" invariant that the readdir-driven consumers lean on — the reconciler's `scan_hours()` availability glob and the panel's watermark sweep now list directories the NAS is concurrently writing, and on an **ext4** export a paged NFS READDIR spanning an htree bucket split can transiently omit an existing older entry while showing newer ones, turning that omission into a permanent `would_mint` ledger verdict or a silently skipped panel hour. On **btrfs** the readdir cookies are stable/monotonic and the prefix property survives, so btrfs = record and done; ext4 = open a follow-up topic for a by-name stat re-probe before any absence-derived verdict (name lookups bypass readdir cookies entirely).
- Run the attended retirement step (`infra/ops/README.md`): remove the `sync_nas_archive` key + `nas_known_hosts` pin on ops, the NAS-side forced-command entry, and the now-unpinged `archive-pull` healthchecks.io check.
- **Measure the after-state and resolve this topic with it**: `source_lag` with the hop removed, the alert margins at the new steady state, and whether `Reconciler · capture mirror lagging`'s 3 h threshold still encodes the intended number of tolerable missed cycles.
