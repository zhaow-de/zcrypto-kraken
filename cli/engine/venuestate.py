"""The frozen venue-truth snapshot and its Cache reader (spec 00089 D3): the ONE module in this spec that
touches Nautilus types -- everything downstream (the journaled artifact, the strategy hook) consumes plain
`VenueState` data. Nothing here mutates the Cache or places an order, and `positions` values are signed net
quantities (negative for SHORT, `0.0` when flat).

Two-layer failure design, deliberate:

- `venue_state_from_cache` raises `EngineError` on a STRUCTURAL read failure only -- an `INSTRUMENT_IDS`
symbol absent from the Cache, the Cache's own instrument disagreeing with the expected `InstrumentId` (a
venue-truth divergence in its own right, never narrowed silently), or no account cached for the venue. The
caller (the strategy hook) converts the raise to `None` and the cycle proceeds without venue truth (00089
D7): absence is loud, never blocking.
- A present instrument's Cache-supplied numeric constraint
(`ordermin`/`lot_step`/`tick_size`) that reads back `None` does NOT raise here -- it freezes as `0.0`,
where no listing floor stands over it, for `runtime_concordance` to flag per leg, so one broken leg degrades
to a per-symbol concordance failure instead of discarding the whole snapshot.

`costmin` is NOT Cache-supplied at all (spec 00089 D5a): the Kraken adapter never maps it into `min_notional` --
it reads back `None` for every pair -- and Kraken's costmin is not one venue constant either, so it is read from
the committed `cli.engine.instruments.COSTMIN`, labelled `"costmin_source": "snapshot-constant"` in `to_payload()`,
and left to `tests/test_costmin_drift.py`; `runtime_concordance` deliberately never checks it."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime

from nautilus_trader.model import InstrumentId, Venue

from cli.engine.errors import EngineError
from cli.engine.instruments import COSTMIN, INSTRUMENT_IDS

_VENUE = Venue("KRAKEN")


@dataclass(frozen=True)
class InstrumentConstraints:
    """One symbol's venue-quoted order constraints, evidence -- not live-precision, hence float.
    `lot_step`/`tick_size` are the Cache's and `ordermin` is `held_ordermin`'s; `costmin` is neither
    (module docstring, D5a) -- it comes from the committed `COSTMIN` constant, and `costmin_quote` (spec
    00094 D4) is that same `COSTMIN` entry's quote currency, so no consumer can compare `costmin`
    against a notional denominated in the wrong currency without noticing."""

    symbol: str
    instrument_id: str
    ordermin: float
    costmin: float
    costmin_quote: str
    lot_step: float
    tick_size: float


@dataclass(frozen=True)
class VenueState:
    """A frozen, single-instant read of the Cache, with each `ordermin` as `held_ordermin` holds it:
    what the venue said we could trade, held, and had free to spend at `snapshot_at`. Plain data --
    no Nautilus type reachable from here."""

    snapshot_at: datetime
    instruments: dict[str, InstrumentConstraints]
    positions: dict[str, float]
    balances: dict[str, float]

    def to_payload(self) -> dict:
        """JSON-ready; each instrument entry carries `costmin_source` (D5a) so no reader mistakes a committed
        constant for something the venue said this cycle."""
        return {
            "snapshot_at": self.snapshot_at.isoformat(),
            "instruments": {symbol: {**asdict(c), "costmin_source": "snapshot-constant"} for symbol, c in self.instruments.items()},
            "positions": dict(self.positions),
            "balances": dict(self.balances),
        }


@dataclass(frozen=True)
class ConcordanceVerdict:
    """`runtime_concordance`'s verdict: `ok` iff `failures` is empty."""

    ok: bool
    failures: tuple[str, ...]


def _to_float(value: object) -> float:
    return 0.0 if value is None else float(value)


def held_ordermin(cached: object, listed: float | None) -> float:
    """The floor a quantity is held against: the venue listing's, never under the Cache's, so a floor the venue
    raised holds from the next book read and one it lowered from the next start (spec 00156 D2)."""
    floor = _to_float(cached)
    return floor if listed is None else max(floor, listed)


def venue_state_from_cache(cache, *, clock: Callable[[], datetime], listed: Mapping[str, float] | None = None) -> VenueState:
    """Raises `EngineError` on a structural read failure, each named in the message (module docstring). `listed` is
    the newest venue book's floors, and `held_ordermin` decides each leg's."""
    listed = {} if listed is None else listed
    instruments: dict[str, InstrumentConstraints] = {}
    positions: dict[str, float] = {}
    for symbol, instrument_id_str in INSTRUMENT_IDS.items():
        instrument_id = InstrumentId.from_str(instrument_id_str)
        instrument = cache.instrument(instrument_id)
        if instrument is None:
            raise EngineError(f"{symbol}: instrument not found in Cache")
        if str(instrument.id) != instrument_id_str:
            raise EngineError(
                f"{symbol}: Cache instrument id {instrument.id!s} disagrees with the expected "
                f"{instrument_id_str!r} -- a venue-truth divergence, not a benign rename"
            )
        instruments[symbol] = InstrumentConstraints(
            symbol=symbol,
            instrument_id=str(instrument.id),
            ordermin=held_ordermin(instrument.min_quantity, listed.get(symbol)),
            costmin=COSTMIN[symbol][0],
            costmin_quote=COSTMIN[symbol][1],
            lot_step=_to_float(instrument.size_increment),
            tick_size=_to_float(instrument.price_increment),
        )
        open_positions = cache.positions_open(instrument_id=instrument_id)
        positions[symbol] = sum(float(p.signed_qty) for p in open_positions)

    account = cache.account_for_venue(venue=_VENUE)
    if account is None:
        raise EngineError(f"no account cached for venue {_VENUE}")
    balances = {currency.code: float(money) for currency, money in account.balances_free().items()}

    return VenueState(snapshot_at=clock(), instruments=instruments, positions=positions, balances=balances)


def runtime_concordance(state: VenueState) -> ConcordanceVerdict:
    """Per `INSTRUMENT_IDS` symbol (never `state.instruments`, so a hand-built state missing a
    symbol is caught too): the instrument is present, and its three **venue-supplied**
    `ordermin`/`lot_step`/`tick_size` are all `> 0`. `costmin` is deliberately NOT checked here
    (D5a): it is snapshot-sourced, not venue-read, so its correctness is
    `tests/test_costmin_drift.py`'s job -- checking it here would fail all twelve legs on the first
    cycle and hold the concordance alert red forever (the T0135 failure D2 exists to avoid).
    Failure strings are `"SYMBOL: <what>"`."""
    failures: list[str] = []
    for base in INSTRUMENT_IDS:
        constraints = state.instruments.get(base)
        if constraints is None:
            failures.append(f"{base}: instrument not present in snapshot")
            continue
        for field_name in ("ordermin", "lot_step", "tick_size"):
            value = getattr(constraints, field_name)
            if not value > 0:
                failures.append(f"{base}: {field_name} is {value}, not > 0")
    return ConcordanceVerdict(ok=not failures, failures=tuple(failures))


RECONCILIATION_TAG = "RECONCILIATION"


def reconciliation_tagged_orders(cache, position) -> list:
    """The ids of the orders of `position` the library minted to book a difference it could not explain (spec 00157 D1): any
    order of the position, since a later mismatch tags an order on a position whose opener carries none."""
    return [cid for cid in position.client_order_ids() if RECONCILIATION_TAG in ((order := cache.order(cid)) and order.tags or [])]


def reconciliation_booked_positions(cache) -> list:
    return [position for position in cache.positions_open() if reconciliation_tagged_orders(cache, position)]
