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
    """Assemble the point-in-time universe file; deterministic given fixed inputs.

    `spread_cap` is the literal `"pending-capture"` when no spread criterion ran, else the record
    naming the cap, its reference notional and the calibration behind it (spec 00067)."""
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
    """Render the universe file as Markdown."""
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
    cap = file["spread_cap"]
    # The two nulls are not interchangeable: on the placeholder path the criterion never ran, so every row
    # is null, symbols with plenty of capture included; under a real cap the symbol had no calibrated
    # spread — labelling both "not captured" would state something false about the first.
    unscreened = "—" if isinstance(cap, str) else "not screened"
    for entry in file["entries"]:
        selected = "yes" if entry["selected"] else "no"
        margin = "yes" if entry["margin_enabled"] else "no"
        reasons = "; ".join(entry["reasons"]) if entry["reasons"] else "-"
        # Under a real cap an unscreened symbol says so rather than reading silently blank, so a filter
        # that covered only part of the universe cannot be mistaken for a universe-wide one (spec 00067 D3).
        spread = entry.get("spread_bps")
        spread_cell = unscreened if spread is None else f"{spread:.3f}"
        lines.append(
            f"| {entry['symbol']} | {selected} | {margin} | {entry['max_leverage']} "
            f"| {entry['median_quote_volume']:,.2f} | {spread_cell} | {reasons} |"
        )

    lines += ["", "## Parameters", "", "| Parameter | Value |", "|---|---|"]
    for key, value in file["params"].items():
        lines.append(f"| {key} | {value} |")

    unscreened_symbols = ", ".join(e["symbol"] for e in file["entries"] if e.get("spread_bps") is None)
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
            # Name the symbols, never the cause: hardcoding "because the legs are BTC-quoted" would
            # assert it of any future pair missing from the calibration table too.
            f"**{cap['unevaluated_count']} of {len(file['entries'])} symbols carry `spread_bps: null`** "
            f"— no calibrated spread at the reference notional, so the cap did not screen them: "
            f"{unscreened_symbols}."
            if unscreened_symbols
            else f"**Every one of the {len(file['entries'])} symbols was screened against the cap.**",
        ]

    lines += ["", "## Provenance", "", "| Key | Value |", "|---|---|"]
    for key, value in file["provenance"].items():
        lines.append(f"| {key} | {value} |")

    return "\n".join(lines) + "\n"
