# Iterations history — Phase 1 (Data Foundation)

Per-iteration changelog for Phase 1. Appended at each iteration's close-out; see `.claude/rules/prose.md`.

## 2026-07-07 — iter-004: OHLC ingestion → canonical Parquet (Phase 1 · v0)

- **`cli/ohlc/` is the canonical OHLC ingestion path** — public-REST fetch into typed, sorted, deduped polars Parquet under `data/ohlc/` with a content-hashed manifest, so every downstream consumer reads one layout and one hash.
- **`docs/reference/data-catalog.md` is the reproducible record of the v0 dataset** — symbol x interval, rows, span and `dataset_hash` — read there rather than from the gitignored tree.
- **Full-history backfill parked as the binding data dependency**: the REST window is too short for the master plan's walk-forward regimes, and this v0 dataset is what the backfill later extends (archived [[T0001]]).
## 2026-07-07 — iter-005: rule-driven universe finalization (Phase 1)

- **`cli/universe/` applies the mechanical universe rule** — margin, leverage and a median-quote-volume floor, BTC/ETH-EUR mandatory — and **escalates** when the basket falls outside its size band, so a human sees an out-of-band basket before it ships.
- **`docs/universe/point-in-time-universe.md` is the point-in-time universe artifact**, carrying per-symbol criteria, provenance, and the spread criterion still a placeholder until L2 capture exists.
- **The first run escalated**: the EUR volume floor and the BTC-quoted legs' quote-currency mismatch made the basket a human decision, parked as archived [[T0002]] and settled in iter-007 below.
## 2026-07-07 — iter-006: OHLC dataset QA report (Phase 1)

- **`cli.ohlc.qa` is the read-only QA pass over the canonical Parquet tree** — grid gaps, wick outliers, coverage, monotonic timestamps, non-negative volume — with the evaluation time injected, so it reads no clock and no network.
- **`docs/research/02.phase1-ohlc-qa-report.md` is where a reader takes the v0 dataset's QA verdict**; a wick-outlier flag is a heuristic signal, never a failure.
- **Three data-foundation follow-ups were deferred here** and delivered in the iterations below: empty-interval reconstruction, the Binance cross-venue check, and the symbol & corporate-action ledger.
## 2026-07-07 — iter-007: universe floor calibration + quote-currency-aware volume (Phase 1 · T0002)

- **The universe's median-quote-volume floor is EUR 150k/day**, footprint-based (a full max-size position is about 1% of median daily volume), and a BTC-quoted leg's volume is FX-normalised to EUR before the floor applies — the measured basis is master-plan section 3's quote-leg-and-floor subsection.
- **EUR stays the quote leg**: USD books are deeper but that depth does not bind at our footprint and EUR gives up no margin capability, while USD adds conversion, cash-leg FX risk and per-fill tax joins; USDT is ruled out. USD routing is a pre-registered scaling trigger in section 3, not a pending action.
- **`docs/universe/point-in-time-universe.md` regenerated without escalation** — the full section-3 target basket, the two BTC-quoted legs included, with the new dataset hash in its provenance.
- Archived [[T0002]] resolved; decisions in `docs/research/02.phase1-decisions.md`.
## 2026-07-07 — iter-008: full-history OHLCVT backfill (Phase 1 · T0001)

- **`cli/backfill/` reconstructs canonical 1h/4h/1d bars from Kraken's downloadable OHLCVT 1-minute dumps** — every cadence from the 1-minute series, since only native 4h is short and no dump interval carries vwap, so vwap is rebuilt as a volume-weighted proxy.
- **The merge policy is a decision not to re-derive**: the base dump is authoritative for its own range and the quarterly updates contribute only rows past its last timestamp, because the two overlap and disagree and the base is the more complete.
- **`data/ohlc-full/` is the full-history dataset**, catalogued in `docs/reference/data-catalog-full.md`, with its reconciliation against the v0 REST in `docs/research/02.phase1-ohlcvt-backfill-reconciliation.md`.
- Spec and plan `00005`; archived [[T0001]] resolved, and it carries the follow-ups this iteration deferred.
## 2026-07-07 — iter-009: full-history dataset QA report (Phase 1)

- **`docs/research/02.phase1-ohlc-full-qa-report.md` is the QA verdict on `data/ohlc-full/`** — integrity clean, and the gaps it reports are Kraken's omitted no-trade intervals, reported and never filled.
- **The same report carries the per-year bar-density characterisation** a walk-forward design reads before trusting a regime's intraday density; thin-alt early history is sparser and flagged for regime-aware validation.
- No code changed — this iteration reuses the QA pass built in iter-006.
## 2026-07-07 — iter-010: symbol & corporate-action ledger + discontinuity audit (Phase 1)

- **`cli.ohlc.qa` gains the price-discontinuity check** — a bar-over-bar close move far from 1 flags a candidate corporate action or data error.
- **`docs/reference/symbol-corporate-action-ledger.md` is the ledger an agent consults** for Kraken aliases, dump altnames, the corporate-action check and quote-book migrations.
- **The audit's verdict as recorded here** — no corporate-action price artifact in the universe's full history, so no backtest applies a price adjustment. iter-151 below corrects the DOT half of that reading and names why the close-based audit could not have seen it.
## 2026-07-08 — iter-011: empty-interval reconstruction — fill_gaps (Phase 1)

- **`cli.ohlc.reconstruct` fills empty intervals as an opt-in on-read transform, never baked into a canonical dataset** — a synthetic zero-volume flat candle looks like a real bar and would bias features, so the fabrication stays explicit at use time and a filled variant is generated on demand.
## 2026-07-08 — iter-012: Binance cross-venue cross-check (Phase 1)

- **`cli/xcheck/` cross-checks the canonical daily closes against Binance's public data endpoint**, and `docs/research/02.phase1-binance-crosscheck-report.md` carries the verdict: the two venues corroborate each other, so the full-history dataset is venue-consistent.
- **The check reads only the most recent daily candles Binance serves in one page** — the scope is stated in the report and in `cli/xcheck/binance.py`, which also records the full-overlap follow-up via start-time pagination.
## 2026-07-08 — iter-038: T0003 D2 capture pipeline — built + deployed LIVE (Phase 1)

- **`cli/capture/` is the live L2-and-trades capture daemon** on the Kraken WS feed: per-pair book with venue checksum validation (parsed as decimals, since the checksum depends on wire-format trailing zeros), hourly zstd-Parquet finals with sha256 manifests, gap accounting and a disk watermark.
- **`infra/ansible/` provisions and hardens the capture host** — a non-root deploy user, a moved SSH port with root and password login off, CIS-L1 hardening, chrony NTS, unattended upgrades, and a default-drop nftables ruleset that manages only its own table so Docker's NAT survives.
- **Liveness is a healthchecks.io dead-man switch with its badge on the README** — a failure domain deliberately independent of the metrics stack.
- **Secrets are two-layer and self-contained**: a sops+GPG-encrypted ansible-vault password, with deploy keys, hostname and the dead-man key vault-encrypted, so nothing plaintext is committed and the repo stays public.
- Design and plan `00027`; archived [[T0003]] carries the remainder this iteration deferred.
## 2026-07-08 — iter-039: T0004 tick-derived bar reconciliation + true VWAP (Phase 1)

- **`cli/tick/` reads Kraken trades CSVs from a path or a ZIP member**, aggregates them into left-closed epoch-aligned bars, and reconciles them against the canonical OHLCVT — it is the source of a **true tick-weighted vwap** in place of the backfill's close-weighted proxy.
- **`docs/research/02.phase1-tick-reconciliation-report.md` holds the reconciliation verdict** against the master plan's tolerance bar; the vwap difference is the real finding, largest on the thin pairs.
- **The reader recognises the quarterly ZIP schema only** — the complete dataset's layout is different and raises rather than misparsing, which is the remainder archived [[T0004]] carries.
- Spec and plan `00028`.
## 2026-07-08 — iter-042: complete-dataset tick reader + full-history BTC/EUR reconciliation (Phase 1, T0004)

- **`cli/tick/` now reads the complete-dataset trades schema too** — the layout is chosen by field count, and a three-field row is disambiguated by whether its first field is a plausible Unix timestamp, so a genuinely short row still errors rather than being silently reinterpreted.
- **`docs/research/02.phase1-tick-reconciliation-report.md` gains the full-history BTC/EUR run**, and with it the reading an agent carries forward: the strict-tolerance miss is cross-source storage-precision noise rather than aggregation error, and only early-illiquid bars diverge materially.
## 2026-07-08 — iter-043: full-universe full-history tick reconciliation (Phase 1, T0004)

- **`docs/research/02.phase1-tick-reconciliation-report.md` now covers every EUR major over the full history**, with the weakest pair's per-year breakdown beside it — divergence is concentrated in each pair's early-illiquid years and modern history reconciles near-exactly.
- **The exit-bar tolerance judgment was left to a human** because it sets the Phase-1 standard rather than being an engineering call; archived [[T0004]] records the acceptance and where the 15m/tick-storage remainder went.
______________________________________________________________________

**Continuation — post-close Phase-1 backlog (capture-pipeline hardening), appended while Phase 6 is active.**

______________________________________________________________________

## 2026-07-14 — iter-095: capture writer crash-safety — T0036/T0037 + T0032/T0035 slices

- **A committed `<HH>.parquet` now means committed AND complete**: parts are written atomically, finalisation commits through a marker so recovery is mechanical and never guesses, anything unreadable is quarantined rather than deleted, and a single-instance lock keeps two writers off one tree — a restart can no longer silently truncate the hour it lands in.
- **Hour rotation no longer trusts the venue's own timestamp alone**: a boundary-crossing event is held until a second witness confirms the hour, witnesses are clamped at the wall clock so an unconfirmed stamp cannot corroborate itself, and never-confirmed rows spill quarantined instead of fabricating an hour. The accepted residuals ride live [[T0037]].
- **The disk-watermark breach window books into the gap accounting** on its own path, the watermark loop survives a backward clock step and a raising probe, and the reconnect path catches every websocket, OS and timeout error instead of dying — archived [[T0032]] and [[T0035]] carry the remainders.
- **`infra/scripts/continuity.py` measures segment-timestamp continuity against a pulled copy of the archive** — the daemon's own counters cannot see restart damage, so this is the exit-bar instrument and the post-deploy check.
- **A production migration is rehearsed on a replica built with the OLD writer before it touches the live tree**; archived [[T0038]] opened for the NAS mirror's stale parts.
______________________________________________________________________

**Continuation — post-close backlog entries begin here (the phase closed with its report; later data-foundation iterations keep appending below per `iterations-history.md`).**

______________________________________________________________________

## 2026-07-15 — iter-098: the L2 primitive panel (spec 00052, OPS-4)

- **The L2 primitive panel is a live-accruing dataset** — a one-second grid of spread, mid, microprice, imbalance, effective spread at size and depth, materialised hourly from the reconciled capture and replicated to the NAS, so [[T0014]]'s calibration starts from a query rather than a rebuild.
- **Panel hours are chained, not self-contained**: Kraken sends a book snapshot only on subscribe, so book state threads across contiguous hours, a sidecar carries the resume watermark, an unanchored hour is recorded as an honest gap, and the final fractional second of an hour must drain into the carried book or every successor starts stale.
- **The ops node runs the hourly pull-then-materialise timer pair with its own dead-man checks**, so a stalled panel pages instead of ageing quietly.
- **`docs/reference/data-catalog-full.md` gains a live-accruing operational datasets section** — codified as a closeout rule, so the research loop's pick-time surfaces and the dataset inventory cannot drift.
- Spec `00052`.
## 2026-07-16 — iter-099: the capture-pipeline exit bar — verified, and T0003 closed

- **The Phase-1 capture exit bar is met, and its evidence is `docs/research/02.phase1-capture-exit-bar-report.md`** — measured from segment-timestamp continuity rather than the daemon's in-process counters, which reset on restart and understated a crash by orders of magnitude. Archived [[T0003]] resolved.
- **Clock ruling** (decision `[iter-099]`, `docs/research/02.phase1-decisions.md`): a within-budget data GAP does not restart the clean-run clock, unlike a desync producing checksum-INVALID segments — missing data is visible, bounded and priced into the budget; wrong data is none of those.
- **ansible-lint runs as a local pre-commit hook on the already-locked version**, scoped to `infra/`, configured in `.ansible-lint`; the repo's lowercase task-name idiom is skipped by decision, because satisfying it would rename handlers and every notify in lockstep and a desync silently stops a handler firing.
- **Never take a gate's verdict from the last command of a pipeline**: the firewall gate guarding the live trade key read `grep`'s status, and the obvious `pipefail` repair fails it closed on a healthy host — the pipe is dropped so the status is unambiguously the probe's.
- **An ansible run's `ok=` counts skipped tasks too**, so a task header is not proof the changed lines ran; archived [[T0050]] split out for REST trade-backfill, written self-contained because an archived topic is never re-read.
## 2026-07-16 — iter-100: REST trade-backfill — a provably complete trade stream (spec 00053, T0050)

- **`zcrypto archive backfill-trades` makes the trade stream provably complete**: it detects trade-id gaps from the archive itself, fetches only the missing ids from Kraken's public REST, and mints healed hours into the reconciled overlay — trades have a repair path the book stream does not, because REST is an independent third witness.
- **The property it rests on is measured, not assumed**: Kraken's per-pair trade id is dense, so a hole in the sequence IS missing data and is provable with no network call.
- **Two archived records were corrected** — a desync recorded as leaving trades unaffected did not, and the reconnect-overwrite loss recorded as plausible-but-unquantified is now measured and repaired.
- **Spec `00053`'s two wrong rulings are superseded in the spec itself** — one mandated a cursor conversion that loops forever against the live venue, the other demanded REST rows be indistinguishable from WS rows, which the venue's own timestamp precision forbids; both residuals are registered rather than buried.
- **An orchestration must count from the operation's own result**, or it reports recovery it never performed: every fetched row now lands in exactly one printed bucket and detection is reported separately from healing. Archived [[T0052]], [[T0053]] and [[T0054]] registered.
______________________________________________________________________

## 2026-07-16 — iter-101: OPS-5 Offload — the overlay writer moves to the ops node (spec/plan `00054`)

- **The reconciler and the trade-backfill run on the ops node, as ONE unit** — they share an entrypoint, the reconciled overlay and the trade union, so splitting them would put two writers on one tree with an rsync between them. The NAS keeps custody, its pull-and-prune role, its own Alloy and the gate export. Spec and plan `00054`.
- **The NAS still never receives a push**: it acquires the overlay through a pull-only channel of the existing shape, proven confined to its pinned root and unable to write, and hash-verified rather than trusted. Ops reads custody read-only over NFS in place of a three-tree rsync, and the reconcile gate consumes the NAS-written pull status through that mount, fail-closed.
- **Observability lands BEFORE the thing it watches, and that ordering is the safety property** — ops had been writing metric families for weeks with nothing scraping them. Alloy now ships them with host metrics and container logs, and the ops alert group watches them with per-rule no-data behaviour: a dead-man alerts on no data, an exit-code rule does not.
- **Alloy runs as a dedicated non-key-owning uid**, verified live that it cannot read the deploy key through its host mount; the Alloy credentials moved to a group that actually contains the hosts running Alloy, ciphertext moved verbatim with nothing decrypted, and the ops secrets file is rendered from the vault instead of hand-placed.
- **The verified replay is watermark-driven** — it persists the last replayed date and replays every day through yesterday, so a missed timer catches up by construction — and **the NAS came under Ansible**, so a hand-copied file is no longer the deploy mechanism. Archived [[T0056]]/[[T0057]]/[[T0058]]/[[T0059]] carry those; [[T0061]] and [[T0062]] were split out; [[T0044]]'s growth leg was relieved without closing the topic.

## 2026-07-17 — iter-102: the liquidations poller stops re-submitting at source (spec 00055, T0060)

- **The liquidations poller skips already-persisted buckets before the writer** rather than re-submitting them, so a surviving dedup drop in the ops logs is now a genuine anomaly instead of routine noise; the fetch window, writer dedup and late-event floor are untouched.
- **Its cycle log reports what was submitted AND what was skipped at the watermark**, and startup reports how many coins primed — an operator reads counts rather than a bare submitted total annotated with a caveat.
- No CLI or config surface changed; spec `00055`, with the ops deploy tracked in archived [[T0060]].
## 2026-07-17 — iter-096: Role C redundant capture close-out — soak pin, --mint flip, live drill (spec 00050, 2 of 2)

- **The reconciler's splice threshold is `--min-gap-seconds = 30 s`**, pinned from a two-host soak: it clears the largest per-connection coalescing artifact a healthy host produces — a pair silent while its siblings flow on the same host is not a gap — and still sits far below the smallest real outage on record, so it costs no detection power. Archived [[T0039]].
- **Minting is a named, defaulted-off knob** enabled durably in host vars with its evidence beside it, never a silent default change, and the rendered command states its mode explicitly — a boolean override arriving as a string is truthy, so the cast is load-bearing.
- **The live two-leg drill demonstrated the redundant-capture thesis on the production paging path**: a primary outage is healed from the secondary, and a secondary outage costs the canonical nothing. A drill's restore window must exceed the deployed check's timeout PLUS its grace, or the outage can never page — the plan's own numbers could not have fired its own assertion.
- **A dead-man that stops being pinged stays green on fresh metrics**, because healthchecks.io is deliberately a separate failure domain: restoring its ping is part of any rewrite of the unit that sends it, and a gate-skip pings too — a skip means the writer is alive and correctly refusing stale input.
- Spec `00050`; the stale cross-references its closeout adjudicated are recorded on the topics they belong to.
## 2026-07-18 — iter-103: OPS-6 Loop — the hot-cluster dataset exchange, research runnable on ops (spec 00056)

- **Datasets are partitioned by sync behaviour and mutability into custody, hot and private**, and `docs/reference/data-catalog-full.md` is written by that taxonomy: custody is read in place and never transmitted, the hot working set is what every research node exchanges, private per-host state is never synced.
- **`zcrypto data fetch|push|rebuild` is the exchange** — fetch mirrors the NAS hot hub into the local data root manifest-verified, push sends this node's authored sets, rebuild mints a refreshed sibling and pushes it. Config collapses to one NFS mount root from which both the hot source and the custody dumps derive.
- **The hot hub is the only write path into custody and it is append-only SERVER-side**: a vendored jailer pins the path, munges symlink targets and strips deletes and overwrites, so a stolen key running its own client still cannot remove or replace a published file.
- **The ops node is a research node** — the data-dependent suites run there against fetched data rather than skipping — and the fetch verifier attests each fetched file's hash against whatever shape that set's manifest uses, failing closed on an unattested hash rather than assuming one layout.
- **Decision logs became git-tracked, one file per phase, appended live per iteration exactly like this changelog**, so a decision made on either host survives the multi-host loop. Spec `00056`; the fleet users/groups follow-on is spec `00057` ([[T0067]]/[[T0068]]).
## 2026-07-18 — iter-104: fleet users/groups (ops phase) — deploy leaves the data path (spec 00057)

- **The ops data path runs as a dedicated no-sudo machine user** that owns the data trees and serves the NAS pulls, so the passwordless-sudo admin user leaves the data path entirely; a setgid exchange group bridges it to the research user that authors into the hot outbox.
- **A pull-serving account needs a REAL login shell**: sshd runs the forced command through the account's shell, so `nologin` swallows it and every pull fails. The jail is the forced command plus no password, not the shell — spec `00057` D2 and the code comments were corrected so the capture/engine phase gives its pull user a real shell too.
- **The four NAS pull channels are Ansible-provisioned**, each pinned read-only to its own subtree, and the NAS pulls from the machine user; the hand-installed admin-user keys are gone.
- **The admin user is renamed `zcrypto-deploy`** and virgin bootstrap provisions it, so ssh, sudo and Ansible all address one name fleet-wide.
- `infra/ops/README.md` and `infra/nas/README.md` describe the model an operator now works in. Spec `00057`; archived [[T0067]] resolved, [[T0069]] parked for the gate-export CPU cost.
## 2026-07-19 — iter-105: fleet users/groups (capture/engine phase) + container names (spec 00057, [[T0068]])

- **The capture and engine accounts were renamed keeping their uid and gid**, so the numeric compose user stayed byte-identical and neither the capture daemon nor the engine was recreated — the unbackfillable stream never gapped.
- **Every fleet pull channel now runs off the machine user, Ansible-provisioned**, with the admin user's hand-installed keys dropped; the ssh allow-list must admit both accounts BEFORE the NAS is repointed, or sshd denies the pull, and the engine gate asserts that live posture before the trade key renders.
- **Both capture hosts run their own Alloy stack under a dedicated non-login, non-key-owning uid in its own compose project**, so an Alloy redeploy never restarts capture; its journal reader is scoped to avoid double-ingesting the attached capture stdout. The docker-socket residual, now on the trade-key host, is recorded in archived [[T0042]] and re-decided at the go-live review.
- **Every compose service carries an explicit `container_name`, and log relabelling keys on the compose SERVICE label rather than the container name** — a name-prefix strip had collapsed one container's identity and silently broken its error alert and its dead-man.
- `infra/README.md`, `infra/nas/README.md`, `infra/external-systems.md` and `.claude/rules/fleet-deploys.md` name the accounts an operator uses. Spec `00057`; archived [[T0068]] resolved.
## 2026-07-19 — iter-106: panel settle-watermark — an un-healed hour can't be permanently captured ([[T0066]])

- **The panel materialiser defers an hour until it is settle-aged (7 h by default, `--settle-hours`) and holds its monotone watermark off it** — the reconciler mints healed book hours well after the hour closes, so without the gate an hourly pass could consume the un-healed primary and capture it PERMANENTLY, silently degrading the dataset [[T0014]]/[[T0024]] are about to read.
- **Spec `00052` D6 is corrected in place**: *settled* (final and hash-verified) is not *heal-complete*, and the explicit watermark was chosen over ledger-driven invalidation because the freshness cost has no current consumer.
- **The trade-bar materialiser's settle binding is a different problem** — trades are heal-complete only after the daily REST backfill, a chasm rather than a race — and rides live [[T0065]]. Archived [[T0066]] resolved.
## 2026-07-22 — iter-115: the universe's spread cap, retired from placeholder ([[T0024]], spec `00067`)

- **The universe rule screens on an effective-spread cap of 10 bps/side at the EUR 1,400 reference position** the volume floor is already calibrated against, so the two criteria are commensurable; the artifact carries a structured spread-cap record in place of the placeholder string, and the cap reuses [[T0014]]'s calibration rather than re-deriving one.
- **The cap can only screen the EUR-quoted legs**: capture subscribes to EUR pairs only, so the BTC-quoted legs record a NULL spread and are not rejected — absence of evidence is not evidence of a wide spread — and the per-symbol table carries a spread column so that null is visible to every reader. Archived [[T0092]].
- **A threshold chosen to exclude today's worst member is a post-hoc rank, not a criterion** — recorded as the reason the cap was left non-binding.
- **Replaying stored universe entries proves a criterion changes nothing GIVEN THOSE INPUTS, never that a fresh rebuild selects the same names** — the rebuild was measured separately and did not, which is what became [[T0093]].
- Spec `00067`; decisions in `docs/research/02.phase1-decisions.md`; archived [[T0024]] left partial until the artifact was rebuilt.
## 2026-08-11 — iter-136: the universe refresh's volume source — reach reaches the BTC-quoted legs, the universe becomes a resolved stamped-set series ([[T0093]], spec `00093`)

- **The universe rebuild resolves its OHLC source and its published artifact newest-wins, and both resolvers are LOUD on an incomplete newer set** rather than degrading silently to an older one; the `--pairs` help text and the README Usage row describe the resolution rule instead of a fixed path.
- **The reach round is quote-aware, so it can mint the BTC-quoted legs** — the venue spells that quote `XBT` where the repo spells it `BTC`, and reading the mapping as a copy rather than a translation makes the legs look absent when they are not.
- **The engine keeps a DERIVED EUR-only view of the pair-key map**, so re-keying that map by full symbol cannot silently widen the live engine's basket or move its store paths.
- **The universe rebuild refuses a source narrower than the candidate set, naming the missing legs** — the size-band escalation compares the SELECTED set and cannot see that the SOURCE was narrower, which is the silent shrink arriving through a different door.
- **The universe artifact is a series of immutable stamped sets**, because the additive transport cannot express a second version of a fixed filename and a hand-promoted copy would leave every fetching host reading stale. Spec `00093`; decisions in `docs/research/02.phase1-decisions.md`; archived [[T0093]].
## 2026-08-13 — iter-137: the attended universe refresh — the volume signal finally reads a live window ([[T0093]], [[T0024]], spec `00093`)

- **The canonical universe reads a live volume window**: a fresh reach round minted every leg including the BTC-quoted ones, and the rebuild published a stamped set that production resolves, with the source and its stalest bar named in the artifact's provenance.
- **Publishing a reach set is opt-in, never the default** — the round writes a `detached` status and SUCCEEDS rather than aborting, while the hub's transport only ever adds, so a possibly-detached set must not go through that one-way door before anyone inspects it.
- **An intraday series that cannot seam is written under a `detached` filename**, so a consumer globbing the ordinary name finds nothing rather than a series with an invisible hole; REST's per-interval reach-back is what bounds how late a reach round can run, carried in live [[T0065]].
- **The legacy unstamped universe artifact is retired** — absence of a stamped set is fatal and names both recoveries — and the `--pairs` help text and the README Usage row say so in the same change, since that directory can never be updated through the additive transport.
- **A guard tying two properties together was SPLIT rather than repointed**, so the universe can follow its source while the retired dataset's only surviving record still reproduces. Archived [[T0024]] and [[T0093]] resolved; decisions in `docs/research/02.phase1-decisions.md`.
______________________________________________________________________

**Continuation — 2026-08-28: the corporate-action ledger's detection moves onto the operating surface.**

______________________________________________________________________

## 2026-08-28 — iter-151: T0025's trigger is retired rather than waited on, and building its record disproved a claim the ledger carried

- **The refdata sweep's reference-data step REFUSES instead of asking for an eyeball diff**, returning one reason per finding that names the pair and the observed value — an operator's next act is deciding whether a corporate action happened, and "something changed" cannot start that; all reasons are returned, because a batch delisting is announced as a batch.
- **The sweep also scans the venue's scheduled-maintenance feed for entries naming a selected asset**, reading the entry's name, its components AND its update bodies — the live feed names assets only in the body — and matching bodies case-SENSITIVELY, since they are English prose where a case-insensitive ticker fires on ordinary words.
- **Neither check fetches, deliberately**: the feed is the caller's to supply, because a live venue endpoint inside the suite is a flake source and a silent skip on the routine that gates the go/no-go reads as coverage.
- **`docs/reference/symbol-corporate-action-ledger.md` carries per-pair first and last bar** — the first labelled a COVERAGE FLOOR rather than a listing date, the last the quarterly freeze rather than evidence a pair still trades — and states plainly that it cannot show the failure it guards, since a delisted pair leaves the dump entirely.
- **The ledger's DOT redenomination claim is corrected**: the transition sits inside the first bar and is invisible to a close-over-close audit at any bar size, so every newly admitted pair gets one hand read of bar one — and bar one is excluded or distrusted, **never rescaled**, because a unit-based repair lands an order of magnitude below the true price. Archived [[T0025]].
## 2026-08-29 — iter-153: T0037's residuals get detectors, and the guard class gets a guard (spec `00103`, [[T0037]] partial)

- **A parked residual's trigger must be deliverable by instrumentation that exists**: [[T0037]]'s residuals were parked on being OBSERVED in production while nothing could observe them — a baseline counter watching the normal path, a counter on a path neither residual takes, a bare log line, and a metric never shipped at all.
- **An earliness measurement taken with the leading clock subtracts its own lead back out**, so a clock-referenced counter cannot see a leading-clock truncation; the clock-skew signal is that residual's sole detector.
- **The clock is read on the HOST by a chrony timer writing into the existing textfile mount, never inside the metrics container** — reading it there needs a capability that permits SETTING the clock, on hosts whose correctness argument is that the clock cannot be trusted.
- **A stale textfile reads healthy forever**, so an alert watches the exporter's own file mtime; a deleted file is recorded as still uncovered rather than claimed closed.
- **Never assert a config property by substring over the file's text** — a comment or a refusal message satisfies it while the real setting points anywhere, and one such assertion was blind on the live trade path; the repo asserts it structurally instead, with the guard's own residual gaps in its docstring. Spec `00103`; [[T0037]] stays partial.
## 2026-08-28 — iter-152: the NAS pull's verify cost, bounded and observable (spec `00102`, [[T0028]] resolved)

- **The NAS pull hashes only what rsync's own itemisation says it received, plus a rotating slice of the tree** — knowing what changed costs no extra probe, and the alternative (a per-file stat or sidecar probe) is itself proportional to the tree, keeping the growth term this work removes.
- **Only the HASH is narrowed; the WALK stays whole, and that is the load-bearing invariant** — the freshness figure the dead-man reads comes from the full traversal and would go blank exactly when nothing is arriving, and the stale-part prune rides the same walk.
- **The rotating slice is keyed on the loop's OWN cycle counter, never the clock**: this loop's period is interval-plus-work and therefore drifts, so a clock-hour key walks and can leave whole slices never visited.
- **The verify cost is published per channel** — seconds, files hashed, files walked — one file per channel so the pulls do not clobber each other's series, with the textfile mtime series admitted alongside so a stopped channel reads as an ageing mtime rather than a zero that looks like success.
- **One image serves both legs, because the hash scope is a DEPLOYED setting rather than a build**: a digest converge reads the baseline whole, a config-only converge flips the setting, and the flip's rollback is the same one line. Every converge that recreates the container replays the gate cache cold — a cost to budget, corrected in spec `00102`, its plan, `docs/reference/fleet-pins.md` and the rollout skill. The measurement ran on an interim image built from the feature branch by explicit one-off exception, retired by the next develop-build re-pin of the NAS. Archived [[T0028]].
## 2026-09-02 — iter-163: the past-dated detector counted a benign restart, and its alert could not see it either way (spec `00109`, [[T0037]] still partial)

- **The past-dated-stamp detector counts only when the opened past hour holds no captured parts** — a held spill is not capture evidence, and that read must precede held-row redemption — so a reconnect replay after a restart no longer reads as a fabricated hour. Spec `00109` supersedes spec `00103` D5 in its own file, a spec being immutable once written.
- **The capture, ops and NAS roles remove the orphan `config.alloy` above the deployed one**: nothing mounts it, but a stale file at the path an operator would GUESS answers that guess with plausible data instead of an error. Removed in the roles, not by hand, and outside the digest-gated block every ordinary converge skips.
- **A counter whose only step is bound to process start is invisible to `increase()`** — its reset is never scraped — so the rule and its panel read the ABSOLUTE value. The cost is on the surface: the rule is a LATCH only a capture restart clears, so the runbook records the standing value and rules any later one a new event. The sibling counter that steps at every boundary stays on `increase()`.
- **`infra/runbooks/capture.md` no longer claims a hard-zero baseline** — it carries the dated reading and the shapes a count can take, and the peer-host comparison is now the MANDATORY branch of the read: the benign shapes and the fabrication leave the identical trace on the paged host's disk.
- **Landing order is a constraint, not a step, and it lives on `.claude/rules/fleet-deploys.md`**: land the predicate, re-pin BOTH capture hosts verified by DIGEST, then push — a value gate passes inside the canary bake gap and would latch a false CRITICAL on the capture pair. [[T0037]] stays partial; the quarantined-rows counter is dropped here, registered as [[T0161]].
______________________________________________________________________

## 2026-09-03 — iter-167: the fourth venue outage gets its provenance row (spec-less)

- **`docs/reference/capture-era-data-hygiene-map.md` gains the 2026-09-03 venue-outage row** — that map, not the venue-status counter, is the durable answer to "was this hour ours?", and the row cannot wait: the counter's retention, the log retention and the next capture restart each erase the evidence independently.
- **Every figure in the row is read from its source** — the reconcile ledger's own record and the continuity instrument run against BOTH hosts' pulled trees, so the total is cross-host agreement rather than one tree read twice.
- **A capture daemon's log wears the archive's vocabulary but is not the archive**: figures taken from it and reported in the ledger's terms were wrong three times in the same way, so a row's numbers come from the ledger and the refusal reads the fleet-dark intersection, never the per-stream windows.
- **One difference between the daemon's gap seconds and the archive's is recorded as UNEXPLAINED** rather than given a cause it cannot have — an honest open question in the durable record beats a mechanism that cannot produce the number.
