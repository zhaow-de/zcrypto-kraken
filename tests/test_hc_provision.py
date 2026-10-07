"""`infra/scripts/hc-provision.py` against two stubbed v3 APIs, healthchecks.io's and the dead-man service's, answering
as each answers a read-only and a read-write key, with every vault read stubbed: nothing here reaches a network or
a vault."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import urllib.error
import uuid as uuidlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_SCRIPT = REPO / "infra" / "scripts" / "hc-provision.py"
_spec = importlib.util.spec_from_file_location("hc_provision", _SCRIPT)
hp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hp)

HCIO = "https://healthchecks.io/api/v3/"
CLONE = "https://zcrypto-hc.zhaow.me/api/v3/"

HCIO_RO = "hcioRO0f1e2d3c4b5a69788796a5b4c3d2e1f0"
HCIO_RW = "hcioRWa1b2c3d4e5f60718293a4b5c6d7e8f90"
CLONE_RW = "hcRW5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c"
CLONE_RO = "hcRO9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e"
KEYS = {
    ("healthchecks_readonly_api_key", "group_vars/all/vault.yml"): HCIO_RO,
    ("healthchecks_api_key", "group_vars/capture_host/vault.yml"): HCIO_RW,
    ("hc_readwrite_api_key", "group_vars/all/vault.yml"): CLONE_RW,
    ("hc_readonly_api_key", "group_vars/observed/vault.yml"): CLONE_RO,
}
HCIO_KEYS = ("healthchecks_readonly_api_key", "healthchecks_api_key")

# The tree's fixture names the fleet's checks; the definitions below are this file's own.
_TREE = [
    row for row in json.loads((REPO / "tests/fixtures/healthchecks_descriptions.json").read_text()) if row["name"] != "zcrypto-hc"
]
NAMES = sorted(row["name"] for row in _TREE)
CRON = "zcrypto-verify-replay"
SELF = "zcrypto-hc"
TWELVE = sorted([*NAMES, SELF])
_SECRET_FIELDS = ("uuid", "ping_url", "update_url", "pause_url", "resume_url", "channels")
_DEFINITION = ("name", "tags", "desc", "grace", "manual_resume", "timeout", "schedule", "tz")


def _ago(**delta) -> str:
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat(timespec="seconds")


def _source_row(i: int, row: dict) -> dict:
    period = {"schedule": "41 3 * * *", "tz": "Europe/Berlin"} if row["name"] == CRON else {"timeout": 600 + 60 * i}
    return {
        "name": row["name"],
        "slug": row["name"],
        "tags": row["tags"],
        "desc": row["desc"],
        "grace": 300 + i,
        "n_pings": 1000 + i,
        "status": "up",
        "started": False,
        "last_ping": _ago(days=2),
        "next_ping": None,
        "manual_resume": False,
        "methods": "",
        **period,
    }


def _source() -> list[dict]:
    return [_source_row(i, row) for i, row in enumerate(sorted(_TREE, key=lambda r: r["name"]))]


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
        self.kept_on_delete: set[str] = set()
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
        if method == "DELETE":
            check = self.checks[u] if self.checks[u]["name"] in self.kept_on_delete else self.checks.pop(u)
            return 200, self._view(check, key)
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
    def __init__(self, monkeypatch, tmp_path, *, source=None):
        self.hcio = _Service(HCIO, "https://hc-ping.com/", ro=HCIO_RO, rw=HCIO_RW)
        self.clone = _Service(CLONE, "https://zcrypto-hc.zhaow.me/ping/", ro=CLONE_RO, rw=CLONE_RW)
        for row in _source() if source is None else source:
            self.hcio.add(**row)
        self.slack = self.clone.integration("slack")
        self.email = self.clone.integration("email")
        self.requests: list[tuple[str, str, str | None, dict | None, float]] = []
        self.vault: list[tuple[str, str]] = []
        self.unreadable: set[str] = set()
        self.fixture = tmp_path / "healthchecks_descriptions.json"
        self.fixture.write_text(json.dumps([{"name": r["name"], "tags": r["tags"], "desc": r["desc"]} for r in _TREE], indent=2))
        monkeypatch.setattr(hp, "FIXTURE", self.fixture)
        monkeypatch.setattr(hp.grafana_auth, "vault_var", self._vault_var)
        monkeypatch.setattr(hp.urllib.request, "urlopen", self._urlopen)

    def _vault_var(self, name: str, vault_file: str) -> str:
        self.vault.append((name, vault_file))
        if name in self.unreadable:
            raise KeyError(name)
        return KEYS[(name, vault_file)]

    def _urlopen(self, request, timeout):
        url, method = request.full_url, request.get_method()
        body = json.loads(request.data) if request.data else None
        self.requests.append((method, url, request.get_header("X-api-key"), body, timeout))
        service = self.hcio if url.startswith(HCIO) else self.clone
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

    def deletes(self) -> list[str]:
        return [url for method, url, *_ in self.requests if method == "DELETE"]

    def secrets(self) -> set[str]:
        return set(KEYS.values()) | self.hcio.secrets() | self.clone.secrets()

    def moved(self, *names: str) -> None:
        for name in names or TWELVE:
            self.clone.by_name(name).update(status="up", n_pings=12, last_ping=_ago(minutes=1))


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


def _the_twelve(fleet: _Fleet) -> list[dict]:
    return _expected(fleet, [*_source(), hp.ZCRYPTO_HC])


@pytest.fixture
def fleet(monkeypatch, tmp_path) -> _Fleet:
    return _Fleet(monkeypatch, tmp_path)


@pytest.fixture
def retiring(fleet, capsys) -> _Fleet:
    """The move done: twelve checks on the service, each pinged and up, the fixture fetched from it."""
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


def test_apply_writes_the_eleven_the_source_lists_and_the_service_own_check(fleet, capsys):
    rc, out, err = _run(capsys, "apply")
    assert rc == 0, err
    assert fleet.creates() == _the_twelve(fleet)
    assert sorted(c["name"] for c in fleet.clone.checks.values()) == TWELVE


def test_a_source_check_outside_the_fleet_is_never_written(monkeypatch, tmp_path, capsys):
    fleet = _Fleet(monkeypatch, tmp_path, source=[*_source(), {**_source_row(99, _TREE[0]), "name": "owner-nas-backup"}])
    assert _run(capsys, "apply")[0] == 0
    assert fleet.creates() == _the_twelve(fleet)


def test_a_fleet_name_the_source_lacks_ends_the_run_naming_it(monkeypatch, tmp_path, capsys):
    fleet = _Fleet(monkeypatch, tmp_path, source=[row for row in _source() if row["name"] != "zcrypto-panel"])
    rc, out, err = _run(capsys, "apply")
    assert rc == 2 and "zcrypto-panel" in err
    assert fleet.creates() == []


def test_a_fleet_name_the_source_carries_twice_ends_the_run_naming_it(monkeypatch, tmp_path, capsys):
    fleet = _Fleet(monkeypatch, tmp_path, source=[*_source(), _source()[3]])
    rc, out, err = _run(capsys, "apply")
    assert rc == 2 and _source()[3]["name"] in err and "twice" in err
    assert fleet.creates() == []


def test_every_create_asks_for_its_name_to_be_unique(fleet, capsys):
    assert _run(capsys, "apply")[0] == 0
    assert [body.get("unique") for body in fleet.creates()] == [["name"]] * 12
    assert _run(capsys, "apply")[0] == 0
    assert len(fleet.clone.checks) == 12, "a second run updates and never duplicates"


def test_every_create_resumes_on_its_next_ping_whatever_the_source_holds(monkeypatch, tmp_path, capsys):
    source = _source()
    source[0]["manual_resume"] = True
    fleet = _Fleet(monkeypatch, tmp_path, source=source)
    assert _run(capsys, "apply")[0] == 0
    assert [body.get("manual_resume") for body in fleet.creates()] == [False] * 12


def test_every_create_carries_the_one_slack_integration_and_no_other(fleet, capsys):
    assert _run(capsys, "apply")[0] == 0
    assert {body.get("channels") for body in fleet.creates()} == {fleet.slack}


def test_a_cron_source_is_written_with_its_schedule_and_tz_and_no_timeout(fleet, capsys):
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
    ],
    ids=["grace", "timeout", "schedule", "tz", "no channel", "a second channel", "manual_resume"],
)
def test_a_read_back_differing_from_its_source_ends_the_run_naming_the_check(fleet, capsys, name, read_as, field):
    fleet.clone.read_as[name] = read_as(fleet)
    rc, out, err = _run(capsys, "apply")
    assert rc == 2
    (line,) = [line for line in err.splitlines() if name in line]
    assert field in line
    assert not [n for n in TWELVE if n != name and n in err], err


def test_from_fixture_writes_the_same_twelve_as_the_source_the_fixture_was_fetched_from(fleet, capsys):
    assert _run(capsys, "apply")[0] == 0
    assert _run(capsys, "fixture")[0] == 0
    from_source = fleet.creates()
    fleet.requests.clear()
    fleet.clone.checks.clear()
    rc, out, err = _run(capsys, "apply", "--from-fixture")
    assert rc == 0, err
    assert fleet.creates() == from_source == _the_twelve(fleet)
    assert not [url for _, url, *_ in fleet.requests if url.startswith(HCIO)]


def test_two_slack_integrations_are_refused_before_any_write(fleet, capsys):
    fleet.clone.integration("slack")
    rc, out, err = _run(capsys, "apply")
    assert rc == 2 and "Slack" in err
    assert fleet.creates() == []


def test_a_disabled_slack_integration_stops_apply_and_status_naming_its_kind_and_id_prefix(fleet, capsys):
    assert _run(capsys, "apply")[0] == 0
    fleet.requests.clear()
    fleet.clone.integrations[0]["disabled"] = True
    for verb in ("apply", "status"):
        rc, out, err = _run(capsys, verb)
        assert rc == 2, verb
        assert "slack" in err and fleet.slack[:8] in err and fleet.slack not in err + out, (verb, err)
        assert not [name for name in TWELVE if name in out], (verb, out)
    assert fleet.creates() == []


def test_the_fixture_is_the_definitions_sorted_by_name_none_resuming_by_hand(monkeypatch, tmp_path, capsys):
    source = _source()
    source[0]["manual_resume"] = True
    fleet = _Fleet(monkeypatch, tmp_path, source=source)
    assert _run(capsys, "apply")[0] == 0
    fleet.requests.clear()
    rc, out, err = _run(capsys, "fixture")
    assert rc == 0, err
    rows = json.loads(fleet.fixture.read_text())
    assert [row["name"] for row in rows] == TWELVE
    for row in rows:
        period = ("timeout",) if row["name"] != CRON else ("schedule", "tz")
        assert set(row) == {"name", "tags", "desc", "grace", "manual_resume", *period}, row
        assert row["manual_resume"] is False
    assert set().union(*map(set, rows)) <= set(_DEFINITION)
    assert {key for _, _, key, _, _ in fleet.requests} == {CLONE_RO}
    assert fleet.fixture.read_text().endswith("]\n")


def test_plan_prints_each_definition_and_a_description_finding(monkeypatch, tmp_path, capsys):
    source = _source()
    (panel,) = [row for row in source if row["name"] == "zcrypto-panel"]
    panel["desc"] = "The panel unit on the ops node."
    fleet = _Fleet(monkeypatch, tmp_path, source=source)
    rc, out, err = _run(capsys, "plan")
    assert rc == 0, err
    for name in TWELVE:
        (line,) = [line for line in out.splitlines() if line.startswith(f"{name} ")]
        assert line.count(name) == 2, "its name and its slug"
    assert "timeout 600" in out and "grace 600" in out and "41 3 * * *" in out and "Europe/Berlin" in out
    assert "descriptions: `zcrypto-panel`: no `Runbook:" in out
    assert fleet.creates() == []


def test_plan_reads_no_finding_as_one_line(fleet, capsys, monkeypatch):
    monkeypatch.setattr(hp.ops_daily, "check_descriptions", lambda checks: [])
    rc, out, err = _run(capsys, "plan")
    assert rc == 0 and out.splitlines()[-1] == "descriptions: no finding"


def test_status_reads_a_new_check_unmoved_and_a_pinged_up_one_moved(fleet, capsys):
    assert _run(capsys, "apply")[0] == 0
    fleet.moved("zcrypto-capture")
    rc, out, err = _run(capsys, "status")
    assert rc == 0, err
    lines = {line.split()[0]: line for line in out.splitlines() if line.split() and line.split()[0] in TWELVE}
    assert sorted(lines) == TWELVE
    assert lines["zcrypto-capture"].endswith("moved") and " up " in lines["zcrypto-capture"]
    assert not lines["zcrypto-panel"].endswith("moved") and " new " in lines["zcrypto-panel"]
    assert "healthchecks.io" in out


@pytest.mark.parametrize(
    ("spoil", "named"),
    [
        (lambda f: f.clone.by_name("zcrypto-panel").update(status="new", n_pings=0, last_ping=None), "zcrypto-panel"),
        (lambda f: f.clone.by_name(SELF).update(status="down"), SELF),
        (lambda f: f.hcio.by_name("zcrypto-capture-red").update(last_ping=_ago(hours=1)), "zcrypto-capture-red"),
        (lambda f: f.clone.by_name("zcrypto-mon").update(desc="Rewritten in the UI."), "zcrypto-mon"),
    ],
    ids=["one new", "one pinged and down", "one pinged on healthchecks.io an hour ago", "the fixture differs"],
)
def test_retire_refuses_naming_the_check_and_deletes_nothing(retiring, capsys, spoil, named):
    spoil(retiring)
    rc, out, err = _run(capsys, "retire")
    assert rc == 2 and named in err
    assert retiring.deletes() == []


def test_retire_deletes_the_eleven_by_name_each_read_back_404_and_leaves_any_other(retiring, capsys):
    other = retiring.hcio.add(**{**_source_row(99, _TREE[0]), "name": "owner-nas-backup", "last_ping": _ago(minutes=5)})
    fleet_uuids = {c["uuid"]: c["name"] for c in retiring.hcio.checks.values() if c["name"] in NAMES}
    rc, out, err = _run(capsys, "retire")
    assert rc == 0, err
    assert sorted(fleet_uuids[url.rsplit("/", 1)[1]] for url in retiring.deletes()) == NAMES
    assert list(retiring.hcio.checks) == [other]
    for name in NAMES:
        (line,) = [line for line in out.splitlines() if line.startswith(f"{name}:")]
        assert "up" in line and "404" in line, line


def test_a_retire_read_back_answering_200_ends_the_run_naming_the_check(retiring, capsys):
    retiring.hcio.kept_on_delete.add("zcrypto-gate-verify")
    rc, out, err = _run(capsys, "retire")
    assert rc == 2 and "zcrypto-gate-verify" in err and "200" in err


def test_retire_rerun_after_a_partial_delete_completes_it(retiring, capsys):
    gone = NAMES[:4]
    for name in gone:
        retiring.hcio.checks.pop(retiring.hcio.by_name(name)["uuid"])
    rc, out, err = _run(capsys, "retire")
    assert rc == 0, err
    for name in gone:
        assert f"{name}: already deleted" in out
    assert len(retiring.deletes()) == len(NAMES) - len(gone)
    assert retiring.hcio.checks == {}


def test_with_neither_healthchecks_io_key_reading_the_service_alone_still_runs(retiring, capsys):
    retiring.unreadable.update(HCIO_KEYS)
    retiring.requests.clear()
    retiring.clone.checks.clear()
    rc, out, err = _run(capsys, "apply", "--from-fixture")
    assert rc == 0, err
    assert retiring.creates() == _the_twelve(retiring)
    retiring.moved()
    rc, out, err = _run(capsys, "status")
    assert rc == 0, err
    assert [line for line in out.splitlines() if line.split() and line.split()[0] in TWELVE]
    assert not [line for line in out.splitlines() if line.split() and line.split()[0] in TWELVE and "healthchecks.io" in line]
    for verb, key in (
        ("plan", "healthchecks_readonly_api_key"),
        ("apply", "healthchecks_readonly_api_key"),
        ("retire", "healthchecks_api_key"),
    ):
        rc, out, err = _run(capsys, verb)
        assert rc == 2 and key in err, (verb, err)
    assert retiring.deletes() == []


def test_each_verb_reads_the_keys_it_names_and_no_other(retiring, capsys):
    expected = {
        ("plan",): [("healthchecks_readonly_api_key", "group_vars/all/vault.yml")],
        ("apply",): [
            ("healthchecks_readonly_api_key", "group_vars/all/vault.yml"),
            ("hc_readwrite_api_key", "group_vars/all/vault.yml"),
        ],
        ("apply", "--from-fixture"): [("hc_readwrite_api_key", "group_vars/all/vault.yml")],
        ("fixture",): [("hc_readonly_api_key", "group_vars/observed/vault.yml")],
        ("status",): [
            ("hc_readwrite_api_key", "group_vars/all/vault.yml"),
            ("hc_readonly_api_key", "group_vars/observed/vault.yml"),
            ("healthchecks_readonly_api_key", "group_vars/all/vault.yml"),
        ],
        ("retire",): [
            ("hc_readonly_api_key", "group_vars/observed/vault.yml"),
            ("healthchecks_api_key", "group_vars/capture_host/vault.yml"),
        ],
    }
    for argv, keys in expected.items():
        retiring.vault.clear()
        assert _run(capsys, *argv)[0] == 0, argv
        assert sorted(set(retiring.vault)) == sorted(keys), argv


def test_no_key_uuid_or_ping_url_reaches_the_output_and_every_request_waits_30_seconds(retiring, capsys):
    secrets = retiring.secrets()
    printed = ""
    for argv in (("plan",), ("apply",), ("status",), ("fixture",), ("retire",)):
        rc, out, err = _run(capsys, *argv)
        assert rc == 0, (argv, err)
        printed += out + err
    assert secrets and not [s for s in secrets if s in printed]
    assert {timeout for *_, timeout in retiring.requests} == {30}


@pytest.mark.parametrize(
    ("argv", "service", "refused", "named"),
    [
        (("plan",), "hcio", ("GET", "checks/"), "healthchecks.io's checks listing"),
        (("apply",), "clone", ("GET", "channels/"), "integrations listing"),
        (("apply",), "clone", ("POST", "checks/"), "check write"),
        (("apply",), "clone", ("GET", "zcrypto-capture"), "check read-back for zcrypto-capture"),
        (("status",), "clone", ("GET", "checks/"), "checks listing"),
        (("retire",), "hcio", ("DELETE", "zcrypto-engine-shadow"), "check delete for zcrypto-engine-shadow"),
    ],
    ids=["source listing", "integrations", "create", "read-back", "service listing", "retire's delete"],
)
def test_a_500_ends_the_run_naming_the_endpoint_by_its_kind_and_no_secret(retiring, capsys, argv, service, refused, named):
    getattr(retiring, service).refuse[refused] = 500
    rc, out, err = _run(capsys, *argv)
    assert rc == 2 and named in err and "500" in err, err
    assert not [s for s in retiring.secrets() if s in out + err]


def test_an_answer_that_is_not_json_ends_the_run_naming_the_endpoint(fleet, capsys):
    fleet.hcio.raw[("GET", "checks/")] = b"<html>maintenance</html>"
    rc, out, err = _run(capsys, "plan")
    assert rc == 2 and "healthchecks.io's checks listing" in err


def test_a_create_answered_without_a_uuid_ends_the_run_naming_the_check(fleet, capsys, monkeypatch):
    upsert = fleet.clone._upsert

    def no_uuid(body):
        status, answer = upsert(body)
        return status, {k: v for k, v in answer.items() if k != "uuid" or body["name"] != "zcrypto-mon"}

    monkeypatch.setattr(fleet.clone, "_upsert", no_uuid)
    rc, out, err = _run(capsys, "apply")
    assert rc == 2 and "check write for zcrypto-mon" in err, err
