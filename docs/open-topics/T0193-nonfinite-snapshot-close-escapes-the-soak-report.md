---
status: open
---

# A non-finite snapshot close escapes the soak report as a traceback

## Context — what

`realized_internals` (`cli/engine/soak.py`) wraps its validate/assemble/build prologue in `except (EngineError, PortfolioError)` and, on either, returns `available=False` with a reason — its docstring's contract: *"a validate/assemble/build failing on `EngineError`/`PortfolioError` returns `available=False` and leaves the void decision to the caller."*

A non-finite close in a journaled snapshot does not raise either. `build_crossfreq_system_fast` raises `ValueError: cannot convert NaN to integer ratio`, out of `float.as_integer_ratio()` inside the rolling statistics. `EngineError` and `PortfolioError` are both direct `Exception` subclasses and `ValueError` is neither, so the exception escapes `realized_internals`; the call sits in the `else:` branch of `soak_report`'s `build_null` try and is not wrapped again; and `cli/engine/command.py`'s soak command catches only `EngineError`. The operator gets a traceback.

## Why this matters

The contract in the docstring is false for this input class, and a reader of that docstring will believe a corrupt snapshot degrades the run rather than ending it.

**But the obvious repair may be the wrong direction, and that is why this is a topic rather than a fix.** Catching `ValueError` and returning `available=False` makes the failure *quieter*: a traceback is at least visible and unmissable, where `available=False` degrades a go-live run into a report that reads almost normally. Which of the two an operator is better served by is a real fork, and it is not answered here.

The neighbouring question is where the refusal should live at all. `_validate_grid` (`cli/portfolio/crossfreq_system.py`) — the fast builder's own front door — checks the prices dict's shape, its key set against `config.assets`, the ts stamps' type and strict ordering, and each series' length. It never tests a close VALUE. The verified path's refusal is a written guard (`AlphaError: prices must be None or finite positive numbers`); the fast path's is an accident of exact rational arithmetic, and the builder's own docstring already warns that the two paths' error behaviour is not gated.

## Findings so far

- Measured on `synthetic_grids(220)` with one NaN close injected at six placements — first, middle and last bar of both the daily and the 4h grid: all six raise `ValueError: cannot convert NaN to integer ratio` from `build_crossfreq_system_fast`, and the verified builder raises `AlphaError` on the same input.
- The exception classes: `class PortfolioError(Exception)` (`cli/portfolio/errors.py:1`), `class EngineError(Exception)` (`cli/engine/errors.py:1`). Neither is in `ValueError`'s ancestry.
- It is `T0188`'s subject — non-finite handling in `realized_internals` — arriving from the other side: `T0188` is a silent pass over an unmeasurable comparison, this is a loud escape past a contract that promised degradation. `T0188`'s spec `00113` excludes this deliberately and names it here, because closing the silent-pass defect does not answer this fork.

## Suggested next steps

- **Answer the fork first**: is a traceback or a degraded `available=False` the better operator outcome for a corrupt snapshot? Whichever way it goes, the reason belongs in the code, because the next reader will otherwise "fix" it back.
- **Decide whether the fast path should carry a written finiteness guard.** `_validate_grid` refusing a non-finite close would make both builder paths refuse by design instead of one by accident, and would give the refusal a `PortfolioError` the existing handler already catches — which may make the fork above moot.
- Whichever lands, it is a guard and takes the construction: the NaN injection above as the defect fixture, and a healthy grid beside it that must still build.
