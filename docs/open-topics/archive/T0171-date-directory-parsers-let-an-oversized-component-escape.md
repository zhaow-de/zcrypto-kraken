---
status: resolved
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

The same defect was fixed on the capture path by the commit `fix(capture): a stray year directory raises past the except that promised to skip it`. Its review swept `_hour_of` over malformed components — empty, signs, C-int and C-long edges, NAME\_MAX digit runs, PEP 515 underscores, unicode digit scripts, strings past the int-str conversion limit, embedded NUL — and reported `ESCAPING TYPES: NONE`, so `ValueError` and `OverflowError` are the whole set `datetime()` raises on those axes. The fix there was to widen the `except` and leave the docstring standing, because the code then makes the sentence true.

## Resolution

All seven sites are guarded and each guard is constructed against both of its arms.

The five that had a guard were widened to name `OverflowError` beside what they already caught, one commit each: `fix(archive): the canonical reader's skip promise did not cover an oversized year`, `fix(archive): the settlement scan's skip promise did not cover an oversized year`, `fix(archive): an oversized year broke replay_segment's never-raises contract`, `fix(archive): an oversized year aborted the NAS verify walk mid-sweep`, and `fix(panel): the watermark's promise to ignore a hand-made directory raises past it`.

The two that had none were decided rather than patterned, and they were decided differently, on who writes the tree. `cli/costs/calibrate.py` reads the panel copy the NAS pulls, which `panel materialize`'s own refusals tell an operator to hand-delete from, so a foreign directory there is expected and is **skipped** — the guard wraps the `datetime()` construction alone, leaving the window comparison outside it. `cli/tick/materialize.py`'s output tree has one writer, `publish_day`, so a path that is not a date is corruption of canonical output: `_watermark` **refuses**, naming the path — `fix(tick): a foreign year directory crashes the watermark that nothing guarded`, with `fix(costs): a stray year directory raises out of the calibration's file walk` for the skip. That refusal is read outside the sweep's per-day `except`, so it aborts the run instead of being booked as one day's error while publishing continues against a corrupt tree.

Each site carries a test that plants both a non-numeric year and one past the C-int ceiling beside a well-formed final, because `int()` is arbitrary-precision: `int("nope")` raises ValueError before any date arithmetic, and only `datetime()`'s C-int year conversion raises OverflowError. Every guard was proven by narrowing it back to each arm alone under `infra/scripts/mutate-probe.sh`, control proven, and every mutation was killed by an uncaught throw at the guarded line rather than by a downstream assertion.
