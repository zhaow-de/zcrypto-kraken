---
status: resolved
---

# Byte-exact CRC re-derivation from the archive needs raw-string price/qty

## Context — what

Kraken's L2 book feed carries a CRC32 checksum per message; the capture daemon validates it live (`cli/capture/book.py::OrderBook.checksum`/`validate`) and stores the message's checksum in the archive's `BOOK_SCHEMA` `checksum` column. A natural archive-integrity oracle is to **replay** the stored book segments back through `OrderBook` and re-derive the CRC, confirming byte-for-byte that the archived rows still reconstruct the exact book the exchange attested. Discovered while planning OPS-3 (spec 00051): this is **not achievable from the archive as stored**. `BOOK_SCHEMA` persists `price`/`qty` as **Float64** (`cli/capture/command.py:154-155` writes `float(level["price"])`), but Kraken's CRC is computed over the **raw wire-format decimal strings** where trailing zeros are load-bearing (`_format_level`, `book.py:26-31`: `"0.30000000"` → `"30000000"`, whereas `float 0.3` → `Decimal("0.3")` → `"3"`). Reconstructing `Decimal`s from the stored floats drops those trailing zeros, so a recomputed CRC will mismatch the stored `checksum` for the many levels ending in zeros — a guaranteed false alarm, not a real corruption signal.

## Why this matters

It bounds what archive self-attestation can prove. OPS-3's continuity-replay verifier (built in spec 00051) proves the archive **reconstructs a coherent book** — snapshot-anchored hours, updates applying in order, no structural desync — and treats the stored `checksum` as capture-time ground truth (it *was* CRC-validated live). That catches silent archive/reconciler corruption of the row *structure*, which is the main risk. What it cannot do is independently re-attest the exchange CRC from the archive, so a corruption that altered a price/qty value while keeping the row structure valid *and* left the stored checksum column untouched would pass. Combined with the known limit that Kraken's CRC covers only the **top 10** levels ([[T0033]]), full-depth byte-exact archive attestation is simply not available today. This is a completeness gap in the durability story, not an active bug.

## Findings so far

- The blocker is the Float64 storage of `price`/`qty` in `BOOK_SCHEMA` (`cli/capture/segment_writer.py:16-24`; written as floats at `cli/capture/command.py:146-158`). The CRC needs the exact wire strings.
- OPS-3 (spec 00051, `cli/archive/replay.py`) delivers the achievable-now check: structural continuity + desync replay, stored-checksum-as-ground-truth. It explicitly does **not** compare a re-derived CRC.
- A fix would add raw-string `price_str`/`qty_str` columns (or replace the floats) to the captured book schema — a **capture-daemon change on the unbackfillable live stream**, so it is gated behind a capture image re-pin (canary rule + primary clean-run embargo, [[T0032]] / `.claude/rules/fleet-deploys.md`) and only ever attests data captured *after* the change (pre-change history stays float-only forever).

## OPS-3 decision (2026-07-15)

Per the owner's call, OPS-3 (spec 00051) does **not** wait on this. It ships:

- the **verified-path** replay as the primary oracle (`zcrypto engine replay --path verified` scheduled on the ops node — fully valuable, needs no CRC, already exists), and
- a **minimal** book continuity-replay (`cli/archive/replay.py`, Task 6) that checks only what is derivable *without* the CRC: each canonical hour is snapshot-anchored, rows are ts-ordered, the `checksum` column is present/non-null (capture-time attestation exists), the book replays through `OrderBook` without a structural throw, and — its one genuinely new payoff — the reconciler's **spliced output stays coherent across splice boundaries** (Role C keeps snapshot rows at the boundary for exactly this). It deliberately does **not** attempt the unreliable "structural desync" heuristic (for a depth-bounded book, a legitimate update to an out-of-window level is indistinguishable from corruption without the CRC).

The **richer, byte-exact CRC book-replay is deferred to this topic** — it is precisely what the raw-string schema change below unblocks.

## Resolution

**Consciously DROPPED 2026-08-23 on the owner's ruling at the grooming — the completeness gap is accepted, not denied.**

The topic's own text demanded "a decision, not indefinite parking", and this is that decision. The cost side is a schema migration on the **unbackfillable live capture stream**: two extra string columns in `BOOK_SCHEMA`, the raw WS strings threaded through `_handle_book_message`, larger segments forever after, and a gated capture re-pin to ship it. The benefit side is byte-exact CRC re-attestation for post-change, top-10-depth data only — older float-only segments keep the structural check regardless, so the gap never closes retroactively.

What settled it is that the cheaper path has held. The OPS-3 continuity-replay shipped **without** CRC re-derivation on 2026-07-15 and has run since; in the intervening weeks no discrepancy has appeared that the structural check could not localise — which was the exact condition this topic named for revisiting. Paying a live-stream schema change for an attestation nothing has yet needed is the wrong trade against a path whose whole premise is that the data is irreplaceable.

**The gap remains true and remains documented**: the archive stores price/qty as `Float64`, Kraken's CRC is computed over raw wire strings whose trailing zeros are load-bearing, and so a re-derived CRC cannot be compared to the stored `checksum`. That is accepted as a known limit of the archive, not a defect awaiting repair. If a future continuity-replay run ever does surface a discrepancy it cannot localise, the right move is a **new** topic carrying that observation — not a revival of this one, whose premise would then have changed.

*(Kept for the record: the build path, had it been pursued, was `price_str`/`qty_str` in `BOOK_SCHEMA` with the raw strings threaded through `_handle_book_message`, and `cli/archive/replay.py` extended to re-derive and compare when the columns are present. Never a standalone live restart.)*

## Suggested next steps

**None — superseded by the Resolution above.** Both steps below are kept as the record of the path NOT taken, so a future reader can see what the drop cost rather than re-deriving it:

- ~~Decide whether byte-exact CRC re-attestation is worth a capture-schema change.~~ Decided 2026-08-23: no.
- ~~If pursued: add `price_str`/`qty_str` to `BOOK_SCHEMA`, thread the raw WS strings through `_handle_book_message` (they arrive as `Decimal` via `parse_float=Decimal`; keep the original string), and extend `cli/archive/replay.py` to re-derive and compare the CRC when the columns are present (older float-only segments keep the structural-only check). Ship on the next gated capture re-pin, never a standalone live restart.~~ This remains the correct build path if the decision is ever revisited under a changed premise — via a new topic, not a revival of this one.
