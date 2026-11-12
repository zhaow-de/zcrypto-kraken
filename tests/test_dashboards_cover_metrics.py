"""Guard: when an alert fires, the operator must be able to open a picture of what moved -- and the
alert must say which picture.

Family extraction from PromQL: no parser exists in the locked dependency set, so this uses
STRUCTURAL removal instead of a denylist of function names (which rots the moment PromQL grows
one) -- delete the regions of an expression that cannot contain a metric name (string literals,
`$vars`, `{label matchers}`, `[ranges]`, `by (...)`/`on (...)` label lists), then keep every
remaining identifier that is NOT immediately applied to an argument list. `rate`,
`histogram_quantile` and whatever ships next are dropped because they are CALLED, not because they
are listed.
"""

import json
import re
from functools import cache
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
GRAFANA = REPO / "infra/grafana"
ALERTS = GRAFANA / "alerts.yaml"

# The glob `infra/scripts/grafana-push.sh` itself iterates. A dashboard file that does not match it
# is never pushed, so its panels are not a clue anyone can open -- counting them here would let a
# misnamed file satisfy coverage while Grafana never sees it.
DASHBOARD_GLOB = "*-dashboard.json"

# Alerts route by datasource: the Prometheus queries carry PromQL, the Loki ones carry LogQL, whose
# `{container="x"}` stream selectors contain no metric families at all. Splitting on the templated
# uid (which `test_infra_alert_rules.py` already pins to exactly these two values plus `__expr__`)
# is exact and needs no LogQL parsing.
PROM_DS = "${GRAFANA_PROM_DS_UID}"

# The fleet's `host` label values, hand-pinned rather than globbed: the Slack template's map and the
# Logs board's list are held to them.
FLEET_HOSTS = frozenset(
    {
        "nas",
        "ops",
        "zcrypto",
        "zcrypto-red",
        "zaccess",
        "zcrypto-valkey1",
        "zcrypto-valkey2",
        "zcrypto-valkey3",
        "zcrypto-mon",
        "zcrypto-hc",
    }
)


# --- Deliberate exclusions ----------------------------------------------------------------------
# Families deliberately drawn by no panel. Each entry is a REVIEWED decision and the reason IS the
# entry: a bare name here is drift wearing a test's clothes. The bar: charting the family would
# actively mislead, or it is a duplicate view of one already charted -- "we ran out of room" is not
# a reason, densify the layout instead.
NOT_CHARTED: dict[str, str] = {}


# --- PromQL family extraction --------------------------------------------------------------------
_STRING = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`[^`]*`')
_TEMPLATE_VAR = re.compile(r"\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*")
_LABEL_MATCHERS = re.compile(r"\{[^{}]*\}")
# Ranges, subqueries and `[$__rate_interval]` alike: durations only, never a family.
_RANGES = re.compile(r"\[[^\[\]]*\]")
# The one place a bare parenthesised list holds LABEL names rather than an expression. Without this,
# `max by (source) (...)` contributes a family called `source`.
_GROUPING = re.compile(r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^()]*\)")
# The lookbehind is load-bearing: without it the `h` of an unbracketed `offset 1h` is a family.
_IDENT = re.compile(r"(?<![A-Za-z0-9_:])[A-Za-z_:][A-Za-z0-9_:]*")
_APPLIED = re.compile(r"\s*\(")
# Operators and modifiers that survive the structural passes as bare words.
_KEYWORDS = frozenset(
    {
        "and",
        "or",
        "unless",
        "bool",
        "offset",
        "start",
        "end",
        "atan2",
        "by",
        "without",
        "on",
        "ignoring",
        "group_left",
        "group_right",
        "Inf",
        "NaN",
        "inf",
        "nan",
    }
)


def promql_families(expr: str) -> set[str]:
    """Every metric family name referenced by `expr`. See this module's docstring for the method."""
    stripped = _STRING.sub(" ", expr)
    stripped = _TEMPLATE_VAR.sub(" ", stripped)
    stripped = _LABEL_MATCHERS.sub(" ", stripped)
    stripped = _RANGES.sub(" ", stripped)
    stripped = _GROUPING.sub(" ", stripped)
    found = set()
    for match in _IDENT.finditer(stripped):
        if _APPLIED.match(stripped, match.end()):  # applied to an argument list => a function
            continue
        if match.group(0) not in _KEYWORDS:
            found.add(match.group(0))
    return found


# --- Sources -------------------------------------------------------------------------------------
@cache
def _rules() -> tuple[dict, ...]:
    return tuple(yaml.safe_load(ALERTS.read_text())["rules"])


def _prom_expressions(rule: dict) -> list[str]:
    """Every PromQL expression in `rule` -- the Loki and `__expr__` nodes carry neither."""
    return [q["model"]["expr"] for q in rule["data"] if q.get("datasourceUid") == PROM_DS and "expr" in q.get("model", {})]


@cache
def alerted_families() -> dict[str, frozenset[str]]:
    """family -> the rule uids whose PromQL names it."""
    found: dict[str, set[str]] = {}
    for rule in _rules():
        for expr in _prom_expressions(rule):
            for family in promql_families(expr):
                found.setdefault(family, set()).add(rule["uid"])
    return {k: frozenset(v) for k, v in found.items()}


def _walk_panels(panels: list[dict]):
    """Every panel, descending into a collapsed row's nested `panels`."""
    for panel in panels:
        yield panel
        yield from _walk_panels(panel.get("panels") or [])


@cache
def dashboards() -> tuple[tuple[str, dict], ...]:
    files = sorted(GRAFANA.glob(DASHBOARD_GLOB))
    assert files, f"no dashboards matched {GRAFANA}/{DASHBOARD_GLOB} -- coverage would pass vacuously"
    return tuple((f.name, json.loads(f.read_text())) for f in files)


def _prom_targets(panel: dict) -> list[dict]:
    """A hidden target draws nothing; a Loki target carries LogQL, not PromQL."""
    return [t for t in (panel.get("targets") or []) if not t.get("hide") and (t.get("datasource") or {}).get("type") != "loki"]


def _panel_expressions():
    """`(dashboard, where, expr)` for every drawn PromQL target, `where` as `<file> <uid>#<panelId> "<title>"`."""
    for filename, dash in dashboards():
        for panel in _walk_panels(dash.get("panels") or []):
            where = f"{filename} {dash.get('uid')}#{panel.get('id')} {panel.get('title')!r}"
            for target in _prom_targets(panel):
                yield dash, where, target.get("expr") or ""


@cache
def panel_families() -> dict[str, frozenset[str]]:
    """family -> the panels drawing it."""
    found: dict[str, set[str]] = {}
    for _, where, expr in _panel_expressions():
        for family in promql_families(expr):
            found.setdefault(family, set()).add(where)
    return {k: frozenset(v) for k, v in found.items()}


# --- What this repo publishes ---------------------------------------------------------------------
# Four publication mechanisms (patterns), numbered below. Eight
# canaries in `test_the_publisher_scan_still_finds_each_source_kind` -- one per discovery path,
# not one per mechanism (see that test's own comment).
#
# Scope is the four namespaces this repo's own producers publish into. `node_*`, `process_*`, `hc_*`
# and `redis_*` come from node-exporter, prometheus_client, the dead-man service and Alloy's Redis
# exporter -- not ours to chart exhaustively, and the alert layer (assertion 1) already pulls in the
# ones that matter.
_APP = r"(?:zcrypto|ops|zaccess|zcache)_[a-z0-9_]*[a-z0-9]"
# (1) an exposition HELP/TYPE line, wherever it is printed from.
_HELP_LINE = re.compile(rf"#\s+(?:HELP|TYPE)\s+({_APP})\b")
# (2) a sample line: the family name OPENS a quoted literal and is terminated by a label brace or
# whitespace. The opening quote is what keeps this off prose in a docstring and off the ansible
# variables that share the `ops_` prefix -- a bare `ops_` grep over the roles returns more variables
# (`ops_image_digest`, `ops_textfile_dir`, ...) than metrics.
_SAMPLE_LINE = re.compile(rf"""['"]({_APP})(?=[\s{{])""")
# (3) a prometheus_client constructor, whose first positional argument is the family name.
_CONSTRUCTOR = re.compile(
    r"\b(Gauge|Counter|Histogram|Summary|Info|Enum|GaugeMetricFamily|CounterMetricFamily|"
    rf'HistogramMetricFamily|SummaryMetricFamily|InfoMetricFamily|StateSetMetricFamily)\(\s*"({_APP})"'
)
_COUNTER_CONSTRUCTORS = frozenset({"Counter", "CounterMetricFamily"})
# (4) `cli/archive/command.py` assembles every reconcile series as `f"zcrypto_reconcile_{name}"`, so
# no name-shaped scan can see one -- only the `_emit(<suffix>, ...)` call sites can. Derived rather
# than hand-listed so a new reconcile series joins the candidate set on the commit that adds it.
_RECONCILE_EMIT = re.compile(r'_emit\(\s*"([a-z0-9_]+)"')
_RECONCILE_PREFIX = "zcrypto_reconcile_"

_PUBLISHER_GLOBS = ("cli/**/*.py", "infra/**/*.sh", "infra/**/*.j2")


@cache
def published_app_families() -> dict[str, frozenset[str]]:
    """family -> the files this repo publishes it from."""
    found: dict[str, set[str]] = {}
    for glob in _PUBLISHER_GLOBS:
        for path in sorted(REPO.glob(glob)):
            text, rel = path.read_text(), str(path.relative_to(REPO))
            for pattern in (_HELP_LINE, _SAMPLE_LINE):
                for match in pattern.finditer(text):
                    found.setdefault(match.group(1), set()).add(rel)
            for match in _CONSTRUCTOR.finditer(text):
                # `Counter` APPENDS `_total` when the given name lacks it, so the name in the source
                # is not always the name in Grafana. Every call site happens to spell it today, which
                # is exactly why an unnormalised scan would look correct while being wrong.
                family = match.group(2)
                if match.group(1) in _COUNTER_CONSTRUCTORS and not family.endswith("_total"):
                    family += "_total"
                found.setdefault(family, set()).add(rel)
            for match in _RECONCILE_EMIT.finditer(text):
                found.setdefault(_RECONCILE_PREFIX + match.group(1), set()).add(rel)
    return {k: frozenset(v) for k, v in found.items()}


def _describe(family: str) -> str:
    lines = []
    if family in alerted_families():
        lines.append("        alerted by: " + ", ".join(sorted(alerted_families()[family])))
    if family in published_app_families():
        lines.append("        published at: " + ", ".join(sorted(published_app_families()[family])))
    return "\n".join(lines)


# --- (1) every alerted family is drawn -------------------------------------------------------------
def test_every_alerted_family_is_charted():
    """The owner's principle: when an alert fires, the clue is findable on a dashboard. FAMILY-level,
    never rule-level -- two rules on `node_filesystem_avail_bytes` (a low and a high watermark) are
    one signal, served by one trend panel with both thresholds marked, not by two stat tiles."""
    uncovered = sorted(set(alerted_families()) - set(panel_families()) - set(NOT_CHARTED))
    report = "\n".join(f"    {f}\n{_describe(f)}" for f in uncovered)
    assert not uncovered, (
        f"{len(uncovered)} alerted metric families are drawn by no panel on any committed dashboard --"
        f" these rules can page at 03:00 with nothing to open:\n{report}\n"
        f"  Fix: add a panel referencing the family to a dashboard under infra/grafana/{DASHBOARD_GLOB},"
        f" or add a reasoned entry to NOT_CHARTED in {Path(__file__).name}."
    )


# --- (2) every app family we publish is drawn ------------------------------------------------------
def test_every_published_app_family_is_charted():
    """A producer we ship is a producer we can watch break."""
    uncovered = sorted(set(published_app_families()) - set(panel_families()) - set(NOT_CHARTED))
    report = "\n".join(f"    {f}\n{_describe(f)}" for f in uncovered)
    assert not uncovered, (
        f"{len(uncovered)} app-level metric families this repo publishes are drawn by no panel on any"
        f" committed dashboard:\n{report}\n"
        f"  Fix: add a panel referencing the family to a dashboard under infra/grafana/{DASHBOARD_GLOB},"
        f" or add a reasoned entry to NOT_CHARTED in {Path(__file__).name}."
    )


# --- (3) the alert points at the panel -------------------------------------------------------------
# A rule whose signal is genuinely not panel-shaped (a pure log-content rule) may name a runbook
# section instead. `test_infra_alert_rules.py` already proves that every cited anchor resolves; this
# only asks whether one is cited at all.
_RUNBOOK_REFERENCE = re.compile(r"infra/runbooks/[A-Za-z0-9._-]+\.md#[A-Za-z0-9._-]+")


def _annotations(rule: dict) -> dict:
    return rule.get("annotations") or {}


def _cites_a_runbook(rule: dict) -> bool:
    annotations = _annotations(rule)
    return "runbook_url" in annotations or any(_RUNBOOK_REFERENCE.search(str(v)) for v in annotations.values())


def test_every_panel_id_annotation_is_a_string():
    """`grafana-push.sh` does `yaml.safe_load` -> `json.dumps` and Grafana's annotations are
    `map[string]string`, so an unquoted `305` arrives as a JSON number, the provisioning API rejects
    the rule with a bare 400, and `curl -fsS` under `set -euo pipefail` aborts the ENTIRE push --
    every rule and every dashboard, not just this one."""
    wrong = [
        (r["uid"], type(_annotations(r)["__panelId__"]).__name__)
        for r in _rules()
        if "__panelId__" in _annotations(r) and not isinstance(_annotations(r)["__panelId__"], str)
    ]
    assert not wrong, f"__panelId__ must be a QUOTED string in alerts.yaml -- an unquoted id aborts the whole push: {wrong}"


def test_the_panels_over_the_dead_man_series_name_the_service():
    panels = [
        panel
        for name, dash in dashboards()
        if name == "fleet-health-dashboard.json"
        for panel in _walk_panels(dash.get("panels") or [])
        if any(re.search(r"\bhc_check", t.get("expr") or "") for t in _prom_targets(panel))
    ]
    assert sorted(p["id"] for p in panels) == [103, 104], [p.get("id") for p in panels]
    for panel in panels:
        texts = (panel["title"], panel["description"])
        assert panel["title"].startswith("Dead-man service — "), texts
        assert not re.search(r"healthchecks\.io|hc\.io", " ".join(texts)), texts


def test_every_rule_points_at_a_real_panel_or_a_runbook():
    """Grafana builds the notification's panel link from `__dashboardUid__`/`__panelId__`. A pointer
    that is present but wrong is worse than one that is absent -- it is a confident wrong answer -- so
    a rule that carries one must have it RESOLVE, and only a rule carrying none may fall back to a
    runbook reference."""
    by_uid = {dash.get("uid") for _, dash in dashboards()}
    panels = {
        (dash.get("uid"), panel.get("id")): panel for _, dash in dashboards() for panel in _walk_panels(dash.get("panels") or [])
    }
    problems = []
    for rule in _rules():
        annotations = _annotations(rule)
        uid, raw_id = annotations.get("__dashboardUid__"), annotations.get("__panelId__")
        if uid is None and raw_id is None:
            if not _cites_a_runbook(rule):
                problems.append(f"    {rule['uid']} -- neither a __dashboardUid__/__panelId__ pointer nor a runbook reference")
            continue
        if uid is None or raw_id is None:
            problems.append(f"    {rule['uid']} -- half a pointer: __dashboardUid__={uid!r}, __panelId__={raw_id!r}")
            continue
        if not isinstance(raw_id, str):
            continue  # the string check above owns this, and int() below would mask it
        if uid not in by_uid:
            problems.append(f"    {rule['uid']} -- __dashboardUid__ {uid!r} matches no dashboard under infra/grafana/")
            continue
        if not raw_id.isdigit():
            problems.append(f"    {rule['uid']} -- __panelId__ {raw_id!r} is not a panel id")
            continue
        panel = panels.get((uid, int(raw_id)))
        if panel is None:
            problems.append(f"    {rule['uid']} -- dashboard {uid!r} has no panel with id {raw_id}")
        elif panel.get("type") == "row":
            problems.append(f"    {rule['uid']} -- points at row header {panel.get('title')!r}, which draws nothing")
    assert not problems, (
        "alert rules whose notification carries no working link to the clue:\n"
        + "\n".join(problems)
        + "\n  Fix: point __dashboardUid__/__panelId__ at the panel plotting the rule's own expression,"
        " or cite a runbook section on a rule whose signal is not panel-shaped."
    )


# --- the exclusions stay reviewed ------------------------------------------------------------------
def test_the_not_charted_exclusions_stay_reviewed():
    """An exclusion outliving its subject excuses nothing while hiding the next real gap behind a
    plausible-looking entry -- and an exclusion that never had a subject is worse: it is a standing
    pre-waiver, silently exempting the first rule anyone writes on that family."""
    unneeded = sorted(set(NOT_CHARTED) - (set(alerted_families()) | set(published_app_families())))
    assert not unneeded, (
        f"NOT_CHARTED excuses families that no assertion asks for: {unneeded}. Nothing alerts on them"
        f" and this repo does not publish them, so the entry waives a demand that does not exist --"
        f" and would go on waiving it for a rule written years from now. Delete the entries."
    )
    drawn = sorted(set(NOT_CHARTED) & set(panel_families()))
    assert not drawn, f"NOT_CHARTED excuses families that DO have a panel now: {drawn}. Delete the entries."
    unreasoned = sorted(f for f, why in NOT_CHARTED.items() if len(why.strip()) < 40)
    assert not unreasoned, f"NOT_CHARTED entries without a real reason: {unreasoned}"


# --- the extractors themselves must not go blind ---------------------------------------------------
def test_the_extractors_have_not_gone_blind():
    """Every assertion above is a set difference, and a set difference against an empty left-hand side
    passes. A regressed strip or a drifted glob would therefore turn this whole file green while
    checking nothing -- the quietest possible failure, so the floors are real counts rather than
    `> 0`."""
    assert len(alerted_families()) >= 40, f"only {len(alerted_families())} alerted families across {len(_rules())} rules"
    assert len(panel_families()) >= 90, f"only {len(panel_families())} families drawn across {len(dashboards())} dashboards"
    assert len(published_app_families()) >= 60, f"only {len(published_app_families())} app families found in the source tree"
    # Label names (the matcher and `by (...)` strips) and the trailing letter of a duration literal
    # (the `_IDENT` lookbehind) are how this extractor degrades into nonsense.
    leaks = {"host", "source", "pair", "mountpoint", "system", "file", "le", "container", "level", "target", "outcome"}
    leaks |= set("smhdwy")
    junk = sorted((set(alerted_families()) | set(panel_families())) & leaks)
    assert not junk, f"label names or duration units leaked into the family set -- a strip regressed: {junk}"


@pytest.mark.parametrize(
    "family",
    [
        # One canary per discovery path. If a path breaks its families vanish from assertion 2's
        # candidate set and it passes vacuously for all of them.
        "zcrypto_capture_book_desynced",  # a custom collector's GaugeMetricFamily(...) in cli/
        "zcrypto_engine_orders_total",  # a stock Counter(...) in cli/, whose name normalisation runs here
        "zcrypto_gate_streak_days",  # an f-string exposition line in cli/
        "zcrypto_reconcile_source_lag_seconds",  # assembled at runtime, recovered from the _emit call sites
        "ops_verify_replay_run_ok",  # a printf '# HELP ...' in a Jinja template
        "zcrypto_trade_backfill_exit_code",  # a bare sample line with no HELP line
        "zaccess_tls_not_after_seconds",  # a sample line carrying labels
        "zcrypto_engine_journal_prune_kept_days",  # an echo in a plain .sh
        "zcache_wireguard_handshake_age_seconds",  # an echoed HELP line in a plain .sh, the fourth namespace
    ],
)
def test_the_publisher_scan_still_finds_each_source_kind(family):
    assert family in published_app_families(), (
        f"{family} is no longer discovered by the publisher scan. Either its producer moved or was"
        f" renamed (update this canary) or a discovery path broke -- in which case every family that"
        f" path used to find is now silently exempt from coverage."
    )


# A table's frame mixes string label columns with the numeric value, and `fieldConfig.defaults`
# applies to EVERY field in it -- so a date unit parked there is handed the label strings too,
# cannot coerce them, and renders every label column as `NaN`. Number-family units (`short`,
# `bytes`) pass a string through untouched, which is why only the date family is banned here.
# The unit belongs on an override scoped to the value column -- matched by TYPE, not by name: a
# value field's name shifts with the frame count (see the guard below), so a name-matched override
# silently stops applying the moment a query returns a single series.
_DATE_UNIT = re.compile(r"^(?:dateTime|time:)")


def test_no_table_panel_parks_a_date_unit_in_its_defaults():
    offenders = []
    for filename, dash in dashboards():
        for panel in _walk_panels(dash.get("panels") or []):
            if panel.get("type") != "table":
                continue
            unit = ((panel.get("fieldConfig") or {}).get("defaults") or {}).get("unit") or ""
            if _DATE_UNIT.match(unit):
                offenders.append(f"{filename} #{panel.get('id')} {panel.get('title')!r} unit={unit!r}")
    assert not offenders, (
        f"a table panel parks a date unit in fieldConfig.defaults, so every string label column in it"
        f" renders as NaN -- move the unit onto a byType:number override for the value column: {offenders}"
    )


# `merge` and `joinByField` combine one frame per series, and Grafana suffixes the value column
# with its refId ONLY to disambiguate several frames -- so the field is `Value #A` when the query
# returns many series and a bare `Value` when it returns exactly one. A rename keyed on `Value`
# therefore matches nothing in the ordinary multi-series case: the column keeps its raw name, and
# every override aimed at the renamed name misses too, so the value renders unformatted.
#
# The name being data-dependent is also why the value column's own overrides must match by TYPE --
# `test_a_single_target_merged_table_matches_its_value_by_type` below.
_MERGING = frozenset({"merge", "joinByField"})


def test_a_merged_table_renames_the_refid_suffixed_value_column():
    offenders = []
    for filename, dash in dashboards():
        for panel in _walk_panels(dash.get("panels") or []):
            if panel.get("type") != "table":
                continue
            transforms = panel.get("transformations") or []
            if not any(t.get("id") in _MERGING for t in transforms):
                continue
            for t in transforms:
                if t.get("id") != "organize":
                    continue
                if "Value" in ((t.get("options") or {}).get("renameByName") or {}):
                    offenders.append(f"{filename} #{panel.get('id')} {panel.get('title')!r}")
    assert not offenders, (
        f"a merged/joined table renames a bare 'Value', but a multi-series query names that field"
        f" 'Value #<refId>' -- the rename misses there and the column renders raw and unnamed: {offenders}"
    )


# The other half: a single-target merged table must reach its value column by TYPE, since one series
# yields `Value` and several yield `Value #<refId>` -- a `byName` override there works only until the
# pickers narrow to one stream. A panel with several targets is exempt: its frames are structural
# rather than data-driven, so the suffix is stable.
_VALUE_FIELD = re.compile(r"^Value(?: #\w+)?$")
_VALUE_PROPS = frozenset({"unit", "displayName"})


def test_a_single_target_merged_table_matches_its_value_by_type():
    offenders = []
    for filename, dash in dashboards():
        for panel in _walk_panels(dash.get("panels") or []):
            if panel.get("type") != "table":
                continue
            transforms = panel.get("transformations") or []
            if not any(t.get("id") in _MERGING for t in transforms):
                continue
            if len([t for t in (panel.get("targets") or []) if not t.get("hide")]) != 1:
                continue
            # Whatever an `organize` rename turns a value field into. The raw spellings are matched
            # separately, on the matcher's own option: seeding them here would only cover the
            # un-suffixed `Value`, letting an override keyed on the `Value #<refId>` spelling -- the
            # one the UI shows in the multi-series view -- past the guard in exactly the shape it exists to stop.
            renamed_value_names = set()
            for t in transforms:
                if t.get("id") == "organize":
                    for src, dst in ((t.get("options") or {}).get("renameByName") or {}).items():
                        if _VALUE_FIELD.match(src):
                            renamed_value_names.add(dst)
            for ov in (panel.get("fieldConfig") or {}).get("overrides") or []:
                matcher = ov.get("matcher") or {}
                props = {p.get("id") for p in (ov.get("properties") or [])}
                name = matcher.get("options")
                hits_value = name in renamed_value_names or (isinstance(name, str) and bool(_VALUE_FIELD.match(name)))
                if matcher.get("id") == "byName" and hits_value and props & _VALUE_PROPS:
                    offenders.append(
                        f"{filename} #{panel.get('id')} {panel.get('title')!r}"
                        f" byName={matcher.get('options')!r} carries {sorted(props & _VALUE_PROPS)}"
                    )
    assert not offenders, (
        f"a single-target merged table reaches its value column by NAME, but that name changes with"
        f" the number of series returned -- narrowing the pickers to one stream silently drops these"
        f" properties. Match byType:number instead: {offenders}"
    )


# 2, on time range change, re-runs a variable's query on every auto-refresh, and Grafana then cancels and re-runs every
# panel that reads it.
def test_every_query_variable_on_every_board_resolves_on_dashboard_load():
    refresh = {
        f"{filename} ${v['name']}": v.get("refresh")
        for filename, dash in dashboards()
        for v in (dash.get("templating") or {}).get("list") or []
        if v.get("type") == "query"
    }
    assert refresh and set(refresh.values()) == {1}, {name: r for name, r in refresh.items() if r != 1}


def _unscoped(expr: str) -> str:
    """A panel may pin the rule's own expression to the ops exporter with `{host="ops"}`, and an
    ops-only rule carries it in its own; the pairing compares the two without that one matcher on
    either side. `$host` is read as the engine board's one host, the primary, on every board,
    though the fleet, logs and cache boards' `$host` offer others."""
    return (
        expr.replace('{host="ops"}', "")
        .replace('host=~"$capture_host"', 'host=~"zcrypto|zcrypto-red"')
        .replace('host=~"$host"', 'host="zcrypto"')
        .strip()
    )


def _rule_panel_pairs():
    """Every (rule, panel, target) where the panel charts exactly the rule's own expression."""
    rules = yaml.safe_load((REPO / "infra/grafana/alerts.yaml").read_text())

    def iter_rules(o):
        if isinstance(o, dict):
            if "uid" in o and "data" in o:
                yield o
            for v in o.values():
                yield from iter_rules(v)
        elif isinstance(o, list):
            for v in o:
                yield from iter_rules(v)

    def panels(ps):
        for p in ps:
            yield p
            yield from panels(p.get("panels", []))

    dashboards = [json.loads(f.read_text()) for f in sorted((REPO / "infra/grafana").glob("*dashboard*.json"))]
    for r in iter_rules(rules):
        pid = (r.get("annotations") or {}).get("__panelId__")
        expr = next((q["model"]["expr"] for q in r["data"] if "expr" in q.get("model", {})), None)
        cond = next(
            (
                c["evaluator"]["type"]
                for q in r["data"]
                for c in q.get("model", {}).get("conditions", [])
                if c.get("evaluator", {}).get("params")
            ),
            None,
        )
        ev = next(
            (
                c["evaluator"]["params"][0]
                for q in r["data"]
                for c in q.get("model", {}).get("conditions", [])
                if c.get("evaluator", {}).get("params")
            ),
            None,
        )
        if pid is None or expr is None or ev is None:
            continue
        for d in dashboards:
            for p in panels(d.get("panels", [])):
                if str(p.get("id")) != str(pid):
                    continue
                for t in p.get("targets", []):
                    if _unscoped(t.get("expr", "")) == _unscoped(expr):
                        yield r["uid"], p, t, ev, cond


def _first_firing_value(condition: str, evaluator: float) -> str:
    """The smallest whole value that trips the rule -- what a mapping must colour to be a signal."""
    if condition == "lt":
        return str(int(evaluator) - 1 if float(evaluator).is_integer() else int(evaluator))
    return str(int(evaluator) + 1)


def test_a_panels_red_line_agrees_with_the_rule_it_charts():
    """Where a panel draws per-series thresholds, the charted series' bar must equal its rule's.

    A responder paged by a rule opens the panel the annotation names: if that series has no bar, or
    one calibrated for a different rule, the panel says "healthy" while the rule says "fire" -- and
    the panel wins, because it is what a human looks at.
    """
    # `zcrypto-ops-tapebars-not-advancing` charts panel 402 refId F, which has no bar while A/B/C
    # do -- a live instance of exactly what this test forbids, in a dashboard whose intent needs its
    # own reading. New entries are not acceptable: the guard exists to stop this class growing.
    known = {"zcrypto-ops-tapebars-not-advancing"}
    pairs = list(_rule_panel_pairs())
    # Pairing is string equality after `_unscoped`, so reformatting one expression, or a scope it
    # stops reading, drops rules from coverage with no failure anywhere. The floor makes a collapse
    # visible. Lower it only when a rule or panel is deliberately retired.
    assert len(pairs) >= 90, f"rule-to-panel pairing collapsed to {len(pairs)}"
    bad = []
    for uid, panel, target, evaluator, condition in pairs:
        if uid in known:
            continue
        overrides = panel.get("fieldConfig", {}).get("overrides", [])
        by_ref = {o["matcher"]["options"]: o for o in overrides if o.get("matcher", {}).get("id") == "byFrameRefID"}
        ref = target.get("refId")
        if ref in by_ref:
            steps = [
                s
                for prop in by_ref[ref].get("properties", [])
                if prop.get("id") == "thresholds"
                for s in prop.get("value", {}).get("steps", [])
                if s.get("value") is not None
            ]
        else:
            # A series with no override inherits the panel default, which usually carries the bar --
            # reading another refId's override as "this panel bars per series" misjudges a panel
            # whose only override REMOVES one.
            steps = [
                s
                for s in panel.get("fieldConfig", {}).get("defaults", {}).get("thresholds", {}).get("steps", [])
                if s.get("value") is not None
            ]
        if not steps:
            # Some panels colour by value MAPPING rather than a numeric bar (a stat reading
            # "failed"/"ok"). That is a real signal, but only if the mapping covers the value the
            # rule fires at -- a panel mapping 0 and 999 renders a firing 2 in the default colour,
            # which is the same "healthy-looking failure" this test exists to stop.
            mapped = {
                str(k)
                for m in panel.get("fieldConfig", {}).get("defaults", {}).get("mappings", [])
                for k in (m.get("options") or {})
                if k != "match"
            }
            if mapped and _first_firing_value(condition, evaluator) in mapped:
                continue
            bad.append(f"{uid}: panel {panel['id']} refId {ref} has no threshold at all, per-series or default")
            continue

        # For a `gt 0` rule a line at 0 would paint a healthy panel red, so its bar sits in
        # 0 < bar <= 1; every other rule's bar is its evaluator.
        def marks_the_rule(v: float) -> bool:
            if evaluator == 0 and condition == "gt":
                return 0 < v <= 1
            return v == evaluator

        if not any(marks_the_rule(s["value"]) for s in steps):
            bad.append(f"{uid}: panel {panel['id']} refId {ref} bars at {[s['value'] for s in steps]}, rule fires at {evaluator}")
    assert not bad, "a panel's red line disagrees with the rule that points at it:\n  " + "\n  ".join(bad)


def test_the_proxy_page_panel_charts_the_rules_own_expression():
    pairs = {(uid, panel["id"], target["refId"]) for uid, panel, target, *_ in _rule_panel_pairs()}
    assert ("zcrypto-cache-proxy-no-backend", 402, "A") in pairs


def test_the_venue_tiles_read_failure_shows_its_firing_value_red_and_not_as_online():
    # A target with no override of its own inherits the tile's `1` -> ONLINE mapping, which the red-line
    # test above accepts as covering the rule's firing value, so the firing read would show a green ONLINE.
    (board,) = [dash for filename, dash in dashboards() if filename == "engine-dashboard.json"]
    (panel,) = [p for p in _walk_panels(board["panels"]) if p.get("id") == 55]
    (target,) = [t for t in _prom_targets(panel) if "zcrypto_exec_venue_read_failed" in promql_families(t["expr"])]
    overrides = {o["matcher"]["options"]: o for o in panel["fieldConfig"]["overrides"] if o["matcher"]["id"] == "byFrameRefID"}
    assert target["refId"] in overrides, f"refId {target['refId']} carries no override of its own, so it reads the tile's mapping"
    mapped = {
        value: option
        for prop in overrides[target["refId"]]["properties"]
        if prop["id"] == "mappings"
        for mapping in prop["value"]
        for value, option in mapping["options"].items()
    }
    assert mapped.get("1", {}).get("color") == "red" and mapped["1"].get("text") != "ONLINE", mapped


def test_the_reconciliation_tile_reads_not_read_yet_with_no_series():
    (panel,) = [panel for uid, panel, *_ in _rule_panel_pairs() if uid == "zcrypto-engine-reconciliation-position"]
    assert panel["fieldConfig"]["defaults"]["noValue"] == "NOT READ YET"
    steps = panel["fieldConfig"]["defaults"]["thresholds"]["steps"]
    assert [(step["color"], step["value"]) for step in steps] == [("red", None), ("green", 0), ("red", 0.5)], steps


def test_the_slack_template_and_the_logs_board_name_every_host_of_the_topology():
    """A host the template's map lacks reaches a phone as its raw label, and one the Logs board's list lacks ships log
    lines that board cannot select."""
    template = (REPO / "infra/grafana/notification-templates/zcrypto-slack.tmpl").read_text()
    define = template[template.index('{{ define "zcrypto.host" -}}') :]
    named = dict(re.findall(r'eq \. "([^"]+)" \}\}(.+)', define[: define.index("{{- end -}}")]))
    assert set(named) == FLEET_HOSTS, (
        f"only in the template {sorted(set(named) - FLEET_HOSTS)}, only in the topology {sorted(FLEET_HOSTS - set(named))}"
    )
    (board,) = [dash for filename, dash in dashboards() if filename == "zcrypto-logs-dashboard.json"]
    (variable,) = [v for v in board["templating"]["list"] if v["name"] == "host"]
    listed = {value: text for text, value in (option.split(" : ") for option in variable["query"].split(", "))}
    offered = {option["value"]: option["text"] for option in variable["options"] if option["value"] != "$__all"}
    assert listed == offered == named, f"the query lists {listed}, the options offer {offered}, the template names {named}"
