"""Spec 00082: converge guards evaluated through Ansible's own templar.

The test boundary is the guard's REAL condition expression fed constructed probe outcomes --
never a re-implementation of the logic. `load_task` reads the committed YAML; a guard whose
expression is edited drifts here immediately.
"""

from pathlib import Path

import pytest
import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra" / "ansible"


def load_tasks(path: Path) -> list[dict]:
    # play lists (site.yml/bootstrap.yml) and role task lists parse identically; find_task recurses
    # into block/pre_tasks/tasks either way.
    return yaml.safe_load(path.read_text())


def find_task(tasks: list[dict], name: str) -> dict:
    for t in tasks:
        if t.get("name") == name:
            return t
        for key in ("block", "pre_tasks", "tasks"):
            if key in t:
                try:
                    return find_task(t[key], name)
                except KeyError:
                    continue
    raise KeyError(name)


def truthy(expr, variables: dict) -> bool:
    # ansible-core 2.19+ Data-Tagging: a plain str is UNTRUSTED and comes back unrendered -- bool()
    # of the unrendered template string would be True for every fixture, making every test vacuous.
    # trust_as_template is mandatory (measured on the locked 2.21.2; cold review C1). Never
    # re-implement guard logic in Python instead -- the committed expression is the test subject.
    from ansible.template import trust_as_template

    t = Templar(loader=DataLoader(), variables=variables)
    if isinstance(expr, list):
        return all(truthy(e, variables) for e in expr)
    return bool(t.template(trust_as_template("{{ (" + expr + ") | bool }}")))


def assert_that(task: dict) -> list[str]:
    that = task["ansible.builtin.assert"]["that"]
    return that if isinstance(that, list) else [that]


def when_conditions(task: dict) -> list[str]:
    # a `when:` list is ANDed by Ansible, which is exactly what truthy() does with a list.
    when = task.get("when", [])
    return when if isinstance(when, list) else [when]


def task_index(tasks: list[dict], name: str) -> int:
    # Positional, top-level only -- ORDER is the property under test, and find_task's recursion into
    # block/pre_tasks would return a task whose index says nothing about the role's own sequence.
    for i, t in enumerate(tasks):
        if t.get("name") == name:
            return i
    raise KeyError(name)


CAPTURE = ANSIBLE / "roles" / "capture" / "tasks" / "main.yml"

DIGEST_OK = {"capture_digest_probe": {"rc": 0}}
DIGEST_MISSING = {"capture_digest_probe": {"rc": 1}}


def test_capture_digest_preflight_refuses_unpulled_digest():
    task = find_task(load_tasks(CAPTURE), "preflight — refuse a digest the host has not pulled")
    assert not truthy(assert_that(task), DIGEST_MISSING)
    assert truthy(assert_that(task), DIGEST_OK)


PAIR_BASE = {"capture_pairs": ["BTC/EUR", "ETH/EUR", "XRP/BTC"]}


def test_pair_add_order_refuses_a_pair_the_primary_lacks():
    task = find_task(load_tasks(CAPTURE), "pair-add order — refuse a pair the primary does not already carry")
    refuse = {**PAIR_BASE, "capture_primary_pairs": ["BTC/EUR", "ETH/EUR"]}
    ok = {**PAIR_BASE, "capture_primary_pairs": ["BTC/EUR", "ETH/EUR", "XRP/BTC"]}
    assert not truthy(assert_that(task), refuse)
    assert truthy(assert_that(task), ok)


CANARY_BASE = {
    "capture_image_digest": "sha256:" + "c" * 64,
    "capture_secondary_digest_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "0" * 64},
}


@pytest.mark.parametrize(
    ("override", "expected"),
    [("", False), ("true", False), ("yes", False), ("short", False), ("secondary down, rolling back after incident", True)],
)
def test_canary_parity_override_semantics(override, expected):
    task = find_task(load_tasks(CAPTURE), "canary parity — refuse a primary re-pin the secondary has not baked")
    variables = {**CANARY_BASE, "canary_override": override}
    assert truthy(assert_that(task), variables) is expected


def test_canary_parity_passes_when_secondary_runs_the_candidate():
    task = find_task(load_tasks(CAPTURE), "canary parity — refuse a primary re-pin the secondary has not baked")
    ok = {
        "capture_image_digest": "sha256:" + "c" * 64,
        "capture_secondary_digest_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "c" * 64},
        "canary_override": "",
    }
    assert truthy(assert_that(task), ok)


PINS_BASE = {"capture_running_digest_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "a" * 64}}
PINS_FILE_WITH = "| capture | zcrypto | `" + "a" * 12 + "` | 2026-08-02 | prior |"
PINS_FILE_WITHOUT = "| capture | zcrypto | `" + "b" * 12 + "` | 2026-08-02 | prior |"


@pytest.mark.parametrize(
    ("pins_text", "override", "expected"),
    [
        (PINS_FILE_WITH, "", True),
        (PINS_FILE_WITHOUT, "", False),
        (PINS_FILE_WITHOUT, "true", False),
        (PINS_FILE_WITHOUT, "emergency: pins file unreachable, recorded after", True),
    ],
)
def test_pins_recording_semantics(pins_text, override, expected):
    task = find_task(load_tasks(CAPTURE), "pins recording — refuse to replace a digest fleet-pins.md does not record")
    variables = {**PINS_BASE, "capture_fleet_pins_text": pins_text, "pins_override": override}
    assert truthy(assert_that(task), variables) is expected


# --- spec D1's second half: an ACCEPTED override must reach the play log, or the canary fail_msg's
# own promise ("it lands in this log") is false. The echo's `when:` is the assert's scoping AND the
# override fragment AND the primary condition NEGATED -- an echo that fires whenever the override is
# merely PRESENT would log a "why" on runs that overrode nothing, which is the failure these cover.
CANARY_ECHO_BASE = {
    "inventory_hostname": "zcrypto",
    "groups": {"engine_host": ["zcrypto"], "capture_host": ["zcrypto", "zcrypto-red"]},
    "capture_image_digest": "sha256:" + "c" * 64,
}
CANARY_STALE = {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "0" * 64}
CANARY_BAKED = {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "c" * 64}
CANARY_REASON = "secondary down, rolling back after incident"


@pytest.mark.parametrize(
    ("probe", "override", "expected"),
    [
        (CANARY_STALE, CANARY_REASON, True),  # override accepted over a failing parity -> echo the why
        (CANARY_STALE, "", False),  # no override -> the assert refused; there is no why to echo
        (CANARY_BAKED, CANARY_REASON, False),  # parity passes -> nothing was overridden
    ],
)
def test_canary_override_echo_fires_only_on_an_accepted_override(probe, override, expected):
    task = find_task(load_tasks(CAPTURE), "canary override accepted — the reason, on the record")
    variables = {**CANARY_ECHO_BASE, "capture_secondary_digest_probe": probe, "canary_override": override}
    assert truthy(when_conditions(task), variables) is expected


PINS_ECHO_BASE = {
    "capture_running_digest_probe": {"rc": 0, "stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "a" * 64},
}
PINS_REASON = "emergency: pins file unreachable, recorded after"


@pytest.mark.parametrize(
    ("pins_text", "override", "expected"),
    [
        (PINS_FILE_WITHOUT, PINS_REASON, True),  # override accepted over an unrecorded pin -> echo the why
        (PINS_FILE_WITHOUT, "", False),  # no override -> the assert refused; there is no why to echo
        (PINS_FILE_WITH, PINS_REASON, False),  # the pin IS recorded -> nothing was overridden
    ],
)
def test_pins_override_echo_fires_only_on_an_accepted_override(pins_text, override, expected):
    task = find_task(load_tasks(CAPTURE), "pins override accepted — the reason, on the record")
    variables = {**PINS_ECHO_BASE, "capture_fleet_pins_text": pins_text, "pins_override": override}
    assert truthy(when_conditions(task), variables) is expected


SITE = ANSIBLE / "site.yml"


def test_untagged_primary_refusal():
    task = find_task(load_tasks(SITE), "refuse an un-tagged run on the live primary")
    refuse = {"ansible_run_tags": ["all"], "ansible_skip_tags": []}
    tagged = {"ansible_run_tags": ["capture"], "ansible_skip_tags": []}
    skip_scoped = {"ansible_run_tags": ["all"], "ansible_skip_tags": ["engine"]}
    assert not truthy(assert_that(task), refuse)
    assert truthy(assert_that(task), tagged)
    assert truthy(assert_that(task), skip_scoped)


WINDOW = "engine window — refuse a converge outside the inter-cycle gap"


@pytest.mark.parametrize(
    ("since_boundary", "override", "expected"),
    [
        (1900, "", True),  # inside the gap
        (900, "", False),  # completion window [B, B+30min] may still be running
        (13900, "", False),  # within 10 min of the next boundary
        (900, "true", False),  # boolean override refused
        (900, "yes", False),  # I4: every canonical boolean spelling refused
        (900, "short", False),  # I4: sub-9-char fragment refused
        (900, "cycle confirmed complete, converging late on purpose", True),
    ],
)
def test_engine_window_guard(since_boundary, override, expected):
    task = find_task(load_tasks(SITE), WINDOW)
    variables = {
        "engine_epoch_probe": {"stdout": str(1754265600 + since_boundary)},  # 1754265600 % 14400 == 0
        "engine_window_override": override,
    }
    assert truthy(assert_that(task), variables) is expected


# --- when-scoping (cold review M4): the `that:` tests never exercise the scoping, and a mis-scoped
# guard fires on the wrong host or never.
def test_untagged_refusal_scopes_to_engine_host_members_only():
    task = find_task(load_tasks(SITE), "refuse an un-tagged run on the live primary")
    on_primary = {"inventory_hostname": "zcrypto", "groups": {"engine_host": ["zcrypto"]}}
    on_secondary = {"inventory_hostname": "zcrypto-red", "groups": {"engine_host": ["zcrypto"]}}
    assert truthy(when_conditions(task), on_primary)
    assert not truthy(when_conditions(task), on_secondary)


def test_canary_probe_activates_only_on_an_actual_repin():
    task = find_task(load_tasks(CAPTURE), "probe — the secondary's running capture digest (canary parity)")
    base = {
        "inventory_hostname": "zcrypto",
        "groups": {"engine_host": ["zcrypto"], "capture_host": ["zcrypto", "zcrypto-red"]},
    }
    repin = {
        **base,
        "capture_image_digest": "sha256:" + "c" * 64,
        "capture_primary_running_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "0" * 64},
    }
    same = {
        **base,
        "capture_image_digest": "sha256:" + "0" * 64,
        "capture_primary_running_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "0" * 64},
    }
    assert truthy(when_conditions(task), repin)
    assert not truthy(when_conditions(task), same)


def test_pair_add_delegated_probe_engages_only_when_adding_pairs():
    task = find_task(
        load_tasks(CAPTURE),
        "probe — the primary's deployed pair list (pair-add order; fail-CLOSED on unreachable, a new pair is the hazard)",
    )
    base = {"inventory_hostname": "zcrypto-red", "groups": {"engine_host": ["zcrypto"]}}
    adding = {**base, "capture_pairs": ["BTC/EUR", "XRP/BTC"], "capture_deployed_pairs": ["BTC/EUR"]}
    unchanged = {**base, "capture_pairs": ["BTC/EUR"], "capture_deployed_pairs": ["BTC/EUR"]}
    assert truthy(when_conditions(task), adding)
    assert not truthy(when_conditions(task), unchanged)


# --- spec D1's second half for the overridable window guard, same shape as the two capture echoes
# above: the echo's `when:` is the assert's scoping AND the window condition NEGATED AND the override
# fragment. An echo that fires whenever the override is merely PRESENT would log a "why" on runs that
# overrode nothing, which is the failure these cover.
WINDOW_ECHO = "engine window override accepted — the reason, on the record"
WINDOW_REASON = "cycle confirmed complete, converging late on purpose"


@pytest.mark.parametrize(
    ("since_boundary", "override", "expected"),
    [
        (900, WINDOW_REASON, True),  # override accepted over a closed window -> echo the why
        (900, "", False),  # no override -> the assert refused; there is no why to echo
        (1900, WINDOW_REASON, False),  # the window is open -> nothing was overridden
    ],
)
def test_window_override_echo_fires_only_on_an_accepted_override(since_boundary, override, expected):
    task = find_task(load_tasks(SITE), WINDOW_ECHO)
    variables = {
        "ansible_check_mode": False,
        "engine_epoch_probe": {"stdout": str(1754265600 + since_boundary)},
        "engine_window_override": override,
    }
    assert truthy(when_conditions(task), variables) is expected


# --- engine-role guards. Fixture keys carry the `engine_` prefix ansible-lint's
# var-naming[no-role-prefix] forces on every role-registered var -- the keys ARE the guard's
# variable names, so they cannot diverge from the committed YAML.
ENGINE = ANSIBLE / "roles" / "engine" / "tasks" / "main.yml"


def test_engine_digest_preflight():
    task = find_task(load_tasks(ENGINE), "preflight — refuse a digest the host has not pulled")
    assert not truthy(assert_that(task), {"engine_digest_probe": {"rc": 1}})
    assert truthy(assert_that(task), {"engine_digest_probe": {"rc": 0}})


# The empty-digest fail-fast must be reached FIRST in both roles: `*_image_digest` defaults to "",
# so a forgotten `-e` would otherwise be caught by the residency preflight, whose message names a
# `docker pull` of a ref ending in a bare `@` instead of pointing at the digest's source. Fail-closed
# either way; this pins WHICH message the operator gets, on both sides of the mirror.
def test_engine_empty_digest_failfast_precedes_residency_preflight():
    tasks = load_tasks(ENGINE)
    failfast = task_index(tasks, "fail fast if the pinned engine image digest was not supplied")
    assert failfast < task_index(tasks, "preflight — refuse a digest the host has not pulled")


def test_capture_empty_digest_failfast_precedes_residency_preflight():
    tasks = load_tasks(CAPTURE)
    failfast = task_index(tasks, "fail fast if the pinned image digest was not supplied")
    assert failfast < task_index(tasks, "preflight — refuse a digest the host has not pulled")


def test_engine_secrets_preflight():
    task = find_task(load_tasks(ENGINE), "preflight — refuse to restart the engine without its logship secrets")
    assert not truthy(assert_that(task), {"engine_logship_secrets_stat": {"stat": {"exists": False}}})
    assert truthy(assert_that(task), {"engine_logship_secrets_stat": {"stat": {"exists": True}}})


ENGINE_PINS = "pins recording — refuse to replace a digest fleet-pins.md does not record"
ENGINE_PINS_BASE = {
    "engine_running_digest_probe": {"rc": 0, "stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "e" * 64},
}
ENGINE_PINS_WITH = "| engine | zcrypto | `" + "e" * 12 + "` |"
ENGINE_PINS_WITHOUT = "| engine | zcrypto | `" + "f" * 12 + "` |"
ENGINE_PINS_REASON = "rollback in progress, pins recorded immediately after"


def test_engine_pins_recording_semantics():
    task = find_task(load_tasks(ENGINE), ENGINE_PINS)
    variables = {**ENGINE_PINS_BASE, "engine_fleet_pins_text": ENGINE_PINS_WITH, "pins_override": ""}
    assert truthy(assert_that(task), variables)
    variables["engine_fleet_pins_text"] = ENGINE_PINS_WITHOUT
    assert not truthy(assert_that(task), variables)


@pytest.mark.parametrize(
    ("override", "expected"),
    [("", False), ("short", False), ("true", False), (ENGINE_PINS_REASON, True)],
)
def test_engine_pins_override_semantics(override, expected):
    task = find_task(load_tasks(ENGINE), ENGINE_PINS)
    variables = {**ENGINE_PINS_BASE, "engine_fleet_pins_text": ENGINE_PINS_WITHOUT, "pins_override": override}
    assert truthy(assert_that(task), variables) is expected


@pytest.mark.parametrize(
    ("pins_text", "override", "expected"),
    [
        (ENGINE_PINS_WITHOUT, ENGINE_PINS_REASON, True),  # override accepted over an unrecorded pin -> echo the why
        (ENGINE_PINS_WITHOUT, "", False),  # no override -> the assert refused; there is no why to echo
        (ENGINE_PINS_WITH, ENGINE_PINS_REASON, False),  # the pin IS recorded -> nothing was overridden
    ],
)
def test_engine_pins_override_echo_fires_only_on_an_accepted_override(pins_text, override, expected):
    task = find_task(load_tasks(ENGINE), "pins override accepted — the reason, on the record")
    variables = {**ENGINE_PINS_BASE, "engine_fleet_pins_text": pins_text, "pins_override": override}
    assert truthy(when_conditions(task), variables) is expected


# --- ops-role guards. `ops_` fixture keys for the same var-naming reason as the engine block above.
# The ops role's own convention (roles/ops/defaults/main.yml: ops_image_digest has NO default) is
# that a digestless config/alloy-only converge SKIPS every image-consuming task -- so each guard
# here carries `when: ops_image_digest is defined`, and the two skip tests below pin that, since a
# guard that refuses a legitimate alloy-only converge is a broken role, not a strict one.
OPS = ANSIBLE / "roles" / "ops" / "tasks" / "main.yml"


def test_ops_digest_preflight():
    task = find_task(load_tasks(OPS), "preflight — refuse a digest the host has not pulled")
    assert not truthy(assert_that(task), {"ops_digest_probe": {"rc": 1}})
    assert truthy(assert_that(task), {"ops_digest_probe": {"rc": 0}})


LIQUIDATIONS = "liquidations — require an explicit roll-after/defer decision on a repin"


@pytest.mark.parametrize(
    ("decision", "pin_differs", "expected"),
    [
        ("", True, False),  # a repin with no decision -> refuse
        ("yes", True, False),  # a boolean-ish answer is not one of the two decisions
        ("roll-after", True, True),
        ("defer", True, True),
        ("", False, True),  # the file already pins this digest -> not a repin, nothing to decide
    ],
)
def test_liquidations_repin_decision(decision, pin_differs, expected):
    task = find_task(load_tasks(OPS), LIQUIDATIONS)
    deployed = "sha256:" + ("d" * 64 if pin_differs else "e" * 64)
    variables = {
        "ops_image_digest": "sha256:" + "e" * 64,
        "ops_liquidations_pin_probe": {"stdout": '    image: "ghcr.io/zhaow-de/zcrypto-capture@' + deployed + '"'},
        "liquidations_decision": decision,
    }
    assert truthy(assert_that(task), variables) is expected


def test_liquidations_guard_skips_a_digestless_converge():
    task = find_task(load_tasks(OPS), LIQUIDATIONS)
    probed = {"ops_liquidations_pin_probe": {"rc": 0}}
    assert truthy(when_conditions(task), {**probed, "ops_image_digest": "sha256:" + "e" * 64})
    assert not truthy(when_conditions(task), probed)


# grep's two non-zero answers are NOT the same fact: 2 = no such file (first provision, nothing
# deployed to repin -- the only legitimate stand-down), 1 = the file is there and carries no
# `@sha256:` line at all, an anomalous on-host state the guard must refuse rather than skip.
@pytest.mark.parametrize(("rc", "expected"), [(1, True), (2, False)])
def test_liquidations_guard_engages_on_a_compose_file_without_a_digest_line(rc, expected):
    task = find_task(load_tasks(OPS), LIQUIDATIONS)
    variables = {"ops_image_digest": "sha256:" + "e" * 64, "ops_liquidations_pin_probe": {"rc": rc}}
    assert truthy(when_conditions(task), variables) is expected


def test_liquidations_refuses_a_compose_file_without_a_digest_line():
    task = find_task(load_tasks(OPS), LIQUIDATIONS)
    variables = {
        "ops_image_digest": "sha256:" + "e" * 64,
        "ops_liquidations_pin_probe": {"rc": 1, "stdout": ""},
        "liquidations_decision": "",
    }
    assert not truthy(assert_that(task), variables)


def test_panel_timer_hold_excludes_only_the_panel_timer():
    from ansible.template import trust_as_template

    task = find_task(load_tasks(OPS), "enable + start the replay + panel timers")
    loop_expr = task["loop"]
    held = Templar(loader=DataLoader(), variables={"ops_panel_timer_hold": True}).template(trust_as_template(loop_expr))
    live = Templar(loader=DataLoader(), variables={"ops_panel_timer_hold": False}).template(trust_as_template(loop_expr))
    # the hold is OPT-IN: an ordinary converge (variable unset) must still arm the panel timer.
    unset = Templar(loader=DataLoader(), variables={}).template(trust_as_template(loop_expr))
    assert "panel-materialize" not in held and "verify-replay" in held and "verified-replay" in held
    assert "panel-materialize" in live
    assert "panel-materialize" in unset


OPS_PINS = "pins recording — refuse to replace a digest fleet-pins.md does not record"
# The probe behind this is `docker inspect` of the liquidations-poll CONTAINER, never the compose
# file: the recorded incident had the file pinning one digest while the container ran another.
OPS_PINS_BASE = {
    "ops_image_digest": "sha256:" + "c" * 64,
    "ops_running_digest_probe": {"rc": 0, "stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "a" * 64},
}
OPS_PINS_WITH = "| ops | zcrypto-ops | `" + "a" * 12 + "` |"
OPS_PINS_WITHOUT = "| ops | zcrypto-ops | `" + "b" * 12 + "` |"
OPS_PINS_REASON = "recorded in pins after emergency roll"


def test_ops_pins_recording_passes_a_recorded_pin():
    task = find_task(load_tasks(OPS), OPS_PINS)
    variables = {**OPS_PINS_BASE, "ops_fleet_pins_text": OPS_PINS_WITH, "pins_override": ""}
    assert truthy(assert_that(task), variables)


@pytest.mark.parametrize(
    ("override", "expected"),
    [("", False), ("short", False), (OPS_PINS_REASON, True)],
)
def test_ops_pins_override_semantics(override, expected):
    task = find_task(load_tasks(OPS), OPS_PINS)
    variables = {**OPS_PINS_BASE, "ops_fleet_pins_text": OPS_PINS_WITHOUT, "pins_override": override}
    assert truthy(assert_that(task), variables) is expected


def test_ops_pins_guard_skips_a_digestless_converge():
    task = find_task(load_tasks(OPS), OPS_PINS)
    live = {**OPS_PINS_BASE, "ops_fleet_pins_text": OPS_PINS_WITH}
    assert truthy(when_conditions(task), live)
    assert not truthy(when_conditions(task), {k: v for k, v in live.items() if k != "ops_image_digest"})


@pytest.mark.parametrize(
    ("pins_text", "override", "expected"),
    [
        (OPS_PINS_WITHOUT, OPS_PINS_REASON, True),  # override accepted over an unrecorded pin -> echo the why
        (OPS_PINS_WITHOUT, "", False),  # no override -> the assert refused; there is no why to echo
        (OPS_PINS_WITH, OPS_PINS_REASON, False),  # the pin IS recorded -> nothing was overridden
    ],
)
def test_ops_pins_override_echo_fires_only_on_an_accepted_override(pins_text, override, expected):
    task = find_task(load_tasks(OPS), "pins override accepted — the reason, on the record")
    variables = {**OPS_PINS_BASE, "ops_fleet_pins_text": pins_text, "pins_override": override}
    assert truthy(when_conditions(task), variables) is expected


# --- docker-role guard. The docker role is SHARED by every play, but the hazard is capture-specific:
# its daemon.json template task notifies `restart docker`, and bouncing dockerd under live capture is
# an unbackfillable data gap. `docker_daemon_json_diff` carries the role prefix ansible-lint's
# var-naming[no-role-prefix] forces; `daemon_json_ack` is an operator `-e` var, unprefixed like
# `pins_override`. The ack is a BOOLEAN here, unlike the D1 free-text overrides: the debug task
# displays the diff first, so the ack acknowledges specific shown content rather than substituting
# for absent evidence.
DOCKER = ANSIBLE / "roles" / "docker" / "tasks" / "main.yml"
DAEMON_JSON_ACK = "daemon.json — refuse an unacknowledged change (its handler bounces dockerd)"


@pytest.mark.parametrize(
    ("rc", "ack", "expected"),
    [
        (1, False, False),  # rendered output differs, nothing acked -> refuse
        (0, False, True),  # identical render -> no handler fires, no ack owed
        (1, True, True),  # differs, operator acked the displayed diff -> proceed
        # rc 2 is diff's "trouble" exit, which on this host means /etc/docker/daemon.json is ABSENT
        # (first provision). That is a change the handler would act on, so it must refuse, not pass.
        (2, False, False),
    ],
)
def test_daemon_json_change_ack(rc, ack, expected):
    task = find_task(load_tasks(DOCKER), DAEMON_JSON_ACK)
    variables = {"docker_daemon_json_diff": {"rc": rc}, "daemon_json_ack": ack}
    assert truthy(assert_that(task), variables) is expected


# A `failed_when: false` command prints nothing under the default callback, so without this debug the
# operator would ack unseen content -- which is the whole rationale for the boolean ack above.
@pytest.mark.parametrize(("rc", "expected"), [(1, True), (0, False)])
def test_daemon_json_diff_is_displayed_only_when_it_would_change(rc, expected):
    task = find_task(load_tasks(DOCKER), "daemon.json — show the pending change before asking for an ack")
    assert truthy(when_conditions(task), {"docker_daemon_json_diff": {"rc": rc}}) is expected


# One contract, so one test: probe -> show -> ask -> act. ORDER is the whole of it -- every expression
# test above still passes with the guard sitting AFTER the template task it exists to protect, at
# which point dockerd has already been notified and the guard is decorative.
def test_daemon_json_guard_precedes_the_task_whose_handler_bounces_dockerd():
    tasks = load_tasks(DOCKER)
    probe = task_index(tasks, "probe — diff the pending daemon.json against the deployed one")
    show = task_index(tasks, "daemon.json — show the pending change before asking for an ack")
    ask = task_index(tasks, DAEMON_JSON_ACK)
    assert probe < show  # nothing to display until the diff has been registered
    assert show < ask  # the ack is only meaningful once the operator has seen the diff
    assert ask < task_index(tasks, "configure the docker daemon (bounded json-file log driver)")
