---
status: partial
ripe_when: the re-materialization is ATTENDED and ripe once the stale_seconds image/deploy reaches the panel materializer on the ops node — re-run the affected hours (2026-07-27 07 onward, and the 2026-07-13 event if its panel hours exist) so the already-written frozen rows carry the marker too; writes land on the NAS/ops, never through the soft mount
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

## Done so far

**The marker is BUILT (2026-07-28, `stale_seconds`).** Owner decision: option (a), an explicit column — not row suppression, since the dense 3600-row grid is what every downstream consumer assumes and a sparse grid moves the failure from wrong values to wrong shape.

- **`SCHEMA_VERSION` 1 → 2**, because a column addition IS a generation change under spec `00052` D5: polars raises `SchemaError: extra column in file outside of expected schema` on any multi-hour scan mixing 19- and 20-column hours **even when the query touches only old columns**, so the documented calibration read over `panel-1s/**/*.parquet` would have broken the moment one new hour landed. The bump turns a silently unreadable panel into a loud refusal from `_check_generation`.
- `PANEL_SCHEMA` gains `stale_seconds` (Float64): seconds from the last message **applied to the book** to that boundary. **Null means unknown, never 0.0** — a state sidecar predating the column cannot assert freshness.
- **Threaded across hours**, with the clock persisted beside the book in `<HH>.state.json` (a legacy sidecar loads with a null time rather than crashing the sweep). This is load-bearing: the 2026-07-13 blackout began at **06:59:59.69**, inside the previous hour, and a within-hour counter would have restarted at exactly the moment the number mattered most. The trailing-drain messages advance the clock too — they reach the carried book, so they must reach its clock.
- **Verified against the real incident**, not only fixtures. Replaying 2026-07-27 hour 07 from the canonical archive: blackout 212 rows / 2 distinct `mid` / `stale_max` **203.0 s**, against a quiet-second control of 11 rows / 8 distinct `mid` / `stale_max` **1.4 s**. Filtering `stale_seconds > 30` removes **174** fabricated rows and keeps **3,425**; the remaining row is the **null** at `07:00:00` — hour 06's sidecar predates the column, so second 0 has no applied message and its staleness is genuinely unknown. **174 + 3,425 + 1 = 3,600.** That null is the one consumers must be told about: polars drops nulls from `> 30` *and* `<= 30`, so it is neither removed as fabricated nor kept as honest — it silently vanishes from both sides of the partition. Regenerating the tree (below) removes the null; until then, filter it explicitly.
- Five tests cover the mechanism, the cross-hour thread, the null-not-zero rule, the sidecar round trip (including the legacy shape), and that the column reaches the written parquet — a column nothing writes being [[T0100]]'s defect in another costume.

## Suggested next steps

- **(ATTENDED) Regenerate the tree — and it is now a REFUSAL, not a choice.** `SCHEMA_VERSION` is 2, so the hourly materializer will **abort** against the existing generation-1 tree until it is regenerated (spec `00052` D5's whole-tree rule). Sequencing therefore matters: **the deploy and the regeneration go together in one attended window**, or the hourly timer fails and its dead-man pages in the interim. Regenerating also removes the leading null row described above. The inputs are immutable so the replay is deterministic, but it rewrites bytes a manifest may cover — check before rewriting, and never write through the NFS mount.
- **Decide what to do about the already-materialized hours.** Re-materializing 2026-07-27 hours 07–08 with the fix is cheap and the inputs are immutable, but it changes bytes a manifest may already cover — check before rewriting anything, and never write through the NFS mount.
- **Sweep for other blackouts already in the panel**: the 2026-07-13 event (2,697.235577 s per-pair total) predates the panel's current frontier and may carry the same signature. Measure before assuming it does not.
