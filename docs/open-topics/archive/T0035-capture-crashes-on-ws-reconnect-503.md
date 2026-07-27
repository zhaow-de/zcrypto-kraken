---
status: resolved
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

- **Live evidence pulled 2026-07-23 — half the verification is now done, and the half that matters is not.**
  Measured from Grafana Cloud (Prom + Loki), read-only:

  - `zcrypto-red` ran **17.6 h with 9 reconnects and no process restart** (`process_start_time_seconds`
    = 2026-07-22 21:45:07 UTC, the rollout Step-5/6 recreate, unmoved across all nine events;
    `zcrypto_capture_reconnects_total{host=zcrypto-red}` = 9, no reset). The primary shows 0 reconnects
    since its 13:08:52 T0092 recreate.
  - **Every one of the nine succeeded on the first try** — all nine log pairs read
    `WS connection closed, reconnecting: no close frame received or sent` + `reconnecting in 1.0s (attempt 1)`.
  - **Zero `attempt [2-9]` lines exist on either host across the full retained Loki window (~3 days).**

  So the daemon demonstrably rides out connection **drops** in-process — the crash-restart shape does not
  occur. But every observed reconnect *succeeded*, so the handler this topic added
  (`WebSocketException`/`OSError`/`TimeoutError` on a **rejected** attempt) has **never been exercised in
  production**. The nine events are abnormal closures ("no close frame"), not the close-1012 venue restart
  the original trigger named. Re-deferred rather than closed: passing an easier test is not passing this one.

## Resolution

**Resolved 2026-07-27 by drill.** The residual was never a code question — the fix was landed, deployed and regression-tested; what was missing was that the handler for a **rejected** connection attempt had never executed in production. Across the full Loki retention there were zero `attempt [2-9]` lines: every observed reconnect succeeded first try, so passing that test was never passing this one.

A throwaway capture container on the ops node — same pinned digest, real Kraken, isolated data dir, no Loki creds, no dead-man URL — exercised it end to end.

**Both arms of the `except (WebSocketException, OSError, TimeoutError)` branch fired, one of them unprompted:**

- **`WebSocketException`** — Kraken rejected the sandbox's *very first* connect with `server rejected WebSocket connection: HTTP 503`. Nothing induced it. That is this topic's originating fault, arriving on its own within seconds, which says the 503 is more common than production logs suggest: production has simply always succeeded on the retry.
- **`OSError`** — a `docker network disconnect` produced `[Errno -3] Temporary failure in name resolution` for a sustained blackout.

**What the sustained fault proved**, none of it previously observed:

| behaviour | observed |
| --- | --- |
| backoff schedule | `1, 2, 4, 8, 16, 32, 60, 60, 60, 60` — exponential, capped at `_BACKOFF_MAX_SECONDS` |
| the every-10 ERROR | `WS reconnect still failing after 10 consecutive attempts`, at attempt 10 |
| **process survival** | `restarts=0` across ~6 min and 15 attempts — the whole claim |
| recovery | on reconnect: resubscribed and resumed writing without intervention |
| **data consistency** | book **and** trades `10.parquet` — the hour spanning the fault — both hash-verify against their `.sha256` manifests |

**Why a drill is a legitimate close and not a shortcut.** Waiting on a production 503 meant waiting on Kraken, and the topic had already been half-verified twice on evidence that did not test the handler. The drill reproduces the exact exception types the production code catches, in the production image, against the real venue. What it cannot show is *incidence* — how often Kraken rejects a reconnect in normal operation — but incidence was never this topic's question.

**Trigger retained for the record:** any `attempt [2-9]` line, the `_RECONNECT_ERROR_EVERY` ERROR, or `process_start_time_seconds{job="capture_app"}` jumping while `zcrypto_capture_reconnects_total` resets. Those now indicate a live event worth reading, not an unvalidated code path.
