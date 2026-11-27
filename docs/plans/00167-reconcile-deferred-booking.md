# A fleet-dark hour still missing a trades file waits for it, up to six hours, before the reconciler books it Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `both_streams_silent` hour in which a present pair's trades final is on neither mirror, or fails to read, takes no `both_streams_silent` record and no book-heal record and logs one WARNING on each cycle before the late deadline, and is booked by today's code on the first cycle that reads the file or is late; before that deadline an hour's book heal also waits out a cycle on which one of its book segments fails to read.

**Architecture:** In `reconcile`'s hour loop (`cli/archive/command.py`), after the halt evidence is read, the pairs with no trades final on either mirror are listed; while that list or the halt proof's `unread` is not empty and the hour is not late, the booking block is skipped with one WARNING and a `deferred` flag set, and the book heal loop iterates nothing for that hour (spec D1, D2, D4 A, D5 A, D6 A); `deferred` starts each hour as `broken and not late`, so a cycle with an unreadable book segment holds the hour's heal too until the late deadline (D4 A). Every other line of the booking block is today's, re-indented under an `else:` (D3). The skip cache keeps `ALGO_VERSION = 1` (D7 A). The capture and ops runbook pages and the README say the booking can wait; the decisions log takes five `[iter-214]` entries; the rollout is the owner's ops converge after the merge (D8).

**Tech Stack:** Python 3.14, polars, pytest, `infra/scripts/mutate-probe.sh`.

**Spec:** `docs/specs/00167-reconcile-deferred-booking-design.md`

**Tier** — `uv run python infra/scripts/tier.py --paths cli/archive/command.py cli/archive/settle.py tests/test_archive_reconcile_command.py tests/test_archive_settle.py infra/runbooks/capture.md infra/runbooks/ops.md README.md docs/research/14.phase6-decisions.md`, run at `3fb48bf8c`:

```
tier: full
full tests/test_archive_reconcile_command.py — a test importing cli.capture.segment_writer, read as a non-prose change
full tests/test_archive_settle.py — a test importing cli.capture.errors, read as a non-prose change
```

**The decisions.** The owner picked option A of each of spec D4–D7 (asked 2026-11-27T16:11:03Z, answered by 16:18:57Z), the option this plan was written on, and, asked from this plan's review at 2026-11-27T17:12:56Z, held a heal on a cycle whose book read fails before the late deadline too (answered by 17:13:09Z, spec D4 A); Task 3's entries carry the asks and answers verbatim, and the ruling's three options as asked.

Every figure below was measured with this file's fences applied, by a script that reads them from it, to a detached scratch worktree at `3fb48bf8c` (`.tmp/r1-fix/wt` in the branch's worktree, never pushed), each left fence of a replacement matching once where its step places it and each task committed there, the commands run with that tree's own `uv run`: Task 1's code over today's tests read `21 failed, 314 passed in 8.19s` over the reconciler's seven test files (`tests/test_archive_settle.py`, `tests/test_archive_reconcile_command.py`, `tests/test_archive_scan_cache.py`, `tests/test_archive_reconcile.py`, `tests/test_archive_mint.py`, `tests/test_trades_backfill.py`, `tests/test_bench_ledger_scan.py`), the eleven cases Step 1 gives `_tapes`, the nine it moves to `LATE` and the absent-file case; every other figure is in the step that states it, the probe arms' on Task 1's committed tree.

## Global Constraints

- The spec, `docs/specs/00167-reconcile-deferred-booking-design.md`, is the authority, and a task that names one of its decisions reads it there; where it is silent this plan rules, in *Rulings where the spec is silent*.
- No implementer task (Tasks 1–3) converges, builds an image, pushes, pulls or calls an endpoint, and none reads the NAS mirrors, the ops ledger or `/mnt/zhao-crypto/`: the spec's *The measured basis* is the real-data reading, the cases below the proof. No implementer task (Tasks 1–3) runs `infra/scripts/grafana-push.sh`, `infra/scripts/grafana-query.py`, `infra/scripts/host-run.sh`, `infra/ansible/scripts/converge.sh` or `tests/test_grafana_push_sh.py`. No task touches `.claude/`. Task 4 is the coordinator's and the owner's, after the merge, and no implementer runs it.
- The worktree is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/iter-214` (branch `feat/iter-214-reconcile-deferred-booking`); every command runs with it as the working directory, and git takes `-C` that path. The main checkout is live.
- Before Task 1's first command, `mkdir -p .tmp/implementer .local/reconcile-deferred-booking`, its own call: every pytest run takes `--basetemp=.tmp/implementer/pt`.
- Tests per commit: `infra/scripts/consumers.sh --tests --direct <the commit's changed paths> 2>.tmp/implementer/cons.err >.tmp/implementer/cons.list`, its own call, exit 2 meaning no reader; `cat .tmp/implementer/cons.err`, its own call; then `T="$(grep -v '^#' .tmp/implementer/cons.list | grep -v '^tests/test_grafana_push_sh.py$' | sort -u | tr '\n' ' ') <the task's test files>"; uv run pytest $T -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rf`. Never the full suite. A reader that fails only under an in-repository `--basetemp` is re-run alone with `--basetemp=/home/zhaow/.cache/claude-tmp/iter214-implementer/pt` after `mkdir -p /home/zhaow/.cache/claude-tmp/iter214-implementer`, and the message names it beside its result line.
- The gate is `uv run pre-commit run -a`, re-run until clean, its rewrites staged.
- A comment or docstring stays only where a reader would act differently without it, and is correct. The runbook pages, the README and every string literal under `cli/` carry no `spec <NNNNN>`, `D<N>`, `T<NNNN>`, `iter-<N>`, `Phase <N>` or `WP<N>` token (`tests/test_internal_terms_not_operator_visible.py`); the fences below carry none.
- Commits: Conventional Commits, after a `git -C <the worktree> add <every path the commit changes>` of its own, through `git -C <the worktree> commit -F - <<'EOF'`; the message says what changed and pastes the result line of the test command it names, run over the commit's own tree; one state-changing git command per Bash call; never an amend, `--no-verify` or `git stash`; every message ends with `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>`, the implementer's own model in place of the placeholder, and `Claude-Session: https://claude.ai/code/session_018eFiE9ZzjweN7A4N9yBCTV`.
- Probes (this plan's tier is `full`): each arm Task 1 lists runs as its own call on the committed tree, `infra/scripts/mutate-probe.sh --file cli/archive/command.py --control '1,$d' --mutation '<mutation>' -- uv run pytest tests/test_archive_reconcile_command.py -k '<selection>' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`. Before each arm, its own call, the pattern's count reads `1`: `grep -c -F -- '<pattern>' cli/archive/command.py`, or for the arm whose mutation opens with a range, `sed -n '<range>p' cli/archive/command.py | grep -c -F -- '<pattern>'`. `: > .local/reconcile-deferred-booking/probes-task-1.txt` before the arms; after each arm its id and the script's last line are appended, its own call. The verdicts ride an empty commit through `git -C <the worktree> commit --allow-empty -F - <<'EOF'`, the subject Task 1 names, its body the probes file pasted whole, then the trailers; it names no test run, the verdicts being its result.

## Rulings where the spec is silent

- **The wait sits where today's `no trades segment` loop sits**, after `classify_halt` has read every tape, so `unread` is complete when the condition reads it; the WARNING names the pairs and the unread entries in that order, `-` for an empty list.
- **The booking block is re-indented under `else:`, its text unchanged** but the format string's split point (`snapshots=%d"` / `" divergent=%s …`), moved one field earlier so the deeper line is narrower than today's; the string it builds is byte for byte today's.
- **The heal waits through its loop's iterable, `() if deferred else book_pairs`**, one line a probe can address. `deferred` starts every hour beside `present` as `broken and not late` (spec D4 A's book-read clause), and the wait sets it again where the record is decided; read from the hour's own `broken` and `late`, the initializer cannot be hoisted above `for hour in window:` without raising `UnboundLocalError` before the window's first hour. A fleet record left undecided on one cycle and decided on a later one is left so by one of two branches, a failed book read (`broken`) or the wait: a waiting hour's heal is held by the wait, a broken cycle's before the late deadline by the initializer, and a broken cycle past the deadline heals first as today, the record decided later booking only what the heal did not (`_booked_residual`). The two texts that describe that last order, `_booked_residual`'s docstring and the fleet block's `# Minus whatever …` comment, name the deadline.
- **The eleven dark-hour cases that plant no trades final at all take one primary trades final per present pair** through a new `_tapes` helper, one print in the hour's first second — ten by one line each, and `test_a_pair_that_minted_before_the_fleet_detector_ran_is_not_booked_twice`, rewritten whole for spec D4 A's book-read clause, in its fence: the records the ten assert are the ones they asserted, since a tape whose only print precedes every window brackets no window, finds no id hole and leaves `quiet` at its 0.0 sentinel, as no tape does.
- **The nine cases whose trades final cannot be used run at `LATE`**, the bound, where they book as they did at `SETTLED`; whether such a final waits is the new transient-read case's subject.
- **Placement:** `_tapes` directly above `_run`; the five new cases directly after `test_a_trades_final_on_one_mirror_is_enough_for_a_halt`.
- **What a task writes is in the task, verbatim.** Nothing is written from a description.

## File structure

- Modify `cli/archive/command.py`: the `LATE_MINT_HOURS` import, `deferred`, the wait and its WARNING, the booking block under `else:`, the heal loop's iterable and its comment, `_booked_residual`'s docstring and the fleet block's subtraction comment.
- Modify `cli/archive/settle.py`: `SETTLE_HOURS`' premise comment. Modify `tests/test_archive_settle.py`: one comment.
- Modify `tests/test_archive_reconcile_command.py`: `_tapes`; ten cases take it; two cases run at `LATE`; the absent-file case waits first; the broken-read case is rewritten; five new cases.
- Modify `infra/runbooks/capture.md`, `infra/runbooks/ops.md`, `README.md`, `docs/research/14.phase6-decisions.md`.

## Review Focus

1. The wait engages on exactly an absent-on-both-mirrors final or an unread tape, before the late deadline, and nowhere else: pinned by `test_a_dark_hour_missing_a_trades_final_waits_for_it_and_books_a_halt_once_it_lands`, `test_a_trades_segment_unreadable_on_one_cycle_is_read_again_on_the_next`, the existing `test_a_trades_final_on_one_mirror_is_enough_for_a_halt` and its twin `test_a_trades_final_on_the_secondary_alone_is_enough_for_a_halt`, and the rewritten `test_a_pair_with_no_trades_final_on_either_mirror_leaves_the_hour_unproven`, whose waits run at `SETTLED` and `LATE - 1 µs` and whose booking runs at `LATE`.
2. At the end of the wait the record is today's: the rewritten absent-file case asserts today's record, line and counter at `LATE`, and the ten cases of Step 1's `_tapes` table assert theirs unchanged.
3. A waiting hour, and before the late deadline an hour on a cycle whose book read fails, takes no `both_streams_silent` record and no book-heal record, and the mint that follows subtracts the record's seconds: `test_a_pair_that_mints_inside_a_deferred_dark_hour_waits_for_the_fleet_record`, `test_a_failed_book_read_on_a_waiting_cycle_mints_nothing_before_the_fleet_record`, and the rewritten `test_a_pair_that_minted_before_the_fleet_detector_ran_is_not_booked_twice`, whose cycle past the deadline still heals first.
4. The wait's line is a WARNING and pages nothing; the booking's line keeps its level: the first new case asserts no ERROR line on either cycle.

---

### Task 1: A fleet-dark hour missing a trades file waits for it until the late deadline (spec D1–D7)

**Files:**
- Modify: `cli/archive/command.py`, `cli/archive/settle.py`
- Test: `tests/test_archive_reconcile_command.py`, `tests/test_archive_settle.py`

**Interfaces:**
- Consumes: `is_late`'s `late` (already computed per hour), the book loop's `broken`, `unread` and `classify_halt`'s tapes, `LATE_MINT_HOURS`.
- Produces: the WARNING `archive reconcile: booking deferred hour=… until=… missing=… unreadable=… -- a fleet-dark hour waits for these trades segments, then books whatever arrived`, which Task 2's texts quote.

- [ ] **Step 1: Write the cases.** In `tests/test_archive_reconcile_command.py`, directly above `def _run(`:

```python
def _tapes(pri: Path, hour: datetime, *, pairs: tuple[str, ...] = PAIRS) -> None:
    """Each pair's trades final on the primary, its one print in the hour's first second."""
    for pair in pairs:
        _write(pri, pair, "trades", hour, _trades(pair, hour, [1]))
```

Then one line, `_tapes(pri, H)` unless the row says otherwise, at the indentation of the case's body, directly after the line the row names, in each of the ten cases below:

| Case | After the line |
|---|---|
| `test_both_streams_silent_is_ledgered_paged_and_never_minted` | `        _write(sec, pair, "book", H, _book(pair, H, dark))` (the `for pair in PAIRS:` loop's last) |
| `test_a_fleet_dark_window_is_never_booked_as_loss_twice` | `        _outage(pri, sec, H, pair, secondary_dark=True)` |
| `test_a_pair_whose_mirror_arrives_after_the_fleet_decision_still_books_its_own_loss` — `_tapes(pri, H, pairs=("BTC/EUR",))` | its first `    _outage(pri, sec, H, "BTC/EUR", secondary_dark=True)` |
| `test_each_stream_is_booked_its_own_window_not_the_intersection` | `    _dark_from(pri, sec, H, "ETH/EUR", quiet_from=600, quiet_to=1400)` |
| `test_a_streams_window_spanning_two_fleet_windows_is_booked_once` | `    _dark_from(pri, sec, H, "ETH/EUR", quiet_from=600, quiet_to=1500)  # silent across both windows` |
| `test_the_healed_path_subtracts_the_stream_window_the_fleet_record_actually_booked` | `    _dark_from(pri, sec, H, "ETH/EUR", quiet_from=600, quiet_to=1400)` |
| `test_a_stream_missing_a_mirror_is_booked_the_intersection_not_its_own_window` — `_tapes(pri, H, pairs=("BTC/EUR", "ETH/EUR", "ADA/EUR"))` | `    _write(pri, "ADA/EUR", "book", H, _book("ADA/EUR", H, [(float(s), "update") for s in range(0, 600, 10)]))` |
| `test_a_present_but_empty_final_is_booked_the_intersection_not_the_whole_hour` — `_tapes(pri, H, pairs=("BTC/EUR", "ETH/EUR", "ADA/EUR"))` | `        _write(root, "ADA/EUR", "book", H, _book("ADA/EUR", H, []))` |
| `test_the_verdict_is_recorded_and_counted_while_the_booking_is_untouched` | `    _write(sec, "BTC/EUR", "book", H, _book("BTC/EUR", H, split))` |
| `test_the_dark_episode_counter_partitions_the_booked_seconds` | `    _write(sec, "BTC/EUR", "book", H, _book("BTC/EUR", H, split))` |

In `test_an_unreadable_trades_segment_leaves_the_hour_unproven_whatever_another_pair_brackets` and in `test_a_readable_trades_segment_the_proof_cannot_use_leaves_the_hour_unproven`, the one line

```python
    result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)
```

reads

```python
    result = _run([str(pri), str(sec), str(rec), "--mint"], now=LATE, monkeypatch=monkeypatch)
```

`test_a_pair_with_no_trades_final_on_either_mirror_leaves_the_hour_unproven`, from its `def` line to its blank line before `assert result.exit_code == 0`, reads:

```python
def test_a_pair_with_no_trades_final_on_either_mirror_leaves_the_hour_unproven(tmp_path, monkeypatch):
    """Waited for until the late deadline, then booked with what arrived: a pair still without one leaves it unproven."""
    pri, sec, rec = _roots(tmp_path)
    _plant_halt(pri, sec)
    for root in (pri, sec):
        _seg_path(root, "ETH/EUR", "trades", H).unlink()
    errors, warnings = _capture_logs(monkeypatch)
    textfile = tmp_path / "reconcile.prom"
    args = [str(pri), str(sec), str(rec), "--mint", "--textfile", str(textfile)]

    for waiting in (SETTLED, LATE - timedelta(microseconds=1)):
        assert _run(args, now=waiting, monkeypatch=monkeypatch).exit_code == 0
        assert _ledger(rec) == []
    assert not errors and not [m for m in warnings if "no trades segment" in m]

    result = _run(args, now=LATE, monkeypatch=monkeypatch)
```

its assertions from `assert result.exit_code == 0` on unchanged. `test_a_pair_that_minted_before_the_fleet_detector_ran_is_not_booked_twice`, from its `def` line to its last line, reads:

```python
def test_a_pair_that_minted_before_the_fleet_detector_ran_is_not_booked_twice(tmp_path, monkeypatch):
    """The mirror image: an unreadable segment suppresses the fleet detector for a cycle, and the hour's book heal waits
    with it until the late deadline. Past it the heal no longer waits, so a pair that mints on such a cycle books its
    residual FIRST, and the fleet record must then book only the streams that have not already booked their own."""
    pri, sec, rec = _roots(tmp_path)
    for pair in PAIRS:
        _outage(pri, sec, H, pair, secondary_dark=True)
    _tapes(pri, H)
    _seg_path(sec, "ETH/EUR", "book", H).write_bytes(b"not a parquet")

    _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)
    assert [(r["state"], r["pair"]) for r in _ledger(rec)] == [("failed", "ETH/EUR")], "the heal waits before the deadline"

    _run([str(pri), str(sec), str(rec), "--mint"], now=LATE, monkeypatch=monkeypatch)
    btc = [r for r in _ledger(rec) if r["state"] == "minted" and r["pair"] == "BTC/EUR"][0]
    assert btc["residual_seconds"] == pytest.approx(590.0), "nothing had booked it yet"
    assert "both_streams_silent" not in _states(rec)

    _outage(pri, sec, H, "ETH/EUR", secondary_dark=True)  # the segment is re-pulled intact
    _run([str(pri), str(sec), str(rec), "--mint", "--textfile", str(tmp_path / "r.prom")], now=LATE, monkeypatch=monkeypatch)

    fleet = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"][0]
    assert fleet["residual_seconds"] == pytest.approx(590.0), "BTC/EUR's 590 s was already on its own record"
    assert _series(tmp_path / "r.prom")["zcrypto_reconcile_residual_gap_seconds_total"] == pytest.approx(1180.0)
```

Directly after `test_a_trades_final_on_one_mirror_is_enough_for_a_halt`:

```python
def test_a_dark_hour_missing_a_trades_final_waits_for_it_and_books_a_halt_once_it_lands(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _plant_halt(pri, sec)
    for root in (pri, sec):
        _seg_path(root, "ETH/EUR", "trades", H).unlink()
    errors, warnings = _capture_logs(monkeypatch)
    textfile = tmp_path / "reconcile.prom"
    args = [str(pri), str(sec), str(rec), "--mint", "--textfile", str(textfile)]

    assert _run(args, now=SETTLED, monkeypatch=monkeypatch).exit_code == 0

    assert _ledger(rec) == []
    assert _series(textfile)["zcrypto_reconcile_residual_gap_seconds_total"] == 0.0
    assert [m for m in warnings if "booking deferred" in m] == [
        "archive reconcile: booking deferred hour=2026-07-16T09:00:00+00:00 until=2026-07-16T15:00:00+00:00 missing=ETH/EUR"
        " unreadable=- -- a fleet-dark hour waits for these trades segments, then books whatever arrived"
    ]
    assert not errors and not [m for m in warnings if "no trades segment" in m]

    _write(pri, "ETH/EUR", "trades", H, _prints("ETH/EUR", H, [(600.0, 40), (900.0, 41)]))
    assert _run(args, now=SETTLED + timedelta(minutes=30), monkeypatch=monkeypatch).exit_code == 0

    [record] = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    assert (record["verdict"], record["residual_seconds"], record["halt_seconds"]) == ("venue_halt", 0.0, pytest.approx(1220.0))
    assert _series(textfile)["zcrypto_reconcile_residual_gap_seconds_total"] == 0.0
    assert not errors


def test_a_pair_that_mints_inside_a_deferred_dark_hour_waits_for_the_fleet_record(tmp_path, monkeypatch):
    """BTC/EUR's primary resumes 30 s after its secondary, so the heal has seconds to mint inside the halt."""
    pri, sec, rec = _roots(tmp_path)
    _plant_halt(pri, sec)
    _write(
        pri, "BTC/EUR", "book", H, _book("BTC/EUR", H, [(float(s), "update") for s in range(0, 3600, 10) if not 1200 <= s < 1830])
    )
    for root in (pri, sec):
        _seg_path(root, "ETH/EUR", "trades", H).unlink()
    textfile = tmp_path / "reconcile.prom"
    args = [str(pri), str(sec), str(rec), "--mint", "--textfile", str(textfile)]

    assert _run(args, now=SETTLED, monkeypatch=monkeypatch).exit_code == 0

    assert _ledger(rec) == []
    assert not _seg_path(rec, "BTC/EUR", "book", H).exists()

    _write(pri, "ETH/EUR", "trades", H, _prints("ETH/EUR", H, [(600.0, 40), (900.0, 41)]))
    assert _run(args, now=SETTLED + timedelta(minutes=30), monkeypatch=monkeypatch).exit_code == 0

    [fleet] = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    [minted] = [r for r in _ledger(rec) if r["state"] == "minted" and r["pair"] == "BTC/EUR"]
    assert (fleet["verdict"], fleet["halt_seconds"]) == ("venue_halt", pytest.approx(1220.0))
    assert minted["residual_seconds"] == pytest.approx(0.0)
    assert _series(textfile)["zcrypto_reconcile_residual_gap_seconds_total"] == pytest.approx(0.0)


def test_a_failed_book_read_on_a_waiting_cycle_mints_nothing_before_the_fleet_record(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _plant_halt(pri, sec)
    _write(
        pri, "BTC/EUR", "book", H, _book("BTC/EUR", H, [(float(s), "update") for s in range(0, 3600, 10) if not 1200 <= s < 1830])
    )
    for root in (pri, sec):
        _seg_path(root, "ETH/EUR", "trades", H).unlink()
    book = _seg_path(sec, "ETH/EUR", "book", H)
    intact = book.read_bytes()
    textfile = tmp_path / "reconcile.prom"
    args = [str(pri), str(sec), str(rec), "--mint", "--textfile", str(textfile)]

    book.write_bytes(b"not a parquet")
    assert _run(args, now=SETTLED, monkeypatch=monkeypatch).exit_code == 1

    assert [(r["state"], r["pair"]) for r in _ledger(rec)] == [("failed", "ETH/EUR")]
    assert not _seg_path(rec, "BTC/EUR", "book", H).exists()

    book.write_bytes(intact)
    _write(pri, "ETH/EUR", "trades", H, _prints("ETH/EUR", H, [(600.0, 40), (900.0, 41)]))
    assert _run(args, now=SETTLED + timedelta(minutes=30), monkeypatch=monkeypatch).exit_code == 0

    [fleet] = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    [minted] = [r for r in _ledger(rec) if r["state"] == "minted" and r["pair"] == "BTC/EUR"]
    assert (fleet["verdict"], fleet["halt_seconds"]) == ("venue_halt", pytest.approx(1220.0))
    assert minted["residual_seconds"] == pytest.approx(0.0)
    assert _series(textfile)["zcrypto_reconcile_residual_gap_seconds_total"] == pytest.approx(0.0)


def test_a_trades_segment_unreadable_on_one_cycle_is_read_again_on_the_next(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _plant_halt(pri, sec)
    _seg_path(sec, "BTC/EUR", "trades", H).unlink()
    _seg_path(pri, "BTC/EUR", "trades", H).write_bytes(b"not a parquet")
    errors, warnings = _capture_logs(monkeypatch)
    args = [str(pri), str(sec), str(rec), "--mint"]

    assert _run(args, now=SETTLED, monkeypatch=monkeypatch).exit_code == 0

    assert _ledger(rec) == []
    assert [m for m in warnings if "booking deferred" in m and " missing=- unreadable=primary BTC/EUR -- " in m]

    _write(pri, "BTC/EUR", "trades", H, _prints("BTC/EUR", H, [(1185.0, 7), (1805.0, 8)]))
    assert _run(args, now=SETTLED + timedelta(minutes=30), monkeypatch=monkeypatch).exit_code == 0

    [record] = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    assert (record["verdict"], record["halt_seconds"]) == ("venue_halt", pytest.approx(1220.0))
    assert not errors


def test_a_trades_final_on_the_secondary_alone_is_enough_for_a_halt(tmp_path, monkeypatch):
    pri, sec, rec = _roots(tmp_path)
    _plant_halt(pri, sec)
    _seg_path(pri, "BTC/EUR", "trades", H).unlink()
    _, warnings = _capture_logs(monkeypatch)

    result = _run([str(pri), str(sec), str(rec), "--mint"], now=SETTLED, monkeypatch=monkeypatch)

    assert result.exit_code == 0
    [record] = [r for r in _ledger(rec) if r["state"] == "both_streams_silent"]
    assert record["verdict"] == "venue_halt"
    assert record["halt_seconds"] == pytest.approx(1220.0)
    assert not [m for m in warnings if "booking deferred" in m or "no trades segment" in m]
```

In `tests/test_archive_settle.py`, the comment

```python
    # 09:00 finalizes at 10:00 and is pulled by ~11:00; at 11:30 it is settled, 10:00 is not.
```

reads

```python
    # 09:00's book finals close at 10:00 and are pulled by ~11:00; at 11:30 it is settled, 10:00 is not.
```

- [ ] **Step 2: Run them red.** `uv run pytest tests/test_archive_reconcile_command.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`. Expected: `6 failed, 88 passed` — `test_a_pair_with_no_trades_final_on_either_mirror_leaves_the_hour_unproven`, `test_a_dark_hour_missing_a_trades_final_waits_for_it_and_books_a_halt_once_it_lands`, `test_a_pair_that_mints_inside_a_deferred_dark_hour_waits_for_the_fleet_record` and `test_a_trades_segment_unreadable_on_one_cycle_is_read_again_on_the_next`, each on an `assert _ledger(rec) == []` that finds the record booked at the first look, and `test_a_pair_that_minted_before_the_fleet_detector_ran_is_not_booked_twice` and `test_a_failed_book_read_on_a_waiting_cycle_mints_nothing_before_the_fleet_record`, each on its `== [("failed", "ETH/EUR")]` that finds BTC/EUR minted on the cycle whose book read failed; `test_a_trades_final_on_the_secondary_alone_is_enough_for_a_halt` passes, as it does on today's code.

- [ ] **Step 3: Write the code.** In `cli/archive/command.py`'s `from cli.archive.settle import (` block, `    LATE_MINT_HOURS,` directly after `    CAPTURE_DIVERGENT,`. Directly after the line `        present = [pair for pair, frames in books.items() if any(f is not None for f in frames.values())]`:

```python
        deferred = broken and not late
```

The lines from `                # So does a pair with no trades final on either mirror: a writer fault both hosts share` through the closing `                )` of the `_ledger(` call that ends the `if windows and not _decided("*", "book", hour, "both_streams_silent"):` block are replaced by:

```python
                # `cli/capture/segment_writer.py`'s trades writer closes a pair's hour only at its next print, so a quiet
                # pair's final can reach the NAS after the hour settles, and a trades read can fail on one cycle and
                # succeed on the next: until the late deadline the hour waits for both, with no fleet record and no
                # book heal, then books with whatever arrived.
                missing = [
                    p for p in present if all(hour not in scans[src]["trades"].get(p, set()) for src in ("primary", "secondary"))
                ]
                deferred = bool(missing or unread) and not late
                if deferred:
                    logger.warning(
                        "archive reconcile: booking deferred hour=%s until=%s missing=%s unreadable=%s -- a fleet-dark hour"
                        " waits for these trades segments, then books whatever arrived",
                        hour.isoformat(),
                        (hour + timedelta(hours=LATE_MINT_HOURS)).isoformat(),
                        ",".join(missing) or "-",
                        ",".join(unread) or "-",
                    )
                else:
                    # At the late deadline, so does a pair still with no trades final on either mirror: a writer
                    # fault both hosts share removes exactly the prints the proof reads.
                    for p in missing:
                        logger.warning("archive reconcile: no trades segment on either mirror pair=%s hour=%s", p, hour.isoformat())
                        unread.append(p)
                    verdict = VENUE_HALT if halt.holds and not unread and episode.verdict != CAPTURE_DIVERGENT else episode.verdict
                    halted = verdict == VENUE_HALT
                    # WARNING for a halt: `Ops · ERROR logs` pages on this line, and a halt is not loss.
                    (logger.warning if halted else logger.error)(
                        "archive reconcile: both_streams_silent hour=%s windows=%d residual_s=%.1f verdict=%s updates=%d snapshots=%d"
                        " divergent=%s halt_s=%.1f carried=%d/%d bracketed=%d/%d trades_inside=%d id_holes=%d quiet_s=%.3f",
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
                        halt.quiet_seconds,
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
                        quiet_seconds=halt.quiet_seconds,
                    )
```

The two lines

```python
        # --- the witness-based heal: books ------------------------------------------------------
        for pair in book_pairs:
```

read

```python
        # --- the witness-based heal: books ------------------------------------------------------
        # Waits while the fleet record cannot yet be decided -- a deferred hour, or a cycle before the late deadline
        # with an unreadable book segment: `_book_entry` subtracts only the seconds that record has booked, so a pair
        # minted first would book its share of the silence as loss.
        for pair in () if deferred else book_pairs:
```

In `_booked_residual`'s docstring, the lines

```python
    The mirror image of `_booked_dark`, and the reason the attribution is order-independent: an
    unreadable segment suppresses the fleet detector for a cycle, so a pair that mints in the
    meantime books its residual first and the fleet record must then book only the rest. Records
    written before residual was measured carry no `residual_gaps` and booked nothing, so they
    correctly subtract nothing.
```

read

```python
    The mirror image of `_booked_dark`, and the reason the attribution is order-independent: an
    unreadable segment suppresses the fleet detector for a cycle, and on one at or past the late
    deadline the book heal no longer waits for it, so a pair that mints in the meantime books its
    residual first and the fleet record must then book only the rest. Records written before
    residual was measured carry no `residual_gaps` and booked nothing, so they correctly subtract
    nothing.
```

and in the fleet block, the comment

```python
                # Minus whatever that stream's own book record already booked for the same seconds:
                # normally none exists yet, but after a cycle in which an unreadable segment
                # suppressed this detector, a pair that minted meanwhile booked its residual first.
```

reads

```python
                # Minus whatever that stream's own book record already booked for the same seconds:
                # normally none exists yet, but after a cycle at or past the late deadline in which an
                # unreadable segment suppressed this detector, a pair that minted meanwhile booked its
                # residual first.
```

In `cli/archive/settle.py`, the comment above `SETTLE_HOURS = 2`:

```python
# An hour is finalized at H+1h and carried to the NAS by the pull cycle that follows; H+2h gives both
# a full cycle to land, so a settled hour is complete on both mirrors or genuinely missing from them.
```

reads

```python
# An hour's book finals close at H+1h and are carried to the NAS by the pull cycle that follows; H+2h gives
# both a full cycle to land. `cli/capture/segment_writer.py`'s trades writer closes a pair's hour only at its
# next print, so a quiet pair's trades final can land later than that.
```

`uv run ruff format cli/archive/command.py tests/test_archive_reconcile_command.py` then rewrites nothing.

- [ ] **Step 4: Run them green.** `uv run pytest tests/test_archive_settle.py tests/test_archive_reconcile_command.py tests/test_archive_scan_cache.py tests/test_archive_reconcile.py tests/test_archive_mint.py tests/test_trades_backfill.py tests/test_bench_ledger_scan.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`. Expected: `340 passed`. Then the per-commit run of the Global Constraints over `cli/archive/command.py cli/archive/settle.py tests/test_archive_reconcile_command.py tests/test_archive_settle.py` (`1106 passed, 44 warnings` in the scratch run).

- [ ] **Step 5: Commit** `fix(archive): a fleet-dark hour missing a trades file waits for it until the late deadline before it books`, after the gate, the per-commit run's result line in the body.

- [ ] **Step 6: Probe** each arm on the committed tree, as the Global Constraints say:

| Arm | Selection (`-k`) | Mutation |
|---|---|---|
| 1. The wait | `waits_for_it_and_books_a_halt` | `s/deferred = bool(missing or unread) and not late/deferred = False/` |
| 2. The bound is the late deadline | `no_trades_final_on_either_mirror_leaves` | `s/deferred = bool(missing or unread) and not late/deferred = bool(missing or unread)/` |
| 3. An unread tape waits | `unreadable_on_one_cycle` | `s/deferred = bool(missing or unread) and not late/deferred = bool(missing) and not late/` |
| 4. The heal waits | `mints_inside_a_deferred` | `s/for pair in () if deferred else book_pairs:/for pair in book_pairs:/` |
| 5. The wait's line is a WARNING | `waits_for_it_and_books_a_halt` | `/deferred = bool/,/booking deferred/s/logger.warning(/logger.error(/` (count over the range `/deferred = bool/,/booking deferred/`, pattern `logger.warning(`) |
| 6. A final on one mirror ends the wait | `one_mirror_is_enough` | `s/p for p in present if all(hour not in/p for p in present if any(hour not in/` |
| 7. A failed book read holds the heal | `failed_book_read_on_a_waiting_cycle` | `s/deferred = broken and not late/deferred = False/` |
| 8. That hold ends at the late deadline | `minted_before_the_fleet_detector` | `s/deferred = broken and not late/deferred = broken/` |
| 9. The secondary's final ends the wait too | `secondary_alone_is_enough` | `s/for src in ("primary", "secondary")/for src in ("primary",)/` |

Each selection collects one case of 94. Every arm reads `mutate-probe: KILLED (control proven, tree restored byte-identically)`. Then the probes commit, subject `test(archive): the deferred booking proven by infra/scripts/mutate-probe.sh`.

### Task 2: The capture and ops pages and the README say the booking can wait (spec *What stays true for an operator*)

**Files:**
- Modify: `infra/runbooks/capture.md`, `infra/runbooks/ops.md`, `README.md`

- [ ] **Step 1: Load the `zcrypto-refine-rules` skill**, its own call: both pages are top-level runbook pages under its edit contract. Every text below adds no universal word to its list item but those its item's `(no count command: …)` already covers.

- [ ] **Step 2: Replace each text once**, the left fence by the right; each left fence matches exactly one place in its file. In `infra/runbooks/capture.md`, the venue-status section's step 2, and in `infra/runbooks/ops.md`, the residual-gap section's *What it means* — the same list in both pages, replaced in both:

```text
an unreadable trades segment, a pair with no trades segment on either host, a divergence
```

```text
an unreadable trades segment or a pair with no trades segment on either host six hours after the hour's start, a divergence
```

the same step:

```text
Do not close the incident before the reconciler has spoken (no count command:
```

```text
A pair's trades segment that has not reached the NAS — a quiet pair's closes only at its next print — or that fails to read holds the booking: each `:12`/`:42` cycle reads the hour again and logs `archive reconcile: booking deferred hour=… until=… missing=… unreadable=…` at WARNING, ledgering no `both_streams_silent` record and no book-heal record, until the segment lands or six hours past the hour's start, the `until=` stamp, then books with whatever arrived. Do not close the incident before the reconciler has spoken (no count command:
```

its step 5:

```text
which the loss page reports about two hours later.
```

```text
which the loss page reports two to six hours later.
```

the all-streams-silent section's *What it means*:

```text
Whether it cost data is the reconciler's answer, about two hours later —
```

```text
Whether it cost data is the reconciler's answer, two to six hours later —
```

its step 4:

```text
so hour H is bookable no earlier than H+2 h, at the next `*:12`/`*:42` tick. Reading
```

```text
so hour H is bookable no earlier than H+2 h, at the next `*:12`/`*:42` tick, and an hour waiting on a pair's trades segment books when it lands or at the first tick six hours past its start (the venue-status section's step 2). Reading
```

In `infra/runbooks/ops.md`, the residual-gap section's step 4:

```text
so an hour-H gap booked at the `:12`/`:42` tick after H+2 h holds the alert firing
```

```text
so an hour-H gap booked at a `:12`/`:42` tick — the first after H+2 h, or a later one up to the first tick six hours past H's start for a fleet-dark hour waiting on a trades segment (step 6) — holds the alert firing
```

its step 6:

```text
WARNING for the hour, is why: a divergence keeps its loss, and a trades file the reconciler cannot read, or a pair with none on either host, leaves the hour unproven.
```

```text
WARNING for the hour on the cycle that booked it, is why: a divergence keeps its loss, and a trades file the reconciler cannot read, or a pair with none on either host, leaves the hour unproven. Such an hour waited for the file first: each cycle before the booking logged `archive reconcile: booking deferred hour=… until=… missing=… unreadable=…` at WARNING and ledgered no `both_streams_silent` record and no book-heal record for the hour, until the file landed or six hours past the hour's start, the `until=` stamp.
```

In `README.md`'s reconciler paragraph:

```text
An hour is considered once `now ≥ H + 2h` (finalization plus one pull cycle have both had time to land)
```

```text
An hour is considered once `now ≥ H + 2h` (its book finals plus one pull cycle have both had time to land)
```

and

```text
is minted from the complete secondary alone. Healing is
```

```text
is minted from the complete secondary alone. A fleet-dark hour in which a pair's trades final is absent from both mirrors, or does not read, waits for it until `H + 6h` before its `both_streams_silent` record is decided — a quiet pair's trades final closes only at its next print — and the hour's book heal waits with it. Healing is
```

- [ ] **Step 3: Check the pages.** `uv run pre-commit run --files infra/runbooks/capture.md infra/runbooks/ops.md README.md` passes with nothing rewritten; `uv run python infra/scripts/guidance-guard.py --uncounted infra/runbooks/capture.md infra/runbooks/ops.md` prints nothing and exits 0.

- [ ] **Step 4: Commit** `docs(runbooks): the reconciler's booking of a fleet-dark hour can wait up to six hours for a trades file`, after the gate and the per-commit run over the three paths, its result line in the body (`6534 passed, 1 deselected, 44 warnings` in the scratch run).

### Task 3: The decisions log's `[iter-214]` entries (spec D1–D6, D8)

**Files:**
- Modify: `docs/research/14.phase6-decisions.md` (append)

- [ ] **Step 1: Append** to the end of `docs/research/14.phase6-decisions.md`, after its last line, the entries below, the first line blank. D7 takes no entry: a reversible engineering choice (`iteration-closeout`).

```markdown

[iter-214] A quiet pair's trades file closes only at its next print, so it can reach the NAS after the reconciler has booked a fleet-dark hour, as 2026-11-26 08Z's halt was booked as loss. What should the reconciler do when a fleet-dark hour still lacks a trades file for some pair? (Decision: 1)
  Asked 2026-11-26T10:49:46Z, verbatim: "The cause is a race: an hour's trades file is closed only when the pair next trades, so a quiet pair's file can reach the NAS after the reconciler's two-hour settle has already booked the hour. What should the reconciler do when a fleet-dark hour still lacks a trades file for some pair?" The owner's answer by 10:51:44Z, verbatim: "Defer the booking, bounded (Recommended)".
  1. **Defer the booking, bounded (Recommended)** — verbatim: "A both-streams-silent hour with a missing trades file is not booked yet; it is re-read each cycle until the file arrives or a bound passes (I propose H+6 h), then booked as today. Its own short spec and plan, reviewed, landing through an attended converge of this workstation's ops role." **Taken** (owner, 2026-11-26).
  2. **Book now, re-classify later** — verbatim: "Keep booking at H+2 h as today, and add an automatic correction when the missing file arrives. That makes the append-only ledger correct itself, which the runbook today says never happens; a bigger design change."
  3. **No fix, accept the limit** — verbatim: "Record it as a fourth accepted limitation in the capture runbook. A quiet pair during a venue halt can again turn a harmless halt into booked loss and a 24-hour alert."

[iter-214] While a fleet-dark hour's booking waits for a trades file, does the hour's book heal run or wait? (Decision: 1)
  Asked 2026-11-27T16:11:03Z, verbatim: "D4. While a fleet-dark hour's booking waits for a missing trades file, should that hour's book heals wait with it? If they don't, a pair whose two capture copies resume a little apart inside a halt books those seconds as permanent loss immediately, and that pages." The owner's answer by 16:18:57Z, verbatim: "Heals wait too (Recommended)".
  1. **It waits with the booking** — the hour's book mints land with its booking, at the latest on the first cycle six hours past the hour's start, the late mints' own deadline; the booking is decided first and the heal subtracts the seconds it booked. On the spec's fixture a waiting halt books 0 s of loss and 1220 s of halt. **Taken** (owner, 2026-11-27).
  2. **It runs as before** — a pair whose two mirrors resume apart inside a waiting halt mints first and books its unfilled seconds as permanent loss, which pages with no `both_streams_silent` record to read; 610 s of loss and 610 s of halt on the same fixture.

[iter-214] Before the late deadline, does an hour's book heal also wait out a cycle on which one of its book files fails to read? (Decision: 1)
  Asked 2026-11-27T17:12:56Z, verbatim: "D4 follow-up, from the plan review: you picked 'heals wait too', but the plan's code only holds the heal on a cycle where every book file reads. If one of an hour's book files fails to read on one of the waiting cycles (a transient NFS error, say), the fleet check is skipped and the hour's heal runs first. On the reviewer's run that booked 610 s of a provable halt as permanent loss and paged residual-gap with no fleet record. Should an hour whose book read fails before H+6 h hold its heal too?" The owner's answer by 17:13:09Z, verbatim: "Hold the heal too (Recommended)".
  1. **Hold the heal too (Recommended)** — verbatim: "An hour whose book file fails to read on a cycle before H+6 h mints nothing that cycle. That cycle already fails (exit 1), and the next clean cycle decides the fleet record first, then heals. On the fixture: 0 s loss, 1220 s halt. Cost: an ordinary hour with a failed book read heals one cycle later; a book file corrupt for good holds its hour's heals until H+6:12, today's late-mint deadline; today's broken-read test is rewritten." **Taken** (owner, 2026-11-27).
  2. **The heal runs on that cycle** — the hour's other pairs mint ahead of the fleet record, as before; on the review's fixture 610 s of a provable halt book as permanent loss and page residual-gap with no fleet record.

[iter-214] Does a trades file that fails to read wait for the bound like an absent one? (Decision: 1)
  Asked 2026-11-27T16:11:03Z, verbatim: "D5. Should a trades file that exists but fails to read (for example a transient NFS error) wait like a missing one?" The owner's answer by 16:18:57Z, verbatim: "Yes, same bound (Recommended)".
  1. **Yes, to the same bound** — a read that fails on one cycle is read again on the next; a file corrupt for good holds its hour's loss booking and page until six hours past the hour's start. **Taken** (owner, 2026-11-27).
  2. **No, only an absent file waits** — the ruling's words; a read that fails once books a provable halt as loss, once and for good, and pages.

[iter-214] What shows that a fleet-dark hour's booking is waiting? (Decision: 1)
  Asked 2026-11-27T16:11:03Z, verbatim: "D6. What should show that a booking is waiting?" The owner's answer by 16:18:57Z, verbatim: "A WARNING per cycle (Recommended)".
  1. **One WARNING per waiting cycle** — `archive reconcile: booking deferred hour=… until=… missing=… unreadable=…`, at most eight for an hour, paging nothing; no metric and no ledger record. **Taken** (owner, 2026-11-27).
  2. **The WARNING and a gauge of the hours waiting** — a new series in the textfile, a panel on the integrity board and a Grafana push after the converge; no rule reads it.
  3. **The WARNING and a ledger record per waiting hour** — a new state that moves no counter, joining the README's state list and the ledger-scan bench's.
```

- [ ] **Step 2: Commit** `docs(research): the [iter-214] entries, the owner's ruling on the deferred booking and four picks`, after the gate; `consumers.sh` lists no reader for the log, so the run is `uv run pytest tests/test_decisions_log_shape.py tests/test_decisions_log_ties.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` (expected `50 passed`), its result line in the body.

### Task 4: The rollout — the owner's ops converge, the coordinator's reads around it (spec D8, *The converge*)

After the branch merges; no implementer runs it, and nothing here is committed on this branch. Every host read runs through `infra/scripts/host-run.sh hp …`, one check per call, its output read whole; the converge line is the owner's to type.

- [ ] **Step 1: The image.** The ops image built from `develop` at or after the merge commit, its digest the CI build's, as the skill's *Phase 0 — Preflight* step 2 takes a candidate (`.claude/skills/zcrypto-rollout-image/SKILL.md`), pulled on `zcrypto-ops` (every runner is `--pull never`) and checked to carry the change.
- [ ] **Step 2: The running digests,** each by value, against `docs/reference/fleet-pins.md`'s `zcrypto-ops` rows, the operand `infra/runbooks/ops-node.md`'s on-chain procedure step 5 prescribes for each: `sudo docker inspect zcrypto-ops-liquidations --format 'img={{.Config.Image}} restarts={{.RestartCount}} started={{.State.StartedAt}}'` against the `ops (timers + liquidations)` row, `sudo docker inspect --format '{{.Config.Image}}' zcrypto-onchain-bitcoind` against `bitcoind`, `sudo docker inspect --format '{{.Config.Image}}' zcrypto-onchain-bitview` against `bitview`; the Alloy digest the host carries is `alloy_image_digest` in `infra/ansible/group_vars/observed/alloy.yml`, or the host's own `infra/ansible/host_vars/zcrypto-ops/alloy.yml` while it is held. A print the file does not record holds for the owner's word.
- [ ] **Step 3: Kraken's maintenance feed**, `https://status.kraken.com/api/v2/scheduled-maintenances.json`, read whole by `.claude/rules/fleet-deploys.md`'s test, at planning; an entry that is a window over the planned time holds the converge.
- [ ] **Step 4: The preview**, the coordinator's: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags ops --check -e ops_image_digest=sha256:<new> -e ops_alloy_digest=sha256:<step 2's> -e ops_bitcoind_image_id=sha256:<step 2's> -e ops_bitview_image_id=sha256:<step 2's> -e liquidations_decision=roll-after`; any diff not intended stops it.
- [ ] **Step 5: The feed again, immediately before**, read whole.
- [ ] **Step 6: The converge**, the owner's one line: step 4's without `--check`, never under `timeout`.
- [ ] **Step 7: Verify by value** after the next `:12`/`:42` tick: `bash infra/scripts/ops-postverify.sh`, every check passing — `(no series)` is a fail.
- [ ] **Step 8: Record it:** the converge's deploy-log line committed with the `ops (timers + liquidations)` row re-trued from it on a branch, by `fleet-pins.md`'s rules; then `uv run python infra/scripts/prune-host-images.py zcrypto-ops` and its `--apply`, by the skill's rule.
