---
status: resolved
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

- **The discriminator is the hour BOUNDARY, not minting — an earlier revision of this file said minting and a counterexample was already on disk.** `materialize_hour` resets the book when the hour's first message is a `snapshot`, so a hole that STRADDLES the boundary makes the resubscribe snapshot that first message: the carried book is discarded, the pre-snapshot seconds drop, and the hour is an honest short grid. A hole strictly INSIDE an hour leaves the first message an ordinary update, the carried book survives, and the grid fabricates across it.

  | hour | hole | first message | rows | longest frozen run |
  | --- | --- | --- | --- | --- |
  | 2026-07-13 07:00 | began 06:59:59.69, straddling | `snapshot` 07:04:30 | 3,329–3,333 by pair | 0 |
  | 2026-07-27 07:00 | began 07:01:04, 64 s in | `update` 07:00:00.026 | 3,600 | 198–207 |

  **ADA/EUR falsifies the minting claim outright**: it was *not* minted at 07-27T07 (11 of 12 pairs were) and carries the LONGEST frozen run, 207 s. Replaying BTC/EUR primary-only against reconciled shows the splice *shortened* the run 210 s → 203 s, because the secondary's resubscribe snapshot landed ~7 s earlier than the primary's. The splice mitigates; it does not cause.
- **No other hour in the panel is affected** — confirmed by sweeping all 4,968 panel files for zero-update runs: 2026-07-27 07:00 is the only hour anywhere with a run ≥60 s, and the next longest is 10 s. That closes this topic's "sweep for other blackouts" step, by a different route than the one first claimed.

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

**The generation guard now checks the tree, not just its manifest.** An absent manifest over a populated tree refuses instead of minting a fresh one, so deleting `panel-meta.json` alone — the obvious reading of the abort's own message — can no longer stamp this generation onto hours written by another. A *matching* manifest is no longer sufficient either: hours for a pair outside the `PANEL_QUOTE` scope are refused, because the sweep will never revisit them and **no re-run can repair that state** — only deleting them can. Both refusals name deleting on the host **and** the NAS, since the pull is `rsync -a` with no `--delete`.

## Resolution

**Regenerated and verified 2026-07-28.** The run started 16:30:57Z inside the unit and completed 22:4x with `Result=success`, exit 0 — about 6 h, against the ~5 h 15 m estimate this file recorded.

Verified by outcome, not by exit code:

- **4,840 parquet files, every one 20-column.** A full sweep of `/*/*/panel-1s/*/*/*/*.parquet` returned `20 columns: 4770 files` at completion (4,840 after the catch-up run) and **zero** at the old width, so no v1 file survived anywhere.
- **`panel-meta.json` reads `schema_version: 2`**, matching the code that must read it.
- **The BTC-quoted subtrees are gone from both copies** — `ETH/` and `SOL/` are EUR-only and a maxdepth-2 search finds no `/BTC` directory on ops or the NAS. Owner's decision, taken in the window.
- **The corrective payload landed.** 2026-07-27 hour 07 — the only hour in the panel with a frozen run over 10 s — now carries `stale_seconds` on every affected row across all 10 in-scope pairs: max 199.00–207.93 s, 189–198 rows over 10 s each. **ADA/EUR's 207.93 s matches the reconciler's independently-measured 208.566668 s `unwitnessed` window**, two separate code paths agreeing on the same outage. Before, those rows carried a frozen book and the hour read as complete.
- **Scope note**: the payload covers **10** pairs, not the 12 this file anticipated — `SOL/BTC` and `ETH/BTC` were deleted rather than regenerated, so their hours are absent rather than marked.
- **The tier came back cleanly**: the panel timer was re-enabled (its `Persistent=true` fired the missed run, which caught up ~7 hours and exited 0, next tick scheduled normally), the NAS re-pull holds the v2 tree and is *behind* ops rather than ahead — which also proves no stale remnants survived — and all 10 healthchecks.io checks read green.

**The ordering trap this hit is now in `fleet-deploys.md`**: the converge re-enables the panel timer, so a pre-converge disable is silently undone — and leaving it armed *across* the converge is its own hazard. Stop it before and again after, and verify the second stop before the next tick is due.
