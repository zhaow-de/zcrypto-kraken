# 00094 — The /BTC Widening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the engine pipeline twelve-legged end to end — symbol-keyed store/targets/journal/gate/instruments/VenueState — with the `/BTC` legs at structural zero, and re-ratify the deployable on the widened basket in the same iteration.

**Architecture:** The model (`CrossfreqSystemConfig.assets`) stays the ten EUR bases; a **basket-expansion step in the cycle** maps its ten base-keyed outputs onto the twelve-symbol basket, emitting `ETH/BTC`/`SOL/BTC` at exactly `0.0`. Everything downstream of the model re-keys by full symbol (`00093`'s convention). The journal moves to schema 2 with `{1, 2}` loadable, and the Stage-6a gate replays each record per its own schema so the ratified streak survives the deploy boundary. Re-ratification appends a successor registry record whose committed spec documents the widened basket; the owner's adopt verdict is an explicit attended step.

**Tech Stack:** Python 3.14, polars, prometheus_client, pytest; no Nautilus surface changes (00089 already probed those).

## Global Constraints

- **THE STRATEGY DOES NOT CHANGE — D1 is the spec's center.** `CrossfreqSystemConfig.assets` stays `("ADA","AVAX","BTC","DOGE","DOT","ETH","LINK","LTC","SOL","XRP")`; no sleeve ever consumes a `/BTC` series. Every task's tests must remain compatible with the two D1 pins (Task 5): EUR-leg target values identical to the ten-asset model's own outputs; `/BTC` targets exactly `0.0`.
- **The twelve-symbol basket** is `("ADA/EUR","AVAX/EUR","BTC/EUR","DOGE/EUR","DOT/EUR","ETH/BTC","ETH/EUR","LINK/EUR","LTC/EUR","SOL/BTC","SOL/EUR","XRP/EUR")` — sorted, DOT deliberately included (the T0137 ruling), defined ONCE as `cli/engine/store.py::BASKET` and derived everywhere else.
- **The gate streak must survive the schema boundary** — the ratified 30-day streak zeroing at deploy is a self-inflicted gate breach; Task 6's straddling-window test is the proof and no task may weaken it.
- **Sweep before editing**: `00093` measured this blast radius once by grep and still missed a re-export; every re-keying task begins with an untruncated consumer sweep (`grep -rn <symbol> cli/ tests/ infra/` — never piped through `head`), every hit routed or the task stops and reports.
- Full-symbol keys are `BASE/QUOTE` strings; the venue spells XBT where we spell BTC (`XETHXXBT`, `SOLXBT` — already correct in the fetch map; never re-derive them).
- Operator-facing text carries no `T<NNNN>`/spec-serial/`iter-<N>`; metric HELP and alert summaries are in scope.
- Python 3.14 / PEP 758: unparenthesized `except A, B:` is valid — not a defect.
- Commit gate `uv run pre-commit run -a` to clean; stage by explicit path; implementers run **targeted test files only** — the full suite runs in Task 9 (the `00089` lesson, now standing practice) and in the whole-branch review.
- No network in tests; nothing here touches capture, the universe pipeline, or `cli/ohlc/fetch.py::PAIR_KEYS`.

## File Structure

| File | Responsibility |
| --- | --- |
| `cli/engine/store.py` | *modify* — `BASKET` (the one source of truth), symbol-keyed `PAIR_KEYS`, quote-aware `_store_path`, seed/refresh over twelve |
| `cli/engine/instruments.py` | *modify* — symbol-keyed `INSTRUMENT_IDS`, `COSTMIN` per-symbol with explicit quote, `fx_eur_notional` |
| `cli/engine/venuestate.py` + `cli/engine/venueledger.py` | *modify* — symbol-keyed `VenueState.instruments`, concordance over twelve |
| `cli/engine/journal.py` | *modify* — `SCHEMA_VERSION = 2`, `{1,2}` loadable, schema-aware validation and hashing |
| `cli/engine/cycle.py` | *modify* — the basket-expansion step, symbol-keyed targets/orders, schema-2 records |
| `cli/engine/concordance.py` | *modify* — schema-aware replay + key normalization; `evaluate_gate` untouched |
| `cli/engine/command.py` | *modify* — gauges' label keys, `instruments_expected` derivation, the self-test's record pin |
| `cli/engine/soak.py` + `cli/engine/feeders.py` | *modify where the sweep routes hits* — both read targets/universe shapes |
| `docs/research/<successor spec for the widened deployable>` | *create* (Task 7) — the doc the new record's `spec_hash` pins; IMMUTABLE once hashed |
| `docs/reference/trial-registry.jsonl` | *append-only* (Task 7) — the successor record, owner-adopted |
| `tests/test_basket_concordance.py` | *modify* — the `/BTC` exception retires; DOT's cites the ruling |
| `tests/` engine files | *modify* — find the real files first; do not create parallel ones |
| Closeout: phase-6 history, decisions log, T0137 resolve+archive, T0018 rows | *modify* (Task 9 only) |

---

### Task 1: The basket constant and the store re-key

**Files:** Modify `cli/engine/store.py`, `tests/test_engine_store.py`.

**Interfaces:**
- Produces: `BASKET: tuple[str, ...]` — the twelve symbols above, sorted; the single committed source of truth every later task derives from.
- Produces: `PAIR_KEYS: dict[str, str]` — symbol → venue key, `{s: _FETCH_PAIR_KEYS[s] for s in BASKET}` (twelve entries; a `BASKET` member absent from the fetch map must raise at import — fail loud, never narrow).
- Produces: `_store_path(root, symbol, interval) -> Path` — `root / base / quote / f"{interval}.parquet"` from the split symbol.
- `seed_store`/`refresh_store`/`read_store_series` take full symbols; the two `/BTC` series seed and refresh with the same reconcile discipline, genesis rows carrying provenance like any seeded series.

- [ ] **Step 1: The consumer sweep.** `grep -rn 'PAIR_KEYS\|ASSETS\|KEY_TO_ASSET\|_store_path\|seed_store\|refresh_store\|read_store_series' cli/ tests/ infra/` — untruncated. Route every hit to a task (this one, 3, 5, 6, or "unchanged because …") in the task report BEFORE editing. Expected consumers include `cycle.py`, `soak.py`, `feeders.py`, `command.py` gauges, `test_engine_metrics.py`/`test_engine_cycle.py` module-level imports, and `cli/engine/__init__.py` re-exports — the `00093` lesson says expect one more you did not predict; a hit with no route is a stop-and-report.
- [ ] **Step 2: Failing tests** — `BASKET` has exactly twelve sorted members with both `/BTC` legs; `PAIR_KEYS["ETH/BTC"] == "XETHXXBT"` and `PAIR_KEYS["SOL/BTC"] == "SOLXBT"`; `_store_path(root, "ETH/BTC", 1440)` ends `ETH/BTC/1440.parquet` while `"ETH/EUR"` ends `ETH/EUR/1440.parquet`; a `BASKET` symbol missing from the fetch map raises at import (construct via monkeypatched fetch map).
- [ ] **Step 3–4: red → implement → green** on `tests/test_engine_store.py` (the existing ten-leg tests move to symbol keys — value assertions preserved, keys renamed; nothing weakened).
- [ ] **Step 5: Gate, stage, commit** `feat(engine): the twelve-symbol BASKET and the quote-aware store`.

### Task 2: Instruments — symbol keys, per-symbol costmin with explicit quote, the FX term

**Files:** Modify `cli/engine/instruments.py`, `tests/test_engine_instruments.py`, `tests/test_costmin_drift.py`.

**Interfaces:**
- Produces: `INSTRUMENT_IDS: dict[str, str]` — symbol → `f"{base}/{quote}.KRAKEN"`, derived from `BASKET`, twelve entries (`"ETH/BTC" -> "ETH/BTC.KRAKEN"` — Task 1 of `00089` proved the adapter strips venue aliases, so no XBT form appears in IDs).
- Produces: `COSTMIN: dict[str, tuple[float, str]]` — symbol → `(value, quote_currency)`: ten `(0.45, "ZEUR")`, `("ETH/BTC")`/`("SOL/BTC")` → `(2e-05, "XXBT")`. `COSTMIN_EUR` is deleted; its consumers (swept in Task 1) re-route.
- Produces: `fx_eur_notional(symbol: str, qty: float, price: float, btc_eur_close: float) -> float` — EUR-quoted: `qty * price`; XBT-quoted: `qty * price * btc_eur_close`. Pure, uncalled by production (the `size_order` precedent); `btc_eur_close <= 0` raises.
- `size_order` is unchanged — the caller owns denomination, and the docstring says so at the seam.

- [ ] **Step 1: Failing tests** — twelve IDs incl. both `/BTC` forms; `COSTMIN` quotes explicit (`COSTMIN["ETH/BTC"] == (2e-05, "XXBT")`); `fx_eur_notional("ETH/EUR", 2.0, 100.0, 30000.0) == 200.0` and `fx_eur_notional("ETH/BTC", 2.0, 0.05, 30000.0) == 3000.0`; the raise on a non-positive FX close.
- [ ] **Step 2: The drift test widens.** `tests/test_costmin_drift.py` pins all twelve against the newest snapshot. `cli/engine/feeders.py::load_minimums` filters `quote == "EUR"`, so the two XBT entries are read **directly from the snapshot's `universe` block** in the test (same file, no new production reader) — assert value AND quote currency for all twelve.
- [ ] **Step 3–4: red → green.** **Step 5: Gate, stage, commit** `feat(engine): symbol-keyed instruments, per-symbol costmin with explicit quote, the FX term`.

### Task 3: VenueState, the venue ledger, and the gauges go twelve-wide

**Files:** Modify `cli/engine/venuestate.py`, `cli/engine/command.py`, `tests/test_engine_venuestate.py`, `tests/test_engine_metrics.py`.

- [ ] **Step 1:** `venue_state_from_cache` reads the twelve `INSTRUMENT_IDS`; `VenueState.instruments` keys by symbol; `InstrumentConstraints` gains `costmin_quote: str` (from `COSTMIN`), `to_payload()` carries it beside the existing `costmin_source` label; `runtime_concordance` checks the three Cache-supplied constraints for all twelve.
- [ ] **Step 2:** `_VenueGauges`/`CycleResult.venue` `expected` derives `len(INSTRUMENT_IDS)` — tests assert `== 12` now (the literal pin moves with the basket, deliberately). The startup seed and the sink paths are un-re-keyed by design (they consume the summary dict, not the keys) — verify rather than assume, and say so in the report.
- [ ] **Step 3:** Fakes in the venuestate tests grow the two `/BTC` instruments with XBT-denominated attributes (`min_notional` still `None` — D5a of `00089` is unchanged and its exclusion from the runtime check stays).
- [ ] **Step 4: red → green** on the two test files. **Step 5: Gate, stage, commit** `feat(engine): VenueState and the venue gauges widen to the twelve-leg basket`.

### Task 4: Journal schema 2

**Files:** Modify `cli/engine/journal.py`, `tests/test_engine_journal.py` (find the real file name first).

**Interfaces:**
- `SCHEMA_VERSION = 2`; `_LOADABLE_SCHEMA_VERSIONS = frozenset({1, 2})` (the registry's own pattern, named in its comment).
- `from_json` loads BOTH: a v1 record keeps its base-keyed `final_targets` **as-is** (no rewriting — the gate normalizes at compare time, Task 6); a v2 record requires full-symbol keys.
- `validate_record` is schema-aware: v2 refuses base keys (`"ETH"` in a v2 record is a hard `EngineJournalError` — D3's verification bullet: wrong keying is refused, never silently normalized); v1 refuses symbol keys likewise (a v1 record was written by code that could not produce them).
- The record hash: v1 records verify under the v1 byte layout unchanged; v2 defines its layout with `schema_version` in the hashed prefix exactly as v1 did. Existing journaled records on the live host MUST still round-trip — pin with a fixture captured from the current `to_json` output before any edit.

- [ ] **Step 1: Capture the v1 golden fixture FIRST** — serialize a `CycleRecord` with today's code, commit the literal into the test as the compatibility pin.
- [ ] **Step 2: Failing tests** — v1 golden round-trips byte-identically post-change; v2 round-trips; v2-with-base-keys refused; v1-with-symbol-keys refused; unknown schema refused; hash stability for the v1 golden.
- [ ] **Step 3–4: red → green.** **Step 5: Gate, stage, commit** `feat(engine): journal schema 2 -- symbol-keyed targets, both schemas loadable`.

### Task 5: The cycle — basket expansion, symbol targets, schema-2 records

**Files:** Modify `cli/engine/cycle.py`, `tests/test_engine_cycle.py`.

**Interfaces:**
- Produces: `_expand_to_basket(model_targets: dict[str, float]) -> dict[str, float]` — base-keyed ten in, symbol-keyed twelve out: each base maps to its `<base>/EUR` symbol carrying the model's value; `BASKET` members with no model output (`ETH/BTC`, `SOL/BTC`) emit **exactly `0.0`**. A model base with no `<base>/EUR` in `BASKET` raises (fail loud).
- `run_cycle` journals the expanded twelve (schema 2); orders derive from symbol-keyed deltas — a `0.0` target with a `0.0` previous target produces **no order row** for the `/BTC` legs (assert it: order emission is delta-driven and structurally silent there).

- [ ] **Step 1: THE TWO D1 PINS, written before any edit:**

```python
def test_eur_targets_are_the_models_own_values_under_symbol_keys(...):
    """D1's identity pin: the expansion relabels, never recomputes. The model's ten outputs
    appear verbatim under their /EUR symbols."""
    model_out = {"BTC": 0.2, "ETH": -0.1, ...}  # a full ten-base dict, exact fixture values
    expanded = _expand_to_basket(model_out)
    assert expanded["BTC/EUR"] == 0.2 and expanded["ETH/EUR"] == -0.1
    assert set(expanded) == set(BASKET)


def test_btc_legs_are_exactly_zero_and_emit_no_orders(...):
    """D1's zero pin, end to end: a full cycle journals ETH/BTC and SOL/BTC at exactly 0.0,
    and the orders list contains no row for either."""
```

- [ ] **Step 2: red → implement → green**, migrating the existing cycle tests to symbol keys with values preserved.
- [ ] **Step 3: Mutation probes, both named in the report:** (a) widen `CrossfreqSystemConfig.assets` to include `"ETH/BTC"`-adjacent data (the sleeve-sees-an-eleventh-asset defect) → the identity pin must go red; (b) make `_expand_to_basket` emit a non-zero `/BTC` value → the zero pin must go red. Controls proven, tree restored (`infra/scripts/mutate-probe.sh`).
- [ ] **Step 4: Gate, stage, commit** `feat(engine): the basket expansion -- twelve symbol-keyed targets, /BTC at structural zero`.

### Task 6: The gate becomes mixed-window-aware

**Files:** Modify `cli/engine/concordance.py`, `tests/test_engine_concordance.py` (find the real name); sweep-routed edits in `cli/engine/soak.py`.

- [ ] **Step 1:** `replay_cycle` dispatches on `record.schema_version`: v1 replays the ten-asset builder path and **normalizes its base keys to `<base>/EUR`** for comparison; v2 replays the twelve-leg path (model + `_expand_to_basket` — the same code the cycle runs, imported, never duplicated). `compare_targets` itself stays key-agnostic.
- [ ] **Step 2: THE STRADDLE TEST** — construct a journaled run of outcomes spanning the boundary (v1 records before, v2 after, same underlying fixture data) and assert `evaluate_gate` scores an **unbroken streak** across it. Then the refusal leg: a v2 record with base keys never reaches comparison (Task 4's validation refuses it first — assert the error surfaces, not a silent pass).
- [ ] **Step 3:** Route the sweep's `soak.py`/`feeders.py` hits (both read target/universe shapes); the soak's own tests move to symbol keys, values preserved.
- [ ] **Step 4: red → green; gate, stage, commit** `feat(engine): schema-aware gate replay -- the streak survives the boundary`.

### Task 7: Re-ratification — the successor spec, the record, the owner's adopt

**Files:** Create the successor research spec under `docs/research/`; append to `docs/reference/trial-registry.jsonl`; modify the engine self-test's pin in `cli/engine/command.py`.

- [ ] **Step 1: Locate record 44's own spec doc** (resolve its `spec_hash` against committed files — `git grep` the hash in `docs/`; read how that doc is structured) and how records are appended (`cli/registry/record.py`'s writer surface and the append-only discipline). Do not guess either.
- [ ] **Step 2: Author the successor spec** — the widened deployable: the twelve-leg basket (DOT deliberately kept, the T0137 ruling cited), the ten-asset model unchanged, the `/BTC` legs at structural zero via `_expand_to_basket`, metrics expected identical to record 44's on the EUR legs. **This doc is immutable once its sha256 lands in the record** — write it final.
- [ ] **Step 3: Mint the record** via the committed builder/reproduction path with `verdict: "park"` INITIALLY — the append is autonomous, the ADOPT is not.
- [ ] **Step 4 (ATTENDED — the owner's act):** present the record and its reproduced metrics; the owner speaks the adopt. Only then flip the engine self-test's pin to the new `trial_id` (the registry's next id at append — do NOT assume 45; trial 46 is already taken by a B1 reject).
- [ ] **Step 5: Gate, stage, commit** `feat(engine): re-ratify the deployable on the twelve-leg basket` (the spec-doc commit may precede the record commit; keep the doc and its hash consistent).

### Task 8: The concordance baseline and the sequence table

**Files:** Modify `tests/test_basket_concordance.py`, `docs/open-topics/T0018-phase6-build-sequence.md`.

- [ ] **Step 1:** `RULED_SELECTED_BUT_UNREACHABLE` becomes the empty set — delete the exception WITH its comment replaced by the retirement citation (the T0137 survey + the 6b ruling). The basket side reads from `BASKET` now (symbols, not `f"{base}/EUR"` derivation). `RULED_TRADED_BUT_DESELECTED` stays `{"DOT/EUR"}`, its comment rewritten to cite the RULING (keep-traded, 2026-08-14, the test itself the revisit trigger).
- [ ] **Step 2: Mutation probes** — both directions must still bite: remove a `/BTC` leg from the committed universe doc's selected line → red; drop the DOT exception → red.
- [ ] **Step 3:** T0018's table: `00094` row → `landed (iter-<N>)` is Task 9's; here update the row's subject if the sweep changed its shape, nothing else.
- [ ] **Step 4: Gate, stage, commit** `test(engine): the concordance baseline shrinks to the ruled DOT exception`.

### Task 9: Closeout

**Files:** phase-6 history + decisions log; `docs/open-topics/T0137-*` (resolve + archive via `topic-ops`) + index; T0018 rows; the deploy notes.

- [ ] **Step 1:** Load `iteration-closeout`; author the entry FROM THE BRANCH LOG (which now also carries the T0137 survey, three rulings, and the 00089-correction commits — the entry covers the whole branch, not just Tasks 1–8).
- [ ] **Step 2:** Decisions log: the three owner rulings (fully-tradeable depth over minimal; keep-DOT over retire; coupled re-ratification over capability-first) plus D1's construction and D3's mixed-window design, options and `(Decision: N)` marked.
- [ ] **Step 3:** **T0137 → `resolved` + archived**, both halves cited, `ripe_when` absent, index bullet moved and repointed.
- [ ] **Step 4: THE FULL SUITE, in this task, foreground** — `uv run pytest -q`, the `00089` lesson as standing practice. Green before the closeout commit.
- [ ] **Step 5:** Deploy notes into the closeout entry: this payload stacks with `00089`'s still-owed converge — one converge may carry both or two may run; decided at deploy time under `capture-deploys.md`, with D3's specific by-value check (the gate streak after the first schema-2 cycle equals the streak before it plus one).
- [ ] **Step 6: Gate, stage by explicit path, commit** `docs(engine): iter-<N> closeout -- the /BTC widening lands; T0137 resolves`.

---

## The deploy (after merge — NOT part of task execution)

Standard engine discipline: canary via the secondary's capture bake, inter-cycle window, `fleet-pins.md` first, attended converge. **Stacking with `00089`'s owed converge is an operational call at deploy time.** Verify by value: the first schema-2 `cycle-HH.json` carries twelve symbol-keyed targets with both `/BTC` legs at `0.0`; `venue-HH.json` reads twelve instruments; the gate streak after that cycle equals its pre-deploy value plus one — a streak reset is the D3 failure and rolls back.
