"""The as-of reader: for each (series, day), the version latest along the chain among those knowable at t, with its
first-seen time, its last-seen time and the flags on both, the later facts joined. It reads versions, never raw
observations, so an absence counts only where the derivation read a retraction."""

from __future__ import annotations

import math
from datetime import datetime

import polars as pl

_TIME = pl.Datetime("us", "UTC")
AS_OF_SCHEMA: dict[str, pl.DataType] = {
    "ts": _TIME,
    "provider": pl.String(),
    "source": pl.String(),
    "series": pl.String(),
    "token": pl.String(),
    "kind": pl.String(),
    "tick": pl.String(),
    "position": pl.Int64(),
    "first_seen_at": _TIME,
    "last_seen_at": _TIME,
    "flags": pl.String(),
}
_DAY = ["series", "ts"]


def _split(flags: str | None) -> set[str]:
    return {flag for flag in (flags or "").split(",") if flag}


def as_of(versions: pl.DataFrame, coverage: pl.DataFrame, later_facts: pl.DataFrame, t: datetime) -> pl.DataFrame:
    ordered = versions.sort("position", maintain_order=True).with_columns(
        pl.col("position").shift(-1).over(_DAY).alias("next_position")
    )
    current = ordered.filter(pl.col("knowable_at") <= t).group_by(_DAY, maintain_order=True).last()

    seen = coverage.filter((pl.col("knowable_at") <= t) & (pl.col("series") != "*"))
    # A row is known to have held a day in its range when its absences are evidence or its days run unbroken.
    known = pl.col("evidence") | (pl.col("days") == (pl.col("last_day") - pl.col("first_day")).dt.total_days() + 1)
    holders: dict[str, list[dict]] = {}
    for row in seen.filter(known).sort("position", descending=True, maintain_order=True).iter_rows(named=True):
        holders.setdefault(row["series"], []).append(row)

    # A fact is known from its teaching tick's own knowable time, which its row carries, as a version is from its own:
    # never from a later chain position, which a tick under a clock running ahead can hold, nor from the tick's coverage,
    # which a tick that fetched no series lacks.
    facts: dict[str, set[str]] = {}
    for fact in later_facts.filter(pl.col("taught_at") <= t).iter_rows(named=True):
        facts.setdefault(fact["tick"], set()).add(fact["fact"])

    rows = []
    for version in current.iter_rows(named=True):
        day = version["ts"].date()
        upper = math.inf if version["next_position"] is None else version["next_position"]
        last = next(
            (
                row
                for row in holders.get(version["series"], ())
                if version["position"] <= row["position"] < upper and row["first_day"] <= day <= row["last_day"]
            ),
            None,
        )
        found = _split(version["flags"]) | facts.get(version["tick"], set())
        if last is not None:
            found |= _split(last["flags"]) | facts.get(last["tick"], set())
        rows.append(
            {
                "ts": version["ts"],
                "provider": version["provider"],
                "source": version["source"],
                "series": version["series"],
                "token": version["token"],
                "kind": version["kind"],
                "tick": version["tick"],
                "position": version["position"],
                "first_seen_at": version["ended_at"],
                "last_seen_at": None if last is None else last["ended_at"],
                "flags": ",".join(sorted(found)),
            }
        )
    return pl.DataFrame(rows, schema=AS_OF_SCHEMA).sort(["source", "series", "ts"], maintain_order=True)
