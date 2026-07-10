# VPS Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement spec `docs/specs/00042-vps-deployment-design.md`: the watchdog + fail-fast code additions, the `engine` ansible role with the §8 gate and secrets-safe delivery, the gate-ops tooling — then the attended deployment that starts the Stage-6a gate clock.

**Architecture:** Two subagent TDD tasks — (1) engine code additions, (2) infra (workflow, role, units) — then the orchestrator's attended deployment sequence. iter-083's engine contracts are consumed, never modified beyond the three specced additions.

**Tech Stack:** Python 3.14, existing `cli.engine`, ansible (existing roles as patterns), systemd, healthchecks.io API, docker compose.

## Global Constraints

- **Secrets discipline**: the trade key appears ONLY in `/opt/zcrypto-engine/engine.env` (rendered `0600 root:root`, task has `no_log: true` + `diff: false`); the compose file stays secret-free. Nothing in this plan prints key material.
- **Capture safety**: no capture file/unit/variable is touched; deployment = exact dry-run with both digests, then `--tags engine` only.
- **§8 gate asserts run before any secret render**, with `check_mode: false` on the read-only commands.
- Aware-UTC everywhere; `data/ohlc-full` read-only; ruff 132/double quotes; `uv run pre-commit run -a` gate; actual-model trailers + `Claude-Session`; subagent review + `Reviewed-by` before push.

______________________________________________________________________

### Task 1 (subagent, TDD): engine code additions

**Files:** Modify `cli/engine/cycle.py`, `cli/engine/command.py`, `cli/engine/node.py` (if the watchdog lives there), `README.md`; extend `tests/test_engine_cycle.py`, `tests/test_engine_command.py`, `tests/test_engine_node.py`.

1. **Dead-man's switch** (cycle.py): after the record/sidecar write in `run_cycle` — if env `HEALTHCHECK_URL` is set: GET the URL (success) or `<url>/fail` (sidecar), timeout ≤ 10 s, one attempt, `urllib` with an injectable opener module-global (`_hc_opener`), all exceptions swallowed via `logger.warning`. The propagating-exception path deliberately pings nothing (silence-alerts semantics — document in the docstring). Tests: success ping URL captured; sidecar pings `/fail`; env unset → opener never called; opener raises → CycleResult unaffected.
2. **Fail-fast `engine run`** (command.py): before `build_shadow_node` — (a) resolve config; if env `ZCRYPTO_REQUIRE_CONFIG` is set and `Path("zcrypto.toml")` does not exist → print a clear error, exit 1; (b) if `config.store_dir` is missing or contains no `*/EUR/*.parquet` → error, exit 1; (c) log the effective config one-liner (`engine run: exec_enabled=…, store_dir=…, journal_dir=…`). **Watchdog**: after `node.build()`, arrange a check that fires once `timeout_connection + timeout_reconciliation + 30 s` after `node.run()` starts (a `threading.Timer` reading `node.trader.is_running` is acceptable — the node blocks the main thread): not running → log CRITICAL and `os._exit(1)` (the systemd/compose restart is the recovery path). Timeouts read from the node config object (nautilus defaults ~60 s each — read them, don't hardcode). Tests: require-config exit; empty-store exit; effective-config line; watchdog force-exit with a mocked never-running trader (monkeypatch `os._exit` to record) and no-exit with a running one.
3. **`--journal-dir`** on `replay` and `report` (optional `Path`; overrides `config.journal_dir` when given). Tests: flag respected on both commands; default unchanged. **README**: document both flags in the engine Usage rows + the journal-pull one-liner and gate-ops timer install steps per the spec's Workstation-gate-ops section (mirroring the soak-unit walkthrough).

Run the three test files + full suite + pre-commit. Commit `feat(engine): dead-man's switch, fail-fast run, --journal-dir overrides`.

### Task 2 (subagent): infra — workflow, the engine role, gate-ops units

**Files:** Modify `.github/workflows/capture-image.yml` (paths: `cli/**`, `pyproject.toml`, `uv.lock`; a comment noting the image serves capture + engine), `infra/ansible/site.yml` (the engine role after capture, `tags: [engine]`). Create `infra/ansible/roles/engine/{defaults/main.yml,tasks/main.yml,templates/compose.yaml.j2,templates/zcrypto.toml.j2,templates/engine.env.j2,files/zcrypto-engine.service,handlers/main.yml}`, `infra/systemd/zcrypto-engine-gateops.service`, `infra/systemd/zcrypto-engine-gateops.timer`.

The role implements spec §role items 1–9 exactly, in order (the §8 gate first — the four asserts incl. `nft list ruleset` non-empty and `sshd -T` posture, `check_mode: false`; account in-role via `ansible.builtin.user` + `ansible_facts["getent_passwd"]` guarded for check mode; dirs; store copy `creates`-guarded; engine.env `0600` + `no_log`/`diff: false`; the toml template; compose with `env_file`, entrypoint override, `cpus "0.75"` / `memory 1g` / `cpu_shares: 512`, capture-style logging; the system unit mirroring capture's pull/up/down; the rrsync forced-command authorized_key entry for `deploy` (`key_options`, `exclusive: no`) + `deploy` into the `kraken-engine` group + `rsync` package present). Defaults: `engine_image` (same ghcr image), `engine_image_digest: ""` + assert, `engine_state_dir`, `engine_healthcheck_url: ""` (vault-supplied). Gate-ops units per spec (oneshot, `WorkingDirectory=<repo>` placeholder, `/bin/sh -c` chain with `date -u +%%F -d yesterday`, report-runs-after-failed-replay rc-capture, `OnCalendar=*-*-* 06:30:00 UTC`, header docs).

Verification (no live host): `uv run ansible-playbook --syntax-check infra/ansible/site.yml` (list the inventory implications — run from `infra/ansible/` per `ansible.cfg`), `uv run pre-commit run -a` (yamllint), and a `jinja2`-render smoke of the three templates with stub vars (a tiny python snippet in the task report, not committed). Commit `feat(infra): engine ansible role, image-workflow paths, gate-ops units`.

### Task 3 (orchestrator + human, attended): the deployment

- [ ] Measure/record the workstation node RSS (done: ~200 MB — 1g cap has 5× headroom).
- [ ] **Healthcheck**: create via `POST /api/v3/checks/` (vaulted `healthchecks_api_key`; `name=zcrypto-engine-shadow`, `timeout=14400`, `grace=2100`); vault the ping URL as `engine_healthcheck_url` (scripted vault append — decrypt in-process, never printed).
- [ ] **Image**: `gh workflow run capture-image.yml --ref feat/vps-deployment` (workflow_dispatch accepts any ref carrying the workflow file; the branch's image content equals post-merge develop, so one build serves both). Digest from the job summary.
- [ ] **Deploy**: `./scripts/run.sh site.yml --check --diff -e capture_image_digest=sha256:<current-from-host> -e engine_image_digest=sha256:<new>` → review (no capture drift) → `./scripts/run.sh site.yml --tags engine -e engine_image_digest=sha256:<new>` → unit active. Store copy timed away from a boundary+30 window.
- [ ] **First-start verification**: journalctl effective-config line (`exec_enabled=True`, volume paths), exec client connected + reconciled, no watchdog exit; egress IP matches the key allowlist.
- [ ] **First VPS cycle** at the next 4h boundary: journaled record, healthcheck's arming ping received (dashboard), manual workstation pull + `replay --journal-dir … --path verified` + `report --journal-dir …` — the gate clock's first tick, quoted in the history entry.
- [ ] **Gate-ops timer** installed on the workstation after the attended first pull.
- [ ] Closeout: T0018 sync (Done-so-far + trim to the 6b bullet + `ripe_when` refresh); the journal-retention topic registered (`ripe_when` disk-watermark, cross-linked to T0003); iterations-history entry incl. the first-cycle evidence; pre-commit; commit; **one PR** `feat(engine): iter-084 — the engine on the VPS (role, watchdog, gate ops)` carrying code + infra + deployment evidence (the branch-built image makes deploy-before-merge possible); merge on the human's go.
