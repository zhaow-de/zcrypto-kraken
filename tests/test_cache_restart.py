"""The two-process restart harness: the engine's own node, restarted against a real `valkey-server`
this file starts, with the venue a loopback the file scripts.

No environment gate, on purpose: a database is not a venue, and a skip on a missing binary would
read as coverage. `valkey-server` is found on PATH and named, and its absence fails with the
install command. In CI the binary comes from apt (`.github/workflows/coverage.yml`); locally it is
the workstation's own, 8.1.1 at the time of writing where the fleet runs 9.1.2, so a reading that
could differ there is named where it is asserted. Every node runs in a child interpreter
(`tests/cache_restart_child.py`) under a timeout, and reaches nothing past 127.0.0.1.
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
    """A `valkey-server` on a free port under `root`, no persistence, the ACL file carrying the role's
    engine line and an admin user for the harness's own reads."""

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
    """The driver's side of one child node: its state directory, the ledger rows and intents read back
    from it, and the child's records."""

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

    def drop_plan(self, plan_id: str, *, leverage: int | None = 2, notional_eur: float = PRICE * QTY) -> None:
        intent = {"symbol": SYMBOL, "side": "buy", "action": "open", "mode": "execute", "notional_eur": notional_eur}
        if leverage is not None:
            intent["leverage"] = leverage
        plan = {"plan_id": plan_id, "created_at": datetime.now(timezone.utc).isoformat(), "intents": [intent]}
        (exec_dir(self.state) / PLAN_FILENAME).write_text(json.dumps(plan))

    def run(
        self, phase: int, venue: lb.KrakenLoopback, data: lb.WsPeer, exec_: lb.WsPeer, *, window: int, valkey_port=None
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
            "instrument": INSTRUMENT,
            "bid": f"{PRICE:.2f}",
            "ask": f"{PRICE + 0.1:.2f}",
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
    """The venue's side of one order: the open-orders row at the AddOrder, then the `new` and, when
    `fill`, the `trade` frame on the private socket and the listings the fill moves -- the open row's
    `vol_exec`, the trade history and the margin position."""

    def on_add_order(form: dict, txid: str) -> None:
        wire.update(txid=txid, cl_ord_id=form.get("cl_ord_id"))
        venue.open_orders[txid] = dict(lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"), oflags="fciq")

        def frames() -> None:
            time.sleep(0.3)
            if not exec_.subscribed.wait(30):
                return
            exec_.send_execution(lb.exec_new(txid, wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE))
            if not fill:
                return
            time.sleep(0.7)
            exec_.send_execution(
                lb.exec_trade(
                    txid, wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE, last_qty=last_qty, cum_qty=last_qty,
                    exec_id="TLOOP1-AAAAA-AAAAAA", trade_id=1001,
                )
            )  # fmt: skip
            venue.open_orders[txid].update(vol_exec=f"{last_qty:.8f}", price=f"{PRICE:.5f}", cost=f"{last_qty * PRICE:.5f}")
            venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(
                txid, PAIR, vol=f"{last_qty:.8f}", price=f"{PRICE:.2f}", trade_id=1001
            )
            venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
                lb.margin_position(PAIR, volume=f"{last_qty:.8f}"), ordertxid=txid, cost=f"{last_qty * PRICE:.5f}"
            )

        threading.Thread(target=frames, daemon=True).start()

    venue.on_add_order = on_add_order


def _script_cancel_ack(venue: lb.KrakenLoopback, exec_: lb.WsPeer, wire: dict) -> None:
    """The venue's answer to a cancel: the order leaves the open listing for the closed one, and the
    private socket sends the `canceled` frame at the venue's cumulative fill."""

    def on_cancel_order(form: dict) -> None:
        txid = wire["txid"]
        row = venue.open_orders.pop(txid, None)
        cum = float(row["vol_exec"]) if row else 0.0
        venue.closed_orders[txid] = dict(
            lb.closed_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", status="canceled", vol_exec=f"{cum:.8f}"),
            oflags="fciq",
        )

        def frame() -> None:
            time.sleep(0.3)
            exec_.send_execution(lb.exec_canceled(txid, wire["cl_ord_id"], symbol=SYMBOL, qty=QTY, price=PRICE, cum_qty=cum))

        threading.Thread(target=frame, daemon=True).start()

    venue.on_cancel_order = on_cancel_order


def _basket_pairs() -> dict:
    return json.loads(BASKET_FIXTURE.read_text())


def _restore_lines(log: str) -> list[str]:
    return [line.split("cache restore: ", 1)[1] for line in log.splitlines() if "cache restore: " in line]


def _phase_one(valkey: _Valkey, tmp_path: Path) -> tuple[_Node, dict, dict]:
    """A node that placed one leveraged order, filled 0.4 of 1.0, and stopped with it resting: the
    store holds the order, the fill and the margin position, and the venue lists all three."""
    valkey.start()
    node = _Node(tmp_path / "node", valkey.port)
    node.drop_plan("p-phase-1")
    wire: dict = {}
    with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        _script_first_fill(venue, exec_, wire=wire)
        record = node.run(1, venue, data, exec_, window=PHASE1_WINDOW)
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
    """The restore of both identities and the boot line: the restarted node holds the order under
    its own client order id and strategy, matched by venue order id, the position at its entry
    price, and the boot line says so; no `Unresolved positions` line, the failure the operating
    rule stands against."""
    valkey, node, wire, _ = phase_one
    with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.open_orders[wire["txid"]] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"),
            oflags="fciq",
            vol_exec="0.40000000",
            price="150.00000",
            cost="60.00000",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001)
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.40000000"), ordertxid=wire["txid"], cost="60.00000"
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
    assert (position["instrument_id"], position["strategy_id"], position["signed_qty"], position["avg_px_open"]) == (
        INSTRUMENT,
        "ShadowStrategy-000",
        0.4,
        150.0,
    )
    assert _restore_lines(record["log"]) == [
        "1 order(s), 1 position(s) restored",
        "position SOL/EUR.KRAKEN 0.4 @ 150.0 (ShadowStrategy-000)",
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


def test_a_fill_made_while_the_engine_was_down_is_booked_from_the_trade_history(phase_one):
    valkey, node, wire, _ = phase_one
    with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.open_orders[wire["txid"]] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"),
            oflags="fciq",
            vol_exec="0.70000000",
            price="150.00000",
            cost="105.00000",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001)
        venue.trades["TLOOP2-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.30000000", price="150.00", trade_id=1002)
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.70000000"), ordertxid=wire["txid"], cost="105.00000"
        )
        _script_cancel_ack(venue, exec_, wire)
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)

    assert record["errors"] == [], record["errors"]
    assert "Unresolved positions" not in record["log"]
    # The library books the missed fill onto the restored order, keeps the restored position at its
    # stored quantity, and closes the gap to the venue's position with a synthesized EXTERNAL order
    # and position, which the boot line lists beside the restored one.
    orders = {o["strategy_id"]: o for o in record["at_start"]["orders"]}
    positions = {p["strategy_id"]: p for p in record["at_start"]["positions"]}
    assert (orders[record["strategy_id"]]["filled_qty"], orders[record["strategy_id"]]["status"]) == ("0.70000000", "ACCEPTED")
    assert {(p["signed_qty"], p["avg_px_open"]) for p in positions.values()} == {(0.4, 150.0), (0.3, 150.0)}
    assert positions["EXTERNAL"]["signed_qty"] == 0.3
    assert {tuple(p) for p in record["metrics"]["positions"] if p[0] == "SOL/EUR"} == {("SOL/EUR", 0.7)}
    assert _restore_lines(record["log"]) == [
        "1 order(s), 2 position(s) restored",
        "position SOL/EUR.KRAKEN 0.3 @ 150.0 (EXTERNAL)",
        "position SOL/EUR.KRAKEN 0.4 @ 150.0 (ShadowStrategy-000)",
        f"order {wire['client_order_id']} partial, 0.70000000 of 1.00000000 filled @ 150.00",
    ]
    # The executor: the venue's report repairs the row to the venue's figure before the pass's cancel.
    label = f"{wire['client_order_id']} (Kraken {wire['txid']})"
    assert f"adopted order {label} reconciled against the venue: 0.7 filled there against the 0.4 recorded here" in record["log"]
    [row] = node.rows()
    assert (row["filled_qty"], row["state"]) == (0.7, "canceled")
    assert [e["qty"] for e in row["events"] if e.get("event") == "reconciled"] == [pytest.approx(0.3)]


def test_an_order_cancelled_while_the_engine_was_down_is_never_closed_by_the_library(phase_one):
    """Mass status reads open orders only on this pin and ClosedOrders is never requested, so the
    restored copy stays open in the Cache for the process's life -- the shape the startup pass
    settles from the venue's report."""
    valkey, node, wire, _ = phase_one
    with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.closed_orders[wire["txid"]] = dict(
            lb.closed_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", status="canceled", vol_exec="0.40000000"),
            oflags="fciq",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001)
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.40000000"), ordertxid=wire["txid"], cost="60.00000"
        )
        record = node.run(2, venue, data, exec_, window=PHASE2_WINDOW)
        private_calls = list(venue.private_calls)

    assert record["errors"] == [], record["errors"]
    assert "OpenPositions" in private_calls, private_calls
    assert "ClosedOrders" not in private_calls[: private_calls.index("OpenPositions") + 1], private_calls
    [order] = record["at_start"]["orders"]
    assert (order["is_open"], order["filled_qty"]) == (True, "0.40000000")
    assert _restore_lines(record["log"])[0] == "1 order(s), 1 position(s) restored"
    # The executor: the row written from the venue's report, the stale copy left, no cancel sent.
    assert "ClosedOrders" in private_calls and "CancelOrder" not in private_calls, private_calls
    assert (
        f"restored order {wire['client_order_id']} is canceled at the venue -- its stale open copy stays in the Cache and no cancel is sent"
        in record["log"]
    )
    [row] = node.rows()
    [intent] = node.intents()
    assert (row["state"], row["filled_qty"], intent["outcome"]) == ("canceled", 0.4, "revoked")


def test_a_trade_frame_on_a_restored_open_order_is_booked_twice_by_the_library(phase_one):
    """The measured double booking: a `trade` frame on a restored order is booked as an inferred fill
    for the cumulative gap and then as the fill itself, so the Cache's copy reads 0.8 where the
    venue said 0.6. The row is the previous process's reducer, which the startup pass keeps, so the
    order is still open when the frame lands."""
    valkey, node, wire, _ = phase_one
    node.mark_row_reducer(wire["client_order_id"])
    with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.open_orders[wire["txid"]] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"),
            oflags="fciq",
            vol_exec="0.40000000",
            price="150.00000",
            cost="60.00000",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001)
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.40000000"), ordertxid=wire["txid"], cost="60.00000"
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
            venue.trades["TLOOP3-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.20000000", price="150.00", trade_id=1003)

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
    with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
        venue.balances = {"ZEUR": lb.balance("1000.00000000")}
        venue.open_orders[wire["txid"]] = dict(
            lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"),
            oflags="fciq",
            vol_exec="0.40000000",
            price="150.00000",
            cost="60.00000",
        )
        venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001)
        venue.positions["TPOSLP-AAAAA-BBBBBB"] = dict(
            lb.margin_position(PAIR, volume="0.40000000"), ordertxid=wire["txid"], cost="60.00000"
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
            venue.trades["TLOOP3-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.20000000", price="150.00", trade_id=1003)
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
    stop: the library creates the EXTERNAL copy from the venue's report at ACCEPTED with no fill
    applied, and the venue's own report, 0.4, answers for the copy as for every order the Cache holds
    at construction -- no trip. The restarted node reads zero, reconciliation names the order by its
    txid under EXTERNAL, the pass cancels it as an order the ledger carries as no reducer, and the
    fill the library infers at the cancel's ack credits the row nothing, a restored row's credit."""
    valkey = _Valkey(tmp_path / "valkey")
    try:
        valkey.start()
        node = _Node(tmp_path / "node", valkey.port)
        node.drop_plan("p-spot", leverage=None)
        wire: dict = {}
        with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
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
        with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000"), "SOL": lb.balance("0.40000000")}
            venue.open_orders[wire["txid"]] = dict(
                lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"),
                oflags="fciq",
                vol_exec="0.40000000",
                price="150.00000",
                cost="60.00000",
            )
            venue.trades["TLOOP1-AAAAA-AAAAAA"] = lb.trade_row(wire["txid"], PAIR, vol="0.40000000", price="150.00", trade_id=1001)
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
        external["is_open"],
    ) == (
        wire["txid"],
        "EXTERNAL",
        wire["txid"],
        "ACCEPTED",
        True,
    )
    assert "execution kill switch tripped" not in record["log"]
    # The EXTERNAL copy reads 0 filled; the venue's report, 0.4, answers for it as for every order the
    # Cache holds at construction, so the withdrawal check reads no shortfall and the trade history is
    # not consulted -- the check's second source is the copy's, without the cache or under a failed
    # order read, and the executor file's cold-start cases pin it there.
    assert "reads 0 filled on its order figure" not in record["log"]
    assert f"canceling adopted resting order {wire['txid']} -- the ledger does not carry it as a resting reducer" in record["log"]
    assert [form.get("txid") for form in cancels] == [wire["txid"]]
    assert [e["client_order_id"] for e in record["external"]][:1] == [wire["txid"]]
    # The fill the library infers at the cancel's ack, 0.4 again, credits the row nothing, a restored
    # row's credit; the row settles at the venue's 0.4, canceled by the pass.
    [row] = node.rows()
    fills = [e for e in row["events"] if e.get("event") == "fill"]
    assert [(e["qty"], e.get("credited")) for e in fills] == [(0.4, None), (0.4, 0.0)], fills
    assert (row["filled_qty"], row["state"]) == (0.4, "canceled")
    [intent] = node.intents()
    assert intent["outcome"] == "revoked"


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
    """Ten retries under five-second timeouts: a port nothing listens on refuses the start in seconds,
    a peer that accepts and never answers in about 55 s, both inside the inter-cycle gap and this
    harness's timeout, and neither reaches the venue -- `run()` creates the backing before any
    client connects. The budget is the pinned nautilus wheel's Redis client's, its retries and
    timeouts the node's own: no server runs in either shape, so no server version moves it."""
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
    """The store dies under a running node: the first plan's order fills whole, the server is killed,
    a second plan is dropped and its order is placed, acknowledged and filled with the server down,
    every failed write logged at ERROR under `nautilus_infrastructure::redis::cache` and every event
    on the lost order's key at WARN; the server returns empty, the link comes back lazily on the next
    write, and at the return the store holds neither the second order nor its fill."""
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
        with lb.serve_with_sockets(_basket_pairs()) as (venue, data, exec_):
            venue.balances = {"ZEUR": lb.balance("1000.00000000")}

            def on_add_order(form: dict, txid: str) -> None:
                orders.append(txid)
                n = len(orders)
                wire[txid] = form.get("cl_ord_id")
                venue.open_orders[txid] = dict(lb.open_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}"), oflags="fciq")

                def frames() -> None:
                    time.sleep(0.3)
                    if not exec_.subscribed.wait(30):
                        return
                    exec_.send_execution(lb.exec_new(txid, wire[txid], symbol=SYMBOL, qty=QTY, price=PRICE))
                    time.sleep(0.7)
                    exec_.send_execution(
                        lb.exec_trade(
                            txid, wire[txid], symbol=SYMBOL, qty=QTY, price=PRICE, last_qty=QTY, cum_qty=QTY,
                            exec_id=f"TLOOP{n}-AAAAA-AAAAAA", trade_id=1000 + n,
                        )
                    )  # fmt: skip
                    venue.open_orders.pop(txid, None)
                    venue.closed_orders[txid] = dict(
                        lb.closed_order(PAIR, price=f"{PRICE:.2f}", volume=f"{QTY:.8f}", status="closed", vol_exec=f"{QTY:.8f}"),
                        oflags="fciq",
                    )
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
