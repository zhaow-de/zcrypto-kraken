"""The frozen venue-truth snapshot and its Cache reader (spec 00089 D3): the ONE module in this
spec that touches Nautilus types -- everything downstream (the journaled artifact, the strategy
hook) consumes plain `VenueState` data. `venue_state_from_cache` reads the Cache once and freezes
it; nothing here mutates the Cache or places an order.

Two-layer failure design, deliberate:

- `venue_state_from_cache` raises `EngineError` on a STRUCTURAL read failure only -- an
  `INSTRUMENT_IDS` symbol entirely absent from the Cache, the Cache's own instrument disagreeing
  with the expected `InstrumentId` (a venue-truth divergence in its own right, never narrowed
  silently), or no account cached for the venue. Those mean the snapshot as a whole cannot be
  trusted, so the caller (the strategy hook) converts the raise to `None` and the cycle
  proceeds without venue truth (00089 D7): absence is loud, never blocking.
- A present instrument's Cache-supplied numeric constraint (`ordermin`/`lot_step`/`tick_size`)
  that reads back `None` does NOT raise here -- it freezes as `0.0` and is left for
  `runtime_concordance` to flag per leg, so one broken leg degrades to a per-symbol concordance
  failure instead of discarding the whole snapshot (positions and balances on the other eleven
  legs stay evidence).

`costmin` is NOT Cache-supplied at all (spec 00089 D5a, measured): probed against the
nautilus-trader 1.230.0 Kraken adapter (`KrakenSpotHttpClient.request_instruments`,
loopback-served canned `AssetPairs`), the compiled Rust parser reads `ordermin`/`tick_size` into
`min_quantity`/`price_increment` correctly but never maps `costmin` into `min_notional` -- it
comes back `None` for every pair, always, on this adapter version. Kraken's costmin is also not a
single venue constant (0.5 / 0.45 / 0.00002 depending on the pair), so it can't be hardcoded as
one number either. It is instead read from the committed `cli.engine.instruments.COSTMIN`
constant, labelled `"costmin_source": "snapshot-constant"` in `to_payload()` so no future
reader mistakes it for something the venue said this cycle, and its correctness is
`tests/test_costmin_drift.py`'s job -- `runtime_concordance` deliberately never checks it (a
constant that failed all twelve legs on the first cycle would hold D6's alert red forever, the
exact T0135 failure D2 exists to avoid).

Instrument attribute names and the Position/Account surfaces are probe-confirmed, not guessed
(measured on nautilus-trader 1.230.0): `Cache.instrument(InstrumentId) -> Instrument | None`,
`Cache.positions_open(instrument_id=...) -> list[Position]` (`[]` when flat, not an error),
`Cache.account_for_venue(venue=...) -> Account | None`. `CurrencyPair` carries `min_quantity`,
`size_increment`, `price_increment` (all `Quantity`/`Price`, `float()`-able, or `None`).
`Position.signed_qty` is a `float`, positive for LONG, negative for SHORT, `0.0` for FLAT --
confirmed by constructing real fills (`nautilus_trader.model.position.Position`), not by docstring
alone: a SELL-opened position read back `-1.0`, a BUY-opened one `+2.0`. `Account.balances_free()
-> dict[Currency, Money]`; `Currency.code` is the currency string, `Money`/`Quantity`/`Price` are
all `float()`-able.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime

from nautilus_trader.model import InstrumentId, Venue

from cli.engine.errors import EngineError
from cli.engine.instruments import COSTMIN, INSTRUMENT_IDS

_VENUE = Venue("KRAKEN")


@dataclass(frozen=True)
class InstrumentConstraints:
    """One symbol's venue-quoted order constraints, evidence -- not live-precision, hence float.
    `ordermin`/`lot_step`/`tick_size` are read live from the Cache; `costmin` is NOT (module
    docstring, D5a) -- it comes from the committed `COSTMIN` constant, and `costmin_quote` (spec
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
    """A frozen, single-instant read of the Cache: what the venue said we could trade, held, and
    had free to spend at `snapshot_at`. Plain data -- no Nautilus type reachable from here."""

    snapshot_at: datetime
    instruments: dict[str, InstrumentConstraints]
    positions: dict[str, float]
    balances: dict[str, float]

    def to_payload(self) -> dict:
        """JSON-ready: `snapshot_at` as ISO-8601, everything else already plain float/str.
        Each instrument entry carries `costmin_source` (D5a) -- costmin is a committed constant,
        never something the venue said this cycle, and the artifact must say so -- beside the
        `costmin_quote` field `InstrumentConstraints` itself already carries (00094 D4)."""
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
    # `None` is a legitimate Cache reading for a numeric constraint -- freeze it as 0.0 and let
    # runtime_concordance's `> 0` check flag it, rather than raising here.
    return 0.0 if value is None else float(value)


def venue_state_from_cache(cache, *, clock: Callable[[], datetime]) -> VenueState:
    """Read the twelve `INSTRUMENT_IDS` legs from `cache` and freeze them into a `VenueState`.

    Raises `EngineError` on a structural read failure -- a symbol's instrument entirely absent from
    the Cache, the Cache's own instrument id disagreeing with the expected one, or no account
    cached for the venue (each named in the message). The caller converts the raise to `None`;
    this function never narrows a failure into a partial/silent result. `costmin` is never read
    from `cache` at all (module docstring, D5a) -- it comes from the committed `COSTMIN`.
    """
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
            ordermin=_to_float(instrument.min_quantity),
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
    symbol is caught too): the instrument is present, and its three **Cache-supplied**
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
