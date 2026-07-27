---
status: open
ripe_when: a resubscribe is observed failing in production — which the [[T0008]] ladder now makes visible, since a retry or an escalation is logged where previously a failed attempt left no trace at all. Also ripe if a stuck-pair alert fires and the ladder's own logs cannot explain why the resubscribe did not take
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

## Suggested next steps

- **(autonomous, on trigger) Decide scope first: observability-only, or prevention too.** Counting and logging `unsubscribe_error`/`subscribe_error` is much cheaper than awaiting acks and needs no state machine — and it delivers most of the value, since the ladder already handles the failure. Awaiting the ack is the larger half and only addresses cause 2.
- **(same iteration) Name the validation method before building.** If the error path cannot be drilled against real Kraken, say so and lean on unit tests plus a metric that would reveal the path executing in production — rather than shipping a second unexercised handler.
