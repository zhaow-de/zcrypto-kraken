---
status: resolved
---

# The ops node's logs reach Loki but are unusable, and 99.9% of them are by-design noise

## Context — what

Spec `00054` Task 1 put Grafana Alloy on the ops node. Its Task 3 gate proved the **metrics** arrive (8/8 series) and that logs were *present*. It never checked the logs were **usable**. They are not: every ops log stream carries `level=-`, and the volume is ~2000× the NAS's.

Measured 2026-07-16, one hour, via the Loki datasource proxy:

| | lines/hour |
|---|---|
| `{host="ops"}` — all containers | **16,309** |
| `{host="ops", container="zcrypto-ops-liquidations"}` | 16,269 |
| …of which contain `"dropping"` | **16,249** |
| `{host="nas"}` — all containers | **8** |

## Why this matters

Four distinct defects, three of them introduced by spec `00054` Task 1:

1. **(MINE) Both `loki.process` parse stages are dead on ops.** `infra/ansible/roles/ops/files/config.alloy` was written by mirroring `infra/nas/config.alloy` and the selectors were copied **verbatim**:
   - `selector = "{container=\"archive-pull\"}"` — **ops has no such container**. Ops's archive-pull is a *systemd unit* running `docker run --rm`, not a long-lived container. This stage can never match.
   - `selector = "{container=\"alloy\"}"` — ops's Alloy is labelled **`alloy-alloy`** (compose project `alloy` + service `alloy`), so the logfmt stage can never match either.

   Consequence: no `level` label on any ops stream (confirmed: `level=-` on all five, vs `level=INFO` on both NAS streams); the entry timestamp is Docker's capture time rather than the application's own; and **an ERROR-logs alert for ops could never fire** — the NAS has exactly such a rule (`NAS · archive-pull ERROR logs`), and the ops equivalent would be decorative. That is [[T0052]]'s lesson one level up: the gate proved arrival, not usefulness.

2. **(MINE) Ephemeral `docker run --rm` containers create unbounded Loki stream cardinality.** `discovery.docker` ships *every* container, and the ops archive-pull script runs `docker run --rm` twice per cycle (reconcile + backfill). Docker names each with a fresh random name, so each run becomes a **new Loki stream, forever**: `distracted_mirzakhani`, `nice_dubinsky`, `elegant_bose` are already there. That is ~2 new streams per hour, ~48/day, growing without bound — and Loki bills on streams.

3. **(MINE) The container-label scheme diverges from the NAS's.** NAS: `archive-pull`, `alloy`. Ops: `zcrypto-ops-liquidations`, `alloy-alloy`. A dashboard selecting `container="alloy"` sees only the NAS's. This must be settled fleet-wide, not per host — see [[T0020]]'s inventory + the deliberate `host`-label asymmetry recorded there.

4. **(PRE-EXISTING, but Alloy now ships it) The liquidations poller warns about its own design.** `zcrypto liquidations-poll` polls Coinalyze every ~5 min and re-submits ~1318 already-seen 1-minute buckets each cycle; `SegmentWriter._admit` / `_hold` then log a **WARNING per dropped event** (`segment_writer.py:488` "dropping replayed event", `:354` "dropping late event"). The poller's own line says it outright: *"poll cycle submitted 1318 closed bucket(s) (**re-submissions are dropped by dedup/floor**)"* — the re-submission is the design, and dedup is the intended mechanism. So the writer warns, ~15,800 times an hour, about the system working as intended. Measured split in one 4.75 h window: **86,846 WARNING vs 87 INFO** — 99.9% of the log. Real warnings are invisible in that, which is the actual cost. Note this warning is *correct* for the capture daemon (a WS resubscribe replay is worth knowing about); it is wrong only for the poll-and-dedup path.

## Findings so far

- The poller has run since 2026-07-15 22:11 with `RestartCount=0`; the noise is not new and is not caused by the cutover. The apparent "started 17:48" is a **log-rotation artifact** — `json-file` keeps 10 MB × 3, and at ~18k lines/h that is all the history there is.
- Nothing was dropping these lines before because **nothing was scraping ops at all** — that is what Task 1 changed. The noise was always there; it only started costing money and hiding signal tonight.
- The NAS is unaffected and correct: its selectors match its actual container names.

## Done so far

The infra half — defects 1–3 above, plus the alert gap they implied — is done and **deploy-verified** (commits `8fc7b73`, `357ddb2`, `29370e6`, branch `feat/ops5-offload`):

- **Parse stages fixed** via a compose-service-label-first scheme (`8fc7b73`): `container` derives from the compose *service* label (stable, no project prefix or replica index), falling back to the docker name for non-compose containers. Verified live: the `liquidations` and `alloy` streams now carry real `level` labels (INFO/WARNING/ERROR) where every ops stream was `level=-` before.
- **All five `docker run --rm` jobs named** (`8fc7b73`), which enabled the second half: the ephemeral containers are **dropped** from Docker discovery and their logs ship via `loki.source.journal` instead (`357ddb2`, hardened `29370e6`) — the journal also carries the host scripts' own gate-decision lines (e.g. `zcrypto-archive-pull: trade backfill failed (exit=2), continuing`), which existed in no container log by construction. Verified live in Loki: `container=zcrypto-archive-pull` streams with parsed levels, including `reconcile complete` CLI lines and script echo lines.
- **Alert coverage closed and provisioned on the live instance** (verified by API read-back: 10 rules in the `zcrypto-ops` group): ERROR logs, two green-when-blind canaries (`log pipeline dead`, `journal transport dead`, both noData=Alerting), and exit-code rules for all four timer jobs.
- **Empirical record of the Docker transport's unfitness for the ephemerals**: a quiet reconcile run shipped 1 line of 1 by timing luck; the structural gaps (host-script lines invisible to Docker; polling discovery vs second-lived containers; `--rm` deleting the log at exit) are architecture, not measurement.
- **The source fix landed (defect 4)** — spec `docs/specs/00055-liquidations-poller-watermark-design.md`, plan `docs/plans/00055-liquidations-poller-watermark.md`, commits `3103d19` (prime per-coin bucket watermarks from the segment tree), `d5abb42` (filter re-submissions at source in `poll_cycle`), `bf5b1fb` (prime at startup and thread through the poll loop), branch `fix/t0060-poller-watermark`: per-coin bucket watermarks primed from disk at startup and advanced in-memory on submit skip already-persisted buckets *before* the writer, so the ~15,800/h `dropping replayed event` WARNINGs stop at source and any surviving dedup drop is genuine signal. The 30 h fetch window, writer dedup, and late-event floor are untouched.
- **Loki ingest volume re-checked (owner-provided Grafana Cloud figures, 2026-07-17)**: Current Billable Logs — Process 621.1 MiB, Write 61.9 MiB, Query 166 MiB against the free tier's 50 GB/month; the ≈1.2 GiB/month pace is ≈2.4% of the cap. Ingest volume is NOT a forcing constraint — the source fix's rationale is signal-to-noise, not cost.
- **Source fix deployed to the ops node and verified by outcome (2026-07-17, attended; PR #143 merged to develop as `090759a`)**. The capture image built from the develop merge — `ghcr.io/zhaow-de/zcrypto-capture@sha256:495c6d15e8174a2a762d1ac7f51135569a991137bc3713e9e284cfba65a46098` (default AVX; the fix confirmed inside: `prime_bucket_watermarks`, the `watermarks` parameter, and the `skipped_at_watermark` log all present) — was staged on ops, the ops role converged to that digest (`--tags ops -e ops_image_digest=…`, re-render only — the role never auto-restarts the poller), then the poller recreated with an attended `docker compose up -d`. Safe for the live redundant-capture drill because the 00055 merge touched only `cli/liquidations` (`cli/capture`/`cli/archive`/`cli/portfolio` byte-identical), so reconcile/verify-replay/panel behaviour was unchanged. **Outcome (3 cycles, 19:17–19:27Z):** `primed bucket watermarks for 10/10 coin(s)`; `dropping replayed event` fell to **0** (was 122 in the prior 15 min on the old image); the new `poll cycle: submitted=N skipped_at_watermark=M` line carried the counts (cycle 1 `submitted=0 skipped=2030` fully caught up from disk, cycles 2–3 `submitted=9`/`8` proving continued live ingestion, ~2020+ skipped each); `restarts=0`, 0 errors. All four T0060 defects are now closed at source and deploy-verified.
