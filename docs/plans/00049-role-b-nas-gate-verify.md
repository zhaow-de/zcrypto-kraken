# Role B — NAS gate-verify + telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Stage-6a gate scoring onto the always-on NAS and ship NAS host/container/gate telemetry to the single Grafana dashboard (spec `docs/specs/00049-role-b-nas-gate-verify-design.md`, Increment 2 of the three-tier topology).

**Architecture:** A new `zcrypto engine gate-export` batch command runs after each journal pull on the NAS `archive-pull` container, writing a Prometheus textfile + pinging an independent healthchecks.io dead-man. A new NAS Alloy + docker-socket-proxy compose stack scrapes host/container metrics + the gate textfile + container logs and `remote_write`s to Grafana Cloud, surfaced on the one canonical dashboard. The workstation gate-ops timer is retired.

**Tech Stack:** Python 3.14 (Typer CLI, `urllib`), POSIX sh (in-container scheduler), Grafana Alloy (HCL config), docker compose (Container Manager), Grafana dashboard/alert JSON+YAML.

## Global Constraints

- NAS deployment is **`docker compose` under Container Manager only** — no systemd, no DSM Task Scheduler, no NAS-OS config.
- The NAS runs the **`-compat`** (no-AVX) image variant.
- Gate scoring is on the **fast path**, strict **`0.00e+00`** bar (the verified deep-check is out of scope on the NAS — measured too slow + inherently ~`1e-18`-noisy same-runtime).
- The capture and journal rrsync channels use **distinct least-privilege keys** (`/keys/sync_capture`, `/keys/sync_journal`).
- One canonical Grafana dashboard `infra/grafana/zcrypto-dashboard.json` — no separate NAS dashboard; namespace NAS rows so T0020 slots VPS rows into the same file.
- Independent failure domain: keep the healthchecks.io dead-man alongside Alloy.
- Every Claude-authored commit is reviewed by a subagent before push (`.claude/rules/commit-messages.md`); `uv run pre-commit run -a` is the commit gate.
- README `## Usage` updated in the same change as any CLI change (`.claude/rules/readme-usage.md`).

---

### Task 1: `zcrypto engine gate-export` (+ shared `_evaluate_journal` refactor)

**Files:**
- Modify: `cli/engine/command.py` (extract `_evaluate_journal`; refactor `report` to use it; add `gate-export`)
- Modify: `README.md` (`## Usage` — document `zcrypto engine gate-export`)
- Test: `tests/test_engine_gate_export.py` (new); adjust `tests/test_engine_report.py` if the refactor moves internals (keep report's behavior identical)

**Interfaces:**
- Consumes (already in `cli/engine/command.py` / `cli/engine/concordance.py`): `_load_engine_config()`, `_snapshot_reader`, `_journal_artifacts`, `_sidecar_fields`, `from_json`, `replay_cycle`, `compare_targets`, `evaluate_gate`, `CycleOutcome`, `HashMismatchError`, `EngineJournalError`, `EngineError`, `_utc_now`.
- Produces:
  - `_evaluate_journal(journal_root: Path) -> tuple[list[CycleOutcome], JournalCounts, datetime | None]` where `JournalCounts` is a small frozen dataclass `(replayed_ok, mismatches, validation_failures, sidecar_count)` and the third element is the newest cycle timestamp seen (`None` if the journal is empty). This is exactly `report`'s current loop, lifted verbatim (fast path).
  - `zcrypto engine gate-export` command.

**Behavior of `gate-export`:** load config → resolve journal root (`--journal-dir` else `config.journal_dir`) → `entries, counts, newest_ts = _evaluate_journal(root)` → `status = evaluate_gate(entries, now=_utc_now())` → compute `lag = (now - newest_ts).total_seconds()` (or `None`) and `mismatch_total = counts.mismatches + counts.validation_failures` → **atomically** write the `.prom` textfile → ping the healthcheck (clean = `mismatch_total == 0 and lag is not None and lag <= lag_fail_seconds`). Exit `0` on emit success (a gate mismatch is a *finding*, still exit 0); a non-writable textfile or unreadable journal raises → non-zero.

- [ ] **Step 1: Write failing tests** — `tests/test_engine_gate_export.py`. Reuse the existing journal-fixture builders used by the replay/report tests (find them in `tests/` — the same helpers that seed `cycle-*.json` + `snapshots/`). Cover:

```python
# Sketch — adapt fixture construction to the repo's existing journal-fixture helper.
from pathlib import Path
from cli.engine import command

def _prom(text: str) -> dict[str, float]:
    return {ln.split()[0]: float(ln.split()[1]) for ln in text.splitlines() if ln and not ln.startswith("#")}

def test_gate_export_clean_writes_all_series(tmp_path, monkeypatch, clean_journal):  # clean_journal = fixture dir
    out = tmp_path / "gate.prom"
    pings = []
    monkeypatch.setattr(command, "_gate_ping", lambda url, success: pings.append((url, success)))
    res = CliRunner().invoke(app, ["engine", "gate-export", "--journal-dir", str(clean_journal),
                                    "--textfile", str(out), "--healthcheck-url", "http://hc"])
    assert res.exit_code == 0
    m = _prom(out.read_text())
    assert m["zcrypto_gate_mismatch_total"] == 0
    assert "zcrypto_gate_streak_days" in m and "zcrypto_gate_status" in m
    assert "zcrypto_gate_journal_pull_lag_seconds" in m
    assert pings == [("http://hc", True)]

def test_gate_export_mismatch_pings_fail_and_counts(tmp_path, monkeypatch, mismatch_journal):
    out = tmp_path / "gate.prom"; pings = []
    monkeypatch.setattr(command, "_gate_ping", lambda url, success: pings.append((url, success)))
    res = CliRunner().invoke(app, ["engine", "gate-export", "--journal-dir", str(mismatch_journal),
                                    "--textfile", str(out), "--healthcheck-url", "http://hc"])
    assert res.exit_code == 0                       # emit succeeded; mismatch is a finding
    assert _prom(out.read_text())["zcrypto_gate_mismatch_total"] >= 1
    assert pings == [("http://hc", False)]

def test_gate_export_stale_journal_pings_fail(tmp_path, monkeypatch, clean_journal):
    out = tmp_path / "gate.prom"; pings = []
    monkeypatch.setattr(command, "_gate_ping", lambda url, success: pings.append((url, success)))
    # lag-fail below the fixture's age -> stale
    res = CliRunner().invoke(app, ["engine", "gate-export", "--journal-dir", str(clean_journal),
                                    "--textfile", str(out), "--healthcheck-url", "http://hc", "--lag-fail-seconds", "1"])
    assert res.exit_code == 0
    assert pings == [("http://hc", False)]

def test_gate_export_atomic_no_partial_on_write_error(tmp_path, monkeypatch, clean_journal):
    # point --textfile at a path whose parent is unwritable -> non-zero, no partial file
    bad = tmp_path / "nope" / "gate.prom"
    res = CliRunner().invoke(app, ["engine", "gate-export", "--journal-dir", str(clean_journal), "--textfile", str(bad)])
    assert res.exit_code != 0
    assert not bad.exists()

def test_report_output_unchanged_after_refactor(clean_journal):
    res = CliRunner().invoke(app, ["engine", "report", "--journal-dir", str(clean_journal)])
    assert res.exit_code == 0
    assert "streak:" in res.stdout and "gate (>= 14 clean days):" in res.stdout
```

- [ ] **Step 2: Run tests, verify they fail** — `uv run pytest tests/test_engine_gate_export.py -v` → FAIL (no `gate-export`, no `_gate_ping`).

- [ ] **Step 3: Implement.** In `cli/engine/command.py`:
  1. Add a frozen `JournalCounts` dataclass `(replayed_ok, mismatches, validation_failures, sidecar_count)`.
  2. Extract `_evaluate_journal(journal_root)` — lift `report`'s current loop verbatim (the `for boundary, record_path in _journal_artifacts(...)` block building `entries` + counts + the sidecar loop), and track `newest_ts = max(cycle_ts seen)`. Return `(entries, JournalCounts(...), newest_ts)`.
  3. Refactor `report` to call `_evaluate_journal` then keep its existing `typer.echo` lines (behavior identical).
  4. Add `_gate_ping(url: str, success: bool) -> None` (mirror `cli/engine/cycle.py:_ping_healthcheck`: GET `url` on success, `url + "/fail"` on failure; module-level `urlopen` alias so tests stub it; swallow+log network errors — never raise into the loop).
  5. Add `_write_prom_textfile(path, *, status, lag_seconds, mismatch_total, now)` — build the text, write to `path.with_suffix(path.suffix + ".tmp")`, then `os.replace` onto `path` (atomic). Series (omit the lag line when `lag_seconds is None`):
     ```
     # HELP zcrypto_gate_status 1 if the >=14-clean-day gate is MET else 0
     zcrypto_gate_status <1|0>
     zcrypto_gate_streak_days <streak>
     zcrypto_gate_journal_pull_lag_seconds <lag>
     zcrypto_gate_mismatch_total <n>
     zcrypto_gate_export_timestamp_seconds <now epoch>
     ```
  6. Add the `gate-export` command per the Behavior above (`--textfile` required; `--journal-dir`, `--healthcheck-url`, `--lag-fail-seconds` default `18000`).

- [ ] **Step 4: Run tests, verify pass** — `uv run pytest tests/test_engine_gate_export.py tests/test_engine_report.py -v` → PASS.

- [ ] **Step 5: README** — add a `zcrypto engine gate-export` row to `## Usage` (args + the 5 emitted series + exit-code semantics).

- [ ] **Step 6: Commit** — `feat(engine): gate-export — machine-readable gate metrics + dead-man ping`.

---

### Task 2: Journal-pull two-key wiring + the gate-export step (NAS entrypoint + compose)

**Files:**
- Modify: `infra/nas/pull-entrypoint.sh` (per-call `ARCHIVE_SSH_KEY`; post-journal-pull `gate-export` step)
- Modify: `infra/nas/compose.yaml` (journal env, two key vars, gate env, `zcrypto.toml` + textfile mounts)
- Modify: `infra/nas/README.md` (env contract + deploy steps: journal key, `JOURNAL_SOURCE`, `GATE_HEALTHCHECK_URL`, the textfile dir)

**Interfaces:**
- Consumes: `zcrypto archive pull` (reads `ARCHIVE_SSH_KEY` from env — unchanged), `zcrypto engine gate-export` (Task 1).
- Produces: a running journal pull + `gate.prom` under the shared textfile dir.

- [ ] **Step 1: Entrypoint.** In `pull-entrypoint.sh`, set the key per call and add the gate-export step (guarded by `JOURNAL_SOURCE`, after the journal pull):

```sh
# capture pull uses the capture key
if ! ARCHIVE_SSH_KEY="$CAPTURE_SSH_KEY" zcrypto archive pull "$CAPTURE_SOURCE" "$CAPTURE_DEST"; then
    echo "pull-entrypoint: capture pull failed (...), continuing" >&2
fi
if [ -n "${JOURNAL_SOURCE:-}" ]; then
    # journal pull uses its OWN least-privilege key
    if ! ARCHIVE_SSH_KEY="$JOURNAL_SSH_KEY" zcrypto archive pull --no-verify "$JOURNAL_SOURCE" "$JOURNAL_DEST"; then
        echo "pull-entrypoint: journal pull failed (...), continuing" >&2
    fi
    # Role B: score the gate on the freshly-pulled journal + emit (best-effort; never exits the loop)
    if ! zcrypto engine gate-export --journal-dir "$JOURNAL_DEST" --textfile "$GATE_TEXTFILE" \
            ${GATE_HEALTHCHECK_URL:+--healthcheck-url "$GATE_HEALTHCHECK_URL"}; then
        echo "pull-entrypoint: gate-export failed (dest=$JOURNAL_DEST), continuing" >&2
    fi
fi
```

- [ ] **Step 2: compose.** In `infra/nas/compose.yaml`, on `archive-pull`: replace the single `ARCHIVE_SSH_KEY` with `CAPTURE_SSH_KEY: /keys/sync_capture` and `JOURNAL_SSH_KEY: /keys/sync_journal`; add `JOURNAL_SOURCE: ${JOURNAL_SOURCE}`, `JOURNAL_DEST: ${JOURNAL_DEST:-/archive/engine-journal}`, `GATE_TEXTFILE: /textfile/gate.prom`, `GATE_HEALTHCHECK_URL: ${GATE_HEALTHCHECK_URL:-}`; keep `ARCHIVE_SSH_KNOWN_HOSTS`/`ARCHIVE_SSH_PORT`. Add mounts: `./zcrypto.toml:/app/zcrypto.toml:ro` and `/volume1/docker/zcrypto-archive/textfile:/textfile` (RW; also mounted RO into Alloy in Task 3).

- [ ] **Step 3: Verify (config-level).** `sh -n infra/nas/pull-entrypoint.sh` (syntax); `docker compose -f infra/nas/compose.yaml config` renders (stub the env). No new unit test: the key selection is env-var scoping and `command.py`'s env consumption + `gate-export` are already covered by Tasks 1 and the existing archive tests. Note this reasoning in the commit body.

- [ ] **Step 4: README.** Add `JOURNAL_SOURCE`, `JOURNAL_SSH_KEY`/`CAPTURE_SSH_KEY`, `GATE_HEALTHCHECK_URL`, `GATE_TEXTFILE`, `JOURNAL_DEST` rows to the env contract; add deploy steps for the `sync_journal` key + the `zcrypto.toml` + the textfile dir.

- [ ] **Step 5: Commit** — `feat(nas): journal pull (own key) + the Role B gate-export step`.

---

### Task 3: NAS Alloy telemetry stack (compose services + `config.alloy`)

**Files:**
- Modify: `infra/nas/compose.yaml` (add `alloy` + `docker-socket-proxy` services)
- Create: `infra/nas/config.alloy`
- Modify: `infra/nas/README.md` (Alloy deploy + creds + resource notes)

**Interfaces:**
- Consumes: the shared textfile dir (`/textfile/gate.prom` from Task 2), the Docker socket (via the proxy), the vaulted Grafana Cloud creds (distributed to the NAS out-of-band).
- Produces: metrics + logs shipped to Grafana Cloud.

- [ ] **Step 1: compose services.** `docker-socket-proxy` (`ghcr.io/tecnativa/docker-socket-proxy`, digest-pinned; `CONTAINERS=1`, everything mutating `=0`; publish `127.0.0.1:2375`; mount `/var/run/docker.sock:ro`). `alloy` (`grafana/alloy`, digest-pinned; non-root; `network_mode: host`; RO mounts `/proc→/host/proc`, `/sys→/host/sys`, `/→/host/root`, `/var/lib/docker:ro`, `/volume1/docker/zcrypto-archive/textfile:/textfile:ro`, `./config.alloy:/etc/alloy/config.alloy:ro`; RW `./alloy-data:/var/lib/alloy`; `command` sets `--storage.path=/var/lib/alloy` + `--server.http.listen-addr=127.0.0.1:12345`; env `GOMEMLIMIT`; `cpus`/`memory`/`cpu_shares` caps per 00043).

- [ ] **Step 2: `config.alloy`.** Adapt 00043's design:
  - `prometheus.exporter.unix "host"` — `set_collectors = ["cpu","loadavg","meminfo","filesystem","netdev","textfile"]`, `procfs_path="/host/proc"`, `sysfs_path="/host/sys"`, `rootfs_path="/host/root"`, `textfile { directory = "/textfile" }`.
  - `prometheus.exporter.cadvisor "containers"` — `docker_host = "tcp://127.0.0.1:2375"`, `docker_only = true`, disabled network group.
  - `prometheus.scrape` both exporters → `prometheus.remote_write "grafana"` (endpoint URL + basic-auth from env/file; `write_relabel_configs` keep-only to hold series < 1k; drop Alloy self-metrics).
  - `loki.source.docker` (archive-pull container logs via the proxy) → `loki.write "grafana"`.
  - Creds referenced via `env("...")` / `local.file`, sourced from a `0600` NAS-side secrets file (never committed).

- [ ] **Step 3: Verify.** `alloy fmt` / `alloy validate` against the rendered config with stub env (offline, no live creds) — run inside a throwaway `grafana/alloy` container. `docker compose config` renders.

- [ ] **Step 4: README.** Document the creds file, the out-of-band distribution, and the resource budget.

- [ ] **Step 5: Commit** — `feat(nas): Alloy + socket-proxy telemetry stack`.

---

### Task 4: One canonical Grafana dashboard + alerts + push script

**Files:**
- Create: `infra/grafana/zcrypto-dashboard.json`, `infra/grafana/alerts.yaml`, `scripts/grafana-push.sh`

**Interfaces:**
- Consumes: the series from Tasks 1 & 3 (`zcrypto_gate_*`, `node_*` host, `container_*`), Grafana Cloud service-account token (vaulted).
- Produces: the committed-as-code dashboard + alert rules + the push tool.

- [ ] **Step 1: Dashboard.** `zcrypto-dashboard.json` with rows (namespaced `NAS · …` / `Gate · …` so VPS rows slot in later without collision): **NAS host** (load via `node_load1`, mem, disk-free `node_filesystem_avail_bytes` for `/volume1`, net IO `node_network_{receive,transmit}_bytes_total`); **NAS containers** (archive-pull + alloy CPU/mem/fs from cadvisor); **Gate** (`zcrypto_gate_status`, `zcrypto_gate_streak_days`, `zcrypto_gate_journal_pull_lag_seconds`, `increase(zcrypto_gate_mismatch_total[1d])`, a Loki logs panel filtered to the archive-pull container).

- [ ] **Step 2: Alerts.** `alerts.yaml` (Grafana provisioning format), each with explicit no-data handling: gate not-MET when it had been MET; `increase(zcrypto_gate_mismatch_total[…]) > 0`; `zcrypto_gate_journal_pull_lag_seconds > 18000`; `time() - zcrypto_gate_export_timestamp_seconds > 7200` (exporter stale); `node_filesystem_avail_bytes{mountpoint="/volume1"}` low; `node_load1` high; ERROR logs in the archive-pull container. Route to email.

- [ ] **Step 3: Push script.** `scripts/grafana-push.sh` (~20 lines, `set -euo pipefail`): POST the dashboard JSON to `/api/dashboards/db` and the alert rules to the provisioning API, using a service-account token read from an env var (documented as vault-sourced). Idempotent (overwrite=true). `shellcheck`-clean.

- [ ] **Step 4: Verify.** `python -c "import json,sys; json.load(open('infra/grafana/zcrypto-dashboard.json'))"` (valid JSON); `shellcheck scripts/grafana-push.sh`; `yamllint infra/grafana/alerts.yaml`.

- [ ] **Step 5: Commit** — `feat(grafana): the one canonical dashboard + gate/host alerts + push script`.

---

### Task 5: Retire the workstation gate-ops timer

**Files:**
- Delete: `infra/systemd/zcrypto-engine-gateops.service`, `infra/systemd/zcrypto-engine-gateops.timer`
- Modify: `docs/specs/00042-vps-deployment-design.md` (or the nearest gate-ops note) — one line noting the retirement + pointer to spec 00049

- [ ] **Step 1:** `git rm` the two template files (superseded by Role B on the NAS).
- [ ] **Step 2:** Add the one-line retirement note where the workstation gate-ops flow is documented (do NOT rewrite 00042's history — a pointer, not a rewrite). The **attended** step (human disables the installed `--user` timer + removes the decrypted key) is recorded in the iterations-history entry + the closeout, not automated here.
- [ ] **Step 3:** `uv run pytest -q` (nothing references the templates; confirm green).
- [ ] **Step 4: Commit** — `chore(nas): retire the workstation gate-ops timer (superseded by Role B)`.

---

### Task 6: Closeout (orchestrator — authored when the work is real)

**Files:** `docs/iterations-history-phase6.md`; `docs/open-topics/` (T0029, T0003, T0020, T0018) + `docs/open-topics/README.md`

- [ ] **Step 1:** Append the **iter-094** entry to `docs/iterations-history-phase6.md` (Role B live: the determinism finding, gate-export, journal pull, Alloy stack, one dashboard, timer retirement, deploy evidence).
- [ ] **Step 2:** **T0029** → `resolved` (both the AVX two-variant AND the determinism residual are now closed by the measured fast-path bit-identity) + `git mv` to `archive/` + index sync. **T0003** → note Role B (gate-verify) landed; remainder = the ≥7-day clean-run + alerting drill + Role C. **T0020** → note the NAS observability slice (Alloy + the shared dashboard + push script + creds path) landed here; remainder = the VPS `obs` role + app `/metrics`. **T0018** → sync if it tracks the Role B step.
- [ ] **Step 3:** Register any deferral surfaced during execution as a `T####` topic (deferral sweep).
- [ ] **Step 4: Commit** — `docs: iter-094 closeout — Role B live + topic syncs`.

## Self-Review

- **Spec coverage:** journal pull (T2), gate-export/fast-path scoring (T1), NAS Alloy host+container+gate+logs (T3), one dashboard+alerts (T4), timer retirement (T5), determinism finding (recorded T6). ✔
- **Type consistency:** `_evaluate_journal` return shape is consumed identically by `report` and `gate-export`; metric names in T1 match the dashboard/alerts in T4 (`zcrypto_gate_status|streak_days|journal_pull_lag_seconds|mismatch_total|export_timestamp_seconds`). ✔
- **No placeholders:** CLI arg placeholders (`<url>`, `<vps-host>`) are argument slots, not gaps; the lag threshold is pinned (`18000`). ✔
