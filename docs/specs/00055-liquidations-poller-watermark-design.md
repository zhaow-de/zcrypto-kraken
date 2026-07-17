# 00055 — The liquidations poller stops re-submitting at source (T0060)

Ratified 2026-07-17 in an attended session (the owner's three directives on the T0060 findings, plus the follow-up: "the poller should stop re-submitting at source rather than submitting-then-dropping"). Resolves [[T0060]]'s remaining sub-item. The implementation plan is `docs/plans/00055-liquidations-poller-watermark.md`.

## Goal

The Coinalyze liquidations poller re-fetches a wide catch-up window every ~5 minutes and re-submits every closed bucket — ~1,318 per cycle — relying on `SegmentWriter`'s dedup to drop what is already written, and logging a WARNING per drop: **~15,800 warnings/hour, 99.9% of the container's log volume** (measured 2026-07-16: 86,846 WARNING vs 87 INFO in one rotation window). Stop the re-submission at source, so the writer's dedup stops being a garbage disposal and becomes a genuine anomaly detector: any drop that still fires is *signal*.

## The invariant this design must not break

`cli/liquidations/coinalyze.py`'s module docstring, load-bearing and explicit:

> *Overlap-safety invariant (do not "optimize" away): each cycle re-fetches the whole catch-up window and re-submits every closed bucket. TWO mechanisms make that safe, not one: SegmentWriter's dedup [and] the writer's late-event floor. Narrowing the window or touching the floor logic must preserve both.*

The wide window is what makes a failed cycle self-healing (the next cycle's fetch covers the missed span). This design therefore changes **submission only**: the fetch window is untouched, the floor is untouched, and the dedup remains in place as the second mechanism — it just stops being *guaranteed* steady-state work.

## Decisions

- **D1 — Filter at submission, never at fetch.** `poll_cycle` keeps fetching the full catch-up window exactly as today. Before submitting a proven-closed bucket to a coin's writer, consult a **per-coin watermark**: buckets `<= watermark` are skipped *before* the writer (no dedup lookup, no log line); buckets above it submit exactly as today.
- **D2 — The watermark is in-memory, advanced on submit, and primed from disk at startup.** Durability analysis drove this shape:
  - *Advance on submit* (not on flush): simple, monotone per coin, no new writer API on the hot path.
  - *Why in-memory is safe*: a recorder crash loses the watermark — and that is correct, because buckets submitted but not yet flushed died with the process. On restart the watermark re-primes from **what is actually on disk** (the newest persisted bucket per coin, read from the recorder's own tree), the wide fetch window re-covers everything above it, and the un-persisted tail is re-submitted. No new durable state, no fsync discipline, no hole.
  - *Priming source*: the persisted segments themselves (newest bucket `t` per coin), via a small read-only helper at recorder startup. A coin with no persisted data primes to "nothing" and the first cycle submits its whole window — today's behavior, once.
- **D3 — The surviving WARNING stays a WARNING.** With steady-state re-submissions gone, a writer-level dedup drop means something is actually wrong (a watermark bug, an upstream replay, a duplicate from Coinalyze). Demoting it was the fallback option; the owner's ratified direction makes it unnecessary. The capture daemon's identical warning (WS resubscribe replay) is untouched — it was always meaningful there.
- **D4 — The cycle log tells the truth in one line.** `poll cycle submitted N closed bucket(s)` becomes `poll cycle: submitted=N skipped_at_watermark=M window=[…]` — the skip count is the evidence the fix works, visible per cycle in Loki, no per-event lines.
- **D5 — The restart-duplication question MUST be answered with a test, not an assumption.** `SegmentWriter._seen` initializes **empty** on construction; only held hours reseed from disk (`_held_seen`). So today, after a recorder restart mid-hour, a re-submitted bucket for the **current open hour** may pass dedup (empty set) and not be droppable by the floor (same hour). If that appends a duplicate row to the hour, it is a live, pre-existing correctness bug this design happens to fix (the disk-primed watermark skips those buckets before the writer). The implementation must (a) determine the truth by test — restart the writer over a written-but-open hour, re-submit, read the hour back; (b) if duplication is real, add the regression test to the suite and record the finding in T0060; (c) if it is not (some other mechanism intervenes), document *which* mechanism in the module docstring, because three readers have now failed to find it.
- **D6 — No CLI or config surface changes.** The watermark is recorder-internal. No new flags, no `zcrypto.toml` entries, no README change (per `readme-usage.md`, nothing user-facing moved).

## Non-goals

The fetch window and `_FINALIZE_LAG_SECONDS`/floor logic (the invariant above). Any Alloy/alerting change (the T0060 infra half already shipped in PR #141). **Deploying to ops** — the poller restart is REST-lookback-tolerant by design, but the deploy is an attended step after this PR merges, and its verify-by-outcome (the `dropping replayed event` rate falling from ~15,800/h to ~0) belongs to that step.

## Verify

In-scope proof is test-level: a multi-cycle simulation (overlapping windows, a failed cycle, a restart with re-priming) asserting zero writer-level dedup drops in steady state, correct catch-up after failure, and the D5 answer. Every new test mutation-verified able to fail. The post-deploy outcome measurement is recorded in T0060 as the closing evidence when the deploy happens.

## D5 outcome (measured 2026-07-17)

No duplication. The presumed live bug does not exist: `_open_hour` reseeds `_seen` from the open hour's `.part` files (the T0026 seeding, `segment_writer.py:614-616`), so a dedup-keyed writer restarted over an open hour with flushed parts drops a re-submitted event rather than appending it. The abrupt-death variant (no clean close) loses the unflushed buffer entirely — those rows never reached disk, so re-submission is recovery, not duplication. Pinned by the regression test `test_restart_reseeds_dedup_keys_from_open_hour_parts` in `tests/test_capture_segment_writer.py`.
