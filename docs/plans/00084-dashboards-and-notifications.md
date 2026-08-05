# Fleet presentation layer — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every metric family that can page you is visible on a dashboard, every alert points at the panel that shows it, and the Slack message is legible without opening Grafana.

**Architecture:** Four committed Grafana boards (three metric, one logs) pushed by the existing `grafana-push.sh`; a rewritten alert layer that adds four liveness rules plus an engine ERROR-log rule, ungroups three label collapses, and gains a panel pointer on every rule; two Go notification templates provisioned as a template object; two engine gauge-lifecycle fixes in `cli/engine/command.py`; and one new test that makes the coverage invariant mechanical rather than a one-time cleanup.

**Tech Stack:** Grafana Cloud (dashboards + unified alerting, provisioning API), PromQL/LogQL, Go templates, `prometheus_client`, Grafana Alloy keep-regexes, Ansible, pytest.

**Spec:** `docs/specs/00084-dashboards-and-notifications-design.md`. **The spec's D2/D3/D4 panel tables and D11 rule table ARE the requirements** — every panel and rule named there is in scope, with the "what it answers" column as its acceptance criterion. This plan does not restate them; it sequences them and pins the mechanics.

## Global Constraints

Copied verbatim from the spec. Every task's requirements implicitly include this section.

- **Board titles are sentence case, no product prefix**: `Fleet health`, `Data integrity`, `Engine`, `Logs`.
- **New uids**: `zcrypto-fleet`, `zcrypto-integrity`, `zcrypto-engine`. `zcrypto-main` is NOT reused and NOT deleted by tooling — its removal is an owner step at closeout.
- **Filenames must match `infra/grafana/*-dashboard.json`** — that is `grafana-push.sh`'s glob. A non-matching name is committed, tested, and never pushed, silently.
- **`graphTooltip: 1`** (Shared Crosshair) on all three metric boards. Not on `Logs`.
- **`tags: []` on all four boards** — purged, not rewritten (spec D1).
- **Every panel is UNAMBIGUOUS about which host each series belongs to** — by one of D6's three routes: an explicit `host=` / `$host` matcher (mandatory for `node_*`, `process_*`, `zcrypto_capture_*`, `zaccess_*`, `up`); a single-publisher family whose publisher the description names (`zcrypto_gate_*` → NAS; `zcrypto_reconcile_*`, `zcrypto_trade_backfill_*`, `ops_*`, `hc_*` → ops; `zcrypto_engine_*` → the primary); or a per-host legend (`zcrypto_logship_*`, P5). **27 of the 52 metric rules are host-unscoped**, so a panel copying its rule verbatim per P1 will often take route 2 or 3 — that is correct, not a violation. `instance` collides fleet-wide (every Alloy binds `127.0.0.1:12345`); `host` is the only discriminator.
- **P1 — a panel serving a rule plots the RULE'S EXPRESSION, not the rule's family**, divisor included.
- **P2 — a panel serving a rule encodes that rule's threshold as a marked `fieldConfig.thresholds.steps` value**; per-host field overrides where hosts have different bars, never one shared ladder.
- **P3 — a panel's description carries the rule's `for:` duration.**
- **P4 — every monotone counter gets its recent-delta companion**, in the form matching its semantics (`increase` / `delta` / `max_over_time` — spec D2's table).
- **P5 — legends are `{{host}}/{{job}}`** for logship and `process_*`.
- **P6 — every metric board carries a restart annotation** over `changes(process_start_time_seconds[5m]) > 0`; silent on `zaccess` by construction.
- **`$host` is a CUSTOM variable with `label : value` pairs** — `Capture primary : zcrypto, Capture secondary : zcrypto-red, Ops : ops, NAS : nas, Edge : zaccess` — multi, includeAll, `allValue` left EMPTY. This supersedes the `label_values(...)` + regex form: a query variable cannot carry display labels, and a fixed option list is a stronger pin than a regex anyway.
- **Operator-facing text**: no `T<NNNN>`, `spec <NNNNN>`, `iter-<N>`, `Phase <N>`, `WP<N>` in any panel title, panel description, alert rule title, alert summary, or notification template output. Enforced by `tests/test_internal_terms_not_operator_visible.py`.
- **Host display vocabulary** (rule titles, summaries, panel prose, notification text — **not** label values, **not** legends): `zcrypto` → Capture primary, `zcrypto-red` → Capture secondary, `ops` → Ops, `nas` → NAS, `zaccess` → Edge.
- **No metric label value, `external_labels` entry, inventory entry, or hostname changes.** Renaming changes series identity.
- **Panel JSON idiom**: match `infra/grafana/zcrypto-dashboard.json` exactly — same `datasource` shape, `fieldConfig.defaults`/`overrides` structure, `gridPos` layout, `targets[].expr`/`legendFormat`/`refId`. It is hand-written committed JSON; there is no generator.
- **`__panelId__` values MUST be quoted strings in YAML.** `grafana-push.sh` does `yaml.safe_load` → `json.dumps`; an unquoted `305` becomes a JSON number, the provisioning API rejects it, and `curl -fsS` under `set -euo pipefail` aborts the whole push.
- Commit gate is `uv run pre-commit run -a`, run to clean before every commit.

---

### Task 1: Engine gauge lifecycle fixes

Fixes the two defects spec D4 records. Pure code, no deployment, nothing reads these families yet — so it is safe to land first and it de-risks the rest.

**Files:**
- Modify: `cli/engine/command.py` — `_CycleGauges.__init__` and its per-cycle update method
- Test: `tests/test_engine_metrics.py` (extend if present; create if not — check first)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `_CycleGauges` where `cycle_duration` is lazily registered and target-weight labels are retired. Task 8 (Engine board) relies on both: it renders absence as absence, and it does not warn about stale weights.

- [ ] **Step 1: Read the current implementation**

Read `cli/engine/command.py` around `_CycleGauges` — `__init__`, the cycle-update method that calls `.set(...)`, and the existing lazy-registration helper used for `cycle_success` (it is the pattern to copy for `cycle_duration`). Note the exact method names; do not guess them.

- [ ] **Step 2: Write the failing tests**

```python
def test_cycle_duration_is_absent_before_the_first_cycle():
    """It must not publish a gauge default of 0 — a false 'the last cycle took 0 seconds'."""
    registry = CollectorRegistry()
    gauges = _CycleGauges(registry=registry)
    assert registry.get_sample_value("zcrypto_engine_cycle_duration_seconds") is None


def test_cycle_duration_registers_on_first_cycle():
    registry = CollectorRegistry()
    gauges = _CycleGauges(registry=registry)
    gauges.observe_cycle(duration_seconds=12.5)          # use the real method name from Step 1
    assert registry.get_sample_value("zcrypto_engine_cycle_duration_seconds") == 12.5


def test_a_dropped_asset_stops_publishing_its_target_weight():
    """A weight that persists after the asset leaves the book over-reports for the life of the process."""
    registry = CollectorRegistry()
    gauges = _CycleGauges(registry=registry)
    gauges.set_target_weights({"BTC": 0.6, "ETH": 0.4})
    gauges.set_target_weights({"BTC": 1.0})
    assert registry.get_sample_value("zcrypto_engine_target_weight", {"asset": "BTC"}) == 1.0
    assert registry.get_sample_value("zcrypto_engine_target_weight", {"asset": "ETH"}) is None, (
        "a dropped asset must go ABSENT, not to zero — zero and not-in-the-book are different states"
    )
```

- [ ] **Step 3: Run them and confirm they fail**

Run: `uv run pytest tests/test_engine_metrics.py -v`
Expected: all three FAIL — `cycle_duration` present at 0, and `ETH` still reporting 0.4.

- [ ] **Step 4: Implement**

`cycle_duration`: remove it from `__init__`; register it lazily on first observation exactly as `cycle_success` does.

Target weights: track the label set written last cycle and remove the difference.

```python
        # Retire assets that left the target set: a weight left behind keeps publishing its last
        # value for the life of the process. remove(), not set(0) -- a zero weight and a
        # not-in-the-book asset are different states and the executor must tell them apart.
        for asset in self._last_weight_assets - set(weights):
            self.target_weight.remove(asset)
        self._last_weight_assets = set(weights)
```

Initialise `self._last_weight_assets: set[str] = set()` in `__init__`.

- [ ] **Step 5: Run the tests, then the suite**

Run: `uv run pytest tests/test_engine_metrics.py -v` — expect PASS.
Then: `uv run pytest` — the engine journal/cycle tests exercise these gauges; expect no regressions.

- [ ] **Step 6: Commit**

```bash
uv run pre-commit run -a
git add cli/engine/command.py tests/test_engine_metrics.py
git commit -m "fix(engine): retire dropped target weights and stop publishing a false zero duration"
```

---

### Task 1b: The carried ledger-records gauge

Spec D3's "carried rider". **This iteration carries T0044 and the memo is the ruling that says so** — the gauge has no other carrier, and shipping without it returns T0044 to waiting on a human ledger correction that may never come. Code, so it lands beside Task 1 rather than with the panels.

**Files:**
- Modify: `cli/archive/command.py` — `_write_textfile()`
- Test: `tests/test_archive_reconcile.py` (find the module that already covers `_write_textfile` / `_totals`; do not create a new one if one exists)

**Interfaces:**
- Produces: `zcrypto_reconcile_ledger_records`, a gauge. Task 7 renders it as a second series on the reconcile row's "Gap totals" panel.

- [ ] **Step 1: Write the failing test**

```python
def test_textfile_publishes_the_ledger_record_count(tmp_path):
    """Every reconcile counter is summed from the whole ledger, so a reset has no visible cause
    without this. It explains the silent empty-ledger path too, which a corrections counter cannot."""
    out = tmp_path / "reconcile.prom"
    _write_textfile(out, now=..., totals={..., "ledger_records": 4211}, lags={...})
    body = out.read_text()
    assert "# TYPE zcrypto_reconcile_ledger_records gauge" in body
    assert "zcrypto_reconcile_ledger_records 4211" in body
```

Fill the `...` from the existing tests in that module — reuse their fixture shape rather than inventing one.

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/test_archive_reconcile.py -v` — expect FAIL, the family is absent.

- [ ] **Step 3: Implement**

Add `ledger_records` to `_totals()` (it already walks every record — count them in that same pass, no second read), then one `_emit(...)` call beside `trade_dedup_rows_total`:

```python
    _emit(
        "ledger_records",
        "gauge",
        "Records in the append-only reconcile ledger this cycle summed its totals from.",
        [("", totals["ledger_records"])],
    )
```

A **gauge**, not a counter: it must be able to fall, since a correction removing records is exactly the event it exists to explain.

- [ ] **Step 4: Verify, including the keep-list**

Run: `uv run pytest tests/test_archive_reconcile.py tests/test_infra_alloy_series.py -v`

The ops keep-regex admits `zcrypto_reconcile_.*` as a wildcard, so no config change is needed — but `test_infra_alloy_series.py` maintains a hand-curated published-family list per host, so **add the family there** or its own guard goes stale.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a
git add cli/archive/command.py tests/test_archive_reconcile.py tests/test_infra_alloy_series.py
git commit -m "feat(archive): publish the reconcile ledger record count so a counter reset has a visible cause"
```

---

### Task 2: Widen the zaccess keep-regex

**Files:**
- Modify: `infra/ansible/roles/access/files/config.alloy` (the `keep` write_relabel_config regex)
- Modify: `tests/test_infra_alloy_series.py` (the access host's `required` list)

**Interfaces:**
- Produces: `node_scrape_collector_success` admitted on `zaccess`. Task 11's coverage assertion 3 depends on this; Task 6's collector panel drops its `host!="zaccess"` exclusion because of it.

- [ ] **Step 1: Write the failing test**

Add `"node_scrape_collector_success"` to the access entry's `required` list in `tests/test_infra_alloy_series.py`. Read the file first — the lists are module-level constants keyed per host.

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/test_infra_alloy_series.py -v`
Expected: `test_keep_regex_admits_every_published_series[access]` FAILS naming `node_scrape_collector_success`.

- [ ] **Step 3: Add the family to the regex**

Insert `node_scrape_collector_success` into the `keep` regex in `infra/ansible/roles/access/files/config.alloy`, alphabetically adjacent to the other `node_scrape_*`-class entries if one exists, otherwise beside `node_filesystem_size_bytes`. **Add only this one family** — the other five the access regex lacks relative to its siblings have no rule behind them and cost series for nothing.

- [ ] **Step 4: Verify**

Run: `uv run pytest tests/test_infra_alloy_series.py -v` — expect PASS.

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a
git add infra/ansible/roles/access/files/config.alloy tests/test_infra_alloy_series.py
git commit -m "fix(access): admit node_scrape_collector_success so the collector alert can fire for the bridgehead"
```

---

### Task 3: Close both dashboard-glob traps

**Files:**
- Modify: `tests/test_internal_terms_not_operator_visible.py` (`_dashboard_texts`, plus one new test)

**Interfaces:**
- Produces: a guard that walks every `*.json` in `infra/grafana/` and proves each matches the push glob. Tasks 6–9 depend on it to catch a mis-named board immediately.

- [ ] **Step 1: Write the failing test**

```python
def test_every_dashboard_json_matches_the_push_script_glob():
    """grafana-push.sh iterates infra/grafana/*-dashboard.json. A board named otherwise is
    committed, passes every check, and is NEVER pushed -- silently absent from Grafana."""
    strays = [
        p.name
        for p in sorted((REPO / "infra/grafana").glob("*.json"))
        if not p.name.endswith("-dashboard.json")
    ]
    assert not strays, f"these .json files will never be pushed by grafana-push.sh: {strays}"
```

- [ ] **Step 2: Prove the guard trips**

Create `infra/grafana/stray.json` containing `{}`. Run the test — expect FAIL naming `stray.json`. Delete the file. **A guard that has not been seen to trip is unproven.**

- [ ] **Step 3: Widen the vocabulary glob**

In `_dashboard_texts`, change `glob("*dashboard*.json")` to `glob("*.json")`. Leave the existing `assert out, "walked no dashboard text — the glob is broken, not the dashboards clean"` in place.

- [ ] **Step 4: Prove THAT guard trips too**

Create `infra/grafana/temp-dashboard.json` containing a panel whose title is `"Phase 6 gate"`. Run `uv run pytest tests/test_internal_terms_not_operator_visible.py -v` — expect the vocabulary test to FAIL naming that title. Delete the file.

- [ ] **Step 5: Run and commit**

```bash
uv run pytest tests/test_internal_terms_not_operator_visible.py -v
uv run pre-commit run -a
git add tests/test_internal_terms_not_operator_visible.py
git commit -m "test(grafana): walk every dashboard json and prove each one is actually pushed"
```

---

### Task 4: Alert rules — new liveness rules, label ungrouping, title harmonisation

Everything in `alerts.yaml` except the logs rules (Task 5) and the panel pointers (Task 10).

**Files:**
- Modify: `infra/grafana/alerts.yaml`

**Interfaces:**
- Consumes: nothing.
- Produces: four new/corrected rule titles that Tasks 6–9 reference in their panels' `serves_alert_rules`, and the ungrouped labels the Slack template (Task 12) renders.

- [ ] **Step 1: Add the two capture rules and the two engine rules**

Author exactly the four new rules from spec D11's table — `Capture · every book stream on a host is silent`, `Capture · a book stream has stopped delivering`, `Engine · cycles have stopped`, `Engine · the last cycle failed` — with the expression, `for`, `noDataState`, and severity given there. Copy the surrounding rules' YAML shape (uid, `condition`, `data` node structure, `execErrState`, `notification_settings`) exactly.

**The `900` in the per-pair silence rule is a starting threshold and must be derived before the push** — see Task 13, Step 2. Author it as `900` with a comment recording that it is provisional and what derives it.

- [ ] **Step 2: Ungroup the three label collapses**

Per spec D11: `Access · WireGuard tunnel stale` → `max by (host) (...)`; `Access · edge cert expiring` → `min by (host, target) (...)`; `Capture · Kraken reports the venue is not online` → `sum by (host, system) (... {host=~"zcrypto|zcrypto-red", system!="online"})`. Update each rule's `summary` to interpolate the newly-available label (`{{ $labels.host }}`, `{{ $labels.target }}`, `{{ $labels.system }}`).

**Superseded for `{{ $labels.host }}` — the opposite is now true, and enforced.** Grafana bakes annotations at *evaluation* time, before any notification template runs, so the Slack template's hostname mapping cannot reach a summary and interpolating `host` ships the raw internal hostname to a phone. No summary interpolates `host`; `tests/test_infra_alert_rules.py::test_no_alert_summary_interpolates_the_internal_hostname` pins that, and the summaries instead say "the host this notification names" and leave the naming to the template. `{{ $labels.target }}` and `{{ $labels.system }}` are not hostnames and correctly remain.

- [ ] **Step 3: Harmonise the six hostname-carrying titles**

`Capture · log pipeline dead — primary (zcrypto)` → `… — Capture primary`; the secondary likewise; `Fleet · Alloy dark — capture primary (zcrypto)` → `… — Capture primary`; secondary likewise; `— ops` → `— Ops`; `— zaccess` → `— Edge`. **Do not touch any `uid`** — the rule identity must not change.

- [ ] **Step 4: Sweep every summary for hostnames**

```bash
uv run python -c "
import re, yaml
rs = yaml.safe_load(open('infra/grafana/alerts.yaml'))['rules']
# A hostname used AS a hostname -- a parenthetical, or a bare token after an em-dash or 'on'.
pat = re.compile(r'\((?:zcrypto|zcrypto-red|zaccess)\)|[—-] (?:zcrypto|zcrypto-red|zaccess)\b|\bon (?:zcrypto|zcrypto-red)\b')
bad = [(r['title'], m.group(0)) for r in rs
       for m in [pat.search(r['title'] + ' :: ' + r.get('annotations',{}).get('summary',''))] if m]
[print('LEAK:', t, '::', m) for t, m in bad]
print('leaks:', len(bad))
"
```

Expected: `leaks: 0`.

**The sweep targets hostnames used AS hostnames, and that narrowness is deliberate.** A naive substring search over titles and summaries hits **29 rules** today, almost all benignly: CLI command names (`zcrypto engine gate-export`), unit and container names (`zcrypto-archive-pull`), and paths (`/var/lib/zcrypto-capture`). Those are correct text and rewording them is not in scope — D6's vocabulary is about naming *a machine*, not about purging a token. If you find yourself rewording a command name to satisfy this check, the check is wrong, not the summary.

- [ ] **Step 5: Validate and commit**

```bash
uv run python -c "import yaml; d=yaml.safe_load(open('infra/grafana/alerts.yaml')); print(len(d['rules']), 'rules')"
uv run pytest tests/test_internal_terms_not_operator_visible.py -v
uv run pre-commit run -a
git add infra/grafana/alerts.yaml
git commit -m "feat(grafana): add engine and capture liveness rules, ungroup collapsed labels, harmonise titles"
```

---

### Task 5: Alert rules — the eleven logs rules

**Files:**
- Modify: `infra/grafana/alerts.yaml` (logs-sourced rules only)

**Interfaces:**
- Produces: `host`/`container` labels on every logs alert, and a `msg` label on the two ERROR rules that the logs notification template (Task 12) renders.

- [ ] **Step 1: Give the nine bare-`sum()` rules a `by` clause**

Each currently reads `sum(count_over_time({...}[Xh]))`. Add `by (host, container)` — or `by (host)` where `container` is already pinned to a literal in the selector.

**Interpolate `{{ $labels.host }}` into the summary on the PRESENCE-fired rules only.** Seven of these rules are dead-canary rules that fire on the `or on() vector(0)` arm: when the stream is empty the `sum by (...)` returns **no series at all**, and the unlabelled `vector(0)` is what crosses the threshold — so the `by` clause is inert at exactly fire time and `{{ $labels.host }}` renders as an empty string, mangling the page on the alerts where the page is the only signal. On those seven, write the host and container into the summary **as literal words**; their selectors are literal, so the rule knows statically what it watches. Keep the `by` clause there anyway — harmless, and correct if the arm ever changes — but do not claim it fixes anything.

Correction to the spec's rationale, verified: `container="archive-pull"` **is** unambiguous — only the NAS produces that container label; ops publishes `zcrypto-archive-pull`. The `by` clause earns its place on the presence-fired rules, not on that argument.

- [ ] **Step 2: Confirm `__line__` is available inside `label_format`**

**Blocking precondition, and it is checked in Grafana Explore against live Loki, not assumed.** Run the hoist query from spec D12 against a 15-minute window on a host known to have log lines. If `msg` is populated, continue. If `label_format` rejects `__line__`, **stop and report** — the fallback is to drop the `msg` half and let the template's "counts lines rather than carrying them" branch render; nothing else in this task depends on it.

- [ ] **Step 3: Hoist the message on the two ERROR rules**

Apply the `topk(5, sum by (host, container, level, msg) (count_over_time(... | label_format msg=...)))` form from spec D12 to `zcrypto-capture-error-logs` and `zcrypto-ops-error-logs`. `topk(5, …)` is not optional: without it a log storm mints one alert instance per distinct line and blows past Slack's length limit.

- [ ] **Step 4: Narrow the ops ERROR rule by container**

`zcrypto-ops-error-logs` selects `{host="ops", level=~"ERROR|CRITICAL"}` with no container filter. Add one. Enumerate the containers actually shipping from ops first — do not guess the list:

```bash
uv run python infra/scripts/grafana-query.py 'count by (container) ({host="ops"} | logfmt)' 2>/dev/null || \
  echo "use Grafana Explore: sum by (container) (count_over_time({host=\"ops\"}[24h]))"
```

- [ ] **Step 5: Validate and commit**

```bash
uv run python -c "import yaml; yaml.safe_load(open('infra/grafana/alerts.yaml')); print('parses')"
uv run pre-commit run -a
git add infra/grafana/alerts.yaml
git commit -m "feat(grafana): label the logs rules by host and container, carry the log line on the two error rules"
```

---

### Task 6: `Fleet health` board

**Files:**
- Create: `infra/grafana/fleet-health-dashboard.json`

**Interfaces:**
- Consumes: Task 2's keep-regex widening (the collector panel drops `host!="zaccess"`); Task 4's harmonised rule titles.
- Produces: uid `zcrypto-fleet` and its panel ids, which Task 10 turns into `__panelId__` pointers.

- [ ] **Step 1: Author the board**

Build every row and panel in **spec D2's "Rows and panels" table**, with D2's template variables, the two quoted expressions (the three-series load panel with per-host threshold overrides, and the three-series collector panel), and the exclusion matchers D2 lists. `graphTooltip: 1`. The restart annotation (P6). Match `zcrypto-dashboard.json`'s JSON idiom exactly.

- [ ] **Step 2: Validate structurally**

```bash
uv run python - <<'EOF'
import json, re
d = json.load(open("infra/grafana/fleet-health-dashboard.json"))
assert d["uid"] == "zcrypto-fleet" and d["title"] == "Fleet health"
assert d.get("graphTooltip") == 1, "Shared Crosshair not enabled"
assert d.get("tags") == [], f"tags must be purged, found {d.get('tags')}"
ps = [p for p in d["panels"] if p.get("type") != "row"]
for p in ps:
    for tgt in p.get("targets", []):
        e = tgt.get("expr", "")
        assert e, f"empty expr on {p['title']}"
        assert re.search(r"host\s*(=~|!=|=)", e), f"unscoped expr on {p['title']}: {e[:70]}"
print(len(ps), "panels, all host-scoped")
EOF
```

**This is a lint, not a pin.** It requires a host *matcher*, so it no longer passes on a bare `by (host)` — but it still cannot tell a correct matcher from a wrong one. And P1 legitimately produces host-unscoped expressions wherever the RULE is unscoped (the gate rules, both reconcile rules, the WireGuard rule): those panels copy the rule verbatim and must be **exempted by hand with a comment**, not "fixed" to satisfy this script.

- [ ] **Step 3: Vocabulary + glob checks**

Run: `uv run pytest tests/test_internal_terms_not_operator_visible.py -v` — expect PASS (this is where a `Phase 6`-style leak or a mis-named file is caught).

- [ ] **Step 4: Commit**

```bash
uv run pre-commit run -a
git add infra/grafana/fleet-health-dashboard.json
git commit -m "feat(grafana): add the fleet health board"
```

---

### Task 7: `Data integrity` board

**Files:**
- Create: `infra/grafana/data-integrity-dashboard.json`

**Interfaces:**
- Produces: uid `zcrypto-integrity` and its panel ids for Task 10.

- [ ] **Step 1: Author the board**

Every row and panel in **spec D3's table**, D3's three template variables, and all four quoted expressions — the `resets()`-guarded residual series, the per-desynced-pair rate with its deliberately-unscoped divisor, the summed resubscribe-failure series, and the `host=~"primary|secondary"` trade-deficit selector. Apply every "Corrections applied from review" item in D3 (they are requirements, not commentary). `graphTooltip: 1`, restart annotation.

- [ ] **Step 2: Assert the two expressions most likely to be silently wrong**

```bash
uv run python -c "
import json
d = json.load(open('infra/grafana/data-integrity-dashboard.json'))
exprs = [t.get('expr','') for p in d['panels'] for t in p.get('targets',[])]
res = [e for e in exprs if 'residual_gap_seconds_total' in e and 'increase(' in e]
assert res, 'no residual-gap delta series found'
assert all('resets(' in e for e in res), 'a residual-gap delta WITHOUT the resets() guard -- this repaints the 2026-07-14 false alarm in mirror image'
dfc = [e for e in exprs if 'trade_deficit_rows_total' in e]
assert dfc and all('primary' in e for e in dfc), 'trade deficit must select host=~\"primary|secondary\", not host=\"ops\" -- it renders empty otherwise'
print('guarded:', len(res), 'residual series;', len(dfc), 'deficit series')
"
```

- [ ] **Step 3: Run the structural check from Task 6 Step 2** against this file, changing only the path, uid (`zcrypto-integrity`) and title (`Data integrity`).

- [ ] **Step 4: Commit**

```bash
uv run pre-commit run -a
git add infra/grafana/data-integrity-dashboard.json
git commit -m "feat(grafana): add the data integrity board"
```

---

### Task 8: `Engine` board

**Files:**
- Create: `infra/grafana/engine-dashboard.json`

**Interfaces:**
- Consumes: Task 1 (absence is now real absence, so the panels render it honestly and carry no stale-weight caveat); Task 4's two new engine rules.

- [ ] **Step 1: Author the board**

Every row and panel in **spec D4's table**, including the board-head text panel naming `data/engine-journal` as the sole source of truth for realized state. Absence renders via value mappings with a neutral base step and explicit `noValue` text — never a thresholds-driven stat, which would paint absence red and invent the claim the code refuses to publish. `graphTooltip: 1`, restart annotation.

**Ship no caveat sentences about stale target weights or a false-zero duration** — Task 1 removed both defects.

- [ ] **Step 2: Assert intent is unmistakable and absence is not coloured**

```bash
uv run python -c "
import json
d = json.load(open('infra/grafana/engine-dashboard.json'))
assert d['title'] == 'Engine', d['title']
ps = [p for p in d['panels'] if p.get('type') != 'row']
order = [p for p in ps if any('orders_total' in t.get('expr','') or 'order_notional' in t.get('expr','') for t in p.get('targets',[]))]
assert order, 'no order panels found'
for p in order:
    blob = (p['title'] + ' ' + p.get('description','')).lower()
    assert 'intend' in blob, f'order panel does not say intended: {p[\"title\"]}'
txt = [p for p in ps if p.get('type') == 'text']
assert any('engine-journal' in json.dumps(p) for p in txt), 'no head text panel naming the journal'
print(len(order), 'order panels, all marked intent')
"
```

- [ ] **Step 3: Structural check + vocabulary test** — Task 6 Step 2's script with path, uid (`zcrypto-engine`) and title (`Engine`) changed, then `uv run pytest tests/test_internal_terms_not_operator_visible.py -v`.

- [ ] **Step 4: Commit**

```bash
uv run pre-commit run -a
git add infra/grafana/engine-dashboard.json
git commit -m "feat(grafana): add the engine board"
```

---

### Task 9: `Logs` board — the rate lane

**Files:**
- Modify: `infra/grafana/zcrypto-logs-dashboard.json`

- [ ] **Step 1: Add the rate lane and fix the viewer**

Add the three-panel lane from **spec D5** at the top at `h: 6` (total lines/min; by level; by host+container), plus the "last line seen" table. Make the existing `$container` variable multi-select with `includeAll` — the board already carries `host`/`container`/`level`/`search`; this task changes one, it does not add it. Retitle the board to `Logs`. Apply the query-time `| json` plus `line_format` promoting `message` to the existing viewer panel.

Keep the raw-count and `level=~".+"` series as separate first-class panels — different rules fire on each, and collapsing them sends the responder to the wrong layer.

- [ ] **Step 2: Verify the lane does not dominate**

```bash
uv run python -c "
import json
d = json.load(open('infra/grafana/zcrypto-logs-dashboard.json'))
assert d['title'] == 'Logs'
assert 'graphTooltip' not in d or d['graphTooltip'] == 0, 'Logs takes no crosshair sync'
lane = [p for p in d['panels'] if p['gridPos']['y'] < 8 and p.get('type') != 'row']
assert all(p['gridPos']['h'] <= 6 for p in lane), 'lane panel taller than h=6'
viewer = [p for p in d['panels'] if p.get('type') == 'logs']
assert viewer and any('| json' in t.get('expr','') for t in viewer[0]['targets']), 'viewer not parsing json'
print(len(lane), 'lane panels, viewer parses json')
"
```

- [ ] **Step 3: Commit**

```bash
uv run pre-commit run -a
git add infra/grafana/zcrypto-logs-dashboard.json
git commit -m "feat(grafana): add a rate lane to the logs board and parse the daemon json at query time"
```

---

### Task 10: Panel pointers on every alert rule

**Files:**
- Modify: `infra/grafana/alerts.yaml`

**Interfaces:**
- Consumes: the uids and panel ids produced by Tasks 6–9.

- [ ] **Step 1: Extract the real panel ids**

```bash
uv run python -c "
import json, pathlib
for f in sorted(pathlib.Path('infra/grafana').glob('*-dashboard.json')):
    d = json.loads(f.read_text())
    print('==', d['uid'], d['title'])
    for p in d['panels']:
        if p.get('type') != 'row':
            print(f\"   {p['id']:>4}  {p['title']}\")
"
```

- [ ] **Step 2: Add the annotations**

For each rule, add `__dashboardUid__` and `__panelId__` per the ownership recorded in spec D2/D3/D4's `serves_alert_rules` columns. **Both values are quoted strings** — an unquoted integer aborts the entire push. Where a rule's signal is genuinely not panel-shaped, give it a runbook reference instead; no rule may have neither.

- [ ] **Step 2b: Add the `unit:` annotations**

Spec D12's call #4: **selectively**, where a bare number is ambiguous — durations in seconds, byte counts, ratios, row counts. Skip boolean and presence rules, where the value is `0`/`1` and the unit is the rule. The metrics template reads `.Annotations.unit` and D12's worked example depends on one existing, so this cannot be left to the rollout.

- [ ] **Step 3: Assert every pointer resolves**

```bash
uv run python -c "
import json, pathlib, yaml
panels = {}
for f in pathlib.Path('infra/grafana').glob('*-dashboard.json'):
    d = json.loads(f.read_text())
    panels[d['uid']] = {str(p['id']) for p in d['panels'] if p.get('type') != 'row'}
bad = []
for r in yaml.safe_load(open('infra/grafana/alerts.yaml'))['rules']:
    a = r.get('annotations', {})
    uid, pid = a.get('__dashboardUid__'), a.get('__panelId__')
    if uid is None and pid is None:
        if 'runbook_url' not in a: bad.append((r['title'], 'no pointer and no runbook'))
        continue
    if not isinstance(pid, str): bad.append((r['title'], f'__panelId__ is {type(pid).__name__}, must be a quoted string'))
    elif uid not in panels: bad.append((r['title'], f'unknown dashboard uid {uid}'))
    elif pid not in panels[uid]: bad.append((r['title'], f'panel {pid} not on {uid}'))
[print('BAD:', t, '::', w) for t, w in bad]
assert not bad, f'{len(bad)} broken pointers'
print('all pointers resolve')
"
```

- [ ] **Step 4: Commit**

```bash
uv run pre-commit run -a
git add infra/grafana/alerts.yaml
git commit -m "feat(grafana): point every alert rule at the panel that shows it"
```

---

### Task 11: The coverage test

**Files:**
- Create: `tests/test_dashboards_cover_metrics.py`
- Reference (OPTIONAL, may be absent): `/tmp/claude-1000/-home-zhaow-Projects-zcrypto-kraken/9155f24a-9e4a-4274-8653-7324e91389ec/scratchpad/test_dashboards_cover_metrics.py` — a prior draft in a session scratchpad that does **not** survive a reboot. If it is gone, build from spec D8 alone; nothing here depends on it. **Read it, do not paste it**: it was written against the pre-review design (old uids, `zcrypto-main`, no `Logs` rate lane) and its baseline assumptions have changed. Its PromQL family-extraction approach and its exclusion-set structure are the parts worth reusing.

- [ ] **Step 1: Write the three assertions**

Per spec D8. Family extraction from PromQL must not mistake label values, function names (`rate`, `increase`, `sum`, `min`, `by`, `on`, `without`, `offset`, `topk`, `count`, `delta`, `resets`, `max_over_time`, `label_replace`, `vector`, `scalar`), duration literals, or label keys for families; state the approach and its failure modes in the module docstring. Every failure names the specific family and where it came from — never a bare "coverage failed".

Assertion 3 — every alerted family is keep-list admitted on the hosts its rule selects — is the load-bearing one: it derives its expectation from `alerts.yaml` rather than from the hand-curated per-host list in `test_infra_alloy_series.py`, which is exactly why that test missed the `zaccess` hole.

Add spec D9's companion assertion in the same file, because nothing in the tree checks it today: every rule resolves to a **real non-row panel** on a committed board (its `__dashboardUid__` exists, its `__panelId__` is a panel id on that board) **or** carries a runbook reference — never neither — and every `__panelId__` loads as a **string**. The string check is the one whose violation is not local: `grafana-push.sh` does `yaml.safe_load` → `json.dumps`, the provisioning API's annotations are string-valued, so an unquoted id is rejected and `curl -fsS` under `set -euo pipefail` aborts the whole push — no rules, no dashboards. Prove it the way `agent-ops.md` requires: unquote one id and watch the assertion fail.

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_dashboards_cover_metrics.py -v`
Expected: PASS. Any failure is a real gap in Tasks 6–9 — fix the dashboard, not the test. Only add an entry to the exclusion set with a written reason.

- [ ] **Step 3: PROVE assertion 3 trips (mandatory)**

```bash
infra/scripts/mutate-probe.sh \
  --file infra/ansible/roles/access/files/config.alloy \
  --mutation 's/|node_scrape_collector_success//' \
  -- uv run pytest tests/test_dashboards_cover_metrics.py -v
```

**Through `mutate-probe.sh`, never a hand-rolled sed-and-`git checkout` loop** (`agent-ops.md`): it refuses a dirty tree, refuses a no-op mutation, refuses a probe that fails on unmutated code, requires the control to fail, and neutralises the stale-`.pyc` trap.

Expected: the probe reports the mutated run FAILING and names `node_scrape_collector_success` on `zaccess`. **Read WHICH assertion fired** — a red exit from an unrelated assertion proves nothing, and this trip-proof is what pins assertion 3's semantics: an implementation that derived host expectations only from literal `host=` matchers would never trip on the *unscoped* collector rule. Do not soften this step.

- [ ] **Step 4: Commit**

```bash
uv run pre-commit run -a
git add tests/test_dashboards_cover_metrics.py
git commit -m "test(grafana): assert every alerting family is charted and admitted where its rule selects"
```

---

### Task 12: Slack notification templates

**Files:**
- Create: `infra/grafana/notification-templates/zcrypto-slack.tmpl` — the name spec D12 settles on. The template-object name derives from the basename, so a different filename is visible in the provisioning API.
- Modify: `infra/scripts/grafana-push.sh`

- [ ] **Step 1: Author both templates**

The metrics and logs Go templates verbatim from **spec D12's "The templates"** subsection, with the host display vocabulary applied to `$labels.host`, the severity glyph, the `summary` promotion, the panel-pointer link with its three-way fallback, and the log-line code fences on the logs receiver.

- [ ] **Step 2: Push them and wire the receivers**

Extend `grafana-push.sh` per spec D12's provisioning subsection: upsert the template object, then set `settings.title` / `settings.text` on both contact points to reference it. Follow the script's existing idiom — `curl -fsS` with the `auth` array, a verification read-back, and a message to stderr.

- [ ] **Step 3: Verify no internal vocabulary in the rendered output**

Run: `uv run pytest tests/test_internal_terms_not_operator_visible.py -v`. If the test's surface list does not yet cover `notification-templates/`, **add it in this task** — a new operator-visible surface joins that list and the test together.

- [ ] **Step 4: Commit**

```bash
uv run pre-commit run -a
git add infra/grafana/notification-templates infra/scripts/grafana-push.sh tests/test_internal_terms_not_operator_visible.py
git commit -m "feat(grafana): dense slack notification templates for both receivers"
```

---

### Task 13: Rollout — ATTENDED, owner-gated at every irreversible step

**Not a subagent task.** Every host-touching command runs in the main loop; the permission gate blocks ssh/sudo inside a subagent and the step dies where nobody sees the prompt.

- [ ] **Step 1: Blocker sweep** — `docs/open-topics/README.md` + `docs/memo.local.md`, presented with the rollout proposal.

- [ ] **Step 2: Derive the per-pair silence threshold**

`max_over_time(zcrypto_capture_seconds_since_last_book_message[30d])` per pair per host. Set Task 4's provisional `900` above the binding pair's natural maximum, with the ~2.4× margin the daemon's own 30 s constant uses. **Then edit the rule and commit** — the provisional value must not reach the push.

**FOUR surfaces move together, not three.** The rule's own comment lists three (the evaluator, the `for`, and the summary's stated notice period) — it was written before the boards existed. The fourth is **`data-integrity-dashboard.json` panel 102**, which hardcodes `900` in both its threshold step and its description. Miss it and the panel draws a line the page no longer fires at, on the unbackfillable capture path — the exact panel-disagrees-with-page failure P1 and P2 exist to kill. All four land in the same commit.

- [ ] **Step 3: Push dashboards + rules** — `infra/scripts/grafana-push.sh`, with **`GRAFANA_SLACK_WEBHOOK_URL` exported from the vault**. No host contact. Without it the script takes its webhook-less branch: the template object ships, the receiver wiring is silently skipped with a friendly "receivers already live" message, and every notification keeps the stock rendering — first visible at Step 5 as a baffling symptom. Verify by read-back that all four boards and all **63** rules are live (the count `alerts.yaml` carries; transiently 64 while Step 5's probe rule exists). Read the number, do not eyeball the list: a push that drops exactly one rule is invisible to any check whose expected count is stale by one.

- [ ] **Step 3b: Verify the Logs board's two unproven constructs at first push — they fail SILENTLY**

Both are on `zcrypto-logs-dashboard.json` panel 104 ("last line seen"), and neither can be settled offline.

- `label_format seen=\`{{ unixEpoch __timestamp__ }}\` | unwrap seen [26h]` — a *parse* error 400s loudly, but an **execution** error does not: it sets `__error__`, `unwrap` then drops every sample, and the panel returns **zero rows**. An empty table is the same shape as "every stream has been silent for 26 hours", which is the fleet-wide-outage reading. Open the panel and confirm it returns rows.
- `renameByName: {"Value": "Last line seen"}` silently no-ops if Grafana's Loki backend names the value field anything but `Value`. Confirm the column header reads "Last line seen" rather than "Value".

If either fails, the drop-in replacement drops both unproven constructs and keeps the panel's job (a row present = that stream existed inside the window; a row absent = it has been silent longer than any rule's window). Replace panel 104's single target with `sum by (host, container) (count_over_time({host=~"$host", container=~"$container"} [26h]))` — the `label_format` / `unwrap` stages go, and the trailing `* 1000` goes with them; change the panel's `unit` from `dateTimeAsIso` to `short`; and in the `organize` transform's `renameByName` rename the value column from `Last line seen` to what it now is, a line count over 26 h — retitling the panel to match, since "Last line seen" above a count is a false operator surface. One target, same `labelsToFields → merge → organize` chain, same `gridPos`. Further detail, if the scratch tree is still present: `.superpowers/sdd/00084-dashboards-and-notifications/task-9-report.md`. **Do not skip this because the board renders** — both failures render.

- [ ] **Step 4: Verify the first sample by VALUE, not presence** — read the new engine and capture liveness rules' current values. A rule born into an already-faulted condition bakes that into its baseline and never fires; triage a nonzero as the page it would have been.

- [ ] **Step 5: Live-fire the Slack templates** — add the probe rule `count by (host)(up) > 0` (5 instances, touches no host), read the rendered messages in `#zcrypto`, re-tune the truncation caps from what actually renders, then delete the probe rule and confirm it is gone. Fire one logs rule too — resolve messages are ON for `metrics` and OFF for `logs`, so recovery behaves differently.

- [ ] **Step 6: Converge `zaccess`** — `site.yml --limit` on that host. Native deb Alloy, ungated config copy, **no digest operand and no bake owed**. Verify `node_scrape_collector_success{host="zaccess"}` arrives.

  Then **drop `host!="zaccess"` from `Fleet health` panel 402's three series and re-push** — spec D2 stages that matcher deliberately for the pre-converge window and says to drop it once the converge lands. `zcrypto-node-collector-failed` is host-unscoped, so from this converge on it can fire for the bridgehead; leaving the matcher sends that page to the one panel that structurally excludes the host that fired. Panel 402's description names `zaccess` as structurally excluded — rewrite that sentence in the same edit. The **duration** panel (403) keeps its exclusion permanently: D10(a) admits `node_scrape_collector_success` and nothing else.

- [ ] **Step 6b: Build the engine image and mature its canary bake — START THIS RIGHT AFTER TASKS 1/1b MERGE, not here.**

Step 7 cannot run without this, and the engine role will refuse mechanically if it is skipped. Sequenced first because the bake takes hours-to-days and should mature while Tasks 2–12 proceed. **Load the `zcrypto-captures-rollout` skill and follow it** — this is a capture-image re-pin with its own discipline, not an engine step:

1. Build and push an image carrying Tasks 1 and 1b. Record its digest.
2. Pull it on `zcrypto-red` and **verify the change is in the pulled image** — run the image's own version surface; never infer from the tag.
3. Record the digest in `docs/reference/fleet-pins.md` **before** converging; the roles refuse a digest the file does not record.
4. Re-pin the **secondary** as capture (`site.yml --limit zcrypto-red -e capture_image_digest=sha256:…`).
5. Let the bake gate pass: a clean prune (read `deleted=N` — `deleted=0` is the weak form and needs explicit acceptance), ≥3 full segment-rotation hours, every abort signal clear throughout.
6. Only then is Step 7 startable. **There is no engine secondary — the secondary's capture bake IS the engine's canary gate.**

Precedent for the shape and timing: `fleet-pins.md`'s iter-119 row (`c7ed09020fe1` — red canary leg, bake, then the engine converge the following morning).

- [ ] **Step 7: Converge the engine — the live trade host.** Full `capture-deploys.md` discipline: inside a 4-hourly inter-cycle gap (00/04/08/12/16/20 UTC), digest recorded in `docs/reference/fleet-pins.md` first, the secondary's capture bake as the canary gate, `--check --diff` preview from a tree whose rendered config matches the fleet. Verify by outcome: the next `cycle-HH.json` lands with `completed_at` inside `[B, B+30 min]`, and `zcrypto_engine_cycle_duration_seconds` is **absent** until that cycle completes, then correct.

- [ ] **Step 8: Owner steps** — delete the deprecated `zcrypto-main` board in the Grafana UI; confirm no saved silence was keyed on a retitled rule.

---

### Task 14: Closeout

- [ ] **Step 1: Record measured facts** — per-host series counts after the `zaccess` widening, against `00043`'s <1k target and `00069`'s baseline (nas 144, ops 308, zcrypto 134, zcrypto-red 108). Measured, never assumed.

- [ ] **Step 2: Update `docs/reference/fleet.md`** — the access tier's converge shape: native deb Alloy pinned by `access_alloy_version`, config copied ungated every converge, no `access_alloy_digest` and no drift-assert, so a config change converges with a plain limited `site.yml`. `capture-deploys.md` does not cover this case.

- [ ] **Step 3: Update `docs/reference/fleet-pins.md`** with the engine digest.

- [ ] **Step 4: Resolve [[T0020]]** — `status: resolved`, `ripe_when` deleted, file moved to `docs/open-topics/archive/`, index bullet moved to the category's `### Resolved` with the archived path. Per `topic-ops`.

- [ ] **Step 5: Update [[T0018]]** — its metrics bullet gains the execution-panel handoff onto the `Engine` board, with the naming instruction and the do-not-rename-the-intent-families warning.

- [ ] **Step 6: Append the iterations-history entry** to the phase-6 changelog per `iteration-closeout`. Re-verify every status claim against the full branch log immediately before PR-open — an entry drafted mid-branch reads stale the moment later work lands beside it.

- [ ] **Step 7: Decisions-log entry** in the phase-6 decisions log for the design decisions the owner ruled on: board split, coverage principle, the no-defer ruling, and the naming harmonisation scope.

- [ ] **Step 8: Commit and report the branch ready.** Do not open the PR without the owner's explicit word.
