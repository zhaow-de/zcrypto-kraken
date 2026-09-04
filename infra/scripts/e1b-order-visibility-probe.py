#!/usr/bin/env python3
"""E1b — which open-orders call shapes return the resting rows, on the wheel we actually run.

E1 proved the mechanism: the adapter's open-orders read drops rows whose raw venue symbol misses an
unpopulated instrument cache — 0 rows before `cache_instrument`, 2 after, same client, one variable.
This does not re-prove that. It names WHICH of the call shapes return the rows, while the two-order
fixture still stands, so a later reader knows what `zcrypto engine flatten` and the startup pass can
and cannot see rather than inferring it from one data point.

READ-ONLY, and the claim is guarded rather than asserted: `tests/test_e1b_order_visibility_probe.py`
runs this sweep against a stub that raises on every write method, so the property is checked without
money on the line. Nothing here places, cancels, amends or edits anything.

The empty-cache arm is byte-for-byte what `cli/engine/flatten.py` gets: `KrakenSpotHttpClient(key,
secret)` with no other argument, reading with `open_only=True` and no `instrument_id`, under the
engine's own account id. That shape is marked in the table — it is the row that answers "what does
flatten see", and the other seven are the context that makes it interpretable.

`KrakenEnvironment` is deliberately absent: `KrakenSpotHttpClient.__init__` takes no such parameter
at all. The environment selector belongs to `KrakenExecutionClientConfig`, which the order-semantics
probe builds and this one does not — and adding any argument flatten does not pass would end the
like-for-like comparison this run exists to make.

Credentials come from the environment and are never stored, echoed or logged; the refusal names the
VARIABLES. On the engine host, run inside the engine image with the flatten wrapper's own shape —
`--env-file /opt/zcrypto-engine/engine.env` and this script mounted in read-only — but with
`--entrypoint python`, NOT flatten's value: flatten overrides to `zcrypto` because it runs a
subcommand, this is a plain script, and bare `python` is the image's venv interpreter
(`infra/docker/Dockerfile` puts `/app/.venv/bin` first on PATH). The override itself is the
load-bearing part, for the reason the flatten template also states: the image's ENTRYPOINT is a
`sh -c` launcher that `set --`s over whatever you appended and execs `zcrypto capture` with the
trade key in its environment — omit it and your arguments are discarded and this never runs.
`infra/scripts/probe-with-vaulted-key.sh` must not be used for this: its target is fixed to the
order-semantics harness, which places and cancels orders.

Nine venue calls: eight order-status reads, plus the one `request_instruments` the populated arm
needs to obtain an instrument to cache.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from typing import Any

API_KEY_VAR = "KRAKEN_SPOT_API_KEY"
API_SECRET_VAR = "KRAKEN_SPOT_API_SECRET"

# The engine's own account id (`cli/engine/flatten.py`'s ACCOUNT_ID, pinned equal to
# `cli/engine/node.py`'s). A read under a different account id answers a different question.
ACCOUNT_ID = "KRAKEN-001"

# The pair the fixture orders rest on, in the venue's own spelling and in the adapter's.
PAIR = "SOLEUR"
INSTRUMENT_ID = "SOL/EUR.KRAKEN"


class Refusal(RuntimeError):
    """Raised instead of building a client. Names variables, never values."""


@dataclass(frozen=True)
class Shape:
    cache_populated: bool
    open_only: bool
    by_instrument: bool
    is_flatten_shape: bool = False

    @property
    def label(self) -> str:
        cache = "populated" if self.cache_populated else "empty"
        scope = INSTRUMENT_ID if self.by_instrument else "(all)"
        return f"cache={cache:<9} open_only={str(self.open_only):<5} instrument_id={scope}"


# Ordered so the sweep walks the empty-cache arm first and populates the cache once, in the middle:
# the same client throughout, one variable moved, which is what makes the two arms comparable.
SHAPES: tuple[Shape, ...] = (
    Shape(cache_populated=False, open_only=True, by_instrument=False, is_flatten_shape=True),
    Shape(cache_populated=False, open_only=True, by_instrument=True),
    Shape(cache_populated=False, open_only=False, by_instrument=False),
    Shape(cache_populated=False, open_only=False, by_instrument=True),
    Shape(cache_populated=True, open_only=True, by_instrument=False),
    Shape(cache_populated=True, open_only=True, by_instrument=True),
    Shape(cache_populated=True, open_only=False, by_instrument=False),
    Shape(cache_populated=True, open_only=False, by_instrument=True),
)


def credentials() -> tuple[str, str]:
    key = os.environ.get(API_KEY_VAR, "")
    secret = os.environ.get(API_SECRET_VAR, "")
    missing = [name for name, value in ((API_KEY_VAR, key), (API_SECRET_VAR, secret)) if not value]
    if missing:
        raise Refusal(f"{' and '.join(missing)} not set in the environment; refusing to build a client")
    return key, secret


def build_client(key: str, secret: str, *, _ctor: Any = None) -> Any:
    """Exactly `cli/engine/command.py`'s construction — two positional arguments and nothing else.
    `_ctor` exists so a test can assert that without importing the compiled adapter."""
    if _ctor is None:
        from nautilus_trader.adapters.kraken import KrakenSpotHttpClient as _ctor  # noqa: N813
    return _ctor(key, secret)


def _order_ids(rows: Any) -> list[str]:
    """Order ids and nothing else. No descr, no volume, no price: this run answers a visibility
    question, and every additional field is account detail on a terminal that does not need it."""
    out: list[str] = []
    for row in rows or []:
        vid = getattr(row, "venue_order_id", None)
        out.append(str(vid) if vid is not None else "<no venue_order_id>")
    return out


async def sweep(client: Any, *, account_id: Any, pair: str, instrument_id: Any) -> list[tuple[Shape, int, list[str]]]:
    """Walk the eight shapes on ONE client, populating the cache once between the two arms."""
    results: list[tuple[Shape, int, list[str]]] = []
    populated = False
    for shape in SHAPES:
        if shape.cache_populated and not populated:
            instruments = await client.request_instruments(pairs=[pair])
            for instrument in instruments or []:
                client.cache_instrument(instrument)
            populated = True
        kwargs: dict[str, Any] = {"open_only": shape.open_only}
        if shape.by_instrument:
            kwargs["instrument_id"] = instrument_id
        rows = await client.request_order_status_reports(account_id, **kwargs)
        rows = list(rows or [])
        results.append((shape, len(rows), _order_ids(rows)))
    return results


def _render(results: list[tuple[Shape, int, list[str]]]) -> str:
    lines = ["", "shape                                                             rows  order ids", "-" * 100]
    for shape, count, ids in results:
        mark = "  <- flatten's shape" if shape.is_flatten_shape else ""
        lines.append(f"{shape.label:<62} {count:>4}  {', '.join(ids) if ids else '-'}{mark}")
    return "\n".join(lines)


async def _main() -> int:
    parser = argparse.ArgumentParser(description="E1b: which open-orders call shapes return the resting rows")
    parser.parse_args()
    try:
        key, secret = credentials()
    except Refusal as exc:
        print(f"refusing: {exc}")
        return 2
    from nautilus_trader.model import AccountId, InstrumentId

    client = build_client(key, secret)
    results = await sweep(
        client,
        account_id=AccountId(ACCOUNT_ID),
        pair=PAIR,
        instrument_id=InstrumentId.from_str(INSTRUMENT_ID),
    )
    print(_render(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
