---
status: resolved
---

# `req_id`-correlated resubscribe: make a failed attempt say so

## Context — what

Recovery from a checksum desync sends `unsubscribe` then `subscribe` as two fire-and-forget frames, with no correlation to Kraken's responses. [[T0008]]'s ladder (spec `00072`) made recovery *robust* to that — it retries and escalates on continued desync — but deliberately did not make a failed attempt **observable**.

Correlating the frames by `req_id` would: wait for `unsubscribe_ack` before sending `subscribe`, and treat `unsubscribe_error` / `subscribe_error` as an explicit signal rather than an inference.

## Why this matters

**It is prevention for one of the two failure causes, and observability for both.**

- *Prevention:* the race where `subscribe` overtakes `unsubscribe` server-side and is rejected disappears by construction if the ack is awaited.
- *Observability:* today a failed resubscribe leaves **no trace of its own** — it is only inferable from the pair still being desynced. An error frame is something to count, log, and alert on.

It is explicitly **not** a substitute for the ladder, and spec `00072` D6 records why: a snapshot that fails its own checksum produces no error frame at all — Kraken is satisfied, the protocol succeeded, the book is wrong. Correlation cannot see that case. Anything replacing the ladder with correlation would reintroduce half the defect.

## Findings so far

- The ladder's logging already closes part of the gap: `desync recovery: retrying resubscribe` and the escalation ERROR now mark a failed attempt where nothing did before. What is still missing is *why* it failed.
- Cost is real and lands on the unbackfillable capture path: `req_id` plumbed through `parse_message`'s ack/error classification, plus per-pair pending-request state in `CaptureClient`.
- Hard to drill. [[T0008]]'s fault — a bad snapshot — is inducible in-process with a duration knob; making Kraken *reject* an unsubscribe on cue is not. Any build should say up front how it will be validated, given that a fix nobody can prove ran is the exact trap [[T0035]] and [[T0008]] both fell into.

**One defect found after archiving, fixed on PR #223** (recorded here rather than left to a reader who would otherwise trust the design as described above): the waiter guarded on `self._ws is None` rather than on socket identity. A reconnect inside the 5 s ack window installs a NEW socket and resubscribes every pair on it, and the stale waiter then sent a duplicate single-pair subscribe — which Kraken rejects as "Already subscribed", logged at ERROR, and the ops log rule pages on any capture ERROR. So a benign reconnect paged, and the new rejection counter reported a fault that had not occurred. The waiter now captures its socket and returns unless it is still current.

## Resolution

**Resolved 2026-07-28 — both halves built** (owner decision: observability *and* prevention), on the same branch as [[T0104]].

- **Prevention.** Both frames now carry a `req_id`, and the `subscribe` is deferred until the `unsubscribe` is acknowledged — the ordering race is closed by construction rather than hoped past.
- **Observability.** `resubscribe_errors_total` counts an explicit rejection of *either* frame (the subscribe carries its own id precisely because a rejected subscribe is the more interesting failure), and the rejection is logged. Where a failed attempt previously left no trace of its own, there is now a count and a line.
- **The design constraint that decided the shape**, recorded because the obvious implementation deadlocks: rung 1 calls `resubscribe_book` from inside the message handler — the task that drives `stream()`. Awaiting the ack there would block the loop that delivers it. So `resubscribe_book` never awaits; it registers the pending id and hands the second frame to a short-lived waiter task.
- **A lost ack degrades, never strands.** The waiter times out at 5 s and subscribes anyway, falling back to exactly the old ordering, and counts `resubscribe_ack_timeouts_total` so the degradation is visible. **That claim was false when written** — review found both new counters were plain attributes exported nowhere, which is a counter nothing publishes, the same defect class this family names elsewhere as a column nothing writes. Corrected 2026-07-28 on PR #223: both reach `CaptureCollector` and the Alloy keep-regex (an allow-list — an unadmitted series is dropped silently at remote-write), and the `zcrypto-capture-resubscribe-failing` rule watches them, since the ack timeout logs at WARNING and previously reached nothing at all. **The image carrying any of this is not yet rolled** — [[T0107]]. Stranding a pair is the failure [[T0008]]'s ladder exists to remove; trading it for a closed race would have been strictly worse.
- **Correction (2026-09-12), on the sweep's read of the archive:** "The image carrying any of this is not yet rolled — [[T0107]]" is contradicted by [[T0107]]'s own Resolution, shown by `grep -n 'The payload rolled' docs/open-topics/archive/T0107-deferred-capture-image-payload.md` → line 30, "**The payload rolled 2026-07-29** as sha256:99faf16514e3…ab44, built from 3540b0bb", with `head -2 docs/open-topics/archive/T0107-deferred-capture-image-payload.md` → `status: resolved`. The secondary took it at 00:52:53Z and the primary at 07:36:13Z after a 6 h 43 m bake, and both counters this bullet names now arrive in Cloud (`zcrypto_capture_resubscribe_errors_total` and `zcrypto_capture_resubscribe_ack_timeouts_total`, 2 series each), verified from the image's own surface rather than the tag. The adjacent "**Not deployed by this topic.**" paragraph stays true as scoped: the roll was T0107's, not this topic's.
- **The validation question this topic raised is answered by construction, not by a drill.** It asked how an error path that cannot be induced against real Kraken would be validated. The answer: the correlation seam is unit-tested in both directions (ack-releases, timeout-degrades, rejection-counts), and the consumer wiring carries a mutation-verified seam test — so the mechanism is proven to *run* without needing the venue to reject anything on cue.

**Not deployed by this topic.** Capture-daemon code on the unbackfillable path reaches the fleet via an image build, the secondary bake gate, then the primary re-pin (`fleet-deploys.md`, mechanics in the `zcrypto-rollout-image` skill).

**The two steps this topic carried at its close, kept verbatim with what answered each:**

- **(autonomous, on trigger) Decide scope first: observability-only, or prevention too.** Counting and logging `unsubscribe_error`/`subscribe_error` is much cheaper than awaiting acks and needs no state machine — and it delivers most of the value, since the ladder already handles the failure. Awaiting the ack is the larger half and only addresses cause 2. — **ANSWERED:** the scope was decided before building and the decision was *both* halves (the owner's), which is what this Resolution's head records: the Prevention bullet (a `req_id` on both frames, the `subscribe` deferred until the `unsubscribe` ack) and the Observability bullet (`resubscribe_errors_total`, plus the logged rejection).
- **(same iteration) Name the validation method before building.** If the error path cannot be drilled against real Kraken, say so and lean on unit tests plus a metric that would reveal the path executing in production — rather than shipping a second unexercised handler. — **ANSWERED:** the method was named rather than a drill improvised, in this Resolution's last bullet — the correlation seam is unit-tested in both directions (ack-releases, timeout-degrades, rejection-counts) and the consumer wiring carries a mutation-verified seam test. The production-revealing metric half landed too, after review found the counters published nowhere: both reach `CaptureCollector` and the Alloy keep-regex, and `zcrypto-capture-resubscribe-failing` watches them.
