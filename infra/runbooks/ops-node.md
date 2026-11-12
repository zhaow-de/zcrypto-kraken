# Ops node — its timers and units

You are here because **an alert fired in Slack**, or because **a guard in the code pointed you here**. Find the section whose anchor matches the alert `uid` or the anchor in the comment that sent you. Each section is written to be actioned without opening any other document.

Everything below is produced on one host, `zcrypto-ops`, reached as `ssh hp`. Its project timers are this role's, each firing a `Type=oneshot` unit — rendered from `infra/ansible/roles/ops/templates/*.timer.j2`, plus `zcrypto-clock-offset.timer` from its `files/` — beside `zaccess-probe-ops.timer`, which the `access_ops` role owns. `grafana-watchdog`, which probes both nodes, and `zcrypto-clock-offset` are plain scripts; the rest run the repo CLI as an ephemeral, digest-pinned `docker run --rm --pull never`. All but `grafana-watchdog` publish a node-exporter textfile under `/var/lib/zcrypto-ops/textfile/`; the host's Alloy scrapes those files and ships their series to the observability node, and ships the units' journal lines to its Loki. Every rule in this file reads one of those textfile series, or those log lines, or the host's own load average and filesystems. The host has **no `uv`** — it runs containers, not the repo CLI.

`README.md` beside this file states what belongs in a runbook at all; an alert or a guard names a section by file and anchor, and a procedure is found by its file and heading.

______________________________________________________________________

<a name="zcrypto-ops-archive-pull-stalled"></a>
<a name="zcrypto-ops-archive-pull-exit-nonzero"></a>

## zcrypto-ops-archive-pull — ALERT

### What you are seeing

Two Grafana alerts on the same unit, `zcrypto-archive-pull.service` — despite the name it pulls nothing; it is the **overlay-writer cycle** (reconcile + the daily trade backfill), and the unit and metric names are historical because the alert rules are provisioned against them.

- **`Ops · archive-pull stalled (dead-man)`** (uid `zcrypto-ops-archive-pull-stalled`) — **critical**. `time() - ops_archive_pull_last_success_timestamp > 10800` (3 h), `for: 5m`, `noDataState: Alerting`. No series at all is itself the alarm: the host, the timer, or Alloy is gone.
- **`Ops · archive-pull non-zero exit`** (uid `zcrypto-ops-archive-pull-exit-nonzero`) — **warning**. `ops_archive_pull_exit_code > 0`, `for: 5m`, `noDataState: OK`. The cycle ran and its reconcile step failed.

### What it means

`zcrypto-archive-pull.timer` fires at `*-*-* *:12,42:00` with `Persistent=true`, so 3 h is about six missed half-hourly ticks. Each tick reads the NAS's canonical trees through the read-only NFS automount at `/mnt/zhao-crypto` and writes the overlay locally under `/var/lib/zcrypto-ops/capture-reconciled`.

**The two rules partition the failure, and a gate-skip is in neither of them.** The cycle opens with a fail-closed gate: it reads `/mnt/zhao-crypto/.pull-status` — written by the NAS right after its own capture pulls — and skips reconcile *and* backfill unless `capture_ok=1`, `secondary_ok=1`, and `ts_epoch` is younger than 14400 s and no more than 600 s in the future. A skip is a state, not a fault: it exits 0, bumps `ops_archive_pull_last_success_timestamp`, and logs `writer cycle SKIPPED (fail-closed gate): <reason>` at WARNING to the journal. So **stalled firing is never a skip** — it is the unit itself not completing.

`rc=1` is set in exactly one place in `infra/ansible/roles/ops/templates/archive-pull.sh.j2`: the reconcile `docker run` failing. A trade-backfill failure leaves rc at 0 and pages through its own exit-code rule instead.

**A persistent skip pages nowhere here.** A skipped cycle never rewrites `reconcile.prom`, so `zcrypto_reconcile_last_success_timestamp_seconds` ages until `Reconciler · exporter stale` (uid `zcrypto-reconcile-exporter-stale`, critical at 3 h, its section in `infra/runbooks/ops.md`) pages. The same rule is what escalates a reconcile step that keeps failing — the CLI publishes no textfile on a failed cycle, so exit-nonzero at warning is the early notice and exporter-stale at critical is the follow-up.

**The cycle feeds its check on the dead-man service on rc 0** — `curl` to `ops_archive_pull_healthcheck_url` at the tail of `infra/ansible/roles/ops/templates/archive-pull.sh.j2`, with gate-skips deliberately included, so that dead-man measures this unit's own liveness and not the upstream's. The URL is rendered from the project's ping key and the slug `zcrypto-archive-pull`, in `infra/ansible/host_vars/zcrypto-ops/vars.yml`.

### What to do

1. **`ssh hp`, then read the timer and the unit**: `systemctl list-timers zcrypto-archive-pull.timer` and `systemctl status zcrypto-archive-pull.service zcrypto-archive-pull.timer`. A `Persistent=true` catch-up run right after a reboot is expected, not a finding.
2. **Read the journal, and prove you read something**: `sudo journalctl -u zcrypto-archive-pull.service --since -4h --no-pager | wc -l` first, then the same without `wc` — an unprivileged `journalctl -u` prints `-- No entries --` under a hint to rerun with `sudo`, which is a permissions artifact and not an idle unit. Look for `writer cycle SKIPPED (fail-closed gate):` and `reconcile failed, continuing`.
3. **If it is a skip, the fault is upstream.** `cat /mnt/zhao-crypto/.pull-status` and `date -u +%s`, and compare against the gate's conditions above. A not-clean or stale status means the NAS's own capture pulls are broken — go to the NAS's rules and its `infra/nas/pull-entrypoint.sh` logs. **Do not hand-edit `.pull-status`**: it is the gate's ground truth, and the gate exists to refuse a frozen view.
4. **If reconcile failed, look for a leftover container first.** `sudo docker ps -a --filter name=zcrypto-reconcile` — after a dockerd crash the leftover makes the next run fail on the name conflict; `sudo docker rm zcrypto-reconcile`. Then `sudo systemctl status docker`.
5. **Check the mount.** `ls /mnt/zhao-crypto/capture-segments | tail`. It is a `soft` NFS automount (`infra/ansible/roles/ops/tasks/main.yml`), so a hung NAS surfaces EIO rather than hanging, and that EIO fails the cycle loudly — the CLI treats a segment it listed and then cannot read as an integrity fact, never as absence, so it cannot ledger a false verdict on that hour (no count command: `tests/test_archive_reconcile_command.py::test_an_unreadable_segment_exits_one_and_never_mints_that_hour`). A failed *listing* is the hole: `scan_hours` (`cli/archive/settle.py`) enumerates the mirrors with a glob, which swallows the EIO, so a directory that answers EIO yields no hours and the cycle reads that slot as absent — and the fail-closed gate reads `.pull-status` at the top of the cycle, so it does not see an EIO that starts mid-cycle.
6. **Check the image.** The run is `--pull never`, so a digest the host never pulled fails every tick that reaches the container: `sudo docker image inspect --format '{{.Id}}' ghcr.io/zhaow-de/zcrypto-capture@<the ops digest from docs/reference/fleet-pins.md>`. A gate-skipped cycle starts no container, so a wrong digest fails nothing and pages nothing through a skip streak. Scope the inspect to the field you need; `CLAUDE.md`'s Secrets rule names the forms that are never run (set: the non-comment lines of the non-Markdown files under `infra/`, `.claude/`, `cli/` — the roles, templates, units, hooks and scripts a command runs from — with the counter itself excluded; the Markdown runbooks and skills, where the form appears as the prohibition's own text, are outside it; count: `infra/scripts/count-list.sh engine-env-forms-invoked`; the ticks that reach the container, no count command: docker's `--pull never` refuses a digest the host lacks).
7. **Re-running is attended.** `sudo systemctl start zcrypto-archive-pull.service`. Reconcile MINTS on this host (`ops_reconcile_mint: true`, `host_vars/zcrypto-ops`), so a re-run writes healed hours into custody rather than costing only time (no count command: `ops_reconcile_mint: true` in `host_vars/zcrypto-ops/vars.yml` holds it); the ledger dedupes, so repeating it does not double-book, but it is a write; it also runs the daily backfill if today's stamp is absent.
8. **Verify by outcome, from the workstation**: `bash infra/scripts/ops-postverify.sh`. Two of its checks are these rules' own operands: `archive-pull exit code`, and `archive-pull freshness (s)` at the stalled rule's own 10800 s. `reconcile freshness (s)` reads `reconcile.prom`'s mtime, which a gate-skip never refreshes. `(no series)` is a FAIL, never a zero (no count command: `tests/test_ops_postverify.py::test_no_series_is_a_fail_never_a_zero`).
9. **Never read "nothing was lost" out of these two rules.** (no count command: an operator's reading of a page is recorded nowhere) They are unit liveness. Loss is booked by the reconciler, and hour H is bookable no earlier than H+2 h, at the next `:12`/`:42` tick after that.

### Retire when

`zcrypto-ops-archive-pull-stalled` and `zcrypto-ops-archive-pull-exit-nonzero` are both absent from `infra/grafana/alerts.yaml`, or `ops_archive_pull_last_success_timestamp` and `ops_archive_pull_exit_code` are no longer written by `infra/ansible/roles/ops/templates/archive-pull.sh.j2`.

______________________________________________________________________

<a name="zcrypto-trade-backfill-stale"></a>
<a name="zcrypto-trade-backfill-exit-nonzero"></a>

## zcrypto-trade-backfill — ALERT

### What you are seeing

Two **critical** Grafana alerts on the daily trade-tape healing step, which runs as the second half of the same `zcrypto-archive-pull.service` cycle.

- **`Trade backfill · last success stale`** (uid `zcrypto-trade-backfill-stale`) — `time() - zcrypto_trade_backfill_last_success_timestamp > 172800` (~2 days), `for: 5m`, `noDataState: Alerting`. The step is daily, so ~2 days is the cadence plus one tolerated miss.
- **`Trade backfill · non-zero exit code`** (uid `zcrypto-trade-backfill-exit-nonzero`) — `zcrypto_trade_backfill_exit_code > 0`, `for: 5m`, `noDataState: OK`.

### What it means

Only the trade tape is affected. Book data — the unbackfillable part — is untouched by this step; it heals Kraken trade rows over the public REST endpoint, and Kraken serves roughly 18 months of them, so there is no urgency cliff.

**The step runs at most once per UTC day, and it does not retry.** It is gated on `/var/lib/zcrypto-ops/.trade-backfill-last-utc-day`, which holds the UTC day and is written **unconditionally, before the run**. A failure therefore costs one attempt per day, not one per cycle: `zcrypto_trade_backfill_exit_code` stays above zero for up to ~24 h, and the metric — not a retry — is what carries the failure.

**Read the exit code as three cases, not two.** The rule's summary names the CLI's own codes: `2` = the primary root does not exist (the NFS view of `capture-segments` is gone), `1` = the sweep completed and recorded errors, its count printed as `errors=<n>` on the summary line. **Any other value came from `docker run` itself and means the container never started** — most often a leftover `zcrypto-trade-backfill` after a dockerd crash, or a digest the host never pulled. The summary does not cover that case; the code does.

**The backfill sits inside the fail-closed gate.** A skipped cycle never reaches this branch and never writes the stamp, so the backfill simply retries on the first non-skipped cycle of that day. Two days of skips will therefore trip `-stale` — but `Reconciler · exporter stale` will have paged many hours earlier, which is the discriminator.

**A backfill failure leaves the unit's rc at 0**, so `Ops · archive-pull non-zero exit` stays quiet for it by design.

`zcrypto_trade_backfill_hours_repaired_after_loss_total` is monotone and carried forward across runs; a partially failed run that still repaired hours still counts them.

### What to do

1. **Read the day's attempt.** `ssh hp`, then `sudo journalctl -u zcrypto-archive-pull.service --since -48h --no-pager | grep -iE 'backfill|SKIPPED'` — the script logs `trade backfill failed (exit=<n>), continuing` at WARNING and replays the CLI's whole output into the journal, including the `errors=` summary line.
2. **Read the stamp and the textfile.** `cat /var/lib/zcrypto-ops/.trade-backfill-last-utc-day` — today's date means today's attempt has already happened. `cat /var/lib/zcrypto-ops/textfile/trade-backfill.prom` for the exit code, last run and last success as published.
3. **Exit 2 → the mount.** `ls /mnt/zhao-crypto/capture-segments`. Treat it exactly as the writer cycle's mount check above.
4. **Exit 1 → read the errors.** Fetch failures against Kraken's REST point at the venue (check its status page and the capture-side venue-status signals); unreadable segments point at the NAS or the mount.
5. **Any other code → clear the container.** (no count command: `backfill_trades` in `cli/archive/command.py` exits 0, 1 or 2) `sudo docker ps -a --filter name=zcrypto-trade-backfill`, then `sudo docker rm zcrypto-trade-backfill`.
6. **To re-run today instead of waiting 24 h** — attended, and it re-runs reconcile in the same cycle:
   ```
   sudo rm /var/lib/zcrypto-ops/.trade-backfill-last-utc-day
   sudo systemctl start zcrypto-archive-pull.service
   ```
   Both steps are safe to repeat — the reconcile ledger dedupes and the backfill is watermarked — but reconcile MINTS here, so repeating it is a write to custody, not a no-op. If the gate is skipping, this run will skip too and change nothing; fix the `.pull-status` cause first.
7. **Verify the metric moved, not the unit's exit status**: `zcrypto_trade_backfill_exit_code` back at 0 and `zcrypto_trade_backfill_last_success_timestamp` advanced, read through `uv run python infra/scripts/grafana-query.py 'zcrypto_trade_backfill_exit_code' 'zcrypto_trade_backfill_last_success_timestamp'` from the workstation. The unit exits 0 on a failed backfill, so `$?` proves nothing here.
8. **Expect the downstream page if this persists.** tape-bars defers any day whose trade tape is not heal-complete and exits 0 while doing so (no count command: `cli/tick/command.py` books it as `days_unhealed`, a deferral, and exits 0), so a stalled healer surfaces next as `Ops · tape-bars not advancing` — `infra/runbooks/ops.md#zcrypto-ops-tapebars-not-advancing`.

### Retire when

`zcrypto-trade-backfill-stale` and `zcrypto-trade-backfill-exit-nonzero` are both absent from `infra/grafana/alerts.yaml`, or `zcrypto_trade_backfill_last_success_timestamp` and `zcrypto_trade_backfill_exit_code` are no longer written by `infra/ansible/roles/ops/templates/archive-pull.sh.j2`.

______________________________________________________________________

<a name="zcrypto-ops-verified-replay-stale"></a>
<a name="zcrypto-ops-verified-replay-exit-nonzero"></a>

## zcrypto-ops-verified-replay — ALERT

### What you are seeing

Two Grafana alerts on `zcrypto-verified-replay.service`, the daily verified-path replay of the engine journal.

- **`Ops · verified-replay stale`** (uid `zcrypto-ops-verified-replay-stale`) — **warning**. `time() - ops_verified_replay_last_success_timestamp > 172800` (48 h = two missed daily cycles), `for: 5m`, `noDataState: Alerting`.
- **`Ops · verified-replay non-zero exit`** (uid `zcrypto-ops-verified-replay-exit-nonzero`) — **critical**. `ops_verified_replay_exit_code > 0`, `for: 5m`, `noDataState: OK`. Critical because a verified-path mismatch means the canonical replay disagrees with what the engine journaled.

### What it means

`zcrypto-verified-replay.timer` fires daily at `05:23` UTC with `Persistent=true`. The unit runs `zcrypto engine replay --path verified --date <day> --journal-dir /nas/engine-journal` in the pinned image, reading the journal through the same read-only NFS mount.

**It is a catch-up loop over a watermark, not a single-day run.** `/var/lib/zcrypto-ops/.verified-replay-watermark` holds the last successfully replayed UTC day; the loop walks watermark+1 through yesterday, capped at 30 days per run.

**`last_success` bumps only when the run is clean AND fully caught up** (`ops_verified_replay_days_behind` at 0). Read `days_behind` on the same panel — it is the discriminator:

- **`days_behind > 0`, exit code 0** — the loop stopped short, for one of three reasons, each logged verbatim — **the first two stop *without advancing the watermark*, the third advances and resumes tomorrow**: the day's directory under `/mnt/zhao-crypto/engine-journal/<day>/` holds no `cycle-*.json` or `failed-cycle-*.json` (`journal has not caught up`); the **successor** day holds none either, so the day may be only partly pulled (`journal freshness unproven` — that successor-day probe stands in for a journal freshness signal, since `.pull-status` attests `capture_ok`/`secondary_ok` and nothing about the journal) (no count command: a day's pull state lives on the NAS, not in the tree); or the 30-day budget ran out (`capped at 30 day(s)`).
- **Exit code non-zero** — a day genuinely mismatched, the run was **refused** before it started, or a day verified but its watermark could not be persisted.

**A refused run touches neither the watermark nor the textfile**, exits 1, and logs its own reason at WARNING (the dead man's silence and `-stale` page it, not `Ops · ERROR logs`): the watermark is not a `YYYY-MM-DD` day, is a shape-valid but nonexistent calendar date, is beyond yesterday (clock skew or a manual edit), or the seed could not be persisted. An **empty** watermark file is the one to know: it parses as *tomorrow*, would skip the loop forever and read fully healthy while doing so — hence the refusal.

**A mismatch is retried nightly and blocks everything after it.** The loop breaks on the first failing day without advancing, so no later day is verified past the gap — which is why `-stale` follows about 48 h behind a persistent `-exit-nonzero`.

The dead-man for this timer is fed only on a clean, fully-caught-up run, so its silence during a stall is consistent with these pages, not a second incident.

### What to do

1. **`ssh hp`, then read the unit and its last three days**: `systemctl status zcrypto-verified-replay.service`, then `sudo journalctl -u zcrypto-verified-replay.service --since -3d --no-pager` — confirm the output is non-empty before reading anything into it. Grep for the three stop messages above and for `WARNING zcrypto.verified-replay`.
2. **Read the watermark and the journal tree.** `cat /var/lib/zcrypto-ops/.verified-replay-watermark`; `ls /mnt/zhao-crypto/engine-journal/ | tail -3`. The day after the watermark **and** its successor must each hold `cycle-*.json` or `failed-cycle-*.json`.
3. **Journal not arriving is a NAS-side finding**, not this unit's. Nothing here can fix a stalled journal pull, and the fail-closed stop is correct behaviour.
4. **Repair a refused run with a tmp+mv write, matching the script** — an in-place truncate is what the script's own comment rules out:
   ```
   printf '%s\n' YYYY-MM-DD | sudo tee /var/lib/zcrypto-ops/.verified-replay-watermark.tmp > /dev/null
   sudo mv /var/lib/zcrypto-ops/.verified-replay-watermark.tmp /var/lib/zcrypto-ops/.verified-replay-watermark
   ```
   Set it to the last day genuinely verified, or delete the file to re-seed from yesterday-1. **Never leave it empty** (no count command: the watermark file lives on ops, and an operator's edit to it leaves no record the tree reads).
5. **Never advance the watermark past a mismatching day to silence the page** — that marks the day verified forever, and the day is exactly the finding (no count command: a hand edit of the host's watermark file is recorded nowhere).
6. **Reproduce a mismatch off-host** from the workstation, which mounts the same export: `uv run zcrypto engine replay --path verified --date <day> --journal-dir /mnt/zhao-crypto/engine-journal`. **A day with no journal artifacts at all exits 0** after printing `no journaled cycles found` — which is why the loop's artifact probes exist, and why a green exit here is not by itself a verified day.
7. **Clear a leftover container.** `sudo docker ps -a --filter name=zcrypto-verified-replay`, then `sudo docker rm zcrypto-verified-replay` — the name conflict alone yields a non-zero exit.
8. **Re-run attended**: `sudo systemctl start zcrypto-verified-replay.service`. One run replays at most 30 days; a deeper backlog resumes the next night, and `-stale` correctly keeps firing until it catches up.
9. **Record a mismatch somewhere durable before the next clean night.** `ops_verified_replay_exit_code` returns to 0 on the next successful day and the evidence goes with it.

### Retire when

`zcrypto-ops-verified-replay-stale` and `zcrypto-ops-verified-replay-exit-nonzero` are both absent from `infra/grafana/alerts.yaml`, or `ops_verified_replay_last_success_timestamp` and `ops_verified_replay_exit_code` are no longer written by `infra/ansible/roles/ops/templates/verified-replay.sh.j2`.

______________________________________________________________________

<a name="zcrypto-ops-vintage-not-recorded"></a>

## zcrypto-ops-vintage-not-recorded — ALERT

### What you are seeing

Two pages on `zcrypto-vintage-record.service`, the free-source vintage recorder, which stores the bytes four free data providers serve, twice a day, so that their later restatements can be measured: a Grafana alert and a healthchecks dead-man check.

- **`Ops · vintage source not recorded`** (uid `zcrypto-ops-vintage-not-recorded`) — **critical**. `time() - zcrypto_vintage_last_ok_timestamp_seconds > 90000` (25 h), `for: 5m`, `noDataState: Alerting`. It fires per source: one instance per source arrives in one message whose label lines name the sources, and a no-data instance names none. No series at all is itself the alarm: the recorder's textfile, the host's Alloy, or the host is gone. A good fetch that ended after 19:57 UTC is counted from 19:57 of its day.
- **`zcrypto-vintage-record`**, the healthchecks dead-man check, which pages from outside Grafana. The recorder's runner pings it when a tick was published, whichever of its sources failed, and on no other run. Its timeout is 90000 s and its grace 21600 s, so it goes down about 31 h after the last published tick, after the 25 h Grafana rule: it is the page that still comes when Grafana is dark, and it means the recorder stopped, crashed before publishing, or could not start its container. Its triage is the same steps below.

### What it means

The source's UTC day has had no good fetch, and at 00:00 UTC that day's snapshot becomes a permanent hole. It is critical because no later tick records the day, whoever caused the miss: the next good tick carries the source's whole history again, so a miss costs that day's snapshot and the first-seen precision of what was new in it. A day whose bodies all graded outcome 2 holds all their bytes, yet it pages until code acknowledges the change.

`zcrypto-vintage-record.timer` fires at 07:37 and 19:37 UTC, and a tick ends by its 20-minute deadline. Each tick publishes one directory, `/var/lib/zcrypto-ops/vintages/record/YYYY/MM/DD/STAMP/`, set to 0555 with its files 0444, even when some or all of its sources failed: its `tick.json` lists each source's fetch, with the answer's `status`, `headers` and `check` — `outcome` 0 for a good fetch, 1 for not fetched with its `reason`, 2 for a body stored whole whose shape changed. A single failed tick does not page: the next good fetch lands about 24 h after the one before the failure. The 19:57 cap keeps a late hand start from carrying the next day's page past that day's midnight, so after the worst case the page comes at about 21:02 UTC, with about three hours left to record the day.

A provider outage lands here exactly like a stopped recorder: the condition books absence, not fault, so triage comes before acting. A provider down for more than a day pages again at the default 4 h re-notify, nights included, until the silence in step 7 is set.

### What to do

1. **`ssh hp`, then triage: read the unit, its journal and the newest tick.** `systemctl status zcrypto-vintage-record.service` and `systemctl list-timers zcrypto-vintage-record.timer`; then `sudo journalctl -u zcrypto-vintage-record.service -n 100 --no-pager` (an unprivileged `journalctl -u` prints `-- No entries --`, a permissions artifact and not an idle unit); then `ls /var/lib/zcrypto-ops/vintages/record/YYYY/MM/DD/` for today's UTC date and `cat /var/lib/zcrypto-ops/vintages/record/YYYY/MM/DD/STAMP/tick.json` for its newest tick, reading each paged source's `check` and `status`. `cat /var/lib/zcrypto-ops/textfile/vintage.prom` shows the gauges as published; its absence is the no-data instance. Then act on what they show, in the steps below.
2. **No tick today: the fault is ours** — the timer, a leftover container or the pinned image. `sudo docker ps -a --filter name=zcrypto-vintage-record`: after a dockerd crash a leftover fails the next run on the name conflict, `sudo docker rm zcrypto-vintage-record`. A crashed tick leaves its directory under `staging/`, which each later tick names in a WARNING: `sudo ls -la /var/lib/zcrypto-ops/vintages/staging/`, read it, then, with the unit inactive in step 1's status read (a running tick's staging directory is its publish in progress), delete it by hand, `sudo rm -rf /var/lib/zcrypto-ops/vintages/staging/STAMP`; a crashed tick was not published, so nothing in `record/` changes. Fix the cause, then `sudo systemctl start zcrypto-vintage-record.service` before 00:00 UTC records the day; the versions table's derive follows that unit on its own.
3. **Outcome 1 with a transport error, a timeout, a 5xx, a 429 or `breaker` on the provider's host: the fault is the provider's.** The tick's `cm-status` body or the provider's status page shows whether it is known. One hand start once the provider answers again, before 00:00 UTC, records the day: `sudo systemctl start zcrypto-vintage-record.service`. Where sources read `breaker` behind one asset whose own query answers 5xx or 429 at each start, or `tick deadline` because another provider's fault used up the tick and that provider has not answered again, a plain hand start meets the same fault: start the sources still owed, less the failing query's own source and the faulted provider's sources, with `sudo /usr/local/sbin/zcrypto-vintage-record --source <id> --source <id> …`, which dials the named sources alone, then `sudo systemctl start zcrypto-vintage-derive.service`. That hand start runs outside the unit, so its lines reach neither the journal nor Loki: keep the `vintage tick published tick=… tick_json_sha256=…` line it prints in that day's operations journal entry (`docs/reference/ops-journal/<YYYY-MM>.md`), since it is that tick's witness, which a restore reads.
4. **Outcome 1 with a 403 or a 404: a contract change, for the owner.**
5. **A `bg-*` source, the one keyed provider (BGeometrics).** Outcome 1 with `no credential`, `malformed credential`, a 401 or a 403 is the key, which the owner rotates in the account and the vault; with `no credential` beside the runner's ERROR naming the token file, the file is absent, unreadable or a directory, and an `--tags ops` converge renders it again. With `credential echoed` or `credential unscannable`, nothing of that answer was stored, and a key found in a stored byte is rotated. With a 429 or `budget exhausted`, the day's 15 requests were spent: read which ticks spent them in the journal, and never start a further tick that day for this source alone, since each start spends four more (no count command: a hand start is an operator act the tree does not record).
6. **Outcome 2: the bytes are stored**, and the check needs a pinned acknowledgment entry in `cli/vintage/sources.py`, which is the owner's call.
7. **Once the failure is triaged as the provider's, or as awaiting an acknowledgment, silence it per source.** In the node's UI, matched on `alertname` `Ops · vintage source not recorded` and on that `source`, or on that provider's sources; time-boxed to the next 20:00 UTC, so that if the outage continues the page returns with about four hours left to save the next day; read back after it is set, and deleted when the source reads a good fetch. The owner sets it, or `zcrypto-marco` on the owner's word for that silence, and never the daily pass on its own (no count command: a Grafana silence leaves no trace in the tree).
8. **After a late hand start, nothing more**: its good fetches read as 19:57, so a next day that fails still pages before its midnight. For a `bg-*` source whose save then reads `budget exhausted`, read the remaining count and the reset time that the `X-RateLimit-*` headers in the newest tick's `tick.json` state, and start the save once that reset has passed, before 00:00 UTC; a reset after it loses the day for that source.
9. **Never a silence without a `source` matcher, and never a fabricated body under `record/`** (no count command: a silence and a hand-written file leave no trace in the tree). A silence naming no `source` also hides the other sources and the no-data instance.

### Retire when

`zcrypto-ops-vintage-not-recorded` is absent from `infra/grafana/alerts.yaml`, or `zcrypto_vintage_last_ok_timestamp_seconds` is no longer written under `cli/vintage/`.

### Restoring a damaged file from the other copy

`zcrypto vintage verify` names a finding by path: on ops, each tick's own re-read logs it at ERROR, paging through `Ops · ERROR logs`; on the NAS, the loop logs `vintages verify failed (dest=…), continuing`, paging through `zcrypto-nas-archive-pull-errors`. The record keeps two copies, the ops copy at `/var/lib/zcrypto-ops/vintages/record/` and the NAS copy at `/volume1/ZhaoCrypto/vintages/` (mounted at `/mnt/zhao-crypto/vintages/` on the workstation and, read-only, on ops). A finding is repaired by hand from the other copy, with the published bytes and no others.

1. **Read the expected sha256.** For a body, it is the `sha256` its entry records in a `tick.json` that itself hashes to its witness. For a `tick.json`, it is the witness: the `tick_json_sha256` of the tick's `vintage tick published` INFO line, `sudo journalctl -u zcrypto-vintage-record.service --no-pager | grep 'tick=STAMP'` on ops, or `{container="zcrypto-vintage-record"} |= "tick=STAMP"` on the Logs board, which keeps it 90 days; for a tick a named hand start published, the line kept in that day's operations journal entry. The successor's `prev` corroborates it, and stands in for it where the witness is past those 90 days or was not logged, and both copies verified that link clean before the damage.
2. **Where the copies or the successor's `prev` disagree with the witness, stop: the owner decides, against the witness, which copy gets which bytes**, never by copying whichever bytes match `prev` (no count command: a restore is an operator act the tree does not record). The successor's `tick.json` is not rewritten, so that link then stays broken in both copies until code acknowledges it: a pinned entry in `cli/vintage/` naming the successor's stamp, the `prev` hash it recorded and the witnessed hash, shipped through an ops re-pin and a NAS re-pin with a new generation of the versions table. A link whose `prev` carries the chaining check's `error` needs no entry: its predecessor is restored against the witness.
3. **Hash the other copy's file before placing it**: `sha256sum <copy>` must print the expected sha256. For a whole tick, hash each of its files the same way: its `tick.json` against the witness, then each body against that `tick.json`. On ops, the NAS copy's file is read through its mount; for the NAS, the ops copy's file or tick goes to a scratch directory of your own on the NAS host, outside `vintages/`, by the `nas-file-transfer` procedure in `infra/runbooks/nas.md`, and is hashed there.
4. **On ops**, in the tick directory `/var/lib/zcrypto-ops/vintages/record/YYYY/MM/DD/STAMP/`: `sudo chmod 0755 <dir>`, then `sudo -u zcrypto-data cp -f <copy> <file>` — `-f` because a damaged file still present is 0444, and a plain `cp` onto it fails `Permission denied` even in a 0755 directory — then `sudo chmod 0444 <file>`, since `cp -f` leaves the source's mode, and after the file, `sudo chmod 0555 <dir>`.
5. **On the NAS**, on the host itself after `ssh nas`, never through the ops mount or the workstation's (no count command: a write through the mount leaves no record in the tree), as `zcrypto-data`, uid 1000, which owns the NAS copy. Two forms, each after step 3's hashes matched, then the normalise for either:
   - **A single damaged or missing file in a tick the NAS copy holds**: `sudo -u zcrypto-data cp -f <copy> <file>`. A file it creates takes the copy's mode and the user's group, so normalise the tick afterwards, below, with `<dir>` that tick's directory.
   - **A whole tick the NAS copy lacks**: `sudo -u zcrypto-data cp -rn <copy> <path>`, `<path>` its date directory, made first with `mkdir -p` by that user when the day holds no other tick. `-n` never overwrites a file the NAS already holds, since the NAS copy keeps the bytes it took first (no count command: `cp -n` refuses the overwrite itself and records nothing). A placed tick keeps the copy's modes, and a directory `mkdir -p` made keeps the user's group `users` and a umask-cut mode, so normalise afterwards, below, with `<dir>` the highest directory `mkdir -p` made, or the date directory when it made none.
   - **Then normalise** to the NAS's directories 0775, files 0664 and group `zcrypto`, from the workstation: `ssh nas 'sudo bash -s -- <dir>' < infra/nas/normalize-archive-perms.sh`, `<dir>` written with its `/volume1/ZhaoCrypto/vintages/` prefix.
6. **An rsync temporary file `.<name>.XXXXXX` that `verify` names as unlisted** is what a pull killed mid-file leaves on the NAS; remove it on the NAS host: `sudo rm /volume1/ZhaoCrypto/vintages/YYYY/MM/DD/STAMP/.NAME.XXXXXX`.
7. **A fork `verify` names on the NAS copy is never restored on ops** (no count command: a restore is an operator act the tree does not record): the ops copy verifies clean without the tick off the chain, and a restored one would stand as a second head. It clears by a pinned fork entry in `cli/vintage/` naming the tick off the chain and its `tick.json` sha256, read from that tick's witness, or decided by the owner where it has none, shipped through an ops re-pin and a NAS re-pin.
8. **A `missing tick` the NAS copy's `--custody` read names for a fork entry's tick off the chain** clears by putting that tick back on the NAS host from a copy that holds it (a research copy taken from the NAS), its `tick.json` hashed with `sha256sum` against the entry's pinned sha256 and each body against that `tick.json` before step 5 places it. Where no copy holds it, the owner decides a code change marking the entry lost, shipped as the entry was; the old generation's catalog line then names its heads through that tick as rebuildable by no copy. Until the re-pin carrying the fork entry or the lost mark lands, or the tick is back, `zcrypto-nas-archive-pull-errors`, one instance per host over each ERROR the archive-pull container logs, fires on each loop's verify ERROR, so a custody channel's `… pull failed …, continuing` ERROR in that loop raises no page of its own: read the archive-pull ERROR lines by channel each day of that window, and leave that rule unsilenced.
9. **Then a whole `verify` of the copy you restored**, and compare its summary line's head and `tick.json` sha256 by value, since an empty or lagging copy also exits 0; a root that does not exist yet, as on the NAS before its first pull, exits 1 with a `missing root` break. The NAS copy, from the workstation: `zcrypto vintage verify --root /mnt/zhao-crypto/vintages --custody`. The ops copy, on ops, in the recorder's pinned image, the record mounted `:ro`: `sudo docker run --rm --pull never --network none -v /var/lib/zcrypto-ops/vintages/record:/vintages/record:ro --entrypoint zcrypto ghcr.io/zhaow-de/zcrypto-capture@<the ops digest from docs/reference/fleet-pins.md> vintage verify --root /vintages/record`.

### The versions table

The versions table at `/var/lib/zcrypto-ops/vintage-versions/` is derived from the record by `zcrypto-vintage-derive.service`, which follows each start of the recorder's unit; a derive's ERROR pages at warning through `Ops · ERROR logs`, and its head's age is the *Versions table head age* panel on the Data integrity board.

1. **Read the derive's last line.** `systemctl status zcrypto-vintage-derive.service`, then `sudo journalctl -u zcrypto-vintage-derive.service -n 100 --no-pager`: a run ends with `vintage derive complete generation=… head=… head_sha256=… parts_added=…`, or with `vintage derive stopped generation=… head=… at=… reason=…`, its `at` naming the tick it stopped at, or `none` for a refusal before a tick. `cat /var/lib/zcrypto-ops/textfile/vintage-derive.prom` shows the head's tick time as published. The record is untouched: the derive mounts it `:ro`.
2. **A held lock, a full disk, or an exception from a passing fault clears on its own**: the next recorder run's derive catches up from the table's head, so nothing waits on a hand start.
3. **A moved tick or a fork stops each run until it is cleared.** A moved tick, a `tick.json` that no longer hashes to what the table recorded, clears when a restore against the witness (the part above) gives back the bytes the table recorded, and the next run resumes. A fork, whose restored tick stays off the chain the next tick took around it, or a moved tick no restore clears, stops the derive until a new generation ships, a code change and the owner's decision; the old generation is kept, and its catalog line names which of its heads a copy can still rebuild with `--through`.
4. **A dead run's staging leftovers**, which each later run names in one WARNING: `sudo ls -la /var/lib/zcrypto-ops/vintage-versions/staging/`, read them, then, with the derive's unit inactive in step 1's status read (a running derive's staging entries are its publish in progress), delete them by hand, `sudo rm -rf /var/lib/zcrypto-ops/vintage-versions/staging/NAME`. They never block a later run (no count command: `cli/vintage/derive.py` names each staging entry by its run's start second and eight random hex digits).
5. **Rebuild a generation into an empty scratch root**: `zcrypto vintage derive --record <a copy> --table <an empty scratch root> [--through <stamp>]`, run from a revision whose `DERIVE_GENERATION` is that generation. `sudo ls -la /var/lib/zcrypto-ops/vintage-versions/` lists the generations as `gen-N/`, and `cat /var/lib/zcrypto-ops/vintage-versions/gen-N/generation.json` names the revision that opened one. Compare a head's sha256 with the ops table's by value, `sha256sum` over the two `heads/YYYY/MM/DD/STAMP/head.json` files.
6. **Put back a damaged table file**, the table's one write after a rename: a head or `part.json` byte-equal to the rebuild's, or a parquet file whose frame-content hash equals what its `part.json` records, placed with step 4 of the restore above — its directory made writable for the copy and set back to 0555.
7. **A hung derive**: a head that keeps ageing on the dashboard past a recorder run while `systemctl status zcrypto-vintage-derive.service` reads active has hung. Stop it by hand, `sudo systemctl stop zcrypto-vintage-derive.service`, so the next run starts afresh.
8. **A leftover `zcrypto-vintage-derive` container** is removed as the recorder's is: `sudo docker ps -a --filter name=zcrypto-vintage-derive`, then `sudo docker rm zcrypto-vintage-derive`.

______________________________________________________________________

<a name="zcrypto-ops-panel-exit-nonzero"></a>

## zcrypto-ops-panel-exit-nonzero — ALERT

### What you are seeing

A **warning** Grafana alert (`Ops · panel non-zero exit`): `ops_panel_exit_code > 0`, `for: 5m`, `noDataState: OK`. The last hourly L2 panel materialize errored.

### What it means

`zcrypto-panel-materialize.timer` fires at `*-*-* *:22:00` with `Persistent=true` — ten minutes after the `:12` writer tick, so the reconciled overlay hours the materialize prefers are fresh from that cycle. The unit runs `zcrypto panel materialize /nas/capture-segments /data/capture-reconciled --panel-root /data/l2-panel`, writing the panel tree locally under `/var/lib/zcrypto-ops/l2-panel`.

**Freshness, not truth.** The panel is derived, watermarked per pair and recomputable from the archive; a failed hour costs staleness and the next healthy run picks it up. Nothing here is unbackfillable.

The CLI exits 1 **iff at least one hour errored**, and logs each failure at ERROR as `panel hour failed pair=… hour=… : …` — so `Ops · ERROR logs` usually pages the same event with the message attached, which is where the actual cause is. A generation/manifest refusal is different: it aborts before any hour runs and prints its own instruction. Do not "fix" that by deleting `panel-meta.json` alone — the refusal exists precisely because that would stamp this code's generation onto hours another one wrote.

**There is no panel staleness rule, and that is deliberate.** `panel-materialize.sh.j2` publishes `ops_panel_last_success_timestamp` and no rule in `infra/grafana/alerts.yaml` reads it, so a timer that stops firing altogether trips no Grafana rule at all — the exit code freezes at its last value and the textfile is re-served forever. The only thing that catches it is the dead-man for the panel check, pinged only on a clean run and only when `ops_panel_healthcheck_url` is set (`infra/ansible/host_vars/zcrypto-ops/vars.yml`, from the project's ping key and the slug `zcrypto-panel`), surfacing through `Fleet · dead-man watchdog (check down, or the service dark)` (uid `zcrypto-hcio-watchdog`) and the dead-man service's own Slack integration. Drill O established that the dead-man catches it alone, so **no staleness rule is owed**, and that the cost is a notice window of three hours from the last clean ping (`docs/reference/drill-log.md`, entry `O`, holds the check's timeout and grace and the measured time-to-page). **Do not close or reopen this gap from this runbook** — a rule found owed is a change to `alerts.yaml`.

### What to do

1. **Read the failing hours.** `ssh hp`, then `sudo journalctl -u zcrypto-panel-materialize.service --since -2h --no-pager` — each failure names pair, hour and message, and the run closes with a `panel materialize complete … errors=<n>` line.
2. **Check both roots.** `ls /mnt/zhao-crypto/capture-segments` (the read-only NFS view; an EIO on a segment the sweep opened is a loud per-hour error by design, while an EIO on the *listing* is silent — the hour goes unseen and the next hour written carries the watermark past it) (no count command: the mount's `ro` in `infra/ansible/roles/ops/tasks/main.yml` holds it) and `ls /var/lib/zcrypto-ops/l2-panel` (the writable output tree).
3. **Clear a leftover container.** `sudo docker ps -a --filter name=zcrypto-panel-materialize`, then `sudo docker rm zcrypto-panel-materialize`.
4. **Re-run**: wait for the next `:22`, or `sudo systemctl start zcrypto-panel-materialize.service`. The per-pair watermark makes the re-run idempotent — it processes only hours newer than what is already written (no count command: `tests/test_panel_materialize.py::test_materialize_skips_hours_at_or_below_the_watermark`).
5. **A full regeneration is not this, and is not yours to start.** Panel regeneration is the point of no return (no old tree survives, rollback is another full rebuild) and runs only on the user's explicit word, typed into `zcrypto-panel-regenerate`'s own pause gate at a terminal (no count command: `tests/test_panel_regenerate.py::test_pipe_cannot_drive_the_paused_gate`). Related trap while one is in progress: **an ordinary converge silently re-arms this timer**, firing a materialize against a half-rebuilt tree — `-e ops_panel_timer_hold=true` is the opt-in that keeps it stopped for that window.

### Retire when

`zcrypto-ops-panel-exit-nonzero` is absent from `infra/grafana/alerts.yaml`, or `ops_panel_exit_code` is no longer written by `infra/ansible/roles/ops/templates/panel-materialize.sh.j2`. The no-staleness-rule paragraph above retires when any rule in `infra/grafana/alerts.yaml` selects `ops_panel_last_success_timestamp`.

______________________________________________________________________

<a name="zcrypto-ops-load-high"></a>

## zcrypto-ops-load-high — ALERT

### What you are seeing

A **warning** Grafana alert (`Ops · node load high`): `node_load1{host="ops"} > 20`, `for: 5m`, `noDataState: OK`, charted on the `Fleet health` board. The `host="ops"` label comes from `external_labels` on this host's Alloy, which is what makes the selector partition the metric away from the NAS's own `node_load1`.

### What it means

Sustained saturation, not a transient burst. Nothing is lost by load alone — the cost is that timers overrun their ticks, and one of them has a cliff: a writer cycle past 1800 s means the next `:12`/`:42` trigger fires against a still-activating unit and is **dropped**, halving the booking cadence (`infra/runbooks/ops.md#zcrypto-reconcile-cycle-duration` owns that, and its own rule warns at 1500 s).

The load is Alloy plus the timers under `infra/ansible/roles/ops/`; the overlay writer is one of them, not a service beside them. Read the schedules from those templates, or from `systemctl list-timers 'zcrypto-*'` on the host; no list written here is the authority. The bar is 20 whatever the box has. If you are going to reason about the ratio, read the thread count from `nproc` on the host rather than from any figure written here or in a spec.

**Known, accepted overlaps and bursts, none of them findings on their own**: the writer's `:42` slot collides with the 03:41 verify-replay run once a day (both are read-only NFS readers); the host reboots by hand, in its 02:25 UTC slot ([`hosts.md#zcrypto-capture-reboot-pending`](hosts.md#zcrypto-capture-reboot-pending)), and the role's `Persistent=true` timers (`grep -l 'Persistent=true' infra/ansible/roles/ops/templates/*.timer.j2`) run their missed ticks after it, so a post-boot burst is expected; and this host also carries the liquidations poller, Alloy, and the agentboard web terminal with its tmux sessions, so not every load spike is pipeline work.

### What to do

1. **Ask what is running.** `ssh hp`, then `uptime`, `top -bn1 | head -25`, `sudo docker stats --no-stream`.
2. **Ask which oneshots are mid-run.** `systemctl list-units 'zcrypto-*.service' --state=active` and `systemctl list-timers 'zcrypto-*'`.
3. **Correlate on the `Data integrity` board** before touching anything: `zcrypto_reconcile_cycle_duration_seconds` against its 1500 s bar, `zcrypto_reconcile_ledger_scan_seconds` (the append-only ledger becomes the cycle's cost driver as it grows — `infra/runbooks/ops.md#reconcile-ledger-scan-cost`) (no count command: `cli/archive/mint.py` is its one writer, in append mode), and `ops_verified_replay_days_behind` (a catch-up run replays up to 30 days in one pass).
4. **The heaviest single thing this host does is a verify-replay rebuild** after its state directory was lost — it replays the whole archive and takes nights, and the sweep's census says so (`replayed` high, `reused` near zero).
5. **Do not kill a running unit to shed load.** A killed reconcile publishes nothing, so it goes *stale* rather than red and you lose the signal you would have read; a killed verify-replay loses up to 250 replayed hours, its checkpoint interval (`_FLUSH_EVERY` in `cli/archive/replay.py`).
6. **Do not retune the bar in place.** A breach that repeats is capacity or scheduling work, not a threshold problem.

### Retire when

`zcrypto-ops-load-high` is absent from `infra/grafana/alerts.yaml`. The metric itself is node-exporter's and will not stop existing.

______________________________________________________________________

<a name="zcrypto-ops-disk-low"></a>

## zcrypto-ops-disk-low — ALERT

### What you are seeing

A **warning** Grafana alert (`Ops · root filesystem low`): `node_filesystem_avail_bytes / node_filesystem_size_bytes` on `host="ops"`, `mountpoint="/"`, below 0.15 for 30 minutes. `noDataState: OK`, since a dark host is `zcrypto-alloy-dark-ops`'s page. The `Fleet health` board's *Filesystem free % by mountpoint* panel (301) draws the ops line against its red line at 0.15.

### What it means

The root filesystem holds `/home` as well as the system. On it sit the Docker images the ops timers run from, under `/var/lib/docker`; the timers' own state under `/var/lib/zcrypto-ops`, the reconcile ledger among it; the journal; and the operator's checkouts of this repository with their worktrees and their gitignored `data/`. A full disk fails the timers' textfile and ledger writes and the next image pull. `/mnt/zhao-crypto` is the NAS's export on a filesystem of its own, which `zcrypto-nas-disk-low` watches, and `/tmp` is a tmpfs whose inodes `zcrypto-ops-inodes-low` below watches.

### What to do

1. **Read what fills it**, on the host (`ssh hp`): `df -h /`, then `sudo du -xh -d 2 / 2>/dev/null | sort -h | tail -25`. `-x` keeps the walk on this filesystem, so the NFS mount and the tmpfs stay out of it.
2. **Removing anything is the operator's decision**, and this section names candidates, not steps to run. The usual ones: stale images, listed by `uv run python infra/scripts/prune-host-images.py zcrypto-ops` from a checkout (`--apply` is what removes them, and `--keep <digest12>` spares one staged for a converge); the journal, `sudo journalctl --vacuum-size=<size>`; a finished session's worktree or a checkout's `.tmp/`.
3. **A checkout's `data/` is the owner's alone to touch**: those datasets are unversioned and exist nowhere else.
4. **`/var/lib/zcrypto-ops` is not reclaimable space.** The reconcile ledger is the record of what each hour's reconcile decided, and a verify-replay state directory lost is a rebuild that takes nights (`zcrypto-ops-load-high` step 4).
5. **Confirm by value**: panel 301's ops line back above 0.15, and the rule back to Normal.

### Retire when

`zcrypto-ops-disk-low` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-ops-inodes-low"></a>

## zcrypto-ops-inodes-low — ALERT

### What you are seeing

A **warning** Grafana alert (`Ops · inodes low`): free inodes over total, `node_filesystem_files_free / node_filesystem_files` on `host="ops"` for the mountpoints `/` and `/tmp`, below 0.25 for 10 minutes. One instance per mountpoint, and the notification's `mountpoint` label names which. `noDataState: OK`, since a dark host is `zcrypto-alloy-dark-ops`'s page. The `Fleet health` board's *Ops inodes free* panel (305) draws both against the red line at 0.25.

### What it means

A filesystem out of inodes refuses to create a file however many bytes it still has free, and the free-space panels cannot show it. `/tmp` is the one at risk: a tmpfs capped at 1,048,576 inodes, and the Claude Code sessions' default temp root, where a checkout or a dependency tree in a session's scratch costs hundreds of thousands. When it runs out, a `docker run` fails before its container starts (`failed to create temp dir: mkdir /tmp/containerd-mount…: no space left on device`), so the ops timers' runs fail with it and `zcrypto-ops-archive-pull-exit-nonzero` is the usual first page. The overlay writer reconciles a 48 h window, so ticks lost this way are made good by the first clean one inside it. `/` is ext4, its inode table sized with the disk, and is watched for the same failure.

The bar leaves time to act: at the fastest fill seen on `/tmp`, the page lands with a little under two hours to go.

### What to do

1. **Read which filesystem and how full**, on the host (`ssh hp`): `df -i / /tmp`.
2. **Find what holds the inodes**: `sudo du --inodes -x -d 2 /tmp 2>/dev/null | sort -n | tail -20`, or over `/` with `-d 3` when `/` is the one named. The sessions' scratch trees sit under their temp root: `/tmp/claude-<uid>/`, or `claude-<uid>/` under the directory `CLAUDE_CODE_TMPDIR` names in the environment the session was launched in (the owner's shell startup exports it).
3. **Removing files is the operator's decision.** A scratch tree belongs to a session that may still be reading it: ask the session that owns it, or the owner, before anything under a session's temp root goes. A reboot empties the tmpfs, but it also ends the sessions and restarts the host's timers mid-run, so it is not the remedy here.
4. **Confirm by value**: `df -i / /tmp` and panel 305 above 0.25; the next `:12`/`:42` writer tick exits 0, which clears `zcrypto-ops-archive-pull-exit-nonzero` if it paged.

### Retire when

`zcrypto-ops-inodes-low` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-ops-error-logs"></a>

## zcrypto-ops-error-logs — ALERT

### What you are seeing

A **warning** Grafana alert (`Ops · ERROR logs`) on the `logs` receiver, `for: 0s`, `noDataState: OK`. **The log message itself is on the page** — that is the whole point of the rule, so read it before opening anything.

The rule reads `{host="ops", container=~"alloy|liquidations|zcrypto-.*", level=~"ERROR|CRITICAL"}` over a 15 m window, wrapped in `topk(5, …)`, each message truncated at 200 characters.

### What it means

The `container` label names the source, and that is your routing:

- **`zcrypto-archive-pull`** — the reconcile or trade-backfill CLI errored inside the writer cycle. Pair it with `zcrypto-ops-archive-pull-exit-nonzero` and `zcrypto-trade-backfill-exit-nonzero` above.
- **`zcrypto-panel-materialize`** — a per-hour panel failure (`panel hour failed pair=… hour=…`); the panel section above.
- **`zcrypto-verify-replay`** / **`zcrypto-verified-replay`** — that sweep's CLI; `infra/runbooks/ops.md#zcrypto-ops-verify-replay-new-breakage` and the verified-replay section above.
- **`zcrypto-tape-bars`** — the tape-bars sweep; its sections are in `infra/runbooks/ops.md`.
- **`alloy`** — Alloy's own logfmt `level=error`, typically a remote-write or Loki-push failure. The telemetry plane is complaining about itself. A line carrying `component_id=loki.write.mon` (`final error sending batch, no retries left, dropping data`) or `remote_name=mon` (`non-recoverable error`) is the node's ingest failing — the node's Loki or its edge down past about seven minutes, or a 401 from an ingest password changed on the node and not yet on ops: `mon.md#mon-dark`, and `mon.md#mon-secrets` step 4 for the 401. Such a line reaches this rule by a later batch that delivers, after the fault has cleared.
- **`liquidations`** — the poller. **This rule is the only channel its ERROR lines have**: it is a long-lived daemon that flips no exit-code metric, and it direct-ships its own lines to Loki without passing through Alloy at all (no count command: `alerts.yaml` selects its ERROR lines in `zcrypto-ops-error-logs` alone).

**Silence here is not a clean bill, and the reason is mechanical.** The `level` label is set by Alloy's parse stage, which matches only the Python-logging line shape (`YYYY-MM-DD HH:MM:SS,mmm LEVEL …`), and by the stages after it that level the runners' bare echoes by their own shape. `archive-pull.sh` and `verified-replay.sh` write the Python shape for their own warnings, at **WARNING**, so they show under the board's WARNING filter and never page here. Of the echoes, only a tape-bars line reporting a failed day pages here; an echo of a shape no stage names ships with no level, which the observability node's `zcrypto-mon-unlevelled-log-lines` pages. A gate-skip streak produces no ERROR page by construction.

The scope is the journal keep-regex in `infra/ansible/roles/ops/files/config.alloy`; the rule's selector is `zcrypto-.*`, so a unit the keep-regex does not admit produces no page here — extend the regex, not the selector.

### What to do

1. **Act on the message on the page first.** It names the failing pair, hour, day or endpoint in most cases.
2. **Get the full set out of Loki** — `topk(5, …)` truncates a storm, so five instances is a floor, not a count. Query `{host="ops", container="<the one named>", level=~"ERROR|CRITICAL"}` over the last hour, and size the storm with `sum(count_over_time({host="ops", level=~"ERROR|CRITICAL"}[15m]))` before calling it "five errors".
3. **On the host, read the source stream.** For a unit container, `sudo journalctl -u zcrypto-<unit>.service --since -30m --no-pager | wc -l` and then the lines; the archive-pull section's step 2 holds why an empty unprivileged result proves nothing. For the poller: `sudo docker logs --since 30m zcrypto-ops-liquidations`. For Alloy: `sudo docker logs --since 30m grafana-alloy`. **`--since` takes a duration or a full timestamp** — a bare `HH:MM:SS` fails to parse, and a grep over the resulting empty output reads as a clean bill.
4. **Then follow the section that owns whatever was named.** This rule reports that something errored and quotes it; it never diagnoses (no count command: its expr in `infra/grafana/alerts.yaml` counts and quotes lines).
5. **Do not silence it to quiet a known storm** without a time box — for the liquidations poller it is the only page an ERROR line can raise (no count command: `alerts.yaml` selects its ERROR lines in `zcrypto-ops-error-logs` alone).

### Retire when

`zcrypto-ops-error-logs` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="agentboard-node-upgrade"></a>

## agentboard node upgrade — PROCEDURE

### What you are seeing

Nothing fired. You are moving the ops node's web terminal onto a new node, or onto a new `@gbasin/agentboard` pin — the `zaccess-agentboard` unit on `zcrypto-ops` (`ssh hp`), which runs as the `zhaow` user and fronts that user's tmux server.

### What it means

**The upgrade needs no converge.** The unit's `ExecStart` runs the rendered `/usr/local/sbin/zaccess-agentboard-start`, which sources nvm and execs the platform binary at **start** time, so a plain restart picks up whatever node and package are installed by then.

**The restart is safe only because the unit sets `KillMode=process`** (`infra/ansible/roles/access_ops/templates/zaccess-agentboard.service.j2`). agentboard boots the operator's tmux server as a child, and a forked process keeps its unit's cgroup for life — `ppid 1` does not mean out of the unit, so read `/proc/<pid>/cgroup` and never the ppid. Under systemd's default `control-group`, this restart SIGKILLs that tmux server and every session on it.

### What to do

1. **Read `echo $TMUX` first.** A Claude Code session may itself be running inside the tmux that agentboard fronts, and a server-killing action taken from there is self-termination — the session dies mid-command with no report.
2. **Upgrade, then restart** — the nvm and npm halves run as `zhaow`, the unit's `User=`, whose nvm the start script sources (`access_ops_agentboard_nvm_sh`): `nvm install <new> && nvm alias default <new> && npm i -g @gbasin/agentboard@<pin> && sudo systemctl restart zaccess-agentboard`.
3. **`<pin>` is `access_ops_agentboard_version`** (`infra/ansible/roles/access_ops/defaults/main.yml`). The role reinstalls that exact version whenever it is absent under nvm's current node, so a hand install of any other version is put back to the pin by the next converge of this host that runs the `access_ops` role (no count command: the `npm ls -g` presence check in `infra/ansible/roles/access_ops/tasks/main.yml` holds it) — changing the version is a repo edit first.
4. **Never a second or test agentboard on the ops default tmux socket** — it collides with the live one and with the durable session. Isolate any test with `TMUX_TMPDIR` (no count command: an agentboard started by hand is an operator action nothing records).
5. **Never blanket-`pkill agentboard`** — that kills the live systemd unit (no count command: a hand `pkill` is an operator action nothing records).
6. **Confirm which binary is running, by value**: `/proc/$(systemctl show -p MainPID --value zaccess-agentboard.service)/exe`, hashed against the binary inside the pinned `@gbasin/agentboard-linux-x64` tarball. The start script execs the server itself, so MainPID is the server; `npm ls -g @gbasin/agentboard --depth=0` reads the **installed** package and never the running one (no count command: a property of npm, an upstream binary).

### Retire when

`infra/ansible/roles/access_ops/templates/zaccess-agentboard.service.j2` no longer sets `KillMode=process` — every safety clause above is about that setting — or `access_ops_agentboard_live` is no longer true in `infra/ansible/host_vars/zcrypto-ops/vars.yml`, which converges the unit disabled and stopped and leaves nothing running to upgrade.
