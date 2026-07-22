# Log-shipping rework — implementation plan (spec 00068, iter-116)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the CLI ships its own logs to Grafana Cloud Loki behind an opt-in `--ship-logs` flag; the docker-socket log path is deleted fleet-wide; all four Alloys self-ship via the journald driver.

**Architecture:** one new module `cli/logging/ship.py` (bounded ring + daemon worker + urllib POST), a `configure()` extension attaching it **alongside** the untouched console handler, and per-role infra edits that delete the docker log path and add the journald-driver/journal-pipeline replacements. No existing log formats change.

**Tech Stack:** stdlib only (urllib, threading, collections). Infra: Alloy river configs, compose templates, one Dockerfile ENTRYPOINT edit.

## Global Constraints (copied from spec 00068 — exact values)

- Ring capacity **4096**, drop **oldest** on overflow, drop counter exact.
- Batches **≤500** lines or **1 s** cadence, whichever first; **one** in-flight batch; backoff **1 s → 30 s** doubling, reset on success.
- Single **5 s per-operation** socket timeout; opener built with `ProxyHandler({})` and a redirect-refusing handler; no connection pooling.
- Exit flush hard deadline **2 s**; worker is a daemon thread; `emit()` never blocks (deque + O(1) lock only).
- Labels exactly `{host, container, level}`; line = `JsonLineFormatter` output verbatim; entry ts = `record.created` in ns.
- Env names exactly: `ZCRYPTO_LOKI_URL` (the **full** push URL), `ZCRYPTO_LOKI_USERNAME`, `ZCRYPTO_LOKI_PASSWORD`, `ZCRYPTO_LOG_HOST`, `ZCRYPTO_LOG_SERVICE`. Flag `--ship-logs` with any missing ⇒ hard startup error naming the missing vars.
- Console/stdout behavior byte-identical to today in every mode; the ship sink is additive.
- Recovery after drops emits ONE WARNING (to console and shipped): `log shipping recovered; N lines dropped while unreachable`.
- Retry policy: transport errors, 5xx and 429 retry with the capped backoff; **any other 4xx drops the held batch** (counted, announced on next success) — the poisoned-batch wedge is spec D3's named failure case.
- `ZCRYPTO_LOG_HOST` renders **today's exact label values**: `{{ base_hostname }}` on capture hosts, literal `ops` and `nas` on those hosts (spec D5 — the ops rules hardcode `host="ops"`).
- Every compose reference to the logship secrets (`env_file`, `ZCRYPTO_SHIP_LOGS`) is wrapped in the SAME `logship_loki_token is defined` conditional as the render task (spec D5) — a pre-vault converge must leave every container restartable. **The vault entry now EXISTS** (`logship_loki_token` in `group_vars/observed/vault.yml`, added 2026-07-22), so the guard is true on every `observed` host; it stays in place as the structural safety net, not as a temporary stub.
- No new dependencies anywhere. README `## Usage` updated in the same change as the flag (readme-usage rule).
- Existing suites stay green throughout: `uv run pytest` (incl. `tests/test_infra_alloy_series.py`, `tests/test_infra_alert_rules.py`).

______________________________________________________________________

### Task 1: ShipConfig, payload builder, hardened opener, fake Loki

**Files:**

- Create: `cli/logging/ship.py` (module skeleton: `ShipConfig`, `build_payload`, `_build_opener`, `_RedirectRefused`, module constants)
- Create: `tests/fake_loki.py`
- Test: `tests/test_logging_ship_payload.py`

**Interfaces:**

- Produces: `ShipConfig(url, username, password, host, service)` (frozen dataclass); `build_payload(entries: list[tuple[level, ts_ns, line]], cfg) -> bytes`; `_build_opener() -> OpenerDirector`; constants `RING_CAPACITY=4096, BATCH_MAX=500, FLUSH_INTERVAL_S=1.0, TIMEOUT_S=5.0, BACKOFF_MIN_S=1.0, BACKOFF_MAX_S=30.0, EXIT_DEADLINE_S=2.0`.
- `tests/fake_loki.py` produces `FakeLoki` (threading `http.server`, records `(path, headers, body)` per request, scriptable status codes) and `SilentServer` (accepts the TCP connection, never reads nor responds, closes on shutdown) — both context managers yielding their `http://127.0.0.1:<port>` URL.

**Steps:**

- [ ] **Step 1: failing tests** in `tests/test_logging_ship_payload.py`:

```python
def test_payload_groups_entries_into_one_stream_per_level(cfg):
    body = json.loads(build_payload(
        [("INFO", "1", "a"), ("ERROR", "2", "b"), ("INFO", "3", "c")], cfg))
    streams = {s["stream"]["level"]: s for s in body["streams"]}
    assert set(streams) == {"INFO", "ERROR"}
    assert streams["INFO"]["stream"] == {"host": "h1", "container": "svc1", "level": "INFO"}
    assert streams["INFO"]["values"] == [["1", "a"], ["3", "c"]]  # order preserved

def test_post_carries_basic_auth_and_content_type(fake_loki, handler_factory): ...
    # POST one batch; assert fake_loki saw Authorization: Basic base64(u:p), Content-Type: application/json, path /loki/api/v1/push suffix

def test_proxy_env_is_ignored(fake_loki, monkeypatch):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")   # dead port
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:9")
    # a POST via _build_opener() still reaches fake_loki directly

def test_redirects_are_refused(code, handler_factory):
    # parametrize over [302, 303, 307, 308]; 302/303 are the credential-leaking cases --
    # the stdlib's stock HTTPRedirectHandler FOLLOWS them and forwards Authorization
    # (307/308 are already refused by the stdlib itself for POST, so those alone prove
    # nothing about our hardening). Point Location at a SECOND live FakeLoki and assert
    # BOTH: HTTPError raised with the original code, AND the second server received
    # nothing -- an observable, non-vacuous follow check.

def test_module_constants_are_the_spec_values():
    assert (RING_CAPACITY, BATCH_MAX, FLUSH_INTERVAL_S, TIMEOUT_S,
            BACKOFF_MIN_S, BACKOFF_MAX_S, EXIT_DEADLINE_S) == (4096, 500, 1.0, 5.0, 1.0, 30.0, 2.0)
```

- [ ] **Step 2: run, verify FAIL** (`ImportError`/assert): `uv run pytest tests/test_logging_ship_payload.py -q`
- [ ] **Step 3: implement** the skeleton + `tests/fake_loki.py`. Opener exactly:

```python
class _RedirectRefused(urllib.request.HTTPRedirectHandler):
    """Loki push never legitimately redirects; a 3xx must not re-send credentials elsewhere."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def _build_opener() -> urllib.request.OpenerDirector:
    # ProxyHandler({}) disables env-proxy pickup; without it a stray http_proxy would
    # reroute credentialed log traffic (spec 00068 D3).
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _RedirectRefused())
```

- [ ] **Step 4: run, verify PASS**; **Step 5: commit** `feat(logging): loki push payload, hardened opener, fake-loki test server (00068 T1)`

### Task 2: LokiShipHandler — ring, worker, backoff, recovery, close

**Files:**

- Modify: `cli/logging/ship.py`
- Test: `tests/test_logging_ship_handler.py`

**Interfaces:**

- Produces: `LokiShipHandler(cfg, *, ring_capacity=…, batch_max=…, flush_interval_s=…, timeout_s=…, backoff_min_s=…, backoff_max_s=…, exit_deadline_s=…)` — kwargs exist so tests tighten timings; defaults are the spec constants. Public: `dropped_total`.

**Behavior contract (each bullet is a test):**

- [ ] **Step 1: failing tests**, tightened timings (`flush_interval_s=0.02`, `timeout_s=0.3`, `backoff_min_s=0.05`, `backoff_max_s=0.2`, `exit_deadline_s=0.5`):
  - `emit` appends; a batch arrives at the fake Loki within the flush cadence; line is `JsonLineFormatter` output; ts is `str(int(record.created * 1e9))`.
  - ring at capacity: oldest evicted, `dropped_total` exact (fill capacity+K, assert K dropped and the survivors are the newest).
  - endpoint returns 500: the SAME batch is retried (fake records identical bodies), one in-flight batch only; assert the recorded attempt gaps are monotone-doubling-then-capped (the property, not absolute values — flake-proof). Same for 429.
  - endpoint returns 400: the batch is **dropped, not retried** (fake sees it exactly once), `dropped_total` grows by the batch size, the NEXT batch ships, and the recovery WARNING carries the count — the poisoned-batch case.
  - recovery: fail once with ring overflow, then let the fake succeed — exactly one WARNING record `log shipping recovered; N lines dropped while unreachable` arrives at the console handler AND in a shipped batch, with N exact.
  - **emit latency bounded (the structural guarantee):** point at `SilentServer`, emit 2,000 records, assert total wall for the emits < 0.5 s.
  - **accept-then-silent unblocks:** worker POSTing to `SilentServer` returns to backoff within `timeout_s + slack` (batch retained, no hang).
  - `close()` against a live endpoint: flushes the remainder, returns within the deadline, no "unshipped" print.
  - `close()` against `SilentServer`: returns within `exit_deadline_s + slack`, prints `zcrypto log shipping: N lines unshipped at exit` with N = held + ring.
- [ ] **Step 2: verify FAIL**; **Step 3: implement.** Core shape (complete — transcribe and refine):

```python
class LokiShipHandler(logging.Handler):
    def __init__(self, cfg, *, ring_capacity=RING_CAPACITY, batch_max=BATCH_MAX,
                 flush_interval_s=FLUSH_INTERVAL_S, timeout_s=TIMEOUT_S,
                 backoff_min_s=BACKOFF_MIN_S, backoff_max_s=BACKOFF_MAX_S,
                 exit_deadline_s=EXIT_DEADLINE_S):
        super().__init__()
        self.setFormatter(JsonLineFormatter())
        self._cfg, self._batch_max, self._flush_interval_s = cfg, batch_max, flush_interval_s
        self._timeout_s, self._backoff_min_s, self._backoff_max_s = timeout_s, backoff_min_s, backoff_max_s
        self._exit_deadline_s = exit_deadline_s
        self._ring: deque = deque(maxlen=ring_capacity)
        self._ring_lock = threading.Lock()
        self.dropped_total = 0
        self._dropped_unannounced = 0
        self._held: list = []          # the one in-flight batch (part of the memory bound)
        self._auth = "Basic " + base64.b64encode(f"{cfg.username}:{cfg.password}".encode()).decode()
        self._opener = _build_opener()
        self._stop, self._wake = threading.Event(), threading.Event()
        self._worker = threading.Thread(target=self._run, name="zcrypto-log-ship", daemon=True)
        self._worker.start()

    def emit(self, record):
        try:
            entry = (record.levelname, str(int(record.created * 1_000_000_000)), self.format(record))
            with self._ring_lock:
                if len(self._ring) == self._ring.maxlen:
                    self.dropped_total += 1          # deque evicts the oldest on append
                    self._dropped_unannounced += 1
                self._ring.append(entry)
                full_enough = len(self._ring) >= self._batch_max
            if full_enough:
                self._wake.set()
        except Exception:
            self.handleError(record)

    def _drain(self):
        with self._ring_lock:
            return [self._ring.popleft() for _ in range(min(len(self._ring), self._batch_max))]

    def _post(self, entries) -> str:
        """'ok' | 'retry' | 'drop' -- a non-429 4xx is permanently rejected (e.g. entries older
        than Loki's out-of-order window after a long outage); retrying it forever would wedge
        shipping silently (spec D3)."""
        req = urllib.request.Request(self._cfg.url, data=build_payload(entries, self._cfg),
                                     headers={"Content-Type": "application/json",
                                              "Authorization": self._auth}, method="POST")
        try:
            with self._opener.open(req, timeout=self._timeout_s):
                pass
            return "ok"
        except urllib.error.HTTPError as e:
            return "retry" if (e.code >= 500 or e.code == 429) else "drop"
        except (urllib.error.URLError, OSError, TimeoutError):
            return "retry"

    def _run(self):
        backoff = self._backoff_min_s
        while not self._stop.is_set():
            self._wake.wait(self._flush_interval_s)
            self._wake.clear()
            if not self._held:
                self._held = self._drain()
            if not self._held:
                continue
            outcome = self._post(self._held)
            if outcome == "ok":
                self._held, backoff = [], self._backoff_min_s
                self._announce_recovery()
            elif outcome == "drop":
                with self._ring_lock:
                    self.dropped_total += len(self._held)
                    self._dropped_unannounced += len(self._held)
                self._held, backoff = [], self._backoff_min_s
            else:
                self._stop.wait(backoff)             # interruptible: close() never waits on this
                backoff = min(backoff * 2, self._backoff_max_s)
        while True:                                   # final best-effort flush; no retry loop
            if not self._held:
                self._held = self._drain()
            if not self._held or self._post(self._held) != "ok":
                break
            self._held = []

    def _announce_recovery(self):
        with self._ring_lock:
            n, self._dropped_unannounced = self._dropped_unannounced, 0
        if n:
            logging.getLogger("zcrypto.logging.ship").warning(
                "log shipping recovered; %d lines dropped while unreachable", n)

    def close(self):
        self._stop.set()
        self._wake.set()
        self._worker.join(self._exit_deadline_s)      # the app's exit-path bound; the daemon
        left = len(self._held) + len(self._ring)      # thread dies with the interpreter if late
        if left:
            print(f"zcrypto log shipping: {left} lines unshipped at exit", flush=True)
        super().close()
```

- [ ] **Step 4: verify PASS**; run the FULL logging test set. **Step 5: commit** `feat(logging): bounded non-blocking loki ship handler (00068 T2)`

### Task 3: `--ship-logs` flag, env validation, `configure()` wiring, README

**Files:**

- Modify: `cli/logging/config.py` (signature `configure(path, level, ship: ShipConfig | None = None)`; when `ship`, attach a `LokiShipHandler` alongside the console/file handler; the existing owned-handler removal loop also closes a prior ship handler on reconfigure)
- Modify: `cli/logging/__init__.py` (export `ShipConfig`)
- Modify: `cli/__main__.py` (flag + env validation; build `ShipConfig`; pass to `configure`)
- Modify: `README.md` `## Usage` (the flag + the five env names + one sentence on semantics)
- Test: `tests/test_logging_config.py` (extend), `tests/test_logging_cli.py` (the existing CLI-callback test module)

**Steps:**

- [ ] **Step 1: failing tests:** flag off ⇒ handlers unchanged (exact count, console formatter still `PlainTextFormatter`); flag on with full env ⇒ ship handler attached AND console handler untouched; flag on with `ZCRYPTO_LOKI_URL` unset ⇒ `CliRunner` exit code 2, error text contains the exact missing name; reconfigure idempotency (two `configure` calls ⇒ one ship handler, first one closed).
- [ ] **Step 2: FAIL**; **Step 3: implement.** Validation in `cli/__main__.py`:

```python
if ship_logs:
    names = ("ZCRYPTO_LOKI_URL", "ZCRYPTO_LOKI_USERNAME", "ZCRYPTO_LOKI_PASSWORD",
             "ZCRYPTO_LOG_HOST", "ZCRYPTO_LOG_SERVICE")
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        raise typer.BadParameter(f"--ship-logs requires env vars: {', '.join(missing)}")
    ship = ShipConfig(url=os.environ["ZCRYPTO_LOKI_URL"], username=os.environ["ZCRYPTO_LOKI_USERNAME"],
                      password=os.environ["ZCRYPTO_LOKI_PASSWORD"], host=os.environ["ZCRYPTO_LOG_HOST"],
                      service=os.environ["ZCRYPTO_LOG_SERVICE"])
```

- [ ] **Step 4: PASS + full suite**; **Step 5: commit** `feat(cli): --ship-logs flag with env-validated loki config (00068 T3)`

### Task 4: capture-image ENTRYPOINT conveyance

**Files:**

- Modify: `infra/docker/Dockerfile:51` — the inline ENTRYPOINT gains `${ZCRYPTO_SHIP_LOGS:+--ship-logs}` between `zcrypto` and `capture`: `exec zcrypto ${ZCRYPTO_SHIP_LOGS:+--ship-logs} capture "$@"`
- Modify: `infra/docker/compose.yaml` (the standalone reference counterpart named in the capture template header — mirror the env additions of Task 5 so the two stay in lock-step)

**Steps:**

- [ ] **Step 1:** apply both edits (no unit-testable surface; the rollout's positive-trace step verifies). **Step 2:** `docker build` locally if the daemon is available, else record skipped. **Step 3: commit** `feat(infra): capture entrypoint honors ZCRYPTO_SHIP_LOGS (00068 T4)`

### Task 5: capture role — Alloy shrink, journald driver, ship env

**Files:**

- Modify: `infra/ansible/roles/capture/files/config.alloy`
- Modify: `infra/ansible/roles/capture/templates/alloy-compose.yaml.j2`
- Modify: `infra/ansible/roles/capture/templates/compose.yaml.j2`
- Create: `infra/ansible/roles/capture/templates/logship-secrets.env.j2`
- Modify: `infra/ansible/roles/capture/tasks/main.yml`

**Exact edits:**

- [ ] **Step 1 — `config.alloy`:** delete the blocks `discovery.docker "containers"`, `discovery.relabel "container_logs"`, `loki.source.docker "containers"`, and the zcrypto `stage.match` (selector `{container=~"capture|zcrypto-.*"}`) inside `loki.process "parse"` — on the capture hosts the journal carries only prune bash lines and Alloy logfmt, so nothing feeds it (spec D6; on ops/NAS the stage STAYS). Rework the alloy stage: selector plain `{container="alloy"}` (delete the `|~ "^ts=…"` line-match regex), `stage.logfmt { mapping = { "level" = "" } }` + the existing warn→WARNING/fatal→CRITICAL template + `stage.labels` — and **no `stage.output`**: the line ships unmodified (attributes kept; non-logfmt lines pass through unleveled). Remove `prometheus_sd_refresh_duration_seconds_count|prometheus_sd_refresh_failures_total` from the metrics keep-regex (their producer dies with `discovery.docker`) and update the `_SD_` pins in `tests/test_infra_alloy_series.py`. Widen the journal keep to admit the alloy container's journald stream — the two-source OR pattern:

```river
rule {
  source_labels = ["__journal__systemd_unit", "__journal_container_name"]
  separator     = ";"
  regex         = "zcrypto-capture-prune\\.service;.*|.*;grafana-alloy"
  action        = "keep"
}
rule {
  source_labels = ["__journal_container_name"]
  regex         = "grafana-alloy"
  target_label  = "container"
  replacement   = "alloy"
}
```

(keep the existing unit-name → `container` rule for the prune unit; order the container-name rule after it).

- [ ] **Step 2 — `alloy-compose.yaml.j2`:** delete the `- /var/run/docker.sock:/var/run/docker.sock:ro` volume and the docker-group `group_add` entry (the `systemd-journal` group entry **stays** — journal reads need it); add to the alloy service: `logging: { driver: journald }`.
- [ ] **Step 3 — `compose.yaml.j2` (capture service):** inside a `{% if logship_loki_token is defined %}` guard (spec D5 — a pre-vault converge must leave capture restartable): `ZCRYPTO_SHIP_LOGS: "1"`, `ZCRYPTO_LOG_HOST: "{{ base_hostname }}"`, `ZCRYPTO_LOG_SERVICE: capture` in `environment:`, and `env_file: ["/opt/zcrypto-capture/logship-secrets.env"]` (the compose dest dir is hardcoded `/opt/zcrypto-capture` in `tasks/main.yml:53` — there is no `capture_dir` var).
- [ ] **Step 4 — `logship-secrets.env.j2`:** three lines, and note only ONE is new — `ZCRYPTO_LOKI_URL={{ grafana_loki_url }}`, `ZCRYPTO_LOKI_USERNAME={{ grafana_loki_user }}`, `ZCRYPTO_LOKI_PASSWORD={{ logship_loki_token }}` (URL and username are stack properties, not token properties, so they are reused rather than duplicated — one value to rotate, nothing to drift); **Step 5 — `tasks/main.yml`:** render task (root-owned 0600) mirroring the alloy-secrets render task; the vault already carries `logship_loki_token` (and `grafana_loki_url`/`grafana_loki_user` alongside it), so the render works on every `observed` host — the `when: logship_loki_token is defined` gate stays as the structural safety net.
- [ ] **Step 6:** delete the `zcrypto-alloy-docker-sd-wedged` rule from `infra/grafana/alerts.yaml` — its `prometheus_sd_*` series die with `discovery.docker` fleet-wide, leaving it permanently NoData (spec D8; the provisioning PUSH is attended, this is the repo edit). **Step 7:** `uv run pytest tests/test_infra_alloy_series.py tests/test_infra_alert_rules.py -q` — fix what the deletions break (the `_SD_` pins WILL break; that is Step 1's update, verify it landed). **Step 8: commit** `feat(infra): capture hosts — docker.sock retired, alloy self-ships via journald (00068 T5)`

### Task 6: ops role — same treatment + poller flag

**Files:** `infra/ansible/roles/ops/files/config.alloy`, `templates/alloy-compose.yaml.j2`, `templates/compose.yaml.j2`, `templates/logship-secrets.env.j2` (create), `tasks/main.yml`

- [ ] **Step 1:** `config.alloy`: delete the docker path ONLY (`discovery.docker` at ~line 182, its relabel with the ephemeral drop rule, `loki.source.docker`). **The zcrypto parse stage STAYS** — the ops oneshot units ship Python-format lines through the journal, and deleting it strips their `level` forever (spec D6, cold-review C2). Apply the same alloy-stage rework as Task 5 (equality selector, `stage.logfmt`, no output rewrite); remove the two `prometheus_sd_*` entries from the keep-regex; widen the journal keep regex from `zcrypto-(archive-pull|verify-replay|verified-replay|panel-materialize)\.service` with the same two-source OR + container-name rule as Task 5.
- [ ] **Step 2:** `alloy-compose.yaml.j2`: socket volume + docker group_add out; `logging: { driver: journald }` in.
- [ ] **Step 3:** `compose.yaml.j2` liquidations service, inside the `{% if logship_loki_token is defined %}` guard: `entrypoint: ["zcrypto", "--ship-logs", "liquidations-poll"]` (the un-gated branch keeps today's entrypoint), env `ZCRYPTO_LOG_HOST: ops` (**literal — NOT base_hostname, which is `zcrypto-ops`**; the alert rules hardcode `host="ops"`, spec D5/cold-review C1), `ZCRYPTO_LOG_SERVICE: liquidations`, env_file the rendered secrets. **Step 4:** secrets template + gated render task. **Step 5:** infra tests green. **Step 6: commit** `feat(infra): ops — docker.sock retired, poller direct-ships (00068 T6)`

### Task 7: engine role — flag staged, inert until the post-gate converge

**Files:** `infra/ansible/roles/engine/templates/compose.yaml.j2` (+ the engine env/task files as needed)

- [ ] **Step 1:** inside the same `{% if logship_loki_token is defined %}` guard: `entrypoint: ["zcrypto", "--ship-logs", "engine", "run"]` (un-gated branch keeps today's), env `ZCRYPTO_LOG_HOST: "{{ base_hostname }}"` (renders `zcrypto` — matches today's engine stream label), `ZCRYPTO_LOG_SERVICE: engine`; env_file `/opt/zcrypto-capture/logship-secrets.env` (reuse the capture host's rendered file — same host). **The repo change is inert until an attended engine converge, which is gated post-Stage-6a-gate (spec D7 step 6) — state this in the template comment.** **Step 2:** infra tests. **Step 3: commit** `feat(infra): engine compose stages --ship-logs for the post-gate converge (00068 T7)`

### Task 8: NAS — socket retired, first-time journal pipeline

**Files:** `infra/nas/compose.yaml`, `infra/nas/config.alloy`

- [ ] **Step 1:** `compose.yaml`: `logging: { driver: journald }` on BOTH `zcrypto-archive-pull` and `grafana-alloy`; delete the socket volume AND the `group_add: ["0"]` entry from the alloy service (root gid, present solely for the socket — spec D6/cold-review I3); add journal mounts to alloy: `/run/log/journal:/host/journal:ro` (**the volatile path — measured: `/var/log/journal` is empty on DSM**) + `/etc/machine-id:/etc/machine-id:ro`.
- [ ] **Step 2:** `config.alloy`: delete `discovery.docker`/relabel/`loki.source.docker` ONLY — **the zcrypto parse stage (`{container="archive-pull"}`) STAYS**: the pull wrapper's shell lines deliberately mimic the Python line shape so they still get leveled (spec D6, cold-review C2). Add a first-time journal pipeline (`loki.source.journal` at `/host/journal`, `max_age = "48h"`) with keep on `__journal_container_name` regex `grafana-alloy|zcrypto-archive-pull`, container-label mapping (`grafana-alloy`→`alloy`, `zcrypto-archive-pull`→`archive-pull` — preserve today's label values by checking the current relabel first), and `host` as the **static literal `nas`** (today's streams carry it via a static relabel; `constants.hostname` would return the DSM machine name — cold-review I2). Apply the same alloy-stage rework as Task 5; remove the two `prometheus_sd_*` keep-regex entries here too.
- [ ] **Step 3:** infra tests; **Step 4: commit** `feat(infra): nas — docker.sock retired, journald pipeline (00068 T8)`

### Task 9: closeout — full suite, gate, iterations-history entry

- [ ] **Step 1:** `uv run pytest` full; `uv run pre-commit run -a` to clean.
- [ ] **Step 2:** append the iter-116 entry to `docs/iterations-history-phase6.md` per the `iteration-closeout` skill (subject-matter phase 6 — execution/live-prep infra); include: what landed, the flag + env names, the fleet table from spec D6, and the explicit statement that **rollout has NOT happened** — spec D7's attended steps and the cross-topic records (T0089/T0042/T0020) land at rollout, not here.
- [ ] **Step 3: commit** `docs(closeout): iter-116 history entry (00068 T9)`
- [ ] **Deferred (Minor-5, 00068 T4/T5 review; executes at the alert push, spec D7 step 3 -- not in this PR):** once `infra/scripts/grafana-push.sh` runs with pruning and `zcrypto-alloy-docker-sd-wedged` is confirmed gone from Grafana, rewrite `docs/open-topics/T0048-alloy-docker-tailer-dies-on-container-recreate.md`'s mitigation section IN PLACE (never append a retraction — `.claude/rules/agent-ops.md`) to reflect that the pinning/alert it describes no longer exists.

## Explicitly NOT in this plan (attended, spec D7)

Vault token creation, every host converge/recreate, the NAS journald probe, per-step Loki positive-trace verification, alert-rule verification, and the T0089/T0042 topic updates — all attended rollout work, sequenced by spec D7 with the canary rule and the post-gate engine constraint.
