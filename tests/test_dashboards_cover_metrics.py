"""Guard: when an alert fires, the operator must be able to open a picture of what moved -- and the
alert must say which picture.

`test_infra_alloy_series.py` proves a series REACHES Grafana; `test_infra_alert_rules.py` proves
something WATCHES it. Neither proves anyone can SEE it, and neither proves the page carries a link
to it. The four assertions here close that, each against a source it DERIVES rather than a list a
human maintains:

1. every metric family any alert rule queries is drawn by some panel on some committed dashboard;
2. every app-level family this repo publishes is drawn by some panel;
3. every alerted family is keep-list admitted on the hosts its rule selects;
4. every rule resolves to a real, non-row panel on the board its `__dashboardUid__` names, or
   carries a runbook reference -- never neither -- and every `__panelId__` loads as a `str`.

**(3) is the load-bearing one.** `test_infra_alloy_series.py` already guards keep-regex admission,
but from a hand-curated per-host `required` list: it catches a LISTED family being dropped and is
blind to a family missing from the list. That blindness is exactly how `zaccess` came to be
structurally unable to fail its own `node_scrape_collector_success` alert -- admitted nowhere in the
bridgehead's keep-regex, so `min by (host) (node_scrape_collector_success)` could never match that
host, and the rule sat green while the host was invisible to it.

The property this file actually provides, stated precisely rather than as "it cannot recur": the
FAMILY set comes from `alerts.yaml` and the HOST set comes from the rule's own selectors, from
`KEEP_REGEX_FILES` (the fleet topology) or from where this repo publishes the family -- never from
the keep-regexes under audit. An earlier draft derived the fleet-wide host set from the keep-regexes
themselves ("every host admitting `node_load1`"), which failed open at the exact hole it exists to
close: deleting `node_load1` AND `node_scrape_collector_success` from the bridgehead's regex dropped
that host out of the requirement set and every assertion here stayed green. Two edges remain, both
named below under scope limits.

**(4)'s string check is the one whose violation is not local.** `grafana-push.sh` does
`yaml.safe_load` -> `json.dumps`, and Grafana's rule annotations are `map[string]string`: an
unquoted `305` reaches the provisioning API as a JSON number, the API rejects the rule, and
`curl -fsS` under `set -euo pipefail` aborts the whole push -- no rules AND no dashboards ship.

--- Family extraction from PromQL ---------------------------------------------------------------

No PromQL parser exists in the locked dependency set (`prometheus-client` is an exposition library
and ships none), and adding one for a guard test is not licensed here. What replaces it is not a
denylist of function names -- that rots the moment PromQL grows one -- but STRUCTURAL removal:
delete the regions of an expression that cannot contain a metric name (string literals, `$vars`,
`{label matchers}`, `[ranges]`, `by (...)`/`on (...)` label lists), then keep every remaining
identifier that is NOT immediately applied to an argument list. `rate`, `histogram_quantile` and
whatever ships next are dropped because they are CALLED, not because they are listed.

What it gets wrong, in full:

* `{__name__="foo"}` names a family inside a label matcher; matchers are stripped, so that family is
  invisible. PANEL-side that fails loud (a demand for a panel that already exists); RULE-side it
  fails SILENT -- the family never enters `alerted_families()`, so nothing asks for its panel or its
  keep-list admission. No such expression exists in this repo, and one would have to be written by
  hand: no board or rule here selects by `__name__`.
* a recording rule (`level:metric:op`) is indistinguishable from a raw family and would be required
  to have a panel like any other. None exist today.
* an expression that is not valid PromQL yields junk names rather than an error. Grafana's own push
  is the syntax gate; this file is not a linter.
* the host-scope reader (assertion 3) splits a `host=~"a|b"` value on `|`. A value carrying any
  other regex metacharacter is read as "matches any host" instead of guessing -- which widens the
  requirement for `node_*` families and relaxes it for the rest.

`test_the_extractors_have_not_gone_blind` is what keeps a regression in any of this loud: without
it, a broken strip makes every assertion above pass vacuously, which is the quietest possible
failure.

Scope limits, so nobody reads more into a green run than it earns:

* **Panels only.** A family named solely by a template variable's `label_values(...)` query is not
  covered -- a dropdown is not a visual clue.
* **Loki is out of range.** LogQL stream selectors carry no metric families; log rules are covered
  by assertion 4 alone.
* **Assertion 3's host set for an UNSCOPED rule is only as good as the topology behind it.** A
  `node_*` family is required on every host in `KEEP_REGEX_FILES`; an app family is required on
  every host `PUBLISHER_HOSTS` maps its publishing file to. The two edges:
  - a publisher under `cli/**` maps to no host -- a daemon's source says nothing about which machine
    runs it -- so those families fall back to "admitted somewhere on the fleet". Dropping such a
    family from ONE host's keep-regex while another still admits it passes here.
  - `KEEP_REGEX_FILES` is hand-pinned, not derived. A host added to the fleet and not to that dict
    is outside every fleet-wide requirement. It is a five-entry dict next to the four config paths
    it names, and adding a host without its keep-regex file is not a silent edit.
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

# `host` LABEL VALUE -> the config.alloy that renders that host's keep-regex. The two capture hosts
# share one file: one role serves both, and `host=~"zcrypto|zcrypto-red"` selects them by label.
#
# This dict is also the FLEET TOPOLOGY, and that second job is why it is hand-pinned rather than
# globbed: it is what an unscoped `node_*` rule is measured against. Deriving that set from the
# keep-regexes instead makes the whole assertion circular -- see the module docstring.
KEEP_REGEX_FILES = {
    "nas": REPO / "infra/nas/config.alloy",
    "ops": REPO / "infra/ansible/roles/ops/files/config.alloy",
    "zcrypto": REPO / "infra/ansible/roles/capture/files/config.alloy",
    "zcrypto-red": REPO / "infra/ansible/roles/capture/files/config.alloy",
    "zaccess": REPO / "infra/ansible/roles/access/files/config.alloy",
}

# Where a producer LIVES -> the hosts that run it, so an unscoped rule over an app family can still
# be pinned per host. Ansible roles carry the deployment target in their path, which makes this
# derivable from `published_app_families()` rather than from a per-host list of series.
#
# `cli/**` maps to nothing on purpose: a daemon's source says nothing about which machine runs it,
# and guessing would be worse than the honest "admitted somewhere on the fleet".
PUBLISHER_HOSTS = (
    ("infra/ansible/roles/access/", ("zaccess",)),
    # The ops-side half of the same probe pair. Both ends publish `zaccess_wireguard_handshake_age_
    # seconds` and `zaccess_tls_not_after_seconds` (spec 00084 D11) and `host` tells them apart, so
    # "the publisher" is genuinely two hosts and either end can go dark on its own.
    ("infra/ansible/roles/access_ops/", ("ops",)),
    ("infra/ansible/roles/ops/", ("ops",)),
    ("infra/ansible/roles/capture/", ("zcrypto", "zcrypto-red")),
    # The engine runs on the capture primary only; its textfiles are admitted by the shared capture
    # keep-regex, so both capture hosts satisfy the requirement either way.
    ("infra/ansible/roles/engine/", ("zcrypto",)),
    ("infra/nas/", ("nas",)),
)


# --- Deliberate exclusions ----------------------------------------------------------------------
# Families deliberately drawn by no panel. Each entry is a REVIEWED decision and the reason IS the
# entry: a bare name here is drift wearing a test's clothes.
#
# The bar for adding one: charting the family would actively mislead, or it is a duplicate view of
# one already charted. "We ran out of room" is not a reason -- densify the layout instead. And an
# entry is only legitimate while some assertion would otherwise DEMAND that family: an entry nothing
# asks for is a standing pre-waiver for a rule that has not been written yet, which
# `test_the_not_charted_exclusions_stay_reviewed` now refuses.
#
# `node_filesystem_free_bytes` is the case that taught this: charted nowhere, admitted on
# nas/ops/capture, and named by no rule -- so nothing asks for it and it needs no entry. If a rule
# ever thresholds on it, that rule owes a panel like any other; what it must NOT get is a `free`
# series plotted beside the avail-based lines the other three filesystem rules page on, since `free`
# counts the root-reserved blocks `avail` excludes and the two percentages differ.
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


_HOST_MATCHER = re.compile(r'\bhost\s*(=~|=)\s*"([^"]*)"')
# `|` is the only metacharacter a host matcher uses in this repo; anything else and the value is not
# an alternation this file may enumerate.
_PLAIN_ALTERNATION = re.compile(r"[A-Za-z0-9_.-]+(?:\|[A-Za-z0-9_.-]+)*\Z")


def selected_hosts(expr: str, family: str) -> frozenset[str] | None:
    """The `host` label values `family`'s selectors name in `expr`, or None when any occurrence of
    it is host-unscoped (no matcher, a negative matcher, or a regex this file will not enumerate).

    Per-occurrence rather than per-expression: `node_load1{host=~"zcrypto|zcrypto-red"} / on(host)
    ... node_cpu_seconds_total{host=~"zcrypto|zcrypto-red", mode="idle"}` scopes two families, and
    an expression-wide read would hand each of them the other's hosts."""
    occurrence = re.compile(rf"(?<![A-Za-z0-9_:]){re.escape(family)}(?![A-Za-z0-9_:])\s*(\{{[^{{}}]*\}})?")
    hosts: set[str] = set()
    for match in occurrence.finditer(expr):
        matcher = _HOST_MATCHER.search(match.group(1) or "")
        if matcher is None or not _PLAIN_ALTERNATION.match(matcher.group(2)):
            return None
        hosts.update(matcher.group(2).split("|"))
    return frozenset(hosts) or None


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


@cache
def panel_families() -> dict[str, frozenset[str]]:
    """family -> the panels drawing it, as `<file> <uid>#<panelId> "<title>"`."""
    found: dict[str, set[str]] = {}
    for filename, dash in dashboards():
        for panel in _walk_panels(dash.get("panels") or []):
            where = f"{filename} {dash.get('uid')}#{panel.get('id')} {panel.get('title')!r}"
            for target in _prom_targets(panel):
                for family in promql_families(target.get("expr") or ""):
                    found.setdefault(family, set()).add(where)
    return {k: frozenset(v) for k, v in found.items()}


# --- What this repo publishes ---------------------------------------------------------------------
# Three publication mechanisms, three patterns. Anything a producer emits reaches Grafana through one
# of them, and each canary in `test_the_publisher_scan_still_finds_each_source_kind` pins one path:
# if a path breaks, every family it used to find silently drops out of assertion 2's candidate set.
#
# Scope is the three namespaces this repo's own producers publish into. `node_*`, `process_*` and
# `hc_*` come from node-exporter, prometheus_client and healthchecks.io -- not ours to chart
# exhaustively, and the alert layer (assertion 1) already pulls in the ones that matter.
_APP = r"(?:zcrypto|ops|zaccess)_[a-z0-9_]*[a-z0-9]"
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
# `cli/archive/command.py` assembles every reconcile series as `f"zcrypto_reconcile_{name}"`, so no
# name-shaped scan can see one -- only the `_emit(<suffix>, ...)` call sites can. Derived rather than
# hand-listed so a new reconcile series joins the candidate set on the commit that adds it.
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


# --- Keep-regex admission --------------------------------------------------------------------------
@cache
def keep_regexes() -> dict[str, re.Pattern[str]]:
    """host -> the anchored keep-regex its config.alloy installs on the remote_write path."""
    compiled = {}
    for host, path in KEEP_REGEX_FILES.items():
        blocks = re.findall(r"write_relabel_config\s*\{(.*?)\}", path.read_text(), re.DOTALL)
        keeps = [b for b in blocks if "action" in b and '"keep"' in b]
        assert len(keeps) == 1, f"{path}: expected exactly one keep block, found {len(keeps)}"
        match = re.search(r'regex\s*=\s*"([^"]+)"', keeps[0])
        assert match, f"{path}: keep block has no regex"
        compiled[host] = re.compile(r"\A(?:" + match.group(1) + r")\Z")  # relabel regexes are fully anchored
    return compiled


def publishing_hosts(family: str) -> frozenset[str] | None:
    """The hosts that run `family`'s producer, read off the publishing file's path via
    `PUBLISHER_HOSTS`. None when no path maps -- a `cli/**` daemon, whose source cannot say which
    machine runs it."""
    hosts: set[str] = set()
    for where in published_app_families().get(family, ()):
        for prefix, mapped in PUBLISHER_HOSTS:
            if where.startswith(prefix):
                hosts.update(mapped)
    return frozenset(hosts) or None


# Why each host in an expectation is on the hook, carried through so the failure message can say it.
_BECAUSE_SELECTED = "selects that host"
_BECAUSE_FLEET_WIDE = "names no host, so it is a fleet-wide guard over the whole topology"
_BECAUSE_PUBLISHED = "names no host, and this repo publishes the family on that host"


def _admission_expectations() -> list[tuple[str, str, frozenset[str] | None, str]]:
    """`(rule uid, family, hosts that must admit it, why)` for every alerted family, once per rule
    that names it. `None` hosts means "somewhere on the fleet" -- the honest bar when the rule names
    no host AND nothing in the tree says which machine publishes the family."""
    expectations = []
    for rule in _rules():
        for expr in _prom_expressions(rule):
            for family in promql_families(expr):
                hosts, why = selected_hosts(expr, family), _BECAUSE_SELECTED
                if hosts is None:
                    # An unscoped `node_*` rule is fleet-wide: every host runs a node exporter, and a
                    # host whose keep-list omits the family is structurally unable to fail the rule.
                    # The topology comes from KEEP_REGEX_FILES, NEVER from the regexes it audits.
                    if family.startswith("node_"):
                        hosts, why = frozenset(KEEP_REGEX_FILES), _BECAUSE_FLEET_WIDE
                    else:
                        hosts, why = publishing_hosts(family), _BECAUSE_PUBLISHED
                expectations.append((rule["uid"], family, hosts, why))
    return expectations


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
    """A producer we ship is a producer we can watch break. Publishing into a dashboard nobody drew is
    how the `zcrypto_capture_*` and `zcrypto_engine_*` families stayed invisible for months."""
    uncovered = sorted(set(published_app_families()) - set(panel_families()) - set(NOT_CHARTED))
    report = "\n".join(f"    {f}\n{_describe(f)}" for f in uncovered)
    assert not uncovered, (
        f"{len(uncovered)} app-level metric families this repo publishes are drawn by no panel on any"
        f" committed dashboard:\n{report}\n"
        f"  Fix: add a panel referencing the family to a dashboard under infra/grafana/{DASHBOARD_GLOB},"
        f" or add a reasoned entry to NOT_CHARTED in {Path(__file__).name}."
    )


# --- (3) every alerted family is admitted where its rule selects -----------------------------------
def test_every_alerted_family_is_admitted_where_its_rule_selects():
    """A `keep` relabel drops every series it does not list, so a family missing from a host's
    keep-regex does not go unwatched on that host -- it does not EXIST there, and a rule selecting
    that host can never match it. The rule stays green, the host stays invisible, and nothing
    distinguishes that from a healthy fleet."""
    keeps, problems = keep_regexes(), []
    for uid, family, hosts, why in sorted(_admission_expectations()):
        if hosts is None:
            if not any(keep.match(family) for keep in keeps.values()):
                problems.append(
                    f"    {family} -- rule {uid} names no host, and NO host's keep-regex admits it, so the"
                    f" rule reads NoData forever"
                )
            continue
        for host in sorted(hosts):
            if host not in keeps:
                problems.append(
                    f"    {family} on {host} -- rule {uid} {why}, but {host!r} is not in KEEP_REGEX_FILES, so"
                    f" this file cannot say whether it admits the family. Add the host and its config.alloy,"
                    f" or correct the matcher (`host` carries a MIRROR SIDE on some reconcile series)."
                )
                continue
            if not keeps[host].match(family):
                problems.append(
                    f"    {family} on {host} -- rule {uid} {why}, but {KEEP_REGEX_FILES[host].relative_to(REPO)}'s"
                    f" keep-regex drops it: that host is structurally unable to fail this alert"
                )
    assert not problems, (
        "alert rules select hosts whose keep-regex drops the family they watch:\n"
        + "\n".join(problems)
        + "\n  Fix: add the family to that host's config.alloy keep-regex (and to the host's `required`"
        " list in test_infra_alloy_series.py), or scope the rule to the hosts that do publish it."
    )


# --- (4) the alert points at the panel -------------------------------------------------------------
# A rule whose signal is genuinely not panel-shaped (a pure log-content rule) may name a runbook
# section instead. `test_infra_alert_rules.py` already proves that every cited anchor resolves; this
# only asks whether one is cited at all.
_RUNBOOK_REFERENCE = re.compile(r"infra/runbooks/README\.md#[A-Za-z0-9._-]+")


def _annotations(rule: dict) -> dict:
    return rule.get("annotations") or {}


def _cites_a_runbook(rule: dict) -> bool:
    annotations = _annotations(rule)
    return "runbook_url" in annotations or any(_RUNBOOK_REFERENCE.search(str(v)) for v in annotations.values())


def test_every_panel_id_annotation_is_a_string():
    """`grafana-push.sh` does `yaml.safe_load` -> `json.dumps` and Grafana's annotations are
    `map[string]string`, so an unquoted `305` arrives as a JSON number, the provisioning API rejects
    the rule with a bare 400, and `curl -fsS` under `set -euo pipefail` aborts the ENTIRE push --
    every rule and every dashboard, not just this one. The blast radius is why this is its own
    assertion: nothing else in the tree reads `__panelId__` at all."""
    wrong = [
        (r["uid"], type(_annotations(r)["__panelId__"]).__name__)
        for r in _rules()
        if "__panelId__" in _annotations(r) and not isinstance(_annotations(r)["__panelId__"], str)
    ]
    assert not wrong, f"__panelId__ must be a QUOTED string in alerts.yaml -- an unquoted id aborts the whole push: {wrong}"


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
    # (the `_IDENT` lookbehind) are the two ways this extractor degrades into nonsense.
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
    ],
)
def test_the_publisher_scan_still_finds_each_source_kind(family):
    assert family in published_app_families(), (
        f"{family} is no longer discovered by the publisher scan. Either its producer moved or was"
        f" renamed (update this canary) or a discovery path broke -- in which case every family that"
        f" path used to find is now silently exempt from coverage."
    )
