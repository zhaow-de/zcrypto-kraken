"""The two-process restart harness: the engine's own node, restarted against a real `valkey-server`
this file starts, with the venue a loopback the file scripts.

No environment gate, on purpose: a database is not a venue, and a skip on a missing binary would
read as coverage. CI installs the binary from apt (`.github/workflows/test-suite.yml`); a workstation
runs its own, whose version may differ from the fleet's, so a reading a server version could move
is named where it is asserted.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cli.engine.execgate import ARM_FILE, exec_dir
from cli.engine.execledger import exec_record_path, read_exec_record, validate_exec_record
from cli.engine.probeplan import PLAN_FILENAME
from tests import kraken_loopback as lb

REPO = Path(__file__).resolve().parents[1]
CHILD = Path(__file__).parent / "cache_restart_child.py"
ACL_TEMPLATE = REPO / "infra/ansible/roles/cache/templates/users.acl.j2"
BASKET_FIXTURE = Path(__file__).parent / "fixtures" / "kraken_assetpairs_basket.json"
INSTALL = "sudo apt-get install -y valkey-server"

PAIR, SYMBOL, INSTRUMENT = "SOLEUR", "SOL/EUR", "SOL/EUR.KRAKEN"
PRICE = 150.0
QTY = 1.0
SOL_QUOTE = (INSTRUMENT, f"{PRICE:.2f}", f"{PRICE + 0.1:.2f}")
ENGINE_USER, ENGINE_PASSWORD = "engine", "engine-harness-password"
ADMIN_USER, ADMIN_PASSWORD = "admin", "admin-harness-password"
# Phase windows: the executor's startup pass runs on its first tick at 5 s and the plan is picked up on
# the same tick; the first quote after that lands at 6 s and the fill frames within a second of the
# submission; phase 2's re-read pass runs on the tick after the pass's cancel. Each node adds the
# library's ten-second residual wait at stop.
PHASE1_WINDOW = 14
PHASE2_WINDOW = 20
CHILD_TIMEOUT = 150


def _valkey_binary() -> str:
    binary = shutil.which("valkey-server")
    if binary is None:
        pytest.fail(f"valkey-server is not on PATH: {INSTALL}")
    return binary


def _engine_acl_rules() -> str:
    """The `engine` user's rules as the cache role renders them, read off the template so the
    harness's server carries the fleet's ACL line."""
    match = re.search(r"^user engine on #\{\{ [^}]+ \}\} (.+)$", ACL_TEMPLATE.read_text(), re.M)
    assert match, "the users.acl template no longer carries the engine line in the shape this reads"
    return match.group(1)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _resp(port: int, user: str, password: str, *words: str) -> object:
    """One command on a fresh connection, RESP2, the reply decoded."""

    def encode(*items: str) -> bytes:
        return b"*%d\r\n" % len(items) + b"".join(b"$%d\r\n%s\r\n" % (len(w.encode()), w.encode()) for w in items)

    def decode(reader):
        line = reader.readline()
        kind, body = line[:1], line[1:-2]
        if kind == b"+":
            return body.decode()
        if kind == b"-":
            raise RuntimeError(body.decode())
        if kind == b":":
            return int(body)
        if kind == b"$":
            n = int(body)
            return None if n < 0 else reader.read(n + 2)[:-2].decode()
        if kind == b"*":
            n = int(body)
            return None if n < 0 else [decode(reader) for _ in range(n)]
        raise RuntimeError(f"bad reply {line!r}")

    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        reader = sock.makefile("rb")
        sock.sendall(encode("AUTH", user, password))
        assert decode(reader) == "OK"
        sock.sendall(encode(*words))
        return decode(reader)


def _keys(port: int) -> list[str]:
    keys: list[str] = []
    cursor = "0"
    while True:
        cursor, batch = _resp(port, ADMIN_USER, ADMIN_PASSWORD, "SCAN", cursor, "COUNT", "1000")
        keys += batch
        if cursor == "0":
            return sorted(keys)


class _Valkey:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.port = _free_port()
        self.acl = root / "users.acl"
        self.acl.write_text(
            f"user default off\nuser {ADMIN_USER} on >{ADMIN_PASSWORD} ~* &* +@all\n"
            f"user {ENGINE_USER} on >{ENGINE_PASSWORD} {_engine_acl_rules()}\n"
        )
        (root / "data").mkdir(exist_ok=True)
        self.process: subprocess.Popen | None = None
        self.log = root / "valkey.log"

    def start(self) -> None:
        with self.log.open("a") as log:
            self.process = subprocess.Popen(
                [
                    _valkey_binary(), "--port", str(self.port), "--bind", "127.0.0.1", "--dir", str(self.root / "data"),
                    "--save", "", "--appendonly", "no", "--daemonize", "no", "--aclfile", str(self.acl),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
            )  # fmt: skip
        try:
            for _ in range(100):
                try:
                    if _resp(self.port, ADMIN_USER, ADMIN_PASSWORD, "PING") == "PONG":
                        return
                except OSError:
                    time.sleep(0.1)
            pytest.fail(f"valkey-server did not answer on 127.0.0.1:{self.port}: {self.log.read_text()[-2000:]}")
        except BaseException:
            self.stop()
            raise

    def kill(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.send_signal(signal.SIGKILL)
            self.process.wait(10)

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(10)
            except subprocess.TimeoutExpired:
                self.process.kill()


class _Node:
    def __init__(self, root: Path, valkey_port: int, *, max_plan_notional_eur: float = 200.0):
        self.root = root
        self.state = root / "state"
        self.journal = self.state / "journal"
        self.store = self.state / "store"
        self.journal.mkdir(parents=True, exist_ok=True)
        self.store.mkdir(parents=True, exist_ok=True)
        exec_dir(self.state).mkdir(parents=True, exist_ok=True)
        (exec_dir(self.state) / ARM_FILE).touch()
        self.valkey_port = valkey_port
        self.max_plan_notional_eur = max_plan_notional_eur
        self.records: list[dict] = []
        self.logs: list[str] = []

    def _drop(self, plan_id: str, intent: dict) -> None:
        plan = {"plan_id": plan_id, "created_at": datetime.now(timezone.utc).isoformat(), "intents": [intent]}
        (exec_dir(self.state) / PLAN_FILENAME).write_text(json.dumps(plan))

    def drop_plan(self, plan_id: str, *, leverage: int | None = 2, notional_eur: float = PRICE * QTY, symbol: str = SYMBOL) -> None:
        intent = {"symbol": symbol, "side": "buy", "action": "open", "mode": "execute", "notional_eur": notional_eur}
        if leverage is not None:
            intent["leverage"] = leverage
        self._drop(plan_id, intent)

    def drop_spot_sell(self, plan_id: str, *, qty: float, symbol: str = SYMBOL) -> None:
        self._drop(plan_id, {"symbol": symbol, "side": "sell", "action": "close", "mode": "execute", "qty": qty})

    def run(
        self,
        phase: int,
        venue: lb.KrakenLoopback,
        data: lb.WsPeer,
        exec_: lb.WsPeer,
        *,
        window: int,
        valkey_port=None,
        quote: tuple[str, str, str] = SOL_QUOTE,
    ) -> dict:
        out = self.root / f"phase{phase}.json"
        args = {
            "phase": phase,
            "journal_dir": str(self.journal),
            "store_dir": str(self.store),
            "port": self.valkey_port if valkey_port is None else valkey_port,
            "username": ENGINE_USER,
            "password": ENGINE_PASSWORD,
            "api_key": lb.API_KEY,
            "api_secret": lb.API_SECRET,
            "base_url": venue.base_url,
            "ws_public": data.url,
            "ws_private": exec_.url,
            "instrument": quote[0],
            "bid": quote[1],
            "ask": quote[2],
            "quote_every": 3,
            "window_secs": window,
            "out": str(out),
            "max_plan_notional_eur": self.max_plan_notional_eur,
        }
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(self.root)}
        started = time.monotonic()
        result = subprocess.run(
            [sys.executable, str(CHILD), json.dumps(args)], capture_output=True, text=True, timeout=CHILD_TIMEOUT, cwd=REPO, env=env
        )
        log = result.stdout + result.stderr
        (self.root / f"phase{phase}.log").write_text(log)
        self.logs.append(log)
        assert out.exists(), (
            f"phase {phase} wrote no record (exit {result.returncode}, {time.monotonic() - started:.1f} s):\n{log[-4000:]}"
        )
        record = json.loads(out.read_text())
        record["log"] = log
        record["wall_secs"] = time.monotonic() - started
        self.records.append(record)
        return record

    def rows(self) -> list[dict]:
        rows = []
        for path in sorted(self.journal.glob("*/exec-*.json")):
            doc = read_exec_record(path)
            validate_exec_record(doc)
            rows.extend(doc["submitted"])
        return rows

    def intents(self) -> list[dict]:
        out = []
        for path in sorted(self.journal.glob("*/exec-*.json")):
            for entry in read_exec_record(path)["plans"]:
                out.extend(entry["intents"])
        return out

    def mark_row_reducer(self, client_order_id: str) -> None:
        """Rewrite a row's `order.reduce_only` to True: the ledger's witness that the previous process
        placed this order as a reducer, the one row the startup pass keeps resting."""
        for path in sorted(self.journal.glob("*/exec-*.json")):
            doc = read_exec_record(path)
            for row in doc["submitted"]:
                if row["client_order_id"] == client_order_id:
                    row["order"]["reduce_only"] = True
                    validate_exec_record(doc)
                    path.write_text(json.dumps(doc, indent=2, sort_keys=True))
                    return
        pytest.fail(f"no row for {client_order_id}")


def _script_first_fill(venue: lb.KrakenLoopback, exec_: lb.WsPeer, *, last_qty: float = 0.4, wire: dict, fill: bool = True) -> None:

    def on_add_order(form: dict, txid: str) -> None:
        wire.update(txid=txid, cl_ord_id=form.get("cl_ord_id"), opened_at=time.time())
        venue.open_orders[txid] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", opentm=wire["opened_at"]), oflags="fciq"
        )

        def frames() -> None:
            time.sleep(0.3)
            if not exec_.subscribed.wait(30):
                return
            exec_.send_execution(lb.exec_new(txid, wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE))
            if not fill:
                return
            time.sleep(0.7)
            wire["filled_at"] = time.time()
            exec_.send_execution(
                lb.exec_trade(
                    txid, wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE, last_qty=last_qty, cum_qty=last_qty,
                    exec_id="TLOOP1-AAAAA-AAAAAA", trade_id=1001,
                )
            )  # fmt: skip
            venue.open_orders[txid].update(vol_exec=f"{last_qty:.8f}", price=f"{PRICE:.5f}", cost=f"{last_qty * PRICE:.5f}")
            venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(
                txid, PAIR, vol=f"{last_qty:.8f}", price=f"{PRICE:.2f}", trade_id=1001, time=wire["filled_at"]
            )
            venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
                lb.margin_position(PAIR, volume=f"{last_qty:.8f}", time=wire["filled_at"]),
                ordertxid=txid,
                cost=f"{last_qty * PRICE:.5f}",
            )

        threading.Thread(target=frames, daemon=True).start()

    venue.on_add_order = on_add_order


def _script_cancel_ack(venue: lb.KrakenLoopback, exec_: lb.WsPeer, wire: dict) -> None:

    def on_cancel_order(form: dict) -> None:
        txid = wire["txid"]
        row = venue.open_orders.pop(txid, None)
        cum = float(row["vol_exec"]) if row else 0.0
        closed = lb.closed_order(
            PAIR,
            price=f"{PRICE:.2f}",
            volume=f"{QTY:.8f}",
            status="canceled",
            vol_exec=f"{cum:.8f}",
            opentm=wire["opened_at"],
            closetm=time.time(),
        )
        venue.closed_orders[txid] = dict(closed, oflags="fciq")

        def frame() -> None:
            time.sleep(0.3)
            exec_.send_execution(lb.exec_canceled(txid, wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE, cum_qty=cum))

        threading.Thread(target=frame, daemon=True).start()

    venue.on_cancel_order = on_cancel_order


def _script_spot_fills(venue: lb.KrakenLoopback, exec_: lb.WsPeer, *, pair: str, symbol: str, coin: str, fills: list) -> None:
    """Every AddOrder fills whole as a spot order, OpenPositions left as it was."""

    def on_add_order(form: dict, txid: str) -> None:
        side, volume, price = form["type"], form["volume"], form["price"]
        qty, px = float(volume), float(price)
        n = venue.txid_base + len(venue.add_orders)
        cl_ord_id = form.get("cl_ord_id")
        fills.append({"txid": txid, "side": side, "qty": qty, "price": px})
        opened_at = time.time()
        venue.open_orders[txid] = dict(lb.open_order(pair, price=price, volume=volume, side=side, opentm=opened_at), oflags="fciq")

        def frames() -> None:
            time.sleep(0.3)
            if not exec_.subscribed.wait(30):
                return
            exec_.send_execution(lb.exec_new(txid, cl_ord_id, symbol=symbol, qty=qty, price=px, side=side))
            time.sleep(0.7)
            filled_at = time.time()
            exec_.send_execution(
                lb.exec_trade(
                    txid, cl_ord_id, symbol=symbol, qty=qty, price=px, last_qty=qty, cum_qty=qty,
                    exec_id=f"TLOOP{n}-AAAAA-AAAAAA", trade_id=1000 + n, side=side,
                )
            )  # fmt: skip
            del venue.open_orders[txid]
            closed = lb.closed_order(
                pair, price=price, volume=volume, side=side, status="closed", vol_exec=volume, opentm=opened_at, closetm=filled_at
            )
            venue.closed_orders[txid] = dict(closed, oflags="fciq", price=f"{px:.5f}", cost=f"{qty * px:.5f}")
            venue.trades[f"TLOOP{n}-AAAAA-AAAAAA"] = lb.spot_trade_row(
                txid, pair, vol=volume, price=price, trade_id=1000 + n, side=side, time=filled_at
            )
            held = float(venue.balances.get(coin, lb.balance("0"))["balance"])
            held = round(held + qty if side == "buy" else held - qty, 8)
            if held > 0:
                venue.balances[coin] = lb.balance(f"{held:.8f}")
            else:
                venue.balances.pop(coin, None)

        threading.Thread(target=frames, daemon=True).start()

    venue.on_add_order = on_add_order


def _basket_pairs() -> dict:
    return json.loads(BASKET_FIXTURE.read_text())


@contextmanager
def _venue(pairs: dict | None = None) -> Iterator[tuple[lb.KrakenLoopback, lb.WsPeer, lb.WsPeer]]:
    """The loopback and its two peers, ClosedOrders and TradesHistory bounded by a request's `start`: every
    row this file builds is stamped at the moment its venue event happened in the run, so a start's
    reconciliation lookback reads the history it would read at Kraken."""
    with lb.serve_with_sockets(pairs or _basket_pairs()) as (venue, data, exec_):
        venue.bound_by_start = True
        yield venue, data, exec_


def _restore_lines(log: str) -> list[str]:
    return [line.split("cache restore: ", 1)[1] for line in log.splitlines() if "cache restore: " in line]


def _phase_one(valkey: _Valkey, tmp_path: Path) -> tuple[_Node, dict, dict]:
    """A node that placed one leveraged order, filled 0.4 of 1.0, and stopped with it resting: the
    store holds the order, the fill and the margin position. `wire` carries the venue's stamps --
    `opened_at`, `filled_at`, and `stopped_at`, a moment the node was down, after the fill and before
    any restart -- for a later venue to serve the same history."""
    valkey.start()
    node = _Node(tmp_path / "node", valkey.port)
    node.drop_plan("p-phase-1")
    wire: dict = {}
    with _venue() as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        _script_first_fill(venue, exec_, wire=wire)
        record = node.run(1, venue, data, exec_, window=PHASE1_WINDOW)
    wire["stopped_at"] = time.time()
    assert record["errors"] == [], record["errors"]
    assert [e["type"] for e in record["own"]][:4] == ["OrderInitialized", "OrderSubmitted", "OrderAccepted", "OrderFilled"], record[
        "own"
    ]
    [row] = node.rows()
    assert (row["state"], row["filled_qty"], row["order"]["leverage"]) == ("accepted", 0.4, 2), row
    assert row["client_order_id"] == record["own"][0]["client_order_id"]
    wire["client_order_id"] = row["client_order_id"]
    assert "trader-SHADOW-001:orders:" + row["client_order_id"] in _keys(valkey.port)
    return node, wire, record


@pytest.fixture
def phase_one(tmp_path):
    valkey = _Valkey(tmp_path / "valkey")
    try:
        node, wire, record = _phase_one(valkey, tmp_path)
        yield valkey, node, wire, record
    finally:
        valkey.stop()


def test_a_server_that_fails_its_readiness_check_is_stopped_before_the_failure_escapes(tmp_path):
    valkey = _Valkey(tmp_path / "valkey")
    valkey.acl.write_text(valkey.acl.read_text().replace(ADMIN_PASSWORD, "another-harness-password"))
    try:
        with pytest.raises(RuntimeError, match="WRONGPASS"):
            valkey.start()
        listed = subprocess.run(["pgrep", "-af", "valkey-server"], capture_output=True, text=True).stdout.splitlines()
        survivors = [line for line in listed if line.endswith(f"127.0.0.1:{valkey.port}")]
        assert (valkey.process.poll() is not None, survivors) == (True, []), survivors
    finally:
        valkey.kill()


def test_an_execution_peer_that_fails_to_start_closes_the_data_peer_before_the_failure_escapes(monkeypatch):
    closed = []

    class _Peer(lb.WsPeer):
        def __init__(self, label: str):
            if label == "exec":
                raise AssertionError("the exec WebSocket peer did not start")
            super().__init__(label)

        def close(self) -> None:
            closed.append(self.label)
            super().close()

    monkeypatch.setattr(lb, "WsPeer", _Peer)
    with pytest.raises(AssertionError, match="exec WebSocket peer"), lb.serve_with_sockets():
        pass
    assert closed == ["data"]


_BARE_CLIENT_PROBE = """
import runpy, sys
namespace = runpy.run_path(sys.argv[2], run_name="cache_restart_child_probe")
namespace["_refuse_production_defaults"]()
from cli.engine import executor
refused = []
for url in (None, "https://api.kraken.com", "http://127.0.0.2:1"):
    try:
        executor._bare_client(url)
    except AssertionError:
        refused.append(url)
executor._bare_client("http://127.0.0.1:1")
print("PROBE", repr((refused, len(namespace["RECORD"]["errors"]))))
"""


def test_the_child_refuses_a_bare_venue_client_off_the_loopback_whichever_read_asks(tmp_path):
    config = {
        "phase": 0,
        "api_key": lb.API_KEY,
        "api_secret": lb.API_SECRET,
        "password": "unused",
        "base_url": "http://127.0.0.1:1",
        "ws_public": "ws://127.0.0.1:1",
        "ws_private": "ws://127.0.0.1:1",
    }
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONDONTWRITEBYTECODE": "1", "HOME": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, "-c", _BARE_CLIENT_PROBE, json.dumps(config), str(CHILD)],
        capture_output=True,
        text=True,
        timeout=CHILD_TIMEOUT,
        cwd=REPO,
        env=env,
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("PROBE ")]
    assert lines == ["PROBE ([None, 'https://api.kraken.com', 'http://127.0.0.2:1'], 3)"], result.stdout + result.stderr


def test_a_resting_order_and_a_margin_position_are_restored_across_a_restart(phase_one):
    """No `Unresolved positions` line: the failure the operating rule stands against."""
    valkey, node, wire, _ = phase_one
    with _venue() as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.open_orders[wire["txid"]] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", opentm=wire["opened_at"]),
            oflags="fciq",
            vol_exec="0.40000000",
            price="150.00000",
            cost="60.00000",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(
            wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001, time=wire["filled_at"]
        )
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.40000000", time=wire["filled_at"]), ordertxid=wire["txid"], cost="60.00000"
        )
        _script_cancel_ack(venue, exec_, wire)
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)

    assert record["errors"] == [], record["errors"]
    assert "Unresolved positions" not in record["log"]
    assert f"matched by venue_order_id {wire['txid']}" in record["log"]
    [order] = record["at_start"]["orders"]
    assert (order["client_order_id"], order["strategy_id"], order["venue_order_id"], order["filled_qty"]) == (
        wire["client_order_id"],
        "ShadowStrategy-000",
        wire["txid"],
        "0.40000000",
    )
    [position] = record["at_start"]["positions"]
    # The wheel's Position carries Decimal fields, which the child's dump writes as strings.
    assert (position["instrument_id"], position["strategy_id"], position["signed_qty"], position["avg_px_open"]) == (
        INSTRUMENT,
        "ShadowStrategy-000",
        "0.4",
        "150",
    )
    assert _restore_lines(record["log"]) == [
        "1 order(s), 1 position(s) restored",
        "position SOL/EUR.KRAKEN 0.4 @ 150 (ShadowStrategy-000)",
        f"order {wire['client_order_id']} partial, 0.40000000 of 1.00000000 filled @ 150.00",
    ]
    assert record["external"] == [], record["external"]  # every later event reaches the own topic
    # The executor: the restored set, the pass's cancel of the restored opener named with its fill
    # state, the row settled from the venue's report by the re-read pass, and the intent the sweep wrote.
    assert record["restored"] == [wire["client_order_id"]]
    assert (
        f"canceling restored order {wire['client_order_id']}, partial -- the ledger does not carry it as a resting reducer"
        in record["log"]
    )
    [row] = node.rows()
    [intent] = node.intents()
    assert (row["state"], row["filled_qty"], intent["outcome"]) == ("canceled", 0.4, "revoked")
    _reads_nothing(record)


def test_a_fill_made_while_the_engine_was_down_is_booked_from_the_trade_history(phase_one):
    valkey, node, wire, _ = phase_one
    with _venue() as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.open_orders[wire["txid"]] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", opentm=wire["opened_at"]),
            oflags="fciq",
            vol_exec="0.70000000",
            price="150.00000",
            cost="105.00000",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(
            wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001, time=wire["filled_at"]
        )
        venue.trades["TLOOP2-AAAAA-AAAAAA"] = lb.trade_row(
            wire["txid"], PAIR, vol="0.30000000", price="150.00", trade_id=1002, time=wire["stopped_at"]
        )
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.70000000", time=wire["filled_at"]), ordertxid=wire["txid"], cost="105.00000"
        )
        _script_cancel_ack(venue, exec_, wire)
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)

    assert record["errors"] == [], record["errors"]
    assert "Unresolved positions" not in record["log"]
    orders = {o["strategy_id"]: o for o in record["at_start"]["orders"]}
    positions = {p["strategy_id"]: p for p in record["at_start"]["positions"]}
    assert (orders[record["strategy_id"]]["filled_qty"], orders[record["strategy_id"]]["status"]) == (
        "0.70000000",
        "PARTIALLY_FILLED",
    )
    assert {sid: (p["signed_qty"], p["avg_px_open"]) for sid, p in positions.items()} == {"ShadowStrategy-000": ("0.7", "150")}
    assert {tuple(p) for p in record["metrics"]["positions"] if p[0] == "SOL/EUR"} == {("SOL/EUR", 0.7)}
    assert _restore_lines(record["log"]) == [
        "1 order(s), 1 position(s) restored",
        "position SOL/EUR.KRAKEN 0.7 @ 150 (ShadowStrategy-000)",
        f"order {wire['client_order_id']} partial, 0.70000000 of 1.00000000 filled @ 150.00",
    ]
    # The executor: the venue's report repairs the row to the venue's figure before the pass's cancel.
    label = f"{wire['client_order_id']} (Kraken {wire['txid']})"
    assert f"adopted order {label} reconciled against the venue: 0.7 filled there against the 0.4 recorded here" in record["log"]
    [row] = node.rows()
    assert (row["filled_qty"], row["state"]) == (0.7, "canceled")
    assert [e["qty"] for e in row["events"] if e.get("event") == "reconciled"] == [pytest.approx(0.3)]


def test_an_order_cancelled_while_the_engine_was_down_is_closed_by_the_librarys_start(phase_one):
    """Mass status reads ClosedOrders before OpenPositions on this pin, so the start closes the restored
    copy from the venue's report and the startup pass finds nothing resting to cancel."""
    valkey, node, wire, _ = phase_one
    with _venue() as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        closed = lb.closed_order(
            PAIR,
            price=f"{PRICE:.2f}",
            volume=f"{QTY:.8f}",
            status="canceled",
            vol_exec="0.40000000",
            opentm=wire["opened_at"],
            closetm=wire["stopped_at"],
        )
        venue.closed_orders[wire["txid"]] = dict(closed, oflags="fciq")
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(
            wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001, time=wire["filled_at"]
        )
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.40000000", time=wire["filled_at"]), ordertxid=wire["txid"], cost="60.00000"
        )
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
        private_calls = list(venue.private_calls)

    assert record["errors"] == [], record["errors"]
    assert "OpenPositions" in private_calls, private_calls
    assert "ClosedOrders" in private_calls[: private_calls.index("OpenPositions")], private_calls
    [order] = record["at_start"]["orders"]
    assert (order["status"], order["is_open"], order["filled_qty"]) == ("CANCELED", False, "0.40000000")
    assert f"(matched by venue_order_id {wire['txid']}) {INSTRUMENT} [PARTIALLY_FILLED] -> [CANCELED]" in record["log"]
    assert _restore_lines(record["log"]) == [
        "0 order(s), 1 position(s) restored",
        f"position {INSTRUMENT} 0.4 @ 150 (ShadowStrategy-000)",
    ]
    # The executor: the row written from its own venue read, no stale copy left, no cancel sent.
    assert "ClosedOrders" in private_calls[private_calls.index("OpenPositions") :], private_calls
    assert "CancelOrder" not in private_calls, private_calls
    assert "its stale open copy stays in the Cache" not in record["log"]
    [row] = node.rows()
    [intent] = node.intents()
    assert (row["state"], row["filled_qty"], intent["outcome"]) == ("canceled", 0.4, "revoked")


def test_a_trade_frame_on_a_restored_open_order_is_booked_twice_by_the_library(phase_one):
    """The row is the previous process's reducer, which the startup pass keeps, so the order is still
    open when the `trade` frame lands."""
    valkey, node, wire, _ = phase_one
    node.mark_row_reducer(wire["client_order_id"])
    with _venue() as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.open_orders[wire["txid"]] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", opentm=wire["opened_at"]),
            oflags="fciq",
            vol_exec="0.40000000",
            price="150.00000",
            cost="60.00000",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(
            wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001, time=wire["filled_at"]
        )
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.40000000", time=wire["filled_at"]), ordertxid=wire["txid"], cost="60.00000"
        )

        def later() -> None:
            if not exec_.subscribed.wait(60):
                return
            time.sleep(8)  # past the startup pass, which keeps the reducer resting
            exec_.send_execution(
                lb.exec_trade(
                    wire["txid"], wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE, last_qty=0.2, cum_qty=0.6,
                    exec_id="TLOOP3-AAAAA-AAAAAA", trade_id=1003,
                )
            )  # fmt: skip
            venue.open_orders[wire["txid"]].update(vol_exec="0.60000000", cost="90.00000")
            venue.trades["TLOOP3-AAAAA-AAAAAA"] = lb.trade_row(
                wire["txid"], PAIR, vol="0.20000000", price="150.00", trade_id=1003, time=time.time()
            )

        threading.Thread(target=later, daemon=True).start()
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
        cancels = list(venue.cancel_forms)

    assert record["errors"] == [], record["errors"]
    assert cancels == [], cancels  # the pass kept the reducer
    assert "Generated inferred fill" in record["log"]
    fills = [e for e in record["own"] if e["type"] == "OrderFilled"]
    assert [(e["last_qty"], e["reconciliation"]) for e in fills] == [("0.20000000", True), ("0.20000000", True)], fills
    [order] = record["at_end"]["orders"]
    assert order["filled_qty"] == "0.80000000"  # the venue's cumulative figure is 0.6
    # The executor: both fills credit the row nothing, the re-read pass repairs it to the venue's 0.6,
    # and the kept reducer's intent stays pending on its open row.
    assert record["restored"] == [wire["client_order_id"]]
    [row] = node.rows()
    fills = [e for e in row["events"] if e.get("event") == "fill"]
    assert [(e["qty"], e.get("credited")) for e in fills] == [(0.4, None), (0.2, 0.0), (0.2, 0.0)]
    assert "the re-read pass reads 1 restored row(s) with a fill since its last read against the venue" in record["log"]
    assert (row["filled_qty"], row["state"]) == (pytest.approx(0.6), "accepted")
    [intent] = node.intents()
    assert intent["outcome"] == "pending"
    # The realized baseline over a real restored position: each fill's publish reads this process's own
    # realizations, the previous run's left in the baseline.
    assert record["metrics"]["realized"] and set(record["metrics"]["realized"]) == {0.0}, record["metrics"]["realized"]


def test_a_trade_frame_on_a_restored_opener_racing_the_passs_cancel_is_booked_twice_and_the_row_settles_at_the_venues_figure(
    phase_one,
):
    """The D7 race: the restored opener the startup pass cancels takes a `trade` frame (last 0.2,
    cumulative 0.6) between the pass's cancel and the venue's ack. The library books it twice, 0.8 on
    a copy the ack then closes, and flags the ack `reconciliation` -- its fill-decrease handling, so
    the row reads `ambiguous` until the re-read pass reads the venue's closed report; both fills
    credit the row nothing, the pass repairs it to the venue's 0.6 and closes it `canceled`, and the
    intent the sweep wrote at the cancel stays `revoked`."""
    valkey, node, wire, _ = phase_one
    with _venue() as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.open_orders[wire["txid"]] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", opentm=wire["opened_at"]),
            oflags="fciq",
            vol_exec="0.40000000",
            price="150.00000",
            cost="60.00000",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(
            wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001, time=wire["filled_at"]
        )
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.40000000", time=wire["filled_at"]), ordertxid=wire["txid"], cost="60.00000"
        )
        _script_cancel_ack(venue, exec_, wire)
        ack = venue.on_cancel_order

        def trade_then_ack(form: dict) -> None:
            # Inside the venue's CancelOrder: the frame and the listings it moves land before the answer.
            exec_.send_execution(
                lb.exec_trade(
                    wire["txid"], wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE, last_qty=0.2, cum_qty=0.6,
                    exec_id="TLOOP3-AAAAA-AAAAAA", trade_id=1003,
                )
            )  # fmt: skip
            venue.open_orders[wire["txid"]].update(vol_exec="0.60000000", cost="90.00000")
            venue.trades["TLOOP3-AAAAA-AAAAAA"] = lb.trade_row(
                wire["txid"], PAIR, vol="0.20000000", price="150.00", trade_id=1003, time=time.time()
            )
            venue.positions["TPOSLP-AAAAA-BBBBBB"].update(vol="0.60000000", cost="90.00000")
            ack(form)

        venue.on_cancel_order = trade_then_ack
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
        cancels = list(venue.cancel_forms)

    assert record["errors"] == [], record["errors"]
    assert [form.get("txid") for form in cancels] == [wire["txid"]]
    assert "Generated inferred fill" in record["log"]
    assert [(e["type"], e["reconciliation"]) for e in record["own"]] == [
        ("OrderPendingCancel", False),
        ("OrderFilled", True),
        ("OrderFilled", True),
        ("OrderCanceled", True),
    ], record["own"]
    [order] = record["at_end"]["orders"]
    assert (order["status"], order["filled_qty"]) == ("CANCELED", "0.80000000")  # the venue's cumulative figure is 0.6
    [row] = node.rows()
    fills = [e for e in row["events"] if e.get("event") == "fill"]
    assert [(e["qty"], e.get("credited")) for e in fills] == [(0.4, None), (0.2, 0.0), (0.2, 0.0)], fills
    assert "its row reads ambiguous until the re-read pass settles it" in record["log"]
    assert "the re-read pass reads 1 restored row(s) with a fill since its last read against the venue" in record["log"]
    assert (
        f"a fill on restored order {row['client_order_id']} credits nothing until the venue is read -- the next restart is taken flat"
        in record["log"]
    )
    assert (row["state"], row["filled_qty"]) == ("canceled", pytest.approx(0.6))
    assert [e["qty"] for e in row["events"] if e.get("event") == "reconciled"] == [pytest.approx(0.2)]
    [intent] = node.intents()
    assert intent["outcome"] == "revoked"


def test_an_empty_cache_beside_open_ledger_rows_is_a_cold_start_the_pass_reconciles_as_today(tmp_path):
    """The owner's ruling: an empty namespace is a cold start, never a refusal. The order is a spot
    one, so the venue has no margin position for the start to fail on, and it filled 0.4 before the
    stop: the library creates the EXTERNAL copy from the venue's report with that fill applied,
    PARTIALLY_FILLED and no position -- no trip. The restarted node reads zero, reconciliation names
    the order by its txid under EXTERNAL, the pass cancels it as an order the ledger carries as no
    reducer, and the cancel's ack infers no second fill."""
    valkey = _Valkey(tmp_path / "valkey")
    try:
        valkey.start()
        node = _Node(tmp_path / "node", valkey.port)
        node.drop_plan("p-spot", leverage=None)
        wire: dict = {}
        with _venue() as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000")}
            _script_first_fill(venue, exec_, wire=wire)
            record = node.run(1, venue, data, exec_, window=PHASE1_WINDOW)
        assert record["errors"] == [], record["errors"]
        [row] = node.rows()
        assert (row["state"], row["filled_qty"], row["order"]["leverage"]) == ("accepted", 0.4, None)
        wire["client_order_id"] = row["client_order_id"]
        assert len(_keys(valkey.port)) > 0
        # The store lost: a fresh server on the same port, the venue still listing the order open.
        valkey.kill()
        valkey.start()
        assert _keys(valkey.port) == []
        with _venue() as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000"), "SOL": lb.balance("0.40000000")}
            venue.open_orders[wire["txid"]] = dict(
                lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", opentm=wire["opened_at"]),
                oflags="fciq",
                vol_exec="0.40000000",
                price="150.00000",
                cost="60.00000",
            )
            venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(
                wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001, time=wire["filled_at"]
            )
            _script_cancel_ack(venue, exec_, wire)
            record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
            cancels = list(venue.cancel_forms)
    finally:
        valkey.stop()

    assert record["errors"] == [], record["errors"]
    assert _restore_lines(record["log"]) == ["0 order(s), 0 position(s) restored"]
    assert record["restored"] == [wire["txid"]]  # the EXTERNAL copy reconciliation created, in the set under its txid
    assert f"Created external order {wire['txid']}" in record["log"]
    [external] = record["at_start"]["orders"]
    assert (
        external["client_order_id"],
        external["strategy_id"],
        external["venue_order_id"],
        external["status"],
        external["filled_qty"],
        external["is_open"],
    ) == (
        wire["txid"],
        "EXTERNAL",
        wire["txid"],
        "PARTIALLY_FILLED",
        "0.40000000",
        True,
    )
    assert record["at_start"]["positions"] == []
    assert "execution kill switch tripped" not in record["log"]
    # The EXTERNAL copy reads the venue's 0.4, so the withdrawal check reads no shortfall and the trade
    # history is not consulted.
    assert "reads 0 filled on its order figure" not in record["log"]
    assert f"canceling adopted resting order {wire['txid']} -- the ledger does not carry it as a resting reducer" in record["log"]
    assert [form.get("txid") for form in cancels] == [wire["txid"]]
    assert [e["client_order_id"] for e in record["external"]][:1] == [wire["txid"]]
    # The row settles at the venue's 0.4, canceled by the pass.
    [row] = node.rows()
    fills = [e for e in row["events"] if e.get("event") == "fill"]
    assert [(e["qty"], e.get("credited")) for e in fills] == [(0.4, None)], fills
    assert (row["filled_qty"], row["state"]) == (0.4, "canceled")
    [intent] = node.intents()
    assert intent["outcome"] == "revoked"


def _open_positions(dump: dict) -> list[tuple[str, float]]:
    return sorted((p["strategy_id"], p["signed_qty"]) for p in dump["positions"] if p["is_open"])


_SOL = {"pair": PAIR, "symbol": SYMBOL, "coin": "SOL", "quote": SOL_QUOTE}
# Kraken's own spellings: the pair `XDGEUR`, the BalanceEx code `XXDG`, which the adapter reports as `DOGE`.
_DOGE = {"pair": "XDGEUR", "symbol": "DOGE/EUR", "coin": "XXDG", "quote": ("DOGE/EUR.KRAKEN", "0.2", "0.3")}
_EUR_ONLY = {"balances": {"ZEUR": lb.balance("1000.00000000")}}


def _spot_process(node: _Node, n: int, holdings: dict, leg: dict = _SOL, *, pairs: dict | None = None) -> tuple[dict, dict, list]:
    """One node process over a venue holding `holdings`: its record, the venue's holdings afterwards,
    and the fills."""
    fills: list = []
    with _venue(pairs) as (venue, data, exec_):
        venue.hold(holdings)
        _script_spot_fills(venue, exec_, pair=leg["pair"], symbol=leg["symbol"], coin=leg["coin"], fills=fills)
        record = node.run(n, venue, data, exec_, window=PHASE1_WINDOW, quote=leg["quote"])
        record["private_calls"] = list(venue.private_calls)
        return record, venue.holdings(), fills


_BUMP = "the nautilus build the tree pins no longer does what this test recorded of it"


def _reads_nothing(record: dict) -> None:
    counts = record["metrics"]["reconciliation_positions"]
    assert counts and not any(counts), (
        f"{_BUMP}: a position the library's reconciliation did not book no longer reads 0 on the count the page reads, "
        f"or no read of it ran: {counts}"
    )


def test_a_start_holds_the_venues_floor_over_the_stored_instrument(tmp_path):
    basket = _basket_pairs()
    eth = next(key for key, row in basket.items() if row.get("altname") == "ETHEUR")

    def listing(floor: str) -> dict:
        return basket | {eth: basket[eth] | {"ordermin": floor}}

    valkey = _Valkey(tmp_path / "valkey")
    try:
        valkey.start()
        node = _Node(tmp_path / "node", valkey.port)
        first, _, _ = _spot_process(node, 1, _EUR_ONLY, pairs=listing("0.002"))
        stored = _keys(valkey.port)
        second, _, _ = _spot_process(node, 2, _EUR_ONLY, pairs=listing("0.001"))
    finally:
        valkey.stop()

    assert first["errors"] == [] and second["errors"] == []
    assert "trader-SHADOW-001:instruments:ETH/EUR.KRAKEN" in stored
    floors = [record["venue_state_at_start"]["ordermin"]["ETH/EUR"] for record in (first, second)]
    assert floors == [0.002, 0.001], f"{_BUMP}: a start no longer takes the venue's floor over the stored instrument: {floors}"


def test_a_restored_spot_lot_comes_back_at_the_lot_with_no_external_short_and_the_account_keeps_its_coin(tmp_path):
    valkey = _Valkey(tmp_path / "valkey")
    try:
        valkey.start()
        node = _Node(tmp_path / "node", valkey.port)
        node.drop_plan("p-spot-buy", leverage=None)
        bought, holdings, _ = _spot_process(node, 1, _EUR_ONLY)
        node.drop_spot_sell("p-spot-sell", qty=QTY)
        held, sold_out, _ = _spot_process(node, 2, holdings)
        flat, _, _ = _spot_process(node, 3, sold_out)
    finally:
        valkey.stop()

    for record in (bought, held, flat):
        assert record["errors"] == [], record["errors"]
        assert "Unresolved positions" not in record["log"]
    assert [(row["order"]["side"], row["state"], row["filled_qty"]) for row in node.rows()] == [
        ("buy", "filled", QTY),
        ("sell", "filled", QTY),
    ], node.rows()
    assert (holdings["balances"]["SOL"]["balance"], "SOL" in sold_out["balances"]) == (f"{QTY:.8f}", False)

    assert "OpenPositions" in held["private_calls"] and holdings["positions"] == {}, held["private_calls"]
    assert (_restore_lines(held["log"]), _open_positions(held["at_start"])) == (
        ["0 order(s), 1 position(s) restored", f"position {INSTRUMENT} 1 @ 150 (ShadowStrategy-000)"],
        [("ShadowStrategy-000", "1")],
    ), (
        f"{_BUMP}: a restart over a spot lot under spot_account_type=MARGIN no longer restores the lot alone, under the "
        "strategy and at the lot; an EXTERNAL line beside it is upstream #5181's offset back. Rung 3's held figure "
        "(docs/research/00.master-plan.md §12) rests on this restore -- re-read it against what a restart restores now: "
        f"{_restore_lines(held['log'])}"
    )
    buy = node.rows()[0]["client_order_id"]
    orders = [order["client_order_id"] for order in held["at_start"]["orders"]]
    assert buy in orders, (
        f"{_BUMP}: the buy behind a spot lot held across a restart no longer comes back with its order in the store, "
        f"so the 0 below would not read its tags: {buy}, {orders}"
    )
    _reads_nothing(held)
    assert held["venue_state_at_start"]["positions"][SYMBOL] == QTY, (
        f"{_BUMP}: the venue record's position for a spot lot held across a restart is no longer the lot"
    )
    assert "the venue holds" not in held["log"], (
        f"{_BUMP}: the startup pass now reads Kraken's balance and the Cache apart over a restored spot lot"
    )
    gauge = [qty for symbol, qty in held["metrics"]["positions"] if symbol == SYMBOL]
    assert (gauge[0], gauge[-1]) == (QTY, 0.0), gauge

    assert _open_positions(held["at_end"]) == [], (
        f"{_BUMP}: the engine's sale of a restored spot lot no longer leaves the Cache with nothing open: "
        f"{_open_positions(held['at_end'])}"
    )
    settled = [qty for symbol, qty in flat["metrics"]["positions"] if symbol == SYMBOL]
    assert (_restore_lines(flat["log"]), _open_positions(flat["at_start"]), settled, "the venue holds" in flat["log"]) == (
        ["0 order(s), 0 position(s) restored"],
        [],
        [0.0],
        False,
    ), (
        f"{_BUMP}: a restart after a restored spot lot was sold whole no longer leaves the Cache with nothing open: "
        f"{_restore_lines(flat['log'])}"
    )

    stale = (
        "`draft-plan`'s cap on a sell reads the venue record's balances as a figure taken at a start, raised by a later "
        "start and never lowered -- re-read it, and the clearing of the stored account before an entry, against what the "
        "account carries now"
    )
    assert "SOL" not in bought["venue_state_at_end"]["balances"], (
        f"{_BUMP}: the account the venue record is built from now carries a coin inside the process that bought it. "
        f"{stale}: {bought['venue_state_at_end']['balances']}"
    )
    assert held["venue_state_at_start"]["balances"].get("SOL") == QTY, (
        f"{_BUMP}: a restart with the lot held no longer puts the coin on the account at the venue's balance. "
        f"{stale}: {held['venue_state_at_start']['balances']}"
    )
    assert (held["venue_state_at_end"]["balances"].get("SOL"), flat["venue_state_at_start"]["balances"].get("SOL")) == (QTY, QTY), (
        f"{_BUMP}: the account no longer keeps a coin at the lot once it is sold whole and the node restarted with the "
        f"venue's balance at 0. {stale}: {held['venue_state_at_end']['balances']} at the selling process's end, "
        f"{flat['venue_state_at_start']['balances']} after the restart"
    )


def _lines(log: str, text: str) -> list[str]:
    return [line for line in log.splitlines() if text in line]


def test_a_doge_lot_held_across_two_restarts_loads_the_account_at_each_start_and_the_account_carries_it_as_doge(tmp_path):
    # A pair whose base no process registers, beside the basket: no start may log an ERROR over it.
    basket = _basket_pairs()
    pairs = basket | {"QQQZEUR": basket["ADAEUR"] | {"base": "QQQZ", "altname": "QQQZEUR", "wsname": "QQQZ/EUR"}}
    valkey = _Valkey(tmp_path / "valkey")
    stored: list[list[str]] = []
    try:
        valkey.start()
        node = _Node(tmp_path / "node", valkey.port)
        node.drop_plan("p-doge-buy", leverage=None, notional_eur=25.0, symbol=_DOGE["symbol"])
        bought, holdings, [fill] = _spot_process(node, 1, _EUR_ONLY, _DOGE, pairs=pairs)
        stored.append(_keys(valkey.port))
        first, _, _ = _spot_process(node, 2, holdings, _DOGE, pairs=pairs)
        stored.append(_keys(valkey.port))
        second, _, _ = _spot_process(node, 3, holdings, _DOGE, pairs=pairs)
    finally:
        valkey.stop()

    lot = fill["qty"]
    for record in (bought, first, second):
        assert record["errors"] == [], record["errors"]
        assert "at_start" in record and "Unresolved positions" not in record["log"]
    assert holdings["balances"]["XXDG"]["balance"] == f"{lot:.8f}"

    failed_loads = [_lines(record["log"], "Failed to load account") for record in (bought, first, second)]
    assert failed_loads == [[], [], []], (
        f"{_BUMP}: a restart with DOGE held fails the stored account's load again, as 2.0.0rc6.dev20260921 did on the "
        f"code `XDG` -- read what the venue record then carries for the coin: {failed_loads}"
    )
    balances = [record["venue_state_at_start"]["balances"] for record in (first, second)]
    assert [b.get("DOGE") for b in balances] == [lot, lot] and not any("XDG" in b for b in balances), (
        f"{_BUMP}: the account no longer carries the coin as `DOGE`, and only as `DOGE`, at the lot after each restart "
        f"-- the venue record's balance for DOGE is read from it: {balances}"
    )

    held = ["trader-SHADOW-001:currencies:QQQZ", "trader-SHADOW-001:instruments:QQQZ/EUR.KRAKEN"]
    qqqz = [[key for key in keys if "QQQZ" in key] for keys in stored]
    assert qqqz == [held, held], (
        f"{_BUMP}: the store no longer holds the unregistered pair's currency and instrument before the two starts that "
        f"load them, so the burst below no longer reads a load that met them: {qqqz}"
    )

    # Any line naming the pair, not one build's wording: the load-failure wording moves between builds.
    burst = [_lines(record["log"], "QQQZ") for record in (bought, first, second)]
    assert burst == [[], [], []], (
        f"{_BUMP}: a pair whose base currency no process registers is now named by a start's log, as "
        f"2.0.0rc6.dev20260921's start-up ERROR burst named such pairs: {burst}"
    )


def _silent_listener() -> tuple[int, threading.Event]:
    """A TCP listener on 127.0.0.1 that accepts and never writes: a proxy up with no backend."""
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(64)
    stop = threading.Event()
    held: list = []

    def accept() -> None:
        server.settimeout(0.5)
        while not stop.is_set():
            try:
                held.append(server.accept()[0])
            except socket.timeout:
                continue
        for conn in held:
            conn.close()
        server.close()

    threading.Thread(target=accept, daemon=True).start()
    return server.getsockname()[1], stop


@pytest.mark.parametrize("shape", ["refused", "silent"])
def test_the_cache_unreachable_at_start_fails_inside_the_budget_without_touching_the_venue(tmp_path, shape):
    """No server runs in either shape, so no server version moves the budget these bounds hold."""
    port, stop = (1, None) if shape == "refused" else _silent_listener()
    node = _Node(tmp_path / "node", port)
    try:
        with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
            record = node.run(1, venue, data, exec_, window=PHASE1_WINDOW, valkey_port=port)
            private_calls = list(venue.private_calls)
    finally:
        if stop is not None:
            stop.set()
    assert record["errors"] == ["run raised RuntimeError: failed to create cache database backing"], record["errors"]
    assert "at_start" not in record  # no strategy started
    assert private_calls == [], private_calls
    bound = 20 if shape == "refused" else 90
    assert record["run_secs"] < bound, (shape, record["run_secs"])
    if shape == "silent":
        assert record["run_secs"] > 40, record["run_secs"]


def test_the_cache_killed_mid_run_leaves_the_engine_trading_and_the_store_behind(tmp_path):
    valkey = _Valkey(tmp_path / "valkey")
    node = _Node(tmp_path / "node", valkey.port)
    node.drop_plan("p-first")
    wire: dict = {}
    orders: list[str] = []
    # Set by the `finally` before it stops the server: the scripting thread starts no server after it.
    done = threading.Event()
    threads: list[threading.Thread] = []
    try:
        valkey.start()
        with _venue() as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000")}

            def on_add_order(form: dict, txid: str) -> None:
                orders.append(txid)
                n = len(orders)
                wire[txid] = form.get("cl_ord_id")
                opened_at = time.time()
                venue.open_orders[txid] = dict(
                    lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", opentm=opened_at), oflags="fciq"
                )

                def frames() -> None:
                    time.sleep(0.3)
                    if not exec_.subscribed.wait(30):
                        return
                    exec_.send_execution(lb.exec_new(txid, wire[txid], symbol=SYMBOL, qty=QTY, price=PRICE))
                    time.sleep(0.7)
                    filled_at = time.time()
                    exec_.send_execution(
                        lb.exec_trade(
                            txid, wire[txid], symbol=SYMBOL, qty=QTY, price=PRICE, last_qty=QTY, cum_qty=QTY,
                            exec_id=f"TLOOP{n}-AAAAA-AAAAAA", trade_id=1000 + n,
                        )
                    )  # fmt: skip
                    venue.open_orders.pop(txid, None)
                    closed = lb.closed_order(
                        PAIR,
                        price=f"{PRICE:.2f}",
                        volume=f"{QTY:.8f}",
                        status="closed",
                        vol_exec=f"{QTY:.8f}",
                        opentm=opened_at,
                        closetm=filled_at,
                    )
                    venue.closed_orders[txid] = dict(closed, oflags="fciq")
                    if n == 1:
                        time.sleep(2)
                        valkey.kill()
                        node.drop_plan("p-second")
                        if done.wait(12):
                            return
                        valkey.start()

                threads.append(threading.Thread(target=frames, daemon=True))
                threads[-1].start()

            venue.on_add_order = on_add_order
            record = node.run(1, venue, data, exec_, window=32)
        keys_at_return = _keys(valkey.port)
    finally:
        done.set()
        for thread in threads:
            thread.join(30)
        valkey.stop()

    assert record["errors"] == [], record["errors"]
    assert len(orders) == 2, orders
    fills = [(e["client_order_id"], e["last_qty"]) for e in record["own"] if e["type"] == "OrderFilled"]
    assert len(fills) == 2 and fills[0][0] != fills[1][0], fills
    rows = {row["client_order_id"]: row for row in node.rows()}
    assert {row["state"] for row in rows.values()} == {"filled"}, rows
    intents = [i["outcome"] for i in node.intents()]
    assert intents == ["filled", "filled"], intents
    log = record["log"]
    assert re.search(r"\[ERROR\] SHADOW-001\.nautilus_infrastructure::redis::cache: (broken pipe|Connection refused)", log), log[
        -3000:
    ]
    assert re.search(
        r"\[WARN\] SHADOW-001\.nautilus_infrastructure::redis::cache: Cannot update order in Redis, no existing state at", log
    ), log[-3000:]
    second = fills[1][0]
    assert f"trader-SHADOW-001:orders:{second}" not in keys_at_return, keys_at_return


# What reconciliation imported is in `at_start`, taken when the strategy starts, so no executor tick is waited for.
IMPORT_WINDOW = 1
HISTORY_TXID, HISTORY_TRADE = "OHIST1-AAAAA-BBBBBB", "THIST1-AAAAA-AAAAAA"


def _start_over_one_history_fill(node: _Node, phase: int, *, minutes_before: int) -> dict:
    """One start over a venue whose history is one spot buy of 0.5, closed filled `minutes_before` the
    child is launched, so at least that long before the start's own clock."""
    with _venue() as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        at = time.time() - minutes_before * 60
        closed = lb.closed_order(
            PAIR, price=f"{PRICE:.2f}", volume="0.50000000", status="closed", vol_exec="0.50000000", opentm=at, closetm=at
        )
        venue.closed_orders[HISTORY_TXID] = dict(closed, oflags="fciq", price=f"{PRICE:.5f}", cost=f"{0.5 * PRICE:.5f}")
        venue.trades[HISTORY_TRADE] = lb.spot_trade_row(
            HISTORY_TXID, PAIR, vol="0.50000000", price=f"{PRICE:.2f}", trade_id=2001, time=at
        )
        return node.run(phase, venue, data, exec_, window=IMPORT_WINDOW)


def test_a_start_imports_a_history_fill_from_719_minutes_before_it_and_nothing_of_the_same_fill_from_721(tmp_path):
    valkey = _Valkey(tmp_path / "valkey")
    try:
        valkey.start()
        node = _Node(tmp_path / "node", valkey.port)
        outside = _start_over_one_history_fill(node, 1, minutes_before=721)
        valkey.kill()
        valkey.start()
        inside = _start_over_one_history_fill(node, 2, minutes_before=719)
    finally:
        valkey.stop()

    for record in (outside, inside):
        assert record["errors"] == [], record["errors"]
        assert _restore_lines(record["log"]) == ["0 order(s), 0 position(s) restored"]
    assert (outside["at_start"]["orders"], outside["at_start"]["positions"]) == ([], [])
    [order] = inside["at_start"]["orders"]
    assert (order["venue_order_id"], order["strategy_id"], order["status"], order["filled_qty"], order["trade_ids"]) == (
        HISTORY_TXID,
        "EXTERNAL",
        "FILLED",
        "0.50000000",
        [HISTORY_TRADE],
    )


HAND_TXID, HAND_TRADE = "OHAND1-AAAAA-BBBBBB", "THAND1-AAAAA-AAAAAA"


def _script_hand_buy(venue: lb.KrakenLoopback, exec_: lb.WsPeer) -> None:
    """A buy of 0.5 no plan placed, filling whole while the node runs: neither frame carries a client order id."""

    def later() -> None:
        if not exec_.subscribed.wait(60):
            return
        time.sleep(8)  # past the startup pass
        opened_at = time.time()
        exec_.send_execution(lb.exec_new(HAND_TXID, None, symbol=SYMBOL, qty=0.5, price=PRICE))
        time.sleep(0.5)
        exec_.send_execution(
            lb.exec_trade(
                HAND_TXID, None, symbol=SYMBOL, qty=0.5, price=PRICE, last_qty=0.5, cum_qty=0.5, exec_id=HAND_TRADE, trade_id=7001,
            )
        )  # fmt: skip
        filled_at = time.time()
        closed = lb.closed_order(
            PAIR,
            price=f"{PRICE:.2f}",
            volume="0.50000000",
            status="closed",
            vol_exec="0.50000000",
            opentm=opened_at,
            closetm=filled_at,
        )
        venue.closed_orders[HAND_TXID] = dict(closed, oflags="fciq", price=f"{PRICE:.5f}", cost=f"{0.5 * PRICE:.5f}")
        venue.trades[HAND_TRADE] = lb.spot_trade_row(
            HAND_TXID, PAIR, vol="0.50000000", price=f"{PRICE:.2f}", trade_id=7001, time=filled_at
        )
        venue.balances["SOL"] = lb.balance("0.50000000")

    threading.Thread(target=later, daemon=True).start()


def test_a_position_the_library_booked_is_counted_and_a_hand_orders_is_not(tmp_path):
    # No order or trade behind the row: with its fill in the history a start imports that order as `VENUE` and mints nothing.
    row = dict(lb.margin_position(PAIR, volume="0.50000000", time=time.time()), ordertxid=HAND_TXID, cost="75.00000")
    starts = []
    valkey = _Valkey(tmp_path / "leveraged" / "valkey")
    try:
        valkey.start()
        node = _Node(tmp_path / "leveraged" / "node", valkey.port)
        for phase in (1, 2):
            with _venue() as (venue, data, exec_):
                venue.balances = {"ZEUR": lb.balance("1000.00000000")}
                venue.positions["THANDP-AAAAA-BBBBBB"] = row
                starts.append(node.run(phase, venue, data, exec_, window=PHASE2_WINDOW))
    finally:
        valkey.stop()

    tagged = []
    for record in starts:
        assert record["errors"] == [], record["errors"]
        held = [p for p in record["at_start"]["positions"] if p["is_open"]]
        assert [(p["id"], p["strategy_id"], p["signed_qty"]) for p in held] == [(f"{INSTRUMENT}-EXTERNAL", "EXTERNAL", "0.5")], (
            f"{_BUMP}: a leveraged row the Cache does not hold no longer comes back from a start as one position under `EXTERNAL`: {held}"
        )
        tagged.append([cid for cid, tags in held[0]["order_tags"].items() if "RECONCILIATION" in (tags or [])])
        counts = record["metrics"]["reconciliation_positions"]
        assert counts == [1], (
            f"{_BUMP}: the count the page reads no longer reads that position once, at the cold start and again out of the "
            f"store at the next, where a lost tag would quiet the page at the one start it exists for: {counts}, {held}"
        )
        warnings = [line.split(" - ", 1)[1] for line in _lines(record["log"], "reconciliation minted") if " WARNING " in line]
        assert warnings == [
            f"position {INSTRUMENT}-EXTERNAL under EXTERNAL, 0.5, holds an order nautilus's reconciliation minted, {tagged[-1]} "
            "-- see infra/runbooks/engine.md#zcrypto-engine-reconciliation-position"
        ], f"{_BUMP}: the WARNING no longer names that position's id, strategy, quantity and tagged order: {warnings}"
    assert len(tagged[0]) == 1 and tagged[0] == tagged[1], (
        f"{_BUMP}: the one order the first start minted no longer carries `RECONCILIATION`, or the next start no longer "
        f"reads it back from the store: {tagged}"
    )

    valkey = _Valkey(tmp_path / "hand" / "valkey")
    try:
        valkey.start()
        node = _Node(tmp_path / "hand" / "node", valkey.port)
        with _venue() as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000")}
            _script_hand_buy(venue, exec_)
            live = node.run(1, venue, data, exec_, window=PHASE2_WINDOW)
            holdings = venue.holdings()
        with _venue() as (venue, data, exec_):
            venue.hold(holdings)
            restart = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
    finally:
        valkey.stop()

    assert live["errors"] == [] and restart["errors"] == [], (live["errors"], restart["errors"])
    held = [
        (p["id"], p["strategy_id"], p["signed_qty"], list(p["order_tags"]))
        for p in restart["at_start"]["positions"]
        if p["is_open"]
    ]
    assert (_open_positions(live["at_end"]), held) == (
        [("EXTERNAL", "0.5")],
        [(f"{INSTRUMENT}-EXTERNAL", "EXTERNAL", "0.5", [HAND_TXID])],
    ), (
        f"{_BUMP}: a hand order's fill seen live no longer comes back from a restart as a position under `EXTERNAL` "
        f"holding that order: {_open_positions(live['at_end'])}, {held}"
    )
    orders = [order["client_order_id"] for order in restart["at_start"]["orders"]]
    assert HAND_TXID in orders, (
        f"{_BUMP}: a hand order's fill seen live no longer comes back from a restart with the order in the store, "
        f"so the 0 below would not read its tags: {orders}"
    )
    _reads_nothing(restart)


CLOSE_TXID, CLOSE_TRADE = "OCLOSE-AAAAA-BBBBBB", "TCLOSE-AAAAA-AAAAAA"


def test_a_close_the_first_start_missed_across_two_starts(tmp_path):
    valkey = _Valkey(tmp_path / "valkey")
    try:
        node, wire, _ = _phase_one(valkey, tmp_path)
        closed_at = time.time()

        def held(venue: lb.KrakenLoopback) -> None:
            venue.balances = {"ZEUR": lb.balance("1000.00000000")}
            canceled = lb.closed_order(
                PAIR,
                price=f"{PRICE:.2f}",
                volume=f"{QTY:.8f}",
                status="canceled",
                vol_exec="0.40000000",
                opentm=wire["opened_at"],
                closetm=wire["stopped_at"],
            )
            venue.closed_orders[wire["txid"]] = dict(canceled, oflags="fciq")
            venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(
                wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001, time=wire["filled_at"]
            )
            # A part-close in Kraken's row shape: a pair left with no row is compared with nothing, and mints nothing.
            venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
                lb.margin_position(PAIR, volume="0.40000000", time=wire["filled_at"]),
                vol_closed="0.15000000",
                ordertxid=wire["txid"],
                cost="60.00000",
            )

        with _venue() as (venue, data, exec_):
            held(venue)
            first = node.run(2, venue, data, exec_, window=PHASE1_WINDOW)
        with _venue() as (venue, data, exec_):
            held(venue)
            closing = lb.closed_order(
                PAIR, price=f"{PRICE:.2f}", volume="0.15000000", side="sell", status="closed", vol_exec="0.15000000", opentm=closed_at, closetm=closed_at
            )  # fmt: skip
            venue.closed_orders[CLOSE_TXID] = dict(closing, oflags="fciq", price=f"{PRICE:.5f}", cost=f"{0.15 * PRICE:.5f}")
            venue.trades[CLOSE_TRADE] = dict(
                lb.trade_row(CLOSE_TXID, PAIR, vol="0.15000000", price="150.00", trade_id=1009, side="sell", time=closed_at),
                posstatus="closed",
            )
            second = node.run(3, venue, data, exec_, window=PHASE1_WINDOW)
    finally:
        valkey.stop()

    completes = [
        [line.split("KRAKEN: ", 1)[1] for line in _lines(record["log"], "Reconciliation complete")] for record in (first, second)
    ]
    assert first["errors"] == [] and second["errors"] == [], (first["errors"], second["errors"])
    assert completes == [
        ["reconciled=1, external=0, open=0, fills=0, positions=1, skipped=0, filtered=0"],
        ["reconciled=0, external=1, open=0, fills=1, positions=0, skipped=0, filtered=0"],
    ], (
        f"{_BUMP}: the first start no longer books the close it missed as one position difference, or the second no longer "
        f"takes the closing order and its fill with no second difference: {completes}"
    )

    [minted] = [p for p in first["at_start"]["positions"] if p["strategy_id"] == "EXTERNAL"]
    tags = list(minted["order_tags"].values())
    assert (minted["signed_qty"], tags, closed_at * 1e9 < minted["ts_opened"]) == ("-0.15", [["RECONCILIATION"]], True), (
        f"{_BUMP}: the first start no longer books the gap as one `RECONCILIATION` order under `EXTERNAL`, opened after the "
        f"close it missed, so the second start below no longer holds the fill older than that position: {minted}, {closed_at}"
    )

    counts = [record["metrics"]["reconciliation_positions"] for record in (first, second)]
    assert counts == [[1], [1]], (
        f"{_BUMP}: the count the page reads no longer stands at 1 across both starts of the route it exists for: {counts}"
    )

    held_at_end = second["at_end"]
    [closing_order] = [order for order in held_at_end["orders"] if order["client_order_id"] == CLOSE_TXID]
    assert (
        closing_order["strategy_id"],
        closing_order["status"],
        closing_order["filled_qty"],
        closing_order["trade_ids"],
        closing_order["tags"],
    ) == ("EXTERNAL", "FILLED", "0.15000000", [CLOSE_TRADE], ["VENUE"]), (
        f"{_BUMP}: the closing fill no longer lands on its order, imported under `EXTERNAL` with `VENUE`: {closing_order}"
    )
    reached = [p["id"] for p in held_at_end["positions"] if CLOSE_TRADE in p["trade_ids"]]
    assert reached == [], (
        f"{_BUMP}: the closing fill older than the minted position now reaches a position, where it went to the order "
        f"alone. A later fill reaches the minted position and a second mint puts the quantity back, so read the "
        f"`trade_ids`, not the quantity: {reached}"
    )

    assert _open_positions(held_at_end) == [("EXTERNAL", "-0.15"), ("ShadowStrategy-000", "0.4")], (
        f"{_BUMP}: the engine's own position no longer stands at the 0.4 Kraken no longer holds, beside the minted offset, "
        f"after the second start: {_open_positions(held_at_end)}"
    )
    netted = [record["venue_state_at_start"]["positions"][SYMBOL] for record in (first, second)]
    assert netted == [0.25, 0.25], (
        f"{_BUMP}: the venue record no longer nets the own position and the offset to Kraken's 0.25, the figure sizing reads: {netted}"
    )

    said = {
        "venue_holds": _lines(second["log"], "the venue holds"),
        "order_state_only": _lines(second["log"], "to order state only"),
        "the_order_above_info": [line for line in _lines(second["log"], CLOSE_TXID) if "[INFO]" not in line],
        "the_trade_above_info": [line for line in _lines(second["log"], CLOSE_TRADE) if "[INFO]" not in line],
    }
    assert said == {"venue_holds": [], "order_state_only": [], "the_order_above_info": [], "the_trade_above_info": []}, (
        f"{_BUMP}: a line now says the closing fill went to the order alone, where the second start said nothing above INFO "
        f"-- read it, and whether the page's runbook can now name this route: {said}"
    )
