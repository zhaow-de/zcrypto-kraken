---
status: resolved
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
- **Implemented on `feat/ops5-offload`** (commits `1ac9ccd` NAS side, `a3e2182` ops side, `d100a6f` replay/panel read paths + watermark hardening), execution-verified against stubs; the D10 criterion corrected in place in spec `00054` (dated notes in D4/D10) and the [[T0039]] soak-window caveat recorded on that topic (including the anchoring debt on the "no false entries" exoneration).
- **Converged and verified live, 2026-07-17 — resolved.** DSM exports `/volume1/ZhaoCrypto` **read-only** to ops (rule live, hand-added by the owner, recorded in `infra/external-systems.md`, commit `17a7946`); ops automounts it (`ro,nfsvers=3,nolock,soft,timeo=100,retrans=3,noatime,nosuid,nodev` + systemd automount) — the write-probe is **refused for user AND root**, so the no-write-toward-custody boundary holds on both the server and client halves. The NAS writes `.pull-status` (`capture_ok=1 secondary_ok=1` live) and the ops gate consumes it **through the mount**, fail-closed and octal-safe (base-10-forced arithmetic, `17a7946`). Cadence `:12`/`:42` armed and firing.
- **The old channel is retired**: the 3-tree rsync and `sync_nas_archive` — key pair + `nas_known_hosts` removed on ops, the rrsync `authorized_keys` entry removed on the NAS, and ansible re-verified with a ping AFTER the removal, so the deploy path provably survives the key's death.
- **The measured after-state** (the numbers this topic existed to produce): before the OPS-5 move **4072 s** (1.13 h); post-move rsync two-hop **6465 → 7928 s** (~48 min worst margin against the 3 h alert); post-NFS sawtooth **6136 / 6746 / 7938 s** (1.7–2.2 h). The NAS-hop + finalization is now the **only** term, so 2.2 h is a **hard phase bound**, not a drifting average — alert margin ≥ 0.8 h worst-phase, ~1.2–1.4 h typical. The exporter stamps cycle START. `residual_gap` held **2661.8** throughout — no false verdicts, ever.
- **The residual 1.7–2.2 h is the custody hop, and the owner ruled it unavoidable** ("we have distributed systems, therefore the hops are unavoidable"): it is the NAS's own pull cadence + finalization — the price of keeping custody ingestion independent of ops — so the 3 h threshold's margin is **structural** again rather than eroding, and no threshold re-derivation is needed.
- **NFS cycle cost, feeding [[T0028]]**: 7 m 24 s–9 m 17 s per writer cycle — the `verify_manifest` re-hash of the 48 h window now rides the wire, exactly the per-cycle O(window) hashing cost class T0028 tracks; carry this observation into its eventual incremental-verify design.
- **The one un-run next step is split out, not buried**: the `/volume1` btrfs-vs-ext4 readdir-consistency probe → [[T0062]] (per the closing rule — archived files are never reviewed, so a live deferral cannot stay here).
