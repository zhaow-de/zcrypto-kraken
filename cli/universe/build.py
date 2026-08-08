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
    `spread_bps`, where `null` means the symbol is outside the committed calibration and was NOT
    screened. That is no longer a whole quote: since spec 00085 the table covers all twelve legs,
    BTC-quoted included, so a null here marks a genuine one-off rather than a structural blind spot.
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
    cap = file["spread_cap"]
    # A null means "this symbol was not screened", and the two reasons are NOT interchangeable:
    # on the placeholder path the criterion never ran at all (every row is null, including symbols
    # with plenty of capture), whereas under a real cap a null means that symbol had no calibrated
    # spread. Rendering both as "not captured" states something false about the first (T0024 review).
    unscreened = "—" if isinstance(cap, str) else "not screened"
    for entry in file["entries"]:
        selected = "yes" if entry["selected"] else "no"
        margin = "yes" if entry["margin_enabled"] else "no"
        reasons = "; ".join(entry["reasons"]) if entry["reasons"] else "-"
        # The column is the point of the null, not decoration: an unscreened symbol says so here
        # rather than reading silently blank, so a filter covering 10 of 12 cannot be mistaken for
        # a universe-wide one (spec 00067 D3).
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
            # Name the symbols, never the cause: a generated artifact that hardcodes "because the
            # legs are BTC-quoted" would assert it of any future EUR pair missing from the
            # calibration table too. The reader can see which symbols they are (T0024 review).
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
