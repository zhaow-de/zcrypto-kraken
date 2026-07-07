from __future__ import annotations

from cli.universe.rules import UniverseSelection


def build_universe_file(selection: UniverseSelection, *, as_of: str, params: dict, provenance: dict) -> dict:
    """Assemble a structured point-in-time universe file. Deterministic given fixed inputs.

    Embeds `as_of`, the selected symbols, the full per-symbol criteria table, the rule `params`
    used, `spread_cap: "pending-capture"` (no spread criterion yet, per the design's non-goals),
    and `provenance` (the snapshot + OHLC dataset hashes it was derived from).
    """
    return {
        "as_of": as_of,
        "selected": list(selection.selected),
        "escalate": selection.escalate,
        "entries": [dict(entry) for entry in selection.entries],
        "params": dict(params),
        "spread_cap": "pending-capture",
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
        "| Symbol | Selected | Margin | Max leverage | Median quote volume | Reasons |",
        "|---|---|---|---|---|---|",
    ]
    for entry in file["entries"]:
        selected = "yes" if entry["selected"] else "no"
        margin = "yes" if entry["margin_enabled"] else "no"
        reasons = "; ".join(entry["reasons"]) if entry["reasons"] else "-"
        lines.append(
            f"| {entry['symbol']} | {selected} | {margin} | {entry['max_leverage']} "
            f"| {entry['median_quote_volume']:,.2f} | {reasons} |"
        )

    lines += ["", "## Parameters", "", "| Parameter | Value |", "|---|---|"]
    for key, value in file["params"].items():
        lines.append(f"| {key} | {value} |")

    lines += ["", "## Spread cap", "", f"`spread_cap`: {file['spread_cap']}"]

    lines += ["", "## Provenance", "", "| Key | Value |", "|---|---|"]
    for key, value in file["provenance"].items():
        lines.append(f"| {key} | {value} |")

    return "\n".join(lines) + "\n"
