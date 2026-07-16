---
status: open
ripe_when: immediately — the ops node is shipping ~390k unparsed lines/day to Loki right now, and an ERROR-logs alert for it could never fire
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

## Suggested next steps

- **Fix the selectors** (small, obvious): scope the Python stage to the containers ops actually runs. Prefer matching on something stable rather than a literal name — the `docker run --rm` containers have random names by construction, so a name-based selector cannot work for them. Consider deriving the label from the image, or dropping ephemeral containers entirely (next item).
- **Decide what to do about `docker run --rm` streams.** Either give them a stable `--name`, or drop them in `discovery.relabel` (they are one-shot jobs whose output already lands in the systemd journal, which is the natural place to read them), or set a Docker log-driver on those runs. Do **not** leave unbounded random stream names shipping to a billed backend.
- **Stop warning about by-design re-submissions.** The cleanest fix is at the source: give the poll path a floor/watermark so it does not re-submit what it has already written, rather than submitting and dropping. Failing that, log the dedup drop at DEBUG on the poller's kinds while keeping WARNING for the capture daemon's kinds — the two have opposite meanings. **Do not simply filter it in Alloy**: that hides the volume without fixing it, and the writer would still be doing 15,800 pointless dedup lookups an hour.
- **Re-check the Loki ingest budget** once the above lands — the free tier has a monthly ingest allowance and ~390k lines/day from one container is worth knowing about before it bites. Then decide whether the gate for "observability is live" should include *parsed and useful*, not just *arriving* — the whole point of [[T0052]].
