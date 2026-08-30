# Reminders, log levels, and the descriptions no test can reach — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The daily pass computes reminder due-ness itself from the register and the healable counter and checks the ten dead-man descriptions it already fetches; the three reconnect-replay drop lines in the capture writer log at INFO; the belief that hid the lost reminder is corrected where it lives.

**Architecture:** `infra/scripts/ops_daily.py` gains a sixth read, `read_reminders()` (pure repo file + one PromQL query through the existing `_proxy_query`), and a pure `check_descriptions()` that `read_deadmen()` runs over the checks it fetched. Both surface through the existing `Report` (markdown, journal paragraph, exit code). `cli/capture/segment_writer.py` changes three `logger.warning` calls to `logger.info` with one comment naming the counter that replaces them. The runbook sections and the skill say the report is the trigger and Slack the convenience.

**Tech Stack:** Python 3.14 via `uv run`; `urllib.request` (no new dependency); pytest with `caplog`, `monkeypatch`, `tmp_path`; `infra/scripts/mutate-probe.sh` for guard proofs; Markdown under mdformat.

**Spec:** `docs/specs/00107-reminders-and-observability-hygiene-design.md`

## Global Constraints

- **The exit-code contract of `ops_daily.py` holds**: 0 all-clear, 1 attention, 2 a source it could not read; 2 outranks 1. A reminder that is **owed** reports and never blocks (spec D2: "It reports; it does not block") — it leaves the exit code alone. A reminder source the pass **could not read** (no dated register row, the counter query failed or returned no series) is `unreadable` → exit 2, the module's own contract ("a source that cannot be reached is a finding ABOUT that source, never a silent gap"). A **description finding** (spec D5) is attention → exit 1: it is a defect on an operator surface that needs a human rewrite.
- **The instrument stays pure-HTTP** (spec D3): no `ssh`, no ledger read. The healable reminder answers only "did `zcrypto_reconcile_healable_gap_seconds_total` increase in the window"; the count of qualifying days stays the runbook's own step 1, from the ledger.
- **Every guard is proven on a fixture where defect and correct behaviour differ, then mutation-probed** through `infra/scripts/mutate-probe.sh` on a clean tree after its commit (`agent-ops.md`). Verify `--collect-only` selects the intended tests before trusting any verdict.
- **No string literal in `infra/scripts/*.py` may carry `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>`, `WP<N>`, or a `D<n>` decision number** — `tests/test_internal_terms_not_operator_visible.py` scans every non-docstring literal there. Regex source like `r"\bT\d{4}\b"` does not match (no four digits follow the `T`); report text like `"internal token {token!r}"` is a runtime value. Token-carrying fixtures live in `tests/`, which is not scanned. Comments and docstrings may cite `spec 00107`, `T0103`.
- **Test prose never writes a bare plan-task number** (`tests/test_code_prose_citations.py`): say "spec 00107 D4", never "Task 1".
- **Secrets never reach stdout, argv or a file**: the Grafana token and the healthchecks key live in locals and request headers. The description fixture (Task 6) is written from `name`/`tags`/`desc` only — never the whole check object.
- **Stage by explicit path, one commit-type per commit** (`commit-messages.md`); `.claude/` edits are a separate `claude(...)` commit from every other kind. Every commit carries `Co-Authored-By: <the actual authoring model> <noreply@anthropic.com>`; every commit is reviewed by a different agent before push and gets `Reviewed-by:` amended in the turn the review returns. **Task 1 touches the capture write path, so its review floor is Fable** (`spec-plan-locations.md`).
- **Host-touching and vault-touching steps run in the main loop** (`agent-ops.md`): the live pass runs (Task 0, Task 8) and the description fetch (Task 6 Step 4) are main-loop steps, never inside a dispatched subagent. Nothing in this plan touches a fleet host.
- **Markdown: one line per paragraph/bullet**; run `uv run pre-commit run -a` until clean before every commit that touches `.md`, re-staging what mdformat rewrote.
- **`docs/memo.local.md` is gitignored and never committed**; its edit (Task 7 Step 6) is a working-file edit, not a commit.

______________________________________________________________________

### Task 0: The before reading — the live pass's exit code on the unchanged code

**Files:** none modified.

**Interfaces:**
- Produces: the pre-change exit code and report, saved as `<scratchpad>/pass-before.md`, quoted in Task 8's closeout entry.

- [ ] **Step 1: Run the pass on the branch's starting code (main loop — it reads the vault)**

```bash
git log --oneline -1
uv run python infra/scripts/ops-daily.py report --since 24h > "$SCRATCH/pass-before.md"; echo "rc=$?" | tee -a "$SCRATCH/pass-before.md"
tail -3 "$SCRATCH/pass-before.md"
```

where `SCRATCH` is the session's scratchpad directory. Expected: `rc=0`, `rc=1` or `rc=2` printed **immediately after the pipeline's own command** (the `echo` reads `$?` of the redirect, which is the script's); the report's `## Logs` section is what Task 1 changes and its `## Dead-men` section shows `- direct: 10 checks read`. If the vault is locked (the report reads `the vault could not be read`), unlock the GPG agent and re-run — an exit-2-for-the-vault baseline says nothing about the fleet.

______________________________________________________________________

### Task 1: The three reconnect-replay drops log at INFO (spec D4)

**Files:**
- Modify: `cli/capture/segment_writer.py:361-364` (the late-event drop in `append`), `:508-511` (the replay drop in `_admit`), `:542-545` (the replay drop in `_hold`)
- Modify: `tests/test_capture_segment_writer.py` (append three tests at the end; change `caplog.at_level(logging.WARNING)` at line 1988 to `logging.INFO`)
- Modify: `tests/test_liquidations_coinalyze.py:558` and `:572` (`caplog.at_level(logging.WARNING)` → `logging.INFO`)

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
    # ~600 of these per reconnect, on every reconnect: as WARNING they were ~1200 lines a day
    # competing with real findings in the daily pass's log read, and they told nothing the scraped
    # counter `zcrypto_capture_reconnects_total` does not tell better.
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

In `cli/capture/segment_writer.py`, the late-event site (currently lines 361–364) becomes:

```python
            # An hour that is already closed — a `<HH>.parquet` for it is on disk. A reconnect's
            # trade snapshot replays prints from before the boundary (T0026); writing them beside a
            # committed final would either duplicate rows it already holds or strand them.
            # INFO, not WARNING: this is the expected consequence of a normal reconnect, ~600 lines
            # per event, and at WARNING it drowned the daily pass's log read. The instrument for
            # "how often does this happen" is the scraped `zcrypto_capture_reconnects_total`, never
            # a count of these lines — do not raise it back (spec 00107 D4).
            logger.info("dropping late event pair=%s kind=%s ts=%s floor=%s", self._pair, self._kind, ts, floor)
```

The `_admit` site (currently line 510) becomes:

```python
            if key in self._seen:
                # INFO for the reason at the late-event drop in `append`: the reconnect counter is the signal.
                logger.info("dropping replayed event pair=%s kind=%s %s=%s", self._pair, self._kind, self._dedup_key, key)
                return
```

The `_hold` site (currently line 544) becomes:

```python
            if key in seen:
                # INFO for the reason at the late-event drop in `append`: the reconnect counter is the signal.
                logger.info("dropping replayed event pair=%s kind=%s %s=%s", self._pair, self._kind, self._dedup_key, key)
                return
```

`dropping implausible event` (line 354) and `first stamp opened a past hour` (line 497) stay WARNING — they are not reconnect replay and the spec names three sites.

- [ ] **Step 4: Re-level the three existing captures that would now miss the line**

`caplog.at_level(logging.WARNING)` sets the root level, and the `zcrypto.*` loggers inherit it, so an INFO record is not captured at all — `test_restart_reseeds_dedup_keys_from_open_hour_parts` (`tests/test_capture_segment_writer.py:1988`, asserts the line IS present) would go red, and the two in `tests/test_liquidations_coinalyze.py` (`:558` asserts absence, `:572` asserts presence) would be respectively vacuous and red. Change all three to `caplog.at_level(logging.INFO)`.

- [ ] **Step 5: Run the reachable suites**

Run: `uv run pytest tests/test_capture_segment_writer.py tests/test_liquidations_coinalyze.py -q 2>&1 | tail -3`
Expected: all passed, 0 failed.

- [ ] **Step 6: Commit**

```bash
git add cli/capture/segment_writer.py tests/test_capture_segment_writer.py tests/test_liquidations_coinalyze.py
git commit -m "fix(capture): the three reconnect-replay drops log at INFO -- the reconnect counter is the signal"
```

Body: the measured basis (two bursts in 24 h matching `increase(zcrypto_capture_reconnects_total[24h])` = 2 and 1 one-for-one; resubscribes, desyncs 0; gap counter 0), and that the capture log-dead rules select `level=~".+"` and the error rules `ERROR|CRITICAL`, so nothing depended on WARNING.

- [ ] **Step 7: Mutation-probe all three sites (tree must be clean)**

```bash
uv run pytest tests/test_capture_segment_writer.py --collect-only -q -k dropped_at_info 2>&1 | tail -4
```

Expected: exactly 3 tests collected. Then, with `PROBE='uv run pytest tests/test_capture_segment_writer.py -q -p no:cacheprovider -k dropped_at_info'`:

```bash
infra/scripts/mutate-probe.sh --file cli/capture/segment_writer.py \
  --control 's/logger.info("dropping late event/logger.debug("dropping late event/' \
  --mutation 's/logger.info("dropping late event/logger.warning("dropping late event/' -- $PROBE
grep -n 'logger.info("dropping replayed event' cli/capture/segment_writer.py
```

Expected: `mutate-probe: KILLED (control proven, tree restored byte-identically)`. The grep prints two line numbers, `A` (in `_admit`) and `B` (in `_hold`); run once per line:

```bash
infra/scripts/mutate-probe.sh --file cli/capture/segment_writer.py \
  --control 's/logger.info("dropping late event/logger.debug("dropping late event/' \
  --mutation "${A}s/logger.info/logger.warning/" -- $PROBE
infra/scripts/mutate-probe.sh --file cli/capture/segment_writer.py \
  --control 's/logger.info("dropping late event/logger.debug("dropping late event/' \
  --mutation "${B}s/logger.info/logger.warning/" -- $PROBE
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
    status: str    # "due in 5 days (last sweep 2026-08-04)" | "OVERDUE by 6 days (…)" | "counter moved +88.4 s in 24 h, recount the qualifying days" | "counter unchanged in 24 h"
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


@pytest.mark.parametrize("value,owed,word", [("88.4", True, "moved +88.4 s"), ("0", False, "unchanged")])
def test_the_healable_reminder_fires_only_when_the_counter_moved(tmp_path, value, owed, word):
    """The trigger discriminates: a counter that did not move owes nothing, one that did names the
    recount. The count itself stays the runbook's step 1, from the ledger -- Cloud cannot see it."""
    read = ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=_canned(_counter(value)), register=_register(tmp_path, *_TWO_SWEEPS))
    healable = _reminder(read, "healable re-derivation")
    assert healable.owed is owed
    assert word in healable.status, healable.status
    assert healable.runbook == "infra/runbooks/ops.md#healable-threshold-rederivation-due"


def test_a_healable_counter_with_no_series_is_unreadable_never_quiet(tmp_path):
    read = ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=_canned({"data": {"result": []}}), register=_register(tmp_path, *_TWO_SWEEPS))
    assert read.unreadable and "no series" in read.unreadable, read.unreadable
    assert not [r for r in read.reminders if r.name == "healable re-derivation"]
    assert _reminder(read, "refdata sweep")  # the half that could be read still is


def test_the_real_register_yields_a_refdata_reminder(tmp_path):
    """Against the committed file, with the counter canned: the pass's own default path parses."""
    read = ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=_canned(_counter(0)))
    assert read.unreadable is None, read.unreadable
    assert {r.name for r in read.reminders} == {"refdata sweep", "healable re-derivation"}
```

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

In `test_every_endpoint_the_instrument_builds_is_pinned` (line 1073), change the docstring's "the module builds six" to "the module builds seven" and append before the function's end:

```python
    reminders = _recording(_counter(0))
    ops_daily.read_reminders("tok", now=NOW, window=DAY, opener=reminders)
    assert len(reminders.urls) == 1 and "/uid/%s/api/v1/query" % ops_daily.PROM_DS_UID in reminders.urls[0], reminders.urls
    assert "increase(zcrypto_reconcile_healable_gap_seconds_total[24h])" in urllib.parse.unquote(reminders.urls[0]), reminders.urls
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_ops_daily.py -q -k "reminder or transport_failure or endpoint" 2>&1 | tail -6`
Expected: every new test and the two edited ones fail with `AttributeError: module 'ops_daily' has no attribute 'read_reminders'`.

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
        if not series:
            note("the healable counter returned no series, so the re-derivation reminder could not be evaluated")
            return read
        moved = float(series[0]["value"][1])
    except _UNREACHABLE as exc:
        note(f"the healable counter could not be read: {exc}")
        return read
    owed = moved > 0
    status = f"counter moved +{moved:.1f} s in {hours} h, recount the qualifying days" if owed else f"counter unchanged in {hours} h"
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
uv run pytest tests/test_ops_daily.py --collect-only -q -k "reminder or sweep_date or last_row or no_dated_row" 2>&1 | tail -3
```

Expected: at least 12 tests collected. With `PROBE='uv run pytest tests/test_ops_daily.py -q -p no:cacheprovider -k "reminder or sweep_date or last_row or no_dated_row"'` and the control `--control 's/^def read_reminders(/def read_reminderz(/'` on every run:

```bash
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def read_reminders(/def read_reminderz(/' \
  --mutation 's/owed = moved > 0/owed = moved >= 0/' -- $PROBE
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def read_reminders(/def read_reminderz(/' \
  --mutation 's/found = date\.fromisoformat/found = found or date.fromisoformat/' -- $PROBE
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def read_reminders(/def read_reminderz(/' \
  --mutation 's/in_log = line.startswith("## Re-confirmation log")/in_log = True/' -- $PROBE
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def read_reminders(/def read_reminderz(/' \
  --mutation 's/owed=days <= 0/owed=days < 0/' -- $PROBE
```

Expected: `KILLED` four times — always-firing healable trigger, first-row-wins, section-blind parse (the 2099 decoy), and due-today-not-owed each trip a test. Record the verdicts.

______________________________________________________________________

### Task 4: The report carries the reminders (spec D2)

**Files:**
- Modify: `infra/scripts/ops_daily.py` — `Report` (lines 348–425), `build_report` (428–429), `main` (473–481)
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
    assert "reminders refdata sweep: OVERDUE by 6 days" in r.journal_paragraph(), r.journal_paragraph()


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
Expected: every `build_report(` call now fails with `TypeError: build_report() got an unexpected keyword argument 'reminders'`; the clause test fails on `missing clause: reminders`; the required-field test fails because no `TypeError` is raised.

- [ ] **Step 3: Implement**

In `Report` add the field `reminders: RemindersRead` after `deploys: list[dict]`. In `unreadable`, extend the docstring's list ("-- the verdict checks included" → "-- the verdict checks and the reminders included") and the `named` comprehension to `(self.alerts.unreadable, self.logs.unreadable, self.deadmen.unreadable, self.reminders.unreadable)`. In `markdown()`, after the `## Dead-men` block and before `## Deploys in window`:

```python
        out += ["", "## Reminders"] + (
            [f"- {'OWED' if r.owed else 'ok'} {r.name}: {r.status} — {r.runbook}" for r in self.reminders.reminders] or ["- none read"]
        )
```

In `journal_paragraph()`, add before `deploys = ...`:

```python
        reminders = ", ".join(f"{r.name}: {r.status}" for r in self.reminders.reminders) or "none read"
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

______________________________________________________________________

### Task 5: `check_descriptions()` — a resolving runbook link and no internal token (spec D5)

**Files:**
- Modify: `infra/scripts/ops_daily.py` — new constant and function after `HEALTHCHECKS_API` (line 187)
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
    """A link resolves against the FILE it names: an anchor living in a sibling file scrolls nowhere."""
    checks = [
        {"name": "dangling", "desc": "Runbook: infra/runbooks/ops.md#no-such-anchor"},
        {"name": "wrong-file", "desc": "Runbook: infra/runbooks/capture.md#zcrypto-ops-archive-pull-stalled"},
        {"name": "linkless", "desc": "Pings every minute."},
        {"name": "clean", "desc": _CLEAN_DESC},
    ]
    findings = ops_daily.check_descriptions(checks)
    assert sorted(f.split(":")[0] for f in findings) == ["`dangling`", "`linkless`", "`wrong-file`"], findings


def test_a_check_with_no_description_at_all_is_a_finding_not_a_pass():
    assert ops_daily.check_descriptions([{"name": "bare"}]) == ["`bare`: no `Runbook: infra/runbooks/<file>#<anchor>` in its description"]
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_ops_daily.py -q -k description 2>&1 | tail -5`
Expected: 3 failed with `AttributeError: module 'ops_daily' has no attribute 'check_descriptions'`.

- [ ] **Step 3: Implement**

After `HEALTHCHECKS_API = "https://healthchecks.io/api/v3/checks/"` and the `REPO_ROOT`/`DEPLOY_LOG` lines in `infra/scripts/ops_daily.py`:

```python
RUNBOOKS = REPO_ROOT / "infra/runbooks"
# The vocabulary `.claude/rules/operator-facing-text.md` bans from any surface read without the repo
# open. `Phase[ -]` because the live descriptions spelled it `Phase-6`.
_INTERNAL_TOKEN = re.compile(r"\bPhase[ -]\d|\bT\d{4}\b|\biter-\d+|\bspec\s+\d{5}|\bWP\d")


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
        link = _RUNBOOK_LINK.search(desc)
        if link is None:
            out.append(f"`{name}`: no `Runbook: infra/runbooks/<file>#<anchor>` in its description")
        else:
            path = runbooks / link.group(1)
            if not path.exists() or f'<a name="{link.group(2)}"></a>' not in path.read_text():
                out.append(f"`{name}`: its runbook link {link.group(0)} resolves to no anchor")
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
- Modify: `infra/scripts/ops_daily.py` — `DeadmenRead` (lines 206–210), `read_deadmen` (272–293), `Report.exit_code` (375–381), `Report.markdown` dead-men block (397–402), `Report.journal_paragraph` (408–425)
- Create: `tests/fixtures/healthchecks_descriptions.json` (name, tags, desc of the ten live checks — nothing else)
- Modify: `tests/test_ops_daily.py` — new tests appended

**Interfaces:**
- Consumes: `check_descriptions` (Task 5).
- Produces: `DeadmenRead.description_findings: list[str]` (default `[]`), populated by `read_deadmen` after a successful direct read; findings → exit 1, listed under `## Dead-men` in the markdown, counted in the journal paragraph when non-zero.

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


def test_a_description_finding_is_attention_and_reaches_the_report_and_the_paragraph():
    deadmen = ops_daily.DeadmenRead(
        via_prometheus=0.0,
        via_healthchecks=[{"name": "x"}],
        description_findings=["`x`: its description carries the internal token 'T0083'"],
    )
    r = _report(deadmen=deadmen)
    assert r.exit_code == 1, r.exit_code
    assert "- description: `x`: its description carries the internal token 'T0083'" in r.markdown(), r.markdown()
    assert "1 description finding" in r.journal_paragraph(), r.journal_paragraph()


def test_clean_descriptions_say_so_in_the_report_and_stay_out_of_the_paragraph():
    r = _report(deadmen=ops_daily.DeadmenRead(via_prometheus=0.0, via_healthchecks=[{"name": "a"}, {"name": "b"}]))
    assert r.exit_code == 0
    assert "- descriptions: all 2 carry a resolving runbook link and no internal token" in r.markdown(), r.markdown()
    assert "description finding" not in r.journal_paragraph()


def test_todays_ten_real_descriptions_all_pass():
    """The true positive: a check that refuses everything is not a check. `name`/`tags`/`desc` of the
    ten live checks, read 2026-08-30 through the read-only key -- never the whole object, which
    carries the check's write URL. Re-fetch it (the plan for spec 00107 says how) if a description
    is rewritten; a red here after a rewrite is the finding the daily pass would have made."""
    checks = json.loads((Path(__file__).resolve().parent / "fixtures" / "healthchecks_descriptions.json").read_text())
    assert len(checks) == 10, len(checks)
    assert ops_daily.check_descriptions(checks) == []
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest tests/test_ops_daily.py -q -k "descriptions or description_finding" 2>&1 | tail -6`
Expected: the first three fail on `DeadmenRead.__init__() got an unexpected keyword argument 'description_findings'` / missing attribute; the fixture test fails with `FileNotFoundError`.

- [ ] **Step 3: Implement**

`DeadmenRead` gains `description_findings: list[str] = field(default_factory=list)` after `via_healthchecks`. In `read_deadmen`, inside the `try` that reads healthchecks, after `read.via_healthchecks = json.load(response).get("checks", [])`, add (inside the `with` block is fine — it is a pure computation):

```python
        read.description_findings = check_descriptions(read.via_healthchecks)
```

`Report.exit_code`'s attention condition becomes:

```python
        if (
            self.alerts.firing_now
            or [c for c in self.verdict if not c.ok]
            or (self.deadmen.via_prometheus or 0) > 0
            or self.deadmen.description_findings
        ):
            return 1
```

In `markdown()`, after `f"- direct: {len(self.deadmen.via_healthchecks)} checks read",` inside the dead-men list, close that list and add:

```python
        if self.deadmen.description_findings:
            out += [f"- description: {f}" for f in self.deadmen.description_findings]
        elif self.deadmen.via_healthchecks:
            out.append(f"- descriptions: all {len(self.deadmen.via_healthchecks)} carry a resolving runbook link and no internal token")
```

In `journal_paragraph()`, add `findings = len(self.deadmen.description_findings)` beside `warnings = ...`, and change the `read directly` clause to:

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
print(len(out), "checks;", sum(1 for c in out if "Runbook:" in (c["desc"] or "")), "carry a Runbook: line")
EOF
grep -c '"ping_url"\|hc-ping\|"update_url"\|"pause_url"' tests/fixtures/healthchecks_descriptions.json
```

Expected: `10 checks; 10 carry a Runbook: line`, and the grep prints `0` — no URL of any kind in the file. If the count is not 10, or any description lacks a `Runbook:` line, stop: that is a live finding to report, not a fixture to edit.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_ops_daily.py -q 2>&1 | tail -3`
Expected: all passed — including `test_todays_ten_real_descriptions_all_pass`. If it fails, read WHICH description it names: a real defect on the live surface is reported (exit 1 is what the pass will now say), not fixed by editing the fixture.

- [ ] **Step 6: Commit**

```bash
git add infra/scripts/ops_daily.py tests/test_ops_daily.py tests/fixtures/healthchecks_descriptions.json
git commit -m "feat(ops_daily): the dead-man read checks the ten descriptions it fetches"
```

- [ ] **Step 7: Mutation-probe both assertions (clean tree)**

```bash
uv run pytest tests/test_ops_daily.py --collect-only -q -k "description" 2>&1 | tail -3
```

Expected: 7 tests collected. With `PROBE='uv run pytest tests/test_ops_daily.py -q -p no:cacheprovider -k description'`:

```bash
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def check_descriptions(/def check_descriptionz(/' \
  --mutation 's/for token in _INTERNAL_TOKEN.findall(desc):/for token in ():/' -- $PROBE
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def check_descriptions(/def check_descriptionz(/' \
  --mutation 's/not in path.read_text():/not in path.read_text() and False:/' -- $PROBE
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control 's/^def check_descriptions(/def check_descriptionz(/' \
  --mutation 's/or self.deadmen.description_findings$/or []/' -- $PROBE
```

Expected: `KILLED` three times — a token check that never fires, an anchor check that never fires, and a finding that no longer moves the exit code. Record the verdicts.

______________________________________________________________________

### Task 7: The operating surfaces and the corrected belief (spec D1, D6)

**Files:**
- Modify: `infra/runbooks/reference-data.md:3` (the file's opening sentence) and `:13-15` (`refdata-sweep-due` → *What you are seeing*), `:33` (step 4)
- Modify: `infra/runbooks/ops.md:194-198` (`healable-threshold-rederivation-due` → *What you are seeing*), `:216` (step 3)
- Modify: `.claude/skills/zcrypto-daily-ops/SKILL.md` — the paragraph under `## What this is` (line 11) and the two paragraphs under `## 5. Evaluate the due reminders`
- Modify: `docs/open-topics/archive/T0103-reconciler-books-unfilled-silence-as-healed.md:36` (one sentence, in place)
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
The daily pass's report names this reminder under `## Reminders`: **OWED** when `zcrypto_reconcile_healable_gap_seconds_total` increased in the window — a new healable-gap event landed, so the count in step 1 is owed again — and `ok` when it did not. A Slack message in `#zcrypto` may prompt the same; the report is the trigger, the message a convenience ping that cannot be verified to exist from this side. It is not an alert — **nothing is wrong**. Unlike `refdata-sweep-due`, which is calendar-driven, this one is event-driven: qualifying days accrue only when the counter moves, and the pass reads the counter, never the ledger — step 1 is still yours.
```

Step 3 (line 216, `**Fewer than three qualifying days ⇒ do nothing except re-arm.**`) keeps its text; append this sentence to it:

```markdown
The re-arm is a convenience — the pass re-evaluates the counter every day whether or not the message lands.
```

- [ ] **Step 3: Pre-commit and commit the runbooks**

```bash
uv run pre-commit run -a 2>&1 | tail -12
uv run pytest tests/test_infra_alert_rules.py tests/test_ops_daily.py -q -k "runbook or anchor or description" 2>&1 | tail -3
git add infra/runbooks/reference-data.md infra/runbooks/ops.md
git commit -m "docs(runbooks): the daily report is the reminder trigger, the Slack message a convenience"
```

Expected: pre-commit clean after re-staging any mdformat rewrite; the anchor tests still pass (the `<a name=…>` lines are untouched — verify with `git diff HEAD~1 --stat` that no anchor line changed: `git diff HEAD~1 | grep '^[-+]<a name' | wc -l` prints `0`).

- [ ] **Step 4: The skill — step 5 evaluates the report, not the inbox**

In `.claude/skills/zcrypto-daily-ops/SKILL.md`, line 11's clause `It reads what fired, what the logs said, whether the dead-men are alive, whether the fleet's own series are present and fresh, and what was deployed` becomes:

```markdown
It reads what fired, what the logs said, whether the dead-men are alive and their descriptions still resolve, whether the fleet's own series are present and fresh, what was deployed, and which reminders are due
```

Replace the two paragraphs under `## 5. Evaluate the due reminders` (from `The runbook's SCHEDULED REMINDER sections` to `the day the trigger chain is broken is exactly the day the sweep goes unnoticed.`) with:

```markdown
The report's `## Reminders` section is the trigger — an **OWED** line is work, not decoration: open the section it names (`reference-data.md#refdata-sweep-due`, `ops.md#healable-threshold-rederivation-due`) and do it. The sweep's due-ness is computed from the register's last re-confirmation row plus the monthly cadence; the healable line says only whether the counter moved in the window — the count itself is still that section's step 1, from the ledger.

**Slack's scheduled message is a convenience ping, never the check.** Its scheduling cannot be listed or verified from this side, so "no message arrived" means nothing and a message that did arrive adds nothing the report did not already say. A reminder source the report could not read is exit 2, like any other.
```

Then:

```bash
uv run pre-commit run -a 2>&1 | tail -6
git add .claude/skills/zcrypto-daily-ops/SKILL.md
git commit -m "claude(daily_ops): step 5 evaluates the report's reminders; Slack is the convenience"
```

- [ ] **Step 5: T0103's archive — the belief re-trued in place (spec D6)**

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

- [ ] **Step 6: The memo (gitignored — edit, never stage)**

```bash
grep -n "armed OUTSIDE\|noisy warning" docs/memo.local.md
```

Append to the note that says the reminders are armed OUTSIDE the repo: ` — and cannot be verified from this side: the Slack MCP schedules but never lists, so an arming that failed to exist is invisible (T0103's 2026-08-27 reminder never landed); spec 00107 D1 moved the load onto read_reminders() and the message is a convenience.` Mark the `noisy warning` idea discharged by spec 00107 D4 in the memo's own convention for a discharged item. `git status --short` must not list the memo afterwards.

______________________________________________________________________

### Task 8: Closeout — the after reading, the guards that reach docs, the entry

**Files:**
- Modify: `docs/iterations-history-phase6.md` (append one entry)

**Interfaces:**
- Consumes: `<scratchpad>/pass-before.md` (Task 0), the mutation verdicts recorded in Tasks 1, 3 and 6.

- [ ] **Step 1: The after reading (main loop — it reads the vault)**

```bash
uv run python infra/scripts/ops-daily.py report --since 24h > "$SCRATCH/pass-after.md"; echo "rc=$?" | tee -a "$SCRATCH/pass-after.md"
sed -n '/## Reminders/,/## Deploys/p' "$SCRATCH/pass-after.md"; grep -n "description" "$SCRATCH/pass-after.md"; grep -n "capture WARNING\|/capture WARNING" "$SCRATCH/pass-after.md"
```

Expected: `rc=` printed immediately after the command; `## Reminders` shows both lines with `ok`/`OWED` and their runbook anchors; `## Dead-men` shows `- descriptions: all 10 carry a resolving runbook link and no internal token`; exit code equal to Task 0's unless a reminder source was unreadable (then 2, and the line names which — a finding to report, not to paper over). The `## Logs` section still shows the capture WARNING counts for the window: the INFO change reaches the hosts only with the next image rollout (out of scope here — the rollout skill owns it), so the count is expected to persist until then and the entry says so.

- [ ] **Step 2: The suites the branch can reach, and the guards that reach docs**

```bash
uv run pytest tests/test_ops_daily.py tests/test_capture_segment_writer.py tests/test_liquidations_coinalyze.py tests/test_infra_alert_rules.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py -q 2>&1 | tail -3
```

Expected: all passed. The token guard covers the new literals in `infra/scripts/ops_daily.py`; the citation guard covers every new test docstring.

- [ ] **Step 3: The iterations-history entry**

Load the `iteration-closeout` skill. Append to `docs/iterations-history-phase6.md` (Phase 6 — day-2 operations) a section `## 2026-MM-DD — iter-<N>: the signals that were silently absent — reminders, log levels, and the descriptions no test can reach (spec 00107)` where `<N>` is one above the file's highest `iter-` (157 as of writing — re-read the tail before writing). Bullets, one per change, in the file's existing shape:

- the lost reminder and the structural fact (no list/verify API), and D1's answer: `read_reminders()` computes due-ness daily from the register row and the healable counter; owed reports, unreadable exits 2 — with the before/after exit codes and the `## Reminders` lines from Steps 1 and Task 0;
- the three drop lines at INFO with the measured basis (bursts matching `zcrypto_capture_reconnects_total` 2 and 1; gap counter 0) and the note that the hosts emit WARNING until the next image rollout;
- the description check: two assertions per check, the true positive over today's ten (`tests/fixtures/healthchecks_descriptions.json`, fields name/tags/desc only), detection not generation and why;
- every guard mutation-probed: the verdicts from Tasks 1, 3 and 6 (three sites, four reminder mutations, three description mutations — all KILLED, or the one that was not and what was done);
- D6: T0103's sentence re-trued; the memo note extended; `archive/T0113` deliberately left.

No decisions-log entry: nothing here is subject-matter research (`decisions-log.md`'s gate).

```bash
uv run pre-commit run -a 2>&1 | tail -6
git add docs/iterations-history-phase6.md
git commit -m "docs(iterations-history): iter-<N> -- reminders, log levels, and the descriptions no test can reach"
```

- [ ] **Step 4: Review trailers and the branch's end**

`infra/scripts/review-trailer-audit.sh` must pass before push; the Task 1 commit's reviewer is at the Fable floor. Report the branch ready — the PR opens only on the user's word (`branch-workflow.md`). The rollout that carries the INFO change to the capture hosts is a separate attended step through `zcrypto-rollout-image`, not part of this branch.
