"""The Logs board's rule tables, 102 and 103, as Grafana 13 builds their rows.

An instant Loki query does not reach a panel as the series the datasource returned: Grafana's Loki frontend turns
each refId's series into ONE table, `Time`, a string column per label (sorted, an absent label empty) and
`Value #<refId>`, and drops the legend. `_rows` replays the panels' transformations over that table the way Grafana
13's partitionByValues, renameByRegex and reduce name fields; a chain in any other shape is refused rather than
modelled.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BOARD = json.loads((REPO / "infra/grafana/zcrypto-logs-dashboard.json").read_text())
RULE_TABLES = (102, 103)
_SUBSTITUTION = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_CHAIN = re.compile(r"(partitionByValues )*(renameByRegex )*reduce organize (sortBy )?")


def _panel(panel_id: int) -> dict:
    (panel,) = [p for p in BOARD["panels"] if p.get("id") == panel_id]
    return panel


def _grouped_by(expr: str) -> list[str]:
    match = re.search(r"\bby \(([^)]*)\)", expr)
    return sorted(label.strip() for label in match.group(1).split(",")) if match else []


def _legend(legend_format: str, labels: dict[str, str]) -> str:
    return _SUBSTITUTION.sub(lambda m: labels.get(m.group(1), ""), legend_format)


def _js_regex(text: str) -> re.Pattern[str]:
    """Grafana's stringToJsRegex: `/body/flags` as written, anything else anchored at both ends."""
    if not text.startswith("/"):
        return re.compile(f"^{text}$")
    body, flags = re.fullmatch(r"/(.*?)/(g?i?m?y?s?)", text, re.S).groups()
    return re.compile(body, (re.S if "s" in flags else 0) | (re.I if "i" in flags else 0) | (re.M if "m" in flags else 0))


def _js_replace(regex: re.Pattern[str], pattern: str, text: str) -> str:
    match = regex.search(text)
    filled = re.sub(r"\$(\d)", lambda g: match.group(int(g.group(1))) or "", pattern)
    return text[: match.start()] + filled + text[match.end() :]


def _value_name(ref: str, labels: dict[str, str]) -> str:
    """The display name Grafana gives a `Value #<ref>` field carrying `labels`: one label key shows its value
    alone, several show as a sorted `{k="v", ...}` with nothing escaped."""
    if not labels:
        return f"Value #{ref}"
    if len(labels) == 1:
        return f"Value #{ref} {next(iter(labels.values()))}"
    pairs = ", ".join(f'{k}="{labels[k]}"' for k in sorted(labels))
    return f"Value #{ref} {{{pairs}}}"


def _rows(panel: dict, series: dict[str, list[dict[str, str]]]) -> list[str]:
    """The Rule cells the panel makes of `series`: refId -> the label set of each series its query returned."""
    transforms = panel["transformations"]
    assert _CHAIN.fullmatch("".join(f"{t['id']} " for t in transforms)), [t["id"] for t in transforms]
    partitions = {}
    for t in transforms:
        if t["id"] == "partitionByValues":
            # It partitions only the first frame it is handed and drops the rest, so it must be filtered to one refId.
            assert (t.get("filter") or {}).get("id") == "byRefId", t
            partitions[t["filter"]["options"]] = t["options"]["fields"]
    renames = [(_js_regex(t["options"]["regex"]), t["options"]["renamePattern"]) for t in transforms if t["id"] == "renameByRegex"]
    (reduce,) = [t["options"] for t in transforms if t["id"] == "reduce"]
    assert reduce["mode"] == "seriesToRows" and reduce["reducers"] == ["lastNotNull"], reduce
    numeric_only = (reduce.get("fields") or {}).get("id") == "numeric"

    frames = []
    for ref, label_sets in series.items():
        columns = sorted(set().union(*label_sets))
        keys = [k for k in partitions.get(ref, []) if k in columns]
        if keys:
            for values in dict.fromkeys(tuple(s.get(k, "") for k in keys) for s in label_sets):
                frames.append((ref, [c for c in columns if c not in keys], dict(zip(keys, values, strict=True))))
        else:
            frames.append((ref, columns, {}))

    rows = []
    for ref, columns, labels in frames:
        for name in ([] if numeric_only else columns) + [_value_name(ref, labels)]:
            for regex, pattern in renames:
                if regex.search(name):
                    name = _js_replace(regex, pattern, name)
            rows.append(name)
    return rows


def _sample(label: str, i: int) -> str:
    # A message carries quotes, a brace and a newline, as a logged traceback or a logfmt line does.
    return f'ts=1 level=error msg="{i} \\"quoted\\"}} gap"\nsecond line' if label == "msg" else f"{label}-{i}"


_TARGETS = [(panel_id, t["refId"]) for panel_id in RULE_TABLES for t in _panel(panel_id)["targets"]]


@pytest.mark.parametrize(("panel_id", "ref"), _TARGETS)
def test_a_rule_table_names_each_series_row_after_its_targets_legend(panel_id, ref):
    panel = _panel(panel_id)
    (target,) = [t for t in panel["targets"] if t["refId"] == ref]
    assert target["queryType"] == "instant", target
    labels = _grouped_by(target["expr"])
    # A legend that substitutes no label belongs to an expression that selects one stream, so one series.
    count = 2 if _SUBSTITUTION.search(target["legendFormat"]) else 1
    returned = [{label: _sample(label, i) for label in labels} for i in range(count)]
    for label_sets in (returned, [{}]):
        series = {t["refId"]: label_sets if t is target else [{}] for t in panel["targets"]}
        expected = [_legend(t["legendFormat"], s) for t in panel["targets"] for s in series[t["refId"]]]
        assert sorted(_rows(panel, series)) == sorted(expected)
