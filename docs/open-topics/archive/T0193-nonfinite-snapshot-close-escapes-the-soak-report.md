---
status: resolved
---

# A non-finite snapshot close escapes the soak report as a traceback

## Context — what

`realized_internals` (`cli/engine/soak.py`) wraps its validate/assemble/build prologue in `except (EngineError, PortfolioError)` and, on either, returns `available=False` with a reason — its docstring's contract: *"a validate/assemble/build failing on `EngineError`/`PortfolioError` returns `available=False` and leaves the void decision to the caller."*

A non-finite close in a journaled snapshot does not raise either. `build_crossfreq_system_fast` raises `ValueError: cannot convert NaN to integer ratio`, out of `float.as_integer_ratio()` inside the rolling statistics. `EngineError` and `PortfolioError` are both direct `Exception` subclasses and `ValueError` is neither, so the exception escapes `realized_internals`; the call sits in the `else:` branch of `soak_report`'s `build_null` try and is not wrapped again; and `cli/engine/command.py`'s soak command catches only `EngineError`. The operator gets a traceback.

## Why this matters

The contract in the docstring is false for this input class, and a reader of that docstring will believe a corrupt snapshot degrades the run rather than ending it.

**The repair looked like it might be the wrong direction, which is why this was a topic rather than a fix.** Catching `ValueError` and returning `available=False` makes the failure *quieter*: a traceback is at least visible and unmissable, where `available=False` degrades a go-live run into a report that reads almost normally. The Resolution below records who answered that fork, and it was not this topic.

The neighbouring question is where the refusal should live at all. `_validate_grid` (`cli/portfolio/crossfreq_system.py`) — the fast builder's own front door — checks the prices dict's shape, its key set against `config.assets`, the ts stamps' type and strict ordering, and each series' length. It never tests a close VALUE. The verified path's refusal is a written guard carrying the message `prices must be None or finite positive numbers` — `AlphaError` or `BenchmarkError`, by which grid holds the bad close; the fast path's is an accident of exact rational arithmetic, and the builder's own docstring already warns that the two paths' error behaviour is not gated.

## Findings so far

- Measured on `synthetic_grids(220)` with one NaN close injected at six placements — first, middle and last bar of both the daily and the 4h grid: all six raise `ValueError: cannot convert NaN to integer ratio` from `build_crossfreq_system_fast`, and the verified builder refuses the same input with the written message `prices must be None or finite positive numbers, got nan` — `AlphaError` at the three 4h placements, `BenchmarkError` at the three daily ones, neither of which is a `PortfolioError`.
- The exception classes: `class PortfolioError(Exception)` (`cli/portfolio/errors.py:1`), `class EngineError(Exception)` (`cli/engine/errors.py:1`). Neither is in `ValueError`'s ancestry.
- It is `T0188`'s subject — non-finite handling in `realized_internals` — arriving from the other side: `T0188` was a silent pass over an unmeasurable comparison and is closed, this is a loud escape past a contract that promised degradation and is not. Its spec `00113` excluded this deliberately and names it here, because closing the silent-pass defect does not answer this fork.

## Resolution

**The fork was already answered, by spec `00059` D7, and the owner confirmed it stands.** D7 covers this case by
name — a rebuild that cannot be performed because snapshots are "absent/corrupt" — and rules that the two
internals metrics read `n/a` with a stated reason while the five weight metrics still gate, because a missing
rebuild degrades the fingerprint and does not invalidate them. That premise was checked against the tree rather
than taken: the five come from the realized and null series, built from the store and the records' targets, not
from this rebuild, so a corrupt journaled snapshot does not reach them.

So the defect was never the degradation. It was that this input class ESCAPED the degrade net instead of entering
it, which made `realized_internals`' own docstring false.

**The fix is the second suggested step, and it made the first moot.** `_validate_grid` — the door BOTH builders
enter — now refuses a close that is not `None` and not a finite positive number, with the message the verified
path's own guard already used. A non-finite close therefore raises `PortfolioError`, the net catches it, and the
run degrades with a reason that names grid, asset, bar index and value. The fast path used to refuse this input
by an accident of exact rational arithmetic and the verified path by a written guard; they agree by design now.

The guard takes the construction the topic asked for: the six placements it measured — first, middle and last bar
of both grids — against both builders, the rest of the class beside them (`inf`, `-inf`, zero, negative, a bool,
a string), and a `None` gap as the control that keeps the refusal honest. Both arms are probed by
`infra/scripts/mutate-probe.sh`.

The soak-level case is built on the ten-leg fixture, because a single-pair record trips the asset-set check
before any value is read, and the NaN is hashed INTO the record rather than injected after it: injecting after
trips the assembler's content-hash check first, which is a different refusal with its own handling.

**Not done, and not this topic's:** `journal.py`'s snapshot metadata still carries no finiteness claim about the
data behind a `content_hash`, so a snapshot whose NaN was hashed in at write time is refused at the READ rather
than at the write. Refusing at the write is a capture-path change with its own blast radius.
