# The C3 vintage recorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Twice a day on the ops node, keep every byte four free providers serve in an immutable, chained tick directory held in two copies, and after each run refresh an append-only versions table that answers first published, restated, first appeared and as of t from those bytes alone.

**Architecture:** `cli/vintage/` is `zcrypto vintage {record,verify,derive}`. `sources.py` pins the fetch table and the check (D3, D8); `credential.py` and `fetch.py` hold the exchange, its bounds and the key's one path (D4, D7, D20); `storage.py` the exclusive writes and the three renames (D18); `chain.py`, `record.py` and `gauges.py` the tick, its chain and its `.prom` (D5, D6, D9, D10); `verify.py` the integrity read (D15); `derive.py`, `asof.py` and `table.py` the derivation, the as-of reader and the versions table (D16). The ops role runs it from one timer through two root runners and two oneshot units (D1, D2, D16, D17); the NAS pulls `record/` over a fifth `rrsync -ro` channel and re-verifies it (D14, D15); one critical rule, a dashboard row, a dead-man and a runbook section watch it (D11, D12); the fixtures are synthesised from shape files (D19).

**Tech Stack:** Python 3.14 stdlib (`urllib`, `gzip`, `zlib`, `compression.zstd`, `hashlib`, `json`, `tempfile`), polars 2.1.0, typer, pytest, Ansible templates, bash, Grafana provisioning YAML and JSON, `infra/scripts/mutate-probe.sh`.

**Spec:** `docs/specs/00158-c3-vintage-recorder-design.md`, approved as committed at `30567ed8c` (the approval recorded at `d6119fd69`).

**Tier:** `tier: full`, pasted from `uv run python infra/scripts/tier.py --paths <every path the File structure below names>`. One Fable-floor path, `.claude/skills/zcrypto-rollout-image/SKILL.md` (Task 18), from `uv run python infra/scripts/merge-gate.py --fable-paths`.

## The plan session's reads

Read-only, from this host, 2026-11-11, nothing written to disk; each re-checkable at the URL the spec's sources table gives.
- 14:51:41Z, the community catalog: the ten assets' daily lists equal the spec's table, all ten (`btc 31 same` … `avaxp 17 same`); `sol` and `avax` carry 8 each. Its body is compact JSON, `{"data":[{"asset","metrics":[{"metric","frequencies":[{"frequency","min_time","max_time","community"}]}]}]}`, and in O1's recorded body the `1d` frequency objects of `avaxc`, `avaxp` and `dot` also carry `experimental`, a boolean.
- 14:51:56Z, `cm-dot` with its 22 pinned metrics: nine metrics' newest day is 2022-06-03 (`AdrActCnt`, `AdrBalCnt`, `CapMVRVCur`, `CapMrktCurUSD`, `IssTotNtv`, `IssTotUSD`, `SplyCur`, `TxCnt`, `TxTfrCnt`), three's is 2025-12-01, 345 days before (`PriceBTC`, `ROI1yr`, `ROI30d`), and the rest reach 2026-11-10 or, for the five `ReferenceRate*`, 2026-11-11. The spec's exemption rule, "more than a year old", would leave the three 2025-12-01 metrics under the date − 3 bound and grade `cm-dot` 2 at every tick from the first; the bytes win (the spec's *What is left to the implementer*), and `DOT_STOPPED` (Task 2) names `cm-dot`'s twelve stopped metrics. O1's recorded `cm-eth` body adds two more, `HashRate` and `SplyExpFut10yr`, whose newest day is 2022-09-14: `ETH_STOPPED` (Task 2) names them, under the spec's own "more than a year old" rule.
- 14:51:56Z–14:52:10Z, `cm-avaxc`, `cm-avaxp` and `cm-btc`: every `avaxc` and `avaxp` metric's newest day is 2026-11-10, date − 1; every `ReferenceRate*` metric on `btc` and `dot` holds 7 points, 2026-11-05..11; a `json_stream` row lists `asset`, `time`, then its keys in ASCII order, compact, a key absent where the value is null, and the body ends with no newline; numbers are JSON strings; `btc` rows (and, in O1's bodies, `eth` rows) also carry `<metric>-status` (`"flash"`) and `<metric>-status-time` beside `FlowInExNtv`, `FlowInExUSD`, `FlowOutExNtv`, `FlowOutExUSD`, `SplyExNtv` and `SplyExUSD`, keys the catalog does not list.
- 14:53:04Z–14:53:08Z: `fng` is pretty-printed JSON, 3,202 rows newest first, `value` and `timestamp` JSON strings, the newest row alone carrying `time_until_update`, `metadata.error` null; `mempool-hashrate` is compact JSON with `hashrates` (6,522 rows, `timestamp` a JSON integer, the first 1231006505, not 00:00Z), `difficulty` (469 entries of `time`, `height`, `difficulty`, `adjustment`), `currentHashrate` and `currentDifficulty`, and `avgHashrate` JSON numbers of which 4,492 are integers past 2^53 and 1,914 carry a fraction; `cm-status` opens `<?xml version="1.0" encoding="UTF-8"?>` and holds 25 `<entry`.
- `RATIO` (Global Constraints) prints `375 534` at `d6119fd69`.
- The tree refutes one premise: the spec leaves `tests/test_infra_alloy_series.py` untouched, but its `test_the_journal_keep_regex_names_no_unit_the_role_does_not_install` counts as installed only units with a `templates/*.timer.j2` or a `files/*.timer` (lines 85-86), and the derive unit has no timer, so naming `vintage-derive` in the keep-regex fails it. Task 12 widens `_installed_units()` to every `templates/*.service.j2`, and probes it. Every service template the ops role ships today (`archive-pull`, `grafana-watchdog`, `panel-materialize`, `tape-bars`, `verified-replay`, `verify-replay`, `zcrypto-clock-offset`, `zcrypto-reboot-check`) is already kept by the regex or listed in `_JOURNAL_NOT_SHIPPED`, so the widening adds the two vintage units alone.

## Spec deviations

Each is recorded by the coordinator in the branch ledger the review reads and in the PR body (Outside, at the branch's end), so the review weighs it against the approved spec:
- `tests/test_infra_alloy_series.py` changes (Task 12), against the spec's change list ("Untouched, deliberately: … `tests/test_infra_alloy_series.py`") and its tests table ("applies as it stands"), for the reason the read above gives.
- `DOT_STOPPED` names twelve metrics where the spec's "more than a year old" rule names nine on `cm-dot` (Task 2), the bytes winning as the spec's *What is left to the implementer* allows; `ETH_STOPPED`'s two are inside that rule.
- O1's read-back of the bodies recorded 2026-11-11 16:56:10Z–16:57:17Z, the bytes winning; (a), (b) and (d) read as this plan states, (b) over every `cm-<asset>` body, where `cm-eth`'s two are the only stale pinned metrics outside `cm-dot`, `avaxc` and `avaxp`, and (d) finding `bg-lth-sopr` at 1,454 rows, 2026-01-18 missing, which no check reads:
  - (c): `cm-avaxc` and `cm-avaxp` take `LABS_NEWEST_DAYS = LABS_FRESHNESS_DAYS`, date − 30, at source level (Task 2), against the spec's date − 1 source bound for every `cm-<asset>` (D8). Each body's newest row, 2026-11-10, carries all 17 metrics, so it shows no `PriceUSD` ahead of the network metrics, and over 2026-08-13..11-10 `AssetEODCompletionTime` passed D+1 00:00Z by more than 19 h 37 min on 19 `avaxc` days (at most 310.62 h) and 12 `avaxp` days (at most 234.76 h). `BASE_TICK_START`'s reason (Task 1) follows it, with `mempool-hashrate` holding until date + 3, its newest `hashrates` day the fetch date.
  - (e): `/v1/sopr` with a made-up bearer answered 200 with the keyless body byte for byte, so an invalid key is served as keyless; Task 17's catalog line states that branch alone. That the request carried the made-up bearer is held by the recording's command record (the recording agent's one command for `bg-sopr-invalid-bearer.json`, sending `-H "Authorization: Bearer $V"`), not by the body or its `.headers` file, which hold the response alone.
- `.pre-commit-config.yaml` changes, outside the spec's change list: O1's `chore(config)` commit puts `tests/fixtures/vintage/` in the exclude `end-of-file-fixer`, `mixed-line-ending` and `trailing-whitespace` share, which would otherwise rewrite a fixture ending without a newline (Global Constraints).

## Global Constraints

- The spec is the authority; where it is silent this plan rules, in the task the ruling binds. Every value below is the spec's, verbatim.
- The worktree is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/c3-vintage-recorder` (branch `feat/00158-c3-vintage-recorder`); every command runs with it as the working directory.
- The order keeps each commit green: a metric family appears under `cli/` only after its panel exists (`tests/test_dashboards_cover_metrics.py::test_every_published_app_family_is_charted`), so Task 7's rule and row precede Task 8's and Task 10's gauges; the keep-regex and the units it names land in one commit (`tests/test_infra_alloy_series.py` holds both directions); the dead-man's count commit follows the `ops-node.md` anchor its `Runbook:` link names (`tests/test_ops_daily.py::test_todays_real_descriptions_all_pass`).
- No network call, no ssh, no docker, no `ansible-playbook` run, no converge, no Grafana or Kraken call, no `grafana-query.py`, no vault-shaped read, and no read of `.local/vintage-bodies/`: the real bodies are the coordinator's (Outside, O1). Searches are `git grep -l <pattern> -- <paths>` over paths that hold no vault-shaped file.
- Scratch is `.tmp/00158/task<N>/` (`R` below), pytest's `--basetemp="$R/pt"`, removed before the task's report by `chmod -R u+w "$R"` and then `rm -rf "$R"`, each its own call: a published tick, part, head or generation directory is 0555 and its files 0444, so a bare `rm -rf` fails with Permission denied for a non-root user (pytest's own basetemp cleanup chmods and retries; a hand removal does not); a process started is stopped by its PID.
- The task's run, over the commit's changed paths and the task's test files, never the full suite, never `tests/test_grafana_push_sh.py`; its result line is read in its own call before the commit message quotes it with the command:

```bash
R=.tmp/00158/task<N>; mkdir -p "$R"
T="$(infra/scripts/consumers.sh --tests --direct <each changed path> 2>"$R/consumers.err")" || true
uv run pytest $T <the task's test files> -m "not slow" -n auto -q -p no:cacheprovider --basetemp="$R/pt"
```

- A task that edits a page under `infra/runbooks/` loads `zcrypto-refine-rules` first and also runs `WALKERS`: `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_guidance_guard.py tests/test_count_list.py tests/test_guidance_refs_resolve.py tests/test_code_prose_citations.py tests/test_drill_log.py -q -p no:cacheprovider --basetemp="$R/pt"`, and `RATIO`, `` uv run python -c 'from tests.test_ops_daily import _runbook_commands, _destructive, _identity, ops_daily; reads = [c for c in _runbook_commands() if not _destructive(c)]; print(len([c for c in reads if ops_daily.classify_action(f"`{c}`", host="ops", resolve=_identity) is ops_daily.Tier.AUTONOMOUS]), len(reads))' ``, which prints `375 534` at this plan's base against the 0.70 floor of `test_most_read_only_diagnostics_are_autonomous_on_ops`. The floor is a budget, not a ban: `RATIO` prints `a n` (autonomous, counted reads), and a task whose pages add `A` autonomous and `P` other counted reads keeps `(a + A) / (n + A + P) ≥ 0.70`, at the base `0.7·P ≤ 1.2 + 0.3·A`, so one non-autonomous read fits with no autonomous one beside it and each further one costs about two and a third autonomous reads. A counted read is a backtick span or fenced line, under any runbook page, that starts with one of `_runbook_commands`' starters (`sudo `, `uv run `, `systemctl `, `journalctl `, `docker `, `ls `, `cat `, `find `, `stat `, …) and carries no `_DESTRUCTIVE` token, counted once however many times the same text appears. Measured at the base with `ops_daily.classify_action(…, host="ops")`: `systemctl status zcrypto-vintage-record.service`, `journalctl -u zcrypto-vintage-record.service -n 100`, `ls …`, `cat …`, `find …`, `docker ps -a --filter name=zcrypto-vintage-record`, `sudo systemctl start zcrypto-vintage-record.service` and `sudo systemctl start zcrypto-vintage-derive.service` classify AUTONOMOUS; `sudo /usr/local/sbin/zcrypto-vintage-record --source <id> --source <id> …`, `uv run zcrypto vintage verify …`, `uv run zcrypto vintage derive …`, `sudo chmod 0755 <dir>`, `sudo -u zcrypto-data cat <file>` and `sudo -u zcrypto-data cp …` classify PREPARED and spend the budget; `sudo rm …` and `docker rm …` carry a destructive token and are not counted; a bare `zcrypto vintage …` or `sha256sum …` starts with no starter and is not counted, so the spec's bare spellings (`zcrypto vintage verify --root /mnt/zhao-crypto/vintages --custody`, `zcrypto vintage derive --record <a copy> --table <scratch>`) stay bare. `RATIO` is read before and after each such task, and the allowlist is never widened.
- The gate is `uv run pre-commit run -a`, re-run until clean, its rewrites staged; `end-of-file-fixer`, `mixed-line-ending` and `trailing-whitespace` pass over `tests/fixtures/vintage/` (O1's exclude in `.pre-commit-config.yaml`), so every fixture keeps the bytes its generator or O1 wrote.
- A comment or docstring stays only where a reader would act differently without it, and is correct; state and decisions stay, an event goes to the PR body. A new Markdown file is one line per paragraph; an existing one keeps its shape.
- Operator surfaces carry no `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>` or `D<N>` token: every non-docstring string literal under `cli/`, every non-comment line of `*.sh` and `*.sh.j2`, `# HELP` text, `Description=`, Ansible task names, alert summaries, dashboard text, runbook pages and `README.md` (`tests/test_internal_terms_not_operator_visible.py`).
- Every line a `vintage` subcommand prints goes through `cli.logging` (`get_logger("vintage.<module>")`), the parse-stage shape, never `typer.echo`; no line carries a request header.
- `cli.capture` is imported, never edited. `pyproject.toml`, `uv.lock` and `zcrypto.toml` are untouched.
- Commits: Conventional Commits, one subject per change, `git add <every path>` new files first, one state-changing git command per call, never amend, never `--no-verify`. A `.claude/` change is its own `claude(` commit. Every message says what changed, quotes the task's run with its result line, and ends with these two lines, the first naming the executing model, the second the session line the dispatch brief gives:

```
Co-Authored-By: Claude <the executing model> <noreply@anthropic.com>
Claude-Session: <the session line the dispatch brief gives>
```

- Probes (tier `full`): each arm a task lists is its own call on the committed tree, `infra/scripts/mutate-probe.sh --file <f> --control '<control>' --mutation '<sed>' -- uv run pytest <its test file> -k '<its case>' -q -p no:cacheprovider --basetemp="$R/pt"`, its verdict recorded in an empty commit `test(vintage): Task <N> probes through infra/scripts/mutate-probe.sh`. Where this plan pins the line an arm mutates, the arm gives the `sed`; where the implementer writes the line, the arm names the mutation and the implementer writes the `sed` that reaches that one site. The control is `1,$d` unless the arm names its own: `mutate-probe.sh` exits 5 when the control leaves the case green and 2 when it leaves pytest nothing to collect, so an emptied file is no control for a test file itself (nothing is collected), for a body a case bounds from above (an empty body meets the bound), for a module an AST walk reads (an empty module breaks no rule), for a template whose case asserts only that it is valid bash (an empty script is), or for a case that asserts output a runner prints (an empty runner prints none, and an "every line matches" case passes vacuously unless it also counts the lines); each such arm names a control its case reads, or its case is written so an empty file fails it, as Task 12 does for the derive unit's sections and the runner's own lines.
- The spec's numbers this plan pins: slots 07:37:00 and 19:37:00 UTC; tick deadline 20 min; `last_ok` cap 19:57 UTC of the fetch's day; at most 3 attempts; Retry-After capped at 300 s, else 30 s then 120 s; 1 s between requests to a host; socket timeout 30 s; body deadline 120 s; size cap 64 MiB; a retried attempt's first 4 KiB as standard base64; gzip level 9, mtime 0, no name; files 0444, a published tick or table directory 0555, date directories 0755, `staging/` 0750, `.prom` 0644; bounds fng date − 1, cm source date − 1, cm metric date − 3, avaxc and avaxp date − 30 (at source level too since O1 (c), a deviation), mempool date − 3, bg date − 9; collapse under 90% of the last ok body; the rule `gt 90000`, `for: 5m`; the dead-man 90000 s and 21600 s; ops re-verify the newest 4 ticks and a slice of 14 by the count of published ticks, the NAS the newest 4 and `--slices 24`; BGeometrics four requests first, one retry per tick after 30 s, never after 429, 401 or 403; the key's shape `[A-Za-z0-9._~+/-]+=*`.

## File structure

- Create, the CLI: `cli/vintage/__init__.py`, `cli/vintage/sources.py`, `cli/vintage/credential.py`, `cli/vintage/fetch.py`, `cli/vintage/storage.py`, `cli/vintage/chain.py`, `cli/vintage/record.py`, `cli/vintage/gauges.py`, `cli/vintage/verify.py`, `cli/vintage/derive.py`, `cli/vintage/asof.py`, `cli/vintage/table.py`, `cli/vintage/command.py`. Modify `cli/__main__.py`.
- Create, the tests: `tests/vintage_fixtures.py` (the generator), `tests/vintage_stub.py` (the fake HTTPS handler, the clock, the record builder), `tests/test_vintage_sources.py`, `tests/test_vintage_fetch.py`, `tests/test_vintage_record.py`, `tests/test_vintage_verify.py`, `tests/test_vintage_derive.py`, `tests/test_vintage_credential.py`, `tests/test_vintage_table.py`, `tests/test_infra_vintage_record_template.py`; under `tests/fixtures/vintage/`, the synthesised bodies, `second/` and their provenance (Task 1), beside the coordinator's `fng.json`, its provenance and `shapes/` (O1).
- Create, the ops role: `infra/ansible/roles/ops/templates/vintage-record.sh.j2`, `vintage-record.service.j2`, `vintage-record.timer.j2`, `vintage-derive.sh.j2`, `vintage-derive.service.j2`, `vintage-bgeometrics.token.j2`.
- Modify, configuration: `infra/ansible/roles/ops/tasks/main.yml`, `infra/ansible/roles/ops/defaults/main.yml`, `infra/ansible/roles/ops/files/config.alloy`, `infra/ansible/host_vars/zcrypto-ops/vars.yml`, `infra/ansible/host_vars/nas/vars.yml`, `infra/ansible/roles/nas/templates/env.j2`, `infra/nas/compose.yaml`, `infra/nas/pull-entrypoint.sh`, `infra/grafana/alerts.yaml`, `infra/grafana/data-integrity-dashboard.json`, `infra/scripts/ops-postverify.sh`, `infra/scripts/hc-provision.py`.
- Modify, tests: `tests/test_infra_shell_templates_render.py`, `tests/test_infra_hc_role.py`, `tests/fixtures/healthchecks_descriptions.json`, `tests/test_ops_daily.py`, `tests/test_hc_provision.py`, `tests/test_infra_converge_guards.py`, `tests/test_ops_postverify.py`, `tests/test_infra_alert_rules.py`, `tests/test_infra_alloy_series.py`.
- Modify, docs: `infra/runbooks/ops-node.md`, `infra/runbooks/observability.md`, `infra/runbooks/nas.md`, `infra/runbooks/hc.md`, `infra/runbooks/drills-telemetry.md`, `infra/ops/README.md`, `infra/nas/README.md`, `infra/ansible/files/README.md`, `README.md`, `docs/reference/data-catalog-full.md`, `docs/reference/fleet.md`, `docs/research/10.phase4-decisions.md`.
- Modify, in its own `claude(skills)` commit: `.claude/skills/zcrypto-rollout-image/SKILL.md`.

## Review Focus

- A body that parses as JSON but not in its expected shape (a `bg-*` 200 that is an object, a `cm-<asset>` line that is an array, an `fng` whose `data` is an object) grades 2 with a reason and never raises out of the check, so one odd body never stops the tick: Task 2, `test_a_body_in_the_wrong_shape_grades_2_and_never_raises`.
- A `Retry-After` that is zero, negative, an HTTP-date in the past or unparseable falls back to the 30 s then 120 s schedule, never a negative sleep or an exception: Task 3, `test_a_retry_after_in_the_past_or_unparseable_falls_back`.
- A `cm-<asset>` row carrying keys outside the pinned list (the measured `<metric>-status` and `-status-time`) is ignored by the check, which judges pinned metrics alone, and kept by the derivation as series of their own: Task 2, `test_keys_outside_the_pinned_list_are_ignored_by_the_check`; Task 6, `test_the_status_companions_are_series_of_their_own`.
- A record tree holding what is not a tick (a stray file in a date directory, an rsync temporary directory, an empty date directory) leaves the chain, the gauges and the derive unchanged, while `verify` names an unlisted file inside a tick directory: Task 4, `test_the_scan_skips_what_is_not_a_tick`.
- A `json_stream` body read with or without a trailing newline, or with a blank line, yields the same rows (measured: no trailing newline): Task 6, `test_a_json_stream_body_parses_with_or_without_a_trailing_newline`.

---

### Task 1: The fixtures (D19)

**Files:**
- Create: `tests/vintage_fixtures.py`; under `tests/fixtures/vintage/`, `cm-btc.jsonl`, `cm-dot.jsonl`, `cm-avaxc.jsonl`, `cm-catalog.json`, `cm-status.atom`, `mempool-hashrate.json`, `bg-sopr.json`, each with `<file>.provenance.json`, and `second/<variant>.<ext>` with its provenance; `tests/test_vintage_sources.py`.
- Consumes, committed by the coordinator before the plan review (O1): `tests/fixtures/vintage/fng.json`, `fng.json.provenance.json`, `tests/fixtures/vintage/shapes/<source>.shape.json` for the seven sources above (`cm-status`'s regenerated from its recorded body in the plan review's first round, its entity references and `xmlns` value kept, so its synthesised feed is well-formed), and `tests/fixtures/vintage/real-bodies.json`, the record of every recorded body, `{"<file under .local/vintage-bodies/>": {"source", "url", "fetched_at", "status", "sha256", "bytes"}}`, nineteen entries.

**Interfaces:**
- Produces, in `tests/vintage_fixtures.py`: `FIXTURES: Path`; `MAX_ROWS = 120`; `MAX_FILE_BYTES = 500 * 1024`; `SENTINEL_KEY = "vintage.Sentinel-key_0~9+/x=="` (the key's shape, carrying `/`, `+` and `=` so its four scan forms differ); `SENTINEL_FORMS = (b"vintage.Sentinel-key_0~9+/x==", b"vintage.Sentinel-key_0~9+\\/x==", b"vintage.Sentinel-key_0~9%2B%2Fx%3D%3D", b"vintage.Sentinel-key_0~9%2b%2fx%3d%3d")`, the four forms (raw; JSON-escaped; percent-encoded, upper- and lower-case hex) spelt as literals, never computed, so a test that reads them never reads through the `key_forms` under test; `class RawNumber(str)`; `loads_tokens(data: bytes) -> object` (`json.loads` with `parse_int=RawNumber`, `parse_float=RawNumber`); `dumps_compact(obj) -> bytes` (key order kept, separators `,` and `:`, a `RawNumber` unquoted); `synthesize(shape: dict) -> bytes`; `@dataclass(frozen=True) class Variant: base: str; what: str; edit: Callable[[bytes, random.Random], bytes]`; `VARIANTS: dict[str, Variant]`; `body(name: str) -> bytes` (`"cm-btc"`, `"second/cm-btc-restatement"`; the committed file's bytes under `FIXTURES`, never a regeneration, so a probe on a committed fixture reaches every reader); `regenerate() -> dict[Path, bytes]` (every synthesised file and its provenance, in memory); `python -m tests.vintage_fixtures` writes them; `BASE_TICK_START: datetime`, 00:37:00Z on `cm-btc`'s `real.fetched_at` UTC date, a date at which every fixture meets its newest-day bound (the newest rows of `cm-btc`, `cm-dot` and `fng.json` are that date, so a tick two days later grades them 2 under the date − 1 source bound; `avaxc` takes date − 30 at source level since O1 (c)): a test whose ticks must grade ok keeps them on that date, and one that crosses a date names the sources whose bounds still hold (`mempool-hashrate`, its newest `hashrates` day that date, until date + 3, `bg-sopr` until date + 2).

The shape file, written by the coordinator (O1) and held by this task's tests:

```json
{"schema": 1, "source": "cm-btc", "format": "json_stream", "trailing_newline": false,
 "real": {"file": "cm-btc.jsonl", "url": "<the URL Task 2 pins for the source>", "fetched_at": "<UTC, seconds, Z>", "sha256": "<64 hex>", "bytes": 0},
 "licence": "CC BY-NC 4.0", "attribution": "Coin Metrics Community Network Data", "seed": 158001,
 "skeleton": "<the selected rows of the real body as text, every value token masked>"}
```

- `format`: `json_stream` for a `cm-<asset>`, `json` for the catalog, `mempool-hashrate` and `bg-sopr`, `atom` for `cm-status`.
- `skeleton`: the real body's bytes for the selected rows, formatting, key order and quoting untouched, every digit of a value token replaced by `#` and every letter by `~`, except the kept tokens: a `cm-<asset>` row's `asset` and `time`; the catalog's `asset`, `metric`, `frequency` and `community`; a `hashrates` row's `timestamp`; a bg row's `d` and `unixTs`; the feed's XML prolog, its element and attribute names, its entity references (`&lt;`, `&gt;`) and its `xmlns` attribute's value, structure a synthesised feed needs to stay well-formed; JSON keys, `true`, `false` and `null` everywhere.
- The selection: a `cm-<asset>` body keeps its first row, for each key the first and the last row carrying it, then its newest rows until 120, in the body's order; the catalog keeps every asset entry whole; `mempool-hashrate` keeps its first `hashrates` row and the newest 119, the newest 20 `difficulty` entries, `currentHashrate` and `currentDifficulty`; `bg-sopr` keeps its newest 120 rows; `cm-status` keeps all 25 entries.
- `seed`: 158001 plus the source's index in cm-btc, cm-dot, cm-avaxc, cm-catalog, cm-status, mempool-hashrate, bg-sopr.
- `real-bodies.json`, every shape file and every provenance file is `json.dumps(obj, indent=2, sort_keys=True) + "\n"`; a provenance file holds `source`, `file`, `real` (the shape's block), `committed` (`"real"` for `fng.json` alone, `"synthesised"` otherwise), `how` (`{"generator": "tests/vintage_fixtures.py", "shape": "shapes/<source>.shape.json", "seed": <n>}`, null for `fng.json`), `licence`, `attribution`, and for a second tick `"synthetic_second_tick": true`, `from` and `edit`.

- [ ] **Step 1: The failing tests,** in `tests/test_vintage_sources.py`:
  - `test_every_fixture_body_has_its_provenance`, over every file under `tests/fixtures/vintage/` but `shapes/`, `real-bodies.json` and `*.provenance.json`: its provenance exists with every key above; for `fng.json` the committed bytes' sha256 and size equal `real.sha256` and `real.bytes`.
  - `test_only_fear_and_greeds_body_is_committed_real`: every provenance whose source is a `cm-*`, `mempool-hashrate` or `bg-*` says `"synthesised"`.
  - `test_every_synthesised_fixture_regenerates_byte_for_byte`: `regenerate()` equals the committed bytes of every synthesised file and its provenance.
  - `test_no_shape_holds_a_value`: every value token of every skeleton, outside the kept tokens above (the feed's entity references and `xmlns` value among them, each named in the test as excepted), holds no digit and no letter.
  - `test_every_shape_names_a_recorded_body`: each shape's and `fng.json`'s `real` block's `url`, `fetched_at`, `sha256` and `bytes` equal the `real-bodies.json` entry its `file` names, and that entry's `source` is the shape's; `real-bodies.json`'s nineteen entries are the eighteen sources and `bg-sopr-invalid-bearer.json`.
  - `test_every_synthesised_body_parses_in_its_format`: each committed synthesised `json` body parses with `json.loads`, each `json_stream` line does, and the `atom` body parses with `xml.etree.ElementTree.fromstring`.
  - `test_every_fixture_holds_the_bound`: every synthesised body holds at most `MAX_ROWS` rows (`json_stream` lines; the catalog's `data` entries; `hashrates` and `difficulty` each; a bg array; the feed's `<entry`), and every file under `tests/fixtures/vintage/` is under `MAX_FILE_BYTES`.
  - `test_each_second_tick_differs_from_its_base_as_its_name_says`, over `VARIANTS`, each property read by `loads_tokens` against `body(variant.base)`, a pinned metric being one the `cm-catalog` shape lists for `btc` under a `1d` frequency, never a `-status` or `-status-time` companion: `cm-btc-restatement` one (key, day) token of a pinned metric inside its range differs, nothing else; `cm-btc-next` the base's newest row (measured to carry the `ReferenceRate*` metrics alone) gains every pinned metric the row before it carries, `PriceUSD` among them, and nothing else, so it keeps the base's 120 rows (of the variants built from a shape's body, only `bg-sopr-rolled` appends a row, and it drops one first; `fng-next`, edited from the real body, holds no row kind the bound counts); `cm-btc-retraction` one (pinned metric, day) inside that metric's range is gone, nothing else; `cm-btc-metric-gone` one pinned metric is absent from every row; `cm-btc-metric-back-changed` that metric back, one of its tokens differing from the base; `cm-btc-gap` one pinned metric's second-newest day is gone (the backfill's first tick); `cm-btc-time-format` every `time` token reads `YYYY-MM-DDT00:00:00Z`, every key and value as the base; `cm-btc-collapse` 85% of the base's rows, those dropped from the middle and every key's first and last row kept, so every pinned metric keeps its oldest and newest day and the check names `("*", "collapse")` alone; `cm-btc-lost-newest` every pinned metric's two newest days gone; `cm-btc-frozen` one pinned metric's newest five days gone; `cm-catalog-paginated` the base plus a `next_page_url`; `cm-btc-403` the measured forbidden shape `{"error":{"type":"forbidden","message":…}}`; `mempool-hashrate-restated-big` one `avgHashrate` integer past 2^53 differs in its last digit; `bg-sopr-rolled` the oldest row dropped and a next day appended, its `unixTs` the epoch of its `d` at 00:00Z; `bg-sopr-newest-back` the newest row dropped; `bg-sopr-collapse` the newest 100 of 120 rows; `bg-sopr-restatement` one value differs; `bg-sopr-404` the measured Spring shape `{"timestamp":…,"status":404,"error":"Not Found","path":"/v1/sopr"}`; `bg-sopr-401-echo` a 401 body whose message holds `SENTINEL_KEY`; `bg-sopr-429` the Spring shape at 429; `fng-next` the real body with a new newest row and one older row's value changed. Every variant is read by a later case: `cm-btc-collapse` by Task 2's `test_a_collapse_grades_2` and Task 6's source-level case, `cm-btc-frozen` by Task 2's `test_a_metric_past_its_freshness_bound_grades_2`, and each other by the cases that name it.
- [ ] **Step 2: Run them and read them fail** on the missing module.
- [ ] **Step 3: `tests/vintage_fixtures.py`.** `synthesize` fills each `#` with a digit and each `~` with a lower-case letter drawn from `rng = random.Random(shape["seed"])`, except a `~` that sits inside a number token (in a `json` or `json_stream` shape, outside every JSON string), the exponent marker of `mempool-hashrate`'s `avgHashrate`, which it fills with `e`, a run's first `#` nonzero where the run is longer than one and follows neither a digit nor `.`, and appends the newline only when `trailing_newline` is true. Each variant's `edit` works on `loads_tokens` and writes back through `dumps_compact`, except `fng-next`, which keeps the real body's formatting by editing its text; a variant's `rng` is `random.Random(159000 + <its index in VARIANTS>)`. Run `uv run python -m tests.vintage_fixtures` and stage what it wrote.
- [ ] **Step 4: The task's run, the gate, commit** `test(vintage): the synthesised fixtures, their generator and their provenance`.
- [ ] **Step 5: Probes.** Each KILLED.
  - `--file tests/vintage_fixtures.py`, `test_every_synthesised_fixture_regenerates_byte_for_byte`: the seed moved, `s/random\.Random(shape\["seed"\])/random.Random(shape["seed"] + 1)/`.
  - `--file tests/fixtures/vintage/shapes/cm-btc.shape.json`, `test_no_shape_holds_a_value`: one mask filled, `0,/#/s/#/7/`.
  - `--file tests/fixtures/vintage/cm-btc.jsonl`, `test_every_fixture_holds_the_bound`, control every row tripled, `s/.*/&\n&\n&/` (an emptied body holds 0 rows and meets the bound): one row past the bound, `$p`, the fixture sitting at 120 rows by its selection.
  - `--file tests/fixtures/vintage/second/cm-btc-time-format.jsonl`, `test_each_second_tick_differs_from_its_base_as_its_name_says`: one `time` token left off the new format, `0,/T00:00:00Z/s/T00:00:00Z/T00:00:01Z/`.
  - `--file tests/fixtures/vintage/cm-btc.jsonl.provenance.json`, `test_only_fear_and_greeds_body_is_committed_real`: `s/"committed": "synthesised"/"committed": "real"/`.
  - `--file tests/fixtures/vintage/fng.json`, `test_every_fixture_body_has_its_provenance`: one byte added to the real body, `1s/^{/{ /`.
  - `--file tests/fixtures/vintage/real-bodies.json`, `test_every_shape_names_a_recorded_body`: `fng.json`'s recorded sha256 altered, `/"fng\.json"/,/}/s/"sha256": "[0-9a-f]/"sha256": "x/`.
  - `--file tests/fixtures/vintage/mempool-hashrate.json`, `test_every_synthesised_body_parses_in_its_format`: one exponent marker made a letter, `0,/[0-9]e+[0-9]/s/\([0-9]\)e+\([0-9]\)/\1q+\2/`.

### Task 2: The fetch table and the check (D3, D8)

**Files:** Create `cli/vintage/__init__.py` (empty), `cli/vintage/sources.py`; modify `tests/test_vintage_sources.py`.

**Interfaces:**
- Consumes: Task 1's `body`, `BASE_TICK_START`, `VARIANTS`.
- Produces, in `cli/vintage/sources.py`:
  - `@dataclass(frozen=True) class Source: id: str; url: str; file: str; provider: str; host: str; kind: str; keyed: bool; value_key: str | None; asset: str | None`, `kind` one of `fng`, `cm-asset`, `cm-catalog`, `cm-status`, `mempool-hashrate`, `bg`; `provider` one of `alternative.me`, `coinmetrics`, `mempool.space`, `bgeometrics`.
  - `ASSET_METRICS: dict[str, tuple[str, ...]]`, the spec's table verbatim, each list in ASCII order, the order of the catalog fixture.
  - `SOURCES: tuple[Source, ...]` in tick order: `bg-sopr`, `bg-asopr`, `bg-sth-sopr`, `bg-lth-sopr`, `fng`, `cm-status`, `mempool-hashrate`, `cm-btc`, `cm-eth`, `cm-xrp`, `cm-ada`, `cm-link`, `cm-doge`, `cm-ltc`, `cm-dot`, `cm-avaxc`, `cm-avaxp`, `cm-catalog` (spec D7's order: the hosts serving one request each before `community-api.coinmetrics.io`, whose two endpoints can together reach the tick deadline, and on that host the ten assets before the catalog, so a catalog fault beside another host's never costs an asset); `SOURCE_BY_ID: dict[str, Source]`. Files: `fng.json.gz`, `cm-<asset>.jsonl.gz`, `cm-catalog.json.gz`, `cm-status.atom.gz`, `mempool-hashrate.json.gz`, `bg-<metric>.json.gz`. Value keys `sopr`, `asopr`, `sthSopr`, `lthSopr`.
  - `@dataclass(frozen=True) class Acknowledgment: source: str; metric: str; rule: str; since: str`, `metric` a pinned metric or `*`, `rule` one of `shape`, `encoding`, `newest`, `collapse`, `pagination`, `absent`, `freshness`, `top`, `bottom`, `since` a tick stamp; `COMPARISON_RULES = frozenset({"collapse", "top", "bottom"})`; `ACKNOWLEDGMENTS: tuple[Acknowledgment, ...]`.
  - `@dataclass(frozen=True) class BodySummary: rows: int; newest: date | None; metric_newest: dict[str, date]; metric_oldest: dict[str, date]`; `summarise(source: Source, body: bytes) -> BodySummary`, raising `ValueError` on a body it cannot read, which `check_body` grades.
  - `@dataclass(frozen=True) class Check: outcome: int; reason: str | None; newest_day: date | None; rows: int | None; metrics_absent: tuple[str, ...]; metrics_failed: tuple[tuple[str, str], ...]; acknowledged: tuple[Acknowledgment, ...]; summary: BodySummary | None`, `metrics_failed` holding `(metric, rule)`, a source-level failure as `("*", rule)`, so every outcome-2 check names at least one entry.
  - `check_body(source: Source, body: bytes, *, content_encoding: str | None, tick: str, last_ok: BodySummary | None, last_ok_tick: str | None, acknowledgments: tuple[Acknowledgment, ...] = ACKNOWLEDGMENTS) -> Check`; `check_block(check: Check) -> dict` (the `tick.json` `check` keys: `outcome`, `reason`, `newest_day`, `rows`, `metrics_absent`, `metrics_failed`, `acknowledged`).

The acknowledgment's reading, in the spec's four-field form: an entry applies to a tick at or after its `since`; one whose `since` is `GENESIS` turns its rule off, the named exemptions' form; a later one turns a non-comparison rule off and restarts a comparison rule, which then compares only with a last ok body at or after `since`. The pinned lines:

```python
GENESIS = "00000000T000000Z"
FRESHNESS_DAYS = 3
LABS_ASSETS = ("avaxc", "avaxp")
LABS_FRESHNESS_DAYS = 30
LABS_NEWEST_DAYS = LABS_FRESHNESS_DAYS
NEWEST_DAYS = {"fng": 1, "cm-asset": 1, "mempool-hashrate": 3, "bg": 9}
COLLAPSE_FLOOR = 0.9
DOT_STOPPED = (
    "AdrActCnt",
    "AdrBalCnt",
    "CapMVRVCur",
    "CapMrktCurUSD",
    "IssTotNtv",
    "IssTotUSD",
    "SplyCur",
    "TxCnt",
    "TxTfrCnt",
    "PriceBTC",
    "ROI1yr",
    "ROI30d",
)
ETH_STOPPED = ("HashRate", "SplyExpFut10yr")
CM_URL = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics?assets={asset}&metrics={metrics}&frequency=1d&format=json_stream&ignore_forbidden_errors=true&ignore_unsupported_errors=true"
ACKNOWLEDGMENTS = (
    *(Acknowledgment("cm-dot", metric, "freshness", GENESIS) for metric in DOT_STOPPED),
    *(Acknowledgment("cm-eth", metric, "freshness", GENESIS) for metric in ETH_STOPPED),
    *(
        Acknowledgment(f"cm-{asset}", metric, "bottom", GENESIS)
        for asset, metrics in ASSET_METRICS.items()
        for metric in metrics
        if metric.startswith("ReferenceRate")
    ),
)
```

The block is pinned as `ruff format` leaves it, so the arms below reach the lines the gate commits; `CM_URL`, a string the formatter does not split, stays one line past the 132 columns.

The two stopped tuples are the named freshness exemptions, the family read off O1's bodies: every pinned metric outside `avaxc` and `avaxp` whose newest day is older than the fetch date − 3, which is `cm-dot`'s twelve and `cm-eth`'s two, and none on the other six assets. And in the function that decides whether an entry waives a rule, the line `if ack.since != GENESIS and ack.rule in COMPARISON_RULES:`, under which a last ok body at or after `since` is compared. `cm-avaxc` and `cm-avaxp` take `LABS_NEWEST_DAYS`, the Labs assets' source-level bound, in place of `NEWEST_DAYS["cm-asset"]`: O1's read-back (c) found each body's newest row complete, showing no `PriceUSD` ahead of the network metrics, and 19 `avaxc` and 12 `avaxp` days of the last 90 completing more than 19 h 37 min past D+1 00:00Z, so a date − 1 source bound would grade those days 2 and page at 25 h (*Spec deviations*).

- [ ] **Step 1: The failing tests,** in `tests/test_vintage_sources.py`, every body from Task 1's fixtures and every tick at `BASE_TICK_START` unless named:
  - `test_the_fetch_table_is_pinned`: the 18 ids in tick order; `fng` `https://api.alternative.me/fng/?limit=0`; `cm-catalog` `https://community-api.coinmetrics.io/v4/catalog-v2/asset-metrics?assets=btc,eth,sol,xrp,ada,link,doge,ltc,dot,avax,avaxc,avaxp&page_size=2000`; `cm-status` `https://status.coinmetrics.io/history.atom`; `mempool-hashrate` `https://mempool.space/api/v1/mining/hashrate/all`; `bg-*` `https://api.bitcoin-data.com/v1/<metric>`; each file name and provider as above; `len` of each `ASSET_METRICS` list 31, 31, 26, 26, 24, 23, 22, 22, 17, 17 for btc, eth, doge, ltc, ada, xrp, link, dot, avaxc, avaxp.
  - `test_every_cm_url_asks_its_assets_catalog_list_with_both_flags`: per asset, the URL's query parses to `assets=<asset>`, `metrics` equal to the catalog fixture's daily list for that asset in its order, `frequency=1d`, `format=json_stream`, both `ignore_*` flags `true`.
  - `test_no_bg_url_carries_a_query_and_no_url_names_a_kraken_host`.
  - `test_each_source_kinds_fixture_grades_ok`: `fng.json`, `cm-btc`, `cm-dot`, `cm-avaxc`, `cm-catalog`, `cm-status`, `mempool-hashrate`, `bg-sopr` each grade 0 with `last_ok` None.
  - `test_a_broken_body_grades_2`, parametrised: `fng` with `metadata.error` set, `fng` with a row lacking `timestamp`, a `cm-<asset>` line that is not an object, a `cm-<asset>` line lacking `time`, a catalog with an empty `data`, a feed with no `<entry`, a `mempool-hashrate` with an empty `hashrates`, a bg row lacking its value key: each outcome 2, a reason, a `("*", "shape")` entry.
  - `test_a_body_in_the_wrong_shape_grades_2_and_never_raises` (Review Focus): a bg 200 that is a JSON object, a `cm-<asset>` line that is `[]`, an `fng` whose `data` is an object, a body that is not UTF-8: outcome 2, no exception.
  - `test_a_non_identity_encoding_grades_2`: `content_encoding="gzip"` gives `("*", "encoding")`; `None`, `""` and `"identity"` do not.
  - `test_an_absent_pinned_metric_grades_2_and_names_it`: `second/cm-btc-metric-gone` gives `metrics_absent == (<that metric>,)`.
  - `test_a_metric_past_its_freshness_bound_grades_2`: a `cm-btc` body edited in memory so one metric's newest day is the tick's date − 4 gives `(metric, "freshness")`; at date − 3 it grades 0; `cm-dot` at the base tick grades 0 with every `DOT_STOPPED` entry in `acknowledged`, and a `cm-dot` body whose non-stopped `CapMrktEstUSD` stops at date − 4 grades 2; `second/cm-btc-frozen` with `last_ok` None gives `(<its metric>, "freshness")` alone.
  - `test_the_labs_assets_take_date_minus_30`: an `avaxc` metric at date − 31 grades 2; at date − 10 it grades 0, where a date − 3 bound would grade it 2.
  - `test_never_shorter_at_the_top_and_bottom`: against `last_ok = summarise(base)`, `second/cm-btc-lost-newest` gives `(m, "top")` per pinned network metric; a body whose oldest day of a metric moved one day later gives `(m, "bottom")`; one whose `ReferenceRate` oldest moved later grades 0; a `cm-dot` body whose stopped `SplyCur` lost its newest day gives `("SplyCur", "top")`.
  - `test_a_collapse_grades_2`: a body at 89% of `last_ok.rows` gives `("*", "collapse")`; at 90% it grades 0; `second/cm-btc-collapse` against `summarise(base)` gives `metrics_failed == (("*", "collapse"),)` and `metrics_absent == ()`.
  - `test_the_source_level_newest_bound`: a `cm-btc` whose newest row is date − 2 gives `("*", "newest")` and date − 1 grades 0; `mempool-hashrate` date − 4 and − 3; `fng` date − 2 and − 1; bg date − 10 and − 9; an `avaxc` newest row at date − 31 gives `("*", "newest")` and at date − 10 grades 0.
  - `test_a_paginated_catalog_grades_2`: `second/cm-catalog-paginated` gives `("*", "pagination")`.
  - `test_the_bg_check`: against the base's summary, `second/bg-sopr-rolled` grades 0, `second/bg-sopr-newest-back` gives `("*", "top")`, `second/bg-sopr-collapse` gives `("*", "collapse")`, and no bg reason holds a byte of its body.
  - `test_an_acknowledgment_holds_from_its_tick`: with `Acknowledgment("cm-btc", m, "freshness", S)`, a frozen `m` grades 2 at a tick before `S` and 0 at `S`, the check naming the entry; with `Acknowledgment("cm-btc", "*", "collapse", S)`, a collapsed body grades 0 while `last_ok_tick` is before `S` and 2 when it is at or after `S`.
  - `test_keys_outside_the_pinned_list_are_ignored_by_the_check` (Review Focus): `cm-btc` with every row also carrying `FlowInExNtv-status` and `FlowInExNtv-status-time` grades 0, naming neither.
  - `test_the_named_exemptions_are_the_genesis_entries`: the entries at `GENESIS` are exactly `cm-dot` × the twelve metrics this plan's read lists (spelt in the test, never read from `DOT_STOPPED`) × `freshness`, `cm-eth` × `HashRate` and `SplyExpFut10yr` (spelt likewise) × `freshness`, and, per asset, each pinned `ReferenceRate*` × `bottom`.
- [ ] **Step 2: Run them and read them fail.**
- [ ] **Step 3: `cli/vintage/sources.py`**, with the pinned lines above. The parse is `json.loads(…, parse_int=str, parse_float=str)`; a day is the UTC day of `time` (ISO), `timestamp` (epoch seconds, a string for `fng`, an integer for `mempool-hashrate`) or `d`; a structure failure is caught inside `check_body` and graded, never raised.
- [ ] **Step 4: The task's run, the gate, commit** `feat(vintage): the fetch table and the lenient check`.
- [ ] **Step 5: Probes,** `--file cli/vintage/sources.py`, each KILLED:
  - `test_a_metric_past_its_freshness_bound_grades_2`: `s/^FRESHNESS_DAYS = 3$/FRESHNESS_DAYS = 4/`.
  - `test_the_labs_assets_take_date_minus_30`: `s/^LABS_FRESHNESS_DAYS = 30$/LABS_FRESHNESS_DAYS = 9/`.
  - `test_a_collapse_grades_2`: `s/^COLLAPSE_FLOOR = 0\.9$/COLLAPSE_FLOOR = 0.8/`.
  - `test_the_source_level_newest_bound`: `s/"cm-asset": 1,/"cm-asset": 2,/`; `s/"bg": 9}/"bg": 10}/`; and `s/^LABS_NEWEST_DAYS = LABS_FRESHNESS_DAYS$/LABS_NEWEST_DAYS = 1/`.
  - `test_every_cm_url_asks_its_assets_catalog_list_with_both_flags`: `s/&ignore_forbidden_errors=true//`.
  - `test_the_named_exemptions_are_the_genesis_entries`: `/^DOT_STOPPED = ($/,/^)$/{/^    "\(PriceBTC\|ROI1yr\|ROI30d\)",$/d}`; and `s/^ETH_STOPPED = ("HashRate", "SplyExpFut10yr")$/ETH_STOPPED = ("HashRate",)/`.
  - `test_never_shorter_at_the_top_and_bottom`: `s/metric\.startswith("ReferenceRate")/metric.startswith("ReferenceRateX")/`.
  - `test_an_acknowledgment_holds_from_its_tick`: `s/if ack\.since != GENESIS and ack\.rule in COMPARISON_RULES:/if False:/`.
  - `test_a_non_identity_encoding_grades_2`: the identity test widened to admit `gzip`.
  - `test_a_paginated_catalog_grades_2`: the `next_page_url` test's key misspelt.
  - `test_keys_outside_the_pinned_list_are_ignored_by_the_check`: the per-metric loop taken over every key of the body rather than the pinned list.
  - `test_a_body_in_the_wrong_shape_grades_2_and_never_raises`: the `except` that grades a structure failure narrowed to `json.JSONDecodeError`.
  - `test_the_fetch_table_is_pinned`: `s/fng\/?limit=0"/fng\/?limit=10"/`.
  - `test_no_bg_url_carries_a_query_and_no_url_names_a_kraken_host`: a `bg-*` URL given a query string.
  - `test_each_source_kinds_fixture_grades_ok`: `s/"bg": 9}/"bg": 6}/` (the `bg-sopr` fixture's newest `d` sits at date − 7).
  - `test_a_broken_body_grades_2`: the `fng` `metadata.error` test removed.
  - `test_an_absent_pinned_metric_grades_2_and_names_it`: the presence check removed.
  - `test_never_shorter_at_the_top_and_bottom`: the never-shorter-at-the-top comparison removed.
  - `test_the_bg_check`: the `bg-*` oldest-day exemption removed, so a rolled window grades 2.

### Task 3: The exchange (D4, D7, D20)

**Files:** Create `cli/vintage/credential.py`, `cli/vintage/fetch.py`, `tests/vintage_stub.py`, `tests/test_vintage_fetch.py`.

**Interfaces:**
- Consumes: Task 2's `Source`, `SOURCES`; Task 1's `SENTINEL_KEY`, `SENTINEL_FORMS`, `body`.
- Produces, in `tests/vintage_stub.py`: `FakeClock(start: datetime)` with `now() -> datetime`, `monotonic() -> float` (0.0 at `start`, so it never reads near `now().timestamp()`), `sleep(seconds: float) -> None` advancing both, `slept: list[float]`, and `watchdog(seconds: float)`, a context manager that arms nothing real, appends `seconds` to `armed: list[float]` and holds `monotonic() + seconds` in `alarm: float | None` while it is open, `None` once it closes; `Reply(status: int = 200, body: bytes = b"", headers: Sequence[tuple[str, str]] = (), reason: str = "OK", chunk_seconds: float = 0.0, chunk_bytes: int = 65536, stall_after: int | None = None, stall_open: bool = False)`, where `stall_open` makes `https_open` a call that never returns, and `stall_after` makes the response's `read1` and `read` return no byte past that count and then such a call, as a trickled status line, header or chunk framing is: with a watchdog open, the clock moves to its `alarm` and `cli.vintage.fetch.Deadline` is raised; with none open, the call returns 3,000 s later on the clock, `https_open` its response and a read the rest of the body, as a trickle that ends does; `FakeHTTPS(urllib.request.HTTPSHandler)`, `__init__(self, script: Mapping[str, Sequence[Reply | BaseException]], clock: FakeClock)`, whose `https_open(req)` pops the URL's next item (raising an exception item, failing on a URL with none left), records `Seen(url, headers: dict, unredirected: dict, timeout: float | None)` in `self.seen`, `timeout` read from `req.timeout`, and returns a response exposing `status`, `code`, `reason`, `msg`, `version` (11), `headers`, `info()`, `geturl()`, `url`, `read(n)`, which, as `http.client`'s does, gathers chunks until it holds `n` bytes or the body ends, advancing the clock by `chunk_seconds` per chunk, and `read1(n)`, which returns the next chunk alone, at most `n` bytes, advancing the clock by one `chunk_seconds`.
- Produces, in `cli/vintage/credential.py`: `class ApiKey` (`reveal() -> str`; `str` and `repr` read `<redacted>`); `B64TOKEN = re.compile(r"[A-Za-z0-9._~+/-]+=*")`; `read_key(stream: BinaryIO | None) -> tuple[ApiKey | None, str | None]`, the reason `no credential` (no stream, an `OSError`, empty after stripping trailing whitespace) or `malformed credential` (not a `B64TOKEN.fullmatch`); `key_forms(key: ApiKey) -> tuple[bytes, bytes, bytes, bytes]` (raw; `/` as `\/`; `urllib.parse.quote(raw, safe="")`, spelt so, the module's one `safe=`; that with its hex in lower case); `holds_key(data: bytes, forms) -> bool`; `decode_for_scan(body: bytes, content_encoding: str | None, *, max_bytes: int) -> bytes | None` (identity, `gzip`, `deflate` zlib or raw, `zstd` through `compression.zstd`, a comma list undone right to left, each through a streaming decompressor whose output is bounded at `max_bytes`, `zlib.decompressobj(...).decompress(data, max_bytes + 1)` and `ZstdDecompressor().decompress(data, max_bytes + 1)`, after which a layer is decoded only when its decompressor's `eof` is true and its `unused_data` is empty, since one call stops without raising at the end of the first gzip member or zstd frame; `None` for any other encoding, for bytes that do not decode under the named one (a decompressor raising, the catch naming `zlib.error` and `compression.zstd.ZstdError`, which is no subclass of it; a layer ending with `eof` false, as a truncated stream does; a layer leaving `unused_data`, as a second member or frame or trailing bytes do), and for decoded output past `max_bytes`; `fetch.py` passes `SIZE_CAP_BYTES`).
- Produces, in `cli/vintage/fetch.py`: `class Deadline(Exception)`, no `OSError`, so neither urllib's `URLError` wrapping nor the transport-error catch takes it; `class Clock(Protocol)` as `FakeClock` (`now`, `monotonic`, `sleep`, `watchdog`), and `SystemClock`, whose `watchdog(seconds: float)` is a context manager that installs a `SIGALRM` handler raising `Deadline`, arms `signal.setitimer(signal.ITIMER_REAL, seconds)`, and in a `finally` disarms it with `signal.setitimer(signal.ITIMER_REAL, 0)` before it restores the handler it replaced, so a late alarm never meets the default action, which ends the process; `@dataclass class Attempt: started_at: datetime; ended_at: datetime; duration_seconds: float; status: int | None; error: str | None; head: bytes | None; withheld: tuple[str, int] | None`; `@dataclass class Exchange: source: Source; request_headers: list[tuple[str, str]]; attempts: list[Attempt]; final_url: str | None; http_version: str | None; status: int | None; reason: str | None; headers: list[tuple[str, str]]; body: bytes | None; not_fetched: str | None`; `build_openers(https_handler: urllib.request.BaseHandler | None = None) -> tuple[urllib.request.OpenerDirector, urllib.request.OpenerDirector]` (plain, and keyed, whose redirect handler's `redirect_request` returns `None`, so a 3xx arrives as an `HTTPError` and is the final answer); `fetch_all(sources: Sequence[Source], *, key: ApiKey | None, key_reason: str | None, openers: tuple[OpenerDirector, OpenerDirector], clock: Clock, tick_deadline: float, user_agent: str, only: frozenset[str] | None = None) -> list[Exchange]`, `tick_deadline` a `clock.monotonic()` value; with `only` given, a source whose id is outside it reads `not selected` with no request, and the rest run in `sources`' order under the same breakers and deadline (spec D7's named sources).

`not_fetched` reads, verbatim: `HTTP <status> (no retry)`, `HTTP <status> after <n> attempts`, `transport error after <n> attempts`, `timeout after <n> attempts`, `oversize <bytes>`, `body deadline <bytes>`, `tick deadline`, `breaker` (a plain host's or endpoint's: a request that has used up its attempts trips its host's when its last attempt was a transport error or a timeout, and its endpoint's alone, `urllib.parse.urlsplit(source.url)[:3]`, scheme, host and path, when its last attempt answered a 5xx or a 429; the later requests behind the tripped one read it), `breaker (HTTP <status>)` (the keyed host's, naming the 429, 401 or 403 that tripped it, as D20 has it), `budget exhausted`, `no credential`, `malformed credential`, `credential echoed`, `credential unscannable`, `HTTP <status> redirect not followed`, `not selected`. An attempt's `error` is `<class>: <text>` off the keyed host and `<class>` alone on it. The pinned lines:

```python
SOCKET_TIMEOUT_SECONDS = 30
BODY_DEADLINE_SECONDS = 120
MAX_ATTEMPTS = 3
RETRY_AFTER_CAP_SECONDS = 300
BACKOFF_SECONDS = (30, 120)
HOST_SPACING_SECONDS = 1
SIZE_CAP_BYTES = 64 * 1024 * 1024
HEAD_BYTES = 4096
KEYED_RETRY_WAIT_SECONDS = 30
KEYED_RETRIES_PER_TICK = 1
REDACTED_AUTHORIZATION = ("Authorization", "Bearer <redacted>")
```

and, in the keyed request's builder, `request.add_unredirected_header("Authorization", f"Bearer {key.reveal()}")`; and every attempt dials through one helper, whose body is this one line, the module's one call of an opener's `open`, which Task 11's write guard exempts by the helper's name, since its first argument is a `Request`, never a mode:

```python
def _dial(opener: urllib.request.OpenerDirector, request: urllib.request.Request):
    return opener.open(request, timeout=SOCKET_TIMEOUT_SECONDS)
```

Every request carries `Accept-Encoding: identity` and `User-Agent: <user_agent>` and no conditional header; `request_headers` is built from the function's own list, sorted by name, the keyed one carrying `REDACTED_AUTHORIZATION`, never from `Request.header_items()`. A response's headers are kept as ordered pairs, duplicates kept, `Set-Cookie` dropped in any case; on the keyed host a header name or value, or the status line's reason phrase, holding the key in any of its forms is stored as `<redacted>`. The fields a keyed exchange keeps from the response are its status (an integer), `http_version` (from `http.client`'s 10 or 11), `final_url` (the request's own, since no redirect is followed), the reason phrase, the header names and values, and the body: the last three are the server's text, and each is scanned. Nothing of a keyed exchange is kept before the scan has read the reason phrase, every header name and value and the whole received body, decoded where `decode_for_scan` can, before a retried attempt's `head` is cut. No byte a server sends raises out of `fetch_all`: a `Content-Encoding` whose bytes do not decode, or decode past the cap, reads `credential unscannable` on the keyed host, the one host whose bodies are decoded; a `Retry-After` it cannot read falls back (Review Focus); an `X-RateLimit-Remaining-*` value that is not a decimal integer reads as not 0; a read that fails mid-body (`http.client.HTTPException`, `OSError`) is a transport error. A header is looked up by its name in any case, `Content-Encoding` and `X-RateLimit-Remaining-*` among them.

- [ ] **Step 1: The failing tests,** in `tests/test_vintage_fetch.py`, over `build_openers(FakeHTTPS(...))` and a `FakeClock`, but for the system watchdog's case, which reads `SystemClock` over a loopback server:
  - `test_retry_after_is_honoured_and_capped`: a 503 with `Retry-After: 7` then a 200 sleeps 7; `Retry-After: 900` sleeps 300; an HTTP-date 40 s ahead sleeps 40; none sleeps 30 then 120; a 429 on `cm-btc` with `Retry-After: 7` then a 200 sleeps 7 and is fetched.
  - `test_a_socket_timeout_is_retried_and_named`, parametrised on `TimeoutError` raised by `FakeHTTPS` and wrapped as a `urllib.error.URLError`'s `reason`: three on `fng` give `timeout after 3 attempts`, two then a 200 fetch it.
  - `test_a_retry_after_in_the_past_or_unparseable_falls_back` (Review Focus): `0`, `-5`, a past HTTP-date and `soon` each sleep 30 first, and no sleep is negative.
  - `test_a_403_or_404_is_never_retried`: a 403 on `cm-btc` (`second/cm-btc-403`) and a 404 on `bg-sopr` (`second/bg-sopr-404`) each take one attempt, the body kept whole, `not_fetched == "HTTP 403 (no retry)"` and `"HTTP 404 (no retry)"`.
  - `test_a_non_2xx_final_answer_is_kept_whole`: three 503s keep the third's whole body, `HTTP 503 after 3 attempts`.
  - `test_a_retried_attempt_keeps_its_first_4_kib`: a 503 of 10 KiB then a 200 leaves `attempts[0].head` the first 4096 bytes and `attempts[1].head` None.
  - `test_the_breaker`, parametrised, no `Retry-After` served, so every case ends inside the tick deadline: `urllib.error.URLError` three times on `cm-btc` (`transport error after 3 attempts`) leaves the nine later `cm-<asset>` and `cm-catalog` `breaker` with no request seen, the host tripped; a 503 three times and a 429 three times on `cm-btc` (`HTTP 503 after 3 attempts`, `HTTP 429 after 3 attempts`) leave the nine later `cm-<asset>`, its endpoint, `breaker` with no request seen, and `cm-catalog`, on the other endpoint, dialled and fetched; and a 503 then a 200 on `cm-btc` trips nothing, every later `cm-<asset>` dialled.
  - `test_the_body_deadline_cuts_a_trickle`: a 200 of 100 chunks of 10 bytes (`chunk_bytes=10`), each taking 30 s, is cut once 120 s have passed: `body` None, `withheld == ("body deadline", <bytes read>)` with at most 50 bytes read, and the attempt's `duration_seconds` at most 150; a read that waits for 65,536 bytes returns only at the body's end, 3,000 s and 1,000 bytes in.
  - `test_a_call_that_never_returns_ends_at_the_watchdog`, parametrised, over `fng` and `mempool-hashrate` alone (the two `SOURCES` with those ids): a 200 on `fng` whose read stalls after 10 bytes (`stall_after=10`) gives `body` None, `withheld == ("body deadline", 10)` and `duration_seconds == 120`; a `stall_open` reply on `fng` gives `withheld == ("body deadline", 0)` and `duration_seconds == 120`; a `stall_open` reply on `fng` with `tick_deadline` 50 s after the clock's start gives `tick deadline`, `duration_seconds == 50`, and `mempool-hashrate` `tick deadline` with no request seen; in each, `clock.armed[0]` is that attempt's 120 or 50, and `clock.alarm` is None after `fetch_all` returns.
  - `test_the_system_watchdog_ends_a_trickled_framing_read`, parametrised, against a loopback server on `127.0.0.1` in a thread (no network call) that answers `HTTP/1.1 200 OK` with `Transfer-Encoding: chunked` and then sends one byte every 0.1 s for 5 s: inside a chunk-size line; as trailer lines after the `0` chunk; and, before any header, inside the status line itself. `urllib.request.urlopen(<its http URL>, timeout=30)` and a `read1(65536)` loop inside `SystemClock().watchdog(0.5)` raise `Deadline` within 2 s of `time.monotonic()`, and after the `with`, `signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)` and `signal.getsignal(signal.SIGALRM)` is the handler read before it. A fourth case leaves `SystemClock().watchdog(5)` at once and reads the same two, disarming the timer in its own `finally`, so a mutant's live timer never reaches pytest.
  - `test_the_tick_deadline`: with `tick_deadline` passed after the fifth source, every later source reads `tick deadline` and none is dialled; and, with `tick_deadline` 400 s after the clock's start, `fng` answering 503 with `Retry-After: 300` on every attempt makes two attempts and reads `tick deadline`, its second wait cut so `clock.monotonic()` reads exactly 400.0 once `fetch_all` returns, and no later source is dialled.
  - `test_the_size_cap`: a body of `64 * 1024 * 1024 + 1` bytes, spelt so in the test and never through the module's constant, is withheld as `oversize`, with the count.
  - `test_requests_to_a_host_are_a_second_apart_and_ask_identity`: each request's `headers` are exactly `Accept-Encoding: identity` and the user agent; `Authorization` is in neither `headers` nor `unredirected` on every request whose host is not `api.bitcoin-data.com`, and in `unredirected` alone on every request whose host is; each request's `timeout` is 30; and the clock shows at least 1 s between two requests to one host.
  - `test_set_cookie_is_dropped_and_duplicates_are_kept`.
  - `test_the_keyed_requests_run_first`: the first four requests seen are the four `bg-*`, in order.
  - `test_a_source_outside_only_is_never_dialled`: with `only=frozenset({"cm-eth", "fng"})`, `FakeHTTPS.seen` holds `fng`'s URL and then `cm-eth`'s and nothing else, both fetched, and each of the 16 other sources reads `not selected` with no attempt.
  - `test_one_retry_per_tick_on_the_keyed_host`: `bg-sopr` 503 then 200 waits 30 s and is fetched; `bg-asopr` 503 is then not retried and reads `HTTP 503 after 1 attempts`; a transport error takes the one retry the same way.
  - `test_a_429_401_or_403_on_the_keyed_host_trips_its_breaker`: each, on `bg-sopr` (the 429 serving `second/bg-sopr-429` with `X-RateLimit-Remaining-Day: 3`, the 401 and the 403 a body that echoes nothing), is not retried and leaves the other three `breaker (HTTP 429)`, `breaker (HTTP 401)` or `breaker (HTTP 403)`, undialled.
  - `test_a_remaining_header_at_zero_stops_the_keyed_host`: `X-RateLimit-Remaining-Day: 0` on an ok `bg-sopr` keeps it and leaves the other three `budget exhausted`, undialled; the same for `-Hour`, and for `x-ratelimit-remaining-day: 0` spelt in lower case; `X-RateLimit-Remaining-Day: soon` stops nothing and raises nothing.
  - `test_a_keyed_request_follows_no_redirect`: a 302 to another host is the final answer, its body kept, `final_url` the request's URL, `HTTP 302 redirect not followed`, one request seen.
  - `test_the_key_rides_an_unredirected_header_alone`: `FakeHTTPS` sees `Bearer <SENTINEL_KEY>` under `Authorization` in `unredirected` alone, never in `headers` or the URL; `request_headers` holds `("Authorization", "Bearer <redacted>")`.
  - `test_a_missing_or_malformed_key_dials_nothing_on_the_keyed_host`: `key=None` with `no credential`, and with `malformed credential`, leave the four `bg-*` with that reason and no attempt, every other source fetched.
  - `test_read_key`: `b"<SENTINEL_KEY>\n"` reads the key; `b""`, `None` and a stream raising `OSError` read `no credential`; `b"two words\n"` reads `malformed credential`; `str` and `repr` of the key read `<redacted>`.
  - `test_the_scan_reads_every_form_and_every_decodable_encoding`: `key_forms(ApiKey(SENTINEL_KEY)) == SENTINEL_FORMS`, and `holds_key` finds each of `SENTINEL_FORMS` set inside other bytes; `decode_for_scan` undoes `gzip`, `deflate` (zlib and raw) and `zstd`, and returns None for `br`, for non-gzip bytes labelled `gzip`, for a gzip whose output passes `max_bytes`, for a gzip of two members whose second holds the key, for one gzip member followed by the key as raw bytes, for a zlib stream followed by a second one holding the key, for a raw deflate stream followed by the key as raw bytes, for two zstd frames whose second holds the key, and for a gzip cut before its trailer.
  - `test_an_undecodable_or_expanding_keyed_body_is_unscannable`: a 200 on `bg-sopr` labelled `Content-Encoding: gzip` over bytes that are not gzip, and one whose gzip expands to 2 MiB with `cli.vintage.fetch.SIZE_CAP_BYTES` monkeypatched to 1 MiB, each leave `body` None and read `credential unscannable`, and every other source is fetched.
  - `test_an_echoing_reason_phrase_or_header_name_is_redacted`: a 401 on `bg-sopr` whose reason phrase is `f"bad {SENTINEL_KEY}"` keeps `reason == "<redacted>"`, and a 200 carrying a header named with the key keeps that name `<redacted>`.
  - `test_an_echoing_keyed_answer_is_withheld`: a 200 echoing the key raw, JSON-escaped, percent-encoded upper and lower, each the matching `SENTINEL_FORMS` entry, and gzip-encoded (its header spelt `Content-Encoding` and, in a second case, `content-encoding`), each leave `body` None, `withheld == ("credential echoed", <bytes>)`, `credential echoed`; a `WWW-Authenticate` echo is stored `<redacted>`; a `Content-Encoding: br` body reads `credential unscannable`; a 503 echoing it in its first 4 KiB, then a 200, leaves `attempts[0].head` None.
  - `test_an_exception_on_the_keyed_path_is_recorded_by_its_class`: `FakeHTTPS` raising `ValueError("Invalid header value %r" % (b"Bearer " + SENTINEL_KEY.encode()))` on `bg-sopr` leaves `attempts[0].error == "ValueError"`.
- [ ] **Step 2: Run them and read them fail.**
- [ ] **Step 3: `credential.py`, `fetch.py` and `tests/vintage_stub.py`** with the pinned lines. A non-2xx answer is the `HTTPError` urllib raises, read as the response it wraps; the body's data is read by `read1(65536)` (the wrapped response's on an `HTTPError`), which returns once data bytes arrive, never by `read(65536)`, which waits for 65,536 bytes or the body's end however many socket reads that takes, and the size cap, the body deadline and the tick deadline are checked between chunks against `clock.monotonic()`; the dial is `_dial`, its `timeout` `SOCKET_TIMEOUT_SECONDS`. That check bounds no call that does not return: `urlopen` reads the TLS handshake, the status line and the headers, and `http.client` reads a chunked answer's chunk-size lines, their extensions, each chunk's closing CRLF and the trailer lines inside one `read1`, each bounded per receive alone (spec D7). So each attempt runs inside `clock.watchdog(min(BODY_DEADLINE_SECONDS, tick_deadline - clock.monotonic()))`, opened just before the opener's `open` and closed once the body's last byte is read, the scan, the decode, the backoff and the host spacing outside it, and a dial is made only while `tick_deadline - clock.monotonic()` is above 0, since `setitimer` given 0 disarms; every wait before a dial (a retry's backoff or `Retry-After`, the keyed retry's 30 s, the host spacing) is slept as `clock.sleep(max(0.0, min(wait, tick_deadline - clock.monotonic())))`, cut at the tick deadline and never used to skip a retry, so a request whose wait reached the deadline reads `tick deadline` and the tick ends at 20 minutes (spec D7); `Deadline` is caught outside the `with`, before any broader `except`, and reads as the between-chunks cut does: `tick deadline` where the tick deadline was the earlier, else `withheld == ("body deadline", <bytes read>)`, 0 where no response had arrived. `fetch_all` runs in the CLI's main thread, the one thread a signal handler is installed from and run in.
- [ ] **Step 4: The task's run, the gate, commit** `feat(vintage): the exchange, its bounds and the key's one header`.
- [ ] **Step 5: Probes,** `--file cli/vintage/fetch.py`, each KILLED:
  - `test_retry_after_is_honoured_and_capped`: `s/^RETRY_AFTER_CAP_SECONDS = 300$/RETRY_AFTER_CAP_SECONDS = 900/`.
  - `test_a_retried_attempt_keeps_its_first_4_kib`: `s/^HEAD_BYTES = 4096$/HEAD_BYTES = 4000/`.
  - `test_the_size_cap`: `s/^SIZE_CAP_BYTES = 64 \* 1024 \* 1024$/SIZE_CAP_BYTES = 128 * 1024 * 1024/`.
  - `test_the_body_deadline_cuts_a_trickle`: `s/^BODY_DEADLINE_SECONDS = 120$/BODY_DEADLINE_SECONDS = 600/`; and `read1` replaced by `read` at the body's read.
  - `test_a_call_that_never_returns_ends_at_the_watchdog`: the attempt's `clock.watchdog(…)` replaced by `contextlib.nullcontext()`; the watchdog opened after the opener's `open` returns; and its seconds taken as `BODY_DEADLINE_SECONDS` alone, the tick deadline left out.
  - `test_the_system_watchdog_ends_a_trickled_framing_read`: the `setitimer` call that arms removed; the disarm in the `finally` removed; and the restore of the replaced handler removed.
  - `test_requests_to_a_host_are_a_second_apart_and_ask_identity`: `s/^HOST_SPACING_SECONDS = 1$/HOST_SPACING_SECONDS = 0/`.
  - `test_one_retry_per_tick_on_the_keyed_host`: `s/^KEYED_RETRIES_PER_TICK = 1$/KEYED_RETRIES_PER_TICK = 2/`.
  - `test_the_key_rides_an_unredirected_header_alone`: `s/add_unredirected_header("Authorization"/add_header("Authorization"/`.
  - `test_a_403_or_404_is_never_retried`: the retry predicate admitting every 4xx.
  - `test_the_breaker`: the breaker's trip removed; the trip read off transport errors alone, a request that used up its attempts on 5xx or 429 tripping nothing; a 5xx or 429 trip keyed on the host rather than the endpoint; and a transport trip keyed on the endpoint rather than the host.
  - `test_the_tick_deadline`: the tick-deadline test before a dial removed; a retry's wait slept whole rather than cut at the tick deadline; and a retry whose wait would cross the tick deadline skipped, the request read `HTTP <status> after <n> attempts`.
  - `test_the_keyed_requests_run_first`: the keyed sources moved after the others.
  - `test_a_source_outside_only_is_never_dialled`: the `only` test removed, every source dialled.
  - `test_a_429_401_or_403_on_the_keyed_host_trips_its_breaker`: 429 admitted to the keyed retry.
  - `test_a_remaining_header_at_zero_stops_the_keyed_host`: the `X-RateLimit-Remaining-Hour` read removed.
  - `test_a_keyed_request_follows_no_redirect`: the keyed opener built without its redirect refusal.
  - `test_a_retry_after_in_the_past_or_unparseable_falls_back`: the floor at 0 removed from a Retry-After in seconds.
  - `test_requests_to_a_host_are_a_second_apart_and_ask_identity`, a second arm: the `Accept-Encoding: identity` header left out of the request; a third, `s/^SOCKET_TIMEOUT_SECONDS = 30$/SOCKET_TIMEOUT_SECONDS = 300/`; and a fourth, the key added to every source's request, the `source.keyed` test before `add_unredirected_header` dropped.
  - `test_a_non_2xx_final_answer_is_kept_whole`: a final non-2xx body cut to `HEAD_BYTES`.
  - `test_set_cookie_is_dropped_and_duplicates_are_kept`: the `Set-Cookie` filter removed.
  - `test_an_echoing_keyed_answer_is_withheld`: a body whose `Content-Encoding` `decode_for_scan` cannot undo kept rather than withheld.
  - `test_an_exception_on_the_keyed_path_is_recorded_by_its_class`: the keyed attempt's `error` written as `f"{type(exc).__name__}: {exc}"`.
  - `test_a_missing_or_malformed_key_dials_nothing_on_the_keyed_host`: the keyed sources dialled when `key` is `None`.
  - `test_retry_after_is_honoured_and_capped`: 429 read as a non-retried 4xx off the keyed host.
  - `test_a_socket_timeout_is_retried_and_named`: a `TimeoutError` read as a transport error.
  - `test_a_429_401_or_403_on_the_keyed_host_trips_its_breaker`: the keyed breaker's reason written `breaker` without its status.
  - `test_a_remaining_header_at_zero_stops_the_keyed_host`: the header lookup made case-sensitive; and the `Remaining` value read by a bare `int()`.
  - `test_an_echoing_keyed_answer_is_withheld`, a second arm: the `Content-Encoding` lookup made case-sensitive.
  - `test_an_echoing_reason_phrase_or_header_name_is_redacted`: the reason phrase's scan removed; and the header names' scan removed.

  `--file cli/vintage/credential.py`, each KILLED:
  - `test_read_key`: `s/\[A-Za-z0-9._~+\/-]/[A-Za-z0-9._~+\/ -]/` (a space admitted, so `two words` reads as a key).
  - `test_the_scan_reads_every_form_and_every_decodable_encoding`: the lower-case percent form left out of `key_forms`; the percent form built with `/` left unencoded, `s/safe=""/safe="\/"/`; and the `eof` and `unused_data` test after a layer's call removed, so a layer that stops before its input's end returns what it decoded, and, where the code holds that test per encoding, removed on the `deflate` layer alone too.
  - `test_an_undecodable_or_expanding_keyed_body_is_unscannable`: the decode's `except` removed, so a decode error raises; and the output bound removed, so a decoded body past `max_bytes` is returned and scanned.

### Task 4: The tick (D4, D5, D6, D9's refusals, D13)

**Files:** Create `cli/vintage/storage.py`, `cli/vintage/chain.py`, `cli/vintage/record.py`, `tests/test_vintage_record.py`; modify `tests/vintage_stub.py`.

**Interfaces:**
- Consumes: Tasks 2 and 3.
- Produces, in `cli/vintage/storage.py` (two of D18's three rename helpers, the table's in Task 10):
  - `create_exclusive(path: Path, data: bytes) -> None`, through `fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)`, `os.write` to the end, `os.fsync`, `os.close`.
  - `gzip_bytes(raw: bytes) -> bytes`, `gzip.compress(raw, compresslevel=9, mtime=0)`.
  - `fsync_dir(path: Path) -> None`, through `os.open(path, os.O_RDONLY)`.
  - `publish_tick(staged: Path, target: Path) -> None`, the tick-publish helper: `if target.exists():` refuses with `FileExistsError`; date directories made 0755; `os.rename(staged, target)`; the parent fsynced; `os.chmod(target, 0o555)`.
  - `publish_prom(path: Path, text: str) -> None`, the `.prom` helper: `tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")`, `os.write`, `os.fsync`, `os.chmod(tmp, 0o644)`, `os.replace(tmp, path)`.
- Produces, in `cli/vintage/chain.py`: `STAMP_RE = re.compile(r"\d{8}T\d{6}Z")`; `@dataclass(frozen=True) class TickFile: stamp: str; dir: Path; raw: bytes | None; sha256: str | None; manifest: dict | None; error: str | None`; `scan(record_root: Path) -> list[TickFile]`, reading `record/<YYYY>/<MM>/<DD>/<stamp>/tick.json` for names that are four, two and two digits and a stamp alone, with `sha256=hashlib.sha256(raw).hexdigest()`; `@dataclass(frozen=True) class Chain: order: tuple[TickFile, ...]; head: TickFile | None; other_heads: tuple[TickFile, ...]; off_chain: tuple[TickFile, ...]; unreadable: tuple[TickFile, ...]`; `chain(ticks: list[TickFile]) -> Chain`, the head the published tick no other tick's `prev` names, the newest stamp among several, `order` from genesis to the head along `prev`; a tick in `unreadable` is on the chain where its successor's `prev.tick` names it, and the walk goes on at the newest stamp older than it that no readable `tick.json`'s `prev` names, a tick that is then no candidate head, so one damaged `tick.json` in the middle neither cuts `order` nor adds to `other_heads`; `check_head(head: TickFile) -> str | None`, the chaining check's failure: an unparseable `tick.json`, `fetches` naming other body files than the directory holds, or a body that does not re-hash.
- Produces, in `cli/vintage/record.py`: `RECORD_SUBDIR = "record"`; `STAGING_SUBDIR = "staging"`; `TICK_DEADLINE_SECONDS = 20 * 60`; `TICK_SCHEMA = 1`; `class RecordRefused(Exception)`; `@dataclass class Published: stamp: str; dir: Path; tick_json_sha256: str; manifest: dict; exchanges: list[Exchange]; regression: bool`; `record_tick(data_dir: Path, *, key: ApiKey | None, key_reason: str | None, clock_prom: Path | None, https_handler: urllib.request.BaseHandler | None = None, clock: Clock | None = None, version: str | None = None, revision: str | None = None, only: frozenset[str] | None = None) -> Published`, `only` handed to `fetch_all` as it stands, `version` defaulting to `importlib.metadata.version("zcrypto")` and `revision`, when None, to `ZCRYPTO_BUILD_REVISION`, the user agent `zcrypto-vintage/<version>` and `recorder` `<version>+<revision[:12]>` (`<version>` alone when the revision is empty or unset); `tick_json_bytes(manifest: dict) -> bytes`, its body the one line `return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"`; `clock_block(clock_prom: Path | None, now: datetime) -> dict`.
- Produces, in `tests/vintage_stub.py`: `default_bodies() -> dict[str, bytes]`, a body per source id from Task 1's fixtures (`cm-<asset>` other than btc, dot and avaxc built from `cm-btc`'s rows, keeping `asset` renamed, `time` and the asset's pinned metrics, a `ReferenceRate*` it lacks taking `ReferenceRate`'s token; `cm-avaxp` from `cm-avaxc`; `bg-asopr`, `bg-sth-sopr`, `bg-lth-sopr` from `bg-sopr` with the value key renamed); `run_tick(data_dir: Path, at: datetime, replies: Mapping[str, Reply | bytes | BaseException | Sequence] | None = None, *, key: str | None = SENTINEL_KEY) -> Published`, `replies` overriding `default_bodies()` per source id, `version="0.0.0"`, `revision=""`, so no tick it builds, and no head `HEAD_PINS` pins from them (Task 10), reads `ZCRYPTO_BUILD_REVISION` from the environment, `clock_prom=None`; `build_record(data_dir: Path, plan: Sequence[tuple[datetime, Mapping]]) -> list[Published]`, one `run_tick` per entry.

`tick.json` carries the spec's example keys: `schema`, `tick`, `started_at`, `ended_at`, `recorder`, `prev` (`tick`, `tick_json_sha256`, `error`), `genesis_reason`, `clock` (`offset_seconds`, `synchronised`, `prom_age_seconds`, `error`), and per fetch `source`, `url`, `request_headers`, `attempts` (`started_at`, `ended_at`, `duration_seconds`, `status`, `error`, `head` as standard base64 or null, `withheld` as `{"reason", "bytes"}` or null), `final_url`, `http_version`, `status`, `reason`, `headers`, `body` (`file`, `bytes`, `sha256`, or null), `check` (Task 2's block; for outcome 1, `{"outcome": 1, "reason": <not_fetched>, …}` with the other keys null or empty). Times are UTC ISO 8601 with microseconds and `Z`. The steps of `record_tick`, in order: the stamp from `clock.now()`, floored to the second; a target that exists refuses before any request; the scan and the chain; with more than one candidate head (`chain.other_heads` not empty, a broken link), the newest stamp taken and one ERROR naming the other candidates' stamps (D5); a published tick left at 0755 set to 0555; each `staging/` entry named in one WARNING; the chaining check on the head, its failure into `prev.error` with one ERROR; `prev` null and `genesis_reason` `empty record` on an empty chain; `fetch_all` with the deadline `clock.monotonic()` at the start plus `TICK_DEADLINE_SECONDS`; the tick's staging directory made by `(data_dir / STAGING_SUBDIR / stamp).mkdir(mode=0o755, parents=True)`; per kept body `create_exclusive(staged / source.file, gzip_bytes(body))`, then the read-back, `if hashlib.sha256(_read_back(path)).hexdigest() != digest:` raising `RecordRefused`, with `staging/<stamp>/` left; `check_body` per 2xx body, with the `Content-Encoding` its response carried (`None` when it carried none), against the source's last ok body along the chain, `summarise` read from its stored file, so a 2xx served in a non-identity encoding is stored as served and graded 2 with `("*", "encoding")` (D4); each retried attempt's `head` written as `base64.b64encode(attempt.head).decode("ascii")`; `tick_bytes = tick_json_bytes(manifest)` and, before the rename, the line `witness = hashlib.sha256(tick_bytes).hexdigest()`; `tick.json` last, every file and the directory fsynced; the target checked again; `publish_tick`; the witness INFO `vintage tick published tick=<stamp> tick_json_sha256=<witness>` as soon as it returns, `Published.tick_json_sha256` being `witness`; with a stamp at or below the head's, `if stamp <= head.stamp:`, one ERROR naming both stamps, the tick still published.

- [ ] **Step 1: The failing tests,** in `tests/test_vintage_record.py`, every tick through `run_tick` under `tmp_path`, but in the five cases that hand the tick a `.prom` or read `FakeHTTPS.seen`, which `run_tick` neither takes nor returns (`test_the_clock_block`, `test_an_existing_target_refuses_before_any_request`, `test_the_tick_deadline_reads_the_monotonic_clock`, `test_one_host_answering_503_all_tick_leaves_every_other_host_recorded`, `test_the_catalog_endpoint_answering_503_all_tick_leaves_every_asset_recorded`): each calls `record_tick` with its own `FakeHTTPS` over `default_bodies()` and the case's replies, its own `FakeClock`, `key=ApiKey(SENTINEL_KEY)`, `key_reason=None`, `clock_prom` None but in `test_the_clock_block`, and `version="0.0.0"`:
  - `test_a_tick_publishes_every_body_as_served`: `record/<Y>/<M>/<D>/<stamp>/` holds `tick.json` and 18 body files; each gunzips to the bytes served, `body.bytes` and `body.sha256` match the raw bytes, and each file's bytes equal `gzip.compress(raw, compresslevel=9, mtime=0)`; files 0444, the tick directory 0555, the date directories 0755.
  - `test_tick_json_is_compact_sorted_with_a_trailing_newline`: its bytes equal `json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":")).encode() + b"\n"` computed in the test, never through `tick_json_bytes`, end `}\n` and hold one `\n`, and every key above is present with its type.
  - `test_the_same_body_twice_gives_the_same_file_bytes`: two ticks serving one body hold byte-equal files, with `gzip`'s module clock stubbed, `monkeypatch.setattr(gzip, "time", SimpleNamespace(time=<a function returning one second later at each call>))`, so a file written with any `mtime` but 0 differs between the two.
  - `test_a_non_identity_2xx_is_stored_as_served_and_graded_2`: a 200 on `cm-btc` served `Content-Encoding: gzip`, its body `gzip.compress(body("cm-btc"), mtime=0)`, is stored as its file (the stored file gunzips to the served gzip bytes), and its `check.outcome` is 2 with `["*", "encoding"]` in `check.metrics_failed`.
  - `test_a_broken_link_with_several_heads_takes_the_newest_and_names_the_others`: ticks A, B and C published, then B's directory removed (its parent and itself made writable first), so A and C both name no successor: `chain(scan(root))` holds C as `head` and A in `other_heads`, and the next tick's `prev.tick` is C's stamp with one ERROR naming A's stamp.
  - `test_an_exclusive_create_never_truncates`: `create_exclusive` over an existing path raises `FileExistsError` and the file's bytes are unchanged.
  - `test_a_non_2xx_body_is_stored_as_its_file`: a 403 on `cm-btc` stores its file, `check.outcome == 1`, reason `HTTP 403 (no retry)`.
  - `test_one_failing_source_never_stops_the_others`: `fng`, the one source on its host, answering 503 on every attempt keeps its last answer as its file with outcome 1, and the 17 others are stored and checked.
  - `test_a_retried_attempts_head_is_its_first_4_kib_in_standard_base64`: a 503 whose 10 KiB body is `bytes(range(256)) * 40`, so its base64 carries `+` and `/`, then a 200 on `fng`, gives `attempts[0].head == base64.b64encode(first_4096_bytes).decode()` and `attempts[1].head` null.
  - `test_a_read_back_mismatch_refuses_and_publishes_nothing`: `_read_back` patched to return other bytes raises `RecordRefused`, `record/` holds no tick, `staging/<stamp>/` stays.
  - `test_a_crash_before_the_rename_leaves_record_untouched`: over a record holding one earlier tick, `cli.vintage.record.publish_tick` patched to raise: the exception reaches the caller, and every path under `record/`, with its bytes and its mode, reads as before.
  - `test_an_existing_target_refuses_before_any_request`: a pre-made target raises `RecordRefused` and `FakeHTTPS.seen` is empty.
  - `test_publish_tick_refuses_an_existing_target`: an existing empty target raises `FileExistsError` and is not replaced.
  - `test_the_chain_names_the_head_and_its_sha256`: the first tick has `prev` null and `genesis_reason == "empty record"`; the second's `prev` is `{"tick": <first>, "tick_json_sha256": <sha256 of the first's tick.json bytes>, "error": None}`.
  - `test_a_stamp_regression_is_published_with_an_error`: a tick taken an hour before the head is published, one ERROR names both stamps, `prev.tick` is the head's.
  - `test_a_damaged_head_is_named_at_chaining`, parametrised on the head's `tick.json` made unparseable, one listed body removed, an unlisted file added, and one body's bytes changed: the next tick is published, `prev.error` names the failure, `prev.tick_json_sha256` is the sha256 of the bytes found (null when unreadable), one ERROR.
  - `test_the_clock_block`: from a `.prom` holding `zcrypto_clock_offset_seconds 0.001150123` and `zcrypto_clock_synchronised 1`, its mtime set 37 s before the tick, the block reads `0.001150123`, `1`, `37.0`, `null`; an absent file and an unparseable one read nulls with an `error` and the tick is published; a file whose offset reads `NaN`, as its writer publishes an offset it could not read, records `offset_seconds` null and `error` `offset not finite`, and the published `tick.json` holds no `NaN` token.
  - `test_the_witness_line_is_the_published_tick_jsons_sha256`: the INFO line equals `vintage tick published tick=<stamp> tick_json_sha256=<sha256 of the published tick.json>`.
  - `test_crash_leftovers_are_named_and_a_0755_tick_is_set_0555`: a leftover `staging/20261101T073700Z/` is named in one WARNING; a published tick dir chmodded 0755 reads 0555 after the next tick.
  - `test_the_scan_skips_what_is_not_a_tick` (Review Focus): a file in a date directory, a `.rsync-tmp` directory under `record/` and an empty date directory change neither `chain()` nor the next tick's `prev`.
  - `test_an_unreadable_middle_tick_json_keeps_the_chain_whole`: ticks A, B and C published, then B's `tick.json` made unparseable: `chain(scan(root))` holds `order` A, B, C, C as `head`, `other_heads` empty and B in `unreadable`.
  - `test_the_tick_deadline_reads_the_monotonic_clock`: `fng` and `cm-status`, the fifth and sixth sources and each the one request to its host, each answering 503 with `Retry-After: 300` on every attempt, so their waits pass the 1,200 s deadline: `cm-status` reads `tick deadline` after two attempts, `mempool-hashrate` and every later source read `tick deadline`, and no source after `cm-status` is dialled, the `FakeClock`'s `monotonic()` reading from 0.0 while its `now()` reads 2026, so a deadline taken from `clock.now()` never arrives.
  - `test_one_host_answering_503_all_tick_leaves_every_other_host_recorded`: every `community-api.coinmetrics.io` URL scripted to answer 503 with `Retry-After: 300` on each of three attempts, so a fetch that dials past the deadline meets it rather than an empty script: the four `bg-*`, `fng`, `cm-status` and `mempool-hashrate` each outcome 0 with its body stored; `cm-btc` reads `HTTP 503 after 3 attempts`; the nine later `cm-<asset>`, its endpoint, read `breaker` with no request seen for their URLs; and `cm-catalog`, on the other endpoint, is dialled and reads `tick deadline`, its second wait cut at the deadline.
  - `test_the_catalog_endpoint_answering_503_all_tick_leaves_every_asset_recorded`: the `cm-catalog` URL and `fng`'s, the one request to another host, each scripted to answer 503 with `Retry-After: 300` on each of three attempts, so `fng`'s waits spend about 600 s of the deadline before `community-api.coinmetrics.io` is dialled: `fng` reads `HTTP 503 after 3 attempts`; every `cm-<asset>` is dialled and reads outcome 0 with its body stored, as do the four `bg-*`, `cm-status` and `mempool-hashrate`; and `cm-catalog` is dialled and reads `tick deadline`, its second wait cut at the deadline.
- [ ] **Step 2: Run them and read them fail.**
- [ ] **Step 3: `storage.py`, `chain.py`, `record.py`, and `tests/vintage_stub.py`'s builders,** with the pinned lines. Logger `get_logger("vintage.record")`.
- [ ] **Step 4: The task's run, the gate, commit** `feat(vintage): the tick, published by one rename and chained to its predecessor`.
- [ ] **Step 5: Probes,** each KILLED. `--file cli/vintage/storage.py`:
  - `test_an_exclusive_create_never_truncates`: `s/ | os\.O_EXCL, 0o444)/, 0o444)/`.
  - `test_a_tick_publishes_every_body_as_served`: `s/os\.O_EXCL, 0o444)/os.O_EXCL, 0o644)/`; and `s/os\.chmod(target, 0o555)/pass/`; and `s/compresslevel=9, mtime=0/compresslevel=6, mtime=0/`.
  - `test_publish_tick_refuses_an_existing_target`: `s/if target\.exists():/if False:/`.
  - `test_the_same_body_twice_gives_the_same_file_bytes`: `s/compresslevel=9, mtime=0)/compresslevel=9, mtime=None)/`.

  `--file cli/vintage/record.py`:
  - `test_a_read_back_mismatch_refuses_and_publishes_nothing`: `s/!= digest:/!= digest and False:/`.
  - `test_a_stamp_regression_is_published_with_an_error`: `s/if stamp <= head\.stamp:/if False:/`.
  - `test_an_existing_target_refuses_before_any_request`: the early target check removed.
  - `test_crash_leftovers_are_named_and_a_0755_tick_is_set_0555`: the WARNING naming the leftovers removed.
  - `test_the_clock_block`: the absent file's branch raising instead of recording nulls; and a non-finite offset kept as read.
  - `test_tick_json_is_compact_sorted_with_a_trailing_newline`: `s/\.encode() + b"\\n"$/.encode()/`.
  - `test_a_non_2xx_body_is_stored_as_its_file`: a non-2xx body left unstored.
  - `test_a_retried_attempts_head_is_its_first_4_kib_in_standard_base64`: `s/base64\.b64encode(attempt\.head)/base64.urlsafe_b64encode(attempt.head)/`.
  - `test_a_crash_before_the_rename_leaves_record_untouched`: `s/^STAGING_SUBDIR = "staging"$/STAGING_SUBDIR = "record\/.staging"/` (the tick assembled under `record/`).
  - `test_the_witness_line_is_the_published_tick_jsons_sha256`: `s/witness = hashlib\.sha256(tick_bytes)\.hexdigest()/witness = hashlib.sha256(tick_bytes.strip()).hexdigest()/`.
  - `test_a_non_identity_2xx_is_stored_as_served_and_graded_2`: the `Content-Encoding` handed to `check_body` as `None`.
  - `test_a_broken_link_with_several_heads_takes_the_newest_and_names_the_others`: the ERROR naming the other candidates removed.
  - `test_the_tick_deadline_reads_the_monotonic_clock`: the deadline handed to `fetch_all` computed from `clock.now().timestamp()` rather than `clock.monotonic()`.

  `--file cli/vintage/fetch.py`:
  - `test_one_failing_source_never_stops_the_others`: the per-source loop ended at the first source not fetched.
  - `test_one_host_answering_503_all_tick_leaves_every_other_host_recorded`: a 5xx or 429 trip keyed on the host rather than the endpoint, so `cm-catalog` reads `breaker` undialled.

  `--file cli/vintage/sources.py`:
  - `test_one_host_answering_503_all_tick_leaves_every_other_host_recorded`: `cm-status` and `mempool-hashrate` moved after `cm-catalog`, to the end of `SOURCES`, where the earlier draft ran them after `community-api.coinmetrics.io`'s sources, so both read `tick deadline`.
  - `test_the_catalog_endpoint_answering_503_all_tick_leaves_every_asset_recorded`: `cm-catalog` moved back before `cm-btc` in `SOURCES`, the earlier order, so its waits run the deadline out and every `cm-<asset>` reads `tick deadline` undialled.

  `--file cli/vintage/chain.py`:
  - `test_the_chain_names_the_head_and_its_sha256`: `s/hashlib\.sha256(raw)\.hexdigest()/hashlib.sha256(raw.strip()).hexdigest()/`.
  - `test_a_damaged_head_is_named_at_chaining`: `check_head`'s body re-hash removed.
  - `test_the_scan_skips_what_is_not_a_tick`: the stamp's full match loosened to a search.
  - `test_a_broken_link_with_several_heads_takes_the_newest_and_names_the_others`: the oldest stamp taken among several candidates.
  - `test_an_unreadable_middle_tick_json_keeps_the_chain_whole`: the walk stopped at an unreadable tick.

### Task 5: Verify (D15)

**Files:** Create `cli/vintage/verify.py`, `cli/vintage/command.py`, `tests/test_vintage_verify.py`; modify `cli/vintage/sources.py`, `cli/__main__.py`.

**Interfaces:**
- Consumes: Task 4's `scan`, `chain`, `TickFile`; `tests/vintage_stub.py`'s `build_record`.
- Produces, in `cli/vintage/sources.py`: `@dataclass(frozen=True) class LinkAcknowledgment: successor: str; recorded_prev_sha256: str; witnessed_sha256: str`; `LINK_ACKNOWLEDGMENTS: tuple[LinkAcknowledgment, ...] = ()`; `@dataclass(frozen=True) class ForkAcknowledgment: off_chain: str; tick_json_sha256: str; lost: bool = False`, a fork's tick off the chain by its stamp and the sha256 pinned for it (its witness's, or the owner's decision where it has none, spec D15), and `lost` the owner's mark that no copy holds that tick any more (spec D15's restore); `FORK_ACKNOWLEDGMENTS: tuple[ForkAcknowledgment, ...] = ()`, which no derive reads (spec D15).
- Produces, in `cli/vintage/verify.py`: `@dataclass(frozen=True) class Finding: kind: str; path: str; detail: str`; `@dataclass(frozen=True) class VerifyResult: breaks: list[Finding]; notes: list[Finding]; ticks: int; head: str | None; head_tick_json_sha256: str | None; bodies_hashed: int`; `verify(root: Path, *, newest: int | None = None, slice_: int | None = None, slices: int | None = None, acknowledgments: tuple[LinkAcknowledgment, ...] = LINK_ACKNOWLEDGMENTS, forks: tuple[ForkAcknowledgment, ...] = FORK_ACKNOWLEDGMENTS, custody: bool = False) -> VerifyResult`. Break kinds: `missing root` (a root that does not exist, never read as an empty record), `broken link`, `missing tick`, `missing body`, `tampered body`, `unreadable manifest`, `fork`, `unlisted file`, `acknowledged link mismatch`. Note kinds: `clock regression`, `link carries the chaining error`, `acknowledged link`, `acknowledged fork` (a fork whose tick off the chain an entry of `forks` names and whose `tick.json` hashes to its `tick_json_sha256`; any other fork stays a `fork` break, and the off-chain tick's bodies are re-hashed as any tick's), `lost tick` (below). `verify` walks `acknowledgments` and `forks` entry by entry once the chain is read, each entry's named tick (a link's `successor`, a fork's `off_chain`) looked up among the ticks the copy holds, and passes over an entry whose tick the copy does not hold, neither break nor note: every entry ships to both copies, the ops copy never holds a fork's tick off the chain, and a copy taken before a successor arrived holds no link's successor (spec D15); save that with `custody=True` a fork entry whose tick off the chain the copy does not hold is a `missing tick` break naming that tick, the NAS copy being its only custody, or, when the entry's `lost` is true, a `lost tick` note naming it; `lost` is read in that one branch alone, so it changes nothing over a copy that holds the tick or without `custody`. With `newest`, the bodies re-hashed are those of the newest `newest` ticks along the chain from its head and of every tick whose index in stamp order (0 for the oldest stamp) satisfies `index % slices == slice_`, the spec's "position in stamp order is K modulo M", a condition written once in `verify.py` in exactly that text; without, every body.
- Produces, in `cli/vintage/command.py`: `vintage_app = typer.Typer(help=…)` and `verify --root PATH [--custody] [--newest N --slice K --slices M]`, `--custody` handing `custody=True`, logging each break at ERROR and each note at INFO, then one summary line, `vintage verify complete ticks=<n> head=<stamp or none> head_tick_json_sha256=<sha256 or none> bodies_hashed=<n> breaks=<n>`, at INFO when clean and at ERROR otherwise, so an arrival read compares `head` by value, never by the exit code alone, exiting 0 clean and 1 otherwise; `cli/__main__.py` gains `from cli.vintage.command import vintage_app` and `app.add_typer(vintage_app, name="vintage")`.

- [ ] **Step 1: The failing tests,** in `tests/test_vintage_verify.py`, each over a record of four ticks from `build_record`, through `CliRunner` and `verify()`:
  - `test_a_clean_record_and_an_empty_one_exit_0`.
  - `test_the_summary_line_counts_what_it_read`: over the four ticks, `ticks=4`, `head` the last tick's stamp, `head_tick_json_sha256` its `tick.json`'s sha256 and `bodies_hashed` the count of bodies the four `tick.json` files list; over an empty record `ticks=0 head=none head_tick_json_sha256=none bodies_hashed=0`.
  - `test_each_break_exits_1_naming_its_path`, parametrised: a root that does not exist (`missing root`), a body's bytes changed (`tampered body`), a body removed (`missing body`), a middle tick removed (`missing tick`), a `tick.json` replaced by other valid bytes (`broken link` on its successor), a `tick.json` made unparseable (`unreadable manifest`), a second tick naming the same predecessor (`fork`, both named), a `.cm-btc.jsonl.gz.Ab12Cd` file in a tick directory (`unlisted file`).
  - `test_a_stamp_regression_is_named_and_exits_0`.
  - `test_a_link_carrying_the_chaining_error_is_named_and_exits_0`.
  - `test_an_acknowledged_link_exits_0_and_its_mismatch_exits_1`: a successor whose `prev` disagrees with a restored predecessor exits 0 when an entry pins the recorded and the witnessed sha256 and the predecessor hashes to the witnessed one, and 1 when its bytes differ; the same entry over a copy taken before its successor arrived (the successor built as the record's newest tick, then its directory removed, so the restored predecessor is the head and no tick names a missing one) exits 0 with no note and no break.
  - `test_an_acknowledged_fork_exits_0_and_its_mismatch_exits_1`: a fork built as the break case's, its tick off the chain named by a `ForkAcknowledgment` pinning the sha256 of that tick's `tick.json`: exit 0, the `acknowledged fork` note naming it; the entry pinning another sha256: exit 1, `fork`; the entry matching and one of that tick's bodies changed: exit 1, `tampered body`; the matching entry over the ops shape, the same record with the off-chain tick's directory removed, so the tick that chained around it stands and no fork remains: exit 0, no note and no break; the same record and entry run with `--custody` through `CliRunner` and with `custody=True` through `verify()`: exit 1, `missing tick` naming the off-chain tick; and both again with the entry's `lost` true: exit 0, the `lost tick` note naming the off-chain tick.
  - `test_newest_takes_the_chain_not_the_stamps`: after a published regression, `--newest 1` re-hashes the regression tick, the head, and not the newest stamp.
  - `test_slice_takes_exactly_its_ticks`, over its own five ticks published at `BASE_TICK_START` plus 0, 3, 6, 12 and then 9 hours, the last a published regression, so stamp order and chain order differ (the 12-hour tick is stamp index 4 and chain position 3, the 9-hour one stamp index 3 and chain position 4), and a body damaged in the 12-hour tick: `--newest 0 --slice 1 --slices 3` exits 1 (stamp indices 1 and 4) and `--newest 0 --slice 0 --slices 3` exits 0 (stamp indices 0 and 3). A reading of one tick per slice (`index == slice_`) takes index 1 alone and exits 0 at `--slice 1`; a reading by chain position takes positions 0 and 3 and exits 1 at `--slice 0`.
- [ ] **Step 2: Run them and read them fail.**
- [ ] **Step 3: `verify.py`, `command.py`'s `verify`, `cli/__main__.py`, `LinkAcknowledgment` and `ForkAcknowledgment`.** Help text free of internal tokens.
- [ ] **Step 4: The task's run, the gate, commit** `feat(vintage): verify a copy of the record and its chain`.
- [ ] **Step 5: Probes,** `--file cli/vintage/verify.py`, each KILLED, the implementer's `sed` reaching the one site:
  - `test_each_break_exits_1_naming_its_path`: the unlisted-file read removed; the fork read removed; the body re-hash removed.
  - `test_newest_takes_the_chain_not_the_stamps`: the newest ticks taken by stamp.
  - `test_slice_takes_exactly_its_ticks`: the slice taken by chain position rather than stamp order; and `s/index % slices == slice_/index == slice_/`.
  - `test_an_acknowledged_link_exits_0_and_its_mismatch_exits_1`: the acknowledged predecessor's hash test against `witnessed_sha256` removed; and the pass-over of an entry whose successor the copy does not hold turned into a `missing tick` break.
  - `test_an_acknowledged_fork_exits_0_and_its_mismatch_exits_1`: the off-chain `tick.json`'s hash test against the entry's `tick_json_sha256` removed; an acknowledged fork's off-chain tick left out of the body re-hash; and the pass-over of an entry whose off-chain tick the copy does not hold turned into a `missing tick` break; and the `custody` test removed, so a custody copy missing a fork's off-chain tick passes it over; and the `lost` test removed, so a lost entry over a custody copy stays a `missing tick` break.
  - `test_a_stamp_regression_is_named_and_exits_0`: a regression counted as a break.
  - `test_a_link_carrying_the_chaining_error_is_named_and_exits_0`: a link whose successor's `prev` carries `error` reported as a `broken link`.
  - `test_a_clean_record_and_an_empty_one_exit_0`: a record with no tick reported as a `missing tick`.
  - `test_the_summary_line_counts_what_it_read`: `VerifyResult.ticks` set to 0.
  - `test_each_break_exits_1_naming_its_path`, a second arm: a root that does not exist read as an empty record.

  `--file cli/vintage/command.py`, each flag `verify` hands to `verify()` dropped from that call, the flag still declared, so `verify()` takes its default (`--root` is every case's own operand):
  - `test_an_acknowledged_fork_exits_0_and_its_mismatch_exits_1`: `custody=` left out, so `--custody` passes the custody copy's missing off-chain tick over.
  - `test_slice_takes_exactly_its_ticks`: `newest=` left out (every body re-hashed, so `--slice 0` exits 1); `slice_=` left out; and `slices=` left out.

### Task 6: The derivation and the as-of reader (D16, the reader's steps 2 to 11, D10's two-body reading)

**Files:** Create `cli/vintage/derive.py`, `cli/vintage/asof.py`, `tests/test_vintage_derive.py`; modify `tests/vintage_stub.py`.

**Interfaces:**
- Consumes: Tasks 2 and 4; Task 5's `LinkAcknowledgment`; `build_record`, Task 1's variants.
- Produces, in `tests/vintage_stub.py` (modified): `standard_record(data_dir: Path) -> list[Published]`, six ticks on `BASE_TICK_START`'s date at offsets 0, 3, 7, 10, 18 and 22 hours, so the gaps are uneven: `cm-btc` base, `cm-btc-restatement`, `cm-btc-retraction`, base, `cm-btc-metric-gone`, `cm-btc-next`; `bg-*` base, `bg-sopr-restatement`, `bg-sopr-newest-back`, base, `bg-sopr-rolled`, `bg-sopr-rolled` (each renamed per value key as `default_bodies` does). Each leg puts every body edited from the base before the body whose newer days the base would fall behind, so every body grades ok against the last ok body before it but `cm-btc-metric-gone` (an absent metric) and `bg-sopr-newest-back` (its newest day gone back), each graded 2 by design; and the `cm-btc` value the third tick retracts, the fourth restores, a later derive run when the table is built tick by tick; `mempool-hashrate` base, `mempool-hashrate-restated-big`, then base; `fng` the real body, then `fng-next`; every other source its `default_bodies()` body.
- Produces, in `cli/vintage/derive.py`:
  - `DERIVE_GENERATION = 1`; `KINDS = ("inherited", "first_publication", "backfill", "restatement", "retraction", "restoration")`; `CLOCK_OFFSET_BAR_SECONDS = 10`; `CLOCK_FILE_STALE_SECONDS = 600`; `DATE_SKEW_SECONDS = 300`.
  - `parse_series(source: Source, body: bytes) -> dict[str, dict[date, str]]`, token-preserving, every `json.loads` in `derive.py` spelt `json.loads(<text>, parse_int=str, parse_float=str)` with the keywords in that order, a series `cm/<asset>/<key>` for every row key but `asset` and `time`, `fng/value`, `fng/value_classification`, `mempool/avgHashrate`, `bg/<metric>`; a `json_stream` body read line by line, a blank line skipped, an absent key no value and a `null` value the same; a key whose value in any row is an object or an array is no series of that body; and `ValueError` raised on a body it cannot read (not UTF-8, not JSON, not its source's shape: an outcome-2 body only, since a body the check passes is readable).
  - `knowable_at(ended_at: datetime, headers: list[tuple[str, str]]) -> datetime`, holding the line `return max(ended_at, server_date + timedelta(seconds=1))` where a `Date` header parses, `ended_at` otherwise.
  - `flags(manifest: dict, fetch: dict) -> tuple[str, ...]`: `clock-unsynchronised`, `clock-offset` (beyond `CLOCK_OFFSET_BAR_SECONDS`, or null), `clock-file-stale` (beyond `CLOCK_FILE_STALE_SECONDS` or no file), `date-skew` (`ended_at` beyond `DATE_SKEW_SECONDS` from `Date`), sorted; `stamp-regression` is added for a tick at or below its predecessor; the later facts are `regression-predecessor`, `link-error`, `link-acknowledged`.
  - `@dataclass class DeriveState` (per series the high-water day, whether carried, and its newest evidence observation's `ended_at`; per (series, day) the last non-null token and whether it stands retracted); `DeriveState.empty()`.
  - `derive_tick(state: DeriveState, tick: TickFile, position: int, *, tick_dir: Path, regression: bool, entries: tuple[LinkAcknowledgment, ...] = ()) -> tuple[list[dict], list[dict], list[dict]]`, the tick's version rows, coverage rows and later facts (the predecessor of a regression; a predecessor whose link carries `prev.error`; a link acknowledged, when an entry of `entries` names this tick as its `successor`), mutating `state`; `entries` are the generation's D15 entries, which Task 10 passes from `GENERATION_ENTRIES`.
  - `VERSIONS_SCHEMA`, `COVERAGE_SCHEMA`, `LATER_FACTS_SCHEMA`: ordered `dict[str, pl.DataType]` with the spec's columns in order. A choice the spec leaves (it gives `ts` alone a dtype): every time column is `pl.Datetime("us", "UTC")`, `ts`, `ended_at`, `knowable_at` and `appeared_after` in `versions`, `ts`, `ended_at` and `knowable_at` in `coverage`, so `as_of` compares `knowable_at` with an aware datetime and the frame hash renders each as `YYYY-MM-DDTHH:MM:SS.ffffffZ`; `first_day` and `last_day` `pl.Date`; `position`, `outcome` and `days` `pl.Int64`; `evidence` `pl.Boolean`; `provider`, `source`, `series`, `kind`, `token`, `tick`, `tick_json_sha256`, `reason` and `flags` `pl.String`. `LATER_FACTS_SCHEMA` is `tick`, `fact` and `taught_by` `pl.String`, `taught_position` `pl.Int64`; `frames(versions: list[dict], coverage: list[dict], facts: list[dict]) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]`, each sorted as the spec says (`versions` by `ts`, `source`, `series`; `coverage` by `source`, `series`).
  - `derive_record(record_root: Path, *, entries: tuple[LinkAcknowledgment, ...] = ()) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]`, every tick on the chain from genesis.
  - `changed_values(prev: dict[str, dict[date, str]], new: dict[str, dict[date, str]]) -> int`, the spec's two-body reading.
- Produces, in `cli/vintage/asof.py`: `as_of(versions: pl.DataFrame, coverage: pl.DataFrame, later_facts: pl.DataFrame, t: datetime) -> pl.DataFrame`, columns `ts`, `provider`, `source`, `series`, `token`, `kind`, `tick`, `position`, `first_seen_at`, `last_seen_at`, `flags`.

The rules are the spec's reader section, steps 2 to 11, as `derive_tick` applies them per (series, day), in chain order: an observation is a 200 with a complete body; an outcome-2 body's absences are evidence for a series unless its check names it in `metrics_absent` or `metrics_failed` or names `*`; each token is judged against the last non-null token seen and the series' high-water day; inherited is set per series at the first observation carrying it; Q3's lower end is the `ended_at` of the last earlier observation that is evidence for the series (it carries the series and its absences are evidence for it, by the rule above: an outcome-2 body naming the series in `metrics_absent` or `metrics_failed`, or naming `*`, is passed over), that day not yet held there; a `bg/<metric>` day earlier than an observation's oldest day is outside its range, so no retraction. A body `parse_series` cannot read is caught in `derive_tick`, never raised: it adds no version, and its fetch is one coverage row with `series` `*`, its outcome and `evidence` false, so one format-drift body never stops a derive, whose table is a pure function of the record and would stop at that tick in every run. `coverage` keeps a fetch that was no observation as a row with `series` `*` (a choice the spec leaves: the part's `coverage.parquet` keeps them, `part.json` does not list them).

- [ ] **Step 1: The failing tests,** in `tests/test_vintage_derive.py`, each over a record built from the named bodies at `BASE_TICK_START + 3 h × i`, every other source its `default_bodies()` body:
  - `test_as_of_never_returns_a_version_before_its_knowable_time`: base, then `cm-btc-restatement` served with a `Date` 5 s after that fetch's `ended_at`: `as_of` at that `ended_at` and at the `Date` holds the base's token for the restated (series, day), and at `Date + 1 s` the restatement's.
  - `test_an_outcome_2_body_that_lost_history_leaves_as_of_unchanged`: base, then `cm-btc-lost-newest`: `as_of` after the second equals `as_of` after the first.
  - `test_a_value_its_retraction_and_the_same_value_again`: base, `cm-btc-retraction`, base: as of any time after the third the value stands with kind `restoration`, and the day's versions read `inherited`, `retraction`, `restoration`.
  - `test_inherited_is_set_per_series_at_its_first_carrying_observation`: `cm-btc-metric-gone`, then base: the gone metric's days are `inherited` at the second tick and none is a `first_publication`.
  - `test_the_kinds_are_told_apart`: base, `cm-btc-next` (`first_publication` for each new day and for each network metric completing a day), `cm-btc-restatement` (one `restatement`).
  - `test_a_gap_filled_after_a_truncated_outcome_2_body_is_a_backfill`: `cm-btc-gap`, `cm-btc-lost-newest` (its newest day for that metric now before the gap), base: the gap's day is a `backfill` at the third tick, never a `first_publication`.
  - `test_a_value_gone_and_restored_changed_is_a_restatement`: base, `cm-btc-metric-gone`, `cm-btc-metric-back-changed`.
  - `test_an_outcome_2_bodys_absences_are_evidence_only_for_the_series_it_does_not_name`: base, then `cm-btc-frozen` combined in memory with one day inside the frozen metric's range removed and a retraction of another, unnamed metric: the frozen metric, carried and named in `metrics_failed`, reads no retraction, and the other one does.
  - `test_a_source_level_outcome_2_bodys_absences_are_no_evidence_for_any_series`: base, then `cm-btc-collapse` (its check naming `("*", "collapse")` alone): no `retraction` row, and `as_of` after the second equals `as_of` after the first.
  - `test_an_unparseable_observation_adds_no_version_and_never_stops_the_derive`, parametrised: a `cm-btc` 200 served `Content-Encoding: gzip`, an HTML 200 on `cm-btc`, an empty 200 on `fng`, a `bg-sopr` 200 that is a JSON object, a `cm-btc` line that is `[]`, an `fng` whose `data` is an object, a `cm-btc` body that is not UTF-8: base, that body, base: `derive_record` completes, the second tick adds no version for that source and holds one coverage row for it with `series` `*`, outcome 2 and `evidence` false, and `as_of` after the second equals `as_of` after the first; and a `cm-btc` body one of whose rows holds an object under `FlowInExNtv-status`: that key is no series of the body, every other series as the base's.
  - `test_the_coverage_rows_by_value`: base, `cm-btc-frozen` (its check naming the frozen metric alone), `cm-btc-collapse` (naming `*`), then a tick whose `fng` answers 503 three times: each tick holds one coverage row per (source, series) its bodies carry, `first_day`, `last_day` and `days` those `parse_series` reads from the stored body; `evidence` false exactly on the series a tick's check names in `metrics_absent` or `metrics_failed`, or on every series of its source when it names `*` (the frozen metric's series at the second tick, every `cm-btc` series at the third), true on every other row; and the fourth tick's `fng` one row, `series` `*`, outcome 1, reason `HTTP 503 after 3 attempts`.
  - `test_q3_brackets_a_day_first_held_at_the_second_tick`: base, `cm-btc-next`: a new day's `appeared_after` is the first tick's `ended_at` and its own `ended_at` the second's; an inherited day's is null.
  - `test_q3s_lower_end_passes_over_an_observation_that_names_the_series`: base, `cm-btc-frozen` (it carries the frozen metric, a pinned network metric, and its check names it in `metrics_failed`), `cm-btc-next`: the frozen metric's newest day, first held at the third tick, has `appeared_after` equal to base's `ended_at`, never `cm-btc-frozen`'s.
  - `test_a_change_of_time_format_keeps_every_key`: base, `cm-btc-time-format`: no version beyond the first tick's.
  - `test_a_token_beyond_2_53_survives`: base `mempool-hashrate`, then `mempool-hashrate-restated-big`: the `restatement`'s token equals the body's text exactly.
  - `test_a_bg_day_leaving_the_window_is_no_retraction`: base, `bg-sopr-rolled`.
  - `test_last_seen_reads_only_rows_known_to_have_held_the_day`: a coverage row with `evidence` false and a hole inside its range is skipped; one with `evidence` true, or with `days == last_day - first_day + 1`, counts.
  - `test_every_versions_token_is_its_ticks_body_token`: over `standard_record`, each version's `token` equals `parse_series` of the body stored in its `tick` for its (series, day), and is null exactly on a `retraction`.
  - `test_changed_values_counts_restatement_retraction_and_backfill_never_a_first_publication`: base against `cm-btc-restatement` 1, `cm-btc-retraction` 1, `cm-btc-gap` against base 1, base against `cm-btc-next` 0; a day retracted in one ok body and back unchanged in the next counts 1; a value withheld in an outcome-2 body and restored changed counts 1 between the two ok bodies.
  - `test_the_status_companions_are_series_of_their_own` (Review Focus): `parse_series` of a `cm-btc` body carrying `FlowInExNtv-status` holds `cm/btc/FlowInExNtv-status`.
  - `test_a_json_stream_body_parses_with_or_without_a_trailing_newline` (Review Focus): the base, it with `\n` appended, and it with a blank line inserted parse equal.
  - `test_the_flags`: a tick with `synchronised 0`, one with offset 11, one with `prom_age_seconds` 601, one whose `ended_at` is 301 s past `Date` each carry their flag, one whose offset is null carries `clock-offset`, one at 10, 600 and 300 none; a regression tick carries `stamp-regression` and its predecessor a `regression-predecessor` fact taught by it.

  The spec's "`as_of` over the table's frames through a head equals `as_of` over the in-memory derivation" is Task 10's `test_as_of_through_a_head_equals_the_derivation_in_memory`, which reads the frames through `read_table`, so this task holds no parquet round trip of its own.
- [ ] **Step 2: Run them and read them fail.**
- [ ] **Step 3: `derive.py` and `asof.py`.**
- [ ] **Step 4: The task's run, the gate, commit** `feat(vintage): the derivation of versions and the as-of reader`.
- [ ] **Step 5: Probes,** each KILLED. `--file cli/vintage/derive.py`:
  - `test_as_of_never_returns_a_version_before_its_knowable_time`: `s/server_date + timedelta(seconds=1))/server_date)/`.
  - `test_the_flags`: `s/^CLOCK_OFFSET_BAR_SECONDS = 10$/CLOCK_OFFSET_BAR_SECONDS = 11/`; `s/^CLOCK_FILE_STALE_SECONDS = 600$/CLOCK_FILE_STALE_SECONDS = 601/`; `s/^DATE_SKEW_SECONDS = 300$/DATE_SKEW_SECONDS = 301/`.
  - `test_a_gap_filled_after_a_truncated_outcome_2_body_is_a_backfill`: the high-water day read from the observation just before rather than every earlier one.
  - `test_a_value_gone_and_restored_changed_is_a_restatement`: a token judged against the previous observation's rather than the last non-null one.
  - `test_inherited_is_set_per_series_at_its_first_carrying_observation`: inherited set per source.
  - `test_an_outcome_2_bodys_absences_are_evidence_only_for_the_series_it_does_not_name`: every outcome-2 absence read as evidence.
  - `test_a_bg_day_leaving_the_window_is_no_retraction`: the range's lower end ignored.
  - `test_a_change_of_time_format_keeps_every_key`: the key taken from the token text.
  - `test_changed_values_counts_restatement_retraction_and_backfill_never_a_first_publication`: a day after the previous newest counted.
  - `test_the_status_companions_are_series_of_their_own`: series limited to the pinned metrics.
  - `test_a_value_its_retraction_and_the_same_value_again`: the last token seen again after a retraction making no new version.
  - `test_the_kinds_are_told_apart`: a first publication judged against the source's high-water day rather than the series'.
  - `test_q3_brackets_a_day_first_held_at_the_second_tick`: `appeared_after` taken from the version's own `ended_at`.
  - `test_q3s_lower_end_passes_over_an_observation_that_names_the_series`: the evidence test removed from the search for Q3's lower end, so the last observation carrying the series stands.
  - `test_a_token_beyond_2_53_survives`: `s/parse_int=str, parse_float=str/parse_int=float, parse_float=str/`.
  - `test_an_outcome_2_body_that_lost_history_leaves_as_of_unchanged`: `metrics_failed` left out of the evidence rule, `metrics_absent` alone read.
  - `test_every_versions_token_is_its_ticks_body_token`: a version's `tick` written as the series' previous observation's.
  - `test_a_json_stream_body_parses_with_or_without_a_trailing_newline`: the blank-line skip removed.
  - `test_a_source_level_outcome_2_bodys_absences_are_no_evidence_for_any_series`: the `*` term dropped from the evidence rule.
  - `test_an_unparseable_observation_adds_no_version_and_never_stops_the_derive`: `derive_tick`'s catch of `parse_series`' `ValueError` removed.
  - `test_the_coverage_rows_by_value`: `evidence` set from the body's outcome alone; and the outcome-1 `*` row left out.
  - `test_the_flags`, a second arm: a null offset left unflagged.

  `--file cli/vintage/asof.py`, `test_last_seen_reads_only_rows_known_to_have_held_the_day`: the unbroken-days alternative removed.

### Task 7: The rule, the dashboard row and the runbook section (D11, Observability)

**Files:** Modify `infra/grafana/alerts.yaml`, `infra/grafana/data-integrity-dashboard.json`, `infra/runbooks/ops-node.md`, `tests/test_infra_alert_rules.py`.

**Interfaces:** Produces the uid `zcrypto-ops-vintage-not-recorded`, the anchor `infra/runbooks/ops-node.md#zcrypto-ops-vintage-not-recorded`, and panels 700 to 706 that Tasks 8, 10 and 14 rely on.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read its *Before you write guidance*. Read `RATIO`.
- [ ] **Step 2: The failing test,** in `tests/test_infra_alert_rules.py` beside `test_the_backup_rule_pages_a_gauge_older_than_26_hours_or_none_at_all`:

```python
def test_a_vintage_source_not_recorded_in_25_hours_pages_critical():
    rule = _rule("zcrypto-ops-vintage-not-recorded")
    assert _prom_exprs(rule) == ["time() - zcrypto_vintage_last_ok_timestamp_seconds"]
    assert _evaluator(rule) == {"type": "gt", "params": [90000]}
    assert rule["for"] == "5m"
    assert (rule["noDataState"], rule["execErrState"]) == ("Alerting", "Alerting")
    assert rule["labels"]["severity"] == "critical"
    assert (rule["notification_settings"]["receiver"], rule["ruleGroup"]) == ("metrics", "zcrypto-ops")
    assert "repeat_interval" not in rule["notification_settings"]
    summary = rule["annotations"]["summary"]
    assert "{{" not in summary, "a summary naming its source drops out of a message carrying several"
    assert summary.endswith("Runbook: infra/runbooks/ops-node.md#zcrypto-ops-vintage-not-recorded")
    assert rule["annotations"]["__panelId__"] == "701"
```

- [ ] **Step 3: Run it and read it fail** on the missing uid.
- [ ] **Step 4: The rule,** after `zcrypto-ops-verified-replay-stale`, in that rule's shape: title `Ops · vintage source not recorded`, refId A `time() - zcrypto_vintage_last_ok_timestamp_seconds`, `instant: true`, `relativeTimeRange: {from: 600, to: 0}`, threshold C `{type: gt, params: [90000]}`, `noDataState: Alerting`, `execErrState: Alerting`, `for: 5m`, the summary of the spec's D11 in substance, interpolating nothing and ending `Runbook: infra/runbooks/ops-node.md#zcrypto-ops-vintage-not-recorded`, `__dashboardUid__: "zcrypto-integrity"`, `__panelId__: "701"`, `unit: "seconds since the source's last good fetch, capped at 19:57 UTC of its day"`, `severity: critical`, receiver `metrics`. Its comments say why `noDataState` is `Alerting` and why the severity is critical.
- [ ] **Step 5: The row,** on `infra/grafana/data-integrity-dashboard.json` after the *Telemetry integrity* row: a row panel 700 `Free-source vintages` at `y` 129, then timeseries 701 `Last good fetch age by source` (`time() - zcrypto_vintage_last_ok_timestamp_seconds`, legend `{{source}}`, unit seconds, a red threshold step at 90000, the rule's bar), 702 `Outcome by source` (`zcrypto_vintage_outcome`), 703 `Body bytes by source` (`zcrypto_vintage_body_bytes`, bytes), 704 `Days missing by source` (`zcrypto_vintage_days_missing`), 705 `Values changed since the previous good body` (`zcrypto_vintage_changed_values`), 706 `Versions table head age` (`time() - zcrypto_vintage_derive_head_timestamp_seconds`, seconds, no bar), each description saying what it reads and naming no internal term.
- [ ] **Step 6: The runbook section,** in `infra/runbooks/ops-node.md` after `zcrypto-ops-verified-replay`'s section, opening `<a name="zcrypto-ops-vintage-not-recorded"></a>` above `## zcrypto-ops-vintage-not-recorded — ALERT`, with *What you are seeing*, *What it means*, *What to do* and *Retire when* as the spec's Observability bullets give them, the expression, bar, `for: 5m` and `noDataState: Alerting` stated as the page's line 20 states archive-pull's; then a part *Restoring a damaged file from the other copy*, and a part *The versions table*, each as the spec's bullets give it, the `zcrypto vintage derive --record <a copy> --table <an empty scratch root> [--through <stamp>]` rebuild among them. Every universal word carries its `(set: …; count: …)` or `(no count command: …)`. The alert section's own triage reads, the spec's "Its reads use shapes the ops-daily autonomy classifier admits", are spelt in shapes measured AUTONOMOUS (Global Constraints: `systemctl status …`, `journalctl -u … -n 100`, `ls …`, `cat …`, `find …`, `docker ps -a --filter …`, `sudo systemctl start …`). The restore and versions-table parts need commands no autonomous shape covers (`sudo chmod 0755 <dir>`, `sudo -u zcrypto-data cp -f …`, `sudo chmod 0444 <file>`, `sudo chmod 0555 <dir>`), the copy spelt `cp -f` because a damaged file still present is 0444 and a plain `cp` onto it fails `Permission denied` even in a 0755 directory, and the file set back to 0444 before its directory goes back to 0555, since `cp -f` leaves the source's mode; they spend `RATIO`'s budget, each spelt once with the same placeholder wherever it repeats, so it counts once, and the `zcrypto vintage verify` and `zcrypto vintage derive` lines stay bare, as the spec spells them, and uncounted. The alert section's named-source hand start, spelt once as the spec spells it, spends the budget too (Global Constraints). Its bullet also has the operator keep the `vintage tick published …` line that hand start prints in that day's operations journal entry, and the restore part reads a hand-started tick's witness from there (spec D5's witness, D15's restore): a run from the operator's shell reaches neither the journal nor Loki, whose keep rule keys on the unit. That is prose and no command, so it spends nothing. So is the restore part's clearing of a `missing tick` the NAS copy's `--custody` read names (spec D15: the tick put back on the NAS host from a copy that holds it, or the entry marked lost), written over the part's own NAS-host placement and a bare `sha256sum`, and its closing whole `verify` of the NAS copy carries `--custody`, bare and uncounted.
- [ ] **Step 7: `WALKERS`, `tests/test_dashboards_cover_metrics.py`, `RATIO` again (at least `0.70` of the reads autonomous), the task's run, the gate, commit** `feat(grafana): a vintage source not recorded in 25 hours pages critical`.
- [ ] **Step 8: Probes,** each KILLED, the spec's three. `--file infra/grafana/alerts.yaml`, `test_a_vintage_source_not_recorded_in_25_hours_pages_critical`:
  - `/uid: zcrypto-ops-vintage-not-recorded/,/receiver: metrics/s/severity: critical/severity: warning/`;
  - `/uid: zcrypto-ops-vintage-not-recorded/,/receiver: metrics/s/Runbook: infra/{{ $labels.source }} Runbook: infra/`;
  - `/uid: zcrypto-ops-vintage-not-recorded/,/receiver: metrics/s/params: \[90000\]/params: [46800]/`.

### Task 8: The gauges and the record command (D1's CLI, D9, D10, D15's ops re-verify)

**Files:** Create `cli/vintage/gauges.py`; modify `cli/vintage/command.py`, `tests/test_vintage_record.py`.

**Interfaces:**
- Consumes: Task 2's `SOURCE_BY_ID`; Task 4's `record_tick`, `scan`, `chain`; Task 5's `verify`; Task 6's `parse_series`, `changed_values`; Task 3's `read_key`; `cli.capture.command.single_instance_lock`, `cli.capture.errors.CaptureError`.
- Produces, in `cli/vintage/gauges.py`: `LAST_OK_CAP = time(19, 57)`; `last_ok_value(ended_at: datetime) -> float`, the line `return min(ended_at, datetime.combine(ended_at.date(), LAST_OK_CAP, UTC)).timestamp()`; `render_prom(record_root: Path, chain: Chain, published: Published, *, today: date) -> str`, the five families labelled `source`, a `# HELP` and `# TYPE … gauge` each: `zcrypto_vintage_last_ok_timestamp_seconds` (along `chain.order`, never by stamp; 0 with none), `zcrypto_vintage_outcome`, `zcrypto_vintage_body_bytes` (the raw size stored this tick, 0 without), `zcrypto_vintage_days_missing` (UTC days from the source's first tick on the chain through `today - 1` with no ok fetch, by `ended_at`), `zcrypto_vintage_changed_values` (for `fng`, `cm-<asset>`, `mempool-hashrate` and `bg-*`, this tick's ok body against the source's previous ok body along the chain; no line when this tick's is not ok or either fails to parse, with one WARNING).
- Produces, in `cli/vintage/command.py`: `OPS_VERIFY_NEWEST = 4` and `OPS_VERIFY_SLICES = 14`, the re-verify's selection, each defined once, so the slice index and the slice count read one value; `run_record(data_dir: Path, textfile: Path, clock_prom: Path, *, key_stream: BinaryIO | None, https_handler: urllib.request.BaseHandler | None = None, clock: Clock | None = None, version: str | None = None, revision: str | None = None, sources: tuple[str, ...] = ()) -> int`, the exit code; the typer command `record --data-dir PATH --textfile PATH --clock-prom PATH [--bgeometrics-key-stdin] [--source ID]...` calls it with `key_stream=sys.stdin.buffer` under the flag, `None` without, and `sources` the `--source` values in their order, and exits with its code.

`run_record` calls no `configure`: the root callback configures, as for every subcommand, and a second call would reset the handlers and level it set and turn the `zcrypto` logger's propagation off under a test's `caplog`. The command, in order: an id in `sources` not in `SOURCE_BY_ID` logs ERROR `unknown source <id>; the fetch table's ids are <ids in tick order>` and exits 2, before the key is read, the lock taken or any request made; read the key from stdin only under the flag; `with single_instance_lock(data_dir):`, catching `CaptureError` to log ERROR `another vintage recorder holds <data_dir>; refusing. Read the zcrypto-vintage-record.service journal and docker ps -a --filter name=zcrypto-vintage-record` and exit 2; `record_tick`, with `only=frozenset(sources) or None`; then `publish_prom(textfile, render_prom(...))`; then `verify(record_root, newest=OPS_VERIFY_NEWEST, slice_=len(chain.order) % OPS_VERIFY_SLICES, slices=OPS_VERIFY_SLICES)`, `chain` the one `render_prom` read, taken after the publish, so its count includes this tick, each break an ERROR; WARNING per source not ok, naming its outcome and reason; the INFO summary `vintage record complete tick=<stamp> tick_json_sha256=<sha256> ok=<n> not_fetched=<n> failed_checks=<n> bytes=<n>`; exit 0 when every source is ok, the `.prom` written and the re-verify clean, 1 when published and any of the three is not. Every exception is caught at the top: before the rename returned, ERROR and exit 2; after it, ERROR and exit 1; its ERROR carries the class and the innermost frame's file, line and function, never the exception's text, so no request header or key reaches a line. A refusal writes no `.prom`. An unreadable `tick.json` met in the scan logs ERROR naming it and counts as no ok fetch.

- [ ] **Step 1: The failing tests,** in `tests/test_vintage_record.py`, through `run_record` with a `FakeHTTPS` serving `default_bodies()` and a `FakeClock`, and one case through `CliRunner`; a case reading log lines calls `run_record` directly and reads them through `caplog` after `caplog.set_level(logging.DEBUG)`, never after a `CliRunner` invoke in the same case:
  - `test_the_flag_reads_the_key_from_stdin`: `vintage record … --bgeometrics-key-stdin` through `CliRunner(input=SENTINEL_KEY + "\n")`, `run_record` patched to capture its `key_stream`, hands the stream whose bytes are the input; without the flag, `None`.
  - `test_the_source_option_repeats`: `vintage record … --source cm-eth --source fng` through `CliRunner`, `run_record` patched to capture its `sources`, hands `("cm-eth", "fng")`; without the option, `()`.
  - `test_a_named_source_is_recorded_while_another_assets_query_answers_503`: `sources=("cm-eth",)`, `cm-btc`'s URL scripted to answer 503 on every attempt: exit 1, the published `tick.json` holds a fetch for each of the 18 sources, `cm-eth` outcome 0 with its body stored, every other source `not selected` with no attempt, and `FakeHTTPS.seen` holds `cm-eth`'s URL alone.
  - `test_an_unknown_source_refuses_before_any_fetch`: `sources=("cm-eth", "cm-nope")`: exit 2, one ERROR naming `cm-nope`, `FakeHTTPS.seen` empty, no tick under `record/` and no `.prom`.
  - `test_the_exit_codes`, parametrised: every source ok exits 0; one source a 503 exits 1; the textfile's directory read-only exits 1 with the tick published; a body damaged in an earlier tick exits 1 with an ERROR naming its path; `fetch_all` raising exits 2 with nothing published; `render_prom` raising exits 1.
  - `test_the_re_verify_reads_the_newest_four_and_the_slice_the_tick_count_names`: over 15 ticks from `build_record` at `BASE_TICK_START` plus 0 to 14 hours, one an hour, all on its date, then `run_record` publishing the sixteenth at plus 15 hours, so the count of published ticks is 16 and the slice 16 % 14 = 2; parametrised on the stamp index of the tick one of whose bodies is replaced by other valid gzip bytes before the run (its directory made writable and set back): 2, the slice's tick outside the newest four, and 12, the fourth newest outside the slice, each exit 1 with an ERROR naming that body's path; 1 and 11, in neither, each exit 0.
  - `test_a_held_lock_exits_2_with_the_recorders_own_message`: with the lock held by an `fcntl.flock` in the test, exit 2, the ERROR names `zcrypto-vintage-record.service` and holds neither `zcrypto-capture` nor `systemctl stop`.
  - `test_a_failed_source_logs_a_warning_and_a_refusal_an_error`.
  - `test_the_witness_precedes_the_gauges_and_the_summary_repeats_it`: the witness INFO is logged before the `.prom` exists; the summary's `tick_json_sha256` equals it.
  - `test_the_prom_is_0644_and_holds_the_five_families`: over a first tick with `key_stream=None` and `cm-btc` answering 503 three times, the file is 0644 and holds each family's `# HELP` and `# TYPE`, and by value: `zcrypto_vintage_outcome` 1 for `cm-btc` and the four `bg-*` and 0 for `fng`; `zcrypto_vintage_body_bytes` for `fng` equal to `len` of the raw body served, for `cm-btc` to `len` of the stored 503 body, and 0 for each `bg-*`; and a `zcrypto_vintage_last_ok_timestamp_seconds{source="bg-sopr"}` line present whose value parses to 0.
  - `test_last_ok_reads_along_the_chain`: a tick published under a clock a day ahead, then a regression tick: `fng`'s `last_ok` is the chain head's fetch, not the future stamp's.
  - `test_last_ok_is_capped_at_1957_utc`: a fetch ending 23:30 reads that day's 19:57; one ending 19:38 reads itself.
  - `test_days_missing_is_read_off_the_record`, parametrised on the middle day's `mempool-hashrate`, a 503 or a body graded 2 (its `hashrates` emptied): ok at a tick on `BASE_TICK_START`'s date, that answer at one on the next date, and ok at one on the date after gives days missing 1 there.
  - `test_changed_values_is_the_two_body_reading`: base then `cm-btc-restatement` gives `cm-btc` 1; a `cm-btc` 503 this tick gives no `cm-btc` line.
  - `test_a_body_that_does_not_parse_leaves_no_changed_values_line`: `cli.vintage.gauges.parse_series` patched to raise `ValueError` for `cm-btc`'s previous ok body: no `zcrypto_vintage_changed_values` line for `cm-btc`, every other source's line present, one WARNING naming `cm-btc`, exit 0.
  - `test_a_refusal_writes_no_prom`.
  - `test_an_unreadable_tick_json_logs_an_error_and_counts_no_ok_fetch`: an earlier tick's `tick.json` made unparseable gives one ERROR naming its path, and the sources ok only in that tick read their earlier `last_ok`.
- [ ] **Step 2: Run them and read them fail.**
- [ ] **Step 3: `gauges.py` and the `record` command** with the pinned lines. `# HELP` text free of internal tokens.
- [ ] **Step 4: The task's run with `tests/test_dashboards_cover_metrics.py`, the gate, commit** `feat(vintage): the record command, its exit codes and the gauges read off the record`.
- [ ] **Step 5: Probes,** each KILLED. `--file cli/vintage/gauges.py`:
  - `test_last_ok_is_capped_at_1957_utc`: `s/^LAST_OK_CAP = time(19, 57)$/LAST_OK_CAP = time(23, 59)/`.
  - `test_last_ok_reads_along_the_chain`: `last_ok` taken as the largest stamp's.
  - `test_days_missing_is_read_off_the_record`: an outcome-2 day counted as recorded.
  - `test_changed_values_is_the_two_body_reading`: the not-ok line written as 0.
  - `test_a_body_that_does_not_parse_leaves_no_changed_values_line`: `render_prom`'s catch of a parse failure removed.
  - `test_the_prom_is_0644_and_holds_the_five_families`: `zcrypto_vintage_outcome` written as 0 for a source not fetched; `zcrypto_vintage_body_bytes` written from the stored gzip file's size; and the `last_ok` line left out for a source with no ok fetch.

  `--file cli/vintage/storage.py`, `test_the_prom_is_0644_and_holds_the_five_families`: `s/os\.chmod(tmp, 0o644)/pass/`.

  `--file cli/vintage/command.py`:
  - `test_the_exit_codes`: the top-level `except` narrowed to `OSError`; and the re-verify's findings left out of the exit code.
  - `test_the_re_verify_reads_the_newest_four_and_the_slice_the_tick_count_names`: `s/^OPS_VERIFY_NEWEST = 4$/OPS_VERIFY_NEWEST = 1/` (index 12 then exits 0); `s/^OPS_VERIFY_SLICES = 14$/OPS_VERIFY_SLICES = 24/` (the slice 16 of 24, index 2 then exits 0); and `s/slice_=len(chain\.order) % OPS_VERIFY_SLICES/slice_=0/` (indices 0 and 14, index 2 then exits 0).
  - `test_a_held_lock_exits_2_with_the_recorders_own_message`: the `CaptureError` re-raised.
  - `test_a_failed_source_logs_a_warning_and_a_refusal_an_error`: the per-source WARNING logged at INFO.
  - `test_the_witness_precedes_the_gauges_and_the_summary_repeats_it`: the summary line's `tick_json_sha256` field left out.
  - `test_a_refusal_writes_no_prom`: a `.prom` written on the refusal path.
  - `test_an_unreadable_tick_json_logs_an_error_and_counts_no_ok_fetch`: the unreadable `tick.json`'s ERROR removed (in the module that logs it, `gauges.py` when it is there).
  - `test_the_flag_reads_the_key_from_stdin`: `key_stream` passed as `None` under the flag.
  - `test_the_source_option_repeats`: the option's values handed to `run_record` as `()`.
  - `test_a_named_source_is_recorded_while_another_assets_query_answers_503`: `only` handed to `record_tick` as `None`.
  - `test_an_unknown_source_refuses_before_any_fetch`: the unknown-id check removed.

### Task 9: The credential guard (D20)

**Files:** Create `tests/test_vintage_credential.py`.

**Interfaces:** Consumes Task 8's `run_record`, `default_bodies`, `FakeHTTPS`, `FakeClock`, `SENTINEL_KEY`, `SENTINEL_FORMS`; never `decode_for_scan` or `key_forms`, the decode and the forms under test.

- [ ] **Step 1: The tests,** each its own case, `run_record(…, key_stream=io.BytesIO(SENTINEL_KEY.encode() + b"\n"), https_handler=FakeHTTPS(…))` called directly, never through `CliRunner` (whose root callback's `configure` turns the `zcrypto` logger's propagation off), the stub below urllib's handler chain under the real opener, log lines captured by `caplog` at every level after `caplog.set_level(logging.DEBUG)`, and after each: the captured lines hold the case's positive control (the witness INFO, or the per-source WARNING where no tick ends ok, or the top-level ERROR), so the absence below is read over lines that were captured; every echo a stub serves is built from `SENTINEL_FORMS`; no file under the record root, `staging/` or the textfile holds any of `SENTINEL_FORMS`, every file read decompressed, each stored body searched as stored and, where its `tick.json` records a `Content-Encoding`, also decoded by the stdlib (`gzip.decompress` and `compression.zstd.decompress`, which read every member and frame; for `deflate`, one `zlib.decompressobj(…).decompress(body)` call, raw deflate's `wbits=-15` where the zlib header is absent, failing the case unless its `eof` is true and its `unused_data` empty, since `zlib.decompress` returns the first stream and drops what follows without raising), a stored body that does not decode failing the case, every `head` decoded from base64; no captured log line holds it; each keyed attempt's `error` is null or a bare class name; `FakeHTTPS` saw it in `unredirected` alone and only on requests to `api.bitcoin-data.com`; `request_headers` reads `Bearer <redacted>`:
  - `test_an_ok_tick_holds_no_key`;
  - `test_a_retried_answer_echoing_the_key_keeps_no_head` (a 503 echoing it in its first 4 KiB, then a 200);
  - `test_an_echoing_401_body_is_not_stored` (`second/bg-sopr-401-echo`);
  - `test_an_echoing_header_is_redacted` (a 401 with `WWW-Authenticate` holding it);
  - `test_an_echoing_reason_phrase_or_header_name_is_redacted`, parametrised: a 401 whose reason phrase is `f"bad {SENTINEL_KEY}"`, a 200 carrying a header named with the key;
  - `test_echoes_in_every_form_are_not_stored`, parametrised: JSON-escaped, percent-encoded upper and lower, gzip-encoded, and gzip-encoded as two members whose second echoes it;
  - `test_an_unscannable_body_is_not_stored` (`Content-Encoding: br`);
  - `test_a_redirect_is_not_followed_and_holds_no_key` (a 302);
  - `test_a_transport_error_holds_no_key`;
  - `test_an_exception_quoting_the_key_is_recorded_by_its_class` (`FakeHTTPS` raising `ValueError("Invalid header value %r" % …)` built as `http.client`'s, on `bg-sopr`);
  - `test_an_exception_reaching_the_top_holds_no_key`: `cli.vintage.record.fetch_all` patched to raise that `ValueError`: exit 2, one ERROR naming `ValueError` and its innermost frame, and no line holding the key;
  - `test_a_missing_or_malformed_key_dials_nothing_on_the_keyed_host`, parametrised: an empty stream, a stream raising `OSError`, `two words` — no request to `api.bitcoin-data.com`, every other source fetched, the four reading `no credential` or `malformed credential`.
- [ ] **Step 2: The task's run, the gate, commit** `test(vintage): no byte the recorder keeps or logs holds the key`.
- [ ] **Step 3: Probes,** each KILLED, the spec's twelve mutations and the reason phrase's scan. `--file cli/vintage/fetch.py`:
  - `test_an_ok_tick_holds_no_key`: the real value written into `request_headers` (`REDACTED_AUTHORIZATION` replaced at its use by `("Authorization", f"Bearer {key.reveal()}")`); a `?token=` URL (the keyed request's URL built as `f"{source.url}?token={key.reveal()}"`); `s/add_unredirected_header("Authorization"/add_header("Authorization"/`; and the key added to every source's request, the `source.keyed` test before `add_unredirected_header` dropped.
  - `test_an_echoing_401_body_is_not_stored`: the body scan removed.
  - `test_an_echoing_header_is_redacted`: the header redaction removed.
  - `test_an_echoing_reason_phrase_or_header_name_is_redacted`: the reason phrase's scan removed.
  - `test_a_retried_answer_echoing_the_key_keeps_no_head`: the scan of a retried attempt's body removed.
  - `test_echoes_in_every_form_are_not_stored`: the decode before the scan removed.
  - `test_an_exception_quoting_the_key_is_recorded_by_its_class`: the keyed attempt's `error` written as `f"{type(exc).__name__}: {exc}"`.

  `--file cli/vintage/credential.py`, `test_echoes_in_every_form_are_not_stored`: the `eof` and `unused_data` test after a layer's call removed (the two-member body is then scanned in its first member alone, stored, and read whole by `gzip.decompress`); and the percent form built with `/` left unencoded, `s/safe=""/safe="\/"/` (the upper-case percent echo is then scanned for `%2B/x`, stored, and found by its `SENTINEL_FORMS` entry).

  `--file cli/vintage/command.py`, `test_an_exception_reaching_the_top_holds_no_key`: an exception's text logged, the top-level ERROR given `str(exc)`.

### Task 10: The versions table and the derive command (D16's table, D18's third helper)

**Files:** Create `cli/vintage/table.py`, `tests/test_vintage_table.py`; modify `cli/vintage/derive.py`, `cli/vintage/storage.py`, `cli/vintage/command.py`.

**Interfaces:**
- Consumes: Task 6's `derive_tick`, `DeriveState`, schemas and `frames`; Task 5's `LinkAcknowledgment`; Task 4's `scan`, `chain`, `check_head`; `cli.config.load_config` (`nfs_mount_dir`).
- Produces, in `cli/vintage/storage.py`: `refuse_table_root(table_root: Path, record_root: Path, nas_mount: Path) -> str | None` (resolved paths; the table root equal to or under the record root, its parent or the NAS mount is refused); `publish_table_dir(staged: Path, target: Path, *, table_root: Path, record_root: Path, nas_mount: Path) -> None`, the table-publish helper: the refusal, `if target.exists():`, `os.rename`, the parent fsynced, `os.chmod(target, 0o555)`.
- Produces, in `cli/vintage/derive.py`: `GENERATION_ENTRIES: dict[int, tuple[LinkAcknowledgment, ...]] = {1: ()}`, which `derive_table` hands to every `derive_tick` call as `entries=GENERATION_ENTRIES[generation]`; `HEAD_PINS: dict[int, str]`, the fixture record's head sha256 per generation, its shipped entries never edited; `DeriveState.from_frames(versions: pl.DataFrame, coverage: pl.DataFrame) -> DeriveState`, the state a run resumes from, read from the frames `read_table` returns through the current head (from `versions` each (series, day)'s last non-null token and whether it stands retracted; from `coverage` each series' high-water day, whether it has been carried, and its newest observation whose absences are evidence), never from a state file.
- Produces, in `cli/vintage/table.py`: `FRAME_HASH_VERSION = 1`; `frame_hash(df: pl.DataFrame, version: int) -> str`; `write_part(staging: Path, name: str, versions: pl.DataFrame, coverage: pl.DataFrame, part: dict) -> Path`, the part writer, the one site of `DataFrame.write_parquet`, writing each frame to an `io.BytesIO` and then through `create_exclusive`; `@dataclass class TableRead: head: dict; versions: pl.DataFrame; coverage: pl.DataFrame; later_facts: pl.DataFrame`; `read_table(table_root: Path, generation: int, head: str | Path) -> TableRead` (a path within the generation, a stamp, or a sha256 alone); `head(table_root: Path, generation: int) -> dict | None` (the highest `position` in `heads/`); `@dataclass class DeriveOutcome: complete: bool; head: dict | None; parts_added: int; at: str | None; reason: str | None`; `derive_table(record_root: Path, table_root: Path, *, through: str | None = None, nas_mount: Path, generation: int = DERIVE_GENERATION, opened_by: str, clock: Clock | None = None) -> DeriveOutcome`.
- Produces, in `cli/vintage/command.py`: `run_derive(record: Path, table: Path, *, textfile: Path | None, through: str | None, clock: Clock | None = None, version: str | None = None, revision: str | None = None) -> int`, `version` and `revision` defaulting as `record_tick`'s do and handed to `derive_table` as `opened_by=f"{version}+{revision[:12]}"` (`version` alone without a revision), which the typer command `derive --record PATH --table PATH [--textfile PATH] [--through STAMP]` calls, calling no `configure` (the root callback's, as for `run_record`), its NAS mount `load_config().nfs_mount_dir`, `load_config` imported by name into `cli/vintage/command.py` and that one mount handed to both `refuse_table_root` and `derive_table`, running `refuse_table_root` on the resolved paths before it takes the lock, so a refused table root is never created, then holding `single_instance_lock(table_root)` (on `CaptureError`: ERROR naming `zcrypto-vintage-derive.service`, the stop line with `at=none reason=lock held`, exit 1), ending with one line, INFO `vintage derive complete generation=<n> head=<stamp> head_sha256=<sha256> parts_added=<n>` and exit 0, or ERROR `vintage derive stopped generation=<n> head=<stamp or none> at=<stamp or none> reason=<text>` and exit 1, every exception caught; with `--textfile`, on every run that read its table, `publish_prom` of one family `zcrypto_vintage_derive_head_timestamp_seconds`, the Unix time of the head's tick stamp, 0 while the table is empty.

The table's files, each canonical (`json.dumps(…, sort_keys=True, separators=(",", ":")) + "\n"`), created exclusive and 0444, each staged directory renamed whole and set 0555: `gen-<N>/generation.json` `{"entries": [[successor, recorded, witnessed], …], "generation": N, "hash_version": 1, "opened_by": "<version>+<revision>"}`; `gen-<N>/parts/<Y>/<M>/<D>/<stamp>/` with `versions.parquet`, `coverage.parquet` and `part.json` `{"frames": {"coverage": {"hash", "rows"}, "versions": {"hash", "rows"}}, "generation", "later_facts": [{"fact", "tick"}…], "position", "tick", "tick_json_sha256"}`; `gen-<N>/heads/<Y>/<M>/<D>/<stamp>/head.json` `{"entries_sha256", "generation", "hash_version", "part", "part_json_sha256", "parts_sha256", "position", "prev", "prev_tick", "rows": {"coverage": n, "versions": {<kind>: n …}}, "tick", "tick_json_sha256"}`, `rows` counted through the head. `entries_sha256` is the sha256 of the canonical bytes of the generation's entries list; `parts_sha256` is `sha256((prev_parts_sha256 + part_json_sha256).encode("ascii")).hexdigest()` with 64 zeros before genesis; `prev` the sha256 of the previous head's bytes. The frame hash, version 1: the sha256 of lines, the first `json.dumps(columns)`, then per row from `df.iter_rows()` `"[" + ",".join(render(value)) + "]"`, each line ending `\n`; `render` gives a datetime `"YYYY-MM-DDTHH:MM:SS.ffffffZ"`, a date `"YYYY-MM-DD"`, an int in decimal, a bool `true` or `false`, None `null`, a string `json.dumps(value)`. Staging names: `staging/gen-<N>.<run start second>.<8 hex>/`, `staging/<stamp>.<run start second>.<8 hex>.part/` and `.head/`, the run start second from the run's `clock`, the hex from `secrets.token_hex(4)`, spelt once in `table.py` in exactly that text, each staged directory made by an exclusive `mkdir`. A run: the refusals before any tick (`refuse_table_root`, before the lock in `run_derive` and again in `derive_table`; the lock; a `generation.json` whose entries differ from `GENERATION_ENTRIES`); 0755 published directories set 0555; staging leftovers named in one WARNING; the generation opened when absent; the state read through the current head by `read_table`, checking as it reads; every tick the heads name still on the chain at its position with its `tick.json` sha256 (a `fork` or a `moved tick` stops with ERROR naming the tick); each tick after the head, oldest first, its `prev` the sha256 recorded for its predecessor, or carrying `prev.error`, or named by the generation's entries, its bodies re-hashing; a part whose `part.json` exists without its head is adopted when the `part.json` computed equals it byte for byte, else refused; `--through` derives along the chain ending at that stamp and refuses a table root holding any entry but `.capture.lock`, the lockfile `run_derive`'s own lock creates in it before `derive_table` runs.

- [ ] **Step 1: The failing tests,** in `tests/test_vintage_table.py`, log lines read through `caplog` after `caplog.set_level(logging.DEBUG)` on cases that call `run_derive` directly, over `standard_record` (Task 6) and its NAS-shaped copy (`shutil.copytree`, then directories 0775 and files 0664), with `fixture_head_sha256(root: Path) -> str`, the last head's sha256 of a table derived from `standard_record` under `root`:
  - `test_three_tables_agree_head_by_head`: built tick by tick, built with runs that skipped ticks and caught up, and rebuilt into an empty root, from the ops-shaped and the NAS-shaped copy: byte-equal heads at every tick.
  - `test_ticks_after_a_head_change_nothing_read_through_it`.
  - `test_read_table_takes_a_path_a_stamp_or_a_sha256`: the same rows each way, walking back by `prev_tick` over the standard record's uneven gaps.
  - `test_read_table_refuses_what_does_not_hash`, parametrised: a head's byte, a `part.json`'s, a parquet frame whose content changed, a `parts_sha256`.
  - `test_head_names_the_highest_position_after_a_clock_regression`.
  - `test_the_frame_hash`: each dtype renders as above; a frame written and read back by polars hashes equal; a head naming `hash_version` 1 is read with version 1 after `FRAME_HASH_VERSION` is monkeypatched to 2.
  - `test_a_later_fact_lands_in_the_later_part`: a regression's predecessor, a `prev.error` and an acknowledged link each appear in the later tick's `part.json` and none in the earlier part, and `read_table` joins them.
  - `test_a_link_that_does_not_hash_stops_the_run_keeping_earlier_parts`.
  - `test_a_body_that_does_not_rehash_stops_the_run_at_its_tick`: a table derived to the head of a three-tick record, then a fourth tick published and one of its bodies replaced by other valid gzip bytes (its directory made writable and set back) before the next run: ERROR naming the fourth tick, exit 1, the three parts kept and no part for the fourth.
  - `test_a_fork_stops_before_deriving`: a tick the table took deleted from `record/`, the next tick chaining around it: ERROR names it, exit 1, no part added; restored to its recorded bytes, the next run still stops naming it, since the tick that chained around it keeps it off the chain (spec D5's head rule); and `derive_table(…, generation=2)`, `GENERATION_ENTRIES` monkeypatched to hold `2: ()`, builds `gen-2/` along the current chain, a part for the tick that chained around it and none for the restored one, `gen-1/` byte-identical.
  - `test_a_moved_tick_stops_before_deriving`: a taken tick's `tick.json` changed: the same; a restore to the recorded bytes resumes.
  - `test_through_rebuilds_the_old_branch_and_refuses_a_non_empty_root`: on the NAS-shaped copy holding the fork, `--through <the deleted tick>` gives heads byte-equal to the table's old heads, both through `derive_table` and through `run_derive` (the CLI path, whose lock creates `.capture.lock` first) into an empty root; a root holding any other entry is refused.
  - `test_a_dead_runs_staging_never_blocks_and_is_named`: on an empty table root, the leftovers of a dead run in the same start second as the run's `FakeClock`, among them `staging/gen-1.<that second>.deadbeef/`, are named in one WARNING and the run completes, leaving nothing of its own in `staging/`, the leftovers alone; a run over a clean `staging/` leaves it empty.
  - `test_the_state_read_through_a_head_equals_the_state_in_memory`: over `standard_record`, `DeriveState.from_frames` of the frames `read_table` returns through each head equals the `DeriveState` that `derive_tick` built in memory through that tick; and the state through the third tick holds a `cm-btc` (series, day) standing retracted whose fourth-tick version is a `restoration`, so the comparison reads a set flag.
  - `test_a_published_directory_left_0755_is_set_0555`.
  - `test_a_part_without_its_head_is_adopted_or_refused`: byte-equal, only the head staged; differing, refused.
  - `test_a_torn_generation_and_a_differing_generation_json`: a torn staging generation leaves no `gen-1/` and the next run opens it; a `generation.json` whose entries differ from `GENERATION_ENTRIES` stops `at=none`.
  - `test_a_new_generation_builds_from_genesis_and_a_return_resumes`: `derive_table(…, generation=2)`, `GENERATION_ENTRIES` monkeypatched to hold `2: ()`, opens `gen-2/` from genesis with `gen-1/` byte-identical and readable; a later run at `generation=1` resumes `gen-1/` from its head.
  - `test_a_held_lock_stops_with_the_derives_own_message`.
  - `test_the_table_root_refusal`: under a record root, under its parent, and under `nfs_mount_dir` refused; `--record /vintages/record --table /versions` admitted by `refuse_table_root`; a host pair with the table under `vintages/` refused; through `run_derive`, with `cli.vintage.command.load_config` monkeypatched to return `dataclasses.replace(load_config(tmp_path / "absent.toml"), nfs_mount_dir=<a directory under tmp_path>)`, a table root under that directory, outside the record root and its parent, that did not exist exits 1 and still does not exist after the refusal.
  - `test_the_frames_columns_dtypes_and_order`: every column's name, order and dtype, none nested, rows sorted; `token` null exactly on retractions.
  - `test_provider_leaves_out_bgeometrics_alone`: `provider == "bgeometrics"` removes every `bg-*` row of both frames and no other.
  - `test_as_of_through_a_head_equals_the_derivation_in_memory`: at every tick's `ended_at` and one second either side.
  - `test_the_fixture_head_is_pinned`: the last head's sha256 equals `HEAD_PINS[DERIVE_GENERATION]`.
  - `test_the_summary_lines_and_the_prom`: INFO and exit 0 at the record's head; ERROR stop line and exit 1 on a stop; the `.prom` holds the head tick's stamp as Unix time, and 0 on an empty table; and, with `ZCRYPTO_BUILD_REVISION` set by `monkeypatch.setenv`, `generation.json`'s `opened_by` ends with `+` followed by that revision's first 12 characters.
- [ ] **Step 2: Run them and read them fail.**
- [ ] **Step 3: `table.py`, the helper, the `derive` command.** Then, in its own call, `uv run python -c 'from pathlib import Path; from tests.test_vintage_table import fixture_head_sha256; print(fixture_head_sha256(Path(".tmp/00158/task10/pin")))'`, its printed value pasted into `HEAD_PINS = {1: "<that>"}`, and `.tmp/00158/task10/pin` removed by `chmod -R u+w .tmp/00158/task10/pin` and then `rm -rf .tmp/00158/task10/pin`, each its own call (its generation, part and head directories are 0555).
- [ ] **Step 4: The task's run with `tests/test_dashboards_cover_metrics.py`, the gate, commit** `feat(vintage): the versions table, its parts, its head log and the derive command`.
- [ ] **Step 5: Probes,** each KILLED. `--file cli/vintage/table.py`:
  - `test_three_tables_agree_head_by_head`: a part per run rather than per tick.
  - `test_read_table_refuses_what_does_not_hash`: the `parts_sha256` check removed; the `prev` check removed.
  - `test_a_fork_stops_before_deriving`: the ancestry check on chain membership removed.
  - `test_a_moved_tick_stops_before_deriving`: the ancestry check on the `tick.json` sha256 removed.
  - `test_a_part_without_its_head_is_adopted_or_refused`: adoption without the byte comparison.
  - `test_a_torn_generation_and_a_differing_generation_json`: the entries' comparison removed.
  - `test_a_new_generation_builds_from_genesis_and_a_return_resumes`: the generation directory named from `DERIVE_GENERATION` rather than the `generation` argument.
  - `test_the_frame_hash`: the datetime rendered without microseconds.
  - `test_a_later_fact_lands_in_the_later_part`: the regression's fact written into the earlier tick's rows.
  - `test_ticks_after_a_head_change_nothing_read_through_it`: `read_table` reading every part under `parts/` rather than the parts its walk from the head names.
  - `test_read_table_takes_a_path_a_stamp_or_a_sha256`: the predecessor's path computed as the head's stamp less 12 hours rather than read from `prev_tick`.
  - `test_head_names_the_highest_position_after_a_clock_regression`: `head()` taking the newest stamp rather than the highest `position`.
  - `test_a_link_that_does_not_hash_stops_the_run_keeping_earlier_parts`: the link check before a tick is derived removed.
  - `test_through_rebuilds_the_old_branch_and_refuses_a_non_empty_root`: the non-empty-root refusal under `--through` removed; and `.capture.lock` counted as an entry.
  - `test_a_body_that_does_not_rehash_stops_the_run_at_its_tick`: the re-hash of a tick's bodies before it is derived removed.
  - `test_a_dead_runs_staging_never_blocks_and_is_named`: `s/secrets\.token_hex(4)/"deadbeef"/` (a name without its random part meets the dead run's).
  - `test_a_published_directory_left_0755_is_set_0555`: the sweep that sets published directories 0555 removed.
  - `test_as_of_through_a_head_equals_the_derivation_in_memory`: `read_table` returning the head's own part's rows alone.

  `--file cli/vintage/storage.py`, `test_the_table_root_refusal`: the parent's refusal removed.

  `--file cli/vintage/derive.py`:
  - `test_the_fixture_head_is_pinned`: the pinned sha256's last hex digit changed.
  - `test_the_frames_columns_dtypes_and_order`: `knowable_at`'s dtype in `VERSIONS_SCHEMA` made `pl.String`.
  - `test_the_state_read_through_a_head_equals_the_state_in_memory`: `from_frames` leaving every day's retracted flag unset.

  `--file cli/vintage/sources.py`, `test_provider_leaves_out_bgeometrics_alone`: the `bg-*` sources' `provider` spelt `bitcoin-data`.

  `--file cli/vintage/command.py`:
  - `test_a_held_lock_stops_with_the_derives_own_message`: the `CaptureError` re-raised.
  - `test_the_summary_lines_and_the_prom`: the `.prom`'s value taken from the run's clock rather than the head tick's stamp.
  - `test_the_table_root_refusal`: `run_derive`'s refusal moved after the lock; and `run_derive`'s mount taken as `Path("/nonexistent")` in place of `load_config().nfs_mount_dir`.

### Task 11: The write guard (D18)

**Files:** Modify `tests/test_vintage_record.py`.

**Interfaces:** Consumes every `cli/vintage/*.py`; the helper names `create_exclusive`, `publish_tick`, `publish_prom`, `publish_table_dir`, `write_part`, and Task 3's dial, `_dial`.

- [ ] **Step 1: The tests,** an AST walk of every `cli/vintage/*.py`, one case per rule, each naming the offending `path:line`:
  - `test_a_rename_lives_only_in_the_three_helpers`: a rename only inside `publish_tick`, `publish_prom` and `publish_table_dir`. The syntax tree carries no types, so the walk tells a rename by its shape: `os.replace`, `os.rename` and `os.renames` (an attribute call on the name `os`), and any other attribute call named `replace` or `rename` whose arguments are exactly one positional, or exactly the one keyword `target`, the shapes of `Path.replace(target)`, `Path.rename(target)` and their `target=` spellings. `bytes.replace(old, new)` and `str.replace(old, new)`, which `key_forms` needs for the JSON-escaped form, take two positionals, and `datetime.replace(microsecond=0)` takes keywords, so neither is a rename;
  - `test_every_os_open_is_an_exclusive_create_or_a_read`: each `os.open` spells `O_CREAT` and `O_EXCL`, or none of `O_WRONLY`, `O_RDWR`, `O_TRUNC`, `O_APPEND`, in flags the tree spells as `os.O_*` names joined by `|`; any other flags expression fails;
  - `test_mkstemp_lives_only_in_the_prom_helper`;
  - `test_write_parquet_lives_only_in_the_part_writer`;
  - `test_every_other_opening_call_reads`: the builtin `open`, `io.open`, `codecs.open`, `gzip.open`, `gzip.GzipFile`, and any other attribute call named `open` whose receiver is not the name `os` (`Path.open`; `os.open` is the rule above's alone), each only with a literal mode holding none of `w`, `a`, `x`, `+`, except a `gzip.GzipFile` given `fileobj` and an attribute `.open` inside the body of a function named `_dial` that carries no string-literal positional and no `mode=` keyword, Task 3's one dial through an opener, whose first argument is a `Request` and no mode; a `.open` inside `_dial` with either is read as any other. The mode is read from `mode=` or from the positional slot the callee takes it in, the second for the builtin `open`, `io.open`, `codecs.open`, `gzip.open` and `gzip.GzipFile`, the first for an attribute `.open` such as `Path.open`; no mode is the read default, and a mode that is not a string literal fails;
  - `test_no_copy_move_truncate_or_delete`, the allowlist D18 states, so a call the walk does not know fails: every call whose callee resolves, through every import the module holds at any level (`import os`, `import os as o`, `from os import replace as r`), to a name in `os`, `os.path`, `shutil`, `pathlib`, `io`, `codecs`, `gzip` or `tempfile` is on `FS_ALLOWED`, a frozenset the test pins (the read, stat, listing, exclusive-create, fsync and chmod forms the modules use, among them `os.open`, `os.read`, `os.write`, `os.fsync`, `os.close`, `os.chmod`, `os.mkdir`, `os.stat`, `os.fstat`, `os.listdir`, `os.scandir`, `os.environ.get`, every `os.path` name, `os.rename` and `os.replace` (rule 1 holds them to the helpers), `pathlib.Path`, `gzip.compress`, `gzip.decompress`, `gzip.open` and `gzip.GzipFile` (rule 5 holds their modes), `io.open` and `codecs.open` (likewise), `io.BytesIO`, `tempfile.mkstemp` (rule 3)), and a name it would add is a read or a create that never replaces, never a form that writes over, moves, truncates or removes a path, so `shutil`'s copies, moves and `rmtree`, `os.truncate`, `os.ftruncate`, `os.remove`, `os.unlink`, `os.rmdir`, `os.removedirs` and `io.FileIO` are off it; every `from <one of those modules> import <name>` imports a name on it; and no attribute call, whatever its receiver, is named `unlink`, `rmdir`, `truncate`, `write_bytes`, `write_text`, `touch`, `symlink_to`, `hardlink_to`, `copy_into`, `move` or `move_into`, or is named `copy` with any argument (`dict.copy()`, `list.copy()` and `set.copy()` take none), or starts `write_` or `sink_` other than rule 4's `write_parquet`, so `Path.unlink`, 3.14's `Path.copy`, `Path.copy_into`, `Path.move` and `Path.move_into`, each of which replaces an existing target, and polars' `write_csv`, `write_ipc`, `write_json`, `write_ndjson` and `sink_parquet`, whose receivers the tree cannot type, fail by name. With rule 1's `replace` and `rename` and rule 5's `open`, that holds every `pathlib.Path` method of 3.14.6 that writes, moves or removes a path; the ones left, `chmod`, `lchmod` and `mkdir`, change no file's bytes. Rules 1, 3, 4 and 5 resolve a callee through the same imports, so a bare imported name is held as its qualified one;
  - `test_the_guard_admits_the_allowed_forms`: the walk over the real modules is clean, and over a fixture source holding each allowed form (an exclusive `os.open`, `os.open(p, os.O_RDONLY)`, `open(p, "rb")`, `p.open("rb")`, `gzip.GzipFile(fileobj=f, mode="wb")`, `def _dial(o, r): return o.open(r, timeout=30)`, `b"/".replace(b"/", b"\\/")`, `now.replace(microsecond=0)`, `d.copy()`, `from os import fsync` and `fsync(fd)`) reports nothing.

  The walk calls `ast.parse` on each module without catching, so a module that does not parse fails every case.
- [ ] **Step 2: The task's run, the gate, commit** `test(vintage): the write guard, every rename in a named helper and every write exclusive`.
- [ ] **Step 3: Probes,** each KILLED, each appending one line to a module the guard walks. An emptied module breaks no rule, so `1,$d` is no control here: each arm's control appends a second form of the same rule, which the selected case reads whatever `tests/test_vintage_record.py` imports at its top:
  - `--file cli/vintage/verify.py`, `test_a_rename_lives_only_in_the_three_helpers`, control `$a\def _control(p): import os; os.rename(p, p)`: `$a\def _probe(p): import os; os.replace(p, p)`;
  - `--file cli/vintage/verify.py`, `test_every_os_open_is_an_exclusive_create_or_a_read`, control `$a\def _control(p): import os; os.open(p, os.O_RDWR)`: `$a\def _probe(p): import os; os.open(p, os.O_WRONLY | os.O_CREAT)`;
  - `--file cli/vintage/verify.py`, `test_mkstemp_lives_only_in_the_prom_helper`, control `$a\def _control(p): import tempfile; tempfile.mkstemp(dir=p)`: `$a\def _probe(): import tempfile; tempfile.mkstemp()`;
  - `--file cli/vintage/derive.py`, `test_write_parquet_lives_only_in_the_part_writer`, control `$a\def _control(df, p): df.write_parquet(p, compression="zstd")`: `$a\def _probe(df, p): df.write_parquet(p)`;
  - `--file cli/vintage/verify.py`, `test_every_other_opening_call_reads`, control `$a\def _control(p): open(p, "w")`: `$a\def _probe(p): import gzip; gzip.open(p, "wb")`; the dial's form outside `_dial`, `$a\def _probe(o, r): o.open(r, timeout=30)`; and a write mode inside a function named `_dial`, `$a\def _dial(p): return p.open("w")` and `$a\def _dial(p): return p.open(mode="wb")`;
  - `--file cli/vintage/verify.py`, `test_no_copy_move_truncate_or_delete`, control `$a\def _control(a, b): import shutil; shutil.move(a, b)`: `$a\def _probe(a, b): import shutil; shutil.copyfile(a, b)`; `$a\from shutil import copyfile as _c`; `$a\def _probe(df, p): df.write_csv(p)`; `$a\def _probe(p): import io; io.FileIO(p, "w")`; `$a\def _probe(fd): import os; os.ftruncate(fd, 0)`; `$a\def _probe(p, q): p.move(q)`; and `$a\def _probe(p, q): p.copy(q)`.
  - `--file cli/vintage/verify.py`, `test_a_rename_lives_only_in_the_three_helpers`, control `$a\def _control(p): import os; os.rename(p, p)`, a second arm: `$a\def _probe(a, b): from os import replace; replace(a, b)` (a bare imported name); and a third, `$a\def _probe(p, q): p.replace(target=q)`.

  `test_the_guard_admits_the_allowed_forms` takes no arm: it is the six rules' negative side, which no mutation of `cli/vintage/` can turn red without being one of the arms above, and the task's run reads it green.

### Task 12: The ops runners, units and timer, the gated block and the keep-regex (D1, D2, D12's ping, D16's runner, D17)

**Files:** Create `infra/ansible/roles/ops/templates/vintage-record.sh.j2`, `vintage-record.service.j2`, `vintage-record.timer.j2`, `vintage-derive.sh.j2`, `vintage-derive.service.j2`, `tests/test_infra_vintage_record_template.py`; modify `infra/ansible/roles/ops/tasks/main.yml`, `infra/ansible/roles/ops/defaults/main.yml`, `infra/ansible/roles/ops/files/config.alloy`, `tests/test_infra_shell_templates_render.py`, `tests/test_infra_hc_role.py`, `tests/test_infra_alloy_series.py`, `tests/test_vintage_record.py`.

**Interfaces:** Consumes the `record` and `derive` options (Tasks 8 and 10) and Task 4's `run_tick`; produces the role defaults `ops_vintages_subdir: vintages`, `ops_vintage_versions_subdir: vintage-versions`, `ops_vintage_record_healthcheck_url: ""` that Tasks 13 and 14 use, and the task names below.

The record runner, verbatim below its rendered-by header and a comment saying what each part guards:

```bash
set -u

log() {
    _ts=$(date -u +'%Y-%m-%d %H:%M:%S,%N')
    printf '%s %s zcrypto.vintage-record [vintage-record.sh] - %s\n' "${_ts%??????}" "$1" "$2" >&2
}

URL="{{ ops_vintage_record_healthcheck_url }}"
TOKEN="{{ ops_compose_dir }}/vintage-bgeometrics.token"

if ! { exec 3<"$TOKEN"; } 2>/dev/null || ! [ -f /dev/fd/3 ]; then
    exec 3</dev/null
    log ERROR "the BGeometrics key file $TOKEN is absent, unreadable or not a regular file: its four sources record no credential this tick"
fi

out="$(mktemp)"
docker run --rm -i --pull never \
    --name zcrypto-vintage-record \
    --user "{{ ops_uid }}:{{ ops_gid }}" \
    -v "{{ ops_data_dir }}/{{ ops_vintages_subdir }}:/data" \
    -v "{{ ops_textfile_dir }}:/textfile" \
    --entrypoint zcrypto \
    "{{ ops_image }}@{{ ops_image_digest }}" \
    vintage record --data-dir /data --textfile /textfile/vintage.prom --clock-prom /textfile/clock-offset.prom --bgeometrics-key-stdin "$@" \
    <&3 > "$out" 2>&1
rc=$?
exec 3<&-
cat "$out"
witness=$(grep -cE '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2},[0-9]{3} INFO zcrypto\.vintage\.[a-z_.]+ \[[a-z_]+\.py:[0-9]+\] - vintage tick published tick=[0-9]{8}T[0-9]{6}Z tick_json_sha256=[0-9a-f]{64}$' "$out")
witness=${witness:-0}
rm -f "$out"
if [ "$rc" -ge 2 ] || [ "$witness" -eq 0 ]; then
    log ERROR "the recorder run ended with exit $rc and $witness published-tick line(s), so the dead-man was not pinged"
fi
if { [ "$rc" -eq 0 ] || [ "$rc" -eq 1 ]; } && [ "$witness" -ge 1 ] && [ -n "$URL" ]; then
    curl -fsS -m 10 -o /dev/null "$URL" 2>/dev/null || log WARNING "the dead-man ping did not reach its check"
fi
exit "$rc"
```

The derive runner, the same `log()` as `zcrypto.vintage-derive [vintage-derive.sh]`, no stdin, no secret:

```bash
out="$(mktemp)"
docker run --rm --pull never \
    --name zcrypto-vintage-derive \
    --user "{{ ops_uid }}:{{ ops_gid }}" \
    --network none \
    -v "{{ ops_data_dir }}/{{ ops_vintages_subdir }}/record:/vintages/record:ro" \
    -v "{{ ops_data_dir }}/{{ ops_vintage_versions_subdir }}:/versions" \
    -v "{{ ops_textfile_dir }}:/textfile" \
    --entrypoint zcrypto \
    "{{ ops_image }}@{{ ops_image_digest }}" \
    vintage derive --record /vintages/record --table /versions --textfile /textfile/vintage-derive.prom \
    > "$out" 2>&1
rc=$?
cat "$out"
summary=$(grep -cE ' - vintage derive (complete|stopped) generation=' "$out")
summary=${summary:-0}
rm -f "$out"
if { [ "$rc" -ne 0 ] && [ "$rc" -ne 1 ]; } || [ "$summary" -eq 0 ]; then
    log ERROR "the versions table refresh ended with exit $rc and $summary summary line(s); the record is untouched"
fi
exit "$rc"
```

The two units and the timer are the spec's block under *The units and the timer* verbatim, below each one's rendered-by header; the timer's comment records the slot clearance as the spec's D2 lists it. The gated block, after `install the ops stack — recorder compose + replay/panel timers (needs the pinned image digest)`:

```yaml
- name: install the vintage recorder and its versions-table refresh (needs the pinned image digest)
  when: ops_image_digest is defined
  block:
    - name: install the vintage recorder runner script
      ansible.builtin.template: {src: vintage-record.sh.j2, dest: /usr/local/sbin/zcrypto-vintage-record, owner: root, group: root, mode: "0700"}
      no_log: true
      diff: false
    - name: install the versions-table refresh runner script
      ansible.builtin.template: {src: vintage-derive.sh.j2, dest: /usr/local/sbin/zcrypto-vintage-derive, owner: root, group: root, mode: "0700"}
    - name: render the vintage recorder and refresh units and the recorder timer
      ansible.builtin.template: {src: "{{ item }}.j2", dest: "/etc/systemd/system/zcrypto-{{ item }}", owner: root, group: root, mode: "0644"}
      loop: [vintage-record.service, vintage-record.timer, vintage-derive.service]
      register: ops_vintage_unit_install
    - name: enable + start the vintage recorder timer
      ansible.builtin.systemd_service: {name: zcrypto-vintage-record.timer, daemon_reload: true, enabled: true, state: started}
      when: not (ansible_check_mode and ops_vintage_unit_install is changed)
```

written in the file's block style, each task's comment saying why (the runner carries the ping URL; only the timer is enabled; the derive unit has no `[Install]` and is pulled in by the recorder's unit). `config.alloy`'s keep-regex alternation gains `vintage-record|vintage-derive`, and its comment the two units.

- [ ] **Step 1: The failing tests,** in `tests/test_infra_vintage_record_template.py`, rendering with `jinja2.StrictUndefined` and a context of real shapes (`ops_uid` `"998"`, `ops_compose_dir` `/etc/zcrypto-ops`, `ops_vintage_record_healthcheck_url` `https://hc.invalid/ping/k/zcrypto-vintage-record`):
  - `test_the_record_runners_argv`: the `docker run` line, continuations joined and split by `shlex`, is exactly `docker run --rm -i --pull never --name zcrypto-vintage-record --user 998:998 -v /var/lib/zcrypto-ops/vintages:/data -v /var/lib/zcrypto-ops/textfile:/textfile --entrypoint zcrypto <image>@<digest> vintage record --data-dir /data --textfile /textfile/vintage.prom --clock-prom /textfile/clock-offset.prom --bgeometrics-key-stdin $@`, the last token `shlex`'s reading of the quoted `"$@"`, its one input redirection `<&3`, no `-e`, `--env-file`, `--network` or `/mnt/` mount; each option name is an option of `vintage record` on the real CLI (`typer.main.get_command(app)`).
  - `test_the_runners_own_arguments_follow_the_clis`, through the harness of `test_the_dead_man_pings_only_on_a_published_tick` below: the runner run with the arguments `--source cm-eth --source fng` hands the stub an argv ending `--bgeometrics-key-stdin --source cm-eth --source fng`, and run with none, one ending `--bgeometrics-key-stdin`.
  - `test_the_derive_runners_argv`: exactly the derive line above, no `-i`, no `<`, no `-e`, no `--env-file`, no `/mnt/` mount; each option on the real `vintage derive`.
  - `test_the_derive_mounts_the_record_read_only_at_the_hosts_shape`: `-v …/vintages/record:/vintages/record:ro` with `--record /vintages/record`.
  - `test_the_record_unit`: `Type=oneshot`, `Requires=docker.service`, `Wants=network-online.target`, `Wants=zcrypto-vintage-derive.service`, `After=docker.service network-online.target`, `ExecStart=/usr/local/sbin/zcrypto-vintage-record`, no `RequiresMountsFor`.
  - `test_the_timer_fires_at_0737_and_1937_and_catches_up_once`: the two `OnCalendar` lines `*-*-* 07:37:00` and `*-*-* 19:37:00`, `Persistent=true`, `Unit=zcrypto-vintage-record.service`, no `RandomizedDelaySec`, no `TimeoutStartSec`.
  - `test_the_timer_is_wanted_by_timers_target`.
  - `test_the_derive_unit_runs_after_the_recorder`: `After=docker.service zcrypto-vintage-record.service`, `ExecStart=/usr/local/sbin/zcrypto-vintage-derive`.
  - `test_the_derive_unit_has_no_install_section`: its section headers, in order, are exactly `[Unit]` and `[Service]`, so an empty render fails it as surely as an `[Install]` does.
  - `test_the_block_is_gated_on_the_digest_and_enables_the_timer_alone`: the block's `when` is `ops_image_digest is defined` and it follows the getent facts; the record runner's install is root 0700, `no_log`, `diff: false`; the derive runner's root 0700; the one enable names `zcrypto-vintage-record.timer` under `when: not (ansible_check_mode and ops_vintage_unit_install is changed)`; no task in the role starts or enables `zcrypto-vintage-record.service` or `zcrypto-vintage-derive.service`.
  - `test_the_dead_man_pings_only_on_a_published_tick`, through a harness after `tests/test_infra_verify_replay_template.py`'s `_bash_harness`: the rendered runner run by bash with `TMPDIR` under `tmp_path`, `ops_compose_dir` rendered to a directory under `tmp_path`, a `docker` stub that records its argv, `readlink /proc/self/fd/0` and its stdin bytes, prints `$STUB_OUT`, the witness line where a case names no output, and exits `$STUB_RC`, 0 where a case names none, and a `curl` stub recording its calls; parametrised: the witness and 0 pings; the witness and 1 pings; 1 without it, the witness and 2, the witness and 125, and a witness line whose sha256 is 63 hex never ping; and, the runner rendered with `ops_vintage_record_healthcheck_url` `""`, the witness and 0 make no `curl` call and log nothing of the runner's own.
  - `test_a_run_with_no_witness_or_an_exit_past_1_logs_one_runner_error`, through the same harness with the token file holding `SENTINEL_KEY` and the `curl` stub succeeding, parametrised on (exit, output): (0, the witness) and (1, the witness) give no runner line; (0, nothing), (1, nothing), (2, nothing), (125, nothing) and (137, the witness) each give exactly one runner ERROR matching `_ops_parse_regex()` with its `rest` group starting `zcrypto.vintage-record [vintage-record.sh] - ` and naming the exit, and every one of them exits with the stub's code; and with `TMPDIR` naming a directory that does not exist, so `mktemp` fails and the stub never runs, exactly one runner ERROR naming exit 1.
  - `test_an_absent_token_file_gives_dev_null_and_one_error`, `test_a_directory_token_path_gives_dev_null_and_one_error`, `test_an_unreadable_token_file_gives_dev_null_and_one_error` (mode 0000; under uid 0 the case calls `pytest.fail("run as a non-root uid: root reads a 0000 file")`), each: the stub ran once, its stdin is `/dev/null`, and the runner's stderr holds exactly one line, its ERROR, naming the path and no byte of the file.
  - `test_an_empty_token_file_gives_empty_stdin_and_no_error`: the stub ran once, its stdin is the token file and empty, and the runner logged nothing of its own.
  - `test_a_token_file_reaches_stdin_whole`: a file holding `SENTINEL_KEY` and a newline: the stub ran once, its stdin is the token file, its bytes are the file's whole, and the runner logged nothing of its own.
  - `test_every_line_the_runner_prints_is_parse_shaped`: with the token absent and the ping failing, the runner's own lines are exactly two, the token ERROR and the ping WARNING, each matching `_ops_parse_regex()` from `tests/test_infra_archive_pull_template.py` with its `rest` group starting `zcrypto.vintage-record [vintage-record.sh] - `, the logger-and-file shape the unit-parse canary keys on, as `test_verified_replays_refusals_log_through_the_helper_at_warning` asserts it.
  - `test_the_derive_runner_names_an_odd_exit_or_a_missing_summary`, through the same harness on the rendered derive runner, its `docker` stub printing `$STUB_OUT` and exiting `$STUB_RC`, parametrised on (exit, output): (0, a `vintage derive complete generation=1 …` line) and (1, a `vintage derive stopped generation=1 …` line) give no runner line; (0, nothing), (125, nothing) and (137, a `complete` line) each give exactly one runner ERROR matching `_ops_parse_regex()` with its `rest` group starting `zcrypto.vintage-derive [vintage-derive.sh] - `; every case exits with the stub's code; and with `TMPDIR` naming a directory that does not exist, so `mktemp` fails and the stub never runs, exactly one runner ERROR naming exit 1.
  - `test_the_witness_pattern_matches_the_line_the_recorder_logs`: a tick through `tests/vintage_stub.py`'s `run_tick` under `caplog` after `caplog.set_level(logging.DEBUG)`, its `vintage tick published` record formatted by `cli.logging.formatters.PlainTextFormatter`, the console formatter `configure` installs, and that one line fed to `grep -cE` with the pattern read out of the rendered record runner's `witness=$(grep -cE '…' "$out")` line, prints `1`; so the dead-man's gate and the line the CLI really logs are read together, where the harness cases above feed the stub a witness line the test writes.
  - In `tests/test_vintage_record.py`, `test_the_last_ok_cap_is_the_evening_slot_plus_the_tick_deadline`: the timer template's second `OnCalendar` plus `TICK_DEADLINE_SECONDS` equals `LAST_OK_CAP`.
- [ ] **Step 2: Run them and read them fail.**
- [ ] **Step 3: The five templates, the block, the defaults, the keep-regex,** and in the same commit: `REGISTERED` gains `vintage-derive.sh.j2` and `vintage-record.sh.j2`; `PING_RENDERS` gains `("ops", "install the vintage recorder runner script")`; `tests/test_infra_alloy_series.py`'s `_installed_units()` gains every service template, a oneshot with no timer of its own among them, in two statements before its double-prefix assert, so the glob sits on one line under the 132-column limit:

```python
    services = (p.name.removesuffix(".service.j2") for p in (_OPS_ROLE / "templates").glob("*.service.j2"))
    units |= {n if n.startswith("zcrypto-") else f"zcrypto-{n}" for n in services}
```

its docstring saying a oneshot pulled in by another unit is installed too. The alternation in `config.alloy` gains `|vintage-record|vintage-derive` at its end, in that order: `zcrypto-(archive-pull|verify-replay|verified-replay|panel-materialize|tape-bars|vintage-record|vintage-derive)\\.service;.*|.*;grafana-alloy`.
- [ ] **Step 4: The task's run with `tests/test_infra_alloy_series.py`, `tests/test_infra_shell_templates_render.py`, `tests/test_infra_hc_role.py` and `tests/test_internal_terms_not_operator_visible.py`, the gate, commit** `feat(ops): the vintage recorder's timer, its runners and the versions-table refresh`.
- [ ] **Step 5: Probes,** each KILLED. `--file infra/ansible/roles/ops/templates/vintage-record.sh.j2`:
  - `test_the_record_runners_argv`: `s/docker run --rm -i --pull never/docker run --rm -i/`; and `s/^    <&3 > "\$out" 2>&1$/    < "$TOKEN" > "$out" 2>\&1/`.
  - `test_the_runners_own_arguments_follow_the_clis`: `s/ --bgeometrics-key-stdin "\$@" \\$/ --bgeometrics-key-stdin \\/`.
  - `test_the_dead_man_pings_only_on_a_published_tick`: `s/ && \[ "\$witness" -ge 1 \]//`; `s/tick_json_sha256=\[0-9a-f\]{64}\$/tick_json_sha256=[0-9a-f]*/`; and `s/ && \[ -n "\$URL" \]//`.
  - `test_a_run_with_no_witness_or_an_exit_past_1_logs_one_runner_error`: `s/^if \[ "\$rc" -ge 2 \] || \[ "\$witness" -eq 0 \]; then$/if false; then/`; the exit's arm dropped, `s/^if \[ "\$rc" -ge 2 \] || /if /`; the witness's arm dropped, `s/ || \[ "\$witness" -eq 0 \]; then$/; then/`; and the empty count of a failed `mktemp` left empty, `/^witness=\${witness:-0}$/d`.
  - `test_a_directory_token_path_gives_dev_null_and_one_error`: `s/ || ! \[ -f \/dev\/fd\/3 \]//`.
  - `test_an_absent_token_file_gives_dev_null_and_one_error`: `/exec 3<\/dev\/null/d`.
  - `test_an_unreadable_token_file_gives_dev_null_and_one_error`: the guard read off the path rather than the opened descriptor, `s#^if ! { exec 3<"\$TOKEN"; } 2>/dev/null || ! \[ -f /dev/fd/3 \]; then$#{ exec 3<"$TOKEN"; } 2>/dev/null; if ! [ -f "$TOKEN" ]; then#` (a 0000 file is a regular file, so descriptor 3 is never opened; the absent and directory cases stay green under it).
  - `test_an_empty_token_file_gives_empty_stdin_and_no_error`: the empty file sent to the fallback, `s# || ! \[ -f /dev/fd/3 \]; then$# || ! [ -f /dev/fd/3 ] || ! [ -s /dev/fd/3 ]; then#`.
  - `test_a_token_file_reaches_stdin_whole`: stdin from `/dev/null` always, `s/^    <&3 > "\$out" 2>&1$/    <\/dev\/null > "$out" 2>\&1/`.
  - `test_every_line_the_runner_prints_is_parse_shaped`: `s/ zcrypto\.vintage-record \[vintage-record\.sh\] - / zcrypto.vintage-record - /`.
  - `tests/test_infra_shell_templates_render.py -k 'test_shell_template_renders_to_valid_bash and vintage-record.sh.j2'`, control `$a if` (an emptied template is valid bash): `$a fi`.

  `--file infra/ansible/roles/ops/templates/vintage-derive.sh.j2`:
  - `test_the_derive_runners_argv`: `s/    --network none \\$/    \\/`.
  - `test_the_derive_mounts_the_record_read_only_at_the_hosts_shape`: `s/:\/vintages\/record:ro"/:\/vintages\/record"/`.
  - `test_the_derive_runner_names_an_odd_exit_or_a_missing_summary`: the exit-code arm dropped, `s#^if { \[ "\$rc" -ne 0 \] && \[ "\$rc" -ne 1 \]; } || \[ "\$summary" -eq 0 \]; then$#if [ "$summary" -eq 0 ]; then#`; the summary arm dropped, `s# || \[ "\$summary" -eq 0 \]; then$#; then#`; the empty count of a failed `mktemp` left empty, `/^summary=\${summary:-0}$/d`; and the line shape broken, `s/ zcrypto\.vintage-derive \[vintage-derive\.sh\] - / zcrypto.vintage-derive - /`.
  - `tests/test_infra_shell_templates_render.py -k 'test_shell_template_renders_to_valid_bash and vintage-derive.sh.j2'`, control `$a if`: `$a fi`.

  `--file infra/ansible/roles/ops/templates/vintage-record.service.j2`, `test_the_record_unit`: `/^Wants=zcrypto-vintage-derive\.service$/d`.

  `--file infra/ansible/roles/ops/templates/vintage-record.timer.j2`:
  - `test_the_timer_fires_at_0737_and_1937_and_catches_up_once`: `s/19:37:00/19:52:00/`.
  - `test_the_timer_is_wanted_by_timers_target`: `/^WantedBy=timers\.target$/d`.

  `--file infra/ansible/roles/ops/templates/vintage-derive.service.j2`:
  - `test_the_derive_unit_runs_after_the_recorder`: `s/^After=docker\.service zcrypto-vintage-record\.service$/After=docker.service/`.
  - `test_the_derive_unit_has_no_install_section`: `$a [Install]` (the control `1,$d` fails it now that the case reads both sections).

  `--file infra/ansible/roles/ops/tasks/main.yml`:
  - `test_the_block_is_gated_on_the_digest_and_enables_the_timer_alone`: the enable task's unit name made `zcrypto-vintage-record.service`; the block's `when` removed; and the enable's check-mode guard removed, `/when: not (ansible_check_mode and ops_vintage_unit_install is changed)/d`.
  - `tests/test_infra_hc_role.py -k test_every_render_that_carries_a_ping_url_is_never_logged_never_diffed_and_read_by_its_owner_alone`: the record runner install's `no_log` removed, `/name: install the vintage recorder runner script/,/no_log: true/{/no_log: true/d}`.

  `--file infra/ansible/roles/ops/files/config.alloy`, `tests/test_infra_alloy_series.py -k test_the_ops_journal_keep_regex_accounts_for_every_unit_the_role_installs`: `s/|vintage-derive)/)/`.

  `--file cli/vintage/record.py`, `tests/test_vintage_record.py -k test_the_last_ok_cap_is_the_evening_slot_plus_the_tick_deadline`: `s/^TICK_DEADLINE_SECONDS = 20 \* 60$/TICK_DEADLINE_SECONDS = 25 * 60/`.

  `--file cli/vintage/record.py`, `test_the_witness_pattern_matches_the_line_the_recorder_logs`: the witness INFO given `extra={"probe": 1}`, which `PlainTextFormatter` appends after the message, past the pattern's `$`, the implementer's `sed` reaching that one call; Task 4's `test_the_witness_line_is_the_published_tick_jsons_sha256`, which reads the message alone, stays green under it.

  `--file tests/test_infra_alloy_series.py`, `test_the_journal_keep_regex_names_no_unit_the_role_does_not_install`, control the case's assertion inverted, `s/assert not extra, /assert extra, /` (an emptied test file collects nothing, which `mutate-probe.sh` refuses): the service glob pointed at nothing, `s/glob("\*\.service\.j2")/glob("*.service.j2.absent")/`.

### Task 13: The ops preamble — the directories, the pull key and the key file (D13, D14's ops side, D20's host)

Prerequisite: O2 (the owner's `sync_vintages` commit).

**Files:** Create `infra/ansible/roles/ops/templates/vintage-bgeometrics.token.j2`; modify `infra/ansible/roles/ops/tasks/main.yml`, `infra/ansible/host_vars/zcrypto-ops/vars.yml`, `tests/test_infra_vintage_record_template.py`, `tests/test_infra_converge_guards.py`.

**Interfaces:** Consumes `RECORD_SUBDIR`, `STAGING_SUBDIR` (Task 4) and the defaults (Task 12).

- [ ] **Step 1: The failing tests.** In `tests/test_infra_converge_guards.py`, beside `test_the_rolling_staging_dir_is_the_outboxs_sibling_with_its_owner_group_and_mode`:
  - `test_the_vintage_directories`: one ungated task, `ensure the vintage record, staging and versions-table directories exist`, loops `{{ ops_data_dir }}/{{ ops_vintages_subdir }}` 0755, `…/{{ ops_vintages_subdir }}/record` 0755, `…/{{ ops_vintages_subdir }}/staging` 0750 and `{{ ops_data_dir }}/{{ ops_vintage_versions_subdir }}` 0755, owner and group `{{ ops_data_user }}`; `record` and `staging` are `RECORD_SUBDIR` and `STAGING_SUBDIR`, siblings, neither under the other; the versions root is no descendant of the vintages root.
  - `test_the_vintages_pull_key_serves_record_alone`: `install the vintages pull key (rrsync -ro) on zcrypto-data` beside the other four, its `key` `{{ ops_sync_vintages_authorized_key }}`, `key_options` `command="/usr/bin/rrsync -ro {{ ops_data_dir }}/{{ ops_vintages_subdir }}/record",restrict`, the path's last part `RECORD_SUBDIR`, the task ungated.

  In `tests/test_infra_vintage_record_template.py`:
  - `test_the_key_file_renders_root_only_outside_every_mount`: `render the BGeometrics key file (root-only; never logged, never diffed)` sits in the ungated preamble after `ensure the ops compose project directory exists` and before the first digest-gated block, renders `vintage-bgeometrics.token.j2` to `{{ ops_compose_dir }}/vintage-bgeometrics.token`, root:root, `0600`, `no_log: true`, `diff: false`; rendered with the role defaults, its dest lies under neither `ops_data_dir` nor any rrsync root of the role's `authorized_key` tasks; rendered through `tests/role_render.py`'s `render` (Ansible's templar, the path the role takes, never a bare jinja2 environment, which drops the template's final newline), the template renders `"\n"` alone when `bgeometrics_api_key` is undefined, which the CLI, stripping trailing whitespace, reads as `no credential`, and the value with a trailing newline when it is set.
- [ ] **Step 2: Run them and read them fail.**
- [ ] **Step 3: The three tasks, the template** (`{{ bgeometrics_api_key | default('') }}` and a newline), **and `host_vars/zcrypto-ops/vars.yml`'s** `ops_sync_vintages_authorized_key: "{{ lookup('file', playbook_dir ~ '/files/sync_vintages_ed25519.pub') }}"`, its comment's four NAS pull-channel keys becoming five.
- [ ] **Step 4: The task's run with `tests/test_infra_pull_channel_keys.py`, the gate, commit** `feat(ops): the vintage directories, the vintages pull key and the root-only key file`.
- [ ] **Step 5: Probes,** each KILLED. `--file infra/ansible/roles/ops/tasks/main.yml`:
  - `test_the_vintages_pull_key_serves_record_alone`: `s/{{ ops_vintages_subdir }}\/record",restrict/{{ ops_vintages_subdir }}",restrict/`.
  - `test_the_vintage_directories`: the staging entry's path moved under `record`.
  - `test_the_key_file_renders_root_only_outside_every_mount`: the key file's `mode: "0600"` made `"0644"`.

### Task 14: The dead-man (D12)

**Files:** Modify `tests/fixtures/healthchecks_descriptions.json`, `infra/ansible/host_vars/zcrypto-ops/vars.yml`, `tests/test_infra_hc_role.py`, `tests/test_ops_daily.py`, `tests/test_hc_provision.py`, `infra/scripts/hc-provision.py`; then `infra/runbooks/hc.md`, `infra/runbooks/drills-telemetry.md`.

**Interfaces:** Consumes the anchor (Task 7) and the runner's ping (Task 12).

- [ ] **Step 1: The count commit, one commit:**
  - the fixture's row, after `zcrypto-verify-replay`: `{"name": "zcrypto-vintage-record", "tags": "ops vintage-record", "desc": "<what it means, one line, no internal token> Runbook: infra/runbooks/ops-node.md#zcrypto-ops-vintage-not-recorded", "grace": 21600, "manual_resume": false, "timeout": 90000}`, in the file's key order, the order `hc-provision.py fixture` writes;
  - `ops_vintage_record_healthcheck_url: "{{ hc_ping_base }}/zcrypto-vintage-record"` beside `ops_grafana_watchdog_healthcheck_url`;
  - `OPS_CHECKS` gains `"vintage_record"`, and `test_the_ping_url_variables_are_the_twelve_rows_and_their_slugs_the_fixtures_names_with_zcrypto_hc` becomes `test_the_ping_url_variables_are_the_fixtures_rows_and_their_slugs_its_names_with_zcrypto_hc`, its `== 12` reading `== 13`;
  - `tests/test_ops_daily.py`'s `assert len(checks) == 12, len(checks)` reads 13;
  - `tests/test_hc_provision.py`: `TWELVE` becomes `CHECKS`, `_the_twelve` `_the_checks`, `test_apply_writes_the_eleven_the_fixture_defines_and_the_service_own_check` `test_apply_writes_the_checks_the_fixture_defines_and_the_service_own_check`, `test_a_fixture_fetched_from_the_service_writes_the_same_twelve_again` `test_a_fixture_fetched_from_the_service_writes_the_same_checks_again`, `test_the_committed_fixture_reads_as_the_twelve_definitions_apply_writes` `test_the_committed_fixture_reads_as_the_definitions_apply_writes`, the docstring at its line 224 naming no count, and each `* 12` and `== 12` reading 13;
  - `infra/scripts/hc-provision.py`: `twelve` becomes `checks` and `_twelve` `_checks` with their call sites, and the `apply` help `write every check from the fixture, then read each one back`.
- [ ] **Step 2: The task's run over those paths with `tests/test_infra_hc_role.py`, `tests/test_hc_provision.py` and `tests/test_ops_daily.py`, the gate, commit** `feat(hc): a thirteenth dead-man check, zcrypto-vintage-record`.
- [ ] **Step 3: Load `zcrypto-refine-rules`;** every "twelve" and "12" that counts the checks in `infra/runbooks/hc.md` (lines 118, 122, 144, 217, 251, 270) and `infra/runbooks/drills-telemetry.md` (lines 943 and 971, `200 12`) reads 13, and line 144's checks that stay paused until their next ticks, the two daily replay checks at 03:41 and 05:23 UTC, gain the recorder's, at 07:37 or 19:37 UTC; `WALKERS`, `RATIO`, the gate, commit `docs(runbooks): the dead-man service holds thirteen checks`.
- [ ] **Step 4: Probes,** each KILLED:
  - `--file infra/ansible/host_vars/zcrypto-ops/vars.yml`, `tests/test_infra_hc_role.py -k test_the_ping_url_variables_are_the_fixtures_rows_and_their_slugs_its_names_with_zcrypto_hc`: `/^ops_vintage_record_healthcheck_url:/d`.
  - `--file tests/fixtures/healthchecks_descriptions.json`, `tests/test_ops_daily.py -k test_todays_real_descriptions_all_pass`: `s/ops-node\.md#zcrypto-ops-vintage-not-recorded/ops-node.md#zcrypto-ops-vintage-unrecorded/`.

### Task 15: The NAS custody channel (D14, D15's NAS verify)

Prerequisite: O2.

**Files:** Modify `infra/nas/pull-entrypoint.sh`, `infra/nas/compose.yaml`, `infra/ansible/roles/nas/templates/env.j2`, `infra/ansible/host_vars/nas/vars.yml`, `tests/test_infra_converge_guards.py`, `infra/ansible/files/README.md`, `infra/nas/README.md`, `infra/runbooks/nas.md`.

**Interfaces:** Consumes `zcrypto vintage verify` (Task 5).

- [ ] **Step 1: The failing tests,** in `tests/test_infra_converge_guards.py`, `_entrypoint_block` gaining a keyword `extra_stubs: Mapping[str, str] | None = None`, each written executable beside the `rsync` stub, its return unchanged; the vintages cases pass a `zcrypto` stub that appends its argv as JSON to `$ZCRYPTO_STUB_LOG` and exits `$ZCRYPTO_STUB_RC`, and read that log; `VINTAGES_BLOCK = re.compile(r"^\tif [^\n]*\bVINTAGES_SOURCE\b[^\n]*; then\n.*?^\tfi\n", re.M | re.S)`, env `VINTAGES_DEST=/archive/vintages`, `VINTAGES_SSH_KEY=/keys/sync_vintages`, `VINTAGES_SSH_PORT=22`, `slice=7`:
  - `test_the_vintages_pull_copies_record_over_the_pinned_ssh_and_overwrites_nothing`: options `["--archive", "--ignore-existing", "--chmod=D0775,F0664", "-e"]`, the hot block's transport with `/keys/sync_vintages` and `-p 22`, no `--delete` or `--remove-source-files`.
  - `test_the_vintages_verify_runs_after_the_pull_on_the_loops_slice`: the stub's argv is `vintage verify --root /archive/vintages --custody --newest 4 --slice 7 --slices 24`, after the rsync, and after a failed rsync too.
  - `test_a_failed_vintages_pull_logs_an_error_and_the_loop_goes_on`: rsync rc 23 gives the parse-shaped ERROR `vintages pull failed (source=<source> dest=/archive/vintages), continuing`, exit 0.
  - `test_a_vintages_verify_finding_logs_an_error`: `ZCRYPTO_STUB_RC=1` gives ERROR `vintages verify failed (dest=/archive/vintages), continuing`.
  - `test_an_unset_vintages_source_logs_an_error`, unset and empty: ERROR `vintages channel unwired (VINTAGES_SOURCE unset): custody is not acquiring the recorder's ticks`, no rsync, no verify.
  - `test_the_vintages_source_the_env_renders_reaches_the_pull_through_compose`, as the hc-backup case reads it.
  - `test_every_ssh_transport_the_nas_pull_container_builds_connects_over_ipv4_only`'s walked keys gain `$VINTAGES_SSH_KEY`, its assertion reading `["$HOT_SSH_KEY", "$HC_BACKUP_SSH_KEY", "$VINTAGES_SSH_KEY"]`.
- [ ] **Step 2: Run them and read them fail.**
- [ ] **Step 3: The block** directly after the hot block, the spec's *The archive path to the NAS* block, one tab deeper as every block in the loop is (its `if` at `^\tif`, as `VINTAGES_BLOCK` and the probe ranges read it), its words verbatim, with a comment saying why it is raw and why its unset source is an ERROR; `compose.yaml` gains `VINTAGES_SOURCE: ${VINTAGES_SOURCE:-}`, `VINTAGES_DEST: ${VINTAGES_DEST:-/archive/vintages}`, `VINTAGES_SSH_KEY: /keys/sync_vintages`, `VINTAGES_SSH_PORT: ${VINTAGES_SSH_PORT:-22}`; `env.j2` gains `VINTAGES_SOURCE={{ nas_vintages_source }}` and `VINTAGES_SSH_PORT={{ nas_vintages_ssh_port }}`; `host_vars/nas/vars.yml` gains `nas_vintages_source: "zcrypto-data@z-home-zcrypto.zhaow.pro:"` and `nas_vintages_ssh_port: 22`, each the hot channel's value.
- [ ] **Step 4: The docs.** `infra/ansible/files/README.md`'s key inventory gains `| \`sync_vintages_ed25519.pub\` | NAS + vaulted here | ops vintages pull channel; installed on \`zcrypto-data\` by the ops role |`; `infra/nas/README.md` gains the channel; through `zcrypto-refine-rules`, `infra/runbooks/nas.md`'s table of the loop's ERROR lines (line 133) gains `vintages pull failed (…), continuing` and `vintages verify failed (…), continuing`, its note at line 138 the contrast that `vintages channel unwired` is an ERROR, and the page names `zcrypto vintage verify --root /mnt/zhao-crypto/vintages --custody` as the arrival read, `--custody` as every read of the NAS copy runs it (spec D15), its summary line's `head` and `head_tick_json_sha256` compared by value with the ops record's newest tick, never its exit code alone, and `ops-node.md`'s restore part as the remedy.
- [ ] **Step 5: `WALKERS`, `RATIO`, the task's run with `tests/test_infra_pull_channel_keys.py`, the gate, commit** `feat(nas): the vintages custody channel and its verify`.
- [ ] **Step 6: Probes,** `--file infra/nas/pull-entrypoint.sh`, each KILLED, a range anchored on the block's own `if` line so a comment naming `VINTAGES_SOURCE` above it cannot open the range early:
  - `test_the_vintages_pull_copies_record_over_the_pinned_ssh_and_overwrites_nothing`: `/^\tif \[ -n "\${VINTAGES_SOURCE:-}" \]; then$/,/^\tfi$/s/--archive --ignore-existing --chmod=D0775,F0664/--archive --chmod=D0775,F0664/`.
  - `test_the_vintages_verify_runs_after_the_pull_on_the_loops_slice`: `s/--slices 24; then/--slices 12; then/`.
  - `test_the_vintages_verify_runs_after_the_pull_on_the_loops_slice`: `s/ --custody --newest/ --newest/`, the NAS copy verified as the ops copy is.
  - `test_an_unset_vintages_source_logs_an_error`: `s/log ERROR "vintages channel unwired/log WARNING "vintages channel unwired/`.
  - `test_a_vintages_verify_finding_logs_an_error`: `s/log ERROR "vintages verify failed/log INFO "vintages verify failed/`.
  - `test_a_failed_vintages_pull_logs_an_error_and_the_loop_goes_on`: `s/log ERROR "vintages pull failed/log WARNING "vintages pull failed/`.
  - `test_every_ssh_transport_the_nas_pull_container_builds_connects_over_ipv4_only`, its walk now reaching `$VINTAGES_SSH_KEY`: `/^\tif \[ -n "\${VINTAGES_SOURCE:-}" \]; then$/,/^\tfi$/s/ -o AddressFamily=inet//`.

  `--file infra/nas/compose.yaml`, `test_the_vintages_source_the_env_renders_reaches_the_pull_through_compose`, KILLED: `s/VINTAGES_SOURCE: \${VINTAGES_SOURCE:-}/VINTAGES_SOURCE: ""/`.

  `_entrypoint_block`'s `extra_stubs` keyword is test scaffolding, not a guard of its own: the vintages cases' arms above read the `zcrypto` stub's log it writes, so a stub it failed to write turns their baselines red, and the hot and hc-backup cases, which pass no `extra_stubs`, run unchanged in the task's run.

### Task 16: The post-converge liveness read (Observability)

**Files:** Modify `infra/scripts/ops-postverify.sh`, `tests/test_ops_postverify.py`.

- [ ] **Step 1: The failing test,** `test_the_vintage_recorders_liveness_is_one_series_under_25_hours`, in the file's stubbed-query idiom: the query `time() - max(zcrypto_vintage_last_ok_timestamp_seconds)` answering one series at 1000 passes, at 90000 fails, with no series fails. The new check breaks the file's existing cases unless the stub answers it, since `STUB`'s `case` exits 9 on any query it does not know, so in the same step: `STUB` gains `*vintage_last_ok*) printf '%s\\n' "$VINTAGE_OUT" ;;` before its `*)` branch; `GOOD` gains `"VINTAGE_OUT": "query\n  {} = 1000"`; `test_all_green_passes`' `check_lines(r.stdout, "PASS") == 10` and `test_query_error_is_a_fail`'s `check_lines(r.stdout, "FAIL") == 10` read 11.
- [ ] **Step 2: Run it and read it fail.**
- [ ] **Step 3: One check,** after the tape-bars checks, its comment saying why it reads the maximum and never one source's age, and that the series exists only from the recorder's first tick, so a converge before it reads this check `FAIL … — no series`: `check "vintage recorder liveness (s)" 'time() - max(zcrypto_vintage_last_ok_timestamp_seconds)' under 90000`.
- [ ] **Step 4: The task's run, the gate, commit** `feat(ops): postverify reads the vintage recorder's liveness`.
- [ ] **Step 5: Probe,** `--file infra/scripts/ops-postverify.sh`, `test_the_vintage_recorders_liveness_is_one_series_under_25_hours`, KILLED: `s/max(zcrypto_vintage_last_ok_timestamp_seconds)' under 90000/max(zcrypto_vintage_last_ok_timestamp_seconds)' under 900000/`.

### Task 17: The surrounding docs

**Files:** Modify `infra/runbooks/observability.md`, `infra/runbooks/drills-telemetry.md`, `infra/ops/README.md`, `README.md`, `docs/reference/data-catalog-full.md`, `docs/reference/fleet.md`.

**Interfaces:** Consumes O1's (e), the invalid bearer's outcome.

- [ ] **Step 1: Load `zcrypto-refine-rules`.** `observability.md`: the ops textfile row (line 93) gains `zcrypto-ops-vintage-not-recorded` and the `zcrypto_vintage_*` prefix and counts 21 rules, and its third column, the rules that page instead, gains `zcrypto-ops-vintage-not-recorded` too (its `noDataState` is `Alerting`); the awk command (line 99) gains `vintage` in its `zcrypto_(…)` alternation, and run, it prints 21 uids; the keep-regex sentence (line 233) gains `vintage-record` and `vintage-derive`; the dead-man table gains `zcrypto-vintage-record`'s row. `drills-telemetry.md`: drill C's ops half (line 73) eight pages to nine and its five instant rules (line 77) to six, naming `zcrypto-ops-vintage-not-recorded` (critical); drill K's seven of eight and five NoData rules (line 289) to eight of nine and six, its recovery's five (line 303) to six; drill W1's leg 4 five and six (line 569) to six and seven, its restore's five and nine (line 582) to six and ten.
- [ ] **Step 2: The pages outside `infra/runbooks/`.** `infra/ops/README.md`: the `container` labels gain `zcrypto-vintage-record` and `zcrypto-vintage-derive`; the storage notes gain `vintages/` and `vintage-versions/`, the latter pulled by no channel; four NAS pull channels become five; the secrets item gains `bgeometrics_api_key`, vaulted in `host_vars/zcrypto-ops/vault.yml`, rendered root-only to `{{ ops_compose_dir }}/vintage-bgeometrics.token`, read on the recorder's stdin, and D20's rotation steps; line 25's `coinalyze_api_key` "wired via `vars.yml`" corrected, no line of `host_vars/zcrypto-ops/vars.yml` naming it. `README.md`: a `vintage` section naming `record`, `verify` and `derive`. `docs/reference/fleet.md`: the ops-timers cell gains `vintage-record` within its 200-character cap, and the storage list `vintages/` and `vintage-versions/`.
- [ ] **Step 3: The catalog,** under `## custody` in `docs/reference/data-catalog-full.md`, the spec's *The catalog entry* twice: ``### Free-source vintages (`vintages/`; two ticks a day)`` with every bullet the spec gives, the owner's rulings on open questions 4a and 13 quoted verbatim, and, in the BGeometrics line, what O1's (e) measured: an invalid key served as keyless, a 200 whose body was the keyless body byte for byte, so a revoked key reads ok and pages nothing, the record keeping the free plan's window; then ``### Free-source versions table (`vintage-versions/gen-<N>/` on the ops node; every recorded series' versions, refreshed after every recorder run)`` in tape-bars' entry shape with every bullet the spec gives, its *Generations* line left for the rollout (step 11).
- [ ] **Step 4: `WALKERS`, `RATIO`, the gate, commit** `docs: the vintage record and its versions table in the catalog, the runbooks and the READMEs`.

### Task 18: The rollout skill's line (D17, the owner's ruling on open question 11)

**Files:** Modify `.claude/skills/zcrypto-rollout-image/SKILL.md`.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read its *Before you write guidance*.
- [ ] **Step 2: In *Converge mechanics* (line 104),** the sentence "The ops compose file and the archive-pull, replay, panel and tape-bars runners render only when the run is handed `ops_image_digest`" becomes "The ops compose file and the archive-pull, replay, panel, tape-bars and vintage-record runners render only when the run is handed `ops_image_digest`", the rest of the line as it stands; nothing else in the file changes. The derive runner stays out: it renders only under the digest too, but without `no_log` and with its diff (Task 12's block), so its preview shows its change and the source-diff read the sentence prescribes is not owed for it (spec's change list).
- [ ] **Step 3: `T` over the skill with `tests/test_guidance_guard.py` and `tests/test_guidance_refs_resolve.py`, the gate, commit** `claude(skills): the rollout's digest-rendered ops runners include the vintage recorder`. No check reads the sentence, so the task lists no arm.

### Task 19: The decisions log

**Files:** Modify `docs/research/10.phase4-decisions.md`.

- [ ] **Step 1: Load `iteration-closeout`.** Append, verbatim:

```
[00158] How often does C3's forward recorder tick? (Decision: 1)
  1. **Twice a day, 07:37 and 19:37 UTC** — one failed tick never costs a day, same-day revisions are measured, and each tick lands 23 minutes before an engine cycle.
  2. **Once a day** — half the requests; one transient failure loses the day's snapshot unless someone acts by hand.
  3. **Six ticks, 23 minutes before every cycle, with a light probe** — first-seen at cycle resolution; two cadence classes and a due rule for a precision no pre-registered question asks for yet.
  Human: Cadence (open question 1): "Twice a day (Recommended)" — 07:37 and 19:37 UTC.

[00158] How much of Coin Metrics' free tier does the recorder keep? (Decision: 1)
  1. **Every free daily metric per asset** — about 7 GB a year gzipped per copy; a series not recorded today can never be recorded for today.
  2. **The six C3 metrics plus the BTC and ETH exchange flows** — about a quarter of the bytes; every other series' point-in-time history is lost for good.
  Human: Coin Metrics breadth (2): "Every free metric (Recommended)".

[00158] Where does the record's second copy live? (Decision: 1)
  1. **Its own custody channel** — a key pair, the NAS archive-pull on a `-compat` build carrying the verifier, one NAS converge that replays the gate export cold, and a verify of a twenty-fourth of the copy every loop.
  2. **The `hot-out` outbox** — no NAS change, but a set growing by about 7 GB a year reaches every research node through `data fetch`, sharing the hot pull's failure domain.
  Human: NAS route (3): "Own custody channel (Recommended)".

[00158] Does the recorder keep Coin Metrics' CC BY-NC bodies before Coin Metrics answers in writing? (Decision: 1)
  1. **Record privately now, ask in writing before any C3 trial relies on the record** — every day kept from the first tick; the licence question stands until the answer.
  2. **Wait for written permission** — no licence risk; every Coin Metrics day before the answer, MVRV among them, never recorded.
  Human: Coin Metrics licence, private copies before written permission (4a): "Record now, ask in writing (Recommended)" — store privately from day one and ask Coin Metrics for written permission before any C3 trial relies on the record.

[00158] What do the committed test fixtures hold in a public repository? (Decision: 1)
  1. **Synthesised bodies, Fear & Greed's real body alone** — no vendor value published; a generator and shape files to maintain.
  2. **Fixtures kept out of the tree** — nothing published; CI cannot run the check and derivation tests.
  3. **Written permission first** — real bodies; the plan waits for answers from Coin Metrics and mempool.space.
  Human: Fixtures in the public repository (4b): "Synthesised (Recommended)" — a committed generator, made-up values, only Fear & Greed's real body committed.

[00158] Does the recorder take BGeometrics' SOPR family with a registered key? (Decision: 2)
  1. **Not now** — no account, no secret on the ops node; the SOPR family Coin Metrics' free tier lacks goes unrecorded.
  2. **Register, vault the key, record the four SOPR series** — a keyed source on 15 requests a day, a key that only the owner can rotate, and a revoked key that pages critical.
  Human: BGeometrics (5): "Yes, I'll register" — AGAINST the recommendation: the owner creates the account, the key goes in the vault, the recorder gains a keyed source and a secret on the ops node. Then, on its entry condition (12): "BGeometrics token is stored in .tmp/bgeometrics-api-token, the file contains nothing but the token with a newline at the end, no quote or bracket or any other separator, please delete the file after vaulting"

[00158] How loudly does a source not recorded for 25 hours page? (Decision: 2)
  1. **A warning at 25 h** — the file's severity for a loss of freshness; the same re-notify every 4 h.
  2. **Critical at 25 h** — the file's severity for a loss nothing repairs, since no later tick records the day; a provider outage pages red, about six messages a day until the silence after triage.
  3. **13 h** — pages on every failed tick the next one heals.
  Human: Paging (6): "Critical at 25 h" — AGAINST the recommendation (a warning): the same 25-hour condition at critical severity.

[00158] Does this change materialise the derived dataset? (Decision: 2)
  1. **The derivation as code and tests now, the dataset left to the first C3 trial spec** — no table to run; the trial derives what it reads.
  2. **The dataset now too** — the derivation runs on ops and is cataloged in this change, before any trial cites it.
  Human: Reader scope (8): "Dataset now too" — AGAINST the recommendation: this change also materialises and catalogs the derived dataset.

[00158] What form does the derived dataset take? (Decision: 2)
  1. **Frozen sets minted by hand at a named tick** — each immutable, the first at the rollout; current only when someone mints one.
  2. **A table on the ops node refreshed after every recorder run** — append-only per-tick parts and write-once heads, any head pinned by its hash and rebuilt from either copy of the record.
  Human: The derived dataset's form: "Refreshed every run" — AGAINST the recommendation (frozen sets minted by hand): a table on the ops node updated after each run.

[00158] Do BGeometrics' series enter the derived dataset before BGeometrics answers in writing? (Decision: 2)
  1. **Recorded privately, kept out of the derived dataset until a written answer** — no derivative work; C3 waits for the SOPR family.
  2. **Record and derive** — in the table from its first run, for private research use, the derivative-works risk accepted; one `provider` key leaves them out.
  Human: BGeometrics' terms and the derived dataset: "Record and derive" — AGAINST the recommendation: store privately and also include BGeometrics in the derived dataset now, accepting the derivative-works risk for private research use.
```

- [ ] **Step 2: `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py`, the gate, commit** `docs(research): the vintage recorder's rulings on cadence, breadth, custody, licences, the keyed source, paging and the derived dataset`.

## Outside the implementer's tasks

**Before the plan review's lenses, the coordinator (O1).** O1 landed after the plan review's pin and before its lenses, so the source claims the pin could not check without the recorded bytes (the spec's measured basis, line 49, and D19) are graded by the review's next read, from those bytes and `real-bodies.json`, this plan's record of them; Task 1 follows the review. From this host, sequentially, at least 1 s apart per host, `Accept-Encoding: identity`, a user agent naming no person, never printing a body or a header: the 14 keyless URLs exactly as Task 2 pins them, the four `bg-*` URLs keyless, then one `/v1/sopr` carrying `Authorization: Bearer <a made-up value of the key's shape, which no account issued>`, five of the day's 15 BGeometrics requests. Each body goes to the main checkout's `.local/vintage-bodies/<source id>.<ext>` (`bg-sopr-invalid-bearer.json` for the last), its status line and headers to `<file>.headers`. Then, in one commit on the branch, `test(vintage): Fear & Greed's real body and the shapes of the synthesised fixtures`: `tests/fixtures/vintage/fng.json` (the real body whole) and its provenance, the seven shape files in Task 1's schema, each `real` block the recorded body's URL, fetch time, sha256 and size, and `tests/fixtures/vintage/real-bodies.json`, every recorded body's file name, source, URL, fetch time, status, sha256 and size: the plan's record of the bytes the pin re-reads. It reads back, before the plan is committed for its review, and a difference amends the named line of this plan, the bytes winning, each amendment named under *Spec deviations*: (a) the catalog's ten daily lists against Task 2's `ASSET_METRICS` (equal at the plan session's 14:51:41Z read); (b) every `cm-<asset>` body's pinned metrics outside `avaxc` and `avaxp` whose newest day is older than the fetch date − 3 against `DOT_STOPPED` and `ETH_STOPPED`; (c) each `avaxc` and `avaxp` metric's newest day against date − 1, and whether the source-level date − 1 bound survives their tail days, which one read at one fetch time cannot show: each day's `AssetEODCompletionTime` lag past D+1 00:00Z over the last 90 days of the two bodies (the spec measured avaxc's p90 at 179 h). The early fill that bound rests on, `PriceUSD` arriving ahead of the network metrics, was measured on `btc` alone, and a completed row cannot show when it first appeared; so unless the bodies' newest row shows `PriceUSD` ahead of the network metrics at the fetch, a lag past 19 h 37 min on any of those days means neither tick of the next date holds the row, the bound grades the day 2 and pages at 25 h, the fault the spec's own date − 30 rule exists to avoid ("Their known completion lag would page as a fault"), and Task 2 takes the Labs source-level bound its pinned lines name, `LABS_NEWEST_DAYS = LABS_FRESHNESS_DAYS`; otherwise Task 2 stands; (d) each bg body's first-row keys against `sopr`, `asopr`, `sthSopr` and `lthSopr`, and its newest `d` against the fetch date − 7 under the date − 9 bound; (e) the invalid bearer's status, and whether its body is the keyless window, which Task 17's catalog line states.

**Before Task 13, the owner (O2).** Generate the `sync_vintages` pair and commit both halves in one commit: `infra/ansible/files/sync_vintages_ed25519.pub` and the ansible-vault-encrypted `infra/ansible/files/sync_vintages_ed25519`. It reads back as `tests/test_infra_pull_channel_keys.py` green on that commit.

**At the branch's end, the coordinator.** Each entry of *Spec deviations*, written into the branch ledger the `review` reads and into the PR body, so the review weighs it against the approved spec; the `pre-review` and `review` over `develop..HEAD`; the read before push is a Fable read, or an Opus read with `Fable floor substituted by Opus: <reason>` directly below `Read before push by:`, since Task 18 touches `.claude/`; `open-pr`, whose Step 4 writes the change-index row; `merge-pr`.

**After merge, in the spec's deployment order,** the owner's hand from merged `develop`, outside published Kraken maintenance windows, the feed `https://status.kraken.com/api/v2/scheduled-maintenances.json` read whole at planning time and again immediately before each converge, `converge.sh` never wrapped in `timeout`, each converge's deploy-log line committed as it ends on the pins branch cut from `develop` before step 4. Step 1's vault half is done (`a0f4962c0`); its key pair half is O2, which lands on the branch before Task 13.
2. The owner: the capture image builds, default and `-compat`, from the `develop` push; pre-pull the default digest on `zcrypto-ops` (`zcrypto-rollout-image`, *Ops converges*); on the NAS, pull the `-compat` digest and prove its runtime by running polars in it. Reads back: both digests, polars' answer in the `-compat` image.
3. The owner, only if `docs/reference/fleet-pins.md` does not record the running ops digest: a pull request recording it, through `open-pr` and `merge-pr`. Reads back: the row on `develop`.
4. The owner: the ops `--tags alloy` converge with `ops_alloy_digest`, carrying the keep-regex (`zcrypto-bump-alloy` Step 2, ops alone). Reads back: the converge's `rc` 0 and its deploy-log line committed.
5. The owner: provision the thirteenth check with `infra/scripts/hc-provision.py apply`. Reads back: `hc-provision.py status` naming `zcrypto-vintage-record`.
6. The owner: the ops converge with the new `ops_image_digest` and `-e liquidations_decision=roll-after`, just after a timer slot, its preview's source diff read from the newest deploy-log row carrying that digest (Task 18's sentence). Reads back: `systemctl list-timers zcrypto-vintage-record.timer` showing its next slot and no run; `systemctl status zcrypto-vintage-derive.service` inactive, never started; `infra/scripts/ops-postverify.sh`, which the rollout skill runs after this converge, every check PASS but `FAIL vintage recorder liveness (s) — no series (an empty query is not a zero)`, the one FAIL expected before step 9's tick writes the series, read by value and named as expected in the step's record, any other FAIL a stop; the deploy-log line committed.
7. The owner: roll the liquidations poller inside its 30 h window, `docker compose -f /etc/zcrypto-ops/compose.yaml up -d`, and read the container's `.Config.Image` by value against the new digest.
8. The owner: place the private key on the NAS at `keys/sync_vintages` (0600, 1000:1000); move `nas_capture_image` to the `-compat` digest in the working tree and run `--limit nas --tags nas -e nas_apply_compose=true` with it uncommitted, its window sized from `fleet-pins.md`'s Standing constraints and the recreate's pages announced; commit the pin, its archive-pull row and the deploy-log line together. Reads back: one loop past the vintages block with no `vintages` ERROR on the empty `record/`.
9. The owner: the attended first tick, `sudo systemctl start zcrypto-vintage-record.service`. Reads back by value: the journal, `vintage.prom` with every source's `zcrypto_vintage_outcome`, `zcrypto vintage verify --root /var/lib/zcrypto-ops/vintages/record` exiting 0, every `bg-*` outcome and the `X-RateLimit-*` headers its `tick.json` stored (a `bg-*` outcome 1 is fixed before step 12; `malformed credential` means the vaulted value is off the key's shape); then the derive's `vintage derive complete generation=1 head=<the first tick> …` line and `vintage-derive.prom`'s head time equal to the first tick's stamp.
10. The coordinator, from the workstation after the next NAS loop: `uv run zcrypto vintage verify --root /mnt/zhao-crypto/vintages --custody`. Reads back: exit 0, and its summary line's `head` and `head_tick_json_sha256` equal by value to the first tick's stamp and the witness step 9's journal logged; `head=none` means the loop has not carried the tick yet.
11. The coordinator: `uv run zcrypto vintage derive --record /mnt/zhao-crypto/vintages --table .tmp/vintage-rebuild` into that empty root with no `--textfile`; the first tick's `head.json` sha256 there and in `/var/lib/zcrypto-ops/vintage-versions/gen-1/heads/` compared by value; the scratch root removed by `chmod -R u+w .tmp/vintage-rebuild` and then `rm -rf .tmp/vintage-rebuild`, each its own call, since its generation, part and head directories are 0555; the first tick's date written into the vintages heading and the first generation line (generation 1, its first head and sha256, no entry) into the catalog, for the pins pull request.
12. The owner: the push of the rule and the dashboard from `develop` through `zcrypto-grafana-push`. Reads back: its Step 1 preflight, `time() - zcrypto_vintage_last_ok_timestamp_seconds` on ops, eighteen series each under 90000 (a source at about 1.79e9 waits for its good tick, or the push goes ahead with that page announced and the runbook's silence set; `(no series)` holds the push), and its Step 3 first sample by value, recorded in the pins pull request's `## Grafana push` section.
13. The owner: `infra/scripts/ops-postverify.sh`, `ALL PASS` with the vintage liveness line; the ops row in `fleet-pins.md` re-trued from step 6's deploy-log line; the pins pull request, holding steps 4, 6 and 8's commits, step 11's catalog lines and this row, through `open-pr` and `merge-pr`.
