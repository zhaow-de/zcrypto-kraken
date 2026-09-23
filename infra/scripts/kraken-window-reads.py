#!/usr/bin/env python3
"""The open-order reads for the attended window, read-only: it sends no order and no cancel.

  orders <TXID>...  Before the restart: does the read the engine itself issues see each named order?
        The verdict reads only the UNSCOPED shapes. open_only=True is startup reconciliation's and
        query_order's read (upstream `70d887545790`, execution/spot.rs:1356 and :1433); open_only=False
        is the engine's single-report read (spot.rs:1263-1265), which also pages the whole ClosedOrders
        history, so its round trip is timed on its own. SAFE needs exactly one row per TXID in each
        shape and each round trip inside one engine tick. The verdict never reads a row's instrument_id:
        each target row is printed with it, and a spelling other than BTC/EUR.KRAKEN on the BTC order
        is the operator's to catch. The scoped read (instrument_id given) is printed as a contrast and
        never counts: on this wheel it skips a two-way-spelled leg before resolving it (upstream #5067),
        so BTC/EUR reads 0 rows there while the unscoped shapes see it.
  absent <TXID>...  After the restart: SAFE when none of the TXIDs is still open at the venue.

Every row of the listing is read and cached first: a bare client's unscoped read raises on the first
open order it cannot place. `orders` takes one read on the bare client before that and prints it as a
reading.

Exit: 0 SAFE, 1 HAZARD, 2 nothing was read (usage, or no credentials), 3 the listing could not be read.

Run it FROM the workstation, never on the engine host: ssh forwards local stdin into the container, so
the source never lands on the host. Run it inside the engine's inter-cycle gap -- its reads share the
trade key with the running engine:
    IMAGE=$(ssh zcrypto sudo docker inspect --format '{{.Config.Image}}' zcrypto-engine)
    ssh zcrypto sudo docker run --rm -i --env-file /opt/zcrypto-engine/engine.env \
      --entrypoint python "$IMAGE" - orders <BTC-TXID> <SOL-TXID> < infra/scripts/kraken-window-reads.py
Credentials come from the environment and are never printed.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any

API_KEY_VAR = "KRAKEN_SPOT_API_KEY"
API_SECRET_VAR = "KRAKEN_SPOT_API_SECRET"
# The label the engine's reports carry (`cli/engine/node.py`'s `_ACCOUNT_ID`); the adapter only stamps it
# on each report, so it selects no rows.
ACCOUNT_ID = "KRAKEN-001"
SCOPED = ("BTC/EUR.KRAKEN", "SOL/EUR.KRAKEN")
# The engine's tick: a read slower than this does not finish inside the tick that issued it.
ONE_TICK_SECS = 5.0


class Refusal(RuntimeError):
    """Raised instead of building a client. Names variables, never values."""


def credentials() -> tuple[str, str]:
    key, secret = os.environ.get(API_KEY_VAR, ""), os.environ.get(API_SECRET_VAR, "")
    missing = [name for name, value in ((API_KEY_VAR, key), (API_SECRET_VAR, secret)) if not value]
    if missing:
        raise Refusal(f"{' and '.join(missing)} not set in the environment")
    return key, secret


def build_client(key: str, secret: str) -> Any:
    """`cli/engine/command.py`'s construction: two positional arguments, the venue's own endpoint."""
    from nautilus_trader.adapters.kraken import KrakenSpotHttpClient

    return KrakenSpotHttpClient(key, secret)


async def _timed(call):
    t0 = time.monotonic()
    try:
        return list(await call() or []), None, time.monotonic() - t0
    except Exception as exc:  # noqa: BLE001 -- every shape's failure is itself the reading
        return None, f"{type(exc).__name__}: {str(exc)[:240]}", time.monotonic() - t0


def _line(r) -> str:
    return (
        f"{r.venue_order_id} instrument_id={r.instrument_id} client_order_id={r.client_order_id!r} "
        f"status={r.order_status} filled_qty={r.filled_qty}"
    )


async def _cache_listing(client) -> int | None:
    rows, error, secs = await _timed(lambda: client.request_instruments())
    if error:
        print(f"-- listing FAILED ({secs:.2f}s): {error}")
        return None
    for row in rows:
        client.cache_instrument(row)
    print(f"-- listing: {len(rows)} instrument(s) cached in {secs:.2f}s")
    return len(rows)


async def orders(client, txids: list[str]) -> int:
    import nautilus_trader
    from nautilus_trader.model import AccountId, InstrumentId

    account = AccountId(ACCOUNT_ID)
    print(f"nautilus_trader {nautilus_trader.__version__}; targets {' '.join(txids)}")
    rows, error, secs = await _timed(lambda: client.request_order_status_reports(account, open_only=True))
    print(f"-- reading, not the verdict: cache EMPTY, unscoped, open_only=True: {secs:.2f}s -> {error or f'{len(rows)} row(s)'}")
    if await _cache_listing(client) is None:
        return 3
    reasons: list[str] = []
    for open_only in (True, False):
        label = f"cache FULL, unscoped, open_only={open_only}"
        rows, error, secs = await _timed(lambda o=open_only: client.request_order_status_reports(account, open_only=o))
        if error:
            print(f"-- {label}: {secs:.2f}s -> {error}")
            reasons.append(f"{label} raised")
            continue
        open_rows = [r for r in rows if open_only or str(r.order_status) in ("ACCEPTED", "PARTIALLY_FILLED")]
        print(f"-- {label}: {secs:.2f}s -> {len(rows)} row(s), {len(open_rows)} open")
        for txid in txids:
            hits = [r for r in rows if str(r.venue_order_id) == txid]
            for r in hits:
                print(f"     {_line(r)}")
            if len(hits) != 1:
                reasons.append(f"{label}: {len(hits)} row(s) carry {txid}")
        if open_only:
            for r in rows:
                if str(r.venue_order_id) not in txids:
                    print(f"     NOT A TARGET: {_line(r)}")
        if secs > ONE_TICK_SECS:
            reasons.append(f"{label}: round trip {secs:.2f}s exceeds one {ONE_TICK_SECS:.0f}s tick")
    for iid in SCOPED:
        rows, error, secs = await _timed(
            lambda iid=iid: client.request_order_status_reports(account, instrument_id=InstrumentId.from_str(iid), open_only=True)
        )
        print(f"-- contrast, not the verdict: scoped {iid}, open_only=True: {secs:.2f}s -> {error or f'{len(rows)} row(s)'}")
    print("SAFE" if not reasons else "HAZARD: " + "; ".join(reasons))
    return 0 if not reasons else 1


async def absent(client, txids: list[str]) -> int:
    from nautilus_trader.model import AccountId

    account = AccountId(ACCOUNT_ID)
    if await _cache_listing(client) is None:
        return 3
    rows, error, secs = await _timed(lambda: client.request_order_status_reports(account, open_only=True))
    if error:
        print(f"HAZARD: the unscoped read raised after {secs:.2f}s: {error}")
        return 1
    print(f"-- cache FULL, unscoped, open_only=True: {secs:.2f}s -> {len(rows)} open row(s)")
    for r in rows:
        print(f"     {_line(r)}")
    still = [t for t in txids if any(str(r.venue_order_id) == t for r in rows)]
    print("SAFE" if not still else f"HAZARD: still open at the venue: {' '.join(still)}")
    return 0 if not still else 1


def main(argv: list[str]) -> int:
    mode, txids = (argv[0] if argv else ""), [a.strip() for a in argv[1:] if a.strip()]
    if mode not in ("orders", "absent") or not txids:
        print("usage: kraken-window-reads.py orders|absent <TXID>...")
        return 2
    try:
        key, secret = credentials()
    except Refusal as exc:
        print(f"refusing: {exc}")
        return 2
    client = build_client(key, secret)
    return asyncio.run(orders(client, txids) if mode == "orders" else absent(client, txids))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
