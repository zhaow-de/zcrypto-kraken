# Gate — the shadow-concordance export on the NAS

Every signal below comes from one step: the NAS archive-pull loop (`infra/nas/pull-entrypoint.sh`) pulls the engine journal from the engine host with `zcrypto archive pull --no-verify`, which delegates hashing to the replay, then runs `zcrypto engine gate-export --journal-dir /archive/engine-journal --textfile /textfile/gate.prom --cache /tmp/gate-cache.json --lag-fail-seconds 21600` once per loop iteration (`ARCHIVE_PULL_INTERVAL`, 3600 s, plus work), which replays every journaled cycle, scores the ≥ 14-clean-day gate, atomically writes `/volume1/docker/zcrypto-archive/textfile/gate.prom` on the NAS, and pings the healthchecks.io `zcrypto-gate-verify` dead-man. The NAS Alloy scrapes that textfile and ships it, so **every one of these numbers is about the engine's journal but is published by the NAS** — when the NAS telemetry plane is dark (`zcrypto-alloy-dark-nas`) all five rules below are blind, and a page carrying no value means the series is gone rather than the number being bad.

`README.md` beside this file is the index, and states what belongs in a runbook at all.

______________________________________________________________________

<a name="zcrypto-gate-streak-reset"></a>

## zcrypto-gate-streak-reset — ALERT

### What you are seeing

A **warning** Grafana alert, `Gate · streak reset`: `delta(zcrypto_gate_streak_days[6h])` went negative, i.e. the count of consecutive clean complete UTC days the engine's journal has accumulated dropped. The value on the page is the size of the drop in days. Panel 502 on the `zcrypto-integrity` board carries the streak itself beside it. `noDataState` is `OK` here — a vanished series is `zcrypto-gate-exporter-stale`'s job, not this rule's.

### What it means

The exporter re-scored the mirrored journal and the most recently completed UTC day was not clean, so the ≥ 14-day clock restarted at 0.

A day is clean only when all six 4-hourly cycles (00/04/08/12/16/20 UTC) are present *in the mirror the NAS holds*, each cycle's `completed_at` falls inside `[boundary, boundary + 30 min]`, and each replays to the journaled targets. `evaluate_gate` (`cli/engine/concordance.py`) resets the streak on any of five reasons and reports the most recent one: `missing cycle`, `late cycle (outside the 30-minute freshness window)`, `validation failed (schema / boundary invariant)`, `hash mismatch (corrupt evidence)`, `compare mismatch`. A day becomes evaluable only once its 20:00 cycle's 30-minute window has elapsed, so a break appears in the export run after **20:30 UTC**, not at the failing boundary.

**The streak is recomputed from scratch on every run — it is not a stored counter — so a mirror that is merely LATE reads exactly like a broken day.** If the 20:00 cycle has not been rsynced by the time the export runs after 20:30, that day scores `missing cycle`, the streak drops to 0, and the next run after the pull lands restores it. A page that resolves within a pull period or two, with the engine host's own journal showing all six cycles, was mirror lag and nothing broke. This is the single most likely cause and the cheapest to rule out — do step 1 first.

Nothing about live L2 capture or the archive is implicated by this rule. It says the trading-authorisation evidence has a hole, not that data was lost.

### What to do

1. **Name the break, from the mirror, before touching anything.** From the workstation, over the read-only NFS mount (never write through it):
   `uv run zcrypto engine report --journal-dir /mnt/zhao-crypto/engine-journal`
   It prints the outcome tally, the streak, gate MET/not-met, and `last failure: <ISO boundary> -- <reason>`. This is a full replay with no cache, so it costs minutes and grows with the journal — that is the point: it is an independent re-score, not a read of the same cached verdict.
2. **Cross-check the engine host's own copy — it is authoritative, the NAS holds a replica.** `ssh zcrypto`, then `ls -l /var/lib/zcrypto-engine/journal/$(date -u +%F)/` and the previous day's dir. Six `cycle-HH.json` and no `failed-cycle-HH.json` on the engine while the mirror is short ⇒ **mirror lag or a stuck journal pull**; go to `zcrypto-gate-pull-lag` and stop here.
3. **A `failed-cycle-HH.json` sidecar on the engine host is an engine-side operational failure, not evidence corruption.** Its `reason` is `refresh_deadline` (the store's settle-verify refresh missed boundary + 25 min) or `stale_pair` (a pair's raw series did not advance against the boundary invariant). Read the engine's own line: `sudo docker logs --since 48h zcrypto-engine 2>&1 | grep 'run_cycle:'` — it carries the boundary, the reason and the offending pairs. No orders were intended for that boundary.
4. **`hash mismatch` or `validation failed` is evidence corruption on the copy that was scored** — follow `zcrypto-gate-mismatch` below; it is the rule that owns that path and it will normally be firing too.
5. **`late cycle` means the engine ran but finished outside its 30-minute window.** Check the boundary's `completed_at` in `cycle-HH.json` on the engine host and whether the engine restarted around it (`sudo docker inspect --format '{{.State.Status}} {{.RestartCount}}' zcrypto-engine` — scoped to those fields; never inspect the whole config or the container env on this host, it carries the live trade key).
6. **Expect the healthchecks.io `zcrypto-gate-verify` check to go red too, and to stay red for at least a day.** The ping is clean only when `streak > 0` or no complete day has ever been evaluable; after a break it pings `/fail` on every run until a fresh clean day accrues. A Grafana page with no hc.io page (or the reverse) is itself information — the two domains are independent and normally agree here.
7. **Do not restart or converge anything to clear this.** The rule self-resolves as the 6 h window rolls past, whether or not the cause was fixed; resolution is not repair. Record the boundary and the reason — the alert is not a record of what broke.

### Retire when

`zcrypto-gate-streak-reset` is absent from `infra/grafana/alerts.yaml`, or `_write_prom_textfile` in `cli/engine/command.py` no longer emits `zcrypto_gate_streak_days`.

______________________________________________________________________

<a name="zcrypto-gate-mismatch"></a>

## zcrypto-gate-mismatch — ALERT

### What you are seeing

A **critical** Grafana alert, `Gate · mismatch in the last day`: `increase(zcrypto_gate_mismatch_total[1d]) > 0`. Panel 502. `noDataState` and `execErrState` are both `Alerting`, so **a page with no value is the exporter or the NAS telemetry plane being gone**, not a mismatch — that is the same fault `zcrypto-gate-exporter-stale` and `zcrypto-alloy-dark-nas` page for, and all three firing together is one incident.

### What it means

`zcrypto_gate_mismatch_total` is **every not-clean journaled cycle in the whole retained journal**: replay hash mismatches, records that failed validation or could not be read, *compare* mismatches (the replay recomputed different targets), and `failed-cycle-*.json` sidecars. The rule's own summary says "replay mismatch/validation failure", which is **narrower than the code**, which sums `counts.mismatches + counts.validation_failures + counts.sidecar_count` and gates the ping on the streak instead; read the list above, not the summary.

**The metric is a per-run RECOUNT over the whole journal, not a monotonic counter**, and the consequences change how you read this page:

- **It steps once and stays.** One new not-clean cycle raises the total permanently while that cycle is in the journal. `increase()` sees the step, fires, and then **self-resolves ~24 h later with the fault untouched**. Silence tomorrow is not repair.
- **A repair can re-page you for the thing you just fixed.** The value can fall — re-fetch a corrupted parquet and the count drops — and PromQL treats any decrease in an `increase()` argument as a counter reset, adding the pre-reset value back. So a successful repair can synthesize a positive increase inside the window. **Confirm state by VALUE (`zcrypto_gate_mismatch_total`), never by whether the alert is firing.**
- **A rise is not necessarily today's cycle.** The count spans every day the mirror retains; the journal pull is `rsync -a` with no `--delete`, so the NAS mirror never drops a day even though the engine host prunes at 60 days.

Every one of those four kinds breaks the clean-day streak, so `zcrypto-gate-streak-reset` follows at the next day-close if it has not already fired, and the hc.io `zcrypto-gate-verify` check goes red on the same run.

### What to do

1. **Read the value, not the alert state**, from the workstation: `uv run python infra/scripts/grafana-query.py 'zcrypto_gate_mismatch_total' 'zcrypto_gate_streak_days' 'time() - zcrypto_gate_export_timestamp_seconds'`. `(no series)` is a FAIL, never a zero — it means the exporter or Alloy is gone; go to `zcrypto-gate-exporter-stale`. An export age over 7200 s says the same.
2. **Name the offending boundary**: `uv run zcrypto engine report --journal-dir /mnt/zhao-crypto/engine-journal` prints the tally (`N mismatch(es), N validation failure(s), N failed cycle(s) (sidecars)`) and `last failure: <ISO boundary> -- <reason>`. **There is no log line naming a bad cycle** — `_replay_one` classifies the exception silently — so `report` is the only naming mechanism, and it names the most recent break only.
3. **If the count exceeds what `report` names, bisect with a scratch journal root.** Snapshot paths in a record are journal-relative, so a copied day-dir replays correctly on its own: `mkdir -p /tmp/j && cp -a /mnt/zhao-crypto/engine-journal/<YYYY-MM-DD> /tmp/j/ && uv run zcrypto engine report --journal-dir /tmp/j`. Read the **counts** line, not the streak — a single day is usually not evaluable as a complete day, but the per-record tally is computed over every record regardless.
4. **Sidecars are an engine-side failure and need no repair here.** `ls /var/lib/zcrypto-engine/journal/<YYYY-MM-DD>/failed-cycle-*.json` on `ssh zcrypto`, and `sudo docker logs --since 48h zcrypto-engine 2>&1 | grep 'run_cycle:'` for the reason (`refresh_deadline` / `stale_pair`) and the offending pairs. The count stays raised for as long as the sidecar exists; that is correct, the day genuinely was not clean.
5. **A hash mismatch or unreadable snapshot on the mirror is a transport/media fault — and it will not self-heal.** The journal pull runs `rsync -a` with no `--checksum`, so its size+mtime quick-check **never re-transfers a file that was corrupted in place**. Compare the boundary's snapshot files against the engine host, then on the NAS (`ssh nas`) delete the bad file under `/volume1/ZhaoCrypto/engine-journal/<YYYY-MM-DD>/snapshots/cycle-<HH>/` so the next loop re-fetches it. **This is a deliberate, attended deletion inside custody** — the engine host is authoritative for the journal, so confirm the file exists there before removing the mirror's copy, and do it over ssh on the NAS, never through the NFS mount.
6. **After repairing evidence, discard the exporter's scoring cache or the gate stays red for up to a rotation** — a mismatch outcome is itself cached. `ssh nas`, then `sudo /usr/local/bin/docker exec zcrypto-archive-pull rm -f /tmp/gate-cache.json`. The next run re-verifies from cold; see `zcrypto-gate-cache-reverify-stalled` for what that costs.
7. **A `compare mismatch` is neither corruption nor an engine failure and deserves its own stop.** It means the committed builder no longer reproduces targets the journal recorded — an engine image or model change reaching back over old cycles. Do not repair evidence: establish which cycles moved and since when, and treat the gate's verdict as unsafe to read until that is answered.

### Retire when

`zcrypto-gate-mismatch` is absent from `infra/grafana/alerts.yaml`, or `_write_prom_textfile` in `cli/engine/command.py` no longer emits `zcrypto_gate_mismatch_total`.

______________________________________________________________________

<a name="zcrypto-gate-pull-lag"></a>

## zcrypto-gate-pull-lag — ALERT

### What you are seeing

A **critical** Grafana alert, `Gate · journal pull lag high`: `zcrypto_gate_journal_pull_lag_seconds > 21600` (6 h). Panel 503. `noDataState: Alerting` — **a page with no value means the metric was omitted or the series is gone**, and the metric is omitted only when the journal the exporter read was **empty**, so a valueless page says the pull destination is empty or unreadable (or the exporter/Alloy is dead).

### What it means

The metric is `now − the newest cycle_ts anywhere in the mirrored journal`, counting **failed-cycle sidecars as well as successes** — so any artifact the engine writes at a boundary resets it. Its floor is therefore the engine's own 4-hourly cadence, not pull health: measured over the **~14 days** available — the platform retains 14 d, so the derivation's `[30d]` selector returned that same window, and the metric had only existed since 2026-07-12 — the ceiling was **14 767 s (4.10 h)**, p99 14 512 s, 175 samples above 4 h and **zero above 4.5 h**. Read that ceiling as a **lower bound** on the true one. The 21600 s bar is ceiling + one worst-case missed cycle + margin, derived in the rule's own comment and archived `T0069`; it is deliberately in lockstep with `--lag-fail-seconds 21600` in `infra/nas/pull-entrypoint.sh`, which gates the hc.io ping — **change them together or the two paging domains disagree**.

Firing means no new journaled artifact has reached the NAS for over 6 h. Two causes, and this metric cannot tell them apart on its own: the **engine** stopped producing boundaries, or the **pull** stopped delivering them. A genuinely stalled pull grows this without bound, so detection costs about an hour, never correctness.

The hc.io `zcrypto-gate-verify` check takes `/fail` on the same run, so expect a healthchecks.io notification alongside this page.

### What to do

1. **Split engine from transport first — it decides everything after.** `ssh zcrypto`, then `ls -l /var/lib/zcrypto-engine/journal/$(date -u +%F)/` and the previous day. Fresh `cycle-HH.json` (or `failed-cycle-HH.json`) at the last boundary ⇒ the engine is fine and the **pull** is the fault; nothing there ⇒ the **engine** is the fault.
2. **Engine-side**: `sudo docker inspect --format '{{.State.Status}} {{.RestartCount}}' zcrypto-engine` (those fields only — never the container's env or full config on this host, it holds the live Kraken trade key), then `sudo docker logs --since 12h zcrypto-engine 2>&1 | tail -50`. Cycles run at 00/04/08/12/16/20 UTC plus ~90 s settle, so measure lateness against the boundary, not against the clock.
3. **Pull-side**: `ssh nas`, then `sudo /usr/local/bin/docker logs --since 12h zcrypto-archive-pull | grep -E 'journal pull failed|archive pull complete \(no verify\)'`. The journal pull logs `archive pull complete (no verify) source=... dest=...` on success and `journal pull failed (source=... dest=...)` at ERROR on failure; the loop continues either way. Note the `NAS · archive-pull stalled (dead-man)` rule matches `pull complete ... failed=0`, which the **capture and ops channels** also emit — so it stays green while the journal channel alone is broken. Its silence proves nothing here.
4. **If nothing is logged at all, the loop itself is stuck**: `sudo /usr/local/bin/docker inspect --format '{{.State.Status}} {{.RestartCount}}' zcrypto-archive-pull`, then `sudo /usr/local/bin/docker logs --since 6h zcrypto-archive-pull | tail -50`. A last line hours old with no successor is a hung step — the loop has no per-step timeout. Restarting is the fix: `ssh nas`, `cd /volume1/docker/zcrypto-archive && sudo /usr/local/bin/docker compose restart archive-pull` (the entrypoint traps TERM, so the stop is graceful). A restart costs the in-flight pull and nothing else — it does **not** discard the scoring cache.
5. **Check the destination is actually populated**, especially on a valueless page: `ls -l /volume1/ZhaoCrypto/engine-journal/ | tail` on the NAS. An empty tree means the pull has never succeeded — an ssh/key/known-hosts failure on the `sync_journal` channel, which shows up as the `journal pull failed` line above.
6. **Confirm recovery by value, not by the alert clearing**: `uv run python infra/scripts/grafana-query.py 'zcrypto_gate_journal_pull_lag_seconds'` back under ~14 500 s after the next pull period, and the hc.io `zcrypto-gate-verify` check UP again.

### Retire when

`zcrypto-gate-pull-lag` is absent from `infra/grafana/alerts.yaml`, or `_write_prom_textfile` in `cli/engine/command.py` no longer emits `zcrypto_gate_journal_pull_lag_seconds`. The 21600 figure retires only together with `--lag-fail-seconds 21600` in `infra/nas/pull-entrypoint.sh`.

______________________________________________________________________

<a name="zcrypto-gate-exporter-stale"></a>

## zcrypto-gate-exporter-stale — ALERT

### What you are seeing

A **critical** Grafana alert, `Gate · exporter stale`: `time() - zcrypto_gate_export_timestamp_seconds > 7200` (2 h). Panel 503. `noDataState: Alerting` — a page with no value means the series itself is gone (textfile missing or unreadable, or the NAS Alloy dark).

### What it means

That timestamp is written only at the end of a **successful** textfile write. When `gate-export` aborts — unreadable journal, unwritable textfile — nothing is written and the previous file keeps its old timestamp, so this age climbs. Two pull periods have now passed with no successful export.

**Every other gate number is frozen at its last value while this fires.** `zcrypto-gate-mismatch`, `zcrypto-gate-pull-lag` and `zcrypto-gate-streak-reset` are all reading stale figures — their being quiet means nothing until this clears, and `zcrypto-gate-mismatch` will normally be firing valueless alongside it. **Clear this one first; triage the others afterwards.**

The hc.io `zcrypto-gate-verify` check stops receiving pings at the same moment and pages by silence after its grace, so the two independent domains agree on this fault. If Grafana pages and hc.io does not, suspect the ping path rather than assuming the export is fine.

### What to do

1. **Is the loop alive?** `ssh nas`, then `sudo /usr/local/bin/docker inspect --format '{{.State.Status}} {{.RestartCount}}' zcrypto-archive-pull` (those fields only) and `sudo /usr/local/bin/docker logs --since 3h zcrypto-archive-pull | tail -50`. A last line hours old with no successor is hung: `cd /volume1/docker/zcrypto-archive && sudo /usr/local/bin/docker compose restart archive-pull`. That restart preserves the scoring cache, so it costs one pull period, not a cold replay.
2. **Is the export failing?** `sudo /usr/local/bin/docker logs --since 6h zcrypto-archive-pull | grep -E 'gate-export failed|could not write gate textfile|gate-export cache'`. Every `gate-export` failure reports through one ERROR line — the loop logs `gate-export failed (dest=...), continuing` and never exits. Print the log's line count before trusting an empty grep; `--since` needs a duration or a full timestamp, and a mis-parsed one yields empty output that reads like a clean bill.
3. **`could not write gate textfile`** ⇒ the collector directory. `ls -ld /volume1/docker/zcrypto-archive/textfile` — it must exist, be owned `1000:1000` and be mode `0775` (it is a manual bootstrap step, not converged by the role) — and `df -h /volume1` for a full volume (see also `NAS · /volume1 free space low`).
4. **Is it just slow?** Read `zcrypto_gate_export_duration_seconds` on panel 503. A **cold** run after a container recreate replays the whole journal: measured **3505 s on 2026-08-28**, and it grows with the journal — two such runs in a row can hold this alert up on their own. A warm run is a fraction of that. If a converge or re-pin just recreated the container, this is expected and self-clears; re-read the newest duration rather than trusting that figure.
5. **Is the file fresh but unshipped?** `ls -l --time-style=full-iso /volume1/docker/zcrypto-archive/textfile/gate.prom` and `cat` it — it holds only gate metrics, no secrets, and it is the ground truth when Grafana is dark. A recent mtime means the fault is Alloy: check whether `zcrypto-alloy-dark-nas` is firing, `sudo /usr/local/bin/docker logs --since 1h grafana-alloy | tail`, and `uv run python infra/scripts/grafana-query.py 'node_textfile_scrape_error{host="nas"}'` — a 1 means the collector rejected a file in that directory, which the other archive-pull `.prom` files also share. Restarting Alloy is `cd /volume1/docker/zcrypto-archive && sudo /usr/local/bin/docker compose restart alloy`.
6. **A full converge (`-e nas_apply_compose=true`) is an attended action** — it runs `compose up -d` plus a restart of both containers, and a recreate discards the scoring cache and buys a cold replay. Do not reach for it to clear this alert; a targeted `compose restart archive-pull` is the cheap move.
7. **Confirm by value**: `uv run python infra/scripts/grafana-query.py 'time() - zcrypto_gate_export_timestamp_seconds'` under 3600 after the next loop, and `zcrypto-gate-verify` UP on healthchecks.io.

### Retire when

`zcrypto-gate-exporter-stale` is absent from `infra/grafana/alerts.yaml`, or `_write_prom_textfile` in `cli/engine/command.py` no longer emits `zcrypto_gate_export_timestamp_seconds`.

______________________________________________________________________

<a name="zcrypto-gate-cache-reverify-stalled"></a>

## zcrypto-gate-cache-reverify-stalled — ALERT

### What you are seeing

A **critical** Grafana alert, `Gate · cache re-verification stalled`: `zcrypto_gate_cache_oldest_verification_age_seconds > 259200` (3 days), held for 15 m. Panel 504 shows the four cache numbers. `noDataState` is `OK` here, deliberately unlike its siblings — the metric is legitimately absent whenever the cache is inactive or empty, which includes the first run after a container recreate.

### What it means

**This rule is the only witness that the journal's parquet bytes are still being re-read at all.** The scoring cache skips `replay_cycle` on a fingerprint hit, and that replay is the single place the bytes are re-hashed — the journal pull runs `--no-verify` and delegates verification to it. So each run additionally **force-replays a rotating ~1/24 slice** regardless of a cache hit: a cycle's slice is `sha256(cycle_ts) % 24`, a permanent property of the cycle, and a run re-verifies the slice matching `now.hour % 24`. The whole journal is therefore re-verified about daily, and the 3-day bar is roughly three sweeps of slack. Because the fingerprint digests the `content_hash` the record *claims*, not a fresh hash of the file, a cache hit on an altered file would be served as a PASS forever without this rotation.

**The failure direction is a false PASS on the artifact that authorises real-money trading, and every other signal stays green while it happens** — `zcrypto_gate_status` 1, the streak climbing, `mismatch_total` 0, the exporter fresh. Treat the gate verdict as unverified until this clears. The threat model is bit-rot on the RAID, partial or interrupted writes, and anything holding group-write on the deliberately `0775`/`0664` share — not primarily malice.

Mechanisms, in order: the exporter has not run successfully for days (then `zcrypto-gate-exporter-stale` is firing too — clear that first and this follows); the cache file cannot be saved (`save_cache` logs a warning and **continues**, so a full disk presents as a working cache with a quietly ageing age); or the rotation itself stopped replaying, which would show as `zcrypto_gate_cache_replayed` at 0 with `hits` at the full count, run after run.

### What to do

1. **Read the four numbers plus the exporter's age in one call**: `uv run python infra/scripts/grafana-query.py 'zcrypto_gate_cache_replayed' 'zcrypto_gate_cache_hits' 'zcrypto_gate_cache_invalidated' 'zcrypto_gate_cache_oldest_verification_age_seconds' 'time() - zcrypto_gate_export_timestamp_seconds'`. An export age over 7200 s means this is downstream of `zcrypto-gate-exporter-stale`; fix that and re-read. `(no series)` is a FAIL, not a zero.
2. **`replayed` = 0 across consecutive runs with `hits` at the full count is the rotation not firing** — the one shape a fast, healthy-looking warm run also has, which is why the counters and not the runtime are what prove it engaged. Look for the save warning and the disk: `ssh nas`, `sudo /usr/local/bin/docker logs --since 24h zcrypto-archive-pull | grep -iE 'save_cache|gate-export cache'`, and `df -h /volume1`.
3. **The reset — and it is one command.** The cache lives at `/tmp/gate-cache.json` **inside the container, on none of its mounts** (`/archive`, `/keys`, `/app/zcrypto.toml`, `/textfile`, `/opt/pull-entrypoint.sh`), sited there deliberately because the NAS and ops run different polars runtimes and a shared cache would be mutually poisonable. Delete it and the next run re-verifies everything and re-stamps every verification timestamp:
   `ssh nas`, then `sudo /usr/local/bin/docker exec zcrypto-archive-pull rm -f /tmp/gate-cache.json`.
4. **Know what that costs before you run it.** The next run is a **cold replay of the whole journal — measured 3505 s (~58 min) on 2026-08-28**, and the figure grows with the journal, so read `zcrypto_gate_export_duration_seconds` for the current one rather than trusting that number. The hc.io `zcrypto-gate-verify` dead-man tolerates that replay, so the delayed ping is not itself a paging event — re-check that if the journal has grown much further. The metric disappears while the cache is empty (the rule reads `OK`, which is why `noDataState` is not `Alerting`) and returns on the following run.
5. **A `docker compose restart` does NOT clear the cache.** `/tmp` is the container's writable layer with no `VOLUME` or `tmpfs` over it, so a restart preserves the file; only a **recreate** — `compose up -d` with a changed service config, e.g. an image re-pin under `-e nas_apply_compose=true` — discards it, and that is an attended converge, not a triage step. A `replay_fingerprint` change invalidates the cache wholesale without a recreate, which shows as `zcrypto_gate_cache_invalidated` = 1 and buys the same cold replay.
6. **Never point `--cache` at `/archive` or any path both hosts reach**, whatever the disk pressure — that is the poisoning the ephemeral siting exists to prevent.
7. **While this is unresolved, do not read the gate as evidence.** If a go/no-go depends on it, re-score independently: `uv run zcrypto engine report --journal-dir /mnt/zhao-crypto/engine-journal` from the workstation runs with **no cache at all** and re-replays every cycle, which is exactly the guarantee this alert says you have lost.

### Retire when

`zcrypto-gate-cache-reverify-stalled` is absent from `infra/grafana/alerts.yaml`, or `infra/nas/pull-entrypoint.sh` no longer passes `--cache` to `zcrypto engine gate-export` — without the cache there is nothing to rotate and the metric is never emitted.
