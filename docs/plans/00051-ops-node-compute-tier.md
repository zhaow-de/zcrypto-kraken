# Ops-node bring-up (OPS-1…3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the home ops node (`i7-13700 / 64 GB / 4 TB NVMe`, `ssh hp`, AVX2) into the fleet as the compute tier per spec `00051`: provisioned and hardened (OPS-1), seeded with the archive + running the Binance liquidations recorder with NAS replication (OPS-2), and executing the first-ever archive continuity-replay + Role B verified-path runs (OPS-3).

**Architecture:** The ops node is purely additive (spec 00051 D7) — nothing moves off the NAS in this component. It joins ansible as `ops_host` reusing the existing roles; it **pulls** everything (chained, D8) and is **pulled from** for its own products (D9); it runs the **default AVX image variant**, not `-compat`. OPS-4 (L2 panel) and OPS-5/6 (offload, loop) are separate follow-on components tracked by [[T0033]] — not in this plan.

**Tech Stack:** ansible (existing roles + one new `ops` role), docker compose + digest-pinned images, `zcrypto` CLI (Typer / polars / `websockets>=16.1` / asyncio), rrsync forced-command channels, healthchecks.io dead-men.

## Global Constraints

- **No trade key, never `engine_host`, no live execution** on the ops node (spec 00051 D10). The `converge_primary` guard keys on `engine_host` membership — the ops node must never join it.
- **Pull-only transport everywhere** (D8/D9): ops pulls from NAS; NAS pulls ops-produced data. Nobody pushes. Every channel = its own vaulted ed25519 keypair + `rrsync -ro` forced command + pinned host key + `.sha256` manifests where the payload is segments.
- **No sole custody** (D10): anything the ops node produces that cannot be regenerated (liquidations — not backfillable, [[T0023]]) must replicate to the NAS in the same task that creates it.
- **Image variant**: ops node runs the **default** (AVX) build `ghcr.io/zhaow-de/zcrypto-capture@sha256:<digest>` — never `-compat`. Digest-pinned, no `:latest` in deployed compose.
- **Maintenance window**: ops reboot at **02:25 UTC** (provisional; ≥1 h from every 4 h boundary, off the hour, ≥1 h from 21:25/22:25) — asserted distinct from the capture hosts' at converge ([[T0027]]).
- **OS = Debian 13**, matching the capture/engine fleet (decided 2026-07-15). The box arrived as Ubuntu 26.04; it is reinstalled as Debian 13 so the existing `base`/`docker` roles run unchanged — no two-distro `when:` fork (constraint 6). This is a precondition of Task 2.
- **Home-LAN box, not internet-facing**: the ops play omits `hardening`/`firewall`/`fail2ban` (those exist for the public-IP capture/engine hosts). SSH stays on **port 22** (matches the `ssh hp` alias); no lockdown to 10022.
- **Hostname**: the box currently calls itself `zcrypto-red` (collision with the secondary). Inventory name + `base_hostname` = **`zcrypto-ops`**.
- Loggers named `get_logger("<package>.<module>")` → `logging.getLogger("zcrypto.<package>.<module>")`; one-line markdown paragraphs; `uv run pre-commit run -a` is the commit gate; TDD for all code; every commit subagent-reviewed before push.
- **Attended tasks** (marked **[attended]**) touch real hosts, are hard-to-reverse (bootstrap/harden/deploy the owner's home server with the operator master key, restart no live capture), and are executed by the **orchestrator with the user present** — never by a subagent, never unattended. They still verify by outcome.

## Reuse map (from the 2026-07-15 scout pass — exact surfaces)

- **`cli/capture/segment_writer.py::SegmentWriter`** — `__init__(base_dir, pair, kind, schema, *, flush_rows=5000, dedup_key=None, oracle=None)`; per-event `append(event: dict)` (rotation is driven internally by `event["ts"]` crossing the UTC hour — no `rotate()` call); idempotent `close()` (flushes buffer, does **not** finalize the open hour). Output path `<base>/<pair>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet`; sidecar `<HH>.parquet.sha256` = `"<hex>  <HH>.parquet\n"` (two spaces). `ts` must be tz-aware UTC microsecond. Fully generic — reuse **directly** for a new `kind="liquidations"` + `LIQ_SCHEMA`; `dedup_key` seeds an on-disk `_seen` set surviving restarts (Binance redelivers `forceOrder` on reconnect). Module fn `verify_manifest(path) -> bool`.
- **`cli/capture/ws_client.py::CaptureClient.stream()`** — async generator: `connect → subscribe → async for raw in ws → yield parse_message(raw) → backoff-reconnect`; `connect_fn`/`sleep_fn` injected for tests; `compute_backoff` = exp base 1 s cap 60 s, ERROR every 10th failed attempt; `connected` property. `CancelledError` propagates (the stop signal). Reuse the **shape**; Binance body differs (below).
- **`cli/capture/command.py`** — `_run` spawns 3 asyncio tasks (`consumer`, `health`, `disk_check`), `loop.add_signal_handler(SIGINT/SIGTERM, main_task.cancel)`, `finally` cancels all + `writer.close()`. `_healthcheck_loop` gate (verbatim): `if client.connected and monitor.is_healthy(pairs) and not watermark.breached and watermark.measurable: ping_healthcheck(url)`. `ping_healthcheck`/`DiskWatermark`/`GapMonitor` in `cli/capture/gap_monitor.py`.
- **`cli/capture/book.py::OrderBook`** — `__init__(symbol, depth)`, `ingest_snapshot(data)`, `ingest_update(data)`, `checksum()->int`, `validate(expected)->bool` (sets `self.desynced`). `data` is the **Kraken WS payload** shape (`bids`/`asks` = lists of `{"price","qty"}`, `checksum` int), **not** the parquet row. **Precision caveat (design-blocking, see OPS-3):** parquet stores `price`/`qty` as Float64; the CRC needs raw wire strings, so `checksum()` is not byte-exact re-derivable from the archive.
- **`cli/archive/reader.py::canonical_segments(primary_root, reconciled_root=None, *, kind="book") -> Iterator[(pair, hour, path)]`** — reconciled-first, sorted `(pair, hour)`, committed finals only. Concatenate in yield order; never re-sort rows.
- **`cli/engine/command.py::replay`** — `zcrypto engine replay [--date YYYY-MM-DD] [--path fast|verified] [--journal-dir PATH]`; reads journal artifacts (not the L2 archive); `verified` = the oracle builder (`build_crossfreq_system`, may raise on degenerate inputs where `fast` returns); read-only, idempotent, exits non-zero on any mismatch/validation failure. OPS-3 only **schedules** it — no new engine code.

---

### Task 1: Ansible — `ops_host` group, host vars, `ops` role skeleton, site play

**Files:**
- Modify: `infra/ansible/inventory/hosts.yml`, `infra/ansible/site.yml`, `infra/ansible/roles/base/tasks/main.yml`
- Create: `infra/ansible/host_vars/zcrypto-ops/vars.yml`, `infra/ansible/host_vars/zcrypto-ops/vault.yml`, `infra/ansible/roles/ops/tasks/main.yml`, `infra/ansible/roles/ops/defaults/main.yml`

**Interfaces:**
- Produces: inventory group `ops_host` = `{zcrypto-ops}`; a third `site.yml` play `converge the ops node` with roles `[base, hardening, firewall, fail2ban, chrony, docker, ops]`; role defaults `ops_data_dir: /var/lib/zcrypto-ops`, `ops_compose_dir: /etc/zcrypto-ops` (both created `0755 deploy:deploy`).
- Consumes: existing roles unchanged; `hardening_ssh_allow_users`/`hardening_ssh_listen_to` from group/host vars exactly as the capture hosts.

- [ ] **Step 1 — inventory + host_vars.** Add to `hosts.yml` under `children:` a sibling group `ops_host: {hosts: {zcrypto-ops: {}}}` with the comment: *compute tier (spec 00051); NEVER add to engine_host — the trade key must not render here (D10)*. Create `host_vars/zcrypto-ops/vars.yml`: `base_hostname: zcrypto-ops`, `base_unattended_upgrades_reboot_time: "02:25"`. Create `host_vars/zcrypto-ops/vault.yml` (per-value `!vault`, same header as `host_vars/zcrypto-red/vault.yml`) holding `ansible_host` — encrypt `z-home-zcrypto.zhaow.pro` via `uv run ansible-vault encrypt_string --stdin-name ansible_host` (value on stdin; **no** extra `--vault-password-file` — ansible.cfg supplies it, passing both errors `vault-ids default,default`).
- [ ] **Step 2 — generalize the fleet reboot-window assert.** Read the existing assert in `roles/base/tasks/main.yml` that checks the two capture hosts' `base_unattended_upgrades_reboot_time` differ. Generalize it to assert **all** hosts in `groups['capture_host'] + groups['ops_host']` have pairwise-distinct values (build the list from hostvars, compare `| map('extract', hostvars, 'base_unattended_upgrades_reboot_time') | unique | length == list | length`). Keep the per-host `when:` so a `--limit` run still works.
- [ ] **Step 3 — `ops` role.** `roles/ops/defaults/main.yml`: the two dir vars above. `roles/ops/tasks/main.yml`: create both dirs (`deploy:deploy`, `0755`); `apt: {name: [rsync], state: present}` (ships `/usr/bin/rrsync`, needed by OPS-2's replication channel). Nothing else yet — later tasks extend this one role with compose/timer files; keep it **one** role, not four.
- [ ] **Step 4 — site play.** Append a third `site.yml` play: `- name: converge the ops node — compute tier (spec 00051)` / `hosts: ops_host` / `become: true` / roles `[base, chrony, docker, ops]` — **only these four**; the ops node is a home-LAN box, so `hardening`/`firewall`/`fail2ban` are deliberately omitted. Add a `pre_tasks` debug (`tags: [always]`) stating the charter: *no trade key, never engine_host, pull-only transport (D10); home-LAN box, so no hardening/firewall/fail2ban*. Do **not** add the `converge_primary` guard here (that guard keys on `engine_host`; the ops play never touches it).
- [ ] **Step 5 — verify statically.** `uv run ansible-inventory --graph` (NEVER `--list`/`--host` — they decrypt+print the vault) → `zcrypto-ops` under `@ops_host` only, absent from `@engine_host`. `uv run ansible-playbook site.yml --syntax-check`. `uv run pre-commit run -a` clean.
- [ ] **Step 6 — commit** `feat(config): ops_host group + ops role skeleton (spec 00051 OPS-1)`.

---

### Task 2 **[attended]**: Bootstrap + converge the ops node

**Files:** `infra/ansible/bootstrap.yml` (add an `ops_host` play — see Step 0). Otherwise operational; verifies Task 1's artifacts against the real host.

- [ ] **Step 0 — precondition + bootstrap play.** (a) The box is **reinstalled as Debian 13** (it arrived Ubuntu 26.04; decided 2026-07-15 for fleet homogeneity). (b) `bootstrap.yml` today is `hosts: capture_host` and locks SSH down to port 10022 — wrong for a home-LAN ops node. Add a **separate** `bootstrap.yml` play `hosts: ops_host` that creates the `deploy` user + installs its pubkey + passwordless sudo, but **keeps SSH on port 22 and applies no lockdown/hardening** (the ops node's `ssh hp` alias uses port 22). Keep it minimal — just enough that `run.sh` (deploy key) can converge afterward.
- [ ] **Step 1 — pre-flight.** `ssh root@z-home-zcrypto.zhaow.pro` (master key `zhaow-master-2018`) after the Debian reinstall. Confirm `cat /etc/os-release` = Debian 13; hardware `nproc` ≥ 20, `grep -m1 avx2 /proc/cpuinfo` non-empty, `df -h /` ≈ 3+ TB free; nothing zcrypto runs yet.
- [ ] **Step 2 — bootstrap.** `uv run ansible-playbook bootstrap.yml --limit zcrypto-ops -e ansible_user=root -e ansible_port=22` — run **direct**, NOT via `run.sh` (a virgin host answers only to the operator master key, which `run.sh`'s throwaway agent excludes). No `converge_primary` (the ops node is not in `engine_host`).
- [ ] **Step 3 — verify deploy access.** `ssh hp` works (deploy user, passwordless sudo); root SSH refused; the hardened SSH port is live.
- [ ] **Step 4 — converge.** `./scripts/run.sh site.yml --limit zcrypto-ops`. If it fails on a missing capture/engine var, that is a Task-1 bug (the ops play must not import capture/engine vars) — fix Task 1, re-run.
- [ ] **Step 5 — verify by outcome.** `ssh hp hostname` = `zcrypto-ops` (collision gone); the two `ops_data_dir`/`ops_compose_dir` exist `deploy:deploy 0755`; `rrsync` present; docker up; reboot timer at 02:25; firewall/fail2ban/chrony active; `/root/.ssh/authorized_keys` still holds the master key (hardening must not purge it). Record the converge summary (`ok=/changed=/failed=0`).

---

### Task 3: Binance liquidations recorder (`zcrypto liquidations`)

**Files:**
- Create: `cli/liquidations/__init__.py`, `cli/liquidations/ws_client.py`, `cli/liquidations/recorder.py`, `cli/liquidations/command.py`, `cli/liquidations/errors.py`
- Modify: `cli/capture/segment_writer.py` (add `LIQ_SCHEMA` beside `BOOK_SCHEMA`/`TRADE_SCHEMA`), `cli/__main__.py` (register command), `README.md` (Usage)
- Test: `tests/test_liquidations_ws_client.py`, `tests/test_liquidations_recorder.py`, `tests/test_liquidations_command.py`

**Interfaces:**
- Consumes: `SegmentWriter`, `get_logger`, the `CaptureClient.stream()` shape (reimplemented for Binance, not imported — Kraken subscribe/CRC differ).
- Produces: `LIQ_SCHEMA: dict[str, pl.DataType]`; `BinanceLiquidationClient(uri, *, connect_fn=…, sleep_fn=…).stream() -> AsyncIterator[dict]`; `parse_force_order(raw: str) -> dict | None`; a `liquidations` Typer command doing `SegmentWriter(base, symbol, "liquidations", LIQ_SCHEMA, dedup_key="event_id")`.

**Design decisions (resolve up front):**
- Endpoint: keyless combined stream `wss://fstream.binance.com/stream?streams=!forceOrder@arr` (all-symbol force-orders); no auth, no subscribe frame needed (subscription is in the URL). Parse the `{"stream":…, "data":{"e":"forceOrder","o":{…}}}` envelope.
- `LIQ_SCHEMA` columns: `ts: Datetime("us","UTC")` (from `o.T` epoch-ms), `symbol: Utf8` (`o.s`), `side: Utf8` (`o.S`), `price: Float64` (`o.p`), `orig_qty: Float64` (`o.q`), `avg_price: Float64` (`o.ap`), `order_status: Utf8` (`o.X`), `event_id: Utf8` (synthesized `f"{o.s}-{o.T}-{o.p}-{o.q}"` — Binance gives no order id on this stream; used as `dedup_key`).
- `oracle=None` (no cross-stream sibling to corroborate an hour boundary for a single Binance feed; rotation trusts each event ts, still protected by SegmentWriter's implausible-ts guards). Documented in the recorder.
- No CRC, no OrderBook, no GapMonitor checksum path — the only "gap" is a reconnect window; the dead-man gate reduces to `client.connected and not watermark.breached and watermark.measurable` (reuse `DiskWatermark` + `ping_healthcheck` verbatim; drop the `monitor.is_healthy` term or supply a reconnect-only monitor — pick the former for simplicity and note it).

- [ ] **Step 1 — `parse_force_order` test.** A real `forceOrder` JSON envelope → the row dict with a tz-aware UTC `ts`; a non-forceOrder / malformed line → `None` (never raises).
- [ ] **Step 2 — implement `parse_force_order`** in `recorder.py`; `LIQ_SCHEMA` in `segment_writer.py`.
- [ ] **Step 3 — reconnect test.** `BinanceLiquidationClient.stream()` with an injected `connect_fn` yielding two frames then `ConnectionClosed`, and an injected `sleep_fn`: asserts it reconnects, resets backoff on success, and surfaces parsed dicts. Mirror `tests/test_capture_ws_client.py`.
- [ ] **Step 4 — implement `ws_client.py`** (the connect→recv→backoff generator, no subscribe frame).
- [ ] **Step 5 — recorder end-to-end test.** Feed a synthetic stream of N force-orders across two UTC hours into the recorder wired to a real `SegmentWriter(tmp_path, …)`; assert the hour finals exist, `verify_manifest` passes, dedup drops a redelivered event, and shutdown flushes.
- [ ] **Step 6 — implement `recorder.py` run-loop + `command.py`** (3-task asyncio layout, SIGTERM handler, dead-man gate as above); register `app.command(name="liquidations")(...)` in `cli/__main__.py`.
- [ ] **Step 7 — Usage + full suite.** Add the `zcrypto liquidations` subcommand to `README.md` §Usage. `uv run pytest -q` green; `uv run pre-commit run -a` clean.
- [ ] **Step 8 — commit** `feat(liquidations): Binance forceOrder recorder reusing SegmentWriter (spec 00051 OPS-2)`.

---

### Task 4: Recorder deploy artifacts — compose service, NAS replication channel, dead-man

**Files:**
- Create: `infra/ansible/roles/ops/templates/compose.yaml.j2` (the ops-node stack), `infra/ansible/roles/ops/templates/liquidations-replicate.sh.j2` + a systemd timer/service (or an in-compose loop mirroring `pull-entrypoint.sh`), `infra/ops/README.md` (deploy + env-var contract + rrsync channel setup, mirroring `infra/nas/README.md`)
- Modify: `infra/ansible/roles/ops/tasks/main.yml` (install the above)

**Interfaces:**
- Produces: a digest-pinned `liquidations` container writing to `${ops_data_dir}/liquidations`; a `rrsync -ro` forced-command channel on the ops node exposing that tree; the NAS's `pull-entrypoint.sh` gains a `LIQUIDATIONS_SOURCE`/`LIQUIDATIONS_DEST` pull (documented, wired at OPS-2 deploy). Dead-man: a healthchecks.io check pinged by the recorder.
- Consumes: `SegmentWriter` output layout (Task 3), the rrsync channel pattern (`infra/nas/README.md`), the digest-pin discipline.

- [ ] **Step 1 — compose template.** `ghcr.io/zhaow-de/zcrypto-capture@sha256:${ops_image_digest}` (default AVX build), `entrypoint: ["zcrypto","liquidations", …]`, `restart: unless-stopped`, volumes `${ops_data_dir}:/data`, env `LIQUIDATIONS_HEALTHCHECK_URL`, `json-file` logging 10m×3. No trade key, no engine.
- [ ] **Step 2 — replication.** The NAS **pulls** the liquidations tree (D9): document a new `sync_liquidations` rrsync `-ro` forced-command channel on the ops node + its own vaulted key + pinned host key, and the NAS-side `LIQUIDATIONS_SOURCE`/`DEST` pull cycle. Manifests (`.sha256`) already ride along (SegmentWriter writes them) → the NAS pull hash-verifies exactly as the capture channel.
- [ ] **Step 3 — role install tasks + `sh -n`/compose-config render test.** Extend `roles/ops/tasks/main.yml` to template the compose + replication units. Verify: `docker compose -f <rendered> config` parses; `sh -n` the replication script; `ansible-playbook site.yml --syntax-check`.
- [ ] **Step 4 — `infra/ops/README.md`** — deploy steps, env-var contract table, the `sync_liquidations` channel setup (keygen, forced-command line, host-key pin), the healthchecks.io check. Mirror `infra/nas/README.md`'s shape.
- [ ] **Step 5 — commit** `feat(config): ops-node liquidations compose + NAS replication channel (spec 00051 OPS-2)`.

---

### Task 5 **[attended]**: Seed the hot tier + deploy the recorder

**Files:** none (operational; consumes Tasks 3–4). Precondition: Task 2 done (host converged).

- [ ] **Step 1 — build + pin the image.** Trigger the branch `workflow_dispatch` building both variants; read the **default (AVX)** digest (`docker buildx imagetools inspect …:<tag>`); confirm `zcrypto liquidations --help` is in it before pinning. Set `ops_image_digest`.
- [ ] **Step 2 — seed.** From the NAS, pull the compiled sets + a recent raw window to `${ops_data_dir}` (record window size `N`, spec 00051 open param — start 14–30 days). Verify manifests with `verify_tree` on the ops node.
- [ ] **Step 3 — channel keys.** Generate the `sync_liquidations` keypair (vaulted), install the forced-command line on the ops node, pin the ops host key on the NAS (verify against the host's own `/etc/ssh/ssh_host_ed25519_key.pub`, not TOFU).
- [ ] **Step 4 — provision the dead-man.** Create the healthchecks.io check via the Management API (vaulted `healthchecks_api_key`), attach the email channel, put its ping URL in the recorder env.
- [ ] **Step 5 — deploy + verify by outcome.** `docker compose up -d` the recorder; after the next hour boundary confirm `${ops_data_dir}/liquidations/<SYM>/…/<HH>.parquet` finals appear with valid `.sha256`; the NAS pull mirrors them (`checked=N ok=N failed=0`); the dead-man is green. `dropping/late` lines right after start are healthy (resubscribe).

---

### Task 6: Archive continuity-replay driver (`zcrypto archive verify-replay`)

**Files:**
- Create: `cli/archive/replay.py`, and a `verify-replay` command on the archive Typer sub-app (in `cli/archive/command.py`)
- Modify: `README.md` (Usage)
- Test: `tests/test_archive_replay.py`

**Interfaces:**
- Consumes: `OrderBook(symbol, depth)`, `canonical_segments(primary_root, reconciled_root, kind="book")`, `read_parquet`, `BOOK_SCHEMA`.
- Produces: `replay_segment(path: Path, symbol: str, depth: int) -> ReplayResult` and `verify_replay(primary_root, reconciled_root, *, pair=None, since=None, depth) -> list[ReplayResult]`; `ReplayResult(pair, hour, rows, messages, desync_count, first_desync_ts, snapshot_anchored: bool, error: str | None)`.

**Scope (reframed per the 2026-07-15 precision finding — READ THIS):** the archive stores `price`/`qty` as **Float64**, so `OrderBook.checksum()` is **not** byte-exact re-derivable and MUST NOT be compared to the stored `checksum` column (it will mismatch on every zero-trailing level — a guaranteed false alarm). Instead this driver proves the canonical archive **reconstructs a coherent book**: (1) each hour opens with a `type=="snapshot"` anchor; (2) rows regroup by `(ts, symbol, type, checksum)` into WS-shaped `data` and feed `ingest_snapshot`/`ingest_update` in row order without structural error; (3) `OrderBook.desynced` is tracked — but because the CRC can't be re-derived, desync is measured **structurally** (an update to a price level absent from a depth-bounded book beyond tolerance, a snapshot gap), not by CRC compare. The stored `checksum` is treated as capture-time ground truth (it was CRC-validated live at capture). True byte-exact CRC re-derivation is deferred to a new topic (needs a raw-string price/qty capture-schema change — registered at closeout).

- [ ] **Step 1 — regroup test.** Exploded `BOOK_SCHEMA` rows (two messages, one snapshot + one update, each fanned across bid/ask levels sharing `(ts,type,checksum)`) → the two reconstructed WS `data` dicts in order. This is the inverse of `command.py:146-158`.
- [ ] **Step 2 — `replay_segment` happy-path test.** A synthetic one-hour book segment (snapshot then N coherent updates) → `ReplayResult` with `snapshot_anchored=True`, `desync_count=0`, `error=None`.
- [ ] **Step 3 — corruption tests.** (a) an hour with no leading snapshot → `snapshot_anchored=False`; (b) an unreadable/short parquet → `error` set, not raised; (c) a structurally impossible update sequence → `desync_count > 0`. One corrupt hour must not abort the sweep.
- [ ] **Step 4 — implement `replay.py`** (`replay_segment` + `verify_replay` over `canonical_segments`, per-hour try/except isolating failures into `ReplayResult.error`, same isolation pattern as `infra/scripts/gap_distribution.py::observe_gaps`).
- [ ] **Step 5 — `verify-replay` command + a report** (per-hour ok / anchored / desync counts; exit non-zero if any hour has `error` or `desync_count>0`, mirroring `engine replay`'s non-zero-on-drift contract). Add to `README.md` §Usage.
- [ ] **Step 6 — full suite + gate.** `uv run pytest -q` green; `uv run pre-commit run -a` clean.
- [ ] **Step 7 — commit** `feat(archive): canonical book continuity-replay verifier (spec 00051 OPS-3)`.

---

### Task 7: Ops-node replay + verified-path timers

**Files:**
- Create: `infra/ansible/roles/ops/templates/verify-replay.service.j2` + `.timer` (daily continuity-replay over the pulled canonical archive), `infra/ansible/roles/ops/templates/verified-replay.service.j2` + `.timer` (daily `zcrypto engine replay --path verified` over the pulled journal)
- Modify: `infra/ansible/roles/ops/tasks/main.yml`, `infra/ops/README.md`

**Interfaces:**
- Consumes: Task 6's `verify-replay` command; the existing `engine replay --path verified`; the seeded archive + journal on the ops node.
- Produces: two systemd timers on the ops node, each writing a textfile-collector metric (`.prom`) for the pull-lag/verify observability already scraped by Alloy, and pinging a dead-man on a clean run.

- [ ] **Step 1 — timer units.** Both services run the CLI in the pinned image (or the host `zcrypto` if seeded as a venv — pick the container form for parity with capture), off-hour, not overlapping 02:25 or the capture windows. Emit a `.prom` textfile (`ops_verify_replay_desync_total`, `ops_verified_replay_mismatch_total`, `_last_success_timestamp`) so Alloy scrapes them.
- [ ] **Step 2 — role install + render test.** Extend `roles/ops/tasks/main.yml`; `systemd-analyze verify` the rendered units (or `ansible-playbook --syntax-check` + a lint); document in `infra/ops/README.md`.
- [ ] **Step 3 — Grafana** (optional, deferrable to OPS-5): note the two new metric families for a future ops row; do not push rules blind (T0034 discipline — arm only after the series are visible).
- [ ] **Step 4 — commit** `feat(config): ops-node continuity-replay + verified-path timers (spec 00051 OPS-3)`.

---

### Task 8 **[attended]**: First continuity-replay + verified-path runs

**Files:** none (operational; consumes Tasks 6–7). Precondition: Task 5 done (host seeded).

- [ ] **Step 1 — first continuity-replay.** On the ops node, run `zcrypto archive verify-replay` over the seeded canonical archive for a known-good day; expect `desync_count=0`, every hour `snapshot_anchored`. Investigate any desync as a real finding (it may reveal an archive or reconciler bug — do not loosen the check).
- [ ] **Step 2 — first verified-path.** Run `zcrypto engine replay --path verified --date <recent day>` over the seeded journal; expect `0 mismatch, 0 validation failure`. This is the first-ever verified run off the Atom — a `verified`-only raise on degenerate input is a finding to record, not to suppress.
- [ ] **Step 3 — arm the timers + dead-men.** Enable both timers; confirm the `.prom` textfiles appear and Alloy scrapes them; provision + attach the two dead-men.
- [ ] **Step 4 — feed 00050 Task 13.** Record that the ops-node replayer now exists (00050 Task 13's drill after-step depends on it); note it in that plan's Task 13 and in the closeout.

---

### Task 9: Closeout

**Files:**
- Modify: `docs/iterations-history-phase<N>.md` (same phase file as spec 00050's Role C entry — route by subject-matter phase per `.claude/rules/iterations-history.md`), `docs/open-topics/README.md`, `docs/open-topics/T0033-home-ops-node-compute-tier.md`
- Create: the new CRC-precision topic file (serial = next free across `docs/open-topics/` + `archive/`)

**Authored at closeout, not before (per `.claude/rules/iterations-history.md` closeout-doc discipline):**

- [ ] **Step 1 — CRC-precision topic** already registered during planning as [[T0045]] (`docs/open-topics/T0045-crc-rederivation-needs-raw-string-price-qty.md`) — verify its `ripe_when:` still holds and its index bullet is in R&D `### Open`; no new file needed.
- [ ] **Step 2 — flip [[T0033]].** Its OPS-1…3 sub-items land here; keep `status: partial` (OPS-4/5/6 remain) with the remaining next-steps trimmed to OPS-4…6; index bullet synced.
- [ ] **Step 3 — iterations-history entry** — one section, bullets per task/artifact (ops_host role, liquidations recorder + LIQ_SCHEMA, continuity-replay verifier, timers, the CRC-precision reframe + topic).
- [ ] **Step 4 — deferral sweep.** Grep the closeout prose for defer/follow-up/later/once/when/revisit/noted; each exits as a registered topic or an explicit one-line drop. Confirm no attended step (Tasks 2/5/8) was silently skipped — if the host bring-up is still pending, the PR is *(2 of 2)*-style incomplete and says so.
- [ ] **Step 5 — commit** `docs(infra): OPS-1…3 closeout — T0033 sync + CRC-precision topic + iterations-history`.

---

## Execution notes (orchestrator)

- **Autonomous now (reversible code, subagent-driven):** Tasks 1, 3, 6 — and the template/doc halves of 4, 7. Build + test them on the branch; they de-risk the attended deploys.
- **Attended (user present, hard-to-reverse):** Tasks 2, 5, 8 and the deploy halves of 4/5/7 — bootstrap/harden/deploy the home server, seed, first live runs. Never unattended.
- **PR:** one component branch → one PR into `develop`; if the attended tasks are still pending at hand-back, the PR is opened incomplete (checklist unchecked) and stays open until the bring-up completes (one PR = the whole logical component).

## Self-review

- **Spec coverage:** D1–D11 → topology/reuse honored; D7 additive (no NAS cutover) → Task 1 adds a play, moves nothing; D9 pull-only → Task 4 Step 2 has the NAS pull ops; D10 charter → Task 1 Step 4 pre_tasks + no `engine_host`; OPS-1 Provision → Tasks 1–2; OPS-2 Seed+recorder → Tasks 3–5; OPS-3 Replayer → Tasks 6–8. ✅
- **Precision finding** propagated: Task 6 scope block + Task 9 topic. ✅
- **Type consistency:** `LIQ_SCHEMA`, `parse_force_order`, `ReplayResult`, `verify_replay` used consistently across tasks and the reuse map. ✅
- **Attended tasks** never dispatched to subagents; each verifies by outcome. ✅
