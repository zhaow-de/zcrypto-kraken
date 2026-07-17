---
status: open
ripe_when: FIRED — the secondary went live 2026-07-14 and both mirrors land on the NAS; the detect-only soak is running, its analysis due ≈2026-07-16 19:15 UTC (spec 00050 Task 12, feeds the "(2 of 2)" PR)
---

# The reconciler's `--min-gap-seconds` cannot be pinned from single-host data

## Context — what

Spec `00050`'s reconciler detects a primary book gap as a window `(t1, t2)` where the primary stream is silent for `> --min-gap-seconds` **and** the secondary has ≥ 1 update row inside it. The spec sets the default to **5 s** and instructs that it be "pinned from data, not asserted: set it above the measured p99.9 inter-update quiescence of the *thinnest* pair at depth 100".

That instruction was followed (2026-07-14, over 136 h of the real archive, snapshot rows excluded because a resubscribe snapshot is state, not market activity):

| pair | update messages | p99 | p99.9 | p99.99 | **max natural gap** |
| ---- | --------------- | --- | ----- | ------ | ------------------- |
| BTC | 36,519,114 | 0.21 s | 0.44 s | 0.91 s | 7.08 s |
| DOT (thinnest) | 5,316,776 | 1.19 s | **2.48 s** | 4.04 s | 8.30 s |
| AVAX | 7,847,932 | 1.00 s | 2.18 s | 3.68 s | **14.78 s** |

The p99.9 of the thinnest pair is **2.48 s** — so 5 s does clear the stated bar. **But the bar is the wrong one.** The *maximum* natural quiescence is **14.78 s**, three times the proposed default: on a quiet market a healthy primary routinely goes silent for longer than `--min-gap-seconds`.

## Why this matters

At 5 s, the only thing standing between a quiet market and a **phantom splice** is the secondary-activity guard — and that guard rests on an assumption **nobody has tested**: that Kraken's per-connection coalescing can never leave the primary silent for > 5 s while the secondary emits update rows inside the same window.

That assumption is in tension with the spec's own constraint 1: *two healthy hosts record different message streams for the same pair* — coalescing is precisely what makes them differ. If the primary coalesces a burst into messages at `t` and `t+8 s` while the secondary reports intermediate updates at `t+3 s` and `t+6 s`, the reconciler sees an 8 s primary silence with secondary activity inside it, and splices — **healing a gap that never existed**.

Consequences, in order of severity:

- **The archive is not corrupted** (block-splice preserves order, and absolute quantities re-converge at the boundary) — but `healed_gap_seconds_total` inflates, the ledger fills with phantom heals, and the "healed-gap rate high" alert (which exists to flag a degrading primary) fires on nothing.
- Worse, it **corrupts the signal we are meant to trust**: a chronically-gappy primary and a coalescing artifact become indistinguishable in the metric designed to tell them apart.
- And it silently substitutes secondary rows into the canonical view for windows where the primary was fine — exactly the kind of unaudited data swap the provenance ledger exists to prevent, entered through the front door.

This is the same failure shape as the invalidated first draft of spec 00050: **an untested empirical assumption about Kraken's wire behaviour, load-bearing under a design that looks sound on paper.** That draft died because cross-stream row-diffing was never measured before being specified. This is the same class of mistake one layer down.

## Findings so far

- The single-host quiescence measurement above is complete and is the *floor*, not the answer: it bounds how long a healthy stream is quiet, but says nothing about **cross-host asymmetry**, which is the actual trigger condition.
- The decisive measurement — *how often, on healthy hours, is the primary silent > X s while the secondary has update rows in that window?* — **requires two concurrent streams**. None exist: the secondary is provisioned but not capturing, and the three-host data from the 2026-07-13 T0008 investigation was discarded.
- Real primary outages are **83 s** (kernel reboot) and **270 s** (WS-503 crash) — 6–33× above even a 30 s threshold. Raising the threshold therefore costs essentially nothing in detection power.
- **Soak-window caveat (2026-07-17, T0058):** between the 2026-07-16 OPS-5 cutover and the T0058 status-file gate landing, the ops reconciler's pull-failure gate keyed on the NAS→ops rsync — which succeeds even when the NAS's **own** VPS capture pulls are broken — so soak-ledger entries in that window were exposed to the two-hop blindness: a frozen mirror could have ledgered false `would_mint` verdicts once an hour crossed the 6 h `LATE_MINT` line. **No false entries were observed**: `residual_gap` stayed 2662 and no new `would_mint` decisions were ledgered in the window — exactly that, nothing more. **This exoneration is currently UNANCHORED** (review 2026-07-17): the ledger lives under gitignored `data/` on the hosts and `residual_gap` in Grafana, and no snapshot, query output, or ledger line-count was committed — nothing in the repo can substantiate or refute it, and a misread (e.g. checked against the NAS's pulled copy rather than the ops writer copy, or a Grafana window missing the cutover hours) would go undetected into the soak analysis. At the next attended host session, anchor it here: the ops-side ledger's line count + last-entry timestamp (or its sha256) **checked against the writer copy**, and the exact Grafana window/query used. The gate now consumes the NAS-written `.pull-status` file through the read-only NFS mount, fail-closed (spec `00054` addendum, [[T0058]]), so the soak's later windows consume the actual NAS pull outcomes, one cycle delayed.

## Suggested next steps

- **Set the initial default to 30 s**, not 5 s — 2× above the measured 14.78 s maximum natural quiescence, and still far below every real outage on record. Do this in the plan/CLI default; it is the safe direction (a missed 20 s gap is a recorded residual, a phantom splice is an unaudited data swap).
- **Run the reconciler detect-only through the soak**: ledger what it *would* splice, mint nothing. This is the measurement the design needs and cannot get any other way.
- From that soak, **plot the cross-host distribution on healthy hours** — primary-silence duration vs secondary-activity-inside — and pin `--min-gap-seconds` above its tail. Record the derivation the way this topic records the single-host one.
- Only then enable minting. If the distribution shows coalescing-induced asymmetry is real, the secondary-activity guard needs strengthening (e.g. require ≥ N secondary update rows, or require the primary's silence to exceed the secondary's own inter-update spacing in the same window) — design that from the data, not from first principles.
- Cross-reference: the `both_streams_silent` / `total_loss` detectors are **unconditional** and unaffected by this threshold; correlated-loss detection does not depend on getting it right.
