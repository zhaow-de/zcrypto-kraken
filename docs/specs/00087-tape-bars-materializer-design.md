# The live-trades→bars materializer

Closes the autonomous half of [[T0065]]'s REACH round: a fine-cadence bar dataset that reaches the present, built from the captured trade tape rather than from a quarterly dump. The other half — the Q2/Q3 OHLCVT ingest — stays blocked on Kraken publishing (**verified 2026-08-10: the newest 2026 OHLCVT dump on the NAS is Q1**), and is not this spec's subject.

## Context — the gap, and why the tape is the only source that closes it

`data/ohlc-full` is frozen at **2026-03-31** (measured). Below 4h there is no path to the present:

- **REST recedes.** Kraken's public OHLC window is ~720 bars per interval — ~30 d at 1h, ~7.5 d at 15m. The 2026-07-23 reach round proved this by outcome: daily and 4h joined the canonical tail, while **1h came back detached** (gap ≈ 83.7 d) and 15m could not reach at all. A REST bar is retrievable only while the window still reaches it.
- **Dumps are quarterly and late.** Q2 2026 has not published as of 2026-08-10; Q3 arrives ~October. Fine-grain history *inside* a quarter has no other source, which is why the ingest half is real work — but it is external-clock work.
- **The tape accrues.** Captured trades start 2026-07-08 and grow forever. Unlike REST, the tape's reach does not expire.

So the materializer's contribution is precisely the one neither other source can make: **a live tail at fine cadence that never expires.** It does not replace the dumps (they own the deep history) and it does not replace reach (which owns the coarse-grid seam).

## Decisions

### D1 — One accruing dataset at a 15m base, coarser grids derived

`tape-bars`, an **accruing operational** member in the data-model taxonomy (ops-primary + NAS replica), never a frozen research canonical. The base grid is **15 minutes**; 60, 240 and 1440 are *derived on demand*, never separately materialized.

15m divides all three evenly (×4, ×16, ×96), so no boundary is ragged, and `ticks_to_bars` already buckets left-closed against the epoch — which puts 1440 on UTC midnight, matching the canonical OHLCVT convention.

**Derivation is a library function, not a command.** `derive_bars(frames, interval_minutes)` lives in `cli/tick/`; a consumer reads the day files it wants (through `ObservedReader`, which is what records its provenance) and derives the grid it needs. No CLI surface and no materialized coarse dataset until a consumer exists — deliberate YAGNI, and stated so nobody reads its absence as an oversight.

**Derivation is exact, not approximate, and the vwap is why.** `ticks_to_bars` computes a *true tick-weighted* `vwap = Σ(price·volume)/Σ(volume)`. Therefore `Σᵢ(vwapᵢ·volumeᵢ)` over sub-bars equals `Σ(price·volume)` over the whole coarse window identically, and the coarse vwap re-derives as `Σ(vwapᵢ·volᵢ)/Σ(volᵢ)`. `open` = first sub-bar's open, `close` = last sub-bar's close, `high`/`low` = max/min, `volume`/`count` = sums. A naive average of sub-bar vwaps would **not** be exact; the spec names the formula because the wrong one is the tempting one.

Rejected: materializing each grid independently from the tape. It multiplies the work by four, and it makes cross-grid disagreement possible — a class of bug that cannot exist when the coarse grids are a pure function of the base.

### D2 — Daily finals, because the publish grain must match the heal cadence

`<pair>/<YYYY>/<MM>/<DD>.parquet`, 96 rows for a fully-traded day, written by the `cli/archive/mint.py` atomic pattern, which is **fsync the tmp file's data → `os.replace` → fsync the destination directory** (`_replace_durably`; `segment_writer.py` calls these "byte-identical durability semantics"). Omitting the data fsync — as a first draft of this spec's plan did — leaves a renamed file whose contents may not have reached disk, which is a different and weaker guarantee than the one this cites. The `.sha256` sidecar is minted from the tmp bytes and published before the final's rename, so a reader never sees a final without its digest.

The grain is chosen by D3's arithmetic, not by taste: a day cannot be finalized until it is heal-complete, so publishing at any finer grain would either publish un-healed data or defer it anyway. Daily finals keep **final-once-written** literally true — there is no rewrite path in this design.

Rejected: hourly finals (the panel's grain) — 4-row parquets whose metadata dwarfs their data, at ~87.6k files/pair/year, for a freshness the heal cadence can never deliver. Rejected: one growing per-pair file — appending to a live parquet is not atomic, and one bad write endangers the whole series.

**Columns** are `ticks_to_bars`' own: `[ts, open, high, low, close, volume, count, vwap]`. Note this is the same *set* as `ohlc-full`'s but a different *order* (`ohlc-full` is `…close, vwap, volume, count`), so any union selects columns by name — never by position.

### D3 — Heal-completeness is MEASURED, not inferred from the clock

A day may be published only when its tape is heal-complete. The first draft of this spec gated that on wall-clock alone — `now - day_end >= 26 h`, derived from the healer's nominal cadence. **Cold review killed it, and the reasoning is worth keeping**: a time gate is a *proxy* for "the backfill has run", and the healer has designed modes that break the proxy by an order of magnitude — the fail-closed NAS gate skips a whole cycle, the UTC-day stamp is written *before* the run so one failure costs the entire day's attempt, and a leftover container after a dockerd crash "extends the outage by up to 24 h" (the runner's own comment). Under any of them the clock says settled while the tape is not, and this design has **no rewrite path** — so a proxy failure is silent, permanent, and indistinguishable from a quiet market.

**The direct check exists and costs nothing.** `cli/trades/gaps.py::detect(frame) -> Detection` finds missing and duplicated `trade_id`s, and its docstring states the property that makes it decisive: *"Kraken's `trade_id` is DENSE and per-pair monotone (spec `00053` D1, verified empirically), so a hole in the sequence IS missing data — provable with no REST call."* That is exactly heal-completeness, measured from the bytes rather than assumed from the hour.

So the gate is:

1. **`TAPE_SETTLE = 26 h` past day end remains, demoted to a cheap pre-filter** — it stops the sweep from re-reading a day the healer has demonstrably not reached yet, nothing more. It is no longer load-bearing, so its drift is no longer dangerous.
2. **`detect` must come back clean** — zero `gaps`, zero `duplicate_ids` — or the day is refused into `days_unhealed` and retried on a later sweep. A day is published because its tape was *measured* contiguous, never because a clock said so.

**The extension reaches the nearest PRESENT segment on each side — not "one hour".** `detect` bounds its span by the first and last observed id and treats neither endpoint as a gap (capture-start and the live edge are not holes). Run over exactly one day, that blinds it to a gap at either boundary. A first draft extended by exactly one adjacent hour, which is wrong for the same reason D4 below is wrong: **the adjacent hour is often legitimately absent**, and when it is, the extension silently degrades back to endpoint blindness and a truncated day publishes short, permanently. The check therefore extends to the **nearest present segment strictly before the day and strictly after it**, so the day's own edges are always interior.

Two edges where a neighbour genuinely does not exist, each ruled explicitly rather than left to chance:

- **No earlier segment anywhere** — the day is the archive's genesis. `detect`'s endpoint rule is *correct* there (capture-start is not a hole), so the day is accepted, and the residual is recorded in the bounded claims rather than hidden.
- **No later segment anywhere** — the day sits at the live edge with nothing after it. It is refused as unhealed, not accepted: in practice `TAPE_SETTLE`'s pre-filter means a publishable day always has a successor, so this refusal costs nothing and removes the one case where the check could pass blind. One accepted residual: a pair REMOVED from capture keeps its final day at this edge forever, contributing a steady `days_unhealed` of 1 for that pair on every sweep — documented noise, not a fault, and distinguishable from a real stall because it never ages the last-success signal.

**Naming the right constant matters here.** The healer's settle rule is `_SETTLE = dt.timedelta(hours=2)` in `cli/trades/backfill.py` — a module-local constant it does **not** import from `cli/archive/settle.py`. An earlier draft of this spec cited `cli.archive.settle.SETTLE_HOURS`, which the healer never reads; a maintainer told to watch that constant would have watched the wrong one. The nominal timeline (day D's hour 23 is deferred at the D+1 ≈00:12 run and heals at D+2) explains *why* 26 h is a sensible pre-filter, and is now only that — an explanation, not a guarantee.

### D4 — Reconciled-first reads, watermarked sweep, per-day isolation

Input is `canonical_segments(primary_root, reconciled_root, kind="trades")` — the healed view. **`reconciled_root` is a REQUIRED argument with no default at every layer** — `build_day`, `materialize`, and the CLI — because an optional overlay is one forgotten flag away from publishing the un-healed stream, and the ops runner's argument order differs from the panel's it is modelled on, which is exactly how a flag gets transposed. An empty overlay directory is legal and means "nothing healed yet"; *omitting* it is not expressible. **A bare glob over `capture-segments/` is forbidden**: it returns the un-healed stream and, for pre-2026-07-16 hours, silently double-counts (10,986 duplicate `trade_id`s existed archive-wide before the reconcile pass).

**Hour-file presence proves nothing about completeness, so it is not checked.** The capture writer commits no final for an hour with no events (`segment_writer.py`: `if not parts: return  # ... or the hour was never captured`), and zero-print trades hours are production-measured, not hypothetical — `cli/archive/settle.py` records LINK/EUR trading 8 times in hour 01 and 9 times in hour 04 on 2026-07-14 with **zero** between. An earlier draft of this spec refused any day missing one of its 24 hours; that rule would have made **every day containing a quiet hour permanently unpublishable**, which for a thin pair is most days. It is withdrawn. `build_day` aggregates whatever hours the day has, and completeness is D3's measured `trade_id` contiguity — which is strictly stronger, because it detects a *missing* hour and accepts a *quiet* one, a distinction file-presence cannot make.

`materialize()` sweeps per pair, isolating a failed day into `MaterializeResult.errors` rather than aborting the sweep. **Isolation catches broad `Exception`, matching the panel** (`cli/panel/materialize.py`: "one bad hour must not abort the sweep") — a corrupt parquet or an unexpected error inside `detect` must cost one day, not every pair's whole sweep. `errors` is therefore genuinely exceptional; the ordinary "not ready" outcome is `days_unhealed`.

**The sweep range is stated exactly, because "watermark" alone leaves a hole ambiguous.** The per-pair watermark is the newest **published** day file; a sweep attempts every settled day in `[watermark+1, newest settled]`, plus a **trailing re-scan window** of `RESCAN_DAYS = 3` calendar days back from the newest settled day, attempting only days that have no file yet — the same shape as `reconcile`'s `--window-hours 48` trailing re-scan. So a day that failed because its tape was incomplete is retried while a late overlay mint can still rescue it, and then becomes a **permanent, visible gap** rather than an unbounded retry. On a first run (no watermark) the sweep starts at the archive's earliest day. A published day is never re-attempted and never overwritten — D2's final-once-written.

**Pairs are discovered from the archive**, never hardcoded — the capture set has already changed once (`/BTC` legs added 2026-07-23) and a hardcoded list would silently skip them.

### D5 — No manifest, deliberately

`tape-bars` writes per-file `.sha256` sidecars and **no set-level `manifest.json`** — the panel's shape.

Two reasons, both load-bearing. Spec `00086` made a trial's dataset provenance the **bytes it read**, captured by `ObservedReader`, so a manifest would serve no consumer that exists. And every manifest writer added is another shape in the zoo [[T0132]] tracks — five writers, four `series` shapes, two digest spellings — which is the heterogeneity that killed two designs across nine review rounds. Adding a sixth for no consumer would be paying that cost forward for nothing.

### D6 — Runs on ops, hourly, self-healing

An ops systemd timer at `*-*-* *:52:00` — clear of the `:12/:42` pull, the panel's `:22`, and the `02:25` auto-reboot. The runner exports textfile gauges (exit code, days written/unhealed/gap, errors, last-success timestamp) and two alert rules ride the closeout converge: `days_gap > 0` — the permanent-gap event nothing else will ever report again — and last-success staleness, the stalled-healer case where the watermark freezes while the unhealed path keeps exiting 0 by design. A timer whose failure mode is a green silence must carry its own voice. The cadence is hourly though the grain is daily **on purpose**: a day becomes eligible ~26 h after it ends and is taken within the hour, and an hourly sweep catches up by construction after any outage, with no backlog logic to write.

## Verification

**The tape and the canonical do not overlap** — the tape starts 2026-07-08, `ohlc-full` ends 2026-03-31 — so there is no canonical to check against. That absence is the central verification problem, and it is solved by a source that *does* overlap:

- **The REST control (decisive, and perishable).** Materialize a recent day from the tape; fetch Kraken's public REST OHLC at 15m for the same day; require equality on every bar. This proves the whole chain — reconciled read → `ticks_to_bars` → day file — against an independent witness on live data. Kraken serves 15m for only ~7.5 days back, so **the control expires**: it must run against a day inside that window, and is written data-gated so it skips honestly (never passes vacuously) when the window no longer reaches or the archive is absent.
- **Derived-vs-direct equality.** `derive_bars(15m→N)` must equal `ticks_to_bars(tape, interval_minutes=N)` for N ∈ {60, 240, 1440} on the same tape day. This is the property D1 claims; asserting it is what makes the claim more than arithmetic on paper.
- **Settle behaviour, deterministically.** With an injected `now`, a day inside `TAPE_SETTLE` is deferred, counted into `days_unsettled`, and leaves the watermark untouched; the same day past the boundary is taken. This is the exact shape of T0066's panel test.
- **The heal gate bites, measured not mocked**: a day whose tape carries a `trade_id` hole is refused into `days_unhealed` and publishes nothing, and the same day publishes once the hole is filled. A gap sitting exactly on a day boundary must be caught too — that is what the neighbouring-hour extension is for, and a test asserts it, because without the extension `detect` reports the day clean.
- **A quiet hour must NOT block a day.** A day whose tape is contiguous but whose thinnest hour has no segment file publishes normally — the case the withdrawn 24-hour rule would have refused forever.
- **Refusals bite where they should**: a corrupt segment lands in `errors` and costs exactly one day; an incomplete tape lands in `days_unhealed`. The bare-primary path is unreachable *by signature* — `reconciled_root` has no default — so there is nothing to test rather than a behaviour to assert.
- **Every guard proven by a constructed defect** through `infra/scripts/mutate-probe.sh`, each with a control that fails first — never asserted.

## What this does NOT do — bounded claims

1. **It does not extend `ohlc-full`.** Frozen canonicals are immutable; `rebuild_sets` mints a sibling and never writes into a live set. Whether a future re-freeze unions `tape-bars` is that freeze's decision, and the column-order caveat in D2 applies when it does.
2. **It covers 2026-07-08 onward only** — the tape's own start. Fine-grain history before that has no source but the dumps, and the Q2/Q3 ingest remains [[T0065]]'s other half.
3. **The heal gate proves contiguity, not truth.** `detect` shows the `trade_id` sequence has no hole and no duplicate; it cannot show that Kraken served the right trades in the first place. A run the reconciler booked `trades_unrecoverable` is a permanent hole: the day is refused while it sits inside the candidate window (`days_unhealed`), and once the watermark carries the window past it, it is counted forever after as `days_gap` — settled, unpublished, and outside the window, computed from the calendar and the published set alone so the signal never expires. An unrecoverable loss therefore costs the whole day rather than publishing it short, and an alert on `days_gap > 0` is the one place that says so durably. **The genesis day is the one exception**: it has no earlier segment to extend into, so `detect`'s endpoint rule applies and a loss at the very start of the archive is not visible to this check. That is one day, at a boundary that exists once.
4. **It inherits the tape's losses.** A trade the reconciler booked as `trades_unrecoverable` is absent from the bars too; the bars are exactly as complete as the healed archive and no more. The dataset does not re-litigate archive completeness.
5. **`vwap` is tick-weighted, and coarser grids inherit that** — it is not comparable to a close-price reconstruction proxy such as `cli.backfill.aggregate.aggregate_minutes` produces.
6. **The REST control cannot be re-run for an old day.** Once the 15m window recedes past a day, that day's independent witness is gone permanently — the control proves the pipeline, not every day it ever produced.
7. **No backfill of the dataset itself.** If a day is missed beyond the archive's retention, it stays missing; there is no re-mint path, by D2's design.

## Out of scope

- **The Q2/Q3 OHLCVT ingest** — [[T0065]]'s other half, blocked on Kraken publishing (verified absent 2026-08-10).
- **Consuming `tape-bars` in the universe refresh or a re-freeze** — those are their own rounds with their own gates; this spec ships the producer.
- **Any grid below 15m.** An explicit drop: the tape supports it, but no consumer asks for it, and every grid is a permanent commitment once it is on disk.
- **Manifest normalisation** — [[T0132]]; D5 avoids adding to the zoo rather than fixing it.
