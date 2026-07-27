---
status: open
ripe_when: NOW — the damage is already in the materialized panel (2026-07-27 hour 07, written 14:22 local), the measurement is on disk, and every further blackout adds more. It is also ripe on any decision that would consume `l2-panel` for feature engineering, since the fabricated rows are indistinguishable from quiet ones without this fix
---

# The panel emits a frozen book across a canonical gap, and the hour reads as complete

## Context — what

Split out of [[T0101]] on 2026-07-27. `cli/panel/materialize.py` builds a dense 3600-row/hour 1 s grid from the canonical archive. When the archive has a hole, the grid does not: the book is carried forward and each second is emitted with `updates == 0` — which is **also the normal marker for a genuinely quiet second**. `sample_row` returns `None` only when a side is empty, and a carried book is not empty.

Measured on `BTC/EUR`, 2026-07-27 hour 07, over the 07:01:04 → 07:04:35 blackout:

| | blackout window | `updates == 0` control elsewhere in the same hour |
| --- | --- | --- |
| rows | 212 | 11 |
| **distinct `mid`** | **2** | **8** |
| distinct `spread` / `microprice` / `imbalance_l1` | 2 / 2 / 2 | — |

The hour contains its full **3600 rows** and reads as complete. **203 of the hour's 214 zero-update seconds sit inside the blackout.** Genuinely quiet seconds still show a moving mid; these do not — they are one frozen book at `mid = 57292.25`, held for ~3.5 minutes.

## Why this matters

**This is the only defect in the 2026-07-27 investigation whose damage lands in the research feature set rather than in an operational counter.** Roughly **2,437 pair-seconds of fabricated micro-structure** — a stale book presented as live — are now in `l2-panel`, and nothing distinguishes them from ordinary quiet.

The failure mode is the one this project has been burned by twice: *a plausible number from a broken instrument*. A model or calibration reading these rows sees ~3.5 minutes of a perfectly stable book with zero updates — which looks like a calm market, not like missing data. Spread, microprice and imbalance are all frozen at their pre-blackout values, so any statistic conditioned on them is silently wrong for that window.

It is also **not a one-off**: Kraken sent two `1012 (service restart)` frames in 19.3 days of retention (2026-07-13 and 2026-07-27), so more blackouts are expected and each will fabricate more rows.

Timing note, recorded because it was initially got wrong: a first pass reported the panel had not yet reached 2026-07-27 and the damage was still preventable. **It had.** Hour 07 was materialized at 14:22 local and hour 08 at 15:22. The damage is behind us, not ahead — which changes the fix from "prevent" to "prevent *and* decide what to do about what already landed".

## Findings so far

- `cli/panel/primitives.py`'s `sample_row` returns `None` only when a side is empty; a carried-forward book is non-empty, so a hole produces rows rather than absences.
- `updates == 0` is overloaded: it marks both "no updates this second" and "no data existed this second". Nothing in the schema separates them.
- The canonical archive for that hour has a real hole — 2,437.147792 s across 12 pairs is permanently absent (see [[T0103]]) — so this is not the panel inventing data from nothing; it is the panel failing to represent an absence it was handed.
- `cli/panel/materialize.py` resets the book on **every** snapshot row, and minted files now carry two snapshots ~7 s apart, so the spliced secondary block is discarded before it can contribute. For this consumer the reconciler's already-small real heal is effectively zeroed. This couples the two topics but the defects are independent.
- `/mnt/zhao-crypto/l2-panel/BTC/EUR/panel-1s/2026/07/27/` contains hours 00–08; hour 07 is 251,715 bytes with its full 3600 rows.

## Suggested next steps

- **Decide the representation first, then build it.** Options, in rough order of preference: (a) emit an explicit staleness marker column (e.g. `seconds_since_last_update`) so a consumer can filter; (b) suppress rows across a canonical gap above a threshold, leaving the grid genuinely sparse; (c) both. (a) preserves the dense grid every downstream consumer assumes; (b) is safer for a naive consumer but breaks that assumption. **Do not ship (b) without checking every reader of `l2-panel`.**
- **Add the case to `tests/test_panel_materialize.py`**: a canonical gap longer than the threshold must not produce rows indistinguishable from quiet ones. Assert on the *distinguishing* property — a frozen `mid` across N consecutive rows with `updates == 0` — since that is what a consumer would key on.
- **Decide what to do about the already-materialized hours.** Re-materializing 2026-07-27 hours 07–08 with the fix is cheap and the inputs are immutable, but it changes bytes a manifest may already cover — check before rewriting anything, and never write through the NFS mount.
- **Sweep for other blackouts already in the panel**: the 2026-07-13 event (2,697.235577 s per-pair total) predates the panel's current frontier and may carry the same signature. Measure before assuming it does not.
