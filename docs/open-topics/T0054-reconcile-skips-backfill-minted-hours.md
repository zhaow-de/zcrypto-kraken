---
status: open
ripe_when: before the reconciler is switched from --detect-only to --mint (that flip is gated on T0039's cross-host soak) — the interaction only becomes real at that moment
---

# The reconciler will permanently skip any hour the trade-backfill minted first

## Context — what

Both the reconciler and the trade-backfill (spec `00053`, iter-100) mint into the same `capture-reconciled` overlay, by design — consumers read it reconciled-first via `canonical_segments`, so healed hours are picked up with no consumer change.

But `cli/archive/command.py:538` has the reconciler skip any hour that is `already_minted(...)`. Found by the iter-100 final review. The two are on a collision course *in time*:

- The reconciler currently runs **`--detect-only`** (mints nothing), pending [[T0039]]'s cross-host soak that must pin `--min-gap-seconds`.
- The trade-backfill mints **now**, and sweeps the **whole archive** with no trailing window.

So the backfill will mint hours long before reconcile is ever switched to `--mint`. When that flip happens, reconcile will `already_minted → continue` past every one of them — **permanently**, since the skip is unconditional.

## Why this matters

It is an unowned, silent interaction between two writers of one overlay, and the flip that activates it ([[T0039]]) is scheduled work someone will do without necessarily remembering this.

The honest assessment is that the current behaviour is **probably the right one**, which is exactly why it needs registering rather than fixing on a hunch:

- For **trades**, REST is a strictly better witness than the secondary mirror: it is the venue's own record, and it can heal correlated loss (both mirrors dark) that the reconciler explicitly cannot — *"when both streams are dark there is no witness to heal with, so the loss is permanent"*. The largest gap found (974 BTC trades, 2026-07-08) predates the secondary entirely.
- So the skip **protects** the backfill's richer union from being rebuilt as raw-primary ∪ raw-secondary, which would be a strictly poorer frame for that hour.
- The raw mirrors are untouched throughout, so nothing is destroyed either way.

The risk is narrower but real: an hour the backfill minted **for trades** is thereafter invisible to reconcile **for books** too, if reconcile's skip is per-hour rather than per-kind. That wants checking before the flip, not after.

## Findings so far

- `already_minted(root, pair, kind, hour)` takes `kind` — so the skip may already be per-`kind` and the book path unaffected. **Verify this before designing anything**; if it is per-kind, this topic likely collapses to a documentation note.
- The backfill mints only `kind="trades"`; it never touches book hours.
- The backfill's mint is monotone: it reads the existing overlay hour first (reconciled-first) and unions, so re-minting can never *reduce* an hour. A reconcile that later re-minted the same trades hour from raw mirrors alone, however, could.
- Discovered while reviewing iter-100; not triggered today because reconcile mints nothing.

## Suggested next steps

- **(autonomous, first — it may end this topic)** Check whether `already_minted`'s skip in `cli/archive/command.py:538` is scoped per `kind`. If yes: the book path is unaffected, and the only remaining question is whether trades-hour skipping is desirable (it probably is — see above). Record the finding and close or downgrade accordingly.
- **(autonomous, if the skip is NOT per-kind)** Make it per-kind, so a trades-only backfill mint cannot shadow a book hour reconcile would otherwise heal. Books are unbackfillable; a shadowed book heal is the one outcome here that would actually cost data.
- **(process)** Re-read this topic at the [[T0039]] flip — that is the moment the interaction becomes live, and this file is the only place the interaction is written down.
