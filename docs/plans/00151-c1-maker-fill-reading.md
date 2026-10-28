# C1 reading 1 — the queue-position fill model over the captured book, and the reversal surface at the maker hurdle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A producer that derives the frozen dataset `data/l2-fills-<stamp>/` — spec 00151 D2's queue-position fill model over the captured depth-100 book and healed trades — and a reading subject `c1-maker-fill-reading` over it that lands as reading 8 on `docs/reference/reading-ledger.jsonl`, its potential criterion fixed before the hash.

**Architecture:** The fill model is pure code in a new `cli/panel/fills.py` — orders posted on a 15-second grid, a queue-ahead quantity, a fill-or-cancel rule driven by the replayed book and trades — riding `materialize_hour`'s message loop unchanged (`regroup_messages`, `OrderBook`), with the producer and its `zcrypto panel fills` command beside the panel's. The dataset is written one day per pair-file with a `.sha256` sidecar and a conformant `manifest.json` (`cli/data/manifest.py::build_manifest`), so `ObservedReader` attests it as it attests `ohlc-15m`. The reading subject in `cli/research/subjects.py` is built in two halves like spec 00150's — inputs (coverage and counts, no fill outcome) and computes (the fill table, the 96 cells) — its pure functions in a new `cli/alpha/c1.py` reusing `cli/alpha/c2.py`'s returns, scale, signals, `cell_reads` and `rank_ic`. The production is the controller's, on the ops host, after the branch's reads and the spec's hash; the run, the ledger line, the entry, T0016 and the retirement follow plan 00150's Tasks 4–6.

**Tech Stack:** Python 3.14, polars, `cli.archive.reader.canonical_segments`, `cli.archive.replay.regroup_messages`, `cli.capture.book.OrderBook`, `cli.panel.materialize` (`load_state`, `write_state`, `write_hour`'s form), `cli.data.manifest`, `cli.ohlc.dataset.dataset_hash`, `cli.validation.spa.reality_check_pvalue`, pytest.

**Spec:** `docs/specs/00151-c1-maker-fill-reading-design.md`

## Global Constraints

- The hash rule (spec D6): before the spec's sha256 is taken, no program runs the producer over the real archive, reads a fill outcome or a post-fill mid over it, or computes a cell; the producer and the reading are proven on synthetic hours alone. Only the controller reads `/mnt/zhao-crypto/`; a dispatch never does, and never links `data/l2-fills-*` into its worktree.
- The constants, verbatim: posting grid 15 s; sizes the first two rungs of `notionals_for(quote)` (€100, €1,000 in the quote, the BTC quantities at the panel's pinned FX reference for BTC-quoted pairs); the order joins the back of the queue (`queue_ahead_qty` = the level's resting quantity at the post); full fill or none; cancel when the best quote on the order's side has moved away from its price by one tick or more for 5 consecutive seconds, or at the horizon 900 s; stale book skipped at `stale_seconds > 30`; horizons read at 60, 300, 900 s; the reversal surface's lags and scale as `cli/alpha/c2.py`'s (`trailing_std` window 96, `moves` lag 1), thresholds `(1, 2)`, the trade's horizon 3,600 s; the maker round trip `0.0080`; `mean_block` 30, `n_resamples` 4000, `seed` 42; the span `2026-08-01T00:00:00Z` → `2026-10-27T23:59:59Z`; the twelve pairs `ADA/EUR, AVAX/EUR, BTC/EUR, DOGE/EUR, DOT/EUR, ETH/EUR, LINK/EUR, LTC/EUR, SOL/EUR, XRP/EUR, ETH/BTC, SOL/BTC`.
- A cell's name: `f"{pair}|th{threshold}|S{size}|{side}"` with `size` the rung index 0 or 1 and `side` `bid` or `ask`, e.g. `BTC/EUR|th2|S0|bid`.
- The dataset's layout: `data/l2-fills-<stamp>/<BASE>/<QUOTE>/<YYYY>/<MM>/<DD>.parquet` + `.sha256` (the `dataset_hash` of the frame), `manifest.json` conformant (`build_manifest`, `identity="set"`, `series` keyed by relpath, `provenance` naming the producer's code ref and parameters); the stamp is the production's start, `YYYYMMDDTHHMMSSZ`. The rows' columns, in this order: `ts, pair, side, size, mid_at_post, spread_at_post_bps, stale_seconds_at_post, queue_ahead_qty, queue_ahead_notional, our_qty, filled, time_to_fill_s, cancelled_s, fill_price, mid_at_fill_plus_60s, mid_at_fill_plus_900s, mid_at_post_plus_900s, mid_at_post_plus_3600s` — `ts` the post's instant (Datetime µs UTC), `side` `"bid"`/`"ask"`, `size` `0`/`1`, booleans and Float64s, the post-fill mids null when unfilled and the mids at an instant past the data's end null.
- Commits: Conventional Commits, one subject per change; the message says what changed and the result line of the test command it names, pasted; one state-changing git command per Bash call, nothing beside it; never an amend, `--no-verify` or `git stash`; every commit ends with the two trailer lines the dispatch names.
- A comment or docstring stays only where a reader would do something differently without it, and has to be correct; a spec citation names the D-section.
- Probes: on this `full`-tier plan, every new guard through its own `-k` case with `infra/scripts/mutate-probe.sh` on a committed tree, the verdict lines into `.local/iter196/probes-task-<N>.txt` (one `mkdir -p .local/iter196` first; the file started empty by `: > <file>`), carried whole into the next task's first commit message after a `grep -c 'mutate-probe: KILLED'` that must print the task's row count; `--basetemp=.tmp/implementer/pt` after each probe's `--`.
- The worktree is `.claude/worktrees/iter196`; the main checkout at `/home/zhaow/Projects/zcrypto-kraken` is live.

## Review Focus

1. A trade at exactly the order's price on the wrong aggressor side (a buy at our bid price) — never fills a bid. Pinned in Task 1's `test_a_trade_on_the_wrong_side_never_fills`.
2. A level removal (`qty` 0 at the order's price) while the order rests — the best quote moves; the cancel clock starts, and fills until the cancel still count. Pinned in Task 1's `test_a_removed_level_starts_the_cancel_clock_and_a_fill_before_it_counts`.
3. A post at a stale book (`stale_seconds > 30`) — skipped and counted, no row. Pinned in Task 1's `test_a_stale_book_skips_the_post_and_counts_it`.
4. An hour opening with an update and no carried book — the producer refuses the hour as the panel does, counts it, and resumes at the next snapshot; orders carried across the hour boundary keep their clocks. Pinned in Task 2's `test_an_unanchored_hour_is_skipped_and_counted` and Task 1's `test_an_order_carried_across_the_hour_keeps_its_clock`.
5. The post-fill mid at an instant past the data's end — null, never the last mid carried. Pinned in Task 1's `test_a_mid_past_the_data_end_is_null`.

---

### Task 1: the fill model in `cli/panel/fills.py`

**Files:**
- Create: `cli/panel/fills.py`
- Test: `tests/test_panel_fills.py`

**Interfaces:**
- Produces, all in `cli/panel/fills.py`:
  - `GRID_S = 15`; `HORIZON_S = 900`; `CANCEL_AFTER_S = 5`; `STALE_S = 30`; `SIZE_RUNGS = (0, 1)`; `MID_OFFSETS_S = (60, 900, 3600)`; `COLUMNS` the eighteen names of the Global Constraints in order.
  - `@dataclass class Order`: `ts: datetime`, `side: str`, `size: int`, `price: float`, `our_qty: float`, `queue_ahead_qty: float`, `mid_at_post: float`, `spread_at_post_bps: float`, `stale_seconds_at_post: float | None`, `filled_qty: float = 0.0`, `away_since: datetime | None = None`, `filled_at: datetime | None = None`, `fill_price: float | None = None`, `cancelled_at: datetime | None = None`.
  - `post_orders(book: OrderBook, ts: datetime, quote: str, *, stale_seconds: float | None) -> list[Order]` — the four orders (two sides × two rungs) at the best bid and ask; `[]` when a side is empty or `stale_seconds is not None and stale_seconds > STALE_S`; `our_qty` = notional / price for the rung's notional (`notionals_for(quote)[rung]`).
  - `apply_trade(order: Order, trade: dict) -> None` — a trade `{"ts", "side", "price", "qty"}`: a `sell` at `price <= order.price` on a `bid` order, a `buy` at `price >= order.price` on an `ask` order, adds `qty` to `filled_qty`; when `filled_qty >= queue_ahead_qty + our_qty` the order fills at `order.price` with `filled_at = trade["ts"]`; any other trade changes nothing.
  - `tick_cancel(order: Order, book: OrderBook, ts: datetime, tick: float) -> None` — the best quote on the order's side read from `book`; away when `|best − order.price| >= tick`; `away_since` set on the first away second, cleared when back; `cancelled_at = ts` when away for `>= CANCEL_AFTER_S` seconds or `ts − order.ts >= HORIZON_S`.
  - `pair_tick(book: OrderBook) -> float` — the smallest positive price gap between consecutive levels on either side, the tick's proxy; `AlphaError`-free: returns `0.0` on a one-level book, and `tick_cancel` with tick `0.0` treats any move as away.
  - `simulate_hour(messages: list[dict], trades: list[dict], book: OrderBook, hour: datetime, *, quote: str, carried: list[Order], last_msg_ts: datetime | None) -> tuple[list[dict], list[Order], OrderBook, datetime | None, dict]` — the panel's second loop: at each second boundary apply the messages up to it, then the trades up to it against every open order (`apply_trade`), then `tick_cancel` every open order, then on a grid second (`second % GRID_S == 0`) `post_orders`; an order closed in the hour (filled or cancelled) becomes a row dict once its latest mid offset has passed or the hour ends (a mid at an instant past the hour is left for the carry: an order whose offsets are still pending is carried with its outcome); returns `(rows, carried_open_or_pending, book, last_msg_ts, counts)` with `counts = {"posts", "skipped_no_quote", "skipped_stale"}`. The mids at `fill + 60 s`, `fill + 900 s`, `post + 900 s`, `post + 3600 s` are the book's mid at the first second boundary at or after that instant; null when the data ends before it.
  - `rows_frame(rows: list[dict]) -> pl.DataFrame` — the `COLUMNS` schema, sorted by `ts`, `side`, `size`.

- [ ] **Step 1: Write the failing tests** — a synthetic-hour builder `_hour(bids, asks, messages, trades)` from level lists; the cases, each on a known answer: `test_post_orders_make_four_at_the_touch_with_the_rungs_quantities`; `test_post_orders_skip_an_empty_side`; `test_a_stale_book_skips_the_post_and_counts_it`; `test_a_sell_at_or_below_our_bid_fills_once_the_queue_ahead_is_consumed` (queue ahead 1.0, our 0.1, trades 0.6 and 0.5 → filled at the second, `filled_at` its ts, `fill_price` the bid); `test_a_partial_consumption_leaves_the_order_open`; `test_a_trade_on_the_wrong_side_never_fills`; `test_a_removed_level_starts_the_cancel_clock_and_a_fill_before_it_counts`; `test_the_cancel_fires_after_five_consecutive_away_seconds_and_resets_when_back`; `test_the_horizon_cancels_at_900_seconds`; `test_the_mid_offsets_are_read_at_the_first_boundary_at_or_after_the_instant`; `test_a_mid_past_the_data_end_is_null`; `test_an_order_carried_across_the_hour_keeps_its_clock` (an order posted at :59:50 with a fill at the next hour's :00:03 fills with `time_to_fill_s` 13); `test_pair_tick_is_the_smallest_level_gap_and_zero_on_a_one_level_book`; `test_rows_frame_has_the_eighteen_columns_in_order`.
- [ ] **Step 2: Run them red** — `uv run pytest tests/test_panel_fills.py -q -p no:cacheprovider` → `ImportError`.
- [ ] **Step 3: Implement** the module with the Interfaces' signatures; `simulate_hour`'s loop in `materialize_hour`'s form (`regroup_messages` is the caller's; `simulate_hour` takes messages).
- [ ] **Step 4: Run green** — the file's count stated.
- [ ] **Step 5: Commit** — `feat(panel): the queue-position fill model — orders at the touch on a 15 s grid, queue ahead, fill or cancel, the mids after`.
- [ ] **Step 6: Probe** — on the committed tree, one `mutate-probe.sh` per guard through its case: the wrong-side fill (mutation: the side test dropped), the stale skip (`> STALE_S` → `> 10**9`), the cancel after five (`>= CANCEL_AFTER_S` → `>= 10**9`), the horizon, the null mid past the end (the null arm dropped), the carried clock (`time_to_fill_s` from the hour start instead of the post) — verdict lines into `.local/iter196/probes-task-1.txt`.

---

### Task 2: the producer and `zcrypto panel fills`

**Files:**
- Modify: `cli/panel/fills.py` (the producer half), `cli/panel/command.py` (the `fills` and `fills-manifest` commands)
- Test: `tests/test_panel_fills_producer.py`, `tests/test_panel_command.py` (the new commands' rows, if the file parametrises the sub-app)

**Interfaces:**
- Consumes Task 1.
- Produces:
  - `produce_pair(primary_root: Path, reconciled_root: Path | None, out_root: Path, pair: str, *, since: datetime, until: datetime, depth: int = 100) -> dict` — the hours of `canonical_segments(primary_root, reconciled_root, kind="book")` for the pair inside `[since, until]` in yield order, each paired with its trades hour (`kind="trades"`, the same `(pair, hour)`; an absent trades hour is an hour with no trades); the book threaded in memory across consecutive hours (an hour opening with a snapshot re-anchors; an update-opening hour with no carried book is skipped and counted, `unanchored_hours`, and every open order is dropped, counted `orders_dropped`); rows accumulated per UTC day and written at each day's end to `<out_root>/<BASE>/<QUOTE>/<YYYY>/<MM>/<DD>.parquet` with its `.sha256` (`dataset_hash`), a day re-run skipped when its file exists (the watermark is the files); returns the counts `{"hours", "unanchored_hours", "orders_dropped", "posts", "skipped_no_quote", "skipped_stale", "days_written"}`.
  - `write_fills_manifest(out_root: Path, *, params: dict, code_ref: str, written_at: str) -> Path` — `series` = `{relpath: series_entry(frame, relpath)}` over every day file, `provenance = {"producer": "zcrypto panel fills", "code_ref": code_ref, "params": params}`, `build_manifest(...)` written to `manifest.json`; refuses (`PanelError`) a tree whose `.sha256` sidecar disagrees with its file.
  - CLI: `zcrypto panel fills PRIMARY_ROOT OUT_ROOT --reconciled-root PATH --pair PAIR --since ISO --until ISO` (one pair per process; the controller runs them in parallel) and `zcrypto panel fills-manifest OUT_ROOT` (after every pair).

- [ ] **Step 1: Write the failing tests** — a synthetic capture tree under `tmp_path` in the segments' layout with two pairs, three hours (snapshot, update, update) and a fourth hour after a gap opening with an update: `test_produce_pair_writes_a_day_file_with_the_schema_and_a_sidecar`; `test_an_unanchored_hour_is_skipped_and_counted`; `test_the_book_threads_across_consecutive_hours` (an order posted in hour 1 fills in hour 2); `test_a_present_day_file_is_not_rewritten`; `test_hours_outside_since_until_are_not_read`; `test_the_manifest_is_conformant_and_attests_every_day_file` (`read_manifest`'s `hash_by_path()` equals the sidecars; an `ObservedReader(tmp_path)` `read_series` of one day returns the rows); `test_the_manifest_refuses_a_sidecar_that_disagrees`.
- [ ] **Step 2: Run red.**  **Step 3: Implement** `produce_pair`, `write_fills_manifest`, the two commands (Typer options as the panel's `materialize` takes them; `--since`/`--until` parsed as `_parse_since` does).  **Step 4: Run green**; `uv run pytest tests/test_panel_fills.py tests/test_panel_fills_producer.py -q -p no:cacheprovider`.
- [ ] **Step 5: The direct readers** of `cli/panel/command.py` and `cli/panel/fills.py` (`consumers.sh --direct`, stderr to a file under `.tmp/implementer/`) under `-m "not slow and not data and not retired"`; `README.md`'s command table gains the two commands (one row each, the panel's style).
- [ ] **Step 6: Commit** — `feat(panel): zcrypto panel fills — the fill model over the canonical capture, one pair a run, day files with sidecars, and the conformant manifest`, Task 1's probe file carried whole after its count check.
- [ ] **Step 7: Probe** — the unanchored skip, the manifest's sidecar refusal, the day-file watermark; lines into `probes-task-2.txt`.

---

### Task 3: `cli/alpha/c1.py` and the reading subject `c1-maker-fill-reading`

**Files:**
- Create: `cli/alpha/c1.py`
- Modify: `cli/research/subjects.py` (one block before `SUBJECTS`: `_C1ReadingInputs`, `_c1_reads`, `_c1_reading_inputs`, `_c1_reading_metrics`, `_build_c1_maker_fill_reading`, `_C1_READING_KEYS`; one `SUBJECTS` entry; one import line), `tests/test_research_command.py` (a `_CONTRACT_DATASETS` fixture writing a two-day synthetic `l2-fills` tree), `README.md`'s `--subject` row
- Test: `tests/test_alpha_c1.py`, `tests/test_research_c1_maker_fill_reading.py`

**Interfaces:**
- Consumes `cli/alpha/c2.py`'s `log_returns`, `trailing_std`, `moves`, `signals`, `cell_reads`, `rank_ic`, `per_year`; `cli/panel/fills.py`'s `COLUMNS`, `MID_OFFSETS_S`, `HORIZON_S`.
- Produces, in `cli/alpha/c1.py`: `MAKER_ROUND_TRIP = 0.0080`; `HORIZONS_S = (60, 300, 900)`; `THRESHOLDS = (1, 2)`; `SIZES = (0, 1)`; `SIDES = ("bid", "ask")`; `cell_name(pair, threshold, size, side) -> str`; `fill_table(frame: pl.DataFrame) -> dict` — per `(side, size, horizon)` per month and span: `fill_rate`, `median_time_to_fill_s`, `adverse_60_bps`, `adverse_900_bps` (the mid's move from `fill_price` signed against the order, in bps, means over the filled); `quarter_hour_mids(frame) -> tuple[list[datetime], list[float | None]]` — the `mid_at_post` of the bid-side rung-0 post at each quarter-hour boundary, `None` where absent; `reversal_cells(frame, *, threshold, size, side) -> dict` — the signal bars from the quarter-hour mids (`log_returns` on the 15m grid, `trailing_std` 96, `moves` lag 1, `signals` at `threshold`, a down move → the `bid` cell, an up move → the `ask` cell), each signal bar's post of that side and size the trade; among them `n_signals`, `fill_rate_900`; among the filled, the gross return per filled trade `(mid_at_post_plus_3600s − fill_price) / fill_price` for a bid and its negative for an ask, plus `spread_at_post_bps / 2 / 10_000`; the net = gross − `MAKER_ROUND_TRIP`; per month `{n, mean_gross, mean_net}` and span `{n, mean_gross, mean_net, p}` through `cell_reads`' form (one row per filled trade in `ts` order, `cost=MAKER_ROUND_TRIP`, `mean_block=30`, `n_resamples=4000`, `seed=42`); storable leaves only (no nulls: absent keys at `n` 0, `p` absent below 2 trades), string month keys `YYYY-MM`.
- The subject: `_c1_reads(reader, dataset, subject)` reads every `<BASE>/<QUOTE>/<YYYY>/<MM>/<DD>.parquet` the dataset's manifest names (`read_manifest(root/dataset/'manifest.json').series` keys), through `reader.read_series(dataset, relpath)`, concatenated per pair in relpath order; the inputs half: per pair the days present, posts, `skipped` counts are not in the rows (they are the producer's) so the inputs half is per pair × side × size: `posts`, the `queue_ahead_notional` mean per month, the `spread_at_post_bps` mean per month, `stale_seconds_at_post` null count — no `filled`, no mid after the post; the computes half: `fill_table` and the 96 `reversal_cells`, `constants` (`maker_round_trip`, `horizons_s`, `mean_block`, `n_resamples`, `seed`, `grid_s`, `horizon_s`); `_C1_READING_KEYS = frozenset({"fill_table", "cells", "coverage", "constants"})`; refusals: `--as-of` and `--window` before any read with the spec's wording in D6's form for this subject, a manifest absent or unparseable (`RegistryError` passes through as the reader raises it), a pair in the manifest with no rows; `SUBJECTS["c1-maker-fill-reading"] = Subject("c1-maker-fill-reading", (15,), _ASSETS, _build_c1_maker_fill_reading, spec="docs/specs/00151-c1-maker-fill-reading-design.md", metric_keys=_C1_READING_KEYS, seeds=(42,))`; the dataset is whatever `--dataset` names (`l2-fills-<stamp>`), its manifest the source of its files.

- [ ] **Step 1: Write the failing tests** — `tests/test_alpha_c1.py` on synthetic frames with known answers: `test_fill_table_rates_and_adverse_selection_on_a_planted_frame` (4 posts, 2 filled, adverse +5 bps and −3 bps → mean 1 bps), `test_quarter_hour_mids_take_the_bid_rung0_post_at_each_boundary`, `test_reversal_cells_trade_against_the_move_and_credit_the_half_spread`, `test_an_unfilled_signal_bar_counts_as_no_trade`, `test_cell_name`; `tests/test_research_c1_maker_fill_reading.py` on a synthetic two-pair two-day `l2-fills` tree with a conformant manifest: `test_the_build_returns_exactly_the_declared_keys_and_96_cells`, `test_the_inputs_half_reads_no_fill_outcome` (patch `pl.DataFrame.__getitem__`? — no: assert `inputs` carries no `filled`, `time_to_fill_s` or `mid_at_*` column, and monkeypatch `subjects.fill_table` and `subjects.reversal_cells` to `pytest.fail` before the inputs half), `test_as_of_and_window_are_refused_before_any_read`, `test_a_pair_named_by_the_manifest_with_no_rows_is_refused`, `test_the_subject_is_registered_as_a_reading`, `test_the_metrics_hold_only_leaves_the_registry_stores`.
- [ ] **Step 2: Run red.**  **Step 3: Implement.**  **Step 4: Run green**; the readers of `subjects.py` (`consumers.sh --direct`) under `-m "not slow and not data and not retired"` — `tests/test_research_command.py`'s nine contract rows for the new subject among them.
- [ ] **Step 5: Commit** — `feat(research): the reading subject c1-maker-fill-reading — the fill table and spec 00151's 96 cells over a frozen l2-fills set`, Task 2's probe file carried. **Step 6: Probe** — the inputs-half guard, the wrong-side credit in `reversal_cells` (mutation: the ask's sign dropped), the half-spread credit, the storable-leaves guard; lines into `probes-task-3.txt`.

---

### Task 4: the decisions-log entries before the hash

**Files:**
- Modify: `docs/research/10.phase4-decisions.md` (two `[iter-196]` entries)
- Test: `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py`

- [ ] **Step 1:** entry 1 — `[iter-196] C1 opened on the owner's family pick — C1's first step, a no-slot reading in two halves: the queue-position fill model as a frozen dataset and the reversal surface at the maker hurdle, the loop's pick under the owner's run instruction (Decision: 1)` — spec D1's three options; the Logged line quoting the owner's words of 2026-10-28 verbatim: "let's do C1"; "drive C1 exploration autonomously". Entry 2 — `[iter-196] C1's fill model and reading's conventions, pinned by spec 00151 before its hash (Decision: 1)` — the back of the queue with no cancellation ahead credited; full fill or none; the cancel rule (one tick away for 5 s, the horizon 900 s); the 15 s grid and the two rungs; the span 2026-08-01 → 2026-10-27 (complete months, clear of the holdout); the maker round trip 0.0080 with the half-spread credited, an unfilled signal bar no trade; the floor at 100 filled trades per complete month; Bonferroni over 96 at 4,000 resamples — each with its alternative, in the `[iter-195]` conventions entry's form.
- [ ] **Step 2:** `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider`; commit `docs(research): the two [iter-196] entries before spec 00151's hash`, Task 3's probe file carried.

---

### Task 5 (the controller's): the reads, the hash, the production, the catalog and the basis case

- [ ] **Step 1: The reads** — the trio over `develop..HEAD` as plan 00150 Task 3 Step 6 ran them, each on Opus, the `drive` carrying the hash rule in one sentence under 400 characters.
- [ ] **Step 2: The gate and the hash** — the reads closed with no open Critical or Important; `git status --porcelain` empty; `sha256sum docs/specs/00151-c1-maker-fill-reading-design.md`, pasted; the spec never edited after.
- [ ] **Step 3: The production**, on the ops host in the main checkout, the stamp `date -u +%Y%m%dT%H%M%SZ` read once and pasted: for each of the twelve pairs `uv run zcrypto panel fills /mnt/zhao-crypto/capture-segments /home/zhaow/Projects/zcrypto-kraken/data/l2-fills-<stamp> --reconciled-root /mnt/zhao-crypto/capture-reconciled --pair <PAIR> --since 2026-08-01T00:00:00Z --until 2026-10-27T23:59:59Z > .local/iter196/produce-<BASE>-<QUOTE>.out 2>&1`, six at a time as `run_in_background` calls, each acted on at its completion notification, its counts quoted; a pair whose run ends other than rc 0 is re-run once from its watermark, then STOP; then `uv run zcrypto panel fills-manifest /home/zhaow/Projects/zcrypto-kraken/data/l2-fills-<stamp>`; `ls data/` read (14 entries).
- [ ] **Step 4: The catalog entry** — `docs/reference/data-catalog-full.md` gains `### l2-fills-<stamp>` (producer, parameters, span, layout, the counts, caveats: the back-of-queue bound, the cancel rule, no partial fills), committed `docs(reference): the l2-fills dataset cataloged`.
- [ ] **Step 5: The basis figures and the data-gated case** — the inputs half's figures read by a scratch program over the set (posts per pair, days present, the per-month `queue_ahead_notional` means by side and size), written into the spec? **No — the spec is hashed.** They go into `tests/test_research_c1_maker_fill_reading_basis.py` as literals (the data-gated case, `pytestmark = pytest.mark.data`, the literal-rooted `_DATA_ROOT`, the skipif gate naming `l2-fills-*/*/*/*/*/*.parquet`, the `_DATA_ROOT` assertion first) and into the reading's entry; the case committed `test(research): C1's data-gated basis case over l2-fills-<stamp>`, run linked → `1 passed`.

### Task 6 (the controller's): the run, the line's checks, the table, the entry, the replay, the commit

- [ ] Plan 00150's Task 4 Steps 3 and 5–11 with these substitutions: the notes from this plan's fence below; `--subject c1-maker-fill-reading --dataset l2-fills-<stamp> --reading --iteration iter-196 --spec-hash <H>`; the checks-and-table program the fence below, extracted from the read tip; the entry `[iter-196] Maker-fill realism and the reversal surface read on l2-fills-<stamp> (reading 8)`; the slow-cases line `[reading-8]`; the replay with `data/l2-fills-<stamp>` and `data/ohlc-full` linked.

```text
subject c1-maker-fill-reading over l2-fills-<stamp>, the frozen fill-model set read whole, no window and no as-of; descriptive: no hypothesis, no bar, no verdict and no C slot; the fill model: orders at the best bid and ask every 15 s at the first two notional rungs, joining the back of the queue, filled whole when the opposite-side trades at the price consume the queue ahead and the order, cancelled when the best quote has moved a tick away for 5 s or at 900 s; the fill table by side, size and horizon 60, 300, 900 s with the adverse selection at +60 s and +900 s; the reversal surface — 96 cells, pair by threshold (1σ, 2σ) by size by side — each trade the post against a 15m move of the mid, its gross the mid's move to +3600 s in its favour plus the half-spread, its net less the maker round trip 0.0080, the bootstrap p at 4,000 resamples; the potential criterion pre-registered by spec 00151 (sha256 <H>): the floor at 100 filled trades per complete month, legs fill rate ≥ 0.50 at 900 s, mean gross above 0.0080 in each month and over the span, p below 0.05/96.
```

```python
"""Reading 8 off the ledger's last line: its checks, then spec 00151 D5's criterion table — one line per cell the floor
admits, its four legs' values and whether each holds, then the counts; exit 0 only when every check holds."""

import json
import sys
from pathlib import Path

from cli.alpha.c1 import MAKER_ROUND_TRIP, SIDES, SIZES, THRESHOLDS, cell_name
from cli.research.subjects import SUBJECTS

PAIRS = ("ADA/EUR", "AVAX/EUR", "BTC/EUR", "DOGE/EUR", "DOT/EUR", "ETH/EUR", "LINK/EUR", "LTC/EUR", "SOL/EUR", "XRP/EUR", "ETH/BTC", "SOL/BTC")
MONTHS = ("2026-08", "2026-09", "2026-10")
r = json.loads(Path("docs/reference/reading-ledger.jsonl").read_text().splitlines()[-1])
m = r["metrics"]
names = {cell_name(p, th, s, side) for p in PAIRS for th in THRESHOLDS for s in SIZES for side in SIDES}
checks = {
    "labels": (r["reading_id"], r["iteration"], r["spec_hash"], r["attempt"]) == (8, "iter-196", sys.argv[1], None),
    "keys": set(m) == SUBJECTS["c1-maker-fill-reading"].metric_keys,
    "cells": set(m["cells"]) == names,
    "p": all(("p" in c["span"]) == (c["span"].get("n", 0) >= 2) and ("p" not in c["span"] or 0 < c["span"]["p"] <= 1) for c in m["cells"].values()),
    "constants": (m["constants"]["maker_round_trip"], m["constants"]["n_resamples"], m["constants"]["seed"]) == (MAKER_ROUND_TRIP, 4000, 42),
}
print(r["reading_id"], checks)
if not all(checks.values()):
    sys.exit(1)
bound = 0.05 / len(names)
admitted, held = [], [0, 0, 0, 0]
for name in sorted(names):
    c = m["cells"][name]
    months = {mo: c["months"].get(mo, {}) for mo in MONTHS}
    if any(months[mo].get("n", 0) < 100 for mo in MONTHS):
        continue
    legs = (c["fill_rate_900"] >= 0.5, all(months[mo]["mean_gross"] > MAKER_ROUND_TRIP for mo in MONTHS), c["span"]["mean_gross"] > MAKER_ROUND_TRIP, c["span"]["p"] < bound)
    admitted.append((name, all(legs)))
    held = [h + leg for h, leg in zip(held, legs, strict=True)]
    print(name, "| fill rate 900", c["fill_rate_900"], "| (n, mean gross) per month", {mo: (months[mo]["n"], months[mo]["mean_gross"]) for mo in MONTHS}, "| span", c["span"], "| legs", legs, "| potential", all(legs))
print("cells", len(names), "| the floor admits", len(admitted), "| hold legs 1-4", held, "| potential", [n for n, p in admitted if p] or "none")
```

### Task 7: T0016's C1 arm, the retirement, the index — plan 00150 Task 5's form for C1 (its `ripe_when` C1 clause → the `[iter-NNN] C1's next step after the maker-fill reading` entry; the findings bullet from the entry; `c1-maker-fill-reading` retired).

### Task 8 (the controller's): the row, the delta reads, the tip replay, the PR — plan 00150 Task 6's form (title `feat(research): iter-196 — C1 maker-fill realism on L2 (reading 8)`, measured under 72; row `| #<n> | <date> | <title> | iter-196 | 00151 | T0016 |`; the PR body names the new dataset and its catalog entry; `merge-pr`; the memo and the coordination table).
