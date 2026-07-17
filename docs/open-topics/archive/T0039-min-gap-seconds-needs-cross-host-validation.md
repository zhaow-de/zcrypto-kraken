---
status: resolved
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
- **Soak-window caveat (2026-07-17, T0058):** between the 2026-07-16 OPS-5 cutover and the T0058 status-file gate landing, the ops reconciler's pull-failure gate keyed on the NAS→ops rsync — which succeeds even when the NAS's **own** VPS capture pulls are broken — so soak-ledger entries in that window were exposed to the two-hop blindness: a frozen mirror could have ledgered false `would_mint` verdicts once an hour crossed the 6 h `LATE_MINT` line. **No false entries were observed**: `residual_gap` stayed 2662 and no new `would_mint` decisions were ledgered in the window — exactly that, nothing more. **This exoneration is currently UNANCHORED** (review 2026-07-17): the ledger lives under gitignored `data/` on the hosts and `residual_gap` in Grafana, and no snapshot, query output, or ledger line-count was committed — nothing in the repo can substantiate or refute it, and a misread (e.g. checked against the NAS's pulled copy rather than the ops writer copy, or a Grafana window missing the cutover hours) would go undetected into the soak analysis. At the next attended host session, anchor it here: the ops-side ledger's line count + last-entry timestamp (or its sha256) **checked against the writer copy**, and the exact Grafana window/query used. The gate now consumes the NAS-written `.pull-status` file through the read-only NFS mount, fail-closed (spec `00054` addendum, [[T0058]]), so the soak's later windows consume the actual NAS pull outcomes, one cycle delayed. **Closed-out anchor (2026-07-17):** the flip-time ledger census is now committed in `dc71d48` — 11 entries total (10 `trade_deficit`, 1 `both_streams_silent`), **zero** `would_mint`, `healable_gap_seconds_total = 0` — and the drill timeline pins `healable`'s first movement (0 → 15,509.5) to the 17:21Z first mint; no `would_mint` entry from the blind window ever surfaced, through the flip and through the drill's fully-observed first mint.

## Done so far — soak-validated (Task 12), then drill-validated (Task 13); resolved 2026-07-17

**Result: the deployed default of 30 s is validated by data. No change.** The measurement's job was to test whether 30 s is right, not to assume it; it is, with 2.5× margin above the measured tail and 2.8× below the smallest real outage on record.

**Method.** `infra/scripts/gap_distribution.py` over a throwaway snapshot of the two RAW mirrors (never the overlay, never the live dirs — rsynced off the ops node's read-only NFS mount into `/var/lib/zcrypto-ops/soak-snapshot`, analysed in the pinned image on the i7, then deleted). Window: `--since 2026-07-14 --probe-seconds 1.0`, i.e. the whole concurrent period from the secondary's first hour (2026-07-14 19:00) to 2026-07-17 12:00 — **66 h, comfortably past the ≥48 h gate**, all 10 pairs present on both mirrors.

**The distribution** (primary book-silence windows the secondary witnessed):

| | value |
|---|---|
| windows observed | 217 |
| p50 / p90 / p99 | 3.26 / 6.10 / 6.54 s |
| p99.9 / max | 12.08 / 12.08 s |
| single-host reference | 14.78 s (max natural quiescence) |
| deployed default | **30 s** |

**Every window in this soak is natural — there were no real outages to exclude.** The harness warns that a benign ~80 s reboot window normally tops this list; there is none, and nothing above 12.08 s at all. The reason: the primary **did not reboot during the soak** — `uptime` 6 d 10 h (booted 2026-07-11 04:01 UTC), capture container up since 2026-07-14 04:00 with `RestartCount=0`. The 21:25 UTC slot is the *unattended-upgrades* reboot time, not a nightly reboot: it fires only when a package demands one, and none did. So the whole distribution is quiescence + coalescing asymmetry, and per the harness's rule every window here **must be covered** by the threshold.

**The outlier, classified by hand as the harness requires.** The max (12.08 s) is **1.85× the p99** — a clean outlier, so it was classified individually rather than trusted:

- **AVAX/EUR, 2026-07-17 06:36:45.631 → 06:36:57.707** (12.08 s of primary silence; 97,104 primary rows that hour, so the stream was otherwise busy).
- The secondary recorded **59 AVAX rows inside that window** — the witness that makes it a "gap" to the detector.
- **The decisive test — cross-pair on the same host, same window:** ADA 100, BTC 160, DOGE 319, DOT 311, ETH 181, LINK 121, LTC 242, SOL 47, XRP 315 rows — **9 pairs flowing, only AVAX silent.**
- **Verdict: a coalescing artifact, not a gap.** The primary host was demonstrably healthy; only AVAX's per-connection stream was asymmetric. This is precisely the mechanism this topic was opened to measure, and it is now observed rather than hypothesised: **at a 10 s threshold the reconciler would have spliced the secondary's AVAX block into an hour the primary never lost** — an unaudited data swap into an archive that cannot be backfilled.

**Why 30 s and not the harness's suggested 25 s.** The harness suggests `ceil(2 × cross-host max)` = 25 s, which is decision-support, not a verdict. 30 s is kept because it satisfies the conservative rule against **both** measurements: 2.03× the single-host max (14.78 s) and 2.48× the cross-host max (12.08 s), where 25 s is only 1.69× the single-host figure. The cost asymmetry decides the tie — a missed 20 s gap is a *recorded residual*, a phantom splice is an *unaudited data swap* — so the threshold errs high. 30 s also stays 2.8× below the smallest real outage on record (83 s kernel reboot; the other is a 270 s WS-503 crash), so it costs no detection power. Not changing a deployed default is also the zero-risk direction.

**What this soak did NOT establish, stated plainly:**

- **The tail is under-resolved.** With 217 windows, `p99.9 == max` is arithmetic, not an estimate — it is simply the largest of 217 observations, and the spec's rule ("above the p99.9 of the thinnest pair") is therefore satisfied only in the weak sense. The max being 1.85× the p99 says the tail is fat; a longer soak could plausibly surface a larger artifact. 30 s has 2.5× headroom over what was seen, so this does not threaten the choice — but it is a reason to re-read the distribution before the `--mint` flip rather than treat this as final.
- **No negative control.** The window contained no real primary outage, so this soak never tested the other leg — that the detector *catches* a real gap at 30 s. Real outages (83 s, 270 s) are far above the threshold and the arithmetic is not in doubt, but the empirical proof belongs to spec 00050's **Task 13 drills**, which is exactly what they are for.
- **The detect-only soak keeps running and costs nothing.** It should keep accumulating; the ledger's `would_mint` entries are the same measurement continuing.

**The `--mint` flip (2026-07-17, `dc71d48`) — Task 12's last checkbox.** A named, defaulted-off knob (`ops_reconcile_mint`, default `false` in the role), enabled durably in `host_vars` with the evidence beside it — never a silent default change. The template renders `--mint` / `--detect-only` explicitly either way, and the `| bool` cast is load-bearing: a CLI override arrives as the **string** `"false"`, which is truthy — without the cast, the override meant to disable minting would enable it (all four bool/string cases render-verified). Zero-backlog verified before applying: the soak ledger held **zero** `would_mint` entries (11 total: 10 `trade_deficit` — a QA signal, never a mint — and 1 `both_streams_silent`) and `healable_gap_seconds_total = 0`, so the first mint ever would be the drill's gap, deliberately created and fully observed.

**Resolution — the negative control delivered by the live drill (spec 00050 Task 13, 2026-07-17).** The leg the soak could not test — that the detector *catches* a real gap at 30 s — is now proven on a real 25-minute primary outage (Leg A: stop 15:01:15Z → restore 15:26:14Z): the 17:12Z ops cycle minted the first splices ever — `spliced=10 union=6 failures=0`, 15,509.5 pair-seconds healed, one secondary block per pair (BTC/EUR provenance: 3 blocks, the single secondary block [15:01:15.230 → 15:27:05.979] = 356,200 rows, and 374,069 + 356,200 = 730,269 overlay rows, row-exact) — while the phantom-splice risk this topic exists to bound stayed at zero: the hour-16 no-op assertion held (`spliced` stayed 10, no hour-16 book mint, residual frozen at 2661.78874), and the spliced hour passed the full CRC verify-replay (2,190/2,190 hours ok, `checksum=True` across both splice boundaries). **30 s is validated on both legs** — no phantom splice across 66 h of healthy cross-host data or the drill's healthy hours, and a real outage detected and healed exactly — so the question this topic was opened to answer is answered, and it closes. (Cross-reference, unchanged: the `both_streams_silent` / `total_loss` detectors are unconditional and threshold-independent.)
