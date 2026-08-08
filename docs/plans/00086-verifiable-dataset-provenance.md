# Verifiable Dataset Provenance Implementation Plan

> # ⛔ STATUS 2026-08-08: STILL FAILING COLD REVIEW AFTER 4 ROUNDS — DO NOT IMPLEMENT
>
> The round-4 rewrite removed the previous do-not-implement marker; that was premature. An automated
> rework→two-cold-reviewers loop ran **4 rounds (12 agents)** and **did not converge**:
>
> | round | verdicts | blocking findings |
> |---|---|---|
> | 1 | REWORK / REWORK | 10 |
> | 2 | REWORK / REWORK | 6 |
> | 3 | REWORK / REWORK | 6 |
> | 4 | REWORK / REWORK | **5** |
>
> **The plateau is the finding.** Rounds 2–4 sat at 5–6, and the findings kept *moving* rather than
> recurring — each round genuinely fixed things and exposed new ones. They share one root cause:
>
> **The manifest ecosystem has no contract, so anything that reads it generically keeps meeting a
> writer it cannot handle.** Five committed writers, four `series` shapes, two set-level digest key
> spellings, a per-run nonce (`ohlc-reach`'s `series_digest` moves on every rebuild with zero content
> change), an absolute machine-local `source` path (`ohlc-15m`), and a holdout set with no set digest
> at all. Round 1 hit this as "the holdout is unregisterable"; round 4 hits it as
> "`derivatives-funding`/`-oi` are unregisterable" and "`ohlc-reach` false-alarms". Same wall, new brick.
>
> **This wants a different shape, not another round.** Two candidates for the next session:
> **(a) normalise the manifests first** — give them a contract and a single writer/reader, then build
> provenance on it; or **(b) narrow drastically** — an explicit allowlist of the datasets that actually
> back trials, refusing everything else loudly, and defer generality until (a) exists.
>
> Residual blocking findings from round 4, verbatim, for whoever picks this up:
>
> 1. **docs/plans/00086-verifiable-dataset-provenance.md Task 3 Step 2 — test_the_real_dataset_bytes_match_what_its_manifest_says; vs spec Verification bullet "For every dataset present here, the parquet row counts sum to the manifest's whole-set `rows`; every vouched per-series `sha256` is reproduced by a parquet"**
>    - defect: The only test that actually runs the bytes checks over real data is hardcoded to `ohlc-full`. `ohlc-15m`, `derivatives-funding` and `ohlc-holdout-2026-07-10` get no bytes check at all — `_bytes_findings` reaches them only via a schema-4 record naming them, and there are zero schema-4 records. The spec's Verification claim is therefore false as the plan stands, and the holdout — the one set whose ONLY link to its bytes is the row count (D5's stated residual) — is precisely the set left unchecked.
>    - fix: Parametrise it over `CATALOG_PINNED` (skipping per name where the manifest is absent), asserting `rows == capture_datasets({name: []}, DATA_ROOT)[name]["extent"]["rows"]` and `_vouched_sha256s(manifest["series"]) <= hashes` for each; keep the `len(hashes) == 36` pin as an ohlc-full-specific assertion or drop it. Expected values are the four rows measured above.
> 2. **docs/plans/00086-verifiable-dataset-provenance.md Task 3 Step 2 — test_the_vouches_no_bytes_allowlist_is_frozen_and_asserted_both_ways; vs spec D5 "no non-member present on disk may vouch nothing" and Verification "the vouches-nothing allowlist is non-vacuous and exhaustive"**
>    - defect: The both-direction assertion iterates the hardcoded 4-tuple `CATALOG_PINNED`, not the datasets actually present under `DATA_ROOT`. A set present on disk but absent from that tuple can vouch no per-series `sha256` and never be caught — which is exactly the escape hatch D5 exists to make loud. The plan's own Step 1 names two such candidates by name (`derivatives-oi`, `ohlc-reach` — documented, not on this machine, deliberately unpinned), so the first `data fetch` of either silently defeats the assertion.
>    - fix: Enumerate the sets from disk instead: `for manifest in sorted(DATA_ROOT.glob("*/manifest.json"))`, take `name = manifest.parent.name`, and assert the same equality. That makes the direction the spec states ("present on disk") the direction the test checks, and keeps `CATALOG_PINNED` for the pin test only.
> 3. **spec 00086 D4 refusal 4 (L141) / plan Task 1 Step 3 `_extent` / plan Task 3 `test_the_catalog_pins_the_current_series_digest_of_every_canonical_dataset_present_here` (plan L897-912)**
>    - defect: Refusing any leaf whose `first_ts`/`last_ts` is not a parseable non-empty str makes two committed writers' normal output uncapturable, so `derivatives-funding` and `derivatives-oi` become unregisterable whole-set and the catalog-pin test raises rather than fails.
>    - fix: Scope refusal 4 to leaves that carry data: refuse an unusable stamp only when `rows > 0`. A `rows == 0` leaf contributes 0 rows and no span endpoint, so counting it in `series` and excluding it from `span` cannot narrow anything -- D1's silent-collapse case is strictly rows>0-with-a-null-stamp and stays refused. Add the empty-series leaf to Task 1's matrix as a PASS case (the existing null-stamp refusal test must keep its `rows: 10`), and record the shape in Task 6 Step 2's manifest contract.
> 4. **plan Task 3 Step 4, `_bytes_findings` -- `whole, refusal = _captured(data_root, name, ())` (plan L1085)**
>    - defect: D5 re-captures the WHOLE set while `append()` captured only the declared slice, so a record `append()` legitimately writes can be permanently unclearable by Layer 2 on an append-only registry -- the same unrepairable-line class the plan's Global Constraints forbid for the append-vs-load pairing, left open for the append-vs-D5 pairing.
>    - fix: Make both layers read the same slice: run the row check from the record's own `select` capture (`_captured(..., tuple(entry['select']))` is already computed one line above) against the parquet that slice addresses; or, if a whole-set row sum is required, score a whole-set capture refusal as an explicit `unverifiable-here` verdict rather than a finding and say so in D5's honest-guarantee paragraph. Either way add a Global Constraint -- every shape `append()` can write must be a shape D5 can clear -- plus a test that constructs a manifest capturable in slice but not whole and asserts the record does not red.
> 5. **spec D1 L53 ("Nothing in the block is a per-run value … so a re-fetch that changes only the stamp cannot move `dataset_hash`") and L246, which attributes this defect only to the un-committed holdout writer; plan Task 1 `series_digest = compute_hash({"series": series})`**
>    - defect: `series_digest` is a per-run nonce for `ohlc-reach`, a COMMITTED writer with a live subcommand -- it moves on every rebuild with zero content change, which is precisely the false alarm the spec says the design cannot produce.
>    - fix: Digest a fixed projection of each leaf -- the contracted keys `rows`/`first_ts`/`last_ts` plus `sha256` when present -- rather than the whole leaf. That is writer-agnostic (no exhaustive volatile-key list, which is what D1 rightly rejected for top-level keys), per-run noise cannot enter, and the transitive commitment to per-series hashes is unchanged; the named cost is that a future content-bearing leaf key would not be covered, which belongs in the decay list. Alternative if the whole-leaf digest is kept: narrow the L53 claim to the writers it actually holds for and state per dataset which give a stable digest. Either way, add a test that runs a per-run-field writer twice over identical content and asserts one digest.
>
> Sound and worth keeping across any reshape: `dataset_hash = compute_hash(datasets)` derived from the
> record's own block; the `_STORE_OWNED` split that keeps all 46 records loadable; load-time
> enforcement in `validate_stored_record` (there is no production caller of `append()`).


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the trial registry's opaque, caller-supplied `dataset_hash` with a `datasets` block the store derives from each named dataset's manifest, re-derives from disk over the real files — bytes included — and, where the data is not on this machine or has since been refreshed, checks against a committed pin, so a future record's provenance cannot become unresolvable the way 44 of the 46 existing ones have.

**Architecture:** Schema 4 adds a `datasets` block carrying, per dataset, a normalised `select` (the declared slice), an `extent` (that slice, resolved against the manifest) and a `series_digest` (the whole set's drift alarm). `dataset_hash` becomes `compute_hash(datasets)`; both keys become store-owned, so the caller has no argument through which to supply either, and the data root is a module constant rather than a parameter. Two guard layers: `validate_stored_record` re-checks the round-trip on **every load** (D3), and a repo-level test re-derives every schema-4 block from `data/`, re-counts and re-hashes the parquet under each named dataset, and falls back to the catalog's committed `series_digest` pin list where the dataset is absent or superseded (D5). Historical hashes move into a committed table whose evidence the tests execute.

**Tech Stack:** Python 3.14, `cli/registry/` (`record.py`, `store.py`, new `provenance.py`), `cli/ohlc/dataset.py` (test-side parquet read/hash), polars, pytest, `infra/scripts/mutate-probe.sh`.

## Global Constraints

- Spec: `docs/specs/00086-verifiable-dataset-provenance-design.md`. Every decision reference below (D1–D7) is to that file.
- **The registry is append-only and hash-chained.** No task may rewrite, reorder or re-hash an existing record. `docs/reference/trial-registry.jsonl` is touched by NO task in this plan.
- **What reads the registry at runtime, measured — the constraint protects the right thing.** `cli/portfolio/record44_legs.py` constructs `TrialRegistry(path)` at two call sites and therefore goes through the loader: `TrialRegistry.__init__` keeps its single-argument signature and only `append()` changes shape. `cli/engine/command.py` does **not** construct a `TrialRegistry` — it hands `--registry` to `cli/engine/soak.py::_load_registry_record`, which `json.loads` the lines directly and reads only record 44's `metrics`. That path is unaffected by anything in Task 2, and equally uncovered by D3's invariant; the gap is pre-existing, out of scope, and registered in Task 6.
- `_LOADABLE_SCHEMA_VERSIONS` gains `4` and **keeps `2` and `3`**. All 46 committed records must keep loading unchanged; an absent `datasets` block below schema 4 is normal, never an error.
- **`_BASE_STORED_KEYS` is derived and is required of every record at every version** — `datasets` must never enter that derivation (D2). `dataset_hash` must stay in it (every record since schema 2 carries the key).
- **The writer and the loader must agree, and the writer is the side that must be stricter.** The registry is append-only, so a line `append()` writes but `validate_stored_record` rejects is unloadable and unremovable *forever*. Concretely: `validate_stored_record` rejects an empty `datasets` dict, so `capture_datasets` refuses an empty selection **before** `append` opens the file (Task 1 Step 3, Task 2 Step 2). Any new load-time shape check added later owes the same treatment.
- **The schema bump and the writer land in ONE commit (Task 2).** `append()` writes `schema_version=SCHEMA_VERSION`; bumping the constant while leaving `append()` alone would make every record the writer produces unloadable by the validator in the same commit, redding ~8 append-then-reload tests and leaving the tree red for `mutate-probe.sh`, which refuses to run from a red or dirty tree.
- Follow the `variant` precedent: a key that does not apply is **omitted entirely**, never serialised as `null`. The `datasets` entry has no such key — `select`, `series_digest` and `extent` are always present, and `extent` always carries `series`, `rows` and `span`, because a leaf that cannot supply one of them is refused at capture (D4 refusal 4) rather than dropped.
- Error messages are operator-facing: no `T<NNNN>`, no `spec 00086`, no `iter-<N>` in any raised string (`.claude/rules/operator-facing-text.md`). Those tokens go in comments.
- Every guard is proven by `infra/scripts/mutate-probe.sh`, never asserted. The probe refuses a dirty tree, so all probes run in Task 5, after Tasks 1–4 are committed. D5's layer is the one exception and is proven by its constructive companions instead (D7).
- Commit gate `uv run pre-commit run -a` before every commit; a rewriting run reports Failed and leaves rewrites unstaged — re-run, re-stage, re-commit.
- **No decisions-log entry is owed.** `.claude/rules/decisions-log.md` gates on a *subject-matter research* decision; this is registry engineering. Do not add one.
- **No README change is owed** — no CLI subcommand or option changes.

---

### Task 1: Capture a dataset's provenance from its manifest, whatever shape it is

Ordered first deliberately: it changes no schema and touches no existing test, so the suite stays green and Task 2 has `capture_datasets` available in the same commit as the writer that needs it.

**Files:**

- Create: `cli/registry/provenance.py`
- Create: `tests/test_registry_provenance.py`

**Interfaces:**

- Produces: `DATA_ROOT: Path` (the repo's own `data/`); `capture_datasets(selection: dict[str, list[str]], data_root: Path) -> dict` — the D1 block; raises `RegistryError` naming the offending dataset, path, series or token.
- Consumes: `cli.registry.record.compute_hash`, `cli.registry.errors.RegistryError`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_registry_provenance.py`:

```python
import json
from datetime import datetime

import pytest

from cli.registry.errors import RegistryError
from cli.registry.provenance import DATA_ROOT, capture_datasets


def _write(root, name, manifest):
    (root / name).mkdir(parents=True)
    (root / name / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _nested(**extra):
    return {
        "fetched_at": "2026-07-07T21:17:30+00:00",
        "source": "somewhere",
        "basket_sha256": "b" * 64,
        "series": {
            "BTC/EUR": {
                "1440": {"rows": 10, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-10T00:00:00+00:00", "sha256": "c" * 64},
                "240": {"rows": 60, "first_ts": "2020-01-01T04:00:00+00:00", "last_ts": "2020-01-10T20:00:00+00:00", "sha256": "d" * 64},
            },
            "ETH/EUR": {
                "1440": {"rows": 5, "first_ts": "2019-01-01T00:00:00+00:00", "last_ts": "2019-01-06T00:00:00+00:00", "sha256": "e" * 64},
            },
        },
        **extra,
    }


def test_an_empty_select_is_the_whole_set_and_sums_every_leaf(tmp_path):
    # A max()-based rows would read 60 and a single-series span would hide the 2019 start.
    _write(tmp_path, "ohlc-x", _nested())
    got = capture_datasets({"ohlc-x": []}, tmp_path)
    assert got["ohlc-x"]["extent"] == {
        "series": 3,
        "rows": 75,
        "span": ["2019-01-01T00:00:00+00:00", "2020-01-10T20:00:00+00:00"],
    }
    assert got["ohlc-x"]["select"] == []
    assert len(got["ohlc-x"]["series_digest"]) == 64


def test_capture_refuses_an_empty_selection(tmp_path):
    # An empty select LIST is the whole set; an empty selection MAPPING is a record with no provenance
    # at all -- exactly the failure this replaces. It must be refused here, because validate_stored_record
    # rejects such a record at LOAD and the registry is append-only: a line written this way could never
    # be read again and could never be removed.
    with pytest.raises(RegistryError, match="at least one dataset"):
        capture_datasets({}, tmp_path)


@pytest.mark.parametrize(
    "select,series,rows",
    [
        (["1440"], 2, 15),  # OR within one dimension: both pairs' daily
        (["240"], 1, 60),
        (["1440", "240"], 3, 75),
        (["BTC/EUR"], 2, 70),  # a whole pair, both its intervals
        (["BTC/EUR", "1440"], 1, 10),  # AND across dimensions: one leaf
    ],
)
def test_select_resolves_per_dimension_and_the_extent_is_that_slice(tmp_path, select, series, rows):
    # THE regression this design exists to prevent: without per-dimension resolution a daily-only
    # trial, a 4h-only trial and a daily+4h trial all get one identical extent and one identical digest.
    _write(tmp_path, "ohlc-x", _nested())
    got = capture_datasets({"ohlc-x": select}, tmp_path)["ohlc-x"]["extent"]
    assert (got["series"], got["rows"]) == (series, rows)


def test_distinct_slices_get_distinct_blocks(tmp_path):
    _write(tmp_path, "ohlc-x", _nested())
    blocks = [capture_datasets({"ohlc-x": s}, tmp_path) for s in ([], ["1440"], ["240"], ["1440", "240"])]
    assert len({json.dumps(b, sort_keys=True) for b in blocks}) == 4


def test_select_is_normalised_so_one_read_has_one_digest(tmp_path):
    # canonical_json sorts dict keys but preserves list order, so an un-normalised select would give
    # one identical read two different dataset_hash values.
    _write(tmp_path, "ohlc-x", _nested())
    a = capture_datasets({"ohlc-x": ["240", "1440"]}, tmp_path)
    b = capture_datasets({"ohlc-x": ["1440", "240", "1440"]}, tmp_path)
    assert a == b
    assert a["ohlc-x"]["select"] == ["1440", "240"]


def test_the_digest_covers_the_whole_series_subtree_not_the_slice(tmp_path):
    # series_digest is dataset-scoped on purpose: one dataset, one value, so the catalog can pin it
    # and a record stays checkable after the data leaves this machine or is refreshed under it (D1/D5).
    _write(tmp_path, "ohlc-x", _nested())
    whole = capture_datasets({"ohlc-x": []}, tmp_path)["ohlc-x"]["series_digest"]
    assert capture_datasets({"ohlc-x": ["1440"]}, tmp_path)["ohlc-x"]["series_digest"] == whole


def test_only_the_series_subtree_is_digested(tmp_path):
    # Measured on the real manifests: data/ohlc-full and data/ohlc-15m spell the SAME source directory
    # relatively and absolutely. A whole-manifest digest would fire on that, and on reach.py's
    # top-level min_seam_overlap knob -- i.e. on exactly the refresh the alarm must stay quiet for.
    _write(tmp_path, "a", _nested())
    _write(tmp_path, "b", _nested(fetched_at="2026-08-08T00:00:00+00:00", source="/abs/somewhere", min_seam_overlap=8))
    assert capture_datasets({"a": []}, tmp_path)["a"]["series_digest"] == capture_datasets({"b": []}, tmp_path)["b"]["series_digest"]


def test_a_content_change_does_move_the_digest(tmp_path):
    changed = _nested()
    changed["series"]["BTC/EUR"]["1440"]["sha256"] = "0" * 64
    _write(tmp_path, "a", _nested())
    _write(tmp_path, "b", changed)
    assert capture_datasets({"a": []}, tmp_path)["a"]["series_digest"] != capture_datasets({"b": []}, tmp_path)["b"]["series_digest"]


def test_a_flat_manifest_with_no_interval_level_is_captured(tmp_path):
    _write(tmp_path, "funding", {"fetched_at": "x", "basket_sha256": "b" * 64, "series": {
        "BTCUSDT": {"rows": 7, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-08T00:00:00+00:00", "sha256": "f" * 64},
        "ETHUSDT": {"rows": 3, "first_ts": "2020-01-05T00:00:00+00:00", "last_ts": "2020-01-08T00:00:00+00:00", "sha256": "a" * 64}}})
    got = capture_datasets({"funding": ["BTCUSDT"]}, tmp_path)["funding"]["extent"]
    assert (got["series"], got["rows"]) == (1, 7)


def test_a_list_shaped_manifest_is_captured_and_addressable_by_its_row_fields(tmp_path):
    # cli/ohlc/ingest.py and cli/ohlc/reach.py both emit this shape; the rows carry their own address,
    # so the dimensions are the field names rather than nesting depth.
    _write(tmp_path, "reach", {"built_at": "x", "basket_sha256": "b" * 64, "min_seam_overlap": 6, "series": [
        {"symbol": "BTC", "interval": 1440, "status": "continuous", "rows": 4,
         "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-04T00:00:00+00:00", "sha256": "a" * 64},
        {"symbol": "BTC", "interval": 240, "status": "continuous", "rows": 24,
         "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-04T20:00:00+00:00", "sha256": "b" * 64},
        {"symbol": "ETH", "interval": 1440, "status": "detached", "rows": 2,
         "first_ts": "2020-01-03T00:00:00+00:00", "last_ts": "2020-01-04T00:00:00+00:00", "sha256": "c" * 64}]})
    got = capture_datasets({"reach": ["1440", "BTC"]}, tmp_path)["reach"]["extent"]
    assert (got["series"], got["rows"]) == (1, 4)  # symbol AND interval, not either


def test_a_manifest_without_any_per_series_digest_is_captured(tmp_path):
    # data/ohlc-holdout-2026-07-10 has no basket_sha256 and no per-series sha256 at all, and spells its
    # stamps with a space separator. It is the deployable's out-of-sample evidence -- refusing it would
    # disqualify the design, and a string min()/max() across the two spellings would be wrong.
    _write(tmp_path, "holdout", {"pulled_at": "2026-07-10T01:30Z", "manifest_sha256": "0" * 64, "series": {
        "BTC": {"rows": 4681, "first_ts": "2013-09-10 00:00:00+00:00", "last_ts": "2026-07-09 00:00:00+00:00",
                "appended": 100, "overlap_bars_verified": 621}}})
    got = capture_datasets({"holdout": ["BTC"]}, tmp_path)
    assert got["holdout"]["extent"]["span"] == ["2013-09-10T00:00:00+00:00", "2026-07-09T00:00:00+00:00"]


def test_capture_refuses_a_missing_manifest_and_names_the_path(tmp_path):
    with pytest.raises(RegistryError, match=r"ohlc-absent/manifest\.json"):
        capture_datasets({"ohlc-absent": []}, tmp_path)


def test_capture_refuses_an_unparseable_manifest(tmp_path):
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "manifest.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(RegistryError, match="JSON"):
        capture_datasets({"broken": []}, tmp_path)


def test_capture_refuses_a_manifest_with_no_series(tmp_path):
    _write(tmp_path, "empty", {"fetched_at": "x", "series": {}})
    with pytest.raises(RegistryError, match="series"):
        capture_datasets({"empty": []}, tmp_path)


def test_capture_refuses_a_series_with_no_identifiable_leaf(tmp_path):
    _write(tmp_path, "shapeless", {"fetched_at": "x", "series": {"BTC": {"sha256": "a" * 64}}})
    with pytest.raises(RegistryError, match="rows"):
        capture_datasets({"shapeless": []}, tmp_path)


def test_capture_refuses_an_unparseable_timestamp(tmp_path):
    _write(tmp_path, "bad-ts", {"fetched_at": "x", "series": {
        "BTC": {"rows": 1, "first_ts": "yesterday", "last_ts": "today"}}})
    with pytest.raises(RegistryError, match="timestamp"):
        capture_datasets({"bad-ts": []}, tmp_path)


@pytest.mark.parametrize("stamp", [None, ""])
def test_capture_refuses_a_present_but_empty_timestamp_rather_than_dropping_the_leaf(tmp_path, stamp):
    # The silent-collapse case: `first_ts` PRESENT but null passes the leaf-shape test, so an earlier
    # design dropped it from the span while still counting it in `series` and `rows` -- an extent whose
    # span was narrower than the data it claimed to identify, with nothing downstream able to see it.
    _write(tmp_path, "null-ts", {"fetched_at": "x", "series": {
        "A": {"rows": 10, "first_ts": stamp, "last_ts": stamp},
        "B": {"rows": 10, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-02T00:00:00+00:00"}}})
    with pytest.raises(RegistryError, match="timestamp"):
        capture_datasets({"null-ts": []}, tmp_path)


def test_capture_refuses_a_non_int_row_count(tmp_path):
    _write(tmp_path, "strrows", {"fetched_at": "x", "series": {
        "BTC": {"rows": "10", "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-02T00:00:00+00:00"}}})
    with pytest.raises(RegistryError, match="rows"):
        capture_datasets({"strrows": []}, tmp_path)


def test_capture_refuses_an_unknown_select_token_and_names_it(tmp_path):
    _write(tmp_path, "ohlc-x", _nested())
    with pytest.raises(RegistryError, match="1441"):
        capture_datasets({"ohlc-x": ["1441"]}, tmp_path)


def test_capture_refuses_a_select_that_addresses_no_series(tmp_path):
    # Both tokens are real; ETH/EUR has no 4h leaf. Silently capturing the whole set here would be the
    # regression the resolution exists to prevent.
    _write(tmp_path, "ohlc-x", _nested())
    with pytest.raises(RegistryError, match="no series"):
        capture_datasets({"ohlc-x": ["ETH/EUR", "240"]}, tmp_path)


def test_the_block_is_built_in_sorted_name_order(tmp_path):
    _write(tmp_path, "a", _nested())
    _write(tmp_path, "b", _nested())
    assert list(capture_datasets({"b": [], "a": []}, tmp_path)) == ["a", "b"]


def test_the_data_root_constant_points_at_the_repo_data_dir():
    # append() takes no data-root argument; this constant IS the root, and D5 re-derives against it.
    assert DATA_ROOT.name == "data" and (DATA_ROOT.parent / "pyproject.toml").is_file()


_EUR_PAIRS = ["ADA/EUR", "AVAX/EUR", "BTC/EUR", "DOGE/EUR", "DOT/EUR", "ETH/EUR", "LINK/EUR", "LTC/EUR", "SOL/EUR", "XRP/EUR"]


@pytest.mark.parametrize(
    "name,series,rows,span",
    [
        ("ohlc-full", 36, 1052322, ["2013-09-10T00:00:00+00:00", "2026-03-31T23:00:00+00:00"]),
        ("ohlc-15m", 12, 3122044, ["2013-09-10T23:45:00+00:00", "2026-03-31T23:45:00+00:00"]),
        ("derivatives-funding", 10, 68281, ["2020-01-01T00:00:00+00:00", "2026-06-30T16:00:00.005000+00:00"]),
        ("ohlc-holdout-2026-07-10", 10, 30032, ["2013-09-10T00:00:00+00:00", "2026-07-09T00:00:00+00:00"]),
    ],
)
def test_capture_matches_the_measured_extent_of_every_real_dataset(name, series, rows, span):
    if not (DATA_ROOT / name / "manifest.json").is_file():
        pytest.skip(f"{name} absent")
    assert capture_datasets({name: []}, DATA_ROOT)[name]["extent"] == {"series": series, "rows": rows, "span": span}
    assert datetime.fromisoformat(span[0]) < datetime.fromisoformat(span[1])


@pytest.mark.skipif(not (DATA_ROOT / "ohlc-full" / "manifest.json").is_file(), reason="compiled datasets absent")
@pytest.mark.parametrize(
    "select,series,rows",
    [
        (["1440"], 12, 34460),
        (["240"], 12, 205917),
        (["1440", "240"], 24, 240377),
        (["BTC/EUR", "1440"], 1, 4581),
        ([*_EUR_PAIRS, "1440"], 10, 29032),
        ([*_EUR_PAIRS, "1440", "240"], 20, 202405),
    ],
)
def test_slices_of_the_real_dataset_resolve_to_their_measured_extents(select, series, rows):
    # The last row is the cross-check that matters: 29032 + 173373 = 202405 is exactly what
    # tests/test_crossfreq_system.py's frozen per-asset EXTENT table sums to, so the resolution
    # reproduces an independently pinned number instead of asserting one of its own.
    got = capture_datasets({"ohlc-full": select}, DATA_ROOT)["ohlc-full"]["extent"]
    assert (got["series"], got["rows"]) == (series, rows)


@pytest.mark.skipif(not (DATA_ROOT / "ohlc-full" / "manifest.json").is_file(), reason="compiled datasets absent")
def test_the_real_series_digest_is_stable_and_slice_independent():
    digest = "76edb3a0633a5ab5f9f2c6f9d7b3af4d2000c1aaab22c69da0e278cbe88eafb0"
    assert capture_datasets({"ohlc-full": []}, DATA_ROOT)["ohlc-full"]["series_digest"] == digest
    assert capture_datasets({"ohlc-full": ["1440"]}, DATA_ROOT)["ohlc-full"]["series_digest"] == digest
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: FAIL at collection — `cli.registry.provenance` does not exist.

- [ ] **Step 3: Implement `cli/registry/provenance.py`**

One walk produces the leaves *and* their addresses; the slice, the extent and the digest all read off that one traversal.

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from cli.registry.errors import RegistryError
from cli.registry.record import compute_hash

# The one root a record may be captured from. Deliberately a constant and NOT an append() argument:
# `run_ref` anchors to _REPO_ROOT for the same reason. It is also how the append-time and repo-level
# layers agree on what to compare (spec 00086 D4/D5). It removes the data-root PARAMETER, not the
# fabrication path -- data/ is writer-controlled, and closing that is D5's re-count and re-hash.
DATA_ROOT = Path(__file__).resolve().parents[2] / "data"  # cli/registry/provenance.py -> repo root

_LEAF_KEYS = frozenset({"rows", "first_ts", "last_ts"})
# The list-shaped manifests (cli/ohlc/ingest.py, cli/ohlc/reach.py) address their rows by these two
# fields instead of by nesting. This is the ONLY per-shape knowledge in the module.
_ROW_ADDRESS_KEYS = ("symbol", "interval")


def _walk(node, depth: int, address: dict[str, str], leaves: list[tuple[dict[str, str], dict]]) -> None:
    """Collect (address, leaf) pairs without assuming a manifest shape.

    An address maps a *dimension* to this leaf's token in it. Nesting depth is a dimension
    (`level0` = pair, `level1` = interval); a list-shaped manifest's rows carry theirs by field.
    """
    if type(node) is dict:
        if _LEAF_KEYS <= node.keys():
            address = dict(address)
            for key in _ROW_ADDRESS_KEYS:
                if type(node.get(key)) in (str, int):
                    address[key] = str(node[key])
            leaves.append((address, node))
            return  # a leaf's own fields are not addressing tokens
        for key, value in node.items():
            _walk(value, depth + 1, {**address, f"level{depth}": str(key)}, leaves)
    elif type(node) is list:
        for value in node:
            _walk(value, depth, address, leaves)


def _selected(leaves: list[tuple[dict[str, str], dict]], select: list[str], path: Path) -> list[tuple[dict[str, str], dict]]:
    """The leaves `select` addresses: AND across dimensions, OR within one. Empty select = all of them.

    A token that occurs in two dimensions (a symbol spelled like an interval) is required in both, so
    such a select resolves to nothing and is refused rather than silently widened.
    """
    dimensions: dict[str, set[str]] = {}
    for address, _leaf in leaves:
        for dimension, token in address.items():
            dimensions.setdefault(token, set()).add(dimension)
    unknown = [t for t in select if t not in dimensions]
    if unknown:
        raise RegistryError(f"{path}: unknown select token(s) {unknown}; addressable tokens are {sorted(dimensions)}")
    wanted: dict[str, set[str]] = {}
    for token in select:
        for dimension in dimensions[token]:
            wanted.setdefault(dimension, set()).add(token)
    matched = [(address, leaf) for address, leaf in leaves if all(address.get(d) in tokens for d, tokens in wanted.items())]
    if not matched:
        raise RegistryError(f"{path}: select {select} addresses no series; tokens from different dimensions must occur together")
    return matched


def _extent(matched: list[tuple[dict[str, str], dict]], path: Path) -> dict:
    """The identifier for the matched slice: leaf count, row sum, and the union span.

    All three sub-keys are ALWAYS present. A leaf carrying a non-int `rows`, or a stamp that is not a
    parseable non-empty str, is REFUSED here rather than dropped from the aggregate: dropping it would
    still count the leaf in `series` and `rows` while narrowing `span`, producing an extent whose span
    is narrower than the data it claims to identify — the silent collapse this field exists to prevent
    (spec 00086 D1/D4). The `except` deliberately catches ValueError only: a non-str stamp is the
    explicit check's job, and letting a TypeError escape is what makes that check probe-killable.
    """
    rows = 0
    firsts: list[datetime] = []
    lasts: list[datetime] = []
    for address, leaf in matched:
        if type(leaf["rows"]) is not int:  # type() is-strict: rejects bool and a stringified count
            raise RegistryError(f"{path}: series {address} carries rows {leaf['rows']!r}, which is not an int")
        stamps = [leaf["first_ts"], leaf["last_ts"]]
        if any(type(s) is not str or not s for s in stamps):
            raise RegistryError(f"{path}: series {address} has unusable timestamp(s) {stamps!r}; both must be non-empty str")
        try:
            first, last = (datetime.fromisoformat(s) for s in stamps)
        except ValueError as e:
            raise RegistryError(f"{path}: series {address} carries an unparseable timestamp: {e}") from e
        rows += leaf["rows"]
        firsts.append(first)
        lasts.append(last)
    return {"series": len(matched), "rows": rows, "span": [min(firsts).isoformat(), max(lasts).isoformat()]}


def capture_datasets(selection: dict[str, list[str]], data_root: Path) -> dict:
    """The provenance block for each named dataset, read from its manifest. Refuses what it cannot verify."""
    if not selection:
        # An empty select LIST is legal (the whole set); an empty selection MAPPING is not. The loader
        # rejects a record whose datasets block is empty, and the registry is append-only, so such a line
        # would be permanently unloadable and unremovable (spec 00086 D3/D4).
        raise RegistryError("datasets must name at least one dataset: a record with no provenance is the failure this replaces")
    out: dict = {}
    for name in sorted(selection):
        path = Path(data_root) / name / "manifest.json"
        if not path.is_file():
            raise RegistryError(f"no manifest at {path}: a trial can only be registered where the data it read is present")
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise RegistryError(f"{path} is not valid JSON: {e}") from e
        series = manifest.get("series")
        if not series:
            raise RegistryError(f"{path} carries no non-empty 'series': nothing in it identifies the data")
        leaves: list[tuple[dict[str, str], dict]] = []
        _walk(series, 0, {}, leaves)
        if not leaves:
            raise RegistryError(f"{path}: no series entry carries all of {sorted(_LEAF_KEYS)}, so the data cannot be identified")
        select = sorted(set(selection[name]))
        out[name] = {
            "select": select,
            # The series subtree ONLY, and the WHOLE of it: the top level carries a `source` spelled two
            # ways for one directory and per-writer config knobs, and a slice-scoped digest could be
            # pinned nowhere (spec 00086 D1).
            "series_digest": compute_hash({"series": series}),
            "extent": _extent(_selected(leaves, select, path), path),
        }
    return out
```

Sorted-name order is for the in-memory object a caller inspects; `canonical_json` sorts the serialised form regardless.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_registry_provenance.py -q`
Expected: PASS, with the real-dataset cases **running, not skipping** (`data/` is present on the research machine — those parametrisations are the check that the design admits all four manifest shapes and that the slice resolution reproduces the crossfreq table's numbers).

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a
git add cli/registry/provenance.py tests/test_registry_provenance.py
git commit -m "feat(registry): capture a dataset's provenance from its manifest, whatever shape it is"
```

---

### Task 2: Schema 4 — the store-owned split, the load-time invariant, and the writer, in one commit

**Files:**

- Modify: `cli/registry/record.py` (`SCHEMA_VERSION`, `_LOADABLE_SCHEMA_VERSIONS`, the `_STORE_OWNED` split, `_REQUIRED_CALLER`, `_EXPECTED_STORED_KEYS`, `validate_caller_fields`, `validate_stored_record`, `_validate_datasets_block`, `TrialRecord`)
- Modify: `cli/registry/store.py` (`_to_record` and `TrialRegistry.append`)
- Modify: `tests/test_registry_record.py`
- Modify: `tests/test_registry_store.py`
- Modify: `tests/test_trial_registry_provenance.py` (its module-local `_caller()` only — see Step 1)

**Interfaces:**

- Produces: `SCHEMA_VERSION = 4`; `TrialRecord.datasets: dict | None = None`; `dataset_hash` and `datasets` store-owned; `validate_stored_record` enforcing `compute_hash(rec["datasets"]) == rec["dataset_hash"]` for schema ≥ 4; `append(*, ..., datasets: dict[str, list[str]], ...)` with no `dataset_hash` and no `data_root` parameter.
- Consumes: `capture_datasets`, `DATA_ROOT` (Task 1).

- [ ] **Step 1: Fix every existing test the schema bump touches**

Mechanical, and it must be complete before anything else — an unlisted file here is a red suite at commit time and a refused `mutate-probe.sh` in Task 5. The full list, each verified against the current file:

`tests/test_registry_record.py`

- `_caller()` **drops** `dataset_hash="d"` (a caller may no longer supply it).
- `test_constants` asserts `SCHEMA_VERSION == 4`.
- `test_invalid_caller_rejected`'s parametrisation gains `{"dataset_hash": "d"}` and `{"datasets": {}}` — both are store-owned now.
- Three stored-record tests build bodies from `_caller()` with `schema_version=SCHEMA_VERSION` and assert they VALIDATE. All three are **pre-4 compatibility** tests, so each gains an explicit `dataset_hash="d"` and pins `schema_version=3` **literally**: `test_stored_record_hash_and_schema_checks`, `test_stored_record_schema_version_variant_compat` (both `body_v2` — which pins 2 already but still needs `dataset_hash` — and `body_v3`), and `test_stored_record_validation_stays_lenient_about_run_ref`.
- Imports gain `_LOADABLE_SCHEMA_VERSIONS` from `cli.registry.record` and `Path` from `pathlib`.

`tests/test_registry_store.py`

- `_line()` pins `schema_version=3` literally (it exercises chain/contiguity mechanics, not schema 4) and keeps `dataset_hash="d"`. `_line_v2()` is untouched.
- Four more bodies pin `schema_version=SCHEMA_VERSION` and expect a pre-4 outcome — pin each literally to `3`: `test_v3_record_with_nonstr_variant_is_corruption`, `test_v3_unknown_key_forge_is_corruption`, `test_missing_base_key_is_corruption`, `test_v3_without_variant_still_loads`.
- The module-level helper `_append(reg, **over)` is where ~20 call sites reach `append()`: drop `dataset_hash="d"` from its `kw` dict and add `datasets={"ohlc-x": ["1440"]}`. No call site changes, and no `data_root` is threaded anywhere — `append()` has no such parameter (Step 4).
- `test_append_requires_run_ref_explicitly` calls `reg.append(...)` directly: swap its `dataset_hash="d"` for `datasets={"ohlc-x": []}`.
- Rename `test_mixed_v2_and_v3_file_loads_with_intact_chain` → `test_mixed_v2_and_v4_file_loads_with_intact_chain`; its appended record is now schema 4 and the `SCHEMA_VERSION` assertions in it stay correct unchanged.
- Imports gain `inspect` and `from cli.registry import store`.
- Add the autouse data-root fixture, which is what lets every existing `_append` call keep working:

```python
@pytest.fixture(autouse=True)
def _stub_data_root(tmp_path, monkeypatch):
    """append() reads a module constant, not an argument (spec 00086 D4). Point it at a two-series stub
    so every append test exercises the REAL capture path without needing the gitignored data/ tree."""
    root = tmp_path / "data"
    (root / "ohlc-x").mkdir(parents=True)
    (root / "ohlc-x" / "manifest.json").write_text(
        json.dumps({"fetched_at": "2026-07-07T00:00:00+00:00", "series": {"BTC/EUR": {
            "1440": {"rows": 10, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-10T00:00:00+00:00", "sha256": "c" * 64},
            "240": {"rows": 20, "first_ts": "2020-01-01T04:00:00+00:00", "last_ts": "2020-01-10T20:00:00+00:00", "sha256": "d" * 64}}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(store, "DATA_ROOT", root)
    return root
```

`tests/test_trial_registry_provenance.py`

- Its **module-local** `_caller()` (the one near the bottom, beside `test_both_layers_agree_on_path_spelling`) supplies `dataset_hash="d"` and the test calls `validate_caller_fields(_caller(run_ref=spelling))` expecting no raise. Drop `dataset_hash="d"` from it. Nothing else in that file changes in this task.

- [ ] **Step 2: Write the new failing tests**

In `tests/test_registry_record.py`:

```python
_BLOCK = {
    "ohlc-x": {
        "select": ["1440"],
        "series_digest": "a" * 64,
        "extent": {"series": 1, "rows": 10, "span": ["2020-01-01T00:00:00+00:00", "2020-01-10T00:00:00+00:00"]},
    }
}


def _v4_body(**over):
    body = dict(
        _caller(),
        trial_id=1,
        schema_version=4,
        timestamp="2026-07-07T00:00:00+00:00",
        prev_hash=GENESIS_HASH,
        run_ref=None,
        notes="",
        datasets=_BLOCK,
    )
    body["dataset_hash"] = compute_hash(body["datasets"])
    body.update(over)
    return dict(body, record_hash=compute_hash(body))


def test_a_schema_four_record_round_trips():
    validate_stored_record(_v4_body(), "x")


def test_schema_four_dataset_hash_must_equal_compute_hash_of_the_block():
    # The load-time invariant: a record cannot claim a digest it did not derive from its own block.
    with pytest.raises(RegistryCorruptionError, match="dataset_hash"):
        validate_stored_record(_v4_body(dataset_hash="d" * 64), "x")


def test_schema_four_requires_a_datasets_block():
    body = _v4_body()
    del body["record_hash"], body["datasets"]
    with pytest.raises(RegistryCorruptionError, match="datasets"):
        validate_stored_record(dict(body, record_hash=compute_hash(body)), "x")


@pytest.mark.parametrize(
    "block",
    [
        {},  # empty -- and capture refuses to produce it, so append can never write this line
        {"ohlc-x": "not-a-dict"},
        {"ohlc-x": {"select": [], "series_digest": "short", "extent": {}}},
        {"ohlc-x": {"select": [], "series_digest": "a" * 64}},  # no extent
        {"ohlc-x": {"series_digest": "a" * 64, "extent": {}}},  # no select
        {"ohlc-x": {"select": [], "series_digest": "a" * 64, "extent": {"series": 1, "rows": 10}}},  # no span
        {"ohlc-x": {"select": [], "series_digest": "a" * 64,
                    "extent": {"series": 1, "rows": "10", "span": ["a", "b"]}}},  # rows not an int
    ],
)
def test_a_malformed_datasets_block_is_corruption(block):
    with pytest.raises(RegistryCorruptionError):
        validate_stored_record(_v4_body(datasets=block, dataset_hash=compute_hash(block)), "x")


def test_pre_schema_four_records_still_load_and_carry_no_block():
    assert {2, 3, 4} <= _LOADABLE_SCHEMA_VERSIONS
    for version in (2, 3):
        body = dict(
            _caller(),
            trial_id=1,
            schema_version=version,
            timestamp="2026-07-07T00:00:00+00:00",
            prev_hash=GENESIS_HASH,
            dataset_hash="d",
            run_ref=None,
            notes="",
        )
        validate_stored_record(dict(body, record_hash=compute_hash(body)), "x")


def test_a_pre_four_record_carrying_a_datasets_block_is_corruption():
    body = dict(
        _caller(),
        trial_id=1,
        schema_version=3,
        timestamp="2026-07-07T00:00:00+00:00",
        prev_hash=GENESIS_HASH,
        dataset_hash="d",
        run_ref=None,
        notes="",
        datasets=_BLOCK,
    )
    with pytest.raises(RegistryCorruptionError):
        validate_stored_record(dict(body, record_hash=compute_hash(body)), "x")


def test_the_committed_registry_still_loads_record_by_record():
    # The whole point of the store-owned split: 46 live records, one of which the deployable depends on.
    path = Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl"
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 46
    for i, line in enumerate(lines, start=1):
        validate_stored_record(loads_strict(line), f"line {i}")
```

In `tests/test_registry_store.py`:

```python
def test_append_derives_the_dataset_hash_from_the_captured_block(tmp_path):
    r = _append(_new_registry(tmp_path))
    assert r.schema_version == 4
    assert r.dataset_hash == compute_hash(r.datasets)
    assert r.datasets["ohlc-x"] == {
        "select": ["1440"],
        "series_digest": r.datasets["ohlc-x"]["series_digest"],
        "extent": {"series": 1, "rows": 10, "span": ["2020-01-01T00:00:00+00:00", "2020-01-10T00:00:00+00:00"]},
    }
    assert TrialRegistry(tmp_path / "t.jsonl").records[0] == r  # survives write -> read -> re-validate


def test_the_recorded_extent_is_the_declared_slice_not_the_whole_set(tmp_path):
    # The stub manifest carries two intervals; the default _append declares only 1440.
    whole = _append(_new_registry(tmp_path), datasets={"ohlc-x": []})
    assert whole.datasets["ohlc-x"]["extent"]["rows"] == 30
    sliced = _append(_new_registry(tmp_path), datasets={"ohlc-x": ["240"]}, n_trials_in_family=3)
    assert sliced.datasets["ohlc-x"]["extent"]["rows"] == 20
    assert sliced.dataset_hash != whole.dataset_hash  # two different reads, two different digests


def test_append_offers_no_argument_for_the_digest_or_the_data_root(tmp_path):
    # The structural fix: not "validated", ABSENT. A caller can express neither a wrong provenance nor
    # a root to read it from.
    params = inspect.signature(TrialRegistry.append).parameters
    assert "dataset_hash" not in params and "data_root" not in params
    with pytest.raises(TypeError):
        _append(_new_registry(tmp_path), dataset_hash="deadbeef")


def test_append_normalises_the_selected_slice(tmp_path):
    r = _append(_new_registry(tmp_path), datasets={"ohlc-x": ["240", "1440", "1440"]})
    assert r.datasets["ohlc-x"]["select"] == ["1440", "240"]


def test_append_refuses_an_empty_datasets_block_before_writing(tmp_path):
    # The unloadable-line case: validate_stored_record rejects an empty datasets dict, the file is
    # append-only, so a line written this way could never be read or removed again. It must never reach
    # the file -- and, since append() does not re-validate what it writes, the refusal has to be capture's.
    p = tmp_path / "t.jsonl"
    with pytest.raises(RegistryError, match="at least one dataset"):
        _append(TrialRegistry(p), datasets={})
    assert not p.exists() or p.read_text() == ""


def test_append_refuses_a_dataset_that_is_not_on_disk(tmp_path):
    p = tmp_path / "t.jsonl"
    with pytest.raises(RegistryError, match="manifest"):
        _append(TrialRegistry(p), datasets={"ohlc-absent": []})
    assert not p.exists() or p.read_text() == ""  # refused BEFORE the file was opened


def test_append_refuses_an_unknown_select_token_before_writing(tmp_path):
    p = tmp_path / "t.jsonl"
    with pytest.raises(RegistryError, match="1441"):
        _append(TrialRegistry(p), datasets={"ohlc-x": ["1441"]})
    assert not p.exists() or p.read_text() == ""
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/test_registry_record.py tests/test_registry_store.py -q`
Expected: FAIL — `SCHEMA_VERSION` is 3, `datasets` is an unknown key, `append` still takes `dataset_hash`, no round-trip check exists.

- [ ] **Step 4: Implement `cli/registry/record.py`**

Constants — the split is the load-bearing part (D2):

```python
SCHEMA_VERSION = 4
_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4})

# Store-owned in EVERY version: these feed _BASE_STORED_KEYS, required of every record at every version.
# dataset_hash belongs here -- every record since schema 2 carries the key; only its OWNER changes.
_STORE_OWNED_ALWAYS = ("trial_id", "schema_version", "timestamp", "prev_hash", "record_hash", "dataset_hash")
# Store-owned but schema-4 only: version-scoped in _EXPECTED_STORED_KEYS, exactly as `variant` is.
# It must NOT reach _BASE_STORED_KEYS or all 46 committed records fail the missing-key check.
_STORE_OWNED_V4 = ("datasets",)
_STORE_OWNED = _STORE_OWNED_ALWAYS + _STORE_OWNED_V4
_REQUIRED_CALLER = ("iteration", "family", "spec_hash", "seeds", "metrics", "n_trials_in_family", "verdict")

_BASE_STORED_KEYS = frozenset(_STORE_OWNED_ALWAYS) | frozenset(_REQUIRED_CALLER) | {"run_ref", "notes"}
_EXPECTED_STORED_KEYS = {
    2: _BASE_STORED_KEYS,
    3: _BASE_STORED_KEYS | {"variant"},
    4: _BASE_STORED_KEYS | {"variant", "datasets"},
}
```

`validate_caller_fields`: drop `"dataset_hash"` from the `for key in ("iteration", "family", "spec_hash", "dataset_hash")` non-empty-str loop. Nothing else changes there — the existing `supplied_owned` check now rejects a caller passing `dataset_hash` or `datasets`, and the existing `missing` check no longer demands `dataset_hash`.

`validate_stored_record`: insert after the `variant` checks and before the `record_hash` check —

```python
    if type(rec.get("dataset_hash")) is not str or not rec["dataset_hash"]:
        raise RegistryCorruptionError(f"{where}: dataset_hash must be a non-empty str")
    if version >= 4:
        _validate_datasets_block(rec.get("datasets"), where)
        if compute_hash(rec["datasets"]) != rec["dataset_hash"]:
            raise RegistryCorruptionError(f"{where}: dataset_hash is not compute_hash(datasets)")
```

and the module-level helper:

```python
def _validate_datasets_block(block, where: str) -> None:
    """Every shape `capture_datasets` can produce, and nothing wider.

    Each rejection here is a line that could never be loaded or removed again, so capture refuses the
    same cases first — the empty block above all (spec 00086 D3/D4). Do not add a check here without
    the matching capture-time refusal.
    """
    if type(block) is not dict or not block:
        raise RegistryCorruptionError(f"{where}: schema_version 4 record must carry a non-empty datasets dict")
    for name, entry in block.items():
        if type(entry) is not dict:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}] must be a dict")
        if type(entry.get("series_digest")) is not str or len(entry["series_digest"]) != 64:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}].series_digest must be a 64-char str")
        if type(entry.get("select")) is not list:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}].select must be a list")
        extent = entry.get("extent")
        if type(extent) is not dict or type(extent.get("series")) is not int or type(extent.get("rows")) is not int:
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}].extent must carry an int series and an int rows")
        span = extent.get("span")
        if type(span) is not list or len(span) != 2 or any(type(s) is not str for s in span):
            raise RegistryCorruptionError(f"{where}: datasets[{name!r}].extent.span must be a two-element list of str")
```

`TrialRecord`: add `datasets: dict | None = None`, with a docstring line saying it is schema-4+ and that pre-4 records legitimately carry `None`.

**Then implement `cli/registry/store.py` in the same commit.** `_to_record` gains `datasets=rec.get("datasets")`. `TrialRegistry.append` replaces its `dataset_hash: str` parameter with `datasets: dict[str, list[str]]`, adds no other parameter, and imports `DATA_ROOT`/`capture_datasets` from `cli.registry.provenance` (module-level `DATA_ROOT` so the test fixture can point it at a stub). Build `caller` **without** either store-owned key, then capture after `validate_caller_fields(caller)` and before the lock — a refusal must land before the file is opened, exactly as the non-finite-metric check already does:

```python
        validate_caller_fields(caller)  # raises on non-finite metric BEFORE opening the file
        captured = capture_datasets(datasets, DATA_ROOT)  # ...and refuses unverifiable provenance here
        lock_f = open(self.path, "a", encoding="utf-8")
```

and add both keys beside the other store-owned fields in the record body:

```python
            rec = {
                **caller,
                "trial_id": next_id,
                "schema_version": SCHEMA_VERSION,
                "timestamp": _now_utc_iso(),
                "datasets": captured,
                "dataset_hash": compute_hash(captured),
                "prev_hash": prev_hash,
            }
```

`record_hash` chaining, locking, healing and `_assert_cross_record` are untouched. Update the `TrialRegistry` class docstring's "loads schema v2+v3, writes v3" clause to v2+v3+v4 / writes v4.

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_registry_record.py tests/test_registry_store.py -q`
Expected: PASS.

- [ ] **Step 6: Prove the live registry and its runtime reader are intact**

Run: `uv run pytest tests/test_registry_record.py tests/test_registry_store.py tests/test_trial_registry_provenance.py tests/test_portfolio_builder.py tests/test_record44_legs.py -q`
Expected: PASS. These load the real 46-record file. Diagnose by which assertion fires, not by the file: a *missing required key* red means `datasets` leaked into `_BASE_STORED_KEYS`; an *unknown key* red means the `4:` entry is missing from `_EXPECTED_STORED_KEYS`; a *store-owned field* red in `test_trial_registry_provenance.py` means its module-local `_caller()` still supplies `dataset_hash` (Step 1).

- [ ] **Step 7: Commit**

```bash
uv run pre-commit run -a
git add cli/registry/record.py cli/registry/store.py tests/test_registry_record.py tests/test_registry_store.py tests/test_trial_registry_provenance.py
git commit -m "feat(registry): schema 4 derives dataset_hash from a captured datasets block"
```

---

### Task 3: Layer 2 — re-derive from disk, re-count and re-hash the bytes, fall back to the committed pins

Without this the load-time check is self-referential: a hand-writer who invents a block and calls `compute_hash` on it satisfies D3 forever, and a hand-written record is the normal case (D3/D5). Three things carry the layer and each answers a specific way the earlier design was hollow:

- **Capture reads `manifest.json` and nothing else**, so on the machine that wrote the record a re-derivation compares a manifest to itself. The bytes checks are what make it a measurement: the parquet row counts must sum to the manifest's whole-set `rows`, and every vouched `sha256` must be reproduced by a parquet.
- **A manifest that vouches no `sha256` at all** would otherwise opt itself out of the only bytes-touching hash check, invisibly. That is now a finding unless the name is in a frozen, both-direction-asserted allowlist — one member today.
- **Four verdicts, not two.** "Not on this machine" and "refreshed since the record was written" must never be scored as "forged", or the first trial registered against a set another node lacks — or the first rebuild of `ohlc-full` — reds the suite permanently with no in-design remedy.

**Files:**

- Modify: `tests/test_trial_registry_provenance.py`
- Modify: `docs/reference/data-catalog-full.md` (the committed `series_digest` pin lists the fallbacks read)

**Interfaces:**

- Produces: `MANIFEST_VOUCHES_NO_BYTES: frozenset[str]`; `_catalog_pins(name, catalog) -> list[str]`; `_captured(data_root, name, select) -> tuple[dict | None, str | None]`; `_derived(dataset_dir) -> tuple[frozenset[str], int]`; `_vouched_sha256s(node) -> set[str]`; `_bytes_findings(name, data_root) -> list[str]`; `_provenance_findings(records, catalog, data_root) -> tuple[dict[int, list[str]], dict[tuple[int, str], str]]`; six tests.
- Consumes: `capture_datasets`, `DATA_ROOT` (Task 1); schema 4 (Task 2); `cli.ohlc.dataset.dataset_hash` / `read_parquet` / `write_parquet`; `polars` (test-side only, to build the constructed dataset root).

- [ ] **Step 1: Pin each canonical dataset's `series_digest` in the catalog**

`docs/reference/data-catalog-full.md`, four sections, one sentence appended to the line that already carries that set's `Dataset root …` (so the pin sits with the identity it belongs to). **The digest must follow the label immediately** — the pins are read by `` `series_digest` `<64 hex>` `` inside the set's own `### \`name\`` section, so any prose between the two breaks the parse (verified against the real file: the parenthetical goes *after* the digest, never between).

- `### \`ohlc-full\`` → ``` `series_digest` `76edb3a0633a5ab5f9f2c6f9d7b3af4d2000c1aaab22c69da0e278cbe88eafb0` (the registry's provenance pin over the manifest's `series` subtree, spec `00086`). ```
- `### \`ohlc-15m\`` → same wording, digest `cc57da1ff6c48ea6f0b6da5dd70dfbb33b9167f852d44dd0b927e16987239937`.
- `### \`derivatives-funding\`` → same wording, digest `034809ebbd838a786075b50d774cc0b85cdbb6b89d22526e44994d3726ef3a4b`.
- `### \`ohlc-holdout-2026-07-10\`` → same wording, digest `de5b2771579104c711550035d1f2beb371fad5038e84f2203b07df94cc26186f`.

All four were measured this session with the registry's own `compute_hash` over `{"series": manifest["series"]}`.

Add one sentence to the `## hot` preamble stating the rule the pins live by, because the pin is **a list, current first**:

> A set's `series_digest` pins are read in document order and the **first** one in its section must be the digest the data on disk produces today. A rebuild that moves it replaces that first pin in the same change and appends the old value below it on its own line — the plain word Superseded, then the same `series_digest`-plus-64-hex code-span pair, then a parenthetical naming the rebuild that retired it. Trial records written against the old bytes are append-only and can never be edited, so their digests must stay findable here or they become permanently unverifiable.

Only the `` `series_digest` `<hex>` `` pair is parsed; the surrounding words are for the reader, and **document order** is what distinguishes current from superseded.

`derivatives-oi` and `ohlc-reach` are documented but not on this machine, so they get no pin now and none is invented; the first record naming one of them adds it, and the layer's failure message says so.

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_trial_registry_provenance.py` (its imports gain `functools`, `re`, `pytest`, `polars as pl`, `RegistryError`, `DATA_ROOT`/`capture_datasets`, and `dataset_hash`/`read_parquet`/`write_parquet` from `cli.ohlc.dataset`), and extend the module docstring's two-layer paragraph to say the same split now guards `datasets`. Write the tests **without** the helpers they call, so the red is real:

```python
CATALOG = REPO / "docs" / "reference" / "data-catalog-full.md"
CATALOG_PINNED = ("ohlc-full", "ohlc-15m", "derivatives-funding", "ohlc-holdout-2026-07-10")

# A manifest that vouches NO per-series sha256 opts itself out of the only check that reaches past the
# manifest to the bytes' content -- and it does so invisibly, because from here it looks exactly like one
# that vouches them. So it is a finding, and this frozen allowlist is the only exemption. Same both-
# direction discipline as LEGACY_UNCOMMITTED above: every member must genuinely vouch nothing today, and
# nothing outside it may. The holdout is [[T0064]]'s out-of-sample set, written by a driver that was never
# committed; when a committed writer replaces it, the entry comes out.
MANIFEST_VOUCHES_NO_BYTES = frozenset({"ohlc-holdout-2026-07-10"})


def _build_dataset(root, name, rows, *, vouch=True, parquet_rows=None):
    """A minimal but REAL dataset under `root`: a manifest plus a parquet whose bytes the checks read.

    `parquet_rows` fewer than `rows` constructs the manifest-claims-more-than-the-bytes failure;
    `vouch=False` constructs the manifest-vouches-nothing case. Building a root instead of mutating
    data/ is deliberate -- data/ is gitignored, so nothing there can be restored after a test.
    """
    frame = pl.DataFrame({"ts": list(range(rows)), "close": [float(i) for i in range(rows)]})
    write_parquet(frame.head(rows if parquet_rows is None else parquet_rows), root / name / "s.parquet")
    leaf = {"rows": rows, "first_ts": "2020-01-01T00:00:00+00:00", "last_ts": "2020-01-02T00:00:00+00:00"}
    if vouch:
        leaf["sha256"] = dataset_hash(frame)
    (root / name / "manifest.json").write_text(json.dumps({"series": {"S": leaf}}), encoding="utf-8")


def _one_record_verdicts(root, name):
    """Capture `name` whole from `root`, put it in one schema-4 record, and run the layer over it."""
    block = capture_datasets({name: []}, root)
    return _provenance_findings([{"trial_id": 1, "schema_version": 4, "datasets": block}], "", root)


def test_no_schema_four_record_disagrees_with_the_provenance_it_can_be_checked_against():
    # Layer 2. The load-time check proves a record is internally consistent; only this one compares the
    # block to what is on disk -- and, where the dataset is absent or has been refreshed, to the
    # committed catalog pins. Never widen the check to make a red go away: a genuine refresh is recorded
    # by appending the superseded digest to that set's catalog section, which is reviewable and loud.
    findings, _verdicts = _provenance_findings(_records(), CATALOG.read_text(encoding="utf-8"), DATA_ROOT)
    assert findings == {}, f"provenance findings: {findings}"


def test_the_catalog_pins_the_current_series_digest_of_every_canonical_dataset_present_here():
    # Keeps the fallback honest: a pin nobody checks rots into a number that once was true. The FIRST pin
    # must be today's digest -- that is what stops the superseded tail from being used to hide live drift.
    catalog = CATALOG.read_text(encoding="utf-8")
    checked = 0
    for name in CATALOG_PINNED:
        if not (DATA_ROOT / name / "manifest.json").is_file():
            continue
        pins = _catalog_pins(name, catalog)
        assert pins, name
        assert pins[0] == capture_datasets({name: []}, DATA_ROOT)[name]["series_digest"], name
        assert len(set(pins)) == len(pins), name  # a superseded entry equal to the current one pins nothing
        checked += 1
    if not (DATA_ROOT / "ohlc-full" / "manifest.json").is_file():
        pytest.skip("compiled datasets absent")
    assert checked >= 1


@pytest.mark.skipif(not (DATA_ROOT / "ohlc-full" / "manifest.json").is_file(), reason="compiled datasets absent")
def test_the_vouches_no_bytes_allowlist_is_frozen_and_asserted_both_ways():
    vouchless = set()
    for name in CATALOG_PINNED:
        manifest = DATA_ROOT / name / "manifest.json"
        if not manifest.is_file():
            continue
        if not _vouched_sha256s(json.loads(manifest.read_text(encoding="utf-8"))["series"]):
            vouchless.add(name)
    assert vouchless == set(MANIFEST_VOUCHES_NO_BYTES), (
        "the allowlist must name exactly the sets that genuinely vouch no per-series sha256 today: a "
        "member that gained digests must be removed, and a set that lost them is a writer regression."
    )


@pytest.mark.skipif(not (DATA_ROOT / "ohlc-full" / "manifest.json").is_file(), reason="compiled datasets absent")
def test_the_real_dataset_bytes_match_what_its_manifest_says():
    # The link past the manifest to the bytes, over real data: every vouched hash reproduced, and the row
    # count re-measured rather than taken from the manifest that asserted it.
    manifest = json.loads((DATA_ROOT / "ohlc-full" / "manifest.json").read_text(encoding="utf-8"))
    hashes, rows = _derived(DATA_ROOT / "ohlc-full")
    assert len(hashes) == 36
    assert _vouched_sha256s(manifest["series"]) <= hashes
    assert rows == capture_datasets({"ohlc-full": []}, DATA_ROOT)["ohlc-full"]["extent"]["rows"] == 1052322


@pytest.mark.skipif(not (DATA_ROOT / "ohlc-full" / "manifest.json").is_file(), reason="compiled datasets absent")
def test_the_provenance_check_bites_before_any_schema_four_record_exists():
    # Constructive proof, in the same shape as the run_ref one above: the standing assertion is vacuous
    # until the first schema-4 record lands, and a vacuous guard is a decoration.
    catalog = CATALOG.read_text(encoding="utf-8")
    honest = capture_datasets({"ohlc-full": ["1440"]}, DATA_ROOT)

    def _findings(trial_id, block, cat=catalog):
        return _provenance_findings([{"trial_id": trial_id, "schema_version": 4, "datasets": block}], cat, DATA_ROOT)

    assert _findings(900, honest) == ({}, {(900, "ohlc-full"): "rederived"})

    forged = {"ohlc-full": {**honest["ohlc-full"], "series_digest": "0" * 64}}
    assert set(_findings(901, forged)[0]) == {901}

    inflated = {"ohlc-full": {**honest["ohlc-full"], "extent": {**honest["ohlc-full"]["extent"], "rows": 1}}}
    assert set(_findings(902, inflated)[0]) == {902}

    invented = {"ohlc-nowhere": {"select": [], "series_digest": "0" * 64, "extent": {}}}
    assert set(_findings(903, invented)[0]) == {903}  # absent here AND pinned nowhere

    # ...but absent-and-pinned is normal, never a finding: a node that has not fetched a set
    # (derivatives-oi is exactly that today) must not red this suite.
    elsewhere = {"ohlc-elsewhere": honest["ohlc-full"]}
    pinned = "### `ohlc-elsewhere`\n\n`series_digest` `%s`\n" % honest["ohlc-full"]["series_digest"]
    assert _findings(904, elsewhere, pinned) == ({}, {(904, "ohlc-elsewhere"): "absent-here"})

    # ...and a pre-4 record is out of scope for this layer, not silently "passing" it.
    assert _provenance_findings(_records(), catalog, DATA_ROOT) == ({}, {})


def test_a_refreshed_dataset_is_superseded_rather_than_permanently_red(tmp_path):
    # THE decay path the design names for itself. The registry is append-only, so a record written before
    # a rebuild can never be repaired; the catalog's superseded pin is what makes that recordable, and the
    # ONLY thing it excuses is a digest someone wrote down there deliberately.
    _build_dataset(tmp_path, "d", 10)
    current = capture_datasets({"d": []}, tmp_path)["d"]
    catalog = "### `d`\n\n`series_digest` `%s`\n\nSuperseded `series_digest` `%s` (retired by a rebuild).\n" % (
        current["series_digest"], "9" * 64)
    assert _catalog_pins("d", catalog) == [current["series_digest"], "9" * 64]

    stale = [{"trial_id": 7, "schema_version": 4, "datasets": {"d": dict(current, series_digest="9" * 64)}}]
    assert _provenance_findings(stale, catalog, tmp_path) == ({}, {(7, "d"): "superseded"})

    drifted = [{"trial_id": 8, "schema_version": 4, "datasets": {"d": dict(current, series_digest="8" * 64)}}]
    assert set(_provenance_findings(drifted, catalog, tmp_path)[0]) == {8}  # pinned nowhere: still a finding


def test_the_bytes_checks_bite_against_a_constructed_dataset_root(tmp_path):
    # Each case is a real dataset root this test writes, because the checks read bytes and data/ is
    # gitignored -- there is nothing there a probe or a test could safely mutate and restore.
    _build_dataset(tmp_path / "honest", "d", 10)
    assert _one_record_verdicts(tmp_path / "honest", "d") == ({}, {(1, "d"): "rederived"})

    # the manifest claims a row the parquet does not hold: what grounds `extent` in bytes
    _build_dataset(tmp_path / "short", "d", 10, parquet_rows=9)
    assert any("the parquet on disk hold 9" in r for r in _one_record_verdicts(tmp_path / "short", "d")[0][1])

    # a vouched hash no parquet reproduces
    _build_dataset(tmp_path / "forged", "d", 10)
    manifest = tmp_path / "forged" / "d" / "manifest.json"
    tampered = json.loads(manifest.read_text(encoding="utf-8"))
    tampered["series"]["S"]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(tampered), encoding="utf-8")
    assert any("reproduced by no parquet" in r for r in _one_record_verdicts(tmp_path / "forged", "d")[0][1])

    # a manifest that vouches nothing: the escape hatch that must be loud rather than silent
    _build_dataset(tmp_path / "silent", "d", 10, vouch=False)
    assert any("vouches no per-series sha256" in r for r in _one_record_verdicts(tmp_path / "silent", "d")[0][1])

    # ...and the one allowlisted name that legitimately vouches nothing
    allowed = next(iter(MANIFEST_VOUCHES_NO_BYTES))
    _build_dataset(tmp_path / "allowed", allowed, 10, vouch=False)
    assert _one_record_verdicts(tmp_path / "allowed", allowed) == ({}, {(1, allowed): "rederived"})

    # the allowlist exempts the HASH half only -- the row count still binds that set to its bytes
    _build_dataset(tmp_path / "allowed-short", allowed, 10, vouch=False, parquet_rows=9)
    findings = _one_record_verdicts(tmp_path / "allowed-short", allowed)[0][1]
    assert len(findings) == 1 and "the parquet on disk hold 9" in findings[0]
```

- [ ] **Step 3: Run to verify they fail**

Run: `uv run pytest tests/test_trial_registry_provenance.py -q`
Expected: FAIL — `NameError` on `_provenance_findings`, `_catalog_pins`, `_vouched_sha256s`, `_derived`, `_build_dataset` in the new tests, and every pre-existing test in the file still PASSES.

- [ ] **Step 4: Implement the helpers**

```python
def _catalog_pins(name: str, catalog: str) -> list[str]:
    """The `series_digest` values the catalog pins for `name`, in document order, from that set's own
    section. The FIRST is the current one; anything after it is a superseded value kept beside it so a
    record written before that rebuild stays checkable — the registry is append-only and cannot be
    repaired (spec 00086 D5)."""
    head = f"### `{name}`"
    if head not in catalog:
        return []
    section = catalog.split(head, 1)[1].split("\n### ", 1)[0]
    return re.findall(r"`series_digest` `([0-9a-f]{64})`", section)


@functools.cache
def _captured(data_root: Path, name: str, select: tuple[str, ...]) -> tuple[dict | None, str | None]:
    """`(block, None)` or `(None, refusal)`. Cached because the registry is append-only and only grows:
    an un-memoised pass is O(records x dataset) and gets permanently slower with every trial registered.
    Pure within one test run — nothing here writes to `data_root`."""
    try:
        return capture_datasets({name: list(select)}, data_root)[name], None
    except RegistryError as e:
        return None, str(e)


@functools.cache
def _derived(dataset_dir: Path) -> tuple[frozenset[str], int]:
    """Every parquet's content hash under `dataset_dir`, and their total row count. ONE read of each
    frame yields both, which is why grounding `extent` in bytes costs nothing beyond the re-hash that was
    happening anyway. Same re-derivation cli/data/sync.py runs for newly transmitted files."""
    hashes: set[str] = set()
    rows = 0
    for path in sorted(dataset_dir.rglob("*.parquet")):
        frame = read_parquet(path)
        hashes.add(dataset_hash(frame))
        rows += frame.height
    return frozenset(hashes), rows


def _vouched_sha256s(node) -> set[str]:
    """Every per-series `sha256` the manifest vouches for. Key-exact, so a set that exposes none (the
    holdout) yields the empty set rather than sweeping up a manifest-level digest."""
    found: set[str] = set()
    if type(node) is dict:
        for key, value in node.items():
            if key == "sha256" and type(value) is str:
                found.add(value)
            else:
                found |= _vouched_sha256s(value)
    elif type(node) is list:
        for item in node:
            found |= _vouched_sha256s(item)
    return found


def _bytes_findings(name: str, data_root: Path) -> list[str]:
    """What the bytes under `data_root/name` say about its manifest. Empty list = they agree."""
    whole, refusal = _captured(data_root, name, ())
    if refusal:
        return [f"{name}: the manifest present here cannot be captured whole: {refusal}"]
    hashes, rows = _derived(data_root / name)
    out: list[str] = []
    if rows != whole["extent"]["rows"]:
        out.append(f"{name}: the manifest claims {whole['extent']['rows']} rows for the whole set, the parquet on disk hold {rows}")
    vouched = _vouched_sha256s(json.loads((data_root / name / "manifest.json").read_text(encoding="utf-8"))["series"])
    if not vouched:
        if name not in MANIFEST_VOUCHES_NO_BYTES:
            out.append(f"{name}: the manifest vouches no per-series sha256, so nothing links its contents to the bytes on disk")
    elif vouched - hashes:
        out.append(f"{name}: {len(vouched - hashes)} manifest-vouched sha256 reproduced by no parquet on disk")
    return out


def _provenance_findings(
    records: list[dict], catalog: str, data_root: Path
) -> tuple[dict[int, list[str]], dict[tuple[int, str], str]]:
    """Per schema-4 record-dataset pair, one of four verdicts (spec 00086 D5).

    Returns `(findings, verdicts)`. `findings` maps a trial id to the reasons its block disagrees with
    something checkable here. `verdicts` maps each pair that reached a NON-finding verdict to its name:
    `rederived` (matches the manifest and the bytes here), `absent-here` (not on this node; digest meets a
    catalog pin), `superseded` (present but refreshed since; digest meets a superseded pin).
    """
    findings: dict[int, list[str]] = {}
    verdicts: dict[tuple[int, str], str] = {}

    def _note(trial_id: int, reason: str) -> None:
        findings.setdefault(trial_id, []).append(reason)

    for rec in records:
        if rec.get("schema_version", 0) < 4:
            continue
        trial_id = rec["trial_id"]
        for name, entry in rec["datasets"].items():
            pins = _catalog_pins(name, catalog)
            if not (data_root / name / "manifest.json").is_file():
                if entry["series_digest"] in pins:
                    verdicts[(trial_id, name)] = "absent-here"
                else:
                    _note(trial_id, f"{name}: not present here, and its catalog section pins no {entry['series_digest']}")
                continue
            captured, refusal = _captured(data_root, name, tuple(entry["select"]))
            disagreement = refusal or (None if captured == entry else f"re-derives as {captured}, record carries {entry}")
            if disagreement:
                # A dataset refreshed after the record was written cannot be re-derived and never will be;
                # the catalog's superseded pin is the committed, reviewable record of that rebuild.
                if entry["series_digest"] in pins[1:]:
                    verdicts[(trial_id, name)] = "superseded"
                else:
                    _note(trial_id, f"{name}: {disagreement}")
                continue
            problems = _bytes_findings(name, data_root)
            for problem in problems:
                _note(trial_id, problem)
            if not problems:
                verdicts[(trial_id, name)] = "rederived"
    return findings, verdicts
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_trial_registry_provenance.py -q`
Expected: PASS with the new tests **running, not skipping**. A skip on the research machine means `DATA_ROOT` is wrong — fix that before proceeding, since a silently-skipped provenance guard is the failure class this whole change is about. Measured cost on this machine: the first record naming `ohlc-full` pays 0.52 s for the 36-file read-and-hash; every later record naming it pays ~0 (0.002 s for twenty). A run where that cost scales with the record count means `functools.cache` was dropped from `_derived`/`_captured`.

- [ ] **Step 6: Commit**

```bash
uv run pre-commit run -a
git add tests/test_trial_registry_provenance.py docs/reference/data-catalog-full.md
git commit -m "test(registry): re-derive every schema-4 datasets block from disk and pin each set's digest"
```

---

### Task 4: The legacy pins table, with evidence the tests execute

**Files:**

- Create: `docs/reference/legacy-dataset-pins.jsonl`
- Create: `tests/test_legacy_dataset_pins.py`

**Interfaces:**

- Produces: one line per distinct pre-schema-4 `dataset_hash`, keys `dataset_hash`, `records`, `referent`, `confidence`, `evidence`, `notes` (D6). **Every line starts with `{"dataset_hash": "` so a single pin is addressable by a line-anchored pattern** (Task 5 mutates one).
- Consumes: `capture_datasets`, `DATA_ROOT` (Task 1).

- [ ] **Step 1: Write the failing tests**

```python
import collections
import hashlib
import json
from pathlib import Path

from cli.registry.provenance import DATA_ROOT, capture_datasets

REPO = Path(__file__).resolve().parents[1]
PINS = REPO / "docs" / "reference" / "legacy-dataset-pins.jsonl"
REGISTRY = REPO / "docs" / "reference" / "trial-registry.jsonl"


def _pins():
    return [json.loads(line) for line in PINS.read_text(encoding="utf-8").splitlines() if line.strip()]


def _historical():
    records = [json.loads(line) for line in REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in records if r["schema_version"] < 4]


def test_every_pre_schema_four_dataset_hash_is_pinned():
    # Regression protection, not completeness by construction: the historical set is frozen at four the
    # moment SCHEMA_VERSION is 4, so this asserts over constants and is worth exactly that.
    historical = {r["dataset_hash"] for r in _historical()}
    unpinned = historical - {p["dataset_hash"] for p in _pins()}
    assert not unpinned, f"unpinned: {sorted(unpinned)}"
    assert len(historical) == 4


def test_the_table_pins_nothing_that_is_not_in_the_registry():
    assert {p["dataset_hash"] for p in _pins()} <= {r["dataset_hash"] for r in _historical()}


def test_each_pin_names_exactly_the_records_it_stamps():
    stamped = collections.defaultdict(list)
    for r in _historical():
        stamped[r["dataset_hash"]].append(r["trial_id"])
    for pin in _pins():
        assert pin["records"] == sorted(stamped[pin["dataset_hash"]]), pin["dataset_hash"]
    assert sum(len(p["records"]) for p in _pins()) == 46


def test_every_pin_declares_a_known_confidence_and_a_referent():
    for pin in _pins():
        assert pin["confidence"] in {"inferred", "reproduced"}
        assert type(pin["referent"]) is list and pin["referent"]
        assert all(r.startswith("data/") for r in pin["referent"]), pin["referent"]
        assert pin["notes"]
        # `reproduced` is not a label to be written down: it means a recipe item exists and runs.
        has_recipe = any(item["kind"] == "recipe" for item in pin["evidence"])
        assert has_recipe is (pin["confidence"] == "reproduced"), pin["dataset_hash"]


def test_every_pin_carries_evidence_that_executes():
    # THE point of a file over prose: an `inferred` row states arithmetic, and arithmetic is checkable.
    # A referent rename or a re-freeze into a sibling must break this, not sit green under a label.
    ran = collections.Counter()
    for pin in _pins():
        assert pin["evidence"], pin["dataset_hash"]
        for item in pin["evidence"]:
            kind = item["kind"]
            if kind == "extent":
                if not (DATA_ROOT / item["dataset"] / "manifest.json").is_file():
                    ran["extent-skipped"] += 1
                    continue
                got = capture_datasets({item["dataset"]: item["select"]}, DATA_ROOT)[item["dataset"]]
                assert got["extent"] == item["extent"], (pin["dataset_hash"], item["dataset"])
                ran["extent"] += 1
            elif kind == "citation":
                assert item["literal"] in (REPO / item["path"]).read_text(encoding="utf-8"), item["path"]
                ran["citation"] += 1
            elif kind == "recipe":
                assert item["form"] == "sha256(a + ':' + b)", f"unknown recipe form {item['form']!r}"
                assert hashlib.sha256((item["a"] + ":" + item["b"]).encode()).hexdigest() == pin["dataset_hash"]
                ran["recipe"] += 1
            else:
                raise AssertionError(f"unknown evidence kind {kind!r} in pin {pin['dataset_hash']}")
    # The two data-free kinds must ALWAYS run -- an empty table would otherwise satisfy this test.
    assert ran["citation"] == 1 and ran["recipe"] == 1
    assert ran["extent"] + ran["extent-skipped"] == 2
    if (DATA_ROOT / "ohlc-full" / "manifest.json").is_file():
        assert ran["extent"] == 2
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_legacy_dataset_pins.py -q`
Expected: FAIL — the pins file does not exist.

- [ ] **Step 3: Write the four entries**

One JSON object per line, `dataset_hash` first, no trailing spaces (mdformat does not touch `.jsonl`; the whitespace hooks do). The `EUR10` shorthand below is the literal list `["ADA/EUR", "AVAX/EUR", "BTC/EUR", "DOGE/EUR", "DOT/EUR", "ETH/EUR", "LINK/EUR", "LTC/EUR", "SOL/EUR", "XRP/EUR"]`, written out in full in each `select` — no shorthand survives into the file.

- `ba47e37e2601d6098fd13c0e338a5301e8eeebb16bb4341c76a68147c7b08e42`
  - `records`: `[1, 2, … 35, 40, 41, 42]` (38 ids: 1–35 contiguous, then 40, 41, 42).
  - `referent`: `["data/ohlc-full"]`; `confidence`: `"inferred"`.
  - `evidence`: one `extent` item — `{"kind": "extent", "dataset": "ohlc-full", "select": EUR10 + ["1440"], "extent": {"series": 10, "rows": 29032, "span": ["2013-09-10T00:00:00+00:00", "2026-03-31T00:00:00+00:00"]}}`.
  - `notes` must say in its own words: this is **identification by extent, not verification by digest** — an arithmetic match plus an exclusion, never a recomputation; record 1's own `run_ref` (`docs/research/06.phase4-a1-results.md`) headlines "full history 2013→2026, 4581 returns", and 4582 daily union stamps yield 4581 returns (`UNION_BARS = {1440: 4582, 240: 27338}`, pinned in `tests/test_record44_legs.py`); the only alternative daily dataset — the v0 REST seed, retired 2026-07-18, 721 bars from 2024-07-17, zero per-series hash overlap — could not have produced a 2013→2026 walk-forward; and ~226,000 candidate recipes were tested without a match, on a method validated against two known targets.
- `81dc9b44f8897e38aacf78f00d3cffa12d54e724ccf0c9add0bced3fd5e1291f`
  - `records`: `[36, 37, 38, 39]`; `referent`: `["data/ohlc-full"]`; `confidence`: `"inferred"`.
  - `evidence`: one `citation` item — `{"kind": "citation", "path": "docs/specs/00045-b1-seasonality-conditioning-design.md", "literal": "81dc9b44f8897e38aacf78f00d3cffa12d54e724ccf0c9add0bced3fd5e1291f"}`. That spec names it verbatim as "**the literal trials-37–39 dataset hash**".
  - `notes`: it is the 4h primitive behind trials 36–39 and operand `a` of `cccb8d17`'s recipe, so it is reproducible **by citation** and never traced to bytes; the referent is `data/ohlc-full` **by exclusion** — the only 4h set that existed at iter-074, since `ohlc-reach` was first built 2026-07-23 — and **no extent evidence is claimed**, because nothing committed ties this hash to a row count and inventing one would manufacture the inference this table exists to prevent. Same ~226,000-candidate negative as above.
- `45275ebeb7986e3cca76e8ca8952f031256885e32b231fc782be0cd0d58871a7`
  - `records`: `[43, 44]`; `referent`: `["data/ohlc-full"]`; `confidence`: `"inferred"`.
  - `evidence`: one `extent` item — `{"kind": "extent", "dataset": "ohlc-full", "select": EUR10 + ["1440", "240"], "extent": {"series": 20, "rows": 202405, "span": ["2013-09-10T00:00:00+00:00", "2026-03-31T20:00:00+00:00"]}}`.
  - `notes` must state that `docs/research/12.phase5-system-spec-runbook.md` describes it as `sha256(daily ‖ 4h)` **semantically**, that ~100 concatenation forms of `ba47e37e` and `81dc9b44` were tested and none reproduces it, and that the dataset is nevertheless pinned by content: the extent above is exactly the sum of the frozen per-asset `EXTENT` table in `tests/test_crossfreq_system.py` (29,032 daily + 173,373 4h), which is where record 44's identity actually rests.
- `cccb8d175d2038c462de57b295e9eb53ee2d51278e4110accfa350d93ced68b9`
  - `records`: `[45, 46]`; `referent`: `["data/ohlc-full", "data/ohlc-15m"]` — **two roots, and the notes say which operand comes from which**: `a` is `data/ohlc-full`'s 4h primitive (`81dc9b44…`), `b` is `data/ohlc-15m`'s `basket_sha256` (`0fed24a6…`). A single-path referent here would be a false one.
  - `confidence`: `"reproduced"`.
  - `evidence`: one `recipe` item — `{"kind": "recipe", "form": "sha256(a + ':' + b)", "a": "81dc9b44f8897e38aacf78f00d3cffa12d54e724ccf0c9add0bced3fd5e1291f", "b": "0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de1"}`.
  - `notes`: it survived only because `docs/specs/00045-b1-seasonality-conditioning-design.md` wrote the recipe down, operands and all — documentation discipline, which is why this table exists and why the going-forward design derives the digest instead.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_legacy_dataset_pins.py -q`
Expected: PASS, with `ran["extent"] == 2` (both extent items executed against the real `data/ohlc-full`).

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a
git add docs/reference/legacy-dataset-pins.jsonl tests/test_legacy_dataset_pins.py
git commit -m "docs(registry): pin every pre-schema-4 dataset hash with evidence the tests execute"
```

---

### Task 5: Prove the ten mutate-probe guards

**Files:** none — probes only. Runs AFTER Tasks 1–4 are committed; `mutate-probe.sh` refuses a dirty tree and refuses to score anything from a tree whose probe does not pass unmutated.

Each probe must print `KILLED`. Diagnose by exit code, never by re-running blind: **rc 6** (no-op sed) means the committed text differs from the pattern — re-read the file and fix the pattern; **rc 5** (control did not fail) means the harness does not bite — pick another control, verify by reading which test the control would break, and re-run; **rc 7** means the tree is red before any mutation. Never record a verdict from an unproven harness.

Controls were each chosen against a specific existing test that must break; the reasoning is stated so an rc 5 can be diagnosed rather than guessed at. The four `provenance.py` probes share one control — `"series": len(matched)` → `0` breaks `test_an_empty_select_is_the_whole_set_and_sums_every_leaf`, which asserts `series == 3`.

- [ ] **Step 1: Load-time round-trip (D7-1)**

Control breaks `test_invalid_caller_rejected[{"verdict": "maybe"}]`, which then stops raising.

```bash
infra/scripts/mutate-probe.sh --file cli/registry/record.py \
  --control 's|if f\["verdict"\] not in VERDICTS:|if False:|' \
  --mutation 's|if compute_hash(rec\["datasets"\]) != rec\["dataset_hash"\]:|if False:|' \
  -- uv run pytest tests/test_registry_record.py -q
```

- [ ] **Step 2: No caller path to the digest (D7-2)**

Control breaks `test_seeds_may_be_empty_but_metrics_may_not` and `test_invalid_caller_rejected[{"metrics": {}}]` — an empty dict passes `_assert_finite` without raising, so both stop raising.

```bash
infra/scripts/mutate-probe.sh --file cli/registry/record.py \
  --control 's|if type(f\["metrics"\]) is not dict or not f\["metrics"\]:|if False:|' \
  --mutation 's|for k in _STORE_OWNED if k in f|for k in () if k in f|' \
  -- uv run pytest tests/test_registry_record.py -q
```

- [ ] **Step 3: Capture refuses an empty `datasets` mapping (D7-3)**

The unloadable-line guard. With the refusal gone `capture_datasets({}, root)` returns `{}` and raises nothing, so `test_capture_refuses_an_empty_selection` reds — and so does `test_append_refuses_an_empty_datasets_block_before_writing`, which is why the probe runs both files.

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|"series": len(matched)|"series": 0|' \
  --mutation 's|if not selection:|if False:|' \
  -- uv run pytest tests/test_registry_provenance.py tests/test_registry_store.py -q
```

- [ ] **Step 4: Capture refuses an absent manifest (D7-4)**

The mutation makes the missing file surface as a bare `FileNotFoundError`, which `pytest.raises(RegistryError)` does not catch.

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|"series": len(matched)|"series": 0|' \
  --mutation 's|if not path.is_file():|if False:|' \
  -- uv run pytest tests/test_registry_provenance.py -q
```

- [ ] **Step 5: Capture refuses an unusable series timestamp (D7-5)**

The silent-collapse guard. It is killed by the `None` parametrisation specifically: without the explicit check, `datetime.fromisoformat(None)` raises `TypeError`, which the `except ValueError` deliberately does not catch, so `pytest.raises(RegistryError)` fails. (The `""` case would still be converted to a `RegistryError` by the parse — that is why the test carries both stamps and why the `except` must stay narrow.)

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|"series": len(matched)|"series": 0|' \
  --mutation 's|if any(type(s) is not str or not s for s in stamps):|if False:|' \
  -- uv run pytest tests/test_registry_provenance.py -q
```

- [ ] **Step 6: Capture refuses an unknown `select` token (D7-6)**

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|"series": len(matched)|"series": 0|' \
  --mutation 's|if unknown:|if False:|' \
  -- uv run pytest tests/test_registry_provenance.py -q
```

- [ ] **Step 7: `select` resolves per dimension (D7-7)**

The regression guard: with the mutation every leaf matches, so a slice's extent silently becomes the whole set's.

```bash
infra/scripts/mutate-probe.sh --file cli/registry/provenance.py \
  --control 's|"series": len(matched)|"series": 0|' \
  --mutation 's|if all(address.get(d) in tokens for d, tokens in wanted.items())|if True|' \
  -- uv run pytest tests/test_registry_provenance.py -q
```

- [ ] **Step 8: Legacy completeness (D7-8)**

Control corrupts the `cccb8d17` recipe's `b` operand, breaking `test_every_pin_carries_evidence_that_executes`.

```bash
infra/scripts/mutate-probe.sh --file docs/reference/legacy-dataset-pins.jsonl \
  --control 's|0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de1|0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de0|' \
  --mutation '/^{"dataset_hash": "ba47e37e/d' \
  -- uv run pytest tests/test_legacy_dataset_pins.py -q
```

- [ ] **Step 9: Legacy evidence executes (D7-9)**

An `inferred` row's arithmetic must be checked, not labelled. Mutating the `ba47e37e` extent's row count must fail against the real manifest. Control deletes that pin, breaking completeness.

```bash
infra/scripts/mutate-probe.sh --file docs/reference/legacy-dataset-pins.jsonl \
  --control '/^{"dataset_hash": "ba47e37e/d' \
  --mutation 's|"rows": 29032|"rows": 29033|' \
  -- uv run pytest tests/test_legacy_dataset_pins.py -q
```

- [ ] **Step 10: Reproduced means reproduced (D7-10)**

Control deletes the `ba47e37e` pin (breaking completeness); mutation corrupts the recipe operand.

```bash
infra/scripts/mutate-probe.sh --file docs/reference/legacy-dataset-pins.jsonl \
  --control '/^{"dataset_hash": "ba47e37e/d' \
  --mutation 's|0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de1|0fed24a65b0bf3953a1dc266e2de9be68169b879fb8faeafa343d8daf5ec5de0|' \
  -- uv run pytest tests/test_legacy_dataset_pins.py -q
```

- [ ] **Step 11: Record all ten verdicts verbatim** for the closeout entry — each probe's own last line, not a paraphrase. D5's layer carries no probe here by design (D7): its constructed failures live in Task 3's two companion tests, which build a real dataset root and mutate *that*. Mutating a real dataset is impossible in this harness — every file under `data/` is gitignored, so the probe's `git checkout --` restore has nothing to restore from, which is exactly why the companions build their own root.

---

### Task 6: Closeout

- [ ] **Step 1: Full suite.** `uv run pytest` — expected PASS (~7 min with `data/ohlc-full` present, which is required here: Task 1's real-dataset parametrisations, Task 3's real-data assertions and Task 4's extent evidence all need it).

- [ ] **Step 2:** `docs/reference/data-catalog-full.md` — beyond the pins added in Task 3, record the manifest contract the registry now depends on (a non-empty top-level `series`; series leaves carrying `rows`/`first_ts`/`last_ts`; an int row count and parseable ISO timestamps in every leaf a record's `select` matches), that only the `series` subtree is digested and why, that a manifest which vouches no per-series `sha256` is a finding unless allowlisted in `tests/test_trial_registry_provenance.py`, and point at `legacy-dataset-pins.jsonl` as where pre-schema-4 hashes are explained.

- [ ] **Step 3:** Register the soak-read gap as its own topic via the `topic-ops` skill, and queue it in `docs/memo.local.md` in the same edit (registration and queue insertion travel together): `cli/engine/soak.py::_load_registry_record` reads `docs/reference/trial-registry.jsonl` with raw `json.loads` and pulls record 44's `metrics` without any chain, `record_hash` or schema validation — the live engine's instrument self-test trusts a file it never checks. Pre-existing, not introduced here.

- [ ] **Step 4:** [[T0065]] via the `topic-ops` skill — the going-forward half of the execution-reproducibility sub-item is done; rewrite it into `## Done so far` as its outcome and remove it from `## Suggested next steps`. The topic stays `partial`: the committed research-run command and the fine-cadence reach round remain. Update `ripe_when` accordingly and re-check the index bullet.

- [ ] **Step 5:** Append the iterations-history entry (phase 6 → `docs/iterations-history-phase6.md`, per the `iteration-closeout` skill), naming the ten probe verdicts, the four-verdict layer-2 split (and why "absent here" and "refreshed since" must not read as "forged"), the bytes checks that close the manifest→bytes link — the parquet row-count re-measurement that grounds `extent` for every set including the holdout, and the vouched-hash re-derivation with its one-member allowlist — the accepted cost from D4 (a record can only be written where its data sits under the repo's own `data/`), and the residual from D1 (`select` is the caller's declaration; closing it belongs to [[T0065]]'s research-run command).

- [ ] **Step 6: Commit the closeout.** One commit, all non-claude kind (`docs/memo.local.md` is gitignored — do not stage it):

```bash
uv run pre-commit run -a
git add docs/reference/data-catalog-full.md docs/open-topics/README.md \
        docs/open-topics/T0065-data-pipeline-maturity-for-strategy-research.md docs/iterations-history-phase6.md
git add "$(git status --porcelain docs/open-topics | awk '/^\?\?/ {print $2}')"  # the topic Step 3 just created
git commit -m "docs(registry): close out the verifiable-dataset-provenance iteration"
```

- [ ] **Step 7:** Re-verify every status claim on the branch against the full branch log, confirm `git status` is clean, then report the branch ready. **Do not open the PR without the owner's explicit word.**
