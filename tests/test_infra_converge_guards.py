"""Spec 00082: converge guards evaluated through Ansible's own templar.

The test boundary is the guard's REAL condition expression fed constructed probe outcomes --
never a re-implementation of the logic. `load_task` reads the committed YAML; a guard whose
expression is edited drifts here immediately.
"""

import re
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


# An UNREACHABLE secondary is the whole reason the probe carries `ignore_unreachable: true` (I1): the
# result is REGISTERED but carries no `stdout`. Two independent halves make that refuse, and each is
# pinned below, because either one written differently passes the re-pin open:
#   * the assert's `when:` is `is not skipped` -- the natural-looking `stdout is defined` would SKIP
#     the guard on exactly the host it cannot read;
#   * the parity expression's `| default('')` supplies the empty string there is nothing to match in.
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
# Every fixture above sits far from both, so a weakening edit (1800 -> 1000, 600 -> 100) passes them
# all unchanged. These sit ON the comparison boundary, which is the only place a constant is pinned.
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
# in place of B+1800 -- usually earlier, but LATER when the cycle itself ran long (the last two tests
# in this section pin that direction, which no fixture below covers).
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


# The `{10}` in the stdout regex is what the fixture above is blind to: measured by flipping the
# committed expression's `^[0-9]{10}$` to `^[0-9]+$`, the Traceback fixture still passes while THIS
# one flips to allowed -- a short all-digit token becomes a floor in the distant past, i.e. no floor.
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
# point, not a bug. Every fixture above has completed_at early enough that a `min(completion+300,
# B+1800)` expression — the reading the old fail_msg's "when that is sooner" promised — would agree
# with the committed one, so nothing else in this file can tell the two apart.
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
    """The journal path is a LITERAL in site.yml — the probe stays self-contained, readable without
    resolving what the engine role happens to default to (a statically-listed role's defaults ARE
    play-wide on this ansible-core, so the literal is a choice, not a necessity). This test is the
    drift pin that choice owes: a relocation of engine_state_dir cannot silently turn the floor
    permanently conservative (probe rc!=0 forever, guard 'working' but never early)."""
    site_text = SITE.read_text()
    defaults = (SITE.parent / "roles" / "engine" / "defaults" / "main.yml").read_text()
    m = re.search(r"^engine_state_dir:\s*(\S+)", defaults, re.M)
    assert m, "engine_state_dir vanished from the engine role defaults"
    assert f"{m.group(1)}/journal/" in site_text


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
    # a dict fixture is `not skipped` under Templar — wave-1's echo tests evaluate this directly
    assert truthy(conds, v_overridden)
    assert not truthy(conds, {**v_overridden, "canary_override": "true"})
    # The third case every sibling echo test carries: the gate is ACCEPTANCE, not presence. Parity
    # PASSES here, so the reason overrode nothing and printing a "why" would be a false record.
    d = "sha256:" + "ab" * 32
    baked = {**v_overridden, "engine_secondary_digest_probe": {"stdout": f"ghcr.io/x/y@{d}"}}
    assert not truthy(conds, baked)


# --- fix round 1 (cold review M1): the mirror's original 7 tests never read the assert's/probe's
# `when:` side, so a fail-open rewrite of `is not skipped` or a typo'd register name left all 90
# green while the gate silently stood down. These three pin exactly what wave-1's own when-side
# tests pin for the capture block (test_canary_parity_refuses_an_unreachable_secondary and
# test_canary_probe_activates_only_on_an_actual_repin).
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


# --- ops-role guards. `ops_` fixture keys for the same var-naming reason as the engine block above.
# The ops role's own convention (roles/ops/defaults/main.yml: ops_image_digest has NO default) is
# that a digestless config/alloy-only converge SKIPS every image-consuming task -- so each guard
# here carries `when: ops_image_digest is defined`, and the three skip tests below pin that (one per
# guard), since a guard that refuses a legitimate alloy-only converge is a broken role, not a strict one.
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


# The stat MODULE's own failure is a fourth shape, distinct from the three the rc split names.
# Measured on the locked ansible-core: an EACCES on the path (an unreadable PARENT dir stats
# EACCES, not ENOENT) registers {"failed": false, "msg": "Permission denied"} with NO `stat` key --
# `failed_when: false` rewrites the flag, so nothing can arm on `.failed`, and the ABSENT KEY is the
# only signal there is. Read through `stat.exists | default(false)` that shape is indistinguishable
# from "absent", so both guards stood down and the repin proceeded undecided on the one file whose
# pin it moves. The when-chain now engages on the missing key, and the `that:` refuses there.
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
    # Textual pin, not a Templar fixture: without `follow: true` the real stat module lstats a
    # dangling compose.yaml symlink as exists=True, readable=False, tripping the readability guard's
    # chmod/chown fail_msg on a target that was never a permission fault. `follow: true` restores
    # spec D9's `test -e`/`test -r` semantics (both resolve symlinks), so a dangling link reads as
    # absent -> stand-down, matching the old grep behavior.
    task = find_task(load_tasks(OPS), "probe — the deployed liquidations compose file (existence vs readability)")
    assert task["ansible.builtin.stat"]["follow"] is True
    # Spec D9 also specifies `failed_when: false`, which every sibling probe in this role carries: a
    # stat MODULE failure (an unreadable PARENT dir stats EACCES, not ENOENT) would otherwise abort
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
# Its absence made ANY newly added timer unconvergeable through the sanctioned path: under --check
# the unit file is never really written, so enable+start cannot find it, the preview fails, and
# converge.sh refuses the real pass while the preview is red. Nothing pinned that before, so the
# defect was found by hitting it on a live converge rather than in CI.
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
#
# `test_pins_recording_semantics` above feeds the assert CONSTRUCTED probe outcomes, so it is
# structurally blind to what the probe actually inspects. That blindness had a cost: the ops pins
# probe named `liquidations-poll` -- the entrypoint COMMAND -- while the role's own compose template
# rendered `zcrypto-ops-liquidations`. `docker inspect` therefore always returned rc=1, and the
# guard's `when: ... rc == 0` gate skipped the assert on every ops converge this host ever ran. A
# fail-OPEN guard on what its own fail_msg calls "the only rollback operand this host has", found
# 2026-08-20 on a live converge.
#
# Both sites now read `ops_liquidations_container`. This test pins that they agree, so a future
# edit to either one cannot silently re-open the hole.
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
    # and the entrypoint still invokes the SUBCOMMAND of that name -- asserted on the exact
    # exec-form fragment, because the bare string also matches a comment and would pass on a
    # template that no longer runs the poller at all
    assert '"zcrypto", "liquidations-poll"' in template, (
        "the liquidations service must still invoke the liquidations-poll subcommand"
    )
