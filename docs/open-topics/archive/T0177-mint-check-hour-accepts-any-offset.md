---
status: resolved
---

# `_check_hour` accepts an exact hour at any UTC offset, and the path is formatted from it

## Context — what

`cli/archive/mint.py::_check_hour` refuses a naive datetime and a non-zero minute, second or microsecond, but not a non-zero UTC offset: `hour.replace(minute=0, second=0, microsecond=0)` preserves `tzinfo`, so the equality it tests holds for any aware datetime already on an hour boundary in its own zone. `datetime(2026, 7, 27, 9, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))` passes.

The published path is formatted straight from that value, so such an hour would be minted as `.../2026/07/27/09.parquet` while the hour it actually spans is 03:30–04:30 UTC.

## Why this matters

The file name is the only statement of which hour a final covers, and a final is a committed, complete hour by construction — the archive's central invariant. A wrong name is not a wrong label on good data: it makes an hour's worth of book state answer for a window it never covered, and the canonical tree is immutable, so the repair is a hand correction against a claim nothing else contradicts.

Nothing is wrong today, which is why this is a topic and not a fix in flight.

## Findings so far

- Found 2026-09-07 by a blind reader on the docstring pass's `cli/archive` batch, as a false universal in the docstring ("refusing anything that is not an exact UTC hour"). The prose was corrected there to say what the check does; the code was left alone because a prose-only branch cannot carry an assert and its test.
- Re-derived independently by two sessions: the offset value above is accepted, and the resulting path names hour 09 for a 03:30 UTC hour.
- **All three live call sites are safe**: every one derives `hour` from a UTC-anchored scan of the capture tree, so no caller can reach the gap today. The exposure is a future caller, or a refactor that passes an hour through from a configuration or an operator argument.

## Resolution

Fixed in place on the owner's ruling rather than merged as a registration, and the fix is two guards because one does not cover the family.

- `_check_hour` refuses an hour whose `utcoffset()` is not zero — `fix(archive): an exact hour at a non-zero UTC offset could mint under the wrong hour's file name`. Constructed as three events rather than a unit test of the check: the future caller this topic imagined, refused with its offset named; the same through `mint_hour` at `-08:00`, where 09:00 is 17:00 UTC, asserting **on disk** that no final, sidecar, partial or file of any kind was published; and the true positive, a UTC hour still minting to `09.parquet` and still returning the exclusive end.
- `settled_hours` refuses a `now` that is not at UTC — `fix(archive): settled_hours refuses a now that is not at UTC, where the offset would spread`. The enumeration behind it: `settled_hours` propagates whatever offset `now` carries (measured — `now=<+05:30>` yields hours all at `+05:30`), and its one production consumer is the reconciler's window, which feeds eleven write sites: two `mint_hour` calls the first guard closes, and nine `_ledger` appends that never pass through it — five verdicts written before any mint, two `would_mint` on the detect-only path that reaches `mint_hour` by construction never, and two `minted` after it. The guard therefore goes at the source, and with both boundaries closed no hour bearing a non-UTC offset can reach a file name or a ledger key **on this path**.

Not at `reconcile`'s entry, which was the first shape proposed and is worthless: `now` is born there (`command.py`'s `_utc_now()`), so asserting UTC on it would assert that `datetime.now(UTC)` is UTC.

Both guards are **latent by construction**, measured rather than assumed: `reconcile` sources its `now` internally, and `cli/trades/backfill.py` takes its hours from `canonical_segments`, which parses them out of the path with `tzinfo=UTC` (`cli/archive/reader.py:31`), unioned with hours floored from the REST frame's UTC-typed `ts`. No production path reaches either arm today — they are boundary guards against a future caller, not repairs of a live hazard. The arms that carry a refusal were proven by deleting them under `infra/scripts/mutate-probe.sh`: both offset arms KILLED on `DID NOT RAISE CaptureError`, and `settled_hours`' naive arm — message-only, since the offset arm refuses a naive `now` unaided — KILLED on the old `at UTC offset :00:00` rendering. `_check_hour`'s `hour.tzinfo is None or` is message-only in the same way and is NOT pinned: deleting it SURVIVES, because the offset arm catches a naive hour too and its message is already true of one. Left as it is, and named here rather than claimed as proven.

Scope, stated because the sentence above is easy to over-read: this closes the ARCHIVE MINTING path. Five other sites format an hour's wall clock into a canonical file name or a merge target with no offset guard of their own — `cli/panel/materialize.py:164` and `cli/capture/segment_writer.py` at `:453`, `:558`, `:715`, `:751` and `:796` — and they are UTC-safe because of where their hours come from, which is exactly what `_check_hour` relied on before this branch. Named so nobody reads the guarantee as tree-wide — but they need no guard of their own, for two structural reasons, and neither is a promise about a future change.

The panel site and the archive readers build their hours from path integers with `tzinfo=UTC` written into the constructor (`cli/panel/materialize.py:243`, `cli/archive/reader.py:31`, `cli/capture/segment_writer.py:261`), so no offset can enter and an offset guard there would assert a constant. The five capture sites take their hour from `_hour_start` or from that same path parser, and `_hour_start`'s only upstreams are `_utcnow()` — `datetime.now(UTC)` — and an event's own `ts`. So the single place an offset could enter the capture path is the venue timestamp parser that produces that `ts`, and a guard belongs there rather than at five formatting sites downstream of it.

The sibling check `_check_gaps` does not share the defect and structurally cannot: its comparisons are between aware datetimes, which Python compares by absolute instant across zones.

This topic carried a `ripe_when` that nobody would ever have evaluated — "the next change to the minting path, or a second caller" fires only if a person happens to look. It is resolved on constructed evidence instead, and carries no trigger.
