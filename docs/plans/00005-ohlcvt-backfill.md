# Full-History OHLCVT Backfill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Build `cli/backfill/` — read Kraken OHLCVT 1-minute dumps from the NAS, reconstruct canonical 1h/4h/1d bars (with a volume-weighted vwap), write a full-history dataset to a new path, and reconcile it vs the v0 REST dataset.

**Architecture:** A new stdlib+polars package `cli/backfill/` that reuses `cli.ohlc.dataset.to_frame`/`write_parquet`/`dataset_hash` and `cli.ohlc.qa.INTERVAL_SECONDS`. Reads 1-minute rows from ZIPs → aggregates to cadences → canonical frames.

**Tech Stack:** Python 3.14, polars, stdlib `zipfile`. Design: `docs/specs/00005-ohlcvt-backfill-design.md`.

## Global Constraints

- ruff line-length 132, double quotes, `from __future__ import annotations`, stdlib + polars only (no new deps).
- Canonical schema is `cli.ohlc.dataset.to_frame`'s (`ts` UTC Datetime; `open/high/low/close/vwap/volume` Float64; `count` Int64). All failure boundaries raise `cli.backfill.errors.BackfillError`.
- `INTERVAL_SECONDS = {1440: 86400, 240: 14400, 60: 3600}` — import from `cli.ohlc.qa`.
- vwap is a **reconstruction proxy**: `Σ(close_i·vol_i)/Σvol_i` over the 1-minute bars in the bucket; if `Σvol_i == 0`, `vwap = close`.
- The commit gate is `uv run pre-commit run -a`. TDD throughout; no test reads the real 27 GB archive (synthetic ZIPs in `tmp_path`).
- The 12 universe symbols → dump altnames (aliases BTC→XBT, DOGE→XDG on both legs): BTC/EUR→XBTEUR, ETH/EUR→ETHEUR, SOL/EUR→SOLEUR, XRP/EUR→XRPEUR, ADA/EUR→ADAEUR, LINK/EUR→LINKEUR, DOGE/EUR→XDGEUR, LTC/EUR→LTCEUR, DOT/EUR→DOTEUR, AVAX/EUR→AVAXEUR, ETH/BTC→ETHXBT, SOL/BTC→SOLXBT.

---

### Task 1: `cli/backfill/errors.py` + `dump_pair_name`

**Files:** Create `cli/backfill/__init__.py` (empty for now), `cli/backfill/errors.py`, `cli/backfill/read.py`; Test `tests/test_backfill_read.py`.

**Interfaces — Produces:** `BackfillError(Exception)`; `dump_pair_name(symbol: str) -> str`.

- [ ] **Step 1 — failing test** (`tests/test_backfill_read.py`):

```python
from __future__ import annotations
import pytest
from cli.backfill.read import dump_pair_name

def test_dump_pair_name_maps_all_universe_pairs():
    cases = {
        "BTC/EUR": "XBTEUR", "ETH/EUR": "ETHEUR", "SOL/EUR": "SOLEUR", "XRP/EUR": "XRPEUR",
        "ADA/EUR": "ADAEUR", "LINK/EUR": "LINKEUR", "DOGE/EUR": "XDGEUR", "LTC/EUR": "LTCEUR",
        "DOT/EUR": "DOTEUR", "AVAX/EUR": "AVAXEUR", "ETH/BTC": "ETHXBT", "SOL/BTC": "SOLXBT",
    }
    for sym, want in cases.items():
        assert dump_pair_name(sym) == want
```

- [ ] **Step 2 — run, expect fail** (`uv run pytest tests/test_backfill_read.py -v`).
- [ ] **Step 3 — implement.** `errors.py`: `class BackfillError(Exception): ...`. `read.py`:

```python
from __future__ import annotations
from cli.backfill.errors import BackfillError
_ALIAS = {"BTC": "XBT", "DOGE": "XDG"}

def dump_pair_name(symbol: str) -> str:
    try:
        base, quote = symbol.split("/")
    except ValueError as exc:
        raise BackfillError(f"not a BASE/QUOTE symbol: {symbol!r}") from exc
    return _ALIAS.get(base, base) + _ALIAS.get(quote, quote)
```

- [ ] **Step 4 — run, expect pass. Step 5 — commit.**

---

### Task 2: `read_minute_rows`

**Files:** Modify `cli/backfill/read.py`; Test `tests/test_backfill_read.py`.

**Interfaces — Consumes:** `dump_pair_name`, `BackfillError`. **Produces:** `read_minute_rows(source_dir: Path, symbol: str) -> list[list]` returning `[[int ts, str o, str h, str l, str c, str volume, str trades], ...]` sorted by ts, de-duped.

- [ ] **Step 1 — failing tests.** Build synthetic ZIPs in `tmp_path` with `zipfile`: a base `Kraken_OHLCVT.zip` containing `master_q4/FOO_1.csv` (rows for a fake symbol whose `dump_pair_name` is `FOO` — use symbol `"FOO/BAR"` and monkeypatch/extend `dump_pair_name`, OR test with a real altname by writing `master_q4/XBTEUR_1.csv` and reading `"BTC/EUR"`) and a `__MACOSX/master_q4/._XBTEUR_1.csv` cruft entry; a quarterly `Kraken_OHLCVT_Q1_2099.zip` with `XBTEUR_1.csv`. Assert:
  - rows from base + quarterly are merged, sorted by ts, exact-ts duplicates dropped;
  - the `__MACOSX/` entry is ignored;
  - a symbol absent from all zips raises `BackfillError`;
  - a same-ts row with different OHLC across sources raises `BackfillError`.

  Example row CSV content (7-field, no header): `1700000000,42000.0,42010.0,41990.0,42005.0,1.5,12`.

- [ ] **Step 2 — run, expect fail. Step 3 — implement:**

```python
import zipfile
from pathlib import Path

def _parse_csv(text: str) -> list[list]:
    out = []
    for line in text.splitlines():
        if not line:
            continue
        t, o, h, l, c, v, n = line.split(",")
        out.append([int(t), o, h, l, c, v, n])
    return out

def read_minute_rows(source_dir: Path, symbol: str) -> list[list]:
    alt = dump_pair_name(symbol)
    base_zip = source_dir / "Kraken_OHLCVT.zip"
    rows: list[list] = []
    found = False
    # base dump: entry master_q4/{alt}_1.csv
    if base_zip.exists():
        with zipfile.ZipFile(base_zip) as zf:
            name = f"master_q4/{alt}_1.csv"
            if name in zf.namelist():
                rows += _parse_csv(zf.read(name).decode())
                found = True
    # quarterly updates: entry {alt}_1.csv (skip __MACOSX/)
    for qz in sorted(source_dir.glob("Kraken_OHLCVT_Q*_*.zip")):
        with zipfile.ZipFile(qz) as zf:
            name = f"{alt}_1.csv"
            if name in zf.namelist():
                rows += _parse_csv(zf.read(name).decode())
                found = True
    if not found:
        raise BackfillError(f"no 1-minute data for {symbol} ({alt}) under {source_dir}")
    rows.sort(key=lambda r: r[0])
    deduped: list[list] = []
    for r in rows:
        if deduped and deduped[-1][0] == r[0]:
            if deduped[-1] != r:
                raise BackfillError(f"conflicting rows at ts={r[0]} for {symbol}")
            continue
        deduped.append(r)
    return deduped
```

- [ ] **Step 4 — run, expect pass. Step 5 — commit.**

---

### Task 3: `aggregate_minutes`

**Files:** Create `cli/backfill/aggregate.py`; Test `tests/test_backfill_aggregate.py`.

**Interfaces — Produces:** `aggregate_minutes(minute_rows: list[list], interval_secs: int) -> list[list]` returning 8-field rows `[bucket_ts, open, high, low, close, vwap, volume, count]` (floats as Python floats/str acceptable to `to_frame`), sorted by bucket_ts.

- [ ] **Step 1 — failing tests:** e.g. four 1-minute rows within one 1h bucket → one bar with open=first, high=max, low=min, close=last, volume=Σ, count=Σtrades, vwap=Σ(close·vol)/Σvol; rows spanning two buckets → two bars with correct floored ts; Σvol==0 bucket → vwap==close; empty input → `[]`. Feed the output through `cli.ohlc.dataset.to_frame` and assert the canonical schema + row count.
- [ ] **Step 2 — run fail. Step 3 — implement** (group by `ts // interval_secs * interval_secs`, accumulate; emit sorted). Use floats internally; emit `vwap` and prices as values `to_frame` can cast (float or str). **Step 4 — pass. Step 5 — commit.**

---

### Task 4: `backfill_pair` + `backfill_basket`

**Files:** Create `cli/backfill/backfill.py`; Test `tests/test_backfill_backfill.py`.

**Interfaces — Consumes:** `read_minute_rows`, `aggregate_minutes`, `cli.ohlc.dataset.{to_frame,write_parquet,dataset_hash}`, `cli.ohlc.qa.INTERVAL_SECONDS`. **Produces:** `backfill_pair(source_dir, symbol, intervals) -> dict[str, pl.DataFrame]`; `backfill_basket(source_dir, symbols, intervals, out_root, fetched_at) -> dict` (writes `out_root/{base}/{quote}/{interval}.parquet` + `out_root/manifest.json`; returns the manifest).

- [ ] **Steps:** failing test with a synthetic source dir (small zips) writing to `tmp_path` out_root → assert the parquet tree exists, the manifest records per-series `{rows, first_ts, last_ts, sha256}` and a deterministic `basket_sha256`, and re-running is byte-deterministic given a fixed `fetched_at`. Mirror `cli.ohlc.ingest.ingest_basket`'s manifest shape. Implement, pass, commit.

---

### Task 5: `reconcile_series` + `reconcile_dataset` + `render_markdown`

**Files:** Create `cli/backfill/reconcile.py`; Test `tests/test_backfill_reconcile.py`.

**Interfaces — Produces:** `reconcile_series(backfill, rest) -> dict`, `reconcile_dataset(backfill_root, rest_root, intervals) -> dict`, `render_markdown(report) -> str`.

- [ ] **Steps:** failing tests — identical OHLCV frames → `ohlc_match_rate==1.0`; a planted OHLC diff counted; vwap difference reported (not raised); disjoint ts → `overlap_rows==0`. `render_markdown` contains a per-series table. Implement (inner-join on `ts`; compare `open/high/low/close/volume` for exact/near equality; report `vwap` mean-abs-rel-diff). Pass, commit.

---

### Task 6: config `ohlcvt_source_dir` + `cli/backfill/__init__.py`

**Files:** Modify `cli/config.py`, `zcrypto.toml`, `README.md`, `cli/backfill/__init__.py`; Test `tests/test_config.py` (extend if present, else add cases).

- [ ] **Steps:** failing test — `load_config` reads `ohlcvt_source_dir` from `[zcrypto]`; `resolve_ohlcvt_source_dir(flag, cfg)` follows flag→config→`ConfigError`. Implement: add `ohlcvt_source_dir: Path | None` to `AppConfig`, read via `_read_path`, add `resolve_ohlcvt_source_dir`. Set `ohlcvt_source_dir = "../zcrypto-kraken-data/kraken-ohlcvt-updates"` in `zcrypto.toml`; document it in the README `[zcrypto]` block (keep the inline comments aligned). Export the public API from `cli/backfill/__init__.py` (`BackfillError`, `dump_pair_name`, `read_minute_rows`, `aggregate_minutes`, `backfill_pair`, `backfill_basket`, `reconcile_series`, `reconcile_dataset`, `render_markdown`). Pass, commit.

---

### Task 7 (closeout — orchestrator, post-review, not a TDD code task)

After the whole-branch review passes: run `backfill_basket` over the live archive (read `ohlcvt_source_dir` from config; 12 universe symbols × 1h/4h/1d) → `data/ohlc-full/` (gitignored) + `docs/reference/data-catalog-full.md`; run the QA (`cli.ohlc.qa`) + `reconcile_dataset` vs `data/ohlc/` → commit `docs/research/02.phase1-ohlcvt-backfill-reconciliation.md`. Flip **T0001 → resolved** (front-matter + `git mv` to `archive/` + README index move). Append the `iter-008` entry to `docs/iterations-history.md`. Drain: this iteration's decision already logged in `.tmp/decisions.md`.
