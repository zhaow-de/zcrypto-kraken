# The engine on the VPS — deployment, watchdog, gate ops (design)

**Iteration:** iter-084 (attended — the deployment iteration; decisions log `[iter-084]`). **Goal:** the shadow engine runs 24/7 on the D2 VPS as a second compose service beside capture, with the §8-hardening gate honored before the trade key lands, the §10 dead-man's switch live, and the workstation equipped to run the pre-registered gate ops — **the Stage-6a gate clock starts at the VPS node's first journaled cycle** (deploy-now decided `[iter-084]` item 1).

## One image, two services

The existing `ghcr.io/zhaow-de/zcrypto-capture` image installs the whole `cli` package (`COPY cli/ cli/` + `uv sync --frozen --no-dev`) — the engine reuses it with a compose-level **entrypoint override** (`["zcrypto", "engine", "run"]`), bypassing the capture-specific shell ENTRYPOINT. Workflow change: `.github/workflows/capture-image.yml` path triggers extend from `cli/capture/**` to **`cli/**` + `pyproject.toml` + `uv.lock`** (any runtime-relevant change must rebuild — today's image predates `cli/engine`); the image/package name stays `zcrypto-capture` (renaming the ghcr package is churn; a comment notes it now serves both services). The first engine-capable image is built via `workflow_dispatch` during the attended deployment; both services deploy **by digest** (the capture role's pattern — the engine role takes `engine_image_digest`, asserted non-empty).

## Code additions (TDD, before any infra)

1. **The dead-man's switch** (`cli/engine/cycle.py`): at the end of `run_cycle` — both outcomes — if the `HEALTHCHECK_URL` env var is set, GET it (success record → the URL; failed-cycle sidecar → `<url>/fail`), with a short timeout, one attempt, and **any exception swallowed and logged** — a monitoring hiccup must never fail a cycle or delay the journal write (the ping happens *after* the record/sidecar lands). Injectable opener for tests (capture's `HEALTHCHECK_URL` idiom; stub-opener tests: success ping, /fail ping, unset → no call, opener exception → cycle result unaffected).
2. **`--journal-dir` overrides** on `zcrypto engine replay` and `report`: an optional path flag overriding `[zcrypto.engine].journal_dir` (flag → config, the repo convention) so the workstation verifies the **pulled VPS journal** without config edits. Tested via `CliRunner` (flag respected; default unchanged).

## The `engine` ansible role (mirrors `capture`; `site.yml` gains it after capture, tagged `engine`)

Ordered tasks:

1. **The §8-hardening gate — asserts before anything else**: nftables active (`systemctl is-active nftables`), fail2ban active, unattended-upgrades installed + enabled. Any failure aborts the role **before a single secret is rendered** — the spec-00039 decision-2 ordering, enforced not assumed. (The key's IP allowlist is already VPS-only since the iter-079 closure.)
2. `kraken-engine` system account (role-created, `nologin`, like the base role's `kraken-capture` pattern), uid/gid derived for the container's `user:` mapping.
3. Directories: `/var/lib/zcrypto-engine/{store,journal}` owned `kraken-engine`, `0750`.
4. **Store delivery**: copy the workstation's warm, QA'd store (7.7 MB — ansible runs *from* the workstation, so `ansible.builtin.copy` of `data/engine-store/` works) into `/var/lib/zcrypto-engine/store`, owner `kraken-engine`. The node's per-cycle `refresh_store` covers the hours since the copy (720-bar REST window ≫ the gap). Delivered **only when absent** (first deploy) — converges never clobber a live store.
5. **Rendered `zcrypto.toml`** (`/opt/zcrypto-engine/zcrypto.toml`, bind-mounted read-only at `/app/zcrypto.toml`): `[zcrypto.engine]` with `store_dir`/`journal_dir` → the volume paths, **`exec_enabled = true`** (reconciliation from day one — the iter-079-verified exec-client shape connects with the vaulted key), `shadow_nav_eur`/`settle_delay_secs` defaults stated explicitly.
6. **Rendered compose** (`/opt/zcrypto-engine/compose.yaml`): the image@digest, `entrypoint: ["zcrypto", "engine", "run"]`, `user:` the kraken-engine uid/gid, env `KRAKEN_SPOT_API_KEY`/`KRAKEN_SPOT_API_SECRET` (vault) + `HEALTHCHECK_URL` (vault, the new check), volumes (`/var/lib/zcrypto-engine` + the toml), resource limits (`cpus "1.0"`, `memory 1.5g`), capture-style json-file logging caps, `restart: unless-stopped`.
7. **systemd unit** `zcrypto-engine.service` (system, like capture's: `ExecStartPre` compose pull, `ExecStart` up, `ExecStop` down; enabled — boot resume).

**Capture safety (the L2-gap rule):** the role touches no capture file, unit, or variable; deployment runs a full-site **`--check --diff` dry-run first** (drift surfaced, nothing applied), then **`site.yml --tags engine`** only. The capture container is never restarted by this deployment.

## Workstation gate ops (the pre-registered policy, automated)

1. **Journal pull**: `rsync` over the existing pull-only sync key (`sync_ed25519`) from `VPS:/var/lib/zcrypto-engine/journal/` → workstation `data/engine-journal-vps/` (a documented one-liner in the README's engine section; the journal-relocation round-trip test already proved cross-root replays).
2. **A daily user timer** (`infra/systemd/zcrypto-engine-gateops.{service,timer}`, workstation): pull → `zcrypto engine replay --journal-dir data/engine-journal-vps --path verified --date <yesterday>` → `zcrypto engine report --journal-dir data/engine-journal-vps` — automating the pre-registered **≥ 1 verified-path replay per day** so policy compliance never depends on memory; output lands in the systemd journal.
3. The workstation soak **keeps running in parallel** until the 6a exit review (`[iter-084]` item 3) — two independent nodes journaling the same venue; divergence between their journals is itself evidence.

## The attended deployment sequence (closeout, in order)

1. **Healthcheck**: create the `zcrypto-engine-shadow` check via the healthchecks.io API (the vaulted `healthchecks_api_key`; period 4 h, grace 35 min — one ping per cycle), vault the ping URL as `engine_healthcheck_url` (`[iter-084]` item 2).
2. **Image**: `workflow_dispatch` the extended image workflow off the merged `develop`; capture the digest from the job summary.
3. **Deploy**: full-site `--check --diff` (drift review) → `./scripts/run.sh site.yml --tags engine -e engine_image_digest=sha256:<…>` → unit active.
4. **The first VPS cycle watched live** at the next 4h boundary (`journalctl` + the healthcheck ping + a journal pull): **the Stage-6a gate clock's first tick**, quoted in the history entry with its replay/report evidence.
5. **Gate-ops timer** installed on the workstation; first pull + verified replay + report run attended.
6. T0018 closeout sync (deployment done; the 6b executor becomes the sole remainder), iterations-history entry, PR into develop, merge on the human's go.

## Out of scope

Order submission, the order state machine, ops drills, tiny-live (the 6b executor iteration); any change to the gate semantics, the builder, or the journal schema; capture-stack changes beyond the workflow path-trigger extension; healthchecks provisioning as a *role task* (the check is created once, attended — the role only consumes the vaulted URL, capture's exact provenance).
