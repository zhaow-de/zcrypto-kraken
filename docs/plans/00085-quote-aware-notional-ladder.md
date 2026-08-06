# Quote-Aware Notional Ladder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the panel's fill ladder quote-aware so BTC-quoted pairs produce real `fill_bps_*`, then recalibrate all twelve legs on one common window and re-key `SPREAD_CALIBRATION` from base to full symbol.

**Architecture:** The ladder becomes a per-quote table keyed by quote currency, with BTC rungs set to the BTC quantities worth €100/€1k/€10k at a pinned BTC/EUR reference. `sample_row` gains a `quote` argument; `materialize_hour` already receives `pair` so nothing above it changes shape. The panel's four EUR scope guards lift together; `cli/data/rebuild.py`'s quote guard lifts only in the final task, after the table has `/BTC` rows.

**Tech Stack:** Python 3.14 (uv), polars, Typer, pytest. Ansible for the ops converge; `zcrypto-panel-regenerate` on the ops host for the tree rebuild.

## Global Constraints

- **Review floor is Opus for every review in this iteration — never Fable.** Owner ruling, spec D8.
- BTC rungs are EUR-equivalent at a pinned FX reference derived from this repo's own `BTC/EUR` panel mids over the calibration window (spec D1). Not round BTC quantities.
- Column names stay `fill_bps_{bid,ask}_{100,1k,10k}` with per-quote meaning (spec D2).
- `SPREAD_CALIBRATION` inner keys stay the EUR notionals `100 / 1_000 / 10_000`; `_PINNED_SIZES` stays one shared grid; `effective_spread_bps(symbol, notional_eur)` keeps its signature (spec D1 consequence).
- `cli/data/rebuild.py`'s quote guard lifts **only** in Task 7, never earlier (spec D6).
- The universe rebuild is **not run** in this iteration (spec D7 — that is T0025's).
- Every guard is proven against a constructed defect through `infra/scripts/mutate-probe.sh`, never asserted. This shell is zsh: pass probe commands as separate words, never an unquoted `$VAR`.
- Commit kinds split per the `staged-kind` hook: `.claude/` content never shares a commit with code, tests, or docs.
- One line per markdown paragraph/bullet; no internal traceability tokens on operator-visible surfaces.

---

## File structure

| File | Responsibility after this plan |
|---|---|
| `cli/panel/primitives.py` | Owns `NOTIONALS_BY_QUOTE`, `BTC_EUR_REFERENCE`, `_FILL_SUFFIXES`, and a `quote`-aware `sample_row`. |
| `cli/panel/materialize.py` | Threads the pair's quote into `sample_row`; sweeps every captured quote; writes the per-quote ladder into `panel-meta.json`. |
| `cli/panel/command.py` | Generation dict carries the per-quote ladder; the three EUR-scope refusals lift. |
| `cli/costs/spread.py` | Full-symbol-keyed `SPREAD_CALIBRATION`, restamped provenance constants. |
| `cli/costs/calibrate.py` *(new)* | The committed calibration query (spec D5) — reads the panel tree, emits the table and provenance. |
| `cli/data/rebuild.py` | Quote guard collapses to membership (Task 7 only). |

---

### Task 1: The per-quote ladder and its pinned FX reference

**Files:**
- Modify: `cli/panel/primitives.py`
- Test: `tests/test_panel_primitives.py`

**Interfaces:**
- Produces: `NOTIONALS_BY_QUOTE: dict[str, tuple[float, float, float]]`, `BTC_EUR_REFERENCE: float`, `notionals_for(quote: str) -> tuple[float, float, float]` raising `PanelError` on an unknown quote. `_FILL_SUFFIXES` becomes keyed by **rung index** (0/1/2 → `"100"`/`"1k"`/`"10k"`), because the float values now differ per quote.

- [ ] **Step 0: MEASURE the FX reference before writing any code**

The reference must be a measured number from the start, not a placeholder corrected later: the panel tree gets regenerated against whatever value ships in Task 1, so a wrong value here means a second full regeneration. `BTC/EUR` is EUR-quoted and already in the panel, so this needs no ladder change and no regeneration — read it from the **pulled** copy:

```bash
uv run python -c "
import polars as pl
lf = pl.scan_parquet('/mnt/zhao-crypto/l2-panel/BTC/EUR/panel-1s/**/*.parquet')
# time_zone is REQUIRED: 'ts' is Datetime('us','UTC') and a naive literal raises SchemaError.
lf = lf.filter((pl.col('ts') >= pl.datetime(2026,7,23,14,time_zone='UTC')) & (pl.col('ts') < pl.datetime(2026,8,6,6,time_zone='UTC')))
print(lf.select(pl.col('mid').mean().alias('btc_eur_reference'), pl.len()).collect())
"
```

Use that value verbatim in Step 3 and record the window beside it as `BTC_EUR_REFERENCE_WINDOW`.

**This window is the REFERENCE's own and is fixed here forever** (spec D1). It is *not* D4's calibration window and does not move at a restamp: the constant defines what every BTC `fill_bps_*` column in the tree means, so moving it would redefine columns that already exist. Task 5's script recomputes the same number **over this same fixed window** and Task 7 asserts they agree — a divergence means the script is wrong, or the tree must be regenerated. It never means "update the constant to match".

- [ ] **Step 1: Write the failing test**

```python
def test_the_ladder_is_per_quote_and_btc_rungs_are_eur_equivalent():
    from cli.panel.primitives import BTC_EUR_REFERENCE, NOTIONALS_BY_QUOTE, notionals_for

    assert notionals_for("EUR") == (100.0, 1_000.0, 10_000.0)
    btc = notionals_for("BTC")
    # Each BTC rung is the BTC quantity worth the same EUR as the EUR rung at the pinned reference.
    for eur_rung, btc_rung in zip((100.0, 1_000.0, 10_000.0), btc, strict=True):
        assert btc_rung == pytest.approx(eur_rung / BTC_EUR_REFERENCE, rel=1e-12)
    # The rungs must be *different* numbers, or the ladder is not actually quote-aware.
    assert btc != (100.0, 1_000.0, 10_000.0)
    assert set(NOTIONALS_BY_QUOTE) == {"EUR", "BTC"}


def test_an_unknown_quote_refuses_rather_than_defaulting_to_eur():
    from cli.panel.errors import PanelError  # NOT primitives -- it is defined in errors.py
    from cli.panel.primitives import notionals_for

    with pytest.raises(PanelError, match="no notional ladder"):
        notionals_for("USD")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_panel_primitives.py -k ladder_is_per_quote -v`
Expected: FAIL — `ImportError: cannot import name 'NOTIONALS_BY_QUOTE'`

- [ ] **Step 3: Implement**

Replace `NOTIONALS_EUR` / `PANEL_QUOTE` / `_FILL_SUFFIXES` in `cli/panel/primitives.py` with:

```python
from cli.panel.errors import PanelError  # add this import -- errors.py imports nothing, so it is safe

# The depth-at-notional ladder (spec 00052 D2, made quote-aware by spec 00085 D1): walk a side
# accumulating price*qty in the pair's QUOTE currency until the notional is filled, then compare the
# resulting VWAP to mid in bps. The rungs therefore have to be denominated per quote, or a BTC-quoted
# pair asks for 100 BTC where it means EUR 100 -- which is why every `fill_bps_*` on those pairs was
# null before this.
NOTIONALS_EUR: tuple[float, float, float] = (100.0, 1_000.0, 10_000.0)

# The BTC/EUR rate the BTC rungs are pinned to. EUR-EQUIVALENCE is the point (spec 00085 D1): the
# BTC rungs buy the same EUR value as the EUR rungs, so `SPREAD_CALIBRATION`'s inner keys stay EUR
# notionals and one shared interpolation grid serves all twelve legs. Derived from this repo's own
# BTC/EUR panel mids over the calibration window by `cli/costs/calibrate.py`, and restamped with the
# table -- never a live rate, or the column meaning would drift hour to hour.
BTC_EUR_REFERENCE: float = <the value measured in Step 0>
BTC_EUR_REFERENCE_WINDOW: tuple[str, str] = ("2026-07-23T14:00:00Z", "2026-08-06T06:00:00Z")

NOTIONALS_BY_QUOTE: dict[str, tuple[float, float, float]] = {
    "EUR": NOTIONALS_EUR,
    "BTC": tuple(n / BTC_EUR_REFERENCE for n in NOTIONALS_EUR),  # type: ignore[dict-item]
}

# Keyed by rung INDEX, not by value: the values now differ per quote, so a value-keyed map would
# need a lookup per quote and would silently miss on a float that did not round-trip.
_FILL_SUFFIXES: tuple[str, str, str] = ("100", "1k", "10k")


def notionals_for(quote: str) -> tuple[float, float, float]:
    """The ladder for `quote`, refusing rather than defaulting -- a silent EUR fallback on an
    unknown quote is exactly the wrong-number failure this ladder exists to prevent."""
    try:
        return NOTIONALS_BY_QUOTE[quote]
    except KeyError:
        raise PanelError(f"no notional ladder for quote {quote!r}: add one to NOTIONALS_BY_QUOTE") from None
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_panel_primitives.py -k "ladder_is_per_quote or unknown_quote" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Update the existing pin that asserts the old constant**

`tests/test_panel_primitives.py:54` asserts `NOTIONALS_EUR == (100.0, 1_000.0, 10_000.0)` — that stays true and stays. Add nothing else here.

- [ ] **Step 6: Commit**

```bash
git add cli/panel/primitives.py tests/test_panel_primitives.py
git commit -m "feat(panel): the notional ladder is per-quote, with BTC rungs pinned EUR-equivalent"
```

- [ ] **Step 7: Prove the guard bites — AFTER the commit**

`infra/scripts/mutate-probe.sh` refuses a dirty worktree, so every probe in this plan runs on a clean tree, after its own commit. The control must be a sed that really changes the file as committed.

```bash
infra/scripts/mutate-probe.sh --file cli/panel/primitives.py \
  --control 's/def notionals_for/def notionals_for_renamed/' \
  --mutation 's|"BTC": tuple(n / BTC_EUR_REFERENCE for n in NOTIONALS_EUR)|"BTC": NOTIONALS_EUR|' \
  -- uv run pytest tests/test_panel_primitives.py -k ladder_is_per_quote -q
```
Expected: `KILLED (control proven, tree restored byte-identically)`

---

### Task 2: `sample_row` uses the quote's ladder

**Files:**
- Modify: `cli/panel/primitives.py` (the `sample_row` fill loop)
- Test: `tests/test_panel_primitives.py`

**Interfaces:**
- Consumes: `notionals_for`, `_FILL_SUFFIXES` from Task 1.
- Produces: `sample_row(bids, asks, *, quote: str, updates: int, stale_seconds: float | None = None)` — `quote` is **keyword-only and required**, so every existing call site fails loudly rather than silently defaulting to EUR.

- [ ] **Step 1: Write the failing test**

```python
def test_sample_row_fills_a_btc_quoted_book_that_eur_rungs_could_never_fill():
    from decimal import Decimal
    from cli.panel.primitives import sample_row

    # A realistic ETH/BTC book: ~0.03 BTC per ETH, a few hundred ETH of depth.
    bids = {Decimal("0.0300"): Decimal("200"), Decimal("0.0299"): Decimal("300")}
    asks = {Decimal("0.0301"): Decimal("200"), Decimal("0.0302"): Decimal("300")}

    row_btc = sample_row(bids, asks, quote="BTC", updates=1)
    # EUR 100 at the pinned reference is ~0.0017 BTC -- trivially fillable here.
    assert row_btc["fill_bps_ask_100"] is not None
    assert row_btc["fill_bps_bid_100"] is not None

    # The same book read with the EUR ladder asks for 100 BTC and cannot fill: this is the exact
    # bug -- all six columns null -- and it must still be reproducible on demand.
    row_eur = sample_row(bids, asks, quote="EUR", updates=1)
    assert row_eur["fill_bps_ask_100"] is None


def test_sample_row_requires_the_quote_explicitly():
    from decimal import Decimal
    from cli.panel.primitives import sample_row

    with pytest.raises(TypeError):
        sample_row({Decimal("1"): Decimal("1")}, {Decimal("2"): Decimal("1")}, updates=1)  # type: ignore[call-arg]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_panel_primitives.py -k btc_quoted_book -v`
Expected: FAIL — `TypeError: sample_row() got an unexpected keyword argument 'quote'`

- [ ] **Step 3: Implement**

In `sample_row`, add the keyword-only parameter and use the quote's ladder:

```python
def sample_row(
    bids: dict[Decimal, Decimal],
    asks: dict[Decimal, Decimal],
    *,
    quote: str,
    updates: int,
    stale_seconds: float | None = None,
) -> dict | None:
```

and replace the fill loop:

```python
    for index, notional in enumerate(notionals_for(quote)):
        suffix = _FILL_SUFFIXES[index]
        row[f"fill_bps_bid_{suffix}"] = _fill_bps(bid_levels, notional, mid, buy=False)
        row[f"fill_bps_ask_{suffix}"] = _fill_bps(ask_levels, notional, mid, buy=True)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_panel_primitives.py -v`
Expected: PASS. Existing tests calling `sample_row` without `quote` now fail — fix each by passing `quote="EUR"`, which is what they were implicitly testing.

- [ ] **Step 5: Commit**

```bash
git add cli/panel/primitives.py tests/test_panel_primitives.py
git commit -m "feat(panel): sample_row takes the quote and walks that quote's ladder"
```

- [ ] **Step 6: Prove the required-keyword guard bites — AFTER the commit**

```bash
infra/scripts/mutate-probe.sh --file cli/panel/primitives.py \
  --control 's/def sample_row(/def sample_row_renamed(/' \
  --mutation 's/    quote: str,/    quote: str = "EUR",/' \
  -- uv run pytest tests/test_panel_primitives.py -k requires_the_quote -q
```
Expected: `KILLED`

---

### Task 3: `materialize_hour` threads the quote; the sweep stops skipping non-EUR pairs

**Files:**
- Modify: `cli/panel/materialize.py`
- Test: `tests/test_panel_materialize.py`

**Interfaces:**
- Consumes: `sample_row(..., quote=...)` from Task 2.
- Produces: `materialize_hour` unchanged in signature (it already takes `pair`); the sweep visits every pair whose quote is in `NOTIONALS_BY_QUOTE`.

- [ ] **Step 1: Write the failing test**

Reuse this file's existing builders — `_explode(pair, hour, messages)`, `_book(root, pair, hour, frame)` and `_messages()` (defined at the top of `tests/test_panel_materialize.py`). `_book` writes a canonical final plus its `.sha256` sidecar at the archive layout, which is what the sweep walks.

```python
def test_the_sweep_no_longer_skips_a_btc_quoted_pair(tmp_path: Path) -> None:
    capture_root, panel_root = tmp_path / "capture", tmp_path / "panel"
    hour = datetime(2026, 7, 24, 0, tzinfo=timezone.utc)
    _book(capture_root, "ETH/BTC", hour, _explode("ETH/BTC", hour, _messages()))

    # THREE positionals: (primary_root, reconciled_root, panel_root). Passing two silently binds
    # panel_root to reconciled_root and raises TypeError on the missing third.
    result = materialize(capture_root, None, panel_root, settle=timedelta(0), now=hour + timedelta(hours=8))

    assert result.pairs_out_of_scope == 0
    assert result.hours_written == 1
    assert (panel_root / "ETH" / "BTC" / "panel-1s").exists()


def test_a_pair_whose_quote_has_no_ladder_is_still_counted_out_of_scope(tmp_path: Path) -> None:
    capture_root, panel_root = tmp_path / "capture", tmp_path / "panel"
    hour = datetime(2026, 7, 24, 0, tzinfo=timezone.utc)
    _book(capture_root, "ETH/USD", hour, _explode("ETH/USD", hour, _messages()))

    result = materialize(capture_root, None, panel_root, settle=timedelta(0), now=hour + timedelta(hours=8))

    # Skipped, not crashed, and NOT silently walked with the EUR ladder.
    assert result.pairs_out_of_scope == 1
    assert result.hours_written == 0
    assert not (panel_root / "ETH" / "USD").exists()
```

Signature verified against `cli/panel/materialize.py:268-278`: `materialize(primary_root, reconciled_root, panel_root, *, pair, since, depth, settle, now)`. Every existing call passes three positionals (e.g. `tests/test_panel_materialize.py:287`).

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_panel_materialize.py -k no_longer_skips -v`
Expected: FAIL — `pairs_out_of_scope == 1`

- [ ] **Step 3: Implement**

At `cli/panel/materialize.py:132`, pass the quote:

```python
        row = sample_row(book.bids, book.asks, quote=pair.split("/")[-1], updates=updates, stale_seconds=stale)
```

At the sweep's scope check (`materialize.py:318-324`), replace the `PANEL_QUOTE` comparison with ladder membership:

```python
        if seg_pair.split("/")[-1] not in NOTIONALS_BY_QUOTE:
            pairs_out_of_scope += 1
            logger.info(
                "panel skipping pair=%s: no notional ladder for its quote (add one to NOTIONALS_BY_QUOTE)",
                seg_pair,
            )
            continue
```

Update the `from cli.panel.primitives import ...` line to import `NOTIONALS_BY_QUOTE` instead of `PANEL_QUOTE`.

- [ ] **Step 4: Run to verify it passes — INCLUDING the file this breaks**

Run: `uv run pytest tests/test_panel_materialize.py tests/test_panel_command.py tests/test_data_rebuild.py -v`

Expected: `tests/test_panel_command.py::test_materialize_skips_non_eur_quoted_pairs_in_the_sweep` (at `:420-439`) now FAILS — it asserts `pairs_out_of_scope == 1` and `not (panel_root/"ETH"/"BTC").exists()`, both of which this task deliberately inverts. Rewrite it to use a quote with no ladder (`ETH/USD`), which is the property that actually survives.

`tests/test_data_rebuild.py` must stay GREEN here: its `entries["ETH/BTC"] is None` and `unevaluated_count == 1` assertions are what prove `rebuild.py`'s guard is still closed (spec D6). It is included in every run from here to Task 6 for exactly that reason — the guard-order property must be proven by a passing test at each step, not by nobody having touched the file.

- [ ] **Step 5: Commit**

```bash
git add cli/panel/materialize.py tests/test_panel_materialize.py tests/test_panel_command.py
git commit -m "feat(panel): the sweep materializes every quote that has a ladder"
```

---

### Task 4: Generation manifest carries the per-quote ladder; the two remaining EUR refusals lift

**Files:**
- Modify: `cli/panel/command.py`, `cli/panel/materialize.py` (the meta writer)
- Test: `tests/test_panel_command.py`, **`tests/test_panel_materialize.py`** (`:439-440` pins `schema_version == 2` and `notionals_eur`; the second assertion inverts)

**Tests this task breaks and must fix — all of them, by name:**
- `tests/test_panel_materialize.py::test_write_meta_writes_the_generation_manifest` (`:439-440`) — `notionals_eur` → `notionals_by_quote`.
- `tests/test_panel_command.py:118` — same key in the manifest assertion.
- `tests/test_panel_command.py::test_an_out_of_scope_subtree_refuses_because_no_sweep_can_ever_repair_it` (`:172-192`) — **this is the dangerous one.** It plants its stray at `ETH/BTC`, which this task makes legitimate, so the refusal stops firing and the test goes red. It must be re-pointed at a quote with **no ladder** (`ETH/USD`). That guard is the only thing standing between the tree and a manifest describing a generation its hours do not share — losing it silently would be worse than the bug this iteration fixes.
- `tests/test_panel_command.py::test_materialize_refuses_an_explicit_non_eur_pair` (`:442`) — keeps its shape but must use `ETH/USD`, and its `assert "EUR" in result.output` becomes the new message's wording.

**Interfaces:**
- Consumes: `NOTIONALS_BY_QUOTE` from Task 1.
- Produces: `panel-meta.json` key `notionals_by_quote: {"EUR": [...], "BTC": [...]}` **replacing** `notionals_eur`; `_expected_generation` compares the new key. **`SCHEMA_VERSION` stays 2** (spec Rollout): no column changes, that constant documents itself as tracking column-set generations, and the key swap alone already makes every existing tree mismatch.

- [ ] **Step 1: Write the failing test**

```python
def test_the_generation_manifest_records_the_per_quote_ladder():
    from cli.panel.command import _expected_generation

    gen = _expected_generation()
    assert gen["schema_version"] == 2  # unchanged: no column moved
    assert gen["notionals_by_quote"]["EUR"] == [100.0, 1_000.0, 10_000.0]
    assert "BTC" in gen["notionals_by_quote"]
    assert "notionals_eur" not in gen


def test_a_tree_built_on_the_old_eur_only_manifest_refuses(tmp_path: Path) -> None:
    # A panel-meta.json carrying the OLD generation must abort: its columns mean something else now.
    # This is the regeneration gate doing its job, and it is what forces the Task 6 rebuild.
    panel_root = tmp_path / "l2-panel"
    panel_root.mkdir(parents=True)
    (panel_root / "panel-meta.json").write_text(
        json.dumps({"schema_version": 2, "grid": "1s", "notionals_eur": [100.0, 1_000.0, 10_000.0], "k_levels": [1, 5, 10]})
    )
    # schema_version matches; the LADDER KEY does not. That alone must refuse -- which is why no
    # SCHEMA_VERSION bump is needed to force the regeneration.

    with pytest.raises(typer.Exit):
        _check_generation(panel_root)


def test_a_btc_quoted_pair_is_accepted_by_the_pair_option(tmp_path: Path) -> None:
    # Follows test_materialize_refuses_an_explicit_non_eur_pair (:442) exactly: the primary tree and
    # --panel-root are REQUIRED parameters, and Click fails on a missing one BEFORE the function body
    # runs -- so an invocation without them would pass vacuously and prove nothing.
    primary, panel_root = tmp_path / "primary", tmp_path / "panel"
    _seed_primary(primary, "ETH/BTC", H)

    ok = runner.invoke(
        app,
        ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0", "--pair", "ETH/BTC"],
    )
    assert ok.exit_code == 0, ok.output

    _seed_primary(primary, "ETH/USD", H)
    refused = runner.invoke(
        app,
        ["panel", "materialize", str(primary), "--panel-root", str(panel_root), "--settle-hours", "0", "--pair", "ETH/USD"],
    )
    assert refused.exit_code != 0, refused.output
    assert "notional ladder" in refused.output
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_panel_command.py -k per_quote_ladder -v`
Expected: FAIL — `KeyError: 'notionals_by_quote'`

- [ ] **Step 3: Implement**

- `cli/panel/materialize.py:417` and `cli/panel/command.py:62`: replace `"notionals_eur": list(NOTIONALS_EUR)` with `"notionals_by_quote": {q: list(v) for q, v in sorted(NOTIONALS_BY_QUOTE.items())}`.
- `cli/panel/command.py:91-100`: the stray-scope abort now compares against `NOTIONALS_BY_QUOTE` membership instead of `PANEL_QUOTE`.
- `cli/panel/command.py:113-122` (`_affected_pairs`): same membership change.
- `cli/panel/command.py:211-215`: the `--pair` refusal fires only when the quote has no ladder; update the `--help` text at `:183` to say "must have a notional ladder (EUR, BTC)".

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_panel_command.py tests/test_panel_materialize.py tests/test_data_rebuild.py -v`
Expected: PASS once the four named tests above are updated. `:116`'s `schema_version == 2` is unchanged and stays. `tests/test_data_rebuild.py` must still be green — the guard is still closed.

- [ ] **Step 5: Commit**

```bash
git add cli/panel/ tests/test_panel_command.py tests/test_panel_materialize.py
git commit -m "feat(panel): generation manifest carries the per-quote ladder; scope guards lift"
```

- [ ] **Step 6: Prove BOTH guards bite — AFTER the commit**

The generation refusal:
```bash
infra/scripts/mutate-probe.sh --file cli/panel/command.py \
  --control 's/def _expected_generation/def _expected_generation_renamed/' \
  --mutation 's/"notionals_by_quote"/"notionals_eur"/' \
  -- uv run pytest tests/test_panel_command.py -k per_quote_ladder -q
```

And the stray-scope refusal, which this task rewrote and must still bite:
```bash
infra/scripts/mutate-probe.sh --file cli/panel/command.py \
  --control 's/def _check_generation/def _check_generation_renamed/' \
  --mutation 's/if h.parts\[-6\] not in NOTIONALS_BY_QUOTE/if False/' \
  -- uv run pytest tests/test_panel_command.py -k out_of_scope_subtree -q
```
Expected: `KILLED` for both.

---

### Task 5: The committed calibration script

**Files:**
- Create: `cli/costs/calibrate.py`
- Test: `tests/test_costs_calibrate.py`

**Interfaces:**
- Produces: `calibrate(panel_root: Path, window_start: datetime, window_end: datetime) -> CalibrationResult` — a frozen dataclass with `table: dict[str, dict[int, float]]` (full-symbol keys, EUR-notional inner keys), `hours: int`, `min_rows: int`, `max_rows: int`, `btc_eur_reference: float`.

**`hours` means hourly files PER PAIR, not summed pair-hours.** `docs/reference/captured-spread-calibration.md` defines the existing `CALIBRATION_HOURS = 353` that way, and Task 7 restamps that constant from this field — a summed-hours reading would silently multiply it by the pair count inside a restamp nobody is auditing. Where pairs differ, take the minimum and let `max_rows - min_rows` expose the spread.

- [ ] **Step 1: Write the failing test**

Build the panel tree directly with polars — the calibration reads panel output, not capture segments, so no book fixtures are needed. Write two hours per pair at `<BASE>/<QUOTE>/panel-1s/<YYYY>/<MM>/<DD>/<HH>.parquet` with the columns the query reads (`ts`, `mid`, `fill_bps_bid_100`, `fill_bps_ask_100`, and the `1k`/`10k` pairs).

```python
def _panel_hour(root: Path, pair: str, hour: datetime, *, mid: float, fill: float) -> None:
    base, quote = pair.split("/")
    p = root / base / quote / "panel-1s" / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}" / f"{hour:%H}.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 3600
    pl.DataFrame({
        "ts": [hour + timedelta(seconds=i) for i in range(n)],
        "mid": [mid] * n,
        **{f"fill_bps_{side}_{sfx}": [fill] * n for side in ("bid", "ask") for sfx in ("100", "1k", "10k")},
    }).write_parquet(p)


def test_calibrate_produces_full_symbol_keys_and_provenance(tmp_path: Path) -> None:
    panel_root = tmp_path / "l2-panel"
    W_START = datetime(2026, 7, 24, 0, tzinfo=timezone.utc)
    W_END = datetime(2026, 7, 24, 2, tzinfo=timezone.utc)
    for h in (0, 1):
        _panel_hour(panel_root, "BTC/EUR", W_START + timedelta(hours=h), mid=60_000.0, fill=1.5)
        _panel_hour(panel_root, "ETH/BTC", W_START + timedelta(hours=h), mid=0.03, fill=2.5)

    expected_mean_mid = 60_000.0
    result = calibrate(panel_root, W_START, W_END)
    assert set(result.table) == {"BTC/EUR", "ETH/BTC"}
    assert set(result.table["ETH/BTC"]) == {100, 1_000, 10_000}
    assert result.hours == 2  # hourly files PER PAIR, not 2 pairs x 2 hours
    # Joint-sampling: the doc's provenance rests on row counts agreeing across pairs. A bare
    # `min_rows > 0` would sail straight through a partial NAS pull of the two new legs.
    assert result.max_rows - result.min_rows <= 5
    # The FX reference is derived from BTC/EUR mids in the same window, not hardcoded.
    assert result.btc_eur_reference == pytest.approx(expected_mean_mid, rel=1e-9)


def test_calibrate_refuses_a_window_with_no_btc_eur_data(tmp_path: Path) -> None:
    # The FX reference has no source without BTC/EUR -- refuse rather than emit an unpinned table.
    from cli.costs.errors import CostModelError  # check the real module; spread.py imports it too

    panel_root = tmp_path / "l2-panel"
    W_START = datetime(2026, 7, 24, 0, tzinfo=timezone.utc)
    W_END = datetime(2026, 7, 24, 2, tzinfo=timezone.utc)
    for h in (0, 1):
        _panel_hour(panel_root, "ETH/BTC", W_START + timedelta(hours=h), mid=0.03, fill=2.5)

    with pytest.raises(CostModelError, match="no BTC/EUR"):
        calibrate(panel_root, W_START, W_END)


def test_the_committed_script_reproduces_the_table_it_replaces():
    """The script becomes the provenance of record (spec D5), and Task 7 replaces all ten EUR rows
    in the same commit that introduces it -- so a transcription error and the window move would be
    indistinguishable in one diff. Run it over the OLD window and require the OLD table.

    Marked slow: it reads the real panel tree from the read-only NAS mount.
    """
    from cli.costs.spread import CALIBRATION_WINDOW, SPREAD_CALIBRATION

    panel_root = Path("/mnt/zhao-crypto/l2-panel")
    if not panel_root.exists():
        pytest.skip("panel tree not mounted")

    start, end = (datetime.fromisoformat(w.replace("Z", "+00:00")) for w in CALIBRATION_WINDOW)
    result = calibrate(panel_root, start, end)

    for base, rows in SPREAD_CALIBRATION.items():          # pre-re-key: base-keyed
        for size, expected in rows.items():
            assert result.table[f"{base}/EUR"][size] == pytest.approx(expected, abs=0.01)
```

Run this BEFORE Task 7 rewrites the table, while the old rows are still committed — that is the only moment the comparison is available.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_costs_calibrate.py -v`
Expected: FAIL — `ModuleNotFoundError: cli.costs.calibrate`

- [ ] **Step 3: Implement**

`cli/costs/calibrate.py` scans `panel_root/<BASE>/<QUOTE>/panel-1s/**` with `pl.scan_parquet`, computes per-pair per-rung `mean((fill_bps_bid_X + fill_bps_ask_X) / 2)` over the window, derives `btc_eur_reference` as the mean `mid` of `BTC/EUR` over the same window, and returns the frozen `CalibrationResult`. It replaces the prose query at `docs/reference/captured-spread-calibration.md`.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_costs_calibrate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cli/costs/calibrate.py tests/test_costs_calibrate.py
git commit -m "feat(costs): commit the spread calibration query as runnable code"
```

---

### Task 6: Ops converge and the panel regeneration

**Files:** none in the repo — this is the rollout. Every host-touching command runs in the MAIN LOOP, never in a subagent.

- [ ] **Step 1: Record the running ops digest in `docs/reference/fleet-pins.md` before converging**

The pins assert refuses otherwise, and that row is the only rollback operand.

- [ ] **Step 2: Build the ops image from this branch's HEAD; pull it on `zcrypto-ops`**

Not "the merge commit" — Task 8 forbids opening the PR without the owner's word, so no merge commit exists yet.

Every runner is `--pull never`; the role's digest preflight refuses a digest the host has not pulled.

- [ ] **Step 3: Verify the payload from the image's own surface**

```bash
sudo docker run --rm --entrypoint python <image>@sha256:<digest> -c "
import inspect, cli.panel.primitives as p
print('per-quote ladder:', 'NOTIONALS_BY_QUOTE' in inspect.getsource(p))
print('BTC rungs differ from EUR:', p.notionals_for('BTC') != p.notionals_for('EUR'))
print('FX reference:', p.BTC_EUR_REFERENCE)
"
```

- [ ] **Step 4: Converge ops**

```bash
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops \
  -e ops_image_digest=sha256:<digest> -e liquidations_decision=roll-after \
  -e ops_panel_timer_hold=true
```
`ops_panel_timer_hold=true` is required: the role's enable-and-start task otherwise re-arms the timer inside the regeneration window.

- [ ] **Step 5: Regenerate the panel tree**

On `zcrypto-ops`, attended, in a real terminal: `zcrypto-panel-regenerate`. It stops the timer, sizes the window against the 02:25 UTC auto-reboot, takes the healthchecks.io pause as a typed gate, deletes the ops-side tree, rebuilds inside the unit, restarts the timer on success, and prints the closing checklist. **Record the completion line whole**, both unanchored counts included — it is printed before the timer restart for exactly this reason.

- [ ] **Step 6: Work the closing checklist — measuring, not confirming**

Un-pause the healthchecks check FIRST; it is the timer's only liveness signal.

Then the NAS question. Run the checklist's measure-first commands and read what they return — do **not** set out to confirm a claim, which is how a measurement becomes a formality. The expected result is an empty `comm -13` (a ladder change rewrites identical paths; `/BTC` subtrees are additive), but the action depends on what actually comes back:

- **Empty**: nothing is owed. Record that it was measured and stop.
- **Non-empty and `hours_unanchored == 0`**: every candidate is a real orphan and may be deleted on the NAS.
- **Non-empty and `hours_unanchored != 0`**: delete NOTHING until every candidate is accounted for against the per-run `unanchored` WARNINGs. A NAS-only file may be the last copy of an hour the rebuild could not reproduce, and the pull runs outward from ops.
- **Counts unreadable**: delete nothing. An unread count is not a zero.

- [ ] **Step 7: Verify by outcome — through the mandated command**

Run `infra/scripts/ops-postverify.sh`. `capture-deploys.md` names it as *the* ops-converge outcome check: six checks in one command, and `(no series)` reads FAIL, never a zero. Hand-picking two metrics instead is how a converge gets declared good on a subset.

Then, specific to this iteration: `ETH/BTC` and `SOL/BTC` subtrees exist with **non-null** `fill_bps_*` in a spot-checked hour — the whole point of the ladder change.

- [ ] **Step 8: Gate Task 7 on the outward pull completing**

Task 7 calibrates from the **pulled** NAS copy, and the two `/BTC` subtrees are brand new there. Before calibrating, confirm the NAS pull has run to completion *after* the regeneration: the archive-pull loop's next cycle reports `failed=0`, and the `/BTC` hour count on the pulled copy equals the ops-side count. A partial pull yields a quietly short window that only `max_rows - min_rows <= 5` would catch — do not rely on that alone.

---

### Task 7: Recalibrate, re-key, and lift the last guard

**Files:**
- Modify: `cli/costs/spread.py`, `cli/data/rebuild.py`, `docs/reference/captured-spread-calibration.md`
- Test: `tests/test_costs_spread.py`, `tests/test_data_rebuild.py`

**The whole provenance block in `tests/test_costs_spread.py` is in scope and must be rewritten, not patched around:** `EXPECTED` (`:22-33`, ten base-keyed rows) → twelve full-symbol rows; `assert SPREAD_CALIBRATION == EXPECTED` (`:37`); the three provenance pins (`:44-46`); and the parametrization `@pytest.mark.parametrize("pair", sorted(EXPECTED))` feeding `effective_spread_bps(pair, size)` (`:50-52`), whose members are now full symbols. This file IS the "a recalibration is a deliberate edit, never silent drift" gate — if it needed no edit, the recalibration did not happen.

Also inverting: `tests/test_data_rebuild.py:262` calls `effective_spread_bps("BTC", ...)` with a bare base, which raises after the re-key.

**Interfaces:**
- Consumes: `calibrate()` from Task 5, run against the regenerated tree from Task 6.

- [ ] **Step 1: Run the calibration on the PULLED copy**

```bash
uv run python -c "
from pathlib import Path; from datetime import datetime, timezone
from cli.costs.calibrate import calibrate
r = calibrate(Path('/mnt/zhao-crypto/l2-panel'),
              datetime(2026,7,23,14,tzinfo=timezone.utc),
              datetime(2026,8,6,6,tzinfo=timezone.utc))
print(r)
"
```

Never the live dir. Record the exact window end actually used.

- [ ] **Step 2: Write the failing test for the re-keyed table**

```python
def test_the_table_is_keyed_by_full_symbol_and_covers_the_btc_legs():
    from cli.costs.spread import SPREAD_CALIBRATION, effective_spread_bps

    assert "BTC/EUR" in SPREAD_CALIBRATION and "ETH/BTC" in SPREAD_CALIBRATION
    assert len(SPREAD_CALIBRATION) == 12
    assert not any("/" not in k for k in SPREAD_CALIBRATION)  # no bare bases survive
    # The old silent-wrong-value path is now loud.
    with pytest.raises(CostModelError):
        effective_spread_bps("ETH", 1_400)
    assert effective_spread_bps("ETH/BTC", 1_400) > 0
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_costs_spread.py -k full_symbol -v`
Expected: FAIL — `"BTC/EUR" not in SPREAD_CALIBRATION`

- [ ] **Step 4: Apply the table, provenance, and doc restamp together**

Update `SPREAD_CALIBRATION` (twelve full-symbol rows), `CALIBRATION_WINDOW` / `CALIBRATION_HOURS` / `CALIBRATION_MIN_ROWS`, and `docs/reference/captured-spread-calibration.md` — table, provenance, the maintenance-window caveat (2026-08-06 07:01–07:18Z), and the query section now pointing at `cli/costs/calibrate.py`. These move together or not at all.

**Assert the FX agreement over the REFERENCE's own window** — `BTC_EUR_REFERENCE_WINDOW`, not the calibration window of Step 1, which by then ends days later (spec D1). Re-run `calibrate()` over `BTC_EUR_REFERENCE_WINDOW` and require `result.btc_eur_reference == cli.panel.primitives.BTC_EUR_REFERENCE` to within 1e-9 relative. A mismatch means Task 1's constant and the regenerated tree disagree about what a BTC rung is worth — stop and reconcile before touching the table, because every BTC `fill_bps_*` in the tree was computed against Task 1's value.

**Commit this as a test, not a step.** A prose instruction in a task list is archived the moment the iteration closes; the property has to outlive it:

```python
def test_the_fx_reference_still_matches_what_the_tree_was_built_with():
    """BTC_EUR_REFERENCE defines what every BTC fill_bps_* column in the materialized tree MEANS.
    A breach here means either the tree must be regenerated or the divergence must be explained --
    it NEVER means updating the constant to match a newer window. The calibration window may move
    at a restamp; this one may not.
    """
    from cli.costs.calibrate import calibrate
    from cli.panel.primitives import BTC_EUR_REFERENCE, BTC_EUR_REFERENCE_WINDOW

    panel_root = Path("/mnt/zhao-crypto/l2-panel")
    if not panel_root.exists():
        pytest.skip("panel tree not mounted")
    start, end = (datetime.fromisoformat(w.replace("Z", "+00:00")) for w in BTC_EUR_REFERENCE_WINDOW)

    assert calibrate(panel_root, start, end).btc_eur_reference == pytest.approx(BTC_EUR_REFERENCE, rel=1e-9)
```

- [ ] **Step 5: Lift the rebuild quote guard — and only now**

In `cli/data/rebuild.py:183-187`, the code reads **verbatim**:

```python
    spreads = {
        symbol: round(effective_spread_bps(symbol.split("/")[0], SPREAD_REFERENCE_NOTIONAL_EUR), 3)
        for symbol in symbols
        if symbol.split("/")[1] == "EUR" and symbol.split("/")[0] in SPREAD_CALIBRATION
    }
```

Both lines change — the lookup key *and* the guard. The spec's paraphrase says `base in SPREAD_CALIBRATION`; the actual text is `symbol.split("/")[0] in SPREAD_CALIBRATION`, so a literal search-and-replace on the paraphrase silently no-ops:

```python
    spreads = {
        symbol: round(effective_spread_bps(symbol, SPREAD_REFERENCE_NOTIONAL_EUR), 3)
        for symbol in symbols
        if symbol in SPREAD_CALIBRATION
    }
```

- [ ] **Step 6: Run the affected tests and fix the pins that legitimately invert**

Run: `uv run pytest tests/test_costs_spread.py tests/test_data_rebuild.py -v`
Expected: `test_data_rebuild.py`'s `entries["ETH/BTC"] is None` inverts to a value, and `unevaluated_count == 1` becomes `0`. Both are the point of the change, not breakage.

- [ ] **Step 7: Prove the guard-order invariant**

```bash
git add cli/costs/spread.py cli/data/rebuild.py docs/reference/captured-spread-calibration.md tests/
git commit -m "feat(costs): recalibrate all twelve legs and re-key the table by full symbol"
```

- [ ] **Step 8: Prove the re-key bites — AFTER the commit**

```bash
infra/scripts/mutate-probe.sh --file cli/data/rebuild.py \
  --control 's/if symbol in SPREAD_CALIBRATION/if False/' \
  --mutation 's|effective_spread_bps(symbol,|effective_spread_bps(symbol.split("/")[0],|' \
  -- uv run pytest tests/test_data_rebuild.py -q
```
Expected: `KILLED` — passing a bare base must now fail loudly rather than return the EUR row.

---

### Task 8: Closeout

- [ ] **Step 1: Resolve [[T0092]]** — `status: resolved`, `ripe_when` deleted, file moved to `docs/open-topics/archive/`, index bullet moved to the category's `### Resolved` with the archived path. Per `topic-ops`.

- [ ] **Step 2: The docs rewrite the topic's closeout list names** — resolve every target **by content, not by the topic's line numbers**, all of which have drifted: the quote guard, the "no capture" sites in `cli/data/rebuild.py`, `cli/universe/rules.py`, `cli/universe/build.py` and their tests, `docs/reference/data-catalog-full.md`'s scope clause, and `captured-spread-calibration.md`'s scope and query sites.

- [ ] **Step 3: Update `docs/reference/data-catalog-full.md`** — the panel dataset's scope is no longer EUR-only; record the per-quote ladder and the FX-reference provenance.

- [ ] **Step 4: Append the iterations-history entry** to the phase-6 changelog per `iteration-closeout`. Re-verify every status claim against the full branch log immediately before PR-open.

- [ ] **Step 5: Decisions-log entry** in the phase-6 decisions log for D1 (rung denomination) and D2/D4 (window shape), each with its options and the owner's pick.

- [ ] **Step 6: Update `docs/reference/fleet-pins.md`** with the ops digest actually converged, and confirm every row and bullet agrees with the hosts.

- [ ] **Step 7: Report the branch ready.** Do not open the PR without the owner's explicit word.
