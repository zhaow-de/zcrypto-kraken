# A forward recorder on the ops node keeps every byte three free providers serve, twice a day, so C3's point-in-time history accrues from the first tick and every later restatement becomes a measured diff

Branch `feat/00158-c3-vintage-recorder`, cut from `develop` at `182db6045` (committed 2026-11-09) and now on `develop` at `e272cfd9c`, the merge of PR #850 (2026-11-11T01:22:18Z), written 2026-11-11 on `zcrypto-ops`. The owner's words that day, verbatim: at ~00:08Z, "consolidate both reports into T0016's findings, build (1), register (2) as a new T-topic, and skip (3) for now", (1) being marco's proposal, "Start a free forward recorder. Store Fear & Greed and Coin Metrics Community MVRV once a day, with the time we fetched them. Every day not recorded is point-in-time history lost for good."; at ~00:23Z, declining a design interview, "start the design with your best knowledge/learning/finding". Every decision below is therefore marco's call. The owner has approved none of them, and approves this written spec before anything is built.

## Intent and why

C3 (`docs/research/00.master-plan.md` §5 bucket C, line 168: "MVRV-Z / SOPR-style valuation bands as *additional regime-gate inputs* only") needs point-in-time data, a value for day D as it was knowable at D, and §8's data policy (line 243) wants every dataset "immutable + versioned … never 'latest'".
Every vendor studied restates history in place. Coin Metrics restated BTC `SplyCur` by exactly +100 BTC between its 2026-03 GitHub snapshot and today, and moved LINK MVRV on 298 of 327 overlapping days by at most 3.39e-05 relative with no matching notice (the 2026-10-31 sourcing read and the 2026-11-11 off-list read, consolidated into T0016's findings, which PR #850 merged to `develop`). No free vintage archive exists: the `coinmetrics/data` repository stopped on 2026-05-24.
A recorder that stores, from its first tick, exactly what each free source served and when turns that defect into a measured one: as-first-published values going forward, and a diff of every later restatement.
Everything a source returns at the first tick is the vendor's history as revised up to that day, never point-in-time. That is why the start date matters and why each day of delivery is a day the record never holds.
It is research data. Nothing here feeds the live engine.

## Goals, non-goals, anti-goals

Goals:
- From the first tick, every byte of each source's final answer, whatever its status, with the recorder's own fetch time, kept forever and unchanged in two copies, the ops node's and the NAS's, each copy re-verified on a schedule. Three exceptions, named: a body over 64 MiB and a body cut by its deadline are recorded as attempts without their bytes, and an attempt that was retried keeps only its first 4 KiB (D4).
- Two ticks a day, so one failed tick never costs a day, and a page while a day at risk can still be saved by hand.
- Each tick a self-contained directory a reader can copy and verify alone, linked to its predecessor so a missing tick is detectable: in any copy once a later tick names it, and as a fork in a copy that pulled a head deleted before its successor ran (D15).
- A derivation, proven on fixtures in this change, that answers "first published", "restated" and "first appeared" for any series and day, and the as-of view, from the stored bytes alone.
- Boring to run for years: the ops timer pattern, bounded in time, bytes and requests, every hole loud.

Non-goals:
- A derived versions dataset, its registry and `ObservedReader` arm, and any C3 trial: the first C3 trial spec's.
- The BTC chain computation: its own topic, T0228.
- Any keyed or paid source, any account, and every Kraken endpoint.
- Any input to the engine.

Anti-goals, what the recorder must never do:
- Synthesise, backfill or relabel a day: no code writes a tick whose stamp is not its own fetch time.
- Rewrite or delete a published byte, on ops or on the NAS. A hash-checked restore (D15) puts the published bytes back where a copy lost or damaged them, and is not a rewrite.
- Re-serialise a body.
- Let a judgement about a body stop it being stored.
- Write through the NFS mount.
- Carry a credential, an account or a person's name on the request path.

## BLAST_RADIUS

What ships to `zcrypto-ops`: one timer firing one oneshot container twice a day, writing only under `/var/lib/zcrypto-ops/vintages/` and one `.prom`, plus one `rrsync -ro` key.
What ships to the NAS: one rsync-and-verify block in the pull loop, and the archive-pull image moved to a `-compat` build that carries the verifier, which recreates that container once.
A paged operator re-runs a tick by hand, clears a leftover container or restores a damaged file from the other copy; nothing else waits on it.
No trial number changes until a C3 trial reads the record, and nothing feeds the engine.

## The measured basis

Read 2026-11-11 on `zcrypto-ops` at worktree HEAD `182db604585ebf4e871cf3530a10ab9154f7ed1b`. The tree claims below hold at `e272cfd9c` too: its diff from `182db6045` touches only `docs/open-topics/` and `docs/reference/change-index.md`. Three kinds of evidence: the sources read of 2026-11-11 00:25–00:35Z (keyless calls and the sources' own documents, each re-checkable at the URL beside it), this writer's own calls at 01:03–01:08Z (the command below, nothing written to disk), and reads of the tree and the host.
Before the plan's Task 1, the session writing the plan records one real body per source, kept out of the tree unless the owner's answer to open question 4 admits it, and writes from it the committed `.provenance.json` and, for each synthesised source, the shape file from which the committed generator builds its fixture under `tests/fixtures/vintage/` (D19), because the implementer makes no network call; the plan review's pin then re-reads the source claims from those bytes offline.

The command for this writer's sizes and headers, run once per URL three seconds apart:

```
m() {
  curl -sS -A 'zcrypto-vintage-design/0' -H 'Accept-Encoding: identity' -D /dev/stderr \
    -o >(tee >(wc -c) >(gzip -9n | wc -c) >(xz -6 | wc -c) >/dev/null) "$2"
}
```

| Source id | Fetched (UTC) | Raw bytes | gzip -9n | xz -6 | Headers that bear on the design |
|---|---|---|---|---|---|
| `cm-btc`, the six C3 metrics | 01:03:30 | 1,687,796 | 377,257 | 285,304 | HTTP/2 200, `application/x-ndjson`, no Content-Length, `cache-control: no-cache`, `x-ratelimit-plan: download`, `x-ratelimit-limit: 6000, 6000;w=20;comment="sliding window"` |
| `cm-eth`, the six C3 metrics | 01:03:34 | 1,066,182 | 251,648 | 192,448 | as `cm-btc` |
| `cm-btc`, all 31 daily metrics, both `ignore_*` flags | 01:04:22 | 8,341,605 | 1,750,182 | 1,390,008 | as `cm-btc`, plus `expires: Thu, 01 Jan 1970 00:00:00 GMT` |
| `fng` | 01:04:27 | 301,997 | 18,702 | 14,548 | HTTP/2 200, `application/json`, `content-length: 301997`, no ETag, no Last-Modified, no Cache-Control |
| `mempool-hashrate` | 01:04:31 | 431,798 | 103,935 | 77,172 | `cache-control: max-age=120` and `public`, a weak ETag, no Last-Modified |
| `cm-status` (`history.atom`) | 01:04:34 | 35,889 | 6,829 | 6,404 | `cache-control: max-age=10, public, …`, a weak ETag |
| `cm-catalog` | 01:03:46 | 67,569 | — | — | one page, no `next_page_url` |

- **How Coin Metrics fails a pair (this writer, 01:08Z).** `assets=sol&metrics=CapMrktCurUSD,PriceUSD&frequency=1d&start_time=2026-11-08&format=json_stream`: 403, `{"error":{"type":"forbidden","message":"Requested metric 'CapMrktCurUSD' with frequency '1d' for asset 'sol' is not available with supplied credentials."}}` (01:08:35Z). The same URL plus `&ignore_forbidden_errors=true`: 200, three rows carrying `PriceUSD` alone (01:08:38Z). `assets=xrp&metrics=HashRate,PriceUSD`, no flag at all: 200, three rows carrying `PriceUSD` alone (01:08:40Z). An unsupported pair is therefore dropped silently by default, and a forbidden one is dropped silently under the flag.
- **The community catalog per asset (this writer, 01:03:46Z),** `https://community-api.coinmetrics.io/v4/catalog-v2/asset-metrics?assets=btc,eth,sol,xrp,ada,link,doge,ltc,dot,avax,avaxc,avaxp&page_size=2000`, daily metrics counted: btc 31, eth 31, doge 26, ltc 26, ada 24, xrp 23, link 22, dot 22, avaxc 17, avaxp 17, sol 8, avax 8. The names are in the sources table below.
- **Whole-tick sizes (the sources read and an earlier design reading).** The six C3 metrics for the ten asset ids as one `json_stream`: 9,654,777 bytes raw, 2,521,438 gzipped, 2.76 s (sources read); 9,655,022 raw, 2,117,310 at `gzip -9`, 1,580,536 at `xz -6` at 00:47:22Z (design reading). Every free daily metric for twelve asset ids as one `json_stream`: 32,623,978 raw, 9,804,241 gzipped, 9.0 s (sources read).
- **Publication times (sources read).** Fear & Greed: the 2026-11-11 row existed at 00:25:47Z, `time_until_update` 84845 s, so label D appears about D 00:00Z, once a day; 3,202 rows from 2018-02-01, with 2018-04-14..16 and 2024-10-26 missing. Coin Metrics: `AssetEODCompletionTime` minus D+1 00:00Z over D = 2026-08-12..11-09, median and p90, btc 2.76 h and 3.89 h (max 43.25 h), eth 3.00 h and 3.69 h, ltc 2.21 h and 2.48 h, doge 1.55 h and 1.63 h, link 0.91 h and 1.06 h, xrp 0.83 h and 1.02 h, ada 0.53 h and 1.01 h, avaxc 1.04 h and 179 h, avaxp 0.77 h and 22.6 h, from `https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc,eth,xrp,ada,link,doge,ltc,avaxc,avaxp&metrics=AssetEODCompletionTime,AssetCompletionTime&frequency=1d&start_time=2026-08-12&page_size=10000`. At 00:27:13Z the btc row for 2026-11-10 carried only `PriceUSD`. mempool: the row labelled D is indexed once a day after 00:00Z and only a requested reindex rewrites history (`https://raw.githubusercontent.com/mempool/mempool/master/backend/src/api/mining/mining.ts`, lines 444-505, read, not measured).
- **No source dates its own body (sources read).** No source sets a meaningful Last-Modified. `AssetEODCompletionTime` is "The time that the last metric for the asset was calculated" (`https://gitbook-docs.coinmetrics.io/network-data/network-data-overview/availability/asseteodcompletiontime.md`) and was itself seen restated: D=2026-10-22 read D+1 17:56:53Z on 10-31 and 2026-10-23T02:36:35Z on 11-11.
- **No body repeats between fetches (sources read).** Fear & Greed's newest row carries `time_until_update`, counting down every second; mempool's `currentHashrate` and `currentDifficulty` change with every block; every Coin Metrics body gains a row a day. mempool's `avgHashrate` values exceed 2^53 (for example `826267196366358300000`); Coin Metrics serves numbers as JSON strings, and `json_stream` omits a key where `json` gives an explicit null.
- **The host (this writer, 01:09Z).** `df -h /var/lib/zcrypto-ops`: `/` 3.6T, 105G used, 3.3T free. `/var/lib/zcrypto-ops` is `zcrypto-data:zcrypto-data 755` and holds no `vintages`. `/var/lib/zcrypto-ops/textfile/clock-offset.prom` is `root:root 644`, written 01:07:23Z, reading `zcrypto_clock_offset_seconds 0.001150123` and `zcrypto_clock_synchronised 1`. `systemctl is-enabled chrony-wait.service` prints `disabled`, so `time-sync.target`, which systemd orders every `OnCalendar` timer after, does not wait for a synchronised clock.
- **The tree (`182db6045`).** The liquidations poller is a compose service, `restart: unless-stopped` (`infra/ansible/roles/ops/templates/compose.yaml.j2:15`), started only by an attended `docker compose up -d`. The ops journal keep-regex is `zcrypto-(archive-pull|verify-replay|verified-replay|panel-materialize|tape-bars)\\.service;.*|.*;grafana-alloy` (`infra/ansible/roles/ops/files/config.alloy:196`), and `tests/test_infra_alloy_series.py` fails a timer the role installs that is neither in it nor listed as deliberately unshipped. The hot pull is `rsync --archive --ignore-existing --chmod=D2775,F0664` and the three verified channels run `zcrypto archive pull` (`infra/nas/pull-entrypoint.sh:135-202`); the unwired reconciled channel logs a WARNING, never silently. The dead-man fixture holds 12 checks, `OPS_CHECKS` names 6 and `SLUGS` maps 12 (`tests/test_infra_hc_role.py:840-849`). `infra/scripts/tier.py --paths cli/vintage/command.py cli/__main__.py infra/ansible/roles/ops/tasks/main.yml infra/grafana/alerts.yaml infra/nas/pull-entrypoint.sh infra/ansible/roles/ops/files/config.alloy` printed `tier: full`. Engine cycles run at 00/04/08/12/16/20 UTC (`docs/reference/fleet.md:61`). The ops clock rule pages `abs(zcrypto_clock_offset_seconds{host=~"ops|…"}) > 10` or the clock unsynchronised (`infra/grafana/alerts.yaml:3897`).

## Operating model

- **Machines and processes.** One host, `zcrypto-ops`, which is both the research workstation and the venue-facing ops node. On it, one timer fires one oneshot unit at 07:37 and 19:37 UTC. The unit runs one root runner, and the runner runs one attached container. The NAS's `zcrypto-archive-pull` container pulls the record hourly and re-verifies a slice of its copy each loop, and research reads it in place, on ops or through the NAS mount, read-only.
- **Shared state and its writers.** `vintages/record/` and `vintages/staging/` are written only by the recorder container, which holds `single_instance_lock` on `vintages/` for its whole run. Six sibling ops containers run as the same uid with the whole ops data root mounted read-write: `zcrypto-reconcile` and `zcrypto-trade-backfill` (`archive-pull.sh.j2:126` and `:159`), `zcrypto-panel-materialize` (`panel-materialize.sh.j2:36`), `zcrypto-tape-bars` and `zcrypto-rolling-extend` (`tape-bars.sh.j2:40` and `:141`), and the liquidations poller `zcrypto-ops-liquidations` (`compose.yaml.j2:46`, its user at `:16`); verify-replay mounts it read-only (`verify-replay.sh.j2:62`). Their code, not the permissions, keeps them out of `vintages/`; D5's 0555 tick directories and 0444 files make a stray write fail rather than land. The census after the change is `git grep -l ops_vintages_subdir -- cli/ infra/README.md infra/docker/ infra/grafana/ infra/nas/ infra/ops/ infra/runbooks/ infra/scripts/ infra/systemd/ infra/ansible/roles/ infra/ansible/scripts/ infra/ansible/inventory infra/ansible/site.yml infra/ansible/bootstrap.yml infra/ansible/files/README.md 'infra/ansible/group_vars/*/vars.yml' infra/ansible/group_vars/observed/alloy.yml 'infra/ansible/host_vars/*/vars.yml'`, which names only paths outside the vaulted set, because bash-guard builds its file list from the positive pathspecs alone and refuses one that reaches a vaulted file, whatever the excludes say (`scoped_grep` in `.claude/hooks/bash-guard.sh`); bash-guard admitted it on 2026-11-11 and, with `ops_data_dir` as the control pattern, it listed that variable's ten files. Its purpose is that no runner template or compose file other than the recorder's names the variable: among `infra/ansible/roles/ops/templates/` it prints `vintage-record.sh.j2` alone, beside `infra/ansible/roles/ops/defaults/main.yml`, `infra/ansible/roles/ops/tasks/main.yml` and any prose page that names it. `textfile/vintage.prom` is written by the CLI alone. `/volume1/ZhaoCrypto/vintages` is written by the NAS pull alone, and by a hash-checked restore (D15).
- **What identifies a unit across copies.** A tick is identified by its directory name, the UTC start second (`20261112T073700Z`), and by the sha256 of its `tick.json` bytes. A body is identified by its tick, its source id and the sha256 of its raw bytes. All three are the same in the ops copy, the NAS copy and any research copy, because nothing rewrites a published file and the NAS hop never re-sends one.
- **When the state can change.** `record/` changes only when a new tick directory appears by rename, at a timer slot, at a boot catch-up or at a hand start, and is then set to 0555; a hand restore (D15) is the only other change, and it puts back the bytes the tick's manifest already hashes, or, for a `tick.json`, the bytes its witness hashes (D5). `staging/` changes only while a tick holds the lock. A staging directory whose process has died is dead: it is never published, and the next tick names it in a WARNING.
- **A missed tick** publishes nothing. The gauges age and the next tick runs normally. **A double tick** ends one of three ways: a `systemctl start` while the timer's run is active joins that job and starts nothing; a second `docker run` under the container's stable `--name` fails in docker with code 125 and docker's own name-conflict message, before the CLI starts; any other second writer meets the lock and refuses loudly, with exit 2 and the recorder's own message (D9). **A restart** loses nothing: the CLI keeps no state between ticks, and every gauge is recomputed from `record/`. **A reboot over a slot** runs one tick at boot (`Persistent=true`), never one per missed slot.
- **Who reads the page.** One operator, the owner, on the `metrics` receiver, attended or by phone.

## Constraints

- `zcrypto-ops` is a live, venue-facing fleet host. Its converges are the owner's, run from merged `develop`, outside published Kraken maintenance windows, with the feed read whole at planning time and again immediately before (`.claude/rules/fleet-deploys.md`). No play runs from a dispatch.
- A new subcommand reaches the host only in a capture image built from `develop` after merge (`.github/workflows/capture-image.yml`), followed by an ops re-pin. The re-pin moves every ops runner and the liquidations compose, needs `-e liquidations_decision=roll-after|defer`, needs the running digest recorded in `docs/reference/fleet-pins.md` first, and needs the digest pulled beforehand (`--pull never`).
- It reaches the NAS only through `nas_capture_image` in `infra/ansible/host_vars/nas/vars.yml`, edited after merge to a `-compat` build from `develop`, never a branch build, its runtime proven by running polars in the pulled image (`.claude/rules/fleet-deploys.md`), and committed with its `fleet-pins.md` row only after the NAS converge that ran it uncommitted (`tests/test_fleet_contracts.py::test_the_nas_rows_agree_with_the_committed_pins`). A NAS converge that recreates archive-pull replays the gate export cold, and its window is sized from the live figures (`docs/reference/fleet-pins.md`, Standing constraints).
- A `config.alloy` edit ships only through the ops `--tags alloy` converge with `ops_alloy_digest`. Until it lands, an ops converge without that digest refuses on config drift.
- Every line the runner or the CLI prints carries the parse-stage shape; otherwise `Fleet · log lines with no level` pages within 15 minutes.
- Every metric family published under `cli/` or `infra/` is drawn by a dashboard panel (`tests/test_dashboards_cover_metrics.py`, where `NOT_CHARTED` is empty). Every rule links its own runbook anchor.
- Operator surfaces carry no internal token (`tests/test_internal_terms_not_operator_visible.py`). These surfaces are CLI help and Python string literals; every non-comment line of `infra/**/*.sh` and `*.sh.j2`, which covers the new runner and the NAS pull block; `# HELP` text; `Description=`; Ansible task names and operator messages; alert summaries; dashboard text; notification templates; compose files; runbook pages; and `README.md`.
- The hot hop never re-sends a file (`--ignore-existing`), `data fetch` refuses unattested parquet, and `verify_tree` checks `*.parquet` alone. The NAS mount is read-only on ops and is never written through (`docs/reference/fleet.md:66`).
- Spec 00051 D10 rules out sole custody of unbackfillable data.
- The plan reviews at tier `full`, and every guard is proven with `infra/scripts/mutate-probe.sh` through its own `-k` case. No Fable-floor path is touched: `cli.capture` is imported and never edited, and nothing under `.claude/` changes.
- No new runtime dependency: `pyproject.toml` and `uv.lock` stay as they are.

## The sources recorded from day one

Fourteen requests per tick, 28 a day, made sequentially:
- 22 a day to `community-api.coinmetrics.io`, at most 11 in any tick, spaced at least 1 s apart.
- 2 a day to `status.coinmetrics.io`.
- 2 a day to `api.alternative.me`.
- 2 a day to `mempool.space`.

| Source id | URL | Budget and publication | Licence and terms |
|---|---|---|---|
| `fng` | `https://api.alternative.me/fng/?limit=0` | "60 requests per minute enforced over a 10 minute window" (`https://alternative.me/crypto/api/`). Label D appears about D 00:00Z. | "You are free to use our API and data from our API in any way you like, this includes commercial projects of any kind" (the API page). The index page asks for attribution "right next to the display of the data" (`https://alternative.me/crypto/fear-and-greed-index/`). BTC-only. The API "may at any time change or discontinue". |
| `cm-<asset>` for `btc`, `eth`, `xrp`, `ada`, `link`, `doge`, `ltc`, `dot`, `avaxc`, `avaxp` | `https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=<asset>&metrics=<the asset's pinned list>&frequency=1d&format=json_stream&ignore_forbidden_errors=true&ignore_unsupported_errors=true` | "10 requests per 6 seconds per IP address" (`https://gitbook-docs.coinmetrics.io/api-reference/rate-limits.md`). The headers advertise 6000 per 20 s, and the recorder budgets to the documented figure. Label D's network fields fill in from about D+1 00:10Z to 04:00Z. | CC BY-NC 4.0, "for NonCommercial purposes only" (`https://gitbook-docs.coinmetrics.io/packages/coin-metrics-community-data.md`, `https://creativecommons.org/licenses/by-nc/4.0/legalcode.en`). The terms URL `https://coinmetrics.io/terms-of-use/` 301s to Talos, and no current text was found. The licence turns on purpose, not on whether a value reaches the engine: "NonCommercial means not primarily intended for or directed towards commercial advantage or monetary compensation" (its Section 1). Whether research that decides a for-profit engine's inputs passes that test is open question 4. |
| `cm-catalog` | `https://community-api.coinmetrics.io/v4/catalog-v2/asset-metrics?assets=btc,eth,sol,xrp,ada,link,doge,ltc,dot,avax,avaxc,avaxp&page_size=2000` | One page, 67,569 bytes. | As `cm-<asset>`. |
| `cm-status` | `https://status.coinmetrics.io/history.atom` | 25 entries, a rolling window. `https://status.coinmetrics.io/robots.txt` disallows `/api/`, so `incidents.json` is out. | Coin Metrics' status page. |
| `mempool-hashrate` | `https://mempool.space/api/v1/mining/hashrate/all` | "Our API limits aren't disclosed" (`https://github.com/mempool/mempool/discussions/752`). Indexed once a day after 00:00Z. | No data licence. "WE MAKE NO GUARANTEE TO THE ACCURACY OF ANY DATA" (`https://raw.githubusercontent.com/mempool/mempool/master/frontend/src/app/components/terms-of-service/terms-of-service.component.html`, updated July 10, 2024). |

Each `cm-<asset>` request asks for every daily metric the community catalog listed for that asset at 01:03:46Z (D3). The plan pins these lists verbatim from the fixture's catalog bytes on the day the fixture is recorded.

| Asset | Count | Daily metrics |
|---|---|---|
| `btc` | 31 | AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD CapMrktEstUSD FeeTotNtv FlowInExNtv FlowInExUSD FlowOutExNtv FlowOutExUSD HashRate IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur SplyExNtv SplyExUSD SplyExpFut10yr TxCnt TxTfrCnt volume_reported_spot_usd_1d |
| `eth` | 31 | AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD CapMrktEstUSD FeeTotNtv FlowInExNtv FlowInExUSD FlowOutExNtv FlowOutExUSD HashRate IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateEUR ReferenceRateUSD SplyCur SplyExNtv SplyExUSD SplyExpFut10yr TxCnt TxTfrCnt volume_reported_spot_usd_1d |
| `doge` | 26 | AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD CapMrktEstUSD FeeTotNtv HashRate IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur SplyExpFut10yr TxCnt TxTfrCnt volume_reported_spot_usd_1d |
| `ltc` | 26 | AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD CapMrktEstUSD FeeTotNtv HashRate IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur SplyExpFut10yr TxCnt TxTfrCnt volume_reported_spot_usd_1d |
| `ada` | 24 | AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD CapMrktEstUSD FeeTotNtv IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur TxCnt TxTfrCnt volume_reported_spot_usd_1d |
| `xrp` | 23 | AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD CapMrktEstUSD FeeTotNtv PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur SplyExpFut10yr TxCnt TxTfrCnt volume_reported_spot_usd_1d |
| `link` | 22 | AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime CapMVRVCur CapMrktCurUSD CapMrktEstUSD IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur TxCnt TxTfrCnt volume_reported_spot_usd_1d |
| `dot` | 22 | AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime CapMVRVCur CapMrktCurUSD CapMrktEstUSD IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d ReferenceRate ReferenceRateBTC ReferenceRateETH ReferenceRateEUR ReferenceRateUSD SplyCur TxCnt TxTfrCnt volume_reported_spot_usd_1d |
| `avaxc` | 17 | AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD FeeTotNtv IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d SplyCur TxCnt TxTfrCnt |
| `avaxp` | 17 | AdrActCnt AdrBalCnt AssetCompletionTime AssetEODCompletionTime BlkCnt CapMVRVCur CapMrktCurUSD FeeTotNtv IssTotNtv IssTotUSD PriceBTC PriceUSD ROI1yr ROI30d SplyCur TxCnt TxTfrCnt |

Not recorded:
- **BGeometrics** (`https://api.bitcoin-data.com/v3/api-docs`, `https://charts.bgeometrics.com/terms.html`). The API "is available with a free API key", which means an account. The free plan allows "up to 10 requests per hour and 15 requests per day", holds "Historical data … limited to the last 4 years", and hides the last 7 days of MVRV, SOPR and NUPL. This is open question 5.
- **Blockchain.com charts** (`https://www.blockchain.com/explorer/pricing`, `https://www.blockchain.com/legal/terms`). Charts are listed only from the $99/month Analyst plan. The terms forbid copying (§13.1(d)) and automated means (§15.2(c)).
- **`sol` and `avax`.** Price only. The catalog request still records their entitlement.
- **Kraken.** Out of scope.

Bytes, by inferred arithmetic from the measured sizes:
- About 33 MB raw and about 10 MB gzipped per tick at this breadth.
- So about 7 GB a year gzipped on each of the two copies.
- With only the six C3 metrics per asset, about 2.25 MB gzipped per tick, or about 1.6 GB a year.

## D1 — the recorder is an ops timer running one container per tick, not a daemon

**marco's call.** `zcrypto-vintage-record.timer` fires `zcrypto-vintage-record.service`. The unit is Type=oneshot, has `Requires=docker.service`, `Wants=network-online.target` and `After=docker.service network-online.target`, and carries no `RequiresMountsFor`. The network ordering is archive-pull's (`archive-pull.service.j2:10-12`), whose `Persistent=true` boot catch-up also dials out: without it, a `Persistent=true` boot tick taken before the uplink is up spends all fourteen requests on transport errors. Its ExecStart is the root runner `/usr/local/sbin/zcrypto-vintage-record`, rendered from `infra/ansible/roles/ops/templates/vintage-record.sh.j2`, mode 0700, rendered `no_log` and `diff: false` because it carries the dead-man URL (D12).
The runner runs one attached `docker run --rm --pull never --name zcrypto-vintage-record --user "{{ ops_uid }}:{{ ops_gid }}" -v "{{ ops_data_dir }}/{{ ops_vintages_subdir }}:/data" -v "{{ ops_textfile_dir }}:/textfile" --entrypoint zcrypto "{{ ops_image }}@{{ ops_image_digest }}" vintage record --data-dir /data --textfile /textfile/vintage.prom --clock-prom /textfile/clock-offset.prom`. It passes no `-e`, no secret, no network flag and no NAS mount. Its output goes to a `mktemp` file, which is replayed with `cat` because the runner has no pipefail; every line the runner itself prints goes through the `log()` helper's parse shape.
The CLI lives in `cli/vintage/`, registered as `app.add_typer(vintage_app, name="vintage")` in `cli/__main__.py`. Its subcommands are `record` and `verify` (D15). HTTP goes through stdlib `urllib` with an injectable `opener`, the idiom of `cli/liquidations/coinalyze.py:114`.
This corrects the brief's premise. The liquidations poller is a compose service the role renders and never starts, so the recorder takes the poller's CLI shape and the ops timers' runtime.
- Lost: a compose service with an in-process schedule, as the poller runs. Every start is attended, and the schedule is invisible to systemd, so a missed restart would be a silent, permanent loss.
- Lost: `ExecStart` as the `docker run` itself, with no runner (the minimal design). That leaves no root-only place to keep the dead-man URL.
- Lost: host cron. It has no `Persistent` catch-up, no unit for the journal keep-regex, and is not the fleet's pattern.
- Lost: an HTTP library. It would touch `pyproject.toml`, `uv.lock` and the image for what `urllib` already does.

## D2 — two ticks a day, 07:37 and 19:37 UTC, each 23 minutes before an engine cycle

**marco's call.** The timer carries `OnCalendar=*-*-* 07:37:00`, `OnCalendar=*-*-* 19:37:00`, `Persistent=true` and an `[Install]` section with `WantedBy=timers.target`, and no `TimeoutStartSec`: D7's deadlines bound every tick.
The `[Install]` section is what makes D17's enable survive a reboot, as on every sibling ops timer (`archive-pull.timer.j2:22-23`, `grafana-watchdog`, `panel-materialize`, `tape-bars`, `verify-replay`, `verified-replay`). Without it the timer is static: `systemctl enable` links nothing, D17's start arms it for the current boot only, and after the owner's next patch reboot (ops never reboots itself, `host_vars/zcrypto-ops/vars.yml:18-21`) no tick runs and `Persistent=true` has nothing to catch up until the next converge.
07:37 falls after these events:
- Fear & Greed's row for D, at about D 00:00Z.
- mempool's daily index after 00:00Z.
- The 90-day p90 Coin Metrics completion of every MVRV coin except avaxc and avaxp (btc 3.89 h at most).

It also falls 23 minutes before the 08:00 cycle, so the as-of view at that cycle reads what the recorder saw just before it.
19:37 catches late completions (btc's 90-day maximum was 43.25 h, avaxc's p90 179 h). It also measures same-day revisions and acts as the day's automatic retry, 23 minutes before the 20:00 cycle.
The timer comment records the slot clearance, as its siblings' comments do, because nothing checks slot collisions automatically:
- Minute 37 is clear of archive-pull's :12 and :42, panel's :22 and tape-bars' :52.
- 37 mod 5 is 2, so it is clear of grafana-watchdog's minutes ≡ 0 mod 5 and zaccess-probe's ≡ 4 mod 5.
- The hours are clear of 02:25 (ops reboot), 02:30 (data-gated tests), 03:41 (verify-replay) and 05:23 (verified-replay).

There is no catch-up beyond `Persistent`'s single tick at boot.
- Lost: once a day, the owner's word in marco's proposal and marco's first call. One transient failure would cost the day's snapshot unless someone acted by hand, and same-day revisions and late completions would never be measured.
- Lost: six ticks, 23 minutes before every cycle (the point-in-time design), each fetching a 10-day Coin Metrics probe, with the whole histories fetched once a day from 06:00Z and retried the same day. That gives first-seen at cycle resolution for about 24 KB a probe. But it needs two cadence classes, a due rule read back from the records and a gauge that resets at midnight, for a precision no pre-registered question asks for yet. The cadence is two lines to change later (open question 1).
- Lost: hourly ticks. That is 336 requests a day for daily series.
- Lost: `RandomizedDelaySec`. It adds noise to the first-seen time, and fixed slots are the only collision control the role has.
- Lost: `RequiresMountsFor` on the NAS mount. A NAS outage would block ticks.
- Lost: a timer with no `[Install]` section (the earlier draft). It stays armed only until the next reboot, and every day after that until a converge is lost for good.

## D3 — the fetch table is pinned in code, one URL per source id for ever, every free daily metric per asset

**marco's call.** The CLI pins the table above in code (`cli/vintage/sources.py` in the suggested split): source id, exact URL, body file name and check. A changed URL is a new source id, never a redefinition, and an id is never reused. Requests carry `Accept-Encoding: identity` and a fixed `User-Agent: zcrypto-vintage/<package version>` that names no person, and never a conditional header.
**Coin Metrics: one request per asset, with both `ignore_*` flags.** Each asset's request asks for every daily metric the catalog listed for it. The check (D8) fails any body from which a pinned metric is entirely absent, or in which a pinned metric froze or lost days it held before.
This reverses all three earlier designs, which refused `ignore_forbidden_errors`, and it does so by measurement:
- Without the flag, one forbidden pair turns the asset's whole request into a 403. That loses every metric of the asset at every tick until a code change ships through an ops re-pin.
- With the flag, the 200 carries every other metric.
- An unsupported pair is dropped silently with no flag at all.

Silence is the API's default either way, so only a presence check makes a lost metric loud. With the flag, the check pages while the other metrics' bytes keep flowing.
**Breadth.** The request asks for every daily metric, not only the six C3 names. A series not recorded today can never be recorded for today, and C3's features are not pre-registered. The cost is bytes, not requests: btc's 31 metrics are 8,341,605 raw bytes against 1,687,796 for the six.
**Asset ids.**
- The seven MVRV coins: btc, eth, xrp, ada, link, doge, ltc.
- `dot`, whose MVRV, market cap and supply stopped in 2022. It is a cheap check that frozen history stays frozen, and its stopped metrics are D8's named exemptions from the freshness bound.
- `avaxc` and `avaxp`, Coin Metrics Labs experimental series and the only free AVAX valuation.

**Catalog and status feed.** The catalog and the status feed are recorded every tick, so coverage changes and recalculation notices sit in the record beside the bodies they explain.
- Lost: the six C3 metrics plus the BTC and ETH exchange flows only, the recommendation of the other two designs. That is about a quarter of the bytes (open question 2).
- Lost: one `json_stream` for all assets. One transport failure would lose every asset's record that tick.
- Lost: no `ignore_*` flag and catalog-listed pairs only. A revocation would cost the asset's whole record until a re-pin lands.
- Lost: building the metric list each tick from that tick's catalog. That changes the request identity under the reader with no code change; the catalog is recorded instead.
- Lost: BGeometrics, Blockchain.com and `incidents.json`, for the reasons in the sources section.
- Lost: conditional requests on the weak ETags. A 304 records nothing.

## D4 — the exchange is stored as served, and judged second

**marco's call.**
**Storage.**
- The final attempt's body is stored as its raw bytes, whatever its HTTP status and whatever the check says, so a 403's or a 503's whole answer is kept as faithfully as a 200's history.
- An attempt that was retried keeps its first 4 KiB inline in its `attempts` entry, as `head`; the rest of its body is not kept.
- A body over D7's 64 MiB cap, or cut by the per-request or tick deadline, is not stored; its attempt records the reason and the byte count received.
- The bytes are gzipped at compresslevel 9 with mtime 0 and no file name, so the same body always yields the same file bytes.
- The sha256 and size of the raw bytes go in `tick.json`.
- Before publishing, each file is read back, decompressed and re-hashed. A mismatch refuses the tick with exit 2 and an ERROR.

**Exchange metadata.**
- Every response header is kept except `Set-Cookie`: an ordered list of pairs, duplicates kept.
- The record also keeps the final URL after redirects, the HTTP version, the status and the reason.

**Odd bodies.**
- A body served with a non-identity Content-Encoding is stored as served and graded as failing its checks.
- A non-2xx body is stored as its file like any other, and its source is graded not fetched (D8): the answer that broke a contract is kept whole.

**Modes.** Every file is created exclusive (`O_EXCL`, so an existing path is never truncated) with mode 0444. The tick directory is 0755 while it is assembled and 0555 from just after the rename that publishes it (D5); the date directories above it stay 0755. All are owned by `zcrypto-data`. Nothing parses a body to decide whether to store it.
- Lost: parsed rows or parquet. mempool's integers exceed 2^53, Coin Metrics numbers are strings, and `json` and `json_stream` treat nulls differently, so any re-serialisation changes the vintage. A parser bug found in a year would then be a year lost.
- Lost: storing an unchanged body as a reference to its hash, marco's earlier call. It never fires, because no body repeats between fetches, and it breaks the tick's self-containment.
- Lost: content-addressed `xz` blobs with one record file per exchange (the minimal design). `xz -6` is 6–26% smaller across the measurements above, 21% on the largest body (btc's 31 metrics: 1,390,008 against 1,750,182). But gzip reads with `zcat` on any host and with Python's stdlib without a second thought, and at about 7 GB a year on custody the bytes are not the constraint.
- Lost: delta compression against the previous tick. One corrupt file would poison every later one.
- Lost: a non-2xx body's first 4 KiB inline in `tick.json`, with no file (the earlier draft). It breaks the goal of every byte of the final answer, for bodies that are small and that the 64 MiB cap bounds anyway.

## D5 — the tick is one immutable directory, published by one rename, naming its predecessor

**marco's call.**
**Assembly and publication.**
- The tick stamp is the UTC start second, `YYYYMMDDTHHMMSSZ`.
- A tick is assembled under `staging/<stamp>/`, every file created exclusive and 0444 (D4), with `tick.json` written last.
- Each file and the directory are fsynced, then one `rename(2)` moves the directory to `record/<YYYY>/<MM>/<DD>/<stamp>/`, and the parent is fsynced. That rename goes through the tick-publish helper, one of the two renames D18 allows.
- The rename target must not exist. The check runs under the lock, so Python's `os.rename`, which has no no-replace flag, never meets one.
- Right after the rename, the tick directory is set to 0555, so a same-uid sibling container (the operating model) cannot add, rename or remove a file in it without a chmod first. A crash between the rename and the chmod leaves a published tick at 0755, and the next tick's scan sets it to 0555; a chmod changes no byte.

**Refusals and regressions.**
- A stamp whose target directory already exists (two runs in one second) is refused with exit 2 and an ERROR.
- A stamp at or below its predecessor's, a clock that stepped back or one corrected after a tick was published under a clock running ahead, is published with an ERROR naming both stamps. Publication order is the chain's, and the stamps are clock evidence like D6's, which the reader flags (step 9).
- A published directory is never opened for writing again.

A tick is published even when some or every source failed, because its attempt record is evidence.
**The chain.** `tick.json` names its predecessor in `prev`: the chain's head, the sha256 of its `tick.json` bytes, and `error`. The head is the published tick that no other tick's `prev` names, which D10's scan of every `tick.json` already finds. It is the newest stamp unless a regression was published. When a broken link leaves more than one candidate, the newest stamp among them is taken and an ERROR names the others. At an empty record, `prev` is null and `genesis_reason` says why.
**The chaining check.** Before computing `prev`, the recorder checks the head: its `tick.json` parses, its `fetches` name exactly the body files in its directory, and every listed body re-hashes to its entry. When the head fails, `prev` carries its stamp, the sha256 of its `tick.json` bytes as found (null when they cannot be read) and the failure in `error`, and an ERROR is logged; the tick is never refused for it, and a damaged head is never chained silently.
**The witness.** Each `tick.json`'s sha256, computed from the bytes written before the rename, is logged as `tick_json_sha256` in D9's witness line as soon as the rename returns, before the gauges and the re-verify, and repeated in the summary line. The ops journal keeps it, and so does Loki through the keep-regex (D17), for 90 days (`mon_retention_days` in `infra/ansible/roles/mon/defaults/main.yml`): outside both copies, so damage or a hand edit to a `tick.json` before its successor chains it cannot also rewrite the record of what was published. It is what a `tick.json` restore checks against (D15).
The chain lets `zcrypto vintage verify` (D15) detect, whatever the clock says, a tick lost after its successor chained it, in any copy. A head deleted before the next tick runs is chained around on ops; it leaves a fork in a copy that pulled it, which `verify` reports, and its INFO line in the journal. The chain also gives a trial a one-hash pin (the reader section).
- Lost: a per-file rename into a shared directory, as `rolling extend` does. A pull or a reader could see half a tick.
- Lost: an appended JSONL manifest. `--ignore-existing` would freeze it on the NAS at the length it had when first pulled.
- Lost: a directory of per-exchange records named by their own hash (the minimal design). Every file is verifiable by its name, but a tick is no unit a reader can copy alone, and one exchange's attempts scatter.
- Lost: no chain. A tick missing from the NAS copy would read the same as a tick never taken.
- Lost: refusing on a broken `prev`. It would stop recording over a doubt that `verify` reports anyway.
- Lost: refusing a stamp at or below the newest (the earlier draft). One tick published under a clock running ahead, such as a boot catch-up before chrony has synchronised (`chrony-wait.service` is disabled on this host), would refuse every later tick until the clock passed its stamp, and no act the anti-goals allow could clear it, since a published tick is never deleted.
- Lost: files 0644 and directories 0755 after publication (the earlier draft). Six containers with the same uid mount the whole ops data root read-write (the operating model), so only their code kept them out.
- Lost: the successor's `prev` as the only witness of a `tick.json` (the earlier draft). It hashes whatever bytes were on disk when the next tick ran, so damage or a hand edit before then entered the chain, and the restore rule sent the operator to copy the damaged bytes over the other copy's good ones.

## D6 — the recorder's own fetch end is the stamp, the server's Date bounds knowability from below, and the host's clock is evidence

**marco's call.**
**Per attempt.** Each attempt records `started_at` and `ended_at`, UTC to the microsecond, plus its monotonic duration. `ended_at` is taken after the last body byte, and it is the observation's stamp.
**Knowable time.** An observation's knowable time is max(`ended_at`, the final response's server Date + 1 s), or `ended_at` alone where no Date header parses; the as-of view reads it (the reader section, step 6). A host clock running behind stamps a body earlier than it could have been known, and no stamp regression reveals it, so without this floor the as-of view would look ahead by the clock's error. The 1 s covers Date's resolution. A clock running ahead stays conservative, and a cached body's older Date leaves `ended_at` in force. The Date header stays inside the stored headers.
**Host clock evidence.** Each `tick.json` carries a `clock` block:
- `zcrypto_clock_offset_seconds` and `zcrypto_clock_synchronised`, read from `/textfile/clock-offset.prom`, which the ops `zcrypto-clock-offset` timer writes every 5 minutes;
- that file's age.

A missing or unparseable file is recorded as nulls with a reason, never a refusal.
**AssetEODCompletionTime** is stored like every other metric and is never read as a publication time.
- Lost: `started_at` as the stamp. A body is not knowable before it has arrived; btc's body is 1.7 MB.
- Lost: Last-Modified. No source sets a meaningful one.
- Lost: `AssetEODCompletionTime`. It is a last-calculated time, and it was itself seen restated.
- Lost: the server's Date as the stamp. It has 1 s resolution, and a cached body's Date can be up to its max-age old (mempool's is 120 s).
- Lost: `ended_at` alone as the as-of time (the earlier draft). A tick under a clock running behind, such as a boot tick before chrony has synchronised, put a value into the view before it was knowable, and the reader only flagged it.
- Lost: refusing on a clock doubt. That loses an unrecoverable fetch over a doubt a reader can resolve later, and the ops clock rule already pages the cause.
- Lost: an NTP query from inside the container. It duplicates chrony and adds a network dependency to every tick.

## D7 — politeness and bounds: every tick ends

**marco's call.**
**Pacing.** Requests run in sequence, at least 1 s apart per host, with at most 3 attempts per request.
**Retries.**
- Only transport errors, timeouts, 429 and 5xx are retried.
- Wait for Retry-After (seconds or HTTP-date), capped at 300 s; without one, wait 30 s, then 120 s.
- No other 4xx is ever retried: a 403 or 404 is a contract change.

**Per-request bounds.** A 30 s socket timeout, and a 120 s whole-body deadline checked between chunks, since `urllib`'s timeout is per read and a server trickling bytes would otherwise hold the tick open.
**Per-host breaker.** Once one request to a host has used up its attempts on transport errors, the rest of that host's requests in the tick are marked not fetched without dialling.
**Tick deadline.** At 20 minutes, the remaining sources are marked not fetched and the tick is published.
**Size cap.** 64 MiB per response, about eight times the largest measured body (btc's 8.3 MB).
- Lost: retrying until success. A oneshot that never ends blocks the next tick and looks like a hang.
- Lost: parallel requests. They break Coin Metrics' per-IP limit, and that IP is also this workstation's.
- Lost: a unit `TimeoutStartSec` as the only bound. Killing the docker client leaves the container running, and the next tick then fails on the name conflict.
- Lost: budgeting to the `x-ratelimit-*` headers' 6000 per 20 s on a "download" plan, which disagree with the documentation.

## D8 — the check is lenient, structural, and never gates storage

**marco's call.** A source's outcome is 0 (ok), 1 (not fetched: a transport error, a non-2xx status whose body D4 still stores, oversize or deadline) or 2 (a 2xx body fetched and stored, but the check failed). A source is ok when it answered 2xx with identity encoding and its body passes its check.

| Source | Check | Newest-data bound |
|---|---|---|
| `fng` | `data` is a list of objects with `value` and `timestamp`, and `metadata.error` is null | newest row no older than the tick's UTC date − 1 |
| `cm-<asset>` | every line is a JSON object with `asset` and `time`, every pinned metric appears in at least one row, and every pinned metric passes the per-metric rules below | newest row no older than date − 1; per metric, the rules below |
| `cm-catalog` | an object whose `data` list is non-empty and that carries no `next_page_url`, so a catalog that starts paginating is never stored as if page one were the whole | none |
| `cm-status` | the bytes open with an XML or feed prolog and contain `<entry`; no XML parser runs, so there is no entity-expansion surface | none |
| `mempool-hashrate` | `hashrates` is a non-empty list | newest row no older than date − 3 |

**Per metric, for `cm-<asset>`.** The check tracks, for each pinned metric, the newest and the oldest day on which it carries a value, and grades the body 2 when any of these rules fails:
- **Freshness.** The metric's newest day is no older than the tick's UTC date − 3. That absorbs the worst completion measured for the MVRV coins, btc's 90-day maximum of 43.25 h, at a 07:37 tick. Every `avaxc` and `avaxp` metric (Coin Metrics Labs experimental series) is held to date − 30 instead, about four times avaxc's completion p90 of 179 h, checked against the plan's recorded bodies, so a frozen AVAX series still grades 2. One named exemption carries no freshness bound: the metrics whose newest day in the bodies the plan's session records is more than a year old, `dot`'s stopped MVRV, market cap and supply family, which the plan names from those bytes.
- **Never shorter at the top.** The metric's newest day is not earlier than in the source's last ok body. Exempt metrics are held to this too, so a frozen series may not shrink.
- **Never shorter at the bottom.** The metric's oldest day is not later than in the last ok body. The rolling-window `ReferenceRate*` metrics, which keep 7 points by design, are exempt.

The source-level bound is date − 1, because `PriceUSD` fills each row early (the btc row for 2026-11-10 carried it at 00:27:13Z on 11-11). For the full-history sources (`fng`, `cm-<asset>`, `mempool-hashrate`), the row count must also not fall below 90% of the last ok body of the same source.
A `json_stream` body carries no row count and no trailer, and over HTTP/1.1 it arrives chunked with no Content-Length, so a stream the server ends cleanly after a backend fault passes every line check; the per-metric rules are what catch it.
The outcome, its reason, the newest day, the row count, any absent metric and any metric that failed a per-metric rule go into `tick.json`. A failure is source-level when the whole body fails: a line or structure check, the source-level newest-day bound, a collapse or a non-identity encoding; every `fng` and `mempool-hashrate` failure is. A failure is per-metric when the check names the metric in `metrics_absent` or `metrics_failed`. The reader reads absences by that split (the reader section, step 2).
**Acknowledgment.** A failure stands, and pages, until code acknowledges it with a pinned entry in `cli/vintage/sources.py`: (source, metric, or `*` for a source-level rule, rule, the stamp of the tick from which it holds). From that tick on, the rule is not applied to that metric, or, for a rule that compares with the last ok body, the comparison restarts at the first body from that tick. The check names the entry it applied in `tick.json`, and the entry ships through an ops re-pin. The named exemptions above take the same form, holding from genesis.
- Lost: a strict schema check. Cosmetic vendor changes would page.
- Lost: "a 200 is ok". A redirect to an HTML page, a frozen series, a history quietly capped by new pagination or a revoked metric would read green for ever.
- Lost: comparing the row count with the previous stored body. A truncation would fail one tick and then read as normal; comparing with the last ok body keeps it failing, and paging, until code acknowledges it.
- Lost: one newest-row bound per source at date − 3 (the earlier draft). The newest row is `PriceUSD`'s, so a frozen network metric graded ok for ever, as `dot`'s 2022 stop shows, and a body that lost its newest one or two days, or up to a tenth of its oldest rows, graded ok.
- Lost: a per-metric bound at date − 1. btc's completion reached 43.25 h in 90 days, so an ordinary late day would grade a 07:37 tick 2.
- Lost: the date − 3 freshness bound on `avaxc` and `avaxp`. Their known completion lag would page as a fault.
- Lost: no freshness bound on `avaxc` and `avaxp` (the earlier draft). A frozen AVAX series graded ok for ever, the failure this check exists to catch; never-shorter-at-the-top catches a shrink, not a freeze.
- Lost: leaving "until code acknowledges it" unnamed (the earlier draft). The plan could neither implement nor test the end of a failing stretch.

## D9 — outcomes, exit codes and log levels

**marco's call.**
**Exit codes.** `zcrypto vintage record` catches every exception at its top level, and its exit code says whether a tick was published:
- 0 when it published the tick, every source is ok, the gauges were written and the tick's re-verify (D15) was clean;
- 1 only when it published the tick and something beside it is not ok: a source, the gauges or the re-verify;
- 2 whenever it published nothing. That covers every refusal (a held lock, a target that already exists, an unwritable staging or record directory, a read-back mismatch) and every exception raised before the publishing rename returned.

Python's own exit status for an uncaught exception is 1, the code that means "published", so no exception may leave the CLI uncaught, and D12's dead-man, pinged on 0 or 1, then means a published tick and nothing else.
**The lock's message.** `single_instance_lock` raises `CaptureError` on contention, with a message that names capture and `systemctl stop zcrypto-capture` (`cli/capture/command.py:56-59`), a unit `zcrypto-ops` does not have. The CLI catches it and logs its own refusal instead, naming `zcrypto-vintage-record.service` and the `docker ps -a --filter name=zcrypto-vintage-record` read, and exits 2. A lock the helper cannot take for any other reason (a read-only filesystem, no flock support) runs unlocked, named by the ERROR the helper logs itself (`cli/capture/command.py:61-65`).

**Log levels.**
- WARNING for each source that is not ok, naming the source, its outcome and the reason, because the not-recorded rule (D11) owns that event.
- ERROR for every refusal, a head that fails the chaining check (D5), a stamp regression published (D5), an unreadable `tick.json` met while scanning, a re-verify finding, and every unexpected exception. Those persist into the next tick and page now through `Ops · ERROR logs`, whose selector already admits `zcrypto-.*`.
- INFO for the witness line, `vintage tick published tick=… tick_json_sha256=…`, logged as soon as the rename returns and before the gauges and the re-verify, its hash computed from the bytes written before the rename: the tick's witness (D5).
- INFO for one summary line: `vintage record complete tick=… tick_json_sha256=… ok=… not_fetched=… failed_checks=… bytes=…`, which repeats the witness.

Every line goes through `cli.logging`, with no `typer.echo`.
- Lost: ERROR for each failed source. Every transient 503 would page twice, through the ERROR rule and later through staleness.
- Lost: failing the whole tick when one source fails. A partial failure must never cost the healthy sources.
- Lost: WARNING for refusals, as verified-replay logs them. A refusal repeats every tick until someone acts, and the staleness rule would take 25 h to say so.
- Lost: 1 for "a source failed" with exceptions left to Python (the earlier draft). An exception before publication then exits 1 too, and the dead-man stays green while no tick is published, exactly when Grafana's path may be dark.
- Lost: the imported lock's message as it stands. It would page an operator towards a capture unit that does not exist on this host.

## D10 — the gauges are a function of the record

**marco's call.** After publishing, the CLI scans every `tick.json` under `record/` (730 a year) and orders the ticks along the chain (D5). It then writes `/textfile/vintage.prom` atomically through the `.prom` publish helper, the second of the two renames D18 allows: a temporary file from `mkstemp`, `chmod 0644` (the collector is not root, and `mkstemp`'s 0600 would be unreadable), then a rename over the old file. Five families, labelled by `source`:
- `zcrypto_vintage_last_ok_timestamp_seconds`: `ended_at` of the source's latest ok fetch along the chain, 0 if there has never been one. Along the chain, not by the largest stamp, so a tick published under a clock running ahead cannot hold the gauge in the future and silence the rule.
- `zcrypto_vintage_outcome`: this tick's 0, 1 or 2.
- `zcrypto_vintage_body_bytes`: the raw size of the body this tick stored for the source, whatever its status, or 0.
- `zcrypto_vintage_days_missing`: UTC days, from the source's first tick through yesterday, with no ok fetch. A day whose only bodies graded outcome 2 counts: its bytes are stored, but none was good.
- `zcrypto_vintage_changed_values`: for `fng`, `cm-<asset>` and `mempool-hashrate`, the two-body reading of the reader section's step 7, between the source's previous ok body P and this tick's ok body N, read from those two bodies alone, per series S. It counts each (S, D) where both hold D with different tokens (a restatement); where P holds D and N does not, D lying inside the range of days N holds for S (a retraction); and where N holds D and P does not, D lying at or before S's newest day in P (a backfill, or a value restored after a retraction, changed or not, since telling a restoration from a restatement needs the last non-null token, which two bodies do not hold). A day after S's newest day in P is a first publication or a completion and does not count. Only ok bodies are compared, so an outcome-2 body's absences never count, and a value withheld in outcome-2 bodies and restored changed counts once, as a restatement, when the next ok body arrives. The family is computed by D16's code. Its line is left out for a source whose body this tick is not ok, the panel showing the gap, and in any tick where either body fails to parse (a WARNING names it). Restatement becomes a series on the dashboard from the second tick.

An unreadable `tick.json` met in the scan counts as no ok fetch, and the CLI logs ERROR naming the file. A refusal (exit 2) writes no `.prom`. Every family is charted on a new row of `infra/grafana/data-integrity-dashboard.json` (uid `zcrypto-integrity`).
- Lost: the runner parsing a summary line and carrying values forward, as tape-bars does. That is fourteen labelled sources pushed through `sed`, and a wording drift would read as green.
- Lost: a state file of last-ok times. It can disagree with the record, and deleting it would reset the hole count.
- Lost: a runner `.prom` with an exit code and a last-run time (the operator design). Two more families for what D11, the journal and `ops-postverify.sh`'s freshness read already show.
- Lost: a count of failed ticks today (the point-in-time design). It resets at UTC midnight, so a lost day stops paging; D11 pages before the day is lost without a series that resets.
- Lost: counting every value that appears where there was none as a completion (the earlier draft). A value retracted in one ok body and restored with a different value in the next was counted once, as a retraction, and never as the change it carries.
- Lost: comparing each tick with every earlier observation of (S, D). It would parse every stored body each tick; two ok bodies per source bound the cost, and the derivation answers the full history (D16).
- Lost: leaving a same-value restoration out of the gauge while counting it under the backfill rule (the earlier draft), so the gauge and step 7 disagreed. Leaving it out needs the last non-null token, which is the cost the bullet above refuses, so the gauge counts it and step 7 says so.

## D11 — one rule: a source not recorded in 25 hours

**marco's call.** The rule:
- uid `zcrypto-ops-vintage-not-recorded`, title `Ops · vintage source not recorded`, ruleGroup `zcrypto-ops`;
- refId A, `time() - zcrypto_vintage_last_ok_timestamp_seconds`, instant; threshold C `gt 90000`;
- `noDataState: Alerting`: no series means the textfile, Alloy or the host is gone, and that is the alarm, so the rule is pushed only after the first tick has produced the series;
- `execErrState: Alerting`, `for: 5m`, severity `warning`, receiver `metrics`;
- `__dashboardUid__: "zcrypto-integrity"`, a quoted `__panelId__` naming a panel whose bar sits at 90000, and a `unit` annotation;
- a summary that interpolates no host and ends `Runbook: infra/runbooks/ops-node.md#zcrypto-ops-vintage-not-recorded`.

It fires per source.
**Timing.** A single failed tick never pages: the next ok fetch lands about 24 h after the one before the failure, and the 20-minute tick deadline keeps it under 25 h. In the worst case, the last ok fetch was at 19:37 on D−1 and both of D's ticks fail. The age then crosses 25 h at about 20:38 on D, and the rule pages at about 20:43, roughly 3 h 15 min before UTC midnight, while `sudo systemctl start zcrypto-vintage-record.service` can still record D. A source whose last ok fetch is 0 (new, never ok) fires, which is correct.
- Lost: the daily peers' 48 h (`zcrypto-ops-verified-replay-stale`). It fires only after a day is already gone.
- Lost: 13 h. It pages on every tick the next one heals.
- Lost: an exit-code rule. Explicit drop: it pages within the hour for the same event this rule owns, and refusals already page through `Ops · ERROR logs`.
- Lost: a rule on `days_missing > 0`. Explicit drop: it would fire for ever after the first hole. Each hole is paged while it is still preventable and stays visible on the chart.
- Lost: a clock-gated "today not yet recorded" expression. It is empty before its gate, and noData Alerting would then page every night.

## D12 — a dead-man check backs the rule when Grafana's path is dark

**marco's call.** The check:
- slug `zcrypto-vintage-record`, timeout 90000 s and grace 21600 s (verify-replay's), so it goes down about 31 h after the last published tick, after the 25 h rule;
- pinged by the runner with `curl -fsS -m 10` when the `docker run` exits 0 or 1, and on no other code. D9 reserves 0 and 1 for a published tick and catches every exception so none exits 1 by default, so a ping means a tick was published and the check's silence means none was: the recorder stopped, crashed before publishing, or could not start its container (docker's own 125 to 127 and a kill's 137 never ping).

Wiring:
- `ops_vintage_record_healthcheck_url: "{{ hc_ping_base }}/zcrypto-vintage-record"` in `infra/ansible/host_vars/zcrypto-ops/vars.yml`, with a role default of `""`;
- a fixture entry in `tests/fixtures/healthchecks_descriptions.json` (12 to 13), whose description links `Runbook: infra/runbooks/ops-node.md#zcrypto-ops-vintage-not-recorded`;
- `vintage_record` added to `OPS_CHECKS` in `tests/test_infra_hc_role.py` (6 to 7, `SLUGS` 12 to 13), and the runner's install task added to `PING_RENDERS` with the runner's own commit;
- **one commit**, so no commit between is red, holding everything the count couples: the fixture row; the host_vars URL; `OPS_CHECKS` with the `== 12` at `tests/test_infra_hc_role.py:891` moved to 13, since that test also holds `set(_ping_url_vars()) == set(SLUGS)` and the slugs equal to the fixture's names; `tests/test_ops_daily.py:2514` (`len(checks) == 12`); `tests/test_hc_provision.py:258`, `:260` and `:268` (`* 12` and `== 12`; its `TWELVE` list is computed from the fixture); the `apply` help string of `infra/scripts/hc-provision.py:285` ("write the twelve checks"); and the count-named names renamed count-free with their call sites: `TWELVE`, `_the_twelve` and the docstring at `tests/test_hc_provision.py:224` ("Twelve checks on the service"), its test names carrying `eleven` (`:242`) and `twelve` (`:305`, `:316`), `test_the_ping_url_variables_are_the_twelve_rows_…` at `tests/test_infra_hc_role.py:887`, and `twelve` and `_twelve` at `infra/scripts/hc-provision.py:162-167`;
- that commit lands after the `infra/runbooks/ops-node.md` section exists, because `tests/test_ops_daily.py:2515` runs `check_descriptions` (`infra/scripts/ops_daily.py:519-528`), which fails a `Runbook:` link whose anchor the page lacks;
- through `zcrypto-refine-rules`, every "twelve" and "12" that counts the checks in `infra/runbooks/hc.md` (lines 118, 122, 144, 217, 251 and 270) and `infra/runbooks/drills-telemetry.md` (lines 943 and 971, "`200 12`"), each to 13;
- a row in the dead-man table of `infra/runbooks/observability.md`.

The owner provisions the check with `infra/scripts/hc-provision.py` before the converge that renders the URL.
- Lost: no dead-man, as tape-bars has none (the minimal design). Every unbackfillable stream in this fleet has a failure domain outside Grafana, and the daily peers, verify-replay and verified-replay, carry one.
- Lost: pinging only when every source is ok, as verified-replay does. One broken source would page twice.
- Lost: a 12 h timeout. It would race the rule and page twice for one event.
- Lost: the runner pinging only when the newest tick directory is newer after the run than before. It is a second reading, by a root shell walking `record/`, of what the exit code says once D9 reserves 0 and 1 for a published tick.

## D13 — layout, mounts and the lock

**marco's call.** The root is `/var/lib/zcrypto-ops/vintages/` (`ops_vintages_subdir: vintages`). It holds:
- `record/`, 0755, the NAS channel's root;
- `staging/`, 0750, on the same filesystem and never pulled;
- the lockfile `.capture.lock`, which `single_instance_lock` (imported from `cli.capture.command`, never edited) creates in the directory it locks, here `vintages/`, outside the pulled root. Its contention message names capture, so the CLI replaces it with its own (D9).

The role creates `vintages/`, `record/` and `staging/` with no digest gate, owned by `zcrypto-data`.
**Mounts.** The container's data mount is the whole of `vintages/`, because `rename(2)` across two bind mounts fails with EXDEV even on one filesystem (the reason in `tape-bars.sh.j2`'s comment on its own mount). `textfile/` is mounted read-write at `/textfile`, as the reconcile run does.
**Crash leftovers.** A crashed tick's `staging/<stamp>/` is never published. Each later tick names the leftovers in one WARNING, and the runbook says to read them and then delete them by hand.
- Lost: staging in `hot-out-staging/`. It would add a second writer to `rolling extend`'s staging.
- Lost: mounting the whole of `/var/lib/zcrypto-ops` read-write, as tape-bars does. That widens the container's write surface to every ops dataset.
- Lost: the CLI deleting stale staging. That would be the recorder's only delete path, written for a crash-only leftover the pull never sees.
- Lost: the lock inside `record/`. The lockfile would ride to the NAS for good.

## D14 — NAS custody is a fifth ops-sourced pull channel (the NAS loop's ninth), a raw rsync where the first bytes win

**marco's call.** Custody, not hot. The record grows for ever, cannot be backfilled and is read in place, which is the custody cluster's definition (`docs/reference/data-catalog-full.md:127-129`).
**Wiring.**
- **Keys.** A key pair `sync_vintages`, both halves committed to the branch by the owner in one commit before the plan's channel task: the public half at `infra/ansible/files/sync_vintages_ed25519.pub`, and the private half ansible-vault-encrypted at `infra/ansible/files/sync_vintages_ed25519`, as every sync channel's is ("NAS + vaulted here" in `infra/ansible/files/README.md`, which gains the channel's row). `tests/test_infra_pull_channel_keys.py::test_the_tree_has_no_defects` fails a `.pub` without its vaulted sibling, and the implementer never reads a vault-shaped path, so the commit is the owner's. The public half is looked up as `ops_sync_vintages_authorized_key` in `host_vars/zcrypto-ops/vars.yml`, whose comment on "the four NAS pull-channel public keys" becomes five. The owner also places the private half on the NAS at `keys/sync_vintages` (0600, 1000:1000).
- **The ops side.** An `authorized_key` task in the ungated preamble beside the other four, `command="/usr/bin/rrsync -ro {{ ops_data_dir }}/{{ ops_vintages_subdir }}/record",restrict`.
- **NAS settings.** Compose env `VINTAGES_SOURCE`, `VINTAGES_DEST=/archive/vintages`, `VINTAGES_SSH_KEY=/keys/sync_vintages` and `VINTAGES_SSH_PORT`; two `env.j2` lines; and `nas_vintages_source` and `nas_vintages_ssh_port` in `host_vars/nas/vars.yml`.
- **The pull block.** A block in `infra/nas/pull-entrypoint.sh` after the hot block runs `rsync --archive --ignore-existing --chmod=D0775,F0664` over the hot block's pinned ssh options, never `--delete`, then D15's incremental verify of the NAS copy.

**Failures.** A failed pull logs ERROR, and so does a verify finding. An unset source logs ERROR too: the reconciled block's "never silently" precedent, which logs at WARNING, raised to ERROR because this tree is unbackfillable. All three page through `zcrypto-nas-archive-pull-errors`, and `infra/runbooks/nas.md` lists each line.
The copy lands at `/volume1/ZhaoCrypto/vintages`, read in place as `/mnt/zhao-crypto/vintages`. Recording starts at the attended first tick, taken only once the NAS loop has reached this block cleanly on the empty `record/` (the deployment order), so, when the NAS converge finishes before the timer's first slot, the ops copy is never the only copy for longer than one pull interval.
- Lost: the `hot-out` outbox (the minimal design). It needs no NAS change. But hot is chartered as "The `~140 MB` stable working set every research node needs local" (`docs/reference/data-catalog-full.md:7`), and `data fetch` mirrors it whole, while this set grows by about 7 GB a year for ever. It would also share the hot pull's failure domain: one unreadable file fails the rsync with exit 23 and stops `ohlc-rolling` too.
- Lost: a `zcrypto archive pull` channel carrying parquet records with sidecars (the point-in-time design). Its `rsync -a` runs without `--ignore-existing`, so a changed ops file would overwrite the custody copy, and its lag figure reads hourly parquet paths this set does not have.
- Lost: a subtree under `liquidations/`. One dataset would ride another's channel, prune and lag logic.
- Lost: an ops-only tree. That is sole custody on NVMe, which spec 00051 D10 rules out.
- Lost: skipping silently when the source is unset, as hot and liquidations do. Unwired custody of unbackfillable data is an anomaly.

## D15 — integrity and arrival are proven by one read, `zcrypto vintage verify`, run on both copies on a schedule, and repaired only by a hash-checked restore

**marco's call.** `zcrypto vintage verify --root <record root>` is read-only:
- it reads every `tick.json` and walks the chain from genesis to the head;
- it re-hashes bodies' raw bytes against their entries: every body by default, or, with `--newest N --slice K --slices M`, the bodies of the newest N ticks along the chain from its head (D5), never by stamp, so a tick published after a regression is among them, and of every tick whose position in stamp order is K modulo M;
- it reports, by path, the first broken link, a missing tick, a missing or tampered body, an unreadable manifest, a fork (two ticks naming one predecessor, both named: the trace a head deleted before its successor ran leaves in a copy that pulled it), and a file in a tick directory that its `tick.json` does not list, rsync's temporary `.<name>.XXXXXX` among them;
- it names a stamp at or below its predecessor's as a clock regression (D5), which is not a break;
- it names, and does not count as a break, a link whose successor's `prev` carries the chaining check's `error` (D5), and a link code acknowledges (the restore below), whose predecessor's `tick.json` it hashes against the acknowledged sha256; the predecessor's bodies are re-hashed either way;
- it verifies an empty record clean;
- it exits 0 when clean and 1 otherwise.

**Where it runs.**
- **Every ops tick.** After the publish and the `.prom`, the record step runs the same check over `/data/record`, with the newest 4 ticks and the slice of 14 that the count of published ticks names, so each ops body is re-hashed within a week. A finding is an ERROR naming the path, and the tick exits 1 (D9).
- **Every NAS loop.** Right after the vintages rsync: `zcrypto vintage verify --root "$VINTAGES_DEST" --newest 4 --slice "$slice" --slices 24`, `$slice` being the loop's existing 1/24 counter (`pull-entrypoint.sh`, spec 00102 D3), so the newest four ticks are hashed at once, and every other tick, a catch-up pull's older arrivals among them, within 24 loops. A finding logs `vintages verify failed (dest=…), continuing` at ERROR. This runs the archive-pull container's own `zcrypto`, so `nas_capture_image` must first move to a `-compat` build that carries the subcommand (the deployment order).
- **By hand, whole.** On the ops copy and, from the workstation, on the NAS copy in place: the rollout's arrival proof and the runbook's integrity read.

**Restore.** A finding is repaired only by hand, from the other copy, and only with the published bytes. For a body, they are the bytes whose sha256 equals the one a verified `tick.json` records for it. For a `tick.json`, they are the bytes whose sha256 equals its witness, the `tick_json_sha256` its INFO line logged at publish (D5); the successor's `prev` stands in for the witness only where the two agree or, the witness past Loki's 90 days or never logged (a run killed between the rename and the witness line), where both copies verified that link clean before the damage. Where the successor's `prev` and the witness disagree, damage or an edit the chaining check could not see entered the chain: the witness names the published bytes and `prev` the damaged ones, and which copy gets which bytes is the owner's decision against the witness, never a copy of whichever bytes match `prev`. That link then stays broken in every copy, since the successor's `tick.json` is never rewritten, so code acknowledges it in the form D8's acknowledgment takes: a pinned (successor stamp, the `prev` hash it recorded, the witnessed hash) entry in `cli/vintage/`, against which `verify` hashes the restored `tick.json` and names the link; the entry ships through an ops re-pin and a NAS re-pin. A link whose `prev` carries the chaining check's `error` needs no entry: its predecessor is restored against the witness. The bytes put back are the published bytes, so a restore is not a rewrite (the anti-goals). The runbook section (Observability) gives the commands for each copy: on ops, the tick directory is made writable for the copy and set back to 0555.
Path drift between the role's `rrsync` root and the CLI's `record/` is held by a converge-guard test.
- Lost: verify only at rollout and by hand (the earlier draft). Nobody is scheduled to run it, a file damaged as it lands on the NAS stays damaged under `--ignore-existing`, and the other copy may be gone by the time a reader looks.
- Lost: no repair path. A damaged copy would fail `verify` and log ERROR every tick for ever, and readers would learn to step past a red `verify`, which the reader section's step 1 forbids.
- Lost: a whole re-hash on every NAS loop. The Atom already stretched the hourly loop to about 103 minutes (the loop's own comment), and the slice bounds the cost to a twenty-fourth of the record per loop.
- Lost: a hand `sha256sum` of one tick (the operator design). It compares one tick, while `verify` proves a whole copy.
- Lost: a `verify` that read neither forks nor unlisted files and took `--newest` by stamp (the earlier draft). A head deleted before its successor ran left the NAS copy's fork unreported, a pull killed mid-file left its temporary file unreported, and after a published regression `--newest` skipped the tick just copied.
- Lost: a runner-side check of the hub copy through the automount, with a hub-lag gauge and rule. It adds an NFS read to the tick path for failures the NAS ERROR rule and dead-man already page.
- Lost: a daily-pass row reading the hub copy. Explicit drop: it touches `.claude/skills/zcrypto-daily-ops/SKILL.md`, a Fable-floor path, for one read `verify` already gives.

## D16 — the derivation ships as code and tests; the derived dataset is the first trial's

**marco's call.** `cli/vintage/derive.py` holds pure functions from a record root to observations and versions, by the rules in the reader section: each (series, day) keyed on the parsed UTC day; each new token judged against the last non-null token seen for that (series, day), and a first publication against the series' high-water day; inherited history set per series; an outcome-2 body's absences taken as no evidence for the series its check names, or for every series when it failed at source level; Q3's lower end read from any earlier observation that is evidence D was not yet held; and the as-of view read from the versions at each observation's knowable time. In production it computes D10's `changed_values`. In tests it is proven on fixtures to answer the three questions and the as-of view with no look-ahead.
This change ships no `derive` command, no published versions set and no registry or `ObservedReader` arm. Explicit drop: the first C3 trial spec decides what it derives and pins.
- Lost: judging each token against the one just before it, and setting inherited history per source (the earlier draft). A value withheld for a while and restored changed read as a completion and dropped out of Q2; a series first carried after the source's first tick had its whole revised history labelled first published; and a change in a vendor's time format re-keyed every day.
- Lost: one evidence-of-absence rule for both a retraction and Q3, and an as-of view over raw observations (the earlier draft). Q3 had no lower end for an ordinary new day, and an outcome-2 body's unevidenced gaps came back as holes in what a trial reads as of t.
- Lost: deciding first publication against the newest day in the previous observation that carried S (the earlier draft). An outcome-2 body whose newest day went back made a never-seen day behind the high-water day read as first published.
- Lost: leaving every reader to the trial spec (the minimal and operator designs). A capture defect found once months of ticks exist cannot be recaptured: a field the record drops, a header it lacks, a completion it cannot tell from a restatement. The derivation tested now is the capture format's acceptance test.
- Lost: a `zcrypto vintage derive` command writing a versions dataset now (the point-in-time design). It would publish a format no consumer has asked for, which the trial may want differently.

## D17 — converge wiring and log shipping

**marco's call.** The job gets its own block in `infra/ansible/roles/ops/tasks/main.yml`, gated on `ops_image_digest is defined` and placed after the getent facts. The block:
- installs the runner (root 0700, `no_log`, `diff: false`);
- renders the unit and timer (0644, registered);
- enables and starts the timer alone, under the register-based guard `when: not (ansible_check_mode and <register> is changed)`, so a first install previews under `--check`; the enable links the timer into `timers.target` through its `[Install]` section (D2), so it is armed again after every reboot.

The converge never starts the service, and a converge without the digest leaves the timer as it was. The ungated preamble creates the directories and the key.
**Log shipping.** `config.alloy`'s journal keep-regex gains `vintage-record`. Its Alloy converge (`--tags alloy` with `ops_alloy_digest`) lands before the image converge, or the drift assert refuses that converge.
- Lost: appending to the shared replay, panel and tape-bars loops. That renames task names pinned by `tests/test_infra_converge_guards.py` and `tests/test_infra_hc_role.py`, and couples the job to the panel-hold opt-out.
- Lost: archive-pull's unguarded enable. It fails the `--check` preview of a new timer, and `converge.sh` then refuses the real pass.
- Lost: leaving the journal unshipped with a `_JOURNAL_NOT_SHIPPED` row (the minimal design). The runbook's first read is the journal, and refusals must reach `Ops · ERROR logs`.

## D18 — no prune, no delete, anywhere

**marco's call.** Nothing under `record/` or `staging/` is ever deleted, replaced or rewritten by the recorder, on ops or on the NAS, and no code path prunes. Growth is watched by what already exists:
- `zcrypto-ops-disk-low` on the ops root (3.3T free);
- `zcrypto-nas-disk-low` on the NAS;
- the `body_bytes` chart, whose per-tick sum is the growth rate.

A runaway body stops at D7's 64 MiB cap.
**The two renames.** The recorder renames in exactly two places, each through one named helper:
- the tick-publish helper, which moves a staging directory into `record/` under the lock, after its target-absent check (D5);
- the `.prom` publish helper, which renames the temporary textfile over `/textfile/vintage.prom` (D10). That is a replace, of a file outside the record that the CLI alone writes.

**The guard.** A test walks the `cli/vintage/` modules' syntax trees and holds an allowlist, so a call it does not know fails rather than passes:
- a rename (`os.replace`, `os.rename`, `os.renames`, `Path.replace`, `Path.rename`) only inside the two helpers' bodies;
- every `os.open` carries `O_CREAT` and `O_EXCL` in flags the syntax tree spells, or none of `O_WRONLY`, `O_RDWR`, `O_TRUNC` and `O_APPEND` (a directory opened to fsync it); flags it cannot read fail;
- `tempfile.mkstemp` only inside the `.prom` helper's body;
- every other opening call, `open`, `Path.open`, `io.open`, `codecs.open`, `gzip.open` and `gzip.GzipFile` among them, only with a literal read mode, except a `gzip.GzipFile` given a `fileobj`, which is how a body is compressed onto a file from an exclusive `os.open`;
- no `shutil` copy or move (`copy`, `copy2`, `copyfile`, `copytree`, `move`), no `os.truncate`, `os.remove`, `os.unlink`, `os.rmdir`, `os.removedirs`, `shutil.rmtree`, `Path.unlink`, `Path.rmdir`, `Path.write_bytes` or `Path.write_text` anywhere.

`os.chmod` stays allowed: D5 sets published modes with it, and it changes no byte. Each rule is proven with `infra/scripts/mutate-probe.sh`: an allowed form passes, and the same call outside its helper, or an `os.open` without `O_EXCL`, a write-mode `gzip.open` or a `shutil.copyfile`, fails.
- Lost: a rolling prune of the ops copy once the NAS holds it. That is a delete path on unbackfillable data, to save about 7 GB a year against 3.3 TB.
- Lost: a tree-size gauge and rule. The cap and the host rules already bound it.
- Lost: a flat ban on `os.replace` and the deletes alone (the earlier draft). D10's `.prom` publish is a replace by design, the ban pushed it to `os.rename` or `Path.replace`, which overwrite the same way and were not banned, and so the invariant it claimed was false.
- Lost: a ban list of write calls (the earlier draft). It missed the primitive D4 names, `os.open` without `O_EXCL`, and `gzip.open`, `io.open`, `codecs.open` and the `shutil` copies, each of which truncates or overwrites an existing path.

## D19 — tests read fixtures in each source's real shape, with provenance; no live-network test

**marco's call, pending the owner's answer to open question 4.** The repository is public, so a committed fixture is published.
**The real bodies.** Before the plan's Task 1, the session writing the plan fetches one real body per source kind and keeps it out of the tree, under `.local/vintage-bodies/` in the main checkout, which is gitignored and kept; the plan records each body's file name and sha256, so the plan review finds and verifies the bytes it re-reads. The check and the derivation must meet the real shapes, so every fixture is built from one of these bodies.
**The committed fixtures.** `tests/fixtures/vintage/` holds one body per source kind:
- alternative.me's `fng` body, real and whole, since its API terms permit use "in any way you like", with its attribution in the provenance;
- for Coin Metrics (`cm-<asset>`, `cm-catalog`, `cm-status`) and `mempool-hashrate`, a body synthesised in the real body's shape that carries no value the vendor served, written by a committed deterministic generator under `tests/` from a committed shape file and a seed. The shape file holds the field names, the metric names (which the code pins anyway), the key order, the encodings, the token shapes (`json_stream`'s absent keys, a partial last row, the epoch-string `AssetEODCompletionTime`, numbers as JSON strings, and integers past 2^53) and the days its rows cover, and no value; the generator draws every value token from the seed.

Each body has a `.provenance.json` holding the real body's URL, fetch time, sha256 and size, whether the committed bytes are that body or synthesised from it and how (the generator, its seed and the shape file), and the source's attribution and licence.
**The bound.** Every body synthesised from a shape file, a second tick's included, holds at most 120 rows (entries, for the catalog and the status feed), enough for the shape cases and the comparison rules. Every fixture file, `fng`'s real body and any second tick edited from it among them, stays under 500 KB, the default of `check-added-large-files`, which `.pre-commit-config.yaml` runs with no arguments. The measured btc body is 8,341,605 bytes and today's largest tracked fixture 75,443 bytes; `fng`'s real body, 301,997 bytes, fits whole.
**Synthetic second ticks.** Written by the same generator from those bodies, each labelled synthetic in its provenance and held to the bound: a restatement; a completion; a retraction; a metric gone; a metric gone and then restored with a changed value; a series absent at genesis and carried later; a backfilled gap; a change of the vendor's time format; a history collapse; a body that lost its newest days; a frozen metric; a paginated catalog; a non-2xx body; and a token beyond 2^53.
**The network.** The opener is stubbed, and no test dials the network. The recorder's own twice-daily paged run is the live contract check.
- Lost: a test per source gated on `ZCRYPTO_LIVE_VENUE_TESTS`. It proves only that three hosts are up, it spends the sources' per-IP budgets from the recorder's own IP, and it adds a skip reason that reads as a pass.
- Lost: shapes invented without reading a real body (the minimal design). The check and the derivation read bodies now, so each synthesised body is built from a real one, which its provenance names by hash.
- Lost: trimmed real bodies committed for every source (the earlier draft). The repository is public, so that publishes Coin Metrics data under CC BY-NC and mempool.space data that carries no licence grant (open question 4).
- Lost: a sha256 that differs from the real body's as the proof of synthesis (the earlier draft). One changed byte passes it, so a lightly edited vendor body would be published; regenerating the committed bytes from the shape file and the seed proves every value is the generator's.
- Lost: synthesised bodies at the real length. btc's body alone is over sixteen times the commit gate's 500 KB.
- Lost: fixtures kept out of the tree altogether. CI could not run the check and derivation tests.

## The on-disk layout and the manifest

```
/var/lib/zcrypto-ops/vintages/                  zcrypto-data 0755; the container's /data; created by the role, no digest gate
├── .capture.lock                               single_instance_lock's flock
├── staging/                                    0750; same filesystem; never pulled
│   └── 20261112T073700Z/                       a tick being assembled, or a crashed tick's leftover
└── record/                                     0755; the sync_vintages rrsync -ro root
    └── 2026/11/12/                             0755
        ├── 20261112T073700Z/                   published by one rename, then 0555; never written again
        │   ├── tick.json                       the tick's manifest, written last; every file 0444
        │   ├── fng.json.gz
        │   ├── cm-btc.jsonl.gz  cm-eth.jsonl.gz  cm-xrp.jsonl.gz  cm-ada.jsonl.gz  cm-link.jsonl.gz
        │   ├── cm-doge.jsonl.gz cm-ltc.jsonl.gz  cm-dot.jsonl.gz  cm-avaxc.jsonl.gz cm-avaxp.jsonl.gz
        │   ├── cm-catalog.json.gz
        │   ├── cm-status.atom.gz
        │   └── mempool-hashrate.json.gz        a final answer of any status has its file; no body, no file, and tick.json says why
        └── 20261112T193700Z/ …
/var/lib/zcrypto-ops/textfile/vintage.prom      the CLI's, 0644
/usr/local/sbin/zcrypto-vintage-record          the runner, root 0700
/etc/systemd/system/zcrypto-vintage-record.{service,timer}
NAS: /volume1/ZhaoCrypto/vintages/2026/11/12/20261112T073700Z/…   (/mnt/zhao-crypto/vintages), D0775/F0664
```

`tick.json` is one JSON object, stored compact with sorted keys and a trailing newline. It is shown here indented, with every byte count and hash a placeholder:

```
{
  "schema": 1,
  "tick": "20261112T073700Z",
  "started_at": "2026-11-12T07:37:00.412305Z",
  "ended_at": "2026-11-12T07:37:41.118204Z",
  "recorder": "<package version>+<first 12 of ZCRYPTO_BUILD_REVISION>",
  "prev": {"tick": "20261111T193700Z", "tick_json_sha256": "<64 hex>", "error": null},
  "genesis_reason": null,
  "clock": {"offset_seconds": 0.001150123, "synchronised": 1, "prom_age_seconds": 37.4, "error": null},
  "fetches": [
    {
      "source": "cm-btc",
      "url": "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets=btc&metrics=AdrActCnt,…,volume_reported_spot_usd_1d&frequency=1d&format=json_stream&ignore_forbidden_errors=true&ignore_unsupported_errors=true",
      "request_headers": [["Accept-Encoding", "identity"], ["User-Agent", "zcrypto-vintage/<package version>"]],
      "attempts": [{"started_at": "2026-11-12T07:37:03.118204Z", "ended_at": "2026-11-12T07:37:05.902117Z", "status": 200, "error": null, "head": null}],
      "final_url": "<the url unless redirected>",
      "http_version": "HTTP/1.1",
      "status": 200,
      "reason": "OK",
      "headers": [["Date", "Thu, 12 Nov 2026 07:37:03 GMT"], ["Content-Type", "application/x-ndjson"], ["Cache-Control", "no-cache"], ["x-ratelimit-limit", "6000, 6000;w=20;comment=\"sliding window\""]],
      "body": {"file": "cm-btc.jsonl.gz", "bytes": "<raw size>", "sha256": "<sha256 of the raw bytes>"},
      "check": {"outcome": 0, "reason": null, "newest_day": "2026-11-11", "rows": "<n>", "metrics_absent": [], "metrics_failed": []}
    }
  ]
}
```

A source not fetched has an `attempts` list carrying each error and `"check": {"outcome": 1, "reason": "HTTP 403 (no retry)", …}`. Its final answer's body, of whatever status, is stored as its file and named in `body`; `body` is null only when no body was kept (a transport error, oversize or a deadline). An attempt that was retried carries its first 4 KiB in `head`. `metrics_failed` names each metric that failed a D8 per-metric rule, with the rule.

A sample `vintage.prom`, one line per source per family:

```
# HELP zcrypto_vintage_last_ok_timestamp_seconds Unix time a source's latest good fetch ended, read along the chain of recorded ticks; 0 when it has none.
# TYPE zcrypto_vintage_last_ok_timestamp_seconds gauge
zcrypto_vintage_last_ok_timestamp_seconds{source="fng"} 1794469061.118204
# HELP zcrypto_vintage_changed_values Values this tick's good body replaced, withdrew or filled in behind the newest day of the source's previous good body; new days are not counted.
# TYPE zcrypto_vintage_changed_values gauge
zcrypto_vintage_changed_values{source="cm-btc"} 0
```

The unit and timer, rendered from `vintage-record.service.j2` and `vintage-record.timer.j2`:

```
[Unit]
Description=Twice-daily recording of free data sources' whole responses
Requires=docker.service
Wants=network-online.target
After=docker.service network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/zcrypto-vintage-record

[Timer]
OnCalendar=*-*-* 07:37:00
OnCalendar=*-*-* 19:37:00
Persistent=true
Unit=zcrypto-vintage-record.service

[Install]
WantedBy=timers.target
```

## How a reader derives vintages and restatement diffs

1. **Read and verify.** A reader opens a record root read-only, either the ops copy or the NAS copy, and runs `verify` (D15) first. It never steps past a broken link silently.
2. **Observations.** A fetch whose final status is 200 and whose body is complete is an observation, stamped by its `ended_at` and knowable from max(`ended_at`, its final response's server Date + 1 s), or from `ended_at` alone where no Date parses (D6). An outcome-2 body is an observation flagged with its check's reason, and the values it holds are evidence. Its absences are evidence for a series S, as an ok body's are, unless its check names S in `metrics_absent` or `metrics_failed` or it failed at source level (D8), since a body graded 2 for a metric gone, a lost day or a collapsed history can lack what the vendor still holds. An outcome-1 fetch is a non-observation, "the source did not answer at t", which is distinct from "no tick at t".
3. **Parsing.** Bodies are parsed token-preserving, with `json.loads(…, parse_int=str, parse_float=str)` (shown by an earlier design reading to keep `826267196366358300000` and `1.50` exactly). A `json_stream` body is one object per line, and an absent key reads as null. A series is `cm/<asset>/<metric>`, `fng/value`, `fng/value_classification` or `mempool/avgHashrate`. Its key is the UTC day parsed from the row's own `time` (an ISO time) or `timestamp` (epoch seconds), never the token text, so a change in a vendor's time format does not re-key its history. Its value is the token text.
4. **Versions.** For each (S, D), observations are ordered by `ended_at`, which is the chain's order except across a published clock regression, where the chain's order is taken (step 9). An observation is evidence about (S, D) only when it carries S. S's high-water day before an observation is the newest day S held in any earlier observation that carried S. Absence is read two ways, each only from an observation that carries S and whose absences are evidence for S (step 2):
   - evidence that D was withdrawn, for a retraction: the observation does not hold D, and D lies inside the range of days it holds for S;
   - evidence that D was not yet held, for Q3's lower end: the observation does not hold D, whether D lies inside its range or after its newest day.

   Each token is judged against the last non-null token seen for (S, D), never against the observation just before:
   - no earlier token, and D after S's high-water day: a first publication; per series, this covers what a row-level reading calls a completion, a Coin Metrics row whose network fields arrive after its `PriceUSD`;
   - no earlier token, and D at or before S's high-water day: a backfill, never a first publication, even where the observation just before, an outcome-2 body whose newest day went back, held less;
   - a token different from the last one: a restatement, whatever absences lay between;
   - the last token again after a retraction, an absence this step read as withdrawn: a restoration, a version first seen at that observation, which Q2 lists apart from restatements and the as-of view returns; the same token again after an absence that was no evidence makes no new version;
   - absent where the last token was a value, in an observation that is evidence D was withdrawn: a retraction.
5. **The three questions.**
   - First published, Q1: the token of (S, D)'s first publication by step 4, with its `ended_at`. A day inherited (step 8) or backfilled has no Q1.
   - Restated, Q2: every later version, each named for what it is (a restatement, a retraction or a restoration), with the `ended_at` at which it was first seen.
   - First appeared, Q3: the bracket (a, b], b the `ended_at` of the first observation that held D for S, and a that of the last observation before it that was evidence D was not yet held (step 4). For an ordinary new day, a is the `ended_at` of the tick before the one that first held it. An inherited day has no lower end.
6. **As of t.** The view reads step 4's versions, never raw observations: for each (S, D), the newest version whose first observation's knowable time (step 2) is at or before t. An absence counts only where step 4 reads a retraction, so an outcome-2 body's gaps that are no evidence leave the view unchanged. Each value is returned with its version's first-seen `ended_at`, the `ended_at` of the newest observation knowable by t that carried the same token, and any step-9 flag on either, so staleness and clock doubt show. The as-of path never does label arithmetic.
7. **Restatement diffs.** A diff between two ok observations of one source is the set of (S, D) that step 4 reads as a restatement, a retraction or a backfill. D10's gauge is its two-body reading between consecutive ok bodies: the same three kinds, plus a value restored unchanged after a retraction, which two bodies cannot tell from a backfill without the last non-null token.
8. **Inherited history.** Inherited is set per series: every (S, D) present in the first observation that carries S is the vendor's history as revised up to that observation. For a series carried from the source's first tick, that is the first tick. For one first carried later, withheld at genesis or granted later, it is that later observation, so its history is never read as first published. Inherited history is never point-in-time, and a backtest's years before the first tick stay revised.
9. **Clock evidence.** The reader flags, never drops silently, an observation whose tick reports the clock unsynchronised, an offset beyond 10 s (the ops clock rule's bar), a `clock-offset.prom` older than 600 s (two periods of its 5-minute writer; at a boot tick taken before chrony has synchronised, it is the previous boot's file and still reads synchronised) or `ended_at` more than 300 s from the server's Date, and every observation of a tick whose stamp is at or below its predecessor's (D5) and of that predecessor, which may have been taken under a clock running ahead.
10. **Label conventions.** These matter only for inherited history, and the catalog states them:
    - Fear & Greed's label D appears at about D 00:00Z.
    - A Coin Metrics label D summarises [D, D+1), and its row first appears after D+1 00:00Z (the 2026-11-10 btc row carried only `PriceUSD` at 00:27:13Z on 11-11).
    - mempool's label is read from its code as the window [D−1, D). That is not measured, and the record's first-appearance times measure it.
11. **Rolling windows.** The status feed (25 entries) and the `ReferenceRate*` metrics (7 points) are unioned across ticks. A restatement and a recalculation notice from the same window can be paired by reading that tick's `cm-status` body.
12. **Pinning.** A consumer pins the sha256 of the newest `tick.json` it read. Through `prev`, that hash commits to every earlier tick, and through each `tick.json` to every body. How a trial records that pin in the registry is the first C3 trial spec's decision.

## Failure modes

- **A source answers a transport error, timeout, 5xx or 429.** Up to 3 attempts honour Retry-After; a retried attempt keeps its first 4 KiB, and the final answer's body is stored whole. Outcome 1, WARNING, and the other sources continue. The tick is published, the CLI exits 1, and a page comes only after 25 h with no ok fetch.
- **A whole source host is down.** The per-host breaker marks that host's remaining requests not fetched, so the tick ends in seconds rather than minutes.
- **A 403, a 404 or another non-429 4xx.** Not retried. The whole body is stored as its file, outcome 1, and the rule pages if it persists. It is a contract change: the owner drops or repoints the source, and a repoint is a new source id.
- **A Coin Metrics metric is revoked or unsupported.** The 200 still carries the rest of the asset's metrics. The presence check grades the body outcome 2 and names the absent metric. Every byte served is stored, and the rule pages at 25 h until code acknowledges the change with D8's pinned entry.
- **Format drift.** For example an HTML page after a redirect, a renamed field, an empty body or a non-identity encoding. The body is stored as served, outcome 2, with the reason and the final URL. No byte is lost while the code catches up.
- **A frozen metric** (its newest day past its D8 bound), **a body that lost days** (a metric's newest day earlier, or its oldest day later, than in the last ok body, as when a `json_stream` ends cleanly mid-history) **or a collapsed history** (rows under 90% of the last ok body). Outcome 2, the failing metrics named in `metrics_failed`. The page stands until code acknowledges it with D8's pinned entry, because the comparison is with the last ok body. The derivation takes that body's absences as no evidence for the metrics it names, and for every series after a collapse.
- **The catalog starts paginating.** A `next_page_url` in the body grades it outcome 2, so page one is never read as the whole catalog.
- **A response over 64 MiB.** Not stored. Outcome 1, `oversize <bytes>`.
- **A trickling server or the 20-minute deadline.** The per-request body deadline cuts the trickle. Sources not yet reached become outcome 1, `tick deadline`, and the tick is published.
- **The lock is held** (a second writer under another container name; a raced unit start or same-name `docker run` never reaches the CLI), **the target exists**, **staging or the record is unwritable**, **the read-back mismatches, or an exception is raised before the rename.** Exit 2, ERROR, nothing published, no dead-man ping. A held lock logs the recorder's own message, never the capture one. After a read-back mismatch, staging is left for inspection.
- **The stamp regresses** (a clock that stepped back, or one corrected after a tick published under a clock running ahead). The tick is published with an ERROR naming both stamps, `prev` names the chain's head, and recording never stops. The reader flags the tick and its predecessor, and the ops clock rule pages the cause.
- **A boot tick before chrony has synchronised.** `chrony-wait.service` is disabled on this host, so a `Persistent=true` boot tick can run on an unsynchronised clock while `clock-offset.prom` still holds the previous boot's reading. Its age, over 600 s, is in the tick, and the reader flags it (step 9).
- **A disk is full.** The write fails in staging, exit 2 and ERROR. `zcrypto-ops-disk-low` has already paged at 15% free.
- **A crash mid-tick** (OOM, kill or reboot). The partial staging directory is never published. The next tick runs normally and names the leftover in a WARNING, and the kernel releases the flock.
- **A leftover container after a dockerd crash, or the pinned image missing.** The runner fails before the CLI starts, `last_ok` stops advancing, and the rule pages. The runbook covers `docker ps -a --filter name=zcrypto-vintage-record`, removing the leftover and re-pulling the digest.
- **The timer is disabled, or the host is down through both ticks.** The rule pages, and so does noData if the textfile goes. The dead-man goes down at about 31 h, whatever Grafana's state. `Persistent=true` runs one tick at boot, and a tick never records the past.
- **Alloy, remote write or the observability node is dark.** NoData pages where Grafana lives. If Grafana itself is dark, the grafana-watchdog pair and this check's dead-man page.
- **A malformed or unreadable `.prom`.** `zcrypto-capture-textfile-unreadable` (`Node · node-exporter textfile unreadable or malformed (capture, ops)`) pages. The CLI chmods to 0644 before the rename, and a test holds that.
- **A corrupt `tick.json` met in the scan** (bit rot or a hand edit). It counts as no ok fetch, ERROR names the file, and the tick is never rewritten. The hash-checked restore (D15) puts the published bytes back from the other copy, checked against the witness.
- **The newest `tick.json` damaged or edited before the next tick.** The chaining check (D5) catches a head that no longer parses, lists other files than its directory holds, or names a body that no longer re-hashes: `prev` carries the error, ERROR pages, and the head is restored against its witness. An edit that keeps the head consistent is chained as found; the NAS copy pulled before it then disagrees with the successor's `prev`, the NAS verify logs ERROR, and the owner decides against the witness (D15).
- **A head deleted on ops before the next tick.** The next tick chains around it, so the ops copy verifies clean; the NAS copy that pulled it holds a fork, which its verify reports, and the INFO line in the journal names the lost tick.
- **A pull killed mid-file** (a NAS recreate during the rsync). It can leave rsync's temporary `.<name>.XXXXXX` file in a NAS tick directory; verify reports it as a file the `tick.json` does not list, and the runbook removes it by hand.
- **A body or `tick.json` damaged on one copy.** On ops, the tick's re-verify finds it within a week and logs ERROR, and the tick exits 1. On the NAS, the loop's verify finds it within 24 loops, or at once if it arrived damaged among the newest four ticks, and logs `vintages verify failed` at ERROR. Either pages, and stays paging until the hash-checked restore from the other copy (D15).
- **The host clock jumps.** Every observation carries the chrony offset, the sync flag, the offset file's age and the server's Date, and the chain keeps the true order. The reader flags the observations, and the ops clock rule pages.
- **The NAS is down, or a pull fails.** The NAS block logs ERROR, which pages through `zcrypto-nas-archive-pull-errors`. Ops keeps accruing, the window of sole custody grows, and the next pull copies every missed tick.
- **The NAS channel is unwired.** ERROR every loop, which pages.
- **The NAS image lacks the verifier** (archive-pull pinned to a build from before this change). The block's verify fails every loop and logs ERROR, which pages; the deployment order moves `nas_capture_image` in the same NAS converge that deploys the block, so this is a wrong pin.
- **Path drift between the `rrsync` root and `record/`.** A converge-guard test fails in CI.
- **One of the two daily ticks fails systematically** (for example a vendor's maintenance at 19:37). Each day is still recorded, so nothing pages. This is the known residual, visible on the outcome panel and as a lower second-tick rate in the record.
- **A vendor restates history.** Not a failure: it is the dataset's purpose. The bytes are stored as served, and `changed_values` measures it the next tick.
- **The per-IP budgets are shared with the workstation.** A research burst near a tick can meet a 429, which Retry-After and the backoff handle.

## Observability

- **The textfile.** `/var/lib/zcrypto-ops/textfile/vintage.prom` holds D10's five families, written by the CLI alone. The ops Alloy's textfile collector already reads the directory, so it needs no Alloy change for metrics.
- **The rule.** `zcrypto-ops-vintage-not-recorded` (D11), in `infra/grafana/alerts.yaml`'s `zcrypto-ops` group.
- **The dashboard.** A "Free-source vintages" row on `infra/grafana/data-integrity-dashboard.json`, with these panels:
  - last-ok age per source, with the rule's bar at 90000;
  - outcome per source;
  - body bytes per source;
  - days missing per source;
  - changed values per source.
- **The logs.** The unit's journal ships through the keep-regex (D17). ERROR lines page through `zcrypto-ops-error-logs`. The NAS block's three ERROR lines, `vintages pull failed`, `vintages verify failed` and `vintages channel unwired`, page through `zcrypto-nas-archive-pull-errors`.
- **The dead-man.** `zcrypto-vintage-record` (D12).
- **The runbook.** A new section in `infra/runbooks/ops-node.md`, edited through the `zcrypto-refine-rules` skill. It opens with `<a name="zcrypto-ops-vintage-not-recorded"></a>` above `## zcrypto-ops-vintage-not-recorded — ALERT`, and keeps the four parts in order:
  - **What you are seeing:** one source, named by its label, has had no good fetch in 25 hours.
  - **What it means:** the source's day is at risk until UTC midnight; the next good tick carries the whole history again, so what a miss costs is that day's snapshot and the first-seen precision of anything new in it.
  - **What to do:** read `systemctl status zcrypto-vintage-record.service` and the unit's journal since the last good tick, then find the newest tick directory under `/var/lib/zcrypto-ops/vintages/record/`. Each finding has its own next step:
    - no tick today: the recorder did not run, so check the timer, a leftover container or the pinned image;
    - a tick with outcome 1 for the source: read its attempts, and treat a 403 or 404 as a contract change for the owner;
    - outcome 2: the bytes are stored and the check needs code, D8's pinned acknowledgment, which is the owner's call;
    - in every case, `sudo systemctl start zcrypto-vintage-record.service` before 00:00 UTC records the day.
    - Never place a fabricated body under `record/`.
  - **Retire when:** the recorder is retired. That is checkable: `systemctl list-timers` no longer lists `zcrypto-vintage-record.timer` and the rule is pruned.
  - Every universal word the section uses carries its `(set: …; count: …)` or `(no count command: …)`. Its reads use shapes the ops-daily autonomy classifier admits.
  - A second part, the hash-checked restore (D15), which the `verify` findings on either copy point to: how to read the expected sha256, for a body from a verified `tick.json`, and for a `tick.json` from its witness, the INFO line's `tick_json_sha256` in the ops journal or Loki, with the successor's `prev` as corroboration; that where the copies or `prev` disagree with the witness, the owner decides against the witness, never by copying whichever bytes match `prev`, and that such a link then needs D15's pinned acknowledgment; how to hash the other copy's file before placing it; on ops, making the tick directory writable for the copy and setting it back to 0555; on the NAS, replacing the damaged file on the host itself, never through the ops mount; removing an rsync temporary `.<name>.XXXXXX` file that `verify` names as unlisted; and a whole `verify` of that copy after.
- **The surrounding docs, updated in the same change.**
  - `infra/runbooks/observability.md`, through `zcrypto-refine-rules`, since it is a top-level runbook page: its textfile row (:93) gains this rule and the `zcrypto_vintage_*` prefix and counts 21 rules; the awk command that defines that set (:99) gains `vintage` in its `zcrypto_(…)` alternation, so the command prints 21 too; its keep-regex sentence gains `vintage-record`; and its dead-man table gains its row.
  - `infra/runbooks/nas.md`, through `zcrypto-refine-rules`: its table of the pull loop's ERROR lines (:133) gains `vintages pull failed` and `vintages verify failed`, each `(…), continuing`; its note on the raw-rsync channels and the unwired reconciled WARNING (:138) gains the contrast that `vintages channel unwired` is an ERROR; and the page names `zcrypto vintage verify --root /mnt/zhao-crypto/vintages` as the arrival read and the restore part above as the remedy.
  - `infra/ops/README.md`: its `container` label list gains `zcrypto-vintage-record`, and its "four NAS pull channels" become five.
  - `infra/scripts/ops-postverify.sh`: it gains one check, the recorder's liveness, `time() - max(zcrypto_vintage_last_ok_timestamp_seconds)` under 90000, one series, and nothing else, with `tests/test_ops_postverify.py` beside it. It verifies every later ops converge, and its `check` helper fails on any one series out of bounds (`ops-postverify.sh:10-29`), while one source's outage or a check failure awaiting its acknowledgment says nothing about a converge, the converge that ships the acknowledgment included. So the per-source age stays D11's, and `zcrypto_vintage_outcome` is read by value once, at the attended first tick (the deployment), never in postverify.

## The archive path to the NAS

D14 is the decision. In brief: ops never pushes, and the NAS pulls `record/` hourly over its own `rrsync -ro` key with `--ignore-existing` and never `--delete`, so the first bytes to arrive are kept for ever and a file is never re-sent. The block, in the hot block's shape:

```
if [ -n "${VINTAGES_SOURCE:-}" ]; then
	if ! rsync --archive --ignore-existing --chmod=D0775,F0664 \
			-e "ssh -i $VINTAGES_SSH_KEY -p ${VINTAGES_SSH_PORT:-22} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o CheckHostIP=no -o AddressFamily=inet -o UserKnownHostsFile=$ARCHIVE_SSH_KNOWN_HOSTS" \
			"$VINTAGES_SOURCE" "$VINTAGES_DEST"; then
		log ERROR "vintages pull failed (source=$VINTAGES_SOURCE dest=$VINTAGES_DEST), continuing"
	fi
	if ! zcrypto vintage verify --root "$VINTAGES_DEST" --newest 4 --slice "$slice" --slices 24; then
		log ERROR "vintages verify failed (dest=$VINTAGES_DEST), continuing"
	fi
else
	log ERROR "vintages channel unwired (VINTAGES_SOURCE unset): custody is not acquiring the recorder's ticks"
fi
```

A tick directory appears on ops by one rename, so the pull sees whole ticks. A transfer interrupted mid-file leaves no file under its final name (rsync writes a temporary file and renames it), and the next loop completes the copy; a killed one can leave the temporary `.<name>.XXXXXX` file behind, which `verify` reports as unlisted and the runbook removes by hand. The verify runs after a failed pull too, since what is already on the NAS still needs its slice re-hashed. `zcrypto vintage verify` on `/mnt/zhao-crypto/vintages`, whole, proves the copy at rollout.

## The catalog entry

`docs/reference/data-catalog-full.md` gains, under `## custody` and in that section's entry shape:
- **Heading:** ``### Free-source vintages (`vintages/`, since <first tick's date>; two ticks a day)``.
- **Producer:** `zcrypto vintage record` on the ops node at 07:37 and 19:37 UTC. It lists the fetch table's five source kinds and their exact URLs, records each source's whole response as served, and stores the fetch time as the stamp, with the server's Date as the floor of a value's knowable time.
- **Layout:** the tree above, with the `tick.json` fields and their meaning.
- **Sources and licences:**
  - Coin Metrics Community: CC BY-NC 4.0, whose NonCommercial test turns on purpose. Never an engine input without written permission from Coin Metrics. The entry quotes the owner's answer to open question 4, which decides whether a C3 trial may rely on the record before that permission.
  - alternative.me: use "in any way you like", with attribution next to any display.
  - mempool.space: no licence grant and no stated limits; private copies only, never committed or published.
- **Label conventions:** the three, as the reader section states them.
- **Hard caveat:**
  - Everything present in the first tick that carries a series is inherited, revised history.
  - A UTC day on which a source has only outcome-1 fetches, or no tick at all, is a permanent hole in that day's snapshots, paged at 25 h and backed by the `zcrypto-vintage-record` dead-man. A day whose only bodies graded outcome 2 is no hole: its bytes are stored and flagged by the check's reason, and `days_missing` still counts it because none was good.
  - `AssetEODCompletionTime` is a last-calculated time, never a publication time.
- **Attestation:** the raw sha256 of every body in its `tick.json`, the `prev` chain, each `tick.json`'s witness in the ops journal and Loki, `zcrypto vintage verify` run on the ops copy every tick and on the NAS copy every loop, each copy re-hashed whole within a week and within 24 loops, and the hash-checked restore as the only repair.
- **Consumers:** C3 (T0016). The consumption convention pins the newest `tick.json`'s sha256. The derived dataset and its registry arm are the first C3 trial spec's.

## Tests and guards

The plan reviews at tier `full`. Each guard below is proven with `infra/scripts/mutate-probe.sh` through its own `-k` case, against a fixture that sits nearer one side of the case it separates.

| Decision | Guard | Where |
|---|---|---|
| D1, D2, D13, D17 | rendered runner argv: `--pull never`, the stable `--name`, `--user`, exactly the two mounts, no `-e`, no NAS mount, image by digest; the unit's Type=oneshot with no `RequiresMountsFor`, and its `Wants=network-online.target` and `After=docker.service network-online.target`; the timer's two `OnCalendar` lines and `Persistent=true`; the timer's `[Install]` `WantedBy=timers.target`, its own `-k` case; the block gated on the digest; the enable's check-mode guard | new `tests/test_infra_vintage_record_template.py`, the tape-bars precedent |
| D1 | the runner template renders to valid bash | `REGISTERED` in `tests/test_infra_shell_templates_render.py` |
| D3 | the table pinned verbatim; every `cm-<asset>` URL carries both flags and exactly its asset's list from the fixture's catalog; no URL names a Kraken host | new `tests/test_vintage_sources.py` |
| D4 | a read-back mismatch refuses the tick; the same body twice gives the same file bytes; identity is requested; a non-2xx body is stored as its file; a retried attempt keeps its first 4 KiB; every file is created exclusive and 0444 | new `tests/test_vintage_record.py` |
| D5 | a crash before the rename leaves `record/` untouched; an existing target refuses; a stamp at or below its predecessor's is published with an ERROR and `prev` naming the chain's head; `prev` names the head and its sha256; a head edited before the next tick so that its `tick.json` no longer parses, lists other files than its directory holds, or names a body that no longer re-hashes is caught at chaining, with `prev.error` and an ERROR; an empty record writes `genesis_reason`; the published tick directory is 0555 | `tests/test_vintage_record.py` |
| D6 | the clock block is read from a fixture `.prom`; an absent file records nulls and never refuses | `tests/test_vintage_record.py` |
| D7 | Retry-After honoured and capped; a 403 never retried; the breaker; the per-request body deadline; the tick deadline; the size cap | new `tests/test_vintage_fetch.py` |
| D8 | each source's check grades a stored body 2; an absent pinned metric grades 2; a metric past its freshness bound grades 2, and the named exemption does not; an `avaxc` or `avaxp` metric past date − 30 grades 2, and one at date − 10 does not; a metric whose newest day went back, or whose oldest day moved forward, against the last ok body grades 2, and a `ReferenceRate*` oldest day does not; a collapse against the last ok body grades 2; a catalog with a `next_page_url` grades 2; a pinned acknowledgment stops its rule from its tick on, a comparison restarts there, and `tick.json` names the entry | `tests/test_vintage_sources.py` |
| D9 | one failing source never stops the others; exit codes 0, 1 and 2; an exception raised before the rename exits 2; a held lock exits 2 with the recorder's own message, never the capture one; WARNING for a failed source and ERROR for a refusal; the INFO line's `tick_json_sha256` equals the sha256 of the published `tick.json` | `tests/test_vintage_record.py` |
| D10 | the `.prom` is 0644; `last_ok` read along the chain, so a future-stamped tick does not hold it; `days_missing` read off the record; `changed_values` counts a restatement, a retraction and a backfill, a value withheld in an outcome-2 body and restored changed as one restatement, a value retracted in one ok body and restored unchanged in the next as one, and never a first publication | `tests/test_vintage_record.py`, new `tests/test_vintage_derive.py` |
| D11 | uid, fields, runbook anchor, the panel's bar equal to the evaluator | existing `tests/test_infra_alert_rules.py` and `tests/test_dashboards_cover_metrics.py`, which apply as they stand |
| D12 | the dead-man slug, fixture and URL; the runner install `no_log`, `diff: false`, 0700; the ping on exit 0 or 1 and on no other code; the fixture row, the host_vars URL, `OPS_CHECKS` with its `== 13`, every other count of the checks and the count-named names in one commit, after the runbook anchor its `Runbook:` link names | `OPS_CHECKS` and `PING_RENDERS` in `tests/test_infra_hc_role.py`; the template test; `tests/test_ops_daily.py` and `tests/test_hc_provision.py` |
| D13, D14 | the `authorized_key` root equals `record/`; staging is a sibling of `record/`, never under it; the NAS block's argv (`--ignore-existing`, no `--delete`, `--chmod=D0775,F0664`, the pinned ssh options), its verify call with `--slice "$slice" --slices 24` after the rsync, and its ERROR on an unset source, a failed pull and a verify finding | `tests/test_infra_converge_guards.py`, the hot and hc-backup blocks' style |
| D14 | the vaulted private sibling of `sync_vintages_ed25519.pub` exists | existing `tests/test_infra_pull_channel_keys.py`, which applies as it stands |
| D15 | a tampered body, a missing body, a missing tick, a broken link, a fork and a file its `tick.json` does not list each exit 1, naming the paths; a stamp regression is named and exits 0; a link whose successor's `prev` carries an error, and an acknowledged link whose restored `tick.json` matches its pinned witnessed hash, are named and exit 0, and the acknowledged one exits 1 when the bytes differ; an empty record exits 0; `--newest` re-hashes the newest ticks along the chain, a tick published after a regression among them, and `--slice` exactly its ticks; the record step's re-verify logs ERROR and exits 1 on a damaged body | new `tests/test_vintage_verify.py` |
| D16 | as-of reads the versions and never returns a version whose first observation is knowable after t, the knowable time being max(`ended_at`, server Date + 1 s); an outcome-2 body that lost history leaves as-of unchanged; a value, its retraction, then the same value again reads as that value as of any time after the third observation, Q2 listing the retraction and the restoration; inherited is set per series, at the first observation that carries it, including a series absent at genesis; a first publication, a backfill, a restatement, a restoration and a retraction are told apart; a gap filled after a truncated outcome-2 body is a backfill; a value gone and restored changed is a restatement; an outcome-2 body's absences are no evidence for the series its check names and are evidence for the others; a day first held at the second tick has Q3 = (first tick's `ended_at`, second tick's `ended_at`]; a change of time format keeps every key; a token beyond 2^53 survives | `tests/test_vintage_derive.py` |
| D17 | the unit is named in the keep-regex | existing `tests/test_infra_alloy_series.py`, which applies as it stands |
| D18 | the allowlist: a rename only inside the two helpers' bodies; every `os.open` exclusive-create or read-only, with flags the syntax tree spells; `mkstemp` only in the `.prom` helper; every other opening call read-mode, except a `GzipFile` over a `fileobj`; no `shutil` copy or move, truncate, unlink, rmdir, rmtree, `write_bytes` or `write_text` under `cli/vintage/`; each rule probed | `tests/test_vintage_record.py` |
| D19 | every fixture body has a provenance file with the real body's URL, fetch time, sha256 and size, whether the bytes are real or synthesised and how, and the licence; every Coin Metrics and mempool.space fixture's provenance says synthesised, and regenerating it from its committed shape file and seed reproduces its bytes exactly, unless the owner's answer to open question 4 admits real bytes; every body synthesised from a shape file holds at most 120 rows and every fixture file is under 500 KB | `tests/test_vintage_sources.py` |
| all | every new operator string free of internal tokens | existing `tests/test_internal_terms_not_operator_visible.py` |

## Deployment and its order

**marco's call.** The owner's hand, from merged `develop`, outside published Kraken maintenance windows. The feed is read whole at planning time and again immediately before each converge, and `converge.sh` is never wrapped in `timeout`. Each step names the skill that `.claude/rules/fleet-deploys.md` binds it to.
1. Before the plan's channel task: the owner generates the `sync_vintages` pair and commits both halves to the branch in one commit, the `.pub` and the ansible-vault-encrypted private half (D14). Without the private sibling `tests/test_infra_pull_channel_keys.py` fails the branch, and without the `.pub` every later ops converge fails its lookup.
2. After merge: the capture image builds, default and `-compat`, from the `develop` push. Pre-pull the default digest on `zcrypto-ops` (`zcrypto-rollout-image`, "Ops converges"). On the NAS, pull the `-compat` digest and prove its runtime by running polars in it.
3. Only if `docs/reference/fleet-pins.md` does not already record the running ops digest, which the pins assert requires before an ops re-pin: a pull request recording it, through `open-pr` and `merge-pr` (`zcrypto-rollout-image`, "Ops converges"). `nas_capture_image` is not in it: CI holds that pin and the archive-pull row equal at every commit (`tests/test_fleet_contracts.py::test_the_nas_rows_agree_with_the_committed_pins`), and a row records only a digest a converge was handed (`tests/test_pins_converged.py::test_the_real_pair_reads_zero`), so the pin is committed after the NAS converge (step 8).
4. The ops `--tags alloy` converge with `ops_alloy_digest`, carrying the keep-regex: `zcrypto-bump-alloy`'s Step 2, for ops alone. It goes first, because a later ops converge without that digest refuses on drift.
5. Provision the dead-man check with `infra/scripts/hc-provision.py`.
6. The ops converge (`zcrypto-rollout-image`, "Ops converges"), with the new `ops_image_digest` and `-e liquidations_decision=roll-after`, started just after a timer slot (07:37 or 19:37 UTC), so the timer's first slot is about 12 hours away. It creates the directories and the key, renders the runner, unit and timer, and enables the timer; `systemctl list-timers zcrypto-vintage-record.timer` then reads its next slot and no run.
7. Roll the liquidations poller, attended and inside its 30 h window, as `infra/ops/README.md`'s start step reads it (`docker compose -f /etc/zcrypto-ops/compose.yaml up -d`), and read the running container's `.Config.Image` by value against the new digest. The converge repinned its compose file and never restarts it.
8. Place the private key on the NAS (0600, 1000:1000). Move `nas_capture_image` in `infra/ansible/host_vars/nas/vars.yml` to the `-compat` digest in the working tree, so the NAS loop's `zcrypto` carries `vintage verify`, and run the NAS converge with it uncommitted, `--limit nas --tags nas -e nas_apply_compose=true` (`zcrypto-rollout-image`, "NAS converges"), as commit `83e3de4ab` did for the last NAS re-pin. It recreates archive-pull on the new pin, which replays the gate export cold ahead of the vintages block, so its window is sized from the live figures as `docs/reference/fleet-pins.md`'s Standing constraints read them, and the pages a recreate brings are announced. Then commit the pin, its archive-pull row in `fleet-pins.md` and the converge's line in `docs/reference/deploy-log.jsonl` together, in one commit. Wait until the loop has passed the vintages block with no `vintages` ERROR on the empty `record/`.
9. The attended first tick: `sudo systemctl start zcrypto-vintage-record.service`. Read the journal and `vintage.prom` by value, every source's `zcrypto_vintage_outcome` among them, and run `zcrypto vintage verify --root /var/lib/zcrypto-ops/vintages/record`.
10. After the next NAS loop, run `zcrypto vintage verify --root /mnt/zhao-crypto/vintages` from the workstation.
11. Push the rule and the dashboard from `develop` with `zcrypto-grafana-push`, once the series exists, and verify the first sample by value.
12. Run `infra/scripts/ops-postverify.sh` (`zcrypto-rollout-image`, "Ops converges"), re-true the ops row in `fleet-pins.md` from the ops converge's deploy-log line and commit the row with that line; that commit and step 8's go in one pins pull request, through `open-pr` and `merge-pr`.

Readers before writers: the NAS verify is the record format's only reader in this change, and it lands at step 8, before the writer's first tick at step 9; the NAS pull itself is format-blind. No sole custody (spec 00051 D10): the first tick waits for a clean NAS loop, so, when step 8 finishes before the timer's first slot, the ops copy is never the only copy for longer than one pull interval. If step 8 slips past the timer's first slot, that tick is published on ops and sits there alone until the first clean loop copies it, and nothing is held back to avoid that.
The price is the hours of steps 4 to 8 before the first tick, plus step 3's pull request only when the running ops digest is not yet recorded; the pins pull request follows the first tick and holds nothing back. Every day of delay is a day the record never holds, so the rollout takes its own window as soon as the change merges (open question 9).

## What changes in the repo

- **New:** the `cli/vintage/` package; `tests/test_vintage_sources.py`, `tests/test_vintage_fetch.py`, `tests/test_vintage_record.py`, `tests/test_vintage_derive.py`, `tests/test_vintage_verify.py` and `tests/test_infra_vintage_record_template.py`; `tests/fixtures/vintage/` with its provenance and shape files, and the deterministic fixture generator under `tests/` (D19); `infra/ansible/roles/ops/templates/vintage-record.sh.j2`, `vintage-record.service.j2` and `vintage-record.timer.j2`; `infra/ansible/files/sync_vintages_ed25519.pub` and its ansible-vault-encrypted sibling `infra/ansible/files/sync_vintages_ed25519`, both in the owner's one commit (deployment step 1).
- **Changed, code and configuration:** `cli/__main__.py`; `infra/ansible/roles/ops/tasks/main.yml` and `infra/ansible/roles/ops/defaults/main.yml`; `infra/ansible/roles/ops/files/config.alloy`; `infra/ansible/host_vars/zcrypto-ops/vars.yml`, its "four NAS pull-channel public keys" comment becoming five; `infra/ansible/host_vars/nas/vars.yml`; `infra/ansible/roles/nas/templates/env.j2`; `infra/nas/compose.yaml`; `infra/nas/pull-entrypoint.sh`; `infra/grafana/alerts.yaml`; `infra/grafana/data-integrity-dashboard.json`; `infra/scripts/ops-postverify.sh`; the `apply` help string and the count-named names of `infra/scripts/hc-provision.py`.
- **Changed, tests:** `tests/test_infra_shell_templates_render.py`, `tests/test_infra_hc_role.py`, `tests/fixtures/healthchecks_descriptions.json`, `tests/test_ops_daily.py` and `tests/test_hc_provision.py` (the count's part of the last four in D12's one commit, with the host_vars URL and `hc-provision.py`, after the `ops-node.md` section), `tests/test_infra_converge_guards.py`, `tests/test_ops_postverify.py`.
- **Changed, docs:** `infra/runbooks/ops-node.md`, `infra/runbooks/observability.md`, `infra/runbooks/nas.md`, `infra/runbooks/hc.md` and `infra/runbooks/drills-telemetry.md`, each through `zcrypto-refine-rules`; `infra/ops/README.md`, `infra/nas/README.md`, `infra/ansible/files/README.md` (the key inventory's `sync_vintages_ed25519.pub` row, "NAS + vaulted here", ops vintages pull channel), `README.md`, `docs/reference/data-catalog-full.md`, `docs/reference/fleet.md`, the routed decisions log, and `docs/reference/change-index.md` through `open-pr`.
- **Changed in the rollout, after merge:** `nas_capture_image` in `infra/ansible/host_vars/nas/vars.yml`, its archive-pull row in `docs/reference/fleet-pins.md` and the NAS converge's line in `docs/reference/deploy-log.jsonl`, in one commit after that converge (deployment step 8), and the ops row with the ops converge's line (step 12), the two commits in one pins pull request after the first tick; before the ops converge, only if `fleet-pins.md` lacks the running ops digest, a pull request recording it (step 3).
- **Untouched, deliberately:** `pyproject.toml`, `uv.lock`, `zcrypto.toml`, `cli/capture/` (imported, never edited), `cli/data/`, `.claude/` unless the owner admits one line (open question 11), and `tests/test_infra_alloy_series.py`, since the keep-regex names the unit and no `_JOURNAL_NOT_SHIPPED` row is owed.

## Invariants

- No file under `record/` is ever written after the rename that publishes its tick, and nothing transient is ever named under `record/`. A published tick directory is 0555 and its files 0444, and the only bytes ever placed into one afterwards are a hash-checked restore's, equal to what its manifest hashes for a body or to its witness for a `tick.json`.
- A tick's `tick.json` lists every body file in its directory and hashes each one.
- Every tick but the first names its predecessor, the chain's head when it was published. Publication order is the chain's; no two published ticks share a stamp, and a stamp at or below its predecessor's exists only with the ERROR that named it.
- No tick carries a stamp other than its own start second, and no body bytes other than those the source sent.
- Nothing under `record/` or `staging/` is deleted, replaced or rewritten by code under `cli/vintage/`, whose only renames are inside the tick publish and the `.prom` publish helpers and whose every write opens a path it creates exclusively (D18), and no request carries a key.
- `zcrypto vintage record` exits 0 or 1 only when it published a tick, and the dead-man is pinged on nothing else.
- Each copy is re-verified on a schedule: every ops body within a week, every NAS body within 24 loops.

## What stays manual

- Fetching the real bodies and writing from them the shape files and the provenance before the plan's Task 1, by the session writing the plan, since the implementer makes no network call; the generator that turns a shape file and a seed into a fixture is code the plan builds and tests.
- Generating the `sync_vintages` key, committing both halves, the private one vaulted, and placing the private half on the NAS; provisioning the dead-man check.
- The pins pull request, every converge in the deployment order, the poller's roll, the attended first tick, both whole `verify` reads and the Grafana push.
- Retiring or repointing a source: a code change and the owner's decision.
- Acknowledging a check failure (D8) or a link broken by a restored `tick.json` (D15): a pinned entry in code and the owner's decision.
- Deleting a crashed tick's staging leftover, after reading it.
- A hash-checked restore from the other copy, after a `verify` finding (D15).

## What is left to the implementer

- The module split under `cli/vintage/` (a suggested shape is `command.py`, `sources.py`, `fetch.py`, `record.py`, `derive.py`, `verify.py`), the test file names above or better, and the panel layout and ids.
- The exact `# HELP` wording, log line wording and `--help` text, all free of internal tokens.
- The per-asset metric lists, copied verbatim from the recorded catalog bytes. If they differ from this spec's table, the bytes win and the plan says so.
- D8's named exemptions (`dot`'s stopped metrics, the `ReferenceRate*` rolling metrics), its date − 30 bound on `avaxc` and `avaxp` and its date − 1 source bound, checked against the recorded bodies' days and fetch times; where the bytes say otherwise, they win and the plan says so.
- The `verify` option names, if better than `--newest`, `--slice` and `--slices`, kept the same in the ops record step and the NAS block.
- The runbook section's prose and its counted universals, through `zcrypto-refine-rules`; the `infra/ops/README.md` and `infra/nas/README.md` channel sections; the `README.md` `vintage` section; the `docs/reference/fleet.md` ops-timers cell (164 characters plus `vintage-record`, under the 200 cap) and its storage list.
- The plan ends with its decisions-log task, an `[00158]` entry with two or three options and `(Decision: N)` in the log open question 10 names.

## How this design was chosen

Three designs were weighed against the brief and four maps of the tree, the ops pattern, the archive path, the conventions and the sources.
- **The base: the fleet operator's design.** It was the strongest whole. It brings the timer pattern, the tick directory published by one rename, store-first-judge-second, the bounds and breaker, the 25 h rule timed to save a day, the dead-man, the custody channel with `--ignore-existing`, and gauges read off the record.
- **Grafted from the minimal archiver.**
  - The exchange kept whole: headers as ordered pairs, request headers, every attempt.
  - The fetch time as the stamp, with the server's Date as evidence and as the floor of a value's knowable time.
  - The bounded claims below.
  - The point that a runner `.prom` adds nothing the record does not already say.
- **Grafted from the point-in-time design.**
  - The three questions and the as-of view as the record's acceptance test, with the derivation shipped as code and tests.
  - Token-preserving parsing, the inherited flag and host clock evidence in every tick.
  - The chain, which also gives a one-hash pin.
  - Tick slots set 23 minutes before an engine cycle.
- **Rejected wholes.**
  - The minimal archiver's `hot-out` route (the hot charter and `data fetch` to every node), its content-addressed blobs, its unshipped journal and its lack of a dead-man.
  - The point-in-time design's six ticks with two cadence classes, its parquet records through `zcrypto archive pull` (no `--ignore-existing`), its published versions dataset and its count of failed ticks today.
- **Changed against all three.** `ignore_forbidden_errors` turned on, with a presence check, after the 01:08Z measurement showed silence is the API's default for an unsupported pair anyway. And breadth: every free daily metric.
- **Where it departs from marco's earlier calls.**
  - The runtime is the timers', not the poller's.
  - Unchanged bodies by hash reference are dropped.
  - No header dates a body, so the fetch time does.
  - "Once a day" becomes two ticks.
  - The dead-man is kept, because the daily peers carry one.
  - There is no live test at all.

## What the record does not hold

- Intermediate redirect hops: only the final URL is kept.
- The peer address and the TLS details.
- Anything between ticks: first-seen precision is the tick interval, 12 hours.
- A retried attempt's body beyond its first 4 KiB, and any body over 64 MiB or cut by its deadline.
- Any source not in the table, and any metric not in an asset's pinned list, though the recorded catalog shows what was available.
- Proof that a Coin Metrics `json_stream` body was served from one consistent snapshot. A recalculation mid-stream would read as a later restatement.

## Out of scope

- Explicit drops:
  - The derived versions dataset and its registry and `ObservedReader` arm (D16), and a daily-pass arrival row (D15).
  - An exit-code rule and a `days_missing` rule (D11).
  - A live-network test (D19).
  - BGeometrics and Blockchain.com.
  - `sol` and `avax` price series.
- The BTC chain computation, its own topic T0228.
- Any engine input and any trading use of the Coin Metrics data, which waits on a written licence.

## Open questions for the owner

| # | Question | Recommendation | The owner's answer |
|---|---|---|---|
| 1 | Cadence: two ticks at 07:37 and 19:37 UTC, once a day as you first said, or six ticks 23 minutes before every engine cycle with a light probe (D2)? | Two. A single failure never costs a day, late completions and same-day revisions get measured, and the 25 h rule pages while the day can be saved. Six whole ticks is a few timer lines and about three times the requests and bytes; six with the light probe is the machinery D2 rejected, about a day of code. Either waits until a question needs first-seen at cycle resolution. | |
| 2 | Coin Metrics breadth: every free daily metric per asset (about 7 GB a year gzipped per copy), or the six C3 metrics plus the BTC and ETH exchange flows (about 1.6 GB a year for the six, the flows on top and not measured) (D3)? | Every free daily metric. A series not recorded today is lost for good, C3's features are not pre-registered, and the cost is bytes on custody, not requests. | |
| 3 | NAS route: a fifth ops-sourced custody channel, which costs a key pair, the NAS archive-pull moved to a `-compat` build that carries the verifier, one NAS converge that recreates archive-pull and replays the gate export cold, and a verify of a twenty-fourth of the copy every loop; or the `hot-out` outbox, with no NAS change, but the set goes to every research node through `data fetch` (D14, D15)? | Custody. The set grows for ever and cannot be backfilled, which is custody's definition, and spec 00051 D10 rules out sole custody. On the custody route the first tick waits for the NAS channel (deployment); on the outbox route it could start at the ops converge. | |
| 4 | Licences (D3, D19). This repository is public on GitHub, so any fixture committed to it is published. (a) Coin Metrics Community is CC BY-NC 4.0, whose test is purpose: "NonCommercial means not primarily intended for or directed towards commercial advantage or monetary compensation". Research that decides a for-profit trading engine's inputs may itself be directed towards commercial advantage, whether or not a value ever reaches the engine, and the community data is licensed "for NonCommercial purposes only". Do you accept that risk for recording whole Coin Metrics bodies twice a day in the private copies on ops and the NAS, before any permission? If you answer no, the recorder starts with `fng`, `mempool-hashrate` and `cm-status` alone, and the ten `cm-<asset>` sources and `cm-catalog`, under the same licence, wait for written permission; every Coin Metrics day before it arrives is never recorded, MVRV, the series C3 names first, among them. (b) Committed fixtures of Coin Metrics data, and of mempool.space data, which carries no licence grant at all, would be published. Which instead: fixtures synthesised in each source's shape with no vendor values; fixtures kept out of the tree, so CI cannot run the tests that read them; or written permission from Coin Metrics (whose terms URL now redirects to Talos) and mempool.space first, which holds the plan until it arrives? (c) Do you accept two requests a day to mempool.space, which states no limits, kept in private copies only, and alternative.me under its terms, which permit any use with attribution beside a display, its real body committed as a fixture? | (a) Accept, and say so in your answer: no later decision can record the days already passed, and the copies stay private. Ask Coin Metrics in writing before a C3 trial relies on the record; until it answers, the catalog marks the data never an engine input. (b) Synthesised fixtures in each source's shape with no vendor values, built from real bodies kept out of the tree, as D19 now specifies; real Coin Metrics or mempool.space bytes in the tree only after written permission. (c) Accept both. | |
| 5 | BGeometrics: register a free key, which means an account (D3)? | Not now. It would be the recorder's first secret, its 15 requests a day per IP are shared with this workstation, it covers four years and hides the last seven days. Revisit only if C3's SOPR question ripens under T0016. | |
| 6 | Paging: a warning at 25 h without a good fetch, or critical, or 13 h (D11)? | A warning at 25 h. It never pages a tick the next one heals, and it leaves about 3 h to save a day by hand in the worst case. | |
| 7 | Dead-man: a 13th check, `zcrypto-vintage-record`, at 90000 s and 21600 s, pinged only when a tick was published, which D9's exit codes 0 and 1 now mean and nothing else (D12)? It moves the fleet's count of checks from 12 to 13 in three test files, a script's help string and names, and two runbooks. | Yes. It is the one page that still reaches you when Grafana's path is dark, and with every exception caught and exit 1 reserved for a published tick, a crash before publication can no longer keep it green. | |
| 8 | Reader scope: ship the derivation as code and tests now, and leave the derived dataset and its registry arm to the first C3 trial spec (D16)? | Yes. It proves the capture can answer what a trial will ask while a defect can still be fixed, without publishing a format no consumer has asked for. | |
| 9 | Rollout: its own attended window as soon as it merges, or the next routine ops roll; any stopgap recording until then; and does the first tick wait for a clean NAS loop, after a NAS converge that recreates archive-pull on the `-compat` pin, run with the pin uncommitted, and replays the gate export cold, or start at the ops converge with hours in which the ops copy is the only one (deployment)? | Its own window as soon as it merges, no stopgap, and the first tick after the first clean NAS loop. Each day of delay is a day the record never holds, but spec 00051 D10 rules out sole custody, and the wait is one NAS converge; the pins pull request that records it follows the first tick. A hand-made stopgap would lack the clock evidence and the chain and would need its own importer. | |
| 10 | Decisions-log home for the `[00158]` entry: `docs/research/10.phase4-decisions.md`, beside the C families, or `02.phase1-decisions.md`, as a dataset's design? | Phase 4, beside the family whose kill bar the record serves. | |
| 11 | The rollout skill's *Ops converges* names "the archive-pull, replay, panel and tape-bars runners" as the ops renders that need a deploy-log row carrying `ops_image_digest` before the preview's source-diff read (`.claude/skills/zcrypto-rollout-image/SKILL.md`); the new runner renders the same way, so the sentence goes stale. Add the runner to that sentence in this change, as its own `claude(` commit read at that path's floor, or leave the skill untouched? | Add it, one line through `zcrypto-refine-rules`' edit contract: a skill that omits a runner misleads the next ops rollout's preview read. | |
