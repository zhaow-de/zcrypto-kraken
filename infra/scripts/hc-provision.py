#!/usr/bin/env python3
"""Move the fleet's dead-man checks from healthchecks.io to the dead-man service, and read the move.

    uv run python infra/scripts/hc-provision.py plan                    the twelve definitions apply would write
    uv run python infra/scripts/hc-provision.py apply [--from-fixture]  write them, then read each one back
    uv run python infra/scripts/hc-provision.py fixture                 rewrite the fixture from the service's listing
    uv run python infra/scripts/hc-provision.py status                  per check, whether its pinger has moved
    uv run python infra/scripts/hc-provision.py retire                  delete the fleet's checks on healthchecks.io

The fleet's checks are the names in tests/fixtures/healthchecks_descriptions.json; zcrypto-hc, the service's own,
is defined here. `apply --from-fixture` and `fixture` read no healthchecks.io key, so both still run once that
account is closed. Exit 0 done, 2 refused: a refusal names a key, an endpoint by its kind and a check by its name,
never a key's value nor a check's uuid, the secret half of its ping URL.
"""

from __future__ import annotations

import argparse
import http.client
import importlib.util
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("ops_daily", REPO / "infra" / "scripts" / "ops_daily.py")
ops_daily = importlib.util.module_from_spec(_spec)
sys.modules["ops_daily"] = ops_daily
_spec.loader.exec_module(ops_daily)
grafana_auth = ops_daily.grafana_auth

HCIO = "https://healthchecks.io/api/v3/"
SERVICE = "https://zcrypto-hc.zhaow.me/api/v3/"
FIXTURE_PATH = "tests/fixtures/healthchecks_descriptions.json"
FIXTURE = REPO / FIXTURE_PATH
TIMEOUT = 30
# The fleet's size beside zcrypto-hc, so a check fetched into the fixture from outside the fleet cannot join retire's deletes.
FLEET_CHECKS = 11

HCIO_READ = ("healthchecks_readonly_api_key", "group_vars/all/vault.yml")
HCIO_DELETE = ("healthchecks_api_key", "group_vars/capture_host/vault.yml")
SERVICE_WRITE = ("hc_readwrite_api_key", "group_vars/all/vault.yml")
SERVICE_READ = ops_daily.DEADMAN_READONLY_KEY

HCIO_LISTING = "healthchecks.io's checks listing"
SERVICE_LISTING = "the dead-man service's checks listing"
INTEGRATIONS = "the dead-man service's integrations listing"

# The node's self-check pings every 5 minutes, so 600 + 600 s pages a service that stopped storing pings within 20 minutes.
ZCRYPTO_HC = {
    "name": "zcrypto-hc",
    "tags": "hc selfcheck",
    "desc": (
        "The dead-man service's own self-check on zcrypto-hc, every 5 min: it reads the service's status endpoint and "
        "pings only when that answers OK, and the service answers a ping only once it has stored it, so the check also "
        "proves the database writable. It goes down when the web process or its database fails; when the whole node is "
        "dark this check cannot page, and Grafana's watchdog over the service pages instead. "
        "Runbook: infra/runbooks/hc.md#hc-dark"
    ),
    "grace": 600,
    "manual_resume": False,
    "timeout": 600,
}
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class Refusal(Exception):
    pass


def _key(var: tuple[str, str]) -> str:
    name, vault_file = var
    try:
        return grafana_auth.vault_var(name, vault_file)
    except Exception as exc:
        raise Refusal(f"{name} in {vault_file} does not read ({type(exc).__name__})") from None


def _reason(exc: BaseException) -> str:
    # The type alone: an exception's text can carry the request's path, and a check's path carries its uuid.
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, BaseException):
        exc = exc.reason
    return type(exc).__name__


def _send(method: str, url: str, key: str, what: str, body: dict | None = None) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode()
    headers = {"X-Api-Key": key} | ({} if data is None else {"Content-Type": "application/json"})
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as refused:
        return refused.code, None
    except (OSError, http.client.HTTPException) as exc:
        raise Refusal(f"{what} could not be read ({_reason(exc)})") from None
    try:
        return status, json.loads(raw)
    except ValueError:
        raise Refusal(f"{what} answered {status} with a body that is not JSON") from None


def _json(method: str, url: str, key: str, what: str, body: dict | None = None, ok: tuple[int, ...] = (200,)) -> object:
    status, answer = _send(method, url, key, what, body)
    if status not in ok:
        raise Refusal(f"{what} answered HTTP {status}")
    return answer


def _rows(answer: object, field: str, what: str) -> list[dict]:
    rows = answer.get(field) if isinstance(answer, dict) else None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise Refusal(f"{what} answered without a list of {field}")
    return rows


def _listing(base: str, key: str, what: str) -> list[dict]:
    return _rows(_json("GET", base + "checks/", key, what), "checks", what)


def _uuid(check: object, what: str) -> str:
    uuid = check.get("uuid") if isinstance(check, dict) else None
    if not isinstance(uuid, str) or not _UUID.fullmatch(uuid):
        raise Refusal(f"{what} answered without a uuid")
    return uuid


def _period_keys(row: dict) -> tuple[str, ...]:
    return ("timeout",) if "timeout" in row else ("schedule", "tz")


def _definition(row: dict, where: str) -> dict:
    keys = ("name", "tags", "desc", "grace", "manual_resume", *_period_keys(row))
    if missing := [k for k in keys if k not in row]:
        raise Refusal(f"{where} carries {row.get('name', 'a check')} without {', '.join(missing)}")
    return {k: row[k] for k in keys}


def _named(text: str, where: str) -> list[dict]:
    try:
        rows = json.loads(text)
    except ValueError:
        rows = None
    if not isinstance(rows, list) or not all(isinstance(row, dict) and isinstance(row.get("name"), str) for row in rows):
        raise Refusal(f"{where} is not a list of named checks")
    return rows


def _on_disk() -> list[dict]:
    try:
        text = FIXTURE.read_text()
    except OSError as exc:
        raise Refusal(f"the fixture {FIXTURE.name} does not read ({type(exc).__name__})") from None
    return _named(text, f"the fixture {FIXTURE.name}")


def _committed() -> list[dict]:
    where = f"the committed fixture, HEAD:{FIXTURE_PATH}"
    try:
        shown = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:{FIXTURE_PATH}"], capture_output=True, encoding="utf-8")
    except OSError as exc:
        raise Refusal(f"{where}, does not read (git could not run: {type(exc).__name__})") from None
    if shown.returncode != 0:
        raise Refusal(f"{where}, does not read (git exited {shown.returncode})")
    return _named(shown.stdout, where)


def _differing(mine: list[dict], theirs: list[dict]) -> list[str]:
    a, b = {row["name"]: row for row in mine}, {row["name"]: row for row in theirs}
    return sorted(n for n in a.keys() | b.keys() if a.get(n) != b.get(n)) or ([] if mine == theirs else ["their order"])


def _fleet() -> set[str]:
    return {row["name"] for row in _on_disk()} - {ZCRYPTO_HC["name"]}


def _by_name(rows: list[dict], names: set[str], where: str) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for row in rows:
        name = row.get("name")
        if name in names:
            if name in found:
                raise Refusal(f"{where} carries {name} twice")
            found[name] = row
    return found


def _on_service(fleet: set[str], listing: list[dict]) -> list[tuple[str, dict | None]]:
    twelve = fleet | {ZCRYPTO_HC["name"]}
    service = _by_name(listing, twelve, SERVICE_LISTING)
    return [(name, service.get(name)) for name in sorted(twelve)]


def _twelve(rows: list[dict], where: str) -> list[dict]:
    names = _fleet()
    found = _by_name(rows, names, where)
    if missing := sorted(names - found.keys()):
        raise Refusal(f"{where} lacks {', '.join(missing)}")
    return sorted([*(_definition(row, where) for row in found.values()), ZCRYPTO_HC], key=lambda d: d["name"])


def _fixture_rows(listing: list[dict]) -> list[dict]:
    return sorted((_definition(row, SERVICE_LISTING) for row in listing), key=lambda d: d["name"])


def _slack(key: str) -> str:
    rows = _rows(_json("GET", SERVICE + "channels/", key, INTEGRATIONS), "channels", INTEGRATIONS)
    slack = [row for row in rows if row.get("kind") == "slack"]
    if len(slack) != 1:
        raise Refusal(f"{INTEGRATIONS} carries {len(slack)} Slack integrations, where the checks page through one and only one")
    ident = slack[0].get("id")
    if not isinstance(ident, str) or not _UUID.fullmatch(ident):
        raise Refusal(f"{INTEGRATIONS} answered its Slack integration without an id")
    if "disabled" not in slack[0]:
        raise Refusal(
            f"the slack integration {ident[:8]} carries no disabled flag: {INTEGRATIONS} predates the service's "
            "v6.2.0, so whether a check on it pages cannot be read"
        )
    if slack[0]["disabled"] is not False:
        raise Refusal(
            f"the slack integration {ident[:8]} is disabled, so a check on it pages nobody: "
            "remove it and add it again in the service's UI, then run apply"
        )
    return ident


def _body(definition: dict, channel: str) -> dict:
    body = {"name": definition["name"], "slug": definition["name"]}
    body |= {k: definition[k] for k in ("tags", "desc", "grace", *_period_keys(definition))}
    # `channels` assigns exactly the integrations it lists, so a check keeps no email or other integration; and a
    # paused check must resume at its next ping, whatever the source holds, which the key rotation and the rollback
    # rest on.
    return body | {"channels": channel, "manual_resume": False, "unique": ["name"]}


def _differences(definition: dict, back: dict, channel: str) -> list[str]:
    out = [k for k in ("timeout", "grace", "schedule", "tz") if back.get(k) != definition.get(k)]
    if back.get("slug") != definition["name"]:
        out.append("slug")
    channels = back.get("channels")
    if not isinstance(channels, str) or channels.split(",") != [channel]:
        out.append("channels")
    if back.get("manual_resume") is not False:
        out.append("manual_resume")
    return out


def _period(d: dict) -> str:
    return f"timeout {d['timeout']}" if "timeout" in d else f"schedule {d['schedule']!r} tz {d['tz']}"


def _own_check(listing: list[dict]) -> str | None:
    row = _by_name(listing, {ZCRYPTO_HC["name"]}, SERVICE_LISTING).get(ZCRYPTO_HC["name"])
    if row is None:
        return None
    service = _definition(row, SERVICE_LISTING)
    if fields := sorted(k for k in service.keys() | ZCRYPTO_HC.keys() if service.get(k) != ZCRYPTO_HC.get(k)):
        return (
            f"zcrypto-hc on the service differs from this script's definition in {', '.join(fields)}: apply restores "
            "the script's, so a deliberate change is made here first"
        )
    return None


def plan() -> None:
    definitions = _twelve(_listing(HCIO, _key(HCIO_READ), HCIO_LISTING), HCIO_LISTING)
    own = _own_check(_listing(SERVICE, _key(SERVICE_READ), SERVICE_LISTING))
    print(f"{len(definitions)} checks: {HCIO_LISTING} restricted to the fixture's names, and zcrypto-hc")
    for d in definitions:
        print(f"{d['name']:<26} slug {d['name']:<26} {_period(d)}  grace {d['grace']}")
    if own:
        print(own)
    findings = ops_daily.check_descriptions(definitions)
    print("\n".join(f"descriptions: {finding}" for finding in findings) if findings else "descriptions: no finding")


def apply(from_fixture: bool) -> None:
    if from_fixture:
        source = "the fixture"
        definitions = _twelve(_on_disk(), source)
    else:
        source = HCIO_LISTING
        definitions = _twelve(_listing(HCIO, _key(HCIO_READ), source), source)
    key = _key(SERVICE_WRITE)
    channel = _slack(key)
    written = []
    for d in definitions:
        what = f"the dead-man service's check write for {d['name']}"
        status, answer = _send("POST", SERVICE + "checks/", key, what, _body(d, channel))
        if status not in (200, 201):
            raise Refusal(f"{what} answered HTTP {status}")
        written.append((d, _uuid(answer, what)))
        print(f"{d['name']}: {'created' if status == 201 else 'updated'}")
    differing = []
    for d, uuid in written:
        what = f"the dead-man service's check read-back for {d['name']}"
        back = _json("GET", f"{SERVICE}checks/{uuid}", key, what)
        if not isinstance(back, dict):
            raise Refusal(f"{what} answered no check")
        if fields := _differences(d, back, channel):
            differing.append(f"{d['name']}: read back with {', '.join(fields)} not as written")
    if differing:
        raise Refusal(f"the read-back differs from {source}:\n  " + "\n  ".join(differing))
    print(f"read-back: {len(written)} checks as {source} defines them, each on the slack integration {channel[:8]} alone")


def fixture() -> None:
    rows = _fixture_rows(_listing(SERVICE, _key(SERVICE_READ), SERVICE_LISTING))
    FIXTURE.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    print(f"{FIXTURE.name}: {len(rows)} checks from {SERVICE_LISTING}, sorted by name")


def _moved(check: dict) -> bool:
    n_pings = check.get("n_pings")
    return check.get("status") == "up" and isinstance(n_pings, int) and n_pings > 0


def status() -> None:
    _slack(_key(SERVICE_WRITE))
    fleet = _fleet()
    listing = _listing(SERVICE, _key(SERVICE_READ), SERVICE_LISTING)
    on_service = _on_service(fleet, listing)
    try:
        hcio = {row.get("name"): row.get("last_ping") for row in _listing(HCIO, _key(HCIO_READ), HCIO_LISTING)}
    except Refusal as refusal:
        print(f"healthchecks.io left out: {refusal}")
        hcio = None
    for name, check in on_service:
        if check is None:
            print(f"{name:<26} absent")
            continue
        line = (
            f"{name:<26} {check.get('status')!s:<7} n_pings {check.get('n_pings')!s:>6}  last_ping {check.get('last_ping') or '-'}"
        )
        if hcio is not None:
            line += f"  healthchecks.io last_ping {hcio.get(name) or '-'}"
        print(line + ("  moved" if _moved(check) else ""))
    if own := _own_check(listing):
        print(own)


def _when(value: object, what: str) -> datetime | None:
    if value is None:
        return None
    try:
        at = datetime.fromisoformat(value)
    except TypeError, ValueError:
        at = None
    if at is None or at.tzinfo is None:
        raise Refusal(f"{what} answered a last_ping that is no time with an offset")
    return at


def retire() -> None:
    names = _fleet()
    listing = _listing(SERVICE, _key(SERVICE_READ), SERVICE_LISTING)
    hcio_key = _key(HCIO_DELETE)
    targets = [row for row in _listing(HCIO, hcio_key, HCIO_LISTING) if row.get("name") in names]
    failing = []
    for name, check in _on_service(names, listing):
        if check is None:
            failing.append(f"{name}: absent from the dead-man service")
        elif not _moved(check):
            failing.append(
                f"{name}: not moved, the dead-man service reads it {check.get('status')} at {check.get('n_pings')} pings"
            )
    on_disk, fetched, committed = _on_disk(), _fixture_rows(listing), _committed()
    if differ := _differing(on_disk, committed):
        failing.append(
            f"the fixture differs from the committed one at HEAD in {', '.join(differ)}: the committed one is the fleet, "
            "so merge a change to it first, or restore the service and run fixture again"
        )
    if len(names) != FLEET_CHECKS:
        if len(names) < FLEET_CHECKS:
            missing = sorted({row["name"] for row in committed} - {ZCRYPTO_HC["name"]} - names)
            failing.append(
                f"the fixture names {len(names)} fleet checks beside zcrypto-hc, short of {FLEET_CHECKS}, missing "
                f"{', '.join(missing) or 'none the committed fixture names'}: restore the committed fixture, run apply "
                "and fixture, never a delete"
            )
        else:
            failing.append(
                f"the fixture names {', '.join(sorted(names))} beside zcrypto-hc, more than {FLEET_CHECKS}: delete any "
                "other on the service and run fixture again"
            )
    if differ := _differing(on_disk, fetched):
        failing.append(f"the fixture differs from {SERVICE_LISTING} in {', '.join(differ)}: run fixture and merge it first")
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    for row in targets:
        at = _when(row.get("last_ping"), f"{HCIO_LISTING} for {row['name']}")
        if at is not None and at > since:
            failing.append(f"{row['name']}: pinged on healthchecks.io at {row['last_ping']}, within 24 hours")
    doomed = [(row["name"], _uuid(row, f"{HCIO_LISTING} for {row['name']}"), row.get("status")) for row in targets]
    if failing:
        raise Refusal("retire refused, nothing deleted:\n  " + "\n  ".join(failing))
    for name in sorted(names - {name for name, _, _ in doomed}):
        print(f"{name}: already deleted")
    for name, uuid, was in sorted(doomed):
        _json("DELETE", f"{HCIO}checks/{uuid}", hcio_key, f"healthchecks.io's check delete for {name}")
        what = f"healthchecks.io's check read-back for {name}"
        gone, _ = _send("GET", f"{HCIO}checks/{uuid}", hcio_key, what)
        if gone != 404:
            raise Refusal(f"{what} answered HTTP {gone} after its delete, where 404 would say it is gone")
        print(f"{name}: {was}, deleted, read back 404")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="hc-provision.py", description=__doc__.splitlines()[0])
    verbs = parser.add_subparsers(dest="verb", required=True)
    for verb in ("plan", "fixture", "status", "retire"):
        verbs.add_parser(verb)
    verbs.add_parser("apply").add_argument("--from-fixture", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.verb == "apply":
            apply(args.from_fixture)
        else:
            {"plan": plan, "fixture": fixture, "status": status, "retire": retire}[args.verb]()
    except Refusal as refusal:
        print(f"hc-provision: {refusal}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
