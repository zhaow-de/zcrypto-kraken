# Venue-silence discriminator — implementation plan (spec `00096`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach `zcrypto archive reconcile` to say *why* it believes the fleet went dark, without changing one byte of what it books.

**Architecture:** A pure classifier (`classify_dark_episode`) lands in `cli/archive/settle.py` beside `fleet_dark_windows` and `containing_dark_window`, its neighbours in the same detector. It takes the already-computed dark windows plus each pair's per-mirror timestamps and returns a three-valued verdict. `cli/archive/command.py`'s `both_streams_silent` block calls it, widens its existing `logger.error` line, records the verdict on the ledger record, and exports a label-partitioned counter derived from the ledger. The booked seconds are untouched.

**Tech Stack:** Python 3.14, polars, pytest. No new dependency.

## Global Constraints

Copied verbatim from spec `00096`; every task's requirements implicitly include these.

- **The booking never changes.** `residual_gap_seconds_total` books absence of data, not fault attribution (D1). No task may alter what is booked, by how much, or when.
- **The verdict is durable** (D4): it lands on the `both_streams_silent` ledger record AND on `zcrypto_reconcile_dark_episode_seconds_total{verdict=...}`, derived by summing the ledger like every sibling counter. It is a **parallel view, never a subtraction** — `residual_gap` keeps booking every second.
- **Measured, so do not re-derive them:** readers-before-writer converge ordering is **not owed** (the only reader of `reconcile-ledger.jsonl` is `cli/archive/command.py` itself; the NAS transports it unparsed; every read is `record.get(...)` with a default). No Alloy keep-list edit is owed (the ops keep-list admits `zcrypto_reconcile_.*` as a prefix family). No new alert rule — the new series ships **excluded with a written reason**, because venue silence must not page.
- **`undetermined` is the fail-closed default** (D3). Bracketing events — those before the first booked window or after the last — never promote to `venue_silent`.
- **Verdict names are exactly** `venue_silent`, `capture_divergent`, `undetermined`.
- **`venue_silent` requires at least one interior row of type `update`** (D2a). A snapshot is a periodic/resubscribe artifact and does not prove the feed is live. A snapshot-only interior reads `undetermined`.
- **The alert summary is operator-facing text** (D5): no `T<NNNN>`, no spec serial, no `Phase <N>`, no `iter-<N>`. `tests/test_internal_terms_not_operator_visible.py` enforces this.
- **Commit gate is `uv run pre-commit run -a`**, never `--no-verify`. Stage by explicit path, never `git add -A`.
- **Every commit ends** `Co-Authored-By: <the actual authoring model> <noreply@anthropic.com>`, and carries `Reviewed-by:` from a *different* agent before push.

## File structure

| File | Responsibility | Change |
| --- | --- | --- |
| `cli/archive/settle.py` | The dual-silence detector's primitives. Gains the classifier because its inputs are this module's own `DarkWindow` and the same per-mirror stamps `containing_dark_window` already consumes. | Modify — add `EpisodeVerdict`, `classify_dark_episode`, and the three verdict constants |
| `cli/archive/command.py` | The reconcile cycle. Calls the classifier at the booking site, widens the log line, adds `verdict` to the ledger record, and derives the new counter in `_totals`/the exporter. | Modify — the `both_streams_silent` block, `_totals`, and one `_emit` call |
| `infra/grafana/alerts.yaml` | The `zcrypto-reconcile-residual-gap` rule's `summary` annotation gains the triage line. `expr`, threshold, `for`, severity, uid all unchanged. | Modify — annotation text only |
| `tests/test_archive_settle.py` | Unit tests for the classifier — all three verdicts, the true-positive, the bracket refusal. | Modify |
| `tests/test_archive_reconcile_command.py` | The regression that pins D1: the ledger record is unchanged and gains no field. | Modify |
| `docs/reference/capture-era-data-hygiene-map.md` | D6 — the 2026-08-20 row, in the same shape as the 2026-08-06 venue-outage row already there. | Modify at closeout |
| `docs/open-topics/T0143-*.md`, `docs/open-topics/README.md` | T0143 → `resolved`, via the `topic-ops` skill. | Modify at closeout |
| `docs/research/14.phase6-decisions.md`, `docs/iterations-history-phase6.md` | Decisions-log + changelog entries, via the `iteration-closeout` skill. | Modify at closeout |

---

### Task 1: The classifier

**Files:**
- Modify: `cli/archive/settle.py` (append after `containing_dark_window`)
- Test: `tests/test_archive_settle.py`

**Interfaces:**
- Consumes: `DarkWindow` (already defined in this module: frozen dataclass with `start: datetime`, `end: datetime`, `seconds: float`).
- Produces:
  - `VENUE_SILENT = "venue_silent"`, `CAPTURE_DIVERGENT = "capture_divergent"`, `UNDETERMINED = "undetermined"`
  - `EpisodeVerdict` — frozen dataclass, fields `verdict: str`, `interior_updates: int`, `interior_snapshots: int`, `pairs_agreeing: int`, `divergent_pairs: tuple[str, ...]`
  - `classify_dark_episode(windows: Sequence[DarkWindow], mirror_rows: Mapping[str, Mapping[str, list[tuple[datetime, str]] | None]]) -> EpisodeVerdict`

  Both counts are **parquet rows, not wire messages**: the capture writer emits one row per price level per side per message (`cli/capture/command.py`), so a single real book update yields many rows. The names say rows so nobody reads them as message counts. Each row is `(ts, type)` with `type` exactly `"snapshot"` or `"update"`.
  `mirror_rows` is keyed pair → `{"primary": [(ts, type), ...] | None, "secondary": [...] | None}`; `None` means that mirror's segment was absent or unreadable this hour.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_archive_settle.py`, and extend the existing `from cli.archive.settle import (...)` block with `CAPTURE_DIVERGENT`, `EpisodeVerdict`, `UNDETERMINED`, `VENUE_SILENT`, `classify_dark_episode`.

```python
# --- the venue-silence discriminator (spec 00096) -------------------------------------------------
#
# A booked window contains ZERO events by construction -- `fleet_dark_windows` runs over the union
# of both mirrors across every pair -- so the evidence lives in the INTERIOR span: the events
# BETWEEN adjacent booked windows, which exist precisely because some stream ticked there.


def _episode() -> list[DarkWindow]:
    """Two booked windows split by a lone interior event at t=500 -- the 2026-08-20 shape."""
    return [
        DarkWindow(start=_at(0), end=_at(500), seconds=500.0),
        DarkWindow(start=_at(500), end=_at(1000), seconds=500.0),
    ]


def test_mirrors_agreeing_on_the_interior_event_prove_the_venue_went_silent():
    # Both hosts recorded the SAME lone mid-episode message. `ts` is Kraken's own payload timestamp
    # (cli/capture/command.py), never local receipt time, so identical stamps mean both hosts were
    # connected and receiving DURING the episode -- a host that was not receiving cannot invent one.
    verdict = classify_dark_episode(
        _episode(),
        {"BTC/EUR": {"primary": [(_at(500), "update")], "secondary": [(_at(500), "update")]}},
    )
    assert verdict.verdict == VENUE_SILENT
    assert verdict.interior_updates == 1
    assert verdict.pairs_agreeing == 1
    assert verdict.divergent_pairs == ()


def test_a_mirror_that_missed_an_interior_event_is_a_capture_finding():
    # The secondary lacks what the primary got: one host missed a message the venue sent. That is
    # capture-side, and it must NEVER read as venue silence.
    verdict = classify_dark_episode(
        _episode(),
        {"BTC/EUR": {"primary": [(_at(500), "update")], "secondary": []}},
    )
    assert verdict.verdict == CAPTURE_DIVERGENT
    assert verdict.divergent_pairs == ("BTC/EUR",)


def test_divergence_on_any_pair_outranks_agreement_on_every_other():
    # Fail-closed ordering: one mirror missing one message is a finding in its own right, and must
    # not be masked by eleven other pairs agreeing.
    verdict = classify_dark_episode(
        _episode(),
        {
            "BTC/EUR": {"primary": [(_at(500), "update")], "secondary": [(_at(500), "update")]},
            "ETH/EUR": {"primary": [(_at(500), "update")], "secondary": []},
        },
    )
    assert verdict.verdict == CAPTURE_DIVERGENT
    assert verdict.divergent_pairs == ("ETH/EUR",)


def test_a_single_booked_window_has_no_interior_and_is_undetermined():
    # Nothing split the episode, so there is no interior span at all. THE fail-closed default: a
    # simultaneous both-host outage looks exactly like this, and must not be excused.
    one = [DarkWindow(start=_at(0), end=_at(1000), seconds=1000.0)]
    verdict = classify_dark_episode(one, {"BTC/EUR": {"primary": [], "secondary": []}})
    assert verdict.verdict == UNDETERMINED
    assert verdict.interior_updates == 0


def test_bracketing_events_never_promote_to_venue_silent():
    # D3. Both mirrors agree on the events immediately BEFORE and AFTER the episode -- which proves
    # only that both hosts were healthy either side of it. A both-host outage that self-healed
    # produces exactly this signature, so the verdict stays undetermined.
    one = [DarkWindow(start=_at(100), end=_at(1000), seconds=900.0)]
    verdict = classify_dark_episode(
        one,
        {"BTC/EUR": {"primary": [(_at(50), "update"), (_at(1100), "update")], "secondary": [(_at(50), "update"), (_at(1100), "update")]}},
    )
    assert verdict.verdict == UNDETERMINED


def test_a_pair_missing_a_mirror_entirely_contributes_no_evidence():
    # An unreadable/absent segment is not a divergence: there is nothing to compare against.
    verdict = classify_dark_episode(
        _episode(),
        {"BTC/EUR": {"primary": [(_at(500), "update")], "secondary": None}},
    )
    assert verdict.verdict == UNDETERMINED
    assert verdict.divergent_pairs == ()


def test_a_snapshot_only_interior_never_reads_as_venue_silence():
    # D2a -- THE constructible false positive. A regression that breaks update-row writing while
    # leaving book_snapshot handling intact makes BOTH hosts (same image, by the canary rule)
    # write identical sparse snapshot rows. A snapshot is a periodic/resubscribe artifact and
    # proves nothing about a live feed, so this must NOT read as the venue going quiet.
    verdict = classify_dark_episode(
        _episode(),
        {"BTC/EUR": {"primary": [(_at(500), "snapshot")], "secondary": [(_at(500), "snapshot")]}},
    )
    assert verdict.verdict == UNDETERMINED
    # the counts are still recorded, so the record explains ITSELF without re-running anything
    assert verdict.interior_snapshots == 1
    assert verdict.interior_updates == 0


def test_one_interior_update_is_enough_even_beside_snapshots():
    verdict = classify_dark_episode(
        _episode(),
        {"BTC/EUR": {
            "primary": [(_at(500), "snapshot"), (_at(500), "update")],
            "secondary": [(_at(500), "snapshot"), (_at(500), "update")],
        }},
    )
    assert verdict.verdict == VENUE_SILENT
    assert verdict.interior_updates == 1
    assert verdict.interior_snapshots == 1


def test_a_healthy_hour_with_no_windows_is_undetermined_and_never_classifies():
    # THE true-positive: a production-shaped healthy hour books nothing, so the classifier must not
    # manufacture a verdict. An always-classifying implementation fails here.
    verdict = classify_dark_episode([], {"BTC/EUR": {"primary": [(_at(s), "update") for s in range(0, 3600, 5)], "secondary": [(_at(s), "update") for s in range(0, 3600, 5)]}})
    assert verdict.verdict == UNDETERMINED
    assert verdict.interior_updates == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_archive_settle.py -k "interior or venue_silent or capture or bracket or undetermined or mirror" -v`
Expected: collection error — `ImportError: cannot import name 'classify_dark_episode'`. That the import itself fails is the correct first red.

- [ ] **Step 3: Write the implementation**

Append to `cli/archive/settle.py`, after `containing_dark_window`. Add `Mapping` and `Sequence` to the existing `collections.abc` import.

```python
VENUE_SILENT = "venue_silent"
CAPTURE_DIVERGENT = "capture_divergent"
UNDETERMINED = "undetermined"


@dataclass(frozen=True)
class EpisodeVerdict:
    """Why the fleet went dark — TRIAGE ONLY, and deliberately not an input to any booking.

    `residual_gap_seconds_total` books ABSENCE of data; this says what the reconciler believes
    CAUSED the absence. Fusing the two would make a monotonic, unwalkbackable ledger depend on an
    inference, so the verdict reaches the log line and nothing else (spec 00096 D1/D4).
    """

    verdict: str
    interior_updates: int
    interior_snapshots: int
    pairs_agreeing: int
    divergent_pairs: tuple[str, ...]


def classify_dark_episode(
    windows: Sequence[DarkWindow],
    mirror_rows: Mapping[str, Mapping[str, list[tuple[datetime, str]] | None]],
) -> EpisodeVerdict:
    """Was this episode the VENUE going quiet, or the fleet failing to record?

    The discriminator is cross-host agreement, and it is sound rather than coincidental: the capture
    writer stores Kraken's OWN message timestamp (`cli/capture/command.py` sets
    `ts = _parse_ts(entry["timestamp"])`), never local receipt time. Two independent hosts that
    receive the same message therefore record byte-identical `ts` by construction, and a host that
    was not receiving cannot manufacture one.

    This is EVIDENCE-WEIGHTING, never proof. Agreement establishes that both hosts were receiving
    at those instants, and therefore that the silence was upstream of both hosts' write paths --
    it cannot exclude a deterministic shared-code drop (the canary rule puts the same image on
    both hosts by design) or a shared upstream path failure. That is exactly why the verdict never
    gates the booking, and why a verdict landing right after a fleet-wide image change deserves
    scepticism.

    Evidence can only come from the INTERIOR span — between the first booked window's end and the
    last one's start. A booked window contains no events at all by construction (`fleet_dark_windows`
    runs over the union of both mirrors across every pair), and events OUTSIDE the episode are
    refused deliberately: agreement before and after proves only that both hosts were healthy either
    side of it, which is exactly the signature of a simultaneous both-host outage that self-healed.
    Excusing a real correlated capture failure is the one direction this must not fail in, so
    `undetermined` is the default and brackets never promote (D3).

    Divergence outranks agreement: one mirror missing one message is a capture finding in its own
    right, and must not be masked by every other pair agreeing.
    """
    if len(windows) < 2:
        return EpisodeVerdict(UNDETERMINED, 0, 0, 0, ())  # nothing split the episode: no interior
    span_start, span_end = windows[0].end, windows[-1].start
    if span_start > span_end:
        return EpisodeVerdict(UNDETERMINED, 0, 0, 0, ())  # guarded, never assumed: no span to read
    updates = 0
    snapshots = 0
    agreeing = 0
    divergent: list[str] = []
    for pair in sorted(mirror_rows):
        mirrors = mirror_rows[pair]
        primary, secondary = mirrors.get("primary"), mirrors.get("secondary")
        if primary is None or secondary is None:
            continue  # an absent or unreadable mirror is not a divergence -- there is no comparison
        # The key is (ts, type), so a TYPE divergence between mirrors is a divergence like any other.
        inside_p = sorted(row for row in primary if span_start <= row[0] <= span_end)
        inside_s = sorted(row for row in secondary if span_start <= row[0] <= span_end)
        if not inside_p and not inside_s:
            continue  # this pair simply had nothing to say in the interior
        if inside_p == inside_s:
            agreeing += 1
            updates += sum(1 for _, kind in inside_p if kind == "update")
            snapshots += sum(1 for _, kind in inside_p if kind != "update")
        else:
            divergent.append(pair)
    if divergent:
        verdict = CAPTURE_DIVERGENT
    elif agreeing and updates:
        verdict = VENUE_SILENT
    else:
        # Includes the snapshot-only interior (D2a): agreement on periodic/resubscribe artifacts is
        # not evidence of a live feed. The counts are still returned, so the ledger record explains
        # ITSELF rather than needing the classifier re-run to find out why.
        verdict = UNDETERMINED
    return EpisodeVerdict(verdict, updates, snapshots, agreeing, tuple(divergent))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_archive_settle.py -v`
Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 5: Commit**

```bash
git add cli/archive/settle.py tests/test_archive_settle.py
git commit
```

Message: `feat(archive): classify a dark episode as venue silence or capture divergence`

- [ ] **Step 6: Prove the guard bites, then amend the message with the result**

`agent-ops.md`: a guard is unproven until the defect it names is constructed and seen to trip it, and mutation probes run through `infra/scripts/mutate-probe.sh`, never a hand-rolled loop. The script **refuses a dirty worktree** (rc 3) — which is why this follows the commit rather than preceding it.

First confirm the probe actually collects the tests under proof:

```bash
uv run pytest tests/test_archive_settle.py -q --collect-only | tail -3
```

Then run the probe. `--control` must be a mutation that certainly breaks the tests (proving the harness bites); `--mutation` is the real defect under proof:

```bash
infra/scripts/mutate-probe.sh   --file cli/archive/settle.py   --control 's/if len(windows) < 2:/if len(windows) < 0:/'   --mutation 's/if inside_p == inside_s:/if True:/'   -- uv run pytest tests/test_archive_settle.py -q
```

Expected: the control FAILS the probe (rc 0 overall, control proven), and the mutation is reported KILLED. Read **which** test failed under the mutation — it must be `test_a_mirror_that_missed_an_interior_event_is_a_capture_finding` and `test_divergence_on_any_pair_outranks_agreement_on_every_other` asserting on the verdict, not a collection or import error.

Amend the commit message with the probe result:

```bash
git commit --amend
```

Note in the body that the `span_start > span_end` early return is a **defensive branch with no constructible caller** — a two-window episode cannot produce it — so it is documented as unproven rather than given a test for a state the caller cannot reach.

---

### Task 2: Wire it in — log line, ledger field, and the partitioned counter

**Files:**
- Modify: `cli/archive/command.py` — the `both_streams_silent` block, `_totals`, and one `_emit` call
- Test: `tests/test_archive_reconcile_command.py`

**Interfaces:**
- Consumes: `classify_dark_episode` from Task 1.
- Produces: ledger key `verdict` (plus `interior_updates`, `interior_snapshots`, `pairs_agreeing`, `divergent_pairs`) on `both_streams_silent` records; metric `zcrypto_reconcile_dark_episode_seconds_total{verdict="venue_silent|capture_divergent|undetermined"}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_archive_reconcile_command.py`. Reuse the file's existing helpers (`_roots`, `_write`, `_book`, `_run`, `_ledger`, `_series`, `H`, `SETTLED`, `PAIRS`).

```python
def test_the_verdict_is_recorded_and_counted_while_the_booking_is_untouched(tmp_path, monkeypatch, caplog):
    """Spec 00096 D1/D4 — the load-bearing regression, because the booking is a CONTRACT.

    Splitting an episode into two windows must not move `residual_seconds` by a single second: the
    counter derived from it is monotonic and unwalkbackable. The verdict rides ALONGSIDE, on the
    record and in its own partitioned counter, and never subtracts from residual.
    """
    pri, sec, rec = _roots(tmp_path)
    dark = [(float(s), "update") for s in range(0, 3600, 10) if not 1200 <= s < 1800]
    for pair in PAIRS:
        _write(pri, pair, "book", H, _book(pair, H, dark))
        _write(sec, pair, "book", H, _book(pair, H, dark))
    # ONE interior event, on BTC only, written IDENTICALLY to both mirrors -- the 2026-08-20 shape.
    # It splits the fleet-dark span into TWO windows, which is the only thing that creates an
    # interior span at all; without it there is nothing for the discriminator to read.
    split = sorted(dark + [(1500.0, "update")])
    _write(pri, "BTC/EUR", "book", H, _book("BTC/EUR", H, split))
    _write(sec, "BTC/EUR", "book", H, _book("BTC/EUR", H, split))

    with caplog.at_level(logging.ERROR):
        result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    silent = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    assert len(silent) == 1
    record = silent[0]

    # (a) THE CONTRACT: the booked seconds are IDENTICAL to the single-window case in
    #     test_both_streams_silent_is_ledgered_paged_and_never_minted, even though the episode now
    #     books as two windows instead of one -- BTC books 310+300, ETH books its containing 610
    #     once. Splitting an episode must not move the counter.
    assert record["residual_seconds"] == pytest.approx(1220.0)
    assert [w["seconds"] for w in record["windows"]] == [pytest.approx(310.0), pytest.approx(300.0)]

    # (b) the verdict and its evidence are on the DURABLE record, not only in a log line
    assert record["verdict"] == "venue_silent"
    assert record["pairs_agreeing"] == 1
    assert record["divergent_pairs"] == []

    # (c) the key set is pinned EXACTLY: the record gains these four keys and nothing else.
    assert set(record) == {
        "at", "state", "pair", "kind", "hour", "pairs", "windows", "stream_windows", "residual_seconds",
        "verdict", "interior_updates", "interior_snapshots", "pairs_agreeing", "divergent_pairs",
    }

    # (d) the operator's log line carries it too -- that is the 3am path
    line = next(m for m in caplog.messages if "both_streams_silent" in m)
    assert "verdict=venue_silent" in line


def test_the_dark_episode_counter_partitions_the_booked_seconds(tmp_path, monkeypatch):
    """D4 -- the metric checks itself: the three label values sum to exactly the
    `both_streams_silent` seconds, so a classification bug cannot quietly lose or duplicate time.

    And it is a PARALLEL VIEW: residual_gap still books every second, so venue_silent <= residual.
    """
    pri, sec, rec = _roots(tmp_path)
    dark = [(float(s), "update") for s in range(0, 3600, 10) if not 1200 <= s < 1800]
    for pair in PAIRS:
        _write(pri, pair, "book", H, _book(pair, H, dark))
        _write(sec, pair, "book", H, _book(pair, H, dark))
    split = sorted(dark + [(1500.0, "update")])
    _write(pri, "BTC/EUR", "book", H, _book("BTC/EUR", H, split))
    _write(sec, "BTC/EUR", "book", H, _book("BTC/EUR", H, split))

    textfile = tmp_path / "reconcile.prom"
    result = _run(
        [str(pri), str(sec), str(rec), "--mint", "--textfile", str(textfile)],
        now=SETTLED, monkeypatch=monkeypatch,
    )
    assert result.exit_code == 0
    series = _series(textfile)

    booked = sum(
        v for k, v in series.items() if k.startswith("zcrypto_reconcile_dark_episode_seconds_total{")
    )
    assert booked == pytest.approx(1220.0)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="venue_silent"}'] == pytest.approx(1220.0)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="capture_divergent"}'] == pytest.approx(0.0)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="undetermined"}'] == pytest.approx(0.0)
    # the parallel-view invariant: residual books everything, and never less than the classified part
    assert series["zcrypto_reconcile_residual_gap_seconds_total"] >= booked


def test_a_record_written_before_the_discriminator_existed_counts_as_undetermined(tmp_path, monkeypatch):
    """D4a. The two real historical episodes are already in the live ledger with no `verdict`, and
    `_decided` prevents re-deciding them. The counter must NEVER retroactively claim knowledge the
    system did not have -- a verdict-less record is `undetermined`, not `venue_silent`.
    """
    pri, sec, rec = _roots(tmp_path)
    rec.mkdir(parents=True, exist_ok=True)
    legacy = {
        "at": "2026-08-06T09:12:00+00:00",
        "state": "both_streams_silent",
        "pair": "*",
        "kind": "book",
        "hour": "2026-08-06T07:00:00+00:00",
        "pairs": ["BTC/EUR"],
        "windows": [{"start": "2026-08-06T07:01:02+00:00", "end": "2026-08-06T07:18:18+00:00", "seconds": 1036.0}],
        "residual_seconds": 1036.0,
    }
    (rec / "reconcile-ledger.jsonl").write_text(json.dumps(legacy) + "\n")

    textfile = tmp_path / "reconcile.prom"
    result = _run([str(pri), str(sec), str(rec), "--textfile", str(textfile)], now=SETTLED, monkeypatch=monkeypatch)
    assert result.exit_code == 0
    series = _series(textfile)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="undetermined"}'] == pytest.approx(1036.0)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="venue_silent"}'] == pytest.approx(0.0)
```

Check `_run`'s existing signature for the textfile flag's real name before writing these — grep the file for `--textfile` and copy the flag exactly as other tests pass it. If the flag differs, use the real one; do not invent it.

**If `caplog` captures nothing**, the CLI has reconfigured logging under `CliRunner`. Do not weaken assertion (d) — instead `monkeypatch.setattr(command.logger, "error", recorder)` with a recorder appending `fmt % args`, and assert on that.

The numbers 310.0 / 300.0 / 1220.0 are derived, not guessed: `dark` omits `1200 <= s < 1800` on a 10 s cadence, so the fleet-dark span runs `1190 -> 1800` (610 s) and the event at `1500` splits it into 310 + 300; ETH, having no event at 1500, books its containing 610 s once. Re-derive if you change the cadence.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_archive_reconcile_command.py -k "verdict or dark_episode or undetermined" -v`
Expected: FAIL. Assertion (a) in the first test must ALREADY pass — that is the point: it pins current behaviour, so seeing it green *before* the implementation proves it is a real contract rather than an echo of the new code.

- [ ] **Step 3: Write the implementation**

Add `classify_dark_episode` to the existing `from cli.archive.settle import (...)` block.

Immediately before the existing `logger.error("archive reconcile: both_streams_silent ...")` call, insert:

```python
                # TRIAGE ONLY -- never an input to `residual` above (spec 00096 D1). Both mirrors'
                # frames are already in hand from the read above, so this costs no I/O.
                episode = classify_dark_episode(
                    windows,
                    {
                        p: {
                            # (ts, type) pairs. Zipped explicitly rather than `.rows()`, which would
                            # depend on the column order `_read` happened to return.
                            src: (None if f is None else list(zip(f["ts"].to_list(), f["type"].to_list(), strict=True)))
                            for src, f in books[p].items()
                        }
                        for p in present
                    },
                )
```

Widen the log call:

```python
                logger.error(
                    "archive reconcile: both_streams_silent hour=%s windows=%d residual_s=%.1f verdict=%s updates=%d snapshots=%d divergent=%s",
                    hour.isoformat(),
                    len(windows),
                    residual,
                    episode.verdict,
                    episode.interior_updates,
                    episode.interior_snapshots,
                    ",".join(episode.divergent_pairs) or "-",
                )
```

Add four keys to the `_ledger(...)` call that follows — and **change none of its existing arguments**:

```python
                    verdict=episode.verdict,
                    interior_updates=episode.interior_updates,
                    interior_snapshots=episode.interior_snapshots,
                    pairs_agreeing=episode.pairs_agreeing,
                    divergent_pairs=list(episode.divergent_pairs),
```

In `_totals`, add the three partition keys to the `dict.fromkeys((...))` tuple — `"dark_venue_silent"`, `"dark_capture_divergent"`, `"dark_undetermined"` — and accumulate inside the same loop that already walks records:

```python
        if record.get("state") == "both_streams_silent":
            # A record written before the discriminator existed carries no verdict, and the counter
            # must not claim knowledge the system did not have (spec 00096 D4a).
            verdict = record.get("verdict") or "undetermined"
            totals[f"dark_{verdict}"] += float(record.get("residual_seconds") or 0.0)
```

Guard the key: an unknown verdict string would raise `KeyError` here. Use `totals.setdefault(f"dark_{verdict}", 0.0)` if you prefer tolerance, but then the exporter must still emit exactly the three known labels — a fourth series appearing silently is an admitted-metrics surprise.

Add one `_emit` beside `residual_gap_seconds_total`. **The HELP text is operator-facing** (`operator-facing-text.md`): no topic id, no spec serial.

```python
    _emit(
        "dark_episode_seconds_total",
        "counter",
        "The both_streams_silent seconds above, split by what the evidence weighs toward. "
        "venue_silent: both capture hosts recorded the same venue message timestamps inside the "
        "episode, so the silence was upstream of both. capture_divergent: one host missed what the "
        "other received. undetermined: no evidence either way -- including every record written "
        "before this split existed. A PARALLEL VIEW of residual_gap_seconds_total, never subtracted "
        "from it; the three add up to the both_streams_silent share of it.",
        [
            ('{verdict="venue_silent"}', totals["dark_venue_silent"]),
            ('{verdict="capture_divergent"}', totals["dark_capture_divergent"]),
            ('{verdict="undetermined"}', totals["dark_undetermined"]),
        ],
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_archive_reconcile_command.py -v`
Expected: PASS, including every pre-existing test — particularly `test_both_streams_silent_is_ledgered_paged_and_never_minted`, `test_a_fleet_dark_window_is_never_booked_as_loss_twice`, and `test_one_pair_going_quiet_alone_is_never_both_streams_silent`.

- [ ] **Step 5: Confirm the active-series budget still holds**

Three new series against a measured 884 active and spec `00043`'s <1k ceiling. Note the count in the commit message; if the fleet has grown since, re-measure before assuming headroom.

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass. Budget ~7 min 30 s — `data/ohlc-full` is present, so the data-dependent regression tests run.

- [ ] **Step 7: Commit**

```bash
git add cli/archive/command.py tests/test_archive_reconcile_command.py
git commit
```

Message: `feat(archive): record and count the dark-episode verdict beside the booking`

---

### Task 3: The alert triage line

**Files:**
- Modify: `infra/grafana/alerts.yaml` — `uid: zcrypto-reconcile-residual-gap`, `annotations.summary` only
- Test: `tests/test_internal_terms_not_operator_visible.py` (existing; no edit — it must keep passing)

**Interfaces:** none. Text change.

- [ ] **Step 1: Edit the summary**

Replace the `summary:` value of the `zcrypto-reconcile-residual-gap` rule with:

```yaml
      summary: "Permanent L2 loss: silence that NEITHER capture host covered. This cannot be healed or backfilled -- the data is gone. Check the reconcile ledger for the records behind it: both_streams_silent or total_loss for correlated loss, or a minted/would_mint hour whose splice left seconds unfilled -- any of the three can drive this. TRIAGE FIRST: a both_streams_silent record carries a verdict field, also exported as dark_episode_seconds_total by verdict. venue_silent means both capture hosts recorded the same venue message timestamps inside the window, so the silence was upstream of both hosts -- weigh it as a venue event, and treat it sceptically if a fleet-wide image change just landed. capture_divergent means one host missed what the other received: investigate the fleet. undetermined means no evidence either way -- treat it as loss, and check zcrypto_capture_venue_status_total for that hour, where a series for anything other than online is itself a venue signal this check cannot see."
```

`expr`, `condition`, `for`, `noDataState`, `execErrState`, `labels.severity`, `uid`, and the `__dashboardUid__`/`__panelId__`/`unit` annotations are unchanged. This is an **upsert of annotation text**: no uid is superseded, so **no prune is owed** (`capture-deploys.md`).

- [ ] **Step 2: Verify the operator-facing ban still holds**

Run: `uv run pytest tests/test_internal_terms_not_operator_visible.py -v`
Expected: PASS. The summary deliberately names no topic id, spec serial, phase, or iteration.

- [ ] **Step 3: Verify every other field of the rule is byte-identical**

**Assert on what the defect moves** (`agent-ops.md`): the YAML parses and exits 0 whether or not `expr` was disturbed, so parsing proves nothing. Compare the rule against its committed self with the summary popped:

```bash
uv run python - <<'PYEOF'
import subprocess, yaml

UID = "zcrypto-reconcile-residual-gap"

def rule(text):
    for r in yaml.safe_load(text)["rules"]:
        if r.get("uid") == UID:
            return r
    raise SystemExit(UID + " not found")

committed = subprocess.run(["git", "show", "HEAD:infra/grafana/alerts.yaml"],
                           capture_output=True, text=True, check=True).stdout
old = rule(committed)
new = rule(open("infra/grafana/alerts.yaml").read())
old_summary = old["annotations"].pop("summary")
new_summary = new["annotations"].pop("summary")
assert old == new, "something OTHER than the summary changed -- inspect before committing"
assert old_summary != new_summary, "the summary did not actually change"
print("OK: expr, condition, for, severity, uid, dashboard/panel annotations all unchanged")
print("--- OLD ---")
print(old_summary)
print("--- NEW ---")
print(new_summary)
PYEOF
```

Expected: the `OK:` line plus both summaries. Read them — the new one must differ only by the appended triage sentences. Note the top-level shape is `{"rules": [...]}` (72 rules), not Grafana's `groups` form.

- [ ] **Step 4: Run the gate and commit**

```bash
uv run pre-commit run -a
git add infra/grafana/alerts.yaml
git commit
```

Message: `feat(archive): give the residual-gap page its triage line`

**Do not push the rule to Grafana here.** Per `capture-deploys.md`'s alert-rule lifecycle the push happens after the converge, and is verified evaluating *by value*. That is Task 5.

---

### Task 4: Subagent review, then push

- [ ] **Step 1: Dispatch a reviewer that is NOT the implementer**

Mandatory before push (`commit-messages.md`), and this change touches the reconciler's permanent-loss path, so the review floor is **Fable**. The reviewer reads the full branch diff against `develop` and checks, specifically: that no task altered what is booked; that `undetermined` is genuinely the default on every path; that the alert rule's non-annotation fields are untouched.

- [ ] **Step 2: Amend each reviewed commit with its trailer**

`Reviewed-by: <actual reviewer model> <noreply@anthropic.com>` — a reviewer is never a co-author. Amending is free while the branch is unpushed.

- [ ] **Step 3: Push**

```bash
timeout 60 git push -u origin feat/t0143-venue-silence-discriminator
```

---

### Task 5: Attended verification against BOTH real events

> **MAIN LOOP ONLY — do not dispatch this to a subagent or a workflow.** It reads a NAS/host copy of the capture tree, and the permission gate blocks ssh/sudo steps inside a subagent, where the prompt dies unseen (`agent-ops.md`). Verified 2026-08-20: there is no local `capture-segments` tree to substitute.

- [ ] **Step 1: Replay all four records and match the measured table**

The archive is readable locally at `/mnt/zhao-crypto` (the aligned NFS mount — a pulled copy, never the live capture dir), so **this rule was already run against the real data before implementation**. These are regression expectations, not open questions. Any divergence is a finding about the implementation:

| Hour | Expected verdict | Booked (full precision) | Interior evidence |
| --- | --- | --- | --- |
| 2026-07-13 07:00Z | `undetermined` | 2,661.788740 s | 1 window, no interior span |
| 2026-07-27 07:00Z | `undetermined` | 2,385.847992 s | 1 window, no interior span |
| 2026-08-06 07:00Z | `undetermined` | 10,588.382751 s | 1 instant, BTC/EUR only: 200 snapshot rows, **0 updates** |
| 2026-08-20 07:00Z | `venue_silent` | 6,251.349974 s | 98 s span, 12/12 pairs byte-identical, **90 updates**, 2,200 snapshots |

Two of these are load-bearing beyond arithmetic:

- **2026-07-13 is the true negative.** That hour was a Kraken WS 503 followed by a capture-side restart clobber that lost 270 s capture should have kept. It must read `undetermined`. A build that reads `venue_silent` there is excusing a real capture defect and must not ship.
- **2026-08-06 reading `undetermined` is correct, not a miss.** Its only interior evidence is a resubscribe snapshot, which does not prove a live feed. Kraken posted that outage, so the operator-facing path for this class is the venue-status counter named in Task 3 — not a softened rule here.

Reproduce every number from the data at full precision; never quote it from the spec, the hygiene map, or this table (`agent-ops.md`).

The replay is read-only and must **not** rewrite the live ledger: `_decided` prevents re-deciding an already-ledgered `(pair, kind, hour, state)`, so all four production records keep no verdict and count as `undetermined` (D4a). After the converge, confirm the live counter shows exactly that — `undetermined` carrying the sum of all four (21,887.369457 s — which is the ENTIRE residual counter today, so the partition is exactly checkable) and `venue_silent` at 0.0 — rather than assuming it.

- [ ] **Step 2: Record the digest, then converge ops**

`zcrypto-ops` is the compute tier — no canary bake owed — but four operands are mechanically required and a converge missing any of them bounces (`capture-deploys.md`):

1. **Record the running digest in `docs/reference/fleet-pins.md` FIRST** — the pins assert refuses otherwise, and that row is the only rollback operand (`ops_image_digest` has no repo default).
2. **Pull the digest on the host first** — every runner is `--pull never`, and the ops role's digest preflight refuses a digest the host has not pulled.
3. **`--limit zcrypto-ops` is mandatory** — a bare `site.yml` still runs the NAS play. Use `infra/ansible/scripts/converge.sh`, which refuses the bare form and previews first. Never wrap it in `timeout`.
4. **`-e liquidations_decision=roll-after`** — `ops_image_digest` also repins the liquidations compose, which the role never restarts, and it refuses the repin without this. `roll-after` is the standing preference: the poller re-fetches a 30 h window every cycle, so a converge-length restart self-heals.

**Omit `ops_alloy_digest`** — Alloy is not the subject here. No `config.alloy` edit is owed at all: the ops keep-list already admits `zcrypto_reconcile_.*` as a prefix family, so the new series is admitted without touching it. Verify that claim by reading the rendered keep-list before converging rather than trusting this line.

- [ ] **Step 3: Verify the new series by VALUE, then push the alert**

At the next tick run `infra/scripts/ops-postverify.sh` — `(no series)` reads FAIL, never a zero.

Then read the new counter's three label values directly. **Read the numbers, do not check for presence** (`agent-ops.md`): `increase()`/`delta()` are blind to a condition already present in a series' first sample, so a fault born in the deploy window is baked into the baseline and never fires. Expect `undetermined` to be non-zero from the first scrape — the two historical episodes land there by D4a — and `venue_silent` to be 0.0 until a *new* episode books. Assert the partition: the three values must sum to the `both_streams_silent` share of `residual_gap_seconds_total`.

Then `infra/scripts/grafana-push.sh` for the annotation change, and confirm the rule is **evaluating** by value. **No prune is owed** — same uid, annotation-only (Task 3, Step 1) — so do not run `GRAFANA_PRUNE=1`.

---

### Task 6: Closeout

> Authored **now**, at the branch's end — never pre-written during planning (`iterations-history.md`). Re-verify every status claim against the full branch log immediately before PR-open.

- [ ] **Step 1: D6 — annotate BOTH events in the hygiene map**

`docs/reference/capture-era-data-hygiene-map.md` already carries the **2026-08-06** venue-outage row in exactly the right shape: venue cause, gap-seconds, the reconciler's booking, and a FLAG verdict for continuity-sensitive analyses. Add **2026-08-20** in that same shape, and extend 08-06's row with its `both_streams_silent` booking of 10,588.382751 s if it is not already stated there.

This is the established convention, not a new invention — `docs/reference/data-catalog-full.md` is the OHLCVT dataset catalog and carries no per-day capture-continuity figure, so it is the wrong home.

Rewrite narrative in place; never append a retraction (`agent-ops.md`). The per-event evidence — timestamps, counter values, the booking tick — goes in **this commit's message**, not the living doc (`docs-style.md`). Escape `|` as `\|` inside any table code span: `docs/reference/` is outside mdformat's reach, and GFM silently discards surplus cells. Check the rendered cell count after editing.

- [ ] **Step 2: T0143 → `resolved`**

Load the `topic-ops` skill first; it owns the `## Done so far` move, archive mechanics, and index sync.

All three of T0143's own suggested next steps are discharged by this branch: the input decided (cross-host), the triage line written, and the historical bookings annotated. The counter promotion D4 originally deferred is built here too.

**One successor topic IS owed** — registered during planning, not deferred as prose: retroactive venue status. Measurement showed cross-host and venue status are complementary, each catching the event the other misses, and the reason status cannot be used here is that the public endpoint is current-state only while capture never writes what it receives into the archive. Confirm the topic exists and is queued in the memo before archiving T0143; `open-topics.md` forbids archiving a topic still carrying a live deferred sub-item, and registration without a memo queue entry is invisible at pick time.

The whole topic update — `status`, `ripe_when`, `## Done so far`, and removal of the finished next-steps — lands in **this** PR.

- [ ] **Step 3: Decisions-log + changelog entries**

Load the `iteration-closeout` skill first; it owns entry format, phase routing, and dataset-catalog sync. This is a live research iteration touching subject matter, so `docs/research/14.phase6-decisions.md` gets the D1 ruling (the booking books absence, not fault) and the D4 reversal (durable verdict, after the converge-cost objection was measured false). The changelog entry goes in `docs/iterations-history-phase6.md` as `iter-141` — latest is `iter-140`; re-confirm against the file before writing.

- [ ] **Step 4: Open the PR**

Load the `open-pr` skill. Title: `feat(archive): iter-141 — a venue-silence discriminator for the residual-gap counter`. Target `develop`.

**Only on the user's explicit word** (`branch-workflow.md` PR gate, attended session). If the word has not come, report the branch ready and stop.
