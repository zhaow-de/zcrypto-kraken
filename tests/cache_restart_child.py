"""One engine-shaped node in its own interpreter, for tests/test_cache_restart.py.

The node is the engine's own `build_shadow_node`, with the cache backing attached through the config
and every venue default redirected to the loopback the driver runs: the two client configs' URLs,
the gate's venue reader, and the bare-client reads' `base_url`. Before anything is built the child
asserts that no production default remains, the autouse `_no_production_venue_read` fixture's rule
for a node that runs, and the bare client itself refuses a `base_url` off the loopback, the refusal
landing in the record's `errors`. The strategy the engine registers is subclassed to hand the
executor its quotes on a timer, since the data peer sends none, and to stop the node at the window's
end; its executor, its startup pass and its ledger writes are the engine's own.

argv[1] is a JSON object: `phase`, `journal_dir`, `store_dir`, `port`, `username`, `password`,
`api_key`, `api_secret`, `base_url`, `ws_public`, `ws_private`, `instrument`, `bid`, `ask`,
`quote_every`, `window_secs`, `out`, and `max_plan_notional_eur`. It writes `out` at the window's end
and again after `run()` returns, and exits 0 whatever `run()` did: the driver reads the record.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

CONFIG = json.loads(sys.argv[1])
os.environ["KRAKEN_SPOT_API_KEY"] = CONFIG["api_key"]
os.environ["KRAKEN_SPOT_API_SECRET"] = CONFIG["api_secret"]
os.environ["ZCRYPTO_CACHE_PASSWORD"] = CONFIG["password"]

from nautilus_trader.adapters.kraken import (  # noqa: E402
    KrakenDataClientConfig,
    KrakenEnvironment,
    KrakenExecutionClientConfig,
    KrakenProductType,
)
from nautilus_trader.model import AccountId, AccountType, InstrumentId, Price, Quantity, QuoteTick  # noqa: E402

from cli.config import CacheSettings, EngineConfig  # noqa: E402
from cli.engine import executor as executor_module  # noqa: E402
from cli.engine import node as node_module  # noqa: E402
from cli.engine.venue import VenueStatus  # noqa: E402
from cli.engine.venuestate import venue_state_from_cache  # noqa: E402
from cli.logging import configure  # noqa: E402

# The engine's own log shape: plain text on stdout at INFO, where the boot line and the library's
# Rust lines land together, as the unit's journal holds them on the engine host.
configure(None, "INFO", None)

LOOPBACK_HTTP = "http://127.0.0.1:"
LOOPBACK_WS = "ws://127.0.0.1:"
RECORD: dict = {"phase": CONFIG["phase"], "own": [], "external": [], "errors": [], "quotes": 0}
HANDLE: list = [None]


def _data_client_config() -> KrakenDataClientConfig:
    return KrakenDataClientConfig(
        product_type=KrakenProductType.SPOT,
        environment=KrakenEnvironment.LIVE,
        ws_idle_timeout_ms=0,
        base_url=CONFIG["base_url"],
        ws_public_url=CONFIG["ws_public"],
        ws_private_url=CONFIG["ws_public"],
        ws_l3_url=CONFIG["ws_public"],
    )


def _exec_client_config(credentials: tuple[str, str]) -> KrakenExecutionClientConfig:
    # The engine's own fields, plus the two URLs the loopback answers on.
    api_key, api_secret = credentials
    return KrakenExecutionClientConfig(
        account_id=AccountId(node_module._ACCOUNT_ID),
        product_type=KrakenProductType.SPOT,
        environment=KrakenEnvironment.LIVE,
        api_key=api_key,
        api_secret=api_secret,
        spot_account_type=AccountType.MARGIN,
        margin_balance_asset="ZEUR",
        spot_positions_quote_currency="ZEUR",
        use_ws_trade=False,
        base_url=CONFIG["base_url"],
        ws_url=CONFIG["ws_private"],
    )


def _venue_online(*, now, opener=None) -> VenueStatus:
    return VenueStatus(status="online", ok=True, observed_at=now)


node_module._data_client_config = _data_client_config
node_module._exec_client_config = _exec_client_config
node_module.read_system_status = _venue_online
executor_module.read_venue_orders = partial(executor_module.read_venue_orders, base_url=CONFIG["base_url"])
executor_module.cancel_venue_order = partial(executor_module.cancel_venue_order, base_url=CONFIG["base_url"])
executor_module.read_venue_holdings = partial(executor_module.read_venue_holdings, base_url=CONFIG["base_url"])
executor_module.read_venue_fills = partial(executor_module.read_venue_fills, base_url=CONFIG["base_url"])
executor_module.read_venue_positions = partial(executor_module.read_venue_positions, base_url=CONFIG["base_url"])
_production_bare_client = executor_module._bare_client


def _loopback_bare_client(base_url):
    if base_url is None or not str(base_url).startswith(LOOPBACK_HTTP):
        refusal = f"a bare venue client was asked for {base_url!r}, off the loopback"
        RECORD["errors"].append(refusal)
        raise AssertionError(refusal)
    return _production_bare_client(base_url)


executor_module._bare_client = _loopback_bare_client


def _refuse_production_defaults() -> None:
    """Exit 3 before the build if any venue default still points past the loopback."""
    data = _data_client_config()
    exec_ = _exec_client_config(("k", "s"))
    urls = [data.base_url, exec_.base_url]
    sockets = [data.ws_public_url, data.ws_private_url, data.ws_l3_url, exec_.ws_url]
    redirected = all(url.startswith(LOOPBACK_HTTP) for url in urls) and all(url.startswith(LOOPBACK_WS) for url in sockets)
    bare = all(
        isinstance(fn, partial) and str(fn.keywords.get("base_url", "")).startswith(LOOPBACK_HTTP)
        for fn in (
            executor_module.read_venue_orders,
            executor_module.cancel_venue_order,
            executor_module.read_venue_holdings,
            executor_module.read_venue_fills,
            executor_module.read_venue_positions,
        )
    )
    if not (
        redirected
        and bare
        and executor_module._bare_client is _loopback_bare_client
        and node_module.read_system_status is _venue_online
        and node_module._data_client_config is _data_client_config
        and node_module._exec_client_config is _exec_client_config
    ):
        sys.stderr.write("cache_restart_child: a venue default still points past the loopback; refusing to build\n")
        os._exit(3)


def _s(value) -> str | None:
    return None if value is None else str(value)


def _event(event) -> dict:
    out = {
        "type": type(event).__name__,
        "client_order_id": _s(getattr(event, "client_order_id", None)),
        "venue_order_id": _s(getattr(event, "venue_order_id", None)),
        "reconciliation": getattr(event, "reconciliation", None),
        "at": time.time(),
    }
    for key in ("last_qty", "trade_id", "reason"):
        if hasattr(event, key):
            out[key] = _s(getattr(event, key))
    return out


def _dump(cache) -> dict:
    orders = [
        {
            "client_order_id": _s(order.client_order_id),
            "strategy_id": _s(order.strategy_id),
            "venue_order_id": _s(order.venue_order_id),
            "status": _s(order.status),
            "quantity": _s(order.quantity),
            "filled_qty": _s(order.filled_qty),
            "is_open": order.is_open,
        }
        for order in cache.orders()
    ]
    positions = [
        {
            "id": _s(position.id),
            "strategy_id": _s(position.strategy_id),
            "instrument_id": _s(position.instrument_id),
            "signed_qty": position.signed_qty,
            "avg_px_open": position.avg_px_open,
            "realized_pnl": _s(position.realized_pnl),
            "is_open": position.is_open,
        }
        for position in cache.positions()
    ]
    return {"orders": orders, "positions": positions}


def _venue_state(cache) -> dict:
    """The positions and balances a venue record written now would carry, by the engine's own reader."""
    state = venue_state_from_cache(cache, clock=lambda: datetime.now(timezone.utc))
    return {"positions": dict(state.positions), "balances": dict(state.balances)}


class _Recorder:
    """The executor's metrics hook, recording the position and realized readings it publishes."""

    def __init__(self):
        self.positions: list = []
        self.realized: list = []

    def inc_order(self, outcome):
        pass

    def inc_external(self, disposition):
        pass

    def inc_fill(self, liquidity, fee_eur):
        pass

    def set_position(self, symbol, qty):
        self.positions.append((symbol, qty))

    def set_realized(self, value):
        self.realized.append(value)

    def set_resting_age(self, mode, seconds):
        pass

    def set_tracking_state(self, state):
        pass


METRICS = _Recorder()


def _write() -> None:
    RECORD["metrics"] = {"positions": METRICS.positions, "realized": METRICS.realized}
    Path(CONFIG["out"]).write_text(json.dumps(RECORD, indent=1, default=str))


class ShadowStrategy(node_module.ShadowStrategy):
    """The engine's strategy with a quote timer and a stop alert; `run_cycle_fn` is inert so no
    boundary cycle reaches a store or a venue from here. Named as the engine's is, since the
    strategy id the store keys everything under is derived from the class name."""

    def __init__(self, config: EngineConfig, *, executor_factory=None, **_):
        super().__init__(config, run_cycle_fn=lambda cycle_ts, *, config, venue_state=None: None, executor_factory=executor_factory)

    def on_start(self) -> None:
        try:
            super().on_start()
            RECORD["strategy_id"] = str(self.strategy_id)
            RECORD["at_start"] = _dump(self.cache)
            RECORD["venue_state_at_start"] = _venue_state(self.cache)
            self.clock.set_timer("child-quote", timedelta(seconds=CONFIG["quote_every"]), callback=self._quote)
            self.clock.set_time_alert(
                "child-stop", self.clock.utc_now() + timedelta(seconds=CONFIG["window_secs"]), callback=self._stop
            )
        except Exception:
            RECORD["errors"].append(traceback.format_exc())
            _write()
            HANDLE[0].stop()

    def _quote(self, event) -> None:
        tick = QuoteTick(
            InstrumentId.from_str(CONFIG["instrument"]),
            Price.from_str(CONFIG["bid"]),
            Price.from_str(CONFIG["ask"]),
            Quantity.from_str("10.0"),
            Quantity.from_str("10.0"),
            self.clock.timestamp_ns(),
            self.clock.timestamp_ns(),
        )
        RECORD["quotes"] += 1
        self.on_quote(tick)

    def _stop(self, event) -> None:
        try:
            RECORD["at_end"] = _dump(self.cache)
            RECORD["venue_state_at_end"] = _venue_state(self.cache)
            executor = self._executor
            RECORD["attached"] = sorted(executor._attached) if executor is not None else None
            RECORD["restored"] = sorted(getattr(executor, "_restored", ()) or ()) if executor is not None else None
        except Exception:
            RECORD["errors"].append(traceback.format_exc())
        _write()
        HANDLE[0].stop()

    def on_order_event(self, event) -> None:
        RECORD["own"].append(_event(event))
        super().on_order_event(event)

    def _on_external_order_event(self, event) -> None:
        RECORD["external"].append(_event(event))
        super()._on_external_order_event(event)


def main() -> None:
    _refuse_production_defaults()
    config = EngineConfig(
        store_dir=Path(CONFIG["store_dir"]),
        journal_dir=Path(CONFIG["journal_dir"]),
        exec_enabled=True,
        exec_armed=True,
        exec_max_plan_notional_eur=float(CONFIG["max_plan_notional_eur"]),
        cache=CacheSettings(enabled=True, host="127.0.0.1", port=int(CONFIG["port"]), username=CONFIG["username"]),
    )
    node_module.ShadowStrategy = ShadowStrategy
    executor_module.set_executor_hooks(metrics=METRICS)
    started = time.monotonic()
    node = node_module.build_shadow_node(config)
    HANDLE[0] = node.handle()
    RECORD["built_in"] = time.monotonic() - started
    started = time.monotonic()
    try:
        node.run()
    except BaseException as exc:
        RECORD["errors"].append(f"run raised {type(exc).__name__}: {exc}")
    finally:
        RECORD["run_secs"] = time.monotonic() - started
        try:
            node.dispose()
        except BaseException as exc:
            RECORD["errors"].append(f"dispose raised {type(exc).__name__}: {exc}")
        _write()
        sys.stdout.flush()
        os._exit(0)


if __name__ == "__main__":
    main()
