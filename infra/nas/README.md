# NAS archive-pull stack (spec 00048, Role A)

The always-on NAS pull/archive tier: the `archive-pull` container pulls the fleet's segment trees and the engine journal on a schedule and archives them under `/volume1/ZhaoCrypto`, decoupling data durability from the intermittently-online workstation (`docs/specs/00048-three-tier-topology-design.md`, Role A). The engine-journal pull runs `--no-verify`: its `.parquet` snapshots carry no `.sha256` sidecars, and their integrity is a JSON `snapshot_content_hash` verified later by Role B on replay.

Everything runs **inside the container** under Synology Container Manager: no systemd units, no DSM Task Scheduler entries, no NAS-OS config. `infra/nas/pull-entrypoint.sh` is the in-container scheduler — a loop that runs one pull per configured source every `ARCHIVE_PULL_INTERVAL` seconds and survives a single failed pull without exiting; Container Manager's `restart: unless-stopped` policy is what survives a NAS reboot.

## Deploy (Ansible — the `nas` role, T0056)

The NAS is Ansible-managed: the `nas` role (`infra/ansible/roles/nas`, play in `site.yml`) deploys `compose.yaml`, `pull-entrypoint.sh`, `config.alloy` and the vendored `rrsync` **verbatim from this directory** (the single source of truth — no copies live in the role) and renders the two env files next to them under `/volume1/docker/zcrypto-archive/`: `.env` (the image digest pins + pull sources, from `infra/ansible/host_vars/nas/vars.yml`; the vaulted `GATE_HEALTHCHECK_URL` from `host_vars/nas/vault.yml`) and `alloy-secrets.env` (the Grafana Cloud credentials, from `group_vars/observed/vault.yml`). **Never hand-copy a file onto the NAS** — the next converge overwrites it, and until then the deployed tree and this one disagree with nothing saying so.

```bash
cd infra/ansible
./scripts/converge.sh site.yml --limit nas --tags nas --check                     # preview only
./scripts/converge.sh site.yml --limit nas --tags nas                             # render-only: files land + a changed-files report, nothing restarts
./scripts/converge.sh site.yml --limit nas --tags nas -e nas_apply_compose=true   # render + apply EVERYTHING currently rendered
```

Without `-e nas_apply_compose=true` the converge is **render-only**: files land on the NAS and the play reports which ones changed, but nothing restarts. With the flag, the end-of-role apply tasks **run and apply everything currently rendered — not just what changed this run**: `compose up -d`, then an unconditional `archive-pull` restart (`pull-entrypoint.sh` is bind-mounted, so a content change never alters the compose service hash and `up -d` alone would leave the old loop running), then an Alloy restart, which is what applies the `config.alloy` the same converge redeployed. Restarting an already-current container costs a few seconds of downtime on best-effort loops, so the flag is idempotent-safe.

**The play's first act is a UTC clock guard and it fails closed**: `date +%z` must print `+0000`. `docker logs --since` parses its argument in the host's **local** time, so every log-window query against a non-UTC NAS is silently wrong; the refusal names the DSM setting that fixes it.

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
3. Drop the `sync_journal` private key at `/volume1/docker/zcrypto-archive/keys/sync_journal`, mode `0600` — the engine journal's OWN keypair (Role B), distinct from `sync_capture` so a leaked key exposes only one channel. Drop every other channel's key there the same way, one keypair each: `sync_capture_red`, `sync_liquidations`, `sync_panel`, `sync_reconciled`, `sync_hot`.
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

The `.env` next to `compose.yaml` is **rendered in full by the `nas` role** (`roles/nas/templates/env.j2`): every "deploy-time `.env`" row below is set in `infra/ansible/host_vars/nas/vars.yml` (except `GATE_HEALTHCHECK_URL`, vaulted in `host_vars/nas/vault.yml`) — never hand-edited on the NAS. There is no hand-maintained "optional" row: overriding a variable the template does not render (e.g. `ARCHIVE_PULL_INTERVAL`) takes **both** a `vars.yml` entry **and** an `env.j2` line; a variable in neither simply takes its `compose.yaml`/entrypoint default. `CAPTURE_IMAGE` and `ALLOY_IMAGE` (the digest pins, `nas_capture_image` / `nas_alloy_image`) fill `compose.yaml`'s `${...:?}` placeholders, so compose refuses to start without them. The `RECONCILE_*` and `TRADE_BACKFILL_*` knobs left with their writer when OPS-5 (spec `00054`) moved the reconciler and trade-backfill steps to the ops node — the live ones are `ops_reconcile_min_gap_seconds` / `ops_reconcile_window_hours` in `infra/ansible/roles/ops/defaults/main.yml`, and a `RECONCILE_*` var set in this `.env` is consumed by nothing.

Every pull channel shares one shape, so each row below says only what is particular to it:

- Its `*_SOURCE` is an rsync source spec `zcrypto-data@<host>:` — the m2m data user, never the admin `zcrypto-deploy` (spec 00057) — whose `rrsync -ro` forced command pins the remote subtree, so the client-side path is ignored. The ops-node channels (liquidations, panel, reconciled, hot) are set up in `infra/ops/README.md`.
- Its `*_SSH_KEY` is that channel's own least-privilege keypair under `keys/`, so a leaked key exposes one channel. `cli/archive/command.py` reads a single `ARCHIVE_SSH_KEY` from the environment and the entrypoint sets it per subprocess call, which is why each channel needs its own variable here. Every source's host key is pinned in the one shared `keys/known_hosts` (bootstrap step 4).
- Its `*_SSH_PORT` is scoped to that pull the same way: the ops node is a home-LAN box on port **22**, while the VPS channels take `ARCHIVE_SSH_PORT`, 10022.
- It is hash-verified against the source's `.sha256` sidecars — except the engine-journal pull (`--no-verify`) and the `hot/` pull (a raw rsync), each named in its row.
- Leaving its `*_SOURCE` unset skips that pull entirely, so this stack runs on a NAS that has not been given the channel. The primary capture pull is the exception: it is unconditional.

| Variable | Meaning | Set where |
| -- | -- | -- |
| `CAPTURE_SOURCE` | The capture segments on the VPS. The one unconditional pull. | deploy-time `.env` |
| `CAPTURE_DEST` | Local archive path the segments land in. | defaults to `/archive/capture-segments` in `compose.yaml` |
| `JOURNAL_SOURCE` | The engine journal on the VPS. | deploy-time `.env` |
| `JOURNAL_DEST` | Local archive path the journal lands in. | defaults to `/archive/engine-journal` in `compose.yaml` |
| `CAPTURE_SSH_KEY` | The capture channel's key. | fixed to `/keys/sync_capture` in `compose.yaml` (the `./keys:/keys:ro` mount) |
| `JOURNAL_SSH_KEY` | The engine-journal channel's key (bootstrap step 3). | fixed to `/keys/sync_journal` in `compose.yaml` |
| `ARCHIVE_SSH_KNOWN_HOSTS` | `UserKnownHostsFile`; `StrictHostKeyChecking=yes`, so an unseeded or stale entry fails the pull closed. | fixed to `/keys/known_hosts` in `compose.yaml` |
| `CAPTURE_RED_SOURCE` | The **redundant secondary's** capture segments. Unset, `.pull-status` reports `secondary_ok=1` vacuously. | deploy-time `.env` |
| `CAPTURE_RED_DEST` | Where the secondary's raw mirror lands — never mixed with the primary's, the reconciler's independent witness. | defaults to `/archive/capture-segments-red` in `compose.yaml` |
| `CAPTURE_RED_SSH_KEY` | The secondary channel's key. | fixed to `/keys/sync_capture_red` in `compose.yaml` |
| `LIQUIDATIONS_SOURCE` | The **ops node's** liquidations tree (spec 00051 OPS-2). Not backfillable, so this pull is the no-sole-custody replica. | deploy-time `.env` |
| `LIQUIDATIONS_DEST` | Where the liquidations mirror lands. | defaults to `/archive/liquidations` in `compose.yaml` |
| `LIQUIDATIONS_SSH_KEY` | The liquidations channel's key. | fixed to `/keys/sync_liquidations` in `compose.yaml` |
| `LIQUIDATIONS_SSH_PORT` | The ops node's port for this pull. | defaults to `22` in `compose.yaml` |
| `PANEL_SOURCE` | The **ops node's** L2 primitive panel tree (spec 00052 D7). Convenience durability only: recomputable from raw, so not custody-critical. | deploy-time `.env` |
| `PANEL_DEST` | Where the panel mirror lands. | defaults to `/archive/l2-panel` in `compose.yaml` |
| `PANEL_SSH_KEY` | The panel channel's key. | fixed to `/keys/sync_panel` in `compose.yaml` |
| `PANEL_SSH_PORT` | The ops node's port for this pull. | defaults to `22` in `compose.yaml` |
| `RECONCILED_SOURCE` | The **ops node's** healed overlay tree (spec 00054 D4). Its writer moved there, so this pull is how custody re-acquires it; unset is the rollback path. | deploy-time `.env` |
| `RECONCILED_SSH_KEY` | The reconciled-overlay channel's key. | fixed to `/keys/sync_reconciled` in `compose.yaml` |
| `RECONCILED_SSH_PORT` | The ops node's port for this pull. | defaults to `22` in `compose.yaml` |
| `RECONCILED_DEST` | Where the healed-overlay mirror lands — only **healed** hours, plus the append-only ledger. | defaults to `/archive/capture-reconciled` in `compose.yaml` |
| `HOT_SOURCE` | The **ops node's** hot-out outbox (spec 00056 D2/D4), pulled by a raw `rsync --archive --ignore-existing` rather than `zcrypto archive pull`: hot sets carry `manifest.json`, not sidecars. | deploy-time `.env` |
| `HOT_DEST` | Where the hot-cluster working set lands — the `hot/` hub itself (`/archive` == `/volume1/ZhaoCrypto`). | defaults to `/archive/hot` in `compose.yaml` |
| `HOT_SSH_KEY` | Private key for the hot-out pull — a **separate** least-privilege keypair (`sync_hot`), never the other channels' keys. | fixed to `/keys/sync_hot` in `compose.yaml` |
| `HOT_SSH_PORT` | The ops node's SSH port, scoped to this pull only. Home-LAN port **22**, like the panel/reconciled channels. | defaults to `22` in `compose.yaml` |
| `ARCHIVE_SSH_PORT` | VPS SSH port; defaults to 10022 (matching the capture/engine channels) if omitted or blank. | deploy-time `.env` |
| `ARCHIVE_PULL_INTERVAL` | Seconds between pull cycles. | defaults to `3600` (hourly) in `compose.yaml`; not rendered by `env.j2` |
| `GATE_TEXTFILE` | Where `zcrypto engine gate-export`, run after each journal pull, atomically writes the gate metrics. | fixed to `/textfile/gate.prom` in `compose.yaml` (bootstrap step 5) |
| `GATE_HEALTHCHECK_URL` | The gate's dead-man ping URL — **required**, the sole Alloy-independent paging path (bootstrap step 7). | deploy-time `.env` (vaulted: `nas_gate_healthcheck_url`) |
| `ARCHIVE_PULL_HASH_SCOPE` | `full` re-hashes every segment against its sidecar each cycle; `incremental` only rsync's transfers plus a rotating 1/24 slice (spec 00102 D7). | deploy-time `.env` |

## The `hot/` hub push channel (spec 00056 D2)

Every channel above is a **pull** — the NAS reaches out and the fleet stays pull-only into custody. The `hot/` hub is the **one exception**: the workstation *pushes* the replicated working set (`zcrypto data push`) into `/volume1/ZhaoCrypto/hot`, the only write path into custody. It never goes through the NFS mount (a soft-mounted write can corrupt on a timeout); it is rsync-over-ssh, jailed by a vendored `rrsync` forced command:

- **Ansible-managed** by the `nas` role (not a bootstrap step): the role creates `hot/` (`zcrypto-data:zcrypto` `2775` setgid), deploys the vendored `rrsync` (rsync 3.4.1's python3 jailer — the NAS ships none; `infra/nas/rrsync`) to `nas_stack_dir`, and installs the workstation's `zcrypto_hot_push_ed25519.pub` in `zcrypto-data`'s `authorized_keys` as `command="<nas_stack_dir>/rrsync -munge -no-del -no-overwrite /volume1/ZhaoCrypto/hot",restrict` — write-capable (no `-ro`), root pinned to `hot/` (the inbound hot-push lands on the m2m data user, not admin `zcrypto-deploy`; spec 00057).
- **Containment (four layers), all holding against a stolen key running its own rsync client:** `restrict` (SSH-level — no port/agent/pty/X11 forwarding); the `command=""` path jail pins the command-line dest under `hot/`; `-munge` (rsync `--munge-links`) mangles incoming symlink targets so a pushed symlink cannot traverse *out* of `hot/` — the documented writable-rrsync escape; and `-no-del -no-overwrite` enforce the append-only contract **server-side**, stripping every `--delete*`/`--remove*` and forcing `--ignore-existing` (which also neutralizes `--force`'s dir-replace delete). So a stolen key can neither escape the pinned root nor delete or overwrite custody within it. (`-ro` is deliberately absent — it would forbid writes; it is also the only flag that implies `-no-del`, so both are named explicitly.)
- Both writers coexist under `hot/`: the workstation push authors its own set names (`ohlc-full`, …), the ops→NAS `HOT_SOURCE` pull brings ops-authored set names — disjoint subtrees in practice. The pull applies `--chmod=D2775,F0664` — **the one place the fleet's channels diverge** — because `D0775` forces every directory it writes to exactly 0775 and would strip the setgid the role sets on `hot/`; siblings keep `D0775` correctly (single-writer, egid already `zcrypto`). The setgid keeps these trees group-writable AND makes children inherit group `zcrypto`, and `-no-overwrite`/`--ignore-existing` mean that even if the two ever share a set-name subtree, neither can clobber the other's files.

## Reading the pull loop's logs

`docker logs` on the container surfaces `zcrypto archive pull`'s own lines (`cli/archive/command.py`) and the entrypoint's wrapper lines. `infra/runbooks/nas.md` tables every ERROR line with its producer and its meaning, and is the triage path; the one figure it does not define:

- `pull complete source=… checked=N … failed=N lag_s=…` — one line per verified pull. `lag_s` is the pull-lag dead-man signal: the age in seconds of the newest segment the walk FOUND, verified or not — `verify_tree` takes `newest_ts` from the hour path during the traversal, not from the hash, so a narrowed `--hash-scope` never blanks it. A growing `lag_s` across cycles means the loop is stuck or the transport is failing.

```bash
sudo /usr/local/bin/docker logs --since 2h zcrypto-archive-pull
```

## Correcting the reconcile ledger (T0044)

The reconcile counters (`zcrypto_reconcile_residual_gap_seconds_total`, `_healable_gap_seconds_total`, the hour/deficit counters) are **summed from the whole append-only** `reconcile-ledger.jsonl` on every cycle, so they are monotone only as long as the ledger grows. A **correction** — removing a record a classifier bug wrote — decreases one; Prometheus reads the decrease as a **reset**, and a bare `increase()` would report the whole post-reset value as fresh change. Both `increase()`-based rules (`Reconciler · residual gap increased (permanent loss)`, `Reconciler · primary gap rate high (degrading host)`) carry `and resets(...) == 0` precisely so a correction cannot false-page — so **expect both to go quiet for one 24 h window after a correction; that is the guard working, not a fault.**

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

(`zcrypto-data:zcrypto-data` is the writer's uid:gid on the ops node; a NAS-side copy is `zcrypto-data:zcrypto`.)

Rules: keep **one record per line** (`_load_ledger` raises `CaptureError` on a malformed one, failing the next cycle loudly); never truncate to shrink the file — that resets every counter, and `infra/runbooks/ops.md#reconcile-ledger-scan-cost` carries the compaction design that preserves the totals instead ([[T0044]] recorded why); and confirm both rules return to Normal once the reset ages out of the window.

**Any mutation of the ledger, or of the overlay tree, deletes `scan-cache.json` in the same act** (step 4 above) — a hand-removed minted parquet as much as a ledger edit. The cycle skips a settled hour whose fingerprint is unchanged; that fingerprint covers the overlay's own files, but a ledger edit moves nothing it can see, so leaving the cache makes the next cycle skip precisely the hours the correction meant to force a re-examination of. The sampled audit would take **~11 h** to catch it — two hours per cycle, twice an hour, across the window's ~44 cacheable hours — and nothing pages meanwhile. Deleting the cache makes the next cycle deliberately full instead; the cost is one slow cycle. Triage from the other end is [`zcrypto-reconcile-cycle-duration`](../runbooks/ops.md#zcrypto-reconcile-cycle-duration).

Backup rules ([[T0057]]):

- **The backup never goes inside `capture-reconciled/`.** The tree carries data, manifests and the ledger, plus exactly one sidecar the writer itself authors — `scan-cache.json`, spec `00097`'s settled-hour skip cache — and **nothing a hand ever puts there**: it is replicated into custody, so any extra file is copied to every consumer forever, and a single unreadable stray file fails the entire tree's rsync (exit 23) — which is what a `sudo cp` backup left root-owned inside the tree once did to the ops→NAS channel. The sidecar cannot repeat that, for three reasons worth stating rather than assuming: the reconcile cycle writes it with the same process and umask that appends the ledger beside it, so owner and mode match that file exactly; the pull is `rsync -a --chmod=D0775,F0664`, which forces 0664 on arrival regardless; and the tree's integrity walks enumerate `*.parquet` only (`verify_tree`, `prune_stale_parts`), so it is neither hashed as a missing final nor pruned as a stray part. A hand-placed file has none of the three, which is why this rule is about hands and not about file counts. Write the backup to a `ledger-corrections/` dir beside the stack/data dirs on the writer host, outside the rrsync-pinned overlay root, as in step 1 above.
- **Commit the correction's diff to the repo as the durable record** — the removed line(s) verbatim, the backup's hash/size/line count, and why — so the evidence outlives any on-host cleanup. Worked example: `ledger-correction-20260714-link-eur.md` beside this file.

## Alloy telemetry stack (spec 00049 Role B, Task 3)

One more service on the same `compose.yaml`, unrelated to `archive-pull`'s own deploy sequence above: **Grafana Alloy**, shipping NAS host metrics (load, memory, free disk space, network IO), the Role B gate metrics (the `gate.prom` textfile), and both containers' logs to the already-provisioned Grafana Cloud instance.

**Alloy holds no Docker API access on this host, and nothing here may reintroduce it (00068 D6/T8).** `discovery.docker`/`loki.source.docker` are gone from `config.alloy` and the socket mount is gone from `compose.yaml`; both containers log through the `journald` driver and Alloy reads the host journal (`loki.source.journal`). Alloy is kept non-root (uid 1031) and its one remaining `group_add` is DSM's `log` group (gid 19 — DSM ships no `systemd-journal` group, and the journal is `root:log`), which grants journal read only and confers no Docker API access. That is what keeps [[T0042]] — resolved and archived, with the socket-proxy history that closed it — from reopening: a Docker-socket read, direct or behind a proxy, is what would.

**Container-level metrics (CPU/mem/fs per container) are NOT collected on this NAS.** `cadvisor` SIGSEGVs on Synology DSM — a nil-pointer panic because DSM's kernel has no CPU cgroup hierarchy for it to walk — and the panic takes down all of Alloy, so `prometheus.exporter.cadvisor` is not run here at all. Host metrics + the gate metrics + the container logs are what flow off this NAS.

See `docs/specs/00043-observability-design.md` for the VPS design this is adapted from, and `infra/nas/config.alloy` for the Alloy pipeline itself — everything here runs under Container Manager as plain compose services (deployed by the `nas` Ansible role, no systemd).

### Deploy

Part of the same `nas`-role converge as everything else (see **Deploy** above): the role copies `config.alloy` verbatim from this directory and renders `/volume1/docker/zcrypto-archive/alloy-secrets.env` (mode `0600`, never committed, `no_log`) straight from the vaulted `group_vars/observed/vault.yml` — the same six `GRAFANA_PROM_URL/USERNAME/PASSWORD` + `GRAFANA_LOKI_URL/USERNAME/PASSWORD` names the ops role renders, read by `config.alloy` via the River `sys.env(...)` stdlib function (`compose.yaml` itself stays secret-free and diffable — only `env_file: ./alloy-secrets.env` references the file by name). The Alloy image digest pin is `nas_alloy_image` in `host_vars/nas/vars.yml`, rendered into `.env` as `ALLOY_IMAGE`.

The one hand-made prerequisite is the `zcrypto-dummy` user + `alloy-data` dir (One-time bootstrap step 6 above). That dir holds the remote_write WAL and Loki log read-positions, which persist across a container replacement so a redeploy doesn't re-ship each source's retained backlog into the ingest quota. `compose.yaml` pins `user: "1031:1000"` — **not** the image's built-in uid-473 `alloy` user, nor uid 1000 — and its comment on that line carries why each of those two fails. The part that binds an operator: uid 1031 is a dedicated, non-secret-owning user that does **not** own the `0600` rrsync pull keys, but `zcrypto-dummy`'s gid 1000 IS the key-owning group, so the protection rests on those keys staying `0600` — owner-only, group no read — and not on group isolation. Keep the keys `0600`. ([[T0030]] closed on this uid.)

### Resource budget

Diverges from the VPS design (`docs/specs/00043-observability-design.md`) here: the Synology DSM
kernel has no CPU CFS cgroup, so this stack sets **no `cpus:`/`cpu_shares:` limits** at all — a
`NanoCPUs` limit fails hard (`NanoCPUs can not be set ... cgroup is not mounted`) and blocks the
whole `compose up`. Only `memory` limits work (a separate, mounted cgroup): Alloy `memory: 512m`,
`GOMEMLIMIT=460MiB` (Go's GC overshoots a small cap under default behavior otherwise). These are
caps, not reservations.

## Grafana dashboard + alerts (spec 00049 Role B, Task 4)

The committed-as-code dashboards (`infra/grafana/*-dashboard.json`), notification templates and alert rules (`infra/grafana/alerts.yaml`) are provisioned onto the already-live Grafana Cloud instance by `infra/scripts/grafana-push.sh` — from any machine with network access to that instance (nothing runs NAS-side), and **from merged `develop`, never a branch**: alert summaries and panel descriptions cite repo paths, so a branch push ships text naming files `develop` does not have. Idempotent: each dashboard overwrites by its own uid, each alert rule upserts by its own stable uid.

### Deploy

1. Export `GRAFANA_SA_TOKEN` — the one variable the script has no default for. Take it from `grafana_auth.py`'s `vault_var("grafana_sa_token")` by command substitution, never into a file, a log or argv; the script's own header carries the rest of the contract, including the PATH/venv requirement its PyYAML refusal points at.
2. Export `GRAFANA_SLACK_WEBHOOK_URL` (from the vaulted `slack_webhook_url` in `infra/ansible/group_vars/all/vault.yml`, never committed plaintext) — **required on a from-scratch stack**: the script mints the as-code `metrics` and `logs` Slack receivers from it and ABORTS before the rules push if it is unset while those receivers do not exist yet, since a rule referencing a nonexistent receiver would notify nobody. Steady state, unset just skips the Slack upserts. No contact point is ever created by hand.
3. Run `infra/scripts/grafana-push.sh` with those exported.
4. On first load of a dashboard, confirm (or set as the template-variable defaults) that its `${DS_PROMETHEUS}`/`${DS_LOKI}` datasource variables resolve to the correct Prometheus/Loki datasources — Grafana auto-binds these on import, but an instance with more than one datasource of either type needs the operator to confirm/select the right one.
