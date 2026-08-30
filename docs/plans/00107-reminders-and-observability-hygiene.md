# Reminders, log levels, and the descriptions no test can reach — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The daily pass computes reminder due-ness itself from the register and the healable counter and checks the ten dead-man descriptions it already fetches; the three reconnect-replay drop lines in the capture writer log at INFO; the belief that hid the lost reminder is corrected where it lives.

**Architecture:** `infra/scripts/ops_daily.py` gains a sixth read, `read_reminders()` (pure repo file + one PromQL query through the existing `_proxy_query`), and a pure `check_descriptions()` that `read_deadmen()` runs over the checks it fetched. Both surface through the existing `Report` (markdown, journal paragraph, exit code). `cli/capture/segment_writer.py` changes three `logger.warning` calls to `logger.info` with one comment naming the counter that replaces them. The runbook sections and the skill say the report is the trigger and Slack the convenience.

**Tech Stack:** Python 3.14 via `uv run`; `urllib.request` (no new dependency); pytest with `caplog`, `monkeypatch`, `tmp_path`; `infra/scripts/mutate-probe.sh` for guard proofs; Markdown under mdformat.

**Spec:** `docs/specs/00107-reminders-and-observability-hygiene-design.md`

## Global Constraints

- **The exit-code contract of `ops_daily.py` holds**: 0 all-clear, 1 attention, 2 a source it could not read; 2 outranks 1. A reminder that is **owed** reports and never blocks (spec D2: "It reports; it does not block") — it leaves the exit code alone. A reminder source the pass **could not read** (no dated register row, the counter query failed or returned no series) is `unreadable` → exit 2, the module's own contract ("a source that cannot be reached is a finding ABOUT that source, never a silent gap"). A **description finding** (spec D5) leaves the exit code alone too — it is a report line and a journal paragraph clause, never attention: the check cannot repair, so an escalation would never clear until a human logged into healthchecks.io, and every day's journal entry would read `attention` until they did. Its VISIBILITY in both surfaces is the whole guarantee and is what the tests pin. A description source the pass could not READ (healthchecks.io unreachable, the runbooks unreadable) is `unreadable` → exit 2 as above — never blurred with the finding.
- **The instrument stays pure-HTTP** (spec D3): no `ssh`, no ledger read. The healable reminder answers only "did `zcrypto_reconcile_healable_gap_seconds_total` increase in the window"; the count of qualifying days stays the runbook's own step 1, from the ledger.
- **Every guard is proven on a fixture where defect and correct behaviour differ, then mutation-probed** through `infra/scripts/mutate-probe.sh` on a clean tree after its commit (`agent-ops.md`). Verify `--collect-only` selects the intended tests before trusting any verdict.
- **No string literal in `infra/scripts/*.py` may carry `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>`, `WP<N>`, or a `D<n>` decision number** — `tests/test_internal_terms_not_operator_visible.py` scans every non-docstring literal there. Regex source like `r"\bT\d{4}\b"` does not match (no four digits follow the `T`); report text like `"internal token {token!r}"` is a runtime value. Token-carrying fixtures live in `tests/`, which is not scanned. Comments and docstrings may cite `spec 00107`, `T0103`.
- **Test prose never writes a bare plan-task number** (`tests/test_code_prose_citations.py`): say "spec 00107 D4", never "Task 1".
- **Secrets never reach stdout, argv or a file**: the Grafana token and the healthchecks key live in locals and request headers. The description fixture (Task 6) is written from `name`/`tags`/`desc` only — never the whole check object.
- **Stage by explicit path, one commit-type per commit** (`commit-messages.md`); `.claude/` edits are a separate `claude(...)` commit from every other kind. Every commit carries `Co-Authored-By: <the actual authoring model> <noreply@anthropic.com>`; every commit is reviewed by a different agent before push and gets `Reviewed-by:` amended in the turn the review returns. **Task 1 touches the capture write path, so its review floor is Fable** (`spec-plan-locations.md`).
- **Host-touching and vault-touching steps run in the main loop** (`agent-ops.md`): the live pass runs and the healable-counter probe (Task 0, Task 8) and the description fetch (Task 6 Step 4) are main-loop steps, never inside a dispatched subagent. Nothing in this plan touches a fleet host.
- **Markdown: one line per paragraph/bullet**; run `uv run pre-commit run -a` until clean before every commit that touches `.md`, re-staging what mdformat rewrote.
- **`docs/memo.local.md` is gitignored and never committed**; its edit (Task 7 Step 6) is a working-file edit, not a commit.

______________________________________________________________________

### Task 0: The before reading — the live pass's exit code on the unchanged code

**Files:** none modified.

**Interfaces:**
- Produces: the pre-change exit code and report, saved as `.tmp/pass-before.md` (gitignored, and a repo path so a later task's shell finds it), quoted in Task 8's closeout entry; and the two live healable-counter values Step 2 reads, which the reminder's first live run must agree with.

- [ ] **Step 1: Run the pass on the branch's starting code (main loop — it reads the vault)**

```bash
SCRATCH="$(git rev-parse --show-toplevel)/.tmp"; mkdir -p "$SCRATCH"; echo "$SCRATCH"
git log --oneline -1
uv run python infra/scripts/ops-daily.py report --since 24h > "$SCRATCH/pass-before.md"; echo "rc=$?" | tee -a "$SCRATCH/pass-before.md"
tail -3 "$SCRATCH/pass-before.md"
```

`.tmp/` is gitignored (`.gitignore:3`) and it is a repo path, not a shell session's: the later task that quotes this baseline runs in a different shell and re-derives the same directory from the same line. Expected: `rc=0`, `rc=1` or `rc=2` printed **immediately after the pipeline's own command** (the `echo` reads `$?` of the redirect, which is the script's); the report's `## Logs` section is what Task 1 changes and its `## Dead-men` section shows `- direct: 10 checks read`. If the vault is locked (the report reads `the vault could not be read`), unlock the GPG agent and re-run — an exit-2-for-the-vault baseline says nothing about the fleet.

- [ ] **Step 2: Prove the two healable queries answer, before an empty result is wired to exit 2 (main loop — it reads the vault)**

```bash
uv run python infra/scripts/grafana-query.py \
  'sum(increase(zcrypto_reconcile_healable_gap_seconds_total[24h]))' \
  'sum(resets(zcrypto_reconcile_healable_gap_seconds_total[24h]))'
```

Expected: **two results, each exactly one series carrying a numeric value** — read the values, not the exit code. `read_reminders` treats an empty vector from either as a source it could not read, which is a **permanent daily exit 2**; the alert rule over this same counter wraps it `or on() vector(0)` precisely because that shape is possible. An empty answer here is therefore a finding to resolve before the counter is wired up — the query is wrong, or the series is absent — never something to discover from tomorrow's report. Record both values: `resets` is expected `0`, and the `increase` value is what the first live run's `## Reminders` line should agree with.

______________________________________________________________________

### Task 1: The three reconnect-replay drops log at INFO (spec D4)

**Files:**
- Modify: `cli/capture/segment_writer.py` — three `logger.warning` calls, named by symbol, not by line: the `dropping late event` drop in `append`, and the `dropping replayed event` drop in each of `_admit` and `_hold`. Step 3 quotes each replacement block; **the `key = event[self._dedup_key]` assignment that precedes both replay sites is NOT part of either block** — replacing it away is a `NameError` on every dedup-keyed writer.
- Modify: `tests/test_capture_segment_writer.py` (append three tests at the end; change `caplog.at_level(logging.WARNING)` at line 1988 to `logging.INFO`)
- Modify: `tests/test_liquidations_coinalyze.py:558` and `:572` (`caplog.at_level(logging.WARNING)` → `logging.INFO`), and `:549-551` (the test's name and its comment, Step 4)
- Modify: `cli/liquidations/coinalyze.py:16-17` (the last two lines of the module docstring's overlap-safety invariant, Step 4)

**Interfaces:**
- Consumes: `_new_writer`, `_new_trade_writer`, `_oracle_writer`, `_book_event`, `_trade_event`, `_ts`, `HourOracle`, `TRADE_SCHEMA`, the autouse `clock` fixture — all already in `tests/test_capture_segment_writer.py`.
- Produces: the three sites at `logger.info`; the log message strings are unchanged (`dropping late event pair=…`, `dropping replayed event pair=…`).

- [ ] **Step 1: Write the three failing tests**

Append at the end of `tests/test_capture_segment_writer.py`:

```python
# --- spec 00107 D4: the reconnect-replay drops are INFO, and the reconnect counter is the signal ----


def _drop_levels(caplog, prefix: str) -> list[int]:
    """The level of every record whose message starts with `prefix`, as a LIST: a site that stopped
    logging (no record) must fail exactly like one that logs at the wrong level."""
    return [r.levelno for r in caplog.records if r.getMessage().startswith(prefix)]


def test_a_late_event_behind_a_committed_hour_is_dropped_at_info(tmp_path, caplog):
    # A reconnect's replay is expected, not a fault: the scraped `zcrypto_capture_reconnects_total`
    # is the instrument for how often it happens, and the daily pass's WARNING read carries findings only.
    w = _new_writer(tmp_path, flush_rows=5000)
    w.append(_book_event(10, 0))
    assert w.finalize_completed_hours(_ts(11, 0)) == 1
    with caplog.at_level(logging.INFO, logger="zcrypto.capture.segment_writer"):
        w.append(_book_event(10, 30, checksum=999))
    assert _drop_levels(caplog, "dropping late event") == [logging.INFO]


def test_a_replay_into_the_open_hour_is_dropped_at_info(tmp_path, caplog):
    w = _new_trade_writer(tmp_path, flush_rows=50)
    w.append(_trade_event(10, 0, 1))
    with caplog.at_level(logging.INFO, logger="zcrypto.capture.segment_writer"):
        w.append(_trade_event(10, 0, 1))
    w.close()
    assert _drop_levels(caplog, "dropping replayed event") == [logging.INFO]


def test_a_replay_into_a_held_hour_is_dropped_at_info(tmp_path, clock, caplog):
    # The third site: the hold path runs its own de-dup while the hour is still unconfirmed.
    clock.now = _ts(10, 0, 30)
    w = _oracle_writer(tmp_path, HourOracle(), kind="trades", schema=TRADE_SCHEMA, flush_rows=50, dedup_key="trade_id")
    w.append(_trade_event(10, 0, 0))
    with caplog.at_level(logging.INFO, logger="zcrypto.capture.segment_writer"):
        w.append(_trade_event(10, 0, 0))
    w.close()
    assert _drop_levels(caplog, "dropping replayed event") == [logging.INFO]
```

- [ ] **Step 2: Run them and see all three fail on the level**

Run: `uv run pytest tests/test_capture_segment_writer.py -q -k "dropped_at_info" 2>&1 | tail -8`
Expected: 3 failed, each with `assert [30] == [20]` — the record exists and is WARNING. A `[] == [20]` failure means the fixture did not reach the site: fix the fixture before touching the writer.

- [ ] **Step 3: Change the three sites and write the comment once**

In `cli/capture/segment_writer.py`, each block below REPLACES exactly the lines it reproduces — find them by their text, never by a line count. The late-event site in `append` (its three-line comment plus the `logger.warning("dropping late event…` call; the `return` below it is untouched) becomes:

```python
            # An hour that is already closed — a `<HH>.parquet` for it is on disk. A reconnect's
            # trade snapshot replays prints from before the boundary (T0026); writing them beside a
            # committed final would either duplicate rows it already holds or strand them.
            # INFO, not WARNING: the expected consequence of a normal reconnect, not a fault. The
            # instrument for "how often does this happen" is the scraped
            # `zcrypto_capture_reconnects_total`, never a count of these lines — do not raise it
            # back (spec 00107 D4).
            logger.info("dropping late event pair=%s kind=%s ts=%s floor=%s", self._pair, self._kind, ts, floor)
```

The `_admit` site — the three lines `if key in self._seen:` / its `logger.warning` / `return`, leaving the `key = event[self._dedup_key]` above them exactly as it is — becomes:

```python
            if key in self._seen:
                # INFO for the reason at the late-event drop in `append`: the reconnect counter is the signal.
                logger.info("dropping replayed event pair=%s kind=%s %s=%s", self._pair, self._kind, self._dedup_key, key)
                return
```

The `_hold` site — the same three lines, opening `if key in seen:` (no `self.`), with its own `key = event[self._dedup_key]` above them likewise untouched — becomes:

```python
            if key in seen:
                # INFO for the reason at the late-event drop in `append`: the reconnect counter is the signal.
                logger.info("dropping replayed event pair=%s kind=%s %s=%s", self._pair, self._kind, self._dedup_key, key)
                return
```

`dropping implausible event` (line 354) and `first stamp opened a past hour` (line 497) stay WARNING — they are not reconnect replay and the spec names three sites.

- [ ] **Step 4: Re-level the three existing captures that would now miss the line**

`caplog.at_level(logging.WARNING)` sets the root level, and the `zcrypto.*` loggers inherit it, so an INFO record is not captured at all — `test_restart_reseeds_dedup_keys_from_open_hour_parts` (`tests/test_capture_segment_writer.py:1988`, asserts the line IS present) would go red, and the two in `tests/test_liquidations_coinalyze.py` (`:558` asserts absence, `:572` asserts presence) would be respectively vacuous and red. Change all three to `caplog.at_level(logging.INFO)`.

Then the prose those three sites leave false (`code-prose.md`'s rot test — a claim about a level that no longer exists):

- `cli/liquidations/coinalyze.py` lines 16–17 end the overlap-safety invariant with a `dropping replayed event` **warning** that still fires being a genuine anomaly, not steady-state noise. The claim stays true, but the level word is now wrong **and** the liquidations writers are the consumer spec 00107 D4 names as losing its only automated surface — so the sentence gains the guard it now rests on rather than being left as an invariant nobody checks. Replace those two lines with:

```python
the floor logic must preserve all of this -- and a `dropping replayed event` line that still
fires is now a genuine anomaly, not steady-state noise. What holds that claim is
`tests/test_liquidations_coinalyze.py::test_poll_cycle_second_cycle_is_silent_no_dedup_drops`,
which runs in CI on every PR. In production the line logs at INFO (spec 00107 D4, for the
capture writer's reconnect bursts), so it reaches no alert rule and no daily-pass log read: a
runtime-only watermark regression is read from raw INFO logs, and costs no data, because the
writer's dedup and its late-event floor still hold behind the watermark.
```

- `tests/test_liquidations_coinalyze.py:549` — rename `test_poll_cycle_second_cycle_is_silent_no_dedup_warnings` to `test_poll_cycle_second_cycle_is_silent_no_dedup_drops`, and re-word its comment (`:550-551`) from `trigger ZERO writer-level "dropping replayed event" warnings` to `trigger ZERO writer-level "dropping replayed event" drops`. The assertion (`"dropping replayed event" not in caplog.text`) is unchanged and, at INFO capture, now means what its name says. **Do this rename before the docstring edit above**, which cites the new name.

Verify the docstring with `sed -n '8,24p' cli/liquidations/coinalyze.py` — the paragraph must still read as one invariant, the cited test name must match the renamed test exactly, and no other `warning` in the paragraph may have changed.

`docs/plans/00055-liquidations-poller-watermark.md` quotes the old test name; it is a point-in-time record of that iteration and is deliberately left.

Two more prose sites this level change falsifies are **not** touched here — `docs/open-topics/T0037-…` (live, argues from the drop being a bare WARNING) and `.claude/skills/zcrypto-rollout-image/SKILL.md` (calls those lines resubscribe replay). Both are doc-kind edits and land in Task 7, Steps 5 and 7, so this commit stays code-and-tests. Do not edit them from here.

- [ ] **Step 5: Run the reachable suites**

Run: `uv run pytest tests/test_capture_segment_writer.py tests/test_liquidations_coinalyze.py -q 2>&1 | tail -3`
Expected: all passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add cli/capture/segment_writer.py cli/liquidations/coinalyze.py tests/test_capture_segment_writer.py tests/test_liquidations_coinalyze.py
git commit -m "fix(capture): the three reconnect-replay drops log at INFO -- the reconnect counter is the signal"
```

Body: the measured basis (two bursts in 24 h matching `increase(zcrypto_capture_reconnects_total[24h])` = 2 and 1 one-for-one; resubscribes, desyncs 0; gap counter 0), and that the capture log-dead rules select `level=~".+"` and the error rules `ERROR|CRITICAL`, so nothing depended on WARNING.

- [ ] **Step 7: Mutation-probe all three sites (tree must be clean)**

```bash
uv run pytest tests/test_capture_segment_writer.py --collect-only -q -k dropped_at_info 2>&1 | tail -4
```

Expected: exactly 3 tests collected. The probe command is a shell ARRAY, expanded as `"${PROBE[@]}"` — `mutate-probe.sh` runs its arguments as `"$@"`, and the session shell is zsh, where an unquoted scalar `$PROBE` stays ONE word and the baseline fails with rc 7 before anything is mutated:

```bash
PROBE=(uv run pytest tests/test_capture_segment_writer.py -q -p no:cacheprovider -k dropped_at_info)
infra/scripts/mutate-probe.sh --file cli/capture/segment_writer.py \
  --control 's/logger.info("dropping late event/logger.debug("dropping late event/' \
  --mutation 's/logger.info("dropping late event/logger.warning("dropping late event/' -- "${PROBE[@]}"
grep -n 'logger.info("dropping replayed event' cli/capture/segment_writer.py
```

Expected: `mutate-probe: KILLED (control proven, tree restored byte-identically)`. The grep prints the two replay sites; both carry the identical call, so each mutation must be ADDRESSED to one line — `A` in `_admit`, `B` in `_hold`. Assign them from the grep, never by hand, and check them before use: an empty `A` makes `sed` apply `s/logger.info/logger.warning/` to EVERY line, flipping all three sites at once, and `mutate-probe` still prints KILLED — one joint proof recorded as two per-site proofs, with the SURVIVED diagnostic below unable to ever fire.

```bash
A=$(grep -n 'logger.info("dropping replayed event' cli/capture/segment_writer.py | sed -n 1p | cut -d: -f1)
B=$(grep -n 'logger.info("dropping replayed event' cli/capture/segment_writer.py | sed -n 2p | cut -d: -f1)
echo "A=$A B=$B"   # two distinct bare integers, A < B — anything else, stop and re-read the grep
infra/scripts/mutate-probe.sh --file cli/capture/segment_writer.py \
  --control 's/logger.info("dropping late event/logger.debug("dropping late event/' \
  --mutation "${A}s/logger.info/logger.warning/" -- "${PROBE[@]}"
infra/scripts/mutate-probe.sh --file cli/capture/segment_writer.py \
  --control 's/logger.info("dropping late event/logger.debug("dropping late event/' \
  --mutation "${B}s/logger.info/logger.warning/" -- "${PROBE[@]}"
```

Expected: `KILLED` both times. A `SURVIVED` on either replay site means the two `dropping replayed event` tests reached the same site — re-read Step 1's held-hour fixture (the clock must be inside the hour's first five minutes so the row is HELD). Record the three verdicts for Task 8's entry.

______________________________________________________________________

### Task 2: The register's last re-confirmation row (spec D3, refdata half)

**Files:**
- Modify: `infra/scripts/ops_daily.py` — imports at lines 9–21; new constants and functions after `DEPLOY_LOG` (line 189)
- Modify: `tests/test_ops_daily.py` — imports at lines 12–24; new tests appended at the end

**Interfaces:**
- Produces: `REGISTER: Path` (the committed `docs/reference/kraken-snapshot-register.md`), `last_sweep_date(register: Path) -> date | None`, `_a_month_after(d: date) -> date`. Task 3 consumes all three.

- [ ] **Step 1: Write the failing tests**

Add `from datetime import date, datetime, timedelta, timezone` (replacing the existing datetime import line) and `import urllib.parse` beside `import urllib.error` at the top of `tests/test_ops_daily.py`. Append at the end:

```python
# --- spec 00107 D3: the reminders are read from the source that actually knows ------------------------------


def _register(tmp_path, *rows, decoy=True):
    """A register whose re-confirmation log holds `rows` (first-cell, fetched-at) -- plus, by default,
    a dated table AFTER the next heading, so a parser that ignores section boundaries reads 2099."""
    text = [
        "# Kraken reference-data snapshot register",
        "",
        "## Provenance",
        "",
        "| Sweep | Fetched at (UTC) |",
        "| -- | -- |",
        "| not a sweep row | 2000-01-01T00:00:00+00:00 |",
        "",
        "## Re-confirmation log",
        "",
        "Prose before the table, with a date in it: 2031-01-01.",
        "",
        "| Sweep | Fetched at (UTC) | Full response |",
        "| -- | -- | -- |",
        *[f"| {first} | {fetched} | 1429 pairs / 824 assets |" for first, fetched in rows],
        "",
    ]
    if decoy:
        text += ["## Deferred: account-gated facts", "", "| #9 (decoy) | 2099-01-01T00:00:00+00:00 | x |", ""]
    path = tmp_path / "register.md"
    path.write_text("\n".join(text))
    return path


def test_the_last_sweep_date_is_read_from_the_real_register_not_a_fixture_shaped_to_the_parser():
    """The parse must find the committed file's latest row. Row #0 is 2026-07-07 and row #1 is
    2026-08-04, so `>=` the latter proves the LAST row was read, and the bound never rots as sweeps
    append. The second assertion re-derives the answer independently of the parser."""
    found = ops_daily.last_sweep_date(ops_daily.REGISTER)
    assert found is not None and found >= date(2026, 8, 4), found
    rows = [line for line in ops_daily.REGISTER.read_text().splitlines() if line.startswith("| #")]
    assert found.isoformat() in rows[-1], (found, rows[-1])


def test_the_last_row_of_the_log_wins_and_tables_outside_it_are_ignored(tmp_path):
    register = _register(
        tmp_path, ("#0 (Phase 0, iter-002)", "2026-07-07T03:29:00+00:00"), ("#1 (monthly, 2026-08-04)", "2026-08-04T10:40:09+00:00")
    )
    assert ops_daily.last_sweep_date(register) == date(2026, 8, 4)


def test_a_log_with_no_dated_row_reads_as_none_never_as_a_date_from_elsewhere(tmp_path):
    assert ops_daily.last_sweep_date(_register(tmp_path)) is None
    assert ops_daily.last_sweep_date(_register(tmp_path, decoy=False)) is None


@pytest.mark.parametrize(
    "last,expected",
    [
        (date(2026, 8, 4), date(2026, 9, 4)),
        (date(2026, 12, 4), date(2027, 1, 4)),
        (date(2026, 1, 31), date(2026, 2, 28)),
    ],
)
def test_the_monthly_cadence_is_a_calendar_month_with_the_day_clamped(last, expected):
    """The sweep reminders were armed a calendar month apart (2026-08-04 -> 2026-09-04), not 30 days."""
    assert ops_daily._a_month_after(last) == expected
```

- [ ] **Step 2: Run them and see them fail on the missing names**

Run: `uv run pytest tests/test_ops_daily.py -q -k "last_sweep_date or last_row_of_the_log or no_dated_row or monthly_cadence" 2>&1 | tail -6`
Expected: 6 failed (the parametrized test is three), each `AttributeError: module 'ops_daily' has no attribute 'REGISTER'` / `'last_sweep_date'` / `'_a_month_after'`.

- [ ] **Step 3: Implement**

In `infra/scripts/ops_daily.py`, add `import calendar` to the imports (alphabetically, before `import http.client`) and change the datetime import to `from datetime import date, datetime, timedelta, timezone`. After `DEPLOY_LOG = REPO_ROOT / "docs/reference/deploy-log.jsonl"` (line 189) add:

```python
REGISTER = REPO_ROOT / "docs/reference/kraken-snapshot-register.md"
# A row of the register's `## Re-confirmation log` table: first cell `#<n> (...)`, second cell the
# ISO stamp. Only rows under THAT heading count: the register holds other dated tables.
_LOG_ROW = re.compile(r"^\| #\d+[^|]*\|\s*(\d{4}-\d{2}-\d{2})T")


def last_sweep_date(register: Path) -> date | None:
    """The `Fetched at` date of the LAST row under `## Re-confirmation log`, or None when no row parses."""
    found = None
    in_log = False
    for line in register.read_text().splitlines():
        if line.startswith("## "):
            in_log = line.startswith("## Re-confirmation log")
            continue
        row = _LOG_ROW.match(line) if in_log else None
        if row:
            found = date.fromisoformat(row.group(1))
    return found


def _a_month_after(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_ops_daily.py -q 2>&1 | tail -3`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add infra/scripts/ops_daily.py tests/test_ops_daily.py
git commit -m "feat(ops_daily): read the last re-confirmation row of the snapshot register"
```

- [ ] **Step 6: Mutation-probe the cadence guard (tree must be clean)**

`last_sweep_date`'s own mutations live in Task 3 Step 6, where `read_reminders` exists to carry the control. `_a_month_after` has no reader yet, so it is probed here, against its own three fixtures — spec 00107's verification clause is "every guard", and this is the one that would otherwise carry none. The probe is a shell ARRAY, expanded as `"${PROBE[@]}"` (Task 1 Step 7 says why):

```bash
uv run pytest tests/test_ops_daily.py --collect-only -q -k cadence 2>&1 | tail -3
PROBE=(uv run pytest tests/test_ops_daily.py -q -p no:cacheprovider -k cadence)
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def _a_month_after(/def _a_month_afterz(/' \
  --mutation 's/(d.year + 1, 1)/(d.year, 1)/' -- "${PROBE[@]}"
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def _a_month_after(/def _a_month_afterz(/' \
  --mutation 's/min(d.day,/max(d.day,/' -- "${PROBE[@]}"
```

Expected: exactly 3 tests collected — the one parametrization; no other test name in the file carries `cadence` **at this point in the branch**. Task 3 adds `test_the_refdata_reminder_is_computed_from_the_register_and_the_monthly_cadence`, so a re-run of this proof on the final tree collects 6 and stays KILLED (that test reads `_a_month_after` too). Then `KILLED` twice. The first drops the December year rollover, so the Dec→Jan fixture answers `2026-01-04` where it must answer `2027-01-04` — a wrong VALUE, the shape the guard exists to catch. The second drops the day clamp, so the Jan-31 fixture asks for `2026-02-31` and `date()` raises; a raise is a fail and a fail is a kill, and it proves that fixture reaches the clamp at all. Record both verdicts.

______________________________________________________________________

### Task 3: `read_reminders()` — the sixth read (spec D1, D2, D3)

**Files:**
- Modify: `infra/scripts/ops_daily.py` — new dataclasses and `read_reminders` after `_a_month_after` (added in Task 2)
- Modify: `tests/test_ops_daily.py` — new tests appended; the transport-failure loop at lines 952–956; the endpoint-pinning test at lines 1073–1096

**Interfaces:**
- Consumes: `REGISTER`, `last_sweep_date`, `_a_month_after` (Task 2); `_proxy_query`, `PROM_DS_UID`, `_UNREACHABLE` (existing).
- Produces:

```python
@dataclass(frozen=True)
class Reminder:
    name: str      # "refdata sweep" | "healable re-derivation"
    status: str    # "due in 5 days (last sweep 2026-08-04)" | "OVERDUE by 6 days (…)" | "counter moved ~+88.4 s in 24 h (scraped, extrapolated …), recount the qualifying days" | "counter unchanged in 24 h" | "counter reset in 24 h (a ledger correction or rebuild) …"
    owed: bool     # True when the runbook section is work now
    runbook: str   # "infra/runbooks/reference-data.md#refdata-sweep-due" | "infra/runbooks/ops.md#healable-threshold-rederivation-due"

@dataclass
class RemindersRead:
    reminders: list[Reminder] = field(default_factory=list)
    unreadable: str | None = None

def read_reminders(token: str, *, now: datetime, window: timedelta, opener=urllib.request.urlopen, register: Path = REGISTER) -> RemindersRead
```

Task 4 consumes `RemindersRead` and `read_reminders`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ops_daily.py`:

```python
def _counter(value):
    return {"data": {"result": [{"metric": {}, "value": [1, str(value)]}]}}


_TWO_SWEEPS = (("#0 (Phase 0, iter-002)", "2026-07-07T03:29:00+00:00"), ("#1 (monthly, 2026-08-04)", "2026-08-04T10:40:09+00:00"))


def _reminder(read, name):
    (found,) = [r for r in read.reminders if r.name == name]
    return found


@pytest.mark.parametrize(
    "now,status,owed",
    [
        (datetime(2026, 8, 30, 3, 0, tzinfo=timezone.utc), "due in 5 days", False),
        (datetime(2026, 9, 4, 3, 0, tzinfo=timezone.utc), "due in 0 days", True),
        (datetime(2026, 9, 10, 3, 0, tzinfo=timezone.utc), "OVERDUE by 6 days", True),
    ],
)
def test_the_refdata_reminder_is_computed_from_the_register_and_the_monthly_cadence(tmp_path, now, status, owed):
    """A lost Slack message costs nothing: due-ness is derived from repo state every day."""
    read = ops_daily.read_reminders("tok", now=now, window=DAY, opener=_canned(_counter(0)), register=_register(tmp_path, *_TWO_SWEEPS))
    refdata = _reminder(read, "refdata sweep")
    assert refdata.status.startswith(status), refdata.status
    assert "2026-08-04" in refdata.status, refdata.status
    assert refdata.owed is owed
    assert refdata.runbook == "infra/runbooks/reference-data.md#refdata-sweep-due"
    assert read.unreadable is None


def test_a_register_with_no_dated_row_is_an_unreadable_source_never_not_due(tmp_path):
    read = ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=_canned(_counter(0)), register=_register(tmp_path))
    assert read.unreadable and "Re-confirmation log" in read.unreadable, read.unreadable
    assert not [r for r in read.reminders if r.name == "refdata sweep"]


@pytest.mark.parametrize("value,owed,word", [("88.4", True, "moved ~+88.4 s"), ("0", False, "unchanged")])
def test_the_healable_reminder_fires_only_when_the_counter_moved(tmp_path, value, owed, word):
    """The trigger discriminates: a counter that did not move owes nothing, one that did names the
    recount. The count itself stays the runbook's step 1, from the ledger -- Cloud cannot see it.
    Two payloads: the increase, then `resets` (0 -- no reset in the window)."""
    read = ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=_canned(_counter(value), _counter(0)), register=_register(tmp_path, *_TWO_SWEEPS))
    healable = _reminder(read, "healable re-derivation")
    assert healable.owed is owed
    assert word in healable.status, healable.status
    assert healable.runbook == "infra/runbooks/ops.md#healable-threshold-rederivation-due"


def test_the_healable_reminder_names_a_counter_reset_and_never_quotes_it_as_movement(tmp_path):
    """The counter is re-emitted from the ledger's totals every cycle, so a ledger correction or
    rebuild that lowers the total is a reset, and `increase()` then reports the whole post-reset
    value as movement -- the hazard the `zcrypto-reconcile-healable-gap-rate` rule guards with
    `resets()`. The reminder names the reset and owes the ledger recount; the false number never
    reaches the report."""
    read = ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=_canned(_counter("18850.2"), _counter(1)), register=_register(tmp_path, *_TWO_SWEEPS))
    healable = _reminder(read, "healable re-derivation")
    assert healable.owed is True
    assert "reset" in healable.status and "18850" not in healable.status, healable.status


def test_a_healable_counter_with_no_series_is_unreadable_never_quiet(tmp_path):
    read = ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=_canned({"data": {"result": []}}), register=_register(tmp_path, *_TWO_SWEEPS))
    assert read.unreadable and "no series" in read.unreadable, read.unreadable
    assert not [r for r in read.reminders if r.name == "healable re-derivation"]
    assert _reminder(read, "refdata sweep")  # the half that could be read still is


def test_the_real_register_yields_a_refdata_reminder():
    """Against the committed file, with the counter canned: the pass's own default path parses.

    No `tmp_path`, deliberately -- this test's entire value is that it omits `register=`, so the
    committed `REGISTER` default is what gets exercised. A fixture parameter here is an invitation to
    pass `register=_register(tmp_path, ...)` for consistency with its neighbours, which would delete
    the only coverage of the path `main` actually takes."""
    read = ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=_canned(_counter(0)))
    assert read.unreadable is None, read.unreadable
    assert {r.name for r in read.reminders} == {"refdata sweep", "healable re-derivation"}


def test_every_runbook_citation_the_instrument_itself_prints_resolves():
    """Closed in KIND, not by instance: `REFDATA_RUNBOOK` and `HEALABLE_RUNBOOK` reach the operator's
    report verbatim, and the repo's cross-reference guards scan `alerts.yaml`, `infra/grafana/*.json`
    and `infra/runbooks/*.md` -- none of them scans `infra/scripts/`. Spec 00107 D6 rewrites both of
    the sections cited here: a rename would turn the runbook-internal guard red and get it re-pointed
    at the new anchor while this module's copy rotted silently, sending a paged operator to a fragment
    that scrolls nowhere. Scanning the source keeps a citation added later covered by nobody's memory.
    """
    cited = set(re.findall(r"infra/runbooks/([A-Za-z0-9._-]+\.md)#([A-Za-z0-9_-]+)", _SCRIPT.read_text()))
    assert cited, "no runbook citation found in the instrument -- this guard has gone vacuous, not clean"
    anchors = {f"{p.name}#{a}" for p in _RUNBOOKS.glob("*.md") for a in re.findall(r'<a name="([^"]+)"></a>', p.read_text())}
    assert {f"{f}#{a}" for f, a in cited} <= anchors, sorted({f"{f}#{a}" for f, a in cited} - anchors)
```

`re`, `_SCRIPT` (the path `ops_daily` was loaded from, not a second spelling of it) and `_RUNBOOKS` are already at the top of `tests/test_ops_daily.py` (lines 17, 26, 375) — do not re-import or re-declare any of them.

Then edit two existing tests:

In `test_a_transport_failure_is_an_unreadable_source_not_a_crash` (line 944), add the reminders read to the loop:

```python
    for read, kwargs in (
        (ops_daily.read_logs, {"window": DAY}),
        (ops_daily.read_alerts, {"now": NOW, "window": DAY}),
        (ops_daily.read_deadmen, {}),
        (ops_daily.read_reminders, {"now": NOW, "window": DAY}),
    ):
```

In `test_every_endpoint_the_instrument_builds_is_pinned` (line 1073), change the docstring's "the module builds six" to "the module builds eight" (the reminders read is two queries) and append before the function's end:

```python
    reminders = _recording(_counter(0))
    ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=reminders)
    assert len(reminders.urls) == 2 and all("/uid/%s/api/v1/query" % ops_daily.PROM_DS_UID in u for u in reminders.urls), reminders.urls
    assert "sum(increase(zcrypto_reconcile_healable_gap_seconds_total[24h]))" in urllib.parse.unquote(reminders.urls[0]), reminders.urls
    assert "sum(resets(zcrypto_reconcile_healable_gap_seconds_total[24h]))" in urllib.parse.unquote(reminders.urls[1]), reminders.urls
```

The `sum(` is pinned, not decoration: every fixture returns exactly one series, so `series[0]` behaves identically with or without the aggregation and nothing else in the suite would notice its loss. If the counter ever gains a label (a second reconciler instance, a per-pair split), an unaggregated read reports one label's movement as the whole and takes `resets` off a different series than `increase` — a wrong OWED/ok answer on the daily instrument.

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_ops_daily.py -q -k "reminder or healable or no_dated_row or transport_failure or endpoint or citation" 2>&1 | tail -6`
Expected: every test above and the two edited ones fail with `AttributeError: module 'ops_daily' has no attribute 'read_reminders'` — except the citation guard, which fails on its own message (`no runbook citation found in the instrument`), the module carrying no runbook citation until Step 3 adds the two constants. Task 2's `test_a_log_with_no_dated_row…` is selected too and still passes.

- [ ] **Step 3: Implement**

After `_a_month_after` in `infra/scripts/ops_daily.py`:

```python
HEALABLE_COUNTER = "zcrypto_reconcile_healable_gap_seconds_total"
REFDATA_RUNBOOK = "infra/runbooks/reference-data.md#refdata-sweep-due"
HEALABLE_RUNBOOK = "infra/runbooks/ops.md#healable-threshold-rederivation-due"


@dataclass(frozen=True)
class Reminder:
    name: str
    status: str
    owed: bool
    runbook: str


@dataclass
class RemindersRead:
    reminders: list[Reminder] = field(default_factory=list)
    unreadable: str | None = None


def read_reminders(
    token: str, *, now: datetime, window: timedelta, opener=urllib.request.urlopen, register: Path = REGISTER
) -> RemindersRead:
    """Due-ness computed from state the pass can read, so a Slack reminder that never arrives costs
    nothing (spec 00107 D1). Each reminder comes from the source that actually knows: the sweep from
    the register's last re-confirmation row plus the monthly cadence; the healable re-derivation from
    whether its counter moved in the window -- the qualifying-day COUNT is the runbook's own step 1,
    from the ledger, which Grafana Cloud cannot see and this pure-HTTP instrument does not reach.

    An owed reminder reports and never blocks; a source that could not be read is `unreadable`, like
    every other read here.
    """
    read = RemindersRead()

    def note(text):
        read.unreadable = f"{read.unreadable}; {text}" if read.unreadable else text

    try:
        last = last_sweep_date(register)
    except _UNREACHABLE as exc:
        note(f"the snapshot register could not be read: {exc}")
    else:
        if last is None:
            note(f"no dated row under `## Re-confirmation log` in {register.name}")
        else:
            days = (_a_month_after(last) - now.date()).days
            status = f"due in {days} days" if days >= 0 else f"OVERDUE by {-days} days"
            read.reminders.append(Reminder("refdata sweep", f"{status} (last sweep {last.isoformat()})", owed=days <= 0, runbook=REFDATA_RUNBOOK))

    hours = max(1, int(window.total_seconds() // 3600))
    try:
        series = _proxy_query(PROM_DS_UID, f"sum(increase({HEALABLE_COUNTER}[{hours}h]))", token, opener)
        resets = _proxy_query(PROM_DS_UID, f"sum(resets({HEALABLE_COUNTER}[{hours}h]))", token, opener)
        if not series or not resets:
            note("the healable counter returned no series, so the re-derivation reminder could not be evaluated")
            return read
        moved = float(series[0]["value"][1])
        reset = float(resets[0]["value"][1]) > 0
    except _UNREACHABLE as exc:
        note(f"the healable counter could not be read: {exc}")
        return read
    if reset:
        # The counter is re-emitted from the ledger's totals every cycle (`cli/archive/command.py`),
        # so a ledger correction or rebuild that lowers the total is a reset, and `increase()` then
        # reports the whole post-reset value as movement. The `zcrypto-reconcile-healable-gap-rate`
        # rule guards the same window with `resets()` (T0044); this mirrors it, and the number is
        # deliberately not quoted -- the ledger's own count is the arbiter.
        owed = True
        status = f"counter reset in {hours} h (a ledger correction or rebuild), so its movement says nothing -- recount the qualifying days from the ledger"
    else:
        owed = moved > 0
        # `increase()` extrapolates to the range boundaries, so this figure is NOT the ledger's
        # delta -- and the ledger is the arbiter the runbook's step 1 names, precisely because Cloud
        # cannot answer the question. Quote it as the approximation it is (spec 00107 D3).
        status = (
            f"counter moved ~+{moved:.1f} s in {hours} h (scraped, extrapolated -- not the ledger's), recount the qualifying days"
            if owed
            else f"counter unchanged in {hours} h"
        )
    read.reminders.append(Reminder("healable re-derivation", status, owed=owed, runbook=HEALABLE_RUNBOOK))
    return read
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_ops_daily.py -q 2>&1 | tail -3`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add infra/scripts/ops_daily.py tests/test_ops_daily.py
git commit -m "feat(ops_daily): read_reminders -- due-ness from the register row and the healable counter"
```

- [ ] **Step 6: Mutation-probe the two triggers and the row selection (clean tree)**

```bash
uv run pytest tests/test_ops_daily.py --collect-only -q -k "reminder or sweep_date or last_row or no_dated_row or healable" 2>&1 | tail -3
```

Expected: exactly 12 tests collected — by name: the real-register read (1), last-row-wins (1), no-dated-row (1), the refdata parametrization (3), the register-unreadable case (1), the healable parametrization (2), the reset case (1), the no-series case (1), the real-register-yields-both case (1); the cadence test carries none of the words and no mutation below touches `_a_month_after` — that guard is probed on its own three fixtures in Task 2 Step 6 — and the citation guard carries none of them either; Step 7 probes it against the file it actually reads. The probe is a shell array (Task 1 Step 7 says why), with the control `--control 's/^def read_reminders(/def read_reminderz(/'` on every run:

```bash
PROBE=(uv run pytest tests/test_ops_daily.py -q -p no:cacheprovider -k 'reminder or sweep_date or last_row or no_dated_row or healable')
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def read_reminders(/def read_reminderz(/' \
  --mutation 's/owed = moved > 0/owed = moved >= 0/' -- "${PROBE[@]}"
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def read_reminders(/def read_reminderz(/' \
  --mutation 's/reset = float(resets\[0\]\["value"\]\[1\]) > 0/reset = False/' -- "${PROBE[@]}"
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def read_reminders(/def read_reminderz(/' \
  --mutation 's/found = date\.fromisoformat/found = found or date.fromisoformat/' -- "${PROBE[@]}"
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def read_reminders(/def read_reminderz(/' \
  --mutation 's/in_log = line.startswith("## Re-confirmation log")/in_log = True/' -- "${PROBE[@]}"
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def read_reminders(/def read_reminderz(/' \
  --mutation 's/owed=days <= 0/owed=days < 0/' -- "${PROBE[@]}"
```

Expected: `KILLED` five times — always-firing healable trigger, a reset read as movement (the `18850` fixture then reaches the status), first-row-wins, section-blind parse (the 2099 decoy), and due-today-not-owed each trip a test. Record the verdicts.

- [ ] **Step 7: Mutation-probe the citation guard against the RUNBOOK, not the module (clean tree)**

The defect this guard names is a runbook anchor renamed out from under the constant, so the mutated file is the runbook. Mutating the constant instead proves nothing about this guard: the two literal `assert refdata.runbook == …` pins in Step 1 kill that mutation on their own.

```bash
uv run pytest tests/test_ops_daily.py --collect-only -q -k citation 2>&1 | tail -3
PROBE=(uv run pytest tests/test_ops_daily.py -q -p no:cacheprovider -k citation)
infra/scripts/mutate-probe.sh --file infra/runbooks/reference-data.md \
  --control 's|<a name=|<a nameX=|' \
  --mutation 's|<a name="refdata-sweep-due"></a>|<a name="refdata-sweep-due-renamed"></a>|' -- "${PROBE[@]}"
```

Expected: exactly 1 test collected, then `KILLED` — the control (every anchor in that file unharvestable) proves the probe reads the runbooks at all, and the mutation is the rename itself. Record the verdict.

______________________________________________________________________

### Task 4: The report carries the reminders (spec D2)

**Files:**
- Modify: `infra/scripts/ops_daily.py` — the `Report` dataclass (its fields, `unreadable`, `markdown`, `journal_paragraph`), `build_report`, and the `build_report(` call inside `main`. Symbols, not line numbers: the two tasks before this one insert ~100 lines above `Report`, so any coordinate written here is stale by the time this task runs. Every edit below is content-anchored — find it by the text quoted, never by counting.
- Modify: `tests/test_ops_daily.py` — `_report` (247–256), the clause test (287–290), the four direct `build_report(...)` calls (lines 971, 986, 1116, 1130), new tests appended

**Interfaces:**
- Consumes: `RemindersRead`, `read_reminders` (Task 3).
- Produces: `Report.reminders: RemindersRead` (a required field after `deploys`); `build_report(*, alerts, logs, deadmen, verdict, deploys, reminders, now, window=…)`; a `## Reminders` section in `markdown()`; a `reminders …` clause in `journal_paragraph()`.

- [ ] **Step 1: Write the failing tests**

Change the `_report` helper's base dict to include `reminders=ops_daily.RemindersRead(),` after `deploys=[]`. Add `reminders=ops_daily.RemindersRead(),` after `deploys=[],` in each of the four direct `build_report(` calls (`test_a_verdict_read_that_could_not_be_read_exits_2_not_1`, `test_a_healthy_but_empty_verdict_is_not_an_unreadable_source`, `test_the_journal_paragraph_carries_warnings_when_there_are_any`, `test_the_journal_paragraph_stays_quiet_when_nothing_warned`). In `test_the_journal_paragraph_carries_every_labelled_clause`, add `"reminders"` to the clause tuple between `"deploys"` and `"actions"`. Append:

```python
def test_an_owed_reminder_reports_and_never_blocks():
    """Spec 00107 D2: the reminder is a finding in the report, not an exit code -- a calendar date
    passing is not a fleet defect. It reaches the markdown AND the journal paragraph, because the
    paragraph is what gets pasted."""
    owed = ops_daily.RemindersRead(
        reminders=[
            ops_daily.Reminder("refdata sweep", "OVERDUE by 6 days (last sweep 2026-08-04)", owed=True, runbook="infra/runbooks/reference-data.md#refdata-sweep-due"),
            ops_daily.Reminder("healable re-derivation", "counter unchanged in 24 h", owed=False, runbook="infra/runbooks/ops.md#healable-threshold-rederivation-due"),
        ]
    )
    r = _report(reminders=owed)
    assert r.exit_code == 0, r.exit_code
    md = r.markdown()
    assert "## Reminders" in md and "OWED refdata sweep: OVERDUE by 6 days" in md and "#refdata-sweep-due" in md, md
    assert "ok healable re-derivation: counter unchanged" in md, md
    para = r.journal_paragraph()
    assert "reminders OWED refdata sweep: OVERDUE by 6 days" in para, para
    assert "OWED healable" not in para, para  # the marker discriminates; it is not decoration


def test_an_unreadable_reminder_source_exits_2_like_every_other_source():
    r = _report(reminders=ops_daily.RemindersRead(unreadable="the healable counter could not be read: timed out"))
    assert r.exit_code == 2 and "healable counter could not be read" in r.markdown()


def test_the_report_refuses_to_be_built_without_a_reminders_read():
    """A default that reads as 'nothing due' is the silent gap this iteration closes; the field is required."""
    with pytest.raises(TypeError):
        ops_daily.build_report(alerts=ops_daily.AlertsRead(), logs=ops_daily.LogsRead(), deadmen=ops_daily.DeadmenRead(), verdict=[], deploys=[], now=NOW)
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_ops_daily.py -q 2>&1 | tail -8`
Expected: every `build_report(` call now fails with `TypeError: build_report() got an unexpected keyword argument 'reminders'` — the clause test among them, and on that same `TypeError`, not on `missing clause: reminders`: Step 1 put `reminders=` into `_report`'s base dict, so `_report()` raises before the loop it added the clause to ever runs. The required-field test fails with `DID NOT RAISE TypeError`, today's `build_report` accepting the call it must refuse.

- [ ] **Step 3: Implement**

In `Report` add the field `reminders: RemindersRead` after `deploys: list[dict]`. In `unreadable`, extend the docstring's list ("-- the verdict checks included" → "-- the verdict checks and the reminders included") and the `named` comprehension to `(self.alerts.unreadable, self.logs.unreadable, self.deadmen.unreadable, self.reminders.unreadable)`. In `markdown()`, after the `## Dead-men` block and before `## Deploys in window`:

```python
        out += ["", "## Reminders"] + (
            [f"- {'OWED' if r.owed else 'ok'} {r.name}: {r.status} — {r.runbook}" for r in self.reminders.reminders] or ["- none read"]
        )
```

In `journal_paragraph()`, add before `deploys = ...`:

```python
        # The OWED marker travels with the clause. The paragraph is the artefact that gets pasted
        # into the journal, and `refdata sweep: due in 0 days` -- the owed-today spelling -- skims
        # as "not yet" without it, where the markdown's own line is unambiguous.
        reminders = ", ".join(f"{'OWED ' if r.owed else ''}{r.name}: {r.status}" for r in self.reminders.reminders) or "none read"
```

and in the returned f-string insert `f"reminders {reminders} · "` between the `deploys {deploys} · ` clause and `actions none`. `build_report` becomes:

```python
def build_report(*, alerts, logs, deadmen, verdict, deploys, reminders, now, window=timedelta(hours=24)) -> Report:
    return Report(now=now, window=window, alerts=alerts, logs=logs, deadmen=deadmen, verdict=verdict, deploys=deploys, reminders=reminders)
```

In `main`, add `reminders=read_reminders(token, now=now, window=window),` after the `deploys=` line of the `build_report(` call.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_ops_daily.py -q 2>&1 | tail -3`
Expected: all passed.

- [ ] **Step 5: Smoke the CLI's own wiring without the network**

```bash
uv run python - <<'EOF'
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("ops_daily", "infra/scripts/ops_daily.py")
m = importlib.util.module_from_spec(spec); sys.modules["ops_daily"] = m; spec.loader.exec_module(m)
from datetime import datetime, timezone
r = m.build_report(alerts=m.AlertsRead(), logs=m.LogsRead(), deadmen=m.DeadmenRead(), verdict=[], deploys=[],
                   reminders=m.read_reminders("tok", now=datetime.now(timezone.utc), window=m.timedelta(hours=24), opener=lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))),
                   now=datetime.now(timezone.utc))
print(r.markdown().split("## Reminders")[1].splitlines()[1:3]); print(r.exit_code)
EOF
```

Expected: the refdata line reads `- ok refdata sweep: due in N days (last sweep 2026-08-04) — …` (or `OWED … OVERDUE …` if run after 2026-09-04) computed from the real register, and exit `2` because the offline counter is an unreadable source.

- [ ] **Step 6: Commit**

```bash
git add infra/scripts/ops_daily.py tests/test_ops_daily.py
git commit -m "feat(ops_daily): the report carries the reminders -- owed reports, unreadable exits 2"
```

- [ ] **Step 7: Mutation-probe the does-NOT-block half (clean tree)**

Spec 00107 D2's second half is asserted here and nowhere else, and the mutation is not a slip — it is the plausible "fix" a later editor makes on seeing an `OWED` line under an all-clear headline.

```bash
uv run pytest tests/test_ops_daily.py --collect-only -q -k "owed_reminder or unreadable_reminder" 2>&1 | tail -3
PROBE=(uv run pytest tests/test_ops_daily.py -q -p no:cacheprovider -k 'owed_reminder or unreadable_reminder')
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's|if self.unreadable:|if False:|' \
  --mutation 's|if self.alerts.firing_now or|if any(r.owed for r in self.reminders.reminders) or self.alerts.firing_now or|' -- "${PROBE[@]}"
```

Expected: exactly 2 tests collected (`test_an_owed_reminder_reports_and_never_blocks`, `test_an_unreadable_reminder_source_exits_2_like_every_other_source` — no other name in the file carries either phrase), then `KILLED`: the control drops exit 2 and the unreadable test bites it; the mutation turns an owed reminder into attention and the `r.exit_code == 0` assertion bites that. Record the verdict.

**This sed keeps matching for the rest of the branch**: no later task edits `exit_code`, whose attention condition stays the one line `if self.alerts.firing_now or [c for c in self.verdict if not c.ok] or (self.deadmen.via_prometheus or 0) > 0:` (spec 00107 D5 rules the description finding out of it). So the recorded proof re-runs verbatim on the final tree. Should a future change break the line up, `mutate-probe.sh` exits **6** (`no-op sed proves nothing`) rather than reporting a false verdict — re-address the mutation to the rewritten line, never treat the 6 as a pass.

______________________________________________________________________

### Task 5: `check_descriptions()` — a resolving runbook link and no internal token (spec D5)

**Files:**
- Modify: `infra/scripts/ops_daily.py` — new constants and one function, placed by Step 3
- Modify: `tests/test_ops_daily.py` — new tests appended

**Interfaces:**
- Consumes: `_RUNBOOK_LINK` (line 42), `REPO_ROOT` (line 188).
- Produces: `RUNBOOKS: Path`, `check_descriptions(checks: list[dict], runbooks: Path = RUNBOOKS) -> list[str]` — one finding per defect, each starting with the check's name in backticks. Task 6 consumes it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ops_daily.py`:

```python
# --- spec 00107 D5: the dead-man descriptions are checked, not generated ---------------------------------------

_CLEAN_DESC = "Pings on a clean overlay-writer cycle. Runbook: infra/runbooks/ops-node.md#zcrypto-ops-archive-pull-stalled"


def test_a_description_carrying_an_internal_token_is_a_finding_named_per_check():
    """The surface `operator-facing-text.md` governs, read from a phone with nothing open -- and the
    one surface no repo test reaches, because the descriptions are hand-written in a SaaS. The three
    that pre-existed 2026-08-30 carried exactly these tokens."""
    checks = [
        {"name": "zcrypto-engine-shadow", "desc": "Phase-6 shadow engine, spec 00050. Runbook: infra/runbooks/engine.md#zcrypto-engine-cycle-stale"},
        {"name": "zcrypto-gate-verify", "desc": "Gate export, see T0083 and iter-120. Runbook: infra/runbooks/gate.md#zcrypto-gate-exporter-stale"},
        {"name": "clean", "desc": _CLEAN_DESC},
    ]
    findings = ops_daily.check_descriptions(checks)
    engine = [f for f in findings if f.startswith("`zcrypto-engine-shadow`")]
    assert {t for f in engine for t in ("Phase-6", "spec 00050") if repr(t) in f} == {"Phase-6", "spec 00050"}, findings
    gate = [f for f in findings if f.startswith("`zcrypto-gate-verify`")]
    assert {t for f in gate for t in ("T0083", "iter-120") if repr(t) in f} == {"T0083", "iter-120"}, findings
    assert not [f for f in findings if f.startswith("`clean`")], findings
    assert len(findings) == 4, findings


def test_a_missing_or_dangling_runbook_link_is_a_finding():
    """A link resolves against the FILE it names: an anchor living in a sibling file scrolls nowhere.
    And the literal `Runbook: ` prefix is half of what spec 00107 D5 asks for -- a path mentioned in
    passing is not the link an operator follows from a phone.

    `passing-mention-first` is the pair the other fixtures cannot make: a RESOLVING mention ahead of
    a DEAD link, so a check that searches the whole description finds the mention, passes, and sends
    the operator to the fragment that scrolls nowhere. It is the link the prefix introduces that is
    judged."""
    checks = [
        {"name": "dangling", "desc": "Runbook: infra/runbooks/ops.md#no-such-anchor"},
        {"name": "wrong-file", "desc": "Runbook: infra/runbooks/capture.md#zcrypto-ops-archive-pull-stalled"},
        {"name": "linkless", "desc": "Pings every minute."},
        {"name": "prefixless", "desc": "Context in infra/runbooks/ops-node.md#zcrypto-ops-archive-pull-stalled, no link."},
        {
            "name": "passing-mention-first",
            "desc": "Context in infra/runbooks/ops-node.md#zcrypto-ops-archive-pull-stalled. Runbook: infra/runbooks/ops.md#no-such-anchor",
        },
        {"name": "clean", "desc": _CLEAN_DESC},
    ]
    findings = ops_daily.check_descriptions(checks)
    expected = ["`dangling`", "`linkless`", "`passing-mention-first`", "`prefixless`", "`wrong-file`"]
    assert sorted(f.split(":")[0] for f in findings) == expected, findings


def test_a_check_with_no_description_at_all_is_a_finding_not_a_pass():
    assert ops_daily.check_descriptions([{"name": "bare"}]) == ["`bare`: no `Runbook: infra/runbooks/<file>#<anchor>` in its description"]
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_ops_daily.py -q -k "description or runbook_link" 2>&1 | tail -5`
Expected: 3 failed, 1 passed — the three new ones fail with `AttributeError: module 'ops_daily' has no attribute 'check_descriptions'`, and the passing one is the pre-existing `test_the_rules_read_pairs_every_firing_instance_with_its_runbook_link`, which the same word matches. (`-k` matches names only; the dangling-link test carries `runbook_link`, not `description`.)

- [ ] **Step 3: Implement**

After `read_reminders` (the last of Task 3's additions) in `infra/scripts/ops_daily.py` — it needs only `_RUNBOOK_LINK` and `REPO_ROOT`, both defined far above:

```python
RUNBOOKS = REPO_ROOT / "infra/runbooks"
# Spec 00107 D5 asks for the LINK, not a path in passing -- and for THE link the prefix introduces.
# Searching `_RUNBOOK_LINK` over the whole description would judge whichever path comes first, so a
# passing mention that happens to resolve passes a description whose real link is dead. Composed
# from `_RUNBOOK_LINK` rather than respelled, so the two cannot drift apart.
_RUNBOOK_PREFIX = "Runbook: "
_RUNBOOK_CITED = re.compile(re.escape(_RUNBOOK_PREFIX) + _RUNBOOK_LINK.pattern)
# The vocabulary `.claude/rules/operator-facing-text.md` bans from any surface read without the repo
# open. `Phase[ -]` because the live descriptions spelled it `Phase-6`; the optional backtick because
# a serial is as often written `spec `00050``. The bare decision number that rule also bans is
# deliberately absent (spec 00107 D5 says why): this check detects without repairing, so a false
# positive is a finding line in every daily report until a human rewrites a description.
_INTERNAL_TOKEN = re.compile(r"\bPhase[ -]\d|\bT\d{4}\b|\biter-\d+|\bspec\s+`?\d{5}|\bWP\d")


def check_descriptions(checks: list[dict], runbooks: Path = RUNBOOKS) -> list[str]:
    """One line per defect in a dead-man check's description, named per check (spec 00107 D5).

    The descriptions are hand-written in healthchecks.io, outside every repo test, and are read
    from a phone with nothing open. Two assertions each: a `Runbook: infra/runbooks/<file>#<anchor>`
    that resolves against a real `<a name=…>` tag in the file it names, and no internal token.
    Detects, never repairs: with ten checks a human rewrite is proportionate.
    """
    out = []
    for check in checks:
        name = check.get("name") or check.get("slug") or "?"
        desc = check.get("desc") or ""
        link = _RUNBOOK_CITED.search(desc)
        if link is None:
            out.append(f"`{name}`: no `Runbook: infra/runbooks/<file>#<anchor>` in its description")
        else:
            path = runbooks / link.group(1)
            if not path.exists() or f'<a name="{link.group(2)}"></a>' not in path.read_text():
                out.append(f"`{name}`: its runbook link {link.group(0).removeprefix(_RUNBOOK_PREFIX)} resolves to no anchor")
        for token in _INTERNAL_TOKEN.findall(desc):
            out.append(f"`{name}`: its description carries the internal token {token!r}")
    return out
```

- [ ] **Step 4: Run the tests, then the token guard over the new literals**

Run: `uv run pytest tests/test_ops_daily.py tests/test_internal_terms_not_operator_visible.py -q 2>&1 | tail -3`
Expected: all passed — the regex literal carries no four-digit `T`, no digit after `Phase`/`iter-`/`WP`, no five digits after `spec`.

- [ ] **Step 5: Commit**

```bash
git add infra/scripts/ops_daily.py tests/test_ops_daily.py
git commit -m "feat(ops_daily): check_descriptions -- a resolving runbook link and no internal token, per check"
```

______________________________________________________________________

### Task 6: The dead-man read checks the descriptions it fetched, and the true positive (spec D5)

**Files:**
- Modify: `infra/scripts/ops_daily.py` — the `DeadmenRead` dataclass, `read_deadmen`, the `## Dead-men` block of `Report.markdown`, and `Report.journal_paragraph`. **`Report.exit_code` is deliberately NOT touched** (spec 00107 D5's ruling: a description finding is a report line, not an exit code). Symbols, not line numbers: the tasks before this one insert ~100 lines above them all. Every edit below is content-anchored.
- Create: `tests/fixtures/healthchecks_descriptions.json` (name, tags, desc of the ten live checks — nothing else)
- Modify: `tests/test_ops_daily.py` — new tests appended

**Interfaces:**
- Consumes: `check_descriptions` (Task 5).
- Produces: `DeadmenRead.description_findings: list[str] | None` (default `None` — the check did not run; `[]` — it ran and found nothing), set by `read_deadmen` after a successful direct read; findings are listed under `## Dead-men` in the markdown and counted in the journal paragraph when non-zero, and **move no exit code** (spec 00107 D5).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ops_daily.py`:

```python
def test_the_deadmen_read_checks_the_descriptions_it_fetched(monkeypatch):
    monkeypatch.setattr(ops_daily, "_readonly_key", lambda: "hcr_fake")
    prom = {"data": {"result": [{"metric": {}, "value": [1, "0"]}]}}
    direct = {
        "checks": [
            {"name": "zcrypto-engine-shadow", "desc": "T0083 retagged. Runbook: infra/runbooks/engine.md#zcrypto-engine-cycle-stale"},
            {"name": "zcrypto-gate-verify", "desc": _CLEAN_DESC},
        ]
    }
    read = ops_daily.read_deadmen("tok", opener=_canned(prom, direct))
    assert read.unreadable is None
    assert read.description_findings == ["`zcrypto-engine-shadow`: its description carries the internal token 'T0083'"], read.description_findings


def test_a_runbook_read_failure_during_the_descriptions_check_is_named_as_such_not_as_healthchecks(monkeypatch):
    """The check reads runbook files; a failure there is a finding about the RUNBOOKS, and the
    checks it fetched stay read -- never `healthchecks.io could not be read directly`.

    `None` is not `[]`: a check that never ran must not print as one that ran and found nothing.
    Exit 2 and the unreadable line already carry the truth, and a `descriptions: all 1 carry …`
    line beside them says the opposite of what happened."""
    monkeypatch.setattr(ops_daily, "_readonly_key", lambda: "hcr_fake")
    monkeypatch.setattr(ops_daily, "check_descriptions", lambda checks: (_ for _ in ()).throw(OSError("runbooks unreadable")))
    prom = {"data": {"result": [{"metric": {}, "value": [1, "0"]}]}}
    read = ops_daily.read_deadmen("tok", opener=_canned(prom, {"checks": [{"name": "x", "desc": _CLEAN_DESC}]}))
    assert len(read.via_healthchecks) == 1 and read.description_findings is None, read.description_findings
    assert read.unreadable and "runbooks" in read.unreadable and "healthchecks.io" not in read.unreadable, read.unreadable
    markdown = _report(deadmen=read).markdown()
    assert "descriptions: all" not in markdown, markdown


def test_a_description_finding_reaches_the_report_and_the_paragraph_and_never_blocks():
    """Spec 00107 D5: the finding is a report line and a journal clause, never the exit code -- the
    check cannot repair, and a SaaS description no repo change touches would hold the pass at
    `attention` every day until a human logged in, destroying the all-clear entry the journal exists
    to produce. VISIBILITY is therefore the whole guarantee, so both surfaces are pinned here, and so
    is the verdict the operator reads above them."""
    deadmen = ops_daily.DeadmenRead(
        via_prometheus=0.0,
        via_healthchecks=[{"name": "x"}],
        description_findings=["`x`: its description carries the internal token 'T0083'"],
    )
    r = _report(deadmen=deadmen)
    assert r.exit_code == 0, r.exit_code
    md = r.markdown()
    assert "- description: `x`: its description carries the internal token 'T0083'" in md, md
    assert "**Verdict: all-clear** (exit 0)" in md, md
    assert "- descriptions: all" not in md, md  # the finding line and the all-clear line are exclusive
    assert "1 description finding" in r.journal_paragraph(), r.journal_paragraph()


def test_clean_descriptions_say_so_in_the_report_and_stay_out_of_the_paragraph():
    """`description_findings=[]` is the CHECKED-and-clean state, and the only one that may print the
    all-clear line -- the default `None` means the check did not run."""
    r = _report(deadmen=ops_daily.DeadmenRead(via_prometheus=0.0, via_healthchecks=[{"name": "a"}, {"name": "b"}], description_findings=[]))
    assert r.exit_code == 0
    assert "- descriptions: all 2 carry a resolving runbook link and no internal token" in r.markdown(), r.markdown()
    assert "description finding" not in r.journal_paragraph()


def test_todays_ten_real_descriptions_all_pass():
    """The true positive: a check that refuses everything is not a check. `name`/`tags`/`desc` of the
    ten live checks, read 2026-08-30 through the read-only key -- never the whole object, which
    carries the check's write URL. This reads the committed fixture only: rewriting a description in
    healthchecks.io moves nothing here until the fixture is re-fetched (the plan for spec 00107 says
    how), and a red AFTER that re-fetch is the finding the daily pass would have made."""
    checks = json.loads((Path(__file__).resolve().parent / "fixtures" / "healthchecks_descriptions.json").read_text())
    assert len(checks) == 10, len(checks)
    assert ops_daily.check_descriptions(checks) == []
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_ops_daily.py -q -k "descriptions or description_finding" 2>&1 | tail -7`
Expected: 5 failed, in three flavours. The two that CONSTRUCT a `DeadmenRead` with the new kwarg (`…description_finding_reaches…`, `…clean_descriptions_say_so…`) fail on `TypeError: DeadmenRead.__init__() got an unexpected keyword argument 'description_findings'`. The two that read the attribute off a `read_deadmen` result (`…checks_the_descriptions_it_fetched`, `…runbook_read_failure…`) fail on `AttributeError: 'DeadmenRead' object has no attribute 'description_findings'` — the runbook-failure test among them, because nothing calls `check_descriptions` yet, so its raising stub never runs. The fixture test fails with `FileNotFoundError`.

- [ ] **Step 3: Implement**

`DeadmenRead` gains, after `via_healthchecks`:

```python
    # Three states, not two: `None` is "the check did not run" (healthchecks unreadable, or the
    # runbooks were), `[]` is "ran, found nothing". Defaulting to `[]` would print the all-clear
    # description line under a report that never looked.
    description_findings: list[str] | None = None
```

In `read_deadmen`, the healthchecks `try` ends with `note(f"healthchecks.io could not be read directly: {exc}")` — make that except-branch `return read`, and add AFTER the whole try/except, in place of the final `return read`. The check reads runbook FILES, so it gets its own `try` and its own note: inside the healthchecks `try`, an `OSError` from a runbook would be reported as healthchecks.io unreadable.

```python
    try:
        read.description_findings = check_descriptions(read.via_healthchecks)
    # `AttributeError` beside `_UNREACHABLE`: this is the module's first content-dependent parse of
    # the healthchecks payload, and a `checks` element that is not an object would otherwise
    # traceback out at exit 1 -- ATTENTION, the inverted contract this module's docstring names.
    except (*_UNREACHABLE, AttributeError) as exc:
        note(f"the dead-man descriptions could not be checked (the runbooks are read here): {exc}")
    return read
```

**`Report.exit_code` is not edited at all** — spec 00107 D5 rules that a description finding is a report line and a journal clause, never attention, so the attention condition keeps its three terms and the module's `unreadable` → 2 path (which the note above already routes a runbook failure into) is the only exit code this task can move. The instinct on seeing a finding printed under an `all-clear` headline is to escalate it; Step 7's sixth mutation is exactly that instinct, and it must be KILLED.

In `markdown()`, after `f"- direct: {len(self.deadmen.via_healthchecks)} checks read",` inside the dead-men list, close that list and add:

```python
        if self.deadmen.description_findings:
            out += [f"- description: {f}" for f in self.deadmen.description_findings]
        elif self.deadmen.description_findings is not None and self.deadmen.via_healthchecks:
            out.append(f"- descriptions: all {len(self.deadmen.via_healthchecks)} carry a resolving runbook link and no internal token")
```

The `is not None` is the whole point of the three states: without it the all-clear line prints beside `## Sources that could not be read` on a run where the check never ran.

In `journal_paragraph()`, add `findings = len(self.deadmen.description_findings or [])` beside `warnings = ...`, and change the `read directly` clause to:

```python
            f"{len(self.deadmen.via_healthchecks)} read directly{f', {findings} description finding{'s' if findings != 1 else ''}' if findings else ''} · deploys {deploys} · "
```

- [ ] **Step 4: Fetch the ten live descriptions into the fixture (main loop — it reads the vault)**

```bash
uv run python - <<'EOF'
import importlib.util, json, sys, urllib.request
from pathlib import Path
spec = importlib.util.spec_from_file_location("ops_daily", "infra/scripts/ops_daily.py")
m = importlib.util.module_from_spec(spec); sys.modules["ops_daily"] = m; spec.loader.exec_module(m)
key = m._readonly_key()
assert key, "healthchecks_readonly_api_key could not be read from the vault"
req = urllib.request.Request(m.HEALTHCHECKS_API, headers={"X-Api-Key": key})
with urllib.request.urlopen(req, timeout=30) as r:
    checks = json.load(r)["checks"]
# name, tags, desc ONLY: the full object carries the check's write URLs, which are credentials.
out = [{"name": c.get("name"), "tags": c.get("tags"), "desc": c.get("desc")} for c in checks]
Path("tests/fixtures/healthchecks_descriptions.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
print(len(out), "checks;", sum(1 for c in out if "Runbook: infra/runbooks/" in (c["desc"] or "")), "carry the link")
EOF
grep -c '"ping_url"\|hc-ping\|"update_url"\|"pause_url"' tests/fixtures/healthchecks_descriptions.json
```

Expected: `10 checks; 10 carry the link`, and the grep prints `0` — no URL of any kind in the file. The counted prefix is the one `check_descriptions` requires, but the count is the weaker condition: it stops at the prefix where the check goes on to demand a well-formed `<file>.md#<anchor>` that resolves, so `10 carry the link` is a necessary, not a sufficient, agreement — Step 5 is what actually decides. If the count is not 10, or fewer than 10 carry the prefix, that is a live finding to report and Step 5's route applies — never a fixture to edit.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_ops_daily.py -q 2>&1 | tail -3`
Expected: all passed — including `test_todays_ten_real_descriptions_all_pass`.

**All ten are expected to pass — a red here is first a defect in `check_descriptions` or in the fetch, not on the live surface.** The three descriptions that pre-dated 2026-08-30 did carry `Phase-6`, `spec 00050` and `T0083`, and all ten were rewritten that same day: 10 of 10 descriptions written, 10 of 10 runbook targets resolving, 0 carrying an internal token, measured with the admin key and recorded in the memo's Block A ledger (`docs/memo.local.md` — the in-flight authority; grep it before believing anything else about that surface). So read WHICH check and which finding it names, and suspect this code first: a live `Runbook — ` or lower-case `runbook:` that `_RUNBOOK_CITED` misses and reports as *no link at all*; an anchor spelling `_RUNBOOK_LINK`'s character class does not admit; a `_INTERNAL_TOKEN` false positive such as a grace time written `T0300`. Fix the checker where the checker is wrong.

Only when the finding has been **confirmed by eye against the live description** (read it with the read-only key) is it a real defect on the live surface — the daily report will name it under `## Dead-men` every day until a human rewrites that description in healthchecks.io, and it is never a fixture to edit. The route then, with the confirmed check names named in the commit body:

1. Commit the fixture exactly as fetched (Step 6) — it is the evidence of what the surface said that day.
2. Narrow the true positive to the checks that are clean, and pin the offenders so the narrowing cannot silently grow. Narrowing on an *unconfirmed* red is how spec 00107's required true positive gets satisfied by shrinking it: the check goes permanently blind to those names, and the second assertion below does not catch it, because a false positive also produces *some* finding per pinned name.

```python
# Checks whose LIVE description carries a finding, confirmed by eye against the live surface and
# named in the commit body -- each owes a human rewrite in healthchecks.io, which no repo change can
# make. The daily report names them every day until then.
_DESCRIPTIONS_OWED = {"<check name>", ...}


def test_todays_real_descriptions_pass_except_the_ones_owing_a_rewrite():
    """The true positive, narrowed to what is genuinely clean: every description outside
    `_DESCRIPTIONS_OWED` passes, and every name inside it really does produce a finding. `name`/
    `tags`/`desc` of the live checks, read 2026-08-30 through the read-only key -- never the whole
    object, which carries the check's write URL. This reads the committed fixture only: rewriting a
    description in healthchecks.io moves nothing here until the fixture is re-fetched (the plan for
    spec 00107 says how), and a red AFTER that re-fetch is the finding the daily pass would make."""
    checks = json.loads((Path(__file__).resolve().parent / "fixtures" / "healthchecks_descriptions.json").read_text())
    assert len(checks) == 10, len(checks)
    assert ops_daily.check_descriptions([c for c in checks if c["name"] not in _DESCRIPTIONS_OWED]) == []
    owed = ops_daily.check_descriptions([c for c in checks if c["name"] in _DESCRIPTIONS_OWED])
    assert {f.split("`")[1] for f in owed} == _DESCRIPTIONS_OWED, owed   # every finding names its check first
```

The second assertion is what keeps the first honest: a name added to the set without a real finding behind it turns the test red, and a description rewritten in healthchecks.io turns it red too — at which point the name comes out of the set and the true positive widens back.

The rename is not cosmetic: a body asserting that a named subset does **not** pass, under the name `…ten_real_descriptions_all_pass`, is a name and docstring claiming the opposite of their own assertions (`code-prose.md`). The new name still carries `descriptions`, so Step 7's `-k` selection and its collect count are unchanged.

3. Carry the named checks into Task 8's entry as a live finding of this iteration. It needs no separate registration: the report names it in every daily pass until a human rewrites it, which is exactly what spec 00107 D5 bought.

- [ ] **Step 6: Commit**

```bash
git add infra/scripts/ops_daily.py tests/test_ops_daily.py tests/fixtures/healthchecks_descriptions.json
git commit -m "feat(ops_daily): the dead-man read checks the ten descriptions it fetches"
```

- [ ] **Step 7: Mutation-probe both assertions (clean tree)**

```bash
uv run pytest tests/test_ops_daily.py --collect-only -q -k "description or runbook_link" 2>&1 | tail -3
```

Expected: exactly 9 tests collected — the three from Task 5, the five from this task, and the pre-existing `test_the_rules_read_pairs_every_firing_instance_with_its_runbook_link` (`tests/test_ops_daily.py:85`), whose name the word `runbook_link` also matches and which no mutation below moves. `-k` matches NAMES only, and `test_a_missing_or_dangling_runbook_link_is_a_finding` is the one test the anchor mutation below moves (every other fixture's link resolves or is absent), so a filter of `description` alone collects 7 and the second probe SURVIVES for want of a selector, not a guard. The probe is a shell array (Task 1 Step 7 says why):

```bash
PROBE=(uv run pytest tests/test_ops_daily.py -q -p no:cacheprovider -k 'description or runbook_link')
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def check_descriptions(/def check_descriptionz(/' \
  --mutation 's/for token in _INTERNAL_TOKEN.findall(desc):/for token in ():/' -- "${PROBE[@]}"
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def check_descriptions(/def check_descriptionz(/' \
  --mutation 's/not in path.read_text():/not in path.read_text() and False:/' -- "${PROBE[@]}"
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def check_descriptions(/def check_descriptionz(/' \
  --mutation 's/link = _RUNBOOK_CITED.search(desc)/link = _RUNBOOK_LINK.search(desc) if _RUNBOOK_PREFIX in desc else None/' -- "${PROBE[@]}"
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def check_descriptions(/def check_descriptionz(/' \
  --mutation 's/if self.deadmen.description_findings:/if False:/' -- "${PROBE[@]}"
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def check_descriptions(/def check_descriptionz(/' \
  --mutation 's/findings = len(self.deadmen.description_findings or \[\])/findings = 0/' -- "${PROBE[@]}"
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def check_descriptions(/def check_descriptionz(/' \
  --mutation 's|if self.alerts.firing_now or|if self.deadmen.description_findings or self.alerts.firing_now or|' -- "${PROBE[@]}"
```

Expected: `KILLED` six times — a token check that never fires; an anchor check that never fires (the `dangling` fixture: `ops.md` exists, the anchor does not); a link judged by the first path anywhere in the description rather than the one the `Runbook: ` prefix introduces; and then the three that hold spec 00107 D5's ruling, which is now the whole guarantee.

**The last three, since visibility replaced the exit code as what this feature buys.** The fourth mutation suppresses the finding from the markdown — and, because the two branches are exclusive, prints the all-clear description line in its place, the exact silent-gap shape: the finding-line assertion bites. The fifth drops the journal clause while leaving the markdown intact, so the paragraph that actually gets pasted into the journal goes quiet on its own: the `1 description finding` assertion bites, and nothing else moves. The sixth is not a slip but the plausible "fix" — escalating a finding printed under an `all-clear` headline — and `assert r.exit_code == 0` bites it; that sed matches only the single-line attention condition `exit_code` still carries (Task 4 Step 7 says what a rc **6** there means).

The mutations are addressed to distinct lines: `if self.deadmen.description_findings:` matches only the markdown branch (the `elif` reads `… is not None`, not `:`), and `findings = len(…)` only the journal one.

**The third mutation (the link one) is deliberately narrow**: it keeps the prefix *requirement* and drops only the *anchoring*, so `passing-mention-first` is the one and only fixture it moves — `prefixless` still fails on the missing prefix, and every other fixture carries a single path or none. A blunter mutation that dropped the prefix check too would be killed by `prefixless` and prove nothing about the anchoring. Record the six verdicts.

______________________________________________________________________

### Task 7: The operating surfaces and the corrected belief (spec D1, D6)

**Files:**
- Modify: `infra/runbooks/reference-data.md:3` (the file's opening sentence) and `:13-15` (`refdata-sweep-due` → *What you are seeing*), `:33` (step 4)
- Modify: `infra/runbooks/ops.md:194-198` (`healable-threshold-rederivation-due` → *What you are seeing*), `:216` (step 3)
- Modify: `.claude/skills/zcrypto-daily-ops/SKILL.md` — the paragraph under `## What this is` (line 11), the two paragraphs under `## 5. Evaluate the due reminders`, a NEW `## 6.` section after it, and the renumbering of the three headings below
- Modify: `.claude/skills/zcrypto-rollout-image/SKILL.md` — the one `resubscribe replay` sentence on the Phase 1 immediate-checks bullet
- Modify: `docs/open-topics/archive/T0103-reconciler-books-unfilled-silence-as-healed.md:36` (one sentence, in place)
- Modify: `docs/open-topics/T0037-rotation-trusts-an-untrusted-timestamp.md` — the parked-residuals bullet carrying `documented as noise` (one bullet, in place; status untouched)
- Modify: `docs/reference/ops-journal/README.md` — the two example-paragraph lines inside the fenced block (Step 9)
- Edit, never commit: `docs/memo.local.md` (gitignored)

**Interfaces:**
- Consumes: the report's `## Reminders` section and its `OWED`/`ok` markers (Task 4); the `## Dead-men` `description:` lines (Task 6).

- [ ] **Step 1: `reference-data.md` — the report is the trigger, Slack the convenience**

Line 3 currently opens with the sentence `You are here because a **scheduled reminder came due** in Slack.` — replace that first sentence only (the rest of the line stays) with:

```markdown
You are here because the daily pass's report listed a reminder as **OWED** under `## Reminders`, or a **scheduled reminder came due** in Slack.
```

In the `refdata-sweep-due` section, replace the *What you are seeing* paragraph (line 15) with:

```markdown
The daily pass's report (`ops-daily.py report`) names this reminder under `## Reminders` — `due in N days` or `OVERDUE by N days`, computed every day from the last row of the register's re-confirmation log plus the monthly cadence. A scheduled Slack message in `#zcrypto` may say the same. **The report is the trigger; the Slack message is a convenience ping** — its scheduling cannot be listed or verified from this side, so its absence means nothing and its presence adds nothing. It is not an alert — nothing is wrong. The facts it re-confirms are owned by a third party and move without emitting any signal we could alert on.
```

Step 4 (line 33) keeps its re-arm instruction; append this sentence to it:

```markdown
The report computes due-ness regardless — the message is a convenience, not what the check rests on.
```

- [ ] **Step 2: `ops.md` — the healable reminder is event-driven now**

Replace the section's *What you are seeing* paragraph (line 198) with:

```markdown
The daily pass's report names this reminder under `## Reminders`: **OWED** when `zcrypto_reconcile_healable_gap_seconds_total` increased in the window — a new healable-gap event landed, so the count in step 1 is owed again — and `ok` when it did not. **A third line says the counter *reset*** — a ledger correction or rebuild lowered the total, so `increase()` would read the whole post-reset value as movement. That is OWED too, and the report deliberately quotes no figure with it: the recount below is the only arbiter. A Slack message in `#zcrypto` may prompt the same; the report is the trigger, the message a convenience ping that cannot be verified to exist from this side. It is not an alert — **nothing is wrong**. Unlike `refdata-sweep-due`, which is calendar-driven, this one is event-driven: qualifying days accrue only when the counter moves, and the pass reads the counter, never the ledger — step 1 is still yours.
```

Step 3 (line 216, `**Fewer than three qualifying days ⇒ do nothing except re-arm.**`) keeps its text; append these sentences to it — they also settle the lost 2026-08-27 message: it is NOT replaced by a fresh scheduling in this branch, because the next re-arm is this step's own, the next time the report says OWED and the section runs:

```markdown
The re-arm is a convenience — the pass re-evaluates the counter every day whether or not the message lands, so a message that never arrives (the 2026-08-27 one did not) is not replaced out of band: the next one is scheduled here, when this section next runs.
```

- [ ] **Step 3: Pre-commit and commit the runbooks**

```bash
uv run pre-commit run -a 2>&1 | tail -12
uv run pytest tests/test_infra_alert_rules.py tests/test_ops_daily.py -q -k "runbook or anchor or description" 2>&1 | tail -3
git add infra/runbooks/reference-data.md infra/runbooks/ops.md
git commit -m "docs(runbooks): the daily report is the reminder trigger, the Slack message a convenience"
```

Expected: pre-commit clean after re-staging any mdformat rewrite; the anchor tests still pass (the `<a name=…>` lines are untouched — verify with `git diff HEAD~1 --stat` that no anchor line changed: `git diff HEAD~1 | grep '^[-+]<a name' | wc -l` prints `0`).

- [ ] **Step 4: The skill — step 5 evaluates the report, and a new step 6 says what to do about a faulted description**

In `.claude/skills/zcrypto-daily-ops/SKILL.md`, line 11's clause `It reads what fired, what the logs said, whether the dead-men are alive, whether the fleet's own series are present and fresh, and what was deployed` becomes:

```markdown
It reads what fired, what the logs said, whether the dead-men are alive and their descriptions still resolve, whether the fleet's own series are present and fresh, what was deployed, and which reminders are due
```

Replace the two paragraphs under `## 5. Evaluate the due reminders` (from `The runbook's SCHEDULED REMINDER sections` to `the day the trigger chain is broken is exactly the day the sweep goes unnoticed.`) with:

```markdown
The report's `## Reminders` section is the trigger — an **OWED** line is work, not decoration: open the section it names (`reference-data.md#refdata-sweep-due`, `ops.md#healable-threshold-rederivation-due`) and do it. The sweep's due-ness is computed from the register's last re-confirmation row plus the monthly cadence; the healable line says only whether the counter moved in the window — the count itself is still that section's step 1, from the ledger.

**Slack's scheduled message is a convenience ping, never the check.** Its scheduling cannot be listed or verified from this side, so "no message arrived" means nothing and a message that did arrive adds nothing the report did not already say. A reminder source the report could not read is exit 2, like any other.
```

Then the description remedy, which today lands on no operating surface at all: step 2 is per alert that fired and none does, step 3 classifies a command and there is none, and no runbook section covers it — so a pass reading a `description:` line has nothing that tells it what to do. Insert a **new section between `## 5. Evaluate the due reminders` and the journal section**, and renumber the three headings below it (`## 6. Write the journal entry` → `## 7.`, `## 7. Post the summary` → `## 8.`, `## 8. Re-arm tomorrow` → `## 9.`; nothing outside this file cites those numbers — verified by grep over `.claude/`, `infra/runbooks/` and `docs/reference/`):

```markdown
## 6. Rewrite any dead-man description the report faults

The report's `## Dead-men` section prints one `- description:` line per faulted check: a description with no `Runbook: infra/runbooks/<file>#<anchor>` link, one whose link resolves to no anchor in the file it names, or one carrying repo-internal vocabulary — on a surface read from a phone with nothing open.

**This is not an alert.** Nothing fired, so there is no runbook section to open; no command is run, so there is nothing to classify; and it does not move the verdict — a day whose only finding is a description is still `all-clear`, by design. What it needs is a hand rewrite, which no repo change can make: the descriptions are hand-written in healthchecks.io.

**The fix is a hand rewrite of that check's description in healthchecks.io**, with the admin key (`healthchecks_api_key` in the vault — the read-only key the report reads with cannot write). Give it the `Runbook:` link and drop the vocabulary; send the description field and nothing else, so the check's own schedule and grace period are untouched; then read it back. The finding clears on the next pass.

**If it is not fixed, say so in the entry, with the check named.** The line reprints every day until someone rewrites it, and a finding nobody names reads as a new one each morning.
```

Then:

```bash
uv run pre-commit run -a 2>&1 | tail -6
grep -n '^## ' .claude/skills/zcrypto-daily-ops/SKILL.md
git add .claude/skills/zcrypto-daily-ops/SKILL.md
git commit -m "claude(daily_ops): step 5 evaluates the report's reminders; a new step 6 for a faulted description"
```

Expected from the grep: `## What this is`, then `## 1.` … `## 9.` in order with no number repeated or skipped, then `## Failure modes — catch yourself` last. Keep the new section free of the vocabulary `operator-facing-text.md` bars — no phase, topic, iteration or spec serial anywhere in it.

`docs/specs/00104-…-design.md` and `docs/plans/00104-…md` enumerate the pass's steps as 1–8; both are point-in-time records of the iteration that built the skill, and are deliberately left. The skill itself is the live surface.

- [ ] **Step 5: The rollout skill — the drop lines are reconnect replay, not resubscribe (spec D6)**

`.claude/skills/zcrypto-rollout-image/SKILL.md`'s Phase 1 immediate-checks bullet ends with the sentence (verify `grep -c "resubscribe replay" .claude/skills/zcrypto-rollout-image/SKILL.md` prints `1` first):

```markdown
`dropping late event` lines right after start are healthy resubscribe replay, not a failure.
```

The same measurement that licenses spec 00107 D4 disproves that attribution — resubscribes, resubscribe errors and desyncs all read 0 in the window, while reconnects read 2 and 1 and match the bursts one-for-one — and this is a skill an operator follows while converging the unbackfillable capture pair. Replace that sentence, and nothing else on the bullet, with:

```markdown
`dropping late event` lines right after start are healthy reconnect replay, not a failure — a reconnect's trade snapshot replays prints from before the boundary. How often that happens is read from the scraped `zcrypto_capture_reconnects_total`, never from a count of these lines.
```

No level word is written here on purpose: the hosts keep emitting the old level until the capture-image rollout carries spec 00107 D4 to them, and a skill sentence naming a level would be false in the gap and then rot again at the next change. The line's TEXT is what an operator greps, and it is unchanged.

```bash
uv run pre-commit run -a 2>&1 | tail -6
grep -c "resubscribe replay" .claude/skills/zcrypto-rollout-image/SKILL.md   # 0
git add .claude/skills/zcrypto-rollout-image/SKILL.md
git commit -m "claude(rollout_image): the late-event drops are reconnect replay, not resubscribe"
```

- [ ] **Step 6: T0103's archive — the belief re-trued in place (spec D6)**

Load the `topic-ops` skill first (every topic-file edit). In `docs/open-topics/archive/T0103-reconciler-books-unfilled-silence-as-healed.md` line 36, this sentence (verify `grep -c "cannot be deleted through the API"` prints `1` first):

```markdown
**The 2026-08-27 Slack reminder is not gone and cannot be** — a scheduled message cannot be deleted through the API, so it will land in `#zcrypto` on the day: read it as a prompt to open that runbook section, NOT this file.
```

is replaced in place by:

```markdown
**The 2026-08-27 Slack reminder never landed** — `#zcrypto` read across that whole UTC day holds no such message (measured 2026-08-30, spec `00107`). A scheduled message can be created but never listed or verified from this side, so an arming that failed to exist is undetectable; the daily pass now computes this reminder's due-ness itself (`read_reminders` in `infra/scripts/ops_daily.py`), and the Slack message is a convenience ping, not the trigger.
```

Compare `grep '^#' <file>` before and after (identical), then:

```bash
uv run pre-commit run -a 2>&1 | tail -6
git add docs/open-topics/archive/T0103-reconciler-books-unfilled-silence-as-healed.md
git commit -m "docs(open-topics): T0103 -- the 2026-08-27 reminder never landed; the arming cannot be verified"
```

`archive/T0113` also describes the Slack reminder as the sweep's trigger; it is a point-in-time record of how the routine was homed on 2026-08-04 and is deliberately left.

- [ ] **Step 7: T0037's live topic — the argument re-trued where the level change falsifies it (spec D4)**

`docs/open-topics/T0037-rotation-trusts-an-untrusted-timestamp.md` is `status: partial` and live, and one sentence of its parked-residuals argument rests on both facts this iteration changes: that the late-event drop is a bare WARNING, and that the rollout skill calls those lines resubscribe replay. `topic-ops` is already loaded from Step 6. Verify `grep -c "documented as noise" docs/open-topics/T0037-rotation-trusts-an-untrusted-timestamp.md` prints `1`, then replace this bullet in place:

```markdown
- **Both residuals manifest as the same pair of events: an hour finalized EARLY, and that stream's post-stamp tail then dropped as late.** Neither half is counted. The late-event drop is a bare `logger.warning` (`cli/capture/segment_writer.py:362`) with no counter behind it — and `.claude/skills/zcrypto-rollout-image/SKILL.md` tells operators that `dropping late event` lines right after a start are healthy resubscribe replay, so the one visible trace is documented as noise.
```

with:

```markdown
- **Both residuals manifest as the same pair of events: an hour finalized EARLY, and that stream's post-stamp tail then dropped as late.** Neither half is counted. The late-event drop in `append` logs at INFO with no counter behind it (spec `00107` D4), and it is expected reconnect replay by design — so the one visible trace is deliberately noise, which is the argument FOR `zcrypto_capture_hour_finalized_early_total` (`## Done so far`) rather than against it.
```

The status stays `partial` and no sub-item is completed here — this is prose re-truing, so the index bullet and `## Done so far` are untouched. Compare `grep '^#' <file>` before and after (identical), then:

```bash
uv run pre-commit run -a 2>&1 | tail -6
git add docs/open-topics/T0037-rotation-trusts-an-untrusted-timestamp.md
git commit -m "docs(open-topics): T0037 -- the late-event drop is INFO and reconnect replay, not documented noise"
```

- [ ] **Step 8: The memo (gitignored — edit, never stage)**

```bash
grep -n "armed OUTSIDE" docs/memo.local.md
grep -c "noisy warning" docs/memo.local.md
grep -n "owed a second data point" docs/memo.local.md
```

Expected: one hit each, the last two on the **same** line. **There is no `noisy warning` item in `## NEW IDEAS`** — the single occurrence sits inside the Block A ✅-DONE ledger entry, in the clause reading *the capture WARNING bursts (appended to the "noisy warning" idea, owed a second data point)*, which describes an append that never happened. That clause is where the deferral actually lives, so that clause is what gets discharged: do not hunt for an idea item, and do not mark the ✅-DONE line as a whole "discharged" — it records a completed pass, not this deferral.

Two edits, both to the working file only:

1. Append to the note that says the reminders are armed OUTSIDE the repo: ` — and cannot be verified from this side: the Slack MCP schedules but never lists, so an arming that failed to exist is invisible (T0103's 2026-08-27 reminder never landed); spec 00107 D1 moved the load onto read_reminders() and the message is a convenience.`
2. Rewrite that one clause in place, leaving the rest of the ledger entry byte-identical: `the capture WARNING bursts (explained and DISCHARGED by spec 00107 D4 — the two bursts match increase(zcrypto_capture_reconnects_total[24h]) = 2 and 1 one-for-one, so the second data point is delivered, not owed; the three drop lines are now INFO)`.

`git status --short` must not list the memo afterwards.

- [ ] **Step 9: The journal README's example paragraph carries the clauses the instrument now prints**

`docs/reference/ops-journal/README.md` shows the canonical paragraph inside a fenced block, and a pass writing its entry by hand follows that shape. `tests/test_ops_journal.py` checks only headings, so nothing goes red when it drifts — which is exactly why it must be edited here. Replace the **two paragraph lines only** — the ones beginning `window 24 h to` and `dead-men 0 down via Grafana` (16–17 today); the `## 2026-08-29 — all-clear` heading above and the closing ``` ``` ``` fence below them stay, or the rest of the README ends up inside an unterminated code block:

```markdown
window 24 h to 2026-08-29 06:00Z · alerts none · checks all pass · logs 0 ERROR/CRITICAL lines ·
dead-men 0 down via Grafana, 10 read directly · deploys none ·
reminders refdata sweep: due in 5 days (last sweep 2026-08-04), healable re-derivation: counter unchanged in 24 h · actions none · follow-ups none
```

The `N description finding(s)` clause is deliberately not in the example: it is printed only when there are findings, and an example carrying it would teach a shape a clean day never has.

```bash
uv run pre-commit run -a 2>&1 | tail -6
uv run pytest tests/test_ops_journal.py -q 2>&1 | tail -3
git add docs/reference/ops-journal/README.md
git commit -m "docs(ops-journal): the example paragraph carries the reminders clause"
```

______________________________________________________________________

### Task 8: Closeout — the after reading, the guards that reach docs, the entry

**Files:**
- Modify: `docs/iterations-history-phase6.md` (append one entry)

**Interfaces:**
- Consumes: `.tmp/pass-before.md` and the two healable-counter values (Task 0), the mutation verdicts recorded in Tasks 1, 2, 3, 4 and 6.

- [ ] **Step 1: The after reading (main loop — it reads the vault)**

```bash
SCRATCH="$(git rev-parse --show-toplevel)/.tmp"; mkdir -p "$SCRATCH"; ls -l "$SCRATCH/pass-before.md"
uv run python infra/scripts/ops-daily.py report --since 24h > "$SCRATCH/pass-after.md"; echo "rc=$?" | tee -a "$SCRATCH/pass-after.md"
sed -n '/## Reminders/,/## Deploys/p' "$SCRATCH/pass-after.md"; grep -n "description" "$SCRATCH/pass-after.md"; grep -n "capture WARNING\|/capture WARNING" "$SCRATCH/pass-after.md"
```

Expected: `rc=` printed immediately after the command; `## Reminders` shows both lines with `ok`/`OWED` and their runbook anchors; `## Dead-men` shows `- descriptions: all 10 carry a resolving runbook link and no internal token`; exit code equal to Task 0's unless a reminder source was unreadable (then 2, and the line names which — a finding to report, not to paper over). The `## Logs` section still shows the capture WARNING counts for the window: the INFO change reaches the hosts only with the next capture-image rollout — the attended one `T0037`'s `ripe_when` already owes (spec `00103`'s detectors ride the same digest), so no separate rollout is registered for it — and the count is expected to persist until then; the entry says so.

- [ ] **Step 2: The suites the branch can reach, and the guards that reach docs**

```bash
uv run pytest tests/test_ops_daily.py tests/test_capture_segment_writer.py tests/test_liquidations_coinalyze.py tests/test_infra_alert_rules.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py -q 2>&1 | tail -3
```

Expected: all passed. The token guard covers the new literals in `infra/scripts/ops_daily.py`; the citation guard covers every new test docstring.

- [ ] **Step 3: The iterations-history entry**

Load the `iteration-closeout` skill. Append to `docs/iterations-history-phase6.md` (Phase 6 — day-2 operations) a section `## 2026-MM-DD — iter-<N>: the signals that were silently absent — reminders, log levels, and the descriptions no test can reach (spec 00107)` where `<N>` is one above the file's highest `iter-` (157 as of writing — re-read the tail before writing). Bullets, one per change, in the file's existing shape:

- the lost reminder and the structural fact (no list/verify API), and D1's answer: `read_reminders()` computes due-ness daily from the register row and the healable counter; owed reports, unreadable exits 2 — with the before/after exit codes and the `## Reminders` lines from Steps 1 and Task 0;
- the three drop lines at INFO with the measured basis (bursts matching `zcrypto_capture_reconnects_total` 2 and 1; gap counter 0), the accepted loss spec 00107 D4 names for the shared `SegmentWriter`'s liquidations consumers (the reconnect counter is capture's alone; `test_poll_cycle_second_cycle_is_silent_no_dedup_drops` is what still holds the watermark invariant, and re-levelling its capture is what keeps it biting), and the note that the hosts emit WARNING until the capture-image rollout `T0037`'s `ripe_when` owes carries the digest — no rollout of its own;
- the healable reminder's three states — moved, unchanged, reset — and why the reset state exists (the counter is re-emitted from ledger totals; `increase()` reads a correction as movement; the alert rule's `resets()` guard mirrored);
- the description check: two assertions per check, the true positive over today's ten (`tests/fixtures/healthchecks_descriptions.json`, fields name/tags/desc only), detection not generation and why — **and the ruling that a finding is a report line and a journal clause, never the exit code**, so the visibility is what the tests pin and the remedy (a hand rewrite in healthchecks.io with the admin key) is what the skill's new step 6 tells the pass to do; if the true positive named any live description as owed, those check names as a finding of this pass, which the daily report names until the rewrite lands;
- every guard mutation-probed: the verdicts from Tasks 1, 2, 3, 4 and 6 (three drop sites, two cadence mutations, five reminder mutations plus the runbook-anchor rename the citation guard catches, the owed-reminder-must-not-block mutation, six description mutations — all KILLED, or the one that was not and what was done);
- D6: T0103's sentence re-trued and T0037's parked-residuals bullet with it; the rollout skill's `resubscribe replay` attribution corrected to reconnect; the memo note extended; `archive/T0113` deliberately left.

No decisions-log entry: nothing here is subject-matter research (`decisions-log.md`'s gate).

```bash
uv run pre-commit run -a 2>&1 | tail -6
git add docs/iterations-history-phase6.md
git commit -m "docs(iterations-history): iter-<N> -- reminders, log levels, and the descriptions no test can reach"
```

- [ ] **Step 4: Review trailers and the branch's end**

`infra/scripts/review-trailer-audit.sh` must pass before push; the Task 1 commit's reviewer is at the Fable floor. Report the branch ready — the PR opens only on the user's word (`branch-workflow.md`). The INFO change reaches the capture hosts with the attended capture-image rollout `T0037`'s `ripe_when` already registers (through `zcrypto-rollout-image`); this branch owes no rollout and registers none — the topic is the deferral's home, and the report's `## Logs` count is the evidence of the gap until it lands.
