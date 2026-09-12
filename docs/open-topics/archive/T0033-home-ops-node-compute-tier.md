---
status: resolved
---

# Home ops node — a real-CPU compute tier

## Context — what

An always-on **home Linux compute node** (hardware on hand: **Intel i7-13700, 16C/24T, 64 GB DDR5,
4 TB NVMe, 1 GbE to the NAS**), running ~24×7 except for unattended-upgrades reboots and
full-system-backup windows.

**Decided 2026-07-13: yes, but *after* Role C.** It was briefly considered as a prerequisite for Role C,
but measurement showed Role C does not need it — capture is cheap (102 MiB / ~0.4 core at peak) and now
lives on a second Linode, and the reconciler's union repair is a vectorized polars anti-join the Atom can
carry. So the ops node is a **capability upgrade on its own merits**, not a blocker.

## Why this matters

The Atom C3538 (no AVX, 4 slow cores, DSM) is the binding constraint on every *compute-bearing* role, and
we keep paying for it in workarounds rather than capability. What a real CPU buys:

- **CRC archive verification** — measured **34–68 min per hour of data on the Atom** (infeasible inside a
  60-min cycle) vs **~8 min single-threaded** on a normal core, and ~1 min parallelised across 10 pairs on
  16 cores. This is the capability that had to be **descoped from Role C**; the ops node restores it.
  (Note the honest limit found while designing it: Kraken's CRC covers only the **top 10** levels, so it
  attests top-10 correctness — depth 11–100 completeness is not provable by any mechanism available.)
- **Role B's "verified" deep-check path** — dropped in spec `00049` purely because the Atom could not
  finish 8 cycles in 40 min. On an AVX box it runs the *same* runtime as the VPS, so the cross-runtime
  determinism question ([[T0029]]) disappears too.
- **A 24×7 research loop.** Phase-4/5 backtests currently only run when the intermittent workstation is
  on. This is arguably the biggest win and it serves the *research* north star, not just Phase 6.
- **[[T0023]]'s Binance liquidations recorder** — already decided (option a, free live-only). Liquidations
  are **not backfillable**, so its value accrues in wall-clock time and **every day of delay is a
  permanently lost day of forward data**. It has no good home today (the VPS is production; the
  workstation is intermittent). Strong candidate for the ops node's first workload.
- **Container metrics return.** cadvisor SIGSEGVs on DSM's cgroup-less kernel, so we collect **zero**
  container CPU/mem series today. Real `cpus:` limits also start working (nothing on the NAS is
  CPU-bounded — a runaway reconciler can starve the pull).
- **Ansible + systemd instead of bespoke glue.** The "no NAS-OS configuration" constraint is what forces
  the hand-rolled `pull-entrypoint.sh` sleep-loop, the 9-step manual deploy, and the hand-edited deployed
  compose. An ops node is managed like the VPS, reusing the existing base/docker/hardening/firewall roles.

## Findings so far

- **The node is provisioned** (2026-07-14): `z-home-zcrypto.zhaow.pro`, 24 cores / 61 GB / 3.4 TB free, AVX2, Docker not yet installed. The storage-topology decision (NFS vs local NVMe) remains the parked human item. (Note: its hostname is currently set to `zcrypto-red`, colliding with the Amsterdam VPS's name — fix at first converge.)
- Workarounds that become **deletable** once no zcrypto container runs on the Atom: the `-compat`
  (no-AVX) image variant + `POLARS_RUNTIME` build arg + its CI matrix leg; the DSM-ACL/uid dance
  ([[T0030]], `zcrypto-dummy` 1031:1000) and `normalize-archive-perms.sh`; the missing `cpus:` limits;
  the hand-re-pin ritual ([[T0031]]'s whole class). Roughly **250–400 lines of `infra/nas/` glue** is a
  write-off; everything in `cli/` and `infra/grafana/` is platform-agnostic and ports for free.
  **Caveat:** the NAS still runs `archive-pull` + `gate-export` (both use polars), so the `-compat` build
  survives until those move too.
- **T0027 widens** from "VPS reboot policy" to a **fleet maintenance-window policy**: the ops node adds a
  reboot window *and* a backup window. If any window overlaps another host's, multiple streams go dark at
  once. Windows must be pinned non-overlapping (primary 02:00 UTC, secondary 06:00 UTC, ops node
  elsewhere) and asserted in config.

## Resolution — OPS-6 Loop (spec `00056`, iter-103, 2026-07-18) — RESOLVES this topic

OPS-6, the final increment, landed the hot-cluster dataset exchange and proved research runnable on ops (full detail in PR #147's description, iter-103):

- **Topology + tool (D1/D2/D3/D8):** the custody / hot / private cluster split; the `zcrypto data` fetch/push/rebuild group over a NAS `hot/` hub keyed on one `[zcrypto].nfs_mount_dir`; the catalog rewritten by the taxonomy (`docs/reference/data-catalog-full.md`).
- **The channel:** the write-capable push into `hot/` jailed by a vendored `rrsync` (four containment layers, append-only enforced server-side; validated live on the NAS's rsync 3.1.2), and a new dedicated `sync_hot -ro` ops→NAS pull.
- **Seed + acceptance (D4):** all six authored sets seeded (74 files); ops provisioned as a research node (`uv` + clone as `zhaow`), `zcrypto data fetch` works cross-host, and the two data-dependent regression suites **ran (not skipped) and passed on ops (62 tests)** — the ratified flow (workstation authors, ops consumes) works end-to-end. The acceptance caught + fixed a real `data fetch --verify` manifest-parsing bug.
- **Cleanups (D5/D6):** `backup_dir` + dead fetch fields removed; the workstation's `zcrypto-engine-shadow.service` (Phase-6a soak, superseded by the live VPS engine per [[T0018]]) + `zcrypto-engine-gateops.timer` retired **outright** (owner-decided) with their key; `data/ohlc` (v0) + `data/engine-journal-vps` deleted.
- **Decisions continuity (D7):** the per-phase decision logs are git-tracked, one file per phase.

**No live deferred sub-item remains under this topic.** What OPS-6 surfaced but did not do — the ops identity migration (`deploy`→`zcrypto-data`) and the hot-out **authoring** writability (zhaow→hot-out) — is a *new* whole-fleet users/groups regularization, ratified in spec `00057` and tracked as its own follow-on topics [[T0067]] (ops phase) / [[T0068]] (capture/engine phase). OPS-6's ratified flow is complete without them.

**What had landed before OPS-6 — OPS-5 Offload (spec `00054`, iter-101, 2026-07-16)**, its closing note included — the one increment that note still listed as open, **OPS-6**, is the record above, which delivered it and closed this topic:

**The overlay writer now runs on the ops node.** The reconciler and the trade-backfill moved as one unit; the NAS kept custody, Role A's pull/prune, and `gate-export` (D3/D6). Verified by outcome, not exit code (D10):

- The overlay is **byte-identical across both hosts after a full cycle in the NEW direction** — 1175 files, list sha `0b684ce3bf0b3774` on ops and the NAS. The flow inverted cleanly: ops produces it, the NAS *pulls* it into custody over an rrsync `-ro` forced-command channel (proven confined: it cannot escape the pinned root and cannot write, so spec `00051` D10's pull-only transport holds).
- **Exactly one publisher each** for `zcrypto_reconcile_*` and `zcrypto_trade_backfill_*` — the NAS's stale textfiles were deleted at cutover, so the moved writer's series do not have a frozen twin paging forever from a host that no longer does the work.
- The raw mirrors are unharmed (3998 / 1002 finals, `checked=… ok=… failed=0`), the reconciler is **still detect-only** ([[T0039]]'s call, untouched), and the ops-side invariant holds: `gaps=0 trades_missing=0 duplicate_rows_found=0 recovered=0 unrecoverable=0`.
- The ops node is now observable at all: Alloy landed **first** (D1's ordering is a safety property), and the four textfile families it had been writing hourly *for weeks with nothing scraping them* now reach Grafana, with alerts. Active series: 405 of a <1k budget.

**Two things the move revealed that the spec had wrong**, both now registered: the ops image was too old to run the code being moved onto it (re-pinned), and `source_lag` **rose** rather than fell — ops is one hourly hop further from source by construction ([[T0058]]). Also found: the trade-backfill had never actually been deployed to the NAS, so its daily gate had never run once ([[T0056]]).

Still open under this topic: **OPS-6** (the workstation's `data/`, its two leftover systemd payloads, and the bi-directional NAS sync).

**What had landed before OPS-6 — the ratified topology and design (2026-07-15, spec `00051`):**

- **The storage-topology decision is made** (ratified 2026-07-15, attended discussion; recorded as `docs/specs/00051-ops-node-compute-tier-design.md`): a **hybrid of options (a)+(b)** — the NAS remains the archive home and pull owner and holds the full durable copy of everything; the ops node holds the **hot tier** (compiled datasets, the L2 primitive panel, an N-day raw working window) on local NVMe. The network sits in **no hot path** (research reads are local; NAS access = hourly ~20 MB increments + rare cold batch scans), and there is **no NFS anywhere** — every cross-host read is an rsync pull with manifest verification. Placement rule: *custody by durability, computation by weight, capture by redundancy*.
- **The old Roles-A/B/Alloy parallel-run cutover is superseded**: under the ratified topology the ops node is **purely additive** — Role A pull/prune and Alloy stay on the NAS forever; only compute migrates (reconciler, gate-export opportunistically) or unblocks for the first time (Role B verified path, CRC replay). No cutover, no split-brain window, far less churn.
- **The charter-as-non-goals is written** into the spec (D10): no trade key, never `engine_host`, no live execution, no sole custody of anything.
- The execution program is `OPS-1 Provision → OPS-2 Seed → OPS-3 Replayer → OPS-4 Panel → OPS-5 Offload → OPS-6 Loop` (named to avoid colliding with the master plan's §12 "Phase" / go-live "Stage" vocabulary), with 00050 Task 13 depending on OPS-3's replayer.
- **Dropped** (explicit, with reason): the "delete the `-compat` image leg once no zcrypto container runs on the Atom" item — the ratified topology keeps `archive pull` on the NAS indefinitely, so the compat variant is **permanent infrastructure**, not a deletable workaround.

**The steps this topic carried at its close, kept verbatim with what answered each — every one of them disposed, nothing pending:**

- **OPS-1…3 are DONE** (2026-07-15, iter-097 / spec 00051 plan Tasks 1–10): node provisioned + converged (`zcrypto-ops`, Debian 13), the Coinalyze liquidations poller live with NAS replication (the Binance WS recorder shelved in place — geo-fenced, see [[T0023]]), the continuity-replay verifier + verified-path daily timers armed with dead-men, and the archive seeded from the NAS over a new pull-only channel. — **ANSWERED:** delivered as recorded, and it stands: `docs/specs/00051-ops-node-compute-tier-design.md` and `docs/plans/00051-ops-node-compute-tier.md` are committed, and the artifacts are in the tree (`cli/liquidations/coinalyze.py`, `infra/ansible/roles/ops/templates/verify-replay.sh.j2`).
- **OPS-4 is DONE** (2026-07-15, iter-098 / spec 00052): the 1-second L2 primitive panel — materialized, verified (1,740 hours, zero errors), NAS-replicated, accruing hourly behind the new recurring NAS→ops pull timer (which also closed the replay-staleness gap). The state-threading correction (real data falsified the snapshot-per-hour premise) also fixed the merged OPS-3 verifier's semantics. — **ANSWERED:** delivered as recorded, and it stands: `docs/specs/00052-l2-primitive-panel-design.md` and `cli/panel/materialize.py`; [[T0014]]'s record independently reads the same panel (per-pair spread / `fill_bps` over the full capture window).
- Execute the remaining increments: **OPS-5 Offload** — **it relocates the overlay writer as ONE unit: the reconciler AND the trade-backfill** (owner directive 2026-07-16, spec `00053` D4). They share the `archive-pull` entrypoint, the `capture-reconciled` overlay, and `union_trades`, so moving one without the other would split a single writer across two hosts with an rsync between them — two writers on one overlay, where the ops-side mints never reach the NAS. The move also owes the ops→NAS reconciled channel it needs regardless (the `PANEL_*` pattern). Because the backfill was built where the reconciler already lives, OPS-5 stays a purely mechanical move with no new code in flight. Also in scope: reconciler off the Atom (dissolves [[T0044]]'s growth concern); wire the ops-node scraper + the replay-staleness alert; scope the verified-replay timer with `--date` once cadence matters. Then **OPS-6 Loop** — which now also owns (owner directive 2026-07-15): **migrate the workstation's `./data` (measured 2026-07-16: **281 MB**) to the ops node** — moved, or rebuilt there from the NAS-held sources — **and synced to the NAS** *(measured while scoping OPS-5, so this iteration starts with evidence: `ohlc-full` 37M, `ohlc-15m` 98M, `ohlc-holdout-2026-07-10` 1.4M, `derivatives-funding` 736K, `engine-store` 7.7M, `snapshots` 3.4M, universe JSON — **none on the NAS**, `data/*` gitignored, and the configured `backup_dir` absent, so it is genuinely single-copy on an intermittent host. The exposure is nonetheless BOUNDED, which is why this is a chore and not an incident: every one is `f(sources that survive)` — the NAS holds `kraken-ohlcvt-updates` 13G + `kraken-trades` 15G, and funding re-fetches from Binance Vision — and [[T0001]] established the reconstruction is bit-identical, so the trial registry's dataset hashes survive a rebuild. One artifact needs care: `ohlc-holdout-2026-07-10` is the pre-registered holdout ([[T0017]], look budget 1, spent) — it rebuilds deterministically from the ratified window, and rebuilding it is NOT a fresh look.)*, so the research loop's inputs are local to where it runs and the loop can never resume blind to data that lives elsewhere (the data-locality half of the catalog-sync discipline). — **ANSWERED:** both increments landed — OPS-5 as the record folded above (spec `00054`) and OPS-6 as this section (spec `00056`; PR #147, merge `b54b1ed32`). The `./data` half ended as replication rather than a move: the `zcrypto data` fetch/push/rebuild group (`cli/data/command.py:31`/`:51`/`:69`) over the NAS `hot/` hub, its channel at `infra/ansible/files/rrsync-shell`. The three in-scope sub-items hold: the reconciler is off the Atom and the ops scraper + replay-staleness alert are wired (both in the OPS-5 record above), and the verified-replay timer is scoped with `--date` from a watermark loop (`infra/ansible/roles/ops/templates/verified-replay.sh.j2`).

- **Correction (2026-07-17) to the `backup_dir` evidence in the bullet above:** the "configured `backup_dir` absent" reading was right about the outcome and wrong about the cause. The NAS NFS automount **EXISTS on the workstation** (fstab, `rw`), and `ohlcvt_source_dir` (`../zcrypto-kraken-data/kraken-ohlcvt-updates`) actively uses the dedicated share-root layout through it; `backup_dir` (`../zcrypto-kraken-data/zcrypto`) still carries the stale pre-dedicated-share `/zcrypto` jail suffix — a directory that does not exist on the dedicated share — so backups were not landing. The **single-copy conclusion stands**; the "mount not present" evidence was wrong. Repairing `backup_dir` is OPS-6 work (and note the rw+soft mount caveat in the research-flow flags below before routing backups through it). — **OVERTAKEN:** the field was deleted rather than repaired — plan `00056` records `AppConfig` without `backup_dir` and `resolve_backup_dir` gone, with zero non-declaration consumers, and `backup_dir` now survives only in prose (this topic's and [[T0003]]'s). With no such field there is no backup path left to route through that `rw`/`soft` mount.

- **OPS-6's data model — RATIFIED (owner, 2026-07-16); it supersedes the "migrate" framing above.** The end state is a **replication, not a migration**: the **ops node is the premise for the AUTONOMOUS research loop, the workstation is for INTERACTIVE research**, so **both hold an identical copy of the compiled datasets**, and the **NAS is the custody superset of every kind of data**. A script syncs **bi-directionally** with the NAS as hub (workstation ↔ NAS ↔ ops). — **ANSWERED**, and the transport question it left open was answered in the pull-union / push-own direction: `cli/data/command.py`'s fetch/push/rebuild over the NAS `hot/` hub, the push write-jailed by `infra/ansible/files/rrsync-shell` and the return leg a dedicated `sync_hot -ro` pull. The classification below outlived the bullet — `docs/reference/data-catalog-full.md` was rewritten by that taxonomy and its `## private` cluster carries both refusals (`engine-store` rebuilt per host; `engine-journal` per-host, host-scoped in custody). The host-scoped-journal precondition was dissolved rather than built: `cli/config.py:35` still carries the unscoped `journal_dir = Path("data/engine-journal")`, because the retirement below happened instead.

  **Why bi-directional is safe here — and exactly where it stops being safe.** It works *because of* an existing invariant, not in spite of it: canonical data is **immutable and hash-versioned** ("derive to new paths, never `latest`"), so a two-way rsync **without `--delete`** is a **union, not a merge** — nothing is mutated in place, so there is no conflict resolution to get wrong. Two hosts building the same dataset produce the same hash ([[T0001]]: bit-identical reconstruction); building different ones produces different paths. Both union cleanly. That safety belongs to the immutable subset ONLY — classified 2026-07-16:

  - **Union-syncable** (immutable, hash-versioned): `ohlc-full`, `ohlc-15m`, `ohlc`, `ohlc-holdout-2026-07-10`, `derivatives-funding`, `snapshots`, `universe`.
  - **NEVER two-way synced — mutated in place**: `engine-store`. `engine seed` *rewrites* it (it is "the documented repair for a poisoned store tail"), so two writers would fight and last-writer-wins could silently poison a tail. It is `f(ohlc-full + REST)` — **rebuild per host, never replicate**.
  - **NEVER two-way synced — per-host IDENTITY, and the name ALREADY collides**: `engine-journal`. On the workstation it is *the workstation's own shadow engine's* journal; `engine-journal-vps` is a pull of the VPS's; and the **NAS's `engine-journal` is the VPS's**. One name, three different engines' journals, three hosts. Union-syncing it would merge distinct engines' cycle records into one stream and make `engine report` / `gate-export` score a **streak that never happened** — a silent, plausible, wrong verdict, precisely the class §9's QA discipline exists to prevent. **NAS-as-superset therefore REQUIRES host-scoped journal paths** (`engine-journal-<host>/`) as a precondition of any such sync, not as a tidy-up afterwards.

  Left open for OPS-6's design (deliberately not decided here): whether this is a true two-way rsync pair, or simply **"each host pulls the union from the NAS and pushes only what it built"** — the latter reaches the same end state along the project's existing pull-only grain (spec `00051` D10) without inventing a new transport direction. Prefer it unless a two-way script proves genuinely simpler.

- **OPS-6's research-flow scenario — RATIFIED (owner, 2026-07-17, the T0058 consensus session); this is the intent OPS-6 implements, verbatim:** *auto-research on ops is manually started, with the hot datasets local at start; interactive and autonomous research NEVER run in parallel; the workstation fetches the consistent hot-dataset union FROM THE NAS on demand, and pushes produced artifacts back; ops consumes them next run.* (This answers the transport question above in the pull-union / push-own direction, NAS as hub.) Two flags raised when it was ratified: — **ANSWERED:** implemented as ratified, both flags discharged — all six authored sets were seeded (74 files) as OPS-6's first act, with `zcrypto data fetch` proven cross-host and the two data-dependent suites running (not skipped) on ops, and the push runs over the rrsync-jailed ssh channel (`infra/ansible/files/rrsync-shell`), never the `rw`/`soft` automount; spec `00051`'s topology has no NFS write path at all.

  1. **The NAS holds none of the hot compiled sets yet** — `ohlc-full`, `ohlc-15m`, and the rest live only on the workstation today, so **initial seeding of the NAS is OPS-6's first act**, before any fetch-on-demand flow exists to be consistent.
  2. **The workstation push must NOT go through its rw NFS automount** — that mount is `rw` with `soft` (+`sync`), and a soft-mounted **write** path can silently corrupt on timeout (the reason the T0058 ops mount is safe is precisely that it is `ro`). Push over rsync-over-ssh along the existing channel grain, or harden the workstation mount first — decide in OPS-6's design, do not let the push default to the mount because it is already there.

- **OPS-6 also owns the workstation's LEFTOVER PAYLOADS — and retiring them dissolves the journal problem above** (owner directive 2026-07-16; measured the same day). The workstation still runs two systemd `--user` units, both **alive and working**, both **superseded by the fleet**: — **ANSWERED:** the D5/D6 leg of the OPS-6 record above — `zcrypto-engine-shadow.service` and `zcrypto-engine-gateops.timer` retired **outright** (owner-decided) with their key, `data/ohlc` and `data/engine-journal-vps` deleted. That is the explicit decision the closing sub-item demanded, taken in the recommended direction, with no equivalent placed on the ops node.

  - **`zcrypto-engine-gateops.timer`** — **already declared retired** (README §Usage; [[T0003]]: "The workstation `zcrypto-engine-gateops` timer (spec 00042) is retired"), superseded by Role B on the always-on NAS. The repo's templates were deleted, **but the installed units never were**, so it has kept firing daily (last run measured: success, `gate (>= 14 clean days): not met`, **12 min 30 s of CPU**) — re-doing the NAS's work and pulling the VPS journal into `data/engine-journal-vps`. The README already ships the exact disable procedure (`systemctl --user disable --now zcrypto-engine-gateops.timer`, remove the two unit files + `~/.ssh/zcrypto-sync_ed25519`, `daemon-reload`); it simply was never run. **A doc that says "retired" while the thing still runs daily is the same class of drift as a metric nobody scrapes.**
  - **`zcrypto-engine-shadow.service`** — active, journaling real cycles (measured 2026-07-16: `cycle-00.json`, `cycle-08.json`). This is the **iter-083 workstation soak**, superseded by the **iter-084 VPS deployment**: [[T0018]]'s Stage-6a gate clock runs on the **VPS's** journal (ticking since 2026-07-11), not this one. So it is a *second* engine producing a *second* journal that no gate reads.

  **This is what makes the `engine-journal` collision above go away rather than need solving.** Retire both and `data/engine-journal`, `data/engine-journal-vps`, and `data/engine-store` stop being *live per-host state* and become *historical artifacts* — at which point the sync's scope is exactly the immutable, hash-versioned compiled datasets, which union cleanly by construction. **Do the retirement FIRST; then host-scoped journal paths may not be needed at all.** Solving a problem that a cleanup deletes is wasted design.

  Decide explicitly (do not just stop them): is the shadow engine **retired outright** (the VPS is authoritative and this journal feeds nothing), or does an equivalent belong on the ops node for the autonomous loop? Recommend **retire** — a second shadow on ops recreates the same two-journals-one-name hazard on a new host. And note `Linger=yes` is set, so these survive logout: they will keep running until deliberately disabled, and the machine being "just a workstation" has not been protecting anything.
