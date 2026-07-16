# 00053 — REST trade-backfill: a provably complete trade stream (T0050)

Ratified 2026-07-16 in an attended design discussion (decisions logged `[iter-100]`, phase-1 running log). Executes [[T0050]] — the last unshipped clause of the master plan's §8 capture-daemon spec ("systemd, NTP, hourly hashed segments, ≥7-day ring buffer, gap monitoring, **REST trade-backfill**"). The implementation plan is `docs/plans/00053-rest-trade-backfill.md`.

## Goal

Make the canonical **trade** stream provably complete and duplicate-free, and recover the **17,362 trades (3.60 %)** measured missing today — entirely offline, without touching the live unbackfillable capture daemon.

## The measurement that motivates it

Measured 2026-07-16 against the pulled archive (read-only; probe arithmetic self-checked — gap widths must sum to the missing count):

| pair | rows | unique | dups | id_span | missing | gaps | loss% |
| -- | --: | --: | --: | --: | --: | --: | --: |
| ADA/EUR | 24432 | 23449 | 983 | 24736 | 1287 | 21 | 5.20 % |
| AVAX/EUR | 6556 | 6406 | 150 | 7380 | 974 | 29 | **13.20 %** |
| BTC/EUR | 164855 | 162776 | 2079 | 165344 | 2568 | 7 | 1.55 % |
| DOGE/EUR | 10376 | 10079 | 297 | 11170 | 1091 | 29 | 9.77 % |
| DOT/EUR | 9192 | 8842 | 350 | 10164 | 1322 | 30 | **13.01 %** |
| ETH/EUR | 81027 | 79144 | 1883 | 81289 | 2145 | 9 | 2.64 % |
| LINK/EUR | 7378 | 7180 | 198 | 7946 | 766 | 33 | 9.64 % |
| LTC/EUR | 51056 | 49469 | 1587 | 51790 | 2321 | 14 | 4.48 % |
| SOL/EUR | 76516 | 74647 | 1869 | 77296 | 2649 | 9 | 3.43 % |
| XRP/EUR | 45111 | 43521 | 1590 | 45760 | 2239 | 13 | 4.89 % |
| **TOTAL** | | | **10986** | **482875** | **17362** | **194** | **3.60 %** |

The loss is **outage-shaped**, not diffuse: 176 of the 194 gaps carry 91 % of it (widths 6–500), and the two largest (974 + 605 BTC trades) fall in the 2026-07-08 desync window — which [[T0003]] recorded as *"trades unaffected"*. That claim was wrong, and nothing in the stack could see it: `GapMonitor` is in-process, the manifests verify (the rows are *absent*, not corrupt), and the reconciler had no secondary to compare against on 07-08.

The worst-hit names are the **thin alts** (AVAX 13.2 %, DOT 13.0 %, DOGE 9.8 %) — precisely where each print carries the most information, and precisely the pairs whose spread/liquidity terms [[T0014]] and [[T0024]] will calibrate.

## Decisions

- **D1 — The invariant: per pair, across the captured span, the canonical `trade_id` sequence is CONTIGUOUS and UNIQUE** (decision `[iter-100]`). "The captured span" is bounded by the **first and last observed `trade_id` for that pair**: the first is capture-start and the last is the live edge, so **neither endpoint is a gap** — absence outside the span is not loss, and a detector that treats it as loss would chase data that was never ours to have. This rests on a property verified empirically, not assumed: Kraken's `trade_id` is **dense** and per-pair monotone — probed across a liquid pair, a thin pair, the crash window, and 18-month-old data, every page returned exactly N rows spanning N ids with zero non-contiguous steps. Therefore a gap in the sequence **is** missing data, provably, with no REST call. This is the trade stream's answer to a problem books cannot solve: [[T0045]] establishes that book completeness is *unprovable* (the CRC is not re-derivable from the archive), whereas trades get both a proof and a repair path.
- **D2 — Detect from the archive, never from the daemon's counters** (decision `[iter-100]`). The same lesson the Phase-1 exit bar just paid for (`02.phase1-capture-exit-bar-report.md`): `GapMonitor` is in-process, resets on restart, and scored the 07-13 crash at ~5.5 s against an actual 270 s. It also never saw the [[T0026]] overwrite at all. The `trade_id` sequence is self-evident and sees everything.
- **D3 — Placement: the NAS, as a sibling of the reconciler, minting into the existing `capture-reconciled` overlay** (decision `[iter-100]`; options — an ops-node overlay, or folding into OPS-5 — rejected/deferred). Consumers change **nothing**: `canonical_segments(primary, reconciled)` already reads reconciled-first, and the reconciler already unions trades into this exact root. It is one more step in the `archive-pull` entrypoint loop the reconciler already runs — no new container, timer, or channel. The workload is network-bound (fetch) and column-scoped (`trade_id` only), so the Atom is not a constraint; this has Role A's profile, not the reconciler's. Minting on ops instead is **broken today**: while the NAS reconciler owns the overlay and ops pulls it with `rsync -a`, an ops-side minter would be a second writer whose hours never reach the NAS and could be overwritten by the next pull.
- **D4 — OPS-5 relocates the reconciler AND this backfill as ONE unit** (owner directive 2026-07-16). They share the entrypoint, the overlay, and `union_trades`: "the overlay writer" is a single unit, and [[T0033]]'s OPS-5 ("reconciler off the Atom") moves it wholesale, together with the ops→NAS reconciled channel it needs regardless (the `PANEL_*` pattern). This iteration therefore adds **no new NAS glue** beyond one entrypoint line, and OPS-5 stays a purely mechanical move with no new code in flight. T0033's OPS-5 text is updated to say so **at this iteration's closeout**, when the backfill is real.
- **D5 — Source: Kraken public REST `/0/public/Trades`, keyless** (verified live). Paginate on the `last` cursor; 1000 rows/page. **The cursor is returned in NANOSECONDS while `since` accepts seconds** — mixing them silently rewinds or skips a page, so the client carries one explicit unit boundary and a test pinning it. Retention is deep (2025 data served), so there is **no urgency cliff** and no retention-driven pressure on the rollout — unlike the [[T0023]] liquidations poller's 25–33 h window.
- **D6 — Normalization is a mapping, not a copy** (verified against both sides). REST gives `b`/`s`, `m`/`l`, `XXBTZEUR`, epoch float, and stringified numerics; `TRADE_SCHEMA` holds `buy`/`sell`, `market`/`limit`, `BTC/EUR`, `Datetime("us","UTC")`, `Float64`. A REST-sourced row must be **indistinguishable from a WS-captured one** for the same trade, or dedupe-on-`trade_id` would keep an arbitrary one of two spellings and the archive would hold heterogeneous representations of one fact.
- **D7 — Merge: reuse `union_trades`, mint whole hours** (decision `[iter-100]`). `cli/archive/reconcile.py::union_trades` already implements exactly the needed semantics — row-level union, dedupe on `trade_id` keep-first, numeric sort — and documents why that is safe for trades and never for books. It is exposed for reuse rather than copied. An affected hour is minted **whole** (canonical rows ∪ recovered rows), atomically (tmp → fsync → rename), with its `.sha256` and an `<HH>.provenance.json` recording the REST-sourced id ranges.
- **D8 — Scope covers gaps AND duplicates** (decision `[iter-100]`). The 10,986 duplicates are not loss, but they are a live hazard: any consumer summing `qty` over the trades tree double-counts 2.3 % of rows — structurally the same defect as [[T0038]]'s stale-part double-count. The repair is the identical operation (mint the deduped union), so the mint set is *hours with gaps ∪ hours with duplicates*.
- **D9 — The manifest is not the check; the invariant is** (decision `[iter-100]`). This is [[T0026]]'s lesson promoted to a design rule: a minted hour's `.sha256` is **regenerated**, so it hash-verifies while being wrong — which is exactly how the trade overwrite stayed invisible. After every mint the detector re-runs against the overlay and the invariant must hold; a hash match is necessary and nowhere near sufficient.
- **D10 — Never fabricate.** If REST will not serve an id, the gap is **recorded as unrecoverable** in the report, never invented and never silently closed. A residual gap is a finding, not a failure — the same contract the reconciler uses for correlated loss.
- **D11 — Cadence: inside the existing hourly `archive-pull` loop, gated to ONE pass per day; `--detect-only` produces the loss report.** Daily, not hourly, for two reasons: there is no urgency cliff (D5 — Kraken serves ≥18 months), and the detector's scan is O(archive), a per-cycle cost [[T0028]] already flags on this host and which this must not compound. The detect-only run **is** [[T0026]]'s outstanding quantification deliverable, so one command serves both. The first bulk run (194 gaps, ~200–400 REST calls at ~1 req/s) is attended; steady state is a handful of calls per day.
- **D12 — Safety rails** (each one an existing lesson, not a new invention): the **raw mirrors are never written** — minting is overlay-only, the mirrors stay the custody artifact; only hours **older than `H+2h`** are considered, the reconciler's settle rule, so the in-flight hour is structurally untouchable; a per-gap REST failure **logs and the sweep continues** (the `gap_distribution` isolation pattern), exiting non-zero iff any error occurred; and a residual gap is a **finding, not a failure** (D10). Re-running is idempotent: once the invariant holds the detector finds nothing and the pass is a no-op.

## Reuse

`cli/archive/reconcile.py::union_trades` (the merge, tested), `cli/archive/reader.py::canonical_segments(kind="trades")` (reconciled-first enumeration), `cli/capture/segment_writer.py::TRADE_SCHEMA` + `verify_manifest`, the atomic final+manifest pattern (`cli/archive/mint.py`), the injectable-`opener` REST-client shape (`cli/ohlc/fetch.py`), the reconciler's `<HH>.provenance.json` convention, and the NAS `archive-pull` entrypoint/textfile/dead-man scaffolding.

## Why this closes a blind spot nothing else can

The reconciler is explicit that correlated loss is terminal: *"When both streams are dark there is no witness to heal with, so the loss is permanent."* For **trades** that is no longer true — REST is an independent third witness. This is not hypothetical: the largest gap found (974 BTC trades, 2026-07-08) predates the secondary host entirely, so no mirror could ever have healed it. The same machinery answers [[T0043]] (a trades segment lost on *both* mirrors while its book sibling survives is currently invisible — a `trade_id` scan sees it immediately).

## Non-goals

No change to the capture daemon (its [[T0026]] overwrite cause is already fixed by the T0036 committed-final invariant, deployed 2026-07-14 — this is **recovery**, not prevention), no consumer changes, no book-side backfill (impossible — [[T0045]]), no pre-capture tick history (`cli/tick/`'s ZIP dumps own that), and no OPS-5 content (the relocation is sequenced after, per D4).

## Risks / open parameters

- **A minted hour is `f(raw, Kraken)`, not `f(raw)`** — unlike the panel, it is not recomputable from local sources alone. It is *re-fetchable* for as long as Kraken serves the window (≥18 months observed), which makes the NAS copy convenience-durable rather than custody-critical; the raw mirrors remain the custody artifact and are never written.
- **Duplicate-bearing hours with no gaps are touched** solely to collapse duplicates. The mint is the deduped union of rows already present, so no information is lost — but it does widen the blast radius beyond gap-bearing hours, and the invariant re-check is what proves each mint.
- **The 07-08 pre-recovery window is in scope**: it holds the two largest gaps and is real capture data. It sits *before* the Phase-1 exit-bar window (which starts 07-09), so healing it changes no exit-bar verdict.
- **`trade_id` density is load-bearing.** It was verified across four independent probes, but it is Kraken's behaviour, not a contract. The detector must therefore treat a *newly*-observed non-dense pattern as a finding to investigate, never silently absorb it — if density ever fails, the invariant weakens to "unique" and completeness becomes unprovable for trades too.
