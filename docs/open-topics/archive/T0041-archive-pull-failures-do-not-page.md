---
status: resolved
---

# archive-pull failures do not page

## Context — what

`NAS · archive-pull ERROR logs` (`infra/grafana/alerts.yaml`) selects on the `level` label that Alloy attaches at ingest by matching our Python log format. Anything that reports a failure **without going through `logging`** carries no level, so Alloy never labels it and the rule cannot see it.

**Correction to this topic's first draft.** It claimed a failed rsync does not page. That was wrong: `cli/archive/command.py:100` already does `logger.error("archive pull: rsync failed …")`, and a hash mismatch logs at line 119 — both carry a level and both fire the alert. The error was mine, and it is recorded rather than quietly edited away, because the topic was used to justify work.

The genuine gaps, as finally established:

1. **A regression introduced by the label-based rule itself.** `_abort()` (`cli/engine/command.py:51`) reported errors with `typer.echo("ERROR: …", err=True)` — no timestamp, no level. The **previous** rule grepped the raw line for `"ERROR"` and therefore *did* catch these; switching to `level=~"ERROR|CRITICAL"` silently stopped catching them. Sixteen call sites route through it, including every `engine gate-export` failure. Fixing one blind spot had opened another.
2. **Uncaught exceptions.** `cli/__main__.py` handed control to `app()` directly, so Typer's own `sys.excepthook` rendered a Rich traceback straight to stderr, never through `logging`. A crash of the pull loop — the worst thing that can happen to the unbackfillable archive short of the disk filling — was invisible. Pre-existing; the old text grep missed it too (a traceback says `ValueError`, not `ERROR`).
3. **`pull-entrypoint.sh`'s failure paths** used a bare `echo … >&2`. Secondary, since the CLI usually logged an ERROR first — but they are the *only* record when the CLI is killed before it can log for itself (OOM, signal).
4. **No dead-man.** Every rule required archive-pull to still be alive and talking. If the container died, the loop exited, or the NAS went down, everything went quiet and nothing fired.

## Why this matters

L2 capture is unbackfillable. The NAS mirror is the durable copy, and `archive-pull` is what keeps it current. A silently-failing pull is exactly the failure this alert exists to catch, and it is the one shape of failure it cannot see. A detector that is green while the thing it watches is broken is worse than no detector, because it is trusted.

## Findings so far

- Confirmed 2026-07-14: `typer.Typer(...)` at `cli/__main__.py:12` sets no `pretty_exceptions_enable`, so Typer's Rich excepthook is active and bypasses `logging`.
- Confirmed: the seven rules in `infra/grafana/alerts.yaml` are Gate streak-reset / mismatch / journal-pull-lag / exporter-stale, NAS free-space / load, and NAS archive-pull ERROR logs. None is a freshness check on the archive mirror.
- The ingest stage that sets `level` is in `infra/nas/config.alloy` (`stage.match` on `{container="archive-pull"}`); a non-matching line is passed through unchanged (verified: Loki's regex stage is a no-op on non-match and `stage.output` leaves the entry alone when its source key is unset), so these lines DO reach Loki — they simply arrive without a `level`, and the alert selects on `level`.

## Done so far

Resolved on 2026-07-14 (folded into the observability commit on `fix/engine-host-split`). The governing principle: **every error path goes through `logging`, so the level label is always present** — plus a dead-man for the case where there is nothing to label.

- `_abort()` now calls `logger.error(message)` instead of `typer.echo` (closes the regression; all 16 call sites fixed by the one edit). Console output for an interactive user changes from `ERROR: <msg>` to the standard log line — approved by the owner.
- `cli/__main__.py` gained `run()`, the new console-script entry point (`pyproject.toml`: `zcrypto = "cli.__main__:run"`), which wraps `app()` and `logger.exception()`s an unhandled exception before exiting 1. It catches `Exception`, not `BaseException`, so click's own `SystemExit` (usage errors, `typer.Exit`) passes through untouched.
- `pull-entrypoint.sh` gained a `log()` helper emitting the same line shape Python's logging emits, and its three failure paths now log at ERROR. **Note the portability trap found while testing:** GNU date's `%3N` width modifier is a GNU extension that uutils' date (Rust coreutils, shipped by some distros) silently ignores — it emits all 9 nanosecond digits, producing a line Alloy would *not* label. The helper takes the full `%N` and truncates with POSIX parameter expansion instead. This would not have shown up on the GNU-coreutils container, only on a rebuilt image.
- New alert `zcrypto-nas-archive-pull-stalled` — the dead-man: fires when no `pull complete` line has been seen for 3h (the pull runs hourly, so the loop gets three chances). `noDataState: Alerting`, because NoData here means the log pipeline itself is dead, which *is* the alarm.
- `ARCHIVE_PULL_INTERVAL` is now declared with a default in `infra/nas/compose.yaml` rather than resolving to the empty string and relying on the shell fallback.
- Regression tests in `tests/test_error_paths_are_logged.py` pin all of it, including a copy of Alloy's ingest regex — so if the log format and the ingest stage ever drift apart, a test fails rather than the alerting going quiet.

## Deployment note

The `_abort` and `run()` fixes live in the **capture image**, which `archive-pull` runs, so they reach the NAS only when a new image is built and the NAS re-pins to it (the normal image flow; cf. the archived T0031). The alert rule and the `pull-entrypoint.sh` / compose changes are independent of the image and deploy directly.
