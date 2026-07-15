---
status: open
ripe_when: a capture-schema change that stores raw wire-format price/qty strings is on the table (itself gated on a capture image re-pin — canary + clean-run embargo, see T0032), or an OPS-3 continuity-replay run surfaces a discrepancy the structural check cannot localize without the CRC
---

# Byte-exact CRC re-derivation from the archive needs raw-string price/qty

## Context — what

Kraken's L2 book feed carries a CRC32 checksum per message; the capture daemon validates it live (`cli/capture/book.py::OrderBook.checksum`/`validate`) and stores the message's checksum in the archive's `BOOK_SCHEMA` `checksum` column. A natural archive-integrity oracle is to **replay** the stored book segments back through `OrderBook` and re-derive the CRC, confirming byte-for-byte that the archived rows still reconstruct the exact book the exchange attested. Discovered while planning OPS-3 (spec 00051): this is **not achievable from the archive as stored**. `BOOK_SCHEMA` persists `price`/`qty` as **Float64** (`cli/capture/command.py:154-155` writes `float(level["price"])`), but Kraken's CRC is computed over the **raw wire-format decimal strings** where trailing zeros are load-bearing (`_format_level`, `book.py:26-31`: `"0.30000000"` → `"30000000"`, whereas `float 0.3` → `Decimal("0.3")` → `"3"`). Reconstructing `Decimal`s from the stored floats drops those trailing zeros, so a recomputed CRC will mismatch the stored `checksum` for the many levels ending in zeros — a guaranteed false alarm, not a real corruption signal.

## Why this matters

It bounds what archive self-attestation can prove. OPS-3's continuity-replay verifier (built in spec 00051) proves the archive **reconstructs a coherent book** — snapshot-anchored hours, updates applying in order, no structural desync — and treats the stored `checksum` as capture-time ground truth (it *was* CRC-validated live). That catches silent archive/reconciler corruption of the row *structure*, which is the main risk. What it cannot do is independently re-attest the exchange CRC from the archive, so a corruption that altered a price/qty value while keeping the row structure valid *and* left the stored checksum column untouched would pass. Combined with the known limit that Kraken's CRC covers only the **top 10** levels ([[T0033]]), full-depth byte-exact archive attestation is simply not available today. This is a completeness gap in the durability story, not an active bug.

## Findings so far

- The blocker is the Float64 storage of `price`/`qty` in `BOOK_SCHEMA` (`cli/capture/segment_writer.py:16-24`; written as floats at `cli/capture/command.py:146-158`). The CRC needs the exact wire strings.
- OPS-3 (spec 00051, `cli/archive/replay.py`) delivers the achievable-now check: structural continuity + desync replay, stored-checksum-as-ground-truth. It explicitly does **not** compare a re-derived CRC.
- A fix would add raw-string `price_str`/`qty_str` columns (or replace the floats) to the captured book schema — a **capture-daemon change on the unbackfillable live stream**, so it is gated behind a capture image re-pin (canary rule + primary clean-run embargo, [[T0032]] / `.claude/rules/capture-deploys.md`) and only ever attests data captured *after* the change (pre-change history stays float-only forever).

## Suggested next steps

- Decide whether byte-exact CRC re-attestation is worth a capture-schema change. Weigh: it only strengthens attestation for post-change, top-10-depth data, at the cost of a schema migration on the live stream and larger segments (two string columns). The OPS-3 structural check may be sufficient — revisit if a continuity-replay run ever surfaces a discrepancy it cannot localize.
- If pursued: add `price_str`/`qty_str` to `BOOK_SCHEMA`, thread the raw WS strings through `_handle_book_message` (they arrive as `Decimal` via `parse_float=Decimal`; keep the original string), and extend `cli/archive/replay.py` to re-derive and compare the CRC when the columns are present (older float-only segments keep the structural-only check). Ship on the next gated capture re-pin, never a standalone live restart.
