# REST trade-backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the canonical trade stream provably complete and duplicate-free (spec `00053`): `cli/trades/` + `zcrypto archive backfill-trades`, minting healed hours into the existing reconciled overlay from Kraken's public REST `/Trades`, recovering the measured 17,362 missing trades and collapsing 10,986 duplicates — without touching the live capture daemon.

**Architecture:** an offline pass beside the reconciler on the NAS. Read canonical trades (reconciled-first) → detect `trade_id` gaps + duplicates from the archive itself → fetch only the missing id ranges from REST → `union_trades` → atomically mint the affected hours into `capture-reconciled` with provenance. Consumers are unchanged: `canonical_segments(primary, reconciled)` already reads reconciled-first.

**Tech Stack:** polars, `urllib.request` (injectable opener — no new dependency), the existing `union_trades`/`canonical_segments`/`mint_hour` machinery, the NAS `archive-pull` entrypoint loop.

## Global Constraints

- Spec `00053` D1–D12 govern; decisions are logged `[iter-100]` (phase-1 running log). The invariant, placement, and scope are **not** re-litigated here.
- **The raw mirrors are NEVER written.** Minting is overlay-only (`capture-reconciled`).
- **Never fabricate.** An id REST will not serve is recorded as *unrecoverable*; it is never invented and never silently closed. A residual gap is a finding, not a failure.
- **The manifest is not the check; the invariant is.** A minted hour's `.sha256` is regenerated, so it hash-verifies while being wrong (this is exactly how T0026 stayed invisible). Every mint is followed by an invariant re-check.
- Only hours **older than `H+2h`** are considered (the reconciler's settle rule). The in-flight hour is untouchable.
- The **first and last** `trade_id` per pair bound the captured span; **neither endpoint is a gap**.
- Kraken REST: `since` takes **seconds**, the `last` cursor returns **nanoseconds**. Mixing them silently rewinds or skips a page.
- REST row shape: `[price, volume, time, side(b|s), ord_type(m|l), misc, trade_id]`, 1000 rows/page.
- Normalization to `TRADE_SCHEMA`: `b`→`buy`, `s`→`sell`, `m`→`market`, `l`→`limit`, `XXBTZEUR`→`BTC/EUR`, epoch float→`Datetime("us","UTC")`, str→`Float64`. A REST-sourced row must be **indistinguishable** from a WS-captured row for the same trade.
- Loggers `get_logger("trades.<module>")`; TDD (failing test first); `uv run pre-commit run -a` is the gate; every commit subagent-reviewed before push; attended tasks are orchestrator-only.
- Tests **never** touch the network: inject `opener` (the `cli/ohlc/fetch.py` pattern).

## File structure

| File | Responsibility |
| -- | -- |
| `cli/trades/__init__.py` | Package exports. |
| `cli/trades/errors.py` | `TradeBackfillError` (mirrors `cli/ohlc/errors.py::OHLCError`). |
| `cli/trades/rest.py` | Kraken `/0/public/Trades`: paginate, normalize to `TRADE_SCHEMA`. No archive knowledge. |
| `cli/trades/gaps.py` | Pure detection: gaps + duplicates from a `trade_id` series. No I/O. |
| `cli/trades/backfill.py` | Orchestration: canonical → detect → fetch → union → mint → re-check. |
| `cli/archive/mint.py` (modify) | Extend `mint_hour` with `tool` / `extra_provenance` / `replace`. |
| `cli/archive/command.py` (modify) | Register `backfill-trades` on the existing `archive` Typer app. |
| `infra/nas/pull-entrypoint.sh` (modify) | One daily-gated step in the existing loop + textfile metrics. |

---

### Task 1: `cli/trades/rest.py` — the Kraken `/Trades` client (TDD)

**Files:** Create `cli/trades/__init__.py`, `cli/trades/errors.py`, `cli/trades/rest.py`; Test `tests/test_trades_rest.py`.

**Interfaces (produces):**
- `KRAKEN_ALTNAME: dict[str, str]` — canonical→REST pair (`{"BTC/EUR": "XBTEUR", "DOGE/EUR": "XDGEUR", ...}`).
- `fetch_trades(pair: str, since: datetime, *, until: datetime | None = None, opener=urllib.request.urlopen, sleep=time.sleep) -> pl.DataFrame` — rows in `TRADE_SCHEMA`, ascending `trade_id`, `symbol` = the canonical pair. Paginates until `until` (or the page is short). Raises `TradeBackfillError`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_trades_rest.py
import datetime as dt
import io
import json
import polars as pl
import pytest
from cli.capture.segment_writer import TRADE_SCHEMA
from cli.trades.errors import TradeBackfillError
from cli.trades.rest import fetch_trades


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _page(rows, last):
    return _Resp(json.dumps({"error": [], "result": {"XXBTZEUR": rows, "last": str(last)}}).encode())


ROW = ["56062.10000", "0.00008918", 1783735200.0737085, "b", "m", "", 108052012]


def test_normalizes_a_row_into_trade_schema():
    calls = []

    def opener(url, timeout=None):
        calls.append(url)
        return _page([ROW], 1783735200073708500)

    df = fetch_trades("BTC/EUR", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=opener)
    assert list(df.schema.items()) == list(pl.Schema(TRADE_SCHEMA).items())
    r = df.row(0, named=True)
    assert r["symbol"] == "BTC/EUR"          # canonical, not XXBTZEUR
    assert r["side"] == "buy"                # b -> buy
    assert r["ord_type"] == "market"         # m -> market
    assert r["price"] == 56062.1 and r["qty"] == 0.00008918
    assert r["trade_id"] == 108052012
    assert r["ts"] == dt.datetime(2026, 7, 11, 2, 0, 0, 73708, tzinfo=dt.UTC)
    assert "pair=XBTEUR" in calls[0] and "since=1783735200" in calls[0]  # SECONDS on the way in


def test_sell_and_limit_map_too():
    df = fetch_trades(
        "BTC/EUR",
        dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC),
        opener=lambda url, timeout=None: _page([["1", "2", 1783735200.0, "s", "l", "", 7]], 1783735200000000000),
    )
    assert df.row(0, named=True)["side"] == "sell"
    assert df.row(0, named=True)["ord_type"] == "limit"


def test_paginates_using_the_nanosecond_cursor_as_seconds():
    """The `last` cursor is NANOSECONDS; `since` takes SECONDS. Feeding ns back raw would jump
    ~31 years ahead and silently return nothing."""
    urls = []
    pages = [
        _page([[str(i), "1", 1783735200.0 + i, "b", "m", "", 100 + i] for i in range(1000)], 1783735201000000000),
        _page([["1", "1", 1783735300.0, "b", "m", "", 2000]], 1783735300000000000),
    ]

    def opener(url, timeout=None):
        urls.append(url)
        return pages[len(urls) - 1]

    df = fetch_trades("BTC/EUR", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=opener, sleep=lambda _: None)
    assert len(urls) == 2
    assert "since=1783735201" in urls[1]  # ns cursor converted to seconds, NOT passed through
    assert df.height == 1001
    assert df["trade_id"].is_sorted()


def test_stops_at_until_without_fetching_further():
    urls = []

    def opener(url, timeout=None):
        urls.append(url)
        return _page([[str(i), "1", 1783735200.0 + i, "b", "m", "", 100 + i] for i in range(1000)], 1783739000000000000)

    fetch_trades(
        "BTC/EUR",
        dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC),
        until=dt.datetime(2026, 7, 11, 2, 0, 30, tzinfo=dt.UTC),
        opener=opener,
        sleep=lambda _: None,
    )
    assert len(urls) == 1  # page already covers `until`; no second call


def test_kraken_error_array_raises():
    body = _Resp(json.dumps({"error": ["EGeneral:Too many requests"], "result": {}}).encode())
    with pytest.raises(TradeBackfillError, match="Too many requests"):
        fetch_trades("BTC/EUR", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=lambda u, timeout=None: body)


def test_unknown_pair_raises_before_any_request():
    with pytest.raises(TradeBackfillError, match="no Kraken altname"):
        fetch_trades("NOPE/EUR", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=lambda u, timeout=None: _page([], 0))
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_trades_rest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.trades'`

- [ ] **Step 3: Implement**

```python
# cli/trades/errors.py
class TradeBackfillError(Exception):
    """A trade-backfill transport, payload, or configuration failure."""
```

```python
# cli/trades/rest.py
from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request

import polars as pl

from cli.capture.segment_writer import TRADE_SCHEMA
from cli.logging import get_logger
from cli.trades.errors import TradeBackfillError

logger = get_logger("trades.rest")

_BASE_URL = "https://api.kraken.com/0/public/Trades"
_TIMEOUT_SECONDS = 30
_PAGE_ROWS = 1000          # Kraken's page size; a SHORT page means the series is exhausted
_MIN_INTERVAL_SECONDS = 1.5  # public-endpoint courtesy; ~200-400 calls for the historical sweep

# Canonical -> Kraken REST altname. Kraken answers under its OWN key (XBTEUR -> XXBTZEUR), so the
# response key is read positionally, never assumed.
KRAKEN_ALTNAME: dict[str, str] = {
    "BTC/EUR": "XBTEUR", "ETH/EUR": "ETHEUR", "SOL/EUR": "SOLEUR", "XRP/EUR": "XRPEUR",
    "ADA/EUR": "ADAEUR", "DOT/EUR": "DOTEUR", "LINK/EUR": "LINKEUR", "LTC/EUR": "LTCEUR",
    "DOGE/EUR": "XDGEUR", "AVAX/EUR": "AVAXEUR",
}
_SIDE = {"b": "buy", "s": "sell"}
_ORD_TYPE = {"m": "market", "l": "limit"}


def _rows_to_frame(rows: list[list], pair: str) -> pl.DataFrame:
    recs = []
    for r in rows:
        try:
            recs.append(
                {
                    "ts": dt.datetime.fromtimestamp(float(r[2]), dt.UTC),
                    "symbol": pair,
                    "side": _SIDE[r[3]],
                    "price": float(r[0]),
                    "qty": float(r[1]),
                    "ord_type": _ORD_TYPE[r[4]],
                    "trade_id": int(r[6]),
                }
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise TradeBackfillError(f"unexpected REST trade row for {pair}: {r!r} ({exc})") from exc
    return pl.DataFrame(recs, schema=TRADE_SCHEMA)


def fetch_trades(
    pair: str,
    since: dt.datetime,
    *,
    until: dt.datetime | None = None,
    opener=urllib.request.urlopen,
    sleep=time.sleep,
) -> pl.DataFrame:
    """Fetch Kraken public trades for `pair` from `since` (inclusive), paginating to `until`.

    Returns rows in `TRADE_SCHEMA`, ascending `trade_id`, `symbol` set to the CANONICAL pair — a
    REST-sourced row is byte-comparable with a WS-captured one for the same trade, which is what
    makes dedupe-on-`trade_id` safe (spec 00053 D6).
    """
    altname = KRAKEN_ALTNAME.get(pair)
    if altname is None:
        raise TradeBackfillError(f"no Kraken altname for pair {pair!r}")

    cursor_s = int(since.timestamp())
    frames: list[pl.DataFrame] = []
    while True:
        url = f"{_BASE_URL}?pair={altname}&since={cursor_s}"
        try:
            with opener(url, timeout=_TIMEOUT_SECONDS) as response:
                payload = json.load(response)
        except (urllib.error.URLError, OSError) as exc:
            raise TradeBackfillError(f"transport error fetching trades for {pair}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise TradeBackfillError(f"invalid JSON fetching trades for {pair}: {exc}") from exc

        errors = payload.get("error") or []
        if errors:
            raise TradeBackfillError(f"Kraken error fetching trades for {pair}: {errors}")
        result = payload.get("result") or {}
        series_key = next((k for k in result if k != "last"), None)
        if series_key is None:
            raise TradeBackfillError(f"no trade series in REST result for {pair}: keys={list(result)}")
        rows = result[series_key]
        if not rows:
            break

        frame = _rows_to_frame(rows, pair)
        frames.append(frame)

        newest = frame["ts"].max()
        if until is not None and newest >= until:
            break
        if len(rows) < _PAGE_ROWS:
            break  # short page: the series is exhausted

        # `last` is NANOSECONDS; `since` is SECONDS. Passing it through raw lands ~31 years ahead
        # and returns an empty page forever.
        cursor_s = int(int(result["last"]) // 1_000_000_000)
        sleep(_MIN_INTERVAL_SECONDS)

    if not frames:
        return pl.DataFrame([], schema=TRADE_SCHEMA)
    return pl.concat(frames).unique(subset=["trade_id"], keep="first").sort("trade_id")
```

```python
# cli/trades/__init__.py
from cli.trades.errors import TradeBackfillError
from cli.trades.rest import KRAKEN_ALTNAME, fetch_trades

__all__ = ["KRAKEN_ALTNAME", "TradeBackfillError", "fetch_trades"]
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_trades_rest.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Gate + commit**

```bash
uv run pre-commit run -a
git add cli/trades tests/test_trades_rest.py
git commit -m "feat(trades): Kraken REST /Trades client with schema normalization (spec 00053 Task 1)"
```

---

### Task 2: `cli/trades/gaps.py` — the pure detector (TDD)

**Files:** Create `cli/trades/gaps.py`; Test `tests/test_trades_gaps.py`.

**Interfaces (produces):**
- `@dataclass(frozen=True) IdGap: after_id: int; before_id: int; ts_lo: datetime; ts_hi: datetime` — `missing` property = `before_id - after_id - 1`.
- `detect(frame: pl.DataFrame) -> Detection` where `@dataclass(frozen=True) Detection: gaps: list[IdGap]; duplicate_ids: list[int]; rows: int; unique: int; span: int; missing: int`.

Consumes `TRADE_SCHEMA` frames (needs only `ts` + `trade_id`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_trades_gaps.py
import datetime as dt
import polars as pl
from cli.capture.segment_writer import TRADE_SCHEMA
from cli.trades.gaps import detect

T0 = dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC)


def _f(ids):
    return pl.DataFrame(
        [
            {"ts": T0 + dt.timedelta(seconds=i), "symbol": "BTC/EUR", "side": "buy",
             "price": 1.0, "qty": 1.0, "ord_type": "market", "trade_id": t}
            for i, t in enumerate(ids)
        ],
        schema=TRADE_SCHEMA,
    )


def test_contiguous_stream_has_no_gaps_and_no_duplicates():
    d = detect(_f([10, 11, 12, 13]))
    assert d.gaps == [] and d.duplicate_ids == []
    assert (d.rows, d.unique, d.span, d.missing) == (4, 4, 4, 0)


def test_single_gap_is_reported_with_its_bracketing_timestamps():
    d = detect(_f([10, 11, 15, 16]))
    assert len(d.gaps) == 1
    g = d.gaps[0]
    assert (g.after_id, g.before_id, g.missing) == (11, 15, 3)
    assert g.ts_lo == T0 + dt.timedelta(seconds=1) and g.ts_hi == T0 + dt.timedelta(seconds=2)
    assert d.missing == 3


def test_multiple_gaps():
    d = detect(_f([1, 2, 5, 6, 9]))
    assert [(g.after_id, g.before_id) for g in d.gaps] == [(2, 5), (6, 9)]
    assert d.missing == 4  # 3,4 + 7,8


def test_duplicates_are_reported_and_never_counted_as_gaps():
    """v1 of the exploratory probe conflated these: sorted duplicates give (x, x), which trips a
    naive `b != a+1` and yields a negative-width 'gap'."""
    d = detect(_f([10, 11, 11, 12]))
    assert d.duplicate_ids == [11]
    assert d.gaps == []
    assert (d.rows, d.unique, d.missing) == (4, 3, 0)


def test_gap_widths_always_sum_to_missing():
    d = detect(_f([1, 5, 6, 20]))
    assert sum(g.missing for g in d.gaps) == d.missing


def test_endpoints_are_never_gaps():
    """The first id is capture-start, the last is the live edge. Absence outside the span is not
    loss (spec 00053 D1)."""
    d = detect(_f([100, 101, 102]))
    assert d.gaps == [] and d.span == 3


def test_empty_frame_is_inert():
    d = detect(pl.DataFrame([], schema=TRADE_SCHEMA))
    assert d.gaps == [] and d.duplicate_ids == [] and (d.rows, d.unique, d.span, d.missing) == (0, 0, 0, 0)


def test_unsorted_input_is_handled():
    d = detect(_f([12, 10, 11]))
    assert d.gaps == [] and d.missing == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_trades_gaps.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.trades.gaps'`

- [ ] **Step 3: Implement**

```python
# cli/trades/gaps.py
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class IdGap:
    """A contiguous run of missing `trade_id`s, bracketed by the ids/timestamps that survive.

    `ts_lo`/`ts_hi` are the timestamps of `after_id`/`before_id` — the fetch window, since REST is
    queried by time, not by id.
    """

    after_id: int
    before_id: int
    ts_lo: dt.datetime
    ts_hi: dt.datetime

    @property
    def missing(self) -> int:
        return self.before_id - self.after_id - 1


@dataclass(frozen=True)
class Detection:
    gaps: list[IdGap]
    duplicate_ids: list[int]
    rows: int
    unique: int
    span: int
    missing: int


def detect(frame: pl.DataFrame) -> Detection:
    """Find missing and duplicated `trade_id`s in one pair's trades.

    Kraken's `trade_id` is DENSE and per-pair monotone (spec 00053 D1, verified empirically), so a
    hole in the sequence IS missing data — provable with no REST call. The span is bounded by the
    first and last observed id: neither endpoint is a gap (capture-start / the live edge).
    """
    if frame.height == 0:
        return Detection([], [], 0, 0, 0, 0)

    df = frame.select("ts", "trade_id").sort("trade_id")
    ids = df["trade_id"].to_list()

    # Duplicates first, and SEPARATELY from gaps: on a sorted series a duplicate is (x, x), which a
    # naive `b != a+1` reads as a negative-width gap.
    dup_ids = df.group_by("trade_id").len().filter(pl.col("len") > 1)["trade_id"].sort().to_list()

    first = df.unique(subset=["trade_id"], keep="first").sort("trade_id")
    uids = first["trade_id"].to_list()
    tss = first["ts"].to_list()

    gaps = [
        IdGap(after_id=a, before_id=b, ts_lo=tss[i], ts_hi=tss[i + 1])
        for i, (a, b) in enumerate(zip(uids, uids[1:], strict=False))
        if b > a + 1
    ]
    span = uids[-1] - uids[0] + 1
    missing = span - len(uids)
    assert sum(g.missing for g in gaps) == missing, "gap widths must sum to the missing count"
    return Detection(gaps, dup_ids, len(ids), len(uids), span, missing)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_trades_gaps.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Gate + commit**

```bash
uv run pre-commit run -a
git add cli/trades/gaps.py tests/test_trades_gaps.py
git commit -m "feat(trades): trade_id gap + duplicate detector (spec 00053 Task 2)"
```

---

### Task 3: extend `mint_hour` for a non-reconciler caller (TDD)

**Why:** `cli/archive/mint.py::mint_hour` is reconciler-shaped — its provenance hardcodes `"tool": "zcrypto archive reconcile"`, and it refuses to re-mint (`FileExistsError`), which blocks the legitimate retry of a gap recorded unrecoverable on an earlier run (spec `00053` D10). Three back-compatible optional params fix both without disturbing the reconciler.

**Files:** Modify `cli/archive/mint.py` (`mint_hour` signature + provenance dict + the two `final.exists()` guards); Test `tests/test_archive_mint.py` (append).

**Interfaces (produces):** `mint_hour(..., tool: str = "zcrypto archive reconcile", extra_provenance: dict | None = None, replace: bool = False) -> Path`. Defaults preserve today's behaviour exactly.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_archive_mint.py`; reuse that file's existing block/frame fixtures)

```python
def test_tool_defaults_to_reconcile_and_is_overridable(tmp_path):
    hour = dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC)
    p = mint_hour(tmp_path, "BTC/EUR", "trades", hour, [_trade_block()],
                  gaps_healed=[], residual_gaps=[], schema=TRADE_SCHEMA, tool_version="t")
    prov = json.loads(p.with_name("02.provenance.json").read_text())
    assert prov["tool"] == "zcrypto archive reconcile"

    p2 = mint_hour(tmp_path, "ETH/EUR", "trades", hour, [_trade_block()],
                   gaps_healed=[], residual_gaps=[], schema=TRADE_SCHEMA, tool_version="t",
                   tool="zcrypto archive backfill-trades")
    prov2 = json.loads(p2.with_name("02.provenance.json").read_text())
    assert prov2["tool"] == "zcrypto archive backfill-trades"


def test_extra_provenance_is_merged(tmp_path):
    hour = dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC)
    p = mint_hour(tmp_path, "BTC/EUR", "trades", hour, [_trade_block()],
                  gaps_healed=[], residual_gaps=[], schema=TRADE_SCHEMA, tool_version="t",
                  extra_provenance={"recovered_id_ranges": [[11, 14]], "deduped_rows": 2})
    prov = json.loads(p.with_name("02.provenance.json").read_text())
    assert prov["recovered_id_ranges"] == [[11, 14]] and prov["deduped_rows"] == 2
    assert prov["sha256"] and prov["hour"]  # base fields survive the merge


def test_replace_false_still_refuses_an_existing_final(tmp_path):
    hour = dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC)
    mint_hour(tmp_path, "BTC/EUR", "trades", hour, [_trade_block()],
              gaps_healed=[], residual_gaps=[], schema=TRADE_SCHEMA, tool_version="t")
    with pytest.raises(FileExistsError):
        mint_hour(tmp_path, "BTC/EUR", "trades", hour, [_trade_block()],
                  gaps_healed=[], residual_gaps=[], schema=TRADE_SCHEMA, tool_version="t")


def test_replace_true_re_mints_and_the_manifest_tracks_the_new_bytes(tmp_path):
    """The retry case: a gap recorded unrecoverable on an earlier run is recovered later, so the
    hour must be re-minted from the fuller union."""
    hour = dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC)
    mint_hour(tmp_path, "BTC/EUR", "trades", hour, [_trade_block(ids=[10, 11])],
              gaps_healed=[], residual_gaps=[], schema=TRADE_SCHEMA, tool_version="t")
    p = mint_hour(tmp_path, "BTC/EUR", "trades", hour, [_trade_block(ids=[10, 11, 12])],
                  gaps_healed=[], residual_gaps=[], schema=TRADE_SCHEMA, tool_version="t", replace=True)
    assert pl.read_parquet(p).height == 3
    assert verify_manifest(p) is True  # sidecar regenerated for the NEW bytes
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_archive_mint.py -k "tool or extra_provenance or replace" -v`
Expected: FAIL — `TypeError: mint_hour() got an unexpected keyword argument 'tool'`

- [ ] **Step 3: Implement** — in `cli/archive/mint.py`:

Add to the signature (after `tool_version: str`):

```python
    tool: str = "zcrypto archive reconcile",
    extra_provenance: dict | None = None,
    replace: bool = False,
```

Guard the entry check (the `if final.exists(): raise FileExistsError(f"reconciled final already minted: {final}")` near the top):

```python
    if final.exists() and not replace:
        raise FileExistsError(f"reconciled final already minted: {final}")
```

Build provenance with the caller's tool and merged extras (replace `"tool": "zcrypto archive reconcile",` in the dict literal):

```python
        "tool": tool,
        "version": tool_version,
    }
    # Extras are merged, never allowed to shadow the base record: a caller must not be able to
    # rewrite `sha256` or `hour` and make the provenance lie about the file it certifies.
    for k, v in (extra_provenance or {}).items():
        if k in provenance:
            raise CaptureError(f"extra_provenance may not override the base field {k!r}")
        provenance[k] = v
```

Guard the pre-publish re-check:

```python
    if final.exists() and not replace:
        raise FileExistsError(f"reconciled final appeared while minting: {final}")
```

- [ ] **Step 4: Run the full mint suite (the reconciler's existing tests MUST be untouched)**

Run: `uv run pytest tests/test_archive_mint.py tests/test_archive_reconcile.py -v`
Expected: PASS — every pre-existing test still green (the defaults preserve behaviour)

- [ ] **Step 5: Gate + commit**

```bash
uv run pre-commit run -a
git add cli/archive/mint.py tests/test_archive_mint.py
git commit -m "feat(archive): mint_hour gains tool/extra_provenance/replace for non-reconciler callers (spec 00053 Task 3)"
```

---

### Task 4: `cli/trades/backfill.py` — orchestration (TDD)

**Files:** Create `cli/trades/backfill.py`; Test `tests/test_trades_backfill.py`.

**Interfaces:**
- Consumes: `detect`/`IdGap`/`Detection` (Task 2), `fetch_trades` (Task 1), `mint_hour(..., tool=, extra_provenance=, replace=)` (Task 3), `canonical_segments(primary_root, reconciled_root=None, *, kind="book") -> Iterator[tuple[str, datetime, Path]]` (`cli/archive/reader.py:37`), `union_trades(primary, secondary) -> TradeUnion` with fields `frame` / `added_from_secondary` / `deduped_rows` / `secondary_deficit` (`cli/archive/reconcile.py:286`), `Block(source, frame, from_ts, to_ts)` (`cli/archive/reconcile.py:207`), `TRADE_SCHEMA` (`cli/capture/segment_writer.py:27`).
- Produces: `@dataclass(frozen=True) BackfillResult: pairs: int; gaps_found: int; trades_recovered: int; trades_unrecoverable: int; duplicates_collapsed: int; hours_minted: int; errors: list[tuple[str, str]]`
  and `backfill(primary_root: Path, reconciled_root: Path, *, pair: str | None = None, now: datetime, detect_only: bool = False, fetch=fetch_trades) -> BackfillResult`.

**Behaviour (exact):**
1. Enumerate canonical trade hours via `canonical_segments(primary_root, reconciled_root, kind="trades")`; **skip hours where `hour + 2h > now`** (settle rule).
2. Per pair: concat the hours' frames → `detect(...)`.
3. `detect_only=True` → return counts, mint nothing.
4. Per gap: `fetch(pair, since=gap.ts_lo, until=gap.ts_hi)`; keep rows with `gap.after_id < trade_id < gap.before_id`. Ids REST does not return count as `trades_unrecoverable` (**never fabricated**).
5. Affected hours = hours containing a recovered row **∪** hours containing a duplicate id.
6. Per affected hour: `union_trades(primary=<canonical hour frame>, secondary=<recovered rows for that hour>)`; mint `union.frame` as ONE `Block(source="canonical+kraken-rest", ...)` with `tool="zcrypto archive backfill-trades"`, `extra_provenance={"recovered_id_ranges": [...], "deduped_rows": union.deduped_rows}`, `replace=True`, `schema=TRADE_SCHEMA`.
7. A per-gap fetch failure is isolated: log, append to `errors`, continue.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_trades_backfill.py
import datetime as dt
import polars as pl
import pytest
from cli.capture.segment_writer import TRADE_SCHEMA
from cli.trades.backfill import backfill
from cli.trades.errors import TradeBackfillError
from cli.trades.gaps import detect

NOW = dt.datetime(2026, 7, 12, tzinfo=dt.UTC)
H = dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC)


def _rows(ids, hour=H):
    return pl.DataFrame(
        [{"ts": hour + dt.timedelta(seconds=i), "symbol": "BTC/EUR", "side": "buy", "price": 1.0,
          "qty": 1.0, "ord_type": "market", "trade_id": t} for i, t in enumerate(ids)],
        schema=TRADE_SCHEMA,
    )


def _write(root, ids, hour=H, pair="BTC/EUR"):
    d = root / pair.split("/")[0] / pair.split("/")[1] / "trades" / f"{hour:%Y/%m/%d}"
    d.mkdir(parents=True, exist_ok=True)
    _rows(ids, hour).write_parquet(d / f"{hour:%H}.parquet")


def test_a_planted_gap_is_recovered_and_the_invariant_holds(tmp_path):
    """Known-answer proof (master plan §9): plant a gap, recover it, assert the invariant."""
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15, 16])  # 12,13,14 missing

    def fake_fetch(pair, since, *, until=None, **kw):
        return _rows([12, 13, 14])

    res = backfill(primary, overlay, now=NOW, fetch=fake_fetch)
    assert res.gaps_found == 1 and res.trades_recovered == 3 and res.hours_minted == 1
    healed = pl.read_parquet(overlay / "BTC" / "EUR" / "trades" / "2026/07/11" / "02.parquet")
    assert healed["trade_id"].to_list() == [10, 11, 12, 13, 14, 15, 16]
    assert detect(healed).gaps == []          # THE INVARIANT
    assert detect(healed).duplicate_ids == []


def test_duplicates_are_collapsed_even_with_no_gap(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 11, 12])
    res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([]))
    assert res.duplicates_collapsed == 1 and res.hours_minted == 1
    healed = pl.read_parquet(overlay / "BTC" / "EUR" / "trades" / "2026/07/11" / "02.parquet")
    assert healed["trade_id"].to_list() == [10, 11, 12]
    assert detect(healed).duplicate_ids == []


def test_ids_rest_will_not_serve_are_unrecoverable_never_fabricated(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 14])                       # 11,12,13 missing
    res = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12]))  # REST serves only 12
    assert res.trades_recovered == 1 and res.trades_unrecoverable == 2
    healed = pl.read_parquet(overlay / "BTC" / "EUR" / "trades" / "2026/07/11" / "02.parquet")
    assert healed["trade_id"].to_list() == [10, 12, 14]   # 11 and 13 are ABSENT, not invented


def test_unsettled_hours_are_never_touched(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    recent = dt.datetime(2026, 7, 11, 23, tzinfo=dt.UTC)
    _write(primary, [10, 15], hour=recent)
    res = backfill(primary, overlay, now=recent + dt.timedelta(hours=1), fetch=lambda *a, **k: _rows([]))
    assert res.gaps_found == 0 and res.hours_minted == 0
    assert not (overlay / "BTC").exists()


def test_detect_only_mints_nothing(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15])
    res = backfill(primary, overlay, now=NOW, detect_only=True, fetch=lambda *a, **k: _rows([12, 13, 14]))
    assert res.gaps_found == 1 and res.hours_minted == 0
    assert not overlay.exists() or not any(overlay.rglob("*.parquet"))


def test_a_fetch_failure_is_isolated_and_the_sweep_continues(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 15], pair="BTC/EUR")
    _write(primary, [20, 21], pair="ETH/EUR")

    def boom(pair, since, *, until=None, **kw):
        if pair == "BTC/EUR":
            raise TradeBackfillError("kraken down")
        return _rows([])

    res = backfill(primary, overlay, now=NOW, fetch=boom)
    assert len(res.errors) == 1 and res.errors[0][0] == "BTC/EUR"
    assert res.pairs == 2  # ETH still swept


def test_second_run_is_a_no_op(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 11, 15, 16])
    backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([12, 13, 14]))
    res2 = backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([]))
    assert res2.gaps_found == 0 and res2.hours_minted == 0


def test_raw_mirror_is_never_written(tmp_path):
    primary, overlay = tmp_path / "p", tmp_path / "r"
    _write(primary, [10, 15])
    before = {p: p.read_bytes() for p in primary.rglob("*.parquet")}
    backfill(primary, overlay, now=NOW, fetch=lambda *a, **k: _rows([11, 12, 13, 14]))
    assert {p: p.read_bytes() for p in primary.rglob("*.parquet")} == before
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_trades_backfill.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.trades.backfill'`

- [ ] **Step 3: Implement**

```python
# cli/trades/backfill.py
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from cli.archive.mint import mint_hour
from cli.archive.reader import canonical_segments
from cli.archive.reconcile import Block, union_trades  # Block is DEFINED here, re-exported by mint
from cli.capture.segment_writer import TRADE_SCHEMA
from cli.logging import get_logger
from cli.trades.errors import TradeBackfillError
from cli.trades.gaps import detect
from cli.trades.rest import fetch_trades

logger = get_logger("trades.backfill")

_SETTLE = dt.timedelta(hours=2)  # the reconciler's rule: the in-flight hour is untouchable
_TOOL = "zcrypto archive backfill-trades"


@dataclass(frozen=True)
class BackfillResult:
    pairs: int
    gaps_found: int
    trades_recovered: int
    trades_unrecoverable: int
    duplicates_collapsed: int
    hours_minted: int
    errors: list[tuple[str, str]]


def backfill(
    primary_root: Path,
    reconciled_root: Path,
    *,
    pair: str | None = None,
    now: dt.datetime,
    detect_only: bool = False,
    fetch=fetch_trades,
) -> BackfillResult:
    """Heal the canonical trade stream to spec 00053's invariant: contiguous AND unique trade_id."""
    hours: dict[str, list[tuple[dt.datetime, Path]]] = defaultdict(list)
    for p, hour, path in canonical_segments(primary_root, reconciled_root, kind="trades"):
        if pair is not None and p != pair:
            continue
        if hour + _SETTLE > now:
            continue
        hours[p].append((hour, path))

    gaps_found = recovered = unrecoverable = dups = minted = 0
    errors: list[tuple[str, str]] = []

    for p, segs in sorted(hours.items()):
        frames = {h: pl.read_parquet(path) for h, path in sorted(segs)}
        if not frames:
            continue
        det = detect(pl.concat(list(frames.values())))
        gaps_found += len(det.gaps)
        dups += det.rows - det.unique
        if detect_only:
            continue

        got = pl.DataFrame([], schema=TRADE_SCHEMA)
        for g in det.gaps:
            try:
                page = fetch(p, since=g.ts_lo, until=g.ts_hi)
            except TradeBackfillError as exc:  # isolate: one bad gap must not end the sweep
                logger.warning("trade backfill fetch failed pair=%s gap=%s..%s: %s", p, g.after_id, g.before_id, exc)
                errors.append((p, str(exc)))
                continue
            inside = page.filter((pl.col("trade_id") > g.after_id) & (pl.col("trade_id") < g.before_id))
            recovered += inside.height
            unrecoverable += g.missing - inside.height  # never fabricated
            got = pl.concat([got, inside]) if got.height else inside

        touched = {h for h, f in frames.items() if f.height != f.unique(subset=["trade_id"]).height}
        for h in frames:
            if got.height and got.filter((pl.col("ts") >= h) & (pl.col("ts") < h + dt.timedelta(hours=1))).height:
                touched.add(h)

        for h in sorted(touched):
            rest_rows = (
                got.filter((pl.col("ts") >= h) & (pl.col("ts") < h + dt.timedelta(hours=1)))
                if got.height
                else pl.DataFrame([], schema=TRADE_SCHEMA)
            )
            union = union_trades(frames[h], rest_rows)
            ranges = [[int(r["trade_id"]), int(r["trade_id"])] for r in rest_rows.iter_rows(named=True)]
            mint_hour(
                reconciled_root,
                p,
                "trades",
                h,
                [Block(source="canonical+kraken-rest", frame=union.frame, from_ts=None, to_ts=None)],
                gaps_healed=[],
                residual_gaps=[],
                schema=TRADE_SCHEMA,
                tool_version="00053",
                tool=_TOOL,
                extra_provenance={"recovered_id_ranges": ranges, "deduped_rows": union.deduped_rows},
                replace=True,
            )
            minted += 1

    logger.info(
        "trade backfill complete pairs=%d gaps=%d recovered=%d unrecoverable=%d duplicates=%d hours_minted=%d errors=%d",
        len(hours), gaps_found, recovered, unrecoverable, dups, minted, len(errors),
    )
    return BackfillResult(len(hours), gaps_found, recovered, unrecoverable, dups, minted, errors)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_trades_backfill.py -v`
Expected: PASS (8 tests). `Block` is verified as `Block(source: str, frame: pl.DataFrame, from_ts: datetime | None, to_ts: datetime | None)` in `cli/archive/reconcile.py:207`.

- [ ] **Step 5: Gate + commit**

```bash
uv run pre-commit run -a
git add cli/trades/backfill.py tests/test_trades_backfill.py
git commit -m "feat(trades): backfill orchestration — detect, fetch, union, mint (spec 00053 Task 4)"
```

---

### Task 5: `zcrypto archive backfill-trades` CLI + README

**Files:** Modify `cli/archive/command.py` (register on the existing `archive_app`), `README.md` (§Usage, beside `verify-replay`); Test `tests/test_trades_command.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_trades_command.py
import re
from typer.testing import CliRunner
from cli.__main__ import app

runner = CliRunner()


def _plain(s):
    return re.sub(r"\s+", " ", re.sub(r"\x1b\[[0-9;]*m", "", s))


def test_help_lists_the_options():
    r = runner.invoke(app, ["archive", "backfill-trades", "--help"])
    assert r.exit_code == 0
    out = _plain(r.stdout)
    assert "--pair" in out and "--detect-only" in out


def test_missing_primary_root_exits_nonzero(tmp_path):
    r = runner.invoke(app, ["archive", "backfill-trades", str(tmp_path / "nope"), str(tmp_path / "r")])
    assert r.exit_code != 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_trades_command.py -v`
Expected: FAIL — `No such command 'backfill-trades'`

- [ ] **Step 3: Implement** — append to `cli/archive/command.py`:

```python
@archive_app.command(name="backfill-trades")
def backfill_trades(
    primary_root: Path = typer.Argument(..., help="The primary (raw) canonical trade archive."),
    reconciled_root: Path = typer.Argument(..., help="The overlay healed hours are minted into."),
    pair: str | None = typer.Option(None, "--pair", help="Only this pair (e.g. BTC/EUR)."),
    detect_only: bool = typer.Option(False, "--detect-only", help="Report the loss; mint nothing."),
) -> None:
    """Heal the canonical trade stream to a contiguous, duplicate-free trade_id sequence."""
    if not primary_root.exists():
        typer.echo(f"ERROR: primary root does not exist: {primary_root}", err=True)
        raise typer.Exit(2)
    res = backfill(primary_root, reconciled_root, pair=pair, now=_utc_now(), detect_only=detect_only)
    typer.echo(
        f"trade backfill complete pairs={res.pairs} gaps={res.gaps_found} recovered={res.trades_recovered} "
        f"unrecoverable={res.trades_unrecoverable} duplicates={res.duplicates_collapsed} "
        f"hours_minted={res.hours_minted} errors={len(res.errors)}"
    )
    raise typer.Exit(1 if res.errors else 0)
```

Imports at the top of `cli/archive/command.py`: `from cli.trades.backfill import backfill`.

- [ ] **Step 4: Run to verify they pass + document**

Run: `uv run pytest tests/test_trades_command.py -v` → PASS.
Add a `### zcrypto archive backfill-trades` subsection to `README.md` §Usage (mirroring `verify-replay`'s shape: one-paragraph description, the invocation, an options table, and the exit-code contract — **no internal serials**, per the README convention).

- [ ] **Step 5: Gate + commit**

```bash
uv run pre-commit run -a
git add cli/archive/command.py README.md tests/test_trades_command.py
git commit -m "feat(trades): zcrypto archive backfill-trades command (spec 00053 Task 5)"
```

---

### Task 6: NAS runner — one daily-gated step in the existing loop

**Files:** Modify `infra/nas/pull-entrypoint.sh`, `infra/nas/README.md`.

- [ ] **Step 1: Add the step.** In `infra/nas/pull-entrypoint.sh`, after the `reconcile` step, add a **daily-gated** invocation (spec `00053` D11 — daily, not per-cycle: the detector's scan is O(archive) and T0028 already flags that cost on this host). Gate on a stamp file so the hourly loop runs it once per UTC day:

```sh
# Trade backfill (spec 00053): heal the canonical trade stream to a contiguous, duplicate-free
# trade_id sequence. Daily, not per-cycle -- the detector scan is O(archive) (T0028) and there is no
# urgency cliff (Kraken serves ~18 months of /Trades).
BACKFILL_STAMP=/archive/.trade-backfill-last-utc-day
TODAY="$(date -u +%Y-%m-%d)"
if [ "$(cat "$BACKFILL_STAMP" 2>/dev/null || echo none)" != "$TODAY" ]; then
    if zcrypto archive backfill-trades /archive/capture-segments /archive/capture-reconciled; then
        echo "$TODAY" > "$BACKFILL_STAMP"
        backfill_rc=0
    else
        backfill_rc=$?   # do NOT stamp on failure: retry next cycle
    fi
    printf 'zcrypto_trade_backfill_exit_code %d\n' "$backfill_rc" > "$TEXTFILE_DIR/trade-backfill.prom.tmp"
    printf 'zcrypto_trade_backfill_last_run_timestamp %d\n' "$(date -u +%s)" >> "$TEXTFILE_DIR/trade-backfill.prom.tmp"
    if [ "$backfill_rc" -eq 0 ]; then
        printf 'zcrypto_trade_backfill_last_success_timestamp %d\n' "$(date -u +%s)" >> "$TEXTFILE_DIR/trade-backfill.prom.tmp"
    fi
    mv "$TEXTFILE_DIR/trade-backfill.prom.tmp" "$TEXTFILE_DIR/trade-backfill.prom"
fi
```

Match the surrounding script's existing variable names (`TEXTFILE_DIR`, the archive mount path) — read the file first and adapt; do not assume.

- [ ] **Step 2: Verify the script parses**

Run: `bash -n infra/nas/pull-entrypoint.sh`
Expected: no output (exit 0)

- [ ] **Step 3: Document + gate + commit.** Add the step + its metrics to `infra/nas/README.md`.

```bash
uv run pre-commit run -a
git add infra/nas/pull-entrypoint.sh infra/nas/README.md
git commit -m "feat(config): daily trade-backfill step in the NAS archive loop (spec 00053 Task 6)"
```

---

### Task 7 **[attended — orchestrator only]**: the bulk run + verification by outcome

- [ ] Build the image off this branch (`workflow_dispatch`), pin the digest, pre-stage on the NAS. **Re-apply the compose digest pin after any file ship** (the 2026-07-15 lesson).
- [ ] **Detect-only first**: run `zcrypto archive backfill-trades --detect-only` against a **pulled copy**. Expect ≈ **194 gaps / 17,362 missing / 10,986 duplicates** — the spec's measured baseline. A materially different number means the detector disagrees with the exploratory probe: **investigate before minting**, do not proceed.
- [ ] **The bulk run** (~200–400 REST calls at ~1.5 s spacing ⇒ ~5–10 min). Then verify **by outcome**, not by exit code:
  - re-run `--detect-only`: **gaps → 0**, duplicates → 0 (any residual must appear as `unrecoverable`, with a logged reason);
  - `verify_manifest` passes on every minted hour;
  - spot-check the 07-08 BTC gap (`107998884 → 107999859`, 974 trades) is filled and the ids are contiguous;
  - the raw mirrors are **byte-unchanged** (compare counts + a sample of hashes before/after);
  - `canonical_segments(primary, reconciled, kind="trades")` now yields the healed hours.
- [ ] Provision the `zcrypto-trade-backfill` dead-man (daily cadence → timeout 172800 / grace 3600), vault + wire the URL.
- [ ] Record the actual recovered/unrecoverable counts for the closeout.

---

### Task 8: Closeout

- [ ] `docs/iterations-history-phase1.md` — append the **iter-100** entry (trade backfill is data-foundation subject matter).
- [ ] `.tmp/decisions-phase1.md` — append the `[iter-100]` decisions (the invariant; NAS-vs-ops placement; gaps-and-duplicates scope). **Append only — do not drain**: phase 1 already closed out, so this floating log drains at the next phase's close-out fan-out.
- [ ] `docs/open-topics/T0050-rest-trade-backfill.md` → `status: resolved`, move to `docs/open-topics/archive/`, index bullet → the **end** of the *Live trading preparation → Resolved* subsection with the `archive/` path.
- [ ] `docs/open-topics/T0033-home-ops-node-compute-tier.md` — update the **OPS-5** text: it relocates **the reconciler AND trade-backfill as ONE unit** (they share the entrypoint, the overlay, and `union_trades`), together with the ops→NAS reconciled channel (owner directive 2026-07-16, spec `00053` D4).
- [ ] `docs/open-topics/T0026-reconnect-trade-snapshot-overwrite.md` — its loss-quantification step is now **delivered** by this iteration; update it with the measured numbers and trim its next-steps to the genuine remainder (flip to `partial`/`resolved` as the sub-items warrant).
- [ ] `docs/open-topics/archive/T0003-d2-capture-pipeline.md` — **correct the record**: its "trades unaffected" claim about the 2026-07-08 desync is false; the two largest gaps (974 + 605 BTC trades) fall inside that window. One inline correction line; the file stays archived.
- [ ] `docs/reference/data-catalog-full.md` — the healed overlay's trade semantics (dataset-catalog sync is a closeout rule for any iteration that changes a dataset's shape or provenance).
- [ ] Commit `docs(trades): trade-backfill closeout (iter-100)`.

## Self-Review

**Spec coverage:** D1 invariant → Tasks 2 + 4 (asserted in the known-answer test); D2 detect-from-archive → Task 2; D3 placement → Task 6; D4 OPS-5 unit → Task 8; D5 REST/pagination/ns-vs-s → Task 1 (a dedicated test); D6 normalization → Task 1; D7 union+mint whole hours → Tasks 3 + 4; D8 gaps AND duplicates → Task 2 (detect) + Task 4 (`touched` includes duplicate hours); D9 invariant-not-manifest → Task 4 test + Task 7 verification; D10 never fabricate → Task 4 (`trades_unrecoverable` test); D11 cadence + detect-only report → Tasks 5 + 6 + 7; D12 safety rails → Task 4 (settle, isolation, raw-immutable tests). No spec requirement is unclaimed.

**Placeholder scan:** none — every code step carries real code; every run step carries its command and expected result. Task 6's script is explicitly "read the file and match its variable names", which is an instruction with a concrete check (`bash -n`), not a TBD.

**Type consistency:** `fetch_trades(pair, since, *, until, opener, sleep) -> pl.DataFrame` is produced in Task 1 and consumed identically in Task 4 (via the `fetch=` seam). `detect(frame) -> Detection` with `IdGap(after_id, before_id, ts_lo, ts_hi)` + `.missing` is produced in Task 2, consumed in Task 4. `mint_hour(..., tool=, extra_provenance=, replace=)` is produced in Task 3, called with exactly those names in Task 4. `BackfillResult` field names match between Task 4's dataclass and Task 5's echo string. `union_trades(primary, secondary) -> TradeUnion` with `.frame`/`.deduped_rows` matches the real `cli/archive/reconcile.py`.
