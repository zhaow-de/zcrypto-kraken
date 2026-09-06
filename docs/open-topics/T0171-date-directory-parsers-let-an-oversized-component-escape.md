---
status: open
---

# Date-directory parsers let an oversized component escape

## Context — what

Seven places walk a `<YYYY>/<MM>/<DD>` tree and turn path components into a date. Three carry the same promise in a trailing comment, and it is false of all three:

> a hand-made directory that is not a date — not ours, ignore it

`int(str)` cannot raise `OverflowError` — Python integers are arbitrary precision — so every `OverflowError` here comes from `datetime`'s conversion of the year to a C int. The boundary was bisected at exactly `2**31` while fixing the capture writer's copy of this parser.

| site | guard | the comment's promise |
|---|---|---|
| `cli/archive/reader.py:32` | `except ValueError:` | present, em dash |
| `cli/archive/settle.py:84` | `except ValueError:` | present, em dash |
| `cli/panel/materialize.py:244` | `except ValueError:` | present, ASCII double hyphen |
| `cli/archive/replay.py:77` | `except ValueError, IndexError:` | absent |
| `cli/archive/pull.py:32` | `except ValueError, IndexError:` | absent |
| `cli/costs/calibrate.py:63` | none | absent |
| `cli/tick/materialize.py:166` | none | absent |

Coordinates verified line by line against develop `5fe5e78c`. **The comment is not one string**: two sites use an em dash and `panel/materialize.py` uses an ASCII double hyphen, so a grep for either form finds a subset and reads as complete.

## Why this matters

None of the seven is under `cli/capture/`, so nothing unbackfillable is at risk — that is what makes this ordinary work rather than an incident. What it costs is a command that dies where it promises to skip: a hand-made or restored directory whose year component exceeds a C int raises out of the walk instead of being ignored, and three of the seven say in writing that it will be ignored.

## Findings so far

The same defect was fixed on the capture path by the commit `fix(capture): a stray year directory raises past the except that promised to skip it` (cited by subject; it is unpushed at the time of writing). Its review swept `_hour_of` over 200,360 malformed components — empty, signs, C-int and C-long edges, NAME\_MAX digit runs, PEP 515 underscores, unicode digit scripts, 5,000-digit strings past the int-str conversion limit, embedded NUL — and reported `ESCAPING TYPES: NONE`, so `ValueError` and `OverflowError` are the whole set `datetime()` raises on those axes. The fix there was to widen the `except` and leave the docstring standing, because the code then makes the sentence true.

## Suggested next steps

- One `fix(cli)` PR. Widen the five guarded sites to also catch `OverflowError`; the three comments then state what the code does.
- **A decision at pick time, not a task**: `cli/costs/calibrate.py` and `cli/tick/materialize.py` parse with no guard at all. Whether a foreign directory in the tree each owns should be skipped like the others or refused loudly is a judgement about those two commands, and it should be made deliberately rather than by copying the pattern.
- One constructed test per site, built the way the capture one was: an oversized-year directory planted beside a well-formed one, red before the widening and green after, with the well-formed final still parsing as the true positive.

<!-- INDEX BULLET, for docs/open-topics/README.md, appended to ## Research and development -> ### Open:
- [T0171 — date-directory parsers let an oversized component escape](T0171-date-directory-parsers-let-an-oversized-component-escape.md) — seven walkers turn path components into a date and only the capture one catches `OverflowError`; three promise in a comment to skip what they raise on.
-->
