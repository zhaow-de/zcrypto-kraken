# A venue halt the two mirrors prove lost nothing is booked as a halt, never as permanent L2 loss Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `both_streams_silent` hour whose two mirrors prove the venue halted its books — every booked stream carried through on a host with no resync snapshot after the silence, and nothing traded across it — books `verdict` `venue_halt` and its seconds to a new `zcrypto_reconcile_venue_halt_seconds_total`, none to the residual counter, logs a WARNING, and pages nothing; every other silence books and pages as today.

**Architecture:** A pure `classify_halt` in `cli/archive/settle.py` returns a `HaltEvidence` from the fleet windows, the stream windows, both mirrors' `(ts, type)` book rows and both mirrors' `(ts, trade_id)` trade tapes (spec D2–D4). The booking block in `cli/archive/command.py` reads the hour's trade tapes through a new `_tape`, sets the verdict to `venue_halt` when the evidence holds and the mirrors do not diverge (D5), writes `residual_seconds` 0.0 and `halt_seconds` with four evidence fields on the record (D6), logs a WARNING for a halt (D8), and `_totals` sums `halt_seconds` into the new counter, which panel 206 charts (D7). The page's summary, the runbooks, the README and the hygiene map are re-trued from the spec's *Runbook and alert texts*; the decisions log takes three `[00163]` entries.

**Tech Stack:** Python 3.14, polars, pytest, `infra/scripts/mutate-probe.sh`.

**Spec:** `docs/specs/00163-venue-halt-not-loss-design.md`

**Tier** — `uv run python infra/scripts/tier.py --paths cli/archive/settle.py cli/archive/command.py tests/test_archive_settle.py tests/test_archive_reconcile_command.py infra/grafana/data-integrity-dashboard.json infra/grafana/alerts.yaml tests/test_infra_alert_rules.py infra/runbooks/ops.md infra/runbooks/capture.md README.md docs/reference/capture-era-data-hygiene-map.md docs/research/14.phase6-decisions.md`, run at `6795cd513` and again at `bee7f06f4`, the spec's fix, with the same output:

```
tier: full
full tests/test_archive_settle.py — a test importing cli.capture.errors, read as a non-prose change
full tests/test_archive_reconcile_command.py — a test importing cli.capture.segment_writer, read as a non-prose change
full infra/grafana/alerts.yaml — under infra/grafana/alerts.yaml, read as a non-prose change
full tests/test_infra_alert_rules.py — a test importing cli.engine.store, read as a non-prose change
```

Every fence below was run against `6795cd513` in the detached scratch worktree `.tmp/r00163/inputs/scripts/wt`, the plan's code applied and committed there, never pushed. Each task's tree read its per-commit run green: Task 1 `245 passed`, Task 2 `984 passed, 44 warnings`, Task 3 `1 failed, 2033 passed, 2 skipped` and Task 4 `1 failed, 4804 passed, 1 deselected`, the one failure in each being `tests/test_ops_daily.py::test_the_deploy_log_is_the_main_checkouts_where_a_worktree_runs_the_pass`, which fails on `6795cd513` under an in-repository `--basetemp` too; Task 5's `1113 passed`; Task 6's `50 passed`. The red readings: Task 1's test file on `6795cd513` reads `ImportError: cannot import name 'RESUME_MARGIN_SECONDS'`, Task 2's thirteen cases on Task 1's tree `11 failed, 2 passed`, Task 3's case on Task 2's tree `1 failed`. Every probe arm the tasks list read `KILLED (control proven, tree restored byte-identically)`. Task 3's, 4's and 5's text fences, run on `6795cd513` against the committed spec, left `alerts.yaml`, both runbook pages, the README and the hygiene map byte-identical to the scratch tree's, which had passed the repository's commit hooks, `guidance-guard` and `mdformat` among them.

## Global Constraints

- The spec, `docs/specs/00163-venue-halt-not-loss-design.md`, is the authority, and a task that names one of its sections reads it there; where it is silent this plan rules, in *Rulings where the spec is silent*.
- No task converges, builds an image, pushes or calls an endpoint; no task runs `infra/scripts/grafana-push.sh` or `tests/test_grafana_push_sh.py`, which drives that script — a reader of `infra/grafana/alerts.yaml` left out of Task 3's run, the PR body naming it as not run. No task reads the NAS mirrors or the ops ledger: the spec's *The measured basis* is the real-data reading, the cases below the proof. No task touches `.claude/`.
- The worktree is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/reconciler-halt` (branch `fix/00163-reconciler-venue-halt-not-loss`); every command runs with it as the working directory, and git takes `-C` that path. The main checkout is live.
- Before Task 1's first command, `mkdir -p .tmp/implementer .local/venue-halt-not-loss`, its own call: every pytest run takes `--basetemp=.tmp/implementer/pt`.
- Tests per commit: `infra/scripts/consumers.sh --tests --direct <the commit's changed paths> 2>.tmp/implementer/cons.err >.tmp/implementer/cons.list`, its own call, exit 2 meaning no reader; `cat .tmp/implementer/cons.err`, its own call; then `T="$(sort -u .tmp/implementer/cons.list | grep -v '^tests/test_grafana_push_sh.py$' | tr '\n' ' ') <the task's test files>"; uv run pytest $T -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rf`. Never the full suite. `tests/test_ops_daily.py::test_the_deploy_log_is_the_main_checkouts_where_a_worktree_runs_the_pass` reads the repository enclosing its temporary directory and fails under an in-repository `--basetemp` on `6795cd513` as on the branch; a commit whose run holds it names it beside its result line.
- The gate is `uv run pre-commit run -a`, re-run until clean, its rewrites staged; stage a new file before the gate, which reads tracked files only.
- A comment or docstring stays only where a reader would act differently without it, and is correct. The alert texts, the runbook pages, the README and every string literal under `cli/` carry no `spec <NNNNN>`, `D<N>`, `T<NNNN>`, `iter-<N>`, `Phase <N>` or `WP<N>` token (`tests/test_internal_terms_not_operator_visible.py`); the fences below carry none.
- Commits: Conventional Commits, after a `git -C <the worktree> add <every path the commit changes>` of its own, through `git -C <the worktree> commit -F - <<'EOF'`; the message says what changed and pastes the result line of the test command it names, run over the commit's own tree; one state-changing git command per Bash call; never an amend, `--no-verify` or `git stash`; every message ends with `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>`, the implementer's own model in place of the placeholder, and `Claude-Session: https://claude.ai/code/session_018eFiE9ZzjweN7A4N9yBCTV`.
- Probes (this plan's tier is `full`): each arm a task lists runs as its own call on the committed tree, `infra/scripts/mutate-probe.sh --file <file> --control '1,$d' --mutation '<mutation>' -- uv run pytest <test file> -k '<selection>' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`. Before each arm, its own call, `grep -c -- '<pattern>' <file>` reads `1` for every pattern its mutation names, the pattern being the mutation's left side. `: > .local/venue-halt-not-loss/probes-task-<N>.txt` before a task's arms; after each arm its id and the script's last line are appended, its own call. A task's verdicts ride an empty commit through `git -C <the worktree> commit --allow-empty -F - <<'EOF'`, the subject the task names, its body the probes file pasted whole, then the trailers; it names no test run, the verdicts being its result.

## Rulings where the spec is silent

- **What a task writes is in the task verbatim or in the spec's *Runbook and alert texts*, which Tasks 3–5 apply with their own fences, so the spec's copy is the one copy.** The code below is the code the scratch tree ran; a fence's layout is `ruff format`'s.
- **Placement.** `VENUE_HALT`, `RESUME_MARGIN_SECONDS`, `HaltEvidence` and `classify_halt` directly after `classify_dark_episode` in `cli/archive/settle.py`; `_tape` directly above `_fail` inside `reconcile`; Task 1's cases directly before the `# --- the int64-microsecond derivation` banner of `tests/test_archive_settle.py`; Task 2's helpers and cases directly before the `# --- the settled-hour skip cache` banner of `tests/test_archive_reconcile_command.py`; Task 3's case directly after `test_the_permanent_loss_page_outlives_a_single_evaluation_hour`.
- **The verdict string is `"venue_halt"` in `settle.py` alone**; `command.py` imports `VENUE_HALT` and `CAPTURE_DIVERGENT` from it.
- **`ALGO_VERSION` stays `1`** (spec D13).

## File structure

- Modify `cli/archive/settle.py`: the module docstring's and `fleet_dark_windows`' docstring's halt sentence; `VENUE_HALT`, `RESUME_MARGIN_SECONDS`, `HaltEvidence`, `classify_halt`.
- Modify `cli/archive/command.py`: the settle imports; `_MINT_FAMILY`'s comment and `_booked_dark`'s docstring line; `_totals`; the residual and dark-episode help texts and the `venue_halt_seconds_total` emit; `_tape`; the booking block.
- Modify `infra/grafana/data-integrity-dashboard.json`: panel 206's description and target `D`.
- Modify `infra/grafana/alerts.yaml`: `zcrypto-reconcile-residual-gap`'s comment line and summary opening.
- Modify `tests/test_archive_settle.py`, `tests/test_archive_reconcile_command.py`, `tests/test_infra_alert_rules.py`.
- Modify `infra/runbooks/ops.md`, `infra/runbooks/capture.md`, `README.md`, `docs/reference/capture-era-data-hygiene-map.md`, `docs/research/14.phase6-decisions.md`.

## Review Focus

1. Prints sharing one Kraken stamp on either side of a window — one taker order against several makers — must bracket it by their ids, not read as a hole. Pinned by Task 1's `test_prints_sharing_a_stamp_bracket_a_window_by_their_ids` (the real hour's DOGE/EUR shape, spec *The measured basis*).
2. A host that reconnects later in the same hour, after the halt — 2026-11-17's secondary — leaves the other host to carry every stream. Pinned by Task 1's `test_one_mirror_carrying_the_stream_is_enough`, both parametrisations.
3. A halt that resumes near the hour's end: at exactly 300 s before it the stream is carried, at 299 s it is not, and with no resume in the hour it is not. Pinned by Task 1's `test_a_resume_inside_the_hours_last_margin_is_not_carried` and `test_a_window_running_to_the_hours_end_is_not_carried`.
4. An unreadable trades segment on both hosts is no trade evidence: the hour books as loss, the cycle still decides it, and the WARNING names each mirror. Pinned by Task 2's `test_an_unreadable_trades_segment_is_no_trade_evidence_and_the_hour_books_as_loss`.
5. A ledger written before the change, and an image that predates the verdict reading one written after it: the decided hour stays booked, and a `venue_halt` record books 0.0 as residual. Pinned by Task 2's `test_an_hour_booked_before_the_halt_verdict_stays_booked_as_it_was`, `test_the_totals_book_a_halt_beside_the_loss_and_never_inside_it` and `test_a_venue_halt_books_its_seconds_to_the_halt_counter_and_none_as_loss`'s `residual_seconds == 0.0`, beside the existing `test_an_unrecognized_verdict_string_counts_as_undetermined_not_a_crash`.

---

### Task 1: `classify_halt` reads, from the two mirrors, whether a fleet-dark hour was the venue halting its books

**Files:**
- Modify: `cli/archive/settle.py:10-13` (module docstring), `:176-181` (`fleet_dark_windows`' docstring), after `:360` (the new block)
- Test: `tests/test_archive_settle.py`

**Interfaces:**
- Consumes: `DarkWindow` (`cli/archive/settle.py:158-164`).
- Produces: `VENUE_HALT: str = "venue_halt"`; `RESUME_MARGIN_SECONDS: float = 300.0`; `HaltEvidence(streams: int, streams_carried: int, windows: int, windows_bracketed: int, trades_inside: int, id_holes: int)`, frozen, with the property `holds -> bool`; `classify_halt(windows: Sequence[DarkWindow], stream_windows: Mapping[str, Sequence[DarkWindow]], book_rows: Mapping[str, Mapping[str, list[tuple[datetime, str]] | None]], trade_rows: Mapping[str, Mapping[str, list[tuple[datetime, int]] | None]], *, hour_end: datetime) -> HaltEvidence`.

- [ ] **Step 1: Write the failing tests.** In the import block from `cli.archive.settle`, add `RESUME_MARGIN_SECONDS,` after `LATE_MINT_HOURS,`, `HaltEvidence,` after `EpisodeVerdict,`, and `classify_halt,` after `classify_dark_episode,`. Then, directly before the `# --- the int64-microsecond derivation (spec 00097 D3)` banner:

```python
# --- the venue halt: the book carried through, and nothing traded --------------------------------

_HALT = DarkWindow(start=_at(600), end=_at(1200), seconds=600.0)
_PAIRS = ("BTC/EUR", "ETH/EUR")


def _carried_rows() -> list[tuple[datetime, str]]:
    """A stream silent from 600 s to 1200 s and updating every 10 s either side of it."""
    return [(_at(s), "update") for s in range(0, 3600, 10) if not 600 < s < 1200]


def _bracketing_tape() -> list[tuple[datetime, int]]:
    """BTC/EUR's last print before the window and its first after it, adjacent ids."""
    return [(_at(590), 7), (_at(1210), 8)]


def _halt_evidence(book=None, trades=None, *, windows=(_HALT,)) -> HaltEvidence:
    book = book if book is not None else {p: {"primary": _carried_rows(), "secondary": _carried_rows()} for p in _PAIRS}
    trades = (
        trades
        if trades is not None
        else {
            "BTC/EUR": {"primary": _bracketing_tape(), "secondary": _bracketing_tape()},
            "ETH/EUR": {"primary": [], "secondary": []},
        }
    )
    return classify_halt(list(windows), {p: list(windows) for p in book}, book, trades, hour_end=HOUR_END)


def test_a_book_carried_through_a_window_no_pair_traded_across_is_a_halt():
    evidence = _halt_evidence()
    assert evidence == HaltEvidence(streams=2, streams_carried=2, windows=1, windows_bracketed=1, trades_inside=0, id_holes=0)
    assert evidence.holds


@pytest.mark.parametrize("at", [600, 1200, 3000], ids=["at-the-windows-start", "at-the-resume", "later-in-the-hour"])
def test_a_snapshot_from_the_window_on_on_every_mirror_leaves_the_stream_not_carried(at):
    rows = sorted([*_carried_rows(), (_at(at), "snapshot")])
    book = {
        "BTC/EUR": {"primary": rows, "secondary": list(rows)},
        "ETH/EUR": {"primary": _carried_rows(), "secondary": _carried_rows()},
    }
    evidence = _halt_evidence(book)
    assert evidence.streams_carried == 1
    assert not evidence.holds


def test_a_snapshot_before_the_window_leaves_the_stream_carried():
    rows = sorted([*_carried_rows(), (_at(300), "snapshot")])
    book = {
        "BTC/EUR": {"primary": rows, "secondary": list(rows)},
        "ETH/EUR": {"primary": _carried_rows(), "secondary": _carried_rows()},
    }
    assert _halt_evidence(book).holds


@pytest.mark.parametrize("snapshotted", ["primary", "secondary"])
def test_one_mirror_carrying_the_stream_is_enough(snapshotted):
    rows = {"primary": _carried_rows(), "secondary": _carried_rows()}
    rows[snapshotted] = sorted([*rows[snapshotted], (_at(3000), "snapshot")])
    evidence = _halt_evidence({"BTC/EUR": rows, "ETH/EUR": {"primary": _carried_rows(), "secondary": _carried_rows()}})
    assert evidence.streams_carried == 2
    assert evidence.holds


@pytest.mark.parametrize(("resume", "carried"), [(3600 - RESUME_MARGIN_SECONDS, True), (3600 - RESUME_MARGIN_SECONDS + 1, False)])
def test_a_resume_inside_the_hours_last_margin_is_not_carried(resume, carried):
    late = DarkWindow(start=_at(3000), end=_at(resume), seconds=resume - 3000.0)
    rows = [*[(_at(s), "update") for s in range(0, 3001, 10)], (_at(resume), "update"), (_at(3590), "update")]
    book = {p: {"primary": rows, "secondary": list(rows)} for p in _PAIRS}
    tape = [(_at(2990), 7), (_at(3595), 8)]
    evidence = _halt_evidence(book, {"BTC/EUR": {"primary": tape, "secondary": tape}}, windows=(late,))
    assert evidence.holds is carried
    assert evidence.streams_carried == (2 if carried else 0)


def test_a_window_running_to_the_hours_end_is_not_carried():
    tail = DarkWindow(start=_at(3000), end=HOUR_END, seconds=600.0)
    rows = [(_at(s), "update") for s in range(0, 3001, 10)]
    book = {p: {"primary": rows, "secondary": list(rows)} for p in _PAIRS}
    evidence = _halt_evidence(book, windows=(tail,))
    assert evidence.streams_carried == 0
    assert not evidence.holds


def test_a_stream_no_mirror_holds_is_not_carried():
    book = {"BTC/EUR": {"primary": None, "secondary": None}, "ETH/EUR": {"primary": _carried_rows(), "secondary": _carried_rows()}}
    evidence = _halt_evidence(book)
    assert evidence.streams_carried == 1
    assert not evidence.holds


def test_no_stream_booked_is_no_halt():
    evidence = classify_halt(
        [_HALT], {}, {}, {"BTC/EUR": {"primary": _bracketing_tape(), "secondary": _bracketing_tape()}}, hour_end=HOUR_END
    )
    assert (evidence.streams, evidence.windows_bracketed) == (0, 1)
    assert not evidence.holds


def test_a_trade_inside_a_window_is_not_a_halt():
    tape = [(_at(590), 7), (_at(900), 8), (_at(1210), 9)]
    evidence = _halt_evidence(trades={"BTC/EUR": {"primary": tape, "secondary": tape}})
    assert evidence.trades_inside == 1
    assert not evidence.holds


def test_a_trade_id_neither_mirror_holds_across_a_window_is_not_a_halt():
    tape = [(_at(590), 7), (_at(1210), 9)]
    evidence = _halt_evidence(trades={"BTC/EUR": {"primary": tape, "secondary": tape}})
    assert (evidence.trades_inside, evidence.id_holes, evidence.windows_bracketed) == (0, 1, 0)
    assert not evidence.holds


def test_the_two_mirrors_trade_tapes_are_read_as_one():
    evidence = _halt_evidence(trades={"BTC/EUR": {"primary": [(_at(590), 7), (_at(1210), 9)], "secondary": [(_at(595), 8)]}})
    assert (evidence.id_holes, evidence.windows_bracketed) == (0, 1)
    assert evidence.holds


def test_prints_sharing_a_stamp_bracket_a_window_by_their_ids():
    tape = [(_at(590), 6), (_at(590), 7), (_at(1210), 8), (_at(1210), 9)]
    evidence = _halt_evidence(trades={"BTC/EUR": {"primary": tape, "secondary": tape}})
    assert (evidence.id_holes, evidence.windows_bracketed) == (0, 1)
    assert evidence.holds


@pytest.mark.parametrize(
    "tape",
    [[], [(_at(590), 7)], [(_at(1210), 8)]],
    ids=["no-trade", "a-print-before-only", "a-print-after-only"],
)
def test_a_window_no_pair_brackets_is_not_a_halt(tape):
    evidence = _halt_evidence(trades={"BTC/EUR": {"primary": tape, "secondary": tape}})
    assert evidence.windows_bracketed == 0
    assert not evidence.holds


def test_every_window_needs_its_own_bracket():
    first, second = (
        DarkWindow(start=_at(600), end=_at(900), seconds=300.0),
        DarkWindow(start=_at(1500), end=_at(1800), seconds=300.0),
    )
    rows = [(_at(s), "update") for s in range(0, 3600, 10) if not (600 < s < 900 or 1500 < s < 1800)]
    book = {p: {"primary": rows, "secondary": list(rows)} for p in _PAIRS}
    tape = [(_at(590), 7), (_at(910), 8)]
    evidence = _halt_evidence(book, {"BTC/EUR": {"primary": tape, "secondary": tape}}, windows=(first, second))
    assert (evidence.windows, evidence.windows_bracketed) == (2, 1)
    assert not evidence.holds
```

- [ ] **Step 2: Run them red.** `uv run pytest tests/test_archive_settle.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`. Expected: `1 error during collection`, `ImportError: cannot import name 'RESUME_MARGIN_SECONDS' from 'cli.archive.settle'`.

- [ ] **Step 3: Implement.** In the module docstring, the line `spliced: the data is gone. They are ledgered, booked into \`residual_gap_seconds_total\`, and paged.` becomes the two lines:

```python
spliced: there is no witness. They are ledgered, booked into `residual_gap_seconds_total`, and paged,
but for a venue halt `classify_halt` proves the book carried through, which books to its own counter.
```

In `fleet_dark_windows`' docstring, the lines `    has no benign explanation, and it is loss. A per-pair silence *count* carries no window and cannot` and `    tell the two apart, so it would page on the benign one.` read:

```python
    is loss or the venue halting its books, which `classify_halt` tells apart. A per-pair silence *count*
    carries no window and cannot tell the two apart, so it would page on the benign one.
```

Directly after `classify_dark_episode`'s `return EpisodeVerdict(verdict, updates, snapshots, interior_seconds, agreeing, skipped, tuple(divergent))`, two blank lines, then:

```python
VENUE_HALT = "venue_halt"

# A resync's snapshot follows the update that tripped it within the desync ladder's span -- the transition
# resubscribe at once, retries at 20, 25 and 35 s, the reconnect rung at 55 s (`cli/capture/desync_recovery.py`)
# -- and that update can reach capture late. A stream that resumes later than this before the hour's end
# could carry its snapshot into the next hour, which no examination of this hour reads.
RESUME_MARGIN_SECONDS = 300.0


@dataclass(frozen=True)
class HaltEvidence:
    """Whether a fleet-dark hour was the venue halting its books, and the counts that say why.

    Unlike `EpisodeVerdict` this IS an input to the booking: when it holds, the hour's seconds book to the
    halt counter and none to `residual_gap_seconds_total`.
    """

    streams: int
    streams_carried: int
    windows: int
    windows_bracketed: int
    trades_inside: int
    id_holes: int

    @property
    def holds(self) -> bool:
        return (
            self.streams > 0
            and self.streams_carried == self.streams
            and self.windows_bracketed == self.windows
            and self.trades_inside == 0
            and self.id_holes == 0
        )


def classify_halt(
    windows: Sequence[DarkWindow],
    stream_windows: Mapping[str, Sequence[DarkWindow]],
    book_rows: Mapping[str, Mapping[str, list[tuple[datetime, str]] | None]],
    trade_rows: Mapping[str, Mapping[str, list[tuple[datetime, int]] | None]],
    *,
    hour_end: datetime,
) -> HaltEvidence:
    """Did the venue halt its books across `windows`, losing nothing, or is the silence unproven?

    Two proofs, both from the mirrors alone, and both must hold:

      * **The book carried through.** Every booked stream has a mirror on which no `snapshot` row lands from
        its first window's start to the hour's end, and which resumes after each window no later than
        `RESUME_MARGIN_SECONDS` before that end. Capture checks every update's CRC against the book it
        carries and resubscribes on a mismatch, and a resubscribe or a reconnect writes a snapshot, so a
        resume with none after it is Kraken's own checksum accepting the book carried across the silence.
        That is the archive's standing ranks-1-10 attestation, no more: a change below rank 10 is outside it.
      * **Nothing traded.** No trade on either mirror inside a window, every pair's trade ids step by
        exactly one across each window they bracket, and some pair brackets every window. A writer that
        dropped rows while capture kept reading leaves the CRC whole, and this is what sees it.

    A stream is `book_rows[pair]`'s mirrors; `trade_rows[pair]`'s two tapes are unioned by trade id.
    """
    margin = timedelta(seconds=RESUME_MARGIN_SECONDS)

    def carried(rows: list[tuple[datetime, str]] | None, own: Sequence[DarkWindow]) -> bool:
        if rows is None or not own:
            return False
        first = min(w.start for w in own)
        if any(kind != "update" for ts, kind in rows if ts >= first):
            return False
        for w in own:
            resumed = [ts for ts, _ in rows if ts >= w.end]
            if not resumed or min(resumed) > hour_end - margin:
                return False
        return True

    carried_streams = sum(
        1 for pair, own in stream_windows.items() if any(carried(rows, own) for rows in (book_rows.get(pair) or {}).values())
    )

    bracketed: set[int] = set()
    inside = holes = 0
    for pair in sorted(trade_rows):
        first_seen: dict[int, datetime] = {}
        for rows in trade_rows[pair].values():
            for ts, trade_id in rows or ():
                first_seen.setdefault(trade_id, ts)
        tape = sorted((ts, trade_id) for trade_id, ts in first_seen.items())
        for i, w in enumerate(windows):
            inside += sum(1 for ts, _ in tape if w.start < ts < w.end)
            before = [t for t in tape if t[0] <= w.start]
            after = [t for t in tape if t[0] >= w.end]
            if before and after:
                if after[0][1] - before[-1][1] == 1:
                    bracketed.add(i)
                else:
                    holes += 1
    return HaltEvidence(
        streams=len(stream_windows),
        streams_carried=carried_streams,
        windows=len(windows),
        windows_bracketed=len(bracketed),
        trades_inside=inside,
        id_holes=holes,
    )
```

- [ ] **Step 4: Run them green.** `uv run pytest tests/test_archive_settle.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`. Expected: `91 passed`.

- [ ] **Step 5: Commit** `fix(archive): classify_halt reads from the two mirrors whether a fleet-dark hour was the venue halting its books`, after the per-commit run over `cli/archive/settle.py tests/test_archive_settle.py` (its readers `tests/test_archive_reader.py tests/test_archive_reconcile.py tests/test_archive_reconcile_command.py tests/test_archive_scan_cache.py tests/test_archive_settle.py tests/test_continuity_overlay.py`; expected `245 passed`) and the gate, the run's result line in the body.

- [ ] **Step 6: Probe, then commit the verdicts** under `test(archive): classify_halt's cases proven by infra/scripts/mutate-probe.sh`. File `cli/archive/settle.py`, test file `tests/test_archive_settle.py`:

| Id | Selection (`-k`) | Mutation |
|---|---|---|
| 1a | `snapshot_from_the_window_on` | `s/if any(kind != "update" for ts, kind in rows if ts >= first):/if False:/` |
| 1b | `at-the-windows-start` | `s/for ts, kind in rows if ts >= first)/for ts, kind in rows if ts > first)/` |
| 1c | `snapshot_before_the_window` | `s/for ts, kind in rows if ts >= first)/for ts, kind in rows)/` |
| 1d | `resume_inside_the_hours_last_margin` | `s/min(resumed) > hour_end - margin/min(resumed) > hour_end/` |
| 1e | `resume_inside_the_hours_last_margin` | `s/min(resumed) > hour_end - margin/min(resumed) >= hour_end - margin/` |
| 1f | `running_to_the_hours_end` | `s/if not resumed or min(resumed) > hour_end - margin:/if resumed and min(resumed) > hour_end - margin:/` |
| 1g | `one_mirror_carrying` | `s/if any(carried(rows, own) for rows/if all(carried(rows, own) for rows/` |
| 1h | `trade_inside_a_window` | `s/inside += sum(1 for ts, _ in tape if w.start < ts < w.end)/inside += 0/` |
| 1i | `trade_id_neither_mirror` | `s/if after\[0\]\[1\] - before\[-1\]\[1\] == 1:/if True:/` |
| 1j | `read_as_one` | `s/for rows in trade_rows\[pair\].values():/for rows in list(trade_rows[pair].values())[:1]:/` |
| 1k | `no_pair_brackets or every_window_needs` | `s/and self.windows_bracketed == self.windows$/and True/` |
| 1l | `no_mirror_holds or snapshot_from_the_window_on` | `s/and self.streams_carried == self.streams$/and True/` |
| 1m | `no_stream_booked` | `s/self.streams > 0$/True/` |
| 1n | `carried_through_a_window_no_pair_traded` | `s/                    bracketed.add(i)/                    pass/` |
| 1o | `sharing_a_stamp` | `s/tape = sorted((ts, trade_id) for trade_id, ts in first_seen.items())/tape = sorted(((ts, trade_id) for trade_id, ts in first_seen.items()), key=lambda t: (t[0], -t[1]))/` |

### Task 2: A venue halt the mirrors prove books to `venue_halt_seconds_total`, never as loss

**Files:**
- Modify: `cli/archive/command.py:47-58` (imports), `:73-76`, `:289`, `:368-444` (`_totals`), `:539-563` and after `:563` (`_write_textfile`), above `:729` (`_tape`), `:850-895` (the booking block)
- Modify: `infra/grafana/data-integrity-dashboard.json:1617`, `:1650-1655` (panel 206)
- Test: `tests/test_archive_reconcile_command.py`

**Interfaces:**
- Consumes: `VENUE_HALT`, `CAPTURE_DIVERGENT`, `classify_halt`, `HaltEvidence.holds` and its fields (Task 1).
- Produces: the record keys `halt_seconds`, `streams_carried`, `windows_bracketed`, `trades_inside`, `trade_id_holes`; `_totals(...)["venue_halt_seconds"]`; the series `zcrypto_reconcile_venue_halt_seconds_total` (Task 3's case reads it through `published_app_families()`).

- [ ] **Step 1: Write the failing tests.** In `test_the_textfile_carries_every_series_and_is_written_atomically`'s set, add `"zcrypto_reconcile_venue_halt_seconds_total",` after the `verdict="undetermined"` member; in the hand-built totals of `test_infinite_source_lag_is_emitted_as_prometheus_plus_inf` and `test_textfile_publishes_the_ledger_record_count`, add `"venue_halt_seconds",` after `"dark_undetermined",`; in `test_the_verdict_is_recorded_and_counted_while_the_booking_is_untouched`'s pinned key set, add after `"divergent_pairs",`:

```python
        "halt_seconds",
        "streams_carried",
        "windows_bracketed",
        "trades_inside",
        "trade_id_holes",
```

Then, directly before the `# --- the settled-hour skip cache (spec 00097 D4/D5)` banner:

```python
# --- the venue halt: booked as a halt, never as loss --------------------------------------------

# Every pair on both hosts silent from 1190 s to 1800 s: one fleet-dark window, 610 s a stream, 1220 s booked.
_DARK = [(float(s), "update") for s in range(0, 3600, 10) if not 1200 <= s < 1800]


def _prints(pair: str, hour: datetime, prints: list[tuple[float, int]]) -> pl.DataFrame:
    """`prints` is [(offset_seconds, trade_id)]."""
    frame = _trades(pair, hour, [trade_id for _, trade_id in prints])
    return frame.with_columns(pl.Series("ts", [hour + timedelta(seconds=o) for o, _ in prints], dtype=TRADE_SCHEMA["ts"]))


def _plant_halt(pri: Path, sec: Path, *, btc_book=_DARK, btc_prints=((1185.0, 7), (1805.0, 8))) -> None:
    """Both pairs dark on both hosts; BTC/EUR's book and prints as given, ETH/EUR's prints none."""
    for root in (pri, sec):
        _write(root, "ETH/EUR", "book", H, _book("ETH/EUR", H, _DARK))
        _write(root, "BTC/EUR", "book", H, _book("BTC/EUR", H, list(btc_book)))
        _write(root, "BTC/EUR", "trades", H, _prints("BTC/EUR", H, list(btc_prints)))


def _capture_logs(monkeypatch) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    monkeypatch.setattr(command.logger, "error", lambda fmt, *a, **k: errors.append(fmt % a))
    monkeypatch.setattr(command.logger, "warning", lambda fmt, *a, **k: warnings.append(fmt % a))
    return errors, warnings


def test_a_venue_halt_books_its_seconds_to_the_halt_counter_and_none_as_loss(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _plant_halt(pri, sec)
    errors, warnings = _capture_logs(monkeypatch)
    textfile = tmp_path / "reconcile.prom"

    result = _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(textfile)], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    [record] = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    assert record["verdict"] == "venue_halt"
    assert record["residual_seconds"] == 0.0
    assert record["halt_seconds"] == pytest.approx(1220.0)
    assert (record["streams_carried"], record["windows_bracketed"], record["trades_inside"], record["trade_id_holes"]) == (
        2,
        1,
        0,
        0,
    )
    series = _series(textfile)
    assert series["zcrypto_reconcile_residual_gap_seconds_total"] == 0.0
    assert series["zcrypto_reconcile_venue_halt_seconds_total"] == pytest.approx(1220.0)
    assert sum(v for k, v in series.items() if k.startswith("zcrypto_reconcile_dark_episode_seconds_total{")) == 0.0
    assert not [m for m in errors if "both_streams_silent" in m]
    line = next(m for m in warnings if "both_streams_silent" in m)
    assert "verdict=venue_halt" in line
    assert "residual_s=0.0" in line
    assert "halt_s=1220.0 carried=2/2 bracketed=1/1 trades_inside=0 id_holes=0" in line


@pytest.mark.parametrize(
    ("btc_book", "btc_prints", "evidence"),
    [
        (sorted([*_DARK, (1800.0, "snapshot")]), ((1185.0, 7), (1805.0, 8)), (1, 1, 0, 0)),
        (_DARK, ((1185.0, 7), (1500.0, 8), (1805.0, 9)), (2, 0, 1, 1)),
        (_DARK, ((1185.0, 7), (1805.0, 9)), (2, 0, 0, 1)),
        (_DARK, ((1185.0, 7),), (2, 0, 0, 0)),
    ],
    ids=["a-reconnect-on-both-hosts", "a-trade-inside", "a-trade-id-neither-host-holds", "no-pair-brackets-the-window"],
)
def test_a_halt_shaped_window_the_mirrors_do_not_prove_books_as_loss(tmp_path, monkeypatch, btc_book, btc_prints, evidence):
    pri, sec, rec = _roots(tmp_path)
    _plant_halt(pri, sec, btc_book=btc_book, btc_prints=btc_prints)
    errors, _ = _capture_logs(monkeypatch)
    textfile = tmp_path / "reconcile.prom"

    result = _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(textfile)], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    [record] = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    assert record["verdict"] == "undetermined"
    assert record["residual_seconds"] == pytest.approx(1220.0)
    assert record["halt_seconds"] == 0.0
    assert (record["streams_carried"], record["windows_bracketed"], record["trades_inside"], record["trade_id_holes"]) == evidence
    series = _series(textfile)
    assert series["zcrypto_reconcile_residual_gap_seconds_total"] == pytest.approx(1220.0)
    assert series["zcrypto_reconcile_venue_halt_seconds_total"] == 0.0
    assert "verdict=undetermined" in next(m for m in errors if "both_streams_silent" in m)


def test_an_unreadable_trades_segment_is_no_trade_evidence_and_the_hour_books_as_loss(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _plant_halt(pri, sec)
    for root in (pri, sec):
        _seg_path(root, "BTC/EUR", "trades", H).write_bytes(b"not a parquet")
    errors, warnings = _capture_logs(monkeypatch)

    result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 1  # the trades heal fails the hour on the same file
    [record] = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    assert record["verdict"] == "undetermined"
    assert record["residual_seconds"] == pytest.approx(1220.0)
    assert record["windows_bracketed"] == 0
    assert (
        len(
            [
                m
                for m in warnings
                if "unreadable primary trades segment pair=BTC/EUR" in m or "unreadable secondary trades segment pair=BTC/EUR" in m
            ]
        )
        == 2
    )
    assert "verdict=undetermined" in next(m for m in errors if "both_streams_silent" in m)


def test_a_divergence_keeps_its_loss_and_its_page_when_the_book_carried_through(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _plant_halt(pri, sec)
    _write(pri, "BTC/EUR", "book", H, _book("BTC/EUR", H, sorted([*_DARK, (1500.0, "update")])))
    errors, _ = _capture_logs(monkeypatch)

    result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    [record] = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    assert (record["streams_carried"], record["windows_bracketed"]) == (2, 2)
    assert record["verdict"] == "capture_divergent"
    assert record["residual_seconds"] == pytest.approx(1220.0)
    assert record["halt_seconds"] == 0.0
    assert "verdict=capture_divergent" in next(m for m in errors if "both_streams_silent" in m)


def test_an_hour_booked_before_the_halt_verdict_stays_booked_as_it_was(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _plant_halt(pri, sec)
    rec.mkdir(parents=True, exist_ok=True)
    booked = {
        "at": "2026-07-16T11:12:42+00:00",
        "state": "both_streams_silent",
        "pair": "*",
        "kind": "book",
        "hour": H.isoformat(),
        "pairs": list(PAIRS),
        "windows": [
            {"start": (H + timedelta(seconds=1190)).isoformat(), "end": (H + timedelta(seconds=1800)).isoformat(), "seconds": 610.0}
        ],
        "residual_seconds": 5432.534453,
        "verdict": "undetermined",
    }
    (rec / "reconcile-ledger.jsonl").write_text(json.dumps(booked) + "\n")
    textfile = tmp_path / "reconcile.prom"

    result = _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(textfile)], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    assert [r for r in _ledger(rec) if r["state"] == "both_streams_silent"] == [booked]
    series = _series(textfile)
    assert series["zcrypto_reconcile_residual_gap_seconds_total"] == pytest.approx(5432.534453)
    assert series['zcrypto_reconcile_dark_episode_seconds_total{verdict="undetermined"}'] == pytest.approx(5432.534453)
    assert series["zcrypto_reconcile_venue_halt_seconds_total"] == 0.0


def test_the_totals_book_a_halt_beside_the_loss_and_never_inside_it():
    loss = {
        "state": "both_streams_silent",
        "hour": "2026-11-17T08:00:00+00:00",
        "residual_seconds": 5432.534453,
        "verdict": "undetermined",
    }
    halt = {
        "state": "both_streams_silent",
        "hour": "2026-11-18T08:00:00+00:00",
        "residual_seconds": 0.0,
        "halt_seconds": 1220.0,
        "verdict": "venue_halt",
    }
    totals = command._totals([loss, halt])
    assert totals["residual_seconds"] == pytest.approx(5432.534453)
    assert totals["dark_undetermined"] == pytest.approx(5432.534453)
    assert totals["venue_halt_seconds"] == pytest.approx(1220.0)
    assert totals["dark_venue_silent"] + totals["dark_capture_divergent"] + totals["dark_undetermined"] == pytest.approx(
        totals["residual_seconds"]
    )
```

- [ ] **Step 2: Run them red.** `uv run pytest tests/test_archive_reconcile_command.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -k "venue_halt or halt_shaped or divergence_keeps or booked_before_the_halt or totals_book_a_halt or unreadable_trades_segment or every_series or infinite_source_lag or ledger_record_count or verdict_is_recorded"`. Expected: `11 failed, 2 passed, 56 deselected`, the two that pass being the hand-built totals.

- [ ] **Step 3: Implement in `cli/archive/command.py`.** The settle import gains, in its sorted place, `CAPTURE_DIVERGENT,` and `VENUE_HALT,` before `classify_dark_episode,` and `classify_halt,` after it. `_MINT_FAMILY`'s comment's last line, `# correlated-loss states are permanent loss and are never minted from.`, reads `# correlated-loss states are never minted from, and book as permanent loss but a venue halt.`; `_booked_dark`'s docstring's first line reads `"""The fleet-dark windows the ledger has ALREADY booked, as loss or as a venue halt, for \`pair\`'s stream in \`hour\`.`.

`_totals` gains `"venue_halt_seconds",` after `"dark_undetermined",` in its keys, and its `both_streams_silent` branch, from `verdict = record.get("verdict") or "undetermined"` to the `totals[f"dark_{verdict}"]` line, reads:

```python
            verdict = record.get("verdict") or "undetermined"
            if verdict == VENUE_HALT:
                # Its `residual_seconds` is 0.0 and its seconds are `halt_seconds`, so an image that
                # predates the verdict buckets it as undetermined at 0.0 and books none of it as loss.
                totals["venue_halt_seconds"] += float(record.get("halt_seconds") or 0.0)
            else:
                if verdict not in ("venue_silent", "capture_divergent", "undetermined"):
                    # The ledger is append-only and outlives any single image version: widen the verdict
                    # vocabulary later, then roll back to THIS code (a normal operation), and it must not
                    # crash-loop indexing a key that does not exist -- an unrecognized verdict is bucketed
                    # as undetermined, same as no verdict at all, rather than raising KeyError.
                    verdict = "undetermined"
                totals[f"dark_{verdict}"] += float(record.get("residual_seconds") or 0.0)
```

In `_write_textfile`, the residual help's second string line, `"healed hour's splice left unfilled and no fleet-wide record already booked). A FLOOR, not the "`, becomes the two lines `"healed hour's splice left unfilled and no fleet-wide record already booked) -- but a venue halt "` and `"the book carried through, which books to venue_halt_seconds_total instead. A FLOOR, not the "`; the dark-episode help's last line, `"from it; the three add up to the both_streams_silent share of it.",`, becomes `"from it; the three add up to the both_streams_silent share of it. A venue_halt record books no "` and `"residual, so it reaches venue_halt_seconds_total and none of these.",`; and directly after the dark-episode `_emit(...)`:

```python
    _emit(
        "venue_halt_seconds_total",
        "counter",
        "Fleet-dark seconds across a venue halt: every booked book stream resumed, on at least one mirror, "
        "with no resync after the window -- capture's live checksum accepted the book it carried through -- "
        "and no pair traded across it. NOT loss, and never in residual_gap_seconds_total; the "
        "both_streams_silent records with verdict venue_halt are its ledger.",
        [("", totals["venue_halt_seconds"])],
    )
```

Inside `reconcile`, directly above `def _fail(`:

```python
    def _tape(root: Path, source: str, pair: str, hour: datetime) -> list[tuple[datetime, int]] | None:
        """`pair`'s trades in `hour` on one mirror as (ts, trade_id); None where that mirror has none it can read."""
        if hour not in scans[source]["trades"].get(pair, set()):
            return None
        try:
            frame = _read(root, pair, "trades", hour, ["ts", "trade_id"])
        except Exception as exc:  # noqa: BLE001 -- an unread tape is no trade evidence, so the hour books as loss
            logger.warning(
                "archive reconcile: unreadable %s trades segment pair=%s hour=%s: %s", source, pair, hour.isoformat(), exc
            )
            return None
        return list(zip(frame["ts"].to_list(), frame["trade_id"].to_list(), strict=True))

```

In the booking block, everything from `# TRIAGE ONLY -- never an input to \`residual\` above (spec 00096 D1).` to the `_ledger(...)` call's closing `)` reads:

```python
                # (ts, type) pairs, from the frames already in hand. Zipped explicitly rather than
                # `.rows()`, which would depend on the column order `_read` happened to return.
                book_rows = {
                    p: {
                        src: (None if f is None else list(zip(f["ts"].to_list(), f["type"].to_list(), strict=True)))
                        for src, f in books[p].items()
                    }
                    for p in present
                }
                # TRIAGE ONLY -- never an input to the booking (spec 00096 D1).
                episode = classify_dark_episode(windows, book_rows)
                # The booking's one input beside the timeline: a halt the book carried through books
                # its seconds to the halt counter, never as loss. A divergence keeps its loss and page.
                halt = classify_halt(
                    windows,
                    stream_windows,
                    book_rows,
                    {
                        p: {
                            src: _tape(root, src, p, hour)
                            for src, root in (("primary", primary_root), ("secondary", secondary_root))
                        }
                        for p in present
                    },
                    hour_end=hour_end,
                )
                verdict = VENUE_HALT if halt.holds and episode.verdict != CAPTURE_DIVERGENT else episode.verdict
                halted = verdict == VENUE_HALT
                # WARNING for a halt: `Ops · ERROR logs` pages on this line, and a halt is not loss.
                (logger.warning if halted else logger.error)(
                    "archive reconcile: both_streams_silent hour=%s windows=%d residual_s=%.1f verdict=%s updates=%d snapshots=%d divergent=%s"
                    " halt_s=%.1f carried=%d/%d bracketed=%d/%d trades_inside=%d id_holes=%d",
                    hour.isoformat(),
                    len(windows),
                    0.0 if halted else residual,
                    verdict,
                    episode.interior_updates,
                    episode.interior_snapshots,
                    ",".join(episode.divergent_pairs) or "-",
                    residual if halted else 0.0,
                    halt.streams_carried,
                    halt.streams,
                    halt.windows_bracketed,
                    halt.windows,
                    halt.trades_inside,
                    halt.id_holes,
                )
                _ledger(
                    state="both_streams_silent",
                    pair="*",  # fleet-wide by construction: it is the intersection across every pair
                    kind="book",
                    hour=hour.isoformat(),
                    pairs=present,
                    windows=[{"start": w.start, "end": w.end, "seconds": w.seconds} for w in windows],
                    # What was ACTUALLY booked, per stream. `_booked_dark` reads this so the healed
                    # path subtracts the same seconds; `windows` stays as the intersection provenance.
                    stream_windows={
                        p: [{"start": c.start, "end": c.end, "seconds": c.seconds} for c in own]
                        for p, own in stream_windows.items()
                    },
                    residual_seconds=0.0 if halted else residual,
                    halt_seconds=residual if halted else 0.0,
                    verdict=verdict,
                    interior_updates=episode.interior_updates,
                    interior_snapshots=episode.interior_snapshots,
                    interior_seconds=episode.interior_seconds,
                    pairs_agreeing=episode.pairs_agreeing,
                    pairs_skipped=episode.pairs_skipped,
                    divergent_pairs=list(episode.divergent_pairs),
                    streams_carried=halt.streams_carried,
                    windows_bracketed=halt.windows_bracketed,
                    trades_inside=halt.trades_inside,
                    trade_id_holes=halt.id_holes,
                )
```

- [ ] **Step 4: Chart the series.** In `infra/grafana/data-integrity-dashboard.json`, panel 206's `description`, the sentence `... and the sum of the three never exceeds the residual total beside it.` is followed by ` venue_halt is the fourth line and sits OUTSIDE that total: episodes the mirrors prove lost nothing -- every book stream resumed on a capture host with no resync, and no pair traded across the silence -- booked as a halt and never as loss.` before ` Read during triage`; and after the target with `"refId": "C"`:

```json
        {
          "datasource": {
            "type": "prometheus",
            "uid": "grafanacloud-prom"
          },
          "expr": "zcrypto_reconcile_venue_halt_seconds_total{host=\"ops\"}",
          "refId": "D",
          "legendFormat": "venue_halt (not loss)"
        }
```

- [ ] **Step 5: Run them green.** The Step 2 command. Expected: `13 passed, 56 deselected`.

- [ ] **Step 6: Commit** `fix(archive): a venue halt the mirrors prove books to venue_halt_seconds_total, never as loss`, after the per-commit run over `cli/archive/command.py tests/test_archive_reconcile_command.py infra/grafana/data-integrity-dashboard.json` (expected `984 passed, 44 warnings`; its readers include `tests/test_dashboards_cover_metrics.py`, which fails without Step 4) and the gate, the run's result line in the body.

- [ ] **Step 7: Probe, then commit the verdicts** under `test(archive): the halt's booking proven by infra/scripts/mutate-probe.sh`. File `cli/archive/command.py`, test file `tests/test_archive_reconcile_command.py`:

| Id | Selection (`-k`) | Mutation |
|---|---|---|
| 2a | `divergence_keeps` | `s/ and episode.verdict != CAPTURE_DIVERGENT else/ else/` |
| 2b | `venue_halt_books_its_seconds` | `s/verdict = VENUE_HALT if halt.holds and/verdict = VENUE_HALT if False and/` |
| 2c | `halt_shaped_window` | `s/verdict = VENUE_HALT if halt.holds and/verdict = VENUE_HALT if True and/` |
| 2d | `venue_halt_books_its_seconds` | `s/residual_seconds=0.0 if halted else residual,/residual_seconds=residual,/` |
| 2e | `venue_halt_books_its_seconds` | `s/halt_seconds=residual if halted else 0.0,/halt_seconds=0.0,/` |
| 2f | `venue_halt_books_its_seconds` | `s/(logger.warning if halted else logger.error)(/logger.error(/` |
| 2g | `totals_book_a_halt` | `s/totals\["venue_halt_seconds"\] += float(record.get("halt_seconds") or 0.0)/totals["venue_halt_seconds"] += 0.0/` |
| 2h | `venue_halt_books_its_seconds` | `s/        return list(zip(frame\["ts"\].to_list(), frame\["trade_id"\].to_list(), strict=True))/        return []/` |
| 2i | `booked_before_the_halt_verdict` | `s/if windows and not _decided("\*", "book", hour, "both_streams_silent"):/if windows:/;s/if key in seen:  # already decided/if False:  # already decided/` |
| 2j | `unreadable_trades_segment` | `s/except Exception as exc:  # noqa: BLE001 -- an unread tape is no trade evidence, so the hour books as loss/except ZeroDivisionError as exc:  # noqa: BLE001/` |

Arm 2i carries two expressions, each pattern counted before it: `_ledger`'s `seen` refuses a second append on its own, so the `_decided` mutation alone reads `SURVIVED`.

### Task 3: The permanent-loss page says a proven venue halt never reaches it

**Files:**
- Modify: `infra/grafana/alerts.yaml:1617`, `:1653` (`zcrypto-reconcile-residual-gap`)
- Test: `tests/test_infra_alert_rules.py`

**Interfaces:**
- Consumes: the published series `zcrypto_reconcile_venue_halt_seconds_total` (Task 2).

- [ ] **Step 1: Write the failing test,** directly after `test_the_permanent_loss_page_outlives_a_single_evaluation_hour`:

```python
def test_the_permanent_loss_page_names_the_halt_counter_the_reconciler_publishes():
    halt = "zcrypto_reconcile_venue_halt_seconds_total"
    assert halt in _rule("zcrypto-reconcile-residual-gap")["annotations"]["summary"]
    assert halt in published_app_families()
```

- [ ] **Step 2: Run it red.** `uv run pytest tests/test_infra_alert_rules.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -k names_the_halt_counter`. Expected: `1 failed, 173 deselected`.

- [ ] **Step 3: Apply the spec's two alert texts,** its *Runbook and alert texts* blocks 1 and 2:

```bash
python3 - <<'EOF'
import re
from pathlib import Path
texts = Path("docs/specs/00163-venue-halt-not-loss-design.md").read_text().split("## Runbook and alert texts", 1)[1].split("## Deployment", 1)[0]
blocks = re.findall(r"```(?:markdown|yaml)?\n(.*?)\n```", texts, re.S)
assert len(blocks) == 16, len(blocks)
p = Path("infra/grafana/alerts.yaml")
s = p.read_text()
line = "      # for, hence `> 0` rather than a tolerance.\n"
opening = "Permanent L2 loss: silence NEITHER capture host covered -- unhealable, the data is gone. The counter books ABSENCE of data, not fault: a venue outage lands here exactly like a capture failure."
assert s.count(line) == 1 and s.count(opening) == 1
p.write_text(s.replace(line, blocks[0] + "\n").replace(opening, blocks[1]))
EOF
```

- [ ] **Step 4: Run it green.** The Step 2 command. Expected: `1 passed, 173 deselected`.

- [ ] **Step 5: Commit** `fix(grafana): the permanent-loss page says a proven venue halt never reaches it`, after the per-commit run over `infra/grafana/alerts.yaml tests/test_infra_alert_rules.py` (without `tests/test_grafana_push_sh.py`; expected `1 failed, 2033 passed, 2 skipped`, the failure the in-repository-basetemp case Global Constraints names) and the gate, the run's result line and that case's name in the body, and a line that the change is the summary and the comment alone — no expression, threshold or uid — so the push after the merge is an annotation upsert with no prune owed.

- [ ] **Step 6: Probe, then commit the verdicts** under `test(grafana): the page's halt pointer proven by infra/scripts/mutate-probe.sh`. Test file `tests/test_infra_alert_rules.py`, selection `names_the_halt_counter`:

| Id | File | Mutation |
|---|---|---|
| 3a | `infra/grafana/alerts.yaml` | `s/it books to zcrypto_reconcile_venue_halt_seconds_total, which pages nothing/it books elsewhere, which pages nothing/` |
| 3b | `cli/archive/command.py` | `s/^        "venue_halt_seconds_total",$/        "venue_halt_total",/` |

### Task 4: The residual-gap, venue-status and silence sections and the README say a proven halt books as a halt

**Files:**
- Modify: `infra/runbooks/ops.md:203`, `:214`, `:217`, `:377`; `infra/runbooks/capture.md:26`, `:29`, `:52`, `:309`, `:318`, `:319`; `README.md:232`

- [ ] **Step 1: Load the `zcrypto-refine-rules` skill** — two top-level pages under `infra/runbooks/` change. The texts add no ambient bytes (the pages are read for universals, never counted), and every list item they write with a universal word carries its `(no count command: …)`.

- [ ] **Step 2: Apply the spec's runbook and README texts,** its *Runbook and alert texts* blocks 3 to 13:

```bash
python3 - <<'EOF'
import re
from pathlib import Path
texts = Path("docs/specs/00163-venue-halt-not-loss-design.md").read_text().split("## Runbook and alert texts", 1)[1].split("## Deployment", 1)[0]
blocks = re.findall(r"```(?:markdown|yaml)?\n(.*?)\n```", texts, re.S)
assert len(blocks) == 16, len(blocks)


def whole_line(path, opening, new):
    p = Path(path)
    lines = p.read_text().split("\n")
    hits = [i for i, line in enumerate(lines) if line.startswith(opening)]
    assert len(hits) == 1, (path, opening, hits)
    lines[hits[0]] = new
    p.write_text("\n".join(lines))


def clause(path, old, new):
    p = Path(path)
    s = p.read_text()
    assert s.count(old) == 1, (path, old)
    p.write_text(s.replace(old, new))


whole_line("infra/runbooks/ops.md", "**The counter books the ABSENCE of data, never fault attribution.**", blocks[2])
whole_line("infra/runbooks/ops.md", "6. **Read the `verdict` on the hour's `both_streams_silent` ledger record**", blocks[3])
clause("infra/runbooks/ops.md", "no evidence either way from the cross-host comparison, which is where a hard halt lands, since a venue emitting *nothing* leaves no interior messages for the two hosts to agree on.", blocks[4])
clause("infra/runbooks/ops.md", "books as `both_streams_silent` — permanent, paged, never revisited", blocks[5])
whole_line("infra/runbooks/capture.md", "2. **A venue-side halt DOES book permanent loss.", blocks[6])
whole_line("infra/runbooks/capture.md", "5. **Do not converge or restart anything on this signal alone.**", blocks[7])
clause("infra/runbooks/capture.md", "read the state and its ladder, expect the loss page hours later,", blocks[8])
whole_line("infra/runbooks/capture.md", "It is nonetheless a **true positive, not noise**.", blocks[9])
clause("infra/runbooks/capture.md", "4. **Expect the loss page, and do not pre-empt it.**", blocks[10])
whole_line("infra/runbooks/capture.md", "5. **Do not converge or restart on this signal alone.**", blocks[11])
whole_line("README.md", "Two **correlated-loss** detectors run regardless of the flag and never mint:", blocks[12])
EOF
```

- [ ] **Step 3: Commit** `docs(runbooks): the residual-gap, venue-status and silence sections and the README say a proven halt books as a halt`, after the per-commit run over `infra/runbooks/ops.md infra/runbooks/capture.md README.md` (expected `1 failed, 4804 passed, 1 deselected`, the failure the case Global Constraints names) and the gate, the run's result line and that case's name in the body.

### Task 5: The hygiene map's 2026-11-17 08Z row, a complete halt, what a halt hour is, and the three earlier halts re-trued

**Files:**
- Modify: `docs/reference/capture-era-data-hygiene-map.md:38`, `:39`, `:41`, after `:41`, before `:43`

- [ ] **Step 1: Apply the spec's map texts,** its *Runbook and alert texts* blocks 14 to 16:

```bash
python3 - <<'EOF'
import re
from pathlib import Path
texts = Path("docs/specs/00163-venue-halt-not-loss-design.md").read_text().split("## Runbook and alert texts", 1)[1].split("## Deployment", 1)[0]
blocks = re.findall(r"```(?:markdown|yaml)?\n(.*?)\n```", texts, re.S)
assert len(blocks) == 16, len(blocks)
row, paragraph, cell = blocks[13], blocks[14], blocks[15]
p = Path("docs/reference/capture-era-data-hygiene-map.md")
lines = p.read_text().split("\n")
old = "unbackfillable, and no re-investigation is owed — the gap is explained."
for head in ("| **2026-10-15 07:01:02.993780 → 07:05:08.324270**", "| **2026-10-29 08:01:07.96 → 08:07:52.93**", "| **2026-10-30 08:01:03.87 → 08:06:21.06**"):
    hits = [i for i, line in enumerate(lines) if line.startswith(head)]
    assert len(hits) == 1 and lines[hits[0]].count(old) == 1, head
    lines[hits[0]] = lines[hits[0]].replace(old, cell)
last = [i for i, line in enumerate(lines) if line.startswith("| **2026-10-30 08:01:03.87 → 08:06:21.06**")][0]
lines.insert(last + 1, row)
anchor = [i for i, line in enumerate(lines) if line.startswith("**The completeness instrument is `continuity.py`")]
assert len(anchor) == 1
lines[anchor[0] : anchor[0]] = [paragraph, ""]
p.write_text("\n".join(lines))
EOF
```

- [ ] **Step 2: Commit** `docs(reference): the hygiene map's 2026-11-17 08Z row, a complete halt, what a halt hour is, and three halts re-trued`, after the gate; `consumers.sh` lists no reader for the map, so the run is `uv run pytest tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` (expected `1113 passed`), its result line in the body, and the body names the spec's *The measured basis* as the measurement behind each revised verdict, the map's own rule.

### Task 6: The decisions log's `[00163]` entries

**Files:**
- Modify: `docs/research/14.phase6-decisions.md` (append)

- [ ] **Step 1: Append** to the end of `docs/research/14.phase6-decisions.md`, after its last line, the four entries below, the first line blank:

```markdown

[00163] Does the reconciler keep booking a venue halt like 2026-11-17 08Z's as permanent loss? (Decision: 2)
  Asked by `zcrypto-zebra` on 2026-11-17, whether the reconciler should stop booking such a halt as residual; the owner's ruling, 2026-11-17T19:47:55.448Z, verbatim: "for the reconciler change, fix it right aways in a branch without deferring it to a new T-topic".
  1. **Keep booking it as loss, as `[iter-141]`'s first entry ruled** — the counter books absence and the hygiene map says whose it was; every halt the venue announces pages "Permanent L2 loss" and `Ops · ERROR logs` for an hour that lost nothing.
  2. **Book a halt the two mirrors prove lost nothing to its own counter, never as loss, on this branch** — taken, on the ruling; it supersedes `[iter-141]`'s first entry for that evidence alone, and every silence it cannot prove books and pages as before.
  3. **Park it in a topic** — refused by the ruling.

[00163] What evidence books a fleet-dark hour as a venue halt rather than loss? (Decision: 1)
  1. **The mirrors alone: the book carried through and nothing traded** — every booked stream has a host with no resync snapshot from its first window to the hour's end and a resume at least 300 s before that end, no trade lands inside a window, and each window is straddled by adjacent trade ids with none skipping. It reads only what the reconciler already reads; over the ledger's 14 dark hours it holds on 2026-10-15, 2026-10-29, 2026-10-30 08Z and 2026-11-17 08Z, and refuses 2026-07-13's capture defect and 2026-10-13's silence, in which spot traded.
  2. **Archive Kraken's `status` ladder for the reconciler** — a schema change on the unbackfillable capture stream, its rows stamped at local receipt; it says the venue announced a halt, not that nothing was lost.
  3. **Read Kraken's scheduled-maintenance feed at booking time** — a third-party call inside the booking path, which `[iter-141]` refused; an announcement is not proof either.
  Decided by the spec's author.

[00163] Where does a halt live on the ledger and in the counters? (Decision: 1)
  1. **A fourth `verdict`, `venue_halt`, on the `both_streams_silent` record, its `residual_seconds` 0.0 and its seconds in `halt_seconds`, summed into a new `zcrypto_reconcile_venue_halt_seconds_total`** — decided once with the record; an image that predates the verdict buckets it as undetermined at 0.0, so a rollback books and pages nothing.
  2. **A ledger state of its own** — an older image would not see the hour decided and would re-book it as `both_streams_silent`, paging on a rollback; `_booked_dark` would read a second state.
  3. **A fourth label on `dark_episode_seconds_total`** — that series would stop partitioning the residual counter's share.
  Decided by the spec's author.

[00163] What becomes of the hours already booked as loss that the rule proves were halts? (Decision: 1)
  Asked 2026-11-17T20:58:17.617Z, verbatim: "The reconciler fix (spec 00163) stops booking a proven venue halt as permanent loss from now on. Already booked are today's 08Z hour (5,432.5 s) and three earlier hours the rule also proves were halts (10-15, 10-29, 10-30 08Z; 8,469.9 s). Together, 13,902.4 s of the residual counter's lifetime total were not loss. The code can't change records already written; only a hand edit of the live ledger on zcrypto-ops can. What should happen to them?" The owner's answer, 20:59:43.800Z, verbatim: "Leave them (Recommended)".
  1. **Leave them (Recommended)** — the counter keeps the 13,902.4 s and the hygiene map records each of the four hours as complete, a halt not a loss; nothing touches a live file.
  2. **Append a note record per hour** — one hand-written append per hour to the live ledger on `zcrypto-ops`, saying it was a halt, with no counter field, like the 2026-07-29 `correction` record.
  3. **Correct them out of the counter** — the records rewritten so the seconds leave the residual counter; Prometheus reads the drop as a reset, the page's `resets()` guard blind for 24 h.
```

- [ ] **Step 2: Commit** `docs(research): the [00163] entries, the owner's two rulings on booking a venue halt and the spec's two calls`, after the gate; `consumers.sh` lists no reader for the log, so the run is `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` (expected `50 passed`), its result line in the body.
