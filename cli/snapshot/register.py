from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

from cli.snapshot.assetpairs import derive_universe


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

    lines += ["", "## Symbol-alias ledger", "", "| Kraken code | Common symbol |", "|---|---|"]
    for altname, common in _alias_ledger(universe):
        lines.append(f"| {altname} | {common} |")

    return "\n".join(lines) + "\n"
