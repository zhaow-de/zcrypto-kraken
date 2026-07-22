from __future__ import annotations

from cli.universe.rules import UniverseSelection


def build_universe_file(
    selection: UniverseSelection,
    *,
    as_of: str,
    params: dict,
    provenance: dict,
    spread_cap: dict | str = "pending-capture",
) -> dict:
    """Assemble a structured point-in-time universe file. Deterministic given fixed inputs.

    Embeds `as_of`, the selected symbols, the full per-symbol criteria table, the rule `params`
    used, the `spread_cap` criterion record, and `provenance` (the snapshot + OHLC dataset hashes
    it was derived from).

    `spread_cap` is either the literal `"pending-capture"` (no spread criterion applied -- pass
    `spread_cap=` to supply one) or a record naming the cap, the reference notional it is priced
    at, and the calibration behind it (T0024, spec 00067). Per-symbol values live on each entry's
    `spread_bps`, where `null` means the symbol has no L2 capture and was NOT screened -- the
    daemon subscribes to EUR-quoted pairs only, so the BTC-quoted legs carry nulls by construction.
    """
    return {
        "as_of": as_of,
        "selected": list(selection.selected),
        "escalate": selection.escalate,
        "entries": [dict(entry) for entry in selection.entries],
        "params": dict(params),
        "spread_cap": spread_cap if isinstance(spread_cap, str) else dict(spread_cap),
        "provenance": dict(provenance),
    }


def render_markdown(file: dict) -> str:
    """Render the selected universe, the per-symbol criteria table, params, and provenance."""
    lines = [
        f"**As of:** {file['as_of']} (UTC)",
        f"**Escalate:** {file['escalate']}",
        "",
        "## Selected universe",
        "",
        ", ".join(file["selected"]) if file["selected"] else "_(none)_",
        "",
        "## Per-symbol criteria",
        "",
        "| Symbol | Selected | Margin | Max leverage | Median quote volume | Spread (bps/side) | Reasons |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry in file["entries"]:
        selected = "yes" if entry["selected"] else "no"
        margin = "yes" if entry["margin_enabled"] else "no"
        reasons = "; ".join(entry["reasons"]) if entry["reasons"] else "-"
        # The column is the point of the null, not decoration: a symbol with no L2 capture reads
        # "not captured" here rather than silently blank, so a filter covering 10 of 12 cannot be
        # mistaken for a universe-wide one (spec 00067 D3).
        spread = entry.get("spread_bps")
        spread_cell = "not captured" if spread is None else f"{spread:.3f}"
        lines.append(
            f"| {entry['symbol']} | {selected} | {margin} | {entry['max_leverage']} "
            f"| {entry['median_quote_volume']:,.2f} | {spread_cell} | {reasons} |"
        )

    lines += ["", "## Parameters", "", "| Parameter | Value |", "|---|---|"]
    for key, value in file["params"].items():
        lines.append(f"| {key} | {value} |")

    cap = file["spread_cap"]
    lines += ["", "## Spread cap", ""]
    if isinstance(cap, str):
        lines += [f"`spread_cap`: {cap}"]
    else:
        lines += [
            f"`max_spread_bps`: {cap['max_spread_bps']} (bps per side, effective spread at "
            f"EUR {cap['reference_notional_eur']:,.0f} — the same max-size position the volume "
            f"floor is calibrated against)",
            "",
            f"Source: {cap['source']}.",
            "",
            f"**{cap['unevaluated_count']} of {len(file['entries'])} symbols carry `spread_bps: null`** "
            "— no L2 capture (the daemon subscribes to EUR-quoted pairs only), so the cap did not "
            "screen them.",
        ]

    lines += ["", "## Provenance", "", "| Key | Value |", "|---|---|"]
    for key, value in file["provenance"].items():
        lines.append(f"| {key} | {value} |")

    return "\n".join(lines) + "\n"
