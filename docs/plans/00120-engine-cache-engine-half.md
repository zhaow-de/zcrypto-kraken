# The engine's cache, the engine-side half: the currency registration, the wiring, the restart harness, the startup pass under a restored Cache, the proxy beside the engine, and the operating rule's lift — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The engine restores its own orders and positions, entry prices included, from the Valkey set spec 00118 built, through a Sentinel-checked HAProxy beside it in its compose project, and its startup pass treats a restored order with the venue as the authority; a two-process harness against a real `valkey-server` measures every scenario the restore has; the proxy is scraped, charted and paged; and the operating rule of 2026-09-23 — no engine converge or restart while a Kraken margin position is open — becomes the operator's test on every page that carries it, lifted by the live proof the Rollout section takes.

**Architecture:** Six tasks on one branch, each a guard-proven commit. Task 1 gives `EngineConfig` its nested `cache` table with a strict arm, reads `ZCRYPTO_CACHE_PASSWORD` at node build and refuses its absence there, and registers the six Kraken currency codes the library's table lacks before a cache-backed build, since the store saves a currency as its bare code and the loader resolves it before the adapter mints it. Task 2 wires the two builder calls behind the config at ten retries under five-second timeouts, states `load_cache`, reads a restored order's fill state off `filled_qty`, and logs the boot line through the `zcrypto` logger. Task 3 brings the restart harness: `tests/test_cache_restart.py` starts a `valkey-server` per scenario, runs the engine's own node twice in a child interpreter against a loopback venue with a scripted private WebSocket peer, and pins eight scenarios of the library's own behaviour; `coverage.yml` installs the binary. Task 4 is the executor: the restored set read at construction, the venue asked over every restored row and every finished row with fills, a restored order the venue holds closed written from the report and left uncancelled, a restored opener cancelled and a ledgered reducer kept, the kept reducer's fills credited nothing and repaired from the venue at the re-read pass with its intent written at its terminal, the realized baseline, the mixed-inventory refusal, the withdrawal check reading the venue's trade history before it trips, and the docstrings rewritten. Task 5 is the engine role: the `cache-proxy` service, its config rendered under `no_log` and validated by the pinned image before it lands, `engine.env` and `zcrypto.toml`, `stop_grace_period`, the two secrets' move to `group_vars/all`, the window guard over `cache-link`, `converge.sh`'s key, the rotation's engine leg. Task 6 is telemetry and pages: the `cache_proxy` scrape and its families, the proxy's journal lines, the Cache board's proxy row, the three rules with their `cache.md` sections and the outage line, the operator's test at its anchor and its clause on every line that carries the rule, `fleet.md`, T0158's trigger and T0213's closeout. The Rollout is attended and plans one gap.

**Tech Stack:** Python 3.14 through `uv run`, pytest, the pinned `nautilus-trader` (`2.0.0rc6.dev20260921`) whose Redis backing, real orders and events the tests drive, `valkey-server` 8.1.1 on the workstation and from apt on the CI runner (the fleet runs 9.1.2), Ansible with `ansible-lint` and `yamllint`, Jinja2 renders under `StrictUndefined`, HAProxy 3.4.5 from the official image, Grafana Alloy, `infra/scripts/mutate-probe.sh` for the guard verdicts, `uv run pre-commit run -a` as the commit gate.

**Spec:** `docs/specs/00120-engine-cache-engine-half-design.md`

## Global Constraints

- The wiring's values are the spec's: `.with_cache_config(CacheConfig(use_instance_id=False, flush_on_start=False))` and `.with_cache_database_factory(RedisCacheConfig(host, port, username, password, ssl=False, connection_timeout=5, response_timeout=5, number_of_retries=10))`, appended by `_node_builder` only when `config.cache.enabled`, with `load_cache=True` stated in the execution engine's config and `load_state` and `save_state` left at their `False` defaults (spec D5). The refused shape fails inside about four seconds and the silent shape inside about a minute, the budget `tests/test_cache_restart.py` bounds at 20 and 40 to 90 seconds.
- The config table is `[zcrypto.engine.cache]` with `enabled: bool = False`, `host: str = "cache-proxy"`, `port: int = 6379`, `username: str = "engine"`; `_build_cache` refuses a non-table, an unknown key, a non-boolean `enabled`, an empty `host` or `username`, and a `port` that is a boolean or outside 1 to 65535, each with the loader's own message shape; the password is `ZCRYPTO_CACHE_PASSWORD`, read in `_node_builder` when enabled and never stored on a module object, logged or interpolated; the committed `zcrypto.toml` keeps no engine table (spec D3).
- The currencies registered before a cache-backed build are the eleven codes the basket's twelve pairs carry on Kraken's AssetPairs: the six outside the library's table, `XETH`, `XLTC`, `XXBT`, `XXDG`, `XXRP` and `ZEUR`, each `Currency(code, 8, 0, code, CurrencyType.CRYPTO)` as the adapter mints them, and the five inside it at the library's own values, `ADA` 6 `Cardano`, `AVAX` 8 `Avalanche`, `DOT` 8 `Polkadot`, `LINK` 8 `Chainlink`, `SOL` 8 `Solana` (spec D4).
- The boot line is the engine's, through the `zcrypto` logger at INFO: `cache restore: N order(s), M position(s) restored`, then per open position, whichever strategy the Cache holds it under, `cache restore: position <instrument> <signed qty> @ <avg_px_open> (<strategy>)`, an instrument's figure being its lines summed, and per open order under the engine's own id `cache restore: order <id> <state>, <filled> of <quantity> filled @ <price>`, the state read off `filled_qty` and never off the status (spec D9, D11); a cold start or an empty namespace reads `0 order(s)`, and `0 position(s) restored` with no position open, and refuses nothing (spec D12).
- The proxy's config is the spec's: three backends `node1` to `node3`, each three `server` lines at the node's mesh address on 6379 with `check addr <one Sentinel's mesh address> port 26379 inter 1s fall 2 rise 2 init-state fully-down on-marked-down shutdown-sessions`, one `tcp-check` sequence of `AUTH <requirepass>` expecting `+OK`, `PING` expecting `+PONG`, `SENTINEL master zcache` expecting the anchored `"\$2\r\nip\r\n\$10\r\n10.98.0.1N\r\n"` with the dollar escaped inside the double quotes, no `QUIT` step, `timeout check 2s`, `use_backend nodeN if { nbsrv(nodeN) ge 2 }`, the Prometheus endpoint on `127.0.0.1:9104`; the image is the official `haproxy`, 3.1 or later for `init-state`, pinned by index digest through `-e cache_proxy_image_digest=` and a `cache-proxy` row on `zcrypto` in `fleet-pins.md`; the service takes a 32m memory cap, which holds only with `maxconn 256` in `global` -- without a bound HAProxy sizes itself off the container's file-descriptor hard limit, 524288 on the fleet's containerd, and its worker is killed under the cap at load -- `json-file` logging, the config bind-mounted read-only from `/opt/zcrypto-engine/haproxy.cfg`, rendered root-owned 0600 under `no_log` and `diff: false`, validated with the pinned image's own `haproxy -c` before it is moved into place; the engine's `depends_on: cache-proxy` takes `condition: service_started` alone, and the engine service takes `stop_grace_period: 20s` (spec D1, D15).
- `cache_engine_password` and `cache_sentinel_requirepass` move verbatim from `group_vars/cache_host/vault.yml` to `group_vars/all/vault.yml`, never decrypted; the engine host holds both to the cache role's floor, five or more of `[A-Za-z0-9]`; `engine.env.j2` gains `ZCRYPTO_CACHE_PASSWORD={{ cache_engine_password }}` under its existing `no_log` render; `zcrypto.toml.j2` renders the table -- `enabled = true`, `host = "cache-proxy"`, `port = 6379`, `username = "engine"` -- behind the role default `engine_cache_enabled: true`, and `-e engine_cache_enabled=false` renders no table, the way back to an engine without the cache on any image inside the same gap; the engine window guard's tasks in `site.yml` take `tags: [engine, cache-link]`, and the `cache_link` role is held off by `when` where `engine` is skipped, since a `--skip-tags engine` run skips the guard's tasks with the engine's (spec D2, D3).
- The harness has no environment gate and takes no second skip name: `shutil.which("valkey-server")` names the binary and its absence is `pytest.fail` with `sudo apt-get install -y valkey-server`; each scenario starts its own server on a free port under its `tmp_path` with `--bind 127.0.0.1 --save "" --appendonly no --daemonize no` and an ACL file carrying the cache role's `engine` line; `coverage.yml` gains `sudo apt-get install -y valkey-server` before `uv sync`, and a runner whose apt lacks the package takes Valkey's own binary tarball, pinned by version and sha256 in the workflow, the choice made at the plan's first CI run (spec D13).
- The withdrawal check's second source is the venue's trade history (spec D19): where an order's figure -- the Cache's copy or the venue's order report -- falls short of the ledger, the pass reads the trade history once through a bare client, `request_fill_reports` from one hour before the earliest row's boundary, and trips only when the history's fills for the row's txid fall short of the ledger; a covered row keeps its figure and joins the rows the pass repaired; an unread history leaves the trip on the order's figure.
- The operating rule's pages carry the operator's test in the anchor paragraph `engine-restart-margin-position` of `infra/runbooks/engine-procedures.md` -- a restart with a margin position open is admitted when the Cache board shows the proxy routed and a session of the engine's up, and the engine's last boot line counted that position as restored -- its instrument's position lines, whichever strategy each names, summing to Kraken's figure, none at entry price 0 -- or this engine opened it after that boot, with no cache outage fired since and no restored order filled since, the executor's WARNING at the fill `a fill on restored order <id> credits nothing until the venue is read`; else close first, as today; a cold start, a lost database or a position the cache never saw keeps the failure until upstream #5065 -- and every link to it keeps pointing there, the conditional stated in one clause on each line (spec D17); the outage line beside the three rules says the store is behind after a cache outage and the next restart is taken flat (spec D14).
- No string literal added under `cli/engine/`, no ansible task name or message, no runbook line, no alert summary and no dashboard text names a spec, a decision, a topic, a phase, an iteration or a work package: `tests/test_internal_terms_not_operator_visible.py` walks them and runs in every task's consumer command; `WP<N>` appears nowhere, this plan included.
- The six tasks land in order on one branch and merge together: the counts each task's failing and passing runs state assume the tasks before it have landed, and every task's first step from the second on checks the previous task's marker.
- A fence is the exact text at its indentation in the file: a `Replace, in <path>, this block:` instruction names the whole block it replaces, which occurs exactly once in the file at that step, and a `Create <path> with this content:` instruction writes the whole file. A fence whose closing backticks sit on its last text line is a mid-line fragment with no trailing newline; a fence closed on its own line ends with a newline. A block that itself carries a line opening with three backticks is fenced with four, and its closing run is four too. Every fence was applied in task order on a scratch worktree and read back identical to the tree that produced every count and verdict below.
- A commit that adds or changes a guard records its `infra/scripts/mutate-probe.sh` verdict on that commit, earned after the commit exists and recorded by a message-only amend with the tree clean, from a file (`git commit --amend -F <file>`) and never from a double-quoted `-m` argument, inside which the shell runs each backticked name of the verdict text as a command substitution; the script refuses a dirty tree, so the probes run after Step 9 and never before Step 8. A probe's mutation changes one line of its file at its step, three excepted whose verdict names the whole it changes -- Task 5's `depends_on` block, the password floor's two asserts and `cache-link` on the window guard's four tasks -- read by applying every `--control` and `--mutation` of the plan with `sed` to the tree its task leaves.
- Every commit is green over the changed files' consumers, the list each task's Step 6 names, run locally in place of the full suite, which CI runs on every push; the restart harness is among Task 3's and Task 4's consumers and takes six to eight minutes.
- `uv run pre-commit run -a` runs the pre-commit stage alone and is clean before every commit, ansible-lint and yamllint over `infra/ansible` and mdformat over the runbooks among its hooks; `guidance-guard` and `message-citations` run at commit-msg, on `git commit`: a runbook list item the tasks write carries no universal word (every, never, always, only, any, cannot) outside code spans without a count entry, and no commit message cites a `path:line`, a `path::symbol` or a topic.
- No step reaches a fleet host, a venue, a credential or Docker: the harness runs on 127.0.0.1 alone, the role's `haproxy -c` validation runs at the rollout's converge, and the proxy's first pin and pins row are the rollout's.
- A new Markdown paragraph or list item is one line: no column wrap, no filler blank lines. An existing file's lines are left as they are, except where a step replaces them.
- A commit message ends with these two trailers, `<model>` and `<the executing session's URL>` being the executing model's own name and its session's URL, written by the executor; the task loop runs on Opus, so the commit fences say `Claude Opus 5.5`:

```
Co-Authored-By: Claude <model> <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
```

## File structure

- Modify `cli/config.py` — `CacheSettings`, `EngineConfig.cache`, `_build_cache`, `_build_engine`'s `cache` arm (Task 1).
- Modify `cli/engine/node.py` — `_CACHE_PASSWORD_VAR`, `_KRAKEN_CURRENCIES`, `_register_kraken_currencies`, `_cache_password`, the refusal in `_node_builder`, the registration in `build_shadow_node` (Task 1); the two builder calls, `load_cache`, `ShadowStrategy._log_cache_restore` and its call in `on_start` (Task 2); the strategy class's and the observer's docstrings (Task 4).
- Modify `cli/engine/executor.py` — `restored_fill_state` (Task 2); `read_venue_fills`, the restored set, the restored fills, the realized baseline, the fills read's per-pass cache, `_read_restored`, `_read_realized_baseline`, `_trades_cover`, `_venue_answers`, `_settle_restored_intent`, `_realized_on`, `_mixed_inventory_refusals`, and `_spot_balance`, the startup pass, the re-read pass, `_read_venue_orders`, `_reconcile_adopted_rows`, `_reconcile_adopted_row`, `_reconcile_finished_rows`, `_reconcile_finished_row`, `_fill_credit`, `_on_detached_event`, `_on_external_event`, `_realized_eur` and `_pickup` changed, with the docstrings (Task 4).
- Modify `tests/kraken_loopback.py` — `trade_row`, the `trades` listing, the `on_add_order` and `on_cancel_order` hooks, the four private endpoints, `WsPeer`, the three execution frames, `serve_with_sockets` (Task 3).
- Create `tests/cache_restart_child.py` and `tests/test_cache_restart.py`; generate `tests/fixtures/kraken_assetpairs_basket.json` (Task 3); the child's fourth redirect, the harness's executor assertions and the cold-start scenario's measured shape (Task 4).
- Modify `.github/workflows/coverage.yml` — the apt install (Task 3).
- Modify `tests/test_config.py`, `tests/test_engine_node.py`, `tests/test_nautilus_interface_pin.py` (Tasks 1, 2, 5); `tests/test_engine_executor.py` (Tasks 2, 4).
- Create `infra/ansible/roles/engine/templates/haproxy.cfg.j2`; modify the engine role's `compose.yaml.j2`, `engine.env.j2`, `zcrypto.toml.j2`, `defaults/main.yml`, `tasks/main.yml`; `infra/ansible/site.yml`; `infra/ansible/scripts/converge.sh`; `infra/ansible/roles/cache/tasks/main.yml`; the two vault files; `infra/runbooks/cache.md` (Task 5); create `tests/test_infra_cache_proxy.py`; modify `tests/test_infra_compose_templates.py`, `tests/test_infra_converge_guards.py` (Task 5).
- Modify `infra/ansible/roles/capture/files/config.alloy`, `infra/grafana/alerts.yaml`, `infra/grafana/cache-dashboard.json`, `infra/runbooks/cache.md`, `infra/runbooks/engine-procedures.md`, `infra/runbooks/engine.md`, `infra/runbooks/drills-order-path.md`, `infra/runbooks/order-semantics-verification.md`, `docs/reference/fleet.md`, `docs/open-topics/T0158-go-live-drill-program-execution.md`; move `docs/open-topics/T0213-engine-cache-engine-half.md` to `docs/open-topics/archive/`; render `docs/open-topics/README.md`; modify `tests/test_infra_alloy_series.py`, `tests/test_infra_alert_rules.py` (Task 6).

## Review Focus

- The restored order under its own id: every order the Cache holds for the venue is read at construction, this engine's own and the EXTERNAL copies, open or closed, attached there where the window carries its row, asked over at the venue, and cancelled or kept by the classification loop, the lines naming a restored order keyed on the own id with its fill state named -- `test_the_restored_set_is_every_order_the_cache_holds_at_construction_only_with_the_cache_enabled`, `test_a_fill_on_a_restored_row_before_the_first_tick_lands_in_its_row_and_trips_nothing`, `test_a_restored_order_the_cache_holds_closed_is_read_at_the_venue_and_the_report_wins`, `test_the_startup_pass_asks_the_venue_over_a_restored_orders_cache_copy_and_the_report_wins`, `test_a_restored_opener_the_venue_reports_open_is_cancelled_by_the_pass_and_a_kept_reducer_is_not` in `tests/test_engine_executor.py`, and `test_a_resting_order_and_a_margin_position_are_restored_across_a_restart` in `tests/test_cache_restart.py`.
- The order that closed while the engine was down: mass status reads open orders only, so the Cache's copy stays open, and the pass writes the row from the venue's report with no cancel sent -- `test_a_restored_order_the_venue_reports_closed_has_its_row_written_from_the_report_and_no_cancel_sent`, and `test_an_order_cancelled_while_the_engine_was_down_is_never_closed_by_the_library` and `test_a_fill_made_while_the_engine_was_down_is_booked_from_the_trade_history` in the harness.
- The kept reducer's double-booked fill: the library books a trade frame on a restored open order twice, and the row credits nothing until the re-read pass repairs it from the venue's cumulative figure, the intent written at the terminal -- `test_a_fill_on_a_restored_row_credits_nothing_and_the_re_read_pass_repairs_the_row_from_the_venue`, `test_a_terminal_on_a_restored_kept_reducer_writes_the_venues_state_and_its_intent`, `test_a_fill_then_a_terminal_on_a_restored_row_before_the_next_tick_is_repaired_by_the_pass`, and `test_a_trade_frame_on_a_restored_open_order_is_booked_twice_by_the_library` and `test_a_trade_frame_on_a_restored_opener_racing_the_passs_cancel_is_booked_twice_and_the_row_settles_at_the_venues_figure` in the harness.
- The cache absent or unreachable: an empty namespace is a cold start under the EXTERNAL identity, the pass cancelling as today and its withdrawal check reading the venue's trade history over the library's unfilled copy, and an unreachable cache fails inside the budget without a venue call -- `test_an_empty_cache_beside_open_ledger_rows_is_a_cold_start_the_pass_reconciles_as_today` and `test_the_cache_unreachable_at_start_fails_inside_the_budget_without_touching_the_venue` in the harness, `test_a_cold_starts_order_figure_short_of_the_ledger_is_no_withdrawal_when_the_trade_history_covers_it` and `test_a_true_withdrawal_with_no_fill_in_the_trade_history_trips_the_kill_switch_as_today` in `tests/test_engine_executor.py`, with `test_a_build_with_the_cache_enabled_registers_the_kraken_codes_a_fresh_process_cannot_resolve` in `tests/test_engine_node.py` for the registration a restore needs.
- The proxy's config and secrets: the check sequence, the anchored reply with its escaped dollar, the routing on two of three, the validation before the install, and the password floor -- `tests/test_infra_cache_proxy.py` whole, `test_the_cache_proxy_config_is_validated_before_it_is_installed_and_never_logged` and `test_the_engine_host_refuses_a_cache_password_below_the_floor_or_outside_letters_and_digits` in `tests/test_infra_converge_guards.py`, and `test_the_engine_compose_file_carries_neither_cache_secret` in `tests/test_infra_compose_templates.py`.

---

### Task 1: The config table, the password's node-build refusal and the Kraken currency registration

This task is spec D3 and D4, with one line of D5 (the password is read at node build): the nested `cache` table with its own strict arm, the password refused at node build by name when the cache is enabled and the variable absent, and the basket's Kraken currency codes registered before the node builds. The builder calls the password feeds, the retry values and the boot line are Task 2's, so this task's refusal guards a build that attaches nothing yet: what it proves is the loader and the registration, each testable alone. The engine role's template renders the table in Task 5, beside the env file whose password the table's `enabled = true` needs, so no converge between the two can render an engine that refuses to build.

What this task decides, where the spec leaves it open:

- `CacheSettings` is a frozen dataclass beside `FetchConfig` in `cli/config.py`, `EngineConfig.cache` its one nested field, and `_build_cache` the arm `_build_engine` hands the `cache` key to; every refusal names `[zcrypto.engine.cache]` and the key, the loader's message shape.
- `_KRAKEN_CURRENCIES` in `cli/engine/node.py` holds one `Currency` per distinct base and quote code the twelve basket pairs carry on Kraken's AssetPairs, eleven codes, at the value the adapter mints or the library's own table already holds: the six codes outside that table (`XETH`, `XLTC`, `XXBT`, `XXDG`, `XXRP`, `ZEUR`) as the adapter mints them, precision 8, no ISO number, the code as the name, crypto, and the five inside it (`ADA`, `AVAX`, `DOT`, `LINK`, `SOL`) as the library holds them; `Currency.register` leaves an existing entry alone, so the five are no-ops and the six are what the restore needs. Measured on the pinned wheel: a fresh interpreter's `Currency.from_str(code, strict=True)` raises `Unknown currency` for exactly the six, resolves the five, and constructing a `Currency` registers nothing.
- The registration happens in `build_shadow_node` before `.build()`, only when `config.cache.enabled`, through `_register_kraken_currencies`; the pin test runs each build in a child interpreter, since a registration is process-wide and would outlive its test.
- The password read is `_cache_password`, the trade credentials' shape: the variable's name in the refusal, the value never on a module object, logged or interpolated; `_node_builder` refuses when the cache is enabled and the variable is absent or empty.

**Files:**
- Modify: `cli/config.py` (`CacheSettings` before `EngineConfig`; `EngineConfig.cache`; `_build_cache` before `_build_engine`; `_build_engine`'s tail)
- Modify: `cli/engine/node.py` (the `nautilus_trader.model` import; `_CACHE_PASSWORD_VAR` after `_API_SECRET_VAR`; `_KRAKEN_CURRENCIES` and `_register_kraken_currencies` after `_EXTERNAL_STRATEGY_ID`; `_cache_password` after `_credentials`; `_node_builder`'s refusal; `build_shadow_node`'s registration)
- Test: `tests/test_config.py` (`CacheSettings` imported; eight cases after the tracking-band cases)
- Test: `tests/test_engine_node.py` (`CacheSettings` imported; three password cases after the credentials cases; `_CURRENCY_PROBE` and two currency cases after the build cases; `_run_build_probe` and `_node_build_facts` taking `cache_enabled`)
- Test: `tests/test_nautilus_interface_pin.py` (`Currency` and `CurrencyType` in `PINNED_SYMBOLS`; `Currency.register`, `Currency.from_str` and `CurrencyType.CRYPTO` in `PINNED_ATTRIBUTES`)

**Interfaces:**
- Consumes: `EngineConfig`, `_build_engine`, `ConfigError`, `CONFIG_TABLE` in `cli/config.py`; `_credentials`, `_node_builder`, `build_shadow_node`, `EngineError` in `cli/engine/node.py`; `_write`, `load_config` in `tests/test_config.py`; `_config`, `_record_assembly`, `_run_build_probe`, `_node_build_facts`, `node`, `_node_builder` in `tests/test_engine_node.py`; `kraken_loopback`'s `serve` and `client`, `PAIR_KEYS` in `cli/engine/store.py`.
- Produces: `CacheSettings(enabled: bool = False, host: str = "cache-proxy", port: int = 6379, username: str = "engine")` and `EngineConfig.cache`; `_build_cache(raw, config_path) -> CacheSettings`; `_CACHE_PASSWORD_VAR`, `_KRAKEN_CURRENCIES: tuple[Currency, ...]`, `_register_kraken_currencies() -> None`, `_cache_password() -> str | None` in `cli/engine/node.py`; `_run_build_probe(..., cache_enabled=False)` and `_node_build_facts(..., cache_enabled=False)` in the test module.

- [ ] **Step 1: Confirm the tree is at the spec's basis**

Run: `grep -c 'cache' cli/config.py; grep -c 'with_cache_config\|with_cache_database_factory\|RedisCacheConfig\|Currency.register' cli/engine/node.py`
Expected: `0` then `0`, the spec's own measured-basis greps (a bare `Currency` reads 2 there, two comments naming the object). Either other than 0 means the tree is not at the spec's basis; stop and report it to the controller.

- [ ] **Step 2: The failing cases in `tests/test_config.py`, `tests/test_engine_node.py` and `tests/test_nautilus_interface_pin.py`**

Replace, in `tests/test_config.py`, this block:

```python
from cli.config import (
    AppConfig,
    ConfigError,
    DataConfig,
    EngineConfig,
    FetchConfig,
```

with:

```python
from cli.config import (
    AppConfig,
    CacheSettings,
    ConfigError,
    DataConfig,
    EngineConfig,
    FetchConfig,
```

Replace, in `tests/test_config.py`, this block:

```python
def test_the_engine_role_template_renders_the_plan_cap_explicitly():
```

with:

```python
def test_the_cache_table_defaults_to_disabled_on_the_proxy(tmp_path):
    cfg = load_config(_write(tmp_path, "[zcrypto.engine]\nexec_enabled = true\n"))
    assert cfg.engine.cache == CacheSettings()
    assert (cfg.engine.cache.enabled, cfg.engine.cache.host, cfg.engine.cache.port, cfg.engine.cache.username) == (
        False,
        "cache-proxy",
        6379,
        "engine",
    )


def test_the_cache_table_reads_every_field(tmp_path):
    cfg = load_config(
        _write(tmp_path, '[zcrypto.engine.cache]\nenabled = true\nhost = "127.0.0.1"\nport = 6390\nusername = "probe"\n')
    )
    assert cfg.engine.cache == CacheSettings(enabled=True, host="127.0.0.1", port=6390, username="probe")
    assert cfg.engine.exec_enabled is False  # the nested table leaves the flat keys at their defaults


def test_the_cache_table_not_a_table_raises(tmp_path):
    with pytest.raises(ConfigError, match=r"\[zcrypto\.engine\.cache\].*must be a table"):
        load_config(_write(tmp_path, "[zcrypto.engine]\ncache = 5\n"))


def test_the_cache_table_refuses_an_unknown_key_so_the_password_can_never_be_config(tmp_path):
    with pytest.raises(ConfigError, match=r"\[zcrypto\.engine\.cache\].*unknown key\(s\): password"):
        load_config(_write(tmp_path, '[zcrypto.engine.cache]\npassword = "never-here"\n'))


def test_the_cache_enabled_flag_rejects_a_non_boolean(tmp_path):
    with pytest.raises(ConfigError, match=r"\[zcrypto\.engine\.cache\]\.enabled.*must be a boolean"):
        load_config(_write(tmp_path, "[zcrypto.engine.cache]\nenabled = 1\n"))


@pytest.mark.parametrize("key", ["host", "username"])
def test_the_cache_host_and_username_reject_an_empty_string(tmp_path, key):
    with pytest.raises(ConfigError, match=rf"\[zcrypto\.engine\.cache\]\.{key}.*must be a non-empty string"):
        load_config(_write(tmp_path, f'[zcrypto.engine.cache]\n{key} = "  "\n'))


@pytest.mark.parametrize("bad", ["true", "0", "65536", '"6379"'])
def test_the_cache_port_rejects_a_boolean_a_string_and_a_value_outside_the_port_range(tmp_path, bad):
    with pytest.raises(ConfigError, match=r"\[zcrypto\.engine\.cache\]\.port.*must be an integer between 1 and 65535"):
        load_config(_write(tmp_path, f"[zcrypto.engine.cache]\nport = {bad}\n"))


def test_the_cache_port_accepts_the_range_ends(tmp_path):
    assert load_config(_write(tmp_path, "[zcrypto.engine.cache]\nport = 1\n")).engine.cache.port == 1
    assert load_config(_write(tmp_path, "[zcrypto.engine.cache]\nport = 65535\n")).engine.cache.port == 65535


def test_the_engine_role_template_renders_the_plan_cap_explicitly():
```

Replace, in `tests/test_nautilus_interface_pin.py`, this block:

```python
    ("nautilus_trader.model", "AccountType"),
    ("nautilus_trader.model", "ClientOrderId"),
    ("nautilus_trader.model", "InstrumentId"),
```

with:

```python
    ("nautilus_trader.model", "AccountType"),
    ("nautilus_trader.model", "ClientOrderId"),
    ("nautilus_trader.model", "Currency"),
    ("nautilus_trader.model", "CurrencyType"),
    ("nautilus_trader.model", "InstrumentId"),
```

Replace, in `tests/test_nautilus_interface_pin.py`, this block:

```python
    ("nautilus_trader.adapters.kraken", "KrakenProductType", "SPOT"),
    ("nautilus_trader.adapters.kraken", "KrakenEnvironment", "LIVE"),
]
```

with:

```python
    ("nautilus_trader.adapters.kraken", "KrakenProductType", "SPOT"),
    ("nautilus_trader.adapters.kraken", "KrakenEnvironment", "LIVE"),
    # The registry calls `cli/engine/node.py` makes before a cache-backed build, and the member the
    # six Kraken codes are registered under.
    ("nautilus_trader.model", "Currency", "register"),
    ("nautilus_trader.model", "Currency", "from_str"),
    ("nautilus_trader.model", "CurrencyType", "CRYPTO"),
]
```

Replace, in `tests/test_engine_node.py`, this block:

```python
from cli.config import EngineConfig
from cli.engine import ShadowStrategy, most_recent_boundary, next_boundary, node, startup_action
```

with:

```python
from cli.config import CacheSettings, EngineConfig
from cli.engine import ShadowStrategy, most_recent_boundary, next_boundary, node, startup_action
```

Replace, in `tests/test_engine_node.py`, this block:

```python
    # And nothing on the assembly path logged them.
    assert secret not in caplog.text


# The node is assembled in a CHILD interpreter, one node per child: `zcrypto engine run` builds one
```

with:

```python
    # And nothing on the assembly path logged them.
    assert secret not in caplog.text


# --- the cache password (spec 00120 D3) ---------------------------------------------------------


def test_the_cache_password_is_never_read_while_the_cache_is_disabled(tmp_path, monkeypatch):
    # The default config: the variable is not consulted at all, so a workstation `zcrypto` command,
    # which reads the same file, never needs a password the file must never carry.
    monkeypatch.setenv(node._CACHE_PASSWORD_VAR, "a-cache-password")
    read = []

    def _tracking_password():
        read.append(True)
        return "a-cache-password"

    monkeypatch.setattr(node, "_cache_password", _tracking_password)
    _record_assembly(tmp_path, monkeypatch)
    assert read == []


def test_the_cache_enabled_with_an_empty_environment_refuses_naming_the_variable(tmp_path, monkeypatch):
    monkeypatch.delenv(node._CACHE_PASSWORD_VAR, raising=False)
    with pytest.raises(EngineError) as excinfo:
        _node_builder(_config(tmp_path, cache=CacheSettings(enabled=True)))
    assert node._CACHE_PASSWORD_VAR in str(excinfo.value)


def test_an_empty_cache_password_is_treated_as_absent(tmp_path, monkeypatch):
    monkeypatch.setenv(node._CACHE_PASSWORD_VAR, "")
    with pytest.raises(EngineError, match=node._CACHE_PASSWORD_VAR):
        _node_builder(_config(tmp_path, cache=CacheSettings(enabled=True)))


# The node is assembled in a CHILD interpreter, one node per child: `zcrypto engine run` builds one
```

Replace, in `tests/test_engine_node.py`, this block:

```python
node_module.ShadowStrategy = capturing
node_module.ExternalOrderObserver = capturing_observer
node = node_module.build_shadow_node(
    EngineConfig(store_dir=root / "store", journal_dir=root / "journal", exec_enabled=sys.argv[2] == "1")
)
(root / "facts.json").write_text(
    json.dumps(
        {
            "trader_id": str(node.trader_id),
```

with:

```python
node_module.ShadowStrategy = capturing
node_module.ExternalOrderObserver = capturing_observer
node = node_module.build_shadow_node(
    EngineConfig(
        store_dir=root / "store",
        journal_dir=root / "journal",
        exec_enabled=sys.argv[2] == "1",
        cache=CacheSettings(enabled=sys.argv[3] == "1"),
    )
)


def resolves(code):
    try:
        Currency.from_str(code, strict=True)
    except ValueError:
        return False
    return True


(root / "facts.json").write_text(
    json.dumps(
        {
            # Read after the build: which of the table's codes a strict lookup resolves in this process.
            "registered": sorted(c.code for c in node_module._KRAKEN_CURRENCIES if resolves(c.code)),
            "trader_id": str(node.trader_id),
```

Replace, in `tests/test_engine_node.py`, this block:

```python
_BUILD_PROBE = """
import asyncio, json, os, sys
from pathlib import Path

from cli.config import EngineConfig
import cli.engine.node as node_module
```

with:

```python
_BUILD_PROBE = """
import asyncio, json, os, sys
from pathlib import Path

from nautilus_trader.model import Currency

from cli.config import CacheSettings, EngineConfig
import cli.engine.node as node_module
```

Replace, in `tests/test_engine_node.py`, this block:

```python
def _run_build_probe(tmp_path: Path, *, exec_enabled: bool, credentials: tuple[str, str] | None = None):
    """Assemble the node in a child interpreter. The child's environment carries exactly the
    credentials this call names and nothing inherited, so what the build does with them is the
    only thing under test."""
    env = os.environ.copy()
    env.pop("KRAKEN_SPOT_API_KEY", None)
    env.pop("KRAKEN_SPOT_API_SECRET", None)
    if credentials is not None:
        env["KRAKEN_SPOT_API_KEY"], env["KRAKEN_SPOT_API_SECRET"] = credentials
    return subprocess.run(
        [sys.executable, "-c", _BUILD_PROBE, str(tmp_path), "1" if exec_enabled else "0"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
```

with:

```python
def _run_build_probe(
    tmp_path: Path, *, exec_enabled: bool, credentials: tuple[str, str] | None = None, cache_enabled: bool = False
):
    """Assemble the node in a child interpreter. The child's environment carries exactly the
    credentials this call names and nothing inherited, so what the build does with them is the
    only thing under test; a cache-enabled build is handed a cache password, since the build
    refuses without one and the registration under test happens before it."""
    env = os.environ.copy()
    env.pop("KRAKEN_SPOT_API_KEY", None)
    env.pop("KRAKEN_SPOT_API_SECRET", None)
    env.pop(node._CACHE_PASSWORD_VAR, None)
    if credentials is not None:
        env["KRAKEN_SPOT_API_KEY"], env["KRAKEN_SPOT_API_SECRET"] = credentials
    if cache_enabled:
        env[node._CACHE_PASSWORD_VAR] = "a-cache-password"
    return subprocess.run(
        [sys.executable, "-c", _BUILD_PROBE, str(tmp_path), "1" if exec_enabled else "0", "1" if cache_enabled else "0"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
```

Replace, in `tests/test_engine_node.py`, this block:

```python
def test_a_real_build_never_prints_the_credentials(tmp_path):
```

with:

```python
@pytest.mark.parametrize("cache_enabled", [False, True], ids=["disabled-registers-nothing", "enabled-registers-the-six"])
def test_a_build_with_the_cache_enabled_registers_the_kraken_codes_a_fresh_process_cannot_resolve(tmp_path, cache_enabled):
    """The store saves a currency as its bare code and the loader resolves it against the process's
    registry before the adapter parses AssetPairs, so a cache-backed build registers the six Kraken
    codes the library's own table lacks first; a build with the cache disabled registers nothing,
    the differential that shows the registration is the build's and not the import's."""
    facts = _node_build_facts(tmp_path, exec_enabled=False, cache_enabled=cache_enabled)
    six = ["XETH", "XLTC", "XXBT", "XXDG", "XXRP", "ZEUR"]
    five = ["ADA", "AVAX", "DOT", "LINK", "SOL"]
    assert facts["registered"] == (sorted(five + six) if cache_enabled else sorted(five))


# Every code the basket's twelve pairs carry as base or quote on Kraken's AssetPairs, read off the
# committed snapshot rather than typed, and which of them a strict lookup resolves before any
# registration; then the adapter's own parse of the mint fixture through the loopback, which mints
# the codes it meets, read back field by field.
_CURRENCY_PROBE = """
import asyncio, json, os, sys
from pathlib import Path

from nautilus_trader.model import Currency

from cli.engine.node import _KRAKEN_CURRENCIES
from cli.engine.store import PAIR_KEYS
from tests import kraken_loopback

root = Path(sys.argv[1])
snapshot = json.loads(Path("tests/fixtures/kraken_assetpairs.json").read_text())
basket_codes = sorted({snapshot[key][side] for key in PAIR_KEYS.values() for side in ("base", "quote")})


def fields(c):
    return [c.code, c.precision, c.iso4217, c.name, str(c.currency_type).rsplit(".", 1)[-1]]


def strict(code):
    try:
        return fields(Currency.from_str(code, strict=True))
    except ValueError:
        return None


before = {code: strict(code) for code in basket_codes}
with kraken_loopback.serve() as venue:
    async def parse():
        client = kraken_loopback.client(venue)
        return await client.request_instruments()

    minted = {}
    for instrument in asyncio.run(parse()):
        for currency in (instrument.base_currency, instrument.quote_currency):
            minted[currency.code] = fields(currency)
(root / "currencies.json").write_text(
    json.dumps({"basket_codes": basket_codes, "before": before, "minted": minted, "table": [fields(c) for c in _KRAKEN_CURRENCIES]})
)
os._exit(0)
"""


def test_the_currency_table_covers_the_baskets_codes_at_the_values_the_adapter_mints(tmp_path):
    """Three reads in one child, since the adapter's parse registers what it mints: the table names
    exactly the base and quote codes the twelve pairs carry; a fresh process resolves the five the
    library's table holds at the table's values and none of the other six; and the adapter's parse
    of the mint fixture mints `ZEUR`, `XXBT` and `SOL` at the table's values, the rule -- precision
    8, no ISO number, the code as the name, crypto -- every one of the six follows. A bump that
    reshapes a minted currency is red here before a store carrying it loads."""
    result = subprocess.run(
        [sys.executable, "-c", _CURRENCY_PROBE, str(tmp_path)], capture_output=True, text=True, timeout=120, cwd=Path.cwd()
    )
    recorded = tmp_path / "currencies.json"
    detail = f"exit={result.returncode}\n--- stdout ---\n{result.stdout[-2000:]}\n--- stderr ---\n{result.stderr[-2000:]}"
    assert recorded.exists(), f"the currency probe produced no result: {detail}"
    facts = json.loads(recorded.read_text())
    table = {row[0]: row for row in facts["table"]}

    assert (
        sorted(table)
        == facts["basket_codes"]
        == ["ADA", "AVAX", "DOT", "LINK", "SOL", "XETH", "XLTC", "XXBT", "XXDG", "XXRP", "ZEUR"]
    )
    resolved = {code: row for code, row in facts["before"].items() if row is not None}
    assert sorted(resolved) == ["ADA", "AVAX", "DOT", "LINK", "SOL"], detail
    assert all(resolved[code] == table[code] for code in resolved), (resolved, table)
    assert facts["minted"] == {code: table[code] for code in ("SOL", "XXBT", "ZEUR")}, (facts["minted"], table)
    for code in ("XETH", "XLTC", "XXBT", "XXDG", "XXRP", "ZEUR"):
        assert table[code] == [code, 8, 0, code, "CRYPTO"], table[code]


def test_a_real_build_never_prints_the_credentials(tmp_path):
```

- [ ] **Step 3: Run the three files and watch the new cases fail**

Run: `uv run pytest tests/test_config.py tests/test_nautilus_interface_pin.py tests/test_engine_node.py -q -p no:cacheprovider`
Expected: `2 errors`, the run interrupted at collection -- `ImportError: cannot import name 'CacheSettings' from 'cli.config'` for `tests/test_config.py` and for `tests/test_engine_node.py` -- so no case of the three files runs; the pin file's five new entries pass against the library once collection completes, at Step 5, and its `test_the_pin_covers_every_nautilus_name_cli_imports` holds either way, since the pin may carry names `cli/` does not import yet.

- [ ] **Step 4: The table in `cli/config.py`, the refusal and the registration in `cli/engine/node.py`**

Replace, in `cli/config.py`, this block:

```python
@dataclass(frozen=True)
class EngineConfig:
    """Operational tuning for the `zcrypto engine` shadow node. Each field overrides a built-in
    default via the [zcrypto.engine] table in zcrypto.toml."""
```

with:

```python
@dataclass(frozen=True)
class CacheSettings:
    """The engine's cache-database backing, the [zcrypto.engine.cache] table: `enabled` attaches it
    at node build, and `host`, `port` and `username` name the proxy the engine reaches it through.
    The password is no field of this file's: it is read from the environment at node build, so a
    workstation command reading the same file never needs one."""

    enabled: bool = False
    host: str = "cache-proxy"
    port: int = 6379
    username: str = "engine"


@dataclass(frozen=True)
class EngineConfig:
    """Operational tuning for the `zcrypto engine` shadow node. Each field overrides a built-in
    default via the [zcrypto.engine] table in zcrypto.toml; `cache` is its one nested table."""
```

Replace, in `cli/config.py`, this block:

```python
    tracking_band_bps: float | None = None


@dataclass(frozen=True)
class DataConfig:
```

with:

```python
    tracking_band_bps: float | None = None
    cache: CacheSettings = CacheSettings()


@dataclass(frozen=True)
class DataConfig:
```

Replace, in `cli/config.py`, this block:

```python
def _build_engine(table: dict, config_path: Path) -> EngineConfig:
    raw = table.get("engine", {})
```

with:

```python
def _build_cache(raw: object, config_path: Path) -> CacheSettings:
    if not isinstance(raw, dict):
        raise ConfigError(f"[{CONFIG_TABLE}.engine.cache] in {config_path} must be a table")
    known = {f.name for f in fields(CacheSettings)}
    unknown = sorted(set(raw) - known)
    if unknown:
        raise ConfigError(f"[{CONFIG_TABLE}.engine.cache] in {config_path} has unknown key(s): {', '.join(unknown)}")

    overrides: dict = {}

    if "enabled" in raw:
        value = raw["enabled"]
        if not isinstance(value, bool):
            raise ConfigError(f"[{CONFIG_TABLE}.engine.cache].enabled in {config_path} must be a boolean")
        overrides["enabled"] = value

    for name in ("host", "username"):
        if name not in raw:
            continue
        value = raw[name]
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"[{CONFIG_TABLE}.engine.cache].{name} in {config_path} must be a non-empty string")
        overrides[name] = value

    if "port" in raw:
        value = raw["port"]
        # bool is a subclass of int — reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
            raise ConfigError(f"[{CONFIG_TABLE}.engine.cache].port in {config_path} must be an integer between 1 and 65535")
        overrides["port"] = value

    return CacheSettings(**overrides)


def _build_engine(table: dict, config_path: Path) -> EngineConfig:
    raw = table.get("engine", {})
```

Replace, in `cli/config.py`, this block:

```python
        overrides["settle_delay_secs"] = value

    return EngineConfig(**overrides)
```

with:

```python
        overrides["settle_delay_secs"] = value

    if "cache" in raw:
        overrides["cache"] = _build_cache(raw["cache"], config_path)

    return EngineConfig(**overrides)
```

Replace, in `cli/engine/node.py`, this block:

```python
from nautilus_trader.model import AccountId, AccountType, StrategyId, TraderId
```

with:

```python
from nautilus_trader.model import AccountId, AccountType, Currency, CurrencyType, StrategyId, TraderId
```

Replace, in `cli/engine/node.py`, this block:

```python
_API_KEY_VAR = "KRAKEN_SPOT_API_KEY"
_API_SECRET_VAR = "KRAKEN_SPOT_API_SECRET"
```

with:

```python
_API_KEY_VAR = "KRAKEN_SPOT_API_KEY"
_API_SECRET_VAR = "KRAKEN_SPOT_API_SECRET"
# The cache password's variable, rendered onto the engine host beside the two above and read the
# same way: by name, never a value in a message.
_CACHE_PASSWORD_VAR = "ZCRYPTO_CACHE_PASSWORD"
```

Replace, in `cli/engine/node.py`, this block:

```python
_EXTERNAL_STRATEGY_ID = StrategyId("EXTERNAL")
```

with:

```python
_EXTERNAL_STRATEGY_ID = StrategyId("EXTERNAL")
# Every base and quote code the basket's twelve pairs carry on Kraken's AssetPairs, at the value the
# adapter mints for it: the store saves a currency as its bare code and the loader resolves that code
# against this process's registry before the adapter has parsed AssetPairs, so a code the library's
# own table lacks -- the six Kraken spellings -- fails the load of every instrument, order and
# position priced in it. The five the table holds are registered at the library's own values, which
# `Currency.register` leaves in place. tests/test_engine_node.py pins the set and each value against
# the adapter's parse, so a bump that reshapes a minted currency is red before a store carrying it
# loads; a registration that disagreed with the adapter would poison its instruments, since a
# registered code is read rather than minted.
_KRAKEN_CURRENCIES: tuple[Currency, ...] = (
    Currency("ADA", 6, 0, "Cardano", CurrencyType.CRYPTO),
    Currency("AVAX", 8, 0, "Avalanche", CurrencyType.CRYPTO),
    Currency("DOT", 8, 0, "Polkadot", CurrencyType.CRYPTO),
    Currency("LINK", 8, 0, "Chainlink", CurrencyType.CRYPTO),
    Currency("SOL", 8, 0, "Solana", CurrencyType.CRYPTO),
    Currency("XETH", 8, 0, "XETH", CurrencyType.CRYPTO),
    Currency("XLTC", 8, 0, "XLTC", CurrencyType.CRYPTO),
    Currency("XXBT", 8, 0, "XXBT", CurrencyType.CRYPTO),
    Currency("XXDG", 8, 0, "XXDG", CurrencyType.CRYPTO),
    Currency("XXRP", 8, 0, "XXRP", CurrencyType.CRYPTO),
    Currency("ZEUR", 8, 0, "ZEUR", CurrencyType.CRYPTO),
)


def _register_kraken_currencies() -> None:
    """Register each of `_KRAKEN_CURRENCIES`, leaving one the registry already holds as it is."""
    for currency in _KRAKEN_CURRENCIES:
        Currency.register(currency)
```

Replace, in `cli/engine/node.py`, this block:

```python
    api_key = os.environ.get(_API_KEY_VAR, "")
    api_secret = os.environ.get(_API_SECRET_VAR, "")
    if not api_key or not api_secret:
        return None
    return api_key, api_secret
```

with:

```python
    api_key = os.environ.get(_API_KEY_VAR, "")
    api_secret = os.environ.get(_API_SECRET_VAR, "")
    if not api_key or not api_secret:
        return None
    return api_key, api_secret


def _cache_password() -> str | None:
    """The cache password read from the environment, or None when absent or empty, on `_credentials`'
    terms: handed straight to the backing's config and never stored, logged or interpolated."""
    return os.environ.get(_CACHE_PASSWORD_VAR, "") or None
```

Replace, in `cli/engine/node.py`, this block:

```python
def _node_builder(config: EngineConfig) -> LiveNodeBuilder:
    """`exec_enabled` alone decides whether this engine may reach the venue's private side: off, the
    credentials are never read; on with either variable absent, this REFUSES rather than substituting a
    placeholder that would defer the failure to the first submission."""
    builder = (
        LiveNode.builder(name=_NODE_NAME, trader_id=TraderId(_TRADER_ID), environment=Environment.LIVE)
        .with_logging(_logging_config())
        .with_exec_engine_config(_exec_engine_config())
        .add_data_client(name=KRAKEN, factory=KrakenDataClientFactory(), config=_data_client_config())
    )
```

with:

```python
def _node_builder(config: EngineConfig) -> LiveNodeBuilder:
    """`exec_enabled` alone decides whether this engine may reach the venue's private side: off, the
    credentials are never read; on with either variable absent, this REFUSES rather than substituting a
    placeholder that would defer the failure to the first submission. `cache.enabled` reads the cache
    password the same way, and refuses here rather than in the loader, which every workstation
    command runs over a file that must never carry a password."""
    builder = (
        LiveNode.builder(name=_NODE_NAME, trader_id=TraderId(_TRADER_ID), environment=Environment.LIVE)
        .with_logging(_logging_config())
        .with_exec_engine_config(_exec_engine_config())
        .add_data_client(name=KRAKEN, factory=KrakenDataClientFactory(), config=_data_client_config())
    )
    if config.cache.enabled and _cache_password() is None:
        raise EngineError(
            f"the cache is enabled but its password is missing: {_CACHE_PASSWORD_VAR} must be set and non-empty; "
            "refusing to build the node"
        )
```

Replace, in `cli/engine/node.py`, this block:

```python
def build_shadow_node(config: EngineConfig) -> LiveNode:
    """Assembles the shadow node without reaching the network -- nothing connects until `node.run()` -- and hands
    the observer THIS strategy's forwarder, because the filter scoping external events is the executor's and
    a strategy wired without one drops them."""
    node = _node_builder(config).build()
```

with:

```python
def build_shadow_node(config: EngineConfig) -> LiveNode:
    """Assembles the shadow node without reaching the network -- nothing connects until `node.run()` -- and hands
    the observer THIS strategy's forwarder, because the filter scoping external events is the executor's and
    a strategy wired without one drops them. With the cache enabled the Kraken currency codes are registered
    first: the store's records resolve their codes at the load `node.run()` makes before the adapter mints them."""
    if config.cache.enabled:
        _register_kraken_currencies()
    node = _node_builder(config).build()
```

- [ ] **Step 5: Run the three files and watch them pass**

Run: `uv run pytest tests/test_config.py tests/test_nautilus_interface_pin.py tests/test_engine_node.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `225 passed, 2 skipped` when this plan was written, the skips `tests/test_engine_node.py`'s two live-venue gates.

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_config.py tests/test_engine_node.py tests/test_engine_command.py tests/test_engine_metrics.py tests/test_engine_executor.py tests/test_engine_stub_fidelity.py tests/test_nautilus_interface_pin.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `1547 passed, 2 skipped` when this plan was written, the skips `tests/test_engine_node.py`'s two live-venue gates.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 8: Commit**

```bash
git add cli/config.py cli/engine/node.py tests/test_config.py tests/test_engine_node.py tests/test_nautilus_interface_pin.py
git commit -m "feat(engine): the cache table in the config, the password refused at node build, and the Kraken currency codes registered before a cache-backed build

Measured on 2026-09-28 on the pinned wheel against a local Valkey 8.1.1: the store saves a currency
as its bare code, and a fresh process's loader resolves that code against a registry the adapter has
not yet filled, so a restore fails on every Kraken instrument with Unknown currency ZEUR; with the
codes registered before the node builds the restore works. EngineConfig gains one nested frozen
dataclass, cache, from [zcrypto.engine.cache], with its own strict arm: a non-table, an unknown key,
a non-boolean enabled, an empty host or username, and a port that is a boolean or outside 1 to
65535 are each refused with the loader's own message shape, and the committed zcrypto.toml keeps
no engine table. The password is ZCRYPTO_CACHE_PASSWORD, read at node build when the cache is
enabled through the trade credentials' shape, the variable named in the refusal and the value
never stored, logged or interpolated; its absence refuses to build the node rather than failing the
loader every workstation command runs. Before a cache-backed build, build_shadow_node registers
the eleven base and quote codes the basket's twelve pairs carry on Kraken's AssetPairs, the six
outside the library's own table at the value the adapter mints for them and the five inside it at
the library's own, which the registry keeps.

Cases: the table's defaults and every field read; a non-table, an unknown key -- password among
them, so it can never be config -- a non-boolean enabled, an empty host or username, and a port
that is a boolean, a string or outside the range refused, the range ends accepted; the password
never read while the cache is disabled, refused by name when absent or empty; a build with the
cache enabled registering the six codes a fresh process cannot resolve and a disabled build
registering none; and the table's eleven codes equal to the basket's AssetPairs codes, the five the
library holds resolving at the table's values before any registration, the six not, and the
adapter's own parse of the mint fixture minting ZEUR, XXBT and SOL at the table's values.

PROBE_VERDICT

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>"
```

- [ ] **Step 9: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 10: Prove the guards with seven probes, then record their verdicts by a message-only amend**

The loader's control misspells the cache table's key so every table case fails. The mutations, in order: the port's upper bound dropped; the boolean port admitted; the unknown-key refusal dropped; the empty-string refusal dropped. The node's control drops the refusal's variable name so the naming cases fail; its mutations: the registration made unconditional, so a disabled build registers the six; the registration dropped, so an enabled build registers none; the password read while the cache is disabled. Each `-k` selects the task's cases from the file it names:

```bash
K1="cache_table or cache_enabled or cache_host or cache_port"
infra/scripts/mutate-probe.sh --file cli/config.py --control 's/if "cache" in raw:/if "cachee" in raw:/' \
  --mutation 's/not 1 <= value <= 65535/not 1 <= value/' \
  -- uv run pytest tests/test_config.py -q -p no:cacheprovider -k "$K1"
infra/scripts/mutate-probe.sh --file cli/config.py --control 's/if "cache" in raw:/if "cachee" in raw:/' \
  --mutation 's/if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:/if not isinstance(value, int) or not 1 <= value <= 65535:/' \
  -- uv run pytest tests/test_config.py -q -p no:cacheprovider -k "$K1"
infra/scripts/mutate-probe.sh --file cli/config.py --control 's/if "cache" in raw:/if "cachee" in raw:/' \
  --mutation '/^def _build_cache/,/^def _build_engine/s/^    if unknown:$/    if False:/' \
  -- uv run pytest tests/test_config.py -q -p no:cacheprovider -k "$K1"
infra/scripts/mutate-probe.sh --file cli/config.py --control 's/if "cache" in raw:/if "cachee" in raw:/' \
  --mutation '/^def _build_cache/,/^def _build_engine/s/if not isinstance(value, str) or not value.strip():/if False:/' \
  -- uv run pytest tests/test_config.py -q -p no:cacheprovider -k "$K1"
K2="cache_password or cache_enabled or registers_the_kraken or currency_table"
infra/scripts/mutate-probe.sh --file cli/engine/node.py --control 's/the cache is enabled but its password is missing: {_CACHE_PASSWORD_VAR}/the cache is enabled but its password is missing/' \
  --mutation 's/^    if config.cache.enabled:$/    if True:/' \
  -- uv run pytest tests/test_engine_node.py -q -p no:cacheprovider -k "$K2"
infra/scripts/mutate-probe.sh --file cli/engine/node.py --control 's/the cache is enabled but its password is missing: {_CACHE_PASSWORD_VAR}/the cache is enabled but its password is missing/' \
  --mutation 's/^        _register_kraken_currencies()$/        pass/' \
  -- uv run pytest tests/test_engine_node.py -q -p no:cacheprovider -k "$K2"
infra/scripts/mutate-probe.sh --file cli/engine/node.py --control 's/the cache is enabled but its password is missing: {_CACHE_PASSWORD_VAR}/the cache is enabled but its password is missing/' \
  --mutation 's/if config.cache.enabled and _cache_password() is None:/if _cache_password() is None and config.cache.enabled:/' \
  -- uv run pytest tests/test_engine_node.py -q -p no:cacheprovider -k "$K2"
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message with the text below: write the whole message, that line replaced, to a file under `.tmp/` (gitignored) and amend from it with `git commit --amend -F <that file>` -- the Global Constraints' rule, never `--amend -m "…"`, inside which the shell runs each backticked name below as a command:

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/config.py`, control the cache key misspelled so
every table case fails, through `-k "cache_table or cache_enabled or cache_host or cache_port"`:
the port's upper bound dropped, KILLED, control proven; the boolean port admitted, KILLED, control
proven; the unknown-key refusal dropped, KILLED, control proven; the empty-string refusal dropped,
KILLED, control proven; over `cli/engine/node.py`, control the refusal's variable name dropped,
through `-k "cache_password or cache_enabled or registers_the_kraken or currency_table"`: the
registration made unconditional, KILLED, control proven; the registration dropped, KILLED, control
proven; the password read while the cache is disabled, KILLED, control proven.
```

Run: `git status --porcelain` -- Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` -- Expected: `0`; `git log -1 --format=%B | grep -c 'infra/scripts/mutate-probe.sh'` -- Expected: `1`, the verdict naming the script.

---
### Task 2: The library wiring, the interface pin and the boot line

This task is spec D5, D9's predicate and D11: the two builder calls behind `cache.enabled` at the retry values the probes settled, `load_cache` stated beside the exec engine's five, the interface pin widened by what `cli/` now imports and states, `restored_fill_state` as the one predicate D9 names, and the boot line through the `zcrypto` logger at INFO. The predicate's other site, the classification's cancel line, is Task 4's; `_ADOPTED_TERMINAL_STATES` maps closed statuses alone, so the regressed status writes no state and no third site reads it.

What this task decides, where the spec leaves it open:

- The wiring is inside `_node_builder`, in the arm Task 1 left as a bare refusal: the password is read once, handed to `RedisCacheConfig` and never held; the cache arm comes before the exec-client arm, and with `enabled` false neither builder method is called, which the recorder pins.
- `restored_fill_state(order)` lives in `cli/engine/executor.py`, since the executor's classification line is its other caller and the node already imports from there; it reads `filled_qty` against `quantity` on `_OVERFILL_TOLERANCE`'s dead band and never the status: `filled` at or above the quantity, `partial` inside, `open` at none. The library's regression is pinned beside it: a partially filled real `LimitOrder` handed `OrderAccepted(reconciliation=True)` reads ACCEPTED while the predicate reads `partial`.
- The boot line is `ShadowStrategy._log_cache_restore`, called from `on_start` after the alert chain is seeded and before the executor is built, only when `cache.enabled`: with the cache disabled no line is written, so an operator reading the line knows the store was attached. It reads the open orders under this strategy's id, `orders_open(strategy_id=...)`, so an order reconciliation created under `EXTERNAL` on a cold start is not counted as restored, and every open position whatever its strategy, `positions_open()`, sorted by instrument and strategy: a fill made while the engine was down beside a restored position leaves that position at its stored quantity and reconciliation books the gap to the venue's figure under `EXTERNAL` (Task 3's fill-while-down scenario), so an instrument's figure, the proof's comparand, is its lines summed, and a boot at entry price 0 shows its 0 whatever strategy holds the position; a read that raises logs one ERROR and `on_start` carries on. Its lines: `cache restore: N order(s), M position(s) restored`, then `cache restore: position <instrument> <signed qty> @ <avg_px_open> (<strategy>)` per open position and `cache restore: order <id> <fill state>, <filled> of <quantity> filled @ <price>` per order, each a separate INFO record so the Logs board's search box `cache restore` finds them all.
- The test stub `_exec_stub` gains `cache` and `strategy_id`, and binds `_log_cache_restore` lazily, so the cases that never enable the cache are untouched by a method the stub does not need.

**Files:**
- Modify: `cli/engine/node.py` (the `nautilus_trader.common` import; the `nautilus_trader.infrastructure` import; the `cli.engine.executor` import; `_exec_engine_config`'s docstring and `load_cache`; `_node_builder`'s cache arm; `_log_cache_restore` after `_snapshot_venue_state`; `on_start`'s call)
- Modify: `cli/engine/executor.py` (`restored_fill_state` after `_ordered_qty`)
- Test: `tests/test_engine_node.py` (`RecordingBuilder`'s two methods; `_exec_stub`'s two fields and the lazy bind; the recorder case's `load_cache` line and the knob parametrisation's row; `test_every_builder_call_exists_on_the_library` recording a cache-backed assembly; four wiring cases after `test_the_builder_is_given_no_exec_client_by_default`; four boot-line cases after `test_on_start_registers_no_exec_tick_without_a_factory`)
- Test: `tests/test_engine_executor.py` (`restored_fill_state` imported; two cases after `test_a_below_costmin_result_names_the_floor`)
- Test: `tests/test_nautilus_interface_pin.py` (`CacheConfig` and `RedisCacheConfig` in `PINNED_SYMBOLS`; `load_cache` in the exec-engine defaults case; three cases after `test_the_inflight_defaults_we_now_state_explicitly_are_unchanged`)

**Interfaces:**
- Consumes: `CacheSettings`, `_cache_password`, `_CACHE_PASSWORD_VAR`, `_node_builder`, `EngineError`, `_exec_engine_config` in `cli/engine/node.py`; `_OVERFILL_TOLERANCE` in `cli/engine/executor.py`; `RecordingBuilder`, `_record_assembly`, `_exec_stub`, `FakeClock`, `_config`, `node` in `tests/test_engine_node.py`; `_resting_limit_order`, `_fill`, `_event`, `OrderAccepted`, `OrderStatus` in `tests/test_engine_executor.py`.
- Produces: `restored_fill_state(order) -> str` in `cli/engine/executor.py`; `ShadowStrategy._log_cache_restore()`; `_exec_stub(config, clock, *, executor_factory=None, executor=None, cache=None, strategy_id=None)`; `RecordingBuilder.with_cache_config` and `.with_cache_database_factory`.

- [ ] **Step 1: Confirm Task 1 has landed and the node is at the spec's basis**

Run: `grep -c '_register_kraken_currencies' cli/engine/node.py; grep -c 'with_cache_config' cli/engine/node.py`
Expected: `2` then `0`, the definition and its call. A first count other than 2 means Task 1 is not on the branch; a second other than 0 means the wiring already exists; stop and report either to the controller.

- [ ] **Step 2: The failing cases in `tests/test_engine_node.py`, `tests/test_engine_executor.py` and `tests/test_nautilus_interface_pin.py`**

Replace, in `tests/test_engine_node.py`, this block:

```python
    def add_exec_client(self, name, factory, config):
        return self._record("add_exec_client", name=name, factory=factory, config=config)

    def named(self, call_name):
```

with:

```python
    def add_exec_client(self, name, factory, config):
        return self._record("add_exec_client", name=name, factory=factory, config=config)

    def with_cache_config(self, config):
        return self._record("with_cache_config", config=config)

    def with_cache_database_factory(self, factory):
        return self._record("with_cache_database_factory", factory=factory)

    def named(self, call_name):
```

Replace, in `tests/test_engine_node.py`, this block:

```python
def _exec_stub(config, clock, *, executor_factory=None, executor=None):
    """A ShadowStrategy stand-in driven through the unbound methods (the house pattern of
    test_schedule_alert_sets_state_and_timer): a real instance's `clock` is readonly until the
    nautilus registration this suite never performs."""
    stub = types.SimpleNamespace(
        clock=clock,
        _engine_config=config,
        _now=lambda: B08 + timedelta(minutes=5),
        _run_cycle_fn=lambda cycle_ts, *, config, venue_state=None: None,
        _snapshot_venue_state=lambda: None,
        _next_cycle_ts=None,
        _executor_factory=executor_factory,
        _executor=executor,
        socket_subscriptions=[],
    )
    stub.subscribe_socket_state = lambda: stub.socket_subscriptions.append("all")
```

with:

```python
def _exec_stub(config, clock, *, executor_factory=None, executor=None, cache=None, strategy_id=None):
    """A ShadowStrategy stand-in driven through the unbound methods (the house pattern of
    test_schedule_alert_sets_state_and_timer): a real instance's `clock` is readonly until the
    nautilus registration this suite never performs. `cache` and `strategy_id` are what the boot
    line reads, bound lazily so a case that never enables the cache reads neither."""
    stub = types.SimpleNamespace(
        clock=clock,
        _engine_config=config,
        _now=lambda: B08 + timedelta(minutes=5),
        _run_cycle_fn=lambda cycle_ts, *, config, venue_state=None: None,
        _snapshot_venue_state=lambda: None,
        _next_cycle_ts=None,
        _executor_factory=executor_factory,
        _executor=executor,
        socket_subscriptions=[],
        cache=cache,
        strategy_id=strategy_id,
    )
    stub.subscribe_socket_state = lambda: stub.socket_subscriptions.append("all")
    stub._log_cache_restore = lambda: ShadowStrategy._log_cache_restore(stub)
```

Replace, in `tests/test_engine_node.py`, this block:

```python
def test_on_start_registers_no_exec_tick_without_a_factory(tmp_path):
    clock = FakeClock()
    stub = _exec_stub(_config(tmp_path), clock)
    ShadowStrategy.on_start(stub)
    assert clock.timers == []
    assert stub._executor is None
    assert stub.socket_subscriptions == []
```

with:

```python
def test_on_start_registers_no_exec_tick_without_a_factory(tmp_path):
    clock = FakeClock()
    stub = _exec_stub(_config(tmp_path), clock)
    ShadowStrategy.on_start(stub)
    assert clock.timers == []
    assert stub._executor is None
    assert stub.socket_subscriptions == []


# --- the boot line (spec 00120 D11) -------------------------------------------------------------


def _restore_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("cache restore")]


def test_on_start_writes_no_restore_line_while_the_cache_is_disabled(tmp_path, caplog):
    stub = _exec_stub(_config(tmp_path), FakeClock())
    with caplog.at_level(logging.INFO, logger="zcrypto.engine.node"):
        ShadowStrategy.on_start(stub)
    assert _restore_lines(caplog) == []


def test_on_start_reads_the_orders_under_this_strategys_id_and_writes_the_zero_line_on_an_empty_namespace(tmp_path, caplog):
    """A cold start or an empty namespace reads zero and is no refusal; the order read is scoped to
    this strategy's id, so an order reconciliation created under EXTERNAL is not counted as
    restored, and the position read takes every strategy's; and the line comes after the alert
    chain is seeded and before the executor is built."""
    reads: list = []
    cache = types.SimpleNamespace(
        orders_open=lambda **kw: reads.append(("orders", kw)) or [],
        positions_open=lambda **kw: reads.append(("positions", kw)) or [],
    )
    clock = FakeClock()

    def factory(strategy):
        reads.append("executor built")
        return RecordingExecutor()

    stub = _exec_stub(
        _config(tmp_path, cache=CacheSettings(enabled=True)),
        clock,
        executor_factory=factory,
        cache=cache,
        strategy_id="ShadowStrategy-000",
    )
    with caplog.at_level(logging.INFO, logger="zcrypto.engine.node"):
        ShadowStrategy.on_start(stub)
    assert _restore_lines(caplog) == ["cache restore: 0 order(s), 0 position(s) restored"]
    assert reads == [
        ("orders", {"strategy_id": "ShadowStrategy-000"}),
        ("positions", {}),
        "executor built",
    ]
    assert [name for name, _, _ in clock.alerts] == ["shadow-cycle-2026-07-10T12"]


def test_on_start_writes_each_restored_position_and_order_at_the_values_the_proof_reads(tmp_path, caplog):
    """The proof's comparand: every open position the Cache holds, whichever strategy holds it -- the
    gap a fill made while the engine was down leaves to the venue's figure is booked under EXTERNAL --
    with its instrument, signed quantity, entry price and strategy, and each order's fill state off
    `filled_qty`, its filled and ordered quantity and its price, one INFO record each under the
    search box's prefix."""
    held = [
        types.SimpleNamespace(instrument_id="SOL/EUR.KRAKEN", signed_qty=0.4, avg_px_open=150.0, strategy_id="ShadowStrategy-000"),
        types.SimpleNamespace(instrument_id="SOL/EUR.KRAKEN", signed_qty=0.3, avg_px_open=150.0, strategy_id="EXTERNAL"),
    ]
    order = types.SimpleNamespace(client_order_id="O-20260928-201651-001-000-1", filled_qty=0.4, quantity=1.0, price=150.0)
    cache = types.SimpleNamespace(
        orders_open=lambda **kw: [order],
        positions_open=lambda strategy_id=None, **kw: [p for p in held if strategy_id in (None, p.strategy_id)],
    )
    stub = _exec_stub(
        _config(tmp_path, cache=CacheSettings(enabled=True)), FakeClock(), cache=cache, strategy_id="ShadowStrategy-000"
    )
    with caplog.at_level(logging.INFO, logger="zcrypto.engine.node"):
        ShadowStrategy.on_start(stub)
    assert _restore_lines(caplog) == [
        "cache restore: 1 order(s), 2 position(s) restored",
        "cache restore: position SOL/EUR.KRAKEN 0.3 @ 150.0 (EXTERNAL)",
        "cache restore: position SOL/EUR.KRAKEN 0.4 @ 150.0 (ShadowStrategy-000)",
        "cache restore: order O-20260928-201651-001-000-1 partial, 0.4 of 1.0 filled @ 150.0",
    ]
    assert {r.levelno for r in caplog.records if r.getMessage().startswith("cache restore")} == {logging.INFO}


def test_a_cache_the_boot_line_cannot_read_logs_one_error_and_on_start_carries_on(tmp_path, caplog):
    def boom(**kw):
        raise RuntimeError("cache blew up")

    cache = types.SimpleNamespace(orders_open=boom, positions_open=boom)
    clock = FakeClock()
    executor = RecordingExecutor()
    stub = _exec_stub(
        _config(tmp_path, cache=CacheSettings(enabled=True)),
        clock,
        executor_factory=lambda strategy: executor,
        cache=cache,
        strategy_id="ShadowStrategy-000",
    )
    with caplog.at_level(logging.INFO, logger="zcrypto.engine.node"):
        ShadowStrategy.on_start(stub)
    assert [r.levelno for r in caplog.records if r.getMessage().startswith("cache restore")] == [logging.ERROR]
    assert stub._executor is executor and [name for name, _, _ in clock.alerts] == ["shadow-cycle-2026-07-10T12"]
```

Replace, in `tests/test_engine_node.py`, this block:

```python
    assert exec_engine.inflight_check_interval_ms == 2000
    assert exec_engine.inflight_check_threshold_ms == 5000
    assert exec_engine.inflight_check_retries == 5

    data_client = recorder.named("add_data_client")[0]
```

with:

```python
    assert exec_engine.inflight_check_interval_ms == 2000
    assert exec_engine.inflight_check_threshold_ms == 5000
    assert exec_engine.inflight_check_retries == 5
    # The restore itself: the library's default, stated because a flip would leave a backing
    # attached that nothing loads from.
    assert exec_engine.load_cache is True

    data_client = recorder.named("add_data_client")[0]
```

Replace, in `tests/test_engine_node.py`, this block:

```python
        ("inflight_check_interval_ms", 2000, 3000),
        ("inflight_check_threshold_ms", 5000, 7000),
        ("inflight_check_retries", 5, 7),
    ],
)
def test_the_engine_config_states_each_exec_knob_rather_than_inheriting_it(monkeypatch, field, stated, flipped):
```

with:

```python
        ("inflight_check_interval_ms", 2000, 3000),
        ("inflight_check_threshold_ms", 5000, 7000),
        ("inflight_check_retries", 5, 7),
        ("load_cache", True, False),
    ],
)
def test_the_engine_config_states_each_exec_knob_rather_than_inheriting_it(monkeypatch, field, stated, flipped):
```

Replace, in `tests/test_engine_node.py`, this block:

```python
def test_the_builder_is_given_no_exec_client_by_default(tmp_path, monkeypatch):
    recorder = _record_assembly(tmp_path, monkeypatch).recorder
    assert recorder.named("add_exec_client") == []
    assert [call["name"] for call in recorder.named("add_data_client")] == ["KRAKEN"]
```

with:

```python
def test_the_builder_is_given_no_exec_client_by_default(tmp_path, monkeypatch):
    recorder = _record_assembly(tmp_path, monkeypatch).recorder
    assert recorder.named("add_exec_client") == []
    assert [call["name"] for call in recorder.named("add_data_client")] == ["KRAKEN"]


# --- the cache backing (spec 00120 D5) ----------------------------------------------------------


def test_the_builder_is_given_no_cache_backing_by_default(tmp_path, monkeypatch):
    # `enabled = false` renders nothing into the node: neither builder method is called.
    monkeypatch.setenv(node._CACHE_PASSWORD_VAR, "a-cache-password")
    recorder = _record_assembly(tmp_path, monkeypatch).recorder
    assert recorder.named("with_cache_config") == [] and recorder.named("with_cache_database_factory") == []


def test_the_builder_is_given_the_cache_backing_at_the_measured_budget_when_enabled(tmp_path, monkeypatch):
    """The two calls, once each: the cache config at the library's own two defaults, stated because
    `True` on the first reloads an empty namespace and on the second issues FLUSHDB; the backing at
    the proxy's address from the config, the password from the environment, and the budget the
    probes settled -- ten retries under five-second timeouts, 3.4 s on a refused port and about
    55 s on a silent peer, inside the gap and above the second a proxy takes to mark its backends."""
    from nautilus_trader.infrastructure import RedisCacheConfig

    monkeypatch.setenv(node._CACHE_PASSWORD_VAR, "a-cache-password")
    recorder = _record_assembly(
        tmp_path, monkeypatch, cache=CacheSettings(enabled=True, host="10.98.0.1", port=6390, username="probe")
    ).recorder

    [cache_call] = recorder.named("with_cache_config")
    assert (cache_call["config"].use_instance_id, cache_call["config"].flush_on_start) == (False, False)
    [factory_call] = recorder.named("with_cache_database_factory")
    factory = factory_call["factory"]
    assert isinstance(factory, RedisCacheConfig)
    assert (factory.host, factory.port, factory.username, factory.password) == ("10.98.0.1", 6390, "probe", "a-cache-password")
    assert (factory.ssl, factory.connection_timeout, factory.response_timeout, factory.number_of_retries) == (False, 5, 5, 10)


def test_the_cache_arm_comes_before_the_exec_client_and_the_data_only_node_still_takes_it(tmp_path, monkeypatch):
    monkeypatch.setenv(node._CACHE_PASSWORD_VAR, "a-cache-password")
    monkeypatch.setenv(node._API_KEY_VAR, "a-key")
    monkeypatch.setenv(node._API_SECRET_VAR, "a-secret")
    calls = [
        name
        for name, _ in _record_assembly(tmp_path, monkeypatch, exec_enabled=True, cache=CacheSettings(enabled=True)).recorder.calls
    ]
    assert calls == [
        "with_logging",
        "with_exec_engine_config",
        "add_data_client",
        "with_cache_config",
        "with_cache_database_factory",
        "add_exec_client",
    ]
    data_only = [name for name, _ in _record_assembly(tmp_path, monkeypatch, cache=CacheSettings(enabled=True)).recorder.calls]
    assert data_only == [
        "with_logging",
        "with_exec_engine_config",
        "add_data_client",
        "with_cache_config",
        "with_cache_database_factory",
    ]


def test_a_cache_backed_assembly_never_logs_the_password(tmp_path, monkeypatch, caplog):
    secret = "cache-password-sentinel"
    monkeypatch.setenv(node._CACHE_PASSWORD_VAR, secret)
    with caplog.at_level(logging.DEBUG):
        recorder = _record_assembly(tmp_path, monkeypatch, cache=CacheSettings(enabled=True)).recorder
    [factory_call] = recorder.named("with_cache_database_factory")
    assert secret not in repr(factory_call["factory"]) and secret not in str(factory_call["factory"])
    assert secret not in caplog.text
```

Replace, in `tests/test_engine_node.py`, this block:

```python
    from nautilus_trader.live import LiveNodeBuilder

    monkeypatch.setenv(node._API_KEY_VAR, "a-key")
    monkeypatch.setenv(node._API_SECRET_VAR, "a-secret")
    recorder = _record_assembly(tmp_path, monkeypatch, exec_enabled=True).recorder
    called = {name for name, _ in recorder.calls}
    assert called, "the recorder saw no builder calls -- it is no longer standing in for anything"
```

with:

```python
    from nautilus_trader.live import LiveNodeBuilder

    monkeypatch.setenv(node._API_KEY_VAR, "a-key")
    monkeypatch.setenv(node._API_SECRET_VAR, "a-secret")
    monkeypatch.setenv(node._CACHE_PASSWORD_VAR, "a-cache-password")
    # Every arm on: the exec client's and the cache's, so both of the cache's calls are recorded.
    recorder = _record_assembly(tmp_path, monkeypatch, exec_enabled=True, cache=CacheSettings(enabled=True)).recorder
    called = {name for name, _ in recorder.calls}
    assert called >= {"with_cache_config", "with_cache_database_factory"}, sorted(called)
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
from cli.engine.executor import ProbeExecutor, read_venue_orders, set_executor_hooks, size_probe_order
```

with:

```python
from cli.engine.executor import ProbeExecutor, read_venue_orders, restored_fill_state, set_executor_hooks, size_probe_order
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
def test_a_below_costmin_result_names_the_floor():
    """The fail-open direction: a matched EUR pair that clears ordermin but falls under the EUR
    costmin floor. A costmin drop (e.g. costmin=0.0) must not survive this test."""
    result = size_probe_order(0.001, 100.0, _constraints())
    assert isinstance(result, BelowMinimum)
    assert "costmin" in result.reason
```

with:

```python
def test_a_below_costmin_result_names_the_floor():
    """The fail-open direction: a matched EUR pair that clears ordermin but falls under the EUR
    costmin floor. A costmin drop (e.g. costmin=0.0) must not survive this test."""
    result = size_probe_order(0.001, 100.0, _constraints())
    assert isinstance(result, BelowMinimum)
    assert "costmin" in result.reason


# --- a restored order's fill state (spec 00120 D9) ----------------------------------------------


@pytest.mark.parametrize(
    "fills, expected",
    [
        ([], "open"),
        ([0.4], "partial"),
        ([0.4, 0.6], "filled"),
        ([0.3, 0.3, 0.4], "filled"),  # three per-fill floats an ulp short of the quantity still read filled
    ],
)
def test_a_restored_orders_fill_state_is_read_off_its_filled_quantity(fills, expected):
    order = _resting_limit_order("O-1")
    for n, qty in enumerate(fills):
        order.apply(_fill("O-1", qty, trade_id=f"T-{n}"))
    assert restored_fill_state(order) == expected


def test_reconciliation_regresses_a_partially_filled_orders_status_and_the_predicate_does_not_follow_it():
    """Measured on the pinned wheel: reconciliation appends `OrderAccepted(reconciliation=True)` to
    a restored order that was PARTIALLY_FILLED, since Kraken's `open` maps to ACCEPTED whatever
    `vol_exec` says, so the status reads open where the fills say partial."""
    order = _resting_limit_order("O-1")
    order.apply(_fill("O-1", 0.4))
    assert order.status == OrderStatus.PARTIALLY_FILLED
    order.apply(_event(OrderAccepted, client_order_id="O-1", reconciliation=True))
    assert order.status == OrderStatus.ACCEPTED
    assert restored_fill_state(order) == "partial"
```

Replace, in `tests/test_nautilus_interface_pin.py`, this block:

```python
    ("nautilus_trader.adapters.kraken", "KrakenSpotHttpClient"),
    ("nautilus_trader.common", "Environment"),
    ("nautilus_trader.common", "LogLevel"),
    ("nautilus_trader.common", "SocketState"),
    ("nautilus_trader.config", "LiveExecutionEngineConfig"),
    ("nautilus_trader.config", "LoggerConfig"),
    ("nautilus_trader.live", "LiveNode"),
```

with:

```python
    ("nautilus_trader.adapters.kraken", "KrakenSpotHttpClient"),
    ("nautilus_trader.common", "CacheConfig"),
    ("nautilus_trader.common", "Environment"),
    ("nautilus_trader.common", "LogLevel"),
    ("nautilus_trader.common", "SocketState"),
    ("nautilus_trader.config", "LiveExecutionEngineConfig"),
    ("nautilus_trader.config", "LoggerConfig"),
    ("nautilus_trader.infrastructure", "RedisCacheConfig"),
    ("nautilus_trader.live", "LiveNode"),
```

Replace, in `tests/test_nautilus_interface_pin.py`, this block:

```python
    assert config.allow_overfills is False, (
        "also inherited, and cli/engine/executor.py names it in the paragraph bounding what covers "
        "a fill that did not happen: upstream's check_overfill, with this False, refuses an "
        "application past the order's own quantity. True removes one of the three bounds that "
        "paragraph and specs 00098 and 00100 rest on"
    )
```

with:

```python
    assert config.allow_overfills is False, (
        "also inherited, and cli/engine/executor.py names it in the paragraph bounding what covers "
        "a fill that did not happen: upstream's check_overfill, with this False, refuses an "
        "application past the order's own quantity. True removes one of the three bounds that "
        "paragraph and specs 00098 and 00100 rest on"
    )
    assert config.load_cache is True, (
        "stated by cli/engine/node.py since spec 00120, so the default no longer reaches production; "
        "a flip would turn the stated value into a divergence worth re-deriving"
    )
```

Replace, in `tests/test_nautilus_interface_pin.py`, this block:

```python
def test_a_position_report_refuses_a_none_side():
```

with:

```python
def test_the_cache_config_defaults_we_state_are_unchanged():
    """`cli/engine/node.py` states both at the library's own values: `True` on the first reloads an
    empty namespace and on the second issues FLUSHDB, so the pin says whether the statement is
    still a restatement."""
    from nautilus_trader.common import CacheConfig

    config = CacheConfig()
    assert config.use_instance_id is False
    assert config.flush_on_start is False


def test_the_node_config_defaults_we_leave_off_are_unchanged():
    """Strategy state is not restored: the ledger is the executor's state, and both stay at the
    library's own off, inherited, so a flip would restore state nothing here designed for."""
    from nautilus_trader.live import LiveNodeConfig

    config = LiveNodeConfig()
    assert config.load_state is False
    assert config.save_state is False


def test_the_redis_cache_config_accepts_the_arguments_we_pass_and_hides_the_password():
    from nautilus_trader.infrastructure import RedisCacheConfig

    secret = "cache-password-sentinel"
    config = RedisCacheConfig(
        host="cache-proxy",
        port=6379,
        username="engine",
        password=secret,
        ssl=False,
        connection_timeout=5,
        response_timeout=5,
        number_of_retries=10,
    )
    assert config.password == secret  # the value reaches the backing
    assert secret not in repr(config) and secret not in str(config)


def test_a_position_report_refuses_a_none_side():
```

- [ ] **Step 3: Run the three files and watch the new cases fail**

Run: `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider`, then `uv run pytest tests/test_engine_node.py tests/test_nautilus_interface_pin.py -q -p no:cacheprovider`
Expected: the first `1 error`, interrupted at collection on `ImportError: cannot import name 'restored_fill_state' from 'cli.engine.executor'`, so the predicate's cases are read at Step 5; the second `8 failed, 170 passed, 2 skipped`: the three boot-line cases that enable the cache, on no `cache restore` line where one is expected (`assert [] == [...]`) and, for the unreadable-cache case, on `assert [] == [40]`; the knob case's `load_cache` arm on `assert False == True`, the stand-in flipping a default the config does not name; `test_the_builder_is_given_the_cache_backing_at_the_measured_budget_when_enabled` and `test_the_cache_arm_comes_before_the_exec_client_and_the_data_only_node_still_takes_it` on the recorder seeing no cache call; `test_a_cache_backed_assembly_never_logs_the_password` on the same empty unpack; and `test_every_builder_call_exists_on_the_library` on `assert called >= {...}`. `test_on_start_writes_no_restore_line_while_the_cache_is_disabled`, `test_the_builder_is_given_no_cache_backing_by_default` and the pin file's five new cases pass on the old tree, which calls nothing and writes nothing.

- [ ] **Step 4: The wiring and the boot line in `cli/engine/node.py`, the predicate in `cli/engine/executor.py`**

Replace, in `cli/engine/executor.py`, this block:

```python
    try:
        return float(row.get("order", {}).get("qty"))
    except AttributeError, TypeError, ValueError:
        return 0.0
```

with:

```python
    try:
        return float(row.get("order", {}).get("qty"))
    except AttributeError, TypeError, ValueError:
        return 0.0


def restored_fill_state(order) -> str:
    """How far a restored order has filled, read off `filled_qty` against `quantity` and never off its
    status: reconciliation appends `OrderAccepted(reconciliation=True)` to a partially filled restored
    order, since Kraken's `open` maps to ACCEPTED whatever `vol_exec` says, so the status reads open
    where the fills say partial. `filled` at or above the quantity, on the sweep's dead band; `partial`
    inside it; `open` at none."""
    filled = float(order.filled_qty)
    if filled >= float(order.quantity) - _OVERFILL_TOLERANCE:
        return "filled"
    return "partial" if filled > _OVERFILL_TOLERANCE else "open"
```

Replace, in `cli/engine/node.py`, this block:

```python
from nautilus_trader.common import Environment, LogLevel
from nautilus_trader.config import LiveExecutionEngineConfig, LoggerConfig
from nautilus_trader.live import LiveNode, LiveNodeBuilder
```

with:

```python
from nautilus_trader.common import CacheConfig, Environment, LogLevel
from nautilus_trader.config import LiveExecutionEngineConfig, LoggerConfig
from nautilus_trader.infrastructure import RedisCacheConfig
from nautilus_trader.live import LiveNode, LiveNodeBuilder
```

Replace, in `cli/engine/node.py`, this block:

```python
from cli.engine.executor import _TICK_SECONDS, ProbeExecutor
```

with:

```python
from cli.engine.executor import _TICK_SECONDS, ProbeExecutor, restored_fill_state
```

Replace, in `cli/engine/node.py`, this block:

```python
    def on_start(self) -> None:
        on_start_logic(
            now=self._now(),
            config=self._engine_config,
            schedule_alert=self._schedule_alert,
            run_cycle_fn=self._run_cycle_fn,
            snapshot_fn=self._snapshot_venue_state,
        )
        if self._executor_factory is not None:
```

with:

```python
    def _log_cache_restore(self) -> None:
        """The boot line, through the `zcrypto` logger at INFO since the library's own restore lines
        are INFO and dropped at ingest, read here after the load and the reconciliation and before
        the executor is built. The counts, then every position the Cache holds open, whichever
        strategy holds it, with its instrument, signed quantity, entry price and strategy: a fill
        made while the engine was down beside a restored position leaves that position at its stored
        quantity and reconciliation books the gap to the venue's figure under EXTERNAL, so the lines
        of one instrument sum to the Cache's net there -- the proof's comparand against Kraken's
        positions page -- and a boot at entry price 0, which passes every other read, shows its 0.
        Then each open order under this strategy's id, the restored ones, with its id, fill state
        off `filled_qty`, filled and ordered quantity and price; an order reconciliation created
        under EXTERNAL is not this strategy's and is not counted. A read that raises logs and
        returns: the line is evidence, never a gate."""
        try:
            orders = list(self.cache.orders_open(strategy_id=self.strategy_id))
            positions = sorted(self.cache.positions_open(), key=lambda p: (str(p.instrument_id), str(p.strategy_id)))
        except Exception:
            logger.exception("cache restore: the Cache could not be read at start")
            return
        logger.info("cache restore: %d order(s), %d position(s) restored", len(orders), len(positions))
        for position in positions:
            logger.info(
                "cache restore: position %s %s @ %s (%s)",
                position.instrument_id,
                position.signed_qty,
                position.avg_px_open,
                position.strategy_id,
            )
        for order in orders:
            logger.info(
                "cache restore: order %s %s, %s of %s filled @ %s",
                order.client_order_id,
                restored_fill_state(order),
                order.filled_qty,
                order.quantity,
                getattr(order, "price", None),
            )

    def on_start(self) -> None:
        on_start_logic(
            now=self._now(),
            config=self._engine_config,
            schedule_alert=self._schedule_alert,
            run_cycle_fn=self._run_cycle_fn,
            snapshot_fn=self._snapshot_venue_state,
        )
        if self._engine_config.cache.enabled:
            # After the alert chain, before the executor: the line reads what the load and the
            # reconciliation left, which the executor's own startup pass then acts on.
            self._log_cache_restore()
        if self._executor_factory is not None:
```

Replace, in `cli/engine/node.py`, this block:

```python
def _exec_engine_config() -> LiveExecutionEngineConfig:
    """Every knob explicit (all five are library defaults) because all five are load-bearing here.
    Reconciliation is live exactly when exec_enabled flips on at deployment.
```

with:

```python
def _exec_engine_config() -> LiveExecutionEngineConfig:
    """Every knob explicit (all six are library defaults) because all six are load-bearing here.
    Reconciliation is live exactly when exec_enabled flips on at deployment. `load_cache` is the
    restore itself: with a backing attached, `run()` loads the store's orders, positions and
    instruments before any client connects and reconciliation matches them by venue order id; the
    node config's `load_state` and `save_state` stay off, the ledger being the executor's state.
```

Replace, in `cli/engine/node.py`, this block:

```python
    return LiveExecutionEngineConfig(
        reconciliation=True,
        filter_unclaimed_external_orders=False,
```

with:

```python
    return LiveExecutionEngineConfig(
        reconciliation=True,
        load_cache=True,
        filter_unclaimed_external_orders=False,
```

Replace, in `cli/engine/node.py`, this block:

```python
    if config.cache.enabled and _cache_password() is None:
        raise EngineError(
            f"the cache is enabled but its password is missing: {_CACHE_PASSWORD_VAR} must be set and non-empty; "
            "refusing to build the node"
        )
```

with:

```python
    if config.cache.enabled:
        password = _cache_password()
        if password is None:
            raise EngineError(
                f"the cache is enabled but its password is missing: {_CACHE_PASSWORD_VAR} must be set and non-empty; "
                "refusing to build the node"
            )
        # Both values equal the library's defaults and are stated because `True` on the first reloads
        # an empty namespace and on the second issues FLUSHDB. The backing is created at `run()`,
        # before any venue client connects, so an unreachable cache fails the start without the
        # venue being touched; ten retries under five-second timeouts refuse a port that answers
        # nothing in about 3.4 s and a peer that accepts and stays silent in about 55 s, the
        # start-order guard behind the proxy's `service_started` and inside the inter-cycle gap.
        builder = builder.with_cache_config(CacheConfig(use_instance_id=False, flush_on_start=False)).with_cache_database_factory(
            RedisCacheConfig(
                host=config.cache.host,
                port=config.cache.port,
                username=config.cache.username,
                password=password,
                ssl=False,
                connection_timeout=5,
                response_timeout=5,
                number_of_retries=10,
            )
        )
```

- [ ] **Step 5: Run the three files and watch them pass**

Run: `uv run pytest tests/test_engine_node.py tests/test_engine_executor.py tests/test_nautilus_interface_pin.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `516 passed, 2 skipped` when this plan was written, the skips `tests/test_engine_node.py`'s two live-venue gates.

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_config.py tests/test_engine_node.py tests/test_engine_command.py tests/test_engine_metrics.py tests/test_engine_executor.py tests/test_engine_execledger.py tests/test_engine_stub_fidelity.py tests/test_nautilus_interface_pin.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `1604 passed, 2 skipped` when this plan was written, the skips `tests/test_engine_node.py`'s two live-venue gates.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 8: Commit**

```bash
git add cli/engine/executor.py cli/engine/node.py tests/test_engine_executor.py tests/test_engine_node.py tests/test_nautilus_interface_pin.py
git commit -m "feat(engine): the cache backing wired behind the config at ten retries, load_cache stated, the restored fill state read off filled_qty, and the boot line through the zcrypto logger

Measured on 2026-09-28 on the pinned wheel: .build() touches no cache and run() creates the
backing before any venue client connects, raising RuntimeError failed to create cache database
backing at 0.22 s on a refused port and 35 s on a silent peer under six retries, the refused
shape's delay growing about as 3.3 ms times 2^N, 3.40 s at ten and 27.75 s at thirteen, while the
library's defaults stayed blocked past 540 s; so the node attaches CacheConfig with
use_instance_id and flush_on_start stated at their defaults and a RedisCacheConfig at the proxy's
address from the config, the password from the environment, ssl off and ten retries under
five-second timeouts, only when the cache is enabled, and states load_cache beside the exec
engine's five. Reconciliation regresses a partially filled restored order's status to ACCEPTED,
so restored_fill_state reads filled_qty against quantity and never the status, the one predicate
the boot line and the executor's sites share. The library's own restore lines are INFO and dropped
at ingest, so the boot line is the engine's: at on_start, after the alert chain and before the
executor, the counts, every open position whichever strategy holds it with its instrument, signed
quantity, entry price and strategy, then each order restored under this strategy's id with its id,
fill state, quantities and price, INFO records under the search box's prefix, a cold start reading zero, a read that
raises logging one ERROR; with the cache disabled no line is written. The interface pin gains the
two config classes, the cache config's two defaults, the node config's two the engine leaves off,
and the backing's constructor with the password hidden from its repr.

Cases: no cache call by default; the two calls once each at the config's address, the
environment's password and the measured budget; the cache arm before the exec client's on a
data-only and an executing assembly; the password absent from a DEBUG-level assembly log and from
the factory's repr; the boot line absent with the cache disabled, reading zero on an empty
namespace, the orders read under this strategy's id and the positions under every strategy, after
the alert chain and before the executor, each position and order at the proof's values, an
EXTERNAL position beside the own one listed, and one ERROR on a Cache that cannot be read with on_start
carrying on; the predicate's four fill shapes and the regression it does not follow; load_cache
stated rather than inherited.

PROBE_VERDICT

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>"
```

- [ ] **Step 9: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 10: Prove the guards with seven probes, then record their verdicts by a message-only amend**

The node's control shortens the boot line's prefix so every boot-line case fails. The mutations, in order: the retry count at six; `load_cache` dropped; the boot line written with the cache disabled; the order read unscoped, every strategy's orders counted; the position read scoped to this strategy's id, the EXTERNAL position unlisted; the boot line's read failure re-raised. The executor's control flips the predicate's `filled` reading so the fill-state cases fail; its mutation reads the status. Each `-k` selects the task's cases from the file it names:

```bash
K1="cache_backing or cache_arm or never_logs_the_password or restore_line or zero_line or restored_position or boot_line or exec_knob"
C1='s/"cache restore: %d order(s), %d position(s) restored"/"cache restor: %d order(s), %d position(s) restored"/'
infra/scripts/mutate-probe.sh --file cli/engine/node.py --control "$C1" \
  --mutation 's/number_of_retries=10,/number_of_retries=6,/' \
  -- uv run pytest tests/test_engine_node.py -q -p no:cacheprovider -k "$K1"
infra/scripts/mutate-probe.sh --file cli/engine/node.py --control "$C1" \
  --mutation '/^        load_cache=True,$/d' \
  -- uv run pytest tests/test_engine_node.py -q -p no:cacheprovider -k "$K1"
infra/scripts/mutate-probe.sh --file cli/engine/node.py --control "$C1" \
  --mutation 's/^        if self._engine_config.cache.enabled:$/        if True:/' \
  -- uv run pytest tests/test_engine_node.py -q -p no:cacheprovider -k "$K1"
infra/scripts/mutate-probe.sh --file cli/engine/node.py --control "$C1" \
  --mutation 's/orders = list(self.cache.orders_open(strategy_id=self.strategy_id))/orders = list(self.cache.orders_open())/' \
  -- uv run pytest tests/test_engine_node.py -q -p no:cacheprovider -k "$K1"
infra/scripts/mutate-probe.sh --file cli/engine/node.py --control "$C1" \
  --mutation 's/positions = sorted(self.cache.positions_open(), key=/positions = sorted(self.cache.positions_open(strategy_id=self.strategy_id), key=/' \
  -- uv run pytest tests/test_engine_node.py -q -p no:cacheprovider -k "$K1"
infra/scripts/mutate-probe.sh --file cli/engine/node.py --control "$C1" \
  --mutation 's/            logger.exception("cache restore: the Cache could not be read at start")/            raise/' \
  -- uv run pytest tests/test_engine_node.py -q -p no:cacheprovider -k "$K1"
K2="restored_orders_fill_state or regresses_a_partially_filled"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control 's/        return "filled"$/        return "full"/' \
  --mutation 's/    return "partial" if filled > _OVERFILL_TOLERANCE else "open"/    return "partial" if order.status == OrderStatus.PARTIALLY_FILLED else "open"/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K2"
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message with the text below: write the whole message, that line replaced, to a file under `.tmp/` (gitignored) and amend from it with `git commit --amend -F <that file>` -- the Global Constraints' rule, never `--amend -m "…"`, inside which the shell runs each backticked name below as a command:

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/engine/node.py`, control the boot line's prefix
shortened so every boot-line case fails, through
`-k "cache_backing or cache_arm or never_logs_the_password or restore_line or zero_line or restored_position or boot_line or exec_knob"`:
the retry count at six, KILLED, control proven; load_cache dropped, KILLED, control proven; the
boot line written with the cache disabled, KILLED, control proven; the order read unscoped,
KILLED, control proven; the position read scoped to this strategy's id, KILLED, control proven;
the boot line's read failure re-raised, KILLED, control proven; over
`cli/engine/executor.py`, control the predicate's filled reading flipped, through
`-k "restored_orders_fill_state or regresses_a_partially_filled"`: the fill state read off the
status, KILLED, control proven.
```

Run: `git status --porcelain` -- Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` -- Expected: `0`; `git log -1 --format=%B | grep -c 'infra/scripts/mutate-probe.sh'` -- Expected: `1`, the verdict naming the script.

---
### Task 3: The two-process restart harness against a real `valkey-server`

This task is spec D13 whole, with D12's cold-start scenario and D5's failure budget as scenarios: `tests/test_cache_restart.py` starts a `valkey-server` per scenario, runs the engine's own node in a child interpreter against a loopback venue with a scripted private WebSocket peer, stops it, and runs it again over the store the first run left. It is cut before the executor task on purpose: every scenario here asserts the library's own behaviour across the restart and the boot line of Task 2, measured green on a tree with no executor change, so Task 4's changes are read against a harness whose readings are already the library's and not its own; Task 4 extends these scenarios with the executor's assertions. The loopback gains what a credentialed MARGIN client calls at connect and at reconciliation (`GetWebSocketsToken`, `TradeBalance`, `TradesHistory` paged by `ofs`, `AddOrder` and `CancelOrder` hooks) and the peer, `coverage.yml` gains the apt install, and a twelve-pair AssetPairs fixture is generated once, since the committed snapshot's rows lack the ten fields the adapter's parser reads.

What this task decides, where the spec leaves it open:

- The harness is `tests/test_cache_restart.py` and the child `tests/cache_restart_child.py`, both outside the `test_engine_*.py` glob `tests/test_engine_stub_fidelity.py` walks: the child is a process, not a double, and the strategy it subclasses is the engine's own class under the engine's own name, since the store keys every order and position under a strategy id derived from that class name.
- Each scenario starts its own server on a free port under its `tmp_path` with `--bind 127.0.0.1 --save "" --appendonly no --daemonize no` and an ACL file carrying the `engine` line read off `infra/ansible/roles/cache/templates/users.acl.j2` at its harness password, plus an `admin` user the harness reads keys through; `shutil.which("valkey-server")` names the binary and its absence is `pytest.fail` with `sudo apt-get install -y valkey-server`, no skip and no environment name, the skip-gate contract untouched.
- The child takes one JSON argument, redirects the two client configs, the gate's venue reader and the three bare-client reads to the loopback, and exits 3 before building if any production default remains -- the `_no_production_venue_read` fixture's rule for a node that runs; it hands the executor a real `QuoteTick` on a timer, since the data peer sends none, stops the node by a time alert at the window's end, and writes a record the test reads: every own and external order event, the Cache's orders and positions at start and at the window's end, the metrics hook's readings, the child's errors and `run()`'s wall time.
- The twelve-pair fixture `tests/fixtures/kraken_assetpairs_basket.json` is generated by the fenced script below, not fenced whole: the two rows the mint fixture already carries verbatim, the ten others the committed snapshot's row plus the parser's ten fields at the executor tests' generic precisions; its sha256 is pinned in Step 4, so a regeneration that differs is caught.
- Windows: a phase-one node runs 14 s and a phase-two node 16 s -- the startup pass and the plan pickup on the first tick at 5 s, the first quote a second later, the fill frames within a second of the submission, the re-read pass on the tick after the pass's cancel -- and every node adds the library's ten-second residual wait at stop; the whole file ran in 369 s on the workstation, its eight scenarios each a minute or two, and the plan's Step 5 names that number so a run twice as long is read as a hang.
- Two readings measured while writing this task are recorded here because a scenario's assertions rest on them. A fill made while the engine was down lands on the restored order (`filled_qty` 0.7 of 1.0, status regressed to ACCEPTED), while the restored position keeps its stored quantity (0.4) and the library closes the gap to the venue's position report with a synthesized EXTERNAL order and position of 0.3 (`Generating reconciliation order for SOL/EUR.KRAKEN: side=Buy, qty=0.30000000`); the net is 0.7, which the executor's position gauge publishes, and the boot line lists both positions, the own 0.4 and the EXTERNAL 0.3, whose sum is the figure the proof reads against Kraken's positions page. With nothing stored -- the order resting unfilled at the stop and 0.3 filled at 149.5 while the engine was down, A2's shape, run as a scratch case on this harness -- the fill is booked onto the restored order and the position opens under the own strategy at 0.3 @ 149.5, no EXTERNAL and no `Unresolved positions` line. And a cold start over a resting opener that had partially filled (ledger 0.4, the venue's open row at `vol_exec` 0.4, one `TradesHistory` row) is today's executor tripping its kill switch: the library creates the EXTERNAL copy at ACCEPTED with `filled_qty` 0 -- its mass status reads `Received 1 order(s), 1 fill(s)` and applies `fills=0` -- and the pass's adopted-row reconcile reads that copy, trips `shows 0 filled at the venue, less than the 0.4 this engine has already recorded` and cancels under the kill's reason; the 0.4 then arrives as `OrderFilled(reconciliation=True)` from the cancel ack's frame. The cold-start scenario pinned here rests the opener unfilled, the shape D12 names, and Task 4 moves it to the measured partial-fill shape under spec D19, the owner's ruling of 2026-09-29.

**Files:**
- Modify: `tests/kraken_loopback.py` (`asyncio` and `Callable` imports; `websockets` import; `trade_row` after `margin_position`; the dataclass's `trades`, `on_add_order` and `on_cancel_order` fields; the four private endpoints and the two hooks in `_answer`; `WsPeer`, `_ws_stamp`, `exec_new`, `exec_trade`, `exec_canceled` and `serve_with_sockets` after `client`)
- Modify: `.github/workflows/coverage.yml` (the apt install before `uv sync`)
- Modify: `tests/test_engine_node.py` (the currency probe's parse over the basket fixture, every one of the eleven codes held to the adapter's mint)
- Create: `tests/cache_restart_child.py`
- Create: `tests/test_cache_restart.py`
- Generate: `tests/fixtures/kraken_assetpairs_basket.json` (the script in Step 4, sha256 pinned there)

**Interfaces:**
- Consumes: `build_shadow_node`, `ShadowStrategy`, `_data_client_config`, `_exec_client_config`, `read_system_status`, `_ACCOUNT_ID` in `cli/engine/node.py`; `read_venue_orders`, `cancel_venue_order`, `read_venue_holdings`, `set_executor_hooks` in `cli/engine/executor.py`; `EngineConfig`, `CacheSettings` in `cli/config.py`; `configure` in `cli/logging.py`; `ARM_FILE`, `exec_dir` in `cli/engine/execgate.py`; `exec_record_path`, `read_exec_record`, `validate_exec_record` in `cli/engine/execledger.py`; `PLAN_FILENAME` in `cli/engine/probeplan.py`; `PAIR_KEYS` in `cli/engine/store.py`; `KrakenLoopback`, `serve`, `open_order`, `closed_order`, `margin_position`, `balance` in `tests/kraken_loopback.py`; the `engine` line of `infra/ansible/roles/cache/templates/users.acl.j2`
- Produces: in `tests/kraken_loopback.py`, `trade_row(txid, pair, *, vol, price, trade_id, side="buy") -> dict`, `KrakenLoopback.trades`, `KrakenLoopback.on_add_order: Callable[[dict, str], None] | None`, `KrakenLoopback.on_cancel_order: Callable[[dict], None] | None`, `WsPeer(name)` with `.send_execution(data)`, `.subscribed`, `.log`, `exec_new(...)`, `exec_trade(...)`, `exec_canceled(...)`, `serve_with_sockets(asset_pairs=None)` yielding `(venue, data_peer, exec_peer)`; `tests/cache_restart_child.py` (argv[1] the JSON config, the record at `out`); in `tests/test_cache_restart.py`, `_Valkey`, `_Node`, `_script_first_fill`, `_script_cancel_ack`, `_phase_one` and the `phase_one` fixture, `_restore_lines`, `_basket_pairs`, `_silent_listener`, the eight scenarios

- [ ] **Step 1: Confirm Task 2's marker, the harness's absence and the binary**

Run: `grep -c 'number_of_retries=10' cli/engine/node.py; grep -c 'serve_with_sockets' tests/kraken_loopback.py; ls tests/test_cache_restart.py tests/cache_restart_child.py tests/fixtures/kraken_assetpairs_basket.json 2>&1 | grep -c 'No such file'; which valkey-server`
Expected: `1`, then `0`, then `3`, then the binary's path. A `1` other than the first means Task 2 is not in, a `serve_with_sockets` already present means this task is; stop and report either to the controller. No path means the binary is missing: `sudo apt-get install -y valkey-server`, and read `valkey-server --version` (8.1.1 on the workstation when this plan was written).

- [ ] **Step 2: The failing harness `tests/test_cache_restart.py`**

Create `tests/test_cache_restart.py` with this content:

```python
"""The two-process restart harness: the engine's own node, restarted against a real `valkey-server`
this file starts, with the venue a loopback the file scripts.

No environment gate, on purpose: a database is not a venue, and a skip on a missing binary would
read as coverage. `valkey-server` is found on PATH and named, and its absence fails with the
install command. In CI the binary comes from apt (`.github/workflows/coverage.yml`); locally it is
the workstation's own, 8.1.1 at the time of writing where the fleet runs 9.1.2, so a reading that
could differ there is named where it is asserted. Every node runs in a child interpreter
(`tests/cache_restart_child.py`) under a timeout, and reaches nothing past 127.0.0.1.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cli.engine.execgate import ARM_FILE, exec_dir
from cli.engine.execledger import exec_record_path, read_exec_record, validate_exec_record
from cli.engine.probeplan import PLAN_FILENAME
from tests import kraken_loopback as lb

REPO = Path(__file__).resolve().parents[1]
CHILD = Path(__file__).parent / "cache_restart_child.py"
ACL_TEMPLATE = REPO / "infra/ansible/roles/cache/templates/users.acl.j2"
BASKET_FIXTURE = Path(__file__).parent / "fixtures" / "kraken_assetpairs_basket.json"
INSTALL = "sudo apt-get install -y valkey-server"

PAIR, SYMBOL, INSTRUMENT = "SOLEUR", "SOL/EUR", "SOL/EUR.KRAKEN"
PRICE = 150.0
QTY = 1.0
ENGINE_USER, ENGINE_PASSWORD = "engine", "engine-harness-password"
ADMIN_USER, ADMIN_PASSWORD = "admin", "admin-harness-password"
# Phase windows: the executor's startup pass runs on its first tick at 5 s and the plan is picked up on
# the same tick; the first quote after that lands at 6 s and the fill frames within a second of the
# submission; phase 2's re-read pass runs on the tick after the pass's cancel. Each node adds the
# library's ten-second residual wait at stop.
PHASE1_WINDOW = 14
PHASE2_WINDOW = 16
CHILD_TIMEOUT = 150


def _valkey_binary() -> str:
    binary = shutil.which("valkey-server")
    if binary is None:
        pytest.fail(f"valkey-server is not on PATH: {INSTALL}")
    return binary


def _engine_acl_rules() -> str:
    """The `engine` user's rules as the cache role renders them, read off the template so the
    harness's server carries the fleet's ACL line."""
    match = re.search(r"^user engine on #\{\{ [^}]+ \}\} (.+)$", ACL_TEMPLATE.read_text(), re.M)
    assert match, "the users.acl template no longer carries the engine line in the shape this reads"
    return match.group(1)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _resp(port: int, user: str, password: str, *words: str) -> object:
    """One command on a fresh connection, RESP2, the reply decoded."""

    def encode(*items: str) -> bytes:
        return b"*%d\r\n" % len(items) + b"".join(b"$%d\r\n%s\r\n" % (len(w.encode()), w.encode()) for w in items)

    def decode(reader):
        line = reader.readline()
        kind, body = line[:1], line[1:-2]
        if kind == b"+":
            return body.decode()
        if kind == b"-":
            raise RuntimeError(body.decode())
        if kind == b":":
            return int(body)
        if kind == b"$":
            n = int(body)
            return None if n < 0 else reader.read(n + 2)[:-2].decode()
        if kind == b"*":
            n = int(body)
            return None if n < 0 else [decode(reader) for _ in range(n)]
        raise RuntimeError(f"bad reply {line!r}")

    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        reader = sock.makefile("rb")
        sock.sendall(encode("AUTH", user, password))
        assert decode(reader) == "OK"
        sock.sendall(encode(*words))
        return decode(reader)


def _keys(port: int) -> list[str]:
    keys: list[str] = []
    cursor = "0"
    while True:
        cursor, batch = _resp(port, ADMIN_USER, ADMIN_PASSWORD, "SCAN", cursor, "COUNT", "1000")
        keys += batch
        if cursor == "0":
            return sorted(keys)


class _Valkey:
    """A `valkey-server` on a free port under `root`, no persistence, the ACL file carrying the role's
    engine line and an admin user for the harness's own reads."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.port = _free_port()
        self.acl = root / "users.acl"
        self.acl.write_text(
            f"user default off\nuser {ADMIN_USER} on >{ADMIN_PASSWORD} ~* &* +@all\n"
            f"user {ENGINE_USER} on >{ENGINE_PASSWORD} {_engine_acl_rules()}\n"
        )
        (root / "data").mkdir(exist_ok=True)
        self.process: subprocess.Popen | None = None
        self.log = root / "valkey.log"

    def start(self) -> None:
        with self.log.open("a") as log:
            self.process = subprocess.Popen(
                [
                    _valkey_binary(), "--port", str(self.port), "--bind", "127.0.0.1", "--dir", str(self.root / "data"),
                    "--save", "", "--appendonly", "no", "--daemonize", "no", "--aclfile", str(self.acl),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
            )  # fmt: skip
        for _ in range(100):
            try:
                if _resp(self.port, ADMIN_USER, ADMIN_PASSWORD, "PING") == "PONG":
                    return
            except OSError:
                time.sleep(0.1)
        pytest.fail(f"valkey-server did not answer on 127.0.0.1:{self.port}: {self.log.read_text()[-2000:]}")

    def kill(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.send_signal(signal.SIGKILL)
            self.process.wait(10)

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(10)
            except subprocess.TimeoutExpired:
                self.process.kill()


class _Node:
    """The driver's side of one child node: the loopback, the two peers, the state directory and the
    child's record. `script` is called with the AddOrder form and the txid at each order, on the peer's
    own thread, to send the frames and move the loopback's listings."""

    def __init__(self, root: Path, valkey_port: int, *, max_plan_notional_eur: float = 200.0):
        self.root = root
        self.state = root / "state"
        self.journal = self.state / "journal"
        self.store = self.state / "store"
        self.journal.mkdir(parents=True, exist_ok=True)
        self.store.mkdir(parents=True, exist_ok=True)
        exec_dir(self.state).mkdir(parents=True, exist_ok=True)
        (exec_dir(self.state) / ARM_FILE).touch()
        self.valkey_port = valkey_port
        self.max_plan_notional_eur = max_plan_notional_eur
        self.records: list[dict] = []
        self.logs: list[str] = []

    def drop_plan(self, plan_id: str, *, leverage: int | None = 2, notional_eur: float = PRICE * QTY) -> None:
        intent = {"symbol": SYMBOL, "side": "buy", "action": "open", "mode": "execute", "notional_eur": notional_eur}
        if leverage is not None:
            intent["leverage"] = leverage
        plan = {"plan_id": plan_id, "created_at": datetime.now(timezone.utc).isoformat(), "intents": [intent]}
        (exec_dir(self.state) / PLAN_FILENAME).write_text(json.dumps(plan))

    def run(
        self, phase: int, venue: lb.KrakenLoopback, data: lb.WsPeer, exec_: lb.WsPeer, *, window: int, valkey_port=None
    ) -> dict:
        out = self.root / f"phase{phase}.json"
        args = {
            "phase": phase,
            "journal_dir": str(self.journal),
            "store_dir": str(self.store),
            "port": self.valkey_port if valkey_port is None else valkey_port,
            "username": ENGINE_USER,
            "password": ENGINE_PASSWORD,
            "api_key": lb.API_KEY,
            "api_secret": lb.API_SECRET,
            "base_url": venue.base_url,
            "ws_public": data.url,
            "ws_private": exec_.url,
            "instrument": INSTRUMENT,
            "bid": f"{PRICE:.2f}",
            "ask": f"{PRICE + 0.1:.2f}",
            "quote_every": 3,
            "window_secs": window,
            "out": str(out),
            "max_plan_notional_eur": self.max_plan_notional_eur,
        }
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(self.root)}
        started = time.monotonic()
        result = subprocess.run(
            [sys.executable, str(CHILD), json.dumps(args)], capture_output=True, text=True, timeout=CHILD_TIMEOUT, cwd=REPO, env=env
        )
        log = result.stdout + result.stderr
        (self.root / f"phase{phase}.log").write_text(log)
        self.logs.append(log)
        assert out.exists(), (
            f"phase {phase} wrote no record (exit {result.returncode}, {time.monotonic() - started:.1f} s):\n{log[-4000:]}"
        )
        record = json.loads(out.read_text())
        record["log"] = log
        record["wall_secs"] = time.monotonic() - started
        self.records.append(record)
        return record

    def rows(self) -> list[dict]:
        rows = []
        for path in sorted(self.journal.glob("*/exec-*.json")):
            doc = read_exec_record(path)
            validate_exec_record(doc)
            rows.extend(doc["submitted"])
        return rows

    def intents(self) -> list[dict]:
        out = []
        for path in sorted(self.journal.glob("*/exec-*.json")):
            for entry in read_exec_record(path)["plans"]:
                out.extend(entry["intents"])
        return out

    def mark_row_reducer(self, client_order_id: str) -> None:
        """Rewrite a row's `order.reduce_only` to True: the ledger's witness that the previous process
        placed this order as a reducer, the one row the startup pass keeps resting."""
        for path in sorted(self.journal.glob("*/exec-*.json")):
            doc = read_exec_record(path)
            for row in doc["submitted"]:
                if row["client_order_id"] == client_order_id:
                    row["order"]["reduce_only"] = True
                    validate_exec_record(doc)
                    path.write_text(json.dumps(doc, indent=2, sort_keys=True))
                    return
        pytest.fail(f"no row for {client_order_id}")


def _script_first_fill(venue: lb.KrakenLoopback, exec_: lb.WsPeer, *, last_qty: float = 0.4, wire: dict, fill: bool = True) -> None:
    """The venue's side of one order: the open-orders row at the AddOrder, then the `new` and, when
    `fill`, the `trade` frame on the private socket and the listings the fill moves -- the open row's
    `vol_exec`, the trade history and the margin position."""

    def on_add_order(form: dict, txid: str) -> None:
        wire.update(txid=txid, cl_ord_id=form.get("cl_ord_id"))
        venue.open_orders[txid] = dict(lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"), oflags="fciq")

        def frames() -> None:
            time.sleep(0.3)
            exec_.subscribed.wait(30)
            exec_.send_execution(lb.exec_new(txid, wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE))
            if not fill:
                return
            time.sleep(0.7)
            exec_.send_execution(
                lb.exec_trade(
                    txid, wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE, last_qty=last_qty, cum_qty=last_qty,
                    exec_id="TLOOP1-AAAAA-AAAAAA", trade_id=1001,
                )
            )  # fmt: skip
            venue.open_orders[txid].update(vol_exec=f"{last_qty:.8f}", price=f"{PRICE:.5f}", cost=f"{last_qty * PRICE:.5f}")
            venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(
                txid, PAIR, vol=f"{last_qty:.8f}", price=f"{PRICE:.2f}", trade_id=1001
            )
            venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
                lb.margin_position(PAIR, volume=f"{last_qty:.8f}"), ordertxid=txid, cost=f"{last_qty * PRICE:.5f}"
            )

        threading.Thread(target=frames, daemon=True).start()

    venue.on_add_order = on_add_order


def _script_cancel_ack(venue: lb.KrakenLoopback, exec_: lb.WsPeer, wire: dict) -> None:
    """The venue's answer to a cancel: the order leaves the open listing for the closed one, and the
    private socket sends the `canceled` frame at the venue's cumulative fill."""

    def on_cancel_order(form: dict) -> None:
        txid = wire["txid"]
        row = venue.open_orders.pop(txid, None)
        cum = float(row["vol_exec"]) if row else 0.0
        venue.closed_orders[txid] = dict(
            lb.closed_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", status="canceled", vol_exec=f"{cum:.8f}"),
            oflags="fciq",
        )

        def frame() -> None:
            time.sleep(0.3)
            exec_.send_execution(lb.exec_canceled(txid, wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE, cum_qty=cum))

        threading.Thread(target=frame, daemon=True).start()

    venue.on_cancel_order = on_cancel_order


def _basket_pairs() -> dict:
    return json.loads(BASKET_FIXTURE.read_text())


def _restore_lines(log: str) -> list[str]:
    return [line.split("cache restore: ", 1)[1] for line in log.splitlines() if "cache restore: " in line]


def _phase_one(tmp_path: Path) -> tuple[_Valkey, _Node, dict, dict]:
    """A node that placed one leveraged order, filled 0.4 of 1.0, and stopped with it resting: the
    store holds the order, the fill and the margin position, and the venue lists all three."""
    valkey = _Valkey(tmp_path / "valkey")
    valkey.start()
    node = _Node(tmp_path / "node", valkey.port)
    node.drop_plan("p-phase-1")
    wire: dict = {}
    with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        _script_first_fill(venue, exec_, wire=wire)
        record = node.run(1, venue, data, exec_, window=PHASE1_WINDOW)
    assert record["errors"] == [], record["errors"]
    assert [e["type"] for e in record["own"]][:4] == ["OrderInitialized", "OrderSubmitted", "OrderAccepted", "OrderFilled"], record[
        "own"
    ]
    [row] = node.rows()
    assert (row["state"], row["filled_qty"], row["order"]["leverage"]) == ("accepted", 0.4, 2), row
    assert row["client_order_id"] == record["own"][0]["client_order_id"]
    wire["client_order_id"] = row["client_order_id"]
    assert "trader-SHADOW-001:orders:" + row["client_order_id"] in _keys(valkey.port)
    return valkey, node, wire, record


@pytest.fixture
def phase_one(tmp_path):
    valkey, node, wire, record = _phase_one(tmp_path)
    try:
        yield valkey, node, wire, record
    finally:
        valkey.stop()


def test_a_resting_order_and_a_margin_position_are_restored_across_a_restart(phase_one):
    """The restore of both identities and the boot line: the restarted node holds the order under
    its own client order id and strategy, matched by venue order id, the position at its entry
    price, and the boot line says so; no `Unresolved positions` line, the failure the operating
    rule stands against."""
    valkey, node, wire, _ = phase_one
    with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.open_orders[wire["txid"]] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"),
            oflags="fciq",
            vol_exec="0.40000000",
            price="150.00000",
            cost="60.00000",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001)
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.40000000"), ordertxid=wire["txid"], cost="60.00000"
        )
        _script_cancel_ack(venue, exec_, wire)
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)

    assert record["errors"] == [], record["errors"]
    assert "Unresolved positions" not in record["log"]
    assert f"matched by venue_order_id {wire['txid']}" in record["log"]
    [order] = record["at_start"]["orders"]
    assert (order["client_order_id"], order["strategy_id"], order["venue_order_id"], order["filled_qty"]) == (
        wire["client_order_id"],
        "ShadowStrategy-000",
        wire["txid"],
        "0.40000000",
    )
    [position] = record["at_start"]["positions"]
    assert (position["instrument_id"], position["strategy_id"], position["signed_qty"], position["avg_px_open"]) == (
        INSTRUMENT,
        "ShadowStrategy-000",
        0.4,
        150.0,
    )
    assert _restore_lines(record["log"]) == [
        "1 order(s), 1 position(s) restored",
        "position SOL/EUR.KRAKEN 0.4 @ 150.0 (ShadowStrategy-000)",
        f"order {wire['client_order_id']} partial, 0.40000000 of 1.00000000 filled @ 150.00",
    ]
    assert record["external"] == [], record["external"]  # every later event reaches the own topic


def test_a_fill_made_while_the_engine_was_down_is_booked_from_the_trade_history(phase_one):
    valkey, node, wire, _ = phase_one
    with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.open_orders[wire["txid"]] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"),
            oflags="fciq",
            vol_exec="0.70000000",
            price="150.00000",
            cost="105.00000",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001)
        venue.trades["TLOOP2-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.30000000", price="150.00", trade_id=1002)
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.70000000"), ordertxid=wire["txid"], cost="105.00000"
        )
        _script_cancel_ack(venue, exec_, wire)
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)

    assert record["errors"] == [], record["errors"]
    assert "Unresolved positions" not in record["log"]
    # The library books the missed fill onto the restored order, keeps the restored position at its
    # stored quantity, and closes the gap to the venue's position with a synthesized EXTERNAL order
    # and position, which the boot line lists beside the restored one.
    orders = {o["strategy_id"]: o for o in record["at_start"]["orders"]}
    positions = {p["strategy_id"]: p for p in record["at_start"]["positions"]}
    assert (orders[record["strategy_id"]]["filled_qty"], orders[record["strategy_id"]]["status"]) == ("0.70000000", "ACCEPTED")
    assert {(p["signed_qty"], p["avg_px_open"]) for p in positions.values()} == {(0.4, 150.0), (0.3, 150.0)}
    assert positions["EXTERNAL"]["signed_qty"] == 0.3
    assert {tuple(p) for p in record["metrics"]["positions"] if p[0] == "SOL/EUR"} == {("SOL/EUR", 0.7)}
    assert _restore_lines(record["log"]) == [
        "1 order(s), 2 position(s) restored",
        "position SOL/EUR.KRAKEN 0.3 @ 150.0 (EXTERNAL)",
        "position SOL/EUR.KRAKEN 0.4 @ 150.0 (ShadowStrategy-000)",
        f"order {wire['client_order_id']} partial, 0.70000000 of 1.00000000 filled @ 150.00",
    ]


def test_an_order_cancelled_while_the_engine_was_down_is_never_closed_by_the_library(phase_one):
    """Mass status reads open orders only on this pin and ClosedOrders is never requested, so the
    restored copy stays open in the Cache for the process's life -- the shape the startup pass
    settles from the venue's report."""
    valkey, node, wire, _ = phase_one
    with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.closed_orders[wire["txid"]] = dict(
            lb.closed_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", status="canceled", vol_exec="0.40000000"),
            oflags="fciq",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001)
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.40000000"), ordertxid=wire["txid"], cost="60.00000"
        )
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
        private_calls = list(venue.private_calls)

    assert record["errors"] == [], record["errors"]
    assert "ClosedOrders" not in private_calls[: private_calls.index("OpenPositions") + 1], private_calls
    [order] = record["at_start"]["orders"]
    assert (order["is_open"], order["filled_qty"]) == (True, "0.40000000")
    assert _restore_lines(record["log"])[0] == "1 order(s), 1 position(s) restored"


def test_a_trade_frame_on_a_restored_open_order_is_booked_twice_by_the_library(phase_one):
    """The measured double booking: a `trade` frame on a restored order is booked as an inferred fill
    for the cumulative gap and then as the fill itself, so the Cache's copy reads 0.8 where the
    venue said 0.6. The row is the previous process's reducer, which the startup pass keeps, so the
    order is still open when the frame lands."""
    valkey, node, wire, _ = phase_one
    node.mark_row_reducer(wire["client_order_id"])
    with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.open_orders[wire["txid"]] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"),
            oflags="fciq",
            vol_exec="0.40000000",
            price="150.00000",
            cost="60.00000",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001)
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.40000000"), ordertxid=wire["txid"], cost="60.00000"
        )

        def later() -> None:
            exec_.subscribed.wait(60)
            time.sleep(8)  # past the startup pass, which keeps the reducer resting
            exec_.send_execution(
                lb.exec_trade(
                    wire["txid"], wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE, last_qty=0.2, cum_qty=0.6,
                    exec_id="TLOOP3-AAAAA-AAAAAA", trade_id=1003,
                )
            )  # fmt: skip
            venue.open_orders[wire["txid"]].update(vol_exec="0.60000000", cost="90.00000")
            venue.trades["TLOOP3-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.20000000", price="150.00", trade_id=1003)

        threading.Thread(target=later, daemon=True).start()
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
        cancels = list(venue.cancel_forms)

    assert record["errors"] == [], record["errors"]
    assert cancels == [], cancels  # the pass kept the reducer
    assert "Generated inferred fill" in record["log"]
    fills = [e for e in record["own"] if e["type"] == "OrderFilled"]
    assert [(e["last_qty"], e["reconciliation"]) for e in fills] == [("0.20000000", True), ("0.20000000", True)], fills
    [order] = record["at_end"]["orders"]
    assert order["filled_qty"] == "0.80000000"  # the venue's cumulative figure is 0.6


def test_an_empty_cache_beside_open_ledger_rows_is_a_cold_start_the_pass_reconciles_as_today(tmp_path):
    """The owner's ruling: an empty namespace is a cold start, never a refusal. The order is a spot
    one resting unfilled, so the venue has no margin position for the start to fail on and no fill
    for the pass to weigh against the ledger; the restarted node reads zero, reconciliation names
    the order by its txid under EXTERNAL, and the pass cancels it as an order the ledger carries as
    no reducer, today's shape."""
    valkey = _Valkey(tmp_path / "valkey")
    valkey.start()
    try:
        node = _Node(tmp_path / "node", valkey.port)
        node.drop_plan("p-spot", leverage=None)
        wire: dict = {}
        with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000")}
            _script_first_fill(venue, exec_, wire=wire, fill=False)
            record = node.run(1, venue, data, exec_, window=PHASE1_WINDOW)
        assert record["errors"] == [], record["errors"]
        [row] = node.rows()
        assert (row["state"], row["filled_qty"], row["order"]["leverage"]) == ("accepted", 0.0, None)
        wire["client_order_id"] = row["client_order_id"]
        assert len(_keys(valkey.port)) > 0
        # The store lost: a fresh server on the same port, the venue still listing the order open.
        valkey.kill()
        valkey.start()
        assert _keys(valkey.port) == []
        with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000")}
            venue.open_orders[wire["txid"]] = dict(lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"), oflags="fciq")
            _script_cancel_ack(venue, exec_, wire)
            record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
            cancels = list(venue.cancel_forms)
    finally:
        valkey.stop()

    assert record["errors"] == [], record["errors"]
    assert _restore_lines(record["log"]) == ["0 order(s), 0 position(s) restored"]
    assert f"Created external order {wire['txid']}" in record["log"]
    [external] = record["at_start"]["orders"]
    assert (
        external["client_order_id"],
        external["strategy_id"],
        external["venue_order_id"],
        external["status"],
        external["is_open"],
    ) == (
        wire["txid"],
        "EXTERNAL",
        wire["txid"],
        "ACCEPTED",
        True,
    )
    assert "execution kill switch tripped" not in record["log"]
    assert f"canceling adopted resting order {wire['txid']} -- the ledger does not carry it as a resting reducer" in record["log"]
    assert [form.get("txid") for form in cancels] == [wire["txid"]]
    assert [e["client_order_id"] for e in record["external"]][:1] == [wire["txid"]]


def _silent_listener() -> tuple[int, threading.Event]:
    """A TCP listener on 127.0.0.1 that accepts and never writes: a proxy up with no backend."""
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(64)
    stop = threading.Event()
    held: list = []

    def accept() -> None:
        server.settimeout(0.5)
        while not stop.is_set():
            try:
                held.append(server.accept()[0])
            except socket.timeout:
                continue
        for conn in held:
            conn.close()
        server.close()

    threading.Thread(target=accept, daemon=True).start()
    return server.getsockname()[1], stop


@pytest.mark.parametrize("shape", ["refused", "silent"])
def test_the_cache_unreachable_at_start_fails_inside_the_budget_without_touching_the_venue(tmp_path, shape):
    """Ten retries under five-second timeouts: a port nothing listens on refuses the start in seconds,
    a peer that accepts and never answers in about 55 s, both inside the inter-cycle gap and this
    harness's timeout, and neither reaches the venue -- `run()` creates the backing before any
    client connects. Measured on 8.1.1's client library, whose timeouts are the library's own."""
    port, stop = (1, None) if shape == "refused" else _silent_listener()
    node = _Node(tmp_path / "node", port)
    try:
        with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
            record = node.run(1, venue, data, exec_, window=PHASE1_WINDOW, valkey_port=port)
            private_calls = list(venue.private_calls)
    finally:
        if stop is not None:
            stop.set()
    assert record["errors"] == ["run raised RuntimeError: failed to create cache database backing"], record["errors"]
    assert "at_start" not in record  # no strategy started
    assert private_calls == [], private_calls
    bound = 20 if shape == "refused" else 90
    assert record["run_secs"] < bound, (shape, record["run_secs"])
    if shape == "silent":
        assert record["run_secs"] > 40, record["run_secs"]


def test_the_cache_killed_mid_run_leaves_the_engine_trading_and_the_store_behind(tmp_path):
    """The store dies under a running node: the first plan's order fills whole, the server is killed,
    a second plan is dropped and its order is placed, acknowledged and filled with the server down,
    every failed write logged at ERROR under `nautilus_infrastructure::redis::cache` and every event
    on the lost order's key at WARN; the server returns empty, the link comes back lazily on the next
    write, and at the return the store holds neither the second order nor its fill."""
    valkey = _Valkey(tmp_path / "valkey")
    valkey.start()
    node = _Node(tmp_path / "node", valkey.port)
    node.drop_plan("p-first")
    wire: dict = {}
    orders: list[str] = []
    try:
        with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000")}

            def on_add_order(form: dict, txid: str) -> None:
                orders.append(txid)
                n = len(orders)
                wire[txid] = form.get("cl_ord_id")
                venue.open_orders[txid] = dict(lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"), oflags="fciq")

                def frames() -> None:
                    time.sleep(0.3)
                    exec_.subscribed.wait(30)
                    exec_.send_execution(lb.exec_new(txid, wire[txid], symbol=SYMBOL, qty=QTY, price=PRICE))
                    time.sleep(0.7)
                    exec_.send_execution(
                        lb.exec_trade(
                            txid, wire[txid], symbol=SYMBOL, qty=QTY, price=PRICE, last_qty=QTY, cum_qty=QTY,
                            exec_id=f"TLOOP{n}-AAAAA-AAAAAA", trade_id=1000 + n,
                        )
                    )  # fmt: skip
                    venue.open_orders.pop(txid, None)
                    venue.closed_orders[txid] = dict(
                        lb.closed_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", status="closed", vol_exec=f"{QTY:.8f}"),
                        oflags="fciq",
                    )
                    if n == 1:
                        time.sleep(2)
                        valkey.kill()
                        node.drop_plan("p-second")
                        time.sleep(12)
                        valkey.start()

                threading.Thread(target=frames, daemon=True).start()

            venue.on_add_order = on_add_order
            record = node.run(1, venue, data, exec_, window=32)
        keys_at_return = _keys(valkey.port)
    finally:
        valkey.stop()

    assert record["errors"] == [], record["errors"]
    assert len(orders) == 2, orders
    fills = [(e["client_order_id"], e["last_qty"]) for e in record["own"] if e["type"] == "OrderFilled"]
    assert len(fills) == 2 and fills[0][0] != fills[1][0], fills
    rows = {row["client_order_id"]: row for row in node.rows()}
    assert {row["state"] for row in rows.values()} == {"filled"}, rows
    intents = [i["outcome"] for i in node.intents()]
    assert intents == ["filled", "filled"], intents
    log = record["log"]
    assert re.search(r"\[ERROR\] SHADOW-001\.nautilus_infrastructure::redis::cache: (broken pipe|Connection refused)", log), log[
        -3000:
    ]
    assert re.search(
        r"\[WARN\] SHADOW-001\.nautilus_infrastructure::redis::cache: Cannot update order in Redis, no existing state at", log
    ), log[-3000:]
    second = fills[1][0]
    assert f"trader-SHADOW-001:orders:{second}" not in keys_at_return, keys_at_return
```

- [ ] **Step 3: Run the harness and watch every scenario fail before the loopback speaks its shapes**

Run: `uv run pytest tests/test_cache_restart.py -q -p no:cacheprovider`
Expected: `4 failed, 4 errors in 0.85s` -- `AttributeError: module 'tests.kraken_loopback' has no attribute 'serve_with_sockets'` in the four scenarios that build their own first phase (the cold start, the two unreachable shapes, the kill mid-run) and as the `phase_one` fixture's error in the other four; no child process starts, so the time is under a few seconds.

- [ ] **Step 4: The loopback's private endpoints and peer, the child, the fixture and the workflow's install**

Replace, in `tests/kraken_loopback.py`, this block:

```python
from __future__ import annotations

import base64
import json
```

with:

```python
from __future__ import annotations

import asyncio
import base64
import json
```

Replace, in `tests/kraken_loopback.py`, this block:

```python
import time
import urllib.parse
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
```

with:

```python
import time
import urllib.parse
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
```

Replace, in `tests/kraken_loopback.py`, this block:

```python
from pathlib import Path
from typing import Any

# Bound here, not at call time: a test that replaces the adapter's attribute to refuse any client
```

with:

```python
from pathlib import Path
from typing import Any

# The scripted private WebSocket peer below is served by `websockets`, the library the adapter's own
# execution socket speaks to; nothing here reaches past 127.0.0.1.
import websockets

# Bound here, not at call time: a test that replaces the adapter's attribute to refuse any client
```

Replace, in `tests/kraken_loopback.py`, this block:

```python


@dataclass
class KrakenLoopback:
```

with:

```python


def trade_row(txid: str, pair: str, *, vol: str, price: str, trade_id: int, side: str = "buy") -> dict[str, Any]:
    """One TradesHistory row, as Kraken's trades history lists a fill of `txid`; `pair` spelled as the
    AssetPairs key. A margin fill: `posstatus` open and a `postxid`, which the adapter reads beside the
    quantity when it books a fill the stream never delivered."""
    cost = f"{float(vol) * float(price):.5f}"
    return {
        "ordertxid": txid,
        "postxid": "TPOSLP-AAAAA-BBBBBB",
        "pair": pair,
        "time": 1758600000.0,
        "type": side,
        "ordertype": "limit",
        "price": price,
        "cost": cost,
        "fee": "0.00000",
        "vol": vol,
        "margin": f"{float(cost) / 2:.5f}",
        "leverage": "2",
        "misc": "",
        "trade_id": trade_id,
        "maker": True,
        "posstatus": "open",
    }


@dataclass
class KrakenLoopback:
```

Replace, in `tests/kraken_loopback.py`, this block:

```python
    closed_orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    positions: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Depth books by the pair a request names, which the adapter spells as the AssetPairs key. A pair
    # with no book answers `EQuery:Unknown asset pair`, never an empty book.
```

with:

```python
    closed_orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    positions: dict[str, dict[str, Any]] = field(default_factory=dict)
    # TradesHistory rows by trade id, paged by `ofs` as the adapter pages them; a fill the private
    # WebSocket never delivered is booked from here at startup reconciliation.
    trades: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Called with the AddOrder form and the txid it was answered, after the answer is built: a
    # test's chance to script the private WebSocket's frames for that order.
    on_add_order: Callable[[dict[str, str], str], None] | None = None
    # Called with the CancelOrder form after the answer is built: the test's chance to script the
    # cancel's frame and to move the order from the open listing to the closed one.
    on_cancel_order: Callable[[dict[str, str]], None] | None = None
    # Depth books by the pair a request names, which the adapter spells as the AssetPairs key. A pair
    # with no book answers `EQuery:Unknown asset pair`, never an empty book.
```

Replace, in `tests/kraken_loopback.py`, this block:

```python
        if path == "/0/private/OpenPositions":
            return dict(self.positions), []
        if path == "/0/private/AddOrder":
            self.add_orders.append(form)
            return {"descr": {"order": "loopback"}, "txid": [f"OLOOP{len(self.add_orders)}-AAAAA-BBBBBB"]}, []
        if path == "/0/private/CancelOrder":
            self.cancel_forms.append(form)
            return {"count": self.cancel_count}, []
        return None, ["EGeneral:Unknown method"]
```

with:

```python
        if path == "/0/private/OpenPositions":
            return dict(self.positions), []
        if path == "/0/private/GetWebSocketsToken":
            return {"token": "loopback-ws-token", "expires": 900}, []
        if path == "/0/private/TradeBalance":
            return {
                "eb": "1000.0",
                "tb": "1000.0",
                "m": "0.0",
                "uv": "0.0",
                "n": "0.0",
                "c": "0.0",
                "v": "0.0",
                "e": "1000.0",
                "mf": "1000.0",
            }, []
        if path == "/0/private/TradesHistory":
            offset = int(form.get("ofs", "0"))
            page = dict(list(self.trades.items())[offset : offset + _PAGE])
            return {"trades": page, "count": len(self.trades)}, []
        if path == "/0/private/AddOrder":
            self.add_orders.append(form)
            txid = f"OLOOP{len(self.add_orders)}-AAAAA-BBBBBB"
            if self.on_add_order is not None:
                self.on_add_order(form, txid)
            return {"descr": {"order": "loopback"}, "txid": [txid]}, []
        if path == "/0/private/CancelOrder":
            self.cancel_forms.append(form)
            if self.on_cancel_order is not None:
                self.on_cancel_order(form)
            return {"count": self.cancel_count}, []
        return None, ["EGeneral:Unknown method"]
```

Replace, in `tests/kraken_loopback.py`, this block:

```python
    """The real client, built as `cli/engine/command.py` builds it, pointed at the loopback."""
    return KrakenSpotHttpClient(API_KEY, API_SECRET, base_url=venue.base_url)
```

with:

```python
    """The real client, built as `cli/engine/command.py` builds it, pointed at the loopback."""
    return KrakenSpotHttpClient(API_KEY, API_SECRET, base_url=venue.base_url)


class WsPeer:
    """One WebSocket server on its own event-loop thread, bound to 127.0.0.1: it answers `ping` with
    `pong` and acknowledges any `subscribe`, and records the connection that subscribed `executions`
    so a test can script execution frames onto it. The same peer serves the data socket, where it
    acknowledges the quote subscription and sends nothing: the harness hands the executor its quotes
    itself. `log` carries every frame either way, stamped."""

    def __init__(self, label: str):
        self.label = label
        self.port: int | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.exec_conn = None
        self.subscribed = threading.Event()
        self.log: list[str] = []
        ready = threading.Event()

        async def handler(conn):
            async for raw in conn:
                self.log.append(f"{time.time():.3f} {label} <- {raw}")
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                method = message.get("method")
                stamp = _ws_stamp()
                if method == "ping":
                    await conn.send(
                        json.dumps({"method": "pong", "req_id": message.get("req_id"), "time_in": stamp, "time_out": stamp})
                    )
                elif method == "subscribe":
                    channel = (message.get("params") or {}).get("channel")
                    answer = {
                        "method": "subscribe",
                        "req_id": message.get("req_id"),
                        "success": True,
                        "result": {"channel": channel, "snapshot": False},
                        "time_in": stamp,
                        "time_out": stamp,
                    }
                    await conn.send(json.dumps(answer))
                    self.log.append(f"{time.time():.3f} {label} -> {json.dumps(answer)}")
                    if channel == "executions":
                        self.exec_conn = conn
                        self.subscribed.set()

        async def main():
            self.loop = asyncio.get_running_loop()
            async with websockets.serve(handler, "127.0.0.1", 0) as server:
                self.port = server.sockets[0].getsockname()[1]
                ready.set()
                await asyncio.Future()

        threading.Thread(target=lambda: asyncio.run(main()), daemon=True).start()
        ready.wait(10)

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    def send_execution(self, data: dict[str, Any]) -> None:
        """One `executions` update frame carrying `data`, sent to the subscribed connection."""
        frame = {"channel": "executions", "type": "update", "data": [data], "sequence": int(time.time())}
        text = json.dumps(frame)
        self.log.append(f"{time.time():.3f} {self.label} -> {text}")
        asyncio.run_coroutine_threadsafe(self.exec_conn.send(text), self.loop).result(5)


def _ws_stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())


def exec_new(txid: str, cl_ord_id: str | None, *, symbol: str, qty: float, price: float, side: str = "buy") -> dict[str, Any]:
    """The `new` execution frame the private socket sends when an order is accepted, in the shape
    upstream's `KrakenWsExecutionData` parses."""
    data = {
        "exec_type": "new",
        "order_id": txid,
        "symbol": symbol,
        "side": side,
        "order_type": "limit",
        "order_qty": qty,
        "limit_price": price,
        "order_status": "new",
        "time_in_force": "GTC",
        "post_only": False,
        "reduce_only": False,
        "timestamp": _ws_stamp(),
        "cum_qty": 0.0,
        "cum_cost": 0.0,
        "avg_price": 0.0,
    }
    if cl_ord_id is not None:
        data["cl_ord_id"] = cl_ord_id
    return data


def exec_trade(
    txid: str,
    cl_ord_id: str | None,
    *,
    symbol: str,
    qty: float,
    price: float,
    last_qty: float,
    cum_qty: float,
    exec_id: str,
    trade_id: int,
    side: str = "buy",
) -> dict[str, Any]:
    """The `trade` execution frame for one fill of `last_qty`, carrying both halves upstream parses: the
    status half (`order_status`, `cum_qty`) and the fill half (`exec_id`, `last_qty`)."""
    data = {
        "exec_type": "trade",
        "order_id": txid,
        "symbol": symbol,
        "side": side,
        "order_type": "limit",
        "order_qty": qty,
        "limit_price": price,
        "order_status": "filled" if cum_qty >= qty else "partially_filled",
        "timestamp": _ws_stamp(),
        "exec_id": exec_id,
        "trade_id": trade_id,
        "last_qty": last_qty,
        "last_price": price,
        "cost": last_qty * price,
        "cum_qty": cum_qty,
        "cum_cost": cum_qty * price,
        "avg_price": price,
        "liquidity_ind": "m",
        "fees": [{"asset": "EUR", "qty": 0.0}],
    }
    if cl_ord_id is not None:
        data["cl_ord_id"] = cl_ord_id
    return data


def exec_canceled(
    txid: str, cl_ord_id: str | None, *, symbol: str, qty: float, price: float, cum_qty: float, side: str = "buy"
) -> dict[str, Any]:
    """The `canceled` execution frame, `cum_qty` the venue's cumulative fill at the cancel."""
    data = {
        "exec_type": "canceled",
        "order_id": txid,
        "symbol": symbol,
        "side": side,
        "order_type": "limit",
        "order_qty": qty,
        "limit_price": price,
        "order_status": "canceled",
        "timestamp": _ws_stamp(),
        "cum_qty": cum_qty,
        "cum_cost": cum_qty * price,
        "avg_price": price,
        "reason": "User requested",
    }
    if cl_ord_id is not None:
        data["cl_ord_id"] = cl_ord_id
    return data


@contextmanager
def serve_with_sockets(asset_pairs: dict[str, Any] | None = None) -> Iterator[tuple[KrakenLoopback, WsPeer, WsPeer]]:
    """`serve` plus the two WebSocket peers a node's data and execution clients connect to."""
    with serve(asset_pairs) as venue:
        yield venue, WsPeer("data"), WsPeer("exec")
```

Create `tests/cache_restart_child.py` with this content:

```python
"""One engine-shaped node in its own interpreter, for tests/test_cache_restart.py.

The node is the engine's own `build_shadow_node`, with the cache backing attached through the config
and every venue default redirected to the loopback the driver runs: the two client configs' URLs, the
gate's venue reader, and the three bare-client reads' `base_url`. Before anything is built the child
asserts that no production default remains, the autouse `_no_production_venue_read` fixture's rule
for a node that runs. The strategy the engine registers is subclassed to hand the executor its
quotes on a timer, since the data peer sends none, and to stop the node at the window's end; its
executor, its startup pass and its ledger writes are the engine's own.

argv[1] is a JSON object: `phase`, `journal_dir`, `store_dir`, `port`, `username`, `password`,
`api_key`, `api_secret`, `base_url`, `ws_public`, `ws_private`, `instrument`, `bid`, `ask`,
`quote_every`, `window_secs`, `out`, and `max_plan_notional_eur`. It writes `out` at the window's end
and again after `run()` returns, and exits 0 whatever `run()` did: the driver reads the record.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import timedelta
from functools import partial
from pathlib import Path

CONFIG = json.loads(sys.argv[1])
os.environ["KRAKEN_SPOT_API_KEY"] = CONFIG["api_key"]
os.environ["KRAKEN_SPOT_API_SECRET"] = CONFIG["api_secret"]
os.environ["ZCRYPTO_CACHE_PASSWORD"] = CONFIG["password"]

from nautilus_trader.adapters.kraken import (  # noqa: E402
    KrakenDataClientConfig,
    KrakenEnvironment,
    KrakenExecutionClientConfig,
    KrakenProductType,
)
from nautilus_trader.model import AccountId, AccountType, InstrumentId, Price, Quantity, QuoteTick  # noqa: E402

from cli.config import CacheSettings, EngineConfig  # noqa: E402
from cli.engine import executor as executor_module  # noqa: E402
from cli.engine import node as node_module  # noqa: E402
from cli.engine.venue import VenueStatus  # noqa: E402
from cli.logging import configure  # noqa: E402

# The engine's own log shape: plain text on stdout at INFO, where the boot line and the library's
# Rust lines land together, as the unit's journal holds them on the engine host.
configure(None, "INFO", None)

LOOPBACK_HTTP = "http://127.0.0.1:"
LOOPBACK_WS = "ws://127.0.0.1:"
RECORD: dict = {"phase": CONFIG["phase"], "own": [], "external": [], "errors": [], "quotes": 0}
HANDLE: list = [None]


def _data_client_config() -> KrakenDataClientConfig:
    return KrakenDataClientConfig(
        product_type=KrakenProductType.SPOT,
        environment=KrakenEnvironment.LIVE,
        ws_idle_timeout_ms=0,
        base_url=CONFIG["base_url"],
        ws_public_url=CONFIG["ws_public"],
        ws_private_url=CONFIG["ws_public"],
        ws_l3_url=CONFIG["ws_public"],
    )


def _exec_client_config(credentials: tuple[str, str]) -> KrakenExecutionClientConfig:
    # The engine's own fields, plus the two URLs the loopback answers on.
    api_key, api_secret = credentials
    return KrakenExecutionClientConfig(
        account_id=AccountId(node_module._ACCOUNT_ID),
        product_type=KrakenProductType.SPOT,
        environment=KrakenEnvironment.LIVE,
        api_key=api_key,
        api_secret=api_secret,
        spot_account_type=AccountType.MARGIN,
        margin_balance_asset="ZEUR",
        spot_positions_quote_currency="ZEUR",
        use_ws_trade=False,
        base_url=CONFIG["base_url"],
        ws_url=CONFIG["ws_private"],
    )


def _venue_online(*, now, opener=None) -> VenueStatus:
    return VenueStatus(status="online", ok=True, observed_at=now)


node_module._data_client_config = _data_client_config
node_module._exec_client_config = _exec_client_config
node_module.read_system_status = _venue_online
executor_module.read_venue_orders = partial(executor_module.read_venue_orders, base_url=CONFIG["base_url"])
executor_module.cancel_venue_order = partial(executor_module.cancel_venue_order, base_url=CONFIG["base_url"])
executor_module.read_venue_holdings = partial(executor_module.read_venue_holdings, base_url=CONFIG["base_url"])


def _refuse_production_defaults() -> None:
    """Exit 3 before the build if any venue default still points past the loopback."""
    data = _data_client_config()
    exec_ = _exec_client_config(("k", "s"))
    urls = [data.base_url, exec_.base_url]
    sockets = [data.ws_public_url, data.ws_private_url, data.ws_l3_url, exec_.ws_url]
    redirected = all(url.startswith(LOOPBACK_HTTP) for url in urls) and all(url.startswith(LOOPBACK_WS) for url in sockets)
    bare = all(
        isinstance(fn, partial) and str(fn.keywords.get("base_url", "")).startswith(LOOPBACK_HTTP)
        for fn in (executor_module.read_venue_orders, executor_module.cancel_venue_order, executor_module.read_venue_holdings)
    )
    if not (
        redirected
        and bare
        and node_module.read_system_status is _venue_online
        and node_module._data_client_config is _data_client_config
        and node_module._exec_client_config is _exec_client_config
    ):
        sys.stderr.write("cache_restart_child: a venue default still points past the loopback; refusing to build\n")
        os._exit(3)


def _s(value) -> str | None:
    return None if value is None else str(value)


def _event(event) -> dict:
    out = {
        "type": type(event).__name__,
        "client_order_id": _s(getattr(event, "client_order_id", None)),
        "venue_order_id": _s(getattr(event, "venue_order_id", None)),
        "reconciliation": getattr(event, "reconciliation", None),
        "at": time.time(),
    }
    for key in ("last_qty", "trade_id", "reason"):
        if hasattr(event, key):
            out[key] = _s(getattr(event, key))
    return out


def _dump(cache) -> dict:
    orders = [
        {
            "client_order_id": _s(order.client_order_id),
            "strategy_id": _s(order.strategy_id),
            "venue_order_id": _s(order.venue_order_id),
            "status": _s(order.status),
            "quantity": _s(order.quantity),
            "filled_qty": _s(order.filled_qty),
            "is_open": order.is_open,
        }
        for order in cache.orders()
    ]
    positions = [
        {
            "id": _s(position.id),
            "strategy_id": _s(position.strategy_id),
            "instrument_id": _s(position.instrument_id),
            "signed_qty": position.signed_qty,
            "avg_px_open": position.avg_px_open,
            "realized_pnl": _s(position.realized_pnl),
            "is_open": position.is_open,
        }
        for position in cache.positions()
    ]
    return {"orders": orders, "positions": positions}


class _Recorder:
    """The executor's metrics hook, recording the position and realized readings it publishes."""

    def __init__(self):
        self.positions: list = []
        self.realized: list = []

    def inc_order(self, outcome):
        pass

    def inc_external(self, disposition):
        pass

    def inc_fill(self, liquidity, fee_eur):
        pass

    def set_position(self, symbol, qty):
        self.positions.append((symbol, qty))

    def set_realized(self, value):
        self.realized.append(value)

    def set_resting_age(self, mode, seconds):
        pass

    def set_tracking_state(self, state):
        pass


METRICS = _Recorder()


def _write() -> None:
    RECORD["metrics"] = {"positions": METRICS.positions, "realized": METRICS.realized}
    Path(CONFIG["out"]).write_text(json.dumps(RECORD, indent=1, default=str))


class ShadowStrategy(node_module.ShadowStrategy):
    """The engine's strategy with a quote timer and a stop alert; `run_cycle_fn` is inert so no
    boundary cycle reaches a store or a venue from here. Named as the engine's is, since the
    strategy id the store keys everything under is derived from the class name."""

    def __init__(self, config: EngineConfig, *, executor_factory=None, **_):
        super().__init__(config, run_cycle_fn=lambda cycle_ts, *, config, venue_state=None: None, executor_factory=executor_factory)

    def on_start(self) -> None:
        try:
            super().on_start()
            RECORD["strategy_id"] = str(self.strategy_id)
            RECORD["at_start"] = _dump(self.cache)
            self.clock.set_timer("child-quote", timedelta(seconds=CONFIG["quote_every"]), callback=self._quote)
            self.clock.set_time_alert(
                "child-stop", self.clock.utc_now() + timedelta(seconds=CONFIG["window_secs"]), callback=self._stop
            )
        except Exception:
            RECORD["errors"].append(traceback.format_exc())
            _write()
            HANDLE[0].stop()

    def _quote(self, event) -> None:
        tick = QuoteTick(
            InstrumentId.from_str(CONFIG["instrument"]),
            Price.from_str(CONFIG["bid"]),
            Price.from_str(CONFIG["ask"]),
            Quantity.from_str("10.0"),
            Quantity.from_str("10.0"),
            self.clock.timestamp_ns(),
            self.clock.timestamp_ns(),
        )
        RECORD["quotes"] += 1
        self.on_quote(tick)

    def _stop(self, event) -> None:
        try:
            RECORD["at_end"] = _dump(self.cache)
            executor = self._executor
            RECORD["attached"] = sorted(executor._attached) if executor is not None else None
            RECORD["restored"] = sorted(getattr(executor, "_restored", ()) or ()) if executor is not None else None
        except Exception:
            RECORD["errors"].append(traceback.format_exc())
        _write()
        HANDLE[0].stop()

    def on_order_event(self, event) -> None:
        RECORD["own"].append(_event(event))
        super().on_order_event(event)

    def _on_external_order_event(self, event) -> None:
        RECORD["external"].append(_event(event))
        super()._on_external_order_event(event)


def main() -> None:
    _refuse_production_defaults()
    config = EngineConfig(
        store_dir=Path(CONFIG["store_dir"]),
        journal_dir=Path(CONFIG["journal_dir"]),
        exec_enabled=True,
        exec_armed=True,
        exec_max_plan_notional_eur=float(CONFIG["max_plan_notional_eur"]),
        cache=CacheSettings(enabled=True, host="127.0.0.1", port=int(CONFIG["port"]), username=CONFIG["username"]),
    )
    node_module.ShadowStrategy = ShadowStrategy
    executor_module.set_executor_hooks(metrics=METRICS)
    started = time.monotonic()
    node = node_module.build_shadow_node(config)
    HANDLE[0] = node.handle()
    RECORD["built_in"] = time.monotonic() - started
    started = time.monotonic()
    try:
        node.run()
    except BaseException as exc:
        RECORD["errors"].append(f"run raised {type(exc).__name__}: {exc}")
    finally:
        RECORD["run_secs"] = time.monotonic() - started
        try:
            node.dispose()
        except BaseException as exc:
            RECORD["errors"].append(f"dispose raised {type(exc).__name__}: {exc}")
        _write()
        sys.stdout.flush()
        os._exit(0)


if __name__ == "__main__":
    main()
```

Replace, in `tests/test_engine_node.py`, this block:

```python
# committed snapshot rather than typed, and which of them a strict lookup resolves before any
# registration; then the adapter's own parse of the mint fixture through the loopback, which mints
# the codes it meets, read back field by field.
```

with:

```python
# committed snapshot rather than typed, and which of them a strict lookup resolves before any
# registration; then the adapter's own parse of the twelve-pair basket fixture through the loopback,
# which mints every code the basket carries, read back field by field.
```

Replace, in `tests/test_engine_node.py`, this block:

```python
before = {code: strict(code) for code in basket_codes}
with kraken_loopback.serve() as venue:
```

with:

```python
before = {code: strict(code) for code in basket_codes}
with kraken_loopback.serve(json.loads(Path("tests/fixtures/kraken_assetpairs_basket.json").read_text())) as venue:
```

Replace, in `tests/test_engine_node.py`, this block:

```python
    """Three reads in one child, since the adapter's parse registers what it mints: the table names
    exactly the base and quote codes the twelve pairs carry; a fresh process resolves the five the
    library's table holds at the table's values and none of the other six; and the adapter's parse
    of the mint fixture mints `ZEUR`, `XXBT` and `SOL` at the table's values, the rule -- precision
    8, no ISO number, the code as the name, crypto -- every one of the six follows. A bump that
    reshapes a minted currency is red here before a store carrying it loads."""
```

with:

```python
    """Three reads in one child, since the adapter's parse registers what it mints: the table names
    exactly the base and quote codes the twelve pairs carry; a fresh process resolves the five the
    library's table holds at the table's values and none of the other six; and the adapter's parse
    of the twelve-pair basket fixture mints all eleven at the table's values, the six Kraken
    spellings on the rule -- precision 8, no ISO number, the code as the name, crypto. A bump that
    reshapes a minted currency is red here before a store carrying it loads."""
```

Replace, in `tests/test_engine_node.py`, this block:

```python
    assert facts["minted"] == {code: table[code] for code in ("SOL", "XXBT", "ZEUR")}, (facts["minted"], table)
```

with:

```python
    assert facts["minted"] == table, (facts["minted"], table)
```

Generate the twelve-pair fixture, from the repository root:

```bash
uv run python - <<'EOF'
import json
from pathlib import Path

from cli.engine.store import PAIR_KEYS

snapshot = json.loads(Path("tests/fixtures/kraken_assetpairs.json").read_text())
mint = json.loads(Path("tests/fixtures/kraken_assetpairs_mint.json").read_text())
parser_fields = {"aclass_base": "currency", "aclass_quote": "currency", "cost_decimals": 5, "execution_venue": "international", "fee_volume_currency": "ZUSD", "lot": "unit", "lot_multiplier": 1}
precisions = {
    "XETHXXBT": {"pair_decimals": 7, "lot_decimals": 5, "tick_size": "0.0000001"},
    "SOLXBT": {"pair_decimals": 7, "lot_decimals": 3, "tick_size": "0.0000001"},
}
basket = {}
for key in sorted(PAIR_KEYS.values()):
    if key in mint:
        basket[key] = mint[key]
    else:
        basket[key] = {**snapshot[key], **parser_fields, **precisions.get(key, {"pair_decimals": 1, "lot_decimals": 8, "tick_size": "0.1"})}
Path("tests/fixtures/kraken_assetpairs_basket.json").write_text(json.dumps(basket, indent=2) + "\n")
EOF
sha256sum tests/fixtures/kraken_assetpairs_basket.json
```

Expected: the sha256 `5cb0585cc37be85e10272978156b5a1497a930758258c2ed8d2d062f6be14ce3` and the file 1710 lines (`wc -l`); another digest means the mint fixture, the snapshot or `PAIR_KEYS` changed under this plan -- stop and report it to the controller rather than pinning a new digest.

Replace, in `.github/workflows/coverage.yml`, this block:

```yaml
      - run: git branch --force develop origin/develop
      - run: uv sync
```

with:

```yaml
      - run: git branch --force develop origin/develop
      # tests/test_cache_restart.py starts a real valkey-server per scenario and fails without the binary.
      - run: sudo apt-get update && sudo apt-get install -y valkey-server
      - run: uv sync
```

The apt line installs 7.2 on noble, `ubuntu-latest` when this plan was written, the version packages.ubuntu.com lists there: CI runs the harness on a third version beside the workstation's 8.1.1 and the fleet's 9.1.2, the readings that could differ being the ones spec D13's measured basis names, and the first CI run's install step prints the version it took. If the plan's first CI run shows the runner's apt carrying no `valkey-server` package, the spec's D13 names the substitute: Valkey's own binary tarball from its download site, pinned by version and sha256 in the workflow, in place of the apt line -- a decision the executor makes at that run and records in the PR body, never a skip.

- [ ] **Step 5: Run the harness and watch the eight scenarios pass**

Run: `uv run pytest tests/test_cache_restart.py -q -p no:cacheprovider`
Expected: `8 passed`, in about six minutes (`8 passed in 369.21s` on the workstation when this plan was written); a run past fifteen minutes is a hung child -- read `/tmp/pytest-of-<user>/pytest-current/<scenario>/node/phase*.log`, where every child's stdout lands.

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_cache_restart.py tests/test_engine_executor.py tests/test_engine_flatten.py tests/test_engine_node.py tests/test_kraken_fixture_mint_loopback.py tests/test_kraken_wheel_contract.py tests/test_kraken_window_reads.py tests/test_internal_terms_not_operator_visible.py tests/test_engine_stub_fidelity.py tests/test_nautilus_interface_pin.py tests/test_ci_uv_cache.py tests/test_required_status_checks_match_ci.py tests/test_kraken_fixture_mint.py tests/test_snapshot_assetpairs.py tests/test_docker_build_context.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `1739 passed, 3 skipped` when this plan was written, the skips `tests/test_engine_node.py`'s two live-venue gates and `tests/test_engine_flatten.py`'s one. The list is every module that imports `tests.kraken_loopback` or reads the workflows directory, with the pin, the stub walker, the internal-terms walker, and the two modules that read the fixtures the basket is generated from, the mint fixture and the snapshot; the modules that read the snapshot for other reasons are not run, since nothing here rewrites it.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 8: Commit**

```bash
git add .github/workflows/coverage.yml tests/kraken_loopback.py tests/cache_restart_child.py tests/test_cache_restart.py tests/test_engine_node.py tests/fixtures/kraken_assetpairs_basket.json
git commit -m "test(engine): the two-process restart harness against a real valkey-server, with the loopback's private endpoints and execution peer

Each scenario starts its own valkey-server on a free port under its tmp_path, with the cache
role's engine ACL line, and runs the engine's own node twice in a child interpreter: the two
client configs, the gate's venue reader and the three bare-client reads redirected to a loopback
that now answers GetWebSocketsToken, TradeBalance and TradesHistory paged by ofs, and a
scripted private WebSocket peer that sends the new, trade and canceled frames upstream parses.
The child refuses to build if any production default remains, hands the executor quotes on a
timer, stops the node at the window's end and writes a record the test reads. No environment
gate: a database is not a venue, so the binary's absence fails with the install command, and
coverage.yml installs it from apt before uv sync. A twelve-pair AssetPairs fixture is generated
from the mint fixture and the snapshot, since the snapshot's rows lack the fields the adapter
parses; its sha256 is pinned in the plan, and the currency pin's probe now parses it, so every one
of the eleven codes is held to what the adapter mints and not the mint fixture's three alone.

Scenarios, each the library's own behaviour and Task 2's boot line, measured on the pinned wheel
against Valkey 8.1.1: a resting order and a margin position restored across a restart under the
own strategy id, matched by venue_order_id, every later event on the own topic; a fill made while
down booked onto the restored order from TradesHistory, the restored position kept at its stored
quantity and the venue's position report closed by a synthesized EXTERNAL order, the boot line
listing both positions; a cancel made
while down never closing the restored order, since the mass status reads open orders only; a
trade frame on a restored kept reducer booked twice, inferred and then as the fill; an empty namespace
beside an open ledger row as a cold start reading zero, the order under the EXTERNAL txid and the
pass cancelling it as today; the cache unreachable at start failing inside the budget, refused in
under twenty seconds and silent between forty and ninety, with no private endpoint called; and
the server killed mid-run, the engine trading on with the ERROR and WARN lines on stdout and the
store behind at the return.

PROBE_VERDICT

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>"
```

- [ ] **Step 9: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 10: Prove the harness with three probes, then record their verdicts by a message-only amend**

The node's control misspells the boot line's text so the restored scenario fails; the mutations, in order: the retry count cut to two, which the silent shape's lower bound catches; the currency registration dropped, which the restore's loss of every instrument catches. The executor's control respells the pass's cancel line so the cold start fails; its mutation drops the pass's cancel call, the `sed` scoped to the pass's lines since the kill sweep's cancel is the same line at the same indentation, which the loopback's empty cancel listing catches. Each run is a few minutes: the selected scenarios run twice, once under the control and once under the mutation.

```bash
K1="restored_across or (unreachable and silent)"
infra/scripts/mutate-probe.sh --file cli/engine/node.py --control 's/"cache restore: %d order(s), %d position(s) restored"/"cache restor: %d order(s), %d position(s) restored"/' \
  --mutation 's/number_of_retries=10,/number_of_retries=2,/' \
  -- uv run pytest tests/test_cache_restart.py -q -p no:cacheprovider -k "$K1"
infra/scripts/mutate-probe.sh --file cli/engine/node.py --control 's/"cache restore: %d order(s), %d position(s) restored"/"cache restor: %d order(s), %d position(s) restored"/' \
  --mutation 's/^        _register_kraken_currencies()$/        pass/' \
  -- uv run pytest tests/test_cache_restart.py -q -p no:cacheprovider -k "$K1"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control 's/"canceling adopted resting order %s -- %s",/"cancelling adopted resting order %s -- %s",/' \
  --mutation '/"canceling adopted resting order %s -- %s",/,/^            except Exception:/s/^                self._client.cancel_order(order.client_order_id)$/                pass/' \
  -- uv run pytest tests/test_cache_restart.py -q -p no:cacheprovider -k "empty_cache"
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message with the text below: write the whole message, that line replaced, to a file under `.tmp/` (gitignored) and amend from it with `git commit --amend -F <file>`; the amend changes the message only, no file.

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/engine/node.py`, control the boot line's text
misspelled so the restored scenario fails, through `-k "restored_across or (unreachable and
silent)"`: the retry count cut to two, KILLED, control proven; the currency registration dropped,
KILLED, control proven; over `cli/engine/executor.py`, control the pass's cancel line respelled
so the cold start fails, through `-k "empty_cache"`: the pass's cancel call dropped, KILLED,
control proven.
```

Run: `git status --porcelain` -- Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` -- Expected: `0`; `git log -1 --format=%B | grep -c 'infra/scripts/mutate-probe.sh'` -- Expected: `1`, the verdict naming the script.

---
### Task 4: The startup pass under a restored Cache, the kept reducer's credit and intent, the realized baseline, the mixed-inventory refusal, and the withdrawal check's second source

This task is spec D6 to D10, D12's executor half and D19: the executor learns at construction which orders the Cache restored, asks the venue over every one of them and over every finished row with fills, writes a restored order the venue holds closed from the venue's report and sends it no cancel, cancels a restored opener the venue holds open and keeps a ledgered reducer, credits a restored row's fills nothing and repairs the row from the venue at the re-read pass, writes the kept reducer's intent at its terminal, subtracts the realized PnL the Cache held at start, refuses a plan whose pair holds spot inventory beside a margin position while the cache is enabled, reads the venue's trade history before its withdrawal check trips, and rewrites the docstrings a persistent cache made false. The harness of Task 3 gains the executor's assertions in five scenarios and the cold-start scenario takes its measured shape, so every rule here is measured against the library's own restore and not against the stubs alone.

What this task decides, where the spec leaves it open:

- The restored set is read at construction, inside `on_start`, through `orders(venue=_VENUE)` -- every order the Cache holds for the venue, this engine's own and the EXTERNAL copies alike, open or closed: a kept reducer's double-booked copy reads FILLED and a set read from the open orders alone would trust exactly that copy at the next restart; and the store persists the EXTERNAL copy a previous process adopted by its txid and restores it with that process's fills, the same library state as a restored own order, which nothing tells from a copy this boot's reconciliation created, so the venue answers for both and both credit their fills nothing -- only when the cache is enabled, without which the Cache holds at start what this boot's reconciliation adopted and nothing else; the lines that name a restored order, the boot line's and the classification's, key on the own strategy id, since an own-id order in the Cache at `on_start` is by construction restored, and an adopted order keeps its line; each restored order whose row the window carries is attached there too, under its own id and its txid, since a fill on it can reach the own topic in the seconds before the first tick, where `_trip_on_fill` runs first and an unattached order latches the kill switch (D6's attach at `on_start`), and the classification loop attaches again what it classifies. `StubCache.orders` and `orders_open` honour `strategy_id` by the exact id, as the real Cache does. The realized baseline is read unconditionally: a Cache with nothing restored yields zero, and the one existing test that seeded closed positions before construction now seeds them after, since what the Cache holds at construction is by this decision the baseline.
- The venue answers for every row of the restored set whatever its Cache copy's status, not for the non-terminal ones alone as 00118 D11's text has it: the copy of a kept reducer whose trade frame was double-booked reads FILLED where the venue says partial (D7's measured 0.8 against 0.6), and a rule keyed on the copy's status would trust exactly the copy the double booking corrupted. The cost is the same one venue read per restart.
- The kept reducer's intent (D8) is written by `_settle_restored_intent`, once, at the row's terminal, by whichever path ends the row: the detached path's completion or terminal-state write, the external path's, or the re-read pass's repair where the fill's credit was nothing. The last departs from D20's letter that the pass writes no intent, and the departure is forced: with the credit at zero a fill never completes the row on the event path, so a reducer that fills whole would keep its intent `pending` for the process's life; the pass writes it only for a row of the restored set whose intent still reads `pending`, from the row's own state, and no later pass revisits it. A row a fill reached since the pass last read it is not settled by the event's path: its `filled_qty` is the credit-0 figure until the pass repairs it, and a terminal before the next tick -- the venue's cancel ack, an expiry -- puts it among the window's closed rows, which the pass's population takes for the rows of `_restored_fills` too, so the intent is written after the repair, at the repaired quantity.
- The detached path's external-path writes (D12) apply to rows of the restored set alone: this process's own superseded and finished orders keep the no-claim rule their tests pin, and a restored order is the population the writes exist for.
- The mixed-inventory refusal (D12, carried from 00118 D11) refuses an opening intent alone -- a close takes inventory off -- and by the kind it would add: a spot open where the venue's margin positions hold the pair, read through `read_venue_positions` once per plan that carries an open, a bare-client read on the passes' nonce terms -- which `_pickup` keeps by holding such a plan, the cache enabled, until `_nothing_in_flight` holds, the file left for the next tick: on the first tick the startup pass's cancels are still PENDING_CANCEL when the pickup runs, and the read would race them on the one key -- and a margin open where the venue state's balances, already read, hold the pair's base at or above the pair's `ordermin`, since a lot under it is dust the engine cannot sell and would otherwise refuse every margin open on the pair for as long as the cache is enabled. The balances are keyed by the adapter's codes, which spell DOGE `XDG`, so `_spot_balance` reads a base through `resolve_base`, the rule `read_venue_holdings` reads the same balances by, in place of its own `X`-prefix tuple and the BTC one: a base the tuple missed read 0 and admitted a margin open beside a spot lot, and the spot close's bound, the helper's other caller, read the same 0: every DOGE spot close refused at `reduce_only` and none refuted at `full`. The Cache's net was set aside as the margin figure: the Cache books a spot fill as a position too, so the engine's own spot lot read as a margin one and every later plan on the pair was refused, closes included. A read that fails refuses each open intent by name, since the shape is then unknown. The reader is a fifth constructor keyword beside `venue_fills`, with the same stub, refusal and child redirect.
- The withdrawal check's second source (D19) is `_trades_cover`: where an order's figure falls short of the ledger, on the open sweep's negative arm or a finished row's, the pass reads the trade history once through `read_venue_fills`, from one hour before the earliest boundary among the pass's rows, which both passes set before any row asks (`_reset_fills_read`), keeps the sums by txid for the pass, and trips only when the row's txid sums short; a read that fails is not retried in the pass, so N short rows under an unreachable history cost one `_VENUE_READ_TIMEOUT_SECONDS` and never N; a covered row keeps its figure, logs the reading at WARNING and joins `_rows_the_pass_repaired`, so the fill the library infers at a cancel's ack credits it only what the Cache holds beyond it -- measured on the harness, the inferred 0.4 credits 0 and the row settles at 0.4. A read that fails or a row with no txid answers None and the trip stands on the order's figure. The reader is a constructor keyword beside the other three; the executor tests' `_executor` hands every case an empty history unless it passes one, so the existing withdrawal cases trip as before, and the autouse refusal of the production read sets the name with `raising=False`, since the name lands with the source fence and the cases fail on their own terms before it.
- A restored row's fill logs `a fill on restored order <id> credits nothing until the venue is read -- the next restart is taken flat` at WARNING in `_fill_credit`, at the fill, once per row until the re-read pass reads it; why the line marks a fill the library may have booked twice and takes the restart flat whichever it was is spec D8's, and the restart rule's test keys on this line and not the pass's.
- The pass names a restored order it cancels with its fill state, `canceling restored order <id>, <state> -- <reason>` (D9), a separate line from the adopted order's, whose text the executor tests and drills page pin.
- `_cache_enabled` is read once at construction from `config.cache` through a local, since `tests/test_engine_executor.py`'s accessor walk reads every attribute reached under a holder named `cache` as a Cache accessor.

**Files:**
- Modify: `cli/engine/executor.py` (`read_venue_fills` after `read_venue_orders`; `_margin_positions` and `read_venue_positions` beside `read_venue_holdings`, whose position loop moves into the first; the constructor's restored set, restored fills, realized baseline, `_cache_enabled`, `venue_fills`, `venue_positions` and the fills read's per-pass state; `_read_restored` with its attach, `_read_realized_baseline`, `_reset_fills_read`; `_arm_reread_after_mint`'s and `_nothing_in_flight`'s docstrings; `_adopt_resting_orders`' docstring, fills-read reset and classification loop with its stale-copy skip; `_reread_pass`'s population over the open and the closed rows, fills-read reset, lines and clear; `_reconcile_adopted_rows`' venue-wins branch; `_read_venue_orders`; `_cached_order`'s and `_cache_lookup`'s docstrings; `_trades_cover`, `_venue_answers`, `_restored_row`, `_settle_restored_intent`; `_pickup`'s hold; `_reconcile_adopted_row`'s covered arm; `_reconcile_finished_rows` and `_reconcile_finished_row`'s keyword and covered arm; `_mixed_inventory_refusals` and its call in `_pickup`; `_spot_balance` reading through `resolve_base`, `_BTC_BALANCE_ALIASES` removed; `_trip_on_fill`'s docstring; `_realized_eur` and `_realized_on`; `_fill_credit`; `_on_detached_event`; `_on_external_event`)
- Modify: `cli/engine/node.py` (the strategy class's and the observer's docstrings)
- Modify: `tests/test_engine_executor.py` (`CacheSettings` and `FillReport` imported; `_orders_under`, `StubCache.orders` and `orders_open` honouring `strategy_id`; `_executor` taking `venue_fills` and `venue_positions` with empty defaults; the autouse refusal of the fills and positions reads; `_fill_report`, `_VenueFills` and `_VenuePositions`; `_resting_limit_order` taking `strategy_id`; the realized-PnL test's closes moved after construction; the restored cases and the withdrawal-check cases in two new sections at the end of the file)
- Modify: `tests/cache_restart_child.py` (the fourth and fifth bare-client reads redirected and checked)
- Modify: `tests/test_engine_stub_fidelity.py` (`_VenueFills` and `_VenuePositions` classified as stand-ins for `read_venue_fills` and `read_venue_positions`)
- Modify: `tests/test_cache_restart.py` (`PHASE2_WINDOW` 20; the executor's assertions in the restored, fill-while-down, cancelled-while-down and kept-reducer scenarios, the realized readings among the last's; the cold-start scenario at the measured shape, the opener filled 0.4 before the stop; the ninth scenario, the trade frame on a restored opener racing the pass's cancel)

**Interfaces:**
- Consumes: `ProbeExecutor`, `_cached_order`, `_cache_lookup`, `_reconcile_adopted_row`, `_attach`, `_arm_reread_after_mint`, `_venue_terminal_state`, `_cache_net`, `_spot_balance`, `_ordered_qty`, `restored_fill_state`, `_inc_order`, `_bare_client`, `_VENUE_READ_MARGIN`, `_ADOPTED_TERMINAL_STATES`, `_OPEN_ORDER_STATES`, `FLAT_TOLERANCE`, `pending_plan_intents`, `update_plan_intent`, `update_submitted_row` in `cli/engine/executor.py` and `cli/engine/execledger.py`; `INSTRUMENT_IDS` in `cli/engine/instruments.py`; `KrakenSpotHttpClient.request_fill_reports`, `request_position_status_reports` and `FillReport` in the library; `QUOTE_CURRENCY` and `resolve_base` in `cli/engine/flatten.py`; `StubCache`, `StubClient`, `_executor`, `_config`, `_gate`, `_submitted_row`, `_pending_plan_entry`, `_resting_limit_order`, `_closed_order`, `_report`, `_VenueOrders`, `_fill`, `_event`, `_record`, `_intent_entry`, `_plan_entry`, `_drop_plan`, `_plan_dict`, `_executor_errors`, `_kill_file`, `RecordingMetrics`, `kill_trip_expected` in `tests/test_engine_executor.py`; `_script_first_fill`, `_script_cancel_ack`, `_Node.rows`, `_Node.intents` in `tests/test_cache_restart.py`
- Produces: `read_venue_fills(since, *, base_url=None) -> list`; `_margin_positions(reports) -> dict[str, float]`; `read_venue_positions(*, base_url=None) -> dict[str, float]`; `ProbeExecutor(..., venue_fills=None, venue_positions=None)`; `ProbeExecutor._restored: dict[str, str | None]`, `._restored_fills: set[str]`, `._realized_baseline: dict[InstrumentId, float]`, `._cache_enabled: bool`, `._venue_fills_read: dict[str, float] | None`, `._venue_fills_failed: bool`, `._venue_fills_floor: datetime | None`; `_read_restored() -> None`; `_read_realized_baseline() -> None`; `_reset_fills_read(entries) -> None`; `_trades_cover(boundary, venue_order_id, ledgered) -> bool | None`; `_venue_answers(row, *, finished) -> bool`; `_restored_row(row) -> bool`; `_settle_restored_intent(boundary, row) -> None`; `_realized_on(instrument_id) -> float`; `_mixed_inventory_refusals(plan, state) -> list[str]`; `_reconcile_finished_row(..., *, venue_order_id=None)`; in the tests, `_cache_config(tmp_path, enabled=True)`, `_restored_order(client_order_id, *, filled, quantity)`, `_kept_reducer(tmp_path, venue)`, `_fill_report(txid, qty, *, trade_id)`, `_VenueFills(*reports, raises=None)`, `_VenuePositions(held=None, *, raises=None)`, `_orders_under(strategy_id, held)`, `_cold_start_row(tmp_path, *, finished)`

- [ ] **Step 1: Confirm Task 3's marker and this task's absence**

Run: `grep -c 'serve_with_sockets' tests/kraken_loopback.py; grep -c '_restored' cli/engine/executor.py; grep -c 'PHASE2_WINDOW = 16' tests/test_cache_restart.py`
Expected: `1`, then `0`, then `1`. A `0` first means Task 3 is not in; a `_restored` already present means this task is; stop and report either to the controller.

- [ ] **Step 2: The failing cases in `tests/test_engine_executor.py`, the child's fourth redirect, the harness's executor assertions in `tests/test_cache_restart.py`, and the stub table's entry**

Replace, in `tests/test_engine_executor.py`, this block:

```python
    Currency,
    CurrencyPair,
    InstrumentId,
    LimitOrder,
```

with:

```python
    Currency,
    CurrencyPair,
    FillReport,
    InstrumentId,
    LimitOrder,
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
import cli.engine.executor as executor_module
import cli.engine.venuestate as venuestate_module
from cli.config import EngineConfig
from cli.engine.errors import EngineError, EngineJournalError
from cli.engine.execgate import ARM_FILE, KILL_FILE, RESTART_HOLD_FILE, ExecutionGate, GateLevel, GateVerdict, exec_dir
```

with:

```python
import cli.engine.executor as executor_module
import cli.engine.venuestate as venuestate_module
from cli.config import CacheSettings, EngineConfig
from cli.engine.errors import EngineError, EngineJournalError
from cli.engine.execgate import ARM_FILE, KILL_FILE, RESTART_HOLD_FILE, ExecutionGate, GateLevel, GateVerdict, exec_dir
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
class StubCache:
```

with:

```python
def _orders_under(strategy_id, held):
    """`held` under `strategy_id`, the real Cache's own filter: every order when none is given, else
    the ones whose id equals it exactly, and a plain str refused as the typed accessor refuses it."""
    if strategy_id is None:
        return held
    if not isinstance(strategy_id, StrategyId):
        raise TypeError(f"Argument 'strategy_id' has incorrect type (expected StrategyId, got {type(strategy_id).__name__})")
    return [o for o in held if str(getattr(o, "strategy_id", None)) == str(strategy_id)]


class StubCache:
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
        )

    def orders_open(self, *, venue=None, **kwargs):
        return list(self._open_orders)

    def orders_inflight(self, *, venue=None, **kwargs):
```

with:

```python
        )

    def orders(self, *, venue=None, strategy_id=None, **kwargs):
        """The whole index, open and closed, with `strategy_id` honoured as the real Cache honours it,
        by the exact id: the restored set is what the Cache holds under this engine's own, closed
        copies included, never the EXTERNAL identity's adopted orders."""
        return _orders_under(strategy_id, [*self._open_orders, *self._closed_orders])

    def orders_open(self, *, venue=None, strategy_id=None, **kwargs):
        """The open half, `strategy_id` honoured the same way: the boot line's read."""
        return _orders_under(strategy_id, list(self._open_orders))

    def orders_inflight(self, *, venue=None, **kwargs):
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    venue_cancel=None,
    venue_holdings=None,
) -> ProbeExecutor:
    client = client if client is not None else StubClient()
```

with:

```python
    venue_cancel=None,
    venue_holdings=None,
    venue_fills=None,
    venue_positions=None,
) -> ProbeExecutor:
    client = client if client is not None else StubClient()
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
        venue_orders=venue_orders,
        venue_cancel=venue_cancel,
        # An empty answer unless a case hands one in: the settle then publishes nothing, and the read
        # every startup pass makes reaches no venue.
        venue_holdings=venue_holdings if venue_holdings is not None else _VenueHoldings(),
    )
```

with:

```python
        venue_orders=venue_orders,
        venue_cancel=venue_cancel,
        # An empty trade history unless a case hands one in: a withdrawal test's shortfall then trips
        # as it did before the history became the check's second source.
        venue_fills=venue_fills if venue_fills is not None else _VenueFills(),
        # An empty answer unless a case hands one in: the settle then publishes nothing, and the read
        # every startup pass makes reaches no venue.
        venue_holdings=venue_holdings if venue_holdings is not None else _VenueHoldings(),
        # No margin position unless a case hands one in: the mixed-inventory check then refuses nothing.
        venue_positions=venue_positions if venue_positions is not None else _VenuePositions(),
    )
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
        return holdings(base_url=base_url)

    monkeypatch.setattr(executor_module, "read_venue_orders", _refuse)
    monkeypatch.setattr(executor_module, "cancel_venue_order", _refuse_cancel)
    monkeypatch.setattr(executor_module, "read_venue_holdings", _refuse_holdings)


```

with:

```python
        return holdings(base_url=base_url)

    def _refuse_fills(since, **kwargs):
        pytest.fail(f"a test reached the production venue fills read (since {since.isoformat()}) -- pass venue_fills")

    def _refuse_positions(**kwargs):
        pytest.fail("a test reached the production venue positions read -- pass venue_positions")

    monkeypatch.setattr(executor_module, "read_venue_orders", _refuse)
    monkeypatch.setattr(executor_module, "cancel_venue_order", _refuse_cancel)
    monkeypatch.setattr(executor_module, "read_venue_holdings", _refuse_holdings)
    # `raising=False`: the two reads land with their source fence, and the cases fail on their own terms before it.
    monkeypatch.setattr(executor_module, "read_venue_fills", _refuse_fills, raising=False)
    monkeypatch.setattr(executor_module, "read_venue_positions", _refuse_positions, raising=False)


```

Replace, in `tests/test_engine_executor.py`, this block:

```python
def _read_venue_holdings(**kwargs):
```

with:

```python
class _VenuePositions:
    """The executor's `venue_positions` reader: answers `held`, the venue's margin positions by symbol,
    or raises `raises`, and counts its calls -- one per plan that carries an opening intent."""

    def __init__(self, held=None, *, raises=None):
        self.held = {} if held is None else dict(held)
        self.calls = 0
        self._raises = raises

    def __call__(self):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return dict(self.held)


def _read_venue_holdings(**kwargs):
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    `since` of every call -- the startup pass reads once, and the re-read pass once more per arm
    over the rows it minted terminal; any other second call is a finding."""

    def __init__(self, *reports, raises=None):
```

with:

```python
    `since` of every call -- the startup pass reads once, and the re-read pass once more per arm
    over the rows it minted terminal; any other second call is a finding."""

    def __init__(self, *reports, raises=None):
        self.reports = list(reports)
        self.calls: list[datetime] = []
        self._raises = raises

    def __call__(self, since):
        self.calls.append(since)
        if self._raises is not None:
            raise self._raises
        return list(self.reports)


def _fill_report(txid, qty, *, trade_id="T-h1"):
    """A REAL `FillReport` in the shape the adapter builds from Kraken's trade history: the fill named by
    the order's txid and its own trade id, no client order id."""
    return FillReport(
        account_id=AccountId("KRAKEN-001"),
        instrument_id=InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]),
        venue_order_id=VenueOrderId(txid),
        trade_id=TradeId(trade_id),
        order_side=OrderSide.SELL,
        last_qty=Quantity.from_str(qty),
        last_px=Price.from_str("30000.0"),
        commission=Money(0.08, Currency.from_str("EUR")),
        liquidity_side=LiquiditySide.MAKER,
        ts_event=0,
        ts_init=0,
    )


class _VenueFills:
    """The executor's `venue_fills` reader: answers `reports`, or raises `raises`, and records the `since`
    of every call -- the withdrawal check reads once per pass, and only when a figure fell short."""

    def __init__(self, *reports, raises=None):
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    """`Position.realized_pnl` is `Money | None`. The None is skipped rather than `float()`-ed, the
    CLOSED positions are summed too (a round trip's PnL lives nowhere else), and a non-EUR position
    is left out rather than added to a EUR total."""
    client = StubClient()
    client.cache.close_position("BTC/EUR", Money(-4.5, Currency.from_str("ZEUR")))
    client.cache.close_position("BTC/EUR", Money(1.25, Currency.from_str("EUR")))
    client.cache.close_position("BTC/EUR", Money(9999.0, Currency.from_str("XXBT")))  # never summed into a EUR total
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

```

with:

```python
    """`Position.realized_pnl` is `Money | None`. The None is skipped rather than `float()`-ed, the
    CLOSED positions are summed too (a round trip's PnL lives nowhere else), and a non-EUR position
    is left out rather than added to a EUR total. The round trips close after the executor is built:
    what the Cache holds at construction is the baseline the gauge subtracts."""
    client = StubClient()
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, client=client)
    client.cache.close_position("BTC/EUR", Money(-4.5, Currency.from_str("ZEUR")))
    client.cache.close_position("BTC/EUR", Money(1.25, Currency.from_str("EUR")))
    client.cache.close_position("BTC/EUR", Money(9999.0, Currency.from_str("XXBT")))  # never summed into a EUR total
    _drop_plan(tmp_path, _plan_dict())

```

Replace, in `tests/test_engine_executor.py`, this block:

```python


def _resting_limit_order(client_order_id, *, quantity="1.0", venue_order_id=None):
    """A REAL `LimitOrder` resting at the venue, driven to ACCEPTED by the library's own events.

```

with:

```python


def _resting_limit_order(client_order_id, *, quantity="1.0", venue_order_id=None, strategy_id=_STUB_STRATEGY_ID):
    """A REAL `LimitOrder` resting at the venue, driven to ACCEPTED by the library's own events.

```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    acks it REFUSES, which is where reading the order rather than the event's name earns its place.
    `_resting_limit_order(_TXID, venue_order_id=_TXID)` is the shape a restart's reconciliation
    leaves on the pinned wheel: the order named by its txid on both ids."""
    head = (_TRADER_ID, _STUB_STRATEGY_ID, InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]), ClientOrderId(client_order_id))
    order = LimitOrder(
        *head, OrderSide.BUY, Quantity.from_str(quantity), Price.from_str("30000.0"), TimeInForce.GTC,
```

with:

```python
    acks it REFUSES, which is where reading the order rather than the event's name earns its place.
    `_resting_limit_order(_TXID, venue_order_id=_TXID)` is the shape a restart's reconciliation
    leaves on the pinned wheel: the order named by its txid on both ids. Under the stub's own
    `strategy_id` with the id this engine minted, it is the shape the cache restores."""
    head = (_TRADER_ID, strategy_id, InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]), ClientOrderId(client_order_id))
    order = LimitOrder(
        *head, OrderSide.BUY, Quantity.from_str(quantity), Price.from_str("30000.0"), TimeInForce.GTC,
```

Replace, in `tests/test_engine_executor.py`, this block:

```python
    with pytest.raises(EngineJournalError, match="timezone-aware"):
        reader(journal, boundary)
```

with:

```python
    with pytest.raises(EngineJournalError, match="timezone-aware"):
        reader(journal, boundary)


# --- the cache's restored orders and positions (spec 00120 D6 to D10, D12) ------------------------


def _cache_config(tmp_path, enabled=True):
    return _config(tmp_path, cache=CacheSettings(enabled=enabled))


def _restored_order(client_order_id="O-restored", *, filled=None, quantity="0.001"):
    """The Cache's copy of an order a previous process placed, restored under this engine's own id and
    the txid it recorded, with the previous process's fills applied when `filled` is given."""
    order = _resting_limit_order(client_order_id, quantity=quantity, venue_order_id=_TXID)
    if filled is not None:
        order.apply(_fill(client_order_id, filled, venue_order_id=VenueOrderId(_TXID), trade_id="T-before"))
    return order


@pytest.mark.parametrize("enabled", [True, False])
def test_the_restored_set_is_every_order_the_cache_holds_at_construction_only_with_the_cache_enabled(tmp_path, enabled):
    external = _resting_limit_order("OEXTRN-AAAAA-BBBBBB", venue_order_id="OEXTRN-AAAAA-BBBBBB", strategy_id=StrategyId("EXTERNAL"))
    client = StubClient(StubCache(open_orders=[_restored_order(), external]))

    ex = _executor(tmp_path, client=client, config=_cache_config(tmp_path, enabled))

    assert ex._restored == ({"O-restored": _TXID, "OEXTRN-AAAAA-BBBBBB": "OEXTRN-AAAAA-BBBBBB"} if enabled else {})


def test_a_restored_set_the_cache_cannot_read_is_empty_at_critical(tmp_path):
    class _Unreadable(StubCache):
        def orders(self, *, venue=None, strategy_id=None, **kwargs):
            raise RuntimeError("cache read failed")

    with _executor_errors(level=logging.CRITICAL) as records:
        ex = _executor(tmp_path, client=StubClient(_Unreadable()), config=_cache_config(tmp_path))

    assert ex._restored == {}
    assert [r.getMessage() for r in records] == [
        "the restored orders could not be read at start -- the startup pass reads the Cache's copy of each"
    ]


@pytest.mark.parametrize(
    "enabled, filled_qty, events",
    [(True, 0.0006, ["OrderAccepted", "reconciled"]), (False, 0.0004, ["OrderAccepted"])],
)
def test_the_startup_pass_asks_the_venue_over_a_restored_orders_cache_copy_and_the_report_wins(
    tmp_path, enabled, filled_qty, events
):
    """The Cache's copy is the previous process's view, 0.0004 filled, and the ledger agrees with it;
    the venue says 0.0006. With the cache enabled the venue is read and its figure repairs the row;
    without it the Cache's copy answers as before and no venue read is made."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-restored", reduce_only=True, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-restored", add_filled_qty=0.0004)
    client = StubClient(StubCache(open_orders=[_restored_order(filled=0.0004)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0006"))
    ex = _executor(
        tmp_path,
        client=client,
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        config=_cache_config(tmp_path, enabled),
    )

    ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], [e.get("type") or e.get("event") for e in row["events"]]) == (filled_qty, events)
    assert venue.calls == ([_boundary(earlier) - timedelta(hours=1)] if enabled else [])
    assert client.canceled == []  # a ledgered reducer, kept on both settings


def test_a_restored_order_the_venue_reports_closed_has_its_row_written_from_the_report_and_no_cancel_sent(tmp_path):
    """Mass status reads open orders only, so an order that filled while the engine was down comes back
    open in the Cache; the venue's report writes the row, settles the intent through the sweep, and the
    stale open copy is left where it is with no cancel through the handle."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-restored", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_restored_order()]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.FILLED, filled_qty="0.001"))
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("filled", 0.001)
    assert client.canceled == [] and "O-restored" in ex._attached
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == "filled"
    assert metrics.orders == ["filled"]
    assert "restored order O-restored is filled at the venue -- its stale open copy stays in the Cache and no cancel is sent" in [
        r.getMessage() for r in records
    ]


def test_a_restored_orders_stale_open_copy_is_not_cancelled_at_a_later_restart_once_its_row_is_closed(tmp_path):
    """The restart after the one that wrote the row terminal: the row is among the window's closed
    rows, the Cache still lists the copy open, and the classification loop sends it no cancel."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-restored", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-restored", state="filled", add_filled_qty=0.001)
    client = StubClient(StubCache(open_orders=[_restored_order()]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.FILLED, filled_qty="0.001"))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    assert client.canceled == [] and venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert "restored order O-restored is filled at the venue -- its stale open copy stays in the Cache and no cancel is sent" in [
        r.getMessage() for r in records
    ]
    assert not _kill_file(tmp_path).exists()


@pytest.mark.parametrize("reduce_only, canceled, line", [
    (False, ["O-restored"], "canceling restored order O-restored, partial -- the ledger does not carry it as a resting reducer"),
    (True, [], "adopted resting order O-restored is a ledgered reducer -- left resting and re-attached"),
])  # fmt: skip
def test_a_restored_opener_the_venue_reports_open_is_cancelled_by_the_pass_and_a_kept_reducer_is_not(
    tmp_path, reduce_only, canceled, line
):
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-restored", reduce_only=reduce_only, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_restored_order(filled=0.0004)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0004"))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == canceled
    assert line in [r.getMessage() for r in records]
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == ("revoked" if canceled else "pending")


def test_a_finished_row_with_fills_is_read_at_the_venue_over_the_caches_closed_copy_with_the_cache_enabled(
    tmp_path, kill_trip_expected
):
    """The withdrawal check compared against the Cache's restored copy would compare the ledger with
    itself: the copy agrees with the row at 0.001, the venue says the order ended with 0.0006."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-finished", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-finished", state="filled", add_filled_qty=0.001)
    cache = StubCache(closed_orders=[_closed_order("O-finished", OrderStatus.FILLED, filled_qty=0.001, venue_order_id=_TXID)])
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED, filled_qty="0.0006"))
    ex = _executor(
        tmp_path,
        client=StubClient(cache),
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        config=_cache_config(tmp_path),
    )

    ex.on_timer(NOW)

    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert _record(tmp_path, earlier)["submitted"][0]["events"][-1]["event"] == "withdrawn"
    assert (
        f"order O-finished (Kraken {_TXID}) shows 0.0006 filled at the venue, less than the 0.001"
        in _kill_file(tmp_path).read_text()
    )


def test_a_finished_row_the_caches_closed_copy_agrees_with_is_not_read_at_the_venue_without_the_cache(tmp_path):
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-finished", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-finished", state="filled", add_filled_qty=0.001)
    cache = StubCache(closed_orders=[_closed_order("O-finished", OrderStatus.FILLED, filled_qty=0.001, venue_order_id=_TXID)])
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED, filled_qty="0.0006"))
    ex = _executor(tmp_path, client=StubClient(cache), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert venue.calls == [] and not _kill_file(tmp_path).exists()


def test_a_fill_on_a_restored_row_before_the_first_tick_lands_in_its_row_and_trips_nothing(tmp_path):
    """The attach at construction (spec 00120 D6): a restored order's fill can reach the own topic in
    the seconds between `on_start` and the first tick, where `_trip_on_fill` runs first and an order
    no row is attached for latches the kill switch. Attached at construction, under its own id and
    its txid, the fill takes the detached path -- the row's `fill` line with `credited` 0, no kill
    file, and the re-read pass armed for the repair."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_restored_order("O-reducer")]))
    ex = _executor(tmp_path, client=client, config=_cache_config(tmp_path))
    assert not ex._adopted and "O-reducer" in ex._attached and _TXID in ex._attached_by_venue

    fill = _fill("O-reducer", 0.0004, venue_order_id=VenueOrderId(_TXID), trade_id="T-early")
    client.cache.order(ClientOrderId("O-reducer")).apply(fill)
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_order_event(fill)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], row["state"]) == (0.0, "accepted")
    assert row["events"][-1]["event"] == "fill" and (row["events"][-1]["qty"], row["events"][-1]["credited"]) == (0.0004, 0.0)
    assert not _kill_file(tmp_path).exists() and ex._reread_tries == 3
    assert [r.getMessage() for r in records] == [
        "a fill on restored order O-reducer credits nothing until the venue is read -- the next restart is taken flat"
    ]


def test_a_restored_order_the_cache_holds_closed_is_read_at_the_venue_and_the_report_wins(tmp_path):
    """The restored set is every order the Cache holds under the own id, closed copies included: a
    kept reducer's double-booked copy reads FILLED where the venue says partial (spec 00120 D7), and
    a set read from the open orders alone would trust exactly that copy. The row, repaired to 0.0007
    by the previous process, stays there: the venue is read and its partial report is the figure."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-reducer", add_filled_qty=0.0007)
    client = StubClient(StubCache(closed_orders=[_restored_order("O-reducer", filled=0.001)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0007"))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )
    assert client.cache.order(ClientOrderId("O-reducer")).status == OrderStatus.FILLED

    ex.on_timer(NOW)

    assert ex._restored == {"O-reducer": _TXID} and venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"], [e.get("event") for e in row["events"] if e.get("event")]) == ("accepted", 0.0007, [])
    assert not _kill_file(tmp_path).exists() and "O-reducer" in ex._attached


def test_a_restored_external_copy_of_a_kept_reducer_credits_its_fills_nothing_and_the_pass_repairs_the_row(tmp_path):
    """The store persists the EXTERNAL copy a previous process adopted by its txid and restores it with
    that process's fills, the library state a restored own order has and the same double booking on a
    trade frame: the copy is in the restored set under its txid, the venue answers for it, its fills
    credit the row nothing, and the re-read pass repairs the row from the venue's figure."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-reducer", add_filled_qty=0.0004)
    copy = _resting_limit_order(_TXID, venue_order_id=_TXID, strategy_id=StrategyId("EXTERNAL"))
    copy.apply(_fill(_TXID, 0.0004, venue_order_id=VenueOrderId(_TXID), trade_id="T-before", strategy_id=StrategyId("EXTERNAL")))
    client = StubClient(StubCache(open_orders=[copy]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0004"))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    assert ex._restored == {_TXID: _TXID} and venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert client.canceled == [] and f"adopted resting order {_TXID} is a ledgered reducer -- left resting and re-attached" in [
        r.getMessage() for r in records
    ]
    for trade_id in ("T-inferred", "T-frame"):
        fill = _fill(_TXID, 0.0003, venue_order_id=VenueOrderId(_TXID), trade_id=trade_id, strategy_id=StrategyId("EXTERNAL"))
        _deliver_external_event(ex, client, fill)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], row["state"]) == (0.0004, "accepted") and not _kill_file(tmp_path).exists()
    assert [(e["qty"], e.get("credited")) for e in row["events"] if e.get("event") == "fill"] == [(0.0003, 0.0), (0.0003, 0.0)]

    venue.reports = [_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0007")]
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW + timedelta(seconds=5))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], row["state"], row["events"][-1]["event"]) == (0.0007, "accepted", "reconciled")
    assert "the re-read pass reads 1 restored row(s) with a fill since its last read against the venue" in [
        r.getMessage() for r in records
    ]
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == "pending" and len(venue.calls) == 2


def _kept_reducer(tmp_path, venue):
    """A restored reducer the startup pass keeps: its row, its pending intent, the Cache's copy under
    this engine's own id, and the pass run against `venue`'s first report."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_restored_order("O-reducer")]))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )
    ex.on_timer(NOW)
    assert client.canceled == [] and ex._restored == {"O-reducer": _TXID}
    return ex, client, earlier


def test_a_fill_on_a_restored_row_credits_nothing_and_the_re_read_pass_repairs_the_row_from_the_venue(tmp_path):
    """D8's credit rule and the pass that follows it: the frame's fill lands in the row as the stream's
    record with `credited` 0, the row's quantity waits for the venue's cumulative figure, and the
    pass reads it on the next tick with nothing in flight; the completing repair writes the row
    `filled`, counts it, and writes the kept reducer's intent."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    ex, client, earlier = _kept_reducer(tmp_path, venue)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    order = client.cache.order(ClientOrderId("O-reducer"))

    fill = _fill("O-reducer", 0.0004, venue_order_id=VenueOrderId(_TXID), trade_id="T-2")
    order.apply(fill)
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_order_event(fill)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], row["state"]) == (0.0, "accepted")
    assert row["events"][-1]["event"] == "fill" and (row["events"][-1]["qty"], row["events"][-1]["credited"]) == (0.0004, 0.0)
    assert not _kill_file(tmp_path).exists() and ex._reread_tries == 3
    assert [r.getMessage() for r in records] == [
        "a fill on restored order O-reducer credits nothing until the venue is read -- the next restart is taken flat"
    ]

    venue.reports = [_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0004")]
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW + timedelta(seconds=5))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], row["state"], row["events"][-1]["event"]) == (0.0004, "accepted", "reconciled")
    assert len(venue.calls) == 2 and _intent_entry(tmp_path, 0, earlier)["outcome"] == "pending"
    assert [r.getMessage() for r in records][:1] == [
        "the re-read pass reads 1 restored row(s) with a fill since its last read against the venue"
    ]

    last = _fill("O-reducer", 0.0006, venue_order_id=VenueOrderId(_TXID), trade_id="T-3")
    order.apply(last)
    ex.on_order_event(last)
    venue.reports = [_report(_TXID, OrderStatus.FILLED, filled_qty="0.001")]
    ex.on_timer(NOW + timedelta(seconds=10))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], row["state"]) == (0.001, "filled")
    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["filled_qty"]) == ("filled", 0.001)
    assert metrics.orders == ["filled"] and len(venue.calls) == 3


@pytest.mark.parametrize(
    "reconciliation, state, outcome, reasons",
    [(False, "canceled", "revoked", ["the kept reducer ended without filling"]), (True, "ambiguous", "pending", [])],
)
def test_a_terminal_on_a_restored_kept_reducer_writes_the_venues_state_and_its_intent(
    tmp_path, reconciliation, state, outcome, reasons
):
    """The own topic's detached path makes the external path's writes for a restored row: the venue's
    cancel closes the row and writes the intent, a minted one reads ambiguous and leaves the intent
    for the pass that settles the row."""
    ex, client, earlier = _kept_reducer(tmp_path, _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED)))
    canceled = _event(OrderCanceled, client_order_id="O-reducer", reconciliation=reconciliation)
    client.cache.order(ClientOrderId("O-reducer")).apply(canceled)

    ex.on_order_event(canceled)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == state and row["events"][-1]["type"] == "OrderCanceled"
    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["reasons"]) == (outcome, reasons)


@pytest.mark.parametrize("minted", [False, True], ids=["venue-ack", "minted-terminal"])
@pytest.mark.parametrize("reduce_only", [True, False], ids=["kept-reducer", "cancelled-opener"])
def test_a_fill_then_a_terminal_on_a_restored_row_before_the_next_tick_is_repaired_by_the_pass(tmp_path, reduce_only, minted):
    """D7's race on the event path: a restored row takes a fill, credited nothing, and a terminal
    closes it before the re-read pass runs -- the venue's cancel ack, or one the library flagged
    `reconciliation`, which the row reads `ambiguous`. The pass reads the row either way, names it
    among the restored rows with a fill, and repairs it to the
    venue's figure; a kept reducer's intent is written then, at the repaired quantity, never at the
    terminal's credit-0 figure, and a cancelled opener's the startup sweep already wrote."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-restored", reduce_only=reduce_only, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_restored_order()]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )
    ex.on_timer(NOW)
    assert [str(cid) for cid in client.canceled] == ([] if reduce_only else ["O-restored"])
    order = client.cache.order(ClientOrderId("O-restored"))

    fill = _fill("O-restored", 0.0004, venue_order_id=VenueOrderId(_TXID), trade_id="T-race")
    order.apply(fill)
    ex.on_order_event(fill)
    canceled = _event(OrderCanceled, client_order_id="O-restored", reconciliation=minted)
    order.apply(canceled)
    ex.on_order_event(canceled)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("ambiguous" if minted else "canceled", 0.0)
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == ("pending" if reduce_only else "revoked")

    venue.reports = [_report(_TXID, OrderStatus.CANCELED, filled_qty="0.0004")]
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW + timedelta(seconds=5))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"], row["events"][-1]["event"]) == ("canceled", 0.0004, "reconciled")
    assert [r.getMessage() for r in records if r.getMessage().startswith("the re-read pass reads")] == [
        "the re-read pass reads 1 restored row(s) with a fill since its last read against the venue"
    ]
    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["filled_qty"]) == ("revoked", 0.0004 if reduce_only else 0.0)
    assert ex._restored_fills == set() and len(venue.calls) == 2


def test_realized_pnl_takes_the_caches_realizations_at_construction_as_a_baseline(tmp_path):
    """A restored closed position carries a previous run's realization; the gauge reads this
    process's own from the baseline read at construction."""
    client = StubClient()
    client.cache.close_position("BTC/EUR", Money(5.0, Currency.from_str("EUR")))
    ex = _executor(tmp_path, client=client, config=_cache_config(tmp_path))
    ex._traded.add(InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]))

    assert ex._realized_eur() == 0.0
    client.cache.close_position("BTC/EUR", Money(-1.5, Currency.from_str("EUR")))
    assert ex._realized_eur() == pytest.approx(-1.5)


_MARGIN_OPEN = _intent(leverage=2)
_SPOT_CLOSE = _intent(side="sell", action="close", notional_eur=None, qty=0.001)
_MARGIN_CLOSE = _intent(side="sell", action="close", leverage=2)


@pytest.mark.parametrize(
    "intent, margin, balances, refused",
    [
        (_intent(), {"BTC/EUR": 0.001}, {}, "a spot open on BTC/EUR beside a margin position of 0.001 there"),
        (_MARGIN_OPEN, {}, {"XXBT": 0.01}, "a margin open on BTC/EUR beside 0.01 BTC spot inventory"),
        (_MARGIN_OPEN, {}, {"XXBT": 0.0001}, "a margin open on BTC/EUR beside 0.0001 BTC spot inventory"),
        (_MARGIN_OPEN, {}, {"XXBT": 0.00005}, None),
        (_intent(symbol="DOGE/EUR", leverage=2), {}, {"XDG": 12.5}, "a margin open on DOGE/EUR beside 12.5 DOGE spot inventory"),
        (_intent(), {}, {"XXBT": 0.01}, None),
        (_MARGIN_OPEN, {"BTC/EUR": 0.001}, {}, None),
        (_SPOT_CLOSE, {"BTC/EUR": 0.001}, {"XXBT": 0.001}, None),
        (_MARGIN_CLOSE, {"BTC/EUR": 0.001}, {"XXBT": 0.001}, None),
    ],
    ids=[
        "spot-open-beside-margin",
        "margin-open-beside-spot",
        "margin-open-beside-spot-at-ordermin",
        "margin-open-beside-spot-dust",
        "margin-open-beside-spot-spelled-xdg",
        "spot-beside-spot",
        "margin-beside-margin",
        "spot-close",
        "margin-close",
    ],
)
def test_an_opening_intent_that_would_mix_spot_and_margin_inventory_on_its_pair_is_refused_and_a_close_never_is(
    tmp_path, intent, margin, balances, refused
):
    """The refusal 00118 D11 carries into spec 00120 D12, on what can create the mixed shape alone: a
    spot open where the venue's margin positions hold the pair, a margin open where the base has spot
    inventory at or above the pair's `ordermin` (0.0001 on the stub's BTC/EUR) -- a lot under it is
    dust the engine cannot sell -- the base read under Kraken's spellings of it, DOGE's `XDG` among
    them. The same kind beside itself, and a close of either kind beside both,
    are admitted -- the Cache's own position would read a spot lot as the margin one, so the margin
    figure is the venue's, and a close takes inventory off."""
    positions = _VenuePositions(margin)
    ex = _executor(
        tmp_path,
        client=StubClient(StubCache(balances={"ZEUR": 1000.0, **balances})),
        config=_cache_config(tmp_path),
        venue_positions=positions,
    )
    _drop_plan(tmp_path, _plan_dict(intents=[intent]))

    ex.on_timer(NOW)

    entry = _plan_entry(tmp_path)
    expected = [f"intent 0: {refused} -- the cache's restore does not distinguish them"] if refused else []
    reads = 1 if intent["action"] == "open" else 0  # a plan of closes reads no venue position
    assert (entry["disposition"], entry["reasons"], positions.calls) == ("refused" if refused else "accepted", expected, reads)


def test_the_mixed_inventory_check_reads_no_venue_position_for_a_plan_of_closes_or_without_the_cache(tmp_path):
    positions = _VenuePositions({"BTC/EUR": 0.001})
    ex = _executor(tmp_path, client=StubClient(StubCache(balances={"ZEUR": 1000.0, "XXBT": 0.01})), venue_positions=positions)
    _drop_plan(tmp_path, _plan_dict())
    ex.on_timer(NOW)
    assert (_plan_entry(tmp_path)["disposition"], positions.calls) == ("accepted", 0)

    ex = _executor(
        tmp_path,
        client=StubClient(StubCache(balances={"ZEUR": 1000.0, "XXBT": 0.01})),
        config=_cache_config(tmp_path),
        venue_positions=positions,
    )
    _drop_plan(tmp_path, _plan_dict(plan_id="p-2", intents=[_SPOT_CLOSE]))
    ex.on_timer(NOW + timedelta(seconds=5))
    assert (_plan_entry(tmp_path, index=1)["disposition"], positions.calls) == ("accepted", 0)


@pytest.mark.parametrize("enabled", [True, False])
def test_a_plan_with_an_opening_intent_waits_for_a_tick_with_nothing_in_flight_before_the_mixed_inventory_read(tmp_path, enabled):
    """The startup pass's cancel of an adopted order is PENDING_CANCEL on the tick it goes out, and the
    mixed-inventory check's positions read is a signed read on the same key: with the cache enabled
    the plan waits in its file for a tick with nothing in flight, and is picked up on the next one;
    without the cache no venue read is made and the plan is picked up on the first tick."""

    class _PendingCancel(StubClient):
        def cancel_order(self, client_order_id):
            super().cancel_order(client_order_id)
            self.cache.order(client_order_id).apply(
                _event(OrderPendingCancel, client_order_id=str(client_order_id), strategy_id=StrategyId("EXTERNAL"))
            )

    adopted = "OADOPT-AAAAA-BBBBBB"
    client = _PendingCancel(
        StubCache(open_orders=[_resting_limit_order(adopted, venue_order_id=adopted, strategy_id=StrategyId("EXTERNAL"))])
    )
    positions = _VenuePositions()
    ex = _executor(tmp_path, client=client, config=_cache_config(tmp_path, enabled), venue_positions=positions)
    _drop_plan(tmp_path, _plan_dict())

    with _executor_errors(level=logging.INFO) as records:
        ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [adopted] and client.cache.order(ClientOrderId(adopted)).is_inflight
    held = "probe plan p-1 waits for a tick with nothing in flight -- its opening intents take a venue read"
    if enabled:
        assert _plan_path(tmp_path).exists() and positions.calls == 0
        assert held in [r.getMessage() for r in records]
        client.cache.order(ClientOrderId(adopted)).apply(
            _event(OrderCanceled, client_order_id=adopted, strategy_id=StrategyId("EXTERNAL"))
        )
        ex.on_timer(NOW + timedelta(seconds=5))
    else:
        assert held not in [r.getMessage() for r in records]
    assert not _plan_path(tmp_path).exists()
    assert (_plan_entry(tmp_path)["disposition"], positions.calls) == ("accepted", 1 if enabled else 0)


def test_a_margin_position_read_that_fails_refuses_the_opening_intents_by_name(tmp_path):
    positions = _VenuePositions(raises=RuntimeError("timed out"))
    ex = _executor(tmp_path, client=StubClient(StubCache()), config=_cache_config(tmp_path), venue_positions=positions)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(), _SPOT_CLOSE]))

    ex.on_timer(NOW)

    entry = _plan_entry(tmp_path)
    assert (entry["disposition"], entry["reasons"]) == (
        "refused",
        ["intent 0: the venue's margin positions could not be read for the mixed-inventory check -- RuntimeError: timed out"],
    )


# --- the withdrawal check's second source: the venue's trade history (spec 00120 D19) ---------------


def _cold_start_row(tmp_path, *, finished=False):
    """A cold start's shape: the ledger recorded 0.4 filled on an order the Cache holds under the venue's
    txid at ACCEPTED with no fill applied -- the library created it from the venue's report and applied
    none of the trade history's fills to it. `finished` closes the row on that quantity instead."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-cold", reduce_only=False, when=earlier, venue_order_id=_TXID, qty=1.0)
    update_submitted_row(
        tmp_path / "journal", _boundary(earlier), "O-cold", add_filled_qty=0.4, state="filled" if finished else None
    )
    return earlier


@pytest.mark.parametrize("finished", [False, True])
def test_a_cold_starts_order_figure_short_of_the_ledger_is_no_withdrawal_when_the_trade_history_covers_it(tmp_path, finished):
    earlier = _cold_start_row(tmp_path, finished=finished)
    order = _resting_limit_order(_TXID, venue_order_id=_TXID, strategy_id=StrategyId("EXTERNAL"))
    cache = (
        StubCache(closed_orders=[_closed_order("O-cold", OrderStatus.FILLED, filled_qty=0.0, venue_order_id=_TXID)])
        if finished
        else StubCache(open_orders=[order])
    )
    client = StubClient(cache)
    fills = _VenueFills(_fill_report(_TXID, "0.4"))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_fills=fills)

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    assert not _kill_file(tmp_path).exists()
    assert fills.calls == [_boundary(earlier) - timedelta(hours=1)]
    row = _record(tmp_path, earlier)["submitted"][0]
    assert (
        row["filled_qty"] == 0.4 and [e.get("event") for e in row["events"] if e.get("event") in ("withdrawn", "reconciled")] == []
    )
    kind = "finished order" if finished else "adopted order"
    assert f"{kind} O-cold (Kraken {_TXID}) reads 0 filled on its order figure against the 0.4" in " ".join(
        r.getMessage() for r in records
    )
    if not finished:
        assert [str(cid) for cid in client.canceled] == [_TXID]  # cancelled as an order the ledger carries as no reducer
        assert "O-cold" in ex._rows_the_pass_repaired  # a fill the library infers at the ack credits nothing beyond the Cache


@pytest.mark.parametrize(
    "history",
    [(), (("0.2", _TXID), ("0.4", f"{_TXID}-other"))],
    ids=["no-fill", "short-on-the-txid-and-covered-on-another"],
)
@pytest.mark.parametrize("finished", [False, True])
def test_a_true_withdrawal_with_no_fill_in_the_trade_history_trips_the_kill_switch_as_today(
    tmp_path, finished, history, kill_trip_expected
):
    """The cover is the row's own txid's sum: a history short on that txid trips however much another
    order's fills would make up, and presence alone is no cover."""
    earlier = _cold_start_row(tmp_path, finished=finished)
    order = _resting_limit_order(_TXID, venue_order_id=_TXID, strategy_id=StrategyId("EXTERNAL"))
    cache = (
        StubCache(closed_orders=[_closed_order("O-cold", OrderStatus.FILLED, filled_qty=0.0, venue_order_id=_TXID)])
        if finished
        else StubCache(open_orders=[order])
    )
    fills = _VenueFills(*(_fill_report(txid, qty, trade_id=f"T-h{i}") for i, (qty, txid) in enumerate(history)))
    ex = _executor(tmp_path, client=StubClient(cache), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_fills=fills)

    ex.on_timer(NOW)

    assert fills.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert f"O-cold (Kraken {_TXID}) shows 0 filled at the venue, less than the 0.4" in _kill_file(tmp_path).read_text()
    last = _record(tmp_path, earlier)["submitted"][0]["events"][-1]
    assert (last.get("event"), last.get("type")) == (("withdrawn", None) if finished else (None, "OrderAccepted"))


def test_a_trade_history_read_that_fails_leaves_the_withdrawal_check_on_the_order_figure(tmp_path, kill_trip_expected):
    earlier = _cold_start_row(tmp_path)
    order = _resting_limit_order(_TXID, venue_order_id=_TXID, strategy_id=StrategyId("EXTERNAL"))
    fills = _VenueFills(raises=RuntimeError("timed out"))
    ex = _executor(
        tmp_path, client=StubClient(StubCache(open_orders=[order])), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_fills=fills
    )

    with _executor_errors(level=logging.CRITICAL) as records:
        ex.on_timer(NOW)

    assert len(fills.calls) == 1 and f"O-cold (Kraken {_TXID}) shows 0 filled at the venue" in _kill_file(tmp_path).read_text()
    assert "the venue's trade history could not be read for the withdrawal check -- the order's figure decides" in [
        r.getMessage() for r in records
    ]
    _ = earlier


def test_the_trade_history_is_read_once_per_pass_from_the_earliest_rows_boundary_and_a_failed_read_is_not_retried(
    tmp_path, kill_trip_expected
):
    """D19's once per pass: two finished rows short of the ledger, under two boundaries, and a reader
    that raises -- one call, from one hour before the earlier boundary, both rows tripping on their
    order figure."""
    rows = {"O-cold-1": (NOW - timedelta(hours=4), f"{_TXID}-1"), "O-cold-2": (NOW - timedelta(hours=8), f"{_TXID}-2")}
    for cid, (when, txid) in rows.items():
        _submitted_row(tmp_path, cid, reduce_only=False, when=when, venue_order_id=txid, qty=1.0)
        update_submitted_row(tmp_path / "journal", _boundary(when), cid, add_filled_qty=0.4, state="filled")
    cache = StubCache(
        closed_orders=[
            _closed_order(cid, OrderStatus.FILLED, filled_qty=0.0, venue_order_id=txid) for cid, (_, txid) in rows.items()
        ]
    )
    fills = _VenueFills(raises=RuntimeError("timed out"))
    ex = _executor(tmp_path, client=StubClient(cache), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_fills=fills)

    ex.on_timer(NOW)

    assert fills.calls == [_boundary(NOW - timedelta(hours=8)) - timedelta(hours=1)]
    assert _kill_file(tmp_path).exists()
```

Replace, in `tests/cache_restart_child.py`, this block:

```python
The node is the engine's own `build_shadow_node`, with the cache backing attached through the config
and every venue default redirected to the loopback the driver runs: the two client configs' URLs, the
gate's venue reader, and the three bare-client reads' `base_url`. Before anything is built the child
asserts that no production default remains, the autouse `_no_production_venue_read` fixture's rule
for a node that runs. The strategy the engine registers is subclassed to hand the executor its
```

with:

```python
The node is the engine's own `build_shadow_node`, with the cache backing attached through the config
and every venue default redirected to the loopback the driver runs: the two client configs' URLs, the
gate's venue reader, and the five bare-client reads' `base_url`. Before anything is built the child
asserts that no production default remains, the autouse `_no_production_venue_read` fixture's rule
for a node that runs. The strategy the engine registers is subclassed to hand the executor its
```

Replace, in `tests/cache_restart_child.py`, this block:

```python
executor_module.cancel_venue_order = partial(executor_module.cancel_venue_order, base_url=CONFIG["base_url"])
executor_module.read_venue_holdings = partial(executor_module.read_venue_holdings, base_url=CONFIG["base_url"])


```

with:

```python
executor_module.cancel_venue_order = partial(executor_module.cancel_venue_order, base_url=CONFIG["base_url"])
executor_module.read_venue_holdings = partial(executor_module.read_venue_holdings, base_url=CONFIG["base_url"])
executor_module.read_venue_fills = partial(executor_module.read_venue_fills, base_url=CONFIG["base_url"])
executor_module.read_venue_positions = partial(executor_module.read_venue_positions, base_url=CONFIG["base_url"])


```

Replace, in `tests/cache_restart_child.py`, this block:

```python
    bare = all(
        isinstance(fn, partial) and str(fn.keywords.get("base_url", "")).startswith(LOOPBACK_HTTP)
        for fn in (executor_module.read_venue_orders, executor_module.cancel_venue_order, executor_module.read_venue_holdings)
    )
    if not (
```

with:

```python
    bare = all(
        isinstance(fn, partial) and str(fn.keywords.get("base_url", "")).startswith(LOOPBACK_HTTP)
        for fn in (
            executor_module.read_venue_orders,
            executor_module.cancel_venue_order,
            executor_module.read_venue_holdings,
            executor_module.read_venue_fills,
            executor_module.read_venue_positions,
        )
    )
    if not (
```

Replace, in `tests/test_cache_restart.py`, this block:

```python
# library's ten-second residual wait at stop.
PHASE1_WINDOW = 14
PHASE2_WINDOW = 16
CHILD_TIMEOUT = 150

```

with:

```python
# library's ten-second residual wait at stop.
PHASE1_WINDOW = 14
PHASE2_WINDOW = 20
CHILD_TIMEOUT = 150

```

Replace, in `tests/test_cache_restart.py`, this block:

```python
    ]
    assert record["external"] == [], record["external"]  # every later event reaches the own topic


```

with:

```python
    ]
    assert record["external"] == [], record["external"]  # every later event reaches the own topic
    # The executor: the restored set, the pass's cancel of the restored opener named with its fill
    # state, the row settled from the venue's report by the re-read pass, and the intent the sweep wrote.
    assert record["restored"] == [wire["client_order_id"]]
    assert (
        f"canceling restored order {wire['client_order_id']}, partial -- the ledger does not carry it as a resting reducer"
        in record["log"]
    )
    [row] = node.rows()
    [intent] = node.intents()
    assert (row["state"], row["filled_qty"], intent["outcome"]) == ("canceled", 0.4, "revoked")


```

Replace, in `tests/test_cache_restart.py`, this block:

```python
        f"order {wire['client_order_id']} partial, 0.70000000 of 1.00000000 filled @ 150.00",
    ]


```

with:

```python
        f"order {wire['client_order_id']} partial, 0.70000000 of 1.00000000 filled @ 150.00",
    ]
    # The executor: the venue's report repairs the row to the venue's figure before the pass's cancel.
    label = f"{wire['client_order_id']} (Kraken {wire['txid']})"
    assert f"adopted order {label} reconciled against the venue: 0.7 filled there against the 0.4 recorded here" in record["log"]
    [row] = node.rows()
    assert (row["filled_qty"], row["state"]) == (0.7, "canceled")
    assert [e["qty"] for e in row["events"] if e.get("event") == "reconciled"] == [pytest.approx(0.3)]


```

Replace, in `tests/test_cache_restart.py`, this block:

```python
    assert (order["is_open"], order["filled_qty"]) == (True, "0.40000000")
    assert _restore_lines(record["log"])[0] == "1 order(s), 1 position(s) restored"


```

with:

```python
    assert (order["is_open"], order["filled_qty"]) == (True, "0.40000000")
    assert _restore_lines(record["log"])[0] == "1 order(s), 1 position(s) restored"
    # The executor: the row written from the venue's report, the stale copy left, no cancel sent.
    assert "ClosedOrders" in private_calls and "CancelOrder" not in private_calls, private_calls
    assert (
        f"restored order {wire['client_order_id']} is canceled at the venue -- its stale open copy stays in the Cache and no cancel is sent"
        in record["log"]
    )
    [row] = node.rows()
    [intent] = node.intents()
    assert (row["state"], row["filled_qty"], intent["outcome"]) == ("canceled", 0.4, "revoked")


```

Replace, in `tests/test_cache_restart.py`, this block:

```python
    [order] = record["at_end"]["orders"]
    assert order["filled_qty"] == "0.80000000"  # the venue's cumulative figure is 0.6


def test_an_empty_cache_beside_open_ledger_rows_is_a_cold_start_the_pass_reconciles_as_today(tmp_path):
    """The owner's ruling: an empty namespace is a cold start, never a refusal. The order is a spot
    one resting unfilled, so the venue has no margin position for the start to fail on and no fill
    for the pass to weigh against the ledger; the restarted node reads zero, reconciliation names
    the order by its txid under EXTERNAL, and the pass cancels it as an order the ledger carries as
    no reducer, today's shape."""
    valkey = _Valkey(tmp_path / "valkey")
    valkey.start()
```

with:

```python
    [order] = record["at_end"]["orders"]
    assert order["filled_qty"] == "0.80000000"  # the venue's cumulative figure is 0.6
    # The executor: both fills credit the row nothing, the re-read pass repairs it to the venue's 0.6,
    # and the kept reducer's intent stays pending on its open row.
    assert record["restored"] == [wire["client_order_id"]]
    [row] = node.rows()
    fills = [e for e in row["events"] if e.get("event") == "fill"]
    assert [(e["qty"], e.get("credited")) for e in fills] == [(0.4, None), (0.2, 0.0), (0.2, 0.0)]
    assert "the re-read pass reads 1 restored row(s) with a fill since its last read against the venue" in record["log"]
    assert (row["filled_qty"], row["state"]) == (pytest.approx(0.6), "accepted")
    [intent] = node.intents()
    assert intent["outcome"] == "pending"
    # The realized baseline over a real restored position: each fill's publish reads this process's own
    # realizations, the previous run's left in the baseline.
    assert record["metrics"]["realized"] and set(record["metrics"]["realized"]) == {0.0}, record["metrics"]["realized"]


def test_a_trade_frame_on_a_restored_opener_racing_the_passs_cancel_is_booked_twice_and_the_row_settles_at_the_venues_figure(
    phase_one,
):
    """The D7 race: the restored opener the startup pass cancels takes a `trade` frame (last 0.2,
    cumulative 0.6) between the pass's cancel and the venue's ack. The library books it twice, 0.8 on
    a copy the ack then closes, and flags the ack `reconciliation` -- its fill-decrease handling, so
    the row reads `ambiguous` until the re-read pass reads the venue's closed report; both fills
    credit the row nothing, the pass repairs it to the venue's 0.6 and closes it `canceled`, and the
    intent the sweep wrote at the cancel stays `revoked`."""
    valkey, node, wire, _ = phase_one
    with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.open_orders[wire["txid"]] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"),
            oflags="fciq",
            vol_exec="0.40000000",
            price="150.00000",
            cost="60.00000",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001)
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.40000000"), ordertxid=wire["txid"], cost="60.00000"
        )
        _script_cancel_ack(venue, exec_, wire)
        ack = venue.on_cancel_order

        def trade_then_ack(form: dict) -> None:
            # Inside the venue's CancelOrder: the frame and the listings it moves land before the answer.
            exec_.send_execution(
                lb.exec_trade(
                    wire["txid"], wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE, last_qty=0.2, cum_qty=0.6,
                    exec_id="TLOOP3-AAAAA-AAAAAA", trade_id=1003,
                )
            )  # fmt: skip
            venue.open_orders[wire["txid"]].update(vol_exec="0.60000000", cost="90.00000")
            venue.trades["TLOOP3-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.20000000", price="150.00", trade_id=1003)
            venue.positions["TPOSLP-AAAAA-BBBBBB"].update(vol="0.60000000", cost="90.00000")
            ack(form)

        venue.on_cancel_order = trade_then_ack
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
        cancels = list(venue.cancel_forms)

    assert record["errors"] == [], record["errors"]
    assert [form.get("txid") for form in cancels] == [wire["txid"]]
    assert "Generated inferred fill" in record["log"]
    assert [(e["type"], e["reconciliation"]) for e in record["own"]] == [
        ("OrderPendingCancel", False),
        ("OrderFilled", True),
        ("OrderFilled", True),
        ("OrderCanceled", True),
    ], record["own"]
    [order] = record["at_end"]["orders"]
    assert (order["status"], order["filled_qty"]) == ("CANCELED", "0.80000000")  # the venue's cumulative figure is 0.6
    [row] = node.rows()
    fills = [e for e in row["events"] if e.get("event") == "fill"]
    assert [(e["qty"], e.get("credited")) for e in fills] == [(0.4, None), (0.2, 0.0), (0.2, 0.0)], fills
    assert "its row reads ambiguous until the re-read pass settles it" in record["log"]
    assert "the re-read pass reads 1 restored row(s) with a fill since its last read against the venue" in record["log"]
    assert (
        f"a fill on restored order {row['client_order_id']} credits nothing until the venue is read -- the next restart is taken flat"
        in record["log"]
    )
    assert (row["state"], row["filled_qty"]) == ("canceled", pytest.approx(0.6))
    assert [e["qty"] for e in row["events"] if e.get("event") == "reconciled"] == [pytest.approx(0.2)]
    [intent] = node.intents()
    assert intent["outcome"] == "revoked"


def test_an_empty_cache_beside_open_ledger_rows_is_a_cold_start_the_pass_reconciles_as_today(tmp_path):
    """The owner's ruling: an empty namespace is a cold start, never a refusal. The order is a spot
    one, so the venue has no margin position for the start to fail on, and it filled 0.4 before the
    stop: the library creates the EXTERNAL copy from the venue's report at ACCEPTED with no fill
    applied, and the venue's own report, 0.4, answers for the copy as for every order the Cache holds
    at construction -- no trip. The restarted node reads zero, reconciliation names the order by its
    txid under EXTERNAL, the pass cancels it as an order the ledger carries as no reducer, and the
    fill the library infers at the cancel's ack credits the row nothing, a restored row's credit."""
    valkey = _Valkey(tmp_path / "valkey")
    valkey.start()
```

Replace, in `tests/test_cache_restart.py`, this block:

```python
        with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000")}
            _script_first_fill(venue, exec_, wire=wire, fill=False)
            record = node.run(1, venue, data, exec_, window=PHASE1_WINDOW)
        assert record["errors"] == [], record["errors"]
        [row] = node.rows()
        assert (row["state"], row["filled_qty"], row["order"]["leverage"]) == ("accepted", 0.0, None)
        wire["client_order_id"] = row["client_order_id"]
        assert len(_keys(valkey.port)) > 0
```

with:

```python
        with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000")}
            _script_first_fill(venue, exec_, wire=wire)
            record = node.run(1, venue, data, exec_, window=PHASE1_WINDOW)
        assert record["errors"] == [], record["errors"]
        [row] = node.rows()
        assert (row["state"], row["filled_qty"], row["order"]["leverage"]) == ("accepted", 0.4, None)
        wire["client_order_id"] = row["client_order_id"]
        assert len(_keys(valkey.port)) > 0
```

Replace, in `tests/test_cache_restart.py`, this block:

```python
        assert _keys(valkey.port) == []
        with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000")}
            venue.open_orders[wire["txid"]] = dict(lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"), oflags="fciq")
            _script_cancel_ack(venue, exec_, wire)
            record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
```

with:

```python
        assert _keys(valkey.port) == []
        with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000"), "SOL": lb.balance("0.40000000")}
            venue.open_orders[wire["txid"]] = dict(
                lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"),
                oflags="fciq",
                vol_exec="0.40000000",
                price="150.00000",
                cost="60.00000",
            )
            venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001)
            _script_cancel_ack(venue, exec_, wire)
            record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
```

Replace, in `tests/test_cache_restart.py`, this block:

```python
    assert record["errors"] == [], record["errors"]
    assert _restore_lines(record["log"]) == ["0 order(s), 0 position(s) restored"]
    assert f"Created external order {wire['txid']}" in record["log"]
    [external] = record["at_start"]["orders"]
```

with:

```python
    assert record["errors"] == [], record["errors"]
    assert _restore_lines(record["log"]) == ["0 order(s), 0 position(s) restored"]
    assert record["restored"] == [wire["txid"]]  # the EXTERNAL copy reconciliation created, in the set under its txid
    assert f"Created external order {wire['txid']}" in record["log"]
    [external] = record["at_start"]["orders"]
```

Replace, in `tests/test_cache_restart.py`, this block:

```python
    )
    assert "execution kill switch tripped" not in record["log"]
    assert f"canceling adopted resting order {wire['txid']} -- the ledger does not carry it as a resting reducer" in record["log"]
    assert [form.get("txid") for form in cancels] == [wire["txid"]]
    assert [e["client_order_id"] for e in record["external"]][:1] == [wire["txid"]]


```

with:

```python
    )
    assert "execution kill switch tripped" not in record["log"]
    # The EXTERNAL copy reads 0 filled; the venue's report, 0.4, answers for it as for every order the
    # Cache holds at construction, so the withdrawal check reads no shortfall and the trade history is
    # not consulted -- the check's second source is the copy's, without the cache or under a failed
    # order read, and the executor file's cold-start cases pin it there.
    assert "reads 0 filled on its order figure" not in record["log"]
    assert f"canceling adopted resting order {wire['txid']} -- the ledger does not carry it as a resting reducer" in record["log"]
    assert [form.get("txid") for form in cancels] == [wire["txid"]]
    assert [e["client_order_id"] for e in record["external"]][:1] == [wire["txid"]]
    # The fill the library infers at the cancel's ack, 0.4 again, credits the row nothing, a restored
    # row's credit; the row settles at the venue's 0.4, canceled by the pass.
    [row] = node.rows()
    fills = [e for e in row["events"] if e.get("event") == "fill"]
    assert [(e["qty"], e.get("credited")) for e in fills] == [(0.4, None), (0.4, 0.0)], fills
    assert (row["filled_qty"], row["state"]) == (0.4, "canceled")
    [intent] = node.intents()
    assert intent["outcome"] == "revoked"


```

Replace, in `tests/test_engine_stub_fidelity.py`, this block:

```python
            OURS, "cli.engine.executor.read_venue_holdings, the venue_holdings ProbeExecutor is built with", ()
        ),
    },
    "test_engine_command.py": {
```

with:

```python
            OURS, "cli.engine.executor.read_venue_holdings, the venue_holdings ProbeExecutor is built with", ()
        ),
        # Answers REAL `FillReport`s; what it restates is this repo's reader, not the library.
        "_VenueFills": Standin(OURS, "cli.engine.executor.read_venue_fills, the venue_fills ProbeExecutor is built with", ()),
        "_VenuePositions": Standin(
            OURS, "cli.engine.executor.read_venue_positions, the venue_positions ProbeExecutor is built with", ()
        ),
    },
    "test_engine_command.py": {
```

- [ ] **Step 3: Run the executor file and watch the new cases fail**

Run: `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider`
Expected: `331 failed, 50 passed, 35 errors` -- `_executor` now hands the constructor `venue_fills` and `venue_positions`, two keywords it does not take yet, so every case that builds an executor fails at construction with `TypeError` and the fifty that build none pass; the thirty-five errors are `kill_trip_expected`'s teardown on cases that tripped nothing. The count is the whole file's, not the new cases' alone, and it reads green only once the source fence lands. The harness is not run red: its executor assertions fail only after six minutes of scenarios, and the executor file's cases are the same rules read faster.

- [ ] **Step 4: The executor and the two docstrings in `cli/engine/node.py`**

Replace, in `cli/engine/executor.py`, this block:

```python


def cancel_venue_order(venue_order_id: str, instrument_id: str, *, base_url: str | None = None) -> None:
    """Cancel one order at the venue by its txid, on a client of its own (`_bare_client`) and on
```

with:

```python


def read_venue_fills(since: datetime, *, base_url: str | None = None) -> list:
    """The venue's own fills since `since`, as the adapter's `FillReport`s from Kraken's trade history, on
    a client of its own (`_bare_client`) and on `read_venue_orders`' terms: the withdrawal check's second
    source (spec 00120 D19). An order's figure can fall short of the ledger without a fill having been
    withdrawn -- on a cold start the library creates the order from the venue's report and applies none of
    the history's fills to it, so its copy reads 0 filled where the venue's trade history reads the fills
    the ledger recorded -- and the trade history is the venue's own record of what filled. Read once per
    pass, for the rows whose figure fell short, and never retried in it. Anything short of a complete
    answer inside `_VENUE_READ_TIMEOUT_SECONDS` raises."""
    from cli.engine.node import _ACCOUNT_ID

    client = _bare_client(base_url)

    async def _read():
        for instrument in await client.request_instruments() or ():
            client.cache_instrument(instrument)
        return await client.request_fill_reports(AccountId(_ACCOUNT_ID), start=since)

    return list(asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS)) or ())


def cancel_venue_order(venue_order_id: str, instrument_id: str, *, base_url: str | None = None) -> None:
    """Cancel one order at the venue by its txid, on a client of its own (`_bare_client`) and on
```

Replace, in `cli/engine/executor.py`, this block:

```python
    positions, state = asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS))
    held = dict.fromkeys(INSTRUMENT_IDS, 0.0)
    for report in positions:
        symbol = _SYMBOL_BY_INSTRUMENT_ID.get(str(report.instrument_id))
        if symbol is None:
            continue
        qty = float(report.quantity)
        held[symbol] += {"LONG": qty, "SHORT": -qty, "FLAT": 0.0}[str(report.position_side).rsplit(".", 1)[-1]]
    bases = frozenset(_SPOT_SYMBOL_BY_BASE)
```

with:

```python
    positions, state = asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS))
    held = _margin_positions(positions)
    bases = frozenset(_SPOT_SYMBOL_BY_BASE)
```

Replace, in `cli/engine/executor.py`, this block:

```python
def _newest_venue_balances(journal_dir: Path) -> dict:
```

with:

```python
def _margin_positions(reports) -> dict[str, float]:
    """Each margin position report's quantity, signed by its side, summed under its basket symbol; a
    pair outside the basket is not read, and a side that is not LONG, SHORT or FLAT raises."""
    held = dict.fromkeys(INSTRUMENT_IDS, 0.0)
    for report in reports:
        symbol = _SYMBOL_BY_INSTRUMENT_ID.get(str(report.instrument_id))
        if symbol is None:
            continue
        qty = float(report.quantity)
        held[symbol] += {"LONG": qty, "SHORT": -qty, "FLAT": 0.0}[str(report.position_side).rsplit(".", 1)[-1]]
    return held


def read_venue_positions(*, base_url: str | None = None) -> dict[str, float]:
    """The venue's margin positions under every `INSTRUMENT_IDS` symbol, signed by side, on a client of
    its own (`_bare_client`) and on `read_venue_holdings`' terms -- the position half of that read, the
    listing cached first since the position read resolves its rows through it, an empty listing and a
    positions answer of `None` refused the same way. The mixed-inventory refusal's source (spec 00120
    D12): a margin lot is what the venue's OpenPositions lists, and no Cache read tells one from a spot
    lot, which the Cache books as a position too."""
    from cli.engine.flatten import QUOTE_CURRENCY
    from cli.engine.node import _ACCOUNT_ID

    client = _bare_client(base_url)

    async def _read():
        instruments = await client.request_instruments()
        if not instruments:
            raise EngineError("the venue's instrument listing came back empty -- no margin position resolves through it")
        for instrument in instruments:
            client.cache_instrument(instrument)
        positions = await client.request_position_status_reports(
            AccountId(_ACCOUNT_ID), account_type=AccountType.MARGIN, use_spot_position_reports=False, quote_currency=QUOTE_CURRENCY
        )
        if positions is None:
            raise EngineError("the venue answered nothing for the margin positions -- it is never read as a flat margin book")
        return list(positions)

    return _margin_positions(asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS)))


def _newest_venue_balances(journal_dir: Path) -> dict:
```

Replace, in `cli/engine/executor.py`, this block:

```python
        venue_cancel=None,
        venue_holdings=None,
    ) -> None:
        self._client = client
```

with:

```python
        venue_cancel=None,
        venue_holdings=None,
        venue_fills=None,
        venue_positions=None,
    ) -> None:
        self._client = client
```

Replace, in `cli/engine/executor.py`, this block:

```python
        self._venue_cancel = venue_cancel
        self._venue_holdings = venue_holdings
        # The venue's figure less the Cache's, per symbol, at the last settle of the position gauge
        # (`_settle_positions_from_venue`): `_publish_fill` adds it to the Cache's net, so a fill
```

with:

```python
        self._venue_cancel = venue_cancel
        self._venue_holdings = venue_holdings
        self._venue_fills = venue_fills
        self._venue_positions = venue_positions
        # The venue's fills by txid, read once per pass for the rows whose order figure fell short of
        # the ledger (`_trades_cover`): None until a row asks; a read that failed sets the flag and is
        # not retried in the pass; the floor is the earliest boundary among the pass's rows, set by
        # the pass before any row asks, so one read covers every row of it.
        self._venue_fills_read: dict[str, float] | None = None
        self._venue_fills_failed = False
        self._venue_fills_floor: datetime | None = None
        # The venue's figure less the Cache's, per symbol, at the last settle of the position gauge
        # (`_settle_positions_from_venue`): `_publish_fill` adds it to the Cache's net, so a fill
```

Replace, in `cli/engine/executor.py`, this block:

```python
        # re-halting a plan that is already gone.
        self._kill_tripped = False

    # --- the gate ------------------------------------------------------------------------------
```

with:

```python
        # re-halting a plan that is already gone.
        self._kill_tripped = False
        # The orders the Cache holds for the venue at construction, open or closed, by client order id
        # with the txid each carries (spec 00120 D6): this engine's own, restored from a previous
        # process, and the EXTERNAL copies -- restored, or created by this boot's reconciliation, which
        # nothing tells apart. Read here, inside `on_start` after the load and the reconciliation and
        # before the first tick, each attached to the row the ledger's window carries for it, and held
        # for the process's life, since the Cache's copy of each is a view the venue is asked over.
        # Empty without the cache, where what reconciliation adopted answers as before.
        self._restored: dict[str, str | None] = {}
        # The restored rows a fill reached since the re-read pass last read them: the credit is
        # nothing (`_fill_credit`) and the pass repairs the row from the venue's cumulative figure.
        self._restored_fills: set[str] = set()
        # The realized PnL the Cache held per instrument at construction, what a restored position
        # carried in from a previous run, subtracted from the gauge so it reads this process's own.
        self._realized_baseline: dict[InstrumentId, float] = {}
        cache_settings = config.cache
        self._cache_enabled = cache_settings.enabled
        if self._cache_enabled:
            self._read_restored()
        self._read_realized_baseline()

    def _read_restored(self) -> None:
        """The restored set: every order the Cache holds for the venue at construction, open or closed,
        this engine's own and the EXTERNAL copies alike -- a closed copy is the double booking's shape
        too, an order the Cache reads FILLED where the venue says partial (spec 00120 D7), and the store
        restores the EXTERNAL copy a previous process adopted with that process's fills, the same state
        as a restored own order and one nothing tells from a copy this boot's reconciliation created;
        the venue answers for every one of them (`_venue_answers`). Each whose row the ledger's window
        carries is attached here, under its own id and its txid, so a fill on it before the first tick
        lands in its row and never in the unknown-order trip (D6); the startup pass attaches what it
        classifies again. A read that fails leaves the set empty at CRITICAL, and the startup pass then
        reads each such order's Cache copy as it reads an adopted one; a ledger that cannot be read
        leaves the set unattached until the pass, which reads it again."""
        try:
            orders = list(self._cache.orders(venue=_VENUE))
        except Exception:
            logger.critical(
                "the restored orders could not be read at start -- the startup pass reads the Cache's copy of each", exc_info=True
            )
            return
        self._restored = {str(order.client_order_id): _venue_order_id_of(order) for order in orders}
        if not self._restored:
            return
        try:
            rows = open_submitted_rows(self._journal_dir, self._now())
        except Exception:
            logger.critical(
                "the exec ledger could not be read at start -- the restored orders are attached at the startup pass", exc_info=True
            )
            return
        by_own = {row["client_order_id"]: (boundary, row) for boundary, row in rows}
        by_venue = {}
        for boundary, row in rows:
            venue_order_id = _row_venue_order_id(row)
            if venue_order_id is not None:
                by_venue[venue_order_id] = (boundary, row)
        for client_order_id, venue_order_id in self._restored.items():
            entry = by_own.get(client_order_id)
            if entry is None and venue_order_id is not None:
                entry = by_venue.get(venue_order_id)
            if entry is not None:
                self._attach(entry, client_order_id, venue_order_id=venue_order_id)

    def _read_realized_baseline(self) -> None:
        """`_realized_eur`'s baseline (spec 00120 D10): per basket instrument, the realized PnL the Cache
        holds at construction -- after reconciliation's fills, the library's order, and before any fill
        of this process, the tick's. Telemetry: a read that fails leaves the baseline at zero and logs."""
        try:
            for instrument_id in (InstrumentId.from_str(value) for value in INSTRUMENT_IDS.values()):
                held = self._realized_on(instrument_id)
                if held:
                    self._realized_baseline[instrument_id] = held
        except Exception:
            logger.exception("the realized baseline could not be read at start -- the gauge counts every restored realization")

    # --- the gate ------------------------------------------------------------------------------
```

Replace, in `cli/engine/executor.py`, this block:

```python
    def _arm_reread_after_mint(self) -> None:
        """The re-read pass's second trigger: a terminal this engine minted, on the plan's own order, on
        one no intent holds any more (`_on_detached_event`) or on one the startup pass adopted, with no
        socket held down -- the adopted path's shape on this wheel, where each adopt-pass cancel's ack
        goes unapplied and the mint lands about 31 s on with the sockets up (drills G and A1). A mint
```

with:

```python
    def _arm_reread_after_mint(self) -> None:
        """The re-read pass's second trigger: a terminal this engine minted, on the plan's own order, on
        one no intent holds any more (`_on_detached_event`) or on one the startup pass adopted, or a fill
        on a restored row, whose credit is nothing until the pass reads the venue (`_fill_credit`), with no
        socket held down -- the adopted path's shape on this wheel, where each adopt-pass cancel's ack
        goes unapplied and the mint lands about 31 s on with the sockets up (drills G and A1). A mint
```

Replace, in `cli/engine/executor.py`, this block:

```python

        The classification population below is `orders_open`, but the row sweep is NOT: an order that
        filled, was canceled or expired while this process was down is not in the Cache at all -- the
        startup reconciliation reads open orders only -- so the pass cannot return early when nothing
        is resting: an idle startup can still owe row repairs.

        LAST, the window's `pending` intents are settled (`_settle_pending_intents`): no process runs
```

with:

```python

        The classification population below is `orders_open`, but the row sweep is NOT: an order that
        filled, was canceled or expired while this process was down is not in the Cache at all when the
        cache is off -- the startup reconciliation reads open orders only -- so the pass cannot return
        early when nothing is resting: an idle startup can still owe row repairs.

        With the cache enabled the Cache may already hold this engine's OWN orders and positions from a
        previous process (spec 00120 D6, D7): every order it holds at construction, this strategy's own
        and the EXTERNAL copies, restored or created by this boot's reconciliation, is in `_restored`,
        read and attached at construction, and the venue is the authority over each -- the
        sweep asks the venue for every order of the restored set, whatever its Cache copy's status,
        and takes the report over the copy, which is the previous process's view. A restored order the venue reports closed has its
        row written from the report and is left where it is, its stale open copy in the Cache for the
        process's life, since a cancel through the handle would answer nothing this engine applies; a
        restored order the venue reports open is classified as an adopted one is -- cancelled unless
        its row is a ledgered reducer -- and its events reach the own topic under its own id, where
        `_on_detached_event` carries them.

        LAST, the window's `pending` intents are settled (`_settle_pending_intents`): no process runs
```

Replace, in `cli/engine/executor.py`, this block:

```python
        rows_by_venue = {}
        for entry in rows.values():
            venue_order_id = _row_venue_order_id(entry[1])
            if venue_order_id is not None:
                rows_by_venue[venue_order_id] = entry
        cancelled: set[str] = set()
        for order in resting:
            client_order_id = str(getattr(order, "client_order_id", ""))
            venue_order_id = _venue_order_id_of(order)
            attached = rows.get(client_order_id)
            if attached is None and venue_order_id is not None:
                attached = rows_by_venue.get(venue_order_id)
            if attached is not None:
                self._attach(attached, client_order_id, venue_order_id=venue_order_id)
            payload = attached[1].get("order") if attached is not None else None
            if isinstance(payload, dict) and payload.get("reduce_only") is True and not cancel_all:
                logger.warning("adopted resting order %s is a ledgered reducer -- left resting and re-attached", client_order_id)
                continue
            logger.warning(
                "canceling adopted resting order %s -- %s",
                client_order_id,
                f"the gate reads none ({', '.join(verdict.reasons) or '-'})"
                if cancel_all
                else "the ledger does not carry it as a resting reducer",
            )
            try:
                self._client.cancel_order(order.client_order_id)
```

with:

```python
        rows_by_venue = {}
        for entry in rows.values():
            venue_order_id = _row_venue_order_id(entry[1])
            if venue_order_id is not None:
                rows_by_venue[venue_order_id] = entry
        # The window's closed rows by txid: a restored own order whose row a previous startup wrote
        # terminal from the venue's report is still listed open by the Cache at every later restart
        # (spec 00120 D7), unattached here since the rows above are the open ones.
        finished_by_venue = {}
        for _, row in finished.values():
            venue_order_id = _row_venue_order_id(row)
            if venue_order_id is not None:
                finished_by_venue[venue_order_id] = row
        cancelled: set[str] = set()
        for order in resting:
            client_order_id = str(getattr(order, "client_order_id", ""))
            venue_order_id = _venue_order_id_of(order)
            attached = rows.get(client_order_id)
            if attached is None and venue_order_id is not None:
                attached = rows_by_venue.get(venue_order_id)
            if attached is not None:
                self._attach(attached, client_order_id, venue_order_id=venue_order_id)
            own = self._cache_enabled and str(getattr(order, "strategy_id", "")) == str(self._strategy_id)
            if attached is None and own and venue_order_id in finished_by_venue:
                logger.warning(
                    "restored order %s is %s at the venue -- its stale open copy stays in the Cache and no cancel is sent",
                    client_order_id,
                    finished_by_venue[venue_order_id].get("state"),
                )
                continue
            if attached is not None and attached[1].get("state") not in _OPEN_ORDER_STATES:
                # The sweep above wrote the row terminal from the venue's report: the order ended while
                # this engine was down, and the open copy is the previous process's, listed by
                # `orders_open` for the process's life (spec 00120 D7).
                logger.warning(
                    "restored order %s is %s at the venue -- its stale open copy stays in the Cache and no cancel is sent",
                    client_order_id,
                    attached[1].get("state"),
                )
                continue
            payload = attached[1].get("order") if attached is not None else None
            if isinstance(payload, dict) and payload.get("reduce_only") is True and not cancel_all:
                logger.warning("adopted resting order %s is a ledgered reducer -- left resting and re-attached", client_order_id)
                continue
            reason = (
                f"the gate reads none ({', '.join(verdict.reasons) or '-'})"
                if cancel_all
                else "the ledger does not carry it as a resting reducer"
            )
            if own:
                # An order under this engine's own id at startup is one the cache restored (spec 00120 D9).
                logger.warning("canceling restored order %s, %s -- %s", client_order_id, restored_fill_state(order), reason)
            else:
                logger.warning("canceling adopted resting order %s -- %s", client_order_id, reason)
            try:
                self._client.cancel_order(order.client_order_id)
```

Replace, in `cli/engine/executor.py`, this block:

```python
            rows, finished, ledger_read = {}, {}, False
        venue_orders = self._read_venue_orders(rows, finished)
```

with:

```python
            rows, finished, ledger_read = {}, {}, False
        self._reset_fills_read([*rows.values(), *finished.values()])
        venue_orders = self._read_venue_orders(rows, finished)
```

Replace, in `cli/engine/executor.py`, this block:

```python
                row["client_order_id"]: (boundary, row)
                for boundary, row in open_submitted_rows(self._journal_dir, now)
                if self._minted_closed(row) and not _marked_unmatched(row)
            }
            reports = []
```

with:

```python
                row["client_order_id"]: (boundary, row)
                for boundary, row in open_submitted_rows(self._journal_dir, now)
                if (self._minted_closed(row) or row["client_order_id"] in self._restored_fills) and not _marked_unmatched(row)
            }
            # A restored row a fill reached and a terminal then closed before this pass -- the venue's
            # cancel ack, an expiry -- is in the window's closed rows: its credit-0 fill is repaired
            # here all the same (spec 00120 D8), and its intent waits for that repair.
            rows.update(
                {
                    row["client_order_id"]: (boundary, row)
                    for boundary, row in closed_submitted_rows(self._journal_dir, now)
                    if row["client_order_id"] in self._restored_fills and not _marked_unmatched(row)
                }
            )
            self._reset_fills_read(rows.values())
            reports = []
```

Replace, in `cli/engine/executor.py`, this block:

```python
        self._reread_tries = 0
        if rows:
            logger.warning("the re-read pass reads %d row(s) this engine minted terminal against the venue", len(rows))
            self._reconcile_adopted_rows(rows, {str(report.venue_order_id): report for report in reports}, recancel=True)
        self._settle_positions_from_venue("the re-read pass")

```

with:

```python
        self._reread_tries = 0
        if rows:
            restored = [cid for cid in rows if cid in self._restored_fills]
            if len(rows) > len(restored):
                logger.warning(
                    "the re-read pass reads %d row(s) this engine minted terminal against the venue", len(rows) - len(restored)
                )
            if restored:
                logger.warning(
                    "the re-read pass reads %d restored row(s) with a fill since its last read against the venue", len(restored)
                )
            self._reconcile_adopted_rows(rows, {str(report.venue_order_id): report for report in reports}, recancel=True)
        self._restored_fills.clear()
        self._settle_positions_from_venue("the re-read pass")

```

Replace, in `cli/engine/executor.py`, this block:

```python
    def _minted_closed(self, row: dict) -> bool:
```

with:

```python
    def _reset_fills_read(self, entries) -> None:
        """A pass's trade-history state (`_trades_cover`): nothing read yet, no failure, and the floor
        at the earliest boundary among the pass's rows, so the one read a shortfall triggers covers
        every row the pass holds."""
        self._venue_fills_read = None
        self._venue_fills_failed = False
        self._venue_fills_floor = min((boundary for boundary, _ in entries), default=None)

    def _minted_closed(self, row: dict) -> bool:
```

Replace, in `cli/engine/executor.py`, this block:

```python
                    venue_order_id = _row_venue_order_id(row)
                    order = self._cached_order(row, venue_order_id)
                    if order is not None:
                        self._reconcile_adopted_row(
```

with:

```python
                    venue_order_id = _row_venue_order_id(row)
                    order = self._cached_order(row, venue_order_id)
                    report = None if venue_orders is None or venue_order_id is None else venue_orders.get(venue_order_id)
                    if order is not None and report is not None and self._venue_answers(row, finished=False):
                        # A restored order the venue answered for: the report over the Cache's copy, the
                        # previous process's view (spec 00120 D6), and no re-cancel -- the order is open
                        # under this engine's own id, and the classification loop cancels or keeps it.
                        self._reconcile_adopted_row(
                            boundary,
                            row,
                            float(report.filled_qty),
                            report.order_status,
                            order_id=str(order.client_order_id),
                            venue_order_id=venue_order_id,
                        )
                        if recancel:
                            # The repair is what the intent waited for: the row leaves the fill set
                            # before the settle reads it.
                            self._restored_fills.discard(client_order_id)
                            self._settle_restored_intent(boundary, row)
                        continue
                    if order is not None:
                        self._reconcile_adopted_row(
```

Replace, in `cli/engine/executor.py`, this block:

```python
                    _log_resting_outside_the_cache(_row_label(row, venue_order_id), report)
                    self._reconcile_adopted_row(
                        boundary,
                        row,
                        float(report.filled_qty),
                        report.order_status,
                        order_id=order_id,
                        venue_order_id=venue_order_id,
                    )
                except Exception:
                    logger.critical("adopted row %s could not be reconciled against the venue", client_order_id, exc_info=True)
```

with:

```python
                    _log_resting_outside_the_cache(_row_label(row, venue_order_id), report)
                    self._reconcile_adopted_row(
                        boundary,
                        row,
                        float(report.filled_qty),
                        report.order_status,
                        order_id=order_id,
                        venue_order_id=venue_order_id,
                    )
                    if recancel and self._restored_row(row):
                        # A restored row a fill reached whose terminal the library minted -- D7's race,
                        # the ack flagged `reconciliation` -- takes this path, and the repair is what its
                        # intent waited for.
                        self._restored_fills.discard(client_order_id)
                        self._settle_restored_intent(boundary, row)
                except Exception:
                    logger.critical("adopted row %s could not be reconciled against the venue", client_order_id, exc_info=True)
```

Replace, in `cli/engine/executor.py`, this block:

```python

    def _read_venue_orders(self, rows: dict, finished: dict) -> dict | None:
        """The venue's own orders by txid, for the rows the Cache cannot answer: `{}` when no row
        needs them, which is every startup with nothing ledgered to compare, and so no order read; the
        holdings read the pass makes next (`_settle_positions_from_venue`) builds a client of its own at
```

with:

```python

    def _read_venue_orders(self, rows: dict, finished: dict) -> dict | None:
        """The venue's own orders by txid, for the rows the Cache cannot answer for: `{}` when no row
        needs them, which is every startup with nothing ledgered to compare, and so no order read; the
        holdings read the pass makes next (`_settle_positions_from_venue`) builds a client of its own at
```

Replace, in `cli/engine/executor.py`, this block:

```python
        A row needs them when it recorded a txid and the Cache holds no order under either of its
        ids -- an open row whose order closed while this process was down, or a finished row with
        fills, the only kind a withdrawal can show on. The read reaches back to the earliest such
        row's boundary.

        A read that fails leaves those rows unread and returns None, and that is a refusal, not a
```

with:

```python
        A row needs them when it recorded a txid and the Cache holds no order under either of its
        ids -- an open row whose order closed while this process was down, or a finished row with
        fills, the only kind a withdrawal can show on -- and, with the cache enabled, when the Cache's
        order is one it held at construction (`_venue_answers`): every order of the restored set, this
        engine's own and the EXTERNAL copies, whatever its Cache copy's status, and every finished row
        with fills whatever the Cache holds, so the venue is asked at every restart that held anything. The read reaches back to the earliest such row's
        boundary.

        A read that fails leaves those rows unread and returns None, and that is a refusal, not a
```

Replace, in `cli/engine/executor.py`, this block:

```python
                        continue
                    venue_order_id = _row_venue_order_id(row)
                    if venue_order_id is not None and self._cached_order(row, venue_order_id) is None:
                        needed.append(boundary)
                except Exception:
```

with:

```python
                        continue
                    venue_order_id = _row_venue_order_id(row)
                    if venue_order_id is None:
                        continue
                    order = self._cached_order(row, venue_order_id)
                    if order is None or self._venue_answers(row, finished=is_finished):
                        needed.append(boundary)
                except Exception:
```

Replace, in `cli/engine/executor.py`, this block:

```python
            return None

    def _cached_order(self, row: dict, venue_order_id: str | None):
        """The Cache's answer for `row`: its order (`_cache_lookup`), unless that order was closed by
```

with:

```python
            return None

    def _trades_cover(self, boundary: datetime, venue_order_id: str | None, ledgered: float) -> bool | None:
        """Whether the venue's trade history holds fills for `venue_order_id` summing to at least
        `ledgered`, the withdrawal check's second source (spec 00120 D19): the order's figure can fall
        short of the ledger because the library created the order from the venue's report without its
        fills applied, a cold start's shape, and the trade history says whether the fills happened. The
        history is read once per pass, from one hour before the earliest boundary among the pass's rows
        (`_reset_fills_read`), on a client of its own, and its failure answers None for the pass -- the
        check then trips on the order's figure as before, since an unread history is no evidence either
        way, and no later row of the pass reads again. A row with no txid answers None too."""
        if venue_order_id is None or self._venue_fills_failed:
            return None
        if self._venue_fills_read is None:
            since = (boundary if self._venue_fills_floor is None else self._venue_fills_floor) - _VENUE_READ_MARGIN
            try:
                reports = (self._venue_fills or read_venue_fills)(since)
            except Exception:
                self._venue_fills_failed = True
                logger.critical(
                    "the venue's trade history could not be read for the withdrawal check -- the order's figure decides",
                    exc_info=True,
                )
                return None
            filled: dict[str, float] = {}
            for report in reports:
                key = str(report.venue_order_id)
                filled[key] = filled.get(key, 0.0) + float(report.last_qty)
            self._venue_fills_read = filled
        return self._venue_fills_read.get(venue_order_id, 0.0) >= ledgered - _OVERFILL_TOLERANCE

    def _cached_order(self, row: dict, venue_order_id: str | None):
        """The Cache's answer for `row`: its order (`_cache_lookup`), unless that order was closed by
```

Replace, in `cli/engine/executor.py`, this block:

```python
        a terminal this engine minted (`_minted_terminal`), when the Cache holds this engine's own
        guess and answers nothing, so the venue is asked. At startup no order is closed that way --
        reconciliation adopts open orders, and the void it can mint is not one of those terminals --
        so the startup sweeps read as before."""
```

with:

```python
        a terminal this engine minted (`_minted_terminal`), when the Cache holds this engine's own
        guess and answers nothing, so the venue is asked. Without the cache no order is closed that
        way at startup -- reconciliation adopts open orders, and the void it can mint is not one of
        those terminals -- so the startup sweeps read as before; with it, an order a previous process
        closed with a minted terminal is restored closed, its terminal in its history, and is withheld
        here at startup too, and `_venue_answers` says which restored rows the venue is asked over."""
```

Replace, in `cli/engine/executor.py`, this block:

```python
        it goes through the Cache's own venue-order-id index rather than an assumption about how
        reconciliation names what it adopts. `cache.order` serves closed orders as readily as open
        ones, and both accessors are typed and refuse a plain str."""
        cache = self._cache
        order = cache.order(ClientOrderId(row["client_order_id"]))
```

with:

```python
        it goes through the Cache's own venue-order-id index rather than an assumption about how
        reconciliation names what it adopts. `cache.order` serves closed orders as readily as open
        ones, and both accessors are typed and refuse a plain str. With the cache enabled the first
        lookup answers for an order a previous process placed too, restored under the id this engine
        minted; `_venue_answers` says which of those the venue is asked over."""
        cache = self._cache
        order = cache.order(ClientOrderId(row["client_order_id"]))
```

Replace, in `cli/engine/executor.py`, this block:

```python
            order = None if client_order_id is None else cache.order(client_order_id)
        return order

    def _attach(self, entry: tuple[datetime, dict], *client_order_ids: str, venue_order_id: str | None) -> None:
```

with:

```python
            order = None if client_order_id is None else cache.order(client_order_id)
        return order

    def _venue_answers(self, row: dict, *, finished: bool) -> bool:
        """Whether the venue is asked over an order the Cache holds (spec 00120 D6): with the cache
        enabled, every finished row with fills, whatever the Cache's copy, and every row of the restored
        set, whatever its copy's status -- the copy is the previous process's view, or the double
        booking's, which reads an order FILLED where the venue says partial (D7), and a check against it
        would compare the ledger with itself. Without the cache the Cache holds only what this boot's
        reconciliation adopted, and it answers as before."""
        if not self._cache_enabled:
            return False
        return finished or self._restored_row(row)

    def _restored_row(self, row: dict) -> bool:
        """Whether the Cache held `row`'s order at construction (`_read_restored`): under the id this
        engine minted, or, for an EXTERNAL copy, under the txid the row recorded, which is that copy's
        own client order id."""
        return row["client_order_id"] in self._restored or _row_venue_order_id(row) in self._restored

    def _settle_restored_intent(self, boundary: datetime, row: dict) -> None:
        """A restored row's intent, written once at the row's terminal while it still reads `pending`
        (spec 00120 D8): `filled` with the row's `filled_qty`, else `revoked` with the reducer's end.
        The startup sweep settles the window's other pending intents and leaves a kept reducer's, an
        open row it sent no cancel for; this is written by what ends that row -- the event's path, or
        the re-read pass's repair where the fill's credit was nothing -- at the row's own boundary
        without `self._plan`, the sweep's shape, and no later pass revisits it. A row a fill reached
        since the pass last read it (`_restored_fills`) is not settled by the event's path: its
        `filled_qty` is the credit-0 figure until the pass repairs it, and the pass writes the intent
        after that repair."""
        if not self._restored_row(row) or row.get("state") in _OPEN_ORDER_STATES:
            return
        if row["client_order_id"] in self._restored_fills:
            return
        key = (row.get("plan_id"), row.get("intent_index"))
        try:
            pending = {(plan_id, index) for _, plan_id, index in pending_plan_intents(self._journal_dir, self._now())}
        except Exception:
            logger.critical(
                "the plan entries could not be read -- the intent of restored row %s keeps the state it has",
                row["client_order_id"],
                exc_info=True,
            )
            return
        if key not in pending:
            return
        if row.get("state") == "filled":
            outcome, reasons = "filled", ()
        else:
            outcome, reasons = "revoked", ("the kept reducer ended without filling",)
        try:
            update_plan_intent(
                self._journal_dir, boundary, key[0], key[1], outcome=outcome, reasons=reasons, filled_qty=float(row["filled_qty"])
            )
        except Exception:
            logger.critical("intent %s of plan %s could not be journaled as %s", key[1], key[0], outcome, exc_info=True)

    def _attach(self, entry: tuple[datetime, dict], *client_order_ids: str, venue_order_id: str | None) -> None:
```

Replace, in `cli/engine/executor.py`, this block:

```python
        if completes and state == "filled":
            _inc_order("filled")
        if delta < -_OVERFILL_TOLERANCE:
            # The dangerous direction: the ledger claims more filled than the venue reports, so this
            # engine believes it reduced more than it did. Clamping it to zero would swallow the
```

with:

```python
        if completes and state == "filled":
            _inc_order("filled")
        if delta < -_OVERFILL_TOLERANCE and self._trades_cover(boundary, venue_order_id, ledgered) is True:
            # The order's figure fell short of the ledger and the venue's trade history covers the ledger:
            # the figure is the library's copy without its fills applied, a cold start's shape, and no fill
            # was withdrawn. The row keeps its figure and joins the repaired set, so a fill the library
            # later infers for this order credits only what the Cache holds beyond the row.
            self._rows_the_pass_repaired.add(client_order_id)
            logger.warning(
                "adopted order %s reads %.10g filled on its order figure against the %.10g recorded here, and the venue's "
                "trade history covers the ledger -- the figure is the library's copy without its fills applied, no withdrawal",
                label,
                venue_filled,
                ledgered,
            )
        elif delta < -_OVERFILL_TOLERANCE:
            # The dangerous direction: the ledger claims more filled than the venue reports, so this
            # engine believes it reduced more than it did. Clamping it to zero would swallow the
```

Replace, in `cli/engine/executor.py`, this block:

```python
                    venue_order_id = _row_venue_order_id(row)
                    order = self._cached_order(row, venue_order_id)
                    if order is None and venue_order_id is None:
                        self._mark_unmatched(boundary, row, _unmatchable_what(row), open_row=False)
```

with:

```python
                    venue_order_id = _row_venue_order_id(row)
                    order = self._cached_order(row, venue_order_id)
                    if order is not None and venue_order_id is not None and self._venue_answers(row, finished=True):
                        if venue_orders is None:
                            continue  # the read failed: unread, not unknowable, and every plan is refused
                        order = venue_orders.get(venue_order_id)  # the venue's report over the Cache's copy (spec 00120 D6)
                    if order is None and venue_order_id is None:
                        self._mark_unmatched(boundary, row, _unmatchable_what(row), open_row=False)
```

Replace, in `cli/engine/executor.py`, this block:

```python
                        self._mark_unmatched(boundary, row, f"the venue's order read has no order {venue_order_id}", open_row=False)
                        continue
                    self._reconcile_finished_row(boundary, row, float(order.filled_qty), _row_label(row, venue_order_id))
                except Exception:
                    logger.critical("finished row %s could not be reconciled against the venue", client_order_id, exc_info=True)
```

with:

```python
                        self._mark_unmatched(boundary, row, f"the venue's order read has no order {venue_order_id}", open_row=False)
                        continue
                    self._reconcile_finished_row(
                        boundary, row, float(order.filled_qty), _row_label(row, venue_order_id), venue_order_id=venue_order_id
                    )
                except Exception:
                    logger.critical("finished row %s could not be reconciled against the venue", client_order_id, exc_info=True)
```

Replace, in `cli/engine/executor.py`, this block:

```python
            logger.critical("the finished-row sweep raised -- classifying resting orders anyway", exc_info=True)

    def _reconcile_finished_row(self, boundary: datetime, row: dict, venue_filled: float, label: str) -> None:
        """One closed row against the venue's own figure: does the venue still report the quantity
        this row was closed on?
```

with:

```python
            logger.critical("the finished-row sweep raised -- classifying resting orders anyway", exc_info=True)

    def _reconcile_finished_row(
        self, boundary: datetime, row: dict, venue_filled: float, label: str, *, venue_order_id: str | None = None
    ) -> None:
        """One closed row against the venue's own figure: does the venue still report the quantity
        this row was closed on?
```

Replace, in `cli/engine/executor.py`, this block:

```python
        ledgered = row["filled_qty"]
        if venue_filled >= ledgered - _OVERFILL_TOLERANCE:
            return
        payload = {
```

with:

```python
        ledgered = row["filled_qty"]
        if venue_filled >= ledgered - _OVERFILL_TOLERANCE:
            return
        if self._trades_cover(boundary, venue_order_id, ledgered) is True:
            # The second source (spec 00120 D19): the order's figure is the library's copy without its
            # fills applied, and the venue's trade history holds the fills the row was closed on.
            logger.warning(
                "finished order %s reads %.10g filled on its order figure against the %.10g it was closed on, and the venue's "
                "trade history covers the ledger -- no withdrawal",
                label,
                venue_filled,
                ledgered,
            )
            return
        payload = {
```

Replace, in `cli/engine/executor.py`, this block:

```python
        free_zeur = state.balances.get("ZEUR", 0.0) or state.balances.get("EUR", 0.0)
        reasons = plan_refusals(
```

with:

```python
        if self._cache_enabled and any(intent.action == "open" for intent in plan.intents) and not self._nothing_in_flight():
            # The mixed-inventory check's venue read (`_mixed_inventory_refusals`) is a signed read on
            # the trade key, on the passes' nonce terms: on the first tick the startup pass's cancels
            # are still PENDING_CANCEL, so the plan waits in its file for a tick with nothing in flight.
            logger.info(
                "probe plan %s waits for a tick with nothing in flight -- its opening intents take a venue read", plan.plan_id
            )
            return
        free_zeur = state.balances.get("ZEUR", 0.0) or state.balances.get("EUR", 0.0)
        reasons = plan_refusals(
```

Replace, in `cli/engine/executor.py`, this block:

```python
        pass's cancels of adopted orders, and a trip's, PENDING_CANCEL with no intent live. A Cache
        that cannot be read holds the pass, never a plan."""
        try:
            return self._active is None and not list(self._cache.orders_inflight(venue=_VENUE))
        except Exception:
            logger.exception("executor in-flight read raised -- the re-read pass waits for the next tick")
```

with:

```python
        pass's cancels of adopted orders, and a trip's, PENDING_CANCEL with no intent live. A Cache
        that cannot be read holds the pass, and under the cache the pickup of a plan with an opening
        intent (`_pickup`) until the read answers, when its expiry refuses the file; never a plan otherwise."""
        try:
            return self._active is None and not list(self._cache.orders_inflight(venue=_VENUE))
        except Exception:
            logger.exception("executor in-flight read raised -- the re-read pass and a held pickup wait for the next tick")
```

Replace, in `cli/engine/executor.py`, this block:

```python
            free_zeur=free_zeur,
        )
        intents = [
            {"index": i, "intent": raw, "outcome": "pending", "reasons": [], "filled_qty": 0.0}
```

with:

```python
            free_zeur=free_zeur,
        )
        if self._cache_enabled:
            reasons = [*reasons, *self._mixed_inventory_refusals(plan, state)]
        intents = [
            {"index": i, "intent": raw, "outcome": "pending", "reasons": [], "filled_qty": 0.0}
```

Replace, in `cli/engine/executor.py`, this block:

```python
_SPOT_SYMBOL_BY_BASE = {symbol.split("/")[0]: symbol for symbol in INSTRUMENT_IDS if symbol.endswith("/EUR")}
# Kraken spells one asset three ways across its surfaces; the balance read tries them in order.
# Every other base gets the plain code plus its `X`-prefixed classic spelling.
_BTC_BALANCE_ALIASES = ("BTC", "XBT", "XXBT")
```

with:

```python
_SPOT_SYMBOL_BY_BASE = {symbol.split("/")[0]: symbol for symbol in INSTRUMENT_IDS if symbol.endswith("/EUR")}
```

Replace, in `cli/engine/executor.py`, this block:

```python
def _spot_balance(balances: dict, base: str) -> float:
    """What the venue record says is held of `base`, or 0.0 when no spelling of it is present.
    Raises on a present-but-unreadable value -- the caller turns that into a refusal, because a
    balance this process cannot parse is not a balance it may reason about."""
    aliases = _BTC_BALANCE_ALIASES if base == "BTC" else (base, f"X{base}")
    for alias in aliases:
        if alias in balances:
            return float(balances[alias])
    return 0.0
```

with:

```python
def _spot_balance(balances: dict, base: str) -> float:
    """What the venue record says is held of `base`, or 0.0 when no spelling of it is present: a
    code is `base`'s when `resolve_base` maps it there, the rule `read_venue_holdings` reads the
    balances by, so Kraken's `XDG` is DOGE and `XBT` BTC. Raises on a present-but-unreadable value --
    the caller turns that into a refusal, because a balance this process cannot parse is not a
    balance it may reason about."""
    from cli.engine.flatten import resolve_base

    bases = frozenset((base,))
    for code, value in balances.items():
        if resolve_base(code, bases) == base:
            return float(value)
    return 0.0
```

Replace, in `cli/engine/executor.py`, this block:

```python
        self._index = 0
        self._resolved_notional = {}

    def _pump(self, now: datetime) -> None:
```

with:

```python
        self._index = 0
        self._resolved_notional = {}

    def _mixed_inventory_refusals(self, plan, state) -> list[str]:
        """The refusal 00118 D11 carries into spec 00120 D12: while the cache is enabled, an opening
        intent that would put a spot lot and a margin lot on one pair is refused -- the restore reads
        both as the instrument's position and tells neither from the other -- and a close never is, since
        it takes inventory off. A spot open is refused where the venue's margin positions hold the pair,
        read through `read_venue_positions` once per plan that carries an open, on the passes' nonce
        terms, which `_pickup` keeps by holding such a plan until nothing of this process is in flight;
        a margin open where the venue state's balances, already read through `_spot_balance` under
        every spelling of the base, hold the pair's base at or above the pair's `ordermin` -- a lot
        under it is dust the engine cannot sell, and would refuse every margin open on the pair for as
        long as the cache is enabled. A read that fails refuses each open intent, since the shape is
        then unknown."""
        opens = [(index, intent) for index, intent in enumerate(plan.intents) if intent.action == "open"]
        if not opens:
            return []
        try:
            margin = (self._venue_positions or read_venue_positions)()
        except Exception as exc:
            return [
                f"intent {index}: the venue's margin positions could not be read for the mixed-inventory check -- "
                f"{type(exc).__name__}: {exc}"
                for index, _ in opens
            ]
        out: list[str] = []
        for index, intent in opens:
            base = intent.symbol.split("/")[0]
            try:
                spot = _spot_balance(state.balances, base)
            except Exception as exc:
                out.append(f"intent {index}: {intent.symbol} spot inventory could not be read -- {type(exc).__name__}: {exc}")
                continue
            held = margin.get(intent.symbol, 0.0)
            floor = max(state.instruments[intent.symbol].ordermin, FLAT_TOLERANCE)
            if intent.leverage is None and abs(held) > FLAT_TOLERANCE:
                out.append(
                    f"intent {index}: a spot open on {intent.symbol} beside a margin position of {held:.10g} there"
                    " -- the cache's restore does not distinguish them"
                )
            elif intent.leverage is not None and spot >= floor:
                out.append(
                    f"intent {index}: a margin open on {intent.symbol} beside {spot:.10g} {base} spot inventory"
                    " -- the cache's restore does not distinguish them"
                )
        return out

    def _pump(self, now: datetime) -> None:
```

Replace, in `cli/engine/executor.py`, this block:

```python
        final act is the failure this scoping exists to prevent. Two paths reach here and each keeps
        that scoping its own way: `on_order_event` carries only the strategy's own order topic, whose
        events are by construction this engine's submissions; `_on_external_event` carries the
        `events.order.EXTERNAL` topic, which is account-wide, and it is that method's unmatched
        early-return -- no `_attached` row, so counted, logged, and dropped -- that keeps the hand
```

with:

```python
        final act is the failure this scoping exists to prevent. Two paths reach here and each keeps
        that scoping its own way: `on_order_event` carries only the strategy's own order topic, whose
        events are by construction this engine's own orders -- this process's submissions, and the
        ones the cache restored under its id, attached at construction (`_read_restored`); `_on_external_event` carries the
        `events.order.EXTERNAL` topic, which is account-wide, and it is that method's unmatched
        early-return -- no `_attached` row, so counted, logged, and dropped -- that keeps the hand
```

Replace, in `cli/engine/executor.py`, this block:

```python
    def _on_external_event(self, event) -> None:
        """Events from `events.order.EXTERNAL` (spec 00098 D1): the delivery path for orders this
        process adopted at startup, filtered by disposition BEFORE anything else runs.

        Matched (the ledger vouches for the order): delegate into the existing pipeline --
```

with:

```python
    def _on_external_event(self, event) -> None:
        """Events from `events.order.EXTERNAL` (spec 00098 D1): the delivery path for orders this
        process adopted at startup under the venue's txid -- the ones the cache did not restore, or
        every one when the cache is off -- filtered by disposition BEFORE anything else runs. A
        restored own order keeps its own id and its events reach the own topic (spec 00120 D12); an
        EXTERNAL copy the store restored keeps this path, in the restored set under its txid, its fills
        credited nothing and its row repaired by the re-read pass as a restored own order's is, and its
        intent written here as the own path writes it.

        Matched (the ledger vouches for the order): delegate into the existing pipeline --
```

Replace, in `cli/engine/executor.py`, this block:

```python
                row["state"] = "filled"
                _inc_order("filled")
            return
        payload = {"type": name, "at": self._now().isoformat()}
```

with:

```python
                row["state"] = "filled"
                _inc_order("filled")
                self._settle_restored_intent(boundary, row)
            return
        payload = {"type": name, "at": self._now().isoformat()}
```

Replace, in `cli/engine/executor.py`, this block:

```python
        if terminal_state is not None:
            row["state"] = terminal_state  # the mirror the completion guard and D7 both read

    def _cache_net(self, symbol: str) -> float:
```

with:

```python
        if terminal_state is not None:
            row["state"] = terminal_state  # the mirror the completion guard and D7 both read
            self._settle_restored_intent(boundary, row)

    def _cache_net(self, symbol: str) -> float:
```

Replace, in `cli/engine/executor.py`, this block:

```python
        leg this engine opened realizes an outcome that is genuinely this engine's, and scoping to
        our own strategy would systematically miss exactly that case. Telemetry answers what the
        account did; the reconciliation answers what our own orders did."""
        cache = self._cache
        total = 0.0
        for instrument_id in self._traded:
            positions = list(cache.positions_open(instrument_id=instrument_id)) + list(
                cache.positions_closed(instrument_id=instrument_id)
            )
            for position in positions:
                pnl = position.realized_pnl
                if pnl is None:
                    continue
                code = getattr(getattr(pnl, "currency", None), "code", None)
                if code not in EUR_CODES:
                    logger.warning(
                        "realized pnl on %s is denominated in %s, not EUR -- it is left out of the EUR total",
                        instrument_id,
                        code,
                    )
                    continue
                total += float(pnl)
        return total

```

with:

```python
        leg this engine opened realizes an outcome that is genuinely this engine's, and scoping to
        our own strategy would systematically miss exactly that case. Telemetry answers what the
        account did; the reconciliation answers what our own orders did.

        Less the baseline read at construction (spec 00120 D10): with the cache enabled the Cache
        holds a previous run's closed positions and a restored open one's earlier partial closes,
        and their realizations are that run's, not this window's."""
        total = 0.0
        for instrument_id in self._traded:
            total += self._realized_on(instrument_id) - self._realized_baseline.get(instrument_id, 0.0)
        return total

    def _realized_on(self, instrument_id: InstrumentId) -> float:
        """The Cache's realized PnL on one instrument, open and closed positions both, EUR only."""
        cache = self._cache
        total = 0.0
        positions = list(cache.positions_open(instrument_id=instrument_id)) + list(
            cache.positions_closed(instrument_id=instrument_id)
        )
        for position in positions:
            pnl = position.realized_pnl
            if pnl is None:
                continue
            code = getattr(getattr(pnl, "currency", None), "code", None)
            if code not in EUR_CODES:
                logger.warning(
                    "realized pnl on %s is denominated in %s, not EUR -- it is left out of the EUR total",
                    instrument_id,
                    code,
                )
                continue
            total += float(pnl)
        return total

```

Replace, in `cli/engine/executor.py`, this block:

```python
        cannot be read or does not hold the order, credits the event's quantity: the startup's repair
        rebuilds the Cache from the venue first, so nothing replays behind it."""
        if row["client_order_id"] not in self._rows_the_pass_repaired:
            return qty
```

with:

```python
        cannot be read or does not hold the order, credits the event's quantity: the startup's repair
        rebuilds the Cache from the venue first, so nothing replays behind it."""
        if self._restored_row(row):
            # A restored row's fill credits nothing (spec 00120 D8): the library books a trade frame on
            # a restored open order twice, an inferred fill for the cumulative gap and then the fill
            # itself, so the event's quantity would trip a false overfill; the fill arms the re-read
            # pass, whose venue read repairs the row up to the venue's cumulative figure. A fill booked
            # twice leaves the Cache's copy ahead of the venue's for the process's life whatever that
            # read answers, and nothing here tells it from a fill booked once, so the WARNING is logged
            # at each restored row's fill, once per row until the pass reads it, the trip check and the
            # row's append both asking this credit: its text is what an operator searches before a
            # restart, which it takes flat whichever it was.
            if row["client_order_id"] not in self._restored_fills:
                logger.warning(
                    "a fill on restored order %s credits nothing until the venue is read -- the next restart is taken flat",
                    row["client_order_id"],
                )
            self._restored_fills.add(row["client_order_id"])
            self._arm_reread_after_mint()
            return 0.0
        if row["client_order_id"] not in self._rows_the_pass_repaired:
            return qty
```

Replace, in `cli/engine/executor.py`, this block:

```python
        It still gets its ledger row -- that is the no-fill-without-a-forensic-row invariant, and the
        row is chosen by the boundary the ORDER was filed under, never the boundary of the tick that
        saw the event. No state claim is made: this process is not tracking that order's lifecycle,
        so the row keeps whatever open state it has and stays visible to the next re-attach.

        A fill on an order belonging to the RUNNING intent also grows `filled`, so the next
```

with:

```python
        It still gets its ledger row -- that is the no-fill-without-a-forensic-row invariant, and the
        row is chosen by the boundary the ORDER was filed under, never the boundary of the tick that
        saw the event. No state claim is made for an order of this process: it is not tracking that
        order's lifecycle, so the row keeps whatever open state it has and stays visible to the next
        re-attach. A RESTORED order's events land here too, under its own id (spec 00120 D12), and for
        its row this path makes the external path's two writes: a fill completing the ledgered
        quantity writes the row `filled` once and counts it, and every other event asks
        `_venue_terminal_state` for the row's state, `ambiguous` on a mint, a completed row never
        demoted; a terminal writes the kept reducer's intent (`_settle_restored_intent`).

        A fill on an order belonging to the RUNNING intent also grows `filled`, so the next
```

Replace, in `cli/engine/executor.py`, this block:

```python
            if active is not None and self._claims(row, active):
                active.filled += qty
        if is_fill:
            self._publish_fill(event)
```

with:

```python
            if active is not None and self._claims(row, active):
                active.filled += qty
        if self._restored_row(row):
            if is_fill:
                if row.get("state") != "filled" and row["filled_qty"] >= _ordered_qty(row) - _OVERFILL_TOLERANCE:
                    update_submitted_row(self._journal_dir, boundary, row["client_order_id"], state="filled")
                    row["state"] = "filled"
                    _inc_order("filled")
                    self._settle_restored_intent(boundary, row)
            else:
                terminal_state = None if row.get("state") == "filled" else self._venue_terminal_state(event)
                if terminal_state is not None:
                    update_submitted_row(self._journal_dir, boundary, row["client_order_id"], state=terminal_state)
                    row["state"] = terminal_state
                    self._settle_restored_intent(boundary, row)
        if is_fill:
            self._publish_fill(event)
```

Replace, in `cli/engine/node.py`, this block:

```python
    mid-probe -- keeps nautilus's `EXTERNAL` strategy id and structurally never arrives on that
    topic. That scoping is the precondition the executor's unknown-order kill trip rests on;
    widening it would latch the kill switch on a sanctioned act.

    A SECOND order stream reaches this strategy from the side (spec 00098 D1, 00100 D2), and
```

with:

```python
    mid-probe -- keeps nautilus's `EXTERNAL` strategy id and structurally never arrives on that
    topic. That scoping is the precondition the executor's unknown-order kill trip rests on;
    widening it would latch the kill switch on a sanctioned act. With the cache enabled the topic
    also carries the orders a previous process of this engine placed and the cache restored under
    this same id, since the id derives from the class name and the store keys them under it; the
    executor attaches those at its construction, inside this `on_start` (spec 00120 D6).

    A SECOND order stream reaches this strategy from the side (spec 00098 D1, 00100 D2), and
```

Replace, in `cli/engine/node.py`, this block:

```python
    only orders this engine submitted and the unknown-order trip still runs only there. The second
    stream is `ExternalOrderObserver`, a separate strategy registered under the venue's external
    order identity, and it forwards into `_on_external_order_event` -> the executor's disposition
    filter, which acts only on the rows the adopt pass re-attached plus this session's own
    submissions -- a SUBSET of what the ledger vouches for, and a strict one by the rows
    `executor._reconcile_adopted_rows` leaves unattached -- and everything else it counts, logs,
```

with:

```python
    only orders this engine submitted and the unknown-order trip still runs only there. The second
    stream is `ExternalOrderObserver`, a separate strategy registered under the venue's external
    order identity -- the orders the cache did not restore, a cold start's among them -- and it
    forwards into `_on_external_order_event` -> the executor's disposition filter, which acts only
    on the rows the adopt pass re-attached plus this session's own
    submissions -- a SUBSET of what the ledger vouches for, and a strict one by the rows
    `executor._reconcile_adopted_rows` leaves unattached -- and everything else it counts, logs,
```

Replace, in `cli/engine/node.py`, this block:

```python
class ExternalOrderObserver(Strategy):
    """The second order stream (spec 00098 D1, 00100 D2): registered under the venue's external
    order identity, it receives the order events of everything this process did not submit --
    a previous process's resting order the startup pass adopted, and the account owner's own
    hand-placed settling orders alike -- and forwards each to `handler`, which is the shadow
    strategy's `_on_external_order_event` and through it the executor's disposition filter. That
    filter acts only on the rows the adopt pass re-attached and this session's own submissions --
```

with:

```python
class ExternalOrderObserver(Strategy):
    """The second order stream (spec 00098 D1, 00100 D2): registered under the venue's external
    order identity, it receives the order events of everything this process did not submit and the
    cache did not restore under the engine's own id -- a previous process's resting order the
    startup pass adopted by its txid, and the account owner's own hand-placed settling orders
    alike -- and forwards each to `handler`, which is the shadow
    strategy's `_on_external_order_event` and through it the executor's disposition filter. That
    filter acts only on the rows the adopt pass re-attached and this session's own submissions --
```

- [ ] **Step 5: Run the executor and node files, then the harness, and watch them pass**

Run: `uv run pytest tests/test_engine_executor.py tests/test_engine_node.py -q -p no:cacheprovider`
Expected: `482 passed, 2 skipped`, the skips the node file's two live-venue gates.
Run: `uv run pytest tests/test_cache_restart.py -q -p no:cacheprovider`
Expected: `9 passed`, in about seven and a half minutes (`9 passed in 445.92s` when this plan was written).

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_cache_restart.py tests/test_engine_executor.py tests/test_engine_node.py tests/test_engine_command.py tests/test_engine_flatten.py tests/test_engine_metrics.py tests/test_engine_stub_fidelity.py tests/test_engine_execledger.py tests/test_nautilus_interface_pin.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `1763 passed, 3 skipped` when this plan was written, the skips `tests/test_engine_node.py`'s two live-venue gates and `tests/test_engine_flatten.py`'s one. The list is every module that imports `cli.engine.executor` or `cli.engine.node`, with the ledger's, the pin, the stub walker and the internal-terms walker.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 8: Commit**

```bash
git add cli/engine/executor.py cli/engine/node.py tests/test_engine_executor.py tests/cache_restart_child.py tests/test_cache_restart.py tests/test_engine_stub_fidelity.py
git commit -m "feat(engine): the startup pass under a restored Cache -- the venue over every restored order, the kept reducer credited from the venue and its intent written at its terminal, the realized baseline, the mixed-inventory refusal, and the trade history read before a withdrawal trips

Measured on the restart harness against the pinned wheel and Valkey 8.1.1: the Cache restores this
engine's own orders under their own client order ids, reconciliation keeps them and regresses a
partially filled one to ACCEPTED, mass status reads open orders only so an order that closed while
the engine was down comes back open, and a trade frame on a restored open order is booked twice.
The executor reads the restored set at construction when the cache is enabled -- every order the
Cache holds for the venue, this engine's own and the EXTERNAL copies alike, since the store restores
an EXTERNAL copy a previous process adopted with that process's fills, the same state as a restored
own order -- open and closed copies alike, and attaches there each whose row the ledger's window
carries, so a fill in the seconds before the first tick lands in its row and not in the
unknown-order trip; the startup pass asks the venue over every row of that set, whatever its copy's
status, and over every finished row with fills, taking the report over the Cache's copy, the
previous process's view; a restored order the venue holds closed has its row written from the
report and no cancel sent, its stale open copy left in the Cache; one the venue holds open is
cancelled unless its row is a ledgered reducer, the line naming its fill state. A restored row's
fill credits nothing, logs a WARNING at the fill that the next restart is taken flat, and arms the
re-read pass, whose population gains the restored rows with a fill since its last read, the window's closed rows among them, and whose repair brings the row to
the venue's cumulative figure; the kept reducer's intent is written once at the row's terminal,
filled or revoked, by the path that ends it, the re-read pass's repair included, since a zero credit
never completes a row on the event path, and held past a terminal that lands before the pass, so it
names the repaired quantity and never the credit-0 one. The detached path makes the external path's two writes for a restored row alone. The
realized gauge subtracts the realizations the Cache held at construction. An opening intent that would put
a spot lot beside a margin position on its pair, or the reverse, is refused while the cache is
enabled, the margin figure the venue's own positions read through a bare client and the spot figure
every spelling of the base the holdings read resolves, DOGE's XDG among them, and a close never
is. The withdrawal check reads the venue's trade history before it trips, once per pass from the
earliest boundary among the pass's rows and never again in it after a failure: on a cold start the library creates the EXTERNAL
copy from the venue's order report with no fill applied, so the figure reads 0 against the ledger's
0.4 while the trade history holds the 0.4; the check now trips only when the history's fills for
the order fall short of the ledger, a covered row keeping its figure and joining the repaired set so
the fill the library infers at the cancel's ack credits it nothing beyond the Cache, and an unread
history leaving the trip on the order's figure. The docstrings a persistent cache made false are
rewritten in both modules.

Cases: the restored set as every order the Cache holds, own and EXTERNAL, only with the cache
enabled, and empty at CRITICAL when the read fails; a fill on a restored row before the first tick
landing in its row and tripping nothing; a closed restored copy read at the venue with the report
winning; a restored EXTERNAL copy of a kept reducer crediting a frame's two fills nothing and the
pass repairing its row; a restored order's stale open copy sent no cancel at a later restart once
its row is closed; a plan with an opening intent held until nothing is in flight and picked up on
the next tick, and not held without the cache; a margin open refused beside spot inventory at the
pair's ordermin, DOGE's under its XDG spelling too, and admitted beside dust under it; a fill then a minted terminal on a restored row
repaired by the pass and named among its restored rows; a true withdrawal tripping on a history
short on the row's txid however much another txid holds; the venue's report repairing the row over the Cache's copy with the cache
enabled and the copy answering without it; a restored order the venue reports closed written from
the report with no cancel and its intent settled by the sweep; a restored opener cancelled with its
fill state named and a kept reducer left resting; a finished row with fills read at the venue over
the Cache's agreeing copy with the cache enabled, a withdrawal tripping the kill switch, and not
read without it; a fill on a restored row credited nothing with its WARNING logged once at the
fill, the pass repairing the row and the
completing repair writing the intent filled; a venue cancel on the kept reducer writing its row and
its intent revoked, a minted one ambiguous and the intent pending; a fill then a terminal before
the next tick repaired by the pass on a kept reducer and a cancelled opener, the intent written
after the repair; the realized baseline; the mixed-inventory refusal on an opening intent of either
kind beside the other, admitted beside its own kind and on a close, off without the cache and on a
plan of closes, and refused by name when the position read fails; the trade history read once per
pass over two short rows and not retried after a failure; a cold start's order figure short of the ledger covered
by the trade history on an open row and a finished one, no trip and the row kept; a true withdrawal
with no fill in the history tripping as today on both; a history read that fails leaving the trip on
the figure; and, on the harness, the restored set, the pass's cancel of the restored opener and its
row and intent, the fill-while-down repair to the venue's 0.7, the cancelled-while-down row written
from the venue with no cancel sent, both double-booked fills credited nothing and the row repaired
to the venue's 0.6 with the intent pending and the realized readings at zero, the same frame on a
restored opener racing the pass's cancel repaired to the venue's 0.6 on a row the flagged ack left
ambiguous, and the cold start over the partially filled opener tripping nothing, its inferred fill
credited nothing and its row settled at 0.4.

PROBE_VERDICT

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>"
```

- [ ] **Step 9: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 10: Prove the guards with twenty-one probes, then record their verdicts by a message-only amend**

The control respells the restored cancel line so the restored-opener case fails. The mutations, in order: the venue answering for restored rows dropped, so the Cache's copy is trusted again; the restored fill no longer noted for the re-read pass; the re-read pass's repair no longer writing the kept reducer's intent; the realized baseline no longer read; the mixed-inventory refusal dropped; the closed restored order's cancel no longer withheld; the trade history no longer consulted before the open sweep's trip; the attach at construction dropped; the restored set read from the open orders alone; the closed rows dropped from the re-read pass's population; the intent no longer held while a fill waits for its repair; a failed trade-history read retried in the pass; the mixed-inventory check widened to every intent; the pickup's hold dropped, so the positions read races the pass's cancels; the trade history's cover summed across txids; the spot floor back at the flat tolerance, so dust refuses a margin open; the re-read pass's restored count excluding a row a minted terminal closed; the stale open copy cancelled at a later restart; the spot balance read by the removed helper's spellings, the plain and `X`-prefixed code and BTC's `XBT` and `XXBT`, so DOGE's `XDG` alone reads 0 and the `XDG` case alone fails; the restored fill's WARNING dropped; the restored fill's WARNING logged at every credit asked.

```bash
K="restored or kept_reducer or finished_row_with_fills or mix_spot or mixed_inventory or margin_position_read or baseline or cold_starts_order_figure or true_withdrawal or trade_history_read or read_once_per_pass"
C='s/"canceling restored order %s, %s -- %s"/"cancelling restored order %s, %s -- %s"/'
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        return finished or self._restored_row(row)$/        return finished/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            self._restored_fills.add(row\["client_order_id"\])$/            pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^                        if recancel:$/                        if False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        self._read_realized_baseline()$/        pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            reasons = \[\*reasons, \*self._mixed_inventory_refusals(plan, state)\]$/            reasons = list(reasons)/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            if attached is not None and attached\[1\].get("state") not in _OPEN_ORDER_STATES:$/            if False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if delta < -_OVERFILL_TOLERANCE and self._trades_cover(boundary, venue_order_id, ledgered) is True:$/        if False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^                self._attach(entry, client_order_id, venue_order_id=venue_order_id)$/                pass/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/orders = list(self._cache.orders(venue=_VENUE))/orders = list(self._cache.orders_open(venue=_VENUE))/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^                    if row\["client_order_id"\] in self._restored_fills and not _marked_unmatched(row)$/                    if False/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if row\["client_order_id"\] in self._restored_fills:$/        if False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if venue_order_id is None or self._venue_fills_failed:$/        if venue_order_id is None:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        opens = \[(index, intent) for index, intent in enumerate(plan.intents) if intent.action == "open"\]$/        opens = list(enumerate(plan.intents))/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if self._cache_enabled and any(intent.action == "open" for intent in plan.intents) and not self._nothing_in_flight():$/        if False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        return self._venue_fills_read.get(venue_order_id, 0.0) >= ledgered - _OVERFILL_TOLERANCE$/        return sum(self._venue_fills_read.values()) >= ledgered - _OVERFILL_TOLERANCE/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            floor = max(state.instruments\[intent.symbol\].ordermin, FLAT_TOLERANCE)$/            floor = FLAT_TOLERANCE/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            restored = \[cid for cid in rows if cid in self._restored_fills\]$/            restored = [cid for cid, (_, row) in rows.items() if cid in self._restored_fills and not self._minted_closed(row)]/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            if attached is None and own and venue_order_id in finished_by_venue:$/            if False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^        if resolve_base(code, bases) == base:$/        if code in (base, f"X{base}") or (base == "BTC" and code in ("XBT", "XXBT")):/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            if row\["client_order_id"\] not in self._restored_fills:$/            if False:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
infra/scripts/mutate-probe.sh --file cli/engine/executor.py --control "$C" \
  --mutation 's/^            if row\["client_order_id"\] not in self._restored_fills:$/            if True:/' \
  -- uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k "$K"
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message with the text below: write the whole message, that line replaced, to a file under `.tmp/` (gitignored) and amend from it with `git commit --amend -F <file>`; the amend changes the message only, no file.

```
Probe: `infra/scripts/mutate-probe.sh` over `cli/engine/executor.py`, control the restored cancel
line respelled so the restored-opener case fails, through `-k "restored or kept_reducer or
finished_row_with_fills or mix_spot or mixed_inventory or margin_position_read or baseline or
cold_starts_order_figure or true_withdrawal or trade_history_read or read_once_per_pass"`: the
venue no longer answering for restored rows, KILLED, control proven; the restored fill no longer
noted for the re-read pass, KILLED, control proven; the pass's repair no longer writing the kept
reducer's intent, KILLED, control proven; the realized baseline no longer read, KILLED, control
proven; the mixed-inventory refusal dropped, KILLED, control proven; the closed restored order's
cancel no longer withheld, KILLED, control proven; the trade history no longer consulted before the
open sweep's trip, KILLED, control proven; the attach at construction dropped, KILLED, control
proven; the restored set read from the open orders alone, KILLED, control proven; the closed rows
dropped from the re-read pass's population, KILLED, control proven; the intent no longer held while
a fill waits for its repair, KILLED, control proven; a failed trade-history read retried in the
pass, KILLED, control proven; the mixed-inventory check widened to every intent, KILLED, control
proven; the pickup's hold dropped, KILLED, control proven; the trade history's cover summed across
txids, KILLED, control proven; the spot floor back at the flat tolerance, KILLED, control proven;
the re-read pass's restored count excluding a row a minted terminal closed, KILLED, control
proven; the stale open copy cancelled at a later restart, KILLED, control proven; the spot balance
read by the removed helper's spellings, KILLED, control proven; the restored fill's WARNING
dropped, KILLED, control proven; the restored fill's WARNING logged at every credit asked,
KILLED, control proven.
```

Run: `git status --porcelain` -- Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` -- Expected: `0`; `git log -1 --format=%B | grep -c 'infra/scripts/mutate-probe.sh'` -- Expected: `1`, the verdict naming the script.

---
### Task 5: The engine role's cache proxy, the rendered config validated before it lands, the two secrets' move, the window guard over `cache-link`, and the rotation's engine leg

This task is spec D1, D2, D15 and the render half of D3: the `cache-proxy` service beside the engine in its compose project, HAProxy digest-pinned with the engine image's three guards, its config rendered from `haproxy.cfg.j2` under `no_log`, validated with the pinned image's own `haproxy -c` and copied into place only then; `engine.env` carrying `ZCRYPTO_CACHE_PASSWORD`, `zcrypto.toml` carrying the cache table enabled; `stop_grace_period: 20s` and `depends_on: cache-proxy` on the engine service; `cache_engine_password` and `cache_sentinel_requirepass` moved verbatim from the cache group's vault to `group_vars/all`'s, with the engine host's own floor on both; the engine window guard's tasks tagged `cache-link` too; `converge.sh` admitting `cache_proxy_image_digest`; and the rotation procedure's engine leg. Nothing here reaches a host: the proxy's first pin and its `fleet-pins.md` row are the rollout's, and the pins guard skips a container that does not exist yet.

What this task decides, where the spec leaves it open:

- The engine role's variables carry the `engine_` prefix ansible-lint holds role defaults to: `engine_cache_proxy_image`, `engine_cache_proxy_image_digest`, `engine_cache_proxy_memory_limit`, `engine_cache_proxy_master_name` and `engine_cache_proxy_nodes`. The converge operand keeps the spec's spelling, `-e cache_proxy_image_digest=`, and the role reads it through the bridge default `engine_cache_proxy_image_digest: "{{ cache_proxy_image_digest | default('') }}"`, so the empty-digest guard refuses a converge that passed none.
- The proxy's backends and master name are the engine role's own defaults, since the engine play loads neither the cache role nor its defaults; `tests/test_infra_cache_proxy.py` holds them equal to the cache_link role's peers and the cache role's `cache_master_name`.
- `timeout client` and `timeout server` are rendered as `24d`, the parser's longest value (spec D1): HAProxy's `-c` warns at every start about a zero as a missing timeout, and the engine writes at least once per four-hour cycle, so the writer's session is never cut by it; the load's connection, idle once the store is read, is the one it closes, at 24 days, which drops no write.
- The validated candidate is copied into place with `ansible.builtin.copy` and `remote_src`, which changes only where the content differs, so the restart handler fires on a changed config and never on a converge that re-rendered the same file; the candidate is rendered every run and removed after the copy. The validation runs the image as root with the candidate mounted at the image's config path, `haproxy -c -f`, under `no_log`, since a refusal quotes the offending line and the `AUTH` line carries the requirepass.
- The two vault blocks move by a script that never prints or decrypts them, the precedent of spec 00054's move: the same vault password serves both files, so the ciphertext moves verbatim; the `all` vault's header counts are updated to fifteen values and ten rendered. The step below runs it and reads the key names alone.
- The cache role's two messages that named `group_vars/cache_host/vault.yml` as the home of every password now name `group_vars/all/vault.yml` for the two moved, and the rotation procedure gains step 6, the engine converge in the same gap, before its confirm-by-value.
- `haproxy -c` against the pinned image was not run while writing this plan (no Docker on the workstation, no 3.4 binary): the template's shape is pinned by the test file below; the plan-review's pin ran it over the image's unpacked layers, rc 0 with `init-state` accepted, and the validation task's first run against the host's Docker is the rollout's preview, since the render and the validate carry `check_mode: false`.
- The proxy's config is rendered, validated, installed and its candidate removed ahead of the engine's env, toml and compose renders, not after them: a refused render then stops before any engine file is rewritten, the file exists before the compose file names it (a bind mount whose source is missing is created as a directory), and the preview -- `converge.sh`'s `--check --diff` -- runs the render and the validation, the two tasks that change nothing an operator reads, while the install waits for the real pass.
- `global` carries `maxconn 256`: without a bound HAProxy sizes itself off the container's file-descriptor hard limit, 524288 on the fleet's containerd, and its worker, about 69 MB resident, is killed under the 32m cap at every load; at 256 it runs and answers `/metrics` under the cap, measured by the plan-review's pin with the 3.4.5 layers under `MemoryMax=32M`.
- The rendered `zcrypto.toml`'s cache table sits behind the role default `engine_cache_enabled: true`, and `-e engine_cache_enabled=false` renders no table -- the way back to an engine that runs without the cache inside the same gap, since an engine image from before the table refuses a config that carries it (`has unknown key(s): cache`) and a compose re-pin alone leaves the rendered file in place; the operand joins `converge.sh`'s `EVKEYS`, and the proxy service renders either way.
- The `cache_link` role takes `when: "'engine' not in ansible_skip_tags"`: `--skip-tags engine`, the Alloy bump's primary shape, skips the window guard's tasks with the engine's, so the role that guard gates is held off there too, and the mesh drift lands at a `--tags cache-link` converge inside a gap, `--tags engine` running the guard and the engine role and not this one. Measured with a two-task play: `--skip-tags engine` runs neither the guard nor the role, `--tags cache-link` and an un-tagged run both, `--tags capture` neither. The mirror, `--tags engine --skip-tags cache-link`, would run the engine role with the guard skipped, measured on a three-task play: `converge.sh` refuses it -- `--tags` and `--skip-tags` together, and `--skip-tags` taking `engine` alone -- so nothing run through the script reaches it, and a bare `ansible-playbook` is the one path that would.

**Files:**
- Create: `infra/ansible/roles/engine/templates/haproxy.cfg.j2`
- Modify: `infra/ansible/roles/engine/templates/compose.yaml.j2` (the engine's `depends_on` and `stop_grace_period`; the `cache-proxy` service)
- Modify: `infra/ansible/roles/engine/templates/engine.env.j2` (`ZCRYPTO_CACHE_PASSWORD`)
- Modify: `infra/ansible/roles/engine/templates/zcrypto.toml.j2` (`[zcrypto.engine.cache]`)
- Modify: `infra/ansible/roles/engine/defaults/main.yml` (the five `engine_cache_proxy_*` defaults and `engine_cache_enabled`)
- Modify: `infra/ansible/roles/engine/tasks/main.yml` (the proxy's three guards and the password floor before the arming backstop; the render, validate, install and remove tasks between the project directory and the env render; the store-delivery assert's re-run message)
- Modify: `infra/README.md` (the engine converge's proxy digest operand)
- Modify: `infra/ansible/site.yml` (the window guard's four tasks tagged `cache-link`; the cache_link role's `when` and comment)
- Modify: `infra/ansible/scripts/converge.sh` (`EVKEYS`, two keys)
- Modify: `infra/ansible/roles/cache/tasks/main.yml` (two messages naming the vault files)
- Modify: `infra/ansible/group_vars/cache_host/vault.yml` and `infra/ansible/group_vars/all/vault.yml` (the two blocks moved, by the script in Step 4)
- Modify: `infra/runbooks/cache.md` (the rotation procedure's two vault homes and its engine leg)
- Test: `tests/test_infra_compose_templates.py` (`ENGINE_CONTEXT`; three cases)
- Test: `tests/test_config.py` (the rendered cache table case, both renders through jinja2)
- Test: `tests/test_infra_converge_guards.py` (the window tags case with the role's `when`; the proxy guards' four cases and the validation order case)
- Test: `tests/test_infra_cache_proxy.py` (new: the rendered config, the defaults against the cache roles', `converge.sh`'s key, the env file's line, the two secrets' home)

**Interfaces:**
- Consumes: `engine_image_digest`'s three guards and `restart engine service` in `roles/engine`; `cache_link_peers` in `roles/cache_link/defaults/main.yml`; `cache_master_name` in `roles/cache/defaults/main.yml`; `cache_engine_password`, `cache_sentinel_requirepass` in `group_vars/all/vault.yml`; `load_tasks`, `find_task`, `truthy`, `assert_that`, `task_index`, `SITE`, `ENGINE`, `WINDOW` in `tests/test_infra_converge_guards.py`; `_render`, `_ENV`, `ENGINE_TEMPLATE` in `tests/test_infra_compose_templates.py`; `_write`, `load_config`, `CacheSettings` in `tests/test_config.py`
- Produces: the `cache-proxy` compose service and `zcrypto-cache-proxy` container; `/opt/zcrypto-engine/haproxy.cfg`; `engine_cache_proxy_image`, `engine_cache_proxy_image_digest`, `engine_cache_proxy_memory_limit`, `engine_cache_proxy_master_name`, `engine_cache_proxy_nodes`, `engine_cache_enabled`; the converge operands `cache_proxy_image_digest` and `engine_cache_enabled`; `ZCRYPTO_CACHE_PASSWORD` in `engine.env`; the `[zcrypto.engine.cache]` table in the rendered `zcrypto.toml`, absent under `engine_cache_enabled=false`

- [ ] **Step 1: Confirm Task 4's marker and this task's absence**

Run: `grep -c '_restored' cli/engine/executor.py; grep -c 'cache-proxy' infra/ansible/roles/engine/templates/compose.yaml.j2; ls infra/ansible/roles/engine/templates/haproxy.cfg.j2 tests/test_infra_cache_proxy.py 2>&1 | grep -c 'No such file'; grep -c '^cache_engine_password: !vault' infra/ansible/group_vars/cache_host/vault.yml infra/ansible/group_vars/all/vault.yml`
Expected: a number above 0, then `0`, then `2`, then `infra/ansible/group_vars/cache_host/vault.yml:1` and `infra/ansible/group_vars/all/vault.yml:0`. A `0` first means Task 4 is not in; `cache-proxy` already in the compose template or the key already in the `all` vault means this task is; stop and report either to the controller.

- [ ] **Step 2: The failing cases**

Create `tests/test_infra_cache_proxy.py` with this content:

```python
"""The cache proxy's rendered config and the fleet's plumbing for it (spec 00120 D1, D2): the
HAProxy template, the engine defaults it reads against the cache roles' values, the extra-var key
`converge.sh` admits, and the engine's env file carrying the cache password under the no_log render."""

import re
from pathlib import Path

import jinja2
import yaml

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra/ansible"
TEMPLATE = ANSIBLE / "roles/engine/templates/haproxy.cfg.j2"
ENGINE_DEFAULTS = yaml.safe_load((ANSIBLE / "roles/engine/defaults/main.yml").read_text())
CACHE_DEFAULTS = yaml.safe_load((ANSIBLE / "roles/cache/defaults/main.yml").read_text())
LINK_DEFAULTS = yaml.safe_load((ANSIBLE / "roles/cache_link/defaults/main.yml").read_text())
REQUIREPASS = "Sentinel12345"
_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)


def _render() -> str:
    context = {
        "engine_cache_proxy_nodes": ENGINE_DEFAULTS["engine_cache_proxy_nodes"],
        "engine_cache_proxy_master_name": ENGINE_DEFAULTS["engine_cache_proxy_master_name"],
        "cache_sentinel_requirepass": REQUIREPASS,
    }
    return _ENV.from_string(TEMPLATE.read_text()).render(**context)


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def test_the_engine_defaults_name_the_cache_roles_nodes_and_master():
    """The engine play loads neither the cache role nor its defaults, so the proxy's node list and the
    Sentinel master name are the engine role's own, held equal to the cache side's here."""
    nodes = ENGINE_DEFAULTS["engine_cache_proxy_nodes"]
    peers = [p["address"] for p in LINK_DEFAULTS["cache_link_peers"] if p["name"].startswith("zcrypto-valkey")]
    assert [n["address"] for n in nodes] == peers == ["10.98.0.11", "10.98.0.12", "10.98.0.13"]
    assert [n["name"] for n in nodes] == ["node1", "node2", "node3"]
    assert ENGINE_DEFAULTS["engine_cache_proxy_master_name"] == CACHE_DEFAULTS["cache_master_name"] == "zcache"
    assert ENGINE_DEFAULTS["engine_cache_proxy_image"] == "haproxy"
    assert ENGINE_DEFAULTS["engine_cache_proxy_image_digest"] == "{{ cache_proxy_image_digest | default('') }}"
    assert ENGINE_DEFAULTS["engine_cache_proxy_memory_limit"] == "32m"


def test_each_backend_checks_every_sentinel_for_its_own_node_and_routes_on_two_of_three():
    lines = _lines(_render())
    for n, address in ((1, "10.98.0.11"), (2, "10.98.0.12"), (3, "10.98.0.13")):
        assert f"use_backend node{n} if {{ nbsrv(node{n}) ge 2 }}" in lines
        servers = [ln for ln in lines if ln.startswith("server ") and f" {address}:6379 " in ln]
        assert len(servers) == 3, servers
        for sentinel in ("10.98.0.11", "10.98.0.12", "10.98.0.13"):
            assert (
                f"server via-node{sentinel[-1]} {address}:6379 check addr {sentinel} port 26379 inter 1s fall 2 rise 2 "
                "init-state fully-down on-marked-down shutdown-sessions"
            ) in servers
    assert lines.count("backend node1") == lines.count("backend node2") == lines.count("backend node3") == 1


def test_the_check_authenticates_pings_and_expects_the_anchored_master_reply_with_no_quit():
    text = _render()
    lines = _lines(text)
    assert lines.count(f'tcp-check send "AUTH {REQUIREPASS}\\r\\n"') == 3
    assert lines.count("tcp-check expect string +OK") == 3 and lines.count("tcp-check expect string +PONG") == 3
    assert lines.count('tcp-check send "SENTINEL master zcache\\r\\n"') == 3
    for address in ("10.98.0.11", "10.98.0.12", "10.98.0.13"):
        assert f'tcp-check expect string "\\$2\\r\\nip\\r\\n\\$10\\r\\n{address}\\r\\n"' in lines
    assert "QUIT" not in text
    # An unescaped `$` inside a double-quoted argument is an environment variable to haproxy -c.
    assert not re.search(r'"[^"]*(?<!\\)\$[^"]*"', text), "an unescaped $ inside a quoted argument"


def test_the_timeouts_the_logging_and_the_metrics_endpoint():
    lines = _lines(_render())
    assert "timeout check 2s" in lines and "timeout connect 2s" in lines
    assert "maxconn 256" in lines  # without it the worker is OOM-killed under the 32m cap at load
    assert "timeout client 24d" in lines and "timeout server 24d" in lines
    assert "log stdout format raw local0 info" in lines
    assert "user haproxy" in lines and "group haproxy" in lines
    assert "bind 0.0.0.0:9104" in lines and "http-request use-service prometheus-exporter if { path /metrics }" in lines
    assert "bind 0.0.0.0:6379" in lines


def test_converge_sh_admits_the_proxy_digest_as_an_extra_var():
    text = (ANSIBLE / "scripts/converge.sh").read_text()
    evkeys = re.search(r'^EVKEYS="([^"]*)"', text, re.M | re.S).group(1).replace("\\\n", " ").split()
    assert "cache_proxy_image_digest" in evkeys


def test_the_engine_env_file_carries_the_cache_password_under_the_no_log_render():
    env = (ANSIBLE / "roles/engine/templates/engine.env.j2").read_text().splitlines()
    assert [ln for ln in env if ln.startswith("ZCRYPTO_CACHE_PASSWORD=")] == ["ZCRYPTO_CACHE_PASSWORD={{ cache_engine_password }}"]
    tasks = yaml.safe_load((ANSIBLE / "roles/engine/tasks/main.yml").read_text())
    render = next(t for t in tasks if t.get("name", "").startswith("render the engine secrets env file"))
    assert render["no_log"] is True and render["diff"] is False and render["ansible.builtin.template"]["mode"] == "0600"


def test_the_two_secrets_the_engine_host_renders_live_in_the_all_groups_vault():
    """Names only, never values: the engine play reads group_vars/all, not the cache group's file."""
    all_keys = re.findall(r"^([a-z_]+): !vault \|", (ANSIBLE / "group_vars/all/vault.yml").read_text(), re.M)
    cache_keys = re.findall(r"^([a-z_]+): !vault \|", (ANSIBLE / "group_vars/cache_host/vault.yml").read_text(), re.M)
    for key in ("cache_engine_password", "cache_sentinel_requirepass"):
        # config-selector-ok: the two lists are the regex's captures of each entry's own key, so membership is exact
        assert key in all_keys and key not in cache_keys, key
    for key in ("cache_replica_password", "cache_sentinel_password", "cache_exporter_password"):
        # config-selector-ok: the same two lists
        assert key in cache_keys and key not in all_keys, key
```

Replace, in `tests/test_infra_compose_templates.py`, this block:

```python
    "engine_log_max_size": "50m",
    "engine_log_max_file": "5",
}

```

with:

```python
    "engine_log_max_size": "50m",
    "engine_log_max_file": "5",
    "engine_cache_proxy_image": "haproxy",
    "engine_cache_proxy_image_digest": "sha256:" + "c" * 64,
    "engine_cache_proxy_memory_limit": "32m",
}

```

Replace, in `tests/test_infra_compose_templates.py`, this block:

```python


def test_engine_logship_guard_moves_environment_and_entrypoint_together():
    # The riskiest edit this test guards: `environment:` un-nested out of the
```

with:

```python


def test_the_cache_proxy_service_is_pinned_by_digest_root_at_start_with_its_config_read_only_and_its_metrics_on_loopback():
    service = _render(ENGINE_TEMPLATE, ENGINE_CONTEXT)["services"]["cache-proxy"]
    assert service["image"] == "haproxy@sha256:" + "c" * 64
    assert (service["container_name"], service["restart"], service["user"]) == ("zcrypto-cache-proxy", "unless-stopped", "0:0")
    assert service["volumes"] == ["/opt/zcrypto-engine/haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro"]
    assert service["ports"] == ["127.0.0.1:9104:9104"]
    assert service["deploy"]["resources"]["limits"] == {"memory": "32m"}
    assert service["logging"]["driver"] == "json-file"


def test_the_engine_waits_for_the_proxy_to_start_and_stops_inside_twenty_seconds():
    service = _render(ENGINE_TEMPLATE, ENGINE_CONTEXT)["services"]["engine"]
    assert service["depends_on"] == {"cache-proxy": {"condition": "service_started"}}
    assert service["stop_grace_period"] == "20s"


def test_the_engine_compose_file_carries_neither_cache_secret():
    """The passwords reach the host through engine.env and haproxy.cfg, both 0600 and never diffed;
    the compose file stays diffable, so a render handed both values must not carry either."""
    context = {**ENGINE_CONTEXT, "cache_engine_password": "EnginePw12345", "cache_sentinel_requirepass": "SentinelPw12345"}
    rendered = _ENV.from_string(ENGINE_TEMPLATE.read_text()).render(**context)
    assert "EnginePw12345" not in rendered and "SentinelPw12345" not in rendered


def test_engine_logship_guard_moves_environment_and_entrypoint_together():
    # The riskiest edit this test guards: `environment:` un-nested out of the
```

Replace, in `tests/test_config.py`, this block:

```python


def test_committed_zcrypto_toml_has_no_engine_table():
    # EngineConfig's defaults live in code; the committed zcrypto.toml carries no engine table to shadow them.
```

with:

```python


@pytest.mark.parametrize("switch", [True, False], ids=["enabled-by-default", "off-by-the-operand"])
def test_the_engine_role_template_renders_the_cache_table_enabled_at_the_proxys_address_unless_switched_off(tmp_path, switch):
    """The rendered engine config enables the cache from the first boot, every value explicit, and
    the loader reads it back as the settings the node builds from; no password is in the file. With
    `-e engine_cache_enabled=false` the table is not rendered at all -- the way back to an engine
    without the cache, on an image from before the table as on this one."""
    import jinja2

    text = Path("infra/ansible/roles/engine/templates/zcrypto.toml.j2").read_text()
    defaults = yaml.safe_load(Path("infra/ansible/roles/engine/defaults/main.yml").read_text())
    assert defaults["engine_cache_enabled"] is True
    values = {
        "engine_state_dir": "/var/lib/zcrypto-engine",
        "engine_exec_max_plan_notional_eur": "100.0",
        "engine_shadow_nav_eur": "1000.0",
        "engine_settle_delay_secs": "90",
        "engine_cache_enabled": "true" if switch else "false",  # `-e k=v` hands the role a string
    }
    env = jinja2.Environment(trim_blocks=True, undefined=jinja2.StrictUndefined)
    env.filters["bool"] = lambda value: str(value).lower() in ("true", "1", "yes")  # Ansible's own filter, absent from jinja2
    rendered = env.from_string(text).render(**values)
    assert "password" not in rendered.lower().replace("the password is zcrypto_cache_password in engine.env, never here.", "")
    cfg = load_config(_write(tmp_path, rendered))
    assert cfg.engine.cache == (
        CacheSettings(enabled=True, host="cache-proxy", port=6379, username="engine") if switch else CacheSettings()
    )
    assert ("[zcrypto.engine.cache]" in rendered) is switch
    assert [ln.strip() for ln in text.splitlines() if ln.strip() in ("enabled = true", "port = 6379")] == [
        "enabled = true",
        "port = 6379",
    ]


def test_committed_zcrypto_toml_has_no_engine_table():
    # EngineConfig's defaults live in code; the committed zcrypto.toml carries no engine table to shadow them.
```

Replace, in `tests/test_infra_converge_guards.py`, this block:

```python

SITE = ANSIBLE / "site.yml"


```

with:

```python

SITE = ANSIBLE / "site.yml"


def test_every_engine_window_guard_task_also_gates_a_cache_link_converge():
    """spec 00120 D2: the cache-link handler restarts wg-quick@zcache0, which cuts the engine's cache
    session as a failover does, so the window guard's probes, refusal and echo carry both tags."""
    play = next(p for p in load_tasks(SITE) if p.get("hosts") == "engine_host")
    guarded = [t["name"] for t in play["pre_tasks"] if "engine" in t.get("tags", [])]
    assert WINDOW in guarded and len(guarded) >= 4, guarded
    assert all("cache-link" in t.get("tags", []) for t in play["pre_tasks"] if t["name"] in guarded), [
        (t["name"], t.get("tags")) for t in play["pre_tasks"] if t["name"] in guarded
    ]
    # `--skip-tags engine` skips those tasks with the engine's, so the role they gate is held off there
    # too: an Alloy bump's primary shape converges the mesh interface at no hour otherwise.
    link = next(r for r in play["roles"] if r.get("role") == "cache_link")
    assert not truthy(when_conditions(link), {"ansible_run_tags": ["all"], "ansible_skip_tags": ["engine"]})
    assert truthy(when_conditions(link), {"ansible_run_tags": ["all"], "ansible_skip_tags": []})
    assert truthy(when_conditions(link), {"ansible_run_tags": ["cache-link"], "ansible_skip_tags": []})


```

Replace, in `tests/test_infra_converge_guards.py`, this block:

```python
    # THE BITE, against the real files: drop the pinned version and the guard must refuse again.
    assert not truthy(assert_that(task), _arming_derived({**base, "engine_verified_nautilus": [v for v in versions if v != pin]}))


```

with:

```python
    # THE BITE, against the real files: drop the pinned version and the guard must refuse again.
    assert not truthy(assert_that(task), _arming_derived({**base, "engine_verified_nautilus": [v for v in versions if v != pin]}))


# --- the cache proxy's guards (spec 00120 D1, D2): the engine image's three, mirrored for the proxy
# under their own probe names, and the password floor on the two secrets the engine host renders.
PROXY_PINS_BASE = {"engine_cache_proxy_running_probe": {"stdout": "haproxy@sha256:" + "a" * 64}}
PROXY_PINS_WITH = "| cache-proxy | zcrypto | `" + "a" * 12 + "` | 2026-10-02 | first pin |"
PROXY_PINS_WITHOUT = "| cache-proxy | zcrypto | `" + "b" * 12 + "` | 2026-10-02 | first pin |"


def test_the_cache_proxy_digest_is_refused_empty_and_refused_unpulled():
    empty = find_task(load_tasks(ENGINE), "fail fast if the pinned cache proxy image digest was not supplied")
    assert not truthy(assert_that(empty), {"engine_cache_proxy_image_digest": ""})
    assert truthy(assert_that(empty), {"engine_cache_proxy_image_digest": "sha256:" + "c" * 64})
    unpulled = find_task(load_tasks(ENGINE), "preflight — refuse a cache proxy digest the host has not pulled")
    assert not truthy(assert_that(unpulled), {"engine_cache_proxy_digest_probe": {"rc": 1}})
    assert truthy(assert_that(unpulled), {"engine_cache_proxy_digest_probe": {"rc": 0}})


@pytest.mark.parametrize(
    ("pins_text", "override", "expected"),
    [
        (PROXY_PINS_WITH, "", True),
        (PROXY_PINS_WITHOUT, "", False),
        (PROXY_PINS_WITHOUT, "true", False),
        (PROXY_PINS_WITHOUT, "emergency: pins file unreachable, recorded after", True),
    ],
)
def test_cache_proxy_pins_recording_semantics(pins_text, override, expected):
    task = find_task(load_tasks(ENGINE), "cache proxy pins recording — refuse to replace a digest fleet-pins.md does not record")
    variables = {**PROXY_PINS_BASE, "engine_cache_proxy_pins_text": pins_text, "pins_override": override}
    assert truthy(assert_that(task), variables) is expected
    assert "engine_cache_proxy_running_probe.rc == 0" in task["when"]


@pytest.mark.parametrize(
    ("engine_password", "requirepass", "expected"),
    [
        ("Engine12345", "Sentinel12345", True),
        ("Eng1", "Sentinel12345", False),  # under the floor
        ("Engine12345", "Sentinel 12345", False),  # a space splits the check line
        ("Engine12345", 'Sentinel"12345', False),  # a quote ends the check line
    ],
)
def test_the_engine_host_refuses_a_cache_password_below_the_floor_or_outside_letters_and_digits(
    engine_password, requirepass, expected
):
    task = find_task(
        load_tasks(ENGINE), "refuse a cache password shorter than five characters or outside letters and digits (the engine's two)"
    )
    variables = {"cache_engine_password": engine_password, "cache_sentinel_requirepass": requirepass}
    assert truthy(assert_that(task), variables) is expected


def test_the_cache_proxy_config_is_validated_before_it_is_installed_and_never_logged():
    """The order is the property: render to the candidate, validate with the pinned image's own
    `haproxy -c`, copy into place with the restart notify, remove the candidate, all four ahead of
    the engine's env, toml and compose renders -- so a refused render stops before any engine file
    is rewritten, and the config exists before a compose file names it; the render and the validate
    run in check mode too, so the preview is the validation's first run. The render and the copy
    under no_log with no diff, since the file carries the Sentinel requirepass."""
    tasks = load_tasks(ENGINE)
    names = [
        "render the cache proxy config beside its live copy (0600 root-only; never logged, never diffed)",
        "validate the rendered cache proxy config with the pinned image's own haproxy -c",
        "install the validated cache proxy config (changed only where it differs from the live copy)",
        "remove the validated candidate",
    ]
    indexes = [task_index(tasks, name) for name in names]
    assert indexes == sorted(indexes) and indexes[-1] - indexes[0] == 3, indexes
    assert task_index(tasks, "ensure the compose project directory exists") < indexes[0]
    assert indexes[-1] < task_index(tasks, "render the engine secrets env file (0600 root-only; never logged, never diffed)")
    render, validate, install, remove = (find_task(tasks, name) for name in names)
    assert render["ansible.builtin.template"]["dest"] == "/opt/zcrypto-engine/haproxy.cfg.next"
    assert render["ansible.builtin.template"]["mode"] == "0600" and render["no_log"] is True and render["diff"] is False
    assert "notify" not in render and render["check_mode"] is False
    command = " ".join(validate["ansible.builtin.command"].split())
    assert "haproxy.cfg.next:/usr/local/etc/haproxy/haproxy.cfg:ro" in command
    assert command.endswith("haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg") and validate["no_log"] is True
    assert "{{ engine_cache_proxy_image }}@{{ engine_cache_proxy_image_digest }}" in command
    assert validate["check_mode"] is False and "when" not in validate and remove["check_mode"] is False
    copy = install["ansible.builtin.copy"]
    assert (copy["src"], copy["dest"], copy["remote_src"], copy["mode"]) == (
        "/opt/zcrypto-engine/haproxy.cfg.next",
        "/opt/zcrypto-engine/haproxy.cfg",
        True,
        "0600",
    )
    assert install["notify"] == "restart engine service" and install["no_log"] is True and install["diff"] is False
    assert remove["ansible.builtin.file"] == {"path": "/opt/zcrypto-engine/haproxy.cfg.next", "state": "absent"}


```

- [ ] **Step 3: Run the four files and watch the new cases fail**

Run: `uv run pytest tests/test_infra_cache_proxy.py tests/test_infra_compose_templates.py tests/test_config.py tests/test_infra_converge_guards.py -q -p no:cacheprovider`
Expected: `22 failed, 447 passed` -- the seven cases of the new file (the template absent, the defaults absent, the key absent, the env line absent, the secrets in the cache group's vault), the two compose cases, the rendered cache table's two renders, the window tags case and the ten proxy-guard cases; the compose file's secret-free case passes on both trees.

- [ ] **Step 4: The proxy template, the role, the play, the converge script, the cache role's messages, the vault move and the rotation leg**

Create `infra/ansible/roles/engine/templates/haproxy.cfg.j2` with this content:

```jinja
# Rendered by the `engine` Ansible role at /opt/zcrypto-engine/haproxy.cfg (0600 root-only, bind-mounted
# read-only into zcrypto-cache-proxy) -- do not hand-edit on the host, it is overwritten on the next
# converge. It carries the Sentinel requirepass, so the role renders it under no_log, never diffs it, and
# validates the render with the pinned image's own `haproxy -c` before moving it into place.
global
    log stdout format raw local0 info
    # Without a bound HAProxy sizes itself off the container's file-descriptor hard limit -- 524288 on
    # the fleet's containerd, a worker of about 69 MB resident, killed under the 32m cap at load. At 256
    # it runs and answers /metrics under the cap; the engine's sessions and nine checks need a handful.
    maxconn 256
    # The container starts as root so this 0600 file is readable; the workers drop to the image's user.
    user haproxy
    group haproxy

defaults
    mode tcp
    log global
    option tcplog
    timeout connect 2s
    # The library's session idles for hours between writes and reconnects only on the next write, which
    # it drops, so an idle cut would cost a write per idle period: the parser's longest value, which a
    # zero would not be -- a zero is a "missing" timeout, warned about at every start.
    timeout client 24d
    timeout server 24d
    # A mismatched Sentinel reply is not detected as wrong but waited for until this timeout.
    timeout check 2s

frontend metrics
    mode http
    bind 0.0.0.0:9104
    no log
    http-request use-service prometheus-exporter if { path /metrics }

frontend cache
    bind 0.0.0.0:6379
{% for node in engine_cache_proxy_nodes %}
    use_backend {{ node.name }} if { nbsrv({{ node.name }}) ge 2 }
{% endfor %}

{% for node in engine_cache_proxy_nodes %}
# {{ node.name }} routes to {{ node.address }} while two of the three Sentinels name it the primary: one
# server line per Sentinel, each checking that Sentinel and passing only when its answer names this node.
backend {{ node.name }}
    option tcp-check
    tcp-check connect
    tcp-check send "AUTH {{ cache_sentinel_requirepass }}\r\n"
    tcp-check expect string +OK
    tcp-check send "PING\r\n"
    tcp-check expect string +PONG
    tcp-check send "SENTINEL master {{ engine_cache_proxy_master_name }}\r\n"
    tcp-check expect string "\$2\r\nip\r\n\${{ node.address | length }}\r\n{{ node.address }}\r\n"
{% for sentinel in engine_cache_proxy_nodes %}
    server via-{{ sentinel.name }} {{ node.address }}:6379 check addr {{ sentinel.address }} port 26379 inter 1s fall 2 rise 2 init-state fully-down on-marked-down shutdown-sessions
{% endfor %}

{% endfor %}
```

Replace, in `infra/ansible/roles/engine/templates/compose.yaml.j2`, this block:

```yaml
    restart: unless-stopped
    user: "{{ engine_uid }}:{{ engine_gid }}"
{% if logship_loki_token is defined %}
    # --ship-logs is spelled out here, not left to the image's own shell-ENTRYPOINT conveyance
```

with:

```yaml
    restart: unless-stopped
    user: "{{ engine_uid }}:{{ engine_gid }}"
    # The proxy is started first and nothing more (spec 00120 D1): the engine's own retry budget on
    # the cache backing is the start-order guard, ten retries under five-second timeouts.
    depends_on:
      cache-proxy:
        condition: service_started
    # nautilus_live waits ten seconds for residual events before it disconnects its clients, and
    # Docker's default grace is ten, so every stop was a force-kill (spec 00120 D15).
    stop_grace_period: 20s
{% if logship_loki_token is defined %}
    # --ship-logs is spelled out here, not left to the image's own shell-ENTRYPOINT conveyance
```

Replace, in `infra/ansible/roles/engine/templates/compose.yaml.j2`, this block:

```yaml
        max-size: "{{ engine_log_max_size }}"
        max-file: "{{ engine_log_max_file }}"
```

with:

```yaml
        max-size: "{{ engine_log_max_size }}"
        max-file: "{{ engine_log_max_file }}"

  # The engine's route to the cache set (spec 00120 D1): HAProxy, digest-pinned, routing 6379 to the
  # node two of the three Sentinels name the primary, its config a root-owned 0600 file the role
  # validates before it lands here. Its stdout reaches the unit's journal beside the engine's, and the
  # Prometheus endpoint is published on loopback for the host's Alloy.
  cache-proxy:
    image: "{{ engine_cache_proxy_image }}@{{ engine_cache_proxy_image_digest }}"
    container_name: zcrypto-cache-proxy
    restart: unless-stopped
    # Root at start so the 0600 config is readable; the config's global section drops the workers to
    # the image's haproxy user.
    user: "0:0"
    volumes:
      - "/opt/zcrypto-engine/haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro"
    ports:
      - "127.0.0.1:9104:9104"
    deploy:
      resources:
        limits:
          memory: "{{ engine_cache_proxy_memory_limit }}"
    logging:
      driver: json-file
      options:
        max-size: "{{ engine_log_max_size }}"
        max-file: "{{ engine_log_max_file }}"
```

Replace, in `infra/ansible/roles/engine/templates/engine.env.j2`, this block:

```jinja
KRAKEN_SPOT_API_KEY={{ kraken_trade_api_key }}
KRAKEN_SPOT_API_SECRET={{ kraken_trade_api_secret }}
HEALTHCHECK_URL={{ engine_healthcheck_url }}
ZCRYPTO_REQUIRE_CONFIG=1
```

with:

```jinja
KRAKEN_SPOT_API_KEY={{ kraken_trade_api_key }}
KRAKEN_SPOT_API_SECRET={{ kraken_trade_api_secret }}
ZCRYPTO_CACHE_PASSWORD={{ cache_engine_password }}
HEALTHCHECK_URL={{ engine_healthcheck_url }}
ZCRYPTO_REQUIRE_CONFIG=1
```

Replace, in `infra/ansible/roles/engine/templates/zcrypto.toml.j2`, this block:

```toml
shadow_nav_eur = {{ engine_shadow_nav_eur }}
settle_delay_secs = {{ engine_settle_delay_secs }}
```

with:

```toml
shadow_nav_eur = {{ engine_shadow_nav_eur }}
settle_delay_secs = {{ engine_settle_delay_secs }}

{% if engine_cache_enabled | bool %}
# The engine's cache (spec 00120 D3): enabled from the first boot, every value explicit so a converge
# diff shows it. The password is ZCRYPTO_CACHE_PASSWORD in engine.env, never here. The whole table
# goes with -e engine_cache_enabled=false, the way back to an engine that runs without the cache: an
# image from before the table refuses a config that carries it.
[zcrypto.engine.cache]
enabled = true
host = "cache-proxy"
port = 6379
username = "engine"
{% endif %}
```

Replace, in `infra/ansible/roles/engine/defaults/main.yml`, this block:

```yaml
engine_log_max_file: "5"

# healthchecks.io ping URL for the dead-man's switch — vault-supplied (the attended deployment
# vaults it as engine_healthcheck_url); empty means the engine simply skips liveness pings.
```

with:

```yaml
engine_log_max_file: "5"

# The cache proxy beside the engine (spec 00120 D1): the official haproxy image, digest-pinned per run
# with no default, pre-staged on the host first; the pin's row in docs/reference/fleet-pins.md is
# `cache-proxy` on `zcrypto`:
#   -e cache_proxy_image_digest=sha256:<...>   (read it with `docker buildx imagetools inspect haproxy:<version>`)
# HAProxy 3.1 or later: `init-state` on the server lines is a keyword of that release. The operand keeps
# the fleet's spelling, `cache_proxy_image_digest`; the role reads it through its own prefixed name.
engine_cache_proxy_image: haproxy
engine_cache_proxy_image_digest: "{{ cache_proxy_image_digest | default('') }}"
engine_cache_proxy_memory_limit: "32m"
# The rendered zcrypto.toml carries the [zcrypto.engine.cache] table, enabled, unless a converge passes
# `-e engine_cache_enabled=false`: the way back to an engine that runs without the cache inside the same
# gap, since an engine image from before the table refuses a config that carries it; past the gap the
# same value is committed in host_vars/zcrypto/vars.yml, since the next engine converge reads this
# default again. The proxy service renders either way.
engine_cache_enabled: true
# The set's Sentinel master name and the three cache nodes on the zcache mesh, one backend each: the
# cache role's `cache_master_name` and the cache_link role's peers, neither loaded in the engine play,
# which tests/test_infra_cache_proxy.py holds equal.
engine_cache_proxy_master_name: zcache
engine_cache_proxy_nodes:
  - {name: node1, address: 10.98.0.11}
  - {name: node2, address: 10.98.0.12}
  - {name: node3, address: 10.98.0.13}

# healthchecks.io ping URL for the dead-man's switch — vault-supplied (the attended deployment
# vaults it as engine_healthcheck_url); empty means the engine simply skips liveness pings.
```

Replace, in `infra/ansible/roles/engine/tasks/main.yml`, this block:

```yaml
    and (pins_override | default('') | string | lower not in ['true', 'false', '1', 'yes'])

# The arming backstop: a machine check at the only moment that matters, the converge that would
# actually arm the engine. Until it existed, arming on a nautilus version whose attended order-
```

with:

```yaml
    and (pins_override | default('') | string | lower not in ['true', 'false', '1', 'yes'])

# spec 00120 D1: the cache proxy's image, guarded as the engine's is -- non-empty, pre-staged, the
# replaced running digest recorded -- and without the canary parity, which is scoped to the engine
# image: there is no capture bake of an upstream proxy image.
- name: fail fast if the pinned cache proxy image digest was not supplied
  ansible.builtin.assert:
    that: engine_cache_proxy_image_digest | length > 0
    fail_msg: >-
      engine_cache_proxy_image_digest is empty — pass the haproxy index digest docs/reference/fleet-pins.md
      records for cache-proxy on this host, e.g. -e cache_proxy_image_digest=sha256:<...> (read it
      with `docker buildx imagetools inspect haproxy:<version>`), pre-staged on this host.

- name: probe — is the pinned cache proxy digest already on this host
  ansible.builtin.command: docker image inspect "{{ engine_cache_proxy_image }}@{{ engine_cache_proxy_image_digest }}"
  register: engine_cache_proxy_digest_probe
  failed_when: false
  changed_when: false
  check_mode: false

- name: preflight — refuse a cache proxy digest the host has not pulled
  ansible.builtin.assert:
    that: engine_cache_proxy_digest_probe.rc == 0
    fail_msg: >-
      {{ engine_cache_proxy_image }}@{{ engine_cache_proxy_image_digest }} is not on {{ inventory_hostname }} — the
      unit's ExecStartPre pulls at start, and the stop→start window must hold no registry pull.
      Pre-stage it first: sudo docker pull {{ engine_cache_proxy_image }}@{{ engine_cache_proxy_image_digest }}

- name: probe — the currently-running cache proxy digest this converge would replace (pins recording)
  ansible.builtin.command: docker inspect --format '{{ "{{" }}.Config.Image{{ "}}" }}' zcrypto-cache-proxy
  register: engine_cache_proxy_running_probe
  failed_when: false
  changed_when: false
  check_mode: false

- name: read fleet-pins.md from the controller tree (cache proxy)
  ansible.builtin.set_fact:
    engine_cache_proxy_pins_text: "{{ lookup('file', playbook_dir ~ '/../../docs/reference/fleet-pins.md') }}"
  when: engine_cache_proxy_running_probe.rc == 0

- name: cache proxy pins recording — refuse to replace a digest fleet-pins.md does not record
  ansible.builtin.assert:
    that: >-
      ((engine_cache_proxy_running_probe.stdout | default('') | regex_search('sha256:[0-9a-f]{12}') | default('') | replace('sha256:', '')) in engine_cache_proxy_pins_text)
      or ((pins_override | default('') | string | length > 8)
          and (pins_override | default('') | string | lower not in ['true', 'false', '1', 'yes']))
    fail_msg: >-
      The cache proxy digest this converge replaces ({{ engine_cache_proxy_running_probe.stdout }}) is
      not recorded in docs/reference/fleet-pins.md — an unrecorded pin is one docker-prune from an
      unrecoverable rollback. Record the CURRENT digest there first (or pass -e '{"pins_override":
      "<reason>"}' and record it immediately after).
  when: engine_cache_proxy_running_probe.rc == 0 and engine_cache_proxy_pins_text is defined

# The two cache secrets this role renders (spec 00120 D2): the engine's password into engine.env and
# the Sentinel requirepass into the proxy's check line, both unquoted, so the cache role's floor holds
# here too -- five or more letters and digits.
- name: refuse a cache password shorter than five characters or outside letters and digits (the engine's two)
  ansible.builtin.assert:
    that: >-
      [cache_engine_password, cache_sentinel_requirepass] | reject('match', '[A-Za-z0-9]{5,}\Z') | list | length == 0
    fail_msg: >-
      {{ ['cache_engine_password', 'cache_sentinel_requirepass'] | zip([cache_engine_password, cache_sentinel_requirepass]) | rejectattr('1', 'match', '[A-Za-z0-9]{5,}\Z') | map('first') | join(', ') }}
      in group_vars/all/vault.yml must be five or more letters and digits. Re-generate it with
      `openssl rand -hex 24 | tr -d '\n' | uv run ansible-vault encrypt_string --stdin-name <key>` and replace its entry.

# The arming backstop: a machine check at the only moment that matters, the converge that would
# actually arm the engine. Until it existed, arming on a nautilus version whose attended order-
```

Replace, in `infra/ansible/roles/engine/tasks/main.yml`, this block:

```yaml
      purged with it), and re-run this converge with --tags engine, -e converge_primary=true and
      -e engine_image_digest=sha256:<full digest>, inside the inter-cycle gap and outside a published
```

with:

```yaml
      purged with it), and re-run this converge with --tags engine, -e converge_primary=true,
      -e engine_image_digest=sha256:<full digest> and -e cache_proxy_image_digest=sha256:<the running
      proxy digest>, inside the inter-cycle gap and outside a published
```

Replace, in `infra/README.md`, this block:

```
./scripts/run.sh site.yml --tags engine -e converge_primary=true -e engine_image_digest=sha256:<...>
```

with:

```
./scripts/run.sh site.yml --tags engine -e converge_primary=true -e engine_image_digest=sha256:<...> -e cache_proxy_image_digest=sha256:<...>
```

Replace, in `infra/ansible/roles/engine/tasks/main.yml`, this block:

```yaml
- name: ensure the compose project directory exists
  ansible.builtin.file:
    path: /opt/zcrypto-engine
    state: directory
    owner: root
    group: root
    mode: "0755"

- name: render the engine secrets env file (0600 root-only; never logged, never diffed)
```

with:

```yaml
- name: ensure the compose project directory exists
  ansible.builtin.file:
    path: /opt/zcrypto-engine
    state: directory
    owner: root
    group: root
    mode: "0755"

# --- 5a. The cache proxy's config (spec 00120 D1), ahead of the engine's own three files: rendered
# beside the live copy, validated by the pinned image's own `haproxy -c`, and copied into place only
# then, so an invalid render never sits where the unit's next start would read it, a refused render
# stops before engine.env, zcrypto.toml or compose.yaml is rewritten, and the file exists before the
# compose file below names it -- a bind mount whose source is missing is created as a directory. The
# render and the validate run in check mode too (the candidate is 0600 under no_log; `docker run --rm
# ... -c` changes nothing), so converge.sh's preview is the validation's first run. It carries the
# Sentinel requirepass: no_log, never diffed, 0600. The copy is what changes when the render differs,
# and only then does the unit restart.
- name: render the cache proxy config beside its live copy (0600 root-only; never logged, never diffed)
  ansible.builtin.template:
    src: haproxy.cfg.j2
    dest: /opt/zcrypto-engine/haproxy.cfg.next
    owner: root
    group: root
    mode: "0600"
  no_log: true
  diff: false
  check_mode: false

- name: validate the rendered cache proxy config with the pinned image's own haproxy -c
  ansible.builtin.command: >-
    docker run --rm --user 0:0
    -v /opt/zcrypto-engine/haproxy.cfg.next:/usr/local/etc/haproxy/haproxy.cfg:ro
    {{ engine_cache_proxy_image }}@{{ engine_cache_proxy_image_digest }}
    haproxy -c -f /usr/local/etc/haproxy/haproxy.cfg
  changed_when: false
  no_log: true
  check_mode: false

- name: install the validated cache proxy config (changed only where it differs from the live copy)
  ansible.builtin.copy:
    src: /opt/zcrypto-engine/haproxy.cfg.next
    dest: /opt/zcrypto-engine/haproxy.cfg
    remote_src: true
    owner: root
    group: root
    mode: "0600"
  no_log: true
  diff: false
  notify: restart engine service
  when: not ansible_check_mode

- name: remove the validated candidate
  ansible.builtin.file:
    path: /opt/zcrypto-engine/haproxy.cfg.next
    state: absent
  changed_when: false
  check_mode: false

- name: render the engine secrets env file (0600 root-only; never logged, never diffed)
```

Replace, in `infra/ansible/site.yml`, this block:

```yaml
      check_mode: false
      when: not ansible_check_mode
      tags: [engine]  # I2: NOT always — a --tags capture primary run must not be window-blocked; guard 4 covers untagged runs

    # spec 00083 D6: when the boundary's cycle already completed, the fixed B+30 floor protects a
```

with:

```yaml
      check_mode: false
      when: not ansible_check_mode
      # I2: NOT always — a --tags capture primary run must not be window-blocked; guard 4 covers untagged
      # runs. cache-link too (spec 00120 D2): its handler restarts wg-quick@zcache0 on any change, which
      # cuts the engine's cache session as a failover does.
      tags: [engine, cache-link]

    # spec 00083 D6: when the boundary's cycle already completed, the fixed B+30 floor protects a
```

Replace, in `infra/ansible/site.yml`, this block:

```yaml
      check_mode: false
      when: not ansible_check_mode
      tags: [engine]

    # The close stands a play's work above the deploy-log audit's `_BEFORE_BOUNDARY_SECONDS`,
```

with:

```yaml
      check_mode: false
      when: not ansible_check_mode
      tags: [engine, cache-link]

    # The close stands a play's work above the deploy-log audit's `_BEFORE_BOUNDARY_SECONDS`,
```

Replace, in `infra/ansible/site.yml`, this block:

```yaml
          -e '{"engine_window_override": "<why this cannot wait>"}' (a reason, not a boolean).
      when: not ansible_check_mode and engine_epoch_probe.stdout is defined
      tags: [engine]

    # The window condition is mirrored here character-for-character. A folded scalar keeps both the
```

with:

```yaml
          -e '{"engine_window_override": "<why this cannot wait>"}' (a reason, not a boolean).
      when: not ansible_check_mode and engine_epoch_probe.stdout is defined
      tags: [engine, cache-link]

    # The window condition is mirrored here character-for-character. A folded scalar keeps both the
```

Replace, in `infra/ansible/site.yml`, this block:

```yaml
        and (engine_window_override | default('') | string | length > 8)
        and (engine_window_override | default('') | string | lower not in ['true', 'false', '1', 'yes'])
      tags: [engine]
  roles:
    # The engine host's end of the zcache mesh, under its own tag. It restarts no container, and a
    # changed zcache0.conf restarts wg-quick@zcache0, which carries no engine traffic until the engine
    # half routes the cache through it, so it takes no engine window yet. The capture play's
    # converge_primary guard still gates it, and `--skip-tags engine` runs it too.
    - role: cache_link
      tags: [cache-link]
```

with:

```yaml
        and (engine_window_override | default('') | string | length > 8)
        and (engine_window_override | default('') | string | lower not in ['true', 'false', '1', 'yes'])
      tags: [engine, cache-link]
  roles:
    # The engine host's end of the zcache mesh, under its own tag. It restarts no container, and a
    # changed zcache0.conf restarts wg-quick@zcache0, which carries the engine's cache traffic, so it
    # takes the engine window above. The capture play's converge_primary guard still gates it. A
    # `--skip-tags engine` run skips the guard's tasks with the engine's, so it skips this role too:
    # the mesh drift lands at a `--tags cache-link` converge inside a gap.
    - role: cache_link
      tags: [cache-link]
      when: "'engine' not in ansible_skip_tags"
```

Replace, in `infra/ansible/scripts/converge.sh`, this block:

```bash
# `daemon_json_ack` and `ops_panel_timer_hold` (the rollout skill), `ops_reconcile_mint` (the ops
# host_vars), `docker_apt_distribution` and `access_ops_agentboard_live` (their role defaults); plus
# spec 00118's three: the cache role's two digests and its deliberate config re-render (D9).
EVKEYS="capture_image_digest capture_alloy_digest engine_image_digest converge_primary \
ops_image_digest ops_alloy_digest ops_panel_timer_hold ops_grafana_watchdog_probe_url \
ops_reconcile_mint liquidations_decision nas_apply_compose daemon_json_ack \
docker_apt_distribution access_ops_agentboard_live cache_image_digest cache_alloy_digest \
cache_config_reset"
# A reason is prose, and `k=v` truncates it at the first space, so these four travel as JSON alone.
OVERRIDES="canary_override pins_override engine_window_override arming_override"
```

with:

```bash
# `daemon_json_ack` and `ops_panel_timer_hold` (the rollout skill), `ops_reconcile_mint` (the ops
# host_vars), `docker_apt_distribution` and `access_ops_agentboard_live` (their role defaults); plus
# spec 00118's three: the cache role's two digests and its deliberate config re-render (D9); spec
# 00120's two: the engine host's cache proxy digest, and the cache table's switch, the way back.
EVKEYS="capture_image_digest capture_alloy_digest engine_image_digest converge_primary \
ops_image_digest ops_alloy_digest ops_panel_timer_hold ops_grafana_watchdog_probe_url \
ops_reconcile_mint liquidations_decision nas_apply_compose daemon_json_ack \
docker_apt_distribution access_ops_agentboard_live cache_image_digest cache_alloy_digest \
cache_config_reset cache_proxy_image_digest engine_cache_enabled"
# A reason is prose, and `k=v` truncates it at the first space, so these four travel as JSON alone.
OVERRIDES="canary_override pins_override engine_window_override arming_override"
```

Replace, in `infra/ansible/roles/cache/tasks/main.yml`, this block:

```yaml
        fail_msg: >-
          {{ ['cache_engine_password', 'cache_replica_password', 'cache_sentinel_password', 'cache_sentinel_requirepass', 'cache_exporter_password'] | zip([cache_engine_password, cache_replica_password, cache_sentinel_password, cache_sentinel_requirepass, cache_exporter_password]) | rejectattr('1', 'match', '[A-Za-z0-9]{5,}\Z') | map('first') | join(', ') }}
          in group_vars/cache_host/vault.yml must be five or more letters and digits. Re-generate it with
          `openssl rand -hex 24 | tr -d '\n' | uv run ansible-vault encrypt_string --stdin-name <key>` and replace its entry.

```

with:

```yaml
        fail_msg: >-
          {{ ['cache_engine_password', 'cache_replica_password', 'cache_sentinel_password', 'cache_sentinel_requirepass', 'cache_exporter_password'] | zip([cache_engine_password, cache_replica_password, cache_sentinel_password, cache_sentinel_requirepass, cache_exporter_password]) | rejectattr('1', 'match', '[A-Za-z0-9]{5,}\Z') | map('first') | join(', ') }}
          in group_vars/cache_host/vault.yml (cache_engine_password and cache_sentinel_requirepass: group_vars/all/vault.yml,
          the engine play's read) must be five or more letters and digits. Re-generate it with
          `openssl rand -hex 24 | tr -d '\n' | uv run ansible-vault encrypt_string --stdin-name <key>` and replace its entry.

```

Replace, in `infra/ansible/roles/cache/tasks/main.yml`, this block:

```yaml
          node is the daemon's and this converge left it as it is. Apply a template change by the
          cache-config-reset procedure in infra/runbooks/cache.md, and a password changed in
          group_vars/cache_host/vault.yml by its cache-password-rotation procedure, which resets the three
          nodes together.
      loop: "{{ cache_daemon_files }}"
      when: item not in (cache_conf_render.results | selectattr('changed') | map(attribute='item') | list)
```

with:

```yaml
          node is the daemon's and this converge left it as it is. Apply a template change by the
          cache-config-reset procedure in infra/runbooks/cache.md, and a password changed in
          group_vars/cache_host/vault.yml or group_vars/all/vault.yml by its cache-password-rotation
          procedure, which resets the three nodes together and re-renders the engine host.
      loop: "{{ cache_daemon_files }}"
      when: item not in (cache_conf_render.results | selectattr('changed') | map(attribute='item') | list)
```

Move the two vault blocks, from the repository root; the script prints line counts and never a value:

```bash
uv run python - <<'EOF'
"""Move two `!vault` blocks verbatim from the cache group's vault to group_vars/all's (spec 00120 D2).

Nothing is decrypted or printed: the same vault password serves both files, so the ciphertext moves as
it is, the precedent of spec 00054's move. Run from the repository root.
"""

from pathlib import Path

SRC = Path("infra/ansible/group_vars/cache_host/vault.yml")
DST = Path("infra/ansible/group_vars/all/vault.yml")
KEYS = ("cache_engine_password", "cache_sentinel_requirepass")
NOTE = (
    "# Moved here from group_vars/cache_host/ (spec 00120 D2): the engine play renders `cache_engine_password`\n"
    "# into engine.env and `cache_sentinel_requirepass` into the cache proxy's check line, and the cache role\n"
    "# reads both unchanged. The ciphertext is UNCHANGED -- same vault password, the blocks moved verbatim and\n"
    "# were never decrypted. Rotating either is infra/runbooks/cache.md's cache-password-rotation.\n"
)
HEADER = [
    ("# eight of these DO render onto managed hosts, so this is not a workstation-only file.\n",
     "# ten of these DO render onto managed hosts, so this is not a workstation-only file.\n"),
    ("# MIXED CUSTODY — do not read this file as workstation-only. Eight of the thirteen values ARE\n",
     "# MIXED CUSTODY — do not read this file as workstation-only. Ten of the fifteen values ARE\n"),
    ("# `render the grafana keep-alive secrets env file`; editing it needs `--limit zcrypto-ops` only.\n",
     "# `render the grafana keep-alive secrets env file`; editing it needs `--limit zcrypto-ops` only. The\n"
     "# ninth and tenth are the cache's `cache_engine_password` and `cache_sentinel_requirepass`, rendered onto\n"
     "# `zcrypto` by `roles/engine` (engine.env and haproxy.cfg) and read by `roles/cache` on the three nodes;\n"
     "# rotating either is `infra/runbooks/cache.md`'s `cache-password-rotation`.\n"),
]

lines = SRC.read_text().splitlines(keepends=True)
kept: list[str] = []
moved: list[str] = []
i = 0
while i < len(lines):
    line = lines[i]
    if any(line.startswith(f"{key}: !vault |") for key in KEYS):
        block = [line]
        i += 1
        while i < len(lines) and lines[i].startswith("  "):
            block.append(lines[i])
            i += 1
        moved.append("".join(block))
        continue
    kept.append(line)
    i += 1
assert len(moved) == 2, f"expected the two blocks in {SRC}, found {len(moved)}"
text = DST.read_text()
for old, new in HEADER:
    assert text.count(old) == 1, f"{DST}: header line not found once: {old[:60]!r}"
    text = text.replace(old, new)
assert not any(f"{key}: !vault |" in text for key in KEYS), f"{DST} already carries a moved key"
SRC.write_text("".join(kept))
DST.write_text(text + ("" if text.endswith("\n") else "\n") + NOTE + "".join(moved))
print(f"moved {len(moved)} blocks: {SRC} {len(lines)} -> {len(kept)} lines; {DST} {text.count(chr(10))} -> {(text + NOTE + ''.join(moved)).count(chr(10))} lines")
EOF
grep -c '^cache_[a-z_]*: !vault |' infra/ansible/group_vars/cache_host/vault.yml infra/ansible/group_vars/all/vault.yml
```

Expected: `moved 2 blocks: infra/ansible/group_vars/cache_host/vault.yml 48 -> 30 lines; infra/ansible/group_vars/all/vault.yml 286 -> 308 lines`, then `infra/ansible/group_vars/cache_host/vault.yml:3` and `infra/ansible/group_vars/all/vault.yml:3`; `git diff --stat -- infra/ansible/group_vars/` reads 28 insertions and 21 deletions over the two files. Never print either file: the bash guard refuses it, and a read of a value is `vault_var`'s through command substitution.

Replace, in `infra/runbooks/cache.md`, this block:

```markdown
### What you are seeing

Nothing fired. You mean to change a password in `group_vars/cache_host/vault.yml`, or a converge's drift report named `valkey.conf`, `sentinel.conf` or `users.acl` after one changed there, since their renders carry the passwords.

### What it means

The nodes authenticate to each other: a replica to its primary with the `replica` password, each Sentinel to each Valkey with the `sentinel` password and to the other Sentinels with Sentinel's `requirepass`. A node reset alone to a new password fails to authenticate to, and from, a node still holding the old one, so the three nodes' files are replaced in one stop, the set down for the minutes it takes; once the engine is wired to the set, that is inside an engine inter-cycle gap. The rendered files name valkey1 as the first primary, so valkey1 holds the primary before the stop and starts first, and no write the set took is lost. `vk` and `sn` read their passwords from files a converge carrying the node's image digest re-renders, and Alloy reads the exporter password and `requirepass` from a secrets file a converge carrying the Alloy digest re-renders and the container reads when it is recreated. The stop fires `zcrypto-cache-primary-count` once its two minutes pass, and it clears when step 5 is done on valkey2, the second node whose Sentinel and Alloy run on the new passwords; `zcrypto-cache-replicas-short` fires when valkey3's step 5 comes more than five minutes after valkey1's, and clears when valkey3's replica connects.

### What to do

1. **Put the primary on valkey1 while the nodes still run the old passwords:** `cache-manual-failover` above, repeated until `sn SENTINEL get-master-addr-by-name zcache` names `10.98.0.11`. When a converge already carried the change, `vk` or `sn` answers `WRONGPASS` or `NOAUTH`: put the old value back in `vault.yml`, converge each node with the two digests it runs, read as step 3 reads them — step 5's command without `-e cache_config_reset=true` — and begin here again.
2. **Change the password** in `group_vars/cache_host/vault.yml` by the recipe in that file's header, merged to `develop`, which the converges below run from. Steps 3 to 5 follow in the same sitting, and no other cache converge — a `cache-config-reset` on another node, an Alloy bump's cache leg — runs between this merge and step 5: a converge without the reset in that window renders the new password into the env files its digests gate, against a `users.acl` and a Sentinel `requirepass` still holding the old one, and two nodes in that state page `zcrypto-cache-primary-count` on a healthy set.
3. **Read each node's running digests**, on each node: `sudo docker inspect zcrypto-valkey grafana-alloy --format '{{.Config.Image}}'` prints Valkey's, then Alloy's.
4. **Stop the three nodes, valkey3 and valkey2 before valkey1:** `sudo systemctl stop zcrypto-cache.service` on each.
5. **Converge each node with the reset, valkey1 first, and recreate its Alloy before the next node's converge**, from `infra/ansible`: `./scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags cache -e cache_config_reset=true -e cache_image_digest=sha256:<its Valkey digest> -e cache_alloy_digest=sha256:<its Alloy digest>`, which renders the node's files and starts its daemons; then, on the node, `cd /opt/zcrypto-cache/alloy && sudo docker compose up -d`, which recreates Alloy so it reads the new secrets.
6. **Confirm by value:** on valkey2 and valkey3, `cache-rejoin-node` steps 3 and 4; on each node, `sn SENTINEL ckquorum zcache` answers `OK 3 usable Sentinels`; from the workstation, `uv run python infra/scripts/grafana-query.py 'redis_up{host=~"zcrypto-valkey[123]"}'` reads 1 on six series, a node's `valkey` and `sentinel` each.

### Retire when
```

with:

```markdown
### What you are seeing

Nothing fired. You mean to change a password in `group_vars/cache_host/vault.yml`, or `cache_engine_password` or `cache_sentinel_requirepass` in `group_vars/all/vault.yml`, or a converge's drift report named `valkey.conf`, `sentinel.conf` or `users.acl` after one changed there, since their renders carry the passwords.

### What it means

The nodes authenticate to each other: a replica to its primary with the `replica` password, each Sentinel to each Valkey with the `sentinel` password and to the other Sentinels with Sentinel's `requirepass`. A node reset alone to a new password fails to authenticate to, and from, a node still holding the old one, so the three nodes' files are replaced in one stop, the set down for the minutes it takes, inside an engine inter-cycle gap while the engine is flat: the engine authenticates with the `engine` password and its proxy checks the Sentinels with their `requirepass`, both rendered on the engine host from `group_vars/all/vault.yml`, and between the nodes' stop and the engine converge of step 6 the engine holds no session the new passwords admit, its writes are dropped and the store is behind — the outage the `zcrypto-engine-cache-write-failed` section below describes, whose restart is that converge. The rendered files name valkey1 as the first primary, so valkey1 holds the primary before the stop and starts first, and no write the set took is lost. `vk` and `sn` read their passwords from files a converge carrying the node's image digest re-renders, and Alloy reads the exporter password and `requirepass` from a secrets file a converge carrying the Alloy digest re-renders and the container reads when it is recreated. The stop fires `zcrypto-cache-primary-count` once its two minutes pass, and it clears when step 5 is done on valkey2, the second node whose Sentinel and Alloy run on the new passwords; `zcrypto-cache-replicas-short` fires when valkey3's step 5 comes more than five minutes after valkey1's, and clears when valkey3's replica connects.

### What to do

1. **Put the primary on valkey1 while the nodes still run the old passwords:** `cache-manual-failover` above, repeated until `sn SENTINEL get-master-addr-by-name zcache` names `10.98.0.11`. When a converge already carried the change, `vk` or `sn` answers `WRONGPASS` or `NOAUTH`: put the old value back in `vault.yml`, converge each node with the two digests it runs, read as step 3 reads them — step 5's command without `-e cache_config_reset=true` — and begin here again.
2. **Change the password** in `group_vars/cache_host/vault.yml`, or in `group_vars/all/vault.yml` for `cache_engine_password` and `cache_sentinel_requirepass`, by the recipe in the cache file's header, merged to `develop`, which the converges below run from. Steps 3 to 6 follow in the same sitting, and no other converge that renders a password — a `cache-config-reset` on another node, an Alloy bump's cache leg, an engine converge of `zcrypto` — runs between this merge and step 6: a cache converge without the reset in that window renders the new password into the env files its digests gate, against a `users.acl` and a Sentinel `requirepass` still holding the old one, and two nodes in that state page `zcrypto-cache-primary-count` on a healthy set; an engine converge in it — an arm or disarm, the rollout skill's same-day shape — renders the new `engine` password into `engine.env` or the new `requirepass` into `haproxy.cfg` against nodes still holding the old, and its handler restarts the engine into `failed to create cache database backing` at ten-second intervals until step 6.
3. **Read each node's running digests**, on each node: `sudo docker inspect zcrypto-valkey grafana-alloy --format '{{.Config.Image}}'` prints Valkey's, then Alloy's.
4. **Stop the three nodes, valkey3 and valkey2 before valkey1:** `sudo systemctl stop zcrypto-cache.service` on each.
5. **Converge each node with the reset, valkey1 first, and recreate its Alloy before the next node's converge**, from `infra/ansible`: `./scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags cache -e cache_config_reset=true -e cache_image_digest=sha256:<its Valkey digest> -e cache_alloy_digest=sha256:<its Alloy digest>`, which renders the node's files and starts its daemons; then, on the node, `cd /opt/zcrypto-cache/alloy && sudo docker compose up -d`, which recreates Alloy so it reads the new secrets.
6. **Converge the engine host in the same gap, the one engine converge step 2 admits between the merge and here**, when `cache_engine_password` or `cache_sentinel_requirepass` changed: `./scripts/converge.sh site.yml --limit zcrypto -e converge_primary=true -e engine_image_digest=sha256:<the running engine digest> -e cache_proxy_image_digest=sha256:<the running proxy digest> --tags engine`, both digests read off the containers as `docs/reference/fleet-pins.md` prescribes; it re-renders `engine.env` and `haproxy.cfg` and its handler restarts the engine and the proxy, the restart `engine-restart-margin-position` in `infra/runbooks/engine-procedures.md` admits while flat.
7. **Confirm by value:** on valkey2 and valkey3, `cache-rejoin-node` steps 3 and 4; on each node, `sn SENTINEL ckquorum zcache` answers `OK 3 usable Sentinels`; from the workstation, `uv run python infra/scripts/grafana-query.py 'redis_up{host=~"zcrypto-valkey[123]"}'` reads 1 on six series, a node's `valkey` and `sentinel` each.

### Retire when
```

- [ ] **Step 5: Run the four files and watch them pass**

Run: `uv run pytest tests/test_infra_cache_proxy.py tests/test_infra_compose_templates.py tests/test_config.py tests/test_infra_converge_guards.py -q -p no:cacheprovider`
Expected: `469 passed`.

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_bash_guard.py tests/test_config.py tests/test_config_selectors_are_parsed.py tests/test_converge_sh.py tests/test_count_list.py tests/test_dashboards_cover_metrics.py tests/test_deploy_log_audit.py tests/test_deploy_log.py tests/test_engine_execgate.py tests/test_engine_flatten.py tests/test_engine_flatten_wrapper.py tests/test_engine_journal_prune.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_infra_alert_rules.py tests/test_infra_cache_proxy.py tests/test_infra_compose_templates.py tests/test_infra_converge_guards.py tests/test_infra_firewall_template.py tests/test_infra_grafana_keepalive.py tests/test_infra_unattended_upgrades.py tests/test_internal_terms_not_operator_visible.py tests/test_merge_gate.py tests/test_message_citations.py tests/test_ops_daily.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_run_sh.py tests/test_fleet_contracts.py tests/test_open_topics_frontmatter.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `4861 passed, 1 skipped` when this plan was written, the skip `tests/test_engine_flatten.py`'s live-venue gate. The list is every module that reads the engine role, `site.yml`, `converge.sh`, the cache role's tasks, the two vault files or a runbook page, with the fleet contracts, the topics' frontmatter and the selector guard over the new test file.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed, ansible-lint and yamllint among them; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 8: Commit**

```bash
git add infra/ansible/roles/engine infra/ansible/site.yml infra/ansible/scripts/converge.sh infra/ansible/roles/cache/tasks/main.yml infra/ansible/group_vars/cache_host/vault.yml infra/ansible/group_vars/all/vault.yml infra/runbooks/cache.md infra/README.md tests/test_infra_compose_templates.py tests/test_config.py tests/test_infra_converge_guards.py tests/test_infra_cache_proxy.py
git commit -m "feat(infra): the engine's cache proxy beside it in the compose project, its config validated by the pinned image before it lands, the two cache secrets under group_vars/all, and the window guard over cache-link

The engine role renders a cache-proxy service, HAProxy digest-pinned through the operand
cache_proxy_image_digest under the engine image's three guards -- non-empty, pre-staged, the
replaced digest recorded in fleet-pins.md -- and no canary parity, since no capture bake of an
upstream image exists. Its config carries three backends, one per cache node, each with a server
line per Sentinel that authenticates, pings and expects the anchored SENTINEL master reply naming
that node, and the frontend routes to the backend two of three Sentinels name; the file is rendered
root-owned 0600 under no_log beside its live copy, validated by the pinned image's own haproxy -c,
and copied into place only then, the restart firing on a changed copy alone -- the four ahead of
the engine's own three renders, so a refused render stops before any engine file is rewritten and
the config exists before the compose file names it, the render and the validate in check mode too,
so the preview is the validation's first run. global carries maxconn 256, without which HAProxy
sizes itself off the container's 524288 file-descriptor limit and its worker is killed under the
32m cap at load. The client and server timeouts are rendered as 24 days, the parser's longest, since a zero warns at every start as a
missing timeout and the engine writes every cycle. The engine service waits for the proxy to start
and takes twenty seconds to stop, engine.env carries ZCRYPTO_CACHE_PASSWORD, and zcrypto.toml
renders the cache table enabled at cache-proxy:6379 as engine behind engine_cache_enabled, whose
-e false renders no table: the way back to an engine without the cache on any image inside the
same gap. cache_engine_password and
cache_sentinel_requirepass move verbatim to group_vars/all/vault.yml, where the engine play reads
them, the ciphertext unchanged under the same vault password; the engine host holds both to the
cache role's floor. The engine window guard's four tasks take the cache-link tag, since that role's
handler restarts the mesh interface the engine's cache session now crosses, the cache_link role is
held off where engine is skipped, since a --skip-tags engine run skips the guard with it, and the
rotation procedure gains the engine converge in the same gap, the one engine converge its sitting
admits. The store-delivery assert's re-run message and infra/README.md's engine converge carry the
proxy digest operand the role now refuses empty.

Cases: the rendered config's backends, servers, check sequence, anchored reply, timeouts, maxconn,
logging and metrics endpoint, with no unescaped dollar and no QUIT; the engine defaults' nodes and master
name equal to the cache roles'; converge.sh admitting the operand; the env line under the no_log
render; the two secrets in the all group's vault and the other three in the cache group's; the
compose service's pin, user, mount, port, cap and logging, the engine's depends_on and grace, and
a render handed both secrets carrying neither; the rendered toml's cache table, and none under
the operand; every window-guard task tagged cache-link and the cache_link role held off under
--skip-tags engine; the proxy digest refused empty and unpulled, the pins recording's four
shapes, the password floor's four shapes, and the render-validate-install-remove order ahead of
the env render, the render and the validate in check mode, with no_log on the render and the
install.

PROBE_VERDICT

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>"
```

- [ ] **Step 9: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 10: Prove the guards with fourteen probes, then record their verdicts by a message-only amend**

The proxy template's control moves the check timeout so the timeouts case fails; its mutations drop `init-state`, route on one Sentinel, unescape the reply's dollar, and drop `maxconn`. The compose template's control moves the grace so the engine case fails; its mutations drop the root user and the `depends_on`. The role's control drops `-c` from the validation so the order case fails; its mutations lower the password floor to four, make the install a plain copy, and skip the validation in check mode. The play's control renames the window task so `find_task` fails; its mutations drop `cache-link` from every guard tag, and drop the cache_link role's `when`. The converge script's control renames the key set so the parse fails; its mutation drops the proxy digest's key. The toml template's control comments the enabled line so the exact-line case fails; its mutations render the cache disabled, and render the table whatever the operand.

```bash
K="proxy or cache_table or window_guard_task or password_below or two_secrets or each_backend or timeouts_the_logging or check_authenticates or converge_sh_admits or engine_env_file"
T="uv run pytest tests/test_infra_cache_proxy.py tests/test_infra_compose_templates.py tests/test_config.py tests/test_infra_converge_guards.py -q -p no:cacheprovider -k"
H=infra/ansible/roles/engine/templates/haproxy.cfg.j2
HC='s/timeout check 2s/timeout check 3s/'
infra/scripts/mutate-probe.sh --file $H --control "$HC" --mutation 's/init-state fully-down //' -- $T "$K"
infra/scripts/mutate-probe.sh --file $H --control "$HC" --mutation 's/nbsrv({{ node.name }}) ge 2/nbsrv({{ node.name }}) ge 1/' -- $T "$K"
infra/scripts/mutate-probe.sh --file $H --control "$HC" --mutation 's/"\\\$2/"$2/' -- $T "$K"
infra/scripts/mutate-probe.sh --file $H --control "$HC" --mutation '/^    maxconn 256$/d' -- $T "$K"
C=infra/ansible/roles/engine/templates/compose.yaml.j2
CC='s/stop_grace_period: 20s/stop_grace_period: 25s/'
infra/scripts/mutate-probe.sh --file $C --control "$CC" --mutation 's/^    user: "0:0"$/    user: "1000:1000"/' -- $T "$K"
infra/scripts/mutate-probe.sh --file $C --control "$CC" --mutation '/^    depends_on:$/,/^        condition: service_started$/d' -- $T "$K"
R=infra/ansible/roles/engine/tasks/main.yml
RC='s/haproxy -c -f/haproxy -f/'
infra/scripts/mutate-probe.sh --file $R --control "$RC" --mutation 's/\[A-Za-z0-9\]{5,}\\Z/[A-Za-z0-9]{4,}\\Z/g' -- $T "$K"
infra/scripts/mutate-probe.sh --file $R --control "$RC" --mutation 's/^    remote_src: true$/    remote_src: false/' -- $T "$K"
infra/scripts/mutate-probe.sh --file $R --control "$RC" --mutation '/validate the rendered cache proxy config/,/^$/s/^  check_mode: false$/  when: not ansible_check_mode/' -- $T "$K"
infra/scripts/mutate-probe.sh --file infra/ansible/site.yml --control 's/engine window — refuse a converge outside the inter-cycle gap/engine window - refuse a converge outside the inter-cycle gap/' \
  --mutation 's/tags: \[engine, cache-link\]/tags: [engine]/' -- $T "$K"
infra/scripts/mutate-probe.sh --file infra/ansible/site.yml --control 's/engine window — refuse a converge outside the inter-cycle gap/engine window - refuse a converge outside the inter-cycle gap/' \
  --mutation "/^      when: \"'engine' not in ansible_skip_tags\"\$/d" -- $T "$K"
infra/scripts/mutate-probe.sh --file infra/ansible/scripts/converge.sh --control 's/^EVKEYS=/EVKEYSS=/' \
  --mutation 's/cache_config_reset cache_proxy_image_digest engine_cache_enabled"/cache_config_reset engine_cache_enabled"/' -- $T "$K"
infra/scripts/mutate-probe.sh --file infra/ansible/roles/engine/templates/zcrypto.toml.j2 --control 's/^enabled = true$/enabled = true # x/' \
  --mutation 's/^enabled = true$/enabled = false/' -- $T "$K"
infra/scripts/mutate-probe.sh --file infra/ansible/roles/engine/templates/zcrypto.toml.j2 --control 's/^enabled = true$/enabled = true # x/' \
  --mutation 's/{% if engine_cache_enabled | bool %}/{% if true %}/' -- $T "$K"
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message with the text below: write the whole message, that line replaced, to a file under `.tmp/` (gitignored) and amend from it with `git commit --amend -F <file>`; the amend changes the message only, no file.

```
Probe: `infra/scripts/mutate-probe.sh` over the proxy template, control the check timeout moved so
the timeouts case fails: init-state dropped, KILLED, control proven; routing on one Sentinel,
KILLED, control proven; the reply's dollar unescaped, KILLED, control proven; maxconn dropped,
KILLED, control proven; over the compose template, control the grace moved so the engine case
fails: the root user dropped, KILLED, control proven; depends_on dropped, KILLED, control proven;
over the role's tasks, control -c dropped from the validation so the order case fails: the password
floor lowered to four, KILLED, control proven; the install made a plain copy, KILLED, control
proven; the validation skipped in check mode, KILLED, control proven; over site.yml, control the
window task renamed so find_task fails: cache-link dropped from every guard tag, KILLED, control
proven; the cache_link role's when dropped, KILLED, control proven; over converge.sh, control the
key set renamed so the parse fails: the proxy digest's key dropped, KILLED, control proven; over
the toml template, control the enabled line commented so the exact-line case fails: the cache
rendered disabled, KILLED, control proven; the table rendered whatever the operand, KILLED, control
proven.
```

Run: `git status --porcelain` -- Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` -- Expected: `0`; `git log -1 --format=%B | grep -c 'infra/scripts/mutate-probe.sh'` -- Expected: `1`, the verdict naming the script.

---
### Task 6: The proxy's telemetry, the three rules and their sections, the operator's test on every page that carries the rule, and the topics

This task is spec D14 and D17, with D1's failover line and D16's topic closeouts: the `cache_proxy` scrape on the capture hosts' Alloy with its six families in the keep-regex and the keep-lists, the proxy's journal lines labelled `cache-proxy` ahead of the engine's block, the Cache board's proxy row, the two proxy rules and the cache-write rule in the `zcrypto-cache` group with a section each in `cache.md`, the outage line beside them, the anchor paragraph `engine-restart-margin-position` rewritten to the operator's test with its four reads, the conditional stated in one clause on every line that carries the rule across the four runbooks, `fleet.md` and the adapter-verification page, `fleet.md`'s telemetry rows, T0158's trigger re-keyed to either lift, T0213 resolved and archived, and the two consumers the new rules and the new pipeline block reach -- the ops daily's uid map and the Alloy stages guard -- kept green.

What this task decides, where the spec leaves it open:

- The proxy's journal lines are selected by a line filter on the compose prefix of their container, `zcrypto-cache-proxy +| `, inside a `stage.match` placed before the engine's block, which relabels every remaining line of the unit; HAProxy's `[NOTICE]`, `[WARNING]`, `[ALERT]` and `[INFO]` words map to the Python spellings the Logs board's level picker holds; a traffic line or a server state line, which carries none, ships with no level label, the level stages sitting in an inner match over lines opening with the word, since Alloy's template over an absent value labels a line `<no value>` (measured with the pinned v1.19.2 binary over the file's own `loki.process "parse"`). The Logs board's container picker is a `label_values` query, so `cache-proxy` appears in it with the first shipped line and no dashboard edit.
- The no-backend rule reads `max(haproxy_backend_active_servers{host="zcrypto"}) or on() vector(0)` below 2, the frontend's own `nbsrv(nodeN) ge 2` routing bound, which `tests/test_infra_alert_rules.py` reads out of the template and holds equal, since a backend at one check passing routes nothing new; the fallback because the scrape target is static and a stopped proxy takes its series away; the no-session rule takes `zcrypto-engine-dark-with-exposure`'s math shape, sessions below 1 while the engine's scrape reads 1; the write rule takes `zcrypto-engine-error-logs`' Loki shape over `container="engine-nautilus"` and routes to the `logs` receiver as that rule does. The Cache board's panels 402 and 403 chart each rule's own expression as their first target with the bar at each rule's threshold, 2 and 1, where the red-line guard reads them. HAProxy's exporter publishes the status families as one 0/1 series per `state` label, never one enumerated value (measured on 3.4.5: `haproxy_backend_status{proxy="node1",state="DOWN"} 1` beside `{state="UP"} 0`), so panels 401 and 404 select `state="UP"` and panel 406 charts the check-status series at 1 with the state in its legend.
- The rule's pages state the conditional as `with no Kraken margin position open beyond those [the restart rule]'s test admits`, or `open that [the restart rule]'s test does not admit`, one clause per line, the link unchanged; `only` is not used, since the guidance guard reads it as a universal on a list item. The order-semantics page's three places say the harness's own node keeps no cache, so the test lifts nothing there, as D17 has it.
- T0213 is resolved here rather than at the rollout: the plan's tasks deliver the topic's solution, and the converge it still needs is the fleet's concern; its `## Resolution` names the spec, the plan and the Rollout section, and the index is re-rendered by `infra/scripts/topics-index.py`, never edited by hand. T0158's trigger keeps its `A2:` shape and names both lifts.
- `fleet.md`'s new telemetry row and its two edited bullets stay under the contracts' caps (a cell at most 200 characters, a bullet 700), which `tests/test_fleet_contracts.py` holds.

**Files:**
- Modify: `infra/ansible/roles/capture/files/config.alloy` (the `cache_proxy` scrape after `engine_app`; six families in the keep-regex; the `cache_proxy` match before `engine_nautilus`)
- Modify: `infra/grafana/alerts.yaml` (three rules appended to the `zcrypto-cache` group)
- Modify: `infra/grafana/cache-dashboard.json` (panel 211's description; row 400 and panels 401 to 406)
- Modify: `infra/runbooks/cache.md` (the primary-count page's write clause; the failover's cost line; three alert sections)
- Modify: `infra/runbooks/engine-procedures.md` (the anchor paragraph with its four reads; the arm converge's proxy digest; seven lines), `infra/runbooks/engine.md` (nine lines, the store re-delivery converge's proxy digest among them), `infra/runbooks/drills-order-path.md` (six lines), `infra/runbooks/order-semantics-verification.md` (three places)
- Modify: `docs/reference/adapter-verification/2.0.0rc6.dev20260921.md` (the operating rule's heading and paragraph; the lift bullet)
- Modify: `infra/scripts/ops_daily.py` (`_UID_HOST`, the three rules)
- Modify: `docs/reference/fleet.md` (the two Reboots lines; the telemetry table's proxy row and Alloy row; the labels bullet)
- Modify: `docs/open-topics/T0158-go-live-drill-program-execution.md` (`ripe_when`; the A2 step)
- Modify and move: `docs/open-topics/T0213-engine-cache-engine-half.md` to `docs/open-topics/archive/` (status, trigger, `## Resolution`)
- Render: `docs/open-topics/README.md` (`infra/scripts/topics-index.py`)
- Test: `tests/test_infra_alloy_series.py` (`CACHE_PROXY_SERIES` in the capture list and the other hosts' exclusions; the scrape-and-pipeline case)
- Test: `tests/test_infra_alert_rules.py` (four `NOT_A_FAULT_SIGNAL` entries; the three rules' case, the no-backend threshold held to the template's routing bound)
- Test: `tests/test_infra_alloy_stages.py` (`_engine_blocks` selecting the nautilus stage and its drop by name, not by a substring the proxy's block shares)
- Modify, in its own `claude(` commit: `.claude/skills/zcrypto-rollout-image/SKILL.md` (the engine shape's third digest)

**Interfaces:**
- Consumes: `prometheus.remote_write.grafana`, `loki.write.grafana` and the `engine_nautilus` stage in `config.alloy`; the `zcrypto-cache` group, `GRAFANA_PROM_DS_UID`, `GRAFANA_LOKI_DS_UID` in `alerts.yaml`; `CAPTURE_REQUIRED`, `_keep_regex`, `CAPTURE_ALLOY` in `tests/test_infra_alloy_series.py`; `NOT_A_FAULT_SIGNAL`, `_rules` in `tests/test_infra_alert_rules.py`; `infra/scripts/topics-index.py`
- Produces: the `cache_proxy` scrape job; the `cache-proxy` container label; rules `zcrypto-cache-proxy-no-backend`, `zcrypto-cache-proxy-no-engine-session`, `zcrypto-engine-cache-write-failed` and their `cache.md` anchors; panels 400 to 406 on `zcrypto-cache`; `CACHE_PROXY_SERIES`; the operator's test at `engine-restart-margin-position`

- [ ] **Step 1: Confirm Task 5's marker and this task's absence**

Run: `grep -c 'cache-proxy' infra/ansible/roles/engine/templates/compose.yaml.j2; grep -c 'cache_proxy' infra/ansible/roles/capture/files/config.alloy; grep -c 'zcrypto-cache-proxy-no-backend' infra/grafana/alerts.yaml; ls docs/open-topics/T0213-engine-cache-engine-half.md`
Expected: a number above 0, then `0`, then `0`, then the topic's path. A `0` first means Task 5 is not in; a scrape or rule already present, or the topic already under `archive/`, means this task is; stop and report either to the controller.

- [ ] **Step 2: The failing cases in `tests/test_infra_alloy_series.py` and `tests/test_infra_alert_rules.py`**

Replace, in `tests/test_infra_alloy_series.py`, this block:

```python
]

# The capture host's own alert-bearing node families: `Capture · spool disk low` reads
# node_filesystem_avail_bytes/node_filesystem_size_bytes, and `Capture · node load high` reads
```

with:

```python
]

# The engine's cache proxy, HAProxy's Prometheus endpoint scraped as `cache_proxy` on the capture
# hosts (zcrypto-red admits a family it never publishes, as it does the engine's). Two are
# alert-bearing (zcrypto-cache-proxy-no-backend, -no-engine-session) and the other four are the
# detail the Cache board's proxy row draws; dropped from the keep-regex, the rules read 0 forever.
CACHE_PROXY_SERIES = [
    "haproxy_backend_status",
    "haproxy_backend_active_servers",
    "haproxy_backend_current_sessions",
    "haproxy_server_status",
    "haproxy_server_check_status",
    "haproxy_server_check_failures_total",
]

# The capture host's own alert-bearing node families: `Capture · spool disk low` reads
# node_filesystem_avail_bytes/node_filesystem_size_bytes, and `Capture · node load high` reads
```

Replace, in `tests/test_infra_alloy_series.py`, this block:

```python
    *CAPTURE_APP_SERIES,
    *ENGINE_APP_SERIES,
    *LOGSHIP_SERIES,
    *PROCESS_FAMILIES,
```

with:

```python
    *CAPTURE_APP_SERIES,
    *ENGINE_APP_SERIES,
    *CACHE_PROXY_SERIES,
    *LOGSHIP_SERIES,
    *PROCESS_FAMILIES,
```

Replace, in `tests/test_infra_alloy_series.py`, this block:

```python
    [
        # No daemon runs on the NAS at all (00069 T7) -- none of the app/logship families exist there.
        (NAS_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *LIQUIDATIONS_APP_SERIES, *LOGSHIP_SERIES]),
        # The poller runs on ops, not capture or engine.
        (OPS_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES]),
        # Capture/engine run on the capture hosts, not the poller.
        (CAPTURE_ALLOY, LIQUIDATIONS_APP_SERIES),
        # No app daemon runs on the bridgehead, and (D11) no `exporter.self "alloy"` component
        # either -- none of the app/logship/process families exist there.
        (ACCESS_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *LIQUIDATIONS_APP_SERIES, *LOGSHIP_SERIES, *PROCESS_FAMILIES]),
        (CACHE_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *LIQUIDATIONS_APP_SERIES, *LOGSHIP_SERIES]),
    ],
    ids=["nas", "ops", "capture", "access", "cache"],
```

with:

```python
    [
        # No daemon runs on the NAS at all (00069 T7) -- none of the app/logship families exist there.
        (NAS_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *CACHE_PROXY_SERIES, *LIQUIDATIONS_APP_SERIES, *LOGSHIP_SERIES]),
        # The poller runs on ops, not capture or engine.
        (OPS_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *CACHE_PROXY_SERIES]),
        # Capture/engine run on the capture hosts, not the poller.
        (CAPTURE_ALLOY, LIQUIDATIONS_APP_SERIES),
        # No app daemon runs on the bridgehead, and (D11) no `exporter.self "alloy"` component
        # either -- none of the app/logship/process families exist there.
        (
            ACCESS_ALLOY,
            [
                *CAPTURE_APP_SERIES,
                *ENGINE_APP_SERIES,
                *CACHE_PROXY_SERIES,
                *LIQUIDATIONS_APP_SERIES,
                *LOGSHIP_SERIES,
                *PROCESS_FAMILIES,
            ],
        ),
        (CACHE_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *CACHE_PROXY_SERIES, *LIQUIDATIONS_APP_SERIES, *LOGSHIP_SERIES]),
    ],
    ids=["nas", "ops", "capture", "access", "cache"],
```

Replace, in `tests/test_infra_alloy_series.py`, this block:

```python

# --- the cache nodes' config ---------------------------------------------------------------------
def test_the_cache_keep_regex_admits_exactly_the_cache_required_list():
    """Both directions, where the per-host admission test reads one: a family the regex admits that the
```

with:

```python

# --- the cache nodes' config ---------------------------------------------------------------------
def test_the_capture_config_scrapes_the_cache_proxy_and_labels_its_journal_lines_before_the_engines_block():
    """The proxy's scrape on the engine's loopback port under its own job, and its journal lines
    labelled `cache-proxy` by a match that runs before the nautilus block, which would otherwise
    relabel every line of the unit as the engine's."""
    text = CAPTURE_ALLOY.read_text()
    scrape = re.search(r'prometheus\.scrape "cache_proxy" \{(.*?)\n\}', text, re.DOTALL)
    assert scrape, "no cache_proxy scrape block"
    assert '"127.0.0.1:9104"' in scrape.group(1) and 'job_name        = "cache_proxy"' in scrape.group(1)
    proxy, engine = text.index('pipeline_name = "cache_proxy"'), text.index('pipeline_name = "engine_nautilus"')
    assert proxy < engine, "the proxy's match must run before the engine's, which relabels the whole unit"
    block = text[proxy:engine]
    assert 'container = "cache-proxy"' in block and "zcrypto-cache-proxy" in block
    assert "NOTICE|WARNING|ALERT|INFO" in block


def test_the_cache_keep_regex_admits_exactly_the_cache_required_list():
    """Both directions, where the per-host admission test reads one: a family the regex admits that the
```

Replace, in `tests/test_infra_alert_rules.py`, this block:

```python
    #   pages and its runbook reads this first to tell a cache disagreement from a crash.
    "ops_verify_replay_audit_mismatches",
}

```

with:

```python
    #   pages and its runbook reads this first to tell a cache disagreement from a crash.
    "ops_verify_replay_audit_mismatches",
    # The engine's cache proxy: the two alerted families are the most-agreed backend's active
    # servers and the sessions; these four are the detail the Cache board's proxy row draws once
    # one has paged. backend_status per backend is the alert's own signal broken out per node,
    # server_status and server_check_status are per-Sentinel views of the same checks, and the
    # failures counter rises on every failover by design, so a threshold on it pages on a healthy
    # set moving its primary.
    "haproxy_backend_status",
    "haproxy_server_status",
    "haproxy_server_check_status",
    "haproxy_server_check_failures_total",
}

```

Replace, in `tests/test_infra_alert_rules.py`, this block:

```python
            found.setdefault(anchor, []).append(path.name)
    return found


```

with:

```python
            found.setdefault(anchor, []).append(path.name)
    return found


def test_the_cache_proxy_rules_read_the_primary_and_the_write_rule_reads_the_librarys_lines():
    """The three rules of the engine's cache: every Prometheus expression scoped to the engine host,
    since the static scrape reads 0 on the secondary, and the write rule reading the library's own
    stream, which the engine's ERROR rule never selects."""
    rules = {r["uid"]: r for r in _rules()}
    backend, session, writes = (
        rules["zcrypto-cache-proxy-no-backend"],
        rules["zcrypto-cache-proxy-no-engine-session"],
        rules["zcrypto-engine-cache-write-failed"],
    )
    for rule in (backend, session):
        exprs = [q["model"]["expr"] for q in rule["data"] if "expr" in q.get("model", {})]
        assert exprs and all('host="zcrypto"' in e for e in exprs), (rule["uid"], exprs)
    assert (backend["for"], backend["labels"]["severity"]) == ("2m", "critical")
    assert 'max(haproxy_backend_active_servers{host="zcrypto"})' in backend["data"][0]["model"]["expr"]
    # The threshold is the frontend's own routing bound: a backend below `nbsrv ... ge N` routes nothing.
    haproxy_cfg = (REPO / "infra/ansible/roles/engine/templates/haproxy.cfg.j2").read_text()
    bound = {int(n) for n in re.findall(r"nbsrv\(\{\{ node\.name \}\}\) ge (\d+)", haproxy_cfg)}
    assert bound == {2}, bound
    assert backend["data"][1]["model"]["conditions"] == [{"evaluator": {"type": "lt", "params": [bound.pop()]}}]
    assert (session["for"], session["labels"]["severity"], session["condition"]) == ("15m", "warning", "D")
    assert session["data"][2]["model"]["expression"] == "$A < 1 && $B > 0"
    assert 'up{job="engine_app",host="zcrypto"}' in session["data"][1]["model"]["expr"]
    loki = writes["data"][0]
    assert loki["datasourceUid"] == "${GRAFANA_LOKI_DS_UID}"
    assert '{host="zcrypto", container="engine-nautilus"} |= "nautilus_infrastructure::redis::cache"' in loki["model"]["expr"]
    assert (writes["labels"]["severity"], writes["notification_settings"]["receiver"]) == ("warning", "logs")
    for rule in (backend, session, writes):
        assert rule["ruleGroup"] == "zcrypto-cache" and f"infra/runbooks/cache.md#{rule['uid']}" in rule["annotations"]["summary"]


```

Replace, in `tests/test_infra_alloy_stages.py`, this block:

```python
    blocks = [b for b in _blocks(_parse_body(CAPTURE_ALLOY.read_text()), "stage.match") if "engine" in b]
    assert len(blocks) == 2, f"expected the nautilus stage and its drop, found {len(blocks)}"
    stage, drop = blocks
    assert _assigned(stage, "pipeline_name") == "engine_nautilus" and _assigned(drop, "action") == "drop"
    return stage, drop
```

with:

```python
    blocks = _blocks(_parse_body(CAPTURE_ALLOY.read_text()), "stage.match")
    stages = [b for b in blocks if _assigned(b, "pipeline_name") == "engine_nautilus"]
    drops = [b for b in blocks if _assigned(b, "action") == "drop" and "engine-nautilus" in (_assigned(b, "selector") or "")]
    assert len(stages) == 1 and len(drops) == 1, f"expected the nautilus stage and its drop, found {len(stages)} and {len(drops)}"
    return stages[0], drops[0]
```

- [ ] **Step 3: Run the two files and watch the new cases fail**

Run: `uv run pytest tests/test_infra_alloy_series.py tests/test_infra_alert_rules.py -q -p no:cacheprovider`
Expected: `4 failed, 249 passed` -- the capture keep-regex dropping the six families, the scrape-and-pipeline case, the exclusion list naming families no keep-regex admits yet, and the three rules absent.

- [ ] **Step 4: The Alloy config, the rules, the board, the runbooks, `fleet.md` and the topics**

Replace, in `infra/ansible/roles/capture/files/config.alloy`, this block:

```alloy
}

// ---- Scrape -> remote_write ------------------------------------------------------------------
// T0048 defect 1's SD-wedge detection RETIRED with `discovery.docker` (D6/D8): the alert it fed
```

with:

```alloy
}

// The engine's cache proxy: HAProxy's Prometheus endpoint, published on loopback by the engine's
// compose file beside the engine's own. Scraped from both capture hosts as `engine_app` is, so its
// series read 0 on zcrypto-red by construction and every rule on them carries host="zcrypto".
prometheus.scrape "cache_proxy" {
  targets         = [{"__address__" = "127.0.0.1:9104"}]
  job_name        = "cache_proxy"
  forward_to      = [prometheus.remote_write.grafana.receiver]
  scrape_interval = "60s"
}

// ---- Scrape -> remote_write ------------------------------------------------------------------
// T0048 defect 1's SD-wedge detection RETIRED with `discovery.docker` (D6/D8): the alert it fed
```

Replace, in `infra/ansible/roles/capture/files/config.alloy`, this block:

```alloy
    write_relabel_config {
      source_labels = ["__name__"]
      regex         = "up|node_load1|node_load5|node_load15|node_memory_MemTotal_bytes|node_memory_MemAvailable_bytes|node_memory_MemFree_bytes|node_filesystem_avail_bytes|node_filesystem_size_bytes|node_filesystem_free_bytes|node_network_receive_bytes_total|node_network_transmit_bytes_total|node_cpu_seconds_total|node_scrape_collector_success|node_scrape_collector_duration_seconds|zcrypto_capture_reconnects_total|zcrypto_capture_resubscribes_total|zcrypto_capture_resubscribe_errors_total|zcrypto_capture_resubscribe_ack_timeouts_total|zcrypto_capture_segments_written_total|zcrypto_capture_segment_bytes_total|zcrypto_capture_rows_held_total|zcrypto_capture_rows_quarantined_total|zcrypto_capture_gap_seconds_total|zcrypto_capture_seconds_since_last_book_message|zcrypto_capture_venue_status_total|zcrypto_capture_book_desynced|zcrypto_capture_disk_watermark_breached|zcrypto_capture_hour_finalized_early_total|zcrypto_capture_ts_past_dated_hour_total|zcrypto_engine_target_weight|zcrypto_engine_orders_total|zcrypto_engine_order_notional_eur|zcrypto_engine_cycle_success|zcrypto_engine_cycle_completed_at_seconds|zcrypto_engine_cycle_duration_seconds|zcrypto_engine_sleeve_gross|zcrypto_engine_active_sleeves|zcrypto_exec_gate_level|zcrypto_exec_armed|zcrypto_exec_kill_tripped|zcrypto_exec_venue_ok|zcrypto_exec_last_evaluation_timestamp_seconds|zcrypto_exec_restart_hold|zcrypto_exec_orders_total|zcrypto_exec_fills_total|zcrypto_exec_fees_eur_total|zcrypto_exec_position|zcrypto_exec_resting_order_age_seconds|zcrypto_exec_realized_pnl_eur|zcrypto_exec_external_events_total|zcrypto_exec_tracking_state|zcrypto_engine_limit_bound_total|zcrypto_venue_snapshot_timestamp_seconds|zcrypto_venue_instruments_loaded|zcrypto_venue_instruments_expected|zcrypto_venue_concordance_failures|zcrypto_logship_dropped_lines_total|zcrypto_logship_shipped_lines_total|zcrypto_logship_last_cycle_timestamp_seconds|zcrypto_logship_last_success_timestamp_seconds|process_cpu_seconds_total|process_max_fds|process_open_fds|process_resident_memory_bytes|process_start_time_seconds|process_virtual_memory_bytes|node_reboot_required|node_textfile_scrape_error|node_textfile_mtime_seconds|zcache_wireguard_handshake_age_seconds|zcrypto_engine_journal_prune_deleted_days|zcrypto_engine_journal_prune_kept_days|zcrypto_engine_journal_prune_oldest_day_age_seconds|zcrypto_engine_journal_prune_last_run_timestamp_seconds|zcrypto_clock_offset_seconds|zcrypto_clock_synchronised"
      action        = "keep"
    }
```

with:

```alloy
    write_relabel_config {
      source_labels = ["__name__"]
      regex         = "up|node_load1|node_load5|node_load15|node_memory_MemTotal_bytes|node_memory_MemAvailable_bytes|node_memory_MemFree_bytes|node_filesystem_avail_bytes|node_filesystem_size_bytes|node_filesystem_free_bytes|node_network_receive_bytes_total|node_network_transmit_bytes_total|node_cpu_seconds_total|node_scrape_collector_success|node_scrape_collector_duration_seconds|zcrypto_capture_reconnects_total|zcrypto_capture_resubscribes_total|zcrypto_capture_resubscribe_errors_total|zcrypto_capture_resubscribe_ack_timeouts_total|zcrypto_capture_segments_written_total|zcrypto_capture_segment_bytes_total|zcrypto_capture_rows_held_total|zcrypto_capture_rows_quarantined_total|zcrypto_capture_gap_seconds_total|zcrypto_capture_seconds_since_last_book_message|zcrypto_capture_venue_status_total|zcrypto_capture_book_desynced|zcrypto_capture_disk_watermark_breached|zcrypto_capture_hour_finalized_early_total|zcrypto_capture_ts_past_dated_hour_total|zcrypto_engine_target_weight|zcrypto_engine_orders_total|zcrypto_engine_order_notional_eur|zcrypto_engine_cycle_success|zcrypto_engine_cycle_completed_at_seconds|zcrypto_engine_cycle_duration_seconds|zcrypto_engine_sleeve_gross|zcrypto_engine_active_sleeves|zcrypto_exec_gate_level|zcrypto_exec_armed|zcrypto_exec_kill_tripped|zcrypto_exec_venue_ok|zcrypto_exec_last_evaluation_timestamp_seconds|zcrypto_exec_restart_hold|zcrypto_exec_orders_total|zcrypto_exec_fills_total|zcrypto_exec_fees_eur_total|zcrypto_exec_position|zcrypto_exec_resting_order_age_seconds|zcrypto_exec_realized_pnl_eur|zcrypto_exec_external_events_total|zcrypto_exec_tracking_state|zcrypto_engine_limit_bound_total|zcrypto_venue_snapshot_timestamp_seconds|zcrypto_venue_instruments_loaded|zcrypto_venue_instruments_expected|zcrypto_venue_concordance_failures|zcrypto_logship_dropped_lines_total|zcrypto_logship_shipped_lines_total|zcrypto_logship_last_cycle_timestamp_seconds|zcrypto_logship_last_success_timestamp_seconds|process_cpu_seconds_total|process_max_fds|process_open_fds|process_resident_memory_bytes|process_start_time_seconds|process_virtual_memory_bytes|node_reboot_required|node_textfile_scrape_error|node_textfile_mtime_seconds|zcache_wireguard_handshake_age_seconds|zcrypto_engine_journal_prune_deleted_days|zcrypto_engine_journal_prune_kept_days|zcrypto_engine_journal_prune_oldest_day_age_seconds|zcrypto_engine_journal_prune_last_run_timestamp_seconds|zcrypto_clock_offset_seconds|zcrypto_clock_synchronised|haproxy_backend_status|haproxy_backend_active_servers|haproxy_backend_current_sessions|haproxy_server_status|haproxy_server_check_status|haproxy_server_check_failures_total"
      action        = "keep"
    }
```

Replace, in `infra/ansible/roles/capture/files/config.alloy`, this block:

```alloy
loki.process "parse" {
  forward_to = [loki.write.grafana.receiver]

  // Only nautilus's [WARN]/[ERROR] lines are kept, under their own label container="engine-nautilus",
```

with:

```alloy
loki.process "parse" {
  forward_to = [loki.write.grafana.receiver]

  // The cache proxy's lines share the unit's journal with the engine's, under the compose prefix of
  // their own container: the prefix comes off, HAProxy's own level word is read where a line carries
  // one, and every survivor is labelled container="cache-proxy" here, before the engine's block below
  // claims what is left of the unit. A traffic line and a server state line carry no level word and
  // ship with no level label: the inner match takes only a line opening with the word, since a
  // template over an absent value would label the rest "<no value>".
  stage.match {
    selector      = "{container=\"zcrypto-engine\"} |~ \"^zcrypto-cache-proxy +\\\\| \""
    pipeline_name = "cache_proxy"

    stage.replace {
      expression = "^(zcrypto-cache-proxy +\\| )"
      replace    = ""
    }

    stage.match {
      selector = "{container=\"zcrypto-engine\"} |~ \"^\\\\[(NOTICE|WARNING|ALERT|INFO)\\\\] \""

      stage.regex {
        expression = "^\\[(?P<level>NOTICE|WARNING|ALERT|INFO)\\] "
      }

      stage.template {
        source   = "level"
        template = "{{ if eq .Value \"ALERT\" }}CRITICAL{{ else if eq .Value \"NOTICE\" }}INFO{{ else }}{{ .Value }}{{ end }}"
      }

      stage.labels {
        values = { level = "level" }
      }
    }

    stage.static_labels {
      values = { container = "cache-proxy" }
    }
  }

  // Only nautilus's [WARN]/[ERROR] lines are kept, under their own label container="engine-nautilus",
```

Replace, in `infra/scripts/ops_daily.py`, this block:

```python
    "zcrypto-engine-journal-prune-dead": "zcrypto",
```

with:

```python
    "zcrypto-engine-journal-prune-dead": "zcrypto",
    "zcrypto-cache-proxy-no-backend": "zcrypto",
    "zcrypto-cache-proxy-no-engine-session": "zcrypto",
    "zcrypto-engine-cache-write-failed": "zcrypto",
```

Replace, in `infra/grafana/alerts.yaml`, this block:

```yaml
      unit: "fraction of Valkey's container memory limit"
    labels:
      severity: warning
    notification_settings:
      receiver: metrics
```

with:

```yaml
      unit: "fraction of Valkey's container memory limit"
    labels:
      severity: warning
    notification_settings:
      receiver: metrics

  # ---- the engine's cache proxy and the engine's own cache writes, on the engine host -----------------
  # `cache_proxy` is a STATIC scrape target on both capture hosts (roles/capture/files/config.alloy), so
  # its series read 0 on zcrypto-red by construction: every rule here carries host="zcrypto". The proxy
  # routes the engine's connections -- the load's, idle after the start, and the writer's -- to the node
  # two of the three Sentinels name the primary; a backend short of two servers UP is one the frontend
  # routes nothing to, the engine's writes going nowhere, and the engine's sessions absent while the
  # engine runs is a link cut the lazy reconnect has not yet taken -- the writer's returns at the next
  # write, which the library drops, and the load's never does.
  - uid: zcrypto-cache-proxy-no-backend
    title: "Cache · proxy has no backend"
    ruleGroup: zcrypto-cache
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          # The most Sentinels agreeing on any one backend: 2 or 3 while the set has a primary the quorum
          # names, 1 while only one Sentinel does, 0 while none does or the proxy is down -- `or on()
          # vector(0)` reads a dead proxy as 0 rather than NoData, since the scrape target is static and
          # a proxy container that stopped takes its series away. The threshold is the frontend's own
          # routing bound, `nbsrv(nodeN) ge 2` in roles/engine/templates/haproxy.cfg.j2: at 1 the proxy
          # routes nothing new, which tests/test_infra_alert_rules.py holds equal.
          expr: >-
            max(haproxy_backend_active_servers{host="zcrypto"}) or on() vector(0)
          instant: true
          refId: A
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "A"
          refId: C
          conditions:
            - evaluator: {type: lt, params: [2]}
    noDataState: OK
    execErrState: Alerting
    # A failover leaves the frontend without a backend for the seconds the Sentinels take to name the
    # new primary and the checks to pass twice; 2m clears one.
    for: 2m
    annotations:
      summary: "For 2+ minutes no backend of the engine's cache proxy has two Sentinel checks passing, the frontend's routing bound, so the engine's cache writes have nowhere to land: the set has no primary its quorum names, the proxy cannot reach two Sentinels over the mesh, or the proxy container is down. Nothing is replayed once the link returns, so the store is behind from the first dropped write and the engine's next restart is taken flat. Runbook: infra/runbooks/cache.md#zcrypto-cache-proxy-no-backend"
      __dashboardUid__: "zcrypto-cache"
      __panelId__: "402"
      unit: "Sentinel checks passing on the most-agreed backend"
    labels:
      severity: critical
    notification_settings:
      receiver: metrics

  - uid: zcrypto-cache-proxy-no-engine-session
    title: "Cache · engine running with no session through the proxy"
    ruleGroup: zcrypto-cache
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    # The conjunction zcrypto-engine-dark-with-exposure takes: the engine's scrape reads 1 (node B reads
    # the VALUE, since the target is static) while the proxy carries no session (node A). `or on()
    # vector(0)` on both so a dead proxy or a dark engine reads 0 rather than NoData.
    condition: D
    data:
      - refId: A
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          expr: >-
            sum(haproxy_backend_current_sessions{host="zcrypto"}) or on() vector(0)
          instant: true
          refId: A
      - refId: B
        queryType: ""
        relativeTimeRange: {from: 600, to: 0}
        datasourceUid: "${GRAFANA_PROM_DS_UID}"
        model:
          expr: 'min(up{job="engine_app",host="zcrypto"}) or on() vector(0)'
          instant: true
          refId: B
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: math
          expression: "$A < 1 && $B > 0"
          refId: C
      - refId: D
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "C"
          refId: D
          conditions:
            - evaluator: {type: gt, params: [0]}  # the math node is 1 iff BOTH halves hold
    noDataState: OK
    execErrState: Alerting
    # The library reconnects lazily, on the engine's next write: an idle engine between cycles holds no
    # session for minutes after a cut, and 15m is the longest an armed engine stays silent.
    for: 15m
    annotations:
      summary: "The engine has been reporting for 15+ minutes while the cache proxy carries no session from it: the link was cut -- a failover's shutdown of sessions, a proxy restart, the mesh interface restarted -- and the library reconnects only on the engine's next write, which it drops. The writer's session returns at the write after that; the store is behind by what the cut cost, nothing replays it, and the engine's next restart is taken flat. Runbook: infra/runbooks/cache.md#zcrypto-cache-proxy-no-engine-session"
      __dashboardUid__: "zcrypto-cache"
      __panelId__: "403"
      unit: "sessions through the proxy"
    labels:
      severity: warning
    notification_settings:
      receiver: metrics

  - uid: zcrypto-engine-cache-write-failed
    title: "Cache · the engine's cache writes failed"
    ruleGroup: zcrypto-cache
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    condition: C
    data:
      # The library logs each write it could not deliver at ERROR (`broken pipe`, `Connection refused`)
      # and each event on an order whose key an outage lost at WARN (`Cannot update order in Redis, no
      # existing state`), every one naming its module, `nautilus_infrastructure::redis::cache`, and the
      # capture primary's Alloy ships nautilus's WARN and ERROR lines as container="engine-nautilus",
      # which zcrypto-engine-error-logs (container="engine") never selects. Nothing is logged at the cut
      # itself: detection comes from writes, so an engine idle between cycles logs nothing about an
      # outage, which zcrypto-cache-proxy-no-engine-session covers from the proxy's side. Shape as
      # zcrypto-engine-error-logs: a count over 15m, `or on() vector(0)` for a clean window.
      - refId: A
        queryType: instant
        relativeTimeRange: {from: 900, to: 0}
        datasourceUid: "${GRAFANA_LOKI_DS_UID}"
        model:
          expr: >-
            sum(count_over_time({host="zcrypto", container="engine-nautilus"} |= "nautilus_infrastructure::redis::cache" [15m])) or on() vector(0)
          queryType: instant
          refId: A
      - refId: B
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: reduce
          reducer: last
          expression: "A"
          refId: B
      - refId: C
        queryType: ""
        relativeTimeRange: {from: 0, to: 0}
        datasourceUid: "__expr__"
        model:
          datasource: {type: "__expr__", uid: "__expr__"}
          type: threshold
          expression: "B"
          refId: C
          conditions:
            - evaluator: {type: gt, params: [0]}
    noDataState: OK  # `or on() vector(0)` makes a clean window evaluate to 0, not NoData
    execErrState: Alerting
    for: 0s
    annotations:
      summary: "The engine's library logged a cache write it could not deliver, or an event on an order whose cache key an outage lost, in the last 15 minutes. The link recovers lazily on the next write, which fails and is dropped, and nothing written during the outage is replayed: the store is behind by everything written while the link was down and by the dropped write, an order whose creating write was lost logs this on every later event, and the engine's next restart is taken flat. Runbook: infra/runbooks/cache.md#zcrypto-engine-cache-write-failed"
      unit: "cache write failures logged in the last 15 minutes"
    labels:
      severity: warning
    notification_settings:
      receiver: logs
```

Replace, in `infra/grafana/cache-dashboard.json`, this block:

```json
      "type": "timeseries",
      "title": "Connected clients",
      "description": "Client connections on each Valkey: the exporter, the Sentinels, the replicas on the primary, and the engine through its proxy once it is wired.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 6, "x": 18, "y": 41},
```

with:

```json
      "type": "timeseries",
      "title": "Connected clients",
      "description": "Client connections on each Valkey: the exporter, the Sentinels, the replicas on the primary, and on the primary the engine's sessions through its proxy, cache-proxy on the engine host -- two from a never-cut engine, the load's, idle after the start, and the writer's, which alone is re-made lazily at the next write after a cut.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 6, "x": 18, "y": 41},
```

Replace, in `infra/grafana/cache-dashboard.json`, this block:

```json
        "graphMode": "none"
      }
    }
  ]
```

with:

```json
        "graphMode": "none"
      }
    },
    {
      "id": 400,
      "type": "row",
      "title": "Cache proxy on the engine host",
      "collapsed": false,
      "panels": [],
      "gridPos": {"h": 1, "w": 24, "x": 0, "y": 73}
    },
    {
      "id": 401,
      "type": "stat",
      "title": "Backend status per node",
      "description": "Whether each backend of the engine's cache proxy is UP, its `state=\"UP\"` series -- HAProxy publishes one 0/1 series per state, never one enumerated value: a backend is a cache node, and its servers are the three Sentinels' checks of that node, UP while a Sentinel names it the primary. Exactly one backend UP is the healthy reading; none is the alert below; two is a failover in progress.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 5, "w": 8, "x": 0, "y": 74},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "haproxy_backend_status{host=\"zcrypto\", state=\"UP\"}",
          "refId": "A",
          "legendFormat": "{{proxy}}",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "mappings": [
            {
              "type": "value",
              "options": {
                "0": {"text": "DOWN", "color": "red", "index": 0},
                "1": {"text": "UP", "color": "green", "index": 1}
              }
            }
          ],
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "red", "value": null}, {"color": "green", "value": 1}]
          }
        },
        "overrides": []
      },
      "options": {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false},
        "textMode": "value_and_name",
        "colorMode": "background",
        "orientation": "auto",
        "graphMode": "none"
      }
    },
    {
      "id": 404,
      "type": "stat",
      "title": "Server status per backend and Sentinel",
      "description": "Each backend's three servers, one per Sentinel, their `state=\"UP\"` series: UP while that Sentinel names the backend's node the primary, DOWN otherwise. The frontend routes to a backend with two or more UP.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 5, "w": 16, "x": 8, "y": 74},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "haproxy_server_status{host=\"zcrypto\", state=\"UP\"}",
          "refId": "A",
          "legendFormat": "{{proxy}}/{{server}}",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "mappings": [
            {
              "type": "value",
              "options": {
                "0": {"text": "DOWN", "color": "red", "index": 0},
                "1": {"text": "UP", "color": "green", "index": 1}
              }
            }
          ],
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "red", "value": null}, {"color": "green", "value": 1}]
          }
        },
        "overrides": []
      },
      "options": {
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": false},
        "textMode": "value_and_name",
        "colorMode": "background",
        "orientation": "auto",
        "graphMode": "none"
      }
    },
    {
      "id": 402,
      "type": "timeseries",
      "title": "Sentinel checks passing on the most-agreed backend \u2014 the page's value",
      "description": "The most Sentinels agreeing on any one backend, and each backend's own count. 2 or 3 is a primary the quorum names and the frontend routes to; 1 is one Sentinel alone, a backend the frontend routes nothing to; 0 is no backend at all, or the proxy down, since the scrape target is static and a stopped proxy takes its series away. The red line, at the frontend's own bound of 2, is where the alert fires, after `for: 2m`. Runbook: infra/runbooks/cache.md#zcrypto-cache-proxy-no-backend",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 8, "x": 0, "y": 79},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "max(haproxy_backend_active_servers{host=\"zcrypto\"}) or on() vector(0)",
          "refId": "A",
          "legendFormat": "most-agreed backend"
        },
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "haproxy_backend_active_servers{host=\"zcrypto\"}",
          "refId": "B",
          "legendFormat": "{{proxy}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "line"}, "lineInterpolation": "stepAfter"},
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "red", "value": null}, {"color": "green", "value": 2}]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 403,
      "type": "timeseries",
      "title": "Sessions through the proxy \u2014 the page's value",
      "description": "Sessions the proxy carries to the cache set, summed over its backends: 2 from a never-cut engine, the load's connection, idle after the start, and the writer's; after a cut the writer's is re-made at the engine's next write, which the library drops, and the load's never comes back: a cut of both reads 0 until that write and 1 after it, a cut of the writer's alone 1 until that write and 2 after it, and a cut of the load's alone 1, no write dropped. Below the red line while the engine reports for `for: 15m` is the alert. Runbook: infra/runbooks/cache.md#zcrypto-cache-proxy-no-engine-session",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 8, "x": 8, "y": 79},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "sum(haproxy_backend_current_sessions{host=\"zcrypto\"}) or on() vector(0)",
          "refId": "A",
          "legendFormat": "sessions"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "line"}, "lineInterpolation": "stepAfter"},
          "thresholds": {
            "mode": "absolute",
            "steps": [{"color": "red", "value": null}, {"color": "green", "value": 1}]
          }
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 405,
      "type": "timeseries",
      "title": "Sentinel check failures per server",
      "description": "The rate at which each server's Sentinel check fails: a Sentinel not naming that backend's node the primary, or unreachable over the mesh. Two of three servers of the routed backend failing for two checks in a row moves the route.",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 7, "w": 8, "x": 16, "y": 79},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "rate(haproxy_server_check_failures_total{host=\"zcrypto\"}[5m])",
          "refId": "A",
          "legendFormat": "{{proxy}}/{{server}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "off"}, "lineInterpolation": "stepAfter"},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    },
    {
      "id": 406,
      "type": "timeseries",
      "title": "Sentinel check status code per server",
      "description": "HAProxy's own code for each server's last check, the `haproxy_server_check_status` series at 1 -- one 0/1 series per code, sixteen of them, so the one at 1 is the code: read beside the failures panel to tell a Sentinel that answered with another node (L7RSP, L7TOUT) from one that did not answer at all (L4CON, L4TOUT).",
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "gridPos": {"h": 6, "w": 24, "x": 0, "y": 86},
      "targets": [
        {
          "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
          "expr": "haproxy_server_check_status{host=\"zcrypto\"} == 1",
          "refId": "A",
          "legendFormat": "{{proxy}}/{{server}} {{state}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "short",
          "custom": {"thresholdsStyle": {"mode": "off"}, "lineInterpolation": "stepAfter"},
          "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": null}]}
        },
        "overrides": []
      },
      "options": {
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": true},
        "tooltip": {"mode": "multi", "sort": "none"}
      }
    }
  ]
```

Replace, in `infra/runbooks/cache.md`, this block:

```markdown
**No agreed primary**: a failover did not complete — fewer than two Sentinels agree the old primary is down, or no replica is eligible — or two of the three Sentinels are down, and cache writes have nowhere to land; the engine, once wired, logs its failed writes on its native side, which reaches no log store. One node's telemetry going dark does not fire it: the other two Sentinels still name the primary. The rule stays quiet while fewer than two nodes' telemetry ships, which the Alloy-dark alerts own. A node that still reads `role:master` after the Sentinels moved the primary is not counted here; `cache-rejoin-node` turns it back into a replica.
```

with:

```markdown
**No agreed primary**: a failover did not complete — fewer than two Sentinels agree the old primary is down, or no replica is eligible — or two of the three Sentinels are down, and cache writes have nowhere to land; the engine's failed writes page `zcrypto-engine-cache-write-failed` below, and the store is behind from the first one. One node's telemetry going dark does not fire it: the other two Sentinels still name the primary. The rule stays quiet while fewer than two nodes' telemetry ships, which the Alloy-dark alerts own. A node that still reads `role:master` after the Sentinels moved the primary is not counted here; `cache-rejoin-node` turns it back into a replica.
```

Replace, in `infra/runbooks/cache.md`, this block:

```markdown
### What it means

`SENTINEL failover zcache` makes the Sentinel you ask promote a replica without waiting for the others to agree the primary is down; it picks by `replica-priority`, then by replication offset, so from valkey1 the primary moves to valkey2 and from valkey2 to valkey1, and valkey3 is picked when it is the one replica left. The old primary is turned into a replica of the new one. The engine, once wired to the set, holds its connection through the proxy on its own host, whose checks cut the session at the switch so its client reconnects to the new primary; do it inside an engine inter-cycle gap by preference.

### What to do
```

with:

```markdown
### What it means

`SENTINEL failover zcache` makes the Sentinel you ask promote a replica without waiting for the others to agree the primary is down; it picks by `replica-priority`, then by replication offset, so from valkey1 the primary moves to valkey2 and from valkey2 to valkey1, and valkey3 is picked when it is the one replica left. The old primary is turned into a replica of the new one. The engine holds its connection through the proxy on its own host, whose checks cut the session at the switch (`on-marked-down shutdown-sessions`); the library reconnects lazily, on the engine's next write, which it drops, so the store is behind by that write until the write after it — the outage line under `zcrypto-engine-cache-write-failed` below — and the engine's next restart is taken flat: do it inside an engine inter-cycle gap while the engine is flat, by preference.

### What to do
```

Replace, in `infra/runbooks/cache.md`, this block:

```markdown

`zcrypto-cache-valkey-rss-headroom` is absent from `infra/grafana/alerts.yaml`, or `redis_memory_used_rss_bytes` leaves the keep regex in `infra/ansible/roles/cache/files/config.alloy`.
```

with:

```markdown

`zcrypto-cache-valkey-rss-headroom` is absent from `infra/grafana/alerts.yaml`, or `redis_memory_used_rss_bytes` leaves the keep regex in `infra/ansible/roles/cache/files/config.alloy`.

______________________________________________________________________

<a name="zcrypto-cache-proxy-no-backend"></a>

## zcrypto-cache-proxy-no-backend — ALERT

### What you are seeing

A **critical** Grafana alert, `Cache · proxy has no backend`. For over 2 minutes no backend of the engine's cache proxy has had two Sentinel checks passing: `max(haproxy_backend_active_servers{host="zcrypto"}) or on() vector(0)` read below 2, the frontend's own routing bound.

### What it means

The proxy is HAProxy in the engine's compose project on `zcrypto`, container `zcrypto-cache-proxy`, the engine's only route to the cache set: it routes `6379` to the backend two of the three Sentinels name the primary, each backend a node and each of its servers one Sentinel's check of that node, so a backend with one check passing routes nothing new. Fewer than two passing on every backend means the set has no primary its quorum names (`zcrypto-cache-primary-count` fires beside this), the proxy cannot reach the Sentinels over the `zcache0` mesh (`zcrypto-cache-wg-handshake-stale` on the engine host), or the proxy container is down, which takes the series away and reads 0 through the fallback. Meanwhile every cache write the engine makes fails: the library logs each at ERROR (`zcrypto-engine-cache-write-failed` below) and drops it, and nothing is replayed when the route returns — the store is behind from the first dropped write, and the engine's next restart is taken flat. The engine itself keeps trading: the cache is an accelerator and a recovery, never the authority on what is open. A running engine, that is: no engine start succeeds while this fires, since the node's `run()` creates the cache backing before any venue client connects and raises `failed to create cache database backing` inside about a minute, the unit restarting into it every ten seconds and `zcrypto-engine-error-logs` paging on the traceback ([`engine.md#zcrypto-engine-error-logs`](engine.md#zcrypto-engine-error-logs)) — so hold every restart, an arm or disarm converge, a kill-file clear and a `systemctl restart` alike, until the route is back; one that cannot wait is a re-converge of the engine host with the running digests and `-e engine_cache_enabled=false`, an engine without the cache, whose start is a cold one that the restart rule's test refuses with a position open. With the cache disabled on purpose — `engine_cache_enabled: false` on the engine host, the rollout's abort — the engine runs without the proxy and this page is no incident of the engine's: silence it until the cache is re-enabled, and work the proxy's route on its own clock.

### What to do

1. **Read the set first**, on one cache node: `sn SENTINEL get-master-addr-by-name zcache`. No answer, or three answers that disagree, is the set's incident: `zcrypto-cache-primary-count` above. An agreed address means the proxy does not see it.
2. **Read the proxy's checks**, on `zcrypto`: `sudo docker ps --filter name=zcrypto-cache-proxy` for the container, then `curl -s 127.0.0.1:9104/metrics | grep -E 'haproxy_server_(status|check_status)'` for each server's last check. The Cache board's proxy row shows the same per backend and Sentinel.
3. **Read the mesh from the engine host**: `sudo wg show zcache0 latest-handshakes` names each cache node's mesh address with the seconds since its last handshake; a stale one is `zcrypto-cache-wg-handshake-stale`'s procedure, on the engine host's side.
4. **Read the proxy's own lines**: on `zcrypto`, `sudo journalctl -u zcrypto-engine --since -30m | grep zcrypto-cache-proxy | tail -50`, or the Logs board with container `cache-proxy`. A `WRONGPASS` or `NOAUTH` in a check's reply is the Sentinel `requirepass` disagreeing between the rendered config and the nodes: `cache-password-rotation` above.
5. **Read first whether the unit was stopped on purpose** — `systemctl is-active zcrypto-engine` on `zcrypto`, the kill file `/var/lib/zcrypto-engine/exec/kill`, and the flatten record: an engine the red button or a latched kill file left stopped stays stopped until its reason is decided ([`engine-procedures.md#engine-flatten`](engine-procedures.md#engine-flatten)), and this rule is silenced for that stop rather than answered with a restart. **A proxy container down or wedged under a running engine is restarted with the engine**, inside the inter-cycle gap while the engine is flat, since the unit runs both: `sudo systemctl restart zcrypto-engine`, under [the restart rule](engine-procedures.md#engine-restart-margin-position), once steps 1 to 3 read a quorum-named primary the proxy reaches, since a start under a routeless proxy fails as *What it means* says. A config fault is a converge of the engine host with the running digests, not a host edit.

**Verify by value:** `uv run python infra/scripts/grafana-query.py 'max(haproxy_backend_active_servers{host="zcrypto"})'` reads 2 or 3 with the rule back to **Normal**; `(no series)` is the proxy still dark, not a zero. Then read the engine's next cache write: a `nautilus_infrastructure::redis::cache` line in Loki after the route returned is the one dropped write, and the store is behind by it and by everything written while the route was down.

### Retire when

`zcrypto-cache-proxy-no-backend` is absent from `infra/grafana/alerts.yaml`, or `infra/ansible/roles/engine/templates/compose.yaml.j2` no longer renders a `cache-proxy` service.

______________________________________________________________________

<a name="zcrypto-cache-proxy-no-engine-session"></a>

## zcrypto-cache-proxy-no-engine-session — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · engine running with no session through the proxy`. For over 15 minutes the engine's scrape has read 1 while the proxy carried no session: `sum(haproxy_backend_current_sessions{host="zcrypto"})` read 0 with `up{job="engine_app",host="zcrypto"}` at 1.

### What it means

The engine's link to the cache was cut and not yet re-made. The library holds two connections through the proxy from a start that was never cut — the load's, which idles once the store is read, and the writer's — and reconnects lazily: the next write after a cut of the writer's connection fails and is dropped, the write after that opens a fresh connection for the writer, and the load's connection never comes back, so a healthy engine reads 2 sessions from a start never cut, and 1 or 2 after a cut, by whether the cut took the load's connection. A cut is a failover's `shutdown-sessions`; one Sentinel's check going down on the routed backend — each server entry is that backend's node checked through one Sentinel, the default roundrobin balance spreads the engine's sessions over the three, and `on-marked-down shutdown-sessions` closes the sessions an entry carries, so a replica node's reboot, a Sentinel restart or a mesh blip to one node cuts the sessions routed through it; a proxy restart; the `zcache0` interface restarted by a `cache-link` converge; or a node reboot under the primary. After a cut of both connections — a failover, a proxy restart, a dead link — an engine idle between cycles shows no session for as long as it makes no write, which is what this page reads; after a per-entry cut it shows 1 and this page stays quiet: one of the writer's alone is paged by the dropped write's ERROR at the next write ([`#zcrypto-engine-cache-write-failed`](#zcrypto-engine-cache-write-failed)), and one of the load's alone drops no write. The store is behind by the dropped write and by everything written while the link was down, nothing replays it, and the engine's next restart is taken flat. The engine keeps trading. With the cache disabled on purpose — `engine_cache_enabled: false` on the engine host, the rollout's abort — the engine holds no session by design and this page is no incident: silence it until the cache is re-enabled.

### What to do

1. **Read what cut it**: the Cache board's proxy row for a route change (`Backend status per node` moved), `zcrypto-cache-primary-count` or `cache-manual-failover` for a failover, the deploy log for a `cache-link` or engine converge, and on `zcrypto` `sudo journalctl -u zcrypto-engine --since -1h | grep zcrypto-cache-proxy` for the proxy's own lines.
2. **Wait for the engine's next write**, at its next boundary cycle at the latest: the session returns at the write after the dropped one, and the alert clears itself. Nothing on the host re-makes it sooner without a restart.
3. **Treat the store as behind** from this cut until the engine's next restart, which is taken flat: [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test refuses a restart with a position open once a cache outage has fired since the boot.

**Verify by value:** `uv run python infra/scripts/grafana-query.py 'sum(haproxy_backend_current_sessions{host="zcrypto"})'` reads 1 or more with the rule back to **Normal**.

### Retire when

`zcrypto-cache-proxy-no-engine-session` is absent from `infra/grafana/alerts.yaml`, or `infra/ansible/roles/engine/templates/compose.yaml.j2` no longer renders a `cache-proxy` service.

______________________________________________________________________

<a name="zcrypto-engine-cache-write-failed"></a>

## zcrypto-engine-cache-write-failed — ALERT

### What you are seeing

A **warning** Grafana alert, `Cache · the engine's cache writes failed`. In the last 15 minutes the engine's library logged at least one line naming `nautilus_infrastructure::redis::cache`, shipped from the unit's journal as `container="engine-nautilus"`: `[ERROR] … broken pipe` or `Connection refused (os error 111)` for a write it could not deliver, or `[WARN] … Cannot update order in Redis, no existing state at …` for an event on an order whose key an outage lost.

### What it means

**The store is behind, and it stays behind.** After a cache outage — a proxy without a backend, a session cut by a failover or by one Sentinel's check going down on the routed backend, a dead link — the library reconnects lazily on the next write, which fails and is dropped, and the write after it opens a fresh connection; nothing written during the outage is replayed. An order whose creating write was lost never gets its key and logs the WARN on every later event; a lost position key is a silent no-op. So the store is behind by everything written while the link was down and by the dropped write, and the engine's next restart is taken flat: [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test refuses a restart with a position open once this, `zcrypto-cache-proxy-no-backend` or `zcrypto-cache-proxy-no-engine-session` has fired since the engine's last boot. Detection comes from writes alone: nothing is logged at the cut itself, and an engine idle between cycles logs nothing about an outage, which the no-session rule covers from the proxy's side. The engine itself keeps trading.

### What to do

1. **Read the lines** on the Logs board, container `engine-nautilus`, or on `zcrypto`: `sudo journalctl -u zcrypto-engine --since -1h | grep 'redis::cache'`. A burst of `Connection refused` is the proxy or the set down: `zcrypto-cache-proxy-no-backend` above. One `broken pipe` and nothing after is a cut the reconnect has taken.
2. **Read the proxy** as `zcrypto-cache-proxy-no-backend`'s steps 1 to 4 do, if it fires beside this; a `WRONGPASS` or `NOAUTH` in the library's line is the `engine` password disagreeing between `engine.env` and the nodes' ACL: `cache-password-rotation` above.
3. **Record the outage against the boot**: the engine's next restart is taken flat whatever the positions page reads, until a boot line after it counts the positions again.

**Verify by value:** the next boundary cycle's writes log no `redis::cache` line: `uv run python infra/scripts/grafana-query.py 'sum(count_over_time({host="zcrypto", container="engine-nautilus"} |= "redis::cache" [15m]))'` reads 0 with the rule back to **Normal**; the store's lag is not read back from here, since nothing replays it.

### Retire when

`zcrypto-engine-cache-write-failed` is absent from `infra/grafana/alerts.yaml`, or `roles/capture/files/config.alloy` no longer labels nautilus's lines `engine-nautilus`.
```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
<a name="engine-restart-margin-position"></a>

**No engine converge or restart while a Kraken margin position is open, until the nautilus-trader build the engine runs carries upstream #5065.** Kraken's margin position report carries no entry price, the node's startup reconciliation needs one to rebuild an open position, and #5065 is the upstream change that puts the entry average on that report. On 2.0.0rc6.dev20260921 a start with a margin position open goes one of two ways, depending on the pair's fill history: it fails with `Unresolved positions during startup reconciliation … missing avg_px_open for position recovery` and the container restarts into the same failure, or it boots with the position's entry price at 0, where the one reading that goes wrong is the realized-PnL gauge (`zcrypto_exec_realized_pnl_eur`). So before any procedure below converges or restarts the engine, read Kraken's positions page, or `kraken positions -o json` on the workstation, and close the position first or wait. A start already failing that way is ended by the red button's press ([`#engine-flatten`](#engine-flatten)): it stops the unit and reads the account through its own client, which runs no startup reconciliation. The rule ends once the engine runs a pinned build carrying #5065; the converge that puts it there is still a start of the engine and waits for a flat account like any other.

<a name="engine-probe-window"></a>
```

with:

```markdown
<a name="engine-restart-margin-position"></a>

**An engine converge or restart with a Kraken margin position open is admitted by one test, and refused otherwise until the nautilus-trader build the engine runs carries upstream #5065.** Kraken's margin position report carries no entry price, the node's startup reconciliation needs one to rebuild an open position, and #5065 is the upstream change that puts the entry average on that report; the engine's cache holds its own orders and positions, entry prices included, across a restart, and that is what the test reads. Four reads before any procedure below converges or restarts the engine: the Cache board's proxy row, where `Sentinel checks passing on the most-agreed backend` reads 2 or 3 and `Sessions through the proxy` reads 1 or more — the proxy routed and the engine's sessions up, two from a never-cut engine, the load's, idle after the start, and the writer's, which alone comes back after a cut; the engine's last boot line in Loki under container `engine`, `cache restore: N order(s), M position(s) restored` with a `cache restore: position <instrument> <quantity> @ <entry price> (<strategy>)` line per open position, under the engine's own strategy or `EXTERNAL` — a fill made while the engine was down beside a restored position shows as a second line under `EXTERNAL`, so an instrument's figure is its lines summed; Kraken's positions page, or `kraken positions -o json` on the workstation, for what is open; and the engine's log under the same container since that boot line for `credits nothing until the venue is read`, the executor's WARNING `a fill on restored order <id> credits nothing until the venue is read -- the next restart is taken flat`, logged at the fill whatever the venue read after it answers. The restart is admitted when every open position is one that boot line counted as restored — its instrument's lines summing to Kraken's figure, none at entry price 0 — or one this engine opened after that boot — the order that opened it this engine's own, placed after that boot, whether it filled while the engine ran or while it was down — no cache outage has fired since that boot, and no restored order has filled since it: a `zcrypto-engine-cache-write-failed`, `zcrypto-cache-proxy-no-backend` or `zcrypto-cache-proxy-no-engine-session` page since the boot line means the store is behind by what was written while the link was down and by the write the reconnect dropped, nothing replays it, and the restart is taken flat ([`cache.md#zcrypto-engine-cache-write-failed`](cache.md#zcrypto-engine-cache-write-failed)); that WARNING since the boot line marks a fill the library may have booked twice into the cache, its stored copy of the order and the position then ahead of the venue's figure, which the next start's reconciliation meets as a difference against the venue — a diff fill at the stored price, or a failed start where it crosses zero — and the line does not say whether it was: it is logged at the first fill on an order the engine held at that start and not again until the re-read pass reads that order -- restored or, on a cold start, read from Kraken, the resting order a cold start cancels at its first tick among them, whose one fill the cache books once; so the restart is taken flat on the line whichever it was. Otherwise close the position first or wait, as before: a cold start, a lost database, or a position the cache never saw — opened by hand, or by an order the cache never held — goes one of two ways on 2.0.0rc6.dev20260921, depending on the pair's fill history: the start fails with `Unresolved positions during startup reconciliation … missing avg_px_open for position recovery` and the container restarts into the same failure, or it boots with the position's entry price at 0, where the one reading that goes wrong is the realized-PnL gauge (`zcrypto_exec_realized_pnl_eur`). A start already failing that way is ended by the red button's press ([`#engine-flatten`](#engine-flatten)): it stops the unit and reads the account through its own client, which runs no startup reconciliation. The test ends once the engine runs a pinned build carrying #5065; the converge that puts it there is still a start of the engine and takes the test like any other.

<a name="engine-probe-window"></a>
```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

````markdown
2. **Edit one line** in `infra/ansible/roles/engine/templates/zcrypto.toml.j2`: `exec_armed = false` → `exec_armed = true`. There is deliberately **no** `-e` override for this value — arming is a reviewed one-line diff in the repo, not a flag anyone can type on a command line.

3. **Converge, inside the 4-hourly inter-cycle gap** (boundaries 00/04/08/12/16/20 UTC — the play refuses outside it), **with no Kraken margin position open** ([the restart rule](#engine-restart-margin-position)):

   ```
````

with:

````markdown
2. **Edit one line** in `infra/ansible/roles/engine/templates/zcrypto.toml.j2`: `exec_armed = false` → `exec_armed = true`. There is deliberately **no** `-e` override for this value — arming is a reviewed one-line diff in the repo, not a flag anyone can type on a command line.

3. **Converge, inside the 4-hourly inter-cycle gap** (boundaries 00/04/08/12/16/20 UTC — the play refuses outside it), **with no Kraken margin position open beyond those [the restart rule](#engine-restart-margin-position)'s test admits**:

   ```
````

Replace, in `infra/runbooks/engine-procedures.md`, this block:

````markdown
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine \
     -e converge_primary=true \
     -e engine_image_digest=sha256:<digest-from-step-1>
   ```
````

with:

````markdown
   infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine \
     -e converge_primary=true \
     -e engine_image_digest=sha256:<digest-from-step-1> \
     -e cache_proxy_image_digest=sha256:<the running proxy digest>
   ```

   The proxy digest is read the same way, `sudo docker inspect --format '{{.Config.Image}}' zcrypto-cache-proxy`, and passed back as it is: the engine role refuses an empty one after the capture play has already converged.
````

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
   **An order that closed while the engine was down is read at the venue by its txid, in one read at startup.** The node's own startup reconciliation reads open orders only, so an order that filled, was canceled or expired during the downtime is in the engine's cache under no name. When a preserved row names such an order — an open row whose order no longer rests, or a closed row with fills, the kind a withdrawn fill lands on — the pass reads the venue's open and closed orders once, back to an hour before the earliest such row's boundary. It makes that read through a second client on the trade key, before it sends a cancel and before a plan can be picked up, and not at all when no row needs it; it needs the key's *Query Closed Orders & Trades* permission, which the node's own startup read of the trade history already needs. A report it finds for a row takes the same comparison a resting order's figure takes, described below.

   **A failed read of the venue's orders refuses every plan until the engine is restarted.** The rows that needed it are left exactly as they were, none of them is marked, and the kill switch is not tripped: an unread figure is not a divergence. The engine logs one CRITICAL line, `the venue's orders could not be read at startup -- N ledgered row(s) were never compared against venue truth; every plan is refused until the engine is restarted`, and each plan placed after it is journaled `refused` with the reason `the startup reconciliation could not read the venue's orders, so N ledgered row(s) were never compared against venue truth -- restart the engine to retry`, then deleted, which the ledger read shows. The remedy is that restart, inside the inter-cycle gap and with no Kraken margin position open ([the restart rule](#engine-restart-margin-position)); the new process reads again.

   **A row the pass cannot match to a venue order is marked `ambiguous`, never guessed at.** That is a row that recorded no txid — written before the engine recorded them, or a `submitting` row whose acceptance never reached the ledger — or one whose events record two txids that disagree, or one whose txid the venue read does not return. An open row takes the state `ambiguous`, the ledger's word for an order that may still be resting, and an `ambiguous` event naming why; a closed row with fills takes the event alone and keeps its state, since what is unestablished there is only whether the venue later withdrew a fill. A row already marked is not marked again, and nothing trips or refuses. The engine cannot manage an order it cannot identify — the pass cancels a resting order it can match to no row, and a fill on such an order is counted `unmatched` with no row write — so settle each marked row by hand:
```

with:

```markdown
   **An order that closed while the engine was down is read at the venue by its txid, in one read at startup.** The node's own startup reconciliation reads open orders only, so an order that filled, was canceled or expired during the downtime is in the engine's cache under no name. When a preserved row names such an order — an open row whose order no longer rests, or a closed row with fills, the kind a withdrawn fill lands on — the pass reads the venue's open and closed orders once, back to an hour before the earliest such row's boundary. It makes that read through a second client on the trade key, before it sends a cancel and before a plan can be picked up, and not at all when no row needs it; it needs the key's *Query Closed Orders & Trades* permission, which the node's own startup read of the trade history already needs. A report it finds for a row takes the same comparison a resting order's figure takes, described below.

   **A failed read of the venue's orders refuses every plan until the engine is restarted.** The rows that needed it are left exactly as they were, none of them is marked, and the kill switch is not tripped: an unread figure is not a divergence. The engine logs one CRITICAL line, `the venue's orders could not be read at startup -- N ledgered row(s) were never compared against venue truth; every plan is refused until the engine is restarted`, and each plan placed after it is journaled `refused` with the reason `the startup reconciliation could not read the venue's orders, so N ledgered row(s) were never compared against venue truth -- restart the engine to retry`, then deleted, which the ledger read shows. The remedy is that restart, inside the inter-cycle gap and with no Kraken margin position open beyond those [the restart rule](#engine-restart-margin-position)'s test admits; the new process reads again.

   **A row the pass cannot match to a venue order is marked `ambiguous`, never guessed at.** That is a row that recorded no txid — written before the engine recorded them, or a `submitting` row whose acceptance never reached the ledger — or one whose events record two txids that disagree, or one whose txid the venue read does not return. An open row takes the state `ambiguous`, the ledger's word for an order that may still be resting, and an `ambiguous` event naming why; a closed row with fills takes the event alone and keeps its state, since what is unestablished there is only whether the venue later withdrew a fill. A row already marked is not marked again, and nothing trips or refuses. The engine cannot manage an order it cannot identify — the pass cancels a resting order it can match to no row, and a fill on such an order is counted `unmatched` with no row write — so settle each marked row by hand:
```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
1. **The owner deletes the arm file**: `sudo rm /var/lib/zcrypto-engine/exec/armed`. This disarms immediately — no deploy, no restart, no engine downtime. Gate read → `level=none`, `reasons=arm_file_absent`.

2. **Converge `exec_armed` back to `false` the same day — not "eventually".** Between deleting the arm file and that converge the deployed config still says armed, so arming is effectively **one** key rather than two: anything that recreates a file at `/var/lib/zcrypto-engine/exec/armed` re-arms the engine with no review and no deploy. Revert the one line in `infra/ansible/roles/engine/templates/zcrypto.toml.j2` and converge with the same command as the arm step (same running digest, same inter-cycle gap). A Kraken margin position still open holds this converge until it is closed ([the restart rule](#engine-restart-margin-position)); step 1 has already disarmed the engine, and the one-key exposure above lasts until then. Read the preview: exactly one line changes back. **The changed line re-renders `zcrypto.toml`, so the handler restarts the engine and the deployed digest owes one clean boundary cycle again** -- at the next 4-hourly boundary, a `cycle-<HH>.json` whose `completed_at` falls inside `[B, B+30 min]` with no `failed-cycle-<HH>.json` beside it (no count command: the proof is a journal artifact on the engine host, and the reading of it is an operator act nothing in the tree records).

3. **Confirm both keys are down.** Gate read → `level=none` with `reasons=config_not_armed,arm_file_absent,restart_hold` — three reasons; the restart hold is back because the converge restarted the engine, and that is the correct resting state, so leave it. From the workstation, `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_armed{host="zcrypto"}'` reads `0`.
```

with:

```markdown
1. **The owner deletes the arm file**: `sudo rm /var/lib/zcrypto-engine/exec/armed`. This disarms immediately — no deploy, no restart, no engine downtime. Gate read → `level=none`, `reasons=arm_file_absent`.

2. **Converge `exec_armed` back to `false` the same day — not "eventually".** Between deleting the arm file and that converge the deployed config still says armed, so arming is effectively **one** key rather than two: anything that recreates a file at `/var/lib/zcrypto-engine/exec/armed` re-arms the engine with no review and no deploy. Revert the one line in `infra/ansible/roles/engine/templates/zcrypto.toml.j2` and converge with the same command as the arm step (same running digest, same inter-cycle gap). A Kraken margin position still open holds this converge until it is closed, unless [the restart rule](#engine-restart-margin-position)'s test admits it; step 1 has already disarmed the engine, and the one-key exposure above lasts until then. Read the preview: exactly one line changes back. **The changed line re-renders `zcrypto.toml`, so the handler restarts the engine and the deployed digest owes one clean boundary cycle again** -- at the next 4-hourly boundary, a `cycle-<HH>.json` whose `completed_at` falls inside `[B, B+30 min]` with no `failed-cycle-<HH>.json` beside it (no count command: the proof is a journal artifact on the engine host, and the reading of it is an operator act nothing in the tree records).

3. **Confirm both keys are down.** Gate read → `level=none` with `reasons=config_not_armed,arm_file_absent,restart_hold` — three reasons; the restart hold is back because the converge restarted the engine, and that is the correct resting state, so leave it. From the workstation, `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_armed{host="zcrypto"}'` reads `0`.
```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
1. **A window has journaled `full`.** Run the count in the probe-window procedure's verify step above. Every exec record written outside an armed window reads `level: "none"`, and the restart hold is written at every engine start and cleared only by hand (no count command: `evaluate` and `write_restart_hold` in `cli/engine/execgate.py` set `none` and latch the hold; nothing under `cli/` clears it) — so a week spent held reads `reduce_only` at best, and any week with a boundary below `full` is refused as `NOT SCORED` rather than scored. A week the engine could actually trade must be able to show 42 records reading `full`; if it cannot, the hold-clearing step is what changes, before any band is set.
2. **A band exists that real weeks have been measured against.** `uv run zcrypto engine tracking-report --journal-dir <pulled journal> --since <first day> --until <last day>` on the workstation prints each week's realized mean beside the floor the venue's own minimums impose. The band is a number chosen from those readings and recorded in `docs/research/14.phase6-decisions.md`, never one invented here (no count command: where a band's number came from is an owner's act nothing counts).
3. **The band is deployed as config.** `tracking_band_bps` is read from `[zcrypto.engine]` in the rendered `/opt/zcrypto-engine/zcrypto.toml`; the engine role's template does not render the key today, so arming means adding it there — one line, reviewed like the `exec_armed` line beside it — and converging inside a 4-hourly inter-cycle gap, with no Kraken margin position open ([the restart rule](#engine-restart-margin-position)). Verify by outcome at the next boundary: the tile moves off `DISARMED`, and `grafana-query.py` reads a number rather than `(no series)`.

Three standing conditions once it IS armed, each of which silently changes what a scored week means:
```

with:

```markdown
1. **A window has journaled `full`.** Run the count in the probe-window procedure's verify step above. Every exec record written outside an armed window reads `level: "none"`, and the restart hold is written at every engine start and cleared only by hand (no count command: `evaluate` and `write_restart_hold` in `cli/engine/execgate.py` set `none` and latch the hold; nothing under `cli/` clears it) — so a week spent held reads `reduce_only` at best, and any week with a boundary below `full` is refused as `NOT SCORED` rather than scored. A week the engine could actually trade must be able to show 42 records reading `full`; if it cannot, the hold-clearing step is what changes, before any band is set.
2. **A band exists that real weeks have been measured against.** `uv run zcrypto engine tracking-report --journal-dir <pulled journal> --since <first day> --until <last day>` on the workstation prints each week's realized mean beside the floor the venue's own minimums impose. The band is a number chosen from those readings and recorded in `docs/research/14.phase6-decisions.md`, never one invented here (no count command: where a band's number came from is an owner's act nothing counts).
3. **The band is deployed as config.** `tracking_band_bps` is read from `[zcrypto.engine]` in the rendered `/opt/zcrypto-engine/zcrypto.toml`; the engine role's template does not render the key today, so arming means adding it there — one line, reviewed like the `exec_armed` line beside it — and converging inside a 4-hourly inter-cycle gap, with no Kraken margin position open beyond those [the restart rule](#engine-restart-margin-position)'s test admits. Verify by outcome at the next boundary: the tile moves off `DISARMED`, and `grafana-query.py` reads a number rather than `(no series)`.

Three standing conditions once it IS armed, each of which silently changes what a scored week means:
```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
- **Disarm the band across a basket widening.** The trip demands every model leg's target in every record it reads, so the first record written under a wider basket makes every earlier one un-scoreable (no count command: `_stage` in `cli/engine/executor.py` refuses a record whose targets are not the model's legs). The refusal is the safe direction, but it lasts until the whole scored span post-dates the widening — a full week — and reads as a broken trip if nobody expects it.

**To disarm it** — remove the key and converge, under [the restart rule](#engine-restart-margin-position) like any converge. Nothing else clears it; the disarmed state is the absent key.

### Retire when
```

with:

```markdown
- **Disarm the band across a basket widening.** The trip demands every model leg's target in every record it reads, so the first record written under a wider basket makes every earlier one un-scoreable (no count command: `_stage` in `cli/engine/executor.py` refuses a record whose targets are not the model's legs). The refusal is the safe direction, but it lasts until the whole scored span post-dates the widening — a full week — and reads as a broken trip if nobody expects it.

**To disarm it** — remove the key and converge, under [the restart rule](#engine-restart-margin-position)'s test like any converge. Nothing else clears it; the disarmed state is the absent key.

### Retire when
```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown
- **The record names `orders_unread`, `positions_unreadable` or `position_unread`?** A read could not see everything, so the run ended at 2 whatever else it found. The ones taken before the cancel are in `snapshot_before.unread`, the final reads' among the `residuals`. `orders_unread`: the open-order read before the cancel failed, and the account-wide cancel went out regardless, reaching the orders nobody read. `positions_unreadable`: the whole-account position read failed and each basket pair was read on its own. `position_unread`: a basket pair whose own read failed, or one the listing does not carry. Which positions got a closer is not in these names: the closers are sized by a separate position read after the cancel, whose own per-pair misses the record does not list, and a basket position Kraken spells by its altname is not seen by a read taken pair by pair. The `error` beside each says why; a row on a pair the listing does not carry fails a whole read this way. Read Kraken's own Open Orders and Positions pages, close by hand what is still open there, then run it again.

6. **Do not clear the kill file to restart the engine until you have decided the reason no longer holds**, nor while a Kraken margin position is still open ([the restart rule](#engine-restart-margin-position)). Clearing it is the same procedure as for any other latched halt (no count command: every latch is the one `KILL_FILE` of `cli/engine/execgate.py`), in [`engine.md`](engine.md#zcrypto-engine-exec-kill-tripped).

<a name="flatten-read-only-dry-run"></a>
```

with:

```markdown
- **The record names `orders_unread`, `positions_unreadable` or `position_unread`?** A read could not see everything, so the run ended at 2 whatever else it found. The ones taken before the cancel are in `snapshot_before.unread`, the final reads' among the `residuals`. `orders_unread`: the open-order read before the cancel failed, and the account-wide cancel went out regardless, reaching the orders nobody read. `positions_unreadable`: the whole-account position read failed and each basket pair was read on its own. `position_unread`: a basket pair whose own read failed, or one the listing does not carry. Which positions got a closer is not in these names: the closers are sized by a separate position read after the cancel, whose own per-pair misses the record does not list, and a basket position Kraken spells by its altname is not seen by a read taken pair by pair. The `error` beside each says why; a row on a pair the listing does not carry fails a whole read this way. Read Kraken's own Open Orders and Positions pages, close by hand what is still open there, then run it again.

6. **Do not clear the kill file to restart the engine until you have decided the reason no longer holds**, nor while a Kraken margin position is open that [the restart rule](#engine-restart-margin-position)'s test does not admit. Clearing it is the same procedure as for any other latched halt (no count command: every latch is the one `KILL_FILE` of `cli/engine/execgate.py`), in [`engine.md`](engine.md#zcrypto-engine-exec-kill-tripped).

<a name="flatten-read-only-dry-run"></a>
```

Replace, in `infra/runbooks/engine-procedures.md`, this block:

```markdown

1. **After the engine converge that carries the wrapper, never before.** (no count command: the dry run's order against the converge is an operator act) `/usr/local/sbin/zcrypto-flatten` reaches the host with that converge and not earlier.
2. **With the engine running or stopped, and a NON-EUR spot balance the command can sell.** A dry run neither stops the unit nor reads whether it runs. Not while the engine is starting: its one startup read of the venue's orders is never retried, and a dry run on the same key can have it refused for its nonce, which refuses every plan until a restart. `spot_legs` skips the euro, skips a zero free balance, and skips a code it cannot resolve to a listed `/EUR` or `/BTC` pair — and the book read, the fifth shape, is made only for a leg. With no leg at all — nothing sellable and no margin position open — four of the five are proven while the row would say five. If the account has none, `infra/scripts/mint-with-vaulted-key.sh` mints one. It mints every ingredient the account is missing — the sellable balance, a resting order and a margin position — and there is no way to ask for only one (no count command: `spot_legs` in `cli/engine/flatten.py`; `infra/scripts/kraken-fixture-mint.py` takes `--pair` and `--execute` alone, with no cancel path), so read the printed plan for what it will actually send. Nothing unwinds them: the script has no cancel path, so the resting order and the position stay in the account until a real press closes them or someone closes them by hand on Kraken's own pages — and while that margin position is open the engine is neither converged nor restarted ([the restart rule](#engine-restart-margin-position)). It is attended, run from a workstation rather than on the host, and prints its plan without sending anything until `--execute` and a typed word; it places orders and cannot cancel them, so read the plan before confirming. The key it uses is IP-bound: `order-semantics-verification.md` section 1.3 adds the workstation's address and section 7.3 removes it again — the removal is mandatory, not an afterthought.
3. **On the engine host, through the wrapper:**

```

with:

```markdown

1. **After the engine converge that carries the wrapper, never before.** (no count command: the dry run's order against the converge is an operator act) `/usr/local/sbin/zcrypto-flatten` reaches the host with that converge and not earlier.
2. **With the engine running or stopped, and a NON-EUR spot balance the command can sell.** A dry run neither stops the unit nor reads whether it runs. Not while the engine is starting: its one startup read of the venue's orders is never retried, and a dry run on the same key can have it refused for its nonce, which refuses every plan until a restart. `spot_legs` skips the euro, skips a zero free balance, and skips a code it cannot resolve to a listed `/EUR` or `/BTC` pair — and the book read, the fifth shape, is made only for a leg. With no leg at all — nothing sellable and no margin position open — four of the five are proven while the row would say five. If the account has none, `infra/scripts/mint-with-vaulted-key.sh` mints one. It mints every ingredient the account is missing — the sellable balance, a resting order and a margin position — and there is no way to ask for only one (no count command: `spot_legs` in `cli/engine/flatten.py`; `infra/scripts/kraken-fixture-mint.py` takes `--pair` and `--execute` alone, with no cancel path), so read the printed plan for what it will actually send. Nothing unwinds them: the script has no cancel path, so the resting order and the position stay in the account until a real press closes them or someone closes them by hand on Kraken's own pages — and while that margin position is open the engine is neither converged nor restarted, since a position the mint opened is one the engine's cache never saw and [the restart rule](#engine-restart-margin-position)'s test refuses. It is attended, run from a workstation rather than on the host, and prints its plan without sending anything until `--execute` and a typed word; it places orders and cannot cancel them, so read the plan before confirming. The key it uses is IP-bound: `order-semantics-verification.md` section 1.3 adds the workstation's address and section 7.3 removes it again — the removal is mandatory, not an afterthought.
3. **On the engine host, through the wrapper:**

```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
1. **Read the full picture on the engine host**: `zcrypto engine exec-status`. `reasons` will list `kill_switch` alongside whatever else the gate is currently refusing on — the gauges alone cannot show this (no count command: `cli/engine/command.py`'s `_ExecGauges` publishes no `reasons`).
2. **If the switch was engaged deliberately and the reason still holds**, silence this alert in Grafana for the expected duration rather than letting it keep paging — its `for: 5m` is a pending period before the first page, not a re-arming clock: it stays firing for as long as the file exists and re-pages at the default notification policy's repeat interval (no count command: the rule in `infra/grafana/alerts.yaml` sets no `repeat_interval` of its own).
3. **If the reason no longer holds, remove the kill file on the engine host.** This clears within three minutes at most, with no deploy and no restart for a file placed by hand: the executor's next gate refresh within a minute, then a scrape and the rule's evaluation, a minute each. A file this process wrote on a trip also latches the process, which refuses each plan after it until a restart inside the inter-cycle gap with no Kraken margin position open ([the restart rule](engine-procedures.md#engine-restart-margin-position)) (no count command: `_GATE_REFRESH` in `cli/engine/executor.py` is the idle cadence).
   **One reason carries work you must finish first — a withdrawn fill.** If the reason reads *shows N filled at the venue, less than the M this engine recorded*, the venue has taken back a fill it already reported. Nothing is reversed on that path by design: the ledger keeps the quantity it recorded, so `held`, the fills counter, the fee counter and the position the ladder sizes against all still carry the withdrawn amount. Clearing the kill file is exactly what lets the engine size its next order — against that stale figure. **Reconcile the ledger against venue truth before you clear it.** No code path does this, which is why the file is cleared by hand: the operator who clears it owns the reconciliation.
4. **If you did not expect the kill switch to be engaged**, that is itself the finding — read the engine log for whatever wrote the file before removing it.
```

with:

```markdown
1. **Read the full picture on the engine host**: `zcrypto engine exec-status`. `reasons` will list `kill_switch` alongside whatever else the gate is currently refusing on — the gauges alone cannot show this (no count command: `cli/engine/command.py`'s `_ExecGauges` publishes no `reasons`).
2. **If the switch was engaged deliberately and the reason still holds**, silence this alert in Grafana for the expected duration rather than letting it keep paging — its `for: 5m` is a pending period before the first page, not a re-arming clock: it stays firing for as long as the file exists and re-pages at the default notification policy's repeat interval (no count command: the rule in `infra/grafana/alerts.yaml` sets no `repeat_interval` of its own).
3. **If the reason no longer holds, remove the kill file on the engine host.** This clears within three minutes at most, with no deploy and no restart for a file placed by hand: the executor's next gate refresh within a minute, then a scrape and the rule's evaluation, a minute each. A file this process wrote on a trip also latches the process, which refuses each plan after it until a restart inside the inter-cycle gap with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits (no count command: `_GATE_REFRESH` in `cli/engine/executor.py` is the idle cadence).
   **One reason carries work you must finish first — a withdrawn fill.** If the reason reads *shows N filled at the venue, less than the M this engine recorded*, the venue has taken back a fill it already reported. Nothing is reversed on that path by design: the ledger keeps the quantity it recorded, so `held`, the fills counter, the fee counter and the position the ladder sizes against all still carry the withdrawn amount. Clearing the kill file is exactly what lets the engine size its next order — against that stale figure. **Reconcile the ledger against venue truth before you clear it.** No code path does this, which is why the file is cleared by hand: the operator who clears it owns the reconciliation.
4. **If you did not expect the kill switch to be engaged**, that is itself the finding — read the engine log for whatever wrote the file before removing it.
```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
2. **If cycles ARE completing but this still fires**, the boundary sink's gate evaluation has been dropped from the cycle path — a code regression, not an infrastructure problem — or its exec record write has been failing at every boundary: the sink writes the record before it touches the gauges, so a write that raises starves this heartbeat by design, and `metrics sink raised for cycle …` in the engine log is that shape. The other five gate gauges on the board (`zcrypto_exec_gate_level`, `zcrypto_exec_armed`, `zcrypto_exec_kill_tripped`, `zcrypto_exec_restart_hold`, `zcrypto_exec_venue_ok`) keep moving on the executor's idle refresh, which publishes them with the heartbeat left alone, so they are live while the executor ticks, and `zcrypto engine exec-status` on the host reads the current state before you trust a tile; what is missing is the boundary's exec record, so read the engine journal on the host for the boundary's `exec-*.json` before trusting a window's ledger (set: the writes to the six gate gauges under `cli/` from outside `_ExecGauges.update`, whose one call publishes the five readings and, except on the idle refresh, the heartbeat; count: `infra/scripts/count-list.sh gate-gauge-writes-outside-the-publish-call`).
3. **Read the current state directly on the engine host**, never from the dashboard, while this is firing: `zcrypto engine exec-status`. It re-evaluates the gate on the spot rather than reading a possibly-stale published value, and it prints `reasons` — that field never reaches a gauge, so there is no dashboard reading it could otherwise be checked against (no count command: the read is an operator action nothing records; `cli/engine/command.py`'s `_ExecGauges` publishes no `reasons`).
4. **Restore evaluation** (a code fix and a redeploy, or a restart if the process itself has wedged without crashing, either one with no Kraken margin position open: [the restart rule](engine-procedures.md#engine-restart-margin-position)) and confirm the heartbeat panel starts advancing again before considering this resolved — the alert clears itself once a fresh sample lands.

### Retire when
```

with:

```markdown
2. **If cycles ARE completing but this still fires**, the boundary sink's gate evaluation has been dropped from the cycle path — a code regression, not an infrastructure problem — or its exec record write has been failing at every boundary: the sink writes the record before it touches the gauges, so a write that raises starves this heartbeat by design, and `metrics sink raised for cycle …` in the engine log is that shape. The other five gate gauges on the board (`zcrypto_exec_gate_level`, `zcrypto_exec_armed`, `zcrypto_exec_kill_tripped`, `zcrypto_exec_restart_hold`, `zcrypto_exec_venue_ok`) keep moving on the executor's idle refresh, which publishes them with the heartbeat left alone, so they are live while the executor ticks, and `zcrypto engine exec-status` on the host reads the current state before you trust a tile; what is missing is the boundary's exec record, so read the engine journal on the host for the boundary's `exec-*.json` before trusting a window's ledger (set: the writes to the six gate gauges under `cli/` from outside `_ExecGauges.update`, whose one call publishes the five readings and, except on the idle refresh, the heartbeat; count: `infra/scripts/count-list.sh gate-gauge-writes-outside-the-publish-call`).
3. **Read the current state directly on the engine host**, never from the dashboard, while this is firing: `zcrypto engine exec-status`. It re-evaluates the gate on the spot rather than reading a possibly-stale published value, and it prints `reasons` — that field never reaches a gauge, so there is no dashboard reading it could otherwise be checked against (no count command: the read is an operator action nothing records; `cli/engine/command.py`'s `_ExecGauges` publishes no `reasons`).
4. **Restore evaluation** (a code fix and a redeploy, or a restart if the process itself has wedged without crashing, either one with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits) and confirm the heartbeat panel starts advancing again before considering this resolved — the alert clears itself once a fresh sample lands.

### Retire when
```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
  **The cost, before you do it:** boundary cycles run at 00/04/08/12/16/20 UTC, and a boundary that passes with no journal artifact zeroes the ratified gate streak. A restart re-runs a missed boundary only within `[B, B+25 min]` and only while that boundary has no `cycle-<HH>.json` *or* `failed-cycle-<HH>.json`. Stopping just after a boundary is nearly free; stopping just before one costs the streak.

  Start it again with `sudo systemctl start zcrypto-engine` once `zcrypto_capture_reconnects_total{host="zcrypto"}` stops moving and no Kraken margin position is open ([the restart rule](engine-procedures.md#engine-restart-margin-position)), and read the next `cycle-<HH>.json` for `completed_at` inside `[B, B+30 min]` as the all-clear.

- **A single `Reconnecting`/`Reconnect succeeded` pair** with the venue quiet: note it and move on; the heartbeat did its job.
```

with:

```markdown
  **The cost, before you do it:** boundary cycles run at 00/04/08/12/16/20 UTC, and a boundary that passes with no journal artifact zeroes the ratified gate streak. A restart re-runs a missed boundary only within `[B, B+25 min]` and only while that boundary has no `cycle-<HH>.json` *or* `failed-cycle-<HH>.json`. Stopping just after a boundary is nearly free; stopping just before one costs the streak.

  Start it again with `sudo systemctl start zcrypto-engine` once `zcrypto_capture_reconnects_total{host="zcrypto"}` stops moving and no Kraken margin position is open that [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test does not admit, and read the next `cycle-<HH>.json` for `completed_at` inside `[B, B+30 min]` as the all-clear.

- **A single `Reconnecting`/`Reconnect succeeded` pair** with the venue quiet: note it and move on; the heartbeat did its job.
```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
- **The telemetry plane on the primary is dark.** The gauge is seeded at engine startup from the newest journal artifact (falling back to process start), so it is never legitimately absent while the engine runs (no count command: `cli/engine/command.py` sets it from `_seed_cycle_state` at startup); absence means the exporter or the whole plane is gone. `Fleet · Alloy dark — Capture primary` counts the host's series rather than reading this scrape's value, so the two rules do not cover each other.
- **The engine container is stopped or crash-looping.**
- **`run_cycle` raised before journaling the boundary**: a poisoned store, a disk error. The node survives it deliberately and logs `shadow node: run_cycle(<ts>) raised; the boundary stays journal-absent`. The dead-man behaves differently here: a success pings healthchecks.io, a sidecar pings `/fail`, and a *raising* cycle pings **nothing**, so a healthchecks.io alert with no preceding `/fail` reads "the node is up but a cycle raised; suspect the store". A traceback naming a pair, a grid, a bar and a close that is "not a finite positive number" comes from one of three doors: the refresh's own over the store file, when the same traceback names that file and `is not the frame the store readers join`, the sentence that refusal also carries for a stamp off the leg's grid, a null or repeated stamp and a frame whose shape the readers refuse; the same door over the REST fetch, when it names `the REST fetch for <pair>@<grid>` in place of a file, which is a row the venue itself carries and the venue's to answer -- nothing was written, the store is as it was, the next run fetches again, and no store repair or converge reaches it; and the snapshot write, when it names neither, the store readable and the refresh done. Each of the three raises before the boundary is journaled, the boundary's venue record excepted; a re-run refuses the same way at the two doors that read the store, and at the REST door for as long as the venue's answer carries that row -- the REST window reaches 720 bars back, about 120 days on the 4h grid and about two years on the daily -- with no bypass to wave it through, since a door waved through writes into the store the row it refused. The repair for the two doors that read the store is the store's, and on this host it is a re-delivery, not a seed: `zcrypto engine seed` runs on the workstation alone (the image carries no canonical dataset) and over an existing file it replaces a divergent tail inside the REST window and nothing older, so, with the unit still running and nothing on the host touched yet, repair that series in the workstation's `data/engine-store/` first (read the stamp the traceback names; a series moved aside there is re-copied from the canonical and gap-filled from REST by `zcrypto engine seed`, while the newest frozen sibling's last stamp lies inside the 4h REST window of about 120 days, else the next quarterly ingest is minted first; and a seed that refuses naming the REST fetch rather than a file is a row the venue itself carries, the venue's to answer, which writes nothing and which no store repair reaches); then stop the unit and move the store dir aside rather than deleting it (`sudo mv /var/lib/zcrypto-engine/store /var/lib/zcrypto-engine/store.aside-$(date -u +%Y%m%dT%H%MZ)`, beside it under the same owner; unversioned data has no undo, and the host's store is not replicated, so until the purge below the aside dir is the one copy of the pre-repair store, the file the refusal named being what a read of the cause opens), touching nothing else under `/var/lib/zcrypto-engine` (`exec/` stays as it is, so the procedures page's rule for a restored state directory is not entered), then take step 5's attended converge with the engine tag, `-e converge_primary=true` and `-e engine_image_digest=sha256:<digest>` (the full 64-hex value listed under `## Full digests` in `docs/reference/fleet-pins.md`, the one whose first twelve hex are the engine row's digest cell; the row's rollback operand is the previous image, not this one; the role asserts the digest before the store copy, so a converge without it aborts with the unit stopped), inside the inter-cycle gap, with no Kraken margin position open ([the restart rule](engine-procedures.md#engine-restart-margin-position)), and outside a published Kraken maintenance window checked immediately before (`.claude/rules/fleet-deploys.md`), so the role's copy for an absent store re-delivers it and the play starts the unit itself; then take the measurements the converge owes, step 6's all-clear by value the last of them, and purge the aside dir once the refused file has been read — on the host, or copied to the workstation for that read, since the all-clear reads the delivered store and not the aside copy — and that all-clear has landed (`sudo rm -r /var/lib/zcrypto-engine/store.aside-<stamp>`), naming the aside path and the purge in the commit that carries the converge's deploy-log row.

**A missed boundary is not recoverable once B+25 min has passed**, so that UTC day will not be clean and the gate's streak resets at the next day-close.
```

with:

```markdown
- **The telemetry plane on the primary is dark.** The gauge is seeded at engine startup from the newest journal artifact (falling back to process start), so it is never legitimately absent while the engine runs (no count command: `cli/engine/command.py` sets it from `_seed_cycle_state` at startup); absence means the exporter or the whole plane is gone. `Fleet · Alloy dark — Capture primary` counts the host's series rather than reading this scrape's value, so the two rules do not cover each other.
- **The engine container is stopped or crash-looping.**
- **`run_cycle` raised before journaling the boundary**: a poisoned store, a disk error. The node survives it deliberately and logs `shadow node: run_cycle(<ts>) raised; the boundary stays journal-absent`. The dead-man behaves differently here: a success pings healthchecks.io, a sidecar pings `/fail`, and a *raising* cycle pings **nothing**, so a healthchecks.io alert with no preceding `/fail` reads "the node is up but a cycle raised; suspect the store". A traceback naming a pair, a grid, a bar and a close that is "not a finite positive number" comes from one of three doors: the refresh's own over the store file, when the same traceback names that file and `is not the frame the store readers join`, the sentence that refusal also carries for a stamp off the leg's grid, a null or repeated stamp and a frame whose shape the readers refuse; the same door over the REST fetch, when it names `the REST fetch for <pair>@<grid>` in place of a file, which is a row the venue itself carries and the venue's to answer -- nothing was written, the store is as it was, the next run fetches again, and no store repair or converge reaches it; and the snapshot write, when it names neither, the store readable and the refresh done. Each of the three raises before the boundary is journaled, the boundary's venue record excepted; a re-run refuses the same way at the two doors that read the store, and at the REST door for as long as the venue's answer carries that row -- the REST window reaches 720 bars back, about 120 days on the 4h grid and about two years on the daily -- with no bypass to wave it through, since a door waved through writes into the store the row it refused. The repair for the two doors that read the store is the store's, and on this host it is a re-delivery, not a seed: `zcrypto engine seed` runs on the workstation alone (the image carries no canonical dataset) and over an existing file it replaces a divergent tail inside the REST window and nothing older, so, with the unit still running and nothing on the host touched yet, repair that series in the workstation's `data/engine-store/` first (read the stamp the traceback names; a series moved aside there is re-copied from the canonical and gap-filled from REST by `zcrypto engine seed`, while the newest frozen sibling's last stamp lies inside the 4h REST window of about 120 days, else the next quarterly ingest is minted first; and a seed that refuses naming the REST fetch rather than a file is a row the venue itself carries, the venue's to answer, which writes nothing and which no store repair reaches); then stop the unit and move the store dir aside rather than deleting it (`sudo mv /var/lib/zcrypto-engine/store /var/lib/zcrypto-engine/store.aside-$(date -u +%Y%m%dT%H%MZ)`, beside it under the same owner; unversioned data has no undo, and the host's store is not replicated, so until the purge below the aside dir is the one copy of the pre-repair store, the file the refusal named being what a read of the cause opens), touching nothing else under `/var/lib/zcrypto-engine` (`exec/` stays as it is, so the procedures page's rule for a restored state directory is not entered), then take step 5's attended converge with the engine tag, `-e converge_primary=true`, `-e engine_image_digest=sha256:<digest>` (the full 64-hex value listed under `## Full digests` in `docs/reference/fleet-pins.md`, the one whose first twelve hex are the engine row's digest cell; the row's rollback operand is the previous image, not this one; the role asserts the digest before the store copy, so a converge without it aborts with the unit stopped) and `-e cache_proxy_image_digest=sha256:<the running proxy digest>` (`sudo docker inspect --format '{{.Config.Image}}' zcrypto-cache-proxy`, the role's second digest guard), inside the inter-cycle gap, with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits, and outside a published Kraken maintenance window checked immediately before (`.claude/rules/fleet-deploys.md`), so the role's copy for an absent store re-delivers it and the play starts the unit itself; then take the measurements the converge owes, step 6's all-clear by value the last of them, and purge the aside dir once the refused file has been read — on the host, or copied to the workstation for that read, since the all-clear reads the delivered store and not the aside copy — and that all-clear has landed (`sudo rm -r /var/lib/zcrypto-engine/store.aside-<stamp>`), naming the aside path and the purge in the commit that carries the converge's deploy-log row.

**A missed boundary is not recoverable once B+25 min has passed**, so that UTC day will not be clean and the gate's streak resets at the next day-close.
```

Replace, in `infra/runbooks/engine.md`, this block:

````markdown
   ```
   A boundary with `snapshots/cycle-<HH>/` but no record raised **after** snapshotting (store or model side); a boundary with no `snapshots/cycle-<HH>/` of its own (the day's `snapshots/` holds the earlier boundaries') raised before its first snapshot file: a store the reader fails to open, a config fault, the refresh's own door refusing the store file or the REST fetch it merges -- the traceback naming that file, or `the REST fetch for <pair>@<grid>` in place of one, with `is not the frame the store readers join` -- or the snapshot write refusing a close the store holds at a present stamp, which the traceback step 2 greps names with its pair, grid, bar and value (the third bullet under *What it means* reads the three and holds the repair for each). A `failed-cycle-<HH>.json` present means this is not your alert: go to the failed-cycle section below.
4. **Restart only if the unit is down or the process is wedged, and only inside the inter-cycle gap, with no Kraken margin position open.** A unit that keeps restarting into `Unresolved positions during startup reconciliation … missing avg_px_open for position recovery` is failing on such a position, and a restart repeats the failure: [the restart rule](engine-procedures.md#engine-restart-margin-position) says how to end it. Nothing refuses a hand restart, so the reading is yours: the boundaries are 4-hourly from 00 UTC, the gap opens 5 min past the boundary cycle's journalled `completed_at` -- later than B+30 min when that cycle ran long, and B+30 min only when the journal is unreadable -- and closes 15 min before the next boundary, so `date -u` alone does not say the gap is open; read the boundary's `cycle-<HH>.json` for `completed_at` first (set: deploy-log rows whose `tags` include `engine`, since the last refine round closed for the first count; count: `infra/scripts/count-list.sh engine-rows-outside-the-gap`, and count: `infra/scripts/count-list.sh engine-rows-on-the-completion-floor` for the rows the log can only infer were admitted, a number to watch; whether the unit is down or wedged, and whether a margin position is open, are operator reads nothing records).
   ```
   sudo systemctl restart zcrypto-engine
   ```
   **`docker stop zcrypto-engine` does not stop the engine**: the unit is an attached `docker compose up` with `Restart=always`/`RestartSec=10`, so systemd brings it back ten seconds later; [`engine-data-socket-idle`](#engine-data-socket-idle) has the full treatment and the outage-time reasoning. If now is still within `[B, B+25 min]` and that boundary has no artifact, the restarted node re-runs it by itself; past that nothing catches up, and a `cycle --at` for a lapsed boundary lands outside the 30-minute window, so the day stays unclean either way.
5. **A converge is a separate, attended decision** (`.claude/rules/fleet-deploys.md`): the engine play needs `-e converge_primary=true` and re-asserts the inter-cycle window, and it restarts the live trade engine, so it waits while a Kraken margin position is open ([the restart rule](engine-procedures.md#engine-restart-margin-position)). Never run `site.yml` un-tagged on the primary (set: deploy-log rows with `limit == "zcrypto"`; count: `infra/scripts/count-list.sh un-tagged-primary-runs`).
6. **All-clear by value**: the next `cycle-<HH>.json` lands with `completed_at` inside `[B, B+30 min]`, and `uv run python infra/scripts/grafana-query.py 'time() - zcrypto_engine_cycle_completed_at_seconds{host="zcrypto"}'` drops below 1800.

````

with:

````markdown
   ```
   A boundary with `snapshots/cycle-<HH>/` but no record raised **after** snapshotting (store or model side); a boundary with no `snapshots/cycle-<HH>/` of its own (the day's `snapshots/` holds the earlier boundaries') raised before its first snapshot file: a store the reader fails to open, a config fault, the refresh's own door refusing the store file or the REST fetch it merges -- the traceback naming that file, or `the REST fetch for <pair>@<grid>` in place of one, with `is not the frame the store readers join` -- or the snapshot write refusing a close the store holds at a present stamp, which the traceback step 2 greps names with its pair, grid, bar and value (the third bullet under *What it means* reads the three and holds the repair for each). A `failed-cycle-<HH>.json` present means this is not your alert: go to the failed-cycle section below.
4. **Restart only if the unit is down or the process is wedged, and only inside the inter-cycle gap, with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits.** A unit that keeps restarting into `Unresolved positions during startup reconciliation … missing avg_px_open for position recovery` is failing on a position the cache never saw, and a restart repeats the failure: the restart rule says how to end it; one restarting into `failed to create cache database backing` is failing on its cache proxy routing no backend, and a restart repeats that too — [`cache.md#zcrypto-cache-proxy-no-backend`](cache.md#zcrypto-cache-proxy-no-backend) is the incident, and `-e engine_cache_enabled=false` on a re-converge with the running digests is the start without the cache. Nothing refuses a hand restart, so the reading is yours: the boundaries are 4-hourly from 00 UTC, the gap opens 5 min past the boundary cycle's journalled `completed_at` -- later than B+30 min when that cycle ran long, and B+30 min only when the journal is unreadable -- and closes 15 min before the next boundary, so `date -u` alone does not say the gap is open; read the boundary's `cycle-<HH>.json` for `completed_at` first (set: deploy-log rows whose `tags` include `engine`, since the last refine round closed for the first count; count: `infra/scripts/count-list.sh engine-rows-outside-the-gap`, and count: `infra/scripts/count-list.sh engine-rows-on-the-completion-floor` for the rows the log can only infer were admitted, a number to watch; whether the unit is down or wedged, and whether a margin position is open, are operator reads nothing records).
   ```
   sudo systemctl restart zcrypto-engine
   ```
   **`docker stop zcrypto-engine` does not stop the engine**: the unit is an attached `docker compose up` with `Restart=always`/`RestartSec=10`, so systemd brings it back ten seconds later; [`engine-data-socket-idle`](#engine-data-socket-idle) has the full treatment and the outage-time reasoning. If now is still within `[B, B+25 min]` and that boundary has no artifact, the restarted node re-runs it by itself; past that nothing catches up, and a `cycle --at` for a lapsed boundary lands outside the 30-minute window, so the day stays unclean either way.
5. **A converge is a separate, attended decision** (`.claude/rules/fleet-deploys.md`): the engine play needs `-e converge_primary=true` and re-asserts the inter-cycle window, and it restarts the live trade engine, so it waits while a Kraken margin position is open that [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test does not admit. Never run `site.yml` un-tagged on the primary (set: deploy-log rows with `limit == "zcrypto"`; count: `infra/scripts/count-list.sh un-tagged-primary-runs`).
6. **All-clear by value**: the next `cycle-<HH>.json` lands with `completed_at` inside `[B, B+30 min]`, and `uv run python infra/scripts/grafana-query.py 'time() - zcrypto_engine_cycle_completed_at_seconds{host="zcrypto"}'` drops below 1800.

````

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
   - **`metrics sink raised …`**: the record and its artifact were already written before the sink ran, so nothing about the cycle is in doubt, though the sink writes the boundary's `exec-<HH>.json` first and a raise there costs that ledger record (no count command: `cli/engine/command.py::_make_exec_sink` writes it before the gauges).
   - **`cancel of adopted order … was REJECTED by the venue`**: the venue refused the startup pass's, or a kill trip's, cancel of an order this process adopted, and the cancel is not re-sent; its intent, where the pass wrote it, reads `revoked` already, and the order may still rest; absent from Kraken's open orders, the venue had already ended it. Cancel it by hand on Kraken's open-orders page where it rests, and read the row's `filled_qty` for what filled before that; no disarm is owed for this line alone (no count command: the line is `_venue_terminal_state`'s in `cli/engine/executor.py`, and the venue's refusal is the venue's act).
   - **`the re-read pass could not read the ledger or the venue on 3 ticks …`**, **`the re-read pass's cancel of … raised or was refused`** or **`the re-cancel of … could not be journaled`**: the executor's re-read pass — run on its next tick with nothing in flight after a socket's return, or after a terminal it minted with no socket held down — re-reads at the venue each row it minted terminal and cancels what still rests, and could not read on three ticks or could not cancel; the order may still rest at Kraken, its row open — `ambiguous`, or `accepted` where the mint landed after the ack deadline stranded the intent. Cancel it by hand on Kraken's open-orders page; a restart — inside the inter-cycle gap and with no Kraken margin position open, [the restart rule](engine-procedures.md#engine-restart-margin-position) — has its startup pass read the row too (the `revoked` outcome's paragraph under [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) names the window). The third line is the pass's cancel returning and the row write after it failing: the order is cancelled at Kraken and its row still open; read the row against Kraken's closed orders, and the pass's next arm or a startup inside the re-attach window settles it. The read's line names each row it could not read for, `<id> (Kraken <txid>)`, and names none when the ledger itself could not be read: the open row's txid is then in the probe window's ledger read. The sweep's other CRITICAL lines, which the pass shares with the startup — an order the venue read has none for, logged once by the pass and on every startup inside the window, a row that could not be reconciled or journaled, a trip — take the execution-path class below. A row the pass did close reads `canceled` with a `recancelled` event, and is read against Kraken's closed orders and positions: the cancel's answer is not read, so a fill between the pass's read and its cancel reaches the row when the stream delivers it, credited with what the Cache holds beyond the row, less than the fill where the cut's own fills did not reach the stream — on an order the startup pass adopted it can then complete the row `filled` — and is on Kraken's page alone when it does not. No disarm is owed for these lines alone (no count command: the lines are `_reread_pass`'s and `_recancel`'s in `cli/engine/executor.py`, and the venue's answer is the venue's act).
   - **Anything naming the executor, an order, a fill, the ledger, or the kill switch is the execution path, and it is the one to act on now.** Continue at step 3.
3. **An execution-path error while ARMED is a live money situation.** Read the gate on the host, which prints `reasons` live; it never reaches a gauge, and `zcrypto_exec_armed` conflates the two arming keys into one gauge (no count command: `cli/engine/command.py`'s `_ExecGauges` publishes no `reasons` and ANDs the two keys):
```

with:

```markdown
   - **`metrics sink raised …`**: the record and its artifact were already written before the sink ran, so nothing about the cycle is in doubt, though the sink writes the boundary's `exec-<HH>.json` first and a raise there costs that ledger record (no count command: `cli/engine/command.py::_make_exec_sink` writes it before the gauges).
   - **`cancel of adopted order … was REJECTED by the venue`**: the venue refused the startup pass's, or a kill trip's, cancel of an order this process adopted, and the cancel is not re-sent; its intent, where the pass wrote it, reads `revoked` already, and the order may still rest; absent from Kraken's open orders, the venue had already ended it. Cancel it by hand on Kraken's open-orders page where it rests, and read the row's `filled_qty` for what filled before that; no disarm is owed for this line alone (no count command: the line is `_venue_terminal_state`'s in `cli/engine/executor.py`, and the venue's refusal is the venue's act).
   - **`the re-read pass could not read the ledger or the venue on 3 ticks …`**, **`the re-read pass's cancel of … raised or was refused`** or **`the re-cancel of … could not be journaled`**: the executor's re-read pass — run on its next tick with nothing in flight after a socket's return, or after a terminal it minted with no socket held down — re-reads at the venue each row it minted terminal and cancels what still rests, and could not read on three ticks or could not cancel; the order may still rest at Kraken, its row open — `ambiguous`, or `accepted` where the mint landed after the ack deadline stranded the intent. Cancel it by hand on Kraken's open-orders page; a restart — inside the inter-cycle gap and with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits — has its startup pass read the row too (the `revoked` outcome's paragraph under [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) names the window). The third line is the pass's cancel returning and the row write after it failing: the order is cancelled at Kraken and its row still open; read the row against Kraken's closed orders, and the pass's next arm or a startup inside the re-attach window settles it. The read's line names each row it could not read for, `<id> (Kraken <txid>)`, and names none when the ledger itself could not be read: the open row's txid is then in the probe window's ledger read. The sweep's other CRITICAL lines, which the pass shares with the startup — an order the venue read has none for, logged once by the pass and on every startup inside the window, a row that could not be reconciled or journaled, a trip — take the execution-path class below. A row the pass did close reads `canceled` with a `recancelled` event, and is read against Kraken's closed orders and positions: the cancel's answer is not read, so a fill between the pass's read and its cancel reaches the row when the stream delivers it, credited with what the Cache holds beyond the row, less than the fill where the cut's own fills did not reach the stream — on an order the startup pass adopted it can then complete the row `filled` — and is on Kraken's page alone when it does not. No disarm is owed for these lines alone (no count command: the lines are `_reread_pass`'s and `_recancel`'s in `cli/engine/executor.py`, and the venue's answer is the venue's act).
   - **`RuntimeError: failed to create cache database backing`** under `unhandled exception -- aborting`: the node's `run()` could not open its cache backing — the cache proxy routing no backend, or the set unreachable — and the unit restarts into the same failure ten seconds on, so no start succeeds until the route is back: [`cache.md#zcrypto-cache-proxy-no-backend`](cache.md#zcrypto-cache-proxy-no-backend) is the incident, and an engine that must run before then takes a re-converge with the running digests and `-e engine_cache_enabled=false`, a start without the cache (no count command: the raise is the library's, logged by `cli/__main__.py`'s catch-all).
   - **Anything naming the executor, an order, a fill, the ledger, or the kill switch is the execution path, and it is the one to act on now.** Continue at step 3.
3. **An execution-path error while ARMED is a live money situation.** Read the gate on the host, which prints `reasons` live; it never reaches a gauge, and `zcrypto_exec_armed` conflates the two arming keys into one gauge (no count command: `cli/engine/command.py`'s `_ExecGauges` publishes no `reasons` and ANDs the two keys):
```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
   That disarms immediately (no deploy, no restart, no engine downtime) and the gate then reads `level=none`, `reasons=arm_file_absent`. **Removing the arm file is only the first key.** The deployed config still says armed until `exec_armed` is converged back to `false`, which [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) requires the same day; do the converge as that procedure describes, inside the inter-cycle gap.
4. **Then reconcile what actually happened at the venue**: the exec ledger's `exec-<HH>.json` records for every boundary the window spans (the ledger read in `engine-procedures.md` prints them by value), and `zcrypto_exec_orders_total{outcome="submitted"}` on the Engine board as the fast read (no count command: a reconciliation is an operator action nothing records). The ledger is the authority.
5. **Do not restart on an ERROR line alone.** Restart only when the node loop itself is wedged (no completion at the next boundary), and then only inside the inter-cycle gap and with no Kraken margin position open ([the restart rule](engine-procedures.md#engine-restart-margin-position)) (set: deploy-log rows whose `tags` include `engine`, since the last refine round closed; count: `infra/scripts/count-list.sh engine-rows-outside-the-gap`; whether the loop is wedged, and whether a margin position is open, are operator reads nothing records).
6. **The same message every boundary is a defect, not an incident to re-triage.** Capture the message and put the work where work lives; this runbook is not the backlog (no count command: the classification is an operator judgement nothing records).

```

with:

```markdown
   That disarms immediately (no deploy, no restart, no engine downtime) and the gate then reads `level=none`, `reasons=arm_file_absent`. **Removing the arm file is only the first key.** The deployed config still says armed until `exec_armed` is converged back to `false`, which [`engine-procedures.md#engine-probe-window`](engine-procedures.md#engine-probe-window) requires the same day; do the converge as that procedure describes, inside the inter-cycle gap.
4. **Then reconcile what actually happened at the venue**: the exec ledger's `exec-<HH>.json` records for every boundary the window spans (the ledger read in `engine-procedures.md` prints them by value), and `zcrypto_exec_orders_total{outcome="submitted"}` on the Engine board as the fast read (no count command: a reconciliation is an operator action nothing records). The ledger is the authority.
5. **Do not restart on an ERROR line alone.** Restart only when the node loop itself is wedged (no completion at the next boundary), and then only inside the inter-cycle gap and with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits (set: deploy-log rows whose `tags` include `engine`, since the last refine round closed; count: `infra/scripts/count-list.sh engine-rows-outside-the-gap`; whether the loop is wedged, and whether a margin position is open, are operator reads nothing records).
6. **The same message every boundary is a defect, not an incident to re-triage.** Capture the message and put the work where work lives; this runbook is not the backlog (no count command: the classification is an operator judgement nothing records).

```

Replace, in `infra/runbooks/engine.md`, this block:

```markdown
   A non-zero count means the process is logging and the shipper is what failed; the ship handler's own failures are visible locally only (no count command: the ship handler hands its own failures to `logging.Handler.handleError` at `cli/logging/ship.py:118`, whose stderr write is the stdlib's and reaches no shipper). **Print that count before trusting any conclusion drawn from an empty grep.**
4. **Check whether capture went dark with it.** Both `zcrypto-capture-log-dead-primary` and this rule firing ⇒ the host's push path or Grafana Cloud, not the engine; the two services read Loki creds from the same rendered file. Engine alone ⇒ the engine container or its env.
5. **A credential fix is a converge, never a hand edit**: the engine's Loki env comes from the render, and the file is read at container create, so a rotated token needs the role's converge. That is attended, needs `-e converge_primary=true`, and runs inside the inter-cycle gap only, with no Kraken margin position open ([the restart rule](engine-procedures.md#engine-restart-margin-position)) (set: deploy-log rows whose `tags` include `engine`, since the last refine round closed; count: `infra/scripts/count-list.sh engine-rows-outside-the-gap`; a hand edit is an operator action nothing records, and whether a margin position is open an operator read nothing records).
6. **All-clear by value**: after the next boundary's burst, the rule's own query returns a count above 0, the threshold being `< 1`: `sum by (host) (count_over_time({host="zcrypto", container="engine", level=~".+"} [6h]))`. Confirm the number; an empty result is not a zero.

```

with:

```markdown
   A non-zero count means the process is logging and the shipper is what failed; the ship handler's own failures are visible locally only (no count command: the ship handler hands its own failures to `logging.Handler.handleError` at `cli/logging/ship.py:118`, whose stderr write is the stdlib's and reaches no shipper). **Print that count before trusting any conclusion drawn from an empty grep.**
4. **Check whether capture went dark with it.** Both `zcrypto-capture-log-dead-primary` and this rule firing ⇒ the host's push path or Grafana Cloud, not the engine; the two services read Loki creds from the same rendered file. Engine alone ⇒ the engine container or its env.
5. **A credential fix is a converge, never a hand edit**: the engine's Loki env comes from the render, and the file is read at container create, so a rotated token needs the role's converge. That is attended, needs `-e converge_primary=true`, and runs inside the inter-cycle gap only, with no Kraken margin position open beyond those [the restart rule](engine-procedures.md#engine-restart-margin-position)'s test admits (set: deploy-log rows whose `tags` include `engine`, since the last refine round closed; count: `infra/scripts/count-list.sh engine-rows-outside-the-gap`; a hand edit is an operator action nothing records, and whether a margin position is open an operator read nothing records).
6. **All-clear by value**: after the next boundary's burst, the rule's own query returns a count above 0, the threshold being `< 1`: `sum by (host) (count_over_time({host="zcrypto", container="engine", level=~".+"} [6h]))`. Confirm the number; an empty result is not a zero.

```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
- **Never induce inside a published Kraken maintenance window.** Read `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json` at planning time and again immediately before each induction; an empty feed is never evidence the window is clear (no count command: `converges-inside-a-kraken-window` reads deploy-log rows, and an induction is not one). Which entries count is the same standing rule in [`drills-telemetry.md`](drills-telemetry.md) and the converge bullet of `.claude/rules/fleet-deploys.md`.
- **A drill whose instrument is not on the host is `blocked`, never `fail`** (no count command: `tests/test_drill_log.py` reads a heading's status, not the body under it). Both instruments are in the tree: the `rest-hold` plan mode (`cli/engine/probeplan.py`'s `MODES`), an order priced `offset_pct` passive of the touch, deliberately not cancelled on the venue's acknowledgement and resting for its declared `hold_minutes`, which `rest-cancel` cannot give; and Drill B's flatten command (`cli/engine/flatten.py`), whose procedure is [`engine-procedures.md#engine-flatten`](engine-procedures.md#engine-flatten). Whether the engine host is running them is the engine row of `docs/reference/fleet-pins.md`, read at drill time. Each affected drill states its own gap in its *Preconditions*. Never run with a substitute plan mode: an order cancelled a second after it was placed exercises none of what these drills measure. The first live rest-hold order will be a drill's: `docs/open-topics/T0018-phase6-build-sequence.md` records that none has been placed.
- **No drill starts, restarts or converges the engine with a Kraken margin position open while the engine's build lacks upstream #5065** ([`engine-procedures.md#engine-restart-margin-position`](engine-procedures.md#engine-restart-margin-position)): that start fails and the container restarts into the same failure, or it boots with the position's entry price at 0. A2 lands there by design, since its fill opens a leveraged position while the host is down, so A2 is recorded `blocked` with that reason until the engine runs such a build (no count command: `tests/test_drill_log.py` reads a heading's status, not the body under it). D's restore, and a restart after another drill's leveraged order filled, wait until the position is closed, by B or by hand on Kraken.
- **One induction at a time. Revert it and verify the revert by value before the next one starts.** An instrument is never widened (no count command: it lands in a drill-log body, which `tests/test_drill_log.py` does not read): each *Induce* names exactly what to do, and anything heavier is a different act with a different blast radius (the same rule in `drills-telemetry.md`).
- **A start or a reboot moves the `.State.StartedAt` of every container it touches, which is what a `since` cell of [`fleet-pins.md`](../../docs/reference/fleet-pins.md) records — re-true every row it moved, with the revert** (no count command: a drill entry's *operator action* clause is prose). One `docker inspect <name> --format '{{.State.StartedAt}}'` per row is the whole cost; skipped, the cell keeps a value the container no longer has and no later reader can tell it from a converge-clock value.
```

with:

```markdown
- **Never induce inside a published Kraken maintenance window.** Read `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json` at planning time and again immediately before each induction; an empty feed is never evidence the window is clear (no count command: `converges-inside-a-kraken-window` reads deploy-log rows, and an induction is not one). Which entries count is the same standing rule in [`drills-telemetry.md`](drills-telemetry.md) and the converge bullet of `.claude/rules/fleet-deploys.md`.
- **A drill whose instrument is not on the host is `blocked`, never `fail`** (no count command: `tests/test_drill_log.py` reads a heading's status, not the body under it). Both instruments are in the tree: the `rest-hold` plan mode (`cli/engine/probeplan.py`'s `MODES`), an order priced `offset_pct` passive of the touch, deliberately not cancelled on the venue's acknowledgement and resting for its declared `hold_minutes`, which `rest-cancel` cannot give; and Drill B's flatten command (`cli/engine/flatten.py`), whose procedure is [`engine-procedures.md#engine-flatten`](engine-procedures.md#engine-flatten). Whether the engine host is running them is the engine row of `docs/reference/fleet-pins.md`, read at drill time. Each affected drill states its own gap in its *Preconditions*. Never run with a substitute plan mode: an order cancelled a second after it was placed exercises none of what these drills measure. The first live rest-hold order will be a drill's: `docs/open-topics/T0018-phase6-build-sequence.md` records that none has been placed.
- **No drill starts, restarts or converges the engine with a Kraken margin position open that the restart rule's test does not admit** ([`engine-procedures.md#engine-restart-margin-position`](engine-procedures.md#engine-restart-margin-position)): the test admits a position the engine's last boot line counted as restored, or one this engine opened after that boot, with no cache outage fired since and no restored order filled since; every other one — opened by hand, or by an order the cache never held — fails the start and the container restarts into the same failure, or boots with the position's entry price at 0, while the engine's build lacks upstream #5065. A2's fill opens a leveraged position while the host is down on an order this engine placed, which the test admits once the cache's live proof has read clean, so A2 is recorded `blocked` until that proof or such a build (no count command: `tests/test_drill_log.py` reads a heading's status, not the body under it). D's restore, and a restart after another drill's leveraged order filled, wait until the position is closed, by B or by hand on Kraken, unless the test admits it.
- **One induction at a time. Revert it and verify the revert by value before the next one starts.** An instrument is never widened (no count command: it lands in a drill-log body, which `tests/test_drill_log.py` does not read): each *Induce* names exactly what to do, and anything heavier is a different act with a different blast radius (the same rule in `drills-telemetry.md`).
- **A start or a reboot moves the `.State.StartedAt` of every container it touches, which is what a `since` cell of [`fleet-pins.md`](../../docs/reference/fleet-pins.md) records — re-true every row it moved, with the revert** (no count command: a drill entry's *operator action* clause is prose). One `docker inspect <name> --format '{{.State.StartedAt}}'` per row is the whole cost; skipped, the cell keeps a value the container no longer has and no later reader can tell it from a converge-clock value.
```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
### Preconditions

- **Recorded `blocked` under the restart rule in the standing rules until the engine runs a nautilus-trader build carrying upstream #5065**: the fill lands while the host is down, so the host's return is an engine start with a margin position open.
- A1's preconditions in full, with one difference: the plan is priced marketable, so a fill is expected rather than avoided. That is real money at probe size, and it leaves a real position open.
- **Know before you start that `matched` will read 0 here, and that this is not a finding.** A fill applied during the node's own startup reconciliation is published before the adopt pass has attached a single row, so it counts `unmatched` by design. The by-value `zcrypto_exec_external_events_total{disposition="matched"}` reading that proves a restart re-attaches a row by the Kraken txid it recorded belongs to G, where the cancel ack arrives after the rows are attached.
```

with:

```markdown
### Preconditions

- **Recorded `blocked` under the restart rule in the standing rules until the engine runs a nautilus-trader build carrying upstream #5065 or the cache's live proof has read clean**: the fill lands while the host is down on an order this engine placed, so the host's return is an engine start with a margin position open, one the restart rule's test admits once the proof is in.
- A1's preconditions in full, with one difference: the plan is priced marketable, so a fill is expected rather than avoided. That is real money at probe size, and it leaves a real position open.
- **Know before you start that `matched` will read 0 here, and that this is not a finding.** A fill applied during the node's own startup reconciliation is published before the adopt pass has attached a single row, so it counts `unmatched` by design. The by-value `zcrypto_exec_external_events_total{disposition="matched"}` reading that proves a restart re-attaches a row by the Kraken txid it recorded belongs to G, where the cancel ack arrives after the rows are attached.
```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
### Preconditions

- **A real margin position open, opened for this drill by a funded leveraged `execute` plan the owner places in the window while the engine runs**, read by value from the ledger and from venue truth immediately before. A2's end state was this input, and A2 is `blocked` under the restart rule in the standing rules. Not the probe window's own open-plan positions: their later steps close them through the engine, and D's restore waits for the position to close. A flat account cannot trip this rule (no count command: its `$A > 0 && $B < 1` condition in `infra/grafana/alerts.yaml` holds it) and the run would be `blocked`.
- The window attended and the phone in hand; the page arriving is the deliverable, not the rule's internal state.
- **The telemetry plane read green by value immediately before**, because this rule fires on two routes and only one of them is this drill's (no count command: the rule's `B` node in `infra/grafana/alerts.yaml` carries both; D's *Induce* takes one):
```

with:

```markdown
### Preconditions

- **A real margin position open, opened for this drill by a funded leveraged `execute` plan the owner places in the window while the engine runs**, read by value from the ledger and from venue truth immediately before. A2's end state was this input, and A2 is `blocked` under the restart rule in the standing rules until either of its lifts. Not the probe window's own open-plan positions: their later steps close them through the engine, and D's restore waits for the position to close, or for the restart rule's test to admit it. A flat account cannot trip this rule (no count command: its `$A > 0 && $B < 1` condition in `infra/grafana/alerts.yaml` holds it) and the run would be `blocked`.
- The window attended and the phone in hand; the page arriving is the deliverable, not the rule's internal state.
- **The telemetry plane read green by value immediately before**, because this rule fires on two routes and only one of them is this drill's (no count command: the rule's `B` node in `infra/grafana/alerts.yaml` carries both; D's *Induce* takes one):
```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

````markdown
**The drill is what the responder does with the page, so work it from the page and not from here.** Open [`engine.md#zcrypto-engine-dark-with-exposure`](engine.md#zcrypto-engine-dark-with-exposure) from the notification, on the phone, and follow it from the top: ruling out the plane first, then reading the engine directly, and only then reaching for B. Whether the responder stops at the discriminator or reaches B is the finding; prompting them from this page destroys it.

Then restore, once the position is closed — by B, or by hand on Kraken — while the engine's build lacks upstream #5065 (the restart rule in the standing rules):

```
````

with:

````markdown
**The drill is what the responder does with the page, so work it from the page and not from here.** Open [`engine.md#zcrypto-engine-dark-with-exposure`](engine.md#zcrypto-engine-dark-with-exposure) from the notification, on the phone, and follow it from the top: ruling out the plane first, then reading the engine directly, and only then reaching for B. Whether the responder stops at the discriminator or reaches B is the finding; prompting them from this page destroys it.

Then restore, once the position is closed — by B, or by hand on Kraken — or once the restart rule's test admits it (the standing rules):

```
````

Replace, in `infra/runbooks/drills-order-path.md`, this block:

```markdown
2. **Reconnect**: `sudo docker network connect <the network> zcrypto-engine`, then `up{job="engine_app",host="zcrypto"}` back at 1 by value.
3. **Read the engine log for the re-cancel, then Kraken's open orders by hand.** On its first tick after `Reconnect succeeded` with nothing in flight, the executor's re-read pass reads the venue for the row the mint closed and cancels the order by its txid on the bare client, logging `re-cancelled <id> (Kraken <txid>) -- it rested at Kraken (<status>) after a terminal this engine minted`; Kraken's open orders then no longer carry it. The row reads `canceled` with a `recancelled` event, and the intent stays `ambiguous`: it was terminal at the mint, and the row is the re-cancel's record. Read a `recancelled` row against Kraken's closed orders and the positions page: the cancel's answer is not read, so a fill landing between the pass's read and its cancel closes the row `canceled` all the same, and reaches the row — a `fill` line after the `recancelled` event, credited with what the Cache holds beyond the row, which is less than the fill where the cut's own fills did not reach the stream — when the stream delivers it, and is on Kraken's page alone when it does not. A hand-placed kill file still sweeps nothing on this path.
4. **Clear it deliberately when the pass did not.** A CRITICAL `the re-read pass could not read the ledger or the venue on 3 ticks` or `the re-read pass's cancel of <id> raised or was refused` line means the order may still rest, and so does the pass's own line missing three ticks after `Reconnect succeeded`. A direct cancel in the Kraken web UI always works (no count command: the venue's behaviour). A restart inside the inter-cycle gap works too: its adopt pass finds the order's row by the Kraken txid the row recorded and cancels the opener, logging `canceling adopted resting order <txid>`. If the boot logs the CRITICAL `ledgered order <id> (Kraken <txid>) rests at Kraken (<status>) …` line instead, the node's startup reconciliation dropped the order and the restart did not cancel it: cancel it on Kraken's page. Read Kraken's positions page before taking that route: if the order filled, a margin position is open and the restart waits for it to close (the restart rule in the standing rules). Note the wall-clock time it rested, from the disconnect to the cancel.

"The order dies with the socket" is re-cancel-on-reconnect, delivered by the executor's re-read pass<!-- T0018 -->: this drill measures it — the time from `Reconnect succeeded` to the pass's line, and to the order leaving Kraken's open orders — and records a pass whose line did not come as the finding it is.
```

with:

```markdown
2. **Reconnect**: `sudo docker network connect <the network> zcrypto-engine`, then `up{job="engine_app",host="zcrypto"}` back at 1 by value.
3. **Read the engine log for the re-cancel, then Kraken's open orders by hand.** On its first tick after `Reconnect succeeded` with nothing in flight, the executor's re-read pass reads the venue for the row the mint closed and cancels the order by its txid on the bare client, logging `re-cancelled <id> (Kraken <txid>) -- it rested at Kraken (<status>) after a terminal this engine minted`; Kraken's open orders then no longer carry it. The row reads `canceled` with a `recancelled` event, and the intent stays `ambiguous`: it was terminal at the mint, and the row is the re-cancel's record. Read a `recancelled` row against Kraken's closed orders and the positions page: the cancel's answer is not read, so a fill landing between the pass's read and its cancel closes the row `canceled` all the same, and reaches the row — a `fill` line after the `recancelled` event, credited with what the Cache holds beyond the row, which is less than the fill where the cut's own fills did not reach the stream — when the stream delivers it, and is on Kraken's page alone when it does not. A hand-placed kill file still sweeps nothing on this path.
4. **Clear it deliberately when the pass did not.** A CRITICAL `the re-read pass could not read the ledger or the venue on 3 ticks` or `the re-read pass's cancel of <id> raised or was refused` line means the order may still rest, and so does the pass's own line missing three ticks after `Reconnect succeeded`. A direct cancel in the Kraken web UI always works (no count command: the venue's behaviour). A restart inside the inter-cycle gap works too: its adopt pass finds the order's row by the Kraken txid the row recorded and cancels the opener, logging `canceling adopted resting order <txid>`. If the boot logs the CRITICAL `ledgered order <id> (Kraken <txid>) rests at Kraken (<status>) …` line instead, the node's startup reconciliation dropped the order and the restart did not cancel it: cancel it on Kraken's page. Read Kraken's positions page before taking that route: if the order filled, a margin position is open and the restart waits for it to close unless the restart rule's test admits it (the standing rules). Note the wall-clock time it rested, from the disconnect to the cancel.

"The order dies with the socket" is re-cancel-on-reconnect, delivered by the executor's re-read pass<!-- T0018 -->: this drill measures it — the time from `Reconnect succeeded` to the pass's line, and to the order leaving Kraken's open orders — and records a pass whose line did not come as the finding it is.
```

Replace, in `infra/runbooks/drills-order-path.md`, this block:

````markdown
```

**Read Kraken's open orders in the web UI while the engine is down.** That reading is deliverable 1 and it is unrepeatable: once the engine is back, the adopt pass has already acted on whatever was there. Read Kraken's positions page too: the `rest-hold` plan shape carries leverage, so if the order filled while the engine was down a margin position is open, and the start waits for that position to close (the restart rule in the standing rules). Then start it again:

```
````

with:

````markdown
```

**Read Kraken's open orders in the web UI while the engine is down.** That reading is deliverable 1 and it is unrepeatable: once the engine is back, the adopt pass has already acted on whatever was there. Read Kraken's positions page too: the `rest-hold` plan shape carries leverage, so if the order filled while the engine was down a margin position is open, and the start waits for that position to close unless the restart rule's test admits it (the standing rules). Then start it again:

```
````

Replace, in `infra/runbooks/order-semantics-verification.md`, this block:

```markdown
On the workstation, `kraken positions -o json` must print no position. Check again immediately before §5.1.

From 2.0.0rc6.dev20260921 a node refuses to start while the account holds a Kraken margin position its startup reconciliation cannot rebuild, and the adapter's margin position report carries no entry price, so an ordinary open position can be enough: the start fails with `Unresolved positions during startup reconciliation ... missing avg_px_open for position recovery`. The harness records that as `FAIL` on probe 2 or 6, naming the instrument and quantity (§6). It is not the harness's position to close: find its owner, and run the pass once it is closed.

### 2. Environment: the interpreter under test
```

with:

```markdown
On the workstation, `kraken positions -o json` must print no position. Check again immediately before §5.1.

From 2.0.0rc6.dev20260921 a node refuses to start while the account holds a Kraken margin position its startup reconciliation cannot rebuild, and the adapter's margin position report carries no entry price, so an ordinary open position can be enough: the start fails with `Unresolved positions during startup reconciliation ... missing avg_px_open for position recovery`. The harness records that as `FAIL` on probe 2 or 6, naming the instrument and quantity (§6). It is not the harness's position to close: find its owner, and run the pass once it is closed. The harness runs its own node, which keeps no cache, so the engine's restart rule's test — which admits a position the engine's cache restores — lifts nothing here: this section stands as written.

### 2. Environment: the interpreter under test
```

Replace, in `infra/runbooks/order-semantics-verification.md`, this block:

```markdown
Two node-start failures read differently. Both happen inside startup reconciliation, before any probe runs, so nothing was submitted and §8's flatten-by-hand does not apply:

`Unresolved positions during startup reconciliation … missing avg_px_open for position recovery` is exit 1, with probe 2 and/or 6 `FAIL` naming each instrument and quantity. The account holds a margin position the node cannot adopt (§1.7). That is a precondition of the pass, not an adapter result, so the pre-approved fallback does not apply: find the position's owner, have it closed, and re-run.

`Failed to get mass status from KRAKEN` is exit 2, and the harness prints the candidate causes, because the binding drops the adapter's own. In order of likelihood: the key lacks a query permission (Query Open Orders & Trades, Query Closed Orders & Trades); a WARN line earlier in the same run (`Failed to fetch tokenized asset pairs`, `Failed to parse instrument`) left a pair out of the listing; an open order or position sits on a pair outside the listing, which Kraken → Open Orders and Positions show.
```

with:

```markdown
Two node-start failures read differently. Both happen inside startup reconciliation, before any probe runs, so nothing was submitted and §8's flatten-by-hand does not apply:

`Unresolved positions during startup reconciliation … missing avg_px_open for position recovery` is exit 1, with probe 2 and/or 6 `FAIL` naming each instrument and quantity. The account holds a margin position the node cannot adopt (§1.7). That is a precondition of the pass, not an adapter result, so the pre-approved fallback does not apply: find the position's owner, have it closed, and re-run. The harness's node keeps no cache, so the engine's restart rule's test lifts nothing here.

`Failed to get mass status from KRAKEN` is exit 2, and the harness prints the candidate causes, because the binding drops the adapter's own. In order of likelihood: the key lacks a query permission (Query Open Orders & Trades, Query Closed Orders & Trades); a WARN line earlier in the same run (`Failed to fetch tokenized asset pairs`, `Failed to parse instrument`) left a pair out of the listing; an open order or position sits on a pair outside the listing, which Kraken → Open Orders and Positions show.
```

Replace, in `infra/runbooks/order-semantics-verification.md`, this block:

```markdown
3. After both, re-run probe 6 as §5.4 does, `$RUN --probes 6 --evidence-dir "$EVID"` with the pass's `--pair` and `--known-order <txid>` arguments, and confirm `ours 0` and `unclaimed 0` with verdict `PASS` (orders you named read `known`), then confirm it a second time on Kraken's own Open Orders page, the tie-breaker (§7.1).

Why it matters even though the engine is disarmed: at its next restart the engine's adopt pass reads the resting orders reconciliation put in its cache, finds no ledgered row for a probe order, and cancels it, a silent interaction between two systems in the logs of only one of them. A margin position left open does more: until the engine runs a build carrying upstream #5065, its next restart either fails to start or books that position at an entry price of 0, which is why no converge or restart is made while one is open ([`engine-procedures.md#engine-restart-margin-position`](engine-procedures.md#engine-restart-margin-position)). Either way: leave nothing for it to find.

Ctrl-C behaviour: one Ctrl-C is safe. It stops the node, which runs the harness's cancel-everything sweep while the exec client is still connected; the node holds its clients open for `max(10, --order-timeout)` seconds after the stop so those cancels can reach the venue, so raising `--order-timeout` widens that window and the time an interrupt takes to exit. Every later interrupt is swallowed, deliberately, so the sweep always completes. An interrupted run still prints its table and its leftover banner, and exits 2, or 3 if anything survived the sweep. If you must abandon it, `kill -9` the process from another terminal and work this section by hand.
```

with:

```markdown
3. After both, re-run probe 6 as §5.4 does, `$RUN --probes 6 --evidence-dir "$EVID"` with the pass's `--pair` and `--known-order <txid>` arguments, and confirm `ours 0` and `unclaimed 0` with verdict `PASS` (orders you named read `known`), then confirm it a second time on Kraken's own Open Orders page, the tie-breaker (§7.1).

Why it matters even though the engine is disarmed: at its next restart the engine's adopt pass reads the resting orders reconciliation put in its cache, finds no ledgered row for a probe order, and cancels it, a silent interaction between two systems in the logs of only one of them. A margin position left open does more: until the engine runs a build carrying upstream #5065, its next restart either fails to start or books that position at an entry price of 0 unless its cache restores it, which is why no converge or restart is made while one is open that the restart rule's test does not admit ([`engine-procedures.md#engine-restart-margin-position`](engine-procedures.md#engine-restart-margin-position)); a position the mint opened is one the engine's cache never saw, and the test refuses it. Either way: leave nothing for it to find.

Ctrl-C behaviour: one Ctrl-C is safe. It stops the node, which runs the harness's cancel-everything sweep while the exec client is still connected; the node holds its clients open for `max(10, --order-timeout)` seconds after the stop so those cancels can reach the venue, so raising `--order-timeout` widens that window and the time an interrupt takes to exit. Every later interrupt is swallowed, deliberately, so the sweep always completes. An interrupted run still prints its table and its leftover banner, and exits 2, or 3 if anything survived the sweep. If you must abandon it, `kill -9` the process from another terminal and work this section by hand.
```

Replace, in `docs/reference/adapter-verification/2.0.0rc6.dev20260921.md`, this block:

```markdown
## The operating rule on this pin: no engine restart with a margin position open

The owner's ruling of 2026-09-23, binding until a pin carries upstream #5065: no engine converge or restart while a Kraken margin position is open. On this version such a restart either fails startup (`Unresolved positions during startup reconciliation ... missing avg_px_open`) and crash-loops, or boots with the position's entry price at 0, where only the realized-PnL gauge is wrong; which of the two depends on the pair's fill history. The red button clears a crash loop: its wrapper stops the unit, and it does not reconcile. So the window below has no step 6, the restart with the fixture's margin position open, and each restart in it follows a `kraken positions -o json` that prints no position.
```

with:

```markdown
## The operating rule on this pin: no engine restart with a margin position open the restart rule's test does not admit

The owner's ruling of 2026-09-23, binding until a pin carries upstream #5065 or, for a position the engine's cache restores, until the cache's live proof reads clean: no engine converge or restart while a Kraken margin position is open that the test in `infra/runbooks/engine-procedures.md`'s `engine-restart-margin-position` does not admit. On this version such a restart either fails startup (`Unresolved positions during startup reconciliation ... missing avg_px_open`) and crash-loops, or boots with the position's entry price at 0, where only the realized-PnL gauge is wrong; which of the two depends on the pair's fill history. The red button clears a crash loop: its wrapper stops the unit, and it does not reconcile. So the window below has no step 6, the restart with the fixture's margin position open, and each restart in it follows a `kraken positions -o json` that prints no position.
```

Replace, in `docs/reference/adapter-verification/2.0.0rc6.dev20260921.md`, this block:

```markdown
- **When the operating rule lifts.** The rule above holds until a pin carries upstream #5065. On that pin the restart this window skips as step 6 is taken and read: an engine restart inside an inter-cycle gap with a Kraken margin position open, whose boot logs no `Unresolved positions during startup reconciliation` line, leaves `.RestartCount` unchanged, counts the position in its `Reconciliation complete for KRAKEN` line, and books the position at Kraken's entry price, not at 0. The first three reads do not show the fourth: this version's other failure, the boot with the entry price at 0, passes all three. Nothing the engine publishes carries that price directly: the `positions` of a `venue-<HH>.json` record are signed net quantities, and `zcrypto_exec_realized_pnl_eur` takes a position in only once this engine records a fill on its instrument (`_publish_fill` in `cli/engine/executor.py`), when a position booked at 0 shows a realized figure the size of its whole close value. So the reading names where it read the entry price the engine booked on that pin, and the rule stays until a read shows it is Kraken's. On a clean reading the rule comes out of the pages that carry it: `infra/runbooks/engine-procedures.md` (the `engine-restart-margin-position` paragraph and each step that links to it), `infra/runbooks/engine.md` (the restart and converge steps that link to that anchor), `infra/runbooks/drills-order-path.md` (the standing rule, A2's `blocked` precondition, drill D's precondition and restore step, F2's operator step 4 and G's induce step), `infra/runbooks/order-semantics-verification.md` (§1.7, §6's `Unresolved positions` paragraph and §8's closing paragraph) and the Reboots section of `docs/reference/fleet.md`.
```

with:

```markdown
- **When the operating rule lifts.** The rule above holds until a pin carries upstream #5065, or, for a position the engine's cache restores, until the cache's live proof reads clean — the restart rule's test in `infra/runbooks/engine-procedures.md`, whose proof is this window's step 6 taken under it. On a pin carrying #5065 the restart this window skips as step 6 is taken and read: an engine restart inside an inter-cycle gap with a Kraken margin position open, whose boot logs no `Unresolved positions during startup reconciliation` line, leaves `.RestartCount` unchanged, counts the position in its `Reconciliation complete for KRAKEN` line, and books the position at Kraken's entry price, not at 0. The first three reads do not show the fourth: this version's other failure, the boot with the entry price at 0, passes all three. Nothing the engine publishes carries that price directly: the `positions` of a `venue-<HH>.json` record are signed net quantities, and `zcrypto_exec_realized_pnl_eur` takes a position in only once this engine records a fill on its instrument (`_publish_fill` in `cli/engine/executor.py`), when a position booked at 0 shows a realized figure the size of its whole close value. So the reading names where it read the entry price the engine booked on that pin, and the rule stays until a read shows it is Kraken's. On a clean reading the rule comes out of the pages that carry it: `infra/runbooks/engine-procedures.md` (the `engine-restart-margin-position` paragraph and each step that links to it), `infra/runbooks/engine.md` (the restart and converge steps that link to that anchor), `infra/runbooks/drills-order-path.md` (the standing rule, A2's `blocked` precondition, drill D's precondition and restore step, F2's operator step 4 and G's induce step), `infra/runbooks/order-semantics-verification.md` (§1.7, §6's `Unresolved positions` paragraph and §8's closing paragraph) and the Reboots section of `docs/reference/fleet.md`.
```

Replace, in `docs/reference/fleet.md`, this block:

```markdown
| `zcrypto-capture` | zcrypto, zcrypto-red | `/var/lib/zcrypto-capture/<BASE>/<QUOTE>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet` | `/metrics` `127.0.0.1:9101` |
| `zcrypto-engine` | zcrypto | `/var/lib/zcrypto-engine/{store,journal}` (bind mounts; compose at `/opt/zcrypto-engine`); a journal day-dir: `cycle-HH.json` (written last, after validation), `orders.jsonl`, `snapshots/` | `/metrics` `127.0.0.1:9102` |
| the red button | zcrypto | `/usr/local/sbin/zcrypto-flatten` (`750 root:root`), rendered by the engine converge from `roles/engine/templates/zcrypto-flatten.sh.j2`; `infra/runbooks/engine-procedures.md`'s `engine-flatten` | — |
| liquidations poller | zcrypto-ops | under `ops_data_dir` = `/var/lib/zcrypto-ops` (`/data` inside the container) | `/metrics` `127.0.0.1:9103` |
| `grafana-alloy` | zcrypto, zcrypto-red, zcrypto-ops, nas, zcrypto-valkey1 to 3 | scrape jobs: `capture_app`, `engine_app` on the capture hosts (`engine_app` reads 0 on red); `liquidations_app`, `healthchecks` on ops; host and textfile on the nas; journal logs | self-metrics `:12345` |
| ops timers | zcrypto-ops | `zcrypto-{archive-pull,panel-materialize,tape-bars,verify-replay,verified-replay}.service` (a `docker run` per tick); `grafana-{watchdog,keepalive}` (scripts); `zcrypto-clock-offset` (5-min) | `.prom` into `/var/lib/zcrypto-ops/textfile` (all but the watchdog), read by the ops Alloy textfile collector |
| capture and engine timers | zcrypto, zcrypto-red | `zcrypto-capture-prune` (03:17), `zcrypto-reboot-check` (15-min), `zcrypto-clock-offset` (5-min); on zcrypto also `zcrypto-engine-journal-prune` (01:23, day-dirs, 60 d, keep-newest 60) | `.prom` into `/var/lib/zcrypto-node-textfile`, read by Alloy's textfile collector over the `/:/host/root:ro` mount (spec `00071`) |
```

with:

```markdown
| `zcrypto-capture` | zcrypto, zcrypto-red | `/var/lib/zcrypto-capture/<BASE>/<QUOTE>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet` | `/metrics` `127.0.0.1:9101` |
| `zcrypto-engine` | zcrypto | `/var/lib/zcrypto-engine/{store,journal}` (bind mounts; compose at `/opt/zcrypto-engine`); a journal day-dir: `cycle-HH.json` (written last, after validation), `orders.jsonl`, `snapshots/` | `/metrics` `127.0.0.1:9102` |
| `zcrypto-cache-proxy` | zcrypto | HAProxy beside the engine in `/opt/zcrypto-engine`, its config `haproxy.cfg` (`0600 root`), the Sentinel-checked route to the cache set's primary over `zcache0` | `/metrics` `127.0.0.1:9104`, the `cache_proxy` scrape |
| the red button | zcrypto | `/usr/local/sbin/zcrypto-flatten` (`750 root:root`), rendered by the engine converge from `roles/engine/templates/zcrypto-flatten.sh.j2`; `infra/runbooks/engine-procedures.md`'s `engine-flatten` | — |
| liquidations poller | zcrypto-ops | under `ops_data_dir` = `/var/lib/zcrypto-ops` (`/data` inside the container) | `/metrics` `127.0.0.1:9103` |
| `grafana-alloy` | zcrypto, zcrypto-red, zcrypto-ops, nas, zcrypto-valkey1 to 3 | scrape jobs: `capture_app`, `engine_app`, `cache_proxy` on the capture hosts (the last two read 0 on red); `liquidations_app`, `healthchecks` on ops; host and textfile on the nas; journal logs | self-metrics `:12345` |
| ops timers | zcrypto-ops | `zcrypto-{archive-pull,panel-materialize,tape-bars,verify-replay,verified-replay}.service` (a `docker run` per tick); `grafana-{watchdog,keepalive}` (scripts); `zcrypto-clock-offset` (5-min) | `.prom` into `/var/lib/zcrypto-ops/textfile` (all but the watchdog), read by the ops Alloy textfile collector |
| capture and engine timers | zcrypto, zcrypto-red | `zcrypto-capture-prune` (03:17), `zcrypto-reboot-check` (15-min), `zcrypto-clock-offset` (5-min); on zcrypto also `zcrypto-engine-journal-prune` (01:23, day-dirs, 60 d, keep-newest 60) | `.prom` into `/var/lib/zcrypto-node-textfile`, read by Alloy's textfile collector over the `/:/host/root:ro` mount (spec `00071`) |
```

Replace, in `docs/reference/fleet.md`, this block:

```markdown
- Reboot the secondary first, then the primary — the canary order of an image rollout: a kernel that bricks the secondary leaves the primary untouched.
- Schedule: ≥ 1 h from each 4 h bar boundary and off the hour boundary; ≥ 1 h between hosts; the primary in the book-traffic trough, right after a completed engine cycle, measured from the archive rather than guessed; and never inside a published Kraken maintenance window, read again immediately before — `.claude/rules/fleet-deploys.md` carries the feed (no count command: a reboot leaves no row in the tree; the deploy log records converges).
- A primary reboot restarts the engine, so the engine's restart rule holds for it: until the engine's nautilus-trader build carries upstream #5065, `zcrypto` is not rebooted while a Kraken margin position is open — read Kraken's positions page, or `kraken positions -o json` on the workstation, first (`infra/runbooks/engine-procedures.md`'s `engine-restart-margin-position`).
- Expect a ~83 s capture gap; both containers self-restart.
- A package upgrade that restarts containerd or Docker is not run under live capture: read the peer first (`up{job="capture_app",host="<peer>"}` 1 and `min(zcrypto_capture_seconds_since_last_book_message{host="<peer>"})` under 1), stop `zcrypto-capture.service` by hand, upgrade, then start it at once — `sudo systemctl start zcrypto-capture.service`, or the pending reboot taken now — because a unit stopped by hand stays stopped across a runtime restart. Unstopped, capture is force-killed across a containerd restart and its unflushed buffers lost (no count command: an upgrade leaves no row in the tree).
- On the primary that runtime restart takes the engine too, so the upgrade obeys the engine's restart rule as a reboot does: no Kraken margin position open, inside the inter-cycle gap (`infra/runbooks/engine-procedures.md`'s `engine-restart-margin-position`; the gap is `.claude/rules/fleet-deploys.md`'s) (no count command: an upgrade leaves no row in the tree).
- Verify by outcome before touching the next host — the checks a converge owes: on the pulled copy, every book stream's next `<HH>.parquet` begins where the other host's does (identical first rows), not at a fixed `:00:00.0x`; the NAS archive-pull's next cycle logs `pull complete … failed=0` for every verified channel; `infra/scripts/continuity.py` on a pulled copy shows no new truncated hours; on the primary, the next `cycle-<HH>.json` lands with `completed_at` inside `[B, B+30 min]`, and the restart marker is the container's `.State.StartedAt`, never the reboot command's return time (no count command: a reboot leaves no row in the tree).

```

with:

```markdown
- Reboot the secondary first, then the primary — the canary order of an image rollout: a kernel that bricks the secondary leaves the primary untouched.
- Schedule: ≥ 1 h from each 4 h bar boundary and off the hour boundary; ≥ 1 h between hosts; the primary in the book-traffic trough, right after a completed engine cycle, measured from the archive rather than guessed; and never inside a published Kraken maintenance window, read again immediately before — `.claude/rules/fleet-deploys.md` carries the feed (no count command: a reboot leaves no row in the tree; the deploy log records converges).
- A primary reboot restarts the engine, so the engine's restart rule holds for it: until the engine's nautilus-trader build carries upstream #5065, `zcrypto` is not rebooted while a Kraken margin position is open that the restart rule's test does not admit — read the Cache board's proxy row, the engine's last `cache restore` boot line in Loki and Kraken's positions page, or `kraken positions -o json` on the workstation, first (`infra/runbooks/engine-procedures.md`'s `engine-restart-margin-position`).
- Expect a ~83 s capture gap; both containers self-restart.
- A package upgrade that restarts containerd or Docker is not run under live capture: read the peer first (`up{job="capture_app",host="<peer>"}` 1 and `min(zcrypto_capture_seconds_since_last_book_message{host="<peer>"})` under 1), stop `zcrypto-capture.service` by hand, upgrade, then start it at once — `sudo systemctl start zcrypto-capture.service`, or the pending reboot taken now — because a unit stopped by hand stays stopped across a runtime restart. Unstopped, capture is force-killed across a containerd restart and its unflushed buffers lost (no count command: an upgrade leaves no row in the tree).
- On the primary that runtime restart takes the engine too, so the upgrade obeys the engine's restart rule as a reboot does: no Kraken margin position open that the restart rule's test does not admit, inside the inter-cycle gap (`infra/runbooks/engine-procedures.md`'s `engine-restart-margin-position`; the gap is `.claude/rules/fleet-deploys.md`'s) (no count command: an upgrade leaves no row in the tree).
- Verify by outcome before touching the next host — the checks a converge owes: on the pulled copy, every book stream's next `<HH>.parquet` begins where the other host's does (identical first rows), not at a fixed `:00:00.0x`; the NAS archive-pull's next cycle logs `pull complete … failed=0` for every verified channel; `infra/scripts/continuity.py` on a pulled copy shows no new truncated hours; on the primary, the next `cycle-<HH>.json` lands with `completed_at` inside `[B, B+30 min]`, and the restart marker is the container's `.State.StartedAt`, never the reboot command's return time (no count command: a reboot leaves no row in the tree).

```

Replace, in `docs/reference/fleet.md`, this block:

```markdown
## Telemetry labels

- Loki labels: `container`, `host`, `job`, `level`, `service_name`; `host ∈ {nas, ops, zcrypto, zcrypto-red, zcrypto-valkey1, zcrypto-valkey2, zcrypto-valkey3}`. The engine's own records ship as `container="engine"`; the nautilus library's `[WARN]`/`[ERROR]` lines, read from the unit's journal by the primary's Alloy, as `container="engine-nautilus"`, which no rule pages on.
- The cache nodes ship under `host="zcrypto-valkey1"` to `"zcrypto-valkey3"`, shown as `Cache 1` to `Cache 3` in Slack and on the Logs board; their Valkey and Sentinel series carry `job="valkey"` and `job="sentinel"`, their log lines `container` `valkey`, `sentinel`, `alloy` and `zcache-probe`, and `zcache_wireguard_handshake_age_seconds`, which the engine host ships too, a `peer` label holding the far end's mesh address.
- The bridgehead ships Prometheus under `host="zaccess"`; its `zaccess_wireguard_handshake_age_seconds` and `zaccess_tls_not_after_seconds` also arrive under `host="ops"` from the ops-side probe, so the tunnel is watched from both ends; the certificates are three, one per target — the bridgehead reads its own edge certificate for each of the `tmux` and `nas` vhosts, the ops probe reads the NAS's DSM certificate as `nas-dsm`, and no other probe reads them.
```

with:

```markdown
## Telemetry labels

- Loki labels: `container`, `host`, `job`, `level`, `service_name`; `host ∈ {nas, ops, zcrypto, zcrypto-red, zcrypto-valkey1, zcrypto-valkey2, zcrypto-valkey3}`. The engine's own records ship as `container="engine"`; the nautilus library's `[WARN]`/`[ERROR]` lines, read from the unit's journal by the primary's Alloy, as `container="engine-nautilus"`, which `zcrypto-engine-cache-write-failed` alone pages on; the cache proxy's lines, from the same journal, as `container="cache-proxy"`.
- The cache nodes ship under `host="zcrypto-valkey1"` to `"zcrypto-valkey3"`, shown as `Cache 1` to `Cache 3` in Slack and on the Logs board; their Valkey and Sentinel series carry `job="valkey"` and `job="sentinel"`, their log lines `container` `valkey`, `sentinel`, `alloy` and `zcache-probe`, and `zcache_wireguard_handshake_age_seconds`, which the engine host ships too, a `peer` label holding the far end's mesh address.
- The bridgehead ships Prometheus under `host="zaccess"`; its `zaccess_wireguard_handshake_age_seconds` and `zaccess_tls_not_after_seconds` also arrive under `host="ops"` from the ops-side probe, so the tunnel is watched from both ends; the certificates are three, one per target — the bridgehead reads its own edge certificate for each of the `tmux` and `nas` vhosts, the ops probe reads the NAS's DSM certificate as `nas-dsm`, and no other probe reads them.
```

Replace, in `docs/open-topics/T0158-go-live-drill-program-execution.md`, this block:

```markdown
---
status: partial
ripe_when: 'A2: the engine''s pinned nautilus-trader build carries upstream #5065, lifting the reboot-with-a-margin-position rule in docs/reference/fleet.md § Reboots'
---

```

with:

```markdown
---
status: partial
ripe_when: 'A2: either lift of the engine restart rule — the engine''s pinned nautilus-trader build carries upstream #5065, or the cache''s live proof, a restart with a margin position open whose boot line reads the position at Kraken''s entry price, is recorded in docs/reference/drill-log.md — the rule being the test in infra/runbooks/engine-procedures.md § engine-restart-margin-position'
---

```

Replace, in `docs/open-topics/T0158-go-live-drill-program-execution.md`, this block:

```markdown
**Every remaining sub-item is human-gated — this topic has no autonomous residual left.** The 2026-08-29 authorization recorded in `## Findings so far` lists **N** and **R** among the drills the loop may induce itself; that grant is about the *mechanism*, and blast radius overrides it here. Read the sub-item, never the grant, before inducing anything.

- **(human)** A2 — the primary reboots and a fill lands while it is down — the tier's one unrun drill, `blocked` in `drill-log.md` on `docs/reference/fleet.md` § Reboots' margin-position rule; it runs when `ripe_when` fires.
- **(human)** The same tier carries [[T0027]]'s last requirement, transferred at its archive: reconciliation survives the engine host rebooting with an order resting (A1) or filling while down (A2), and an engine stop with an order resting (G) — A1 and G read `pass`, and A2 stands with the item above; a reboot with any intent in flight is among none of them and is not claimed.
```

with:

```markdown
**Every remaining sub-item is human-gated — this topic has no autonomous residual left.** The 2026-08-29 authorization recorded in `## Findings so far` lists **N** and **R** among the drills the loop may induce itself; that grant is about the *mechanism*, and blast radius overrides it here. Read the sub-item, never the grant, before inducing anything.

- **(human)** A2 — the primary reboots and a fill lands while it is down — the tier's one unrun drill, `blocked` in `drill-log.md` on `docs/reference/fleet.md` § Reboots' margin-position rule; it runs when `ripe_when` fires, on either lift: A2's fill lands on an order this engine placed, which the restart rule's test admits once the cache's live proof is in.
- **(human)** Before A1's, G's or A2's next run, the reads their steps key on are re-derived on the drills page for the cache-enabled engine, which they state for the cache-less one: a restored order's pass line is `canceling restored order <id>, <state> -- …` and not `canceling adopted resting order …` (A1 step 2, G's operator action 3), its cancel's events reach the engine's own stream and not the external one, so G's `matched` does not count them (G's Record), and a venue figure short of the ledger trips the kill switch when the trade history falls short too, and not on the order figure alone (A2 step 4).
- **(human)** The same tier carries [[T0027]]'s last requirement, transferred at its archive: reconciliation survives the engine host rebooting with an order resting (A1) or filling while down (A2), and an engine stop with an order resting (G) — A1 and G read `pass`, and A2 stands with the item above; a reboot with any intent in flight is among none of them and is not claimed.
```

Replace, in `docs/open-topics/T0213-engine-cache-engine-half.md`, this block:

```markdown
---
status: open
ripe_when: 'a milestone: Rung 1 has its verdict, which §6 item 9 of the `engine-probe-window` procedure in `infra/runbooks/engine-procedures.md` records in `docs/research/14.phase6-decisions.md` — after which Rung 2''s design point opens the engine-side spec and plan of 00118'
---

```

with:

```markdown
---
status: resolved
---

```

Replace, in `docs/open-topics/T0213-engine-cache-engine-half.md`, this block:

```markdown
- **The engine image this half's rollout builds carries spec `00119`'s change** — the reprice ladder, the ledger reader, the startup sweep and the Cache handles the executor reads through, T0018's build-list item of 2026-09-26, and its two drill-day lines: the re-read pass, a socket-state subscription in `ShadowStrategy.on_start`, `_cached_order` withholding an order a minted terminal closed and the startup sweep re-run on the executor's tick with a bare-client cancel by txid, which this half's redesign of the startup pass keeps working, the gate's idle refresh, a `SystemStatus` GET a minute while no plan runs, and the position gauge's startup seed carried forward through the journal's fills after its venue record and settled from the venue's own holdings at the startup and re-read passes — on the owner's word of 2026-09-26; if this half's plan is not converged within a week of that pair's merge, the pair takes its own rollout through `.claude/skills/zcrypto-rollout-image/SKILL.md`'s engine section, and that date is an arm on T0018's trigger from the pair's closeout.

## Suggested next steps

- **(design, after the trigger)** Write the engine-side spec and plan under `00118`'s decisions: read the infrastructure plan's *Resolution* and, in `docs/specs/00118-engine-cache-design.md`, each decision it lists as the engine half's, then brainstorm the second pair with the owner and take it through `zcrypto-plan-review` before Task 1.
- **(read, at the trigger)** Read Rung 1's verdict entry and its `unmatched` and reconciliation readings in `docs/reference/adapter-verification/2.0.0rc6.dev20260921.md`: what a restart with a position open must recover is what the engine half's D11 startup pass is designed against.
- **(design, with the spec)** Re-gate the engine host's cache-link converge behind the engine window once the engine routes the cache through zcache0 — the role's handler restarts wg-quick@zcache0 on any conf change.
```

with:

```markdown
- **The engine image this half's rollout builds carries spec `00119`'s change** — the reprice ladder, the ledger reader, the startup sweep and the Cache handles the executor reads through, T0018's build-list item of 2026-09-26, and its two drill-day lines: the re-read pass, a socket-state subscription in `ShadowStrategy.on_start`, `_cached_order` withholding an order a minted terminal closed and the startup sweep re-run on the executor's tick with a bare-client cancel by txid, which this half's redesign of the startup pass keeps working, the gate's idle refresh, a `SystemStatus` GET a minute while no plan runs, and the position gauge's startup seed carried forward through the journal's fills after its venue record and settled from the venue's own holdings at the startup and re-read passes — on the owner's word of 2026-09-26; if this half's plan is not converged within a week of that pair's merge, the pair takes its own rollout through `.claude/skills/zcrypto-rollout-image/SKILL.md`'s engine section, and that date is an arm on T0018's trigger from the pair's closeout.

## Resolution

Delivered by spec `00120` (`docs/specs/00120-engine-cache-engine-half-design.md`) and its plan `docs/plans/00120-engine-cache-engine-half.md`, the branch `spec/00120-engine-cache-engine-half`: the cache table and the Kraken currency registration, the backing wired behind the config with the boot line, the two-process restart harness, the startup pass under a restored Cache, the engine role's proxy and the secrets' move, and the telemetry and pages. The rollout and the live proof are the plan's Rollout section, attended; the operating rule is the test `engine-restart-margin-position` in `infra/runbooks/engine-procedures.md` now states, and its other lift, upstream #5065, stands on T0158's re-keyed trigger. The cache-link converge on the engine host takes the engine window from this branch on.
```

Then move the topic and re-render the index, from the repository root:

```bash
git mv docs/open-topics/T0213-engine-cache-engine-half.md docs/open-topics/archive/T0213-engine-cache-engine-half.md
uv run python infra/scripts/topics-index.py
git status --porcelain -- docs/open-topics
```

Expected: the render rewrites `docs/open-topics/README.md`, and the status reads the README modified, T0158 modified and T0213 renamed into `archive/`; the README lists T0213 under `## Resolved` and T0158 under `## Partially done` with its new trigger.

- [ ] **Step 5: Run the two files and watch them pass**

Run: `uv run pytest tests/test_infra_alloy_series.py tests/test_infra_alert_rules.py -q -p no:cacheprovider`
Expected: `255 passed`.

- [ ] **Step 6: The consumers**

Run: `uv run pytest tests/test_infra_alloy_series.py tests/test_infra_alert_rules.py tests/test_infra_alloy_stages.py tests/test_ops_daily.py tests/test_dashboards_cover_metrics.py tests/test_runbook_triggers.py tests/test_runbook_internal_tokens.py tests/test_internal_terms_not_operator_visible.py tests/test_open_topics_frontmatter.py tests/test_fleet_contracts.py tests/test_drill_log.py tests/test_guidance_refs_resolve.py tests/test_message_citations.py -q -p no:cacheprovider`
Expected: every test passed or skipped by a gate, none failed; `2634 passed, 1 skipped` when this plan was written, the skip `tests/test_infra_alloy_stages.py`'s check against an `alloy` binary on PATH. The list is every module that reads the Alloy configs, the rules, the dashboards, the runbooks, the topics or the fleet contracts, the daily-ops uid map among them.

- [ ] **Step 7: The commit gate**

Run: `uv run pre-commit run -a`
Expected: every hook Passed, mdformat over the runbooks and the guidance guard among them -- a list item that says `every`, `never`, `always`, `only`, `any` or `cannot` without a count entry is refused there; re-run after any rewrite until clean, then stage what it rewrote.

- [ ] **Step 8: Commit**

```bash
git add infra/ansible/roles/capture/files/config.alloy infra/grafana/alerts.yaml infra/grafana/cache-dashboard.json infra/scripts/ops_daily.py infra/runbooks/cache.md infra/runbooks/engine-procedures.md infra/runbooks/engine.md infra/runbooks/drills-order-path.md infra/runbooks/order-semantics-verification.md docs/reference/fleet.md docs/reference/adapter-verification/2.0.0rc6.dev20260921.md docs/open-topics tests/test_infra_alloy_series.py tests/test_infra_alert_rules.py tests/test_infra_alloy_stages.py
git commit -m "feat(infra): the cache proxy's scrape, rules, board row and sections, the engine restart rule as the operator's test on every page that carries it, and the topics' closeout

The capture hosts' Alloy scrapes the proxy's Prometheus endpoint as cache_proxy and admits its six
families, and its journal pipeline labels the proxy's lines cache-proxy ahead of the engine's block
that relabels the rest of the unit, the level label only where HAProxy's level word opens the
line. Three rules join the cache group, each with a section in cache.md: the proxy with no backend
two of three Sentinels name, critical after two minutes at the frontend's own routing bound of two
checks passing; the
engine reporting while the proxy carries no session from it, warning after fifteen; and the
library's own cache-write failures on the engine-nautilus stream, warning, the outage line beside
all three saying the store is behind by what was written while the link was down and by the write
the reconnect dropped, nothing replays it, and the next restart is taken flat. The Cache board
gains the proxy's row, its status panels reading the exporter's per-state series. The engine
restart rule becomes the operator's test at its anchor -- the proxy routed and a session up on the
Cache board, two from a never-cut engine, the engine's last boot line counting the position as
restored or the position opened by this engine after that boot, no cache outage since, no restored
order filled since, and Kraken's positions page for what is open -- and every line that carries
the rule states the conditional in one clause, the order-semantics page saying its own node keeps
no cache and the adapter-verification page naming the test beside the pin's own lift; the engine
converges the pages spell carry the proxy's digest, which the role now refuses empty. fleet.md
carries the proxy's row and label, T0158's trigger names both lifts, and T0213 is resolved and
archived, the index re-rendered.

Cases: the capture keep-regex admitting the six families and the other hosts' excluding them; the
scrape on the engine host's loopback port and the proxy's match ahead of the engine's; the four
unalerted families excused with their reasons; the three rules scoped to the engine host, the
no-backend threshold equal to the template's routing bound, the write rule on the library's
stream, their groups and their anchors; the uid map carrying the three; the stages guard finding
the nautilus stage beside the proxy's block; and the generic guards -- every
alerted family charted and admitted where its rule selects, every rule pointing at a real panel or
a runbook, every anchor resolving, the red line agreeing with the rule, the runbook pages carrying
no internal vocabulary, the archived topic carrying its resolution and no trigger, the index the
render of the files, and the fleet contracts' caps.

PROBE_VERDICT

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>"
```

- [ ] **Step 9: The tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 10: Prove the guards with seven probes, then record their verdicts by a message-only amend**

The Alloy config's control renames the scrape job so the scrape case fails; its mutations drop the alerted family from the keep-regex and respell the proxy's container label. The rules file's control misspells a uid so the rules case fails; its mutations move the no-backend threshold off the panel's bar and point the write rule at the engine's own stream. The board's control renames panel 402 so the rule points at nothing; its mutation moves the panel's bar off the rule. The runbook's control misspells an anchor so the link fails to resolve; its mutation deletes another anchor. The archived topic's control misspells its resolution heading; its mutation reopens its status, which the index's render then contradicts.

```bash
T="uv run pytest tests/test_infra_alloy_series.py tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_open_topics_frontmatter.py -q -p no:cacheprovider"
A=infra/ansible/roles/capture/files/config.alloy
AC='s/job_name        = "cache_proxy"/job_name        = "cache-proxy"/'
infra/scripts/mutate-probe.sh --file $A --control "$AC" --mutation 's/|haproxy_backend_active_servers|/|/' -- $T
infra/scripts/mutate-probe.sh --file $A --control "$AC" --mutation 's/values = { container = "cache-proxy" }/values = { container = "cache_proxy" }/' -- $T
R=infra/grafana/alerts.yaml
RC='s/uid: zcrypto-cache-proxy-no-backend$/uid: zcrypto-cache-proxy-no-backendd/'
infra/scripts/mutate-probe.sh --file $R --control "$RC" --mutation '/uid: zcrypto-cache-proxy-no-backend$/,/noDataState/s/{type: lt, params: \[2\]}$/{type: lt, params: [1]}/' -- $T
infra/scripts/mutate-probe.sh --file $R --control "$RC" --mutation 's/container="engine-nautilus"} |= "nautilus_infrastructure::redis::cache"/container="engine"} |= "nautilus_infrastructure::redis::cache"/' -- $T
infra/scripts/mutate-probe.sh --file infra/grafana/cache-dashboard.json --control 's/"id": 402,/"id": 4020,/' \
  --mutation '/"id": 402,/,/"id": 403,/s/{"color": "green", "value": 2}/{"color": "green", "value": 3}/' -- $T
infra/scripts/mutate-probe.sh --file infra/runbooks/cache.md --control 's/<a name="zcrypto-engine-cache-write-failed"><\/a>/<a name="zcrypto-engine-cache-write-faile"><\/a>/' \
  --mutation '/<a name="zcrypto-cache-proxy-no-engine-session"><\/a>/d' -- $T
infra/scripts/mutate-probe.sh --file docs/open-topics/archive/T0213-engine-cache-engine-half.md --control 's/^## Resolution$/## Resolutio/' \
  --mutation 's/^status: resolved$/status: open/' -- $T
```

Expected: each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then replace the `PROBE_VERDICT` line of the commit message with the text below: write the whole message, that line replaced, to a file under `.tmp/` (gitignored) and amend from it with `git commit --amend -F <file>`; the amend changes the message only, no file.

```
Probe: `infra/scripts/mutate-probe.sh` over the capture Alloy config, control the scrape job
renamed so the scrape case fails: the alerted family dropped from the keep-regex, KILLED, control
proven; the proxy's container label respelled, KILLED, control proven; over alerts.yaml, control a
uid misspelled so the rules case fails: the no-backend threshold moved off the panel's bar, KILLED,
control proven; the write rule pointed at the engine's own stream, KILLED, control proven; over the
Cache board, control panel 402 renamed so the rule points at nothing: the panel's bar moved off
the rule, KILLED, control proven; over cache.md, control an anchor misspelled so the link fails to
resolve: another anchor deleted, KILLED, control proven; over the archived topic, control its
resolution heading misspelled: its status reopened, KILLED, control proven.
```

Run: `git status --porcelain` -- Expected: empty; `git log -1 --format=%B | grep -c PROBE_VERDICT` -- Expected: `0`; `git log -1 --format=%B | grep -c 'infra/scripts/mutate-probe.sh'` -- Expected: `1`, the verdict naming the script.

- [ ] **Step 11: The rollout skill's engine shape, its own `claude(` commit**

The engine role now refuses an empty cache proxy digest after the capture play has converged (Task 5), so the skill's engine shape names the third digest; the cache converges' failover bullet takes D1's cost, since a session cut drops the engine's next write; and the rollback phase takes D3's way back, since an engine image from before the cache table refuses the rendered config and a compose re-pin to it leaves the engine refusing to start -- the converge in the shape the role admits: the secondary's capture re-pinned back first so the canary parity assert passes on the previous digest, the primary's capture back by the same re-pin so the pair ends on one digest, the running proxy digest the role fails fast without and its `fleet-pins.md` row the role's pins assert reads, the parity bypass named as the one that takes the user's word, and the two proxy rules' silences the abort path already names. A skill file is guidance: it rides its own `claude(` commit, never the feat commit above, and the guidance guard judges it at commit -- the edited lines are two paragraphs and a list item carrying no universal word, so no count entry is owed.

Replace, in `.claude/skills/zcrypto-rollout-image/SKILL.md`, this block:

```markdown
Then, on the user's word, the same-day default shape, BOTH digests: `converge.sh site.yml --limit zcrypto -e converge_primary=true -e capture_image_digest=sha256:<candidate> -e engine_image_digest=sha256:<candidate> --tags capture,engine` — the engine role pins from its own variable and fails fast on an empty one AFTER the capture play has already converged, so a command carrying only the capture digest leaves the two tiers on different digests. The capture tag discipline per `fleet-deploys.md`.
```

with:

```markdown
Then, on the user's word, the same-day default shape, all THREE digests: `converge.sh site.yml --limit zcrypto -e converge_primary=true -e capture_image_digest=sha256:<candidate> -e engine_image_digest=sha256:<candidate> -e cache_proxy_image_digest=sha256:<the running proxy digest, docker inspect --format '{{.Config.Image}}' zcrypto-cache-proxy> --tags capture,engine` — the engine role pins from its own variables and fails fast on an empty one, the engine's or the proxy's, AFTER the capture play has already converged, so a command carrying only the capture digest, or the two app digests without the proxy's, leaves the two tiers on different digests. The capture tag discipline per `fleet-deploys.md`.
```

Replace, in `.claude/skills/zcrypto-rollout-image/SKILL.md`, this block:

```markdown
- **Then a deliberate `SENTINEL failover zcache`, by `cache-manual-failover`**, so the engine's one reconnect, once the engine is wired to the set, lands when you choose rather than on the Sentinels' detection timer — inside an engine inter-cycle gap by preference, not as a gate — and **the old primary last**, a replica by then, re-pinned and read the same way.
```

with:

```markdown
- **Then a deliberate `SENTINEL failover zcache`, by `cache-manual-failover`**, so the engine's session cut lands when you choose rather than on the Sentinels' detection timer — the cut drops the engine's next write, so the store is behind by it and the engine's next restart is taken flat: inside an engine inter-cycle gap while the engine is flat, by preference, not as a gate — and **the old primary last**, a replica by then, re-pinned and read the same way.
```

Replace, in `.claude/skills/zcrypto-rollout-image/SKILL.md`, this block:

```markdown
The previous-good digest is retained locally (verified in Phase 0), so rollback is a compose re-pin, no registry round-trip, ~2 min, and re-opens no data gap: edit the compose pin back → `sudo docker compose up -d` in the project dir → re-verify the positive traces (container up, ship succeeding, parquet advancing). Then stop and report — a rollback is a finding, not a retry license.
```

with:

```markdown
The previous-good digest is retained locally (verified in Phase 0), so rollback is a compose re-pin, no registry round-trip, ~2 min, and re-opens no data gap: edit the compose pin back → `sudo docker compose up -d` in the project dir → re-verify the positive traces (container up, ship succeeding, parquet advancing). Then stop and report — a rollback is a finding, not a retry license. The engine on an image from before the cache table is the exception: that image refuses the rendered `zcrypto.toml`'s `cache` table, so a compose re-pin leaves it refusing its config; its way back is an engine converge, which the role's canary parity assert admits once the secondary runs the previous digest as capture — the assert reads the secondary's running capture digest and no other host's — so the secondary's capture goes back first by the same compose re-pin, the previous digest's bake being the one its own rollout passed, and the primary's capture, on the candidate since Phase 3, goes back by the same re-pin beside it, since the record is not complete while the two capture hosts differ (Phase 5) — then, inside the inter-cycle gap: `converge.sh site.yml --limit zcrypto -e converge_primary=true -e engine_image_digest=sha256:<previous> -e cache_proxy_image_digest=sha256:<the running proxy digest, docker inspect --format '{{.Config.Image}}' zcrypto-cache-proxy> -e engine_cache_enabled=false --tags engine` — the proxy's digest because the role fails fast on an empty one, its `cache-proxy` row in `fleet-pins.md` because the role's pins assert refuses to replace a running proxy digest that file does not record — the row the proxy's rollout wrote before the converge that first rendered it, so the converges after it find it — and `engine_cache_enabled=false` because it renders no table. Where the secondary is unreachable, or is to stay on the candidate, the assert's bypass is `-e '{"canary_override": "<reason>"}'`, JSON, and it takes the user's explicit approval per `fleet-deploys.md`, asked before the converge. `engine_cache_enabled: false` committed in `infra/ansible/host_vars/zcrypto/vars.yml`, reverted by the change that re-enables the cache, keeps the next converge from rendering the table again, and the two rules the proxy left running fire — `zcrypto-cache-proxy-no-engine-session` after fifteen minutes, the proxy up with no session through it, and `zcrypto-cache-proxy-no-backend` where its backends are not at `L7OK` — are silenced in Grafana until that revert, as their sections say.
```

Run: `uv run pre-commit run -a` -- Expected: every hook Passed. Then:

```bash
git add .claude/skills/zcrypto-rollout-image/SKILL.md
git commit -m "claude(skills): the rollout skill's engine shape carries the cache proxy digest, its failover bullet the session cut's cost, and its rollback the pre-cache image's way back

The engine role refuses an empty cache_proxy_image_digest after the capture play has already
converged, as it refuses an empty engine digest, so the same-day default shape names all three:
the two app digests and the running proxy's, read off the container as fleet-pins.md prescribes.
The cache converges' deliberate failover cuts the engine's session, which drops its next write, so
the store is behind and the engine's next restart is taken flat: the bullet says so and asks for
the failover while the engine is flat. An engine image from before the cache table refuses the
rendered config's cache table, so a compose re-pin to it leaves the engine refusing to start: the
rollback phase names the converge with engine_cache_enabled=false as that image's way back, in
the shape the role admits -- the secondary's capture re-pinned back first so the canary parity
assert passes on the previous digest, the primary's capture back by the same re-pin so the pair
ends on one digest, the running proxy digest the role fails fast without and its fleet-pins.md row
the role's pins assert reads, the parity bypass as the one that takes the user's word, and the two
proxy rules' silences as the abort path has them.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>"
```

Run: `git status --porcelain` -- Expected: empty; `git log -1 --format=%s` -- Expected: the `claude(skills):` subject above, its own commit behind the task's.

## Rollout (attended)

One gap, on the owner's word, the cache enabled from the engine's first boot on it (spec D16). Before anything: the image is built from `develop` once this branch merges, carries spec 00119's change and this half, and takes the capture secondary's re-pin and bake as every app image does, through `.claude/skills/zcrypto-rollout-image/SKILL.md`; the proxy's pin is `haproxy:3.4.5`, whose index digest read `sha256:76928c0d6b39bdd5f1c15d519cf48c47a6aa18c1dc552f7af1c146d2aa003c14` on 2026-09-26 and is re-read at the rollout with `docker buildx imagetools inspect haproxy:3.4.5`, then pre-staged on `zcrypto` with `sudo docker pull haproxy@sha256:<digest>`; the engine host's `DefaultTimeoutStopSec` (`systemctl show -p DefaultTimeoutStopSec`) is read and named in the deploy row, since it bounds the unit's `compose down` above the service's twenty seconds; the Kraken maintenance feed is read whole, never through `head` or `tail`, at planning time and again immediately before each converge; no `infra/scripts/grafana-push.sh` runs from `develop` between this branch's merge and step 2's ops converge, a failed one holding it until an ops converge succeeds, since the push carries `zcrypto-capture-textfile-missing` at `< 3` while ops publishes no `node_reboot_required`, and that rule would page falsely at 2 after twenty minutes.

1. **The `cache-proxy` pins row first, then the primary inside the journal-computed gap while flat.** `docs/reference/fleet-pins.md` gains the `cache-proxy` row on `zcrypto` in the controller tree before the converge -- `<pinned>`'s first 12 hex, `76928c0d6b39 -- HAProxy 3.4.5, upstream haproxy` as read on 2026-09-26, rollback `first pin`, and its glossary line, `since` left for step 5 -- since the row records the digest the converge is handed, and the role's `cache proxy pins recording` assert reads that file at every converge that meets a running proxy and refuses one whose digest it does not carry: step 4's abort re-converge and the rollout skill's Phase 4 rollback both meet it, and neither reaches for `pins_override`. Then, from `infra/ansible`: `./scripts/converge.sh site.yml --limit zcrypto -e converge_primary=true -e capture_image_digest=<candidate> -e capture_alloy_digest=<running> -e engine_image_digest=<candidate> -e cache_proxy_image_digest=<pinned> --tags capture,engine` -- the `capture` tag because `config.alloy` changed, the `engine` tag for the role's changes, the proxy and `stop_grace_period` riding it; the preview runs the role's render and `haproxy -c` validation against the pinned image, both in check mode, and a refusal there stops before any engine file is written. Its own deploy-log row.
2. **The ops drop-in of PR #625 and ops' reboot flip in the same session**, its own row: `./scripts/converge.sh site.yml --limit zcrypto-ops --tags base,ops -e ops_image_digest=<running> -e ops_alloy_digest=<running> -e liquidations_decision=roll-after`, the skill's ops shape with `base` added, since `base` is where the apt file renders, so the host's file carries `Automatic-Reboot "false"` from code rather than from the owner's hand edit, and with the running Alloy digest, since ops' `config.alloy` gained `node_reboot_required` and the role's drift assert refuses a converge without it. Then the read-backs on ops: `grep Automatic-Reboot /etc/apt/apt.conf.d/50unattended-upgrades` shows `"false"`, `systemctl is-active zcrypto-reboot-check.timer` reads `active`, `cat /var/lib/zcrypto-ops/textfile/reboot.prom` carries `node_reboot_required 0` or `1`, and `/etc/systemd/system/docker.service.d/zcrypto-wait-for-resolver.conf` is present.
3. **The pushes**, from `develop`: `infra/scripts/grafana-push.sh` with the proxy row, the three rules and spec 00119's tiles, and the four pending-reboot rules widened to ops under their own uids, with the fleet board's panels 501 to 503; the widened family verified by value -- `node_reboot_required{host="ops"}` present at 0 or 1 (`ops` is the label ops' Alloy stamps, not the inventory name) and `count(node_reboot_required{host=~"zcrypto|zcrypto-red|ops"})` at 3, `max by (host)(node_textfile_scrape_error{host="ops"})` at 0, and `time() - max(node_textfile_mtime_seconds{host="ops",file=~".*/reboot.prom"})` under 3600; the proxy rules' first samples read by value with `infra/scripts/grafana-query.py` -- `max(haproxy_backend_active_servers{host="zcrypto"})` at 2 or 3, `sum(haproxy_backend_current_sessions{host="zcrypto"})` at 2 once the engine has written, the load's and the writer's, the Loki count at 0 in Explore -- and the four detail families read once each, `haproxy_backend_status{host="zcrypto",state="UP"}` at 1 on one backend, `haproxy_server_status{host="zcrypto",state="UP"}` at 1 on that backend's three servers, `haproxy_server_check_status{host="zcrypto",state="L7OK"}` at 1 on them, and `haproxy_server_check_failures_total{host="zcrypto"}` present -- `(no series)` a fail, never a zero.
4. **The boot line in Loki**, container `engine`, host `zcrypto`: `cache restore: 0 order(s), 0 position(s) restored`, the flat first boot, beside `Reconciliation complete for KRAKEN` and no `Unresolved positions` line; with it the readings the spec sends to the first boot: `sudo docker stats --no-stream zcrypto-cache-proxy` on `zcrypto` under the 32m cap; the proxy's backends at `L7OK` in `curl -s 127.0.0.1:9104/metrics | grep 'haproxy_server_check_status.*state="L7OK"} 1'`, the anchored expect passing against 9.1.2's `SENTINEL master` field order; and `ACL LOG` on the primary node's Valkey reading empty, nothing the node issues beyond `info` in 9.1.2's `dangerous` category. **If the boot line is absent within ten minutes of the converge** -- the unit restart-looping on `failed to create cache database backing`, the backends never `L7OK`: the mesh reach or the MTU the spec lists as unmeasured -- re-converge in the same gap with the same digests and `-e engine_cache_enabled=false`, which renders no cache table and starts the engine as before, the proxy left in place -- its running digest is what the role's `cache proxy pins recording` assert now reads, admitted on the `cache-proxy` row step 1 wrote -- and record the reading in the deploy row; the rollout skill's compose re-pin is no way back on its own, since an engine image from before the table refuses the rendered config. Then make the abort durable before the gap closes, since the role's default is `true` and the rollout skill's engine shape names no key, so the next routine engine converge would render the table again: a one-line PR to `develop` adding `engine_cache_enabled: false` to `infra/ansible/host_vars/zcrypto/vars.yml`, which every later engine converge reads, reverted by the change that re-enables the cache; and the two rules the abort leaves firing -- `zcrypto-cache-proxy-no-engine-session` after fifteen minutes, the proxy running with no session through it, and `zcrypto-cache-proxy-no-backend` where the backends never reached `L7OK` -- are silenced in Grafana until that revert, as their sections say. Then spec 00119's own post-converge readings, the first tick's holdings lines and the first hour's socket lines, taken on T0018's line.
5. **The pins**: the `cache-proxy` row step 1 wrote takes its `since` from `sudo docker inspect zcrypto-cache-proxy --format '{{.State.StartedAt}}'`; the engine row is re-trued from `sudo docker inspect zcrypto-engine --format '{{.Config.Image}}'`; every read of the engine container names its field -- `.Config.Image`, `.State.StartedAt`, `.Mounts` -- and never `.Config` whole or `.Config.Env`.
6. **The proof**, since the fixture mint cannot supply the position (its legs trade under `KRAKEN-902` through a bare client, outside the engine's cache): an attended probe window in drill D's shape -- the pre-probe checklist, the 60-minute pre-boundary rule, rung-1 money, a funded leveraged `execute` plan the owner places while the engine runs, opening one margin leg, then a leveraged `rest-hold` plan dropped last in the window with `hold_minutes` at its cap of 60, and, while that order rests and with the arm file in place, `sudo systemctl restart zcrypto-engine` on `zcrypto` inside the window's own gap -- at least ten minutes before the hold ends and sixty before the boundary, the restart the operator's test admits -- so that one restart restores the resting order beside the position: the boot's gate reads `reduce_only` on the restart hold, the pass cancels the opener, and the spec's two live-only readings below are taken at that boot. The disarm follows the proof and never precedes it: §5's step 1 removes the arm file and the running engine revokes a resting order at once, so an order dropped before the disarm rests through no restart, and a disarmed boot would read `the gate reads none (config_not_armed, ...)` in place of the ledger's reason. The boot line's position lines -- instrument, signed quantity, entry price, strategy -- summed per instrument and read against Kraken's positions page, where a fill on the resting order in the seconds the engine was down can show as a second line under `EXTERNAL` beside the restored one, or `kraken positions -o json` on the workstation, beside `Reconciliation complete for KRAKEN` counting the position and no `Unresolved positions` line; the restart marker is the container's new id and `.State.StartedAt`, never `.RestartCount`, which every `compose down` removes with the container. The restored order, at that boot, takes the spec's two live-only readings: the boot line's `cache restore: order <id> open, 0 of <qty> filled @ <price>`, its price read against the order's own -- a `0.00` there is the reprice the spec infers from the parser -- and the pass's `canceling restored order <id>, open -- the ledger does not carry it as a resting reducer` line followed either by the venue's `OrderCanceled` applied to the row, read as `canceled` in the ledger read within the tick, or by the adopted path's 31 s mint, `OrderCanceled for <id> was reconciled, not received`, the row `ambiguous` until the re-read pass settles it; the pass's line names its fill state, which reads `partial` where the resting order took a fill, since the pass reads the venue's figure before the cancel. Recorded as a drill-log entry and as the adapter-verification page's step 6, both readings named, and the operating rule's lift holds from that reading; A2 on T0158 is unblocked by it. The leg is then closed through the engine by a close plan, which `reduce_only` admits, and the disarm follows as §5 has it, its converge a second restart the test admits with the position open, or a flat one by then.
7. **The closeout**: the deploy-log rows, the pins row and the drill-log entry in one commit; T0018's build-list line of 2026-09-26 re-trued to name the converge and the readings taken; the 2026-10-05 arm on T0018's trigger goes at this converge, and the trigger gains the arm `or an engine log line canceling restored order naming an order Kraken already holds closed -- the pass's cancel of a stale open copy whose row left the ledger's window: read the venue's answer and the engine's events for that order after it`, the reading spec D12's cost leaves unread; and spec D18's hand-off line to the `nautilus` peer session through the coordination table, naming the two defects the harness measured on the pinned wheel -- the store saving a currency as its bare code, which a venue-minted code cannot resolve before the adapter runs, and the double booking of a trade frame on a restored order, its status half inferring the fill its fill half then reports -- with the open-only mass status noted as already fixed by #5110, and nothing here waiting on any of the three. What comes after -- Rung 2, then the nautilus bump whose compat check reads the upstream warning that a mass-status client conflicting with an execution client becomes a startup error -- is T0018's.

## Resolution

The branch delivers the engine-side half of the engine's cache, spec 00120, one pull request: the config table and the currency registration, the wiring behind the config with the boot line, the two-process restart harness, the startup pass under a restored Cache, the engine role's proxy with the secrets' move and the window guard over `cache-link`, and the proxy's telemetry with the operating rule as the operator's test on every page that carries it. T0213 is resolved and archived by Task 6, its solution being this plan and the Rollout it names; T0158's trigger names both lifts and the topic stays `partial`; T0018 stays `partial`, its build-list line re-trued at the rollout's closeout, by the controller, to name the converge and the readings. The rollout, the proof and the lift are the Rollout section's, attended, and no converge is planned by a task.

## Self-review

- Spec coverage: D1, D2 and D15 are Task 5; D3 and D4 are Task 1; D5, D9 and D11 are Task 2, with D9's predicate read at its two sites, the boot line and the classification's cancel line; D6, D7, D8, D10, D12 and D19 are Task 4, D12's cold start and both identities measured by Task 3's harness and D19's measured shape by the harness's cold-start scenario; D13 is Task 3, its opener double-booking scenario Task 4's ninth; D14 and D17 are Task 6, D1's failover line with them; D16 is the Rollout; D18 is the hand-off line the Rollout's step 7 sends to the `nautilus` peer session, and no task; 00118's amended D1, D10 and D11 are covered where their spec 00120 decisions are.
- Placeholders: `PROBE_VERDICT` is the one token, replaced in each task's Step 10 and checked to be gone; `<model>` and `<the executing session's URL>` in the trailers are the executing model's own name and its session's URL, a Global Constraint; `<candidate>`, `<running>`, `<pinned>` and `<digest>` in the Rollout are the digests the rollout reads, attended.
- Names: every name a task consumes is listed under its Interfaces and exists in the module at the step that uses it; the new source names (`CacheSettings`, `_build_cache`, `_CACHE_PASSWORD_VAR`, `_KRAKEN_CURRENCIES`, `_register_kraken_currencies`, `_cache_password`, `restored_fill_state`, `_log_cache_restore`, `read_venue_fills`, `_margin_positions`, `read_venue_positions`, `_read_restored`, `_read_realized_baseline`, `_reset_fills_read`, `_trades_cover`, `_venue_answers`, `_restored_row`, `_settle_restored_intent`, `_realized_on`, `_mixed_inventory_refusals`, `trade_row`, `WsPeer`, `exec_new`, `exec_trade`, `exec_canceled`, `serve_with_sockets`, `engine_cache_proxy_image`, `engine_cache_proxy_image_digest`, `engine_cache_proxy_memory_limit`, `engine_cache_proxy_master_name`, `engine_cache_proxy_nodes`, `engine_cache_enabled`, `CACHE_PROXY_SERIES`) are introduced by the task whose Interfaces list them and consumed only after.
