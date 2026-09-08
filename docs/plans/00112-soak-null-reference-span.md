# Plan — the soak's null reference spans only the era its basket exists in

Spec: `docs/specs/00112-soak-null-reference-span-design.md`. Branch `fix/t0184-soak-hhi-aggregate`, off `develop`.

## Global constraints

- `cli/engine/soak.py` is off the live trade path but the soak report is the instrument a go-live decision reads. Every change is fail-safe or refuses; none may make a verdict quieter without saying so on the report's own face.
- **`structural_metrics` is NOT touched.** The per-bar `0.0` stays. Spec D4.
- **The builder's INPUT is not sliced.** `build_crossfreq_system_fast` receives the full canonical arrays; only the result's per-bar series are cut. Spec D2 — reversing this reintroduces the defect.
- Do not touch `cli/capture/`, `cli/tick/`, `cli/backfill/`, `cli/xcheck/`, `cli/portfolio/record44_legs.py`.
- Every per-bar list on `NullSystem` is parallel and must be cut with the same index, and the two derived scalars recomputed. The fields are `weights`, `net_live`, `multipliers`, `day_index`, `governed_net`, `cap_breach` (lists) and `n_periods`, `cap_breach_bars` (derived). `day_index` feeds `governor_engaged_daily`, so a desynchronised cut silently misattributes governor days. Task 3's reference-span field is deliberately NOT a seventh parallel list — it holds two stamps — so this enumeration stays closed and no new series can fall out of step with it.
- **`null` is `None` on three of `soak_report`'s four paths**, and nothing in `render_report` or `_json_payload` dereferences it today, so a new read has no sibling guard to copy: `cli/engine/soak.py:1538` and `:1548` render with `None, None, None, None` (no journaled cycles; `realized_series` raised) and `:1598` with the canonical-absent branch's `null=None`, each followed immediately by `_json_payload` on the same arguments. Four existing tests call the renderer that way too — `tests/test_engine_soak.py:1387`, `:1429`, `:1456`, `:1594`. Every new read of `null` on either face is guarded.
- Tests live in `tests/test_engine_soak.py` (136 collected by `uv run pytest --collect-only -q` today) and `tests/test_engine_soak_command.py` (10). `test_build_null_on_real_canonical` reads `data/ohlc-full`, which is gitignored and absent in CI **and absent from this worktree** — a test that needs it is data-gated and must be run locally before the PR, on the precondition Task 4 states.

## Task 1 — derive the first bar at which the basket is complete

`cli/engine/soak.py`. Add a module-level helper beside `_load_canonical`:

```python
def _basket_complete_index(prices: dict[str, list[float | None]], assets: tuple[str, ...]) -> int:
    """The first index at which every basket asset carries a finite price, derived per call because the basket
    changes and a constant would not (spec 00112 D3)."""
```

That docstring is the whole of it: one sentence of contract plus the one clause that stops the wrong edit this task invites, hardcoding the index (`.claude/rules/prose.md`). Why the cut exists at all belongs at the call site, where Task 2 puts it.

It returns the index, and raises `SoakError` naming the assets that are never all present together if no such index exists. `None`, a non-finite entry, and an asset carrying no entry in `prices` at all count as absent — the last at every index, so a missing key reaches the refusal instead of raising `KeyError` out of a helper nobody catches.

Tests in `tests/test_engine_soak.py`:
- `test_basket_complete_index_is_the_first_all_present_bar`: three assets, one entering late, asserts the index is that asset's first bar.
- `test_basket_complete_index_ignores_a_later_hole`: three assets, the second entering at bar 2 and the third absent again at bar 4 — asserts the index is 2, the first ALL-present bar, and that the later hole does not move it. The fixture's first all-present bar must be greater than zero or a helper stubbed to return `0` passes it and the red proof below cannot be produced.
- `test_basket_complete_index_refuses_a_basket_never_complete`: one asset all-`None` → `SoakError` naming it.
- `test_basket_complete_index_refuses_an_asset_missing_from_prices`: an asset in `assets` with no key in `prices` → the same `SoakError`, naming it.
- `test_basket_complete_index_is_zero_when_all_present_from_the_start`: the true-positive control.

Red proof: each of the first four fails against a stub returning `0`.

## Task 2 — cut the null's series at that index

`cli/engine/soak.py`, in `build_null`, after `_net_live_from_result` and before the `NullSystem` construction, in this order:

1. **Refuse a disagreement while both sides still exist**: `sum(cap_breach) != result.cap_breach_bars` raises `SoakError`. The soak's own reconstruction and the builder's count are two independent computations of one quantity — `_net_live_from_result`'s docstring (`cli/engine/soak.py:283`) states the invariant that binds them — and `tests/test_engine_soak.py:451`'s `assert sum(ns.cap_breach) == ns.cap_breach_bars` is the only place in the tree that compares them over the full canonical. Step 3 turns that assertion into `sum(x) == sum(x)`, so the comparison moves here or it is gone, and the `cap_breach` gating verdict a go-live decision reads keeps a reconstruction the builder disagrees with. `n_periods` has no such twin — it is `result.n_periods` and every per-bar list is already built from it — so it is the only other derived scalar and it needs nothing.
2. Compute `cut = _basket_complete_index(h4_prices, config.assets)` — the h4 grid, because the null's bars are h4 bars.
3. Slice every parallel list from `cut` and recompute the two scalars: `n_periods` becomes the retained length and `cap_breach_bars` is recomputed from the retained `cap_breach`, never carried over.

The comment above the slice states what D2 fixes: the builder saw the whole history, so the first retained bar is warm.

**Both new refusals are contained at the call site rather than left to abort the command.** They are DATA-driven, unlike the `path` refusal already in `build_null`: a canonical that predates the newest basket leg is the ordinary state after a basket change, which spec D3 says to expect, and a builder-vs-reconstruction disagreement is a property of a run. `build_null` is called at `cli/engine/soak.py:1559` with no handler, so either refusal would abort `soak-check` through `cli/engine/command.py:1094` and print nothing at all — no realized-series window, no STORE-BOUND WINDOW warning, no self-tests — where every other canonical-side shortfall degrades instead. Wrap that call in `except SoakError as exc`, append `f"null unavailable: {exc}"` to `void_reasons` beside `"canonical absent — null unavailable"`, and leave `null`, `analysis`, `self_test` and `internals` as `None`, exactly as the canonical-absent branch does, so `soak_report`'s contract that it never raises on a short, void or absent-canonical run still holds.

**Two existing tests stub `_load_canonical` to an empty panel and must be widened in this task** — `git grep -n '_load_canonical", lambda' -- tests/` returns both and no others: `tests/test_engine_soak.py:459` (`test_build_null_path_selects_builder`) and `:2511` (`test_build_null_casts_its_book_onto_the_live_symbol_space`). Both return `({}, [], {}, [])`, so `h4_prices` is `{}`, no index exists, and Task 1's helper refuses before either test's own assertions run. Give each a ten-key h4 panel keyed by `CrossfreqSystemConfig().assets`, every leg finite from index 0 so `cut` is 0 and neither test's subject moves, over an `h4_ts` of `result.n_periods + 1` four-hourly stamps. **Task 1's refusal is not to be relaxed to make them pass**: a helper returning `0` where no index exists ships the full-span null this pair exists to remove, under a report block that says otherwise, and the refusal's own test would stay green through it.

Tests against a stubbed builder and that widened loader stub, so they need no canonical tree — in `tests/test_engine_soak.py` unless the bullet names another file:
- `test_build_null_drops_bars_before_the_basket_completes`: a stub whose late asset enters at bar k — asserts `n_periods` equals the retained count and that `weights[0]` is the bar at index k.
- `test_build_null_cuts_every_parallel_series_to_the_same_length`: asserts `len()` is equal across `weights`, `net_live`, `multipliers`, `day_index`, `governed_net`, `cap_breach` and equal to `n_periods`. This is the desynchronisation guard; it must fail against a version that slices `weights` alone.
- `test_build_null_recomputes_cap_breach_bars_over_retained_bars`: a stub with a clipped bar BEFORE the cut and one after — asserts `cap_breach_bars == 1`, which fails against a carried-over count of 2.
- `test_build_null_refuses_a_builder_count_its_reconstruction_disagrees_with`: the same stub with `result.cap_breach_bars` set one above what its sleeves reconstruct → `SoakError`; the unmodified stub is the true-positive control that must still build.
- `test_build_null_keeps_everything_when_the_basket_is_complete_from_bar_zero`: the true-positive control; nothing is dropped and `n_periods` is unchanged.
- `test_soak_report_degrades_when_the_null_refuses`, in `tests/test_engine_soak_command.py` beside `test_soak_check_no_canonical_short_window_is_no_verdict` (`:84`) and on its `_mk_journal_and_store` fixture: a canonical directory `_canonical_present` accepts, with `_load_canonical` stubbed to a panel one leg never enters — asserts the run exits as that test's does, that the report still carries the realized-series window and the self-tests block, and that `void_reasons` names the null as unavailable.

Red proof for each by the mutation its name implies; the count test's control must fail for a different reason than the length test's.

**The one real-data assertion.** Every test above runs against a stub, so nothing else exercises the cut over a real price panel. Extend `test_build_null_on_real_canonical` (`tests/test_engine_soak.py:441`, data-gated) with the property that defines the cut, derived from the loader and never written as `17971` or as a date, which the basket's next change would falsify: with `h4_prices`/`h4_ts` loaded in the test and `k = len(h4_ts) - 1 - ns.n_periods` the number of dropped bars, assert `k > 0` (a cut fired at all — a helper returning `0` on the real panel is otherwise a silent no-op that passes every existing assertion in that test), that every `CrossfreqSystemConfig().assets` leg carries a finite price at index `k`, and that at least one does not at `k - 1`.

## Task 3 — the report says which span the null covers

`cli/engine/soak.py`, `render_report` (`:1238`). The `REALIZED-SERIES WINDOW` block already prints the realized span. Add a `NULL REFERENCE SPAN` block beside it, above the void gate at `:1309`, so a void run carries it too: the span is provenance, and a run that prints NO VERDICT still says which reference it would have judged against. Two runs against different references are then distinguishable on the page (spec D5).

`null` is `None` on the no-journal and canonical-absent runs (Global constraints), so the block carries two independent guards, the way the realized-window block already carries its own two (`:1263` for the span lines, `:1275` for `window_bound`). Under `if null is not None`, with `  no null reference available` otherwise — the shape at `:1272`:

- `retained bars` — `null.n_periods`, which Task 2 redefined to the retained length, so no second count exists to drift from it.
- `first bar` / `last  bar` — the two stamps of the reference span.
- `no-book bars` — how many retained null bars carry `structural_metrics`' no-book sentinel, with the total they are out of.

Under `if realized is not None`, so it still prints when the canonical is absent and the trigger below stays readable:

- `realized no-book bars` — the same count over the realized window, with its own total.

Count both as `structural_metrics(...)["hhi"] == 0.0`, the sentinel branch's own output rather than a second spelling of its `gross > 1e-12` test, so neither count can disagree with the branch it reports. The realized line is what `T0184`'s parked aggregation ruling is read off: a realized window carrying a no-book bar is the point at which the live figure itself is biased rather than only the reference it is compared against (spec D5).

**The stamps field.** `NullSystem` gains ONE field, `reference_span: tuple[datetime, datetime] | None = None` — the first and last retained stamp, never a seventh per-bar list, so the Global constraints' parallel-list enumeration stays closed and Task 2's length guard needs no new name. It is populated in `build_null` (`cli/engine/soak.py:369`), not in the renderer: `(h4_ts[cut], h4_ts[n - 1])` with `n = result.n_periods`, and `None` when `n <= cut`. **`h4_ts[cut:]` is the wrong slice** — `h4_ts` is one longer than every per-bar list (`:319` records the same offset for `multipliers`), so its last entry is the forming bar the null never scores: on today's canonical `h4_ts[-1]` is 2026-03-31T20:00 against a last scored bar of 2026-03-31T16:00, and a span whose end postdates the bars the verdicts were computed over defeats the disclosure. The field's default keeps the two `NullSystem` construction sites outside `build_null` working unchanged — `_mk_null` (`tests/test_engine_soak.py:844`) and `_mk_fake_null` (`tests/test_engine_soak_command.py:132`), both of which pass all ten of today's fields by keyword, no field of `NullSystem` carrying a default.

**The JSON face carries the same values.** `_json_payload` (`:1408`) is the machine-readable twin and today discards the null (`del null` at `:1412`) under a docstring asserting that every null-derived number already lives in `analysis` — false the moment the span exists only on `NullSystem`, and two payloads archived across this change would otherwise carry identical `provenance` blocks and different bands with nothing saying the reference moved. Add a `null_reference` block beside `provenance` carrying the retained count, the two stamps and the null's no-book count, `None` when `null` is `None`; put the realized no-book count in `provenance`, where the realized window's own facts already live, so it survives a canonical-absent run exactly as its text line does; delete the `del null`; correct that docstring clause. The convention is the repo's own — `window_bound` lives in the realized-series block **and** in the JSON provenance (`README.md:120`, and the comment at `:1443`).

Operator-visible text: no `T<NNNN>`, no `spec <NNNNN>`, no `Phase <N>`, no `iter-<N>` and no `D<n>` decision numbers — `tests/test_internal_terms_not_operator_visible.py`'s `VOCABULARY` bans each of them over every non-docstring string literal under `cli/`, and a decision number is this task's likeliest slip because D5 is its whole subject (`.claude/rules/operator-facing-text.md`). It must pass.

Tests:
- `test_report_states_the_null_reference_span` (`tests/test_engine_soak.py`): asserts the block is present and carries the retained count and both stamps, failing against today's renderer.
- `test_report_names_the_absent_null_reference`: `render_report(None, rs, None, None, …)` renders the fallback line and does not raise.
- `test_build_null_reference_span_ends_at_the_last_scored_bar`: against Task 2's widened stub, asserts `reference_span[1]` is the stamp at `n_periods - 1` and not `h4_ts[-1]`, so an `h4_ts[cut:]` implementation goes red.
- `test_report_counts_no_book_bars_in_both_series`: a null and a realized series each carrying one all-zero-weight bar among active ones — asserts both counts, failing against a block that prints only the null's.
- `tests/test_engine_soak_command.py`: extend the payload assertions (`:119`–`:128` is the shape) with `null_reference` carrying the same retained count as the text block, `null_reference` `None` on the canonical-absent run, and `provenance`'s realized no-book count present on that same run.

## Task 4 — closeout

- `docs/reference/data-catalog-full.md`: under `ohlc-full`, one sentence recording that the basket completes on 2021-12-21 with AVAX the last leg, and that a cross-sectional statistic computed over the full span therefore measures a growing universe before that date. The per-symbol table already carries the dates; what is missing is the consequence a consumer acts on.
- `README.md:120`, the `soak-check` row: the null is no longer "rebuilt from the frozen canonical dataset" but from that dataset's complete-basket era, and the report carries a null-reference block in the text **and** in the JSON payload (`.claude/rules/readme-usage.md`).
- `docs/research/14.phase6-decisions.md`: the span ruling, in the form the entries this instrument already carries there use (`.claude/rules/decisions-log.md`; the `iteration-closeout` skill owns the entry format).
- `docs/open-topics/T0184-soak-hhi-aggregate-averages-a-sentinel.md` — the topic's WHOLE update lands in this PR (`.claude/rules/open-topics.md`), not the status alone:
  - move the span item to `## Done so far`, rewritten as its outcome;
  - rewrite the surviving aggregation next-step's figures to what the shipped null actually produces. Its "The null is where the 13.46% sits, and half its windows are affected" (`T0184:73`) is the full-span reading and this change falsifies it; the era-matched figures are 8.36% of bars over 53.72% of windows, already recorded at `T0184:60`. Correct `T0184:64`'s `0.4740` to `0.4739` in the same pass — that cell was computed at a cut eight bars past the one D3's rule yields, the same slip the spec's own band cells carried;
  - mark the five-candidate table (`T0184:42-50`) as scored against the pre-cut null, since every "what kills it" cell was measured there — the owner's aggregation ruling is made off that table and would otherwise be made against a reference the code no longer builds;
  - keep `status: partial` and add the aggregation ruling's trigger, read off the report rather than reasoned about, as frontmatter and in the index bullet: `ripe_when: uv run zcrypto engine soak-check reports a non-zero realized no-book bar count in its null-reference block, or an hhi verdict other than consistent`. The first clause fires when the live point estimate itself becomes biased rather than only its reference; the second when the live reading sits near enough to a band edge for the correction to flip it. Both are printed by the block Task 3 adds, which is what its no-book counts are for. Use the `topic-ops` skill for the file mechanics and the index sync.
- `docs/iterations-history-phase6.md`: one entry, bullets saying what a reader of the soak report now does differently.
- Run the data-gated tests locally, naming which data root was present: `tests/test_engine_soak.py`, `tests/test_engine_soak_command.py`, `tests/test_internal_terms_not_operator_visible.py`, `tests/test_code_prose_citations.py`, plus whatever `git grep -l soak -- tests/` adds. **`data/ohlc-full` is absent from this worktree and `test_build_null_on_real_canonical`'s skipif is a RELATIVE path**, so it skips silently here beside the passes and the skip is not coverage. Symlink the dataset in from the main checkout before the run and unlink it before the worktree is removed (`.claude/rules/agent-ops.md`'s snapshot bullet), and report that test by its own outcome — passed, never collected. It is the branch's only exercise of the cut against a real price panel.
