---
status: open
ripe_when: "the next change to cli/archive/mint.py's minting path, or a second caller of mint_hour that does not derive its hour from a UTC-anchored scan: git grep -n 'mint_hour(' -- cli/ infra/ returns a call site outside cli/archive/command.py's scan loop"
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

## Suggested next steps

- Decide whether the UTC precondition becomes an assertion or stays an unstated caller obligation. If an assertion: `hour.utcoffset() == timedelta(0)` in `_check_hour`, with a test that constructs the `+05:30` hour above and sees the refusal fire, and a true positive that a UTC hour still mints. The change is on the minting path, so it takes the review that path's changes take.
- If instead it stays a caller obligation, say so in the docstring as an obligation rather than a refusal, and drop this topic with the reason recorded.
