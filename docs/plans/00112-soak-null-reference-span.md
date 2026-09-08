# Plan — the soak's null reference spans only the era its basket exists in

Spec: `docs/specs/00112-soak-null-reference-span-design.md`. Branch `fix/t0184-soak-hhi-aggregate`, off `develop`.

## Global constraints

- `cli/engine/soak.py` is off the live trade path but the soak report is the instrument a go-live decision reads. Every change is fail-safe or refuses; none may make a verdict quieter without saying so on the report's own face.
- **`structural_metrics` is NOT touched.** The per-bar `0.0` stays. Spec D4.
- **The builder's INPUT is not sliced.** `build_crossfreq_system_fast` receives the full canonical arrays; only the result's per-bar series are cut. Spec D2 — reversing this reintroduces the defect.
- Do not touch `cli/capture/`, `cli/tick/`, `cli/backfill/`, `cli/xcheck/`, `cli/portfolio/record44_legs.py`.
- Every per-bar list on `NullSystem` is parallel and must be cut with the same index, and the two derived scalars recomputed. The fields are `weights`, `net_live`, `multipliers`, `day_index`, `governed_net`, `cap_breach` (lists) and `n_periods`, `cap_breach_bars` (derived). `day_index` feeds `governor_engaged_daily`, so a desynchronised cut silently misattributes governor days.
- Tests live in `tests/test_engine_soak.py` (130 tests today) and `tests/test_engine_soak_command.py`. `test_build_null_on_real_canonical` reads `data/ohlc-full`, which is gitignored and absent in CI — a test that needs it is data-gated and must be run locally before the PR.

## Task 1 — derive the first bar at which the basket is complete

`cli/engine/soak.py`. Add a module-level helper beside `_load_canonical`:

```python
def _basket_complete_index(prices: dict[str, list[float | None]], assets: tuple[str, ...]) -> int:
    """The first index at which every basket asset carries a finite price -- the null's reference starts here,
    because a cross-sectional statistic over a partly-listed basket measures the listing, not the strategy
    (spec 00112 D1). Derived, never a date: the basket changes and a constant would not (D3)."""
```

It returns the index, and raises `SoakError` naming the assets that are never all present together if no such index exists. A `None` or a non-finite entry both count as absent.

Tests in `tests/test_engine_soak.py`:
- `test_basket_complete_index_is_the_first_all_present_bar`: three assets, one entering late, asserts the index is that asset's first bar.
- `test_basket_complete_index_ignores_a_later_hole`: an asset present, absent, then present again — the index is the first ALL-present bar, and a later hole does not move it.
- `test_basket_complete_index_refuses_a_basket_never_complete`: one asset all-`None` → `SoakError` naming it.
- `test_basket_complete_index_is_zero_when_all_present_from_the_start`: the true-positive control.

Red proof: each of the first three fails against a stub returning `0`.

## Task 2 — cut the null's series at that index

`cli/engine/soak.py`, in `build_null`, after `_net_live_from_result` and before the `NullSystem` construction. Compute `cut = _basket_complete_index(h4_prices, config.assets)` — the h4 grid, because the null's bars are h4 bars — then slice every parallel list from `cut` and recompute the two scalars: `n_periods` becomes the retained length and `cap_breach_bars` is recomputed from the retained `cap_breach`, never carried over.

The comment above the slice states what D2 fixes: the builder saw the whole history, so the first retained bar is warm.

Tests in `tests/test_engine_soak.py`, all against a stubbed builder so they need no canonical tree (follow `test_build_null_path_selects_builder` at `:454` for the stubbing shape):
- `test_build_null_drops_bars_before_the_basket_completes`: a stub whose late asset enters at bar k — asserts `n_periods` equals the retained count and that `weights[0]` is the bar at index k.
- `test_build_null_cuts_every_parallel_series_to_the_same_length`: asserts `len()` is equal across `weights`, `net_live`, `multipliers`, `day_index`, `governed_net`, `cap_breach` and equal to `n_periods`. This is the desynchronisation guard; it must fail against a version that slices `weights` alone.
- `test_build_null_recomputes_cap_breach_bars_over_retained_bars`: a stub with a clipped bar BEFORE the cut and one after — asserts `cap_breach_bars == 1`, which fails against a carried-over count of 2.
- `test_build_null_keeps_everything_when_the_basket_is_complete_from_bar_zero`: the true-positive control; nothing is dropped and `n_periods` is unchanged.

Red proof for each by the mutation its name implies; the count test's control must fail for a different reason than the length test's.

## Task 3 — the report says which span the null covers

`cli/engine/soak.py`, `render_soak_report`. The `REALIZED-SERIES WINDOW` block already prints the realized span. Add a `NULL REFERENCE SPAN` block beside it, printing the retained bar count and the first and last stamp the null covers, so two runs against different references are distinguishable on the page (spec D5).

This needs the stamps on `NullSystem`: add a field carrying the retained h4 stamps, or the first and last — choose the smaller change and say which in the report file. Operator-visible text: no `T<NNNN>`, no `spec <NNNNN>`, no `Phase <N>`, no `iter-<N>` (`.claude/rules/operator-facing-text.md`); `tests/test_internal_terms_not_operator_visible.py` enforces it and must pass.

Test: `test_report_states_the_null_reference_span` asserts the block is present and carries the retained count, failing against today's renderer.

## Task 4 — closeout

- `docs/reference/data-catalog-full.md`: under `ohlc-full`, one sentence recording that the basket completes on 2021-12-21 with AVAX the last leg, and that a cross-sectional statistic computed over the full span therefore measures a growing universe before that date. The per-symbol table already carries the dates; what is missing is the consequence a consumer acts on.
- `docs/open-topics/T0184-soak-hhi-aggregate-averages-a-sentinel.md`: move the span item to `## Done so far` rewritten as its outcome, leave the aggregation item open, keep `status: partial`.
- `docs/iterations-history-phase6.md`: one entry, bullets saying what a reader of the soak report now does differently.
- Run the data-gated tests locally, naming which data root was present: `tests/test_engine_soak.py`, `tests/test_engine_soak_command.py`, `tests/test_internal_terms_not_operator_visible.py`, `tests/test_code_prose_citations.py`, plus whatever `git grep -l soak -- tests/` adds.
