# Venue-silence discriminator — implementation plan (spec `00096`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach `zcrypto archive reconcile` to say *why* it believes the fleet went dark, without changing one byte of what it books.

**Architecture:** A pure classifier (`classify_dark_episode`) lands in `cli/archive/settle.py` beside `fleet_dark_windows` and `containing_dark_window`, its neighbours in the same detector. It takes the already-computed dark windows plus each pair's per-mirror timestamps and returns a three-valued verdict. `cli/archive/command.py`'s `both_streams_silent` block calls it and widens its existing `logger.error` line. Nothing else in the booking path is touched — no ledger field, no counter, no schema change.

**Tech Stack:** Python 3.14, polars, pytest. No new dependency.

## Global Constraints

Copied verbatim from spec `00096`; every task's requirements implicitly include these.

- **The booking never changes.** `residual_gap_seconds_total` books absence of data, not fault attribution (D1). No task may alter what is booked, by how much, or when.
- **No ledger field, no new counter, no schema change** (D4). The reconcile ledger record format is untouched, so `capture-deploys.md`'s readers-before-writer converge ordering is never triggered, no Alloy keep-list edit is owed, and no admitted-metrics rule is owed.
- **`undetermined` is the fail-closed default** (D3). Bracketing events — those before the first booked window or after the last — never promote to `venue_silent`.
- **Verdict names are exactly** `venue_silent`, `capture_divergent`, `undetermined`.
- **The alert summary is operator-facing text** (D5): no `T<NNNN>`, no spec serial, no `Phase <N>`, no `iter-<N>`. `tests/test_internal_terms_not_operator_visible.py` enforces this.
- **Commit gate is `uv run pre-commit run -a`**, never `--no-verify`. Stage by explicit path, never `git add -A`.
- **Every commit ends** `Co-Authored-By: <the actual authoring model> <noreply@anthropic.com>`, and carries `Reviewed-by:` from a *different* agent before push.

## File structure

| File | Responsibility | Change |
| --- | --- | --- |
| `cli/archive/settle.py` | The dual-silence detector's primitives. Gains the classifier because its inputs are this module's own `DarkWindow` and the same per-mirror stamps `containing_dark_window` already consumes. | Modify — add `EpisodeVerdict`, `classify_dark_episode`, and the three verdict constants |
| `cli/archive/command.py` | The reconcile cycle. Calls the classifier at the existing booking site and widens the log line. | Modify — the `both_streams_silent` block only |
| `infra/grafana/alerts.yaml` | The `zcrypto-reconcile-residual-gap` rule's `summary` annotation gains the triage line. `expr`, threshold, `for`, severity, uid all unchanged. | Modify — annotation text only |
| `tests/test_archive_settle.py` | Unit tests for the classifier — all three verdicts, the true-positive, the bracket refusal. | Modify |
| `tests/test_archive_reconcile_command.py` | The regression that pins D1: the ledger record is unchanged and gains no field. | Modify |
| `docs/reference/data-catalog-full.md` | D6 — annotates 2026-08-20 where the continuity figure can be read. | Modify at closeout |
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
  - `EpisodeVerdict` — frozen dataclass, fields `verdict: str`, `interior_events: int`, `pairs_agreeing: int`, `divergent_pairs: tuple[str, ...]`
  - `classify_dark_episode(windows: Sequence[DarkWindow], mirror_stamps: Mapping[str, Mapping[str, list[datetime] | None]]) -> EpisodeVerdict`

`mirror_stamps` is keyed pair → `{"primary": [...] | None, "secondary": [...] | None}`; `None` means that mirror's segment was absent or unreadable this hour.

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
        {"BTC/EUR": {"primary": [_at(500)], "secondary": [_at(500)]}},
    )
    assert verdict.verdict == VENUE_SILENT
    assert verdict.interior_events == 1
    assert verdict.pairs_agreeing == 1
    assert verdict.divergent_pairs == ()


def test_a_mirror_that_missed_an_interior_event_is_a_capture_finding():
    # The secondary lacks what the primary got: one host missed a message the venue sent. That is
    # capture-side, and it must NEVER read as venue silence.
    verdict = classify_dark_episode(
        _episode(),
        {"BTC/EUR": {"primary": [_at(500)], "secondary": []}},
    )
    assert verdict.verdict == CAPTURE_DIVERGENT
    assert verdict.divergent_pairs == ("BTC/EUR",)


def test_divergence_on_any_pair_outranks_agreement_on_every_other():
    # Fail-closed ordering: one mirror missing one message is a finding in its own right, and must
    # not be masked by eleven other pairs agreeing.
    verdict = classify_dark_episode(
        _episode(),
        {
            "BTC/EUR": {"primary": [_at(500)], "secondary": [_at(500)]},
            "ETH/EUR": {"primary": [_at(500)], "secondary": []},
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
    assert verdict.interior_events == 0


def test_bracketing_events_never_promote_to_venue_silent():
    # D3. Both mirrors agree on the events immediately BEFORE and AFTER the episode -- which proves
    # only that both hosts were healthy either side of it. A both-host outage that self-healed
    # produces exactly this signature, so the verdict stays undetermined.
    one = [DarkWindow(start=_at(100), end=_at(1000), seconds=900.0)]
    verdict = classify_dark_episode(
        one,
        {"BTC/EUR": {"primary": [_at(50), _at(1100)], "secondary": [_at(50), _at(1100)]}},
    )
    assert verdict.verdict == UNDETERMINED


def test_a_pair_missing_a_mirror_entirely_contributes_no_evidence():
    # An unreadable/absent segment is not a divergence: there is nothing to compare against.
    verdict = classify_dark_episode(
        _episode(),
        {"BTC/EUR": {"primary": [_at(500)], "secondary": None}},
    )
    assert verdict.verdict == UNDETERMINED
    assert verdict.divergent_pairs == ()


def test_a_healthy_hour_with_no_windows_is_undetermined_and_never_classifies():
    # THE true-positive: a production-shaped healthy hour books nothing, so the classifier must not
    # manufacture a verdict. An always-classifying implementation fails here.
    verdict = classify_dark_episode([], {"BTC/EUR": {"primary": [_at(s) for s in range(0, 3600, 5)], "secondary": [_at(s) for s in range(0, 3600, 5)]}})
    assert verdict.verdict == UNDETERMINED
    assert verdict.interior_events == 0
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
    interior_events: int
    pairs_agreeing: int
    divergent_pairs: tuple[str, ...]


def classify_dark_episode(
    windows: Sequence[DarkWindow],
    mirror_stamps: Mapping[str, Mapping[str, list[datetime] | None]],
) -> EpisodeVerdict:
    """Was this episode the VENUE going quiet, or the fleet failing to record?

    The discriminator is cross-host agreement, and it is sound rather than coincidental: the capture
    writer stores Kraken's OWN message timestamp (`cli/capture/command.py` sets
    `ts = _parse_ts(entry["timestamp"])`), never local receipt time. Two independent hosts that
    receive the same message therefore record byte-identical `ts` by construction, and a host that
    was not receiving cannot manufacture one.

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
        return EpisodeVerdict(UNDETERMINED, 0, 0, ())  # nothing split the episode: no interior
    span_start, span_end = windows[0].end, windows[-1].start
    if span_start > span_end:
        return EpisodeVerdict(UNDETERMINED, 0, 0, ())  # guarded, never assumed: no span to read
    events = 0
    agreeing = 0
    divergent: list[str] = []
    for pair in sorted(mirror_stamps):
        mirrors = mirror_stamps[pair]
        primary, secondary = mirrors.get("primary"), mirrors.get("secondary")
        if primary is None or secondary is None:
            continue  # an absent or unreadable mirror is not a divergence -- there is no comparison
        inside_p = sorted(t for t in primary if span_start <= t <= span_end)
        inside_s = sorted(t for t in secondary if span_start <= t <= span_end)
        if not inside_p and not inside_s:
            continue  # this pair simply had nothing to say in the interior
        if inside_p == inside_s:
            agreeing += 1
            events += len(inside_p)
        else:
            divergent.append(pair)
    if divergent:
        return EpisodeVerdict(CAPTURE_DIVERGENT, events, agreeing, tuple(divergent))
    if agreeing:
        return EpisodeVerdict(VENUE_SILENT, events, agreeing, ())
    return EpisodeVerdict(UNDETERMINED, 0, 0, ())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_archive_settle.py -v`
Expected: PASS, including every pre-existing test in the file.

- [ ] **Step 5: Prove the guard bites**

The classifier is unproven until its defect is constructed and seen to trip it (`agent-ops.md`).

Run: `uv run bash infra/scripts/mutate-probe.sh` is not applicable here (it drives its own selection); instead run the two probes below by hand on a CLEAN tree, restoring after each.

1. Change `if span_start > span_end:` to `if False:` — expected: no test fails. That is the honest result (the guard is defensive), so **record it as an unproven defensive branch in the commit message** rather than inventing a test for a state the caller cannot produce.
2. Change `if inside_p == inside_s:` to `if True:` — expected: `test_a_mirror_that_missed_an_interior_event_is_a_capture_finding` and `test_divergence_on_any_pair_outranks_agreement_on_every_other` both FAIL. Read WHICH failure fired: it must be the verdict assertion, not a collection or import error.

Restore the file (`git checkout -- cli/archive/settle.py` only if nothing else is uncommitted; otherwise revert the edit by hand) and confirm `uv run pytest tests/test_archive_settle.py -q` is green before committing.

- [ ] **Step 6: Commit**

```bash
git add cli/archive/settle.py tests/test_archive_settle.py
git commit
```

Message: `feat(archive): classify a dark episode as venue silence or capture divergence` — body records the mutation-probe results from Step 5, including the unproven defensive branch.

---

### Task 2: Wire it into the booking block

**Files:**
- Modify: `cli/archive/command.py` — the `both_streams_silent` block only (the `logger.error` call and the lines immediately above it)
- Test: `tests/test_archive_reconcile_command.py`

**Interfaces:**
- Consumes: `classify_dark_episode` and `EpisodeVerdict` from Task 1.
- Produces: no new public name. The reconcile log line gains `verdict=`, `interior_events=`, `divergent=`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_archive_reconcile_command.py`. Follow the file's existing fixture helpers (`_ledger`, `_states`) and the shape of `test_both_streams_silent_is_ledgered_paged_and_never_minted` at line 247 for building a two-mirror hour.

```python
def test_the_verdict_reaches_the_log_and_never_the_ledger(tmp_path, monkeypatch, caplog):
    """Spec 00096 D1/D4, and this is the load-bearing regression: the booking is a CONTRACT.

    The verdict is triage. It must reach the operator's log line and leave the ledger record
    byte-identical -- no new key, and the same booked seconds -- because the counter derived from
    that record is monotonic and unwalkbackable.
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

    # (a) the record gained NO field. The key set is pinned EXACTLY, so a future ledger widening
    #     that bypasses capture-deploys.md's readers-before-writer rule turns this red.
    assert set(record) == {
        "at", "state", "pair", "kind", "hour", "pairs", "windows", "stream_windows", "residual_seconds",
    }

    # (b) the booked seconds are IDENTICAL to the single-window case in
    #     test_both_streams_silent_is_ledgered_paged_and_never_minted, even though the episode now
    #     books as two windows instead of one: BTC books 310+300 and ETH books its containing 610 s
    #     once. THAT invariance is the contract -- splitting the episode must not move the counter
    #     by a single second.
    assert record["residual_seconds"] == pytest.approx(1220.0)
    assert [w["seconds"] for w in record["windows"]] == [pytest.approx(310.0), pytest.approx(300.0)]

    # (c) the verdict IS in the log the operator reads.
    line = next(m for m in caplog.messages if "both_streams_silent" in m)
    assert "verdict=venue_silent" in line
    assert "interior_events=1" in line
```

**If `caplog` captures nothing**, the CLI has reconfigured logging under `CliRunner`. Do not weaken assertion (c) — instead `monkeypatch.setattr(command.logger, "error", recorder)` with a recorder that appends `fmt % args`, and assert on that. The log line IS the deliverable (D4 routes the verdict there and nowhere else), so a test that stops checking it has stopped testing the feature.

The three expected numbers are derived, not guessed: `dark` omits `1200 <= s < 1800` on a 10 s cadence, so the fleet-dark span runs `1190 -> 1800` (610 s) and the interior event at `1500` splits it into 310 s + 300 s. ETH, having no event at 1500, books its own containing 610 s window once. Re-derive them if you change the cadence.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_archive_reconcile_command.py::test_the_verdict_reaches_the_log_and_never_the_ledger -v`
Expected: FAIL on assertion (c) — `verdict=venue_silent` is absent from the log line. Assertions (a) and (b) must ALREADY pass, and that is the point: they are the contract this change must not break, so seeing them green before the implementation is the proof they are pinning real current behaviour rather than the new code's own output.

- [ ] **Step 3: Write the implementation**

In `cli/archive/command.py`, add `EpisodeVerdict` is not needed; import `classify_dark_episode` into the existing `from cli.archive.settle import (...)` block alongside `containing_dark_window` and `fleet_dark_windows`.

Immediately before the existing `logger.error("archive reconcile: both_streams_silent ...")` call, insert:

```python
                # TRIAGE ONLY -- never an input to the booking below (spec 00096 D1). The mirrors'
                # frames are already in hand from the read above, so this costs no I/O.
                episode = classify_dark_episode(
                    windows,
                    {
                        p: {src: (None if f is None else f["ts"].to_list()) for src, f in books[p].items()}
                        for p in present
                    },
                )
```

and widen the log call to:

```python
                logger.error(
                    "archive reconcile: both_streams_silent hour=%s windows=%d residual_s=%.1f verdict=%s interior_events=%d divergent=%s",
                    hour.isoformat(),
                    len(windows),
                    residual,
                    episode.verdict,
                    episode.interior_events,
                    ",".join(episode.divergent_pairs) or "-",
                )
```

Change nothing else. The `_ledger(...)` call that follows keeps its exact argument list.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_archive_reconcile_command.py -v`
Expected: PASS, including every pre-existing test in the file — particularly `test_a_fleet_dark_window_is_never_booked_as_loss_twice` and `test_one_pair_going_quiet_alone_is_never_both_streams_silent`.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: all pass. Budget ~7 min 30 s — `data/ohlc-full` is present, so the data-dependent regression tests run.

- [ ] **Step 6: Commit**

```bash
git add cli/archive/command.py tests/test_archive_reconcile_command.py
git commit
```

Message: `feat(archive): log the dark-episode verdict without touching the booking`

---

### Task 3: The alert triage line

**Files:**
- Modify: `infra/grafana/alerts.yaml` — `uid: zcrypto-reconcile-residual-gap`, `annotations.summary` only
- Test: `tests/test_internal_terms_not_operator_visible.py` (existing; no edit — it must keep passing)

**Interfaces:** none. Text change.

- [ ] **Step 1: Edit the summary**

Replace the `summary:` value of the `zcrypto-reconcile-residual-gap` rule with:

```yaml
      summary: "Permanent L2 loss: silence that NEITHER capture host covered. This cannot be healed or backfilled -- the data is gone. Check the reconcile ledger for the records behind it: both_streams_silent or total_loss for correlated loss, or a minted/would_mint hour whose splice left seconds unfilled -- any of the three can drive this. TRIAGE FIRST: the reconcile log line for that hour carries a verdict. venue_silent means both capture hosts recorded the same venue timestamps through the window, so the venue went quiet and no data was lost -- the counter books absence, not fault. capture_divergent means one host missed what the other got: investigate the fleet. undetermined means the evidence cannot tell them apart; treat it as loss."
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

### Task 5: Attended verification against the real event

> **MAIN LOOP ONLY — do not dispatch this to a subagent or a workflow.** It reads a NAS/host copy of the capture tree, and the permission gate blocks ssh/sudo steps inside a subagent, where the prompt dies unseen (`agent-ops.md`). There is no local `capture-segments` tree — verified 2026-08-20.

- [ ] **Step 1: Replay hour 07 of 2026-08-20**

On a **pulled copy**, never the live capture dir. Run the reconcile cycle over that hour and read the log line.
Expected: `verdict=venue_silent`, and the booked residual reproduces **6251.35 s** at full precision. Reproduce the number from the data — do not quote it from the topic (`agent-ops.md`).

If the verdict reads `undetermined`, that is a finding, not a failure to route around: it means the episode booked as a single window with no interior split, and D3's default fired correctly. Report it and stop — the spec's central example would then not be covered by its own discriminator, which is a verdict on the design's shape.

- [ ] **Step 2: Converge, then push the rule, then verify by value**

Order is fixed by `capture-deploys.md`: converge → push → verify the value. `zcrypto-ops` is the compute tier, so `--limit zcrypto-ops` is mandatory, `converge.sh` previews first, and no canary bake is owed. Record the running digest in `docs/reference/fleet-pins.md` **before** converging — the pins assert refuses otherwise.

Then `infra/scripts/grafana-push.sh`, and confirm the rule is **evaluating** — read the value, never mere presence. No prune is owed (Task 3, Step 1).

---

### Task 6: Closeout

> Authored **now**, at the branch's end — never pre-written during planning (`iterations-history.md`). Re-verify every status claim against the full branch log immediately before PR-open.

- [ ] **Step 1: D6 — annotate 2026-08-20 where its numbers are read**

`docs/reference/data-catalog-full.md`: the venue-quiet window explains the day's continuity figure, so a later reader does not diagnose a capture regression that did not happen. Rewrite the narrative in place; never append a retraction (`agent-ops.md`). The per-event evidence — timestamps, counter values, the booking tick — goes in **this commit's message**, not in the living doc (`docs-style.md`).

- [ ] **Step 2: T0143 → `resolved`**

Load the `topic-ops` skill first; it owns serials, the `## Done so far` move, archive moves, and index sync. The whole topic update — `status`, `ripe_when`, `## Done so far`, and removal of the finished next-steps — lands in **this** PR (`open-topics.md`).

- [ ] **Step 3: Decisions-log + changelog entries**

Load the `iteration-closeout` skill first; it owns entry format, phase routing, and dataset-catalog sync. This is a live research iteration touching subject matter, so `docs/research/14.phase6-decisions.md` gets the D1 ruling. The changelog entry goes in `docs/iterations-history-phase6.md` as `iter-141` (latest is `iter-140` — re-confirm against the file before writing).

- [ ] **Step 4: Open the PR**

Load the `open-pr` skill. Title: `feat(archive): iter-141 — a venue-silence discriminator for the residual-gap counter`. Target `develop`.

**Only on the user's explicit word** (`branch-workflow.md` PR gate, attended session). If the word has not come, report the branch ready and stop.
