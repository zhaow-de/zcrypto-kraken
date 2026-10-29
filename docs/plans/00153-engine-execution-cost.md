# Reading 9 — the engine's execution cost from its ladder replayed at the cycle boundaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A producer that derives the frozen dataset `data/l2-ladder-<stamp>/` — spec 00153 D2's replay of the engine's maker-first ladder at the deployable's cycle boundaries over the captured book — and a reading subject `engine-cost-reading` over it that lands as reading 9 on `docs/reference/reading-ledger.jsonl`, its computes fixed before the hash.

**Architecture:** The episode is pure code in a new `cli/panel/ladder.py` over `cli/panel/fills.py`'s posting, fill rule and seed, the queue cap extracted from `tick_cancel` into `cap_queue` so both call it; the producer and its `zcrypto panel ladder` / `ladder-manifest` commands sit beside the fill producer's, writing one day per pair-file with a frame-hash sidecar, a run record per pair and a conformant manifest. The cost computations are pure code in a new `cli/costs/ladder.py`; the subject in `cli/research/subjects.py` reads the frozen set whole as `c1-maker-fill-reading` reads `l2-fills`.

**Tech Stack:** Python 3.14, polars, `decimal.Decimal`, `cli.archive.replay.regroup_messages`, `cli.capture.book.OrderBook`, `cli.panel.fills` (`_post`, `apply_trade`, `seed_book`, `_ingest`, `_fresh_mid`, `_listing`, `_read_hour`, `_healed`, `_mark`, `cap_queue`), `cli.data.manifest` (`build_manifest`, `read_manifest`), `cli.ohlc.dataset.dataset_hash`, `cli.capture.segment_writer._replace_durably`, `cli.validation.bootstrap.bootstrap_ci`, pytest.

**Spec:** `docs/specs/00153-engine-execution-cost-design.md`

## Global Constraints

- The hash rule (spec D4): before the spec's sha256 is taken, no program runs the producer over the real archive or reads a fill, a box-end touch or a mid after a post over it; the producer and the reading are proven on synthetic hours alone. Only the controller reads `/mnt/zhao-crypto/`; a dispatch never does.
- The constants, verbatim: posts at `B + 120 s` for each cycle boundary `B` whose hour is in `(0, 4, 8, 12, 16, 20)`; the C1 rungs (`_post` → `post_orders`, sizes €100 and €1,000 of the quote); the fill rule `apply_trade` and `cap_queue`, no away-cancel; the time box 900 s, the box end at `post + 900 s`; the maker fee 0.0040 and the taker fee 0.0080 a side; the registered 0.006 a side; the bootstrap mean block 6, 2,000 resamples, seed 42; the span 2026-08-01T00:00Z ≤ `B` < 2026-10-26T00:00Z; the months 2026-08, 2026-09, 2026-10; the ten EUR legs of `cli.portfolio.crossfreq_system.CrossfreqSystemConfig().assets` plus `ETH/BTC` and `SOL/BTC` for the twelve pairs.
- The row's columns, in this order: `ts, pair, side, size, price, our_qty, queue_ahead_qty, mid_at_post, spread_at_post_bps, filled, time_to_fill_s, fill_price, box_end_mid, box_end_touch_price, box_end_touch_qty`; `side` is `bid` (a buy) or `ask` (a sell), `size` the rung 0 or 1.
- `cli/panel/fills.py`'s behaviour is unchanged: its whole test file passes before and after Task 1's extraction.
- Commits: Conventional Commits, one subject per change; the message says what changed and the result line of the test command it names, pasted; one state-changing git command per Bash call, nothing beside it; never an amend, `--no-verify` or `git stash`; every commit ends with the two trailer lines the dispatch names — `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>` and the session line.
- A comment or docstring stays only where a reader would do something differently without it, and has to be correct; a spec citation names the D-section — except a Typer command's docstring, its `--help` screen, which cites no spec or other term `tests/test_internal_terms_not_operator_visible.py` refuses.
- Probes: on this `full`-tier plan, each guard a task's Probe step lists, through its own case, with `infra/scripts/mutate-probe.sh` on a committed tree, the verdict lines into `.local/iter199/probes-task-<N>.txt` (one `mkdir -p .local/iter199` first; the file started empty by `: > <file>`), carried whole into the next commit's message; `--basetemp=.tmp/implementer/pt` after each probe's `--`.
- The worktree is `.claude/worktrees/iter199`; the main checkout at `/home/zhaow/Projects/zcrypto-kraken` is live, and its `data/` is written only by Task 5's production, to the new root.

## Review Focus

1. An order the touch leaves and returns to — C1's rule cancels it; the ladder keeps it, and a later print at its price fills it. Pinned in Task 1's `test_an_order_the_touch_leaves_and_returns_to_is_filled_by_a_later_print`.
2. The box end — an order unfilled at exactly `post + 900 s` reads the opposite touch at that second, a fill at `post + 900 s` itself counts as a fill, and no print after it is applied. Pinned in Task 1's `test_the_box_end_reads_the_opposite_touch_at_post_plus_900s` and `test_a_print_at_the_box_end_second_fills_and_one_after_does_not`.
3. The cost's sign on each side — a buy filled at the bid below the mid costs the fee less the half-spread; a sell filled at the ask the same; a buy's fallback at the ask costs the fee plus the half-spread. Pinned in Task 3's `test_the_cost_of_a_side_is_signed_against_the_order`.
4. A fallback whose box-end book is empty or stale — no touch, no cost; counted as unpriced, never priced at zero. Pinned in Task 3's `test_an_unpriced_fallback_is_counted_and_left_out_of_the_mean`.
5. The extraction — `tick_cancel`'s cap through `cap_queue` behaves as before on every C1 case. Pinned by Task 1's run of `tests/test_panel_fills.py` whole and `test_cap_queue_caps_as_tick_cancel_did`.

---

### Task 1: `cap_queue` and the ladder episode

**Files:**
- Modify: `cli/panel/fills.py` (extract `cap_queue`)
- Create: `cli/panel/ladder.py`
- Test: `tests/test_panel_ladder.py`

**Interfaces:**
- Produces in `cli/panel/fills.py`: `cap_queue(order: Order, book: OrderBook) -> None` — `order.ahead_qty = min(order.ahead_qty, order.level_qty)`, then `order.level_qty` the level's resting quantity at `order.price` on the order's own side (0 when gone); `tick_cancel` calls it in place of its two lines, its comment moving with them.
- Produces in `cli/panel/ladder.py`: `BOUNDARY_HOURS = (0, 4, 8, 12, 16, 20)`; `POST_OFFSET_S = 120`; `BOX_S = 900`; `COLUMNS` the Global Constraints' fifteen names; `simulate_episode(messages: list[dict], trades: list[dict], book: OrderBook, hour: datetime, *, pair: str, last_msg_ts: datetime | None) -> tuple[list[dict], dict[str, int]]` — over the seconds `0 … POST_OFFSET_S + BOX_S` of `hour`, at each second as `fills.simulate_hour` orders it: the messages up to it (`fills._ingest`), the prints up to it against every open order (`fills.apply_trade`), `fills.cap_queue` on every open order; at second `POST_OFFSET_S`, after that second's prints and caps, the orders `fills._post` returns, its `counts` (`posts`, `skipped_no_quote`, `skipped_stale`) the episode's; at second `POST_OFFSET_S + BOX_S`, after that second's prints, one row per order: `filled`, `time_to_fill_s` and `fill_price` (the order's price) when filled, else null; `box_end_mid` = `fills._fresh_mid(book, …)`; `box_end_touch_price` and `box_end_touch_qty` the opposite side's best level — the best ask for a bid, the best bid for an ask — as floats, null when that side is empty or the mid is not fresh. No message or print after the box end is read.
- `rows_frame(rows: list[dict]) -> pl.DataFrame` — the `COLUMNS` schema, sorted by `ts`, `side`, `size`.

- [ ] **Step 1: Write the failing tests** in `tests/test_panel_ladder.py`, synthetic messages and prints built as `tests/test_panel_fills.py` builds them:
  - `test_cap_queue_caps_as_tick_cancel_did` — on an order whose level is cut and then refilled, `cap_queue` leaves `ahead_qty` at the cut quantity and `level_qty` at the refilled one.
  - `test_orders_post_at_boundary_plus_120s` — four rows, each `ts == hour + 120 s`.
  - `test_a_print_at_second_300_fills_the_bid_and_never_the_ask` — the bid filled with `time_to_fill_s == 180`, the ask not.
  - `test_an_order_the_touch_leaves_and_returns_to_is_filled_by_a_later_print` — the best bid moves a tick up at second 130 and back at second 400; a sell print at the order's price at second 500 fills it.
  - `test_the_box_end_reads_the_opposite_touch_at_post_plus_900s` — the best ask changes at second 1019 and at 1021; the bid's `box_end_touch_price` and `box_end_touch_qty` are the second-1020 values.
  - `test_a_print_at_the_box_end_second_fills_and_one_after_does_not` — a print at second 1020 fills, one at 1021 does not.
  - `test_an_order_larger_than_the_box_end_touch_is_recorded_larger` — `box_end_touch_qty < our_qty` on the row.
  - `test_a_stale_book_at_the_post_skips_and_counts` — no row, `counts["skipped_stale"] == 4`.
- [ ] **Step 2: Run them to see them fail** — `uv run pytest tests/test_panel_ladder.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`; expected: every case fails on the missing module or name.
- [ ] **Step 3: Implement** the extraction and `cli/panel/ladder.py` to the interfaces above.
- [ ] **Step 4: Run them to see them pass**, then `uv run pytest tests/test_panel_ladder.py tests/test_panel_fills.py tests/test_panel_fills_producer.py -q -p no:cacheprovider -n 6 --basetemp=.tmp/implementer/pt`; expected: all pass.
- [ ] **Step 5: Commit** `feat(panel): the engine's ladder episode over the captured book, the queue cap shared with the fill model (spec 00153 D2)`.
- [ ] **Probe**: no away-cancel — a cancel added after `cap_queue` for an order whose touch moved (`-k leaves_and_returns`); the box end's `<=` made `<` (`-k box_end_second`); the opposite side made the own side (`-k opposite_touch`).

### Task 2: the producer, its manifest and its commands

**Files:**
- Modify: `cli/panel/ladder.py`, `cli/panel/command.py`, `README.md` (the `zcrypto panel` section), `tests/test_data_manifest.py` (the driver table)
- Create: `tests/l2_ladder_fixtures.py`
- Test: `tests/test_panel_ladder_producer.py`

**Interfaces:**
- Consumes: Task 1's `simulate_episode`, `rows_frame`, `BOUNDARY_HOURS`; `fills._listing`, `fills._read_hour`, `fills._healed`, `fills.seed_book`, `fills._mark`, `fills.PRODUCING_MARKER`, `regroup_messages`, `OrderBook`, `dataset_hash`, `_replace_durably`, `build_manifest`.
- Produces in `cli/panel/ladder.py`: `RUN_RECORD = "ladder-run.json"`; `produce_ladder_pair(primary_root: Path, reconciled_root: Path | None, panel_root: Path, out_root: Path, pair: str, *, since: datetime, until: datetime, depth: int = 100) -> dict` — refuses an out root holding `manifest.json` and a pair root whose run record names other parameters or another code ref (`PanelError`, by name); marks the out root with `fills._mark` after those checks; resumes after the pair's newest day file; for each boundary `B` in `[since, until)`: the hour's book and trades from the two listings, an absent book hour counted `episodes_absent`, the book seeded by `seed_book(panel_root, pair, B, depth=depth)` and replaced by a fresh `OrderBook` when the hour opens with a snapshot, an unseeded hour counted `episodes_unanchored`, else `simulate_episode`; one day file per UTC day once its six boundaries are done, `<out_root>/<BASE>/<QUOTE>/<YYYY>/<MM>/<DD>.parquet` with a `.sha256` sidecar of the frame's `dataset_hash`, the run record per pair holding `params` (`post_offset_s`, `box_s`, `boundary_hours`, `size_rungs`, `depth`, `since`, `until`), `code_ref` and per-day counts; each refusal of a read or write by name, as the fill producer's; returns the counts. `write_ladder_manifest(out_root: Path, primary_root: Path, reconciled_root: Path | None, *, written_at: str) -> Path` — a conformant manifest (`identity="set"`, provenance `params`, `code_ref`, each pair's day records), refusing a day file its sidecar or record disagrees with and run records that disagree across pairs; after it lands, removes the out root's `fills.PRODUCING_MARKER`, refusing by name when it cannot.
- Produces in `cli/panel/command.py`: `zcrypto panel ladder <primary_root> <out_root> [--reconciled-root] --panel-root --pair --since --until [--depth]` and `zcrypto panel ladder-manifest <primary_root> <out_root> [--reconciled-root]`, as `fills` and `fills-manifest` are declared, printing the counts as one JSON line; exit 1 on a `PanelError`.
- Produces in `tests/l2_ladder_fixtures.py`: `write_l2_ladder_set(root: Path, dataset: str, *, days: tuple[date, ...]) -> datetime` — a synthetic frozen set of the twelve pairs through `write_ladder_manifest`'s own writers, rows planted per D2's columns.

- [ ] **Step 1: Write the failing tests** in `tests/test_panel_ladder_producer.py` over a synthetic archive and panel state (the fixtures `tests/test_panel_fills_producer.py` builds): a day's six episodes land in one day file with its sidecar and record; an hour seeded from the panel's state; an absent book hour counted; an out root holding a manifest refused and left unmarked; the run marks the out root and the manifest lifts the mark; a record with other parameters refused by name; the commands' exit codes and JSON line.
- [ ] **Step 2: Add the driver row** `"cli/panel/ladder.py": _drive_ladder` to `tests/test_data_manifest.py`'s `_PRODUCERS`, `_drive_ladder` writing `write_l2_ladder_set` and returning its manifest's path.
- [ ] **Step 3: Run them to see them fail** — `uv run pytest tests/test_panel_ladder_producer.py tests/test_data_manifest.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`.
- [ ] **Step 4: Implement** the producer, the manifest writer, the commands and their README rows.
- [ ] **Step 5: Run them to see them pass**, and `uv run pytest tests/test_panel_ladder.py tests/test_panel_ladder_producer.py tests/test_data_manifest.py tests/test_panel_fills_producer.py -q -p no:cacheprovider -n 6 --basetemp=.tmp/implementer/pt`.
- [ ] **Step 6: Commit** `feat(panel): zcrypto panel ladder and ladder-manifest — the ladder replay as a frozen set (spec 00153 D2)`, carrying Task 1's probe verdicts.
- [ ] **Probe**: the finished-set refusal (`-k holding_a_manifest`); the mark's lift (`-k lifts_the_mark`).

### Task 3: the cost computations in `cli/costs/ladder.py`

**Files:**
- Create: `cli/costs/ladder.py`
- Test: `tests/test_costs_ladder.py`

**Interfaces:**
- Produces: `MAKER_FEE = 0.0040`; `TAKER_FEE = 0.0080`; `REGISTERED_PER_SIDE = 0.006`; `MONTHS = ("2026-08", "2026-09", "2026-10")`; `MEAN_BLOCK = 6`; `N_RESAMPLES = 2000`; `SEED = 42`; `side_costs(frame: pl.DataFrame) -> pl.DataFrame` — a `cost` column: a filled row `s·(fill_price − mid_at_post)/mid_at_post + MAKER_FEE`, an unfilled one `s·(box_end_touch_price − mid_at_post)/mid_at_post + TAKER_FEE`, `s` +1 for `bid` and −1 for `ask`; null for an unfilled row whose `box_end_touch_price` is null; `cost_table(frame: pl.DataFrame) -> dict` keyed `"<side>|S<size>"`, each over `"span"` and each month: `posts`, `maker_share`, `median_time_to_fill_s`, `mean_cost`, `cost_ci_low`, `cost_ci_high` (`bootstrap_ci` over the priced costs in `ts` order at `MEAN_BLOCK`, `N_RESAMPLES`, alpha 0.05, `SEED`), `fallback_larger_share` (unfilled rows with `box_end_touch_qty < our_qty`, over the unfilled), `unpriced`; `blend(frames: dict[str, pl.DataFrame], legs: tuple[str, ...]) -> dict` keyed `"S0"`, `"S1"`: per size, the series in boundary order of the mean priced cost over `legs` and both sides at each boundary, its mean, interval as above, and the boundaries it spans.

- [ ] **Step 1: Write the failing tests** in `tests/test_costs_ladder.py` over planted frames: `test_the_cost_of_a_side_is_signed_against_the_order` (a bid filled at 99.9 with mid 100 → −0.001 + 0.0040; an ask filled at 100.1 → the same; a bid's fallback at 100.1 → +0.001 + 0.0080; an ask's at 99.9 → the same); `test_an_unpriced_fallback_is_counted_and_left_out_of_the_mean`; `test_each_month_reads_its_own_rows` (each month's `posts` its own count, `"span"` their sum); `test_the_blend_weights_each_leg_equally` (two legs with 10 and 1,000 rows at costs 0.01 and 0.0 → 0.005); `test_the_interval_is_bootstrap_ci_at_the_constants` (equal to a direct `bootstrap_ci` call).
- [ ] **Step 2: Run them to see them fail** — `uv run pytest tests/test_costs_ladder.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`.
- [ ] **Step 3: Implement** to the interfaces.
- [ ] **Step 4: Run them to see them pass.**
- [ ] **Step 5: Commit** `feat(costs): a side's cost under the engine's ladder, by pair, side, size and month, and the blend (spec 00153 D3)`, carrying Task 2's probe verdicts.
- [ ] **Probe**: the sign table (`-k signed_against`); the unpriced exclusion (`-k unpriced`); the equal weighting (`-k equally`).

### Task 4: the reading subject `engine-cost-reading`

**Files:**
- Modify: `cli/research/subjects.py`, `tests/test_research_command.py` (its `_CONTRACT_DATASETS` row), `README.md` (the `--subject` row)
- Test: `tests/test_research_engine_cost_reading.py`

**Interfaces:**
- Consumes: Task 2's `write_l2_ladder_set`, Task 3's functions.
- Produces: `_build_engine_cost_reading(reader, dataset, window, as_of=None, accept_holes=False) -> dict` — refuses `as_of` and `window` (`SubjectError`, by name, as `_build_c1_maker_fill_reading` does); reads the frozen set whole as `_c1_reads` reads `l2-fills` — its manifest's twelve pairs, every day file inside the span, the provenance's day records and its `params` equal to D2's — and returns `{"cost_table": {pair: cost_table(frame)}, "blend": blend(frames, the ten EUR legs), "coverage": {pair: episodes, posts, skips and absences from the records}, "constants": {the fees, the registered basis, the bootstrap's}}`; `SUBJECTS["engine-cost-reading"] = Subject("engine-cost-reading", (), (), _build_engine_cost_reading, spec="docs/specs/00153-engine-execution-cost-design.md", metric_keys=frozenset({"cost_table", "blend", "coverage", "constants"}), seeds=(42,))`, no rule, no family.

- [ ] **Step 1: Write the failing tests**: the build's keys; an as-of and a window refused; a set missing a pair, a day outside the span and other params each refused by name; the cost table and the blend equal Task 3's functions over the same frames.
- [ ] **Step 2: Add the `_CONTRACT_DATASETS` row** writing `write_l2_ladder_set`.
- [ ] **Step 3: Run them to see them fail; implement; run them to see them pass** — `uv run pytest tests/test_research_engine_cost_reading.py tests/test_research_command.py -q -p no:cacheprovider -n 6 --basetemp=.tmp/implementer/pt`.
- [ ] **Step 4: Commit** `feat(research): the engine-cost-reading subject over a frozen l2-ladder set (spec 00153 D3)`, carrying Task 3's probe verdicts.
- [ ] **Probe**: the params refusal (`-k other_params`).

### Task 5 (the controller): the hash, the production, the reading

- [ ] **Step 1: The pick entry** in `docs/research/14.phase6-decisions.md`, `[iter-199] The engine's execution cost — a ladder replay at the cycle boundaries, not a re-read of the C1 set (Decision: 1)`, D1's three options and the owner's words verbatim; committed.
- [ ] **Step 2: The hash** — `sha256sum docs/specs/00153-engine-execution-cost-design.md` on a clean tree with Tasks 1–4 in, pasted with `date -u`.
- [ ] **Step 3: Two timed boundary days** — `zcrypto panel ladder` over BTC/EUR 2026-09-03 into a scratch out root, its seconds read; the production sized from them.
- [ ] **Step 4: The production** — the twelve pairs, six at a time, `--since 2026-08-01T00:00:00Z --until 2026-10-26T00:00:00Z`, into `/home/zhaow/Projects/zcrypto-kraken/data/l2-ladder-<stamp>` (the stamp the start's `date -u +%Y%m%dT%H%M%SZ`), each awaited; then `zcrypto panel ladder-manifest`; the catalog entry in `docs/reference/data-catalog-full.md`.
- [ ] **Step 5: The reading** — the set linked into the worktree (`ln -snT`), `uv run zcrypto research eval --subject engine-cost-reading --dataset l2-ladder-<stamp> --reading --iteration iter-199 --spec-hash <hash>`; reading 9 committed; the subject retired in `tests/retired_subjects.py`; the replay case run in a scratch worktree at the commit.
- [ ] **Step 6: The reading's entry** in the phase-6 log with the blend and the per-pair table; T0214's findings and T0122's line; each committed; the link removed.

Decisions log: Task 5 Steps 1 and 6.
