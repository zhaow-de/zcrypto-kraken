"""Guard: `infra/grafana/alerts.yaml` is pushed to Grafana Cloud's provisioning API by
`infra/scripts/grafana-push.sh`, and the API rejects a malformed rule with a bare HTTP 400 whose
body the script discards. That failure mode is expensive out of proportion to its cause: it needs a
vaulted token and a TTY for the GPG pinentry, so it can only be discovered during an attended push,
and the operator sees `curl: (22) ... error: 400` with no indication of which rule or which field.

Every constraint pinned here is one the API enforces silently and the repo previously did not. The
40-char UID limit cost a full attended round-trip on 2026-07-20 (a 41-char uid); note that the
longest surviving uid is exactly 40, so the ceiling is real and routinely approached."""

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
ALERTS = REPO / "infra/grafana/alerts.yaml"

# Grafana's alert-rule UID column is `varchar(40)`, and the provisioning API's OpenAPI spec declares
# `maxLength: 40`. A uid is IMMUTABLE once the rule exists, so an update never carries a new uid --
# the length is therefore only ever tested at creation, and a too-long uid breaks exactly once, on
# the run that first introduces it, which is when the diagnosis is hardest. (It is not that updates
# skip a validation: they simply never present a fresh uid to validate.)
_UID_MAX = 40

# The provisioning API's enums. A value outside these is a 400, not a validation message.
_NO_DATA_STATES = {"Alerting", "NoData", "OK"}
_EXEC_ERR_STATES = {"Alerting", "Error", "OK"}


def _rules():
    return yaml.safe_load(ALERTS.read_text())["rules"]


def test_alert_rule_uids_fit_grafanas_column():
    over = [(r["uid"], len(r["uid"])) for r in _rules() if len(r["uid"]) > _UID_MAX]
    assert not over, f"uid longer than Grafana's {_UID_MAX}-char limit -- the create call will 400: {over}"


def test_alert_rule_uids_are_unique():
    uids = [r["uid"] for r in _rules()]
    dupes = sorted({u for u in uids if uids.count(u) > 1})
    assert not dupes, f"duplicate uid -- the second push silently overwrites the first: {dupes}"


@pytest.mark.parametrize("field,allowed", [("noDataState", _NO_DATA_STATES), ("execErrState", _EXEC_ERR_STATES)])
def test_alert_rule_states_are_valid_enums(field, allowed):
    bad = [(r["uid"], r.get(field)) for r in _rules() if r.get(field) not in allowed]
    assert not bad, f"{field} outside the API's enum {sorted(allowed)}: {bad}"


def test_every_rule_has_the_fields_the_api_requires():
    # Omitting any of these is a 400. `condition` must also name a refId that exists in `data`,
    # which the API checks but does not explain.
    required = ("uid", "title", "condition", "data", "noDataState", "execErrState", "for", "ruleGroup", "folderUID")
    problems = []
    for r in _rules():
        missing = [f for f in required if f not in r]
        if missing:
            problems.append((r.get("uid", "<no uid>"), f"missing {missing}"))
            continue
        refids = {d.get("refId") for d in r["data"]}
        if r["condition"] not in refids:
            problems.append((r["uid"], f"condition {r['condition']!r} not among data refIds {sorted(refids)}"))
    assert not problems, f"rules the provisioning API would reject: {problems}"


def test_datasource_uids_are_templated_not_hardcoded():
    # grafana-push.sh substitutes ${GRAFANA_*_DS_UID} at push time. A hardcoded uid silently
    # repoints a rule at another datasource -- the API accepts it and reports health=ok (T0034),
    # so the push-time read-back is the only other thing that would catch it.
    allowed = {"${GRAFANA_PROM_DS_UID}", "${GRAFANA_LOKI_DS_UID}", "__expr__"}
    bad = [(r["uid"], d.get("datasourceUid")) for r in _rules() for d in r["data"] if d.get("datasourceUid") not in allowed]
    assert not bad, f"datasourceUid neither templated nor the expression node: {bad}"
