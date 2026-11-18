# A venue halt the two mirrors prove lost nothing is booked as a halt, never as permanent L2 loss

Branch `fix/00163-reconciler-venue-halt-not-loss`, cut from `develop` at `6795cd513` on 2026-11-17. The owner ruled at 2026-11-17T19:47:55.448Z, verbatim: "for the reconciler change, fix it right aways in a branch without deferring it to a new T-topic" (D1). This spec designs the reconciler's fix; its plan is `docs/plans/00163-venue-halt-not-loss.md`, reviewed by `zcrypto-plan-review` at tier `full` (`infra/scripts/tier.py --paths` over the plan's files, its output in the plan's head) before its first task. No topic is registered for any part of it.

## Intent and the measured defect

On 2026-11-17 Kraken's announced "Kraken Website and API Maintenance" (08:01–08:16Z) halted the books, and the archive reconciler booked hour 08 as permanent L2 loss: a `both_streams_silent` record of 5,432.534453 s, verdict `undetermined` on three fleet-dark windows, logged at ERROR, which stepped `zcrypto_reconcile_residual_gap_seconds_total` from 72113.36129 to 77545.895743 and paged both `zcrypto-reconcile-residual-gap` ("Permanent L2 loss … the data is gone") and `Ops · ERROR logs` (*The measured basis*). The hour lost nothing: the primary's hour-08 updates, replayed from the L2 panel's hour-07 state, equal the fresh snapshot Kraken sent the secondary at its 08:12:18Z reconnect at all 200 levels on 12 of 12 pairs, and no trade printed inside the windows. The silence was the venue's book standing still.

The reconciler books every fleet-dark second as loss by design (`[iter-141]`, spec 00096 D1): `classify_dark_episode`'s verdict is triage only (`cli/archive/settle.py:275-282`), and on any episode that is not exactly two windows it returns `undetermined` before weighing anything (`:319-320`). Nothing the reconciler reads says a halt lost nothing, so it pages a loss for every halt the venue announces.

This change reads, from the two mirrors the reconciler already holds, whether the book carried through the silence, whether anything traded across it, and whether the whole market stood still around it long enough to be a halt; when all three hold, the hour's seconds book to a new non-paging counter and none to the residual counter.

## Goals, non-goals

Goals:

- A `both_streams_silent` hour whose mirrors prove the venue halted its books — every booked stream back on both hosts without a reconnect and carried through on at least one with no resync after the silence, nothing traded across it, and no pair printing for at least 240 s around each of its windows — books `verdict` `venue_halt`, its seconds to `zcrypto_reconcile_venue_halt_seconds_total`, none to `zcrypto_reconcile_residual_gap_seconds_total`, and pages nothing.
- Every other silence books and pages exactly as today: a host missing the hour or coming back on a reconnect, a reconnect or a resync on every host, a trade or a missing trade id across the silence, a trades segment that cannot be read or holds a null, mistyped or unconvertible stamp or id, a resume inside the hour's last five minutes, an all-pairs quiet shorter than 240 s around a window, a divergence between the mirrors on a two-window episode.
- The ledger stays append-only; records written before the change read as before, hour 08 of 2026-11-17 among them; an older image reading a `venue_halt` record books nothing from it.
- The page, the all-streams-silent page, the residual page's runbook section, the venue-status and silence sections, the README and the hygiene map say what a halt is and what it books.

Non-goals:

- Re-booking hour 08 of 2026-11-17 or any other hour already decided (D9, D16).
- Archiving Kraken's `status` ladder, or reading Kraken's or Grafana's endpoints from the reconciler (D2).
- Proving the book beyond rank 10 across a silence; the archive's own attestation stops there (D2).
- `continuity.py`'s exit bar, which reads no ledger (spec 00096's *Out of scope* stands).

## Constraints

- The reconciler runs on `zcrypto-ops`, this workstation, a live venue-facing fleet host: no play runs against it from this branch, and nothing here calls a Kraken or Grafana endpoint. Every reading below is offline, against the NAS's read-only mirrors and the ops ledger, read-only.
- The ledger is append-only and each `(pair, kind, hour, state)` is decided once (`_ledger`, `cli/archive/command.py:714-721`; `_decided`, `:726-727`); the counters are sums over it (`_totals`, `:368-444`), so a record that lowered a total would read as a counter reset.
- `zcrypto-reconcile-residual-gap` fires on `increase(…[24h]) > 0 and resets(…[24h]) == 0` (`infra/grafana/alerts.yaml:1635`); `Ops · ERROR logs` (`:2606`) pages on any ERROR line of the reconciler's unit.
- `tests/test_internal_terms_not_operator_visible.py` keeps `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>`, `D<N>` and `WP<N>` out of the alert texts, the runbook pages, the README and every string literal under `cli/`: the texts and lines below carry none.
- A top-level runbook page's list item with a universal word names its count or declares `(no count command: …)` (`infra/scripts/guidance-guard.py:72-76`).
- An alert-rule change ships by a Grafana push from `develop` after the merge (`.claude/skills/zcrypto-grafana-push/SKILL.md`), never from a task here; the app change ships on the ops image by an ops converge, the owner's hands (`.claude/rules/fleet-deploys.md`, `.claude/skills/zcrypto-rollout-image/SKILL.md`'s *Ops converges*).

## The measured basis

Read on this workstation from 2026-11-17, in one detached scratch worktree, `.tmp/r00163/inputs/scripts/wt`, at `6795cd513` (`base`) and with the plan's code committed on it as `fca07df6d` records it, before the quiet proof (`branch`), never pushed, but for the readings that name their own date and tree; the peer session's three scripts sit in its parent directory, read whole before they ran, and every script read the mirrors and the panel read-only. The mirrors are the NAS's export, `/mnt/zhao-crypto/capture-segments` (primary) and `/mnt/zhao-crypto/capture-segments-red` (secondary), the paths the deployed reconciler reads (`infra/ansible/roles/ops/templates/archive-pull.sh.j2:122-134`, `ops_nas_mount` at `infra/ansible/roles/ops/defaults/main.yml:97`); the ledger is `/var/lib/zcrypto-ops/capture-reconciled/reconcile-ledger.jsonl`, world-readable, read without `sudo`.

**The booking.** The ledger's record for hour 08, its stream windows summed per pair, and the residual counter as develop's own `_totals` sums the ledger cut before that record, at it, and whole (`.tmp/r00163/measure/m_record08.py`, run on `base`):

```
cd .tmp/r00163/inputs/scripts/wt && uv run -q python ../../../measure/m_record08.py
window 2026-11-17 08:01:05.624052+00:00 -> 2026-11-17 08:06:27.187670+00:00 321.563618
window 2026-11-17 08:06:28.474026+00:00 -> 2026-11-17 08:07:21.840157+00:00 53.366131
window 2026-11-17 08:08:57.384088+00:00 -> 2026-11-17 08:10:00.183500+00:00 62.799412
{'residual_seconds': 5432.534453, 'verdict': 'undetermined', 'interior_updates': 0, 'interior_snapshots': 0, 'pairs_agreeing': 0, 'pairs_skipped': 0, 'divergent_pairs': [], 'at': '2026-11-17T10:12:42.617497+00:00'}
ADA/EUR 454.499135 AVAX/EUR 468.104989 BTC/EUR 440.8996 DOGE/EUR 439.580915 DOT/EUR 454.613494 ETH/BTC 440.35824 ETH/EUR 440.01186 LINK/EUR 441.993294 LTC/EUR 477.31857 SOL/BTC 458.849172 SOL/EUR 471.979815 XRP/EUR 444.325369
record 507 of 520 | residual before it 72113.36128999999 with it 77545.89574299999 whole ledger 77545.89574299999
```

The SOL/BTC stream window opens the earliest, `08:01:04.649345`, and closes the latest, `08:10:18.021279` (the record's `stream_windows`). The textfile as it stands:

```
grep -E "^zcrypto_reconcile_(residual|dark|healable)" /var/lib/zcrypto-ops/textfile/reconcile.prom
zcrypto_reconcile_healable_gap_seconds_total 35854.826292
zcrypto_reconcile_residual_gap_seconds_total 77545.89574299999
zcrypto_reconcile_dark_episode_seconds_total{verdict="venue_silent"} 8469.908675
zcrypto_reconcile_dark_episode_seconds_total{verdict="capture_divergent"} 0.0
zcrypto_reconcile_dark_episode_seconds_total{verdict="undetermined"} 69075.987068
```

The venue's announcement, its ladder, the paging and the ERROR line are recorded in the ops journal's 2026-11-17 entry, on branch `ops-journal` at `6f01c8828`, not yet on `develop` (`git show 6f01c8828:docs/reference/ops-journal/2026-11.md`, lines 301 and 309): "Kraken Website and API Maintenance" posted 08:49:37.100Z on 2026-11-16 for 08:01–08:16Z; the `status` ladder on both hosts `maintenance` 08:01:05.643329Z, `cancel_only` 08:06:27.198347Z, `post_only` 08:08:17.516247Z, `maintenance` 08:08:57.398387Z, `post_only` 08:09:43.971784Z, `online` 08:10:21.745705Z; the 10:12:59.692Z line `archive reconcile: both_streams_silent hour=2026-11-17T08:00:00+00:00 windows=3 residual_s=5432.5 verdict=undetermined updates=0 snapshots=0 divergent=-` at ERROR; `zcrypto-ops-error-logs` Alerting at 10:13:40Z and `zcrypto-reconcile-residual-gap` at 10:14:00Z. This session reads no capture log, Loki or Kraken endpoint, so these are the journal's figures, not re-measured.

**The hour is complete at depth 100.** The peer session's replay, re-run: the panel's `07.state.json` book per pair, every primary hour-08 update through `cli/capture/book.py`'s `OrderBook` to the message whose stamp and checksum equal the snapshot's, compared with the secondary's 08:12:18Z snapshot.

```
cd .tmp/r00163/inputs/scripts/wt && uv run -q python ../l2_align.py
ADA/EUR   aligned at primary msg #6123 ts 08:12:18.538123 (snapshot 08:12:18.538123, 5 candidate(s)) mismatched levels 0 []
AVAX/EUR  aligned at primary msg #3925 ts 08:12:18.473107 (snapshot 08:12:18.473107, 2 candidate(s)) mismatched levels 0 []
BTC/EUR   aligned at primary msg #9853 ts 08:12:18.527185 (snapshot 08:12:18.527185, 6 candidate(s)) mismatched levels 0 []
DOGE/EUR  aligned at primary msg #13264 ts 08:12:18.500279 (snapshot 08:12:18.500279, 2 candidate(s)) mismatched levels 0 []
DOT/EUR   aligned at primary msg #2585 ts 08:12:18.473059 (snapshot 08:12:18.473059, 2 candidate(s)) mismatched levels 0 []
ETH/BTC   aligned at primary msg #5700 ts 08:12:18.482149 (snapshot 08:12:18.482149, 1 candidate(s)) mismatched levels 0 []
ETH/EUR   aligned at primary msg #15612 ts 08:12:18.561312 (snapshot 08:12:18.561312, 6 candidate(s)) mismatched levels 0 []
LINK/EUR  aligned at primary msg #13510 ts 08:12:18.472256 (snapshot 08:12:18.472256, 1 candidate(s)) mismatched levels 0 []
LTC/EUR   aligned at primary msg #3272 ts 08:12:18.121168 (snapshot 08:12:18.121168, 3 candidate(s)) mismatched levels 0 []
SOL/BTC   aligned at primary msg #1906 ts 08:12:18.340946 (snapshot 08:12:18.340946, 3 candidate(s)) mismatched levels 0 []
SOL/EUR   aligned at primary msg #7652 ts 08:12:18.282292 (snapshot 08:12:18.282292, 1 candidate(s)) mismatched levels 0 []
XRP/EUR   aligned at primary msg #14676 ts 08:12:18.412351 (snapshot 08:12:18.412351, 2 candidate(s)) mismatched levels 0 []
exact at all 200 levels: 12 of 12
cd .tmp/r00163/inputs/scripts/wt && uv run -q python ../l2_control.py
ADA/EUR   dropped 40 message(s), 266 level rows, stamped 08:07:22.007 -> mismatched levels 114
AVAX/EUR  dropped 61 message(s), 212 level rows, stamped 08:07:32.860 -> mismatched levels 55
BTC/EUR   dropped 30 message(s), 309 level rows, stamped 08:07:21.930 -> mismatched levels 132
DOGE/EUR  dropped 41 message(s), 251 level rows, stamped 08:07:21.951 -> mismatched levels 154
DOT/EUR   dropped 42 message(s), 216 level rows, stamped 08:07:21.951 -> mismatched levels 77
ETH/BTC   dropped 23 message(s), 127 level rows, stamped 08:07:21.955 -> mismatched levels 60
ETH/EUR   dropped 44 message(s), 303 level rows, stamped 08:07:21.915 -> mismatched levels 86
LINK/EUR  dropped 42 message(s), 223 level rows, stamped 08:07:21.840 -> mismatched levels 159
LTC/EUR   dropped 59 message(s), 190 level rows, stamped 08:07:54.315 -> mismatched levels 35
SOL/BTC   dropped 29 message(s), 140 level rows, stamped 08:07:21.945 -> mismatched levels 58
SOL/EUR   dropped 62 message(s), 255 level rows, stamped 08:07:51.982 -> mismatched levels 59
XRP/EUR   dropped 45 message(s), 326 level rows, stamped 08:07:21.898 -> mismatched levels 119
control broke the match on 12 of 12 pairs
```

The peer's third script, `l2_continuity.py`, cuts at `ts <` the snapshot's stamp and reads `pairs matching at every level: 0 of 12`, each pair 1–3 levels off: the cut drops the snapshot's own instant, the shape the peer reported, and the reason `l2_align.py` cuts on stamp and checksum.

**What the reconciler can read of it.** Per pair: the snapshot rows on each mirror, the type of the first row at or after each booked stream window's end, and the trade tape, both mirrors unioned by id and ordered by stamp then id, across the three fleet windows (`.tmp/r00163/measure/m_hour08.py`):

```
cd .tmp/r00163/inputs/scripts/wt && uv run -q python ../../../measure/m_hour08.py
ADA/EUR   primary snapshot_rows=0 first_after=update/update/update | secondary snapshot_rows=200 at 08:12:18.538123 first_after=update/update/update | trades=68 inside=0 id_step=-,-,-
AVAX/EUR  primary snapshot_rows=0 first_after=update/update/update | secondary snapshot_rows=200 at 08:12:18.473107 first_after=update/update/update | trades=61 inside=0 id_step=-,-,-
BTC/EUR   primary snapshot_rows=0 first_after=update/update/update | secondary snapshot_rows=200 at 08:12:18.527185 first_after=update/update/update | trades=1377 inside=0 id_step=1,1,1
DOGE/EUR  primary snapshot_rows=0 first_after=update/update/update | secondary snapshot_rows=200 at 08:12:18.500279 first_after=update/update/update | trades=25 inside=0 id_step=1,1,1
DOT/EUR   primary snapshot_rows=0 first_after=update/update/update | secondary snapshot_rows=200 at 08:12:18.473059 first_after=update/update/update | trades=30 inside=0 id_step=-,-,-
ETH/BTC   primary snapshot_rows=0 first_after=update/update/update | secondary snapshot_rows=200 at 08:12:18.482149 first_after=update/update/update | trades=29 inside=0 id_step=-,-,-
ETH/EUR   primary snapshot_rows=0 first_after=update/update/update | secondary snapshot_rows=200 at 08:12:18.561312 first_after=update/update/update | trades=219 inside=0 id_step=1,1,1
LINK/EUR  primary snapshot_rows=0 first_after=update/update/update | secondary snapshot_rows=200 at 08:12:18.472256 first_after=update/update/update | trades=44 inside=0 id_step=1,1,1
LTC/EUR   primary snapshot_rows=0 first_after=update/update/update | secondary snapshot_rows=200 at 08:12:18.121168 first_after=update/update/update | trades=73 inside=0 id_step=1,1,1
SOL/BTC   primary snapshot_rows=0 first_after=update/update/update | secondary snapshot_rows=200 at 08:12:18.340946 first_after=update/update/update | trades=20 inside=0 id_step=-,-,-
SOL/EUR   primary snapshot_rows=0 first_after=update/update/update | secondary snapshot_rows=200 at 08:12:18.282292 first_after=update/update/update | trades=213 inside=0 id_step=1,1,1
XRP/EUR   primary snapshot_rows=0 first_after=update/update/update | secondary snapshot_rows=200 at 08:12:18.412351 first_after=update/update/update | trades=221 inside=0 id_step=1,1,1
```

`-` is a pair with no print in the hour before the first window. The first reading ordered the tape by stamp alone and read DOGE/EUR's step as 2: two of its prints share one stamp after the windows, and a tie broken against the ids reads a hole that is not there. The rule orders by stamp then id (D4), and a case pins it.

**The rule over every dark hour the ledger holds.** `classify_halt` as the plan writes it, over each `both_streams_silent` record's own `windows` and `stream_windows` (a record that predates `stream_windows` reads its `windows`), on the mirrors' files for that hour (`.tmp/r00163/measure/m_impl_backtest.py`, its print line carrying `quiet_s`, run by the orchestrator on 2026-11-18 from a scratch worktree at `3ca813e40` carrying the plan's `cli/archive/settle.py`):

```
cd .tmp/r3fix/wt && uv run -q python ../../r00163/measure/m_impl_backtest.py
2026-07-13T07 booked=None windows=1 carried=0/10 bracketed=0/1 trades_inside=120 id_holes=0 quiet_s=0.0 holds=False residual_s=2661.788740 classify_s=0.00
2026-07-27T07 booked=None windows=1 carried=0/12 bracketed=1/1 trades_inside=0 id_holes=0 quiet_s=321.8 holds=False residual_s=2385.847992 classify_s=0.29
2026-08-06T07 booked=None windows=2 carried=0/12 bracketed=2/2 trades_inside=0 id_holes=0 quiet_s=1036.3 holds=False residual_s=10588.382751 classify_s=0.18
2026-08-20T07 booked=None windows=2 carried=0/12 bracketed=2/2 trades_inside=0 id_holes=0 quiet_s=779.7 holds=False residual_s=6251.349974 classify_s=0.48
2026-09-03T07 booked=undetermined windows=1 carried=0/12 bracketed=1/1 trades_inside=0 id_holes=0 quiet_s=305.2 holds=False residual_s=2134.703242 classify_s=0.42
2026-09-17T07 booked=undetermined windows=1 carried=0/12 bracketed=1/1 trades_inside=0 id_holes=0 quiet_s=331.8 holds=False residual_s=2208.788413 classify_s=0.30
2026-10-01T07 booked=undetermined windows=1 carried=0/12 bracketed=1/1 trades_inside=0 id_holes=0 quiet_s=304.9 holds=False residual_s=2407.083528 classify_s=0.74
2026-10-13T14 booked=undetermined windows=1 carried=0/12 bracketed=1/1 trades_inside=37 id_holes=9 quiet_s=67.1 holds=False residual_s=748.267788 classify_s=0.92
2026-10-15T07 booked=venue_silent windows=2 carried=12/12 bracketed=2/2 trades_inside=0 id_holes=0 quiet_s=303.0 holds=True residual_s=2849.043767 classify_s=2.77
2026-10-29T08 booked=venue_silent windows=2 carried=12/12 bracketed=2/2 trades_inside=0 id_holes=0 quiet_s=406.6 holds=True residual_s=3276.446273 classify_s=1.96
2026-10-30T02 booked=undetermined windows=1 carried=0/12 bracketed=0/1 trades_inside=0 id_holes=0 quiet_s=0.0 holds=False residual_s=26831.390459 classify_s=0.29
2026-10-30T03 booked=undetermined windows=3 carried=0/12 bracketed=0/3 trades_inside=0 id_holes=0 quiet_s=0.0 holds=False residual_s=7425.849728 classify_s=1.82
2026-10-30T08 booked=venue_silent windows=2 carried=12/12 bracketed=2/2 trades_inside=0 id_holes=0 quiet_s=318.0 holds=True residual_s=2344.418635 classify_s=2.51
2026-11-17T08 booked=undetermined windows=3 carried=12/12 bracketed=3/3 trades_inside=0 id_holes=0 quiet_s=557.0 holds=True residual_s=5432.534453 classify_s=3.00
```

Four of the fourteen hold. The capture defect of 2026-07-13 (spec 00096's true negative) is refused on its snapshots and its 120 prints inside the window; 2026-10-13, a derivatives maintenance in which spot traded on, on its snapshots, 37 prints inside and 9 id holes; 2026-10-30 02Z on a window that runs to the hour's end. On the rest every stream carries a snapshot on both mirrors at or after its first window's start — at its resume, between its windows, or after its last — reconnects, which leave unread whether anything changed in the silence. The classification took 0.00–3.00 s a dark hour on this run; the timing varies by run (runs before the quiet proof read 0.00–2.87 s, 0.00–2.86 s and 0.00–2.96 s) and is not a bound. Where each stream's first such snapshot sits (`.tmp/r00163/measure/m_snapshot_ranges.py`):

```
cd .tmp/r00163/inputs/scripts/wt && uv run -q python ../../../measure/m_snapshot_ranges.py
2026-07-13T07 primary   none=0 at_resume=1 between=0 after=9 1.8-4.4s
2026-07-13T07 secondary none=0 at_resume=0 between=0
2026-07-27T07 primary   none=0 at_resume=0 between=0 after=12 9.7-11.8s
2026-07-27T07 secondary none=0 at_resume=1 between=0 after=11 0.5-5.4s
2026-08-06T07 primary   none=0 at_resume=11 between=1
2026-08-06T07 secondary none=0 at_resume=0 between=12
2026-08-20T07 primary   none=0 at_resume=11 between=1
2026-08-20T07 secondary none=0 at_resume=11 between=1
2026-09-03T07 primary   none=0 at_resume=12 between=0
2026-09-03T07 secondary none=0 at_resume=12 between=0
2026-09-17T07 primary   none=0 at_resume=12 between=0
2026-09-17T07 secondary none=0 at_resume=12 between=0
2026-10-01T07 primary   none=0 at_resume=12 between=0
2026-10-01T07 secondary none=0 at_resume=1 between=0 after=11 2.2-9.8s
2026-10-13T14 primary   none=0 at_resume=12 between=0
2026-10-13T14 secondary none=0 at_resume=0 between=0 after=12 3.9-4.3s
2026-10-15T07 primary   none=12 at_resume=0 between=0
2026-10-15T07 secondary none=12 at_resume=0 between=0
2026-10-29T08 primary   none=12 at_resume=0 between=0
2026-10-29T08 secondary none=12 at_resume=0 between=0
2026-10-30T02 primary   none=12 at_resume=0 between=0
2026-10-30T02 secondary none=12 at_resume=0 between=0
2026-10-30T03 primary   none=0 at_resume=0 between=0 after=12 432.8-511.7s
2026-10-30T03 secondary none=0 at_resume=0 between=0 after=12 1354.4-1432.8s
2026-10-30T08 primary   none=12 at_resume=0 between=0
2026-10-30T08 secondary none=12 at_resume=0 between=0
2026-11-17T08 primary   none=12 at_resume=0 between=0
2026-11-17T08 secondary none=0 at_resume=0 between=0 after=12 120.3-138.3s
```

2026-07-13's secondary held no file for the hour (`carried=0/10` is its ten pairs on the primary alone).

Where each mirror came back after each stream window — the latest first row at or after a window's end, past the hour's start; how many such resumes fall in the hour's last 300 s; how many are missing (no row after the window, or no file); and how many are a snapshot, a snapshot row sharing the resume's stamp counting (`.tmp/r00163/measure/m_resumes.py`):

```
cd .tmp/r00163/inputs/scripts/wt && uv run -q python ../../../measure/m_resumes.py
2026-07-13T07 primary latest=0:04:30.615836 last_300s=0 missing=0 on_snapshot=10 | secondary latest=None last_300s=0 missing=10 on_snapshot=0
2026-07-27T07 primary latest=0:04:34.703063 last_300s=0 missing=0 on_snapshot=12 | secondary latest=0:04:28.316700 last_300s=0 missing=0 on_snapshot=12
2026-08-06T07 primary latest=0:16:15.958488 last_300s=0 missing=0 on_snapshot=11 | secondary latest=0:16:15.958488 last_300s=0 missing=0 on_snapshot=11
2026-08-20T07 primary latest=0:10:15.672329 last_300s=0 missing=0 on_snapshot=11 | secondary latest=0:10:15.672329 last_300s=0 missing=0 on_snapshot=11
2026-09-03T07 primary latest=0:04:00.668272 last_300s=0 missing=0 on_snapshot=12 | secondary latest=0:04:00.668272 last_300s=0 missing=0 on_snapshot=12
2026-09-17T07 primary latest=0:04:11.477770 last_300s=0 missing=0 on_snapshot=12 | secondary latest=0:04:11.477770 last_300s=0 missing=0 on_snapshot=12
2026-10-01T07 primary latest=0:04:25.757377 last_300s=0 missing=0 on_snapshot=12 | secondary latest=0:04:31.444883 last_300s=0 missing=0 on_snapshot=12
2026-10-13T14 primary latest=0:31:50.019821 last_300s=0 missing=0 on_snapshot=12 | secondary latest=0:31:53.981279 last_300s=0 missing=0 on_snapshot=12
2026-10-15T07 primary latest=0:05:08.324270 last_300s=0 missing=0 on_snapshot=0 | secondary latest=0:05:08.324270 last_300s=0 missing=0 on_snapshot=0
2026-10-29T08 primary latest=0:05:58.561001 last_300s=0 missing=0 on_snapshot=0 | secondary latest=0:05:58.561001 last_300s=0 missing=0 on_snapshot=0
2026-10-30T02 primary latest=None last_300s=0 missing=12 on_snapshot=0 | secondary latest=None last_300s=0 missing=12 on_snapshot=0
2026-10-30T03 primary latest=0:10:38.697894 last_300s=0 missing=0 on_snapshot=0 | secondary latest=0:10:38.697894 last_300s=0 missing=0 on_snapshot=0
2026-10-30T08 primary latest=0:04:32.830694 last_300s=0 missing=0 on_snapshot=0 | secondary latest=0:04:32.830694 last_300s=0 missing=0 on_snapshot=0
2026-11-17T08 primary latest=0:10:18.021279 last_300s=0 missing=0 on_snapshot=0 | secondary latest=0:10:18.021279 last_300s=0 missing=0 on_snapshot=0
```

The four halts came back on an update on both mirrors on every stream. Each other hour's mirrors came back on a snapshot on 10 to 12 of their resumes — 2026-07-13's secondary holding no file — but 2026-10-30's: 02Z never came back in the hour, and 03Z's snapshots sit after its last window (above).

**How long the market stood still.** Around each dark hour's fleet windows, the all-pairs quiet span — from the last print on any of the 12 pairs, on either mirror, at or before the window's start, to the first at or after its end — read over the hour's day and the days either side; then every all-pairs gap of 90 s or more from 2026-07-14 on outside the ledger's dark hours — the hygiene map's rows before that date are launch day, with its crash-loop and its largest trade gap on a capture host predating the secondary, and the desync-heal era to 07-14 04:00:42, whose tape it calls gap-pocked, so an all-pairs gap there can be one host's own loss — and, across the longest, each pair's trade ids either side of it and each mirror's book rows inside it (`.tmp/r00163/measure/m_quiet.py` and `m_quiet2.py`, read-only, their output saved beside them as `m_quiet.out` and `m_quiet2.out` on 2026-11-18; `m_quiet.out`'s Part 2, its lines 28 to 79, every all-pairs gap of 60 s or more from 2026-07-01 on, is not pasted, and reads 16 gaps of 240 s or more outside the dark hours: 15 on 2026-07-08 and 2026-07-11, each `ledger=-`, the longest 727.8 s at 2026-07-11T02:15:31, and the 2026-10-08 stretch below):

```
sed -n '1,26p' .tmp/r00163/measure/m_quiet.out
pairs: 12 ADA/EUR AVAX/EUR BTC/EUR DOGE/EUR DOT/EUR ETH/BTC ETH/EUR LINK/EUR LTC/EUR SOL/BTC SOL/EUR XRP/EUR

== Part 1: each dark hour's fleet windows, the all-pairs quiet span around each
2026-07-13T07 verdict=None window 07:00:00->07:04:26 (266.2 s) inside=111 quiet span=389.56158 s (06:59:54 -> 07:06:23)
2026-07-27T07 verdict=None window 07:01:04->07:04:22 (198.8 s) inside=0 quiet span=321.839188 s (07:00:59 -> 07:06:21)
2026-08-06T07 verdict=None window 07:01:02->07:15:07 (845.0 s) inside=0 quiet span=1036.296453 s (07:01:02 -> 07:18:18)
2026-08-06T07 verdict=None window 07:15:07->07:15:39 (32.2 s) inside=0 quiet span=1036.296453 s (07:01:02 -> 07:18:18)
2026-08-20T07 verdict=None window 07:01:04->07:07:17 (372.5 s) inside=0 quiet span=779.709086 s (07:01:03 -> 07:14:02)
2026-08-20T07 verdict=None window 07:08:55->07:09:43 (48.0 s) inside=0 quiet span=779.709086 s (07:01:03 -> 07:14:02)
2026-09-03T07 verdict=undetermined window 07:01:02->07:03:58 (176.4 s) inside=0 quiet span=305.171671 s (07:00:59 -> 07:06:04)
2026-09-17T07 verdict=undetermined window 07:01:04->07:03:53 (169.0 s) inside=0 quiet span=331.830042 s (07:01:04 -> 07:06:35)
2026-10-01T07 verdict=undetermined window 07:01:03->07:04:21 (197.1 s) inside=0 quiet span=304.930478 s (07:01:03 -> 07:06:08)
2026-10-13T14 verdict=undetermined window 14:30:47->14:31:49 (62.0 s) inside=33 quiet span=67.129539 s (14:30:47 -> 14:31:54)
2026-10-15T07 verdict=venue_silent window 07:01:03->07:02:56 (112.9 s) inside=0 quiet span=302.965471 s (07:00:58 -> 07:06:01)
2026-10-15T07 verdict=venue_silent window 07:03:27->07:04:55 (88.6 s) inside=0 quiet span=302.965471 s (07:00:58 -> 07:06:01)
2026-10-29T08 verdict=venue_silent window 08:01:07->08:03:14 (126.9 s) inside=0 quiet span=406.615811 s (08:01:06 -> 08:07:52)
2026-10-29T08 verdict=venue_silent window 08:03:19->08:04:34 (74.3 s) inside=0 quiet span=406.615811 s (08:01:06 -> 08:07:52)
2026-10-30T02 verdict=undetermined window 02:22:44->03:00:00 (2235.9 s) inside=0 quiet span=3129.533946 s (02:22:40 -> 03:14:50)
2026-10-30T03 verdict=undetermined window 03:00:00->03:06:34 (394.4 s) inside=0 quiet span=3129.533946 s (02:22:40 -> 03:14:50)
2026-10-30T03 verdict=undetermined window 03:06:38->03:07:29 (51.3 s) inside=0 quiet span=3129.533946 s (02:22:40 -> 03:14:50)
2026-10-30T03 verdict=undetermined window 03:08:40->03:09:20 (40.1 s) inside=0 quiet span=3129.533946 s (02:22:40 -> 03:14:50)
2026-10-30T08 verdict=venue_silent window 08:01:03->08:02:55 (111.6 s) inside=0 quiet span=317.958359 s (08:01:03 -> 08:06:21)
2026-10-30T08 verdict=venue_silent window 08:02:56->08:04:01 (65.0 s) inside=0 quiet span=317.958359 s (08:01:03 -> 08:06:21)
2026-11-17T08 verdict=undetermined window 08:01:05->08:06:27 (321.6 s) inside=0 quiet span=557.017323 s (08:01:04 -> 08:10:21)
2026-11-17T08 verdict=undetermined window 08:06:28->08:07:21 (53.4 s) inside=0 quiet span=557.017323 s (08:01:04 -> 08:10:21)
2026-11-17T08 verdict=undetermined window 08:08:57->08:10:00 (62.8 s) inside=0 quiet span=557.017323 s (08:01:04 -> 08:10:21)
cat .tmp/r00163/measure/m_quiet2.out
== Part A: all-pairs gaps >= 90 s from 2026-07-14, outside both_streams_silent hours
      95.3 s  2026-09-27T02:34:26 -> 2026-09-27T02:36:02  Sun
     968.4 s  2026-10-08T14:59:54 -> 2026-10-08T15:16:03  Thu
     121.3 s  2026-10-08T15:16:57 -> 2026-10-08T15:18:59  Thu
     108.4 s  2026-11-03T03:13:12 -> 2026-11-03T03:15:00  Tue
  count: 4

== Part B: 2026-10-08 14:59:54 -> 15:16:03
  ADA/EUR   last before 2026-10-08 14:59:49.430459+00:00 id 14695153 | first after 2026-10-08 15:20:54.753930+00:00 id 14696137 | id step 984 | primary: updates=140850 other=200; secondary: updates=140048 other=200
  AVAX/EUR  last before 2026-10-08 14:59:04.662518+00:00 id 1880055 | first after 2026-10-08 15:21:06.954996+00:00 id 1880495 | id step 440 | primary: updates=67265 other=200; secondary: updates=67033 other=200
  BTC/EUR   last before 2026-10-08 14:59:43.431171+00:00 id 109788834 | first after 2026-10-08 15:21:03.615646+00:00 id 109789917 | id step 1083 | primary: updates=159198 other=200; secondary: updates=158643 other=200
  DOGE/EUR  last before 2026-10-08 14:59:49.446199+00:00 id 10150922 | first after 2026-10-08 15:20:55.147888+00:00 id 10151223 | id step 301 | primary: updates=139490 other=200; secondary: updates=138379 other=200
  DOT/EUR   last before 2026-10-08 14:59:35.830988+00:00 id 8205866 | first after 2026-10-08 15:20:53.085320+00:00 id 8206272 | id step 406 | primary: updates=67538 other=200; secondary: updates=67101 other=200
  ETH/BTC   last before 2026-10-08 14:57:31.106917+00:00 id 46377230 | first after 2026-10-08 15:20:41.010418+00:00 id 46377323 | id step 93 | primary: updates=99492 other=200; secondary: updates=99132 other=200
  ETH/EUR   last before 2026-10-08 14:59:54.691152+00:00 id 56654371 | first after 2026-10-08 15:21:10.555322+00:00 id 56655224 | id step 853 | primary: updates=183003 other=200; secondary: updates=182661 other=200
  LINK/EUR  last before 2026-10-08 14:59:05.431384+00:00 id 5674841 | first after 2026-10-08 15:20:59.520594+00:00 id 5675169 | id step 328 | primary: updates=161492 other=200; secondary: updates=161018 other=200
  LTC/EUR   last before 2026-10-08 14:59:22.653774+00:00 id 21584917 | first after 2026-10-08 15:21:02.851034+00:00 id 21585617 | id step 700 | primary: updates=38885 other=200; secondary: updates=38798 other=200
  SOL/BTC   last before 2026-10-08 14:50:52.662889+00:00 id 4271104 | first after 2026-10-08 15:16:03.094661+00:00 id 4271150 | id step 46 | primary: updates=36298 other=200; secondary: updates=36129 other=200
  SOL/EUR   last before 2026-10-08 14:59:50.092547+00:00 id 15199989 | first after 2026-10-08 15:21:06.989391+00:00 id 15200793 | id step 804 | primary: updates=67875 other=200; secondary: updates=67411 other=200
  XRP/EUR   last before 2026-10-08 14:59:49.438412+00:00 id 28638357 | first after 2026-10-08 15:21:01.207835+00:00 id 28638965 | id step 608 | primary: updates=159083 other=200; secondary: updates=157841 other=200
```

Each of the four halts' spans opens and closes inside its hour, so the rule, which reads the hour's files alone, reads the same: 302.965471 s on 2026-10-15 the shortest, 557.017323 s on 2026-11-17 the longest. The 2026-10-08 stretch is not a quiet market: every pair's ids step 46 to 1,083 across it while each mirror holds 36,129 to 183,003 book updates a pair inside it, the trades missing from the mirrors, and the 121.3 s gap after it ends before 11 of the 12 pairs print again, ETH/BTC first at 15:20:41. Outside the ledger's dark hours, the market's own all-pairs quiet from 2026-07-14 on runs to 108.4 s. The rule over every dark hour, run with the quiet proof, holds on the same four, their `quiet_s` 303.0, 406.6, 318.0 and 557.0, the spans above rounded, and refuses the other ten, every column but `quiet_s` and `classify_s` as the run before the quiet proof read.

**The reconciler end to end.** Develop's and the branch's `zcrypto archive reconcile`, the branch's code the plan's as `fca07df6d` records it, before the quiet proof, detect-only, over the same mirrors into empty scratch overlays under `.tmp/r00163/golden/`, both started 23:36Z with `--window-hours 14`, so both examined 08Z–21Z:

```
G=.tmp/r00163/golden   # run on base into $G/base, then on branch into $G/branch, each from the scratch worktree
uv run -q zcrypto archive reconcile /mnt/zhao-crypto/capture-segments /mnt/zhao-crypto/capture-segments-red $G/<run>/reconciled --window-hours 14 --min-gap-seconds 30 --detect-only --textfile $G/<run>/reconcile.prom > $G/<run>/log.txt 2>&1
base:   started 23:36:04Z, real 0m32.294s, rc=0
branch: started 23:36:37Z, real 0m34.389s, rc=0
python3 .tmp/r00163/measure/m_golden.py
base archive reconcile: both_streams_silent hour=2026-11-17T08:00:00+00:00 windows=3 residual_s=5432.5 verdict=undetermined updates=0 snapshots=0 divergent=- | ERROR
base reconcile complete mode=detect-only window_h=14 spliced=0 union=0 healed_s=0.0 residual_s=5432.5 failures=0 skipped=0 audited=0 | INFO
branch archive reconcile: both_streams_silent hour=2026-11-17T08:00:00+00:00 windows=3 residual_s=0.0 verdict=venue_halt updates=0 snapshots=0 divergent=- halt_s=5432.5 carried=12/12 bracketed=3/3 trades_inside=0 id_holes=0 | WARNING
branch reconcile complete mode=detect-only window_h=14 spliced=0 union=0 healed_s=0.0 residual_s=0.0 failures=0 skipped=0 audited=0 | INFO
records 13 13 differing: [('both_streams_silent', '2026-11-17T08:00:00+00:00', ['halt_seconds', 'residual_seconds', 'streams_carried', 'trade_id_holes', 'trades_inside', 'verdict', 'windows_bracketed'])]
{'verdict': 'venue_halt', 'residual_seconds': 0.0, 'halt_seconds': 5432.534453, 'streams_carried': 12, 'windows_bracketed': 3, 'trades_inside': 0, 'trade_id_holes': 0}
base's hour-08 record equals the live ledger's but for at: True
zcrypto_reconcile_dark_episode_seconds_total{verdict="undetermined"} 5432.534453 -> 0.0
zcrypto_reconcile_residual_gap_seconds_total 5432.534453 -> 0.0
zcrypto_reconcile_venue_halt_seconds_total None -> 5432.534453
```

The two ledgers agree on every record and every key but the hour-08 record's halt fields, and develop's record equals the live ledger's but for `at`. The plan as it stands also writes `quiet_seconds` on that record and `quiet_s=` on that line, and the rule it ships is the one *The rule over every dark hour the ledger holds* ran above, which holds on this hour with `quiet_s=557.0`. The deployed reconciler runs `--mint` (`infra/ansible/host_vars/zcrypto-ops/vars.yml:51`); the `both_streams_silent` block runs in both modes and before the mint path, so detect-only reads it whole.

**Where the ladder lives.** Nowhere the reconciler reads: capture's `status` branch logs `venue status system=… version=… effective_time=…` and bumps an in-memory count behind `zcrypto_capture_venue_status_total` (`cli/capture/command.py:273-287`), no parquet column carries it, and the capture log is on the two capture hosts and in Loki (`infra/runbooks/capture.md`, the venue-status section's step 1). The reconciler's inputs are the two mirrors' `book` and `trades` finals and its own ledger.

## Operating model

- **The capture daemons.** One on `zcrypto` (primary), one on `zcrypto-red` (secondary), each with its own Kraken WS v2 connection subscribing `book` at depth 100 and `trade` for the 12 pairs, every subscribe asking for a snapshot (`cli/capture/ws_client.py:41-45`). Each book message is written row per level with Kraken's own stamp as `ts`, its `type` `snapshot` or `update`, and Kraken's checksum (`cli/capture/command.py:204-222`); each update's CRC is checked live against the book the daemon carries, and a mismatch resubscribes at once (`:187-197`), a desync still open retrying at 20, 25 and 35 s and reconnecting at 55 s (`cli/capture/desync_recovery.py:38-40`, `due`), each rung writing a fresh snapshot when Kraken answers it. A disk-watermark breach stops the writes, books and trades both, while the reads go on (`:204`, `:227`). Hour finals concatenate rows in arrival order and are never sorted (`cli/capture/segment_writer.py:864`); the reconciler refuses a stream whose stamps go backwards (`cli/archive/reconcile.py:66-114`).
- **The NAS pull.** The NAS pulls each host's segments hash-verified into `capture-segments` and `capture-segments-red` and exports them read-only over NFS; the ops host mounts them at `/mnt/zhao-crypto` (`ops_nas_mount`).
- **The reconciler.** `zcrypto-archive-pull.timer` on `zcrypto-ops`, at `:12` and `:42` (`infra/ansible/roles/ops/templates/archive-pull.timer.j2:17`), runs `zcrypto archive reconcile /nas/capture-segments /nas/capture-segments-red /data/capture-reconciled --window-hours 48 --min-gap-seconds 30 --mint --textfile /textfile/reconcile.prom` in the ops image (`archive-pull.sh.j2:122-134`, `ops_reconcile_window_hours` and `ops_reconcile_min_gap_seconds` at `infra/ansible/roles/ops/defaults/main.yml:127-128`). One process per tick, no state but the ledger.
- **Its ledger.** `reconcile-ledger.jsonl` in the overlay, under `ops_data_dir`; the NAS replicates it unparsed. Its only reader is `cli/archive/command.py` itself (`bench-ledger-scan.py` writes its own synthetic one).
- **Its metrics.** `reconcile.prom` in the textfile directory, rewritten whole each clean cycle (`_write_textfile`, `:463-596`) and shipped by the ops Alloy, whose metric pipeline relabels and drops nothing (`infra/ansible/roles/ops/files/config.alloy:50-155`; `grep -c "prometheus.relabel\|metric_relabel\|write_relabel"` reads `0`). `zcrypto-reconcile-residual-gap` reads the residual counter; `Ops · ERROR logs` reads the unit's journal by level.
- **What names an hour and a silent window across them.** An hour is a UTC hour H, one `<HH>.parquet` final per pair per kind per mirror, settled at H+2 h (`SETTLE_HOURS`) and decided at the first tick after. A fleet-dark window is a gap of more than `--min-gap-seconds` in the union of every pair's book stamps on both mirrors (`fleet_dark_windows`, `cli/archive/settle.py:167-198`); a stream's window is that stream's own silence around it over both mirrors (`containing_dark_window`, `:201-262`). Because `ts` is Kraken's stamp, the same message carries the same stamp on both hosts, and the windows are the venue's timeline, not either host's clock. A trade is named by its pair and Kraken's `trade_id`, dense per pair (`docs/reference/capture-era-data-hygiene-map.md`'s canonical-trades row).

## Decisions

**D1. The owner's ruling: the fix now, on this branch, with no topic.** Asked by `zcrypto-zebra` whether the reconciler should stop booking a halt like 2026-11-17 08Z's as residual; the owner's ruling, 2026-11-17T19:47:55.448Z, verbatim: "for the reconciler change, fix it right aways in a branch without deferring it to a new T-topic". It supersedes spec 00096 D1 and `[iter-141]`'s first entry for one evidence class alone, the halt D2 defines. D1's three grounds were weighed against it: the traumatic correction it cites is not repeated, since nothing already booked is touched (D9); the asymmetric failure — a shared-mode capture failure going unbooked — is what D2's three proofs and D5 exist to refuse, each refusal pinned by a case, but for one residue they cannot: a fault of the capture image both hosts run that drops every pair's rows on both inside a natural all-pairs quiet of 240 s or more books as a halt and pages nothing, a quiet the archive from 2026-07-14 on has not shown outside the ledger's dark hours, its longest 108.4 s (*The measured basis*, *Failure modes*); and its "evidence-weighting must never gate a monotonic record" is met by evidence about the data, not about the cause: the venue's own checksum accepting the book carried across the silence, and its own dense trade ids.

**D2. A venue halt, to the reconciler, is a fleet-dark hour its two mirrors prove lost nothing; the announcement is not the proof.** Three proofs, all holding:

- *The book carried through.* For every stream the record books, both mirrors hold it and come back after each of its windows on an update, and at least one of them stamps no `snapshot` row from the stream's first window's start to the hour's end. Capture checks every update against the book it carries and resyncs on a mismatch, and a resync or a reconnect writes a snapshot; so a resume with no snapshot after it is Kraken's checksum accepting, for ranks 1–10, the book the host carried across the silence — the archive's standing attestation (the hygiene map's ranks 1–10 row), applied to the silence. The other mirror must hold the stream and come back on an update too (D3): the carrying host's checksum vouches for what it received, not what it wrote.
- *Nothing traded.* No pair prints, on either mirror, inside its own booked silence — the stream windows the record books for it, each containing a fleet window, so a pair that went quiet before the fleet or came back after it is held over the whole of its booked seconds; every pair whose prints straddle a fleet window steps its trade ids by exactly one across it; and each fleet window is straddled by some pair. A writer that dropped rows while the daemon kept reading — the watermark breach, or a shared-image writer bug — leaves the checksum whole, and this is what sees it wherever the venue matched across the drop: ids skip or a print lands inside.
- *The market stood still long enough to be a halt.* Around each fleet window, the all-pairs quiet span — from the last print on any pair the record books, on either mirror, at or before the window's start, to the first at or after its end, both inside the hour's files — is at least `QUIET_SPAN_SECONDS = 240.0`, else the hour is unproven and books as today. A writer that drops every pair's rows on both hosts across a stretch in which no pair printed passes the other two proofs, leaving the mirrors a halt leaves; a halt stops every pair's matching for minutes, and the market's own all-pairs quiet is shorter. 240 s is 2.2 times the longest all-pairs quiet the archive shows from 2026-07-14 on outside the ledger's dark hours, 108.4 s, and 62.965471 s under the shortest proven halt's, 302.965471 s on 2026-10-15 (*The measured basis*); a real halt with a shorter quiet books as loss and pages, as every halt does today.

The ladder is not in the reconciler's inputs (*The measured basis*), and reading it, or Kraken's maintenance feed, or Grafana, from the reconciler is a third-party call in an append-only booking path (`[iter-141]`'s third option, T0145's resolution); and an announcement says the venue meant to halt, not that the hosts missed nothing. What the evidence cannot establish stays what it is today: `undetermined` (or `venue_silent`), booked as loss, paged.

**D3. Both mirrors hold a stream and come back on an update; one of them carries it; a snapshot anywhere from its first window's start to the hour's end takes that mirror out; a resume later than 300 s before the hour's end, on either mirror, takes the stream out.** One mirror's checksum suffices because the window is dark on both: a venue message emitted inside it and missed would fail that host's checksum at the resume. That checksum vouches for what the host received, never for what it wrote — a watermark breach stops the writes while the reads, and the checksum, go on (*Operating model*) — so the other mirror must hold the stream for the hour and come back after each window on an update as well. A host that holds no file, never comes back in the hour, or comes back on a snapshot (a restart or a reconnect, whose subscribe asks for one; a snapshot row sharing the resume's stamp counts) went dark by its own outage, and the window would then be the carrying host's silence alone — one host's dropped writes reading as a halt. With both coming back on an update, a dropped write on one host loses data only if the other failed inside the same window too (*Failure modes*). The snapshot test runs to the hour's end rather than to a horizon after the resume: a horizon is a knob with a cliff — the secondary's reconnect on 2026-11-17 came 120.3–138.3 s after its streams resumed — and a later unrelated reconnect costs only that mirror. It starts at the window's start because a snapshot carries the stamp of the book's last change — each of the secondary's twelve 08:12:18Z snapshots carries the stamp and checksum of a primary update (*The measured basis*) — so a reconnect inside a frozen book lands a snapshot stamped at the window's start. `RESUME_MARGIN_SECONDS = 300.0`: a resync's snapshot follows the update that tripped it by at most the ladder's 55 s to its reconnect rung plus one 5 s recovery tick (`DESYNC_RECOVERY_INTERVAL_SECONDS`, `cli/capture/command.py:310`), and the update itself can reach capture late; a resume closer to the hour's end could carry its snapshot into the next hour, which the examination of this hour does not read. Over the ledger's fourteen dark hours no resume on either mirror falls in an hour's last 300 s; 2026-10-30 02Z, whose windows run to the hour's end, has none at all, and the four the rule holds on came back on both mirrors by 0:10:18.021279 into their hour (*The measured basis*).

**D4. The trade tape is both mirrors' prints unioned by id, ordered by stamp then id; an unreadable tape leaves the hour unproven.** A print one host missed and the other kept is a print, so a hole needs both to lack it. Prints sharing a stamp are one taker order against several makers; ordering ties by id makes the last print before a window the highest id and the first after the lowest (*The measured basis*, DOGE/EUR). The tape is read only on an hour that books `both_streams_silent`, two columns, `ts` and `trade_id`, of the files the trades heal reads anyway. An unreadable trades segment — one that cannot be opened; that opens with a null, or a dtype other than `TRADE_SCHEMA`'s, in `ts` or `trade_id`, the columns the proof compares and subtracts; or that holds a value in them with no Python stamp or id, out of range or one polars panics on converting — logs one WARNING and refuses the halt, whatever its twin or another pair's ids show: the prints it holds could be the ones inside a window, and the trades heal path is no backstop, skipping a pair-hour whose secondary final is absent and one whose primary final is absent until the late deadline (`cli/archive/command.py:1010-1014`). The hour still books, as loss: a read failure must not hold back a booking the book's own timeline already decided. Every trades final of the ledger's fourteen dark hours passes that test, 322 present on the two mirrors and 10 absent, 2026-07-13's secondary (`.tmp/r00163/measure/m_tape_schema.py`, read-only, from the scratch worktree: `fails: none` on every hour, `{'pass': 322, 'absent': 10}`); `m_impl_backtest.py` converts every one of them to Python values and printed all fourteen hours.

**D5. A divergence the triage reads keeps its loss and its page; a halt outranks `venue_silent` and `undetermined`.** `capture_divergent` says one host missed what the other received, a fleet finding the page exists for, so it is never masked by a halt. `classify_dark_episode` reads it on a two-window episode alone, comparing the mirrors between the windows; on one window or three or more it compares nothing, as on develop, and no divergence vetoes. When the three proofs hold, every trades segment read (D4), and the triage reads no divergence, the verdict is `venue_halt`, whatever else `classify_dark_episode` weighed: its verdict stays triage but for that one veto, which can only keep a loss, and the evidence fields it writes stay on the record.

**D6. The halt is a fourth `verdict` on the `both_streams_silent` record, its seconds in a new key.** The record keeps every key it has and gains six, written on every record the new code decides: `halt_seconds` (the stream-window seconds, net of what a book record booked first — the same figure `residual_seconds` carries today — when the verdict is `venue_halt`, else 0.0), `streams_carried`, `windows_bracketed`, `trades_inside`, `trade_id_holes`, `quiet_seconds` (the shortest all-pairs quiet span around a window, 0.0 where a window has no print on one side in the hour). A `venue_halt` record's `residual_seconds` is 0.0. Not a state of its own: `_decided` and `_booked_dark` key on `both_streams_silent`, so the hour stays decided once and a healed hour still subtracts the halt's stream windows; and an image that predates the verdict reads the record as `undetermined` at 0.0 (`_totals`' unknown-verdict bucket, `:411-416`) — a rollback books nothing and pages nothing, where a state of its own would be re-decided by that image as `both_streams_silent` and page.

**D7. One new counter, `zcrypto_reconcile_venue_halt_seconds_total`, outside the residual counter; the two existing views keep their meaning.** `_totals` sums `halt_seconds` of `venue_halt` records into it and buckets none of their seconds into `dark_episode_seconds_total`, whose three labels go on partitioning the residual counter's `both_streams_silent` share. The residual counter's and the dark-episode series' help texts gain one clause each saying where a halt goes. No rule reads the new counter: a halt is not a fault. It is charted beside the verdict split on the integrity board's panel 206, which `tests/test_dashboards_cover_metrics.py` requires of every published family.

**D8. A halt's booking line is a WARNING; every other stays an ERROR; six fields are appended.** `Ops · ERROR logs` pages on an ERROR line of the unit, so an ERROR for a halt is the false page by another road. The line keeps its prefix — `both_streams_silent hour=… windows=… residual_s=… verdict=… updates=… snapshots=… divergent=…` — so a reader that greps for it reads it, with `residual_s=0.0` for a halt, and appends `halt_s=… carried=<n>/<streams> bracketed=<n>/<windows> trades_inside=<n> id_holes=<n> quiet_s=…`: why an hour was not a halt is on the line that booked it, but for an unreadable trades segment, whose WARNING the same cycle logs (`infra/runbooks/ops.md`'s residual-gap step 6 names it).

**D9. What was booked stays booked; hour 08 stays in the residual counter, and the hygiene map says it is complete.** The new code cannot re-decide an hour (`_decided`, `_ledger`'s `seen`), so every record written before the change reads and sums exactly as before, verdict-less ones as `undetermined`, and the totals stay consistent with them; the textfile carries the same residual it does today, and moves only on a new loss; a new halt moves only the halt counter. Hour 08's 5,432.534453 s stay in `zcrypto_reconcile_residual_gap_seconds_total`, as do the 2026-10-15, 2026-10-29 and 2026-10-30 08Z halts the rule holds on (8,469.908675 s, booked `venue_silent`): moving them needs a ledger correction the owner approves and costs a `resets()` blind spot of 24 h on the page (D16). The map, not the counter, is the answer to "was this hour ours?" (`infra/runbooks/ops.md`'s step 9), and it is re-trued for all four (D12).

**D10. The page keeps its expression; its comment and summary say a proven halt never reaches it.** `zcrypto-reconcile-residual-gap`'s `expr`, threshold, `for`, severity and uid are unchanged, so the push is an annotation upsert with no prune owed. Its summary keeps its triage line and gains one sentence naming the halt counter; a test pins that the summary names the counter and that the reconciler publishes it. `zcrypto-capture-all-streams-silent`'s summary, the first text an operator reads in a halt, calls every second of the silence permanent loss; its clause says instead that the silence is loss unless the reconciler later proves a halt, the rule's expression, threshold, `for`, severity and uid unchanged too, so its push is an annotation upsert with no prune owed as well.

**D11. The operator's pages say the same.** `infra/runbooks/ops.md`'s residual-gap section: *What it means* says what a proven halt is and books, step 6 reads the line's six new fields and names the WARNING an unreadable trades segment leaves, step 9's "which is where a hard halt lands" becomes the halt the mirrors could not prove; the source-lag section's no-witness bullet says a halt there books as loss too, proving one taking both hosts' records. `infra/runbooks/capture.md`: the venue-status section's step 2 ("A venue-side halt DOES book permanent loss") and the all-streams-silent section's *What it means* say a halt books as a halt when the mirrors prove it; the venue-status section's step 5 and the all-streams-silent section's step 5 say a capture host still reconnecting when the feed comes back, or both restarted in a halt's hour, takes the proof away; the recurrence section's step 1 and the all-streams-silent section's step 4 say to expect the reconciler's booking. The README's correlated-loss paragraph says it. The texts are *Runbook and alert texts*.

**D12. The hygiene map's row for 2026-11-17 08Z rides this branch, written as the complete hour it is; the map says what a halt hour is; the three earlier halts are re-trued in place.** The row is owed by step 9 whatever this change does, and its measurement is this spec's. A halt hour the reconciler books `venue_halt` takes no row: its content is KEEP, ranks 1–10 venue-verified across the silence but for the one residue *Failure modes* names, the panel's carried-forward rows there the venue's frozen book; the ledger's `venue_halt` records are the list; what a consumer owes a halt is market realism — the venue matched nothing, so a fill model places none inside one. The rows for 2026-10-15, 2026-10-29 and 2026-10-30 08Z call their hours unbackfillable and FLAG them; the rule holds on them (*The measured basis*), so their guidance cells read KEEP, as the 2026-11-17 08Z row does, and call the panel's `stale_seconds > 30` rows there the frozen book, their fabricated-row sentence dropped — the map's own rule ("record any revision here with the measurement that justifies it").

**D13. The settled-hour skip cache keeps `ALGO_VERSION = 1`.** Its comment asks a bump when anything that decides an hour's verdict changes (`cli/archive/scan_cache.py:65-69`), and the cache's verdict is whether an examination appends a record. This change alters a field of a `both_streams_silent` record decided on an hour's first examination, never whether one is appended, and a cached hour is one whose examination appended nothing, so no cached skip is wrong under the new code; a bump would buy one cold cycle and nothing else. The sampled audit stays the backstop.

**D14. Shipping: merge, then the ops converge, then the Grafana push.** The app change rides the ops image built from `develop` after the merge; the converge is the owner's (*Deployment*). The push carries `alerts.yaml`'s residual rule's comment and summary, the all-streams-silent rule's summary, and the integrity board's panel 206, and follows the converge: the panel's new query and the summary's sentence describe a series and a behaviour only the new image publishes, and the push's verification reads the new series by value (`zcrypto-grafana-push` Step 3), which is `(no series)` before the converge.

**D15. The decisions log carries the owner's two rulings and two of this spec's calls.** The booking of a dark episode is the subject `[iter-141]` logged in `docs/research/14.phase6-decisions.md`, so the `[00163]` entries go there: D1's ruling, D2's evidence, D6's ledger shape and D16's ruling.

**D16. The hours already booked stay booked; the hygiene map says each was a halt.** The owner's ruling, asked 2026-11-17T20:58:17.617Z, answered 20:59:43.800Z, verbatim: "Leave them (Recommended)". The question: hour 08 of 2026-11-17's 5,432.534453 s and the three earlier proven halts' 8,469.908675 s stay in `zcrypto_reconcile_residual_gap_seconds_total`, since the ledger is append-only. The options were leaving them, the hygiene map recording each hour complete; appending a note record per hour with no counter field; and correcting the records so the seconds leave the counter, which Prometheus reads as a reset. Taken: leave them, as D9 has it — the counter's lifetime level keeps 13,902.443128 s that were not loss, and the map explains each.

## Tests and guards

New cases in `tests/test_archive_settle.py` (`classify_halt`), `tests/test_archive_reconcile_command.py` (the booking, the counters, the line, the ledger's history) and `tests/test_infra_alert_rules.py` (the page); five existing cases change: the textfile's series set and the record's pinned key set gain the new names, that case's docstring scoping "never subtracts from residual" to the triage verdict, the dark-episode partition case's docstring scoping "books every second" to the seconds booked as residual, and two hand-built totals gain the new key; `tests/test_archive_reconcile.py`'s double-count banner gains one line on a halt. Each guard is proven by `infra/scripts/mutate-probe.sh` through its own `-k` selection, the control `1,$d` on the file named; every arm below read `KILLED` with the plan's code committed in a scratch worktree of the branch, `.tmp/r3fix/wt` at `fca07df6d`, whose code is `6795cd513`'s.

| Id | Guard | Case (`-k`) | File and mutation |
|---|---|---|---|
| 1a | A snapshot after the window takes a mirror out | `snapshot_from_the_window_on` | `cli/archive/settle.py`, `return any(all(kind == "update" for ts, kind in rows if ts >= first) for rows in both)` to `return True` |
| 1b | … from the window's own start | `at-the-windows-start` | `for ts, kind in rows if ts >= first)` to `… if ts > first)` |
| 1c | … and not before it | `snapshot_before_the_window` | `for ts, kind in rows if ts >= first)` to `for ts, kind in rows)` |
| 1d | A resume inside the hour's last 300 s takes it out | `resume_inside_the_hours_last_margin` | `at > hour_end - margin` to `at > hour_end` |
| 1e | … and one at exactly 300 s does not | `resume_inside_the_hours_last_margin` | `at > hour_end - margin` to `at >= hour_end - margin` |
| 1f | No resume in the hour takes it out | `running_to_the_hours_end` | `if at is None or at > hour_end - margin:` to `if at is not None and at > hour_end - margin:` |
| 1g | One mirror carries a stream | `one_mirror_carrying` | `return any(all(kind == "update"` to `return all(…` |
| 1h | A print inside a window is counted | `trade_inside_a_window` | `inside += sum(1 for ts, _ in tape for w in (stream_windows.get(pair) or windows) if w.start < ts < w.end)` to `inside += 0` |
| 1i | A skipped id is counted | `trade_id_neither_mirror` | `if after[0][1] - before[-1][1] == 1:` to `if True:` |
| 1j | The two tapes are one | `read_as_one` | `for rows in trade_rows[pair].values():` to `… list(trade_rows[pair].values())[:1]:` |
| 1k | Every window needs a straddling pair | `no_pair_brackets or every_window_needs` | `and self.windows_bracketed == self.windows` to `and True` |
| 1l | Every stream must be carried | `no_mirror_holds or snapshot_from_the_window_on` | `and self.streams_carried == self.streams` to `and True` |
| 1m | No stream, no halt | `no_stream_booked` | `self.streams > 0` to `True` |
| 1n | The positive case | `carried_through_a_window_no_pair_traded` | `bracketed.add(i)` to `pass` |
| 1o | Prints sharing a stamp order by id | `sharing_a_stamp` | the tape's `sorted(…)` to `sorted(…, key=lambda t: (t[0], -t[1]))` |
| 1p | A print inside a window refuses, beside a bracketing pair | `print_inside_a_window_refuses` | `and self.trades_inside == 0` to `and True` |
| 1q | A skipped id refuses, beside a bracketing pair | `skipped_id_refuses` | `and self.id_holes == 0` to `and True` |
| 1r | A stream needs both mirrors | `both_mirrors_resume_on_an_update` | `if len(both) < 2 or not own:` to `if not both or not own:` |
| 1s | … each coming back on an update, not a snapshot | `resumes-on-a-snapshot` | `if any(kind != "update" for ts, kind in rows if ts == at):` to `if False:` |
| 1t | … after every window, not only the first | `after-the-second` | `            for w in own:` to `            for w in own[:1]:` |
| 1u | … and not only the last | `after-the-first` | `            for w in own:` to `            for w in own[-1:]:` |
| 1v | … the primary held to it | `both_mirrors_resume_on_an_update and primary` | `        for rows in both:` to `        for rows in both[1:]:` |
| 1w | … and the secondary | `both_mirrors_resume_on_an_update and secondary` | `        for rows in both:` to `        for rows in both[:1]:` |
| 1x | A print inside a pair's own booked window, outside every fleet window, is counted | `own_booked_window` | `for w in (stream_windows.get(pair) or windows) if` to `for w in windows if` |
| 2a | A divergence keeps its verdict | `divergence_keeps` | `cli/archive/command.py`, ` and episode.verdict != CAPTURE_DIVERGENT else` to ` else` |
| 2b | A proven halt books as a halt | `venue_halt_books_its_seconds` | `verdict = VENUE_HALT if halt.holds and` to `… if False and` |
| 2c | An unproven one books as loss | `halt_shaped_window` | `verdict = VENUE_HALT if halt.holds and` to `… if True and` |
| 2d | A halt's residual is 0.0 | `venue_halt_books_its_seconds` | `residual_seconds=0.0 if halted else residual,` to `residual_seconds=residual,` |
| 2e | Its seconds are `halt_seconds` | `venue_halt_books_its_seconds` | `halt_seconds=residual if halted else 0.0,` to `halt_seconds=0.0,` |
| 2f | Its line is a WARNING | `venue_halt_books_its_seconds` | `(logger.warning if halted else logger.error)(` to `logger.error(` |
| 2g | The totals sum it | `totals_book_a_halt` | `totals["venue_halt_seconds"] += float(record.get("halt_seconds") or 0.0)` to `… += 0.0` |
| 2h | The tape is read | `venue_halt_books_its_seconds` | `_tape`'s `tape = list(zip(…))` to `tape = []` |
| 2j | An unreadable tape does not crash the cycle | `unreadable_trades_segment` | `_tape`'s `except (Exception, pl.exceptions.PanicException) as exc:  # noqa: BLE001 -- …` to `except ZeroDivisionError as exc:  # noqa: BLE001` |
| 2i | A decided hour is not re-decided | `booked_before_the_halt_verdict` | `if windows and not _decided("*", "book", hour, "both_streams_silent"):` to `if windows:` together with `_ledger`'s `if key in seen:` to `if False:` |
| 2k | An unreadable tape leaves the hour unproven | `unreadable_trades_segment` | ` and not unread and ` to ` and ` |
| 2l | A halt outranks `venue_silent` | `outranks_a_venue_silent` | ` and episode.verdict != CAPTURE_DIVERGENT else` to ` and episode.verdict not in (CAPTURE_DIVERGENT, "venue_silent") else` |
| 2m | A readable tape with a null or mistyped stamp or id leaves the hour unproven, never a crash | `proof_cannot_use` | `_tape`'s `            if any(frame[c].dtype != TRADE_SCHEMA[c] or frame[c].null_count() for c in ("ts", "trade_id")):` to `            if False:` |
| 2n | The heal subtracts a halt's stream windows | `subtracts_a_venue_halts` | `if record.get("state") != "both_streams_silent" or record.get("hour") != stamp:` to `… or record.get("verdict") == "venue_halt":` |
| 2o | A market quiet shorter than a halt's refuses it, every other proof holding | `quiet_too_brief` | `cli/archive/settle.py`, `and self.quiet_seconds >= QUIET_SPAN_SECONDS` to `and True` |
| 2p | A stamp out of Python's range leaves the hour unproven, never a crash | `a-stamp-out-of-range` | `cli/archive/command.py`, 2j's mutation |
| 2q | … and so does a stamp polars panics on converting | `a-stamp-polars-panics-on` | `cli/archive/command.py`, `except (Exception, pl.exceptions.PanicException) as exc:` to `except Exception as exc:` |
| 3a | The page names the halt counter | `names_the_halt_counter` | `infra/grafana/alerts.yaml`, `it books to zcrypto_reconcile_venue_halt_seconds_total, which pages nothing` to `it books elsewhere, which pages nothing` |
| 3b | … which the reconciler publishes | `names_the_halt_counter` | `cli/archive/command.py`, the `_emit`'s `"venue_halt_seconds_total",` to `"venue_halt_total",` |

Arm 2i read `SURVIVED` with the `_decided` mutation alone: `_ledger`'s `seen` refuses the second append on its own, so the two guards are probed together. Red readings, each task's test file on the tree before that task: Task 1's reads `ImportError: cannot import name 'RESUME_MARGIN_SECONDS'`; Task 2's twenty-four new and behaviour-changed cases read `21 failed, 3 passed`, the three that pass being the hand-built totals, which an extra key does not break, and the heal's subtraction of a halt's stream windows, which holds before the change too; Task 3's case reads `1 failed`.

## Change list

- `cli/archive/settle.py`: `VENUE_HALT`, `RESUME_MARGIN_SECONDS`, `QUIET_SPAN_SECONDS`, `HaltEvidence`, `classify_halt`; the module docstring's and `fleet_dark_windows`' "the data is gone" and "it is loss" re-trued; `EpisodeVerdict`'s docstring, its verdict a veto on a halt.
- `cli/archive/command.py`: the imports; `_MINT_FAMILY`'s and `_booked_dark`'s comments; `_totals`' `venue_halt_seconds`; the residual, dark-episode and new `venue_halt_seconds_total` emits; `_tape`, its null and dtype test and its conversion inside its `try`; the booking block's `book_rows`, `classify_halt`, the unread-tape veto, verdict, line and record.
- `cli/archive/reconcile.py`: `overlap_seconds`' docstring, one line on a halt.
- `infra/grafana/data-integrity-dashboard.json`: panel 206's description and a fourth target.
- `infra/grafana/alerts.yaml`: `zcrypto-reconcile-residual-gap`'s comment and summary; `zcrypto-capture-all-streams-silent`'s summary clause.
- `tests/test_archive_settle.py`, `tests/test_archive_reconcile_command.py`, `tests/test_infra_alert_rules.py`: the cases above; `tests/test_archive_reconcile.py`: the double-count banner, one line.
- `infra/runbooks/ops.md`, `infra/runbooks/capture.md`, `README.md`: *Runbook and alert texts*.
- `docs/reference/capture-era-data-hygiene-map.md`: the 2026-11-17 08Z row, the halt paragraph, three guidance cells.
- `docs/research/14.phase6-decisions.md`: the `[00163]` entries.

## Runbook and alert texts

Each text replaces the line or clause named, byte for byte; each went through the repository's hooks — `mdformat`, `guidance-guard`, `yamllint` among them — in the scratch worktree, and `tests/test_internal_terms_not_operator_visible.py` read `1113 passed` over them.

`infra/grafana/alerts.yaml`, `zcrypto-reconcile-residual-gap`, the comment's first paragraph's last line, `      # for, hence \`> 0\` rather than a tolerance.`, reads as the two lines below:

```yaml
      # for, hence `> 0` rather than a tolerance. A venue halt the mirrors prove lost nothing books to
      # zcrypto_reconcile_venue_halt_seconds_total instead, which no rule reads: it is not loss.
```

and the summary's opening, from `Permanent L2 loss:` to `a venue outage lands here exactly like a capture failure.`, reads:

```
Permanent L2 loss: silence NEITHER capture host covered -- unhealable, the data is gone. A venue halt the reconciler proves lost nothing -- every book stream came back on both capture hosts with no reconnect, on one with no resync, no pair traded across it, and no pair printed for at least four minutes around it -- never lands here: it books to zcrypto_reconcile_venue_halt_seconds_total, which pages nothing. Any other venue outage lands here exactly like a capture failure: the counter books ABSENCE of data, not fault.
```

the rest of the summary, from ` TRIAGE FIRST` to the runbook link, unchanged.

`infra/runbooks/ops.md`, the residual-gap section's *What it means*, the paragraph opening `**The counter books the ABSENCE of data, never fault attribution.**`:

```markdown
**The counter books the ABSENCE of data, never fault attribution, and a venue halt the mirrors prove lost nothing does not reach it.** It is derived by summing an append-only ledger and is monotonic, so whatever it books is permanent — there is no later correction path short of a deliberate, approved ledger edit. When Kraken halts its books the feed goes quiet because nothing changes, and the reconciler proves that from the two mirrors: every book stream came back after the silence on both capture hosts on an update, not a reconnect's snapshot, and on at least one with no resync snapshot after it to the hour's end, so capture's live checksum accepted the book it carried through; each resume came at least five minutes before the hour's end; no trade lands inside the silence; each window is straddled by a pair whose trade ids step by exactly one across it, with no pair's ids skipping; and no pair printed for at least four minutes around each window, since inside a shorter quiet, the market's own, a writer that dropped every pair's rows on both hosts would read the same. Such an hour's `both_streams_silent` record reads `verdict` `venue_halt`, `residual_seconds` 0.0 and its seconds in `halt_seconds`, and books to `zcrypto_reconcile_venue_halt_seconds_total`, which pages nothing. Any other venue outage — a host missing the hour or coming back on a reconnect, a reconnect or resync on both hosts later in the hour, a trade or a missing trade id across the silence, a resume inside the hour's last five minutes, a window no pair's trades straddle (a halt across an hour boundary among them), a market quiet shorter than four minutes around a window, an unreadable trades segment, a divergence between the mirrors on a two-window episode — lands here exactly the same way a capture failure does: both leave no book data on either host for the window, and the counter cannot on its own tell the two apart. Reading this page as "we lost data" is correct; reading it as "our capture broke" is not, and the discriminator below exists precisely to stop that leap.
```

Step 6, the item opening `6. **Read the \`verdict\` on the hour's \`both_streams_silent\` ledger record**`:

```markdown
6. **Read the `verdict` on the hour's `both_streams_silent` ledger record** — TRIAGE FIRST, before chasing the fleet. **A record carrying no `verdict` key at all reads `undetermined`, not a failed read**: every record booked before the discriminator shipped carries no field, and the exporter folds those into `undetermined` deliberately. The reconciler also logs the whole answer as it books — `archive reconcile: both_streams_silent hour=… windows=… residual_s=… verdict=… updates=… snapshots=… divergent=… halt_s=… carried=…/… bracketed=…/… trades_inside=… id_holes=… quiet_s=…` — which is the fastest read. Check `windows=` first: on anything but 2, `classify_dark_episode` (`cli/archive/settle.py`) refused before weighing anything: `verdict=` reads `undetermined`, and `updates=`, `snapshots=` and `divergent=` are that refusal's zero or `-`, not evidence. The last five fields say why the hour did not book as a venue halt: `carried=` short of its stream count is a stream a host holds no record of or came back to on a reconnect, one every host resynced or reconnected after, or one that resumed too late in the hour; `bracketed=` short of the window count is a window no pair's trades straddle; `trades_inside=` or `id_holes=` above 0 is the venue trading across the silence; `quiet_s=` under 240 is a market quiet too short to tell a halt from a writer that dropped every pair's rows on both hosts (0.0 where a window has no print on one side in the hour, which a short `bracketed=` also shows). With all five clean, `verdict=capture_divergent` (step 8) or an `archive reconcile: unreadable … trades segment` WARNING for the hour is why: a divergence keeps its loss, and a trades file the reconciler cannot read leaves the hour unproven. A `venue_halt` record does not reach this page: its line is a WARNING reading `residual_s=0.0`, its seconds in `halt_s=`. `zcrypto_reconcile_dark_episode_seconds_total` answers from Prometheus, but it is cumulative over the whole ledger: read the **step** across the `:12`/`:42` tick that booked your hour, never its level (no count command: the ledger and the read live on the ops host; `classify_dark_episode` returns the zeros).
```

Step 9, its clause `no evidence either way from the cross-host comparison, which is where a hard halt lands, since a venue emitting *nothing* leaves no interior messages for the two hosts to agree on.`:

```markdown
no evidence either way from the cross-host comparison, which is where a hard halt the mirrors could not prove lands — step 6 says which proof failed — since a venue emitting *nothing* leaves no interior messages for the two hosts to agree on.
```

The source-lag section's no-witness bullet, its clause ``books as `both_streams_silent` — permanent, paged, never revisited``:

```markdown
books as `both_streams_silent` — permanent, paged, never revisited, a venue halt included, since proving a halt takes both hosts' records
```

`infra/runbooks/capture.md`, the venue-status section's step 2, the item opening `2. **A venue-side halt DOES book permanent loss.`:

```markdown
2. **A venue-side halt books as a halt when the mirrors prove the book carried through, and as permanent loss when they cannot. Expect the reconciler's booking hours later.** The reconciler books it as `both_streams_silent` against the halt's hour. When every book stream came back on both capture hosts without a reconnect, on at least one with no resync after the silence, no pair traded across it, and no pair printed for at least four minutes around it, the record reads `verdict` `venue_halt` and its seconds book to `zcrypto_reconcile_venue_halt_seconds_total`, which pages nothing: the venue sent nothing because nothing changed, and the hour is complete. Otherwise — a host missing the hour or coming back on a reconnect, a reconnect or resync on both hosts later in the hour, a trade or a missing trade id across the silence, a resume inside the hour's last five minutes, a window no pair's trades straddle (a halt across an hour boundary among them), a market quiet shorter than four minutes around a window, an unreadable trades segment, a divergence between the mirrors on a two-window episode — it books as loss and `zcrypto-reconcile-residual-gap` pages; that rule carries `for: 0s`, so it transitions within a scrape of the booking while the notification lands later. Read the booking's own log line rather than waiting on the page: `archive reconcile: both_streams_silent hour=… windows=… residual_s=… verdict=… … halt_s=…`, in the reconciler's journal on `zcrypto-ops` (needs `sudo`) or via Loki, at WARNING for a halt and ERROR for loss. `residual_s`, or `halt_s` for a halt, is the booked seconds summed across streams; divide by the stream count for the per-stream figure an incident record quotes. Do not close the incident before the reconciler has spoken (no count command: the verdict lands on the ops host's ledger record, read from the hour's two mirrors).
```

Step 5, the item opening `5. **Do not converge or restart anything on this signal alone.**`:

```markdown
5. **Do not converge or restart anything on this signal alone.** Nothing in the capture path reacts to venue status, and a restart costs a resubscribe whose snapshot takes that host out of the reconciler's proof that a halt lost nothing: a host still reconnecting when the feed comes back, or both restarted in the halt's hour, books it as loss. A feed that heals itself costs nothing when the mirrors prove the halt, and unbackfillable L2 on every pair when they cannot (no count command: a venue halt's reach is the venue's behaviour), which the loss page reports about two hours later.
```

The recurrence section's step 1, its clause `read the state and its ladder, expect the loss page hours later,`:

```markdown
read the state and its ladder, expect the reconciler's booking hours later,
```

The all-streams-silent section's *What it means*, the paragraph opening `It is nonetheless a **true positive, not noise**.`:

```markdown
It is nonetheless a **true positive, not noise**: the feed did stop. Whether it cost data is the reconciler's answer, about two hours later — a halt the mirrors prove lost nothing books as a halt and pages nothing, and one they cannot books as loss and pages; the venue-status section's step 2 has the test.
```

Its step 4's bold opening `4. **Expect the loss page, and do not pre-empt it.**`, the rest of the item unchanged:

```markdown
4. **Expect the reconciler's booking, and do not pre-empt it.**
```

Its step 5, the item opening `5. **Do not converge or restart on this signal alone.**`:

```markdown
5. **Do not converge or restart on this signal alone.** Nothing in the capture path reacts to venue status, and a restart costs a resubscribe whose snapshot takes that host out of the reconciler's proof that a halt lost nothing: a host still reconnecting when the feed comes back, or both restarted in the halt's hour, books it as loss.
```

`README.md`, the paragraph opening `Two **correlated-loss** detectors run regardless of the flag and never mint:`:

```markdown
Two **correlated-loss** detectors run regardless of the flag and never mint: `both_streams_silent` (every pair silent on *both* hosts in the *same* window) and `total_loss` (an hour absent from both mirrors while real data brackets it on either side). When both streams are dark there is no witness to heal with, so the silence is ledgered, booked into `zcrypto_reconcile_residual_gap_seconds_total` as permanent loss, and paged — unless the two mirrors prove a `both_streams_silent` hour a venue halt that lost nothing: every book stream came back on both hosts without a reconnect, on at least one with no resync snapshot after the silence, no pair traded across it, and no pair printed for at least four minutes around it. That hour books to `zcrypto_reconcile_venue_halt_seconds_total` instead and pages nothing.
```

`docs/reference/capture-era-data-hygiene-map.md`: the row below directly after the 2026-10-30 08Z row, the paragraph below directly before the one opening `**The completeness instrument is \`continuity.py\``, followed by one blank line; and in the rows opening `| **2026-10-15 07:01:02.993780 → 07:05:08.324270**`, `| **2026-10-29 08:01:07.96 → 08:07:52.93**` and `| **2026-10-30 08:01:03.87 → 08:06:21.06**`, the sentence `FLAG for continuity-sensitive analyses over any window containing <the row's date>; unbackfillable, and no re-investigation is owed — the gap is explained.` reads as the third block, and the sentence opening ` The L2 panel's fabricated-row density for this hour is **not recorded here**`, through its `do not read its absence from this row as zero.`, is dropped with its leading space.

```markdown
| **2026-11-17 08:01:04.649345 → 08:10:18.021279** — Kraken venue halt, complete | A venue-side halt, not a capture defect and not a loss, and **Kraken announced it**: posted as "Kraken Website and API Maintenance" `08:01 → 08:16Z` at 08:49:37.100Z on 2026-11-16, and both capture hosts' `status` ladder read `maintenance` 08:01:05.64Z → `cancel_only` 08:06:27.20Z → `post_only` 08:08:17.52Z → `maintenance` 08:08:57.40Z → `post_only` 08:09:43.97Z → `online` 08:10:21.75Z, as the ops journal's entry for the day records it. The header is the **fleet data-gap span** (widest `stream_windows` extent in the ledger record): `08:01:04.649345` (SOL/BTC) → `08:10:18.021279` (SOL/BTC). The fleet-dark intersection is three windows, `08:01:05.624052 → 08:06:27.187670` (321.563618 s), `08:06:28.474026 → 08:07:21.840157` (53.366131 s) and `08:08:57.384088 → 08:10:00.183500` (62.799412 s); the second ends at a burst of 23–62 messages each pair carries under one Kraken stamp, 08:07:21.840 to 08:07:54.315. **The hour is complete at depth 100**: the primary's hour-08 updates, replayed through `cli/capture/book.py`'s `OrderBook` from the L2 panel's hour-07 state, equal the snapshot Kraken sent the secondary at its 08:12:18Z reconnect at all 200 levels on 12 of 12 pairs, and dropping the burst breaks the match on 12 of 12 by 35–159 levels. The primary holds no snapshot row in the hour, no trade lands inside a window on either host, and 7 pairs' trade ids step by exactly one across all three. Booked at the 10:12Z tick (`at` `10:12:42.617497Z`) as **5,432.534453 s** of `both_streams_silent` across 12 streams (439.580915 s DOGE/EUR to 477.31857 s LTC/EUR), verdict **`undetermined`** on the window COUNT, three windows: that was before the reconciler's halt rule, and the seconds stay in the append-only residual counter. The rule, run over the same mirrors, books the hour `venue_halt`: 12 of 12 streams carried, 3 of 3 windows straddled, no trade inside, no id hole, and no pair printing for 557.017323 s around the three windows (08:01:04 → 08:10:21). | KEEP. The silence is the venue's frozen book, not missing data, and the L2 panel's `stale_seconds > 30` rows in these windows are that frozen book, not fabrication. The venue matched nothing from `maintenance` to `online`, so a fill model places no fill inside the windows. |
```

```markdown
**A venue halt is not loss.** When Kraken halts its books — the `status` ladder `maintenance` → `cancel_only` → `post_only` → `online` — the feed goes quiet because nothing changes. Since the reconciler's halt rule, an hour whose two mirrors prove that — every book stream came back after the silence on both capture hosts without a reconnect, on at least one with no resync snapshot after it to the hour's end, each resume at least five minutes before the hour's end, no trade inside the silence, each window straddled by a pair whose trade ids step by exactly one, with no pair's ids skipping, and no pair printing for at least four minutes around each window — books as `verdict` `venue_halt` to `zcrypto_reconcile_venue_halt_seconds_total`, never as loss, and takes **no row here**: its content is KEEP, ranks 1–10 venue-verified across the silence as everywhere else, and the panel's `stale_seconds > 30` rows inside it are the venue's frozen book. The rule cannot tell one fault from a halt: a capture writer on the image both hosts run dropping every pair's rows on both inside a market quiet of four minutes or more; the archive from 2026-07-14 on shows no such quiet outside the reconciler's dark hours, its longest 108.4 s. The ops host's `reconcile-ledger.jsonl` is the list of such hours, its `venue_halt` records. What a consumer owes a halt is market realism, not hygiene: the venue matched nothing in it, so a fill model places no fill inside one. A halt the mirrors cannot prove still books as loss and takes its row by `infra/runbooks/ops.md`'s residual-gap step 9, whose step 6 reads which proof failed from the booking line. The other venue-outage rows above were written before the rule and call their hours unbackfillable; the rule, run over the mirrors, holds on 2026-10-15, 2026-10-29, 2026-10-30 08Z and 2026-11-17 08Z, whose rows say so, and on none of the other dark hours the ledger holds.
```

```markdown
KEEP. The gap is the venue's frozen book, not missing data: the reconciler's halt rule, run over this hour's mirrors, holds — 12 of 12 streams carried across both windows with no resync, both windows straddled by adjacent trade ids, no trade inside, and no pair printing for over 300 s around them — so ranks 1–10 are venue-verified across it as everywhere else, and the L2 panel's `stale_seconds > 30` rows in these windows are that frozen book, not fabrication. It stays booked in the append-only residual counter, and no re-investigation is owed.
```

`infra/grafana/alerts.yaml`, `zcrypto-capture-all-streams-silent`'s summary, the clause from `L2 is unbackfillable and every` through the next line's `second here is permanent loss.`, the line break and indent between them included, reads as the one line below, appended last so no earlier block's index moves:

```
L2 is unbackfillable, and every second here is permanent loss unless the reconciler later proves it a venue halt that lost nothing, which books as a halt and pages nothing.
```

## Deployment

The merge ships no behaviour: the reconciler runs the image `ops_image_digest` pins until an ops converge re-pins it, and the texts land at the merge, the runbook's halt sentences describing an image not yet running — the old image books a halt as loss and pages, which the page's own triage still reads correctly. The converge is the owner's hands, by `.claude/skills/zcrypto-rollout-image/SKILL.md`'s *Ops converges* and *Converge mechanics*: the ops image built from `develop` at or after the merge, pulled on the host; the running digest recorded in `docs/reference/fleet-pins.md` first, as the rollback operand; `-e liquidations_decision=roll-after`; Kraken's `scheduled-maintenances.json` read whole at planning and again immediately before, `zcrypto-ops` being venue-facing (`.claude/rules/fleet-deploys.md`); `infra/ansible/scripts/converge.sh` with `--limit zcrypto-ops`, never under `timeout`; the pins row re-trued from the deploy-log line. Readers-before-writer is not owed: the ledger's one reader is the process that writes it. No Alloy change is owed (*Operating model*).

What the converge carries, verified by value after the next `:12`/`:42` tick: `infra/scripts/ops-postverify.sh`, every check; and the new family's first scrape, `uv run python infra/scripts/grafana-query.py 'zcrypto_reconcile_venue_halt_seconds_total{host="ops"}'` reading `0` — `(no series)` is a fail. Then the Grafana push from `develop` (D14), by `zcrypto-grafana-push`: the residual rule's comment and summary and the all-streams-silent rule's summary, annotation upserts under their own uids, no prune; panel 206's description and fourth target; Step 3 reads each changed rule's first sample and the panel's new query by value. The first halt after the converge is the change's first real proof: its line a WARNING with `verdict=venue_halt`, `zcrypto_reconcile_venue_halt_seconds_total` stepping by its `halt_s`, the residual counter flat, no page.

Rollback is the re-converge to the recorded digest: the older image reads each `venue_halt` record as `undetermined` at 0.0 (D6), so the residual counter does not move, and `zcrypto_reconcile_venue_halt_seconds_total` stops publishing, its panel line ending.

## Failure modes

- **A resync whose snapshot never lands.** The ladder's every rung writes a snapshot; a pair Kraken never answers a subscribe for stays desynced with none, and on that host its rows still read carried. It needs the venue to have changed the book inside the silence unseen by both hosts, the other host to resync, and no print across the window; `zcrypto-capture-book-desync-stuck` pages the stuck pair on its own.
- **A writer that dropped rows while reading on.** The checksum stays whole on that host. On one host alone the book proof refuses it: the window is fleet-dark only if the other host recorded nothing either, and the other host must hold the hour and come back on an update — so either it was connected and heard nothing, the venue sending nothing and the dropped writes losing nothing, or it failed inside the same window too (D3). On both hosts at once — one fault of a capture image both hosts run, dropping every pair's rows on each — the book proof passes; the trade proof refuses it whenever any pair printed inside its own booked silence or skipped an id across a window, the quiet proof whenever the last print before a window and the first after it, on any pairs, lie less than 240 s apart, and `zcrypto-capture-watermark-breached` pages a watermark breach on its own. The residue is that one fault inside a natural all-pairs quiet of 240 s or more, some pair still straddling each window with adjacent ids: it books as a halt and pages nothing, and the archive from 2026-07-14 on shows no all-pairs quiet that long outside the ledger's dark hours, its longest 108.4 s (*The measured basis*).
- **A change below rank 10 in the silence.** Kraken's checksum covers ranks 1–10, so a level deeper than that changed unseen passes; the archive carries the same caveat for every hour (the hygiene map's ranks > 10 row), and 2026-11-17 08Z's full-depth replay is the one measurement that closes it for an hour.
- **A halt that straddles an hour boundary.** The hour whose window runs to its end has no resume and books as loss; the next hour's window opens at that hour's start, so no print of that hour precedes it, no pair straddles it, and it books as loss too. Both page, as today; the map's step-9 row is owed for each.
- **An unreadable trades segment**, or one holding a null, mistyped or unconvertible `ts` or `trade_id`. One WARNING per file, and the hour books as loss and pages whatever the file's twin or the other pairs' ids show (D4); the trades heal path fails the hour on that file only where it reads it.
- **Two mirrors whose interiors diverge in a halt.** On a two-window episode, `capture_divergent`, booked and paged as today (D5); on any other count the triage compares no interior, as on develop, and no divergence vetoes a halt the three proofs hold.
- **An image without the verdict reading a `venue_halt` record.** `undetermined` at 0.0, nothing booked, nothing paged (D6).

## Open questions for the owner

None open: the one the code could not settle, the hours already booked, is D16, on the owner's ruling.

## Out of scope

- The ladder in the archive, or any venue status read by the reconciler (D2): dropped, the evidence class the ruling asks for is the data's, and an archived frame would be stamped at local receipt.
- Re-booking any hour already decided (D9): dropped on the owner's ruling, D16.
- A horizon after the resume in place of the hour's end (D3): dropped, a knob with a cliff 120.3–138.3 s from the one real case.
- A halt straddling an hour boundary proven across both hours (*Failure modes*): dropped; it needs the neighbouring hours' files on every dark hour, and the one recorded straddle, 2026-10-30 02Z–03Z, reconnected on both hosts in its second hour, so no proof was there to read.
- `continuity.py`'s exit bar: spec 00096's *Out of scope* stands.
- The panel's `stale_seconds` accounting inside a halt: unchanged; the map says what those rows are (D12).
