---
status: partial
ripe_when: a venue-side WS restart (close 1012 / handshake 503) is observed after 2026-07-14 — verify it was ridden out in-process, then close
---

# Capture crashes when a WS reconnect attempt is rejected (Kraken 503)

## Context — what

On **2026-07-13 07:04:47 UTC** Kraken restarted its WebSocket service and closed our connection with
code **1012 (service restart)**. `WSClient.stream()` caught the `ConnectionClosed`, logged
`reconnecting in 1.0s (attempt 1)`, and backed off — correctly. One second later it re-connected, and
Kraken's endpoint — still coming back up — answered the handshake with **HTTP 503**:

```
InvalidStatus: server rejected WebSocket connection: HTTP 503
  /app/cli/capture/command.py:238 in capture   ->  asyncio.run(_run(...))
  /app/cli/capture/command.py:201 in _run      ->  await task
```

`stream()` (`cli/capture/ws_client.py`) guards its `try` block with **`except ConnectionClosed` only**,
but the connection-*establishment* call `self._connect(self._uri)` sits inside that same `try`. A
handshake rejection raises `websockets.exceptions.InvalidStatus`, which is **not** a `ConnectionClosed`
— so it escaped the handler, propagated through `_consume` (no try/except) and `_run` (catches only
`asyncio.CancelledError`), and **killed the process** with a traceback. The `while True` backoff/retry
loop built for exactly this situation never got past attempt 1.

Docker's restart policy restarted the container at 07:04:51.8; capture resumed at 07:04:52.6.
**Total gap ≈ 5.5 s** (plus resubscribe/snapshot settling).

## Why this matters

**The daemon does not survive the venue's own maintenance.** A WS service restart is a *routine*
Kraken event, not an exotic one, and a 503 during the endpoint's comeback is the single most likely
thing a reconnect will hit. The retry logic designed to ride this out is effectively dead on the path
that actually fires.

Capture only stayed up because **docker's `restart: unless-stopped` caught the crash** — a layer that
knows nothing about WebSockets and just happened to be there. The recovery is *incidental*, not
designed. Consequences:

- **A longer Kraken outage becomes a crash-loop**, not a backoff. Each crash restarts the process,
  drops every in-memory book, and re-subscribes all 10 pairs from scratch — instead of a cheap,
  bounded, in-process retry. Docker's restart backoff, not `compute_backoff`, ends up governing our
  reconnection behaviour against the venue.
- The blast radius is the **unbackfillable** stream: if the restart policy were ever absent or
  exhausted (a different supervisor, a bare `docker run`, a crash-loop backoff ceiling), a routine
  venue restart would stop L2 capture until a human noticed.

Severity is bounded — the crash is **loud** (traceback, non-zero exit) and self-healed in ~5.5 s, so
this is *not* a silent-death bug like [[T0032]]. It is a "the safety net we designed never deploys,
and an unrelated safety net catches us" bug.

## Findings so far

- **Root cause confirmed from the production system journal** (not merely inferred): the traceback
  above is the real one, ending in `InvalidStatus: server rejected WebSocket connection: HTTP 503`.
- Independently reproduced by a review subagent three ways (raw script, direct `_run()`, and the full
  `zcrypto capture` Typer entrypoint with a monkeypatched failing connect): every path exits non-zero
  with a traceback, matching production exactly.
- Verified by code reading: `stream()`'s `try` wraps `async with self._connect(self._uri) as ws:`
  (`ws_client.py:131`); the sole handler is `except ConnectionClosed` (`:137`); `finally: self._ws =
  None` (`:139`) cleans state but swallows nothing. No caller catches the escape — `_consume`
  (`command.py:128–148`) has no try/except around `async for msg in client.stream():`, and `_run`'s
  only handler (`:201–209`) catches `asyncio.CancelledError` alone.
- The `while True` loop, the `finally`, and the `compute_backoff`/`attempt` machinery are all correct.
  **This is a missing exception class, not a broken design.**
- Observed once in 5 days. Unrelated to [[T0008]] (the book-depth bug), which causes *checksum*
  desyncs and never exits.
- **Caveat on an earlier claim in this repo's own history:** an initial pass recorded this incident as
  a *silent* exit-code-0 death. That was a measurement error — `docker inspect .State.ExitCode` on a
  **running** container always reads `0` and says nothing about the previous run. The crash is loud.

## Done so far

The code fix landed on branch `fix/t0036-segment-writer-restart-clobber` in the commit
`fix(capture): survive a rejected WS reconnect attempt (T0035)` — the same commit that carries this
status flip:

- `stream()` now catches connection-*establishment* failures alongside `ConnectionClosed`:
  `websockets.exceptions.WebSocketException` (the superclass covering the observed `InvalidStatus`),
  plus `OSError` (`ConnectionRefusedError`, DNS/network errors) and `TimeoutError` — each backs off
  and retries exactly like a drop of an established connection. `asyncio.CancelledError` still
  propagates (the designed stop signal), pinned by a test.
- Regression tests (`tests/test_capture_ws_client.py`) drive a `connect_fn` raising the **real**
  `InvalidStatus` (HTTP 503, the production exception) and a `ConnectionRefusedError`: `stream()`
  keeps yielding afterwards and `compute_backoff` is applied across the failed attempts. All three
  new behaviour tests failed on the pre-fix code with the production traceback.
- The prolonged-outage cap/alert: `stream()` now logs an **ERROR** every 10 consecutive failed
  reconnect attempts (`_RECONNECT_ERROR_EVERY`), so a genuinely long venue outage is loud in the
  logs instead of an endless stream of INFO lines. No new config.
- **Dropped** (was a "consider"): making the dead-man's-switch notice a fast crash-restart — this fix
  removes the crash-restart this incident produced (the retry now stays in-process), and generic
  process-restart observability belongs to the T0020 Grafana/Alloy stack if it ever recurs.

- **Deployed 2026-07-14 (verified 2026-07-19):** the fix rode the T0036 deploy — the digest running on
  both capture hosts (`sha256:63708539…`, image built 2026-07-14 03:51 UTC, ten minutes after the fix
  commit `a57b2c6`) contains the fixed `ws_client.py` (`WebSocketException` handler present, checked
  inside the image itself). The deploy sub-item is done; only the live verification remains.

## Suggested next steps

- Verify on the next venue-side WS restart (Kraken close 1012): the container journal must show
  `WS connect attempt failed, reconnecting: ...` followed by `reconnecting in ...s (attempt N)` and a
  resumed stream — **no** container restart, no `InvalidStatus` traceback, no non-zero exit. Then
  close this topic.
