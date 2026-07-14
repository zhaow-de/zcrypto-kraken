# Role C — redundant L2/trade capture + dual-source reconciliation (design, spec 00050)

**Spec:** `00050` · **Increment:** 3 of 3 of the three-tier topology (spec `00048`, Role C) · **Supersedes:** 00048's Role C sketch of a NAS-local capture container (see Context). · **Status:** final — cross-validation findings resolved (summarized in the introducing PR); incorporates the 2026-07-14 state update (PR #122 image live on the primary).

## Goal

Stand up a **second, independent L2/trade capture host** and an hourly **reconciliation** step so that a primary outage (host crash, network blip, Linode maintenance, the 21:25 UTC reboot window) no longer punches a permanent hole in the unbackfillable L2 archive. Reconciliation heals the canonical archive by **whole-window book gap-splice** and **trade-id union**, provenance-tagged and auditable. The failure drill that proves it also discharges T0003's outstanding **alerting-drill** exit-bar item.

## Context & what changed since 00048

00048 sketched Role C as "the NAS runs a second `zcrypto capture` container". Two facts have shifted since (decided 2026-07-13, recorded in T0033):

- Capture is cheap — measured **~102 MiB RAM, ≲41 % of one core** at peak, **0.48 GB/day** for 10 pairs (book depth-100 + trades) — so it fits a **$12/mo Linode 2 GB**, already provisioned: `zcrypto-red.zhaow.me` (Amsterdam, 1 vCPU / 2 GB / 50 GB), reboot window **22:25 UTC** vs the primary's 21:25 UTC (slots measured + criteria-derived, 2026-07-14 — see `.claude/rules/capture-deploys.md`).
- The home **ops node** (`z-home-zcrypto.zhaow.pro`, 24 threads / 61 GB / 3.4 TB NVMe / AVX2) is provisioned but deliberately **not** a Role C dependency (T0033: "a capability upgrade, not a blocker") — it appears here only as the on-demand home for CRC replay QA.

The capture writer was hardened (T0036/T0037: restart-safe, crash-safe, corroborated rotation; `<HH>.parquet` on disk always means "committed and complete") **and the hardened image is already live on the primary**: as of 2026-07-14 04:00 UTC it runs digest `sha256:63708539c3f9683608b0d5ad396ea213717d6a38c0291233bbf0d5af220b3676` (PR #122 — T0008 depth-prune, T0032 withheld-ping + gap booking, T0036 crash-safe writer, T0037 rotation quorum + intra-hour trade dedup, T0035 reconnect fixes; 1 s deploy downtime, post-deploy checks green, desyncs 0). **This design changes zero lines of `cli/capture/`** — the secondary runs that identical deployed digest, and all new code is archive-side.

## Hard empirical constraints (measured on this project's data — violating them is silent corruption)

1. **Kraken coalesces book updates per WebSocket connection.** Two healthy hosts record *different* message streams for the same pair (different counts, both 100 % CRC-valid). Cross-host row-diffing of book streams measures coalescing, not loss; **interleaving rows from two book streams corrupts the book**. Book redundancy therefore operates only at **whole-window granularity**: on a primary gap, splice the secondary's complete window as a block — never mix rows within a window.
2. **Trades are safe to union**: `trade_id` is globally unique and identical across hosts, so trade streams can be unioned/deduped row-level.
3. **Book segments are self-verifying by CRC replay**: replaying stored rows through the book with wire-precision formatting reproduces Kraken's CRC32 checksums (top-10 levels). Cost ~80 s per busy pair-hour on an old Xeon — 34–68 min per hour-of-data on the NAS's Atom (infeasible hourly there), cheap on the ops node.
4. **L2 is unbackfillable, and desyncs split into two subclasses.** The *deterministic* subclass — a message every host's book mishandles — is host-correlated (T0008's three hosts diverged at the identical microsecond) and no second host helps: a gap both hosts share is permanent. But a desync from *genuine per-connection message loss* is host-**local** (loss cannot be microsecond-synchronised across independent connections — T0008's own proof logic), and so is a pair stuck desynced after a failed one-shot resubscribe (T0008's open remainder): both present as a silent stream on **one** host — exactly the outage shape the splice covers, which materially de-risks T0008's parked stuck-pair item. A second host therefore protects against host/network/maintenance outages **and host-local desyncs**; correlated events and dual outages remain permanent (T0008 owns recovery robustness).

A useful corollary of (1)+(3): two CRC-valid books are different *sequences* but the **same state** — every update carries an absolute quantity, so applying one stream's next message onto the other stream's current book yields the true book again (exactly for the CRC-attested top-10; assumed for levels 11–100, the honest limit noted in T0033). This is what makes a block splice replayable across its boundaries, and it is empirically checkable (see Verification).

## Decisions

### D1 — Where the second capture stream runs

1. **NAS container** (00048's original sketch) — no new host cost; but the NAS's downtime is the home-ISP outage (≤ 14 h, ~2×/yr), it adds a 24×7 writer to the archive volume it must also verify, DSM's bespoke no-systemd glue grows, and the Atom is the fleet's weakest CPU.
2. **Second Linode (2 GB, Amsterdam)** — datacenter network quality, a different region and a different maintenance/reboot window than the primary, managed by the *existing* ansible roles unchanged, capture-only attack surface (no keys). Cost $12/mo. Residual: same provider as the primary (accepted; see Risks).
3. **Home ops node** — free capacity, but it shares the home-ISP failure domain with the NAS (the archive tier), and T0033's charter keeps it out of sole custody of durability paths until its storage topology is decided.

**Recommendation: 2** (validated — the host is already provisioned per the owner's decision; this block records why). Confidence: high.

### D2 — How the secondary's data reaches the NAS

1. **Second Role A pull source** — the NAS pulls `zcrypto-red` exactly as it pulls the primary: an `rrsync -ro` forced-command channel on the secondary's `deploy` user, keyed by a **new** vaulted ed25519 keypair (`sync_capture_red` — per-channel least privilege, the established posture), hash-verified per segment, mirrored to `/archive/capture-segments-red`.
2. **Secondary pushes to the NAS** — requires inbound access to the NAS; violates its egress-only posture. Rejected.
3. **Daisy-chain via the primary** (NAS pulls both trees from the primary) — makes the primary a single point of failure for the *redundant* stream's durability, the exact coupling Role C exists to remove. Rejected.

**Recommendation: 1.** Confidence: high. The pinned `known_hosts` gains the secondary's host key; `pull-entrypoint.sh` and `compose.yaml` gain `CAPTURE_RED_SOURCE` / `CAPTURE_RED_DEST` / `CAPTURE_RED_SSH_KEY` mirroring the existing per-source pattern.

### D3 — Where and when reconciliation runs

1. **NAS, in the hourly pull loop** (after both pulls) — the data is already local; every reconcile operation is Atom-cheap: an hour-timestamp continuity scan, a polars anti-join on `trade_id`, and block concatenation. No CRC replay in the loop (constraint 3).
2. **Ops node** — buys CRC replay in-line, but drags a just-provisioned box into the durability path, pre-empting T0033's parked storage-topology decision (its NFS-vs-NVMe question changes how it would even read the archive).
3. **Primary VPS** — the production node would have to consume the secondary's data, and the reconciler must outlive precisely the host whose failure it heals. Rejected.

**Recommendation: 1**, with CRC replay of spliced windows earmarked to the **ops node as an on-demand, non-gating QA step** (a T0033 first workload, run attended after each drill/real splice). Confidence: high.

### D4 — Book splice granularity

1. **Hour-file substitution** — any canonical hour intersecting a primary gap is replaced wholesale by the secondary's hour file. Dead simple (a file copy + its manifest), but it discards the primary's post-reconnect snapshot anchor mid-hour, imports any unrelated blemish the secondary's hour has elsewhere, and flags a whole hour as secondary-sourced when only ~83 s were missing.
2. **Gap-window block splice** — mint the hour as ordered blocks: primary rows `ts ≤ t1`, secondary rows `t1 < ts < t2`, primary rows `ts ≥ t2`, where `[t1, t2]` is the primary's silence window. Exact coverage; the exit boundary `t2` is the primary's reconnect **snapshot** (a true re-anchor); a secondary with its own unrelated gap elsewhere in the hour still heals this one (only the window must be clean). Cost: row surgery — but block-wise concatenation only, never interleave, never sort (the `_write_merging` rule: L2 rows are order-sensitive).
3. Both, chosen per case — two code paths for one job. Rejected.

**Recommendation: 2.** Confidence: medium-high — option 1 is simpler but has a real correctness wart (it can *introduce* a secondary-side gap while healing a primary one, muddying residual-gap accounting); option 2 has one crisp rule that covers every gap topology, including a wholly-missing primary hour (the splice degenerates to one full-secondary block) and a gap spanning an hour boundary (each hour minted independently with its intersection of the window).

### D5 — Trade reconciliation trigger and shape

1. **Always union** — mint a union hour for every hour. Uniform, but it copies the whole trade archive into the overlay, doubles manifest/provenance churn, and buries the signal (which hours actually differed).
2. **Deficit-triggered union** — every cycle, anti-join secondary vs primary on `trade_id` per settled hour (Atom-cheap). Primary missing trade_ids → mint the union hour (all primary rows + the missing secondary rows, ordered by `trade_id` — per-pair monotone, so time-ordered and deterministic). Secondary-only deficits are a QA metric, not a mint. A `trade_id` present on both with differing fields (should be impossible) keeps the primary row and raises a QA alert.
3. Union only when a *book* gap was detected — misses trade-only asymmetries (T0026-class reconnect-replay windows, which the hardened writer now drops as late events on the primary but the secondary may have captured live). Rejected.

**Recommendation: 2.** Confidence: high. The anti-join doubles as 00048's "cross-validation bonus": a persistent nonzero diff in either direction on healthy hours flags a capture bug.

### D6 — The canonical read surface

1. **Full canonical copy** (reconcile every hour into a third tree) — doubles storage and the verify sweep for a tree that is 99.9 % byte-identical to the primary mirror. Rejected.
2. **Overlay** — the primary mirror stays canonical-by-default; the reconciler writes **only healed hours** to `/archive/capture-reconciled/` (same `<PAIR>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet` layout) plus an append-only ledger; a reader helper resolves reconciled-first, primary-final otherwise.
3. **In-place fix-up of the primary mirror** — violates 00048's invariant (raw streams are never overwritten in place) and destroys auditability. Rejected.

**Recommendation: 2**, with a small `cli/archive/reader.py` helper (`canonical_segments(...)`) that yields per-hour canonical paths using a **strict final-name match** (`<HH>.parquet`, two digits) — which also makes T0038's stale-part double-count structurally impossible for consumers who use it (T0014 spread calibration is the first). Confidence: high.

### D7 — Retention of redundant secondary hours on the NAS (the common case: both hosts have the hour)

1. **Discard after reconcile confirms the primary hour clean** — minimal storage, but forfeits the one thing the redundant stream is uniquely good for late: recovering from a *latent* primary-stream defect discovered after the fact (T0036 was found 5 days after it began destroying data).
2. **Rolling window (~90 days)** — a middle ground that still amputates the recovery option at an arbitrary age.
3. **Keep indefinitely** — both mirrors together grow ~0.96 GB/day (~350 GB/yr) on a 27 TB volume; the only real cost is the hourly verify sweep, whose wall (T0028) sits years out at the *measured* rate (T0028's "~1–2 months" estimate was derived from the discredited ~10 GB/day figure — correct its `ripe_when` at closeout).

**Recommendation: 3** — simplest rule, negligible cost, preserves late-discovery recovery. Confidence: high.

### D8 — Capture-host segment retention (the secondary's 50 GB disk forces the question)

1. **Prune the secondary only** — solves the immediate 50 GB constraint (~85 days to full) and leaves T0032's primary-retention half open (primary disk full ≈ 2026-11-23).
2. **Prune both hosts** with one mechanism — a `capture`-role systemd timer (`zcrypto-capture-prune`) running a daily `find` deleting `<HH>.parquet` finals + `.sha256` sidecars older than `capture_retention_days` (default **14**). Never touches `.part` / `.held` / `.corrupt` (live hour, quarantine, evidence — all tiny). Closes T0032's retention remainder with the same tested template.

**Recommendation: 2.** Confidence: high. Safety: eviction at 14 days vs a verified hourly NAS pull (worst observed pull outage ≤ 14 h) is a ≥ 20× margin, and the pull-lag alert pages long before eviction could touch un-archived data. Steady state per host ≈ 6.7 GB. Deploy embargo: converge the primary only **after** the ≥ 7-day clean-run gate banks (~2026-07-15) — the 2026-07-14 image deploy (1 s downtime, inside the measured gap budget) is the already-booked exception; no further primary-touching change before the bank.

## Component design

### The secondary capture host (`zcrypto-red`)

- **Same image, same daemon, same config**: the digest the primary runs since 2026-07-14 — `sha256:63708539…` (PR #122) — via the `capture` compose + systemd unit, 10 EUR pairs at depth-100 from the shared `group_vars/capture_host` (a universe change converges both hosts identically). No engine, no keys, public WS only. **Bring-up asserts the running image digest ≥ PR #122's build** (and any future primary re-pin re-asserts it): that digest pins the T0008 depth-prune (a pre-fix image self-inflicts ~200 correlated desyncs/day — sub-`--min-gap-seconds` dual-silent windows no splice heals and no metric records), the T0032 withheld-ping, and the T0037 intra-hour trade dedup.
- **Image-rollout discipline (common-mode guard)**: both hosts on one digest makes a **bad build a likelier common-mode failure than a Linode outage** — it would kill both streams at once, destroying the redundancy. Standing rule for every future re-pin: converge the **secondary first**, bake **≥ 24 h** green (dead-man up, `source_lag{secondary}` nominal, desyncs 0), then re-pin the primary. **Materialized as `.claude/rules/capture-deploys.md`** (2026-07-14 review), so it outlives this spec and loads into every session; the converge-time assert below is the config-level enforcement.
- **Ansible**: add `zcrypto-red` to `capture_host`; add a new **`engine_host` group containing only `zcrypto`** and retarget `site.yml`'s engine role at it (the base→capture roles keep targeting `capture_host`). Host-level overrides in `host_vars/zcrypto-red`: `base_unattended_upgrades_reboot_time: "22:25"`, its own vaulted `capture_healthcheck_url` (a new healthchecks.io check, e.g. `zcrypto-capture-red`), `sync_capture_authorized_key` overridden to the new `sync_capture_red` public key (the capture role already installs this var as the rrsync forced command — no role change), **`capture_memory_limit: 1g`** (the `2g` default is 100 % of this host's RAM and could OOM the OS; 102 MiB measured ⇒ ~10× headroom), and **`capture_cpu_limit: "0.9"`** (1-vCPU box). Bring-up = the existing `bootstrap.yml` → `site.yml` flow, attended. **SSH posture (2026-07-14 review):** the `deploy` user reuses the repo's vaulted key (`infra/ansible/files/deploy_ed25519`) — never a per-host key — so the operator's existing `ssh red` alias works the moment `site.yml` converges (deploy@10022, passwordless sudo); and root SSH stays enabled **key-only** (`PermitRootLogin prohibit-password`) as the break-glass path, with the operator installing the master pubkey (`zhaow-master-2018`) manually at bootstrap — ansible never manages or purges `/root/.ssh/authorized_keys`.
- **Maintenance windows**: **21:25 (primary) vs 22:25 (secondary) UTC** — re-decided 2026-07-14 from measured traffic (6 days of archive). Criteria: (a) ≥ 1 h from any 4h bar boundary (00/04/08/12/16/20 UTC); (b) for the primary, the *book*-traffic trough — books are the unbackfillable loss currency, trades are REST-backfillable (measured: 20:00–21:00 UTC ≈ 136 k rows/pair-hr vs 242 k at the old 02:00 slot and 359 k at the 14:00 peak); (c) off the hour boundary (segment rotation). The +1 h separation keeps a same-night kernel reboot from ever overlapping and gives a failed primary reboot time to page (21:25 UTC = 23:25 Berlin — the operator is plausibly awake) before the secondary follows. A small converge-time assert that the two hosts' reboot times differ pins the T0027/T0033 fleet-window policy in config. Re-derive from the archive if seasonality shifts; do not guess.
- **Disk**: 0.48 GB/day into 50 GB; the D8 prune caps steady state ~6.7 GB; `DiskWatermark` + the dead-man's withheld-ping (T0032 fix, live in the deployed image) page on any breach.
- **Dead-man**: the daemon's existing healthcheck logic (ping withheld on WS-down, desync, or watermark breach) against the new check — the secondary gets exactly the primary's independent paging path. (T0032's probe-outage blind spot is inherited, not fixed — see Risks.)

### NAS pull + reconcile (extends the Role A loop)

`pull-entrypoint.sh` per cycle (hourly): pull primary (verify) → pull secondary (verify, own key, `/archive/capture-segments-red`) → journal pull + gate-export (unchanged) → **`zcrypto archive reconcile`**. Each step best-effort: a failure logs and the loop continues (the Role A pattern) — **except the reconcile step, which is skipped on any cycle whose capture pull exited non-zero**: a multi-hour pull outage must not mint "healed" full-secondary hours for primary data that exists and arrives later; the skip keeps the ledger honest for free.

**`zcrypto archive reconcile <primary_root> <secondary_root> <reconciled_root> [--window-hours 48] [--min-gap-seconds 5] [--textfile <path>]`** (new Typer command in `cli/archive/`, TDD):

- **Settle rule**: consider hour `H` once `now ≥ H + 2 h` (finalization + one pull cycle have both had time to land). Re-scan the trailing `--window-hours` each cycle; skip hours already ledgered with a minted final. If the primary final is still absent past a late deadline (~`H + 6 h`) and the secondary's is present, mint anyway (the secondary hour is complete, so nothing arriving later can add coverage). Exact constants are plan details.
- **Book gap detection (cross-stream, book streams only** — books tick continuously; trades legitimately go quiet, the `continuity.py` rationale): a window `(t1, t2)` where the primary stream is silent for `> --min-gap-seconds` **and** the secondary has ≥ 1 **update** row inside it. Requiring secondary activity is the guard against false-positive splices on a genuinely quiet market — and snapshot rows don't count: a secondary **resubscribe snapshot** is full state, not market activity, so alone it must not fabricate a healed-gap entry for a window where nothing was lost (pinned test case). `--min-gap-seconds` is **pinned from data, not asserted**: set it above the measured p99.9 inter-update quiescence of the *thinnest* pair at depth 100, and record the value + derivation in the plan. All timestamps are **Kraken's own event stamps**, so splice boundaries are immune to host-clock skew. A missing primary hour is the degenerate whole-hour window.
- **Correlated-loss detection (unconditional — no secondary witness):** every pair silent in **both** streams for ≥ the threshold ⇒ ledger state `both_streams_silent` + page (all 10 pairs quiet at once at depth 100 has no benign explanation); an hour absent from **both** mirrors while later segments exist ⇒ ledger state `total_loss` + page. Both book into `residual_gap_seconds_total`, so the failure table's both-dark promise has a detection mechanism of its own, not just the host dead-men.
- **Book splice (D4)**: mint `<HH>.parquet` as the ordered concatenation of blocks — primary `ts ≤ t1` / secondary `t1 < ts < t2` / primary `ts ≥ t2` — each block preserving its source file's row order; strict inequalities keep rows sharing one `ts` (one wire message) intact within a block. Multiple gaps per hour → alternating blocks by the same rule. Splice only where the secondary is clean over the window; any uncovered remainder is a **residual gap**, recorded, never papered over.
- **Trade union (D5)**: anti-join per settled hour; deficit → mint the union hour ordered by `trade_id`, **idempotent against duplicate ids within a stream**: dedup `unique(trade_id, keep=first)` with primary priority and a **logged dedup count**. The writer now dedups intra-hour at capture time (T0037 round-2 fix, in the deployed image), so live hours should be clean — but pre-fix archive hours contain reconnect-replay duplicates (T0026), and the reconciler must handle history.
- **Immutability & idempotence**: a minted reconciled final is never overwritten (the writer's own invariant, reused); re-runs are no-ops on ledgered hours; a provisionally-residual hour may later be healed by a new mint + a superseding ledger record.
- **Write path**: temp → fsync → rename (the `_replace_durably` pattern), `.sha256` sidecar minted from the final's bytes (same format as capture manifests, so `verify_tree` works unchanged over the reconciled root).

**Exit-bar isolation (pinned):** the T0003 Phase-1 exit-bar gap measurement runs on the **raw primary mirror only** — `continuity.py`'s overlay mode is a *separate* report for the canonical view and is **never** an input to the exit bar. Rationale: the overlay heals gaps by design, so measuring the bar on it would let a raw-capture regression bank a "clean" run — exactly the defect class the bar exists to catch. This matters most in the window between secondary go-live and the ~2026-07-15 bank, when a healed primary gap would otherwise vanish from a gate run.

### Provenance (auditability of spliced content)

Beside each minted final, `<HH>.provenance.json`:

```json
{"pair": "BTC/EUR", "kind": "book", "hour": "2026-07-16T09:00:00Z",
 "blocks": [{"source": "primary", "file": ".../09.parquet", "sha256": "…", "from_ts": "…", "to_ts": "…", "rows": 231019},
            {"source": "secondary", "file": ".../09.parquet", "sha256": "…", "from_ts": "…", "to_ts": "…", "rows": 412}],
 "gaps_healed": [{"start": "…", "end": "…", "seconds": 83.4}], "residual_gaps": [],
 "minted_at": "…", "tool": "zcrypto archive reconcile", "version": "…"}
```

plus one appended record per mint in `<reconciled_root>/reconcile-ledger.jsonl` (append-only; the audit index — non-mint states `both_streams_silent` / `total_loss` are ledgered here too). Input digests chain every spliced byte back to the immutable raw mirrors (retained indefinitely, D7). The archive verify chain therefore has three legs: raw mirrors verify against capture-minted manifests; the reconciled overlay verifies against reconciler-minted manifests; provenance ties the two together.

### Telemetry & alerting

`reconcile --textfile` writes `reconcile.prom` into the existing shared textfile dir. **Mandatory `infra/nas/config.alloy` change, or none of this leaves the NAS:** the `remote_write` keep-regex (ending `…|zcrypto_gate_.*`) **silently drops every unknown series** — extend it with `|zcrypto_reconcile_.*|zcrypto_capture_.*`, and confirm the new series are **visible in Grafana Cloud before the alert rules are pushed** (else every new rule evaluates against a non-existent metric). Series: `zcrypto_reconcile_last_success_timestamp_seconds`, `zcrypto_reconcile_source_lag_seconds{source="primary"|"secondary"}` (age of each mirror's newest final — detects a dead source via dataflow, independently of its dead-man), `…_spliced_hours_total`, `…_union_hours_total`, `…_healed_gap_seconds_total`, `…_residual_gap_seconds_total`, `…_trade_deficit_rows_total{host=…}`, `…_trade_dedup_rows_total`. (`source_lag` is an age gauge and a dead exporter freezes it — it is a staleness signal only in tandem with the `last_success_timestamp` rule; the plan keeps that pairing.) Grafana gains a Role C dashboard row + **four** rules: reconcile exporter stale; **residual gap increased** (a permanent loss — page; also fired by `both_streams_silent` / `total_loss`); source lag high; **healed-gap rate high** (warn — a chronically gappy primary whose gaps the secondary keeps healing never trips residual-gap or its dead-man, yet is a degrading capture host; this rule discharges T0003's gap-rate-alert sub-item). Reconcile step failures also hit the existing archive-pull ERROR-logs rule. No Alloy on the secondary (T0020's VPS obs role generalizes later; dead-man + source-lag suffice for a capture-only box).

## Failure modes & handling

| Event | Behavior |
|---|---|
| Primary reboot (21:25 window) / crash / Linode maintenance | Secondary keeps capturing; next reconcile splices the window; canonical gap = 0; primary dead-man pages. |
| Secondary reboot (22:25 window) / crash | Primary canonical unaffected; secondary dead-man pages; `source_lag{secondary}` climbs; secondary-gap QA metric records it. |
| One pair desynced/stuck or lossy on one host (host-local; incl. T0008's stuck-pair remainder) | Presents as a one-host silent stream → the splice covers it like any outage; de-risks T0008's parked item (cross-referenced there at closeout). |
| Both hosts dark in the same window (correlated desync, dual outage) | **Permanent loss** (constraint 4): detected unconditionally by `both_streams_silent` / `total_loss` (no secondary-witness required); residual-gap metric increments → page; ledgered honestly, never spliced over. |
| Secondary silently degraded (desynced, watermark-breached) | Its dead-man withholds pings → pages (same T0032-hardened logic as the primary, live in the deployed image; probe-outage blind spot excepted — see Risks). |
| NAS pull of either source fails | Logged ERROR → existing log alert; `source_lag` climbs; reconcile skipped that cycle (ledger honesty); retried next cycle; capture hosts buffer 14 days. |
| Reconciler dies / loop stuck | `reconcile_last_success` goes stale → alert; pulls unaffected. |
| Reconciled output corrupted later | Its own `.sha256` catches it; raw mirrors + provenance allow a deterministic re-mint. |
| Bad image build (common-mode: kills both streams) | Canary rule: secondary converges first, ≥ 24 h bake before the primary re-pin; secondary dead-man + `source_lag{secondary}` page during the bake. |
| Trade-id collision with differing fields / persistent cross-host trade deficit on healthy hours | QA alert — capture-bug investigation, primary stands. |

## The failure drill (discharges T0003's alerting drill)

Preconditions: the ≥ 7-day clean-run gate is **banked** (the drill's induced outage must never land inside the measured window); both streams green ≥ 48 h; the drill **refuses to run inside either reboot window** (21:25 / 22:25 UTC ± margin). **Leg A (primary kill):** at ~:20 past an hour — after a moment-of-truth pre-check that the secondary's newest **book row per pair is < 60 s old** (the 48 h precondition is stale by drill time; this is what guarantees the splice source is alive *now*) — arm the timed restore **before** the stop: `systemd-run --on-active=900 --unit=zcrypto-capture-restore systemctl start zcrypto-capture`, so the primary restarts even if the SSH session dies mid-drill; then `systemctl stop zcrypto-capture`. Assert the healthchecks.io check flips **down and the alert email arrives** — this observed page **is** T0003's "stop the daemon → confirm the alert fires" drill item. After ≥ 10 min, restart manually (the armed restore's later `start` is then a no-op). Within ~2 h assert: the reconciled hour(s) exist; provenance shows one secondary block spanning `[stop → restart snapshot]`; the **overlay's own continuity report** (canonical view) shows zero gap for the window while the raw primary mirror — the exit bar's only input, per Exit-bar isolation — shows the full gap (the honesty check); `healed_gap_seconds` incremented by ≈ the outage × streams, `residual_gap_seconds` unchanged; the dead-man recovered. Note: leg A exercises the dead-path page (pings stop); the withhold-**while-alive** path (desync / watermark / probe withhold) is *not* exercised here and its live verification stays open on T0032. **Leg B (secondary kill):** stop the secondary 10 min (same fences: timed restore armed first, outside reboot windows) → its check pages → restart; canonical view unaffected; secondary-gap QA metric records it. A redundant stream that can die silently is not redundancy — leg B proves it can't. Afterwards (attended, ops node, **fixed-image replayer** — the pre-71b72e9 book falsely fails 117–482 checks/hour on sound data): CRC-replay the spliced hour end-to-end — checksums validating **across the block boundaries** empirically confirm the state-convergence corollary for the top-10.

## Rollout order

1. **CLI (TDD, no infra):** `zcrypto archive reconcile`, `cli/archive/reader.py`, overlay mode for `infra/scripts/continuity.py` — a **separate mode**: the T0003 exit bar keeps running raw-primary-only (Exit-bar isolation). Zero changes to `cli/capture/`.
2. **Ansible:** inventory + `engine_host` split, `host_vars/zcrypto-red` (incl. the 1g/0.9 resource limits), vaulted `sync_capture_red` keypair, prune timer in the `capture` role, reboot-window non-overlap assert.
3. **Secondary bring-up (attended):** create the healthchecks.io check; `bootstrap.yml` → `site.yml` **with `--limit zcrypto-red`** (the embargo: the engine-host split / prune timer / reboot assert must not converge the primary pre-bank); verify 10/10 pairs flowing, dead-man green, AVX present, and the **running image digest = the primary's deployed digest (≥ PR #122's build)**.
4. **Image + NAS (attended compose redeploy):** build + push the CLI image containing `archive reconcile`, and **re-pin the NAS compose digest (the T0031 flow)** — the command does not exist in the currently-pinned image, so the reconcile step cannot be enabled before this. Then drop the red key, append the red host key to the pinned `known_hosts`, extend `.env`/`compose.yaml`/`pull-entrypoint.sh`; verify both mirrors pull + verify and `reconcile.prom` appears.
5. **Grafana:** extend the Alloy `remote_write` keep-regex (`|zcrypto_reconcile_.*|zcrypto_capture_.*`) and **confirm the new series visible in Grafana Cloud first**, then push the Role C row + four rules.
6. **Soak ≥ 48 h.** Converge the primary's prune timer only after the clean-run gate banks (deploy embargo; the 2026-07-14 image deploy is the already-booked 1 s exception). All future image re-pins follow the canary rule (secondary first, ≥ 24 h bake).
7. **Drills** (legs A + B) → closeout: T0003 (alerting drill + Role C done; gap-rate alert done via the healed-gap-rate rule; correct the stale 04:00-reboot and "Role C = NAS capture" text; keep the ansible-lint + `name[casing]` + `getent` sub-items explicitly listed as the open remainder so the partial-status trim doesn't drop them), T0032 (retention half done; fix the stale "D9 / secondary-only" pointer — this spec prunes both hosts and has no D9; withhold-while-alive verification + probe-outage blind spot stay open), T0008 (cross-reference: the splice covers host-local stuck-pair silence, de-risking the parked remainder), T0027 (fleet-window note), T0028 (corrected `ripe_when` math), T0038 (reader-helper cross-ref), 00048 (correct the eviction non-goal rationale, reasoned from the 20×-wrong fill rate), README `## Usage` (`zcrypto archive reconcile`), `iterations-history-phase1` entry.

## Cost

+**$12/mo** (Linode 2 GB Amsterdam) — infrastructure spend per master-plan §8, separate from the $200/mo data cap. Everything else runs on existing hardware; +1 healthchecks.io check and ~10 Grafana series, both inside free tiers.

## Non-goals

- **Correlated-desync protection** — the deterministic subclass hits every host at the same exchange event (constraint 4) and a gap both hosts share is permanent; T0008 owns recovery robustness. (Host-*local* desyncs — per-connection loss, a stuck pair — are covered incidentally: they present as one-host silence, the outage shape the splice heals.)
- **Cross-host row-level book merging** — constraint 1; it measures coalescing, not loss, and corrupts the book.
- **CRC replay in the hourly loop** — 34–68 min per hour-of-data on the Atom; it runs on-demand on the ops node as non-gating QA (T0033's first workload).
- **Feeding reconciled L2 into live trading** — 00048's scope guard stands; this is a research/archive artifact.
- **A third source / N-way reconciliation** — the reconciler is written primary-plus-one-secondary.
- **Moving Roles A/B or the reconciler to the ops node** — T0033's own spec, gated on its parked storage-topology decision.
- **Alloy/host metrics on the secondary** — T0020's VPS obs role generalizes later. (The keep-regex extension in Telemetry is on the **NAS** Alloy and unrelated to this non-goal.)
- **Fixing T0032's probe-outage blind spot** — requires `cli/capture/` changes this design forgoes; carried as a named residual (see Risks), tracked on T0032.
- **REST trade-backfill** — still T0003's parked item; the union reduces its urgency, doesn't replace it.
- **Multi-provider diversification** — both hosts are Linode (different regions); accepted residual, revisit before scaling capital.
- **Retro-healing gaps predating the secondary's go-live** — nothing exists to splice from. (Retro trade-union of pre-secondary history is likewise out; the intra-stream dedup exists so pre-fix hours don't corrupt future unions, not to launder history.)

## Testing & verification (outcome, not output)

- **Exit-bar isolation (pinned):** the T0003 gate instrument runs **raw-primary-only, overlay mode off** — asserted in the gate script/flags; the canonical view gets its **own, separate** continuity report; an overlay is never an input to the Phase-1 exit bar (it would mask exactly the raw-capture regressions the bar exists to catch).
- **Reconciler (TDD):** planted primary gap → spliced hour with correct block boundaries (shared-`ts` rows never split; source order preserved, never sorted); missing primary hour → full-secondary mint; gap spanning an hour boundary → two mints; secondary gap overlapping the primary's → residual recorded, not spliced; **secondary resubscribe-snapshot-only window → no splice, no healed-gap entry**; **all pairs silent in both streams → `both_streams_silent` ledgered + alert state, never minted**; **hour absent from both mirrors → `total_loss`**; trade union exact on fixtures (deficit healed, collision kept-primary + flagged, **intra-stream duplicate ids — a pre-fix T0026 archive fixture — deduped with logged count, idempotent**); idempotent re-run; existing reconciled final never overwritten; manifest + provenance minted atomically; `verify_tree` passes over a minted overlay.
- **Reader helper:** reconciled-first resolution; stale `.part` files invisible (the T0038 trap).
- **Prune:** spares young finals, `.part`/`.held`/`.corrupt`, and anything under retention; deletes only aged finals + sidecars.
- **Live:** secondary dead-man green ≥ 48 h and its running digest asserted ≥ PR #122's build; NAS logs `checked=N ok=N failed=0` for **both** sources; `reconcile.prom` fresh with `source_lag` ≤ ~2 h for both; the new `zcrypto_reconcile_*` series **visible in Grafana Cloud before the rules are pushed**.
- **End-to-end:** drill legs A + B as specified — one observed page per leg, zero canonical gap after leg A, and the raw-vs-canonical continuity delta equal to the induced outage.
- **Splice soundness:** ops-node CRC replay of a real spliced hour (fixed-image replayer) validates across block boundaries (the empirical check of the state-convergence corollary).
- **Cross-validation (continuous):** trade-deficit metrics ≈ 0 in both directions on healthy hours; a persistent skew is a capture-bug alarm, investigated not suppressed.

## Open questions / risks

- **Shared-vCPU contention** on the 2 GB plan: capture measured ≲ 41 % of one (EPYC) core at peak; if a noisy neighbor starves it into desyncs, the dead-man pages and the fallback is a $24/mo 4 GB resize. Bounded.
- **T0032's probe-outage blind spot is inherited, not fixed** (zero `cli/capture/` changes): while the `disk_usage` probe itself keeps failing, `breached` freezes at its last value, so a disk that fills *during* a probe outage leaves the dead-man pinging green — on **both** hosts. Named residual, tracked on T0032 (a sustained probe failure should itself withhold the ping); the reconciler's `source_lag` is the independent dataflow backstop that eventually catches the dead stream.
- **Bad-build common-mode** — likelier than a Linode outage (both hosts, one digest); mitigated by the standing canary rule (secondary first, ≥ 24 h bake), never fully removed.
- **Depth-11–100 convergence at splice boundaries** is assumed (CRC attests only the top-10) — a named waiver, inherited from constraint 3's honest limit; the ops-node replay check attests what is attestable.
- **Atom loop budget** with two mirrors: pulls + two verify sweeps + reconcile inside 3600 s — comfortable for > a year at 0.96 GB/day combined (T0028's wall was computed from the wrong 10 GB/day figure); `source_lag` watches it regardless.
- **Two-IP public WS subscriptions**: unauthenticated public market data, one connection per host, within Kraken's public limits (00048's open question; no per-account coupling exists).
- **Boundary-spanning outages** — the re-decided reboot slots (21:25/22:25) sit mid-hour by design (criterion (c)), so *scheduled* reboots no longer straddle an hour boundary; an unscheduled crash still can. Covered by the per-hour mint rule, and the drill deliberately exercises one boundary-spanning stop once.
