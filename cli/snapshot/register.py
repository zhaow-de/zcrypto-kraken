from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from cli.snapshot.assetpairs import _COMMON_TO_KRAKEN, derive_universe


def _canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def build_snapshot(assetpairs_result: dict, assets_result: dict, symbols: list[str], fetched_at: str) -> dict:
    """Assemble a structured, content-hashed snapshot dict. Deterministic given a fixed `fetched_at`.

    Embeds the raw AssetPairs/Assets results verbatim (so the snapshot is self-contained) alongside
    `raw_sha256`, a hash over just those raw results (not `fetched_at`), for reproducibility.
    """
    universe = derive_universe(assetpairs_result, assets_result, symbols)
    raw = {"assetpairs": assetpairs_result, "assets": assets_result}
    return {
        "fetched_at": fetched_at,
        "raw": raw,
        "raw_sha256": hashlib.sha256(_canonical_json(raw).encode("utf-8")).hexdigest(),
        "symbols": list(symbols),
        "universe": [asdict(row) for row in universe],
    }


# The three ways a selected pair changes identity underneath us -- T0025's trigger, as a check the
# sweep runs rather than a table someone reads. Step 3 of `/zcrypto-refdata-sweep` asks for a diff of
# the rendered tables against the committed ones; a twelve-row table read by eye is where a
# `NOT FOUND`, a `status` that stopped saying `online`, or a renamed altname gets scrolled past.
#
# What this deliberately does NOT cover: a quote-book migration (BTC/EUR moving to a different quote
# book). No endpoint reports one, so there is nothing to compare -- named here so its absence is a
# recorded decision rather than an oversight.
_TRADEABLE_STATUS = "online"


def sweep_refusals(snapshot: dict) -> list[str]:
    """Reasons this snapshot must stop a reference-data sweep, one string each; empty means clean.

    Every reason names the pair and the observed value, because the operator's next act is to decide
    whether a corporate action happened -- and "something changed" cannot start that. ALL reasons are
    returned, never the first: a batch delisting is announced as a batch, and a check that short-
    circuits hides the rest until the next month's sweep.
    """
    reasons: list[str] = []
    for row in snapshot["universe"]:
        symbol = row["symbol"]
        if not row.get("found"):
            reasons.append(f"{symbol}: not in AssetPairs -- the pair is gone from the venue's own list (delisting?)")
            continue
        status = row.get("status")
        if status != _TRADEABLE_STATUS:
            reasons.append(f"{symbol}: status is {status!r}, not {_TRADEABLE_STATUS!r} -- listed but not normally tradeable")
        for common, altname in ((row["base"], row.get("base_altname")), (row["quote"], row.get("quote_altname"))):
            expected = _COMMON_TO_KRAKEN.get(common, common)
            if altname is not None and altname != expected:
                reasons.append(
                    f"{symbol}: {common} spells as {altname!r} where the committed alias says {expected!r} "
                    f"-- a redenomination reaches us this way"
                )
    return reasons


def _alias_ledger(universe: list[dict]) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for row in universe:
        for common, altname in ((row["base"], row["base_altname"]), (row["quote"], row["quote_altname"])):
            if altname and altname != common:
                seen[altname] = common
    return sorted(seen.items())


def render_markdown(snapshot: dict) -> str:
    """Render the candidate-basket table + alias ledger + provenance for `snapshot`."""
    universe = snapshot["universe"]
    lines = [
        f"**Fetched at:** {snapshot['fetched_at']} (UTC)",
        f"**Raw snapshot sha256:** `{snapshot['raw_sha256']}`",
        "",
        "## Candidate-basket margin & leverage ground truth",
        "",
        "| Symbol | Kraken pair | wsname | Margin | Leverage buy | Leverage sell | Ordermin | Costmin | Status |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in universe:
        if row["found"]:
            pair_key, wsname = row["pair_key"], row["wsname"]
            leverage_buy = ",".join(str(x) for x in row["leverage_buy"]) or "-"
            leverage_sell = ",".join(str(x) for x in row["leverage_sell"]) or "-"
            ordermin, costmin, status = row["ordermin"] or "-", row["costmin"] or "-", row["status"] or "-"
        else:
            pair_key = wsname = "NOT FOUND"
            leverage_buy = leverage_sell = ordermin = costmin = status = "-"
        margin = "yes" if row["margin_enabled"] else "no"
        lines.append(
            f"| {row['symbol']} | {pair_key} | {wsname} | {margin} | {leverage_buy} | {leverage_sell} "
            f"| {ordermin} | {costmin} | {status} |"
        )

    # The ⏱ cost facts. Rendered as base tier + ladder depth rather than the full ladders: the
    # ladders live in the snapshot JSON for a drift diff to name WHICH tier moved, but a 10-tier
    # table per pair would bury the row a reader actually checks. Fees are the largest term in the
    # cost model and margin_rate IS the borrow/rollover rate the master plan calls externally owned,
    # so an "unchanged" verdict that never looked at these columns was never worth much.
    lines += [
        "",
        "## Fee schedule, borrow rate & margin bands",
        "",
        "| Symbol | Taker % (base) | Maker % (base) | Fee tiers | Borrow: base (shorts) | Borrow: quote (longs) | Collateral value | Margin call | Margin stop | Long limit | Short limit |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in universe:

        def _f(key, fmt="{}"):
            value = row.get(key)
            return fmt.format(value) if value is not None else "-"

        tiers = len(row.get("fees_taker") or ())
        lines.append(
            f"| {row['symbol']} | {_f('fee_taker_base')} | {_f('fee_maker_base')} | {tiers or '-'} "
            f"| {_f('base_margin_rate')} | {_f('quote_margin_rate')} | {_f('base_collateral_value')} | {_f('margin_call')} "
            f"| {_f('margin_stop')} | {_f('long_position_limit')} | {_f('short_position_limit')} |"
        )

    lines += ["", "## Symbol-alias ledger", "", "| Kraken code | Common symbol |", "|---|---|"]
    for altname, common in _alias_ledger(universe):
        lines.append(f"| {altname} | {common} |")

    return "\n".join(lines) + "\n"
