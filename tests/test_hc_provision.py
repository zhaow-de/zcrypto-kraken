"""`infra/scripts/hc-provision.py` against a stubbed v3 API, the dead-man service's, answering as it answers a read-only
and a read-write key, with every vault read stubbed: nothing here reaches a network or a vault."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import urllib.error
import uuid as uuidlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_SCRIPT = REPO / "infra" / "scripts" / "hc-provision.py"
_spec = importlib.util.spec_from_file_location("hc_provision", _SCRIPT)
hp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hp)

CLONE = "https://zcrypto-hc.zhaow.me/api/v3/"

CLONE_RW = "hcRW5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c"
CLONE_RO = "hcRO9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e"
KEYS = {
    ("hc_readwrite_api_key", "group_vars/all/vault.yml"): CLONE_RW,
    ("hc_readonly_api_key", "group_vars/observed/vault.yml"): CLONE_RO,
}


def test_the_services_read_only_key_is_the_daily_passs_constant():
    assert hp.SERVICE_READ is hp.ops_daily.DEADMAN_READONLY_KEY
    assert hp.SERVICE_READ == ("hc_readonly_api_key", "group_vars/observed/vault.yml")


# The tree's fixture names the fleet's checks; the definitions below are this file's own.
_TREE = [
    row for row in json.loads((REPO / "tests/fixtures/healthchecks_descriptions.json").read_text()) if row["name"] != "zcrypto-hc"
]
NAMES = sorted(row["name"] for row in _TREE)
CRON = "zcrypto-verify-replay"
SELF = "zcrypto-hc"
CHECKS = sorted([*NAMES, SELF])
_SECRET_FIELDS = ("uuid", "ping_url", "update_url", "pause_url", "resume_url", "channels")
_DEFINITION = ("name", "tags", "desc", "grace", "manual_resume", "timeout", "schedule", "tz")


def _definitions() -> list[dict]:
    out = []
    for i, row in enumerate(sorted(_TREE, key=lambda r: r["name"])):
        period = {"schedule": "41 3 * * *", "tz": "Europe/Berlin"} if row["name"] == CRON else {"timeout": 600 + 60 * i}
        out.append(
            {"name": row["name"], "tags": row["tags"], "desc": row["desc"], "grace": 300 + i, "manual_resume": False, **period}
        )
    return out


class _Answer:
    def __init__(self, status: int, raw: bytes):
        self.status, self._raw = status, raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *args):
        return self._raw


class _Service:
    """One v3 API: its checks by uuid and its integrations; a read-only key lists, a read-write key does everything."""

    def __init__(self, base: str, ping: str, *, ro: str, rw: str):
        self.base, self.ping, self.ro, self.rw = base, ping, ro, rw
        self.checks: dict[str, dict] = {}
        self.integrations: list[dict] = []
        self.refuse: dict[tuple[str, str], int] = {}  # (method, "checks/" | "channels/" | a check's name) -> status
        self.read_as: dict[str, dict] = {}  # a check's name -> fields its read-back answers in place of the stored ones
        self.raw: dict[tuple[str, str], bytes] = {}  # (method, path) -> a body that is not the JSON the API sends

    def add(self, **fields) -> str:
        u = str(uuidlib.uuid4())
        self.checks[u] = {
            "uuid": u,
            "ping_url": f"{self.ping}{u}",
            "update_url": f"{self.base}checks/{u}",
            "pause_url": f"{self.base}checks/{u}/pause",
            "resume_url": f"{self.base}checks/{u}/resume",
            "channels": "",
            **fields,
        }
        return u

    def integration(self, kind: str, **fields) -> str:
        u = str(uuidlib.uuid4())
        self.integrations.append({"id": u, "name": f"the {kind} integration", "kind": kind, "disabled": False, **fields})
        return u

    def by_name(self, name: str) -> dict:
        (check,) = [c for c in self.checks.values() if c["name"] == name]
        return check

    def secrets(self) -> set[str]:
        return {c[f] for c in self.checks.values() for f in ("uuid", "ping_url", "update_url")} | {
            i["id"] for i in self.integrations
        }

    def _view(self, check: dict, key: str) -> dict:
        shown = copy.deepcopy(check)
        if key == self.rw:
            return shown
        for field in _SECRET_FIELDS:
            shown.pop(field, None)
        return {**shown, "unique_key": hashlib.sha1(check["uuid"].encode()).hexdigest()}

    def answer(self, method: str, path: str, key: str | None, body: dict | None) -> tuple[int, object]:
        u = path.removeprefix("checks/")
        target = path if path in ("checks/", "channels/") else self.checks.get(u, {}).get("name", path)
        if (method, target) in self.refuse:
            return self.refuse[(method, target)], {"error": "refused"}
        if key not in (self.ro, self.rw):
            return 401, {"error": "missing or invalid API key"}
        if (method, path) == ("GET", "checks/"):
            return 200, {"checks": [self._view(c, key) for c in self.checks.values()]}
        if (method, path) == ("GET", "channels/"):
            return 200, {"channels": copy.deepcopy(self.integrations)}
        if key != self.rw:
            return 401, {"error": "this API key is read-only"}
        if (method, path) == ("POST", "checks/"):
            return self._upsert(body)
        if u not in self.checks:
            return 404, {"error": "not found"}
        if method == "GET":
            return 200, {**self._view(self.checks[u], key), **self.read_as.get(self.checks[u]["name"], {})}
        return 405, {"error": "method not allowed"}

    def _upsert(self, body: dict) -> tuple[int, dict]:
        fields = {k: v for k, v in body.items() if k != "unique"}
        same = [c for c in self.checks.values() if "name" in body.get("unique", ()) and c["name"] == body["name"]]
        if same:
            check = same[0]
            for gone in ("schedule", "tz") if "timeout" in fields else ("timeout",) if "schedule" in fields else ():
                check.pop(gone, None)
            check.update(fields)
            return 200, self._view(check, self.rw)
        period = {"tz": "UTC"} if "schedule" in fields else {"timeout": 86400}
        new = {"tags": "", "desc": "", "grace": 3600, "manual_resume": False, **period}
        u = self.add(**(new | fields), n_pings=0, status="new", last_ping=None)
        return 201, self._view(self.checks[u], self.rw)


class _Fleet:
    def __init__(self, monkeypatch, tmp_path, *, definitions=None):
        self.clone = _Service(CLONE, "https://zcrypto-hc.zhaow.me/ping/", ro=CLONE_RO, rw=CLONE_RW)
        self.slack = self.clone.integration("slack")
        self.email = self.clone.integration("email")
        self.requests: list[tuple[str, str, str | None, dict | None, float]] = []
        self.vault: list[tuple[str, str]] = []
        self.fixture = tmp_path / "healthchecks_descriptions.json"
        self.fixture.write_text(json.dumps(_definitions() if definitions is None else definitions, indent=2))
        monkeypatch.setattr(hp, "FIXTURE", self.fixture)
        monkeypatch.setattr(hp.grafana_auth, "vault_var", self._vault_var)
        monkeypatch.setattr(hp.urllib.request, "urlopen", self._urlopen)

    def _vault_var(self, name: str, vault_file: str) -> str:
        self.vault.append((name, vault_file))
        return KEYS[(name, vault_file)]

    def _urlopen(self, request, timeout):
        url, method = request.full_url, request.get_method()
        body = json.loads(request.data) if request.data else None
        self.requests.append((method, url, request.get_header("X-api-key"), body, timeout))
        service = self.clone
        assert url.startswith(service.base), url
        path = url.removeprefix(service.base)
        if (method, path) in service.raw:
            return _Answer(200, service.raw[(method, path)])
        status, answer = service.answer(method, path, request.get_header("X-api-key"), body)
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "refused", None, io.BytesIO(json.dumps(answer).encode()))
        return _Answer(status, json.dumps(answer).encode())

    def creates(self) -> list[dict]:
        return [body for method, url, _, body, _ in self.requests if method == "POST"]

    def secrets(self) -> set[str]:
        return set(KEYS.values()) | self.clone.secrets()

    def moved(self, *names: str) -> None:
        for name in names or CHECKS:
            self.clone.by_name(name).update(status="up", n_pings=12, last_ping="2026-11-08T09:59:00+00:00")


def _run(capsys, *argv: str) -> tuple[int, str, str]:
    rc = hp.main(list(argv))
    out = capsys.readouterr()
    return rc, out.out, out.err


def _expected(fleet: _Fleet, definitions: list[dict]) -> list[dict]:
    bodies = []
    for d in sorted(definitions, key=lambda d: d["name"]):
        period = {"timeout": d["timeout"]} if "timeout" in d else {"schedule": d["schedule"], "tz": d["tz"]}
        body = {"name": d["name"], "slug": d["name"], "tags": d["tags"], "desc": d["desc"], "grace": d["grace"], **period}
        bodies.append({**body, "channels": fleet.slack, "manual_resume": False, "unique": ["name"]})
    return bodies


def _the_checks(fleet: _Fleet) -> list[dict]:
    return _expected(fleet, [*_definitions(), hp.ZCRYPTO_HC])


@pytest.fixture
def fleet(monkeypatch, tmp_path) -> _Fleet:
    return _Fleet(monkeypatch, tmp_path)


@pytest.fixture
def provisioned(fleet, capsys) -> _Fleet:
    """Every check on the service, each pinged and up, the fixture fetched from it."""
    assert _run(capsys, "apply")[0] == 0
    fleet.moved()
    assert _run(capsys, "fixture")[0] == 0
    return fleet


def test_the_service_own_check_is_defined_here_with_its_runbook():
    assert {k: hp.ZCRYPTO_HC[k] for k in ("name", "tags", "timeout", "grace", "manual_resume")} == {
        "name": "zcrypto-hc",
        "tags": "hc selfcheck",
        "timeout": 600,
        "grace": 600,
        "manual_resume": False,
    }
    assert "Runbook: infra/runbooks/hc.md#hc-dark" in hp.ZCRYPTO_HC["desc"]


def test_apply_writes_the_checks_the_fixture_defines_and_the_service_own_check(fleet, capsys):
    rc, out, err = _run(capsys, "apply")
    assert rc == 0, err
    assert fleet.creates() == _the_checks(fleet)
    assert sorted(c["name"] for c in fleet.clone.checks.values()) == CHECKS


def test_a_fleet_name_the_fixture_carries_twice_ends_the_run_naming_it(monkeypatch, tmp_path, capsys):
    fleet = _Fleet(monkeypatch, tmp_path, definitions=[*_definitions(), _definitions()[3]])
    rc, out, err = _run(capsys, "apply")
    assert rc == 2 and _definitions()[3]["name"] in err and "twice" in err
    assert fleet.creates() == []


def test_every_create_asks_for_its_name_to_be_unique(fleet, capsys):
    assert _run(capsys, "apply")[0] == 0
    assert [body.get("unique") for body in fleet.creates()] == [["name"]] * 13
    assert _run(capsys, "apply")[0] == 0
    assert len(fleet.clone.checks) == 13, "a second run updates and never duplicates"


def test_every_create_resumes_on_its_next_ping_whatever_the_fixture_holds(monkeypatch, tmp_path, capsys):
    definitions = _definitions()
    definitions[0]["manual_resume"] = True
    fleet = _Fleet(monkeypatch, tmp_path, definitions=definitions)
    assert _run(capsys, "apply")[0] == 0
    assert [body.get("manual_resume") for body in fleet.creates()] == [False] * 13


def test_every_create_carries_the_one_slack_integration_and_no_other(fleet, capsys):
    assert _run(capsys, "apply")[0] == 0
    assert {body.get("channels") for body in fleet.creates()} == {fleet.slack}


def test_a_cron_check_is_written_with_its_schedule_and_tz_and_no_timeout(fleet, capsys):
    assert _run(capsys, "apply")[0] == 0
    (body,) = [b for b in fleet.creates() if b["name"] == CRON]
    assert (body.get("schedule"), body.get("tz"), "timeout" in body) == ("41 3 * * *", "Europe/Berlin", False)


@pytest.mark.parametrize(
    ("name", "read_as", "field"),
    [
        ("zcrypto-capture", lambda f: {"grace": 60}, "grace"),
        ("zcrypto-capture", lambda f: {"timeout": 86400}, "timeout"),
        (CRON, lambda f: {"schedule": "* * * * *"}, "schedule"),
        (CRON, lambda f: {"tz": "UTC"}, "tz"),
        ("zcrypto-panel", lambda f: {"channels": ""}, "channels"),
        ("zcrypto-panel", lambda f: {"channels": f"{f.slack},{f.email}"}, "channels"),
        (SELF, lambda f: {"manual_resume": True}, "manual_resume"),
        ("zcrypto-capture", lambda f: {"slug": "zcrypto-capture-1"}, "slug"),
    ],
    ids=["grace", "timeout", "schedule", "tz", "no channel", "a second channel", "manual_resume", "slug"],
)
def test_a_read_back_differing_from_its_definition_ends_the_run_naming_the_check(fleet, capsys, name, read_as, field):
    fleet.clone.read_as[name] = read_as(fleet)
    rc, out, err = _run(capsys, "apply")
    assert rc == 2
    (line,) = [line for line in err.splitlines() if name in line]
    assert field in line
    assert not [n for n in CHECKS if n != name and n in err], err


def test_a_fixture_fetched_from_the_service_writes_the_same_checks_again(fleet, capsys):
    assert _run(capsys, "apply")[0] == 0
    assert _run(capsys, "fixture")[0] == 0
    first = fleet.creates()
    fleet.requests.clear()
    fleet.clone.checks.clear()
    rc, out, err = _run(capsys, "apply")
    assert rc == 0, err
    assert fleet.creates() == first == _the_checks(fleet)


def test_the_committed_fixture_reads_as_the_definitions_apply_writes():
    assert [definition["name"] for definition in hp._checks("the fixture")] == CHECKS


def test_two_slack_integrations_are_refused_before_any_write(fleet, capsys):
    fleet.clone.integration("slack")
    rc, out, err = _run(capsys, "apply")
    assert rc == 2 and "Slack" in err
    assert fleet.creates() == []


def test_no_slack_integration_is_refused_before_any_write(fleet, capsys):
    fleet.clone.integrations = [row for row in fleet.clone.integrations if row["kind"] != "slack"]
    rc, out, err = _run(capsys, "apply")
    assert rc == 2 and "0 Slack integrations" in err, err
    assert fleet.creates() == []


def test_an_integrations_listing_without_the_disabled_flag_stops_apply_and_status(fleet, capsys):
    for row in fleet.clone.integrations:
        del row["disabled"]
    for verb in ("apply", "status"):
        rc, out, err = _run(capsys, verb)
        assert rc == 2 and "v6.2.0" in err and fleet.slack[:8] in err and fleet.slack not in err + out, (verb, err)
        assert not [name for name in CHECKS if name in out], (verb, out)
    assert fleet.creates() == []


def test_a_disabled_slack_integration_stops_apply_and_status_naming_its_kind_and_id_prefix(fleet, capsys):
    assert _run(capsys, "apply")[0] == 0
    fleet.requests.clear()
    fleet.clone.integrations[0]["disabled"] = True
    for verb in ("apply", "status"):
        rc, out, err = _run(capsys, verb)
        assert rc == 2, verb
        assert "slack" in err and fleet.slack[:8] in err and fleet.slack not in err + out, (verb, err)
        assert not [name for name in CHECKS if name in out], (verb, out)
    assert fleet.creates() == []


def test_the_fixture_is_the_definitions_sorted_by_name_none_resuming_by_hand(monkeypatch, tmp_path, capsys):
    definitions = _definitions()
    definitions[0]["manual_resume"] = True
    fleet = _Fleet(monkeypatch, tmp_path, definitions=definitions)
    assert _run(capsys, "apply")[0] == 0
    fleet.requests.clear()
    rc, out, err = _run(capsys, "fixture")
    assert rc == 0, err
    rows = json.loads(fleet.fixture.read_text())
    assert [row["name"] for row in rows] == CHECKS
    for row in rows:
        period = ("timeout",) if row["name"] != CRON else ("schedule", "tz")
        assert set(row) == {"name", "tags", "desc", "grace", "manual_resume", *period}, row
        assert row["manual_resume"] is False
    assert set().union(*map(set, rows)) <= set(_DEFINITION)
    assert {key for _, _, key, _, _ in fleet.requests} == {CLONE_RO}
    assert fleet.fixture.read_text().endswith("]\n")


def test_status_names_a_zcrypto_hc_the_service_holds_otherwise_than_defined_here(fleet, capsys):
    assert _run(capsys, "apply")[0] == 0
    assert "differs" not in _run(capsys, "status")[1]
    fleet.clone.by_name(SELF).update(timeout=900, desc="Edited in the UI.")
    rc, out, err = _run(capsys, "status")
    assert rc == 0, err
    (line,) = [line for line in out.splitlines() if line.startswith("zcrypto-hc on the service differs")]
    assert "desc, timeout" in line and "apply" in line, line
    rc, out, err = _run(capsys, "fixture")
    assert rc == 0 and "differs" not in out + err


def test_status_reads_a_new_check_unmoved_and_a_pinged_up_one_moved(fleet, capsys):
    assert _run(capsys, "apply")[0] == 0
    fleet.moved("zcrypto-capture")
    rc, out, err = _run(capsys, "status")
    assert rc == 0, err
    lines = {line.split()[0]: line for line in out.splitlines() if line.split() and line.split()[0] in CHECKS}
    assert sorted(lines) == CHECKS
    assert lines["zcrypto-capture"].endswith("moved") and " up " in lines["zcrypto-capture"]
    assert not lines["zcrypto-panel"].endswith("moved") and " new " in lines["zcrypto-panel"]


def test_each_verb_reads_the_keys_it_names_and_no_other(provisioned, capsys):
    expected = {
        "apply": [("hc_readwrite_api_key", "group_vars/all/vault.yml")],
        "fixture": [("hc_readonly_api_key", "group_vars/observed/vault.yml")],
        "status": [
            ("hc_readwrite_api_key", "group_vars/all/vault.yml"),
            ("hc_readonly_api_key", "group_vars/observed/vault.yml"),
        ],
    }
    for verb, keys in expected.items():
        provisioned.vault.clear()
        assert _run(capsys, verb)[0] == 0, verb
        assert sorted(set(provisioned.vault)) == sorted(keys), verb


def test_no_key_uuid_or_ping_url_reaches_the_output_and_every_request_waits_30_seconds(provisioned, capsys):
    secrets = provisioned.secrets()
    printed = ""
    for verb in ("apply", "status", "fixture"):
        rc, out, err = _run(capsys, verb)
        assert rc == 0, (verb, err)
        printed += out + err
    assert secrets and not [s for s in secrets if s in printed]
    assert {timeout for *_, timeout in provisioned.requests} == {30}


@pytest.mark.parametrize(
    ("argv", "service", "refused", "named"),
    [
        (("apply",), "clone", ("GET", "channels/"), "integrations listing"),
        (("apply",), "clone", ("POST", "checks/"), "check write"),
        (("apply",), "clone", ("GET", "zcrypto-capture"), "check read-back for zcrypto-capture"),
        (("status",), "clone", ("GET", "checks/"), "checks listing"),
    ],
    ids=["integrations", "create", "read-back", "service listing"],
)
def test_a_500_ends_the_run_naming_the_endpoint_by_its_kind_and_no_secret(provisioned, capsys, argv, service, refused, named):
    getattr(provisioned, service).refuse[refused] = 500
    rc, out, err = _run(capsys, *argv)
    assert rc == 2 and named in err and "500" in err, err
    assert not [s for s in provisioned.secrets() if s in out + err]


def test_an_answer_that_is_not_json_ends_the_run_naming_the_endpoint(fleet, capsys):
    fleet.clone.raw[("GET", "checks/")] = b"<html>maintenance</html>"
    rc, out, err = _run(capsys, "status")
    assert rc == 2 and "the dead-man service's checks listing answered 200 with a body that is not JSON" in err, err


def test_a_create_answered_without_a_uuid_ends_the_run_naming_the_check(fleet, capsys, monkeypatch):
    upsert = fleet.clone._upsert

    def no_uuid(body):
        status, answer = upsert(body)
        return status, {k: v for k, v in answer.items() if k != "uuid" or body["name"] != "zcrypto-mon"}

    monkeypatch.setattr(fleet.clone, "_upsert", no_uuid)
    rc, out, err = _run(capsys, "apply")
    assert rc == 2 and "check write for zcrypto-mon" in err, err
