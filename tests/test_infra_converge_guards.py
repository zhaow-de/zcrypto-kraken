"""Spec 00082: converge guards evaluated through Ansible's own templar.

The test boundary is the guard's REAL condition expression fed constructed probe outcomes --
never a re-implementation of the logic; `load_tasks` reads the committed YAML.
"""

import hashlib
import json
import re
import tomllib
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
    # of the unrendered template string would be True for every fixture, making every test vacuous,
    # so trust_as_template is mandatory.
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


# An UNREACHABLE secondary registers a result with no `stdout`, which `ignore_unreachable: true`
# exists to allow. Two halves refuse there: the assert's `when:` is `is not skipped` -- `stdout is
# defined` would SKIP the guard on the one host it cannot read -- and the parity expression's
# `| default('')` supplies the empty string there is nothing to match in.
CANARY_PARITY = "canary parity — refuse a primary re-pin the secondary has not baked"
CANARY_UNREACHABLE = {"unreachable": True, "msg": "Failed to connect to the host via ssh"}
CANARY_SKIPPED = {"skipped": True, "skip_reason": "Conditional result was False"}
# the `when:` reads host membership, so the scoping vars belong in these fixtures too
CANARY_HOST = {
    "inventory_hostname": "zcrypto",
    "groups": {"engine_host": ["zcrypto"], "capture_host": ["zcrypto", "zcrypto-red"]},
    "capture_image_digest": "sha256:" + "c" * 64,
}


def test_canary_parity_refuses_an_unreachable_secondary():
    task = find_task(load_tasks(CAPTURE), CANARY_PARITY)
    variables = {**CANARY_HOST, "capture_secondary_digest_probe": CANARY_UNREACHABLE, "canary_override": ""}
    assert truthy(when_conditions(task), variables), "the probe RAN (unreachable is not skipped) -- the assert must evaluate"
    assert not truthy(assert_that(task), variables), "an unreadable secondary must refuse, never pass open"


def test_canary_parity_gate_stands_down_only_on_a_genuinely_skipped_probe():
    # The converse of the test above: a probe that never ran (not a re-pin) leaves the assert with no
    # subject, and `is not skipped` is what tells the two states apart.
    task = find_task(load_tasks(CAPTURE), CANARY_PARITY)
    variables = {**CANARY_HOST, "capture_secondary_digest_probe": CANARY_SKIPPED, "canary_override": ""}
    assert not truthy(when_conditions(task), variables)


def test_canary_parity_unreachable_secondary_still_routes_through_the_override():
    # Fail-closed must not mean unbypassable: the documented escape is the reason-required override,
    # the same one a stale secondary uses -- no separate unreachable-only path.
    task = find_task(load_tasks(CAPTURE), CANARY_PARITY)
    base = {**CANARY_HOST, "capture_secondary_digest_probe": CANARY_UNREACHABLE}
    assert not truthy(assert_that(task), {**base, "canary_override": "true"})
    assert truthy(assert_that(task), {**base, "canary_override": "secondary unreachable, incident rollback"})


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


# --- spec 00082 D1's second half: an ACCEPTED override must reach the play log, or the canary
# fail_msg's own promise ("it lands in this log") is false. The echo's `when:` is the assert's
# scoping AND the override fragment AND the primary condition NEGATED -- an echo firing whenever
# the override is merely PRESENT would log a "why" on runs that overrode nothing.
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


# --- guard 4 tightened (spec 00083 D7): only --skip-tags forms naming engine satisfy it ----------


def _untag_guard():
    tasks = load_tasks(SITE)
    return find_task(tasks, "refuse an un-tagged run on the live primary")


def test_unrelated_skip_tags_now_refused():
    v = {"ansible_run_tags": ["all"], "ansible_skip_tags": ["something-else"]}
    assert not truthy(assert_that(_untag_guard()), v)


def test_skip_tags_engine_passes():
    v = {"ansible_run_tags": ["all"], "ansible_skip_tags": ["engine"]}
    assert truthy(assert_that(_untag_guard()), v)


def test_explicit_tags_still_pass():
    v = {"ansible_run_tags": ["capture"], "ansible_skip_tags": []}
    assert truthy(assert_that(_untag_guard()), v)


def test_bare_run_still_refused():
    v = {"ansible_run_tags": ["all"], "ansible_skip_tags": []}
    assert not truthy(assert_that(_untag_guard()), v)


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


# The two floors ARE the guard -- 1800 s (the cycle-completion window [B, B+30 min] may still be
# running) and 600 s (a stop→start begun inside 10 min of the next boundary risks straddling it).
# These fixtures sit ON the comparison boundary, which is the only place a constant is pinned.
@pytest.mark.parametrize(
    ("since_boundary", "expected"),
    [
        (1799, False),  # one second short of the floor
        (1800, True),  # the floor itself is open: `>= 1800`
        (13800, True),  # until_next == 600 exactly -- inclusive on that side too: `>= 600`
        (13801, False),  # until_next == 599
    ],
)
def test_engine_window_floors_are_pinned_at_their_exact_constants(since_boundary, expected):
    task = find_task(load_tasks(SITE), WINDOW)
    variables = {
        "engine_epoch_probe": {"stdout": str(1754265600 + since_boundary)},
        "engine_window_override": "",
    }
    assert truthy(assert_that(task), variables) is expected


# --- window floor from the boundary cycle's completion (spec 00083 D6) --------------------------
# When the boundary's cycle-HH.json already carries completed_at, the floor BECOMES completed_at+300
# in place of B+1800 -- usually earlier, LATER when the cycle itself ran long.
# Absent probe, failed probe, or garbage stdout -> the CONSERVATIVE B+1800 floor.

BOUNDARY = 1785744000  # 2026-08-03 08:00:00 UTC, divisible by 14400


def _window_guard():
    tasks = load_tasks(SITE)
    return find_task(tasks, "engine window — refuse a converge outside the inter-cycle gap")


def test_floor_drops_to_completion_plus_300():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 500)},  # B+500: inside old refusal window
        "engine_cycle_epoch_probe": {"rc": 0, "stdout": str(BOUNDARY + 108)},  # completed 08:01:48
        "engine_window_override": "",
    }
    assert truthy(assert_that(guard), v)  # 500 >= 108+300 -> allowed early


def test_floor_still_refuses_before_completion_plus_300():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 300)},
        "engine_cycle_epoch_probe": {"rc": 0, "stdout": str(BOUNDARY + 108)},
        "engine_window_override": "",
    }
    assert not truthy(assert_that(guard), v)  # 300 < 408


def test_failed_probe_keeps_conservative_floor():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 500)},
        "engine_cycle_epoch_probe": {"rc": 1, "stdout": ""},
        "engine_window_override": "",
    }
    assert not truthy(assert_that(guard), v)  # rc!=0 -> floor stays B+1800


def test_garbage_stdout_keeps_conservative_floor():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 500)},
        "engine_cycle_epoch_probe": {"rc": 0, "stdout": "Traceback (most recent call last)"},
        "engine_window_override": "",
    }
    assert not truthy(assert_that(guard), v)


# This fixture pins the `{10}` in the stdout regex: under `^[0-9]+$` a short all-digit token parses
# as a floor in the distant past, i.e. no floor at all.
def test_short_all_digit_stdout_keeps_conservative_floor():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 500)},
        "engine_cycle_epoch_probe": {"rc": 0, "stdout": "99"},
        "engine_window_override": "",
    }
    assert not truthy(assert_that(guard), v)


# The floor FOLLOWS the journal in both directions — it is not a monotone relaxation of B+1800.
# A cycle that itself ran long (completed_at = B+1700) puts the floor at B+2000, ABOVE the fixed
# one: the 5 min of post-completion clearance is unconditional, and refusing at B+1900 there is the
# point, not a bug.
def test_a_long_running_cycle_raises_the_floor_above_the_fixed_1800():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 1900)},
        "engine_cycle_epoch_probe": {"rc": 0, "stdout": str(BOUNDARY + 1700)},
        "engine_window_override": "",
    }
    assert not truthy(assert_that(guard), v)  # 1900 >= 1800, but 1900 < 1700+300 -> refuse


def test_the_raised_floor_opens_at_completion_plus_300_exactly():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 2000)},
        "engine_cycle_epoch_probe": {"rc": 0, "stdout": str(BOUNDARY + 1700)},
        "engine_window_override": "",
    }
    assert truthy(assert_that(guard), v)  # inclusive on the raised floor too: `>=`


def test_undefined_probe_keeps_conservative_floor():
    guard = _window_guard()
    v = {"engine_epoch_probe": {"stdout": str(BOUNDARY + 500)}, "engine_window_override": ""}
    assert not truthy(assert_that(guard), v)


def test_ceiling_unchanged():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 14400 - 300)},  # last 5 min
        "engine_cycle_epoch_probe": {"rc": 0, "stdout": str(BOUNDARY + 108)},
        "engine_window_override": "",
    }
    assert not truthy(assert_that(guard), v)


def test_old_floor_still_passes_after_1800_without_journal():
    guard = _window_guard()
    v = {
        "engine_epoch_probe": {"stdout": str(BOUNDARY + 1800)},
        "engine_cycle_epoch_probe": {"rc": 1, "stdout": ""},
        "engine_window_override": "",
    }
    assert truthy(assert_that(guard), v)


def test_journal_probe_path_matches_the_engine_role_default():
    """The journal path site.yml probes must be the engine role's `engine_state_dir` default — the
    literal in site.yml is a deliberate choice (a statically-listed role's defaults are play-wide on
    this ansible-core, so the literal is not a necessity), and a relocation of that default would
    otherwise leave the floor permanently conservative (probe rc!=0 forever, guard 'working' but never
    early).
    """
    site_text = SITE.read_text()
    defaults = (SITE.parent / "roles" / "engine" / "defaults" / "main.yml").read_text()
    m = re.search(r"^engine_state_dir:\s*(\S+)", defaults, re.M)
    assert m, "engine_state_dir vanished from the engine role defaults"
    assert f"{m.group(1)}/journal/" in site_text


# --- when-scoping: a mis-scoped guard fires on the wrong host, or never.
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


# --- spec 00082 D1's second half for the overridable window guard, same shape as the two capture
# echoes above: the echo's `when:` is the assert's scoping AND the window condition NEGATED AND the
# override fragment.
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


# --- engine canary parity (spec 00083 D5): the capture parity assert, mirrored ------------------
# The engine has no secondary; the secondary's CAPTURE bake is the engine's canary gate. The mirror
# engages only when engine_image_digest differs from the running engine digest, fails CLOSED on an
# unreachable secondary (empty stdout -> refuse via the override path), and shares canary_override.


def test_engine_parity_refuses_unbaked_digest():
    tasks = load_tasks(ENGINE)
    guard = find_task(tasks, "engine canary parity — refuse an engine re-pin the secondary has not baked")
    v = {
        "engine_image_digest": "sha256:" + "ab" * 32,
        "engine_secondary_digest_probe": {"stdout": "ghcr.io/x/y@sha256:" + "cd" * 32},
        "canary_override": "",
    }
    assert not truthy(assert_that(guard), v)


def test_engine_parity_passes_when_secondary_runs_it():
    tasks = load_tasks(ENGINE)
    guard = find_task(tasks, "engine canary parity — refuse an engine re-pin the secondary has not baked")
    d = "sha256:" + "ab" * 32
    v = {
        "engine_image_digest": d,
        "engine_secondary_digest_probe": {"stdout": f"ghcr.io/x/y@{d}"},
        "canary_override": "",
    }
    assert truthy(assert_that(guard), v)


def test_engine_parity_fails_closed_on_unreachable_secondary():
    tasks = load_tasks(ENGINE)
    guard = find_task(tasks, "engine canary parity — refuse an engine re-pin the secondary has not baked")
    v = {"engine_image_digest": "sha256:" + "ab" * 32, "engine_secondary_digest_probe": {}, "canary_override": ""}
    assert not truthy(assert_that(guard), v)  # no stdout at all -> default('') -> refuse


def test_engine_parity_reason_override_is_accepted_and_boolean_is_not():
    tasks = load_tasks(ENGINE)
    guard = find_task(tasks, "engine canary parity — refuse an engine re-pin the secondary has not baked")
    v = {"engine_image_digest": "sha256:" + "ab" * 32, "engine_secondary_digest_probe": {"stdout": ""}}
    assert truthy(assert_that(guard), {**v, "canary_override": "rollback to the only digest carrying the fix"})
    assert not truthy(assert_that(guard), {**v, "canary_override": "true"})


def test_engine_parity_probe_skips_when_digest_already_running():
    tasks = load_tasks(ENGINE)
    probe = find_task(tasks, "probe — the secondary's running capture digest (engine canary parity)")
    d = "sha256:" + "ab" * 32
    v = {"engine_image_digest": d, "engine_running_parity_probe": {"stdout": f"ghcr.io/x/y@{d}"}}
    assert not truthy(" and ".join("(%s)" % c for c in when_conditions(probe)), v)


def test_engine_parity_probe_is_unreachable_tolerant_and_delegated():
    tasks = load_tasks(ENGINE)
    probe = find_task(tasks, "probe — the secondary's running capture digest (engine canary parity)")
    assert probe.get("ignore_unreachable") is True
    assert "difference(groups['engine_host'])" in probe["delegate_to"]


def test_engine_parity_echo_mirrors_the_negated_assert():
    tasks = load_tasks(ENGINE)
    echo = find_task(tasks, "engine canary override accepted — the reason, on the record")
    v_overridden = {
        "engine_image_digest": "sha256:" + "ab" * 32,
        "engine_secondary_digest_probe": {"stdout": ""},
        "canary_override": "rollback to the only digest carrying the fix",
    }
    conds = " and ".join("(%s)" % c for c in when_conditions(echo))
    # a dict fixture is `not skipped` under Templar
    assert truthy(conds, v_overridden)
    assert not truthy(conds, {**v_overridden, "canary_override": "true"})
    # The third case every sibling echo test carries: the gate is ACCEPTANCE, not presence. Parity
    # PASSES here, so the reason overrode nothing and printing a "why" would be a false record.
    d = "sha256:" + "ab" * 32
    baked = {**v_overridden, "engine_secondary_digest_probe": {"stdout": f"ghcr.io/x/y@{d}"}}
    assert not truthy(conds, baked)


# --- the engine mirror's when-side, mirroring test_canary_parity_refuses_an_unreachable_secondary
# and test_canary_probe_activates_only_on_an_actual_repin for the capture block: a fail-open rewrite
# of `is not skipped`, or a typo'd register name, stands the gate down silently.
ENGINE_UNREACHABLE = {"unreachable": True, "msg": "Failed to connect to the host via ssh"}


def test_engine_parity_when_reaches_the_refusal_on_an_unreachable_secondary():
    tasks = load_tasks(ENGINE)
    guard = find_task(tasks, "engine canary parity — refuse an engine re-pin the secondary has not baked")
    v = {
        "engine_image_digest": "sha256:" + "ab" * 32,
        "engine_secondary_digest_probe": ENGINE_UNREACHABLE,
        "canary_override": "",
    }
    assert truthy(when_conditions(guard), v), "the probe RAN (unreachable is not skipped) -- the assert must evaluate"
    # pins the fail-closed MECHANISM textually: `stdout is defined` would also reach a "true" when
    # here (wrongly) once the unreachable fixture happens to lack `stdout` -- the mechanism, not just
    # the outcome, must be `is not skipped`.
    assert "is not skipped" in guard["when"]


def test_engine_parity_probe_engages_on_an_actual_repin():
    tasks = load_tasks(ENGINE)
    probe = find_task(tasks, "probe — the secondary's running capture digest (engine canary parity)")
    v = {
        "engine_image_digest": "sha256:" + "ab" * 32,
        "engine_running_parity_probe": {"stdout": "ghcr.io/x/y@sha256:" + "cd" * 32},
    }
    assert truthy(when_conditions(probe), v)


def test_engine_parity_when_references_the_correct_probe_register_name():
    tasks = load_tasks(ENGINE)
    guard = find_task(tasks, "engine canary parity — refuse an engine re-pin the secondary has not baked")
    assert "engine_secondary_digest_probe" in guard["when"]


# --- the arming backstop. The one guard here whose subject is real money rather than a digest: it
# refuses a converge that would render the engine ARMED on a nautilus version whose attended
# order-semantics pass has not run.
ARMING = "arming backstop — refuse an ARMED converge on a nautilus version whose order-semantics pass has not run"
ARMING_REASON = "venue incident replay, re-run booked for the same day"

DISARMED_TEMPLATE = "exec_enabled = true\nexec_armed = false\nshadow_nav_eur = 1000\n"
ARMED_TEMPLATE = "exec_enabled = true\nexec_armed = true\nshadow_nav_eur = 1000\n"
# The fail-closed third case: neither literal, because the value became a Jinja expression.
TEMPLATED_ARMED = "exec_enabled = true\nexec_armed = {{ engine_exec_armed }}\nshadow_nav_eur = 1000\n"

VERIFIED_PIN = 'dependencies = [\n    "nautilus-trader==1.230.0",\n]\n'
UNVERIFIED_PIN_VERSION = "1.231.0"
UNVERIFIED_PIN = 'dependencies = [\n    "nautilus-trader==1.231.0",\n]\n'
NO_PIN = 'dependencies = [\n    "polars==1.0.0",\n]\n'
# A pin that is a PREFIX of the recorded version. This is the only shape that exercises Jinja's
# substring containment in the direction that used to vouch: "1.230" IS in "1.230.0".
PREFIX_PIN = 'dependencies = [\n    "nautilus-trader==1.230",\n]\n'
# PEP 440 arbitrary equality, which the committed pyproject uses. The guard must read the VERSION
# out of it and not the third `=`: a mis-read pin is in no record, so an armed converge on a version
# whose pass really did run is refused as unrecorded, and the only exit is arming_override -- the
# money guard routed around at exactly the moment it is supposed to hold.
TRIPLE_EQUALS_VERIFIED_PIN = 'dependencies = [\n    "nautilus-trader===1.230.0",\n]\n'
TRIPLE_EQUALS_UNVERIFIED_PIN = 'dependencies = [\n    "nautilus-trader===1.231.0",\n]\n'
RECORD = ["1.230.0"]
_UNSET = object()  # so a test can pass record=None and mean it


def _pinned_nautilus_version() -> str:
    """The nautilus version the committed pyproject pins, parsed independently of the guard."""
    deps = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["dependencies"]
    entries = [d.strip() for d in deps if re.match(r"^nautilus-trader\b", d.strip())]
    assert len(entries) == 1, f"expected exactly one nautilus-trader dependency, found {entries}"
    version = re.sub(r"^nautilus-trader\s*={2,3}\s*", "", entries[0])
    assert version != entries[0], f"the nautilus-trader dependency must pin by equality: {entries[0]!r}"
    return version


@pytest.mark.parametrize(
    ("record", "why"),
    [
        # Jinja's `in` is SUBSTRING containment on a string, so a record whose list degraded to a
        # comma-joined string VOUCHES for a version it never verified.
        ("1.230.0, 1.231.0", "a comma-joined string"),
        # ...and KEY containment on a mapping, which vouches the same way.
        ({"1.231.0": "note"}, "a mapping keyed by version"),
        (None, "null"),
        (42, "a scalar that is not even a sequence"),
        # A MIXED list passes every structural test -- proper sequence, not a string, not a mapping
        # -- so without an element-type check the Jinja half vouches for the real version in it while
        # cli.engine.execgate collapses the same record to the empty set. The pin must be IN the list:
        # beside a non-string, an unguarded ternary vouches and a guarded one refuses.
        ([UNVERIFIED_PIN_VERSION, 1231], "a list whose elements are not all strings"),
        ("", "an empty string"),
    ],
)
def test_arming_backstop_refuses_a_record_that_is_not_a_proper_list(record, why):
    """A malformed record is a CANNOT-VOUCH, and this guard's contract is cannot-vouch => refuse."""
    task = find_task(load_tasks(ENGINE), ARMING)
    variables = _arming_vars(ARMED_TEMPLATE, UNVERIFIED_PIN, record=record)
    assert not truthy(assert_that(task), variables), why


def test_arming_backstop_refuses_a_pin_that_is_only_a_PREFIX_of_a_string_record():
    """A pin that is only a PREFIX of the recorded version never vouches, string record or list —
    `"1.230" in "1.230.0"` is True under Jinja's substring containment.
    """
    task = find_task(load_tasks(ENGINE), ARMING)
    variables = _arming_vars(ARMED_TEMPLATE, PREFIX_PIN, record="1.230.0")
    assert not truthy(assert_that(task), variables)
    # ...and the same prefix pin against a PROPER list record refuses too, on plain non-membership.
    assert not truthy(assert_that(task), _arming_vars(ARMED_TEMPLATE, PREFIX_PIN, record=["1.230.0"]))


def test_a_malformed_record_still_leaves_a_disarmed_converge_alone():
    """Inertness survives the shape check: a broken record must not block the disarmed converges
    the fleet actually runs -- only an ARMED one is ever refused on it."""
    task = find_task(load_tasks(ENGINE), ARMING)
    variables = _arming_vars(DISARMED_TEMPLATE, UNVERIFIED_PIN, record="1.230.0, 1.231.0")
    assert truthy(assert_that(task), variables)


def _arming_vars(template: str, pyproject: str, override: str = "", record=_UNSET) -> dict:
    return {
        "engine_config_template_text": template,
        "engine_pyproject_text": pyproject,
        "engine_verified_nautilus": RECORD if record is _UNSET else record,
        "arming_override": override,
    }


@pytest.mark.parametrize(
    ("template", "pyproject", "expected", "why"),
    [
        # INERT on every converge the fleet actually runs today: disarmed, so the version is not
        # even consulted. This must hold or every converge from now on needs an override.
        (DISARMED_TEMPLATE, UNVERIFIED_PIN, True, "disarmed on an unverified version"),
        (DISARMED_TEMPLATE, VERIFIED_PIN, True, "disarmed on a verified version"),
        (DISARMED_TEMPLATE, NO_PIN, True, "disarmed with no nautilus pin at all"),
        # THE CONSTRUCTED DEFECT: an armed converge on a version absent from the synthetic RECORD.
        (ARMED_TEMPLATE, UNVERIFIED_PIN, False, "armed on an unverified version"),
        # TRUE POSITIVE: a healthy armed converge on a verified version must PASS, or the guard
        # refuses every legitimate probe window and would simply be routed around.
        (ARMED_TEMPLATE, VERIFIED_PIN, True, "armed on a verified version"),
        # Fail-closed on inputs the guard cannot read: a templated arming value counts as armed,
        # and an unparseable pin is in no record.
        (TEMPLATED_ARMED, UNVERIFIED_PIN, False, "arming value templated away from the literal"),
        (TEMPLATED_ARMED, VERIFIED_PIN, True, "templated arming is still fine on a verified version"),
        (ARMED_TEMPLATE, NO_PIN, False, "armed with an unparseable pin"),
        # Arbitrary equality, both directions. The true positive is the one that discriminates: a
        # guard that swallowed the operator into the capture reads the version as "=1.230.0",
        # which is in no record, so it would refuse this row.
        (ARMED_TEMPLATE, TRIPLE_EQUALS_VERIFIED_PIN, True, "armed on a verified version pinned with ==="),
        (ARMED_TEMPLATE, TRIPLE_EQUALS_UNVERIFIED_PIN, False, "armed on an unverified version pinned with ==="),
    ],
)
def test_arming_backstop_semantics(template, pyproject, expected, why):
    task = find_task(load_tasks(ENGINE), ARMING)
    assert truthy(assert_that(task), _arming_vars(template, pyproject)) is expected, why


@pytest.mark.parametrize(
    ("override", "expected"),
    [("", False), ("short", False), ("true", False), ("yes", False), (ARMING_REASON, True)],
)
def test_arming_backstop_override_demands_a_reason(override, expected):
    """A bare flag must not open this gate -- the override has to carry a why, like its siblings."""
    task = find_task(load_tasks(ENGINE), ARMING)
    variables = _arming_vars(ARMED_TEMPLATE, UNVERIFIED_PIN, override=override)
    assert truthy(assert_that(task), variables) is expected


@pytest.mark.parametrize(
    ("template", "pyproject", "override", "expected"),
    [
        (ARMED_TEMPLATE, UNVERIFIED_PIN, ARMING_REASON, True),  # overrode something -> echo the why
        (ARMED_TEMPLATE, UNVERIFIED_PIN, "", False),  # refused; there is no why to echo
        (ARMED_TEMPLATE, VERIFIED_PIN, ARMING_REASON, False),  # verified -> nothing was overridden
        (DISARMED_TEMPLATE, UNVERIFIED_PIN, ARMING_REASON, False),  # disarmed -> nothing was overridden
    ],
)
def test_arming_override_echo_fires_only_on_an_accepted_override(template, pyproject, override, expected):
    task = find_task(load_tasks(ENGINE), "arming override accepted — the reason, on the record")
    assert truthy(when_conditions(task), _arming_vars(template, pyproject, override=override)) is expected


def test_arming_backstop_reads_the_real_committed_files():
    """Both directions from the REAL role, template and pyproject: a recorded version passes, an
    absent one refuses.

    The membership list is fed state-agnostically -- the true positive gets the pinned version
    present, the bite gets it absent -- because a bumped-but-disarmed repo is a blessed state, and
    asserting the pin IS recorded would go red for the whole legitimate interim between a bump
    landing and its attended pass running.

    The pinned version is read with tomllib, never a copy of the guard's own regex: a re-derivation
    matches itself and passes on a mangled read.
    """
    record = json.loads((REPO / "cli" / "engine" / "order-semantics-verified.json").read_text())
    versions = record["verified_nautilus_versions"]
    pin = _pinned_nautilus_version()
    template = (ANSIBLE / "roles" / "engine" / "templates" / "zcrypto.toml.j2").read_text()

    assert re.search(r"(?m)^exec_armed\s*=\s*false\s*$", template), "the committed template must render disarmed"
    assert "1.230.0" in versions, "the version whose attended pass actually ran must be recorded"
    task = find_task(load_tasks(ENGINE), ARMING)
    armed = re.sub(r"(?m)^exec_armed\s*=\s*false\s*$", "exec_armed = true", template)
    base = {
        "engine_config_template_text": armed,
        "engine_pyproject_text": (REPO / "pyproject.toml").read_text(),
        "arming_override": "",
    }
    # TRUE POSITIVE: a recorded version must NOT be refused. Fed `versions + [pin]` rather than
    # `versions` so this half holds in the interim where the bump has landed and its pass has not.
    assert truthy(assert_that(task), {**base, "engine_verified_nautilus": [*versions, pin]}), (
        "the guard refuses an armed converge on a version the record lists as verified"
    )
    # THE BITE, against the real files: drop the pinned version and the guard must refuse again.
    assert not truthy(assert_that(task), {**base, "engine_verified_nautilus": [v for v in versions if v != pin]})


# --- ops-role guards. `ops_` fixture keys for the same var-naming reason as the engine block above.
# The ops role's convention (roles/ops/defaults/main.yml: ops_image_digest has NO default) is that a
# digestless config/alloy-only converge SKIPS every image-consuming task, so each guard here carries
# `when: ops_image_digest is defined` -- refusing such a converge is a broken role, not a strict one.
OPS = ANSIBLE / "roles" / "ops" / "tasks" / "main.yml"
OPS_DIGEST_PREFLIGHT = "preflight — refuse a digest the host has not pulled"


def test_ops_digest_preflight():
    task = find_task(load_tasks(OPS), OPS_DIGEST_PREFLIGHT)
    assert not truthy(assert_that(task), {"ops_digest_probe": {"rc": 1}})
    assert truthy(assert_that(task), {"ops_digest_probe": {"rc": 0}})


def test_ops_digest_preflight_skips_a_digestless_converge():
    # Without this, an alloy-only converge (no `-e ops_image_digest`) would hit `ops_digest_probe.rc`
    # from a probe that was itself skipped, and refuse the run this role explicitly supports.
    task = find_task(load_tasks(OPS), OPS_DIGEST_PREFLIGHT)
    assert truthy(when_conditions(task), {"ops_image_digest": "sha256:" + "e" * 64})
    assert not truthy(when_conditions(task), {})


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
    probed = {
        "ops_liquidations_pin_probe": {"rc": 0},
        "ops_liquidations_compose_stat": {"stat": {"exists": True, "readable": True}},
    }
    assert truthy(when_conditions(task), {**probed, "ops_image_digest": "sha256:" + "e" * 64})
    assert not truthy(when_conditions(task), probed)


# --- liquidations rc split (spec 00083 D9): absent file stands down, unreadable file refuses -----


def _liq_readable_guard():
    tasks = load_tasks(OPS)
    return find_task(tasks, "liquidations — an unreadable compose file is a fault, never a first-provision skip")


def _liq_decision_guard():
    tasks = load_tasks(OPS)
    return find_task(tasks, LIQUIDATIONS)


def test_unreadable_compose_refuses():
    v = {
        "ops_image_digest": "sha256:" + "ab" * 32,
        "ops_liquidations_compose_stat": {"stat": {"exists": True, "readable": False}},
    }
    assert not truthy(assert_that(_liq_readable_guard()), v)


# The stat MODULE's own failure is a fourth shape, distinct from the three the rc split names: an
# EACCES on the path (an unreadable PARENT dir stats EACCES, not ENOENT) registers no `stat` key at
# all, and `stat.exists | default(false)` cannot tell that shape from "absent".
def test_a_failed_stat_probe_reaches_the_refusal():
    v = {
        "ops_image_digest": "sha256:" + "ab" * 32,
        "ops_liquidations_compose_stat": {"failed": False, "msg": "Permission denied"},
    }
    conds = " and ".join("(%s)" % c for c in when_conditions(_liq_readable_guard()))
    assert truthy(conds, v), "a failed probe must REACH the assert, never skip it"
    assert not truthy(assert_that(_liq_readable_guard()), v)


def test_readable_compose_passes_the_readability_guard():
    v = {
        "ops_image_digest": "sha256:" + "ab" * 32,
        "ops_liquidations_compose_stat": {"stat": {"exists": True, "readable": True}},
    }
    assert truthy(assert_that(_liq_readable_guard()), v)


def test_absent_file_skips_both_guards():
    v = {
        "ops_image_digest": "sha256:" + "ab" * 32,
        "ops_liquidations_compose_stat": {"stat": {"exists": False}},
    }
    for guard in (_liq_readable_guard(), _liq_decision_guard()):
        conds = " and ".join("(%s)" % c for c in when_conditions(guard))
        assert not truthy(conds, v)


def test_decision_guard_engages_when_file_exists():
    v = {
        "ops_image_digest": "sha256:" + "ab" * 32,
        "ops_liquidations_compose_stat": {"stat": {"exists": True, "readable": True}},
        "ops_liquidations_pin_probe": {"rc": 1, "stdout": ""},
        "liquidations_decision": "",
    }
    conds = " and ".join("(%s)" % c for c in when_conditions(_liq_decision_guard()))
    assert truthy(conds, v)
    assert not truthy(assert_that(_liq_decision_guard()), v)  # empty stdout + no decision -> refuse


def test_stat_probe_resolves_symlinks():
    # Textual pin, not a Templar fixture: `follow: true` is what makes a dangling compose.yaml
    # symlink read as absent -- spec 00083 D9's `test -e`/`test -r` semantics -- instead of tripping
    # the readability guard's chmod/chown fail_msg on a target that was never a permission fault.
    task = find_task(load_tasks(OPS), "probe — the deployed liquidations compose file (existence vs readability)")
    assert task["ansible.builtin.stat"]["follow"] is True
    # Spec 00083 D9 also specifies `failed_when: false`: a stat MODULE failure would otherwise abort
    # the play — dropping the host from every later play — instead of letting the two guards below
    # decide from what the probe registered.
    assert task["failed_when"] is False


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

    task = find_task(load_tasks(OPS), "enable + start the replay + panel + tape-bars timers")
    loop_expr = task["loop"]
    held = Templar(loader=DataLoader(), variables={"ops_panel_timer_hold": True}).template(trust_as_template(loop_expr))
    live = Templar(loader=DataLoader(), variables={"ops_panel_timer_hold": False}).template(trust_as_template(loop_expr))
    # the hold is OPT-IN: an ordinary converge (variable unset) must still arm the panel timer.
    unset = Templar(loader=DataLoader(), variables={}).template(trust_as_template(loop_expr))
    # ONLY the panel timer is held: the hold exists for the panel-regeneration window, and tape-bars
    # writes a different tree that the rebuild never touches.
    assert "panel-materialize" not in held and "verify-replay" in held and "verified-replay" in held
    assert "tape-bars" in held and "tape-bars" in live and "tape-bars" in unset
    assert "panel-materialize" in live
    assert "panel-materialize" in unset


def test_panel_regenerate_is_installed_by_the_ops_role():
    tasks = load_tasks(OPS)
    name = "install the panel regenerate flow (delete-and-rebuild with its refusals)"
    task = find_task(tasks, name)
    assert task["ansible.builtin.template"]["dest"] == "/usr/local/sbin/zcrypto-panel-regenerate"
    assert task["ansible.builtin.template"]["mode"] == "0755"
    # TOP-LEVEL and ungated is the load-bearing half, and find_task recurses into `block:` -- so the
    # assertions above stay green with this task moved back inside the digest gate, which is exactly
    # the regression that stops the script landing on a digestless converge. Scan the top level.
    assert name in [t.get("name") for t in tasks]
    assert "when" not in task


OPS_PINS = "pins recording — refuse to replace a digest fleet-pins.md does not record"
# The probe behind this inspects the liquidations-poll CONTAINER, never the compose file: the file
# can pin one digest while the container runs another.
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
# an unbackfillable data gap. The ack is a BOOLEAN, unlike the D1 free-text overrides: the debug task
# displays the diff first, so it acknowledges shown content rather than substituting for evidence.
DOCKER = ANSIBLE / "roles" / "docker" / "tasks" / "main.yml"
DAEMON_JSON_ACK = "daemon.json — refuse an unacknowledged change (its handler bounces dockerd)"


@pytest.mark.parametrize(
    ("rc", "ack", "expected"),
    [
        (1, False, False),  # rendered output differs, nothing acked -> refuse
        (0, False, True),  # identical render -> no handler fires, no ack owed
        (1, True, True),  # differs, operator acked the displayed diff -> proceed
        # rc 2 is diff's "trouble" exit -- here, an absent /etc/docker/daemon.json (first provision).
        # That is a change the handler would act on, so it must refuse, not pass.
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


# One contract, so one test: probe -> show -> ask -> act. ORDER is the whole of it -- a guard sitting
# AFTER the template task it protects is decorative, dockerd having already been notified.
def test_daemon_json_guard_precedes_the_task_whose_handler_bounces_dockerd():
    tasks = load_tasks(DOCKER)
    probe = task_index(tasks, "probe — diff the pending daemon.json against the deployed one")
    show = task_index(tasks, "daemon.json — show the pending change before asking for an ack")
    ask = task_index(tasks, DAEMON_JSON_ACK)
    assert probe < show  # nothing to display until the diff has been registered
    assert show < ask  # the ack is only meaningful once the operator has seen the diff
    assert ask < task_index(tasks, "configure the docker daemon (bounded json-file log driver)")


# --- bootstrap re-bootstrap refusal. Deliberately scoped to the CAPTURE play: bootstrap.yml holds
# three plays, and only this one writes an sshd drop-in, which is the damage the refusal names. The
# ack is a BOOLEAN (like the daemon.json one, unlike the D1 free-text overrides): the refusal cites
# concrete shown evidence -- the existing user -- rather than substituting for absent evidence.
BOOTSTRAP = ANSIBLE / "bootstrap.yml"
REBOOTSTRAP = "refuse to re-bootstrap an already-provisioned host"
REBOOTSTRAP_PROBE = "probe — the zcrypto-deploy user (re-bootstrap refusal)"
PRIMARY_REFUSAL = "refuse to bootstrap the live primary unless explicitly asked"


def capture_play_tasks() -> list[dict]:
    # load_tasks on bootstrap.yml returns a PLAY list, and task_index is top-level-flat by design, so
    # the ordering assertion has to index inside one play's own task list. Selecting the play by
    # `hosts` also pins the guard's deliberate narrow -- it belongs to the capture play, not ops/access.
    play = next(p for p in load_tasks(BOOTSTRAP) if p["hosts"] == "capture_host")
    return play["tasks"]


@pytest.mark.parametrize(
    ("variables", "expected"),
    [
        ({"bootstrap_deploy_user_probe": {"rc": 0}, "rebootstrap": False}, False),  # provisioned, no flag -> refuse
        ({"bootstrap_deploy_user_probe": {"rc": 2}}, True),  # getent found no such user -> first provision
        ({"bootstrap_deploy_user_probe": {"rc": 0}, "rebootstrap": True}, True),  # genuine rebuild
    ],
)
def test_rebootstrap_refusal(variables, expected):
    task = find_task(capture_play_tasks(), REBOOTSTRAP)
    assert truthy(assert_that(task), variables) is expected


# ORDER is a property of its own: the assert reads `bootstrap_deploy_user_probe`, so a probe placed
# after it leaves the fact undefined, and both guards must precede the provisioning tasks they gate.
def test_rebootstrap_guard_follows_the_primary_refusal_and_its_probe():
    tasks = capture_play_tasks()
    primary = task_index(tasks, PRIMARY_REFUSAL)
    probe = task_index(tasks, REBOOTSTRAP_PROBE)
    refusal = task_index(tasks, REBOOTSTRAP)
    assert primary < probe  # the narrower primary refusal still speaks first
    assert probe < refusal  # nothing to assert on until the probe has registered
    assert refusal < task_index(tasks, "zcrypto-deploy sudo user")


# --- the ops role's new-timer check-mode guard ------------------------------------------------
# Without it ANY newly added timer is unconvergeable through the sanctioned path: under --check the
# unit file is never really written, so enable+start cannot find it, the preview fails, and
# converge.sh refuses the real pass while the preview is red.
OPS_TIMER_ENABLE = "enable + start the replay + panel + tape-bars timers"


@pytest.mark.parametrize(
    ("check_mode", "units_changed", "expected", "why"),
    [
        (True, True, False, "first install under --check: the unit was never written, so skip"),
        (True, False, True, "check mode but units unchanged: they exist, so preview the enable"),
        (False, True, True, "REAL run: the render already wrote them — never skip"),
        (False, False, True, "real run, nothing new: enable is idempotent and still runs"),
    ],
)
def test_the_new_timer_guard_never_skips_a_real_run(check_mode, units_changed, expected, why):
    task = find_task(load_tasks(OPS), OPS_TIMER_ENABLE)
    variables = {
        "ansible_check_mode": check_mode,
        "ops_unit_install": {"changed": units_changed},
    }
    assert truthy(when_conditions(task), variables) is expected, why


# --- The probe must name a container that EXISTS ------------------------------------------------
# A pins probe naming a literal the compose template does not render makes `docker inspect` return
# rc=1 forever, so the guard's `when: ... rc == 0` gate skips the assert on every ops converge --
# fail-OPEN. Both sites read `ops_liquidations_container` so they cannot disagree.
OPS_TASKS = ANSIBLE / "roles" / "ops" / "tasks" / "main.yml"
OPS_DEFAULTS = ANSIBLE / "roles" / "ops" / "defaults" / "main.yml"
OPS_COMPOSE_TEMPLATE = ANSIBLE / "roles" / "ops" / "templates" / "compose.yaml.j2"


def test_ops_pins_probe_inspects_the_container_the_compose_template_names():
    probe = find_task(load_tasks(OPS_TASKS), "probe — the currently-running digest this converge would replace (pins recording)")
    command = probe["ansible.builtin.command"]
    rendered = yaml.safe_load(OPS_DEFAULTS.read_text())["ops_liquidations_container"]

    # the probe inspects the variable, never a literal -- a literal is how the two drifted before
    assert "{{ ops_liquidations_container }}" in command, (
        f"the pins probe must inspect ops_liquidations_container, not a literal: {command!r}"
    )
    # and the template names the same variable, so they cannot disagree
    template = OPS_COMPOSE_TEMPLATE.read_text()
    assert "container_name: {{ ops_liquidations_container }}" in template, (
        "the liquidations compose template must render container_name from ops_liquidations_container"
    )
    # the value is a container name, not a CLI subcommand: the entrypoint runs `zcrypto
    # liquidations-poll`, and naming THAT is the exact defect this test exists to prevent
    assert rendered != "liquidations-poll", "ops_liquidations_container is the entrypoint command, not a container name"
    # and EVERY entrypoint the template can render still ends in that subcommand. Asserted over
    # both branches, not one: the ops host defines `logship_loki_token`, so production renders
    # ["zcrypto", "--ship-logs", "liquidations-poll"] and a check for the bare
    # '"zcrypto", "liquidations-poll"' fragment would pin only the branch production never takes.
    entrypoints = [l.strip() for l in template.splitlines() if l.strip().startswith("entrypoint:")]
    assert len(entrypoints) == 2, f"expected both logship branches to render an entrypoint: {entrypoints}"
    for line in entrypoints:
        assert line.endswith('"liquidations-poll"]'), (
            f"every rendered entrypoint must invoke the liquidations-poll subcommand: {line}"
        )


ACCESS_TASKS = ANSIBLE / "roles" / "access" / "tasks" / "main.yml"
_RELAY_GATE = "the ssh relay is running the target this play renders"
_RELAY_FLUSH = "apply pending handlers before the relay drift gate"


def _relay_vars(running: str | None, rendered: str | None, **extra) -> dict:
    # the guard reads .stdout off registered results; None models a task that never ran
    v = {
        "access_ssh_relay_running": {} if running is None else {"stdout": running},
        "access_ssh_relay_rendered": {} if rendered is None else {"stdout": rendered},
    }
    v.update(extra)
    return v


@pytest.mark.parametrize(
    "running,rendered,expected,why",
    [
        # NOT the production target on either side: a fixture set that only ever renders
        # 10.99.0.2:22 cannot tell the committed expression from one that hardcodes it, and the
        # rendered target IS hardcoded in the template -- so that mutation would be invisible.
        ("10.99.0.7:22", "10.99.0.7:22", True, "healthy: the running argv is the rendered target"),
        ("10.99.0.2:22", "10.99.0.3:22", False, "the template's target MOVED and the process kept the old one"),
        ("__not_running__", "10.99.0.7:22", True, "healthy: socket-activated and never triggered, so it cannot be drifted"),
        ("192.168.1.9:22", "10.99.0.2:22", False, "DRIFTED: the process kept a target the unit no longer renders"),
        ("/usr/lib/systemd/systemd-socket-proxyd", "10.99.0.2:22", False, "argv carried no target at all"),
        ("", "", False, "both empty -- equal, but proves nothing; must not read as healthy"),
        # a reader that did not run at all: the gate's `| default('')` fallbacks are what decide
        # these two rows, and an absent read must never count as a healthy one.
        (None, "10.99.0.7:22", False, "the running reader never ran; an absent read is not a healthy one"),
        ("10.99.0.7:22", None, False, "the rendered reader never ran; nothing to compare against"),
    ],
)
def test_the_ssh_relay_drift_gate_separates_drift_from_health(running, rendered, expected, why):
    """The gate must pass BOTH healthy shapes and fail every drifted one.

    `__not_running__` is healthy, not drifted: the socket is `Accept=no` and the service has no
    `[Install]`, so it is inactive from boot until the first connection and `MainPID` reads 0.
    """
    gate = find_task(load_tasks(ACCESS_TASKS), _RELAY_GATE)
    assert truthy(assert_that(gate), _relay_vars(running, rendered)) is expected, why


def test_the_ssh_relay_drift_gate_takes_no_override():
    """spec 00082 D1 reserves overrides for canary/pins/engine-window; this gate takes none."""
    gate = find_task(load_tasks(ACCESS_TASKS), _RELAY_GATE)
    rendered = " ".join(assert_that(gate)) + " " + str(gate["ansible.builtin.assert"].get("fail_msg", ""))
    assert "override" not in rendered.lower(), f"the relay gate must not grow an override (spec 00082 D1): {rendered}"
    # and a drifted host must fail no matter what stray variable is set
    drifted = _relay_vars("192.168.1.9:22", "10.99.0.2:22", access_ssh_relay_override="a stated reason, long enough")
    assert not truthy(assert_that(gate), drifted), "no variable may buy past this gate"


def test_the_ssh_relay_drift_gate_is_skipped_under_check_and_runs_last():
    """The gate skips under check mode and is the role's last task, so nothing it can fail sits below it.

    `converge.sh` previews with `--check --diff` and ABORTS the run if the preview fails, so a gate
    that tripped there would block the whole converge -- including the pinned-leaves and Caddyfile
    tasks that are the client-cert revocation path.
    """
    tasks = load_tasks(ACCESS_TASKS)
    gate = find_task(tasks, _RELAY_GATE)
    assert "not ansible_check_mode" in when_conditions(gate), "the gate must not evaluate under --check"
    assert task_index(tasks, _RELAY_GATE) == len(tasks) - 1, "the gate must be the role's last task"

    # Pinned by the task's ACTION, not by its name: force_handlers defaults False and is set nowhere,
    # so a flush that stopped being a flush would strand `reload caddy` -- the handler that makes a
    # pinned-leaf revocation take effect -- while a name-only assertion stayed green.
    flush = task_index(tasks, _RELAY_FLUSH)
    assert flush < task_index(tasks, _RELAY_GATE), "handlers must flush before the gate can fail the host"
    assert tasks[flush].get("ansible.builtin.meta") == "flush_handlers", (
        f"the pre-gate task must actually flush handlers, not merely be named so: {tasks[flush]}"
    )


def test_the_ssh_relay_readers_read_the_PROCESS_and_the_FILE_not_the_file_twice():
    """The running reader must read the PROCESS's argv and the rendered reader the unit FILE.

    Repointing the running reader at the unit file makes both sides read the same bytes: the gate
    then passes on every converge while the relay drifts unbounded -- the Alloy drift failure the
    `Shared converge mechanics` block records (`.claude/skills/zcrypto-rollout-image/SKILL.md`).
    """
    tasks = load_tasks(ACCESS_TASKS)
    running = find_task(tasks, "read the ssh relay's running target")["ansible.builtin.shell"]["cmd"]
    rendered = find_task(tasks, "read the ssh relay's rendered target")["ansible.builtin.shell"]["cmd"]

    assert "/proc/" in running and "cmdline" in running, f"the running reader must read the process's argv: {running!r}"
    assert "/etc/systemd/system/" not in running, (
        f"the running reader must NOT read the unit file -- that makes both sides the same read: {running!r}"
    )
    assert "ExecStart" not in running, f"the running reader must not parse ExecStart: {running!r}"
    assert "/etc/systemd/system/zaccess-ssh-proxy.service" in rendered, f"the rendered reader must read the unit file: {rendered!r}"
    assert "ExecStart" in rendered, f"the rendered reader must take the target from ExecStart=: {rendered!r}"
    for name, cmd in (("running", running), ("rendered", rendered)):
        assert "zaccess-ssh-proxy" in cmd, f"the {name} reader must name the relay it is about: {cmd!r}"

    # the sentinel the assert special-cases must be the one the shell actually emits, or the
    # not-running case silently becomes a drift report on every socket-activated host
    gate = " ".join(assert_that(find_task(tasks, _RELAY_GATE)))
    sentinel = "__not_running__"
    assert sentinel in running and sentinel in gate, (
        f"the shell emits and the assert excuses the same sentinel; running={running!r} gate={gate!r}"
    )


@pytest.mark.parametrize(
    "stub_pid,expect_sentinel,why",
    [
        ("0", True, "MainPID 0 means socket-activated and never triggered -- the sentinel is correct"),
        (
            "SELF",
            False,
            "a RUNNING relay must never read as not-running: the assert excuses the sentinel, so emitting it while alive makes the gate pass on a drifted relay forever",
        ),
    ],
)
def test_the_ssh_relay_running_reader_emits_the_sentinel_only_when_not_running(tmp_path, stub_pid, expect_sentinel, why):
    """The reader emits `__not_running__` only when the unit is not running (MainPID 0).

    Behavioural, against the committed `cmd` with a stub `systemctl`: an inverted `[ "$pid" = "0" ]`
    keeps every structural assertion green while making a live relay read as not-running.
    """
    import os
    import subprocess

    cmd = find_task(load_tasks(ACCESS_TASKS), "read the ssh relay's running target")["ansible.builtin.shell"]["cmd"]
    pid = str(os.getpid()) if stub_pid == "SELF" else stub_pid
    stub = tmp_path / "systemctl"
    stub.write_text("#!/bin/bash\n" + f'echo "{pid}"\n')
    stub.chmod(0o755)

    out = subprocess.run(
        ["bash", "-c", cmd],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
    ).stdout.strip()

    assert (out == "__not_running__") is expect_sentinel, f"{why} -- reader emitted {out!r}"
    if not expect_sentinel:
        # ...and it must be THIS process's own LAST argv token: asserting only "not the sentinel"
        # lets `| tail -1` become `| head -1`. removesuffix, not rstrip: cmdline is `arg0\0...\0argN\0`
        # and ends `\0\0` when argN is EMPTY -- rstrip eats both, so argv[-1] becomes the PREVIOUS arg
        # while the reader correctly yields "", failing the test for something that is not the defect.
        argv = Path(f"/proc/{os.getpid()}/cmdline").read_bytes().removesuffix(b"\0").split(b"\0")
        assert out == argv[-1].decode(), f"expected the real last argv token {argv[-1].decode()!r}, got {out!r}"


def test_the_ssh_relay_gate_cannot_be_neutered_by_a_task_modifier():
    """This gate's only effect is failing the play, so `failed_when: false` reduces it to decoration."""
    gate = find_task(load_tasks(ACCESS_TASKS), _RELAY_GATE)
    assert "failed_when" not in gate, f"failed_when would make this gate a no-op: {gate.get('failed_when')!r}"
    assert not gate.get("ignore_errors"), "ignore_errors would make this gate a no-op"
    assert "override" not in str(gate.get("when", "")).lower(), "no override may hide in the when: either"
    # exactly one condition: `when: [not ansible_check_mode, false]` keeps the substring check true
    # while the gate never evaluates at all
    assert when_conditions(gate) == ["not ansible_check_mode"], (
        f"the gate's when: must be exactly the check-mode skip: {when_conditions(gate)}"
    )


AGENTBOARD_UNIT = ANSIBLE / "roles" / "access_ops" / "templates" / "zaccess-agentboard.service.j2"
AGENTBOARD_START = ANSIBLE / "roles" / "access_ops" / "templates" / "zaccess-agentboard-start.sh.j2"
ACCESS_OPS_TASKS = ANSIBLE / "roles" / "access_ops" / "tasks" / "main.yml"


def _directives(unit: str) -> dict[str, list[str]]:
    """Map systemd section -> its directive lines, comments and blank lines dropped."""
    section, out = None, {}
    for raw in unit.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line
            continue
        out.setdefault(section, []).append(line)
    return out


def test_agentboard_killmode_and_mainpid_stay_coupled():
    """`KillMode=process` is only safe because the unit ExecStarts the SERVER, not the node shim.

    The two halves live in two files with nothing coupling them. Dropping `KillMode=process`
    restores the control-group SIGKILL that takes the operator's tmux sessions with it; reverting
    the ExecStart to the shim while KillMode stays lets systemd kill the wrapper while the real
    server keeps `:4040`, so the next start cannot bind.
    """
    unit = AGENTBOARD_UNIT.read_text()
    start = AGENTBOARD_START.read_text()

    # Section-aware and LAST-WINS, because three regressions all leave a bare `KillMode=process`
    # somewhere in the file: commenting it out; appending a second `KillMode=control-group` (a scalar
    # setting takes its last assignment); and moving it into [Unit], where it is an unknown key that
    # systemd warns about and ignores, falling back to control-group.
    section, per_section = None, {}
    for raw in unit.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line
            continue
        if re.match(r"KillMode\s*=", line):
            per_section.setdefault(section, []).append(line.split("=", 1)[1].strip())
    assert set(per_section) <= {"[Service]"}, f"KillMode outside [Service] is silently ignored: {per_section}"
    assert per_section.get("[Service]"), "the unit must carry an active KillMode in [Service]"
    assert per_section["[Service]"][-1] == "process", f"the LAST KillMode in [Service] decides: {per_section['[Service]']}"

    # The role comment explaining WHY KillMode matters rests entirely on this line -- and on it being
    # in [Unit]. Relocated into [Service] systemd reports "Unknown key 'Requires' in section
    # [Service], ignoring", so the propagation path would be gone while a section-blind check stayed
    # green. Same walk as above.
    requires = [sec for sec, keys in _directives(unit).items() for k in keys if k == "Requires=wg-quick@zaccess0.service"]
    assert requires == ["[Unit]"], f"Requires=wg-quick must live in [Unit] or systemd ignores it: {requires or 'absent'}"

    # ExecStart: strip before matching, because systemd does. An INDENTED `  ExecStart=` empty-value
    # reset followed by a shim ExecStart loads clean with the last one in effect, so an unstripped
    # startswith() would see one good line and miss the override entirely.
    execstart = [l.strip().split("=", 1)[1].strip() for l in unit.splitlines() if re.match(r"\s*ExecStart\s*=", l)]
    assert len(execstart) == 1, f"expected exactly one ExecStart (an empty-value reset counts): {execstart}"
    assert execstart[0], "an empty ExecStart= resets the list and lets a later one take over"
    assert not execstart[0].startswith("/bin/bash -c"), (
        f"ExecStart must run the rendered script, not an inline shell that execs the PATH shim: {execstart[0]}"
    )

    # ...rendered by a task whose SRC is the script this test actually reads, and executable. Checking
    # the dest against the role's dests alone lets the task's src be swapped for another template.
    renderers = [
        t["ansible.builtin.template"]
        for t in load_tasks(ACCESS_OPS_TASKS)
        if "ansible.builtin.template" in t and t["ansible.builtin.template"].get("dest") == execstart[0]
    ]
    assert len(renderers) == 1, f"ExecStart={execstart[0]} is rendered by {len(renderers)} tasks in this role"
    assert renderers[0]["src"] == AGENTBOARD_START.name, (
        f"the ExecStart'd file must be rendered from {AGENTBOARD_START.name}, not {renderers[0]['src']}"
    )
    assert str(renderers[0].get("mode")) == "0755", f"the ExecStart'd script must be executable: {renderers[0].get('mode')}"

    # and that script must exec the resolved binary, never the shim
    # code lines only: the script's own header explains why it does NOT `exec agentboard`, and a
    # naive substring check over the whole file flags that explanation as the defect it warns about.
    code = [l.strip() for l in start.splitlines() if l.strip() and not l.strip().startswith("#")]
    execs = [l for l in code if l.startswith("exec ")]
    assert execs == ['exec "$bin"'], f"the start script must exec the resolved server binary: {execs}"
    assert not any("exec agentboard" in l for l in code), "exec'ing the PATH shim makes MainPID the wrapper again"

    # ...and what is resolved INTO $bin: `bin="$(command -v agentboard)"` keeps `exec "$bin"` intact
    # while restoring the wrapper as MainPID. EVERY assignment feeding the exec, not just the first
    # -- the fallback at `[ -x "$bin" ] || bin=…` does not start with `bin=`, and `root=` is upstream
    # of both.
    assigns = [l for l in code if re.search(r"\b(?:bin|root)=", l)]  # \b excludes pkg_root=
    assert len(assigns) >= 3, f"expected root= plus both bin= assignments, found: {assigns}"
    for a in assigns:
        assert not any(t in a for t in ("command -v", "which ", "$(type")), f"resolution must not go via PATH: {a}"
    bins = [a for a in assigns if re.search(r"\bbin=", a)]
    assert bins, f"the script must resolve the platform binary into $bin: {assigns}"
    for b in bins:
        assert "agentboard-linux-x64/bin/agentboard" in b, f"$bin must resolve to the platform binary: {b}"
    roots = [a for a in assigns if re.search(r"\broot=", a)]
    assert roots and all("npm root -g" in r for r in roots), f"the root must come from npm's global prefix: {roots}"


NAS = ANSIBLE / "roles" / "nas" / "tasks" / "main.yml"


# "" is refused as AMBIGUOUS, not as CLI-rejected: env.j2 renders it as an empty assignment and both
# compose and the entrypoint substitute `full` for it -- a committed empty value must say what it means.
@pytest.mark.parametrize("value, expected", [("full", True), ("incremental", True), ("bogus", False), ("", False)])
def test_nas_hash_scope_guard_refuses_what_the_cli_would(value, expected):
    task = find_task(load_tasks(NAS), "refuse an archive-pull hash scope the CLI would reject")
    assert all(truthy(c, {"nas_archive_pull_hash_scope": value}) for c in assert_that(task)) is expected


def iter_tasks(tasks: list[dict], inherited: tuple[str, ...] = ()) -> list[tuple[dict, tuple[str, ...]]]:
    # Leaves only, each carrying the `when:` its enclosing blocks impose — Ansible's own inheritance,
    # so a task gated by its block reads as gated and a block never reads as a task in its own right.
    out: list[tuple[dict, tuple[str, ...]]] = []
    for t in tasks:
        gates = inherited + tuple(str(c) for c in when_conditions(t))
        children = [t[k] for k in ("block", "rescue", "always") if k in t]
        if children:
            for child in children:
                out.extend(iter_tasks(child, gates))
        else:
            out.append((t, gates))
    return out


# --- A1: the check-mode timer guard reads only `ops_unit_install`'s AGGREGATE changed flag, so it
# cannot separate a first install from an edit to a unit that already exists. The role's comment
# says so; these fixtures are the assertion of it.
def _unit_install(changed: list[bool]) -> dict:
    # The 8-item loop register the template module produces: the aggregate the guard reads, beside the
    # per-item `results` a narrowed guard would read.
    return {"changed": any(changed), "results": [{"changed": c} for c in changed], "skipped": False}


FIRST_INSTALL = _unit_install([True] * 8)
ONE_EDITED = _unit_install([True] + [False] * 7)
NOTHING_CHANGED = _unit_install([False] * 8)


@pytest.mark.parametrize(
    ("check_mode", "register", "expected", "why"),
    [
        (True, FIRST_INSTALL, False, "first install under --check: no unit was written, so skip"),
        (True, ONE_EDITED, False, "one PRE-EXISTING unit edited: the guard skips all four previews anyway"),
        (True, NOTHING_CHANGED, True, "nothing changed under --check: every unit exists, so preview the enable"),
        (False, ONE_EDITED, True, "REAL run: the render already wrote the units — never skip"),
    ],
    ids=["check-first-install", "check-one-edited", "check-nothing-changed", "real-run-one-edited"],
)
def test_the_timer_guard_suppresses_the_preview_for_a_changed_unit_that_already_existed(check_mode, register, expected, why):
    task = find_task(load_tasks(OPS), OPS_TIMER_ENABLE)
    variables = {"ansible_check_mode": check_mode, "ops_unit_install": register}
    assert truthy(when_conditions(task), variables) is expected, why


def test_the_timer_guard_cannot_tell_a_first_install_from_an_edit_to_an_existing_unit():
    """Pins the blind spot the role's comment documents — the guard reads the aggregate `changed` alone — so a
    deliberate narrowing updates this test and that comment together instead of one drifting off the other."""
    when = when_conditions(find_task(load_tasks(OPS), OPS_TIMER_ENABLE))
    fresh = truthy(when, {"ansible_check_mode": True, "ops_unit_install": FIRST_INSTALL})
    edited = truthy(when, {"ansible_check_mode": True, "ops_unit_install": ONE_EDITED})
    assert fresh == edited, (
        f"the guard now separates the shapes (first-install={fresh}, edited={edited}): if that narrowing is "
        "deliberate, retire this pin and the role's comment in the same change"
    )
    assert edited is not truthy(when, {"ansible_check_mode": True, "ops_unit_install": NOTHING_CHANGED}), (
        "the guard must still evaluate differently when nothing changed, or it gates nothing"
    )


# --- A2: a probe without `failed_when: false` aborts the play on a non-zero rc, so the guard that
# reads its rc never evaluates at all.
def test_every_ops_probe_never_fails_the_play():
    probes = [t for t, _ in iter_tasks(load_tasks(OPS)) if str(t.get("name", "")).startswith("probe")]
    assert probes, "no probe selected in the ops role — the name convention the selection reads has moved"
    print(f"ops-role probes selected: {len(probes)} — {[t['name'] for t in probes]}")
    for probe in probes:
        assert probe.get("failed_when") is False, (
            f"{probe['name']!r} carries failed_when={probe.get('failed_when')!r}: a non-zero rc aborts the play "
            "before the guard that reads it can run"
        )


# --- A3: the ack apparatus above the daemon.json template task exists only because that task
# notifies a handler that bounces dockerd. Ordering stays green when the notify is deleted.
DOCKER_HANDLERS = ANSIBLE / "roles" / "docker" / "handlers" / "main.yml"
DAEMON_JSON_TEMPLATE = "configure the docker daemon (bounded json-file log driver)"


def test_the_daemon_json_task_notifies_a_handler_that_restarts_dockerd():
    task = find_task(load_tasks(DOCKER), DAEMON_JSON_TEMPLATE)
    notify = task.get("notify", [])
    notify = [notify] if isinstance(notify, str) else list(notify)
    assert notify, f"{DAEMON_JSON_TEMPLATE!r} notifies nothing, so the ack guarding it guards no restart"

    handlers = {h["name"]: h for h in load_tasks(DOCKER_HANDLERS)}
    missing = [n for n in notify if n not in handlers]
    assert not missing, (
        f"{missing} is notified but not defined in {DOCKER_HANDLERS.name}: {sorted(handlers)} — resolved by handler "
        "NAME, so a handler that answers through `listen:` instead reds this while the claim stays true"
    )
    # by the handler's ACTION, not its name: a renamed-to-no-op handler keeps every name check green
    bouncers = [
        n
        for n in notify
        if any(
            isinstance(v, dict) and v.get("name") == "docker" and v.get("state") == "restarted"
            for k, v in handlers[n].items()
            if k != "name"
        )
    ]
    assert bouncers, f"no notified handler restarts dockerd, so the ack above this task is decoration: {notify}"


# --- A4: the role states the digest gate as its own convention. A task consumes an image reference
# when one appears in its own body OR in a file it renders — where the role's own comment locates it
# ("this script consumes no image reference"), the script being the RENDERED template.
OPS_DIGEST_GATE = "ops_image_digest is defined"
OPS_ROLE = ANSIBLE / "roles" / "ops"


def _expand_src(src: str, loop) -> list[str]:
    # `{{ item }}` against a literal `loop:` — a list, or a Jinja expression over literals. A src the
    # templar cannot expand comes back as it stands, for the caller to refuse by name.
    from ansible.errors import AnsibleError
    from ansible.template import trust_as_template

    def render(text: str, variables: dict):
        try:
            return Templar(loader=DataLoader(), variables=variables).template(trust_as_template(text))
        except AnsibleError:
            return text

    if "{{" not in src:
        return [src]
    items = loop if isinstance(loop, list) else render(loop, {}) if isinstance(loop, str) else None
    if not isinstance(items, list) or not items:
        return [src]
    return [render(src, {"item": item}) for item in items]


def _role_asset(name: str) -> Path | None:
    # Both of the role's asset directories, without asking which one the module searches: a name that
    # resolves to one file, or to the same content under both, is unambiguous whichever module renders
    # it; a name that resolves to two DIFFERENT files is refused rather than guessed. `None` is off the
    # role: unresolvable, or resolved by the resolver's last resort, the working directory.
    from ansible.errors import AnsibleError

    found: dict[Path, str] = {}
    for subdir in ("files", "templates"):
        try:
            path = Path(DataLoader().path_dwim_relative_stack([str(OPS_ROLE / "tasks"), str(OPS_ROLE)], subdir, name)).resolve()
        except AnsibleError:
            continue
        if path.is_file() and OPS_ROLE.resolve() in path.parents:
            found[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(set(found.values())) < 2, (
        f"{name!r} names a different file under each of {OPS_ROLE.name}/'s asset directories — "
        f"{sorted(str(p) for p in found)}: which one a task renders is the module's to decide, so this "
        "selection cannot read what that task consumes"
    )
    return next(iter(found), None)


def _body_text(task: dict) -> str:
    # WITHOUT the `when:`, which is what keeps the selection from reading the gate back to itself.
    return yaml.safe_dump({k: v for k, v in task.items() if k != "when"}, allow_unicode=True)


def _consumed_text(task: dict) -> str:
    # The task's body plus the text of every file its `src:` names. RESOLUTION decides, not spelling: what
    # resolves inside the role is read however the `src:` is written; what resolves nowhere is off
    # the role — skipped in silence where the `src:` is written as a path (the NFS mount source, the
    # controller-side copy), refused by name where it is a bare filename this role should own.
    text = _body_text(task)
    for value in task.values():
        src = value.get("src") if isinstance(value, dict) else None
        if not isinstance(src, str):
            continue
        for name in _expand_src(src, task.get("loop")):
            resolved = _role_asset(name) if isinstance(name, str) else None
            if resolved is None:
                assert "/" in src, (
                    f"{task['name']!r} renders {name!r}, which resolves to no file under {OPS_ROLE.name}/: this selection "
                    "cannot read what that task consumes"
                )
                continue
            text += resolved.read_text()
    return text


def test_every_image_consuming_ops_task_is_gated_on_the_digest():
    selected, rest = [], []
    for task, gates in iter_tasks(load_tasks(OPS)):
        (selected if "ops_image" in _consumed_text(task) else rest).append((task, gates))
    assert selected, "no image-consuming ops task selected — the selection rule stopped matching"
    print(f"image-consuming ops tasks: {len(selected)} of {len(selected) + len(rest)} — {[t['name'] for t, _ in selected]}")

    def self_gated(task: dict) -> bool:
        return any(OPS_DIGEST_GATE in str(c) for c in when_conditions(task))

    # Two degeneracies the loop below would survive, each excluded by the shape it would take: were
    # the `when:` dumped too, every self-gated task would select itself and none would be left here,
    assert [t["name"] for t, _ in rest if self_gated(t)], (
        "every task naming the digest gate in its own `when:` is selected — the selection is reading the gate back to itself"
    )
    # and were the body read alone, no task consuming the image only through a template would appear.
    # The operand is that template-derived set itself: a body-consuming task added inside a digest-gated
    # block would hold a "selected and block-gated only" operand non-empty while templates went unread.
    assert [t["name"] for t, _ in selected if "ops_image" not in _body_text(t)], (
        "no selected task consumes the image only through a rendered template — template text is no longer reaching the selection"
    )
    for task, gates in selected:
        assert any(OPS_DIGEST_GATE in g for g in gates), f"{task['name']!r} consumes an image reference ungated: {list(gates)}"


# --- A5: an empty hash scope renders a bare assignment, which both consumers read as `full`.
NAS_ENV_TEMPLATE = ANSIBLE / "roles" / "nas" / "templates" / "env.j2"
NAS_COMPOSE = REPO / "infra" / "nas" / "compose.yaml"
NAS_PULL_ENTRYPOINT = REPO / "infra" / "nas" / "pull-entrypoint.sh"
HASH_SCOPE_ENV = "ARCHIVE_PULL_HASH_SCOPE"
_HASH_SCOPE_EXPANSION = re.compile(r"\$\{" + HASH_SCOPE_ENV + r"[^}]*\}")


def _render_nas_env(hash_scope: str) -> str:
    from ansible.template import trust_as_template

    text = NAS_ENV_TEMPLATE.read_text()
    # A placeholder for every name the template reads as a BARE variable, not just the `nas_*` ones: a
    # new line naming anything else would otherwise raise undefined, a red that says nothing about the
    # claim below. A name that is CALLED is Jinja's own (`lookup`, `now`, `q`) — shadowing it with a
    # string is its own false red, so the lookahead leaves it to the environment.
    variables = {name: f"<{name}>" for name in set(re.findall(r"{{\s*(\w+)\b(?!\s*\()", text))}
    variables["nas_archive_pull_hash_scope"] = hash_scope
    return Templar(loader=DataLoader(), variables=variables).template(trust_as_template(text))


@pytest.mark.parametrize(("scope", "expected"), [("", f"{HASH_SCOPE_ENV}="), ("incremental", f"{HASH_SCOPE_ENV}=incremental")])
def test_nas_env_renders_an_empty_hash_scope_as_a_bare_assignment(scope, expected):
    """An empty value must render `NAME=`, not `NAME=""` — a quoted empty defeats the consumers' `:-` default."""
    rendered = [line for line in _render_nas_env(scope).splitlines() if line.startswith(HASH_SCOPE_ENV)]
    assert rendered == [expected]


@pytest.mark.parametrize(("value", "expected"), [("", "full"), ("incremental", "incremental")])
@pytest.mark.parametrize("path", [NAS_COMPOSE, NAS_PULL_ENTRYPOINT], ids=lambda p: p.name)
def test_both_hash_scope_consumers_substitute_full_for_an_empty_assignment(path, value, expected):
    """Evaluated, not spelled: `:-` substitutes on empty as well as unset, and `-` would not — bash is a proxy for
    Compose's own interpolation in compose.yaml, sound because the two agree on `:-` against `-`."""
    import os
    import subprocess

    expansions = sorted(set(_HASH_SCOPE_EXPANSION.findall(path.read_text())))
    assert expansions, f"{path.name} no longer expands {HASH_SCOPE_ENV}"
    for expansion in expansions:
        out = subprocess.run(
            ["bash", "-c", f'echo "{expansion}"'],
            capture_output=True,
            text=True,
            env={HASH_SCOPE_ENV: value, "PATH": os.environ["PATH"]},
        ).stdout.strip()
        assert out == expected, f"{path.name}'s {expansion} yields {out!r} for {value!r}, not {expected!r}"


# --- A6: the echo's negated clause and the assert's first disjunct must stay the same expression;
# both are extracted from the committed YAML, because retyping either here would only move the drift.
OPS_PINS_ECHO = "pins override accepted — the reason, on the record"


def _first_balanced_group(expr: str, start: int = 0) -> str:
    open_at = expr.index("(", start)
    depth = 0
    for i in range(open_at, len(expr)):
        depth += {"(": 1, ")": -1}.get(expr[i], 0)
        if depth == 0:
            return expr[open_at : i + 1]
    raise AssertionError(f"unbalanced parentheses from {open_at} in {expr!r}")


def test_the_pins_echo_negates_the_asserts_own_first_disjunct():
    tasks = load_tasks(OPS)
    disjunct = _first_balanced_group(" ".join(assert_that(find_task(tasks, OPS_PINS))))
    echo = " ".join(when_conditions(find_task(tasks, OPS_PINS_ECHO)))
    marker = "and not "
    assert echo.count(marker) == 1, f"the echo's negation is no longer unambiguous: {echo!r}"
    negated = _first_balanced_group(echo, echo.index(marker) + len(marker))

    # a vacuous "" == "" pass is the failure mode of extraction, so pin what the disjunct must contain
    assert "regex_search" in disjunct and "ops_fleet_pins_text" in disjunct, (
        f"extraction missed the recorded-digest test: {disjunct!r}"
    )
    assert " ".join(negated.split()) == " ".join(disjunct.split()), (
        f"the echo records an override on other cases:\n echo:   {negated}\n assert: {disjunct}"
    )
