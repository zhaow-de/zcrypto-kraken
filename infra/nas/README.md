# NAS archive-pull stack (spec 00048, Role A)

The always-on NAS pull/archive tier: a single container (`archive-pull`) that pulls the VPS
capture segments and the engine journal on a schedule and archives the result to
`/volume1/ZhaoCrypto` — decoupling data durability from the intermittently-online workstation
(see `docs/specs/00048-three-tier-topology-design.md`, Role A). It supersedes T0003's
workstation-pull approach. The capture-segments pull is hash-verified against each segment's
`.sha256` manifest sidecar; the engine-journal pull runs `--no-verify` (its `.parquet` snapshots
have no sidecars — their integrity is a JSON `snapshot_content_hash`, verified later by Role B on
replay).

Everything runs **inside the container** under Synology Container Manager: no systemd units, no
DSM Task Scheduler entries, no NAS-OS config. `infra/nas/pull-entrypoint.sh` is the in-container
scheduler — a loop that runs `zcrypto archive pull` for each source every
`ARCHIVE_PULL_INTERVAL` seconds and survives a single failed pull without exiting; Container
Manager's `restart: unless-stopped` policy is what survives a NAS reboot.

## Deploy (Ansible — the `nas` role, T0056)

The NAS is Ansible-managed: the `nas` role (`infra/ansible/roles/nas`, play in `site.yml`) deploys `compose.yaml`, `pull-entrypoint.sh`, and `config.alloy` **verbatim from this directory** (the single source of truth — no copies live in the role) and renders the two env files next to them under `/volume1/docker/zcrypto-archive/`: `.env` (the image digest pins + pull sources, from `infra/ansible/host_vars/nas/vars.yml`; the vaulted `GATE_HEALTHCHECK_URL` from `host_vars/nas/vault.yml`) and `alloy-secrets.env` (the Grafana Cloud credentials, from `group_vars/observed/vault.yml`). Hand-copying files to the NAS is dead — deployed files drifted for days, and deploying the then-committed `:latest` placeholder verbatim killed the pull loop for ~90 s on 2026-07-16 (T0056).

```bash
cd infra/ansible
./scripts/run.sh site.yml --limit nas --tags nas                        # render-only: files land + a changed-files report, nothing restarts
./scripts/run.sh site.yml --limit nas --tags nas -e nas_apply_compose=true   # render + apply EVERYTHING currently rendered
```

Without `-e nas_apply_compose=true` the converge is **render-only**: files land on the NAS and the play reports which ones changed, but nothing restarts — deliberate, the same explicit-apply discipline as the ops role's attended first start. With the flag, end-of-role apply tasks **always run and apply everything currently rendered — not just what changed this run** (they are gated on the flag itself, not on notifications: a notify consumed by a `when:`-skipped handler is dropped, not deferred, so the old handler-based "render now, apply later" sequence could never apply; finding, 2026-07-17). The apply is three steps: `compose up -d`, then an unconditional `archive-pull` restart (`pull-entrypoint.sh` is bind-mounted, so a content change never alters the compose service hash and `up -d` alone would leave the old loop running), then an Alloy restart — what applies the `config.alloy` the same converge redeploys. It was added for T0048 (Alloy's docker tailer kept following the dead container ID after a recreate), and **that failure mode is retired on this host**: the tailer is gone and logs reach Alloy through the host journal (see the Alloy section below). Idempotent-safe: restarting an already-current container is a harmless few seconds of downtime on best-effort loops.

**The play's first act is a UTC clock guard and it fails closed**: `date +%z` must print `+0000`. `docker logs --since` parses its argument in the host's **local** time, and the NAS's CEST clock produced false review verdicts on 2026-07-16. Fix: DSM Control Panel → Regional Options → Time Zone → **(GMT) Greenwich Mean Time**, then re-run the play.

Host quirks — encoded as `host_vars/nas/vars.yml`, repeated here for humans:

- DSM's `/usr/bin/python3` is 3.8.15, below ansible-core 2.21's 3.9 floor — the play runs the `python314` package's `/usr/local/bin/python3.14` (`ansible_python_interpreter`).
- DSM chroots sftp to the shared folders, so sftp/scp cannot write arbitrary paths — `ansible_ssh_transfer_method: piped` (plain ssh stdin).
- Docker is `/usr/local/bin/docker` and **not** on sudo's PATH — a bare `sudo docker` fails command-not-found, and a script that ignored that failure once read the empty output as a false all-clear (`nas_docker`).

### Image pins — three identifiers for one object

A pin is a **manifest digest** (`@sha256:…`). Two other values name the same image and are easy to mistake for it:

| | what it is | where you meet it |
| --- | --- | --- |
| tag | the GIT SHA of the commit built (`<github.sha><suffix>`) — 40 hex chars, so it *looks* like a digest | what a registry UI displays |
| manifest digest | **what you pin** — `nas_capture_image` and the rendered `.env` | `docker pull` output, `RepoDigests` |
| image ID | the local config-blob digest | the `docker images` ID column |

`docker inspect <container>` reconciles them: `.Config.Image` is what compose asked for (the digest), `.Image` is the local ID, and inspecting that ID lists `RepoTags` + `RepoDigests`.

**A digest-pinned image showing `<none>` locally is NORMAL and never evidence of anything.** `docker image ls` prints `<none>` for *any* image pulled by digest, which is what a pinned deploy always does. Reading that as "untagged, therefore stale" once motivated a re-pin on a false premise.

### One-time bootstrap (hand-placed once; not Ansible-managed)

1. Place `zcrypto.toml` (the app config the `gate-export` step reads for its journal/store paths) under `/volume1/docker/zcrypto-archive/`.
2. Drop the `sync_capture` private key at `/volume1/docker/zcrypto-archive/keys/sync_capture`, mode `0600` (the vaulted keypair; the public half is installed on the VPS as a read-only `rrsync` forced-command channel for the capture segments).
3. Drop the `sync_journal` private key at `/volume1/docker/zcrypto-archive/keys/sync_journal`, mode `0600` — the engine journal's OWN least-privilege keypair (Role B), distinct from `sync_capture` so a leaked key exposes only one channel. The other pull channels' keys (`sync_capture_red`, `sync_liquidations`, `sync_panel`, `sync_reconciled`, `sync_hot`) follow the same pattern, one least-privilege keypair each.
4. Pre-seed the pinned VPS host key at `/volume1/docker/zcrypto-archive/keys/known_hosts`. DSM ships no `ssh-keyscan`, so run it from a machine that has one (e.g. the workstation): `ssh-keyscan -p 10022 <vps-host>` and copy its output to that path. Host-key checking is strict (`StrictHostKeyChecking=yes`), so an unseeded or stale file fails the pull closed.
5. Create the shared textfile-collector directory `/volume1/docker/zcrypto-archive/textfile`, owned `1000:1000` and `chmod 0775`:

   ```bash
   mkdir -p /volume1/docker/zcrypto-archive/textfile
   chown 1000:1000 /volume1/docker/zcrypto-archive/textfile
   chmod 0775 /volume1/docker/zcrypto-archive/textfile
   ```

   The explicit `chmod` matters: a Synology DSM ACL granting the host uid write access is **not** honored inside the container, which only sees the underlying POSIX mode — so real owner-writable bits (`0775`) are required, not just an ACL grant. `archive-pull` writes `gate.prom` there after each journal pull; Alloy also mounts it (read-only) for scraping.

6. Create the dedicated Alloy user **`zcrypto-dummy` (uid 1031, gid 1000 — the `zcrypto` group)** (DSM → Control Panel → User & Group, or `synouser --add`), then create Alloy's `--storage.path` dir owned by it and `chmod 0775` (see the Alloy section below for why this uid):

   ```bash
   mkdir -p /volume1/docker/zcrypto-archive/alloy-data
   chown 1031:1000 /volume1/docker/zcrypto-archive/alloy-data
   chmod 0775 /volume1/docker/zcrypto-archive/alloy-data
   ```

7. Create a new healthchecks.io check (e.g. named `zcrypto-gate-verify`) — a **new, dedicated** check, distinct from the engine's own `HEALTHCHECK_URL` — and vault its ping URL as `nas_gate_healthcheck_url` in `infra/ansible/host_vars/nas/vault.yml`; the role renders it into `.env` as `GATE_HEALTHCHECK_URL`. This is the **sole Alloy-independent paging path** for the gate (spec 00049): if Alloy or the whole Grafana pipeline is down, this dead-man still pages, so it is required, not optional.

## Env-var contract

The `.env` next to `compose.yaml` is **rendered in full by the `nas` role** (`roles/nas/templates/env.j2`): every "deploy-time `.env`" row below is set in `infra/ansible/host_vars/nas/vars.yml` (except `GATE_HEALTHCHECK_URL`, vaulted in `host_vars/nas/vault.yml`) — never hand-edited on the NAS. There is no hand-maintained "optional" row: overriding a variable the template does not render (e.g. `ARCHIVE_PULL_INTERVAL`) takes **both** a `vars.yml` entry **and** an `env.j2` line; a variable in neither simply takes its `compose.yaml`/entrypoint default. `CAPTURE_IMAGE` and `ALLOY_IMAGE` (the digest pins, `nas_capture_image` / `nas_alloy_image`) fill `compose.yaml`'s `${...:?}` placeholders, so compose refuses to start without them. The reconcile/backfill knobs that used to live here (`RECONCILE_TEXTFILE`, `RECONCILE_MIN_GAP_SECONDS`, `RECONCILE_WINDOW_HOURS`, `TRADE_BACKFILL_TEXTFILE`) left with the writer: OPS-5 (spec `00054`) moved the reconciler + trade-backfill steps to the ops node — the **live** knobs are `ops_reconcile_min_gap_seconds` / `ops_reconcile_window_hours` in `infra/ansible/roles/ops/defaults/main.yml`, which is where T0039's soak-derived `--min-gap-seconds` pin lands (setting a `RECONCILE_*` var in this `.env` is consumed by nothing).

| Variable | Meaning | Set where |
| -- | -- | -- |
| `CAPTURE_SOURCE` | rsync source spec for the capture segments, e.g. `zcrypto-data@<vps-host>:` (the `rrsync` forced command on the VPS pins the actual remote subtree, so the client-side path is effectively ignored). Served by the VPS `zcrypto-data` m2m user since the capture-host migration (spec 00057), off the admin user. | deploy-time `.env` |
| `CAPTURE_DEST` | Local archive path the segments land in. | defaults to `/archive/capture-segments` in `compose.yaml` |
| `JOURNAL_SOURCE` | rsync source spec for the engine journal, e.g. `zcrypto-data@<vps-host>:` (same `rrsync` forced-command pattern, the existing journal channel; served by `zcrypto-data` since the capture-host migration, spec 00057). | deploy-time `.env` |
| `JOURNAL_DEST` | Local archive path the journal lands in. | defaults to `/archive/engine-journal` in `compose.yaml` |
| `CAPTURE_SSH_KEY` | Private key path inside the container for the capture channel's rsync-over-ssh transport. Passed as `ARCHIVE_SSH_KEY` to `zcrypto archive pull` for the capture-segments call only (`cli/archive/command.py` reads a single `ARCHIVE_SSH_KEY` from the environment; the entrypoint scopes it per subprocess call). | fixed to `/keys/sync_capture` in `compose.yaml` (matches the `./keys:/keys:ro` mount) |
| `JOURNAL_SSH_KEY` | Private key path inside the container for the engine-journal channel's OWN least-privilege rsync-over-ssh transport, distinct from `CAPTURE_SSH_KEY` (bootstrap step 3). Passed as `ARCHIVE_SSH_KEY` for the journal-pull call only. | fixed to `/keys/sync_journal` in `compose.yaml` |
| `ARCHIVE_SSH_KNOWN_HOSTS` | `UserKnownHostsFile` path pinning the VPS host key. Host-key checking is strict (`StrictHostKeyChecking=yes`), so this file must be pre-seeded (bootstrap step 4) — an unseeded or stale key fails the pull closed. | fixed to `/keys/known_hosts` in `compose.yaml` |
| `CAPTURE_RED_SOURCE` | rsync source spec for the **redundant secondary's** capture segments, e.g. `zcrypto-data@zcrypto-red.zhaow.me:` (its own `rrsync -ro` forced command pins the remote subtree, same pattern as the primary; served by `zcrypto-data` since the capture-host migration, spec 00057). **Leave unset and the secondary pull is skipped entirely**, so this stack still runs on a NAS that has not been given the red channel — `.pull-status` then reports `secondary_ok=1` vacuously (the ops writer's gate consumes only the pulls this host actually runs; the reconcile step itself moved to the ops node, spec `00054`). | deploy-time `.env` |
| `CAPTURE_RED_DEST` | Where the secondary's raw mirror lands. Kept separate from the primary's on purpose: the reconciler needs the two mirrors as **independent witnesses**, and the raw primary is the T0003 exit bar's only input. | fixed to `/archive/capture-segments-red` in `compose.yaml` |
| `CAPTURE_RED_SSH_KEY` | Private key for the secondary's pull channel — a **separate** least-privilege keypair (`sync_capture_red`), never the primary's. | fixed to `/keys/sync_capture_red` in `compose.yaml` |
| `LIQUIDATIONS_SOURCE` | rsync source spec for the **ops node's** liquidations tree (spec 00051 OPS-2), e.g. `zcrypto-data@<ops-host>:` (its own `rrsync -ro` forced command pins the remote subtree — see `infra/ops/README.md` for the channel setup). The four ops-node channels (this + panel/reconciled/hot) are served by the ops node's dedicated `zcrypto-data` m2m user (spec 00057) — as are the capture and journal channels since the capture-host migration, so **every** pull channel now serves as `zcrypto-data@`, off the admin user (`zcrypto-deploy`). Liquidations are not backfillable, so this pull is the no-sole-custody replica. **Leave unset and the pull is skipped entirely**, so this stack still runs on a NAS that has not been given the ops channel. Hash-verified like the capture pulls (the recorder writes `.sha256` manifests). | deploy-time `.env` |
| `LIQUIDATIONS_DEST` | Where the liquidations mirror lands. | fixed to `/archive/liquidations` in `compose.yaml` |
| `LIQUIDATIONS_SSH_KEY` | Private key for the liquidations pull — a **separate** least-privilege keypair (`sync_liquidations`), never the capture or journal keys. | fixed to `/keys/sync_liquidations` in `compose.yaml` |
| `LIQUIDATIONS_SSH_PORT` | The ops node's SSH port, scoped to this pull only (passed as `ARCHIVE_SSH_PORT` per call, like the per-call keys). The ops node is a home-LAN box on port **22**, unlike the VPS channels' 10022. | defaults to `22` in `compose.yaml` |
| `PANEL_SOURCE` | rsync source spec for the **ops node's** L2 primitive panel tree (spec 00052 D7), e.g. `zcrypto-data@<ops-host>:` (its own `rrsync -ro` forced command pins the remote subtree — see `infra/ops/README.md` for the channel setup). Convenience-durability only — the panel is recomputable from raw, so this copy is not custody-critical. **Leave unset and the pull is skipped entirely**, so this stack still runs on a NAS that has not been given the panel channel. Hash-verified like the capture/liquidations pulls (the materializer writes `.sha256` manifests). | deploy-time `.env` |
| `PANEL_DEST` | Where the panel mirror lands. | fixed to `/archive/l2-panel` in `compose.yaml` |
| `PANEL_SSH_KEY` | Private key for the panel pull — a **separate** least-privilege keypair (`sync_panel`), never the capture/journal/liquidations keys. | fixed to `/keys/sync_panel` in `compose.yaml` |
| `PANEL_SSH_PORT` | The ops node's SSH port, scoped to this pull only (passed as `ARCHIVE_SSH_PORT` per call, like the per-call keys). The ops node is a home-LAN box on port **22**, unlike the VPS channels' 10022. | defaults to `22` in `compose.yaml` |
| `RECONCILED_SOURCE` | rsync source spec for the **ops node's** healed overlay tree (spec 00054 D4), e.g. `zcrypto-data@<ops-host>:` (its own `rrsync -ro` forced command pins the remote subtree — see `infra/ops/README.md` for the channel setup). The overlay writer (reconciler + trade-backfill) moved to the ops node, so this pull is how the NAS re-acquires custody of it. **Leave unset and the pull is skipped entirely**, so this stack still runs on a NAS that has not been given the channel — which is also the rollback path. Hash-verified like the capture/liquidations/panel pulls (every minted hour carries a `.sha256` sidecar). | deploy-time `.env` |
| `RECONCILED_SSH_KEY` | Private key for the reconciled-overlay pull — a **separate** least-privilege keypair (`sync_reconciled`), never the capture/journal/liquidations/panel keys. | fixed to `/keys/sync_reconciled` in `compose.yaml` |
| `RECONCILED_SSH_PORT` | The ops node's SSH port, scoped to this pull only (passed as `ARCHIVE_SSH_PORT` per call, like the per-call keys). The ops node is a home-LAN box on port **22**, unlike the VPS channels' 10022. | defaults to `22` in `compose.yaml` |
| `RECONCILED_DEST` | Where the healed-overlay mirror lands (the `RECONCILED_SOURCE` pull's destination — the overlay is *written* on the ops node since OPS-5, spec `00054` D2/D4; this host only re-acquires it into custody). Only **healed** hours arrive, plus the append-only ledger; readers resolve reconciled-first, primary-final otherwise (`cli/archive/reader.py`). | fixed to `/archive/capture-reconciled` in `compose.yaml` |
| `HOT_SOURCE` | rsync source spec for the **ops node's** hot-out outbox (spec 00056 D2/D4), e.g. `zcrypto-data@<ops-host>:` (its own `rrsync -ro` forced command pins the remote subtree — see `infra/ops/README.md` for the channel setup). Pulled into the `hot/` hub by a **raw `rsync --archive --ignore-existing`** (not `zcrypto archive pull`): hot sets are append-only-at-file (D1c) and carry `manifest.json`, not `.sha256` sidecars, so the pull is unverified-at-transport and append-only-by-construction. **Leave unset and the pull is skipped entirely.** | deploy-time `.env` |
| `HOT_DEST` | Where the hot-cluster working set lands — the `hot/` hub itself. | defaults to `/archive/hot` in `compose.yaml` (`/archive` == `/volume1/ZhaoCrypto`, so this is the hub dir the nas role creates) |
| `HOT_SSH_KEY` | Private key for the hot-out pull — a **separate** least-privilege keypair (`sync_hot`), never the other channels' keys. | fixed to `/keys/sync_hot` in `compose.yaml` |
| `HOT_SSH_PORT` | The ops node's SSH port, scoped to this pull only. Home-LAN port **22**, like the panel/reconciled channels. | defaults to `22` in `compose.yaml` |
| `ARCHIVE_SSH_PORT` | VPS SSH port; defaults to 10022 (matching the capture/engine channels) if omitted or blank. | deploy-time `.env` |
| `ARCHIVE_PULL_INTERVAL` | Seconds between pull cycles. | defaults to `3600` (hourly) in `compose.yaml`; not rendered by `env.j2` — changing the cadence takes a `vars.yml` entry **plus** an `env.j2` line (see the intro above) |
| `GATE_TEXTFILE` | Prometheus node-exporter textfile-collector path the `zcrypto engine gate-export` step (run after each journal pull) atomically writes the gate metrics to. | fixed to `/textfile/gate.prom` in `compose.yaml` (matches the textfile-dir mount, bootstrap step 5) |
| `GATE_HEALTHCHECK_URL` | Dead-man's-switch base URL for `gate-export`: GET on a clean gate, GET `<url>/fail` otherwise. **Required** — the sole Alloy-independent paging path (bootstrap step 7); a new, dedicated healthchecks.io check, distinct from the engine's own `HEALTHCHECK_URL`. | deploy-time `.env` (vaulted: `nas_gate_healthcheck_url`) |

## The `hot/` hub push channel (spec 00056 D2)

Every channel above is a **pull** — the NAS reaches out and the fleet stays pull-only into custody. The `hot/` hub is the **one exception**: the workstation *pushes* the replicated working set (`zcrypto data push`) into `/volume1/ZhaoCrypto/hot`, the only write path into custody. It never goes through the read-only NFS mount (a soft-mounted write can corrupt on a timeout); it is rsync-over-ssh, jailed by a vendored `rrsync` forced command:

- **Ansible-managed** by the `nas` role (not a bootstrap step): the role creates `hot/` (`zcrypto-data:zcrypto` `2775` setgid), deploys the vendored `rrsync` (rsync 3.4.1's python3 jailer — the NAS ships none; `infra/nas/rrsync`) to `nas_stack_dir`, and installs the workstation's `zcrypto_hot_push_ed25519.pub` in `zcrypto-data`'s `authorized_keys` as `command="<nas_stack_dir>/rrsync /volume1/ZhaoCrypto/hot",restrict` — write-capable (no `-ro`), root pinned to `hot/` (the inbound hot-push lands on the m2m data user, not admin `zcrypto-deploy`; spec 00057).
- **Containment (four layers), all holding against a stolen key running its own rsync client:** `restrict` (SSH-level — no port/agent/pty/X11 forwarding); the `command=""` path jail pins the command-line dest under `hot/`; `-munge` (rsync `--munge-links`) mangles incoming symlink targets so a pushed symlink cannot traverse *out* of `hot/` — the documented writable-rrsync escape; and `-no-del -no-overwrite` enforce the append-only contract **server-side** — strip every `--delete*`/`--remove*` and force `--ignore-existing` (which also neutralizes `--force`'s dir-replace delete, measured). So a stolen key can neither escape the pinned root nor delete/overwrite custody within it. (`-ro` is deliberately absent — it would forbid writes; it is also the only flag that implies `-no-del`, so both are named explicitly.) `hot/` itself is created **`2775` (setgid)** so both writers' subtrees inherit group `zcrypto` (the push writer's primary group is `users`).
- Both writers coexist under `hot/`: the workstation push authors its own set names (`ohlc-full`, …), the ops→NAS `HOT_SOURCE` pull brings ops-authored set names — disjoint subtrees in practice. The pull applies `--chmod=D2775,F0664` — **the one place the fleet's channels diverge**, because `D0775` forced every directory it wrote to exactly 0775 and stripped the setgid the role sets on `hot/`; the role restored it each converge and the next pull removed it again, invisibly. Siblings keep `D0775` correctly (single-writer, egid already `zcrypto`). The setgid keeps its trees group-writable AND makes children inherit group `zcrypto`, and `-no-overwrite`/`--ignore-existing` mean that even if the two ever share a set-name subtree, neither can clobber the other's files.

## Reading pull-lag + verify failures

`docker logs` on the container surfaces `zcrypto archive pull`'s own log lines (see
`cli/archive/command.py`):

- `pull complete source=... checked=N ok=N failed=N lag_s=...` — one line per pull, for the
  capture-segments source. `lag_s` is the pull-lag dead-man signal: the age (seconds) of the
  newest verified segment. A growing `lag_s` across cycles means the scheduler loop is stuck or
  the transport is failing — check for the `pull-entrypoint: ... pull failed` line right above it.
- `archive pull complete (no verify) source=... dest=...` — the engine-journal pull (run with
  `--no-verify`, see above); no hash-verify pass runs, so this line replaces the
  `pull complete ... checked=...` line for that source.
- `archive pull: verify failed path=...` (ERROR) — a pulled capture segment's hash mismatched its
  manifest; it is logged, not archived as good. Re-pull on the next cycle picks it up again.
- `archive pull: rsync failed source=... dest=... returncode=...` (ERROR) — a transport failure;
  the pull is never verified as authoritative. The loop logs
  `pull-entrypoint: capture pull failed ...` / `... journal pull failed ...` to stderr and
  continues to the next interval rather than exiting the container.

```bash
/usr/local/bin/docker compose -f compose.yaml logs -f archive-pull
```

## Correcting the reconcile ledger (T0044)

The reconcile counters (`zcrypto_reconcile_residual_gap_seconds_total`, `_healable_gap_seconds_total`, the hour/deficit counters) are **summed from the whole append-only** `reconcile-ledger.jsonl` on every cycle, so they are monotone as long as the ledger only ever grows. The one operation that breaks that is a **correction** — removing a record a classifier bug wrote (as on 2026-07-14, a false `total_loss`). A correction *decreases* a counter, Prometheus reads the decrease as a **reset**, and a bare `increase()` would report the whole post-reset value as fresh change. The two `increase()`-based alert rules (`Reconciler · residual gap increased`, `Reconciler · primary gap rate high`) are guarded with `and resets(...) == 0` precisely so a correction cannot false-page — so **expect both to go quiet for one window after a correction; that is the guard working, not a fault.**

The procedure (a deliberate, one-off exception to the ledger's append-only discipline) — run it on the **writer host's** copy (the ops node since spec `00054` moved the overlay writer there; a correction made only on the NAS's pulled copy is overwritten by the next `RECONCILED_SOURCE` pull):

```bash
L=/var/lib/zcrypto-ops/capture-reconciled/reconcile-ledger.jsonl
B=/var/lib/zcrypto-ops/ledger-corrections              # OUTSIDE the replicated tree — see the backup rules below
sudo mkdir -p "$B"
sudo cp "$L" "$B/reconcile-ledger.jsonl.bak-$(date -u +%Y%m%d-%H%M%S)"   # 1. back up VERBATIM (the audit trail of the bug)
# 2. filter by an EXACT-MATCH predicate, asserting the count you expect to drop:
sudo python3 - "$L" <<'PY'
import json, sys
L = sys.argv[1]
keep, dropped = [], []
for line in open(L):
    if not line.strip():
        continue
    r = json.loads(line)                               # raises on a malformed line -> never write a broken ledger
    is_bad = r.get("state") == "total_loss" and r.get("pair") == "LINK/EUR" and r.get("hour", "").startswith("2026-07-14T02")
    (dropped if is_bad else keep).append(r)
assert len(dropped) == 1, f"expected exactly 1 record, found {len(dropped)}"   # 3. STOP if it does not match
open("/tmp/ledger.new", "w").write("".join(json.dumps(r) + "\n" for r in keep))
print(f"dropped {len(dropped)}, kept {len(keep)}")
PY
sudo cp /tmp/ledger.new "$L" && sudo chown zcrypto-data:zcrypto-data "$L" && sudo chmod 0664 "$L" && sudo rm -f /tmp/ledger.new
# 4. drop the skip cache IN THE SAME ACT — its entries describe a ledger state that no longer exists:
sudo rm -f "$(dirname "$L")/scan-cache.json"
```

(`zcrypto-data:zcrypto-data` is the writer uid on the ops node since spec 00057; a NAS-side copy is `zcrypto-data:zcrypto` — the NAS user was renamed `zcrypto → zcrypto-data`, the group `zcrypto` kept.)

Rules: keep **one record per line** (`_load_ledger` raises `CaptureError` on a malformed line, which fails the next cycle loudly); never truncate to shrink the file (that resets every counter — see `infra/runbooks/ops.md#reconcile-ledger-scan-cost` for the compaction design that preserves the totals ([[T0044]], resolved, records why)); and confirm the two alert rules return to Normal within a window after the reset ages out.

**Any mutation of the ledger, or of the overlay tree, deletes `scan-cache.json` in the same act** (step 4 above) — this applies to a hand-removed minted parquet just as much as to a ledger edit. The cycle skips a settled hour whose fingerprint is unchanged, and while that fingerprint covers the overlay's own files, a ledger edit is invisible to it: leave the cache and the next cycle skips precisely the hours the correction meant to force a re-examination of. Nothing pages on that immediately — the sampled audit rotates two hours per cycle through the window's ~44 cacheable hours, twice an hour, so the divergence can sit for **~11 h** before it is caught and the whole cache is dropped. Deleting it makes the next cycle deliberately full instead; the cost is one slow cycle. Triage from the other end is [`zcrypto-reconcile-cycle-duration`](../runbooks/ops.md#zcrypto-reconcile-cycle-duration).

Backup rules ([[T0057]]):

- **The backup never goes inside `capture-reconciled/`.** The tree carries data + manifests + the ledger, plus exactly one sidecar the writer itself authors — `scan-cache.json`, spec `00097`'s settled-hour skip cache — and **nothing a hand ever puts there**. It is replicated into custody, so any extra file is copied to every consumer forever, and a single unreadable stray file fails the entire tree's rsync (exit 23). That is exactly what the 2026-07-14 correction's in-place `.bak` did to the ops→NAS channel on 2026-07-16: `sudo cp` left it root-owned and unreadable by the pull identity. The sidecar cannot repeat that, and for reasons worth stating rather than assuming: the reconcile cycle writes it with the same process and umask that appends the ledger beside it, so owner and mode match that file exactly; the pull is `rsync -a --chmod=D0775,F0664`, which forces 0664 on arrival regardless; and the tree's integrity walks enumerate `*.parquet` only (`verify_tree`, `prune_stale_parts`), so it is neither hashed as a missing final nor pruned as a stray part. A hand-placed file has none of those three properties, which is why this rule is about hands and not about file counts. Write the backup to a `ledger-corrections/` dir beside the stack/data dirs on the writer host (outside the rrsync-pinned overlay root), as in step 1 above.
- **Commit the correction's diff to the repo as the durable record** — the removed line(s) verbatim, the backup's hash/size/line count, and why — so the evidence outlives any on-host cleanup. Worked example: `ledger-correction-20260714-link-eur.md` beside this file.

## Alloy telemetry stack (spec 00049 Role B, Task 3)

One more service on the same `compose.yaml`, unrelated to `archive-pull`'s own deploy sequence above:
**Grafana Alloy**, shipping NAS host metrics (load, memory, free disk space, network IO), the Role B
gate metrics (the `gate.prom` textfile), and every container's logs to the already-provisioned
Grafana Cloud instance.

**Alloy no longer touches the Docker socket at all (00068 D6/T8).** It used to read the socket **directly**, behind a GET-only `docker-socket-proxy` (tecnativa) with `POST=0` as the boundary, removed on 2026-07-14 because it corrupted the logs it existed to carry — its HAProxy `timeout client/server 10m` severed Docker's long-lived `/containers/<id>/logs?follow=1` stream whenever a container went quiet, and Alloy's reconnect (inclusive `since=<second>`) re-ingested the last line each time, duplicating it every 10 minutes forever. The direct-socket read that replaced the proxy is itself now retired: `discovery.docker`/`loki.source.docker` are gone from `config.alloy`, the socket volume mount is deleted from `compose.yaml`, and both containers' logs instead reach Alloy through the host journal (`journald` logging driver on both services + `loki.source.journal` in `config.alloy` — see the compose file's own header comment for the full history). **T0042's docker-socket residual on this host CLOSES**: nothing here holds Docker API access any more. Alloy is still kept non-root (uid 1031); its one remaining `group_add` is DSM's `log` group (gid 19, measured 2026-07-22 — DSM ships no `systemd-journal` group, and the journal is `root:log`), which grants journal read only, confers **no** Docker API access, and so cannot reopen T0042. T0042 is resolved and archived (`docs/open-topics/archive/`).

**Container-level metrics (CPU/mem/fs per container) are NOT collected on this NAS.** `cadvisor`
SIGSEGVs on Synology DSM — a nil-pointer panic because DSM's kernel has no CPU cgroup hierarchy for
it to walk — and the panic takes down all of Alloy with it, so `prometheus.exporter.cadvisor` is
not run here at all. Only host metrics + the gate metrics + the container logs flow off this NAS.

See `docs/specs/00043-observability-design.md` for the design this is adapted from (the VPS
counterpart) and `infra/nas/config.alloy` for the Alloy pipeline itself — everything here runs
under Container Manager as plain compose services (deployed by the `nas` Ansible role, no systemd).

### Deploy

Part of the same `nas`-role converge as everything else (see **Deploy** above): the role copies `config.alloy` verbatim from this directory and renders `/volume1/docker/zcrypto-archive/alloy-secrets.env` (mode `0600`, never committed, `no_log`) straight from the vaulted `group_vars/observed/vault.yml` — the same six `GRAFANA_PROM_URL/USERNAME/PASSWORD` + `GRAFANA_LOKI_URL/USERNAME/PASSWORD` names the ops role renders, read by `config.alloy` via the River `sys.env(...)` stdlib function (`compose.yaml` itself stays secret-free and diffable — only `env_file: ./alloy-secrets.env` references the file by name). The Alloy image digest pin is `nas_alloy_image` in `host_vars/nas/vars.yml`, rendered into `.env` as `ALLOY_IMAGE`.

The one hand-made prerequisite is the `zcrypto-dummy` user + `alloy-data` dir (One-time bootstrap step 6 above). That dir holds the remote_write WAL and Loki log read-positions, which persist across a container replacement so a redeploy doesn't re-ship each source's retained backlog into the ingest quota. The compose file pins `user: "1031:1000"` (`zcrypto-dummy`) — **not** the image's built-in uid-473 `alloy` user, nor uid 1000. Rationale: (1) the upstream `grafana/alloy` image runs as `root` by default (its Dockerfile keeps `USER root`), and the `/:/host/root:ro` mount would then expose every 0600 host secret, so a non-root override is load-bearing; (2) uid 473 is not a Synology-recognized user, so the DSM ACL denies it write (`mkdir /var/lib/alloy/...: permission denied`) — a real DSM user is required, and the bootstrap's `chmod 0775` sets the actual POSIX mode the container honors (the DSM ACL granting host-uid write is **not** seen inside the container); and (3) uid 1031 is a **dedicated, non-secret-owning** user — it is **not** the owner of the `0600` rrsync pull keys (uid 1000 is), so a compromised Alloy cannot read them through `/host/root`. Note `zcrypto-dummy`'s gid 1000 IS the key-owning group, so this protection rests on the keys being `0600` — owner-only, group has no read — not on group isolation; keep the keys `0600`. (This closes [[T0030]]; verified live as 1031:1000: the key read is denied while metrics + logs still ship.)

### Resource budget

Diverges from the VPS design (`docs/specs/00043-observability-design.md`) here: the Synology DSM
kernel has no CPU CFS cgroup, so this stack sets **no `cpus:`/`cpu_shares:` limits** at all — a
`NanoCPUs` limit fails hard (`NanoCPUs can not be set ... cgroup is not mounted`) and blocks the
whole `compose up`. Only `memory` limits work (a separate, mounted cgroup): Alloy `memory: 512m`,
`GOMEMLIMIT=460MiB` (Go's GC overshoots a small cap under default behavior otherwise).
cadvisor is not run on the NAS at all (see above), which also
removes the one component that would have needed its own CPU budget. 32 GB NAS RAM makes the
memory ceiling arithmetic comfortable — these are caps, not reservations.

### Verification note

The NAS deploy shakedown ran this stack live on the actual Synology DSM host and surfaced several
DSM-specific incompatibilities, all now fixed in `compose.yaml`/`config.alloy` and reflected above:
cadvisor SIGSEGVs on DSM's cgroup-less kernel (removed entirely — see the container-metrics note
above), the alloy-data volume's DSM ACL rejects the image's built-in uid 473 (Alloy runs as the
dedicated non-secret-owning uid 1031 `zcrypto-dummy` — see the Alloy Deploy section above), and a
`cpus:`/`cpu_shares:` limit fails hard on DSM's CPU-cgroup-less kernel (removed — see Resource budget
above).

## Grafana dashboard + alerts (spec 00049 Role B, Task 4)

The committed-as-code dashboards (`infra/grafana/*-dashboard.json` — four boards since spec 00084 split the original) and alert rules
(`infra/grafana/alerts.yaml`) are provisioned onto the already-live Grafana Cloud instance by
`infra/scripts/grafana-push.sh` — run from any machine with network access to that instance (not
NAS-side; this is a one-off/on-change push, not a running service). Idempotent: re-run after any
commit to `infra/grafana/`.

### Deploy

1. Set these env vars (vault-sourced — the Grafana Cloud service-account token, same out-of-band
   distribution as the other vaulted secrets above):
   - `GRAFANA_URL` — the Grafana Cloud stack base URL, e.g. `https://<stack>.grafana.net`.
   - `GRAFANA_SA_TOKEN` — a Grafana service-account token with dashboards + alerting-provisioning
     write scope.
   - `GRAFANA_PROM_DS_UID` — the Prometheus datasource UID on the instance (alert-rule queries).
   - `GRAFANA_LOKI_DS_UID` — the Loki datasource UID on the instance (the ERROR-logs rule).
   - `GRAFANA_ALERT_FOLDER_UID` — the folder UID the alert rules provision into.
   - `GRAFANA_SLACK_WEBHOOK_URL` (T0047) — the Slack incoming-webhook URL, sourced from the
     vaulted `slack_webhook_url` in `infra/ansible/group_vars/all/vault.yml` — never committed
     plaintext. **Required on a from-scratch stack**: the script mints the as-code `metrics`/`logs`
     Slack receivers from it and ABORTS before the rules push if the webhook is unset while those
     receivers don't exist yet (a rule referencing a nonexistent receiver would notify nobody).
     Steady state (receivers already live): unset/empty just skips the Slack upserts.
   - `GRAFANA_SLACK_RECEIVER` — **removed 2026-07-16**: the receiver names are as-code constants
     now (`metrics`, resolve messages on; `logs`, resolve messages off), pinned per rule via
     `notification_settings.receiver` in `alerts.yaml`. No contact point is ever created by hand.
2. Run `infra/scripts/grafana-push.sh` with the env vars from step 1 exported. It pushes every
   `infra/grafana/*-dashboard.json` (overwriting by each file's own `uid`), upserts the
   `metrics`/`logs` Slack receivers (stable uids `zcrypto-slack-metrics`/`zcrypto-slack-logs`) and
   points the notification-policy default route at `metrics`, then upserts each alert rule (by its
   own stable `uid`) and read-back-verifies datasource UIDs (T0034). As one-time legacy cleanup it
   **deletes** the pre-2026-07-16 `zcrypto-slack-webhook` integration (the old `email`-named
   receiver) once no rule references it.
3. On first load of the dashboard, confirm (or set as the template-variable defaults) that its
   `${DS_PROMETHEUS}`/`${DS_LOKI}` datasource variables resolve to the correct Prometheus/Loki
   datasources — Grafana auto-binds these on import, but an instance with more than one datasource
   of either type needs the operator to confirm/select the right one.
