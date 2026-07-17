# Liquidations Poller Watermark (spec 00055, T0060, iter-102) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Coinalyze liquidations poller stops re-submitting already-persisted buckets at source — a per-coin watermark filters submission (never the fetch), killing ~15,800 writer-dedup WARNINGs/hour so any surviving drop is genuine signal.

**Architecture:** A `dict[str, int]` (coin → newest submitted bucket epoch-second) primed from the on-disk segment tree at startup, advanced in memory on each submit, threaded `_run → _poll_once → poll_cycle`. The 30h fetch window, the writer's dedup, and the late-event floor are all untouched (the module's overlap-safety invariant). No new durable state: a crash loses the watermark together with any unflushed rows; restart re-primes from disk and the wide window re-covers the tail.

**Tech Stack:** Python 3.14 (uv-locked), polars, pytest + Typer CliRunner. All work in the worktree `/home/zhaow/Projects/zcrypto-kraken-t0060` on branch `fix/t0060-poller-watermark`.

## Global Constraints

- **Working directory for every command: `/home/zhaow/Projects/zcrypto-kraken-t0060`** (a git worktree; the main checkout is on another branch — never touch it).
- The overlap-safety invariant is binding (spec 00055): `_CATCHUP_WINDOW_SECONDS` (30 h), `_CLOSE_MARGIN_SECONDS`, `_FINALIZE_LAG_SECONDS`, and all of `cli/capture/segment_writer.py`'s floor/dedup logic stay byte-identical. Only submission filtering is added.
- D6: no CLI flags, no env vars, no config keys, no README change.
- The new watermark must NOT collide with the existing `DiskWatermark` (a disk-free-space guard, `cli/capture/gap_monitor.py:144`). Naming: the dict is `bucket_watermarks` / parameter `watermarks`; the primer is `prime_bucket_watermarks`.
- `watermarks=None` (the default) must reproduce today's behavior exactly — the existing 21 tests in `tests/test_liquidations_coinalyze.py` must pass UNCHANGED; do not edit them.
- Python 3.14 / PEP 758: `except ValueError, IndexError:` without `as` is valid syntax — never "fix" it.
- Run tests via `uv run pytest …` from the worktree root. Full gate before each commit: `uv run pre-commit run -a` (re-run until clean, stage everything the hooks rewrote, never `--no-verify`).
- Commit messages: `<type>(<scope>): <subject>` with scope `liquidations`, ending with a blank line + `Co-Authored-By: <your actual model name> <noreply@anthropic.com>` (name your real model — never copy a version string from an example).
- Empirical ground truth (measured 2026-07-17, do not re-litigate): a restart + re-submit of a persisted current-hour bucket does NOT duplicate — `_open_hour` reseeds `_seen` from the hour's `.part` files (`segment_writer.py:614-616`, T0026 seeding). Variant with no clean close: unflushed rows never reach disk, so re-submit is recovery, not duplication.

---

### Task 1: `prime_bucket_watermarks` — read the newest persisted bucket per coin

**Files:**
- Modify: `cli/liquidations/coinalyze.py` (new module function + `import re`, `import polars as pl` if not present)
- Test: `tests/test_liquidations_coinalyze.py` (append new tests; touch no existing test)

**Interfaces:**
- Consumes: `SegmentWriter` segment layout `<data_dir>/<coin>/liquidations-1m/<YYYY>/<MM>/<DD>/<HH>.parquet` (finals) and `<HH>.part%04d.parquet` (parts); `LIQ_AGG_SCHEMA`'s `ts` column = bucket start, `pl.Datetime("us","UTC")`.
- Produces: `prime_bucket_watermarks(data_dir: Path, coins: list[str]) -> dict[str, int]` — coin → newest persisted bucket start (epoch s); a coin with no readable data is absent from the dict.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_liquidations_coinalyze.py` (reuse the file's existing imports; add what's missing):

```python
# --- prime_bucket_watermarks (spec 00055) -----------------------------------------------------


def test_prime_bucket_watermarks_empty_dir_returns_empty(tmp_path):
    assert prime_bucket_watermarks(tmp_path, ["BTC", "ETH"]) == {}


def test_prime_bucket_watermarks_reads_newest_part(tmp_path):
    # Persist two buckets an hour apart through the real writer (parts, no final).
    w = SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")
    t_old = 1784300400  # 2026-07-17 15:00:00 UTC
    t_new = 1784304000  # 2026-07-17 16:00:00 UTC
    for t in (t_old, t_new):
        w.append(
            {
                "ts": datetime.fromtimestamp(t, tz=UTC),
                "symbol": "BTCUSDT_PERP.A",
                "long_usd": 1.0,
                "short_usd": 2.0,
                "event_id": f"BTCUSDT_PERP.A-{t}",
            }
        )
    w.close()
    assert prime_bucket_watermarks(tmp_path, COINS) == {"BTC": t_new}


def test_prime_bucket_watermarks_reads_finalized_hour(tmp_path):
    w = SegmentWriter(tmp_path, "ETH", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")
    t = 1784304000
    w.append(
        {
            "ts": datetime.fromtimestamp(t, tz=UTC),
            "symbol": "ETHUSDT_PERP.A",
            "long_usd": 1.0,
            "short_usd": 2.0,
            "event_id": f"ETHUSDT_PERP.A-{t}",
        }
    )
    w.finalize_completed_hours(datetime.fromtimestamp(t + 7200, tz=UTC))  # forces the final
    w.close()
    assert prime_bucket_watermarks(tmp_path, COINS) == {"ETH": t}


def test_prime_bucket_watermarks_unreadable_newest_hour_omits_coin(tmp_path, caplog):
    hour_dir = tmp_path / "BTC" / "liquidations-1m" / "2026" / "07" / "17" / ""
    hour_dir.mkdir(parents=True)
    (hour_dir / "16.part0000.parquet").write_bytes(b"not parquet")
    with caplog.at_level(logging.WARNING):
        marks = prime_bucket_watermarks(tmp_path, COINS)
    assert marks == {}
    assert "priming failed" in caplog.text


def test_prime_bucket_watermarks_coins_are_independent(tmp_path):
    t = 1784304000
    for coin, symbol in (("BTC", "BTCUSDT_PERP.A"), ("DOGE", "DOGEUSDT_PERP.A")):
        w = SegmentWriter(tmp_path, coin, "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")
        w.append(
            {
                "ts": datetime.fromtimestamp(t, tz=UTC),
                "symbol": symbol,
                "long_usd": 1.0,
                "short_usd": 2.0,
                "event_id": f"{symbol}-{t}",
            }
        )
        w.close()
    assert prime_bucket_watermarks(tmp_path, COINS) == {"BTC": t, "DOGE": t}
```

Add the needed imports at the top of the test file if absent: `import logging`, `from cli.liquidations.coinalyze import COINS, prime_bucket_watermarks` (extend the existing `from cli.liquidations.coinalyze import …` line). Check the caplog logger name: `cli/logging.py`'s `get_logger("liquidations.coinalyze")` may or may not prefix `zcrypto.` — read one existing caplog-using test in the repo (`grep -rn "caplog.at_level" tests/ | head`) and match its logger-name idiom; if none exists for this logger, use `caplog.at_level(logging.WARNING)` without the logger kwarg and assert on `caplog.text`.

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_liquidations_coinalyze.py -k prime_bucket_watermarks -v`
Expected: FAIL — `ImportError: cannot import name 'prime_bucket_watermarks'`

- [ ] **Step 3: Implement** — in `cli/liquidations/coinalyze.py`, after the module constants (below `DEFAULT_POLL_SECONDS`), add:

```python
# Matches exactly the files SegmentWriter persists rows in: hour finals and parts. Sidecars
# (.sha256), .merging, .tmp and .corrupt names do not end in ".parquet" so rglob skips them.
_SEGMENT_FILE_RE = re.compile(r"/(\d{4})/(\d{2})/(\d{2})/(\d{2})\.(?:parquet|part\d{4}\.parquet)$")


def prime_bucket_watermarks(data_dir: Path, coins: list[str]) -> dict[str, int]:
    """Newest persisted bucket start (epoch s) per coin, read from the segment tree at startup.

    Fail-open per coin: a coin with no (readable) data is simply absent, so its whole catch-up
    window re-submits once and the writer's dedup/floor absorb it -- exactly the pre-watermark
    behavior, once.
    """
    marks: dict[str, int] = {}
    for coin in coins:
        by_hour: dict[tuple[str, ...], list[Path]] = {}
        for path in (data_dir / coin / "liquidations-1m").rglob("*.parquet"):
            m = _SEGMENT_FILE_RE.search(path.as_posix())
            if m is not None:
                by_hour.setdefault(m.groups(), []).append(path)
        if not by_hour:
            continue
        try:
            ts = pl.scan_parquet(by_hour[max(by_hour)]).select(pl.col("ts").max()).collect().item()
        except Exception:
            logger.warning(
                "bucket-watermark priming failed for %s -- its full window will re-submit once", coin
            )
            continue
        if ts is not None:
            marks[coin] = int(ts.timestamp())
    return marks
```

Add `import re` and `import polars as pl` to the module's imports if not already there (match the existing import grouping/style). Zero-padded path components make lexicographic `max(by_hour)` chronological.

- [ ] **Step 4: Run the new tests + the full liquidations file**

Run: `uv run pytest tests/test_liquidations_coinalyze.py -v`
Expected: all PASS (the 21 pre-existing tests untouched and green).

- [ ] **Step 5: Commit**

`uv run pre-commit run -a` until clean, stage everything, then:

```bash
git add cli/liquidations/coinalyze.py tests/test_liquidations_coinalyze.py
git commit -m "fix(liquidations): prime per-coin bucket watermarks from the segment tree

Co-Authored-By: <your actual model> <noreply@anthropic.com>"
```

---

### Task 2: watermark filtering in `poll_cycle` + the truthful cycle log

**Files:**
- Modify: `cli/liquidations/coinalyze.py` — `poll_cycle` (lines ~114-164), the module docstring (lines ~1-13), the statelessness comment (~52-54), the stale "24h" prose (poll_cycle docstring ~122 and comment ~52 — the window constant is 30 h)
- Test: `tests/test_liquidations_coinalyze.py` (append; touch no existing test)

**Interfaces:**
- Consumes: `prime_bucket_watermarks` from Task 1 (tests build the dict by hand — no coupling).
- Produces: `poll_cycle(api_key, coins, writers, *, watermarks: dict[str, int] | None = None, now=None, opener=…) -> int`. Semantics: a proven-closed bucket with `t <= watermarks.get(coin, -1)` is skipped BEFORE the writer (no dedup lookup, no log line); after a successful `writer.append`, `watermarks[coin] = max(t, watermarks.get(coin, -1))`. `watermarks=None` disables filtering entirely (today's behavior). Return value still counts rows submitted to a writer; the INFO line becomes `poll cycle: submitted=%d skipped_at_watermark=%d closed bucket(s)`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_liquidations_coinalyze.py`. Reuse the file's existing `_opener(body)` helper and canned-body shape (`[{"symbol": "BTCUSDT_PERP.A", "history": [{"t": …, "l": …, "s": …}]}]`) exactly as the existing tests do:

```python
# --- poll_cycle watermark filtering (spec 00055) ----------------------------------------------


def _btc_writer(tmp_path):
    return {"BTC": SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")}


def test_poll_cycle_skips_buckets_at_or_below_watermark(tmp_path):
    now = datetime(2026, 7, 17, 16, 30, tzinfo=UTC)
    t_covered = int(datetime(2026, 7, 17, 16, 0, tzinfo=UTC).timestamp())
    t_fresh = t_covered + 60
    body = [{"symbol": "BTCUSDT_PERP.A", "history": [
        {"t": t_covered, "l": 1.0, "s": 2.0},
        {"t": t_fresh, "l": 3.0, "s": 4.0},
    ]}]
    writers = _btc_writer(tmp_path)
    marks = {"BTC": t_covered}
    written = poll_cycle("key", ["BTC"], writers, watermarks=marks, now=now, opener=_opener(body))
    writers["BTC"].close()
    assert written == 1  # only the fresh bucket reached the writer
    parts = list(tmp_path.rglob("*.part*.parquet"))
    df = pl.concat([pl.read_parquet(p) for p in parts])
    assert df["event_id"].to_list() == [f"BTCUSDT_PERP.A-{t_fresh}"]
    assert marks == {"BTC": t_fresh}  # advanced on submit


def test_poll_cycle_second_cycle_is_silent_no_dedup_warnings(tmp_path, caplog):
    # The production symptom, reproduced and killed: an identical follow-up cycle must submit
    # nothing and trigger ZERO writer-level "dropping replayed event" warnings.
    now = datetime(2026, 7, 17, 16, 30, tzinfo=UTC)
    t = int(datetime(2026, 7, 17, 16, 0, tzinfo=UTC).timestamp())
    body = [{"symbol": "BTCUSDT_PERP.A", "history": [{"t": t, "l": 1.0, "s": 2.0}]}]
    writers = _btc_writer(tmp_path)
    marks: dict[str, int] = {}
    assert poll_cycle("key", ["BTC"], writers, watermarks=marks, now=now, opener=_opener(body)) == 1
    with caplog.at_level(logging.WARNING):
        again = poll_cycle("key", ["BTC"], writers, watermarks=marks, now=now, opener=_opener(body))
    writers["BTC"].close()
    assert again == 0
    assert "dropping replayed event" not in caplog.text


def test_poll_cycle_none_watermarks_preserves_resubmit_behavior(tmp_path, caplog):
    # watermarks=None is today's contract: re-submission reaches the writer and dedup drops it.
    now = datetime(2026, 7, 17, 16, 30, tzinfo=UTC)
    t = int(datetime(2026, 7, 17, 16, 0, tzinfo=UTC).timestamp())
    body = [{"symbol": "BTCUSDT_PERP.A", "history": [{"t": t, "l": 1.0, "s": 2.0}]}]
    writers = _btc_writer(tmp_path)
    poll_cycle("key", ["BTC"], writers, now=now, opener=_opener(body))
    with caplog.at_level(logging.WARNING):
        poll_cycle("key", ["BTC"], writers, now=now, opener=_opener(body))
    writers["BTC"].close()
    assert "dropping replayed event" in caplog.text


def test_poll_cycle_open_bucket_does_not_advance_watermark(tmp_path):
    now = datetime(2026, 7, 17, 16, 30, tzinfo=UTC)
    t_open = int(now.timestamp()) - 60  # closes at now-0s: NOT proven closed (margin 120s)
    body = [{"symbol": "BTCUSDT_PERP.A", "history": [{"t": t_open, "l": 1.0, "s": 2.0}]}]
    writers = _btc_writer(tmp_path)
    marks: dict[str, int] = {}
    written = poll_cycle("key", ["BTC"], writers, watermarks=marks, now=now, opener=_opener(body))
    writers["BTC"].close()
    assert written == 0
    assert marks == {}  # an unsubmitted bucket must never advance the mark


def test_poll_cycle_failure_mid_cycle_leaves_unsubmitted_coins_unadvanced(tmp_path):
    # Spec Verify names "a failed cycle": a malformed entry aborts the cycle (poll_cycle raises,
    # _poll_once catches). Marks advanced before the abort stand (those rows sit in their writer's
    # buffer); coins never reached must stay unadvanced so the next cycle re-covers them.
    now = datetime(2026, 7, 17, 16, 30, tzinfo=UTC)
    t = int(datetime(2026, 7, 17, 16, 0, tzinfo=UTC).timestamp())
    body = [
        {"symbol": "BTCUSDT_PERP.A", "history": [{"t": t, "l": 1.0, "s": 2.0}]},
        {"symbol": "ETHUSDT_PERP.A", "history": [{"t": t, "l": None, "s": 2.0}]},  # float(None) raises
    ]
    writers = {
        coin: SegmentWriter(tmp_path, coin, "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")
        for coin in ("BTC", "ETH")
    }
    marks: dict[str, int] = {}
    with pytest.raises(TypeError):
        poll_cycle("key", ["BTC", "ETH"], writers, watermarks=marks, now=now, opener=_opener(body))
    assert marks == {"BTC": t}  # BTC advanced (its row is buffered in its writer); ETH never did
    for w in writers.values():
        w.close()


def test_poll_cycle_logs_submitted_and_skipped_counts(tmp_path, caplog):
    now = datetime(2026, 7, 17, 16, 30, tzinfo=UTC)
    t = int(datetime(2026, 7, 17, 16, 0, tzinfo=UTC).timestamp())
    body = [{"symbol": "BTCUSDT_PERP.A", "history": [
        {"t": t, "l": 1.0, "s": 2.0},
        {"t": t + 60, "l": 3.0, "s": 4.0},
    ]}]
    writers = _btc_writer(tmp_path)
    with caplog.at_level(logging.INFO):
        poll_cycle("key", ["BTC"], writers, watermarks={"BTC": t}, now=now, opener=_opener(body))
    writers["BTC"].close()
    assert "submitted=1" in caplog.text
    assert "skipped_at_watermark=1" in caplog.text
```

NOTE: the INFO line moves from `_poll_once` into… no — it stays where it is. Read the current code first: the `submitted` INFO line lives in `_poll_once` (coinalyze.py:193), but the counts are produced inside `poll_cycle`. Change `poll_cycle` to return `(written, skipped)`? NO — keep the public return type `int` (existing tests assert on it). Instead: `poll_cycle` emits the new INFO line itself just before returning, and `_poll_once`'s old line 193 is DELETED (its information is now richer and closer to the source). The last test above then passes via `poll_cycle` directly. `skipped` is 0 whenever `watermarks is None`.

- [ ] **Step 2: Run to verify the new tests fail**

Run: `uv run pytest tests/test_liquidations_coinalyze.py -k "watermark or skips or silent or counts or unadvanced" -v`
(If `pytest` isn't already imported in the test file, add it for `pytest.raises`. The response-entry iteration in `poll_cycle` preserves body order, so BTC processes before the malformed ETH entry.)
Expected: FAIL — `TypeError: poll_cycle() got an unexpected keyword argument 'watermarks'`

- [ ] **Step 3: Implement** in `cli/liquidations/coinalyze.py`:

1. `poll_cycle` signature: `def poll_cycle(api_key: str, coins: list[str], writers: dict[str, SegmentWriter], *, watermarks: dict[str, int] | None = None, now: datetime | None = None, opener=urllib.request.urlopen) -> int:`
2. Inside the bucket loop (current lines ~150-162), after the proven-closed `continue` and before `writer.append`:

```python
            if watermarks is not None and t <= watermarks.get(coin, -1):
                skipped += 1
                continue  # already persisted (or submitted this run) -- never reaches the writer
```

   and after the `writer.append(...)` + `written += 1` lines:

```python
            if watermarks is not None:
                watermarks[coin] = max(t, watermarks.get(coin, -1))
```

   Initialize `skipped = 0` beside `written = 0`. `coin` is already in scope from the `symbol_to_coin` lookup.
3. Replace `_poll_once`'s INFO line (current line ~193) — delete it there and emit from `poll_cycle` immediately before `return written`:

```python
    logger.info(
        "poll cycle: submitted=%d skipped_at_watermark=%d closed bucket(s)", written, skipped
    )
```

4. Docstring/comment truth pass (all in this file, all made stale by THIS change):
   - Module docstring overlap-safety paragraph (lines ~9-13): rewrite to state the THREE-layer reality — the cycle still re-fetches the full 30 h window (do not narrow it); a per-coin bucket watermark (primed from disk at startup, advanced on submit) filters re-submissions at source; the writer's dedup (`_seen`) and late-event floor remain intact as the second and third mechanisms, and a `dropping replayed event` warning that still fires is now a genuine anomaly, not steady-state noise.
   - The "no 'since last cycle' state to track" comment (~52-54): update — the bucket watermark IS deliberate cross-cycle in-memory state; it is advisory (fail-open), never durable, and its loss only costs one window of re-submissions absorbed by dedup/floor.
   - The two "24h" prose spots touched by this edit (`poll_cycle` docstring ~122, comment ~52): correct to the actual 30 h window.
   - `poll_cycle`'s docstring: document the `watermarks` parameter contract (None = no filtering; mutated in place; advance only on successful submit).

- [ ] **Step 4: Run the whole test file**

Run: `uv run pytest tests/test_liquidations_coinalyze.py -v`
Expected: all PASS — including the 21 untouched pre-existing tests (their `poll_cycle(...)` calls hit `watermarks=None` and behave exactly as before; the one pre-existing test asserting the OLD info line text, if any, will surface here — if a pre-existing test asserts on "poll cycle submitted", update ONLY that assertion string to the new line, and say so in the report).

- [ ] **Step 5: Commit**

```bash
git add cli/liquidations/coinalyze.py tests/test_liquidations_coinalyze.py
git commit -m "fix(liquidations): filter re-submissions at source via per-coin bucket watermarks

Co-Authored-By: <your actual model> <noreply@anthropic.com>"
```

---

### Task 3: wire priming into `_run`/`_poll_once` + the D5 regression test

**Files:**
- Modify: `cli/liquidations/coinalyze.py` — `_poll_once` (~167-199), `_run` (~202-229)
- Test: `tests/test_liquidations_coinalyze.py` (append), `tests/test_capture_segment_writer.py` (append one regression test)

**Interfaces:**
- Consumes: `prime_bucket_watermarks` (Task 1), `poll_cycle(..., watermarks=...)` (Task 2).
- Produces: `_poll_once(api_key, writers, watermark, bucket_watermarks) -> bool` (new 4th positional param, the dict); `_run` primes once at startup — `bucket_watermarks = prime_bucket_watermarks(data_dir, COINS)` right after the writers dict — logs `primed bucket watermarks for %d/%d coin(s)` at INFO, and passes the dict into every `_poll_once` call.

- [ ] **Step 1: Write the failing tests.** In `tests/test_liquidations_coinalyze.py`:

```python
def test_run_primes_watermarks_and_threads_them_to_poll_cycle(tmp_path, monkeypatch):
    # Persist one bucket, then boot _run: the primed dict must reach poll_cycle so the very
    # first cycle after a restart already skips what is on disk.
    t = 1784304000
    w = SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")
    w.append(
        {
            "ts": datetime.fromtimestamp(t, tz=UTC),
            "symbol": "BTCUSDT_PERP.A",
            "long_usd": 1.0,
            "short_usd": 2.0,
            "event_id": f"BTCUSDT_PERP.A-{t}",
        }
    )
    w.close()

    seen = {}

    def fake_poll_cycle(api_key, coins, writers, *, watermarks=None, now=None, opener=None):
        seen["watermarks"] = watermarks
        return 0

    monkeypatch.setattr(mod, "poll_cycle", fake_poll_cycle)
    monkeypatch.setattr(mod, "_sleep", lambda seconds: None)
    mod._run(tmp_path, "key", 300, None, duration=0)
    assert seen["watermarks"] == {"BTC": t}
```

Use the test file's existing idiom for referring to the module (the existing command tests monkeypatch `cli.liquidations.coinalyze.poll_cycle` — mirror exactly how they import/reference the module, e.g. `import cli.liquidations.coinalyze as mod` if that alias isn't already established).

In `tests/test_capture_segment_writer.py`, append (adapting to that file's local helpers — it has an autouse pinned-clock fixture; construct timestamps its way, e.g. with its `_ts` helper if suitable, otherwise explicit UTC datetimes within the pinned clock's plausibility window):

```python
def test_restart_reseeds_dedup_keys_from_open_hour_parts(tmp_path, caplog):
    # Spec 00055 D5 (measured 2026-07-17): a dedup-keyed writer restarted over an open hour with
    # flushed parts reseeds _seen from disk, so a re-submitted event is dropped, never duplicated.
    # This is the anomaly-detector backstop the liquidations watermark relies on.
    event = {
        "ts": _ts(10, 0, 0),
        "symbol": "BTCUSDT_PERP.A",
        "long_usd": 1.0,
        "short_usd": 2.0,
        "event_id": "BTCUSDT_PERP.A-1",
    }
    w1 = SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")
    w1.append(dict(event))
    w1.close()

    w2 = SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")
    with caplog.at_level(logging.WARNING):
        w2.append(dict(event))
    w2.close()
    assert "dropping replayed event" in caplog.text

    parts = sorted(tmp_path.rglob("*.part*.parquet"))
    assert sum(pl.read_parquet(p).height for p in parts) == 1  # one row, not two
```

Verify `LIQ_AGG_SCHEMA` is importable in that file (it imports from `cli.capture.segment_writer` already — extend the import line) and that `_ts(10, 0, 0)` lands inside the pinned clock's accepted window (read the fixture at the top of the file first; if `_ts` produces hour-10 events the other tests use freely, it is safe).

- [ ] **Step 2: Run to verify both fail**

Run: `uv run pytest tests/test_liquidations_coinalyze.py::test_run_primes_watermarks_and_threads_them_to_poll_cycle tests/test_capture_segment_writer.py::test_restart_reseeds_dedup_keys_from_open_hour_parts -v`
Expected: the first FAILS (`_run`/`_poll_once` don't thread the dict yet — `seen` stays empty or TypeError). The second may already PASS (it pins existing behavior) — that is acceptable for a regression pin; verify it CAN fail by temporarily asserting `== 2` (run, watch it fail, restore `== 1`). State in the report that the mutation check was done.

- [ ] **Step 3: Implement** in `cli/liquidations/coinalyze.py`:

1. `_poll_once` signature → `def _poll_once(api_key: str, writers: dict[str, SegmentWriter], watermark: DiskWatermark, bucket_watermarks: dict[str, int]) -> bool:` and its `poll_cycle` call → `written = poll_cycle(api_key, COINS, writers, watermarks=bucket_watermarks)`. (The old INFO line here is already gone per Task 2.)
2. `_run`: after the writers dict (line ~204) and `DiskWatermark` construction:

```python
    bucket_watermarks = prime_bucket_watermarks(data_dir, COINS)
    logger.info("primed bucket watermarks for %d/%d coin(s)", len(bucket_watermarks), len(COINS))
```

   and the loop's call → `ok = _poll_once(api_key, writers, watermark, bucket_watermarks)`.

- [ ] **Step 4: Run the FULL fast suite**

Run: `uv run pytest`
Expected: all PASS in ~40 s (the data-dependent regression tests skip without `data/ohlc-full` — in this worktree that dir is absent, so the run stays fast). Any pre-existing test of `_poll_once` will fail on the new positional arg — update ONLY the call sites in those tests (adding `, {}` or a primed dict as appropriate), never their assertions, and list every such edit in the report.

- [ ] **Step 5: Commit**

```bash
git add cli/liquidations/coinalyze.py tests/test_liquidations_coinalyze.py tests/test_capture_segment_writer.py
git commit -m "fix(liquidations): prime bucket watermarks at startup and thread them through the poll loop

Co-Authored-By: <your actual model> <noreply@anthropic.com>"
```

---

### Task 4: closeout — T0060, spec addendum, iterations-history (orchestrator-assisted docs)

**Files:**
- Modify: `docs/open-topics/T0060-ops-log-pipeline-unusable-and-noisy.md`
- Modify: `docs/specs/00055-liquidations-poller-watermark-design.md` (D5 outcome addendum only)
- Modify: `docs/iterations-history-phase1.md` (append iter-102 entry)
- Do NOT touch: `README.md` (D6 — no user-facing surface changed), `docs/open-topics/README.md` status position (T0060 stays `partial`; its index bullet stays in `### Partially done`).

- [ ] **Step 1: T0060 update.** In the topic file: extend `## Done so far` with the source fix (this branch's commits + spec/plan links) and the owner-provided Grafana Cloud figures (2026-07-17: Current Billable Logs — Process 621.1 MiB, Write 61.9 MiB, Query 166 MiB against the free tier's 50 GB/month; ≈1.2 GiB/month pace ≈ 2.4% of cap — ingest volume is NOT a forcing constraint; the fix's rationale is signal-to-noise). Trim `## Suggested next steps` to the true residual: deploy the fixed poller image to the ops node (attended; REST-lookback makes the restart loss-free) and verify post-deploy that `dropping replayed event` on ops falls from ~15,800/h to ~0 while `skipped_at_watermark` carries the count — with a `ripe_when: the fix PR is merged and a capture-image build containing it is available` frontmatter trigger if the topic's frontmatter doesn't already express this. Keep `status: partial`.
- [ ] **Step 2: Spec D5 addendum.** Append a short `## D5 outcome (measured 2026-07-17)` section to the spec: no duplication — `_open_hour` reseeds `_seen` from the open hour's `.part` files (T0026 seeding, `segment_writer.py:614-616`); abrupt-death variant loses the unflushed buffer, so re-submission is recovery; regression pinned by `test_restart_reseeds_dedup_keys_from_open_hour_parts`.
- [ ] **Step 3: iterations-history.** Append to `docs/iterations-history-phase1.md` (under its existing continuation divider if the phase is closed — read the file's tail first and follow its established pattern):

```markdown
## 2026-07-17 — iter-102: the liquidations poller stops re-submitting at source (spec 00055, T0060)

- Per-coin bucket watermarks (`prime_bucket_watermarks` + `poll_cycle(watermarks=…)` in `cli/liquidations/coinalyze.py`): primed from the segment tree at startup, advanced in-memory on submit; already-persisted buckets are skipped before the writer, eliminating the ~15,800/h `dropping replayed event` WARNINGs on ops. The 30 h fetch window, writer dedup, and late-event floor are untouched — surviving dedup drops are now genuine anomalies.
- Cycle log truth: `poll cycle: submitted=N skipped_at_watermark=M closed bucket(s)` (was a bare submitted count annotated "re-submissions are dropped by dedup/floor"); startup logs `primed bucket watermarks for N/10 coin(s)`.
- Spec 00055 D5 answered empirically: no restart-duplication — dedup keys reseed from open-hour parts (T0026); pinned by a new regression test in `tests/test_capture_segment_writer.py`.
- No CLI/config surface change; deploy to ops is a follow-up tracked in T0060 (ripe when a capture image containing the fix exists).
```

- [ ] **Step 4: Gate + commit**

`uv run pre-commit run -a` until clean (mdformat will touch the markdown — restage), then:

```bash
git add docs/
git commit -m "docs(liquidations): closeout -- T0060 progress, spec 00055 D5 outcome, changelog

Co-Authored-By: <your actual model> <noreply@anthropic.com>"
```

---

### Post-plan (orchestrator, not a subagent task)

Final whole-branch review (most capable model), `Reviewed-by:` trailers amended per commit while local, push once, PR into `develop` titled `fix(liquidations): iter-102 — the poller stops re-submitting at source (spec 00055)` with body per `pull-requests.md` (Summary / Spec+Plan links / Changes / Test plan / Follow-ups referencing T0060 only / Checklist / aggregated trailers). Deploy is OUT of scope (spec Non-goals).
