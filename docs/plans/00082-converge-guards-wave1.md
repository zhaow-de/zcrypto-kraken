# Converge Guards Wave 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** every converge hazard spec `00082` classifies as guardable refuses at the point of use — thirteen Ansible guards, one probe-harness script, one Claude hook — each proven against a constructed violation before it counts.

**Architecture:** play-level `pre_tasks` — the un-tagged-primary refusal at `tags: [always]`, the engine window guard at `tags: [engine]` (cold review I2: always-tagged would refuse `--tags capture` primary runs the rule permits); role-level probe→assert blocks (the engine §8-gate idiom) for the rest; `tests/test_infra_converge_guards.py` evaluates each guard's real `that:`/`when:` expressions through Ansible's own `Templar` against violation/pass fixtures — the test boundary is *the expression given probe outcomes*, so fixtures supply registered-var shapes, never mock Ansible itself.

**Tech Stack:** ansible-core (already a venv dep), Jinja2, pytest, bash. No new dependencies.

## Global Constraints

- **Operator-facing text** (`.claude/rules/operator-facing-text.md`): every `fail_msg`/`msg` is runtime output from `infra/` — **no `T<NNNN>`, `iter-<N>`, `Phase <N>`, or spec serials in any rendered string**. Serials live in YAML comments only. Every `fail_msg` names the fix in the same sentence.
- **Probe idiom** (spec D2): probes are `failed_when: false`, `changed_when: false`, `check_mode: false`; asserts follow. The engine window guard alone adds `when: not ansible_check_mode`.
- **Var naming**: `ansible-lint var-naming[no-role-prefix]` requires role-registered/derived vars to carry the role prefix (`capture_*`, `engine_*`, `ops_*`) — Task 1 was forced into this; every later task uses prefixed names from the start, in guard YAML and test fixtures alike. Play-level `pre_tasks` registers in `site.yml` are outside the rule.
- **Override echo** (spec D1, second half): every overridable guard is followed by a `debug` task, gated on the override having been ACCEPTED, that prints the reason — the play log must carry the why, or the fail_msg's own promise ("it lands in this log") is false. Applies to canary + pins (Task 1, retrofitted in its fix round), the window guard (Task 2), engine pins (Task 3), ops pins (Task 4).
- **Override convention** (spec D1): `canary_override` / `pins_override` / `engine_window_override` accept only free text ≥ 9 chars that is not `true`/`false`/`1`/`yes`; canonical Jinja fragment (repeat verbatim wherever used):
  `(X | default('') | string | length > 8) and (X | default('') | string | lower not in ['true', 'false', '1', 'yes'])`
- **Guard-proving** (`agent-ops.md`): each task writes the failing test first; a guard whose violation fixture does not fail before the guard lands is a broken test, not a passing one. Read WHICH assertion fired.
- **No host contact in tests.** Everything evaluates locally. `ansible-lint` (commit gate) must stay green.
- Commits: stage by explicit path; Conventional Commits; every commit ends with the implementer's own `Co-Authored-By:` trailer (`commit-messages.md` — a subagent credits its **own** model); review-before-push per that rule is orchestrated outside this plan.
- Files named here are the complete change surface: `infra/ansible/site.yml`, `bootstrap.yml`, roles `capture|engine|ops|docker`, `infra/scripts/mutate-probe.sh`, `.claude/hooks/git-mv-guard.sh`, `.claude/settings.json`, `tests/test_infra_converge_guards.py`, `tests/test_mutate_probe.py`, `tests/test_git_mv_guard.py`. **Do not touch `docs/`** — closeout (Task 10) is orchestrator-owned.

______________________________________________________________________

### Task 1: Test scaffolding + capture-role guards (digest preflight, pair-add order, canary parity, pins recording)

**Files:**
- Create: `tests/test_infra_converge_guards.py`
- Modify: `infra/ansible/roles/capture/tasks/main.yml` (insert after the existing `fail fast if the pinned image digest was not supplied` assert)

**Interfaces:**
- Produces: `load_tasks(path)`, `find_task(tasks, name)`, `truthy(expr, variables)`, `assert_that(task)`, `when_conditions(task)` — every later task's tests reuse these; override cases are inlined per guard (no shared constructor).

- [ ] **Step 1: Write the failing tests**

```python
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
    refuse = {**PAIR_BASE, "primary_pairs": ["BTC/EUR", "ETH/EUR"]}
    ok = {**PAIR_BASE, "primary_pairs": ["BTC/EUR", "ETH/EUR", "XRP/BTC"]}
    assert not truthy(assert_that(task), refuse)
    assert truthy(assert_that(task), ok)


CANARY_BASE = {
    "capture_image_digest": "sha256:" + "c" * 64,
    "secondary_digest_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "0" * 64},
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
        "secondary_digest_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "c" * 64},
        "canary_override": "",
    }
    assert truthy(assert_that(task), ok)


PINS_BASE = {"running_digest_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "a" * 64}}
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
    variables = {**PINS_BASE, "fleet_pins_text": pins_text, "pins_override": override}
    assert truthy(assert_that(task), variables) is expected
```

- [ ] **Step 2: Run — expect FAIL with `KeyError` on every `find_task`** (the guards do not exist): `uv run pytest tests/test_infra_converge_guards.py -q`

- [ ] **Step 3: Implement the four capture-role guards.** Insert after the existing digest-empty assert in `infra/ansible/roles/capture/tasks/main.yml`:

```yaml
# --- spec 00082 converge guards (wave 1). Probe idiom: probes never fail or change; the assert
# --- refuses with the fix in the message. Tests: tests/test_infra_converge_guards.py.
- name: probe — is the pinned digest already on this host
  ansible.builtin.command: docker image inspect "{{ capture_image }}@{{ capture_image_digest }}"
  register: capture_digest_probe
  failed_when: false
  changed_when: false
  check_mode: false

- name: preflight — refuse a digest the host has not pulled
  ansible.builtin.assert:
    that: capture_digest_probe.rc == 0
    fail_msg: >-
      {{ capture_image }}@{{ capture_image_digest }} is not on {{ inventory_hostname }} — the unit's
      ExecStartPre pulls at start, so the stop→start window would contain a registry pull, extending
      the capture gap. Pre-stage it first:
      sudo docker pull {{ capture_image }}@{{ capture_image_digest }}

- name: probe — this host's own deployed pair list (does this converge ADD a pair?)
  ansible.builtin.slurp:
    src: /opt/zcrypto-capture/compose.yaml
  register: local_compose_raw
  when: inventory_hostname not in groups['engine_host']
  failed_when: false
  check_mode: false

- name: derive whether new pairs are being added (guard engages only then — I1)
  ansible.builtin.set_fact:
    deployed_pairs: >-
      {{ (local_compose_raw.content | b64decode | regex_search('CAPTURE_PAIRS: \"([^\"]*)\"', '\1') | first).split(',')
         if local_compose_raw.content is defined else [] }}
  when: inventory_hostname not in groups['engine_host']

- name: probe — the primary's deployed pair list (pair-add order; fail-CLOSED on unreachable, a new pair is the hazard)
  ansible.builtin.slurp:
    src: /opt/zcrypto-capture/compose.yaml
  register: primary_compose_raw
  delegate_to: "{{ groups['engine_host'] | first }}"
  when: >-
    inventory_hostname not in groups['engine_host']
    and capture_pairs | difference(deployed_pairs | default([])) | length > 0
  check_mode: false

- name: derive the primary's pair list
  ansible.builtin.set_fact:
    primary_pairs: >-
      {{ (primary_compose_raw.content | b64decode | regex_search('CAPTURE_PAIRS: \"([^\"]*)\"', '\1') | first).split(',') }}
  when: inventory_hostname not in groups['engine_host'] and primary_compose_raw.content is defined
  # no failed_when on the delegated slurp above: an unreachable primary FAILS the play when (and only
  # when) a new pair is being added — fail-closed is the point (spec D3-7)

- name: pair-add order — refuse a pair the primary does not already carry
  ansible.builtin.assert:
    that: capture_pairs | difference(primary_pairs) | length == 0
    fail_msg: >-
      {{ capture_pairs | difference(primary_pairs) | join(', ') }} not deployed on the primary —
      a secondary-first pair add poisons the reconciler's append-only ledger. Add the pair on the
      PRIMARY first (two --limit runs, primary then secondary), then re-run this converge.
  when: inventory_hostname not in groups['engine_host'] and primary_pairs is defined

- name: probe — the primary's running capture digest (canary scope)
  ansible.builtin.command: docker inspect --format '{{ "{{" }}.Config.Image{{ "}}" }}' zcrypto-capture
  register: primary_running_probe
  failed_when: false
  changed_when: false
  check_mode: false
  when: inventory_hostname in groups['engine_host']

- name: probe — the secondary's running capture digest (canary parity)
  ansible.builtin.command: docker inspect --format '{{ "{{" }}.Config.Image{{ "}}" }}' zcrypto-capture
  register: secondary_digest_probe
  delegate_to: "{{ (groups['capture_host'] | difference(groups['engine_host'])) | first }}"
  failed_when: false
  ignore_unreachable: true  # I1: an unreachable secondary must reach the assert (empty stdout -> refuse via override), never abort or silently pass
  changed_when: false
  check_mode: false
  when: >-
    inventory_hostname in groups['engine_host']
    and primary_running_probe.stdout is defined
    and capture_image_digest not in primary_running_probe.stdout

- name: canary parity — refuse a primary re-pin the secondary has not baked
  ansible.builtin.assert:
    that: >-
      (capture_image_digest in secondary_digest_probe.stdout | default(''))
      or ((canary_override | default('') | string | length > 8)
          and (canary_override | default('') | string | lower not in ['true', 'false', '1', 'yes']))
    fail_msg: >-
      The secondary does not run {{ capture_image_digest }} — the primary's canary gate is that digest
      running as capture on the secondary. Converge the secondary first and let it bake, or pass
      -e canary_override="<why this cannot wait>" (a reason, not a boolean; it lands in this log).
  when: >-
    inventory_hostname in groups['engine_host']
    and secondary_digest_probe is not skipped

- name: probe — the currently-running digest this converge would replace (pins recording)
  ansible.builtin.command: docker inspect --format '{{ "{{" }}.Config.Image{{ "}}" }}' zcrypto-capture
  register: running_digest_probe
  failed_when: false
  changed_when: false
  check_mode: false

- name: read fleet-pins.md from the controller tree
  ansible.builtin.set_fact:
    fleet_pins_text: "{{ lookup('file', playbook_dir ~ '/../../docs/reference/fleet-pins.md') }}"
  when: running_digest_probe.rc == 0

# M3: regex_search yields None (not an error) on a tag-started image ref; default('') then makes the
# needle empty, '' in text is True -> the guard passes open ONLY for a container with no sha256 digest
# in its ref, which cannot happen on this digest-pinned fleet; every sha-pinned ref is checked.
- name: pins recording — refuse to replace a digest fleet-pins.md does not record
  ansible.builtin.assert:
    that: >-
      ((running_digest_probe.stdout | default('') | regex_search('sha256:[0-9a-f]{12}') | default('') | replace('sha256:', '')) in fleet_pins_text)
      or ((pins_override | default('') | string | length > 8)
          and (pins_override | default('') | string | lower not in ['true', 'false', '1', 'yes']))
    fail_msg: >-
      The digest this converge replaces ({{ running_digest_probe.stdout }}) is not recorded in
      docs/reference/fleet-pins.md — an unrecorded pin is one docker-prune from an unrecoverable
      rollback. Record the CURRENT digest there first (or pass -e pins_override="<reason>" and
      record it immediately after).
  when: running_digest_probe.rc == 0 and fleet_pins_text is defined
```

- [ ] **Step 4: Run — expect PASS**: `uv run pytest tests/test_infra_converge_guards.py -q`, then `uv run pre-commit run -a` (ansible-lint included) until clean.
- [ ] **Step 5: Commit** `feat(config): capture-role converge guards — digest, pair order, canary, pins` staging exactly the two files.

______________________________________________________________________

### Task 2: site.yml pre_tasks — un-tagged-primary refusal + engine window guard

**Files:**
- Modify: `infra/ansible/site.yml` (capture play `pre_tasks` beside the existing `converge_primary` assert; engine play `pre_tasks`)
- Modify: `tests/test_infra_converge_guards.py` (append)

**Interfaces:**
- Consumes: Task 1's helpers.

- [ ] **Step 1: Failing tests** (append):

```python
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
        (1900, "", True),          # inside the gap
        (900, "", False),          # completion window [B, B+30min] may still be running
        (13900, "", False),        # within 10 min of the next boundary
        (900, "true", False),      # boolean override refused
        (900, "yes", False),       # I4: every canonical boolean spelling refused
        (900, "short", False),     # I4: sub-9-char fragment refused
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
```

Also append the when-scoping tests (cold review M4 — the `that:` tests never exercise the scoping, and a mis-scoped guard fires on the wrong host or never):

```python
def when_conditions(task: dict) -> list[str]:
    w = task.get("when", [])
    return w if isinstance(w, list) else [w]


def test_untagged_refusal_scopes_to_engine_host_members_only():
    task = find_task(load_tasks(SITE), "refuse an un-tagged run on the live primary")
    on_primary = {"inventory_hostname": "zcrypto", "groups": {"engine_host": ["zcrypto"]}}
    on_secondary = {"inventory_hostname": "zcrypto-red", "groups": {"engine_host": ["zcrypto"]}}
    assert truthy(when_conditions(task), on_primary)
    assert not truthy(when_conditions(task), on_secondary)


def test_canary_probe_activates_only_on_an_actual_repin():
    task = find_task(load_tasks(ANSIBLE / "roles" / "capture" / "tasks" / "main.yml"),
                     "probe — the secondary's running capture digest (canary parity)")
    base = {"inventory_hostname": "zcrypto", "groups": {"engine_host": ["zcrypto"], "capture_host": ["zcrypto", "zcrypto-red"]}}
    repin = {**base, "capture_image_digest": "sha256:" + "c" * 64,
             "primary_running_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "0" * 64}}
    same = {**base, "capture_image_digest": "sha256:" + "0" * 64,
            "primary_running_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "0" * 64}}
    assert truthy(when_conditions(task), repin)
    assert not truthy(when_conditions(task), same)


def test_pair_add_delegated_probe_engages_only_when_adding_pairs():
    task = find_task(load_tasks(ANSIBLE / "roles" / "capture" / "tasks" / "main.yml"),
                     "probe — the primary's deployed pair list (pair-add order; fail-CLOSED on unreachable, a new pair is the hazard)")
    base = {"inventory_hostname": "zcrypto-red", "groups": {"engine_host": ["zcrypto"]}}
    adding = {**base, "capture_pairs": ["BTC/EUR", "XRP/BTC"], "deployed_pairs": ["BTC/EUR"]}
    unchanged = {**base, "capture_pairs": ["BTC/EUR"], "deployed_pairs": ["BTC/EUR"]}
    assert truthy(when_conditions(task), adding)
    assert not truthy(when_conditions(task), unchanged)
```

- [ ] **Step 2: Run — FAIL (KeyError).**
- [ ] **Step 3: Implement.** Capture play, directly after the existing `refuse to converge the live primary unless explicitly asked` assert (composing with it — that one gates *touching* the primary, this one gates doing so *un-tagged*):

```yaml
    # spec 00082 guard 4: even with converge_primary granted, an UN-TAGGED run on the primary pulls
    # in the engine play, whose digest assert fails the host closed — and "fixing" that with
    # -e engine_image_digest=... restarts the LIVE trade engine. Tags must be named explicitly.
    - name: refuse an un-tagged run on the live primary
      ansible.builtin.assert:
        that: ansible_run_tags != ['all'] or ansible_skip_tags | length > 0
        fail_msg: >-
          This run names no tags — on the live primary that sweeps in every play, including the
          engine play. Scope it explicitly: --tags capture, --tags engine, or --skip-tags engine.
      when: inventory_hostname in groups['engine_host']
      tags: [always]
```

Engine play, after the existing note task:

```yaml
    # spec 00082 guard 5: the inter-cycle window, re-read from the TARGET's clock at execution time
    # (chrony-disciplined) — a converge backgrounded for hours re-asserts the window when it fires,
    # by construction. Skipped under check mode so --check --diff previews run at any hour.
    - name: probe — the engine host's clock (window guard)
      ansible.builtin.command: date +%s
      register: engine_epoch_probe
      failed_when: false
      changed_when: false
      check_mode: false
      when: not ansible_check_mode
      tags: [engine]  # I2: NOT always — a --tags capture primary run must not be window-blocked; guard 4 covers untagged runs

    - name: engine window — refuse a converge outside the inter-cycle gap
      ansible.builtin.assert:
        that: >-
          (((engine_epoch_probe.stdout | int) % 14400 >= 1800)
           and (14400 - ((engine_epoch_probe.stdout | int) % 14400) >= 600))
          or ((engine_window_override | default('') | string | length > 8)
              and (engine_window_override | default('') | string | lower not in ['true', 'false', '1', 'yes']))
        fail_msg: >-
          Outside the engine's inter-cycle gap (boundaries 00/04/08/12/16/20 UTC: the first 30 min
          belong to the running cycle, the last 10 min are too close to the next). Wait for the gap,
          or pass -e engine_window_override="<why this cannot wait>" (a reason, not a boolean).
      when: not ansible_check_mode and engine_epoch_probe.stdout is defined
      tags: [engine]
```

- [ ] **Step 4: Run — PASS; `pre-commit run -a` clean.**
- [ ] **Step 5: Commit** `feat(config): site.yml pre-task guards — tag discipline and the engine window`.

______________________________________________________________________

### Task 3: Engine-role guards — digest preflight + secrets/port preflight

**Files:**
- Modify: `infra/ansible/roles/engine/tasks/main.yml` (after the §8 gate, before any render)
- Modify: `tests/test_infra_converge_guards.py`

- [ ] **Step 1: Failing tests** — mirror Task 1's digest pair for `engine_digest_probe`; secrets test:

```python
ENGINE = ANSIBLE / "roles" / "engine" / "tasks" / "main.yml"


def test_engine_digest_preflight():
    task = find_task(load_tasks(ENGINE), "preflight — refuse a digest the host has not pulled")
    assert not truthy(assert_that(task), {"engine_digest_probe": {"rc": 1}})
    assert truthy(assert_that(task), {"engine_digest_probe": {"rc": 0}})


def test_engine_pins_recording_semantics():
    task = find_task(load_tasks(ENGINE), "pins recording — refuse to replace a digest fleet-pins.md does not record")
    variables = {"running_digest_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "e" * 64, "rc": 0},
                 "fleet_pins_text": "| engine | zcrypto | `" + "e" * 12 + "` |", "pins_override": ""}
    assert truthy(assert_that(task), variables)
    variables["fleet_pins_text"] = "| engine | zcrypto | `" + "f" * 12 + "` |"
    assert not truthy(assert_that(task), variables)


def test_engine_secrets_preflight():
    task = find_task(load_tasks(ENGINE), "preflight — refuse to restart the engine without its logship secrets")
    assert not truthy(assert_that(task), {"logship_secrets_stat": {"stat": {"exists": False}}})
    assert truthy(assert_that(task), {"logship_secrets_stat": {"stat": {"exists": True}}})
```

- [ ] **Step 2: FAIL.** **Step 3: Implement** (probe idiom; `docker image inspect` for `{{ engine_image }}@{{ engine_image_digest }}` → `engine_digest_probe`; `ansible.builtin.stat` on `/opt/zcrypto-capture/logship-secrets.env` → `logship_secrets_stat`; assert exists with fail_msg *"absence crash-loops the engine instead of failing the render — the capture role renders it; run the capture play on this host first"*; plus an `ss -ltnp` probe of `:9102` registered and echoed via `debug` — recorded, not asserted, per spec: the holder is evidence for the operator, not a refusal condition). Pins-recording guard for the engine container mirrors Task 1's, probing `zcrypto-engine`.
- [ ] **Step 4: PASS + gate.** **Step 5: Commit** `feat(config): engine-role converge guards — digest, secrets, pins`.

______________________________________________________________________

### Task 4: Ops-role guards — digest preflight, liquidations decision, panel-timer hold, pins

**Files:**
- Modify: `infra/ansible/roles/ops/tasks/main.yml`
- Modify: `tests/test_infra_converge_guards.py`

- [ ] **Step 1: Failing tests**:

```python
OPS = ANSIBLE / "roles" / "ops" / "tasks" / "main.yml"


@pytest.mark.parametrize(
    ("decision", "pin_differs", "expected"),
    [("", True, False), ("yes", True, False), ("roll-after", True, True), ("defer", True, True), ("", False, True)],
)
def test_liquidations_repin_decision(decision, pin_differs, expected):
    task = find_task(load_tasks(OPS), "liquidations — require an explicit roll-after/defer decision on a repin")
    deployed = "sha256:" + ("d" * 64 if pin_differs else "e" * 64)
    variables = {
        "ops_image_digest": "sha256:" + "e" * 64,
        "liquidations_pin_probe": {"stdout": "    image: \"ghcr.io/zhaow-de/zcrypto-capture@" + deployed + "\""},
        "liquidations_decision": decision,
    }
    assert truthy(assert_that(task), variables) is expected


def test_panel_timer_hold_excludes_only_the_panel_timer():
    tasks = load_tasks(OPS)
    task = find_task(tasks, "enable + start the replay + panel timers")
    loop_expr = task["loop"]
    from ansible.template import trust_as_template

    held = Templar(loader=DataLoader(), variables={"ops_panel_timer_hold": True}).template(trust_as_template(loop_expr))
    live = Templar(loader=DataLoader(), variables={"ops_panel_timer_hold": False}).template(trust_as_template(loop_expr))
    assert "panel-materialize" not in held and "verify-replay" in held and "verified-replay" in held
    assert "panel-materialize" in live
```

Add the ops digest-preflight test (I4 — it was missing) beside the liquidations tests:

```python
def test_ops_digest_preflight():
    task = find_task(load_tasks(OPS), "preflight — refuse a digest the host has not pulled")
    assert not truthy(assert_that(task), {"ops_digest_probe": {"rc": 1}})
    assert truthy(assert_that(task), {"ops_digest_probe": {"rc": 0}})


@pytest.mark.parametrize("override,expected", [("", False), ("short", False), ("recorded in pins after emergency roll", True)])
def test_ops_pins_override_semantics(override, expected):
    task = find_task(load_tasks(OPS), "pins recording — refuse to replace a digest fleet-pins.md does not record")
    variables = {"running_digest_probe": {"stdout": "ghcr.io/zhaow-de/zcrypto-capture@sha256:" + "a" * 64, "rc": 0},
                 "fleet_pins_text": "| ops | zcrypto-ops | `" + "b" * 12 + "` |", "pins_override": override}
    assert truthy(assert_that(task), variables) is expected
```

- [ ] **Step 2: FAIL.** **Step 3: Implement.** Digest preflight + pins guard follow Task 1's YAML shape, with two ops-specific rules: **every ops guard is gated `when: ops_image_digest is defined`** (I3 — the role's own convention: a digestless config/alloy-only converge skips all image-consuming tasks, and a guard must not break it), and **the pins probe reads the `liquidations-poll` CONTAINER** (`docker inspect --format '{{ "{{" }}.Config.Image{{ "}}" }}' liquidations-poll`, probe idiom) — never the compose file, which is exactly the surface the 2026-07-31 incident showed lying while the container was right (spec D3-13; I7). Probe rc ≠ 0 (container absent) skips the pins guard. Liquidations: probe the deployed compose image line → `liquidations_pin_probe`; assert `(ops_image_digest in liquidations_pin_probe.stdout) or (liquidations_decision | default('') in ['roll-after', 'defer'])` with fail_msg naming both choices and the 30 h self-heal bound. Panel hold: change the loop on the existing enable-start task to
  `{{ ['verify-replay', 'verified-replay'] + ([] if ops_panel_timer_hold | default(false) | bool else ['panel-materialize']) }}`
  and add a comment: the silent re-arm after a converge was the recorded trap.
- [ ] **Step 4: PASS + gate.** **Step 5: Commit** `feat(config): ops-role converge guards — digest, liquidations decision, panel hold, pins`.

______________________________________________________________________

### Task 5: docker-role daemon.json change-ack

**Files:**
- Modify: `infra/ansible/roles/docker/tasks/main.yml` (before the existing template task)
- Modify: `tests/test_infra_converge_guards.py`

- [ ] **Step 1: Failing test** — `daemon.json — refuse an unacknowledged change (its handler bounces dockerd)`: `{"daemon_json_diff": {"rc": 1}, "daemon_json_ack": False}` → refuse; `{"daemon_json_diff": {"rc": 0}, "daemon_json_ack": False}` → pass; `rc: 1` + ack `True` → pass.
Include the rc==2 fixture (I5): `{"daemon_json_diff": {"rc": 2}, "daemon_json_ack": False}` → refuse (absent deployed file counts as differing).

- [ ] **Step 2: FAIL.** **Step 3: Implement**: template `daemon.json.j2` to `/run/zcrypto-daemon-json.probe` (`changed_when: false`, `check_mode: false` — **a stated exception to the read-only probe idiom: it writes to /run even under `--check`; tmpfs, no secrets, no service touched**, spec D3-8), `command: diff /run/zcrypto-daemon-json.probe /etc/docker/daemon.json` → `daemon_json_diff` (probe idiom; rc != 0 counts as differing), then **a `debug: var=daemon_json_diff.stdout_lines` task gated `when: daemon_json_diff.rc != 0`** — I5: a failed_when-false command prints nothing under the default callback, so without this the operator acks unseen content and the guard's boolean rationale is void — then assert `daemon_json_diff.rc == 0 or daemon_json_ack | default(false) | bool` with fail_msg: *"daemon.json would change and its handler restarts dockerd — under live capture that is a data gap. Review the diff above, then re-run with -e daemon_json_ack=true."*
- [ ] **Step 4: PASS + gate.** **Step 5: Commit** `feat(config): docker-role daemon.json change-ack guard`.

______________________________________________________________________

### Task 6: bootstrap.yml re-bootstrap refusal

**Files:**
- Modify: `infra/ansible/bootstrap.yml` — **capture play only** (M2: bootstrap.yml holds three plays; the ops/access plays are LAN-side, get no sshd drop-in, and their fail_msg would be wrong — generalizing them is wave-2 work if wanted, an explicit narrow here, not an oversight). The guard sits after the existing primary refusal and generalizes it to the *secondary*.
- Modify: `tests/test_infra_converge_guards.py`

- [ ] **Step 1: Failing test** — `refuse to re-bootstrap an already-provisioned host`: `{"deploy_user_probe": {"rc": 0}, "rebootstrap": False}` → refuse; `{"deploy_user_probe": {"rc": 2}}` → pass; rc 0 + `rebootstrap: True` → pass.
- [ ] **Step 2: FAIL.** **Step 3: Implement** (`gather_facts: false` play — use `ansible.builtin.command: getent passwd zcrypto-deploy`, probe idiom): assert `deploy_user_probe.rc != 0 or rebootstrap | default(false) | bool`, fail_msg names the evidence and the flag: *"zcrypto-deploy already exists on {{ inventory_hostname }} — this host is bootstrapped, and re-running would rewrite its sshd drop-in. Converge with site.yml instead, or pass -e rebootstrap=true if you are genuinely rebuilding it."* (Scope: the capture play only — see Files note.)
- [ ] **Step 4: PASS + gate.** **Step 5: Commit** `feat(config): bootstrap re-bootstrap refusal`.

______________________________________________________________________

### Task 7: `infra/scripts/mutate-probe.sh`

**Files:**
- Create: `infra/scripts/mutate-probe.sh` (mode 0755)
- Create: `tests/test_mutate_probe.py`

- [ ] **Step 1: Failing tests** (pytest + subprocess, the `test_capture_prune.py` pattern; scratch git repos in `tmp_path`):

```python
"""mutate-probe.sh: the guard-proving rule as executable form (spec 00082 D4)."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "mutate-probe.sh"


def run(args, cwd, env_extra=None):
    import os
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run([str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, env=env)


def make_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    target = tmp_path / "mod.py"
    target.write_text("VALUE = 1\n")
    probe = tmp_path / "probe.sh"
    probe.write_text("#!/bin/sh\ngrep -q 'VALUE = 1' mod.py\n")
    probe.chmod(0o755)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "seed"], check=True)
    return target


def test_refuses_dirty_worktree(tmp_path):
    target = make_repo(tmp_path)
    target.write_text("VALUE = 1\n# dirty\n")
    r = run(["--file", "mod.py", "--control", "s/VALUE = 1/VALUE = 9/", "--mutation", "s/VALUE/V/", "--", "./probe.sh"], tmp_path)
    assert r.returncode != 0 and "dirty" in (r.stdout + r.stderr).lower()


def test_control_mutation_must_fail_first(tmp_path):
    make_repo(tmp_path)
    # a control that CHANGES the file but does not break the probe (appends comments) => the
    # harness must abort before any real probe. (A non-matching sed would instead trip the
    # no-op guard -- that path has its own test below.)
    r = run(["--file", "mod.py", "--control", "s/$/ # c/", "--mutation", "s/VALUE = 1/VALUE = 2/", "--", "./probe.sh"], tmp_path)
    assert r.returncode != 0 and "control" in (r.stdout + r.stderr).lower()


def test_noop_mutation_aborts(tmp_path):
    make_repo(tmp_path)
    # I6b: a sed that matches nothing must abort loudly, never report SURVIVED on unmutated code
    r = run(["--file", "mod.py", "--control", "s/VALUE = 1/VALUE = 9/", "--mutation", "s/nonexistent/x/", "--", "./probe.sh"], tmp_path)
    assert r.returncode != 0 and "did not change" in (r.stdout + r.stderr)


def test_real_probe_runs_and_restores(tmp_path):
    target = make_repo(tmp_path)
    r = run(["--file", "mod.py", "--control", "s/VALUE = 1/VALUE = 9/", "--mutation", "s/VALUE = 1/VALUE = 2/", "--", "./probe.sh"], tmp_path)
    assert r.returncode == 0
    assert "SURVIVED" in r.stdout or "KILLED" in r.stdout
    assert target.read_text() == "VALUE = 1\n"  # restored byte-identically


def test_sandbox_refuses_pytest(tmp_path):
    make_repo(tmp_path)
    r = run(["--sandbox", "--file", "mod.py", "--control", "s/a/b/", "--mutation", "s/c/d/", "--", "pytest", "-q"], tmp_path)
    assert r.returncode != 0 and "pytest" in (r.stdout + r.stderr).lower()
```

- [ ] **Step 2: FAIL** (script absent). **Step 3: Implement** `mutate-probe.sh`:

```bash
#!/usr/bin/env bash
# The mutate -> measure -> restore cycle with its recorded traps closed (spec 00082 D4):
#   * refuses a dirty worktree (restore uses `git checkout --`, which destroys uncommitted work)
#   * --sandbox seeds from `git archive HEAD` (never cp -a) and REFUSES pytest there (the editable
#     install's .pth resolves cli/tests to the repo, so every verdict would measure unmutated code)
#   * PYTHONDONTWRITEBYTECODE=1 + __pycache__ purge (a same-second same-length mutation re-runs a
#     stale .pyc otherwise)
#   * the CONTROL mutation must FAIL the probe before any real probe counts -- an unproven harness
#     proves nothing (the guard-proving rule as code)
# Usage: mutate-probe.sh [--sandbox] --file <path> --control <sed-expr> --mutation <sed-expr> -- <probe-cmd...>
set -euo pipefail

sandbox=0; file=""; control=""; mutation=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --sandbox) sandbox=1; shift ;;
    --file) file="$2"; shift 2 ;;
    --control) control="$2"; shift 2 ;;
    --mutation) mutation="$2"; shift 2 ;;
    --) shift; break ;;
    *) echo "mutate-probe: unknown arg $1" >&2; exit 2 ;;
  esac
done
[[ -n "$file" && -n "$control" && -n "$mutation" && $# -gt 0 ]] || { echo "usage: mutate-probe.sh [--sandbox] --file F --control SED --mutation SED -- CMD..." >&2; exit 2; }

if [[ $sandbox -eq 1 ]]; then
  for w in "$@"; do case "$w" in *pytest*) echo "mutate-probe: REFUSING pytest in --sandbox — the editable install's .pth resolves cli/tests to the REPO, so the verdict measures unmutated code. Mutate in-repo on a committed tree instead." >&2; exit 3 ;; esac; done
  work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
  git archive HEAD | tar -x -C "$work"
  cd "$work"
else
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "mutate-probe: REFUSING — worktree dirty; restore uses 'git checkout --', which would destroy uncommitted work. Commit or stash first." >&2; exit 3
  fi
fi

export PYTHONDONTWRITEBYTECODE=1
purge() { find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true; }

# I6a: restore must work in BOTH modes — the sandbox has no .git, so keep a pristine copy and
# restore from it; in-repo, git is authoritative and the byte-identity check is the proof.
pristine="$(mktemp)"; cp "$file" "$pristine"
restore() {
  if [[ $sandbox -eq 0 ]]; then
    git checkout -q -- "$file"
    git diff --quiet -- "$file" || { echo "mutate-probe: restore FAILED for $file" >&2; exit 4; }
  else
    cp "$pristine" "$file"
  fi
  cmp -s "$pristine" "$file" || { echo "mutate-probe: restore FAILED for $file (differs from pristine copy)" >&2; exit 4; }
}

# I6b: a sed expression that matches nothing silently no-ops (the str.replace trap) — a probe on
# unmutated code is a false SURVIVED. Every apply must prove the file actually changed.
apply() {
  sed -i "$1" "$file"
  if cmp -s "$pristine" "$file"; then
    echo "mutate-probe: mutation '$1' did not change $file — a no-op sed proves nothing. Fix the expression." >&2
    exit 6
  fi
  purge
}

# 1. control: must FAIL, or the harness is not measuring
apply "$control"
if "$@" >/dev/null 2>&1; then restore; echo "mutate-probe: CONTROL mutation did not fail the probe — the harness does not bite; no real probe counts. Pick a control the probe must detect." >&2; exit 5; fi
restore

# 2. the real mutation
apply "$mutation"
if "$@" >/dev/null 2>&1; then verdict=SURVIVED; else verdict=KILLED; fi
restore; purge
echo "mutate-probe: $verdict (control proven, tree restored byte-identically)"
[[ "$verdict" == KILLED || "$verdict" == SURVIVED ]]
```

- [ ] **Step 4: PASS + gate** (shebang/executable hooks cover mode). **Step 5: Commit** `feat(infra): mutate-probe.sh — the guard-proving cycle as a script`.

______________________________________________________________________

### Task 8: the git-mv hook

**Files:**
- Create: `.claude/hooks/git-mv-guard.sh` (0755)
- Modify: `.claude/settings.json` (PostToolUse, matcher `Bash`)
- Create: `tests/test_git_mv_guard.py`

- [ ] **Step 1: Failing tests** — feed the script synthetic hook JSON on stdin while the **subprocess cwd** is a scratch repo in the `RM` state (the script uses process cwd; it ignores any `cwd` field in the JSON) (edit file → `git mv`); assert stdout warns naming the new path and the fix; a non-`git mv` command exits 0 silently; a clean `git mv` (no prior edit) exits 0 silently.
- [ ] **Step 2: FAIL.** **Step 3: Implement** (memo-guard's parsing idiom):

```bash
#!/usr/bin/env bash
# PostToolUse[Bash] guard: after any command containing `git mv`, warn on RM-state entries --
# rename staged while the worktree still differs, i.e. the staged rename carries PRE-edit content.
# The pre-commit framework stashes unstaged changes before hooks run, so repo-side hooks
# structurally cannot see this; the moment the trap forms is the only place to catch it.
set -euo pipefail
input="$(cat)"
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"
case "$cmd" in *"git mv"*) ;; *) exit 0 ;; esac
rm_lines="$(git status --porcelain 2>/dev/null | grep -E '^RM ' || true)"
[[ -z "$rm_lines" ]] && exit 0
echo "git-mv-guard: WARNING — rename staged but the worktree still differs (the staged rename carries the PRE-edit content):"
echo "$rm_lines"
echo "Fix: git add <newpath> for each line above, then verify against the COMMITTED tree (git show :<path>), never the working tree."
```

Settings entry appended to the existing `PostToolUse` array: matcher `Bash`, command `"$CLAUDE_PROJECT_DIR"/.claude/hooks/git-mv-guard.sh`, timeout 10.

- [ ] **Step 4: PASS + gate.** **Step 5: Commit** `claude(config): git-mv-guard hook — warn the moment the RM trap forms` (claude-kind: hook + settings + its test must not mix with other kinds → stage `.claude/*` in this commit; commit `tests/test_git_mv_guard.py` separately as `test(config): …`).

______________________________________________________________________

### Task 9: End-to-end gate + full suite

- [ ] Run `uv run pytest tests/test_infra_converge_guards.py tests/test_mutate_probe.py tests/test_git_mv_guard.py tests/test_infra_compose_templates.py -q` — all green.
- [ ] Run `uv run pre-commit run -a` — clean (ansible-lint across all touched YAML).
- [ ] Sanity: `ansible-playbook --syntax-check site.yml bootstrap.yml` from `infra/ansible/` (no inventory contact).

______________________________________________________________________

### Task 10: Closeout (orchestrator-owned — recorded here as tasks, not pre-written)

- [ ] The `capture-deploys.md` shrink list: one line per landed guard → pointer to its refusing mechanism, presented to the owner as per-edit sign-offs (protected set).
- [ ] `agent-ops.md`: the four mutation-probe bullets collapse to one pointer at `infra/scripts/mutate-probe.sh`.
- [ ] T0111 → `partial` (wave 1 + M-pair + fold-in landed; wave 2 the remainder); index sync.
- [ ] Decisions log (phase 6): override-semantics rulings (D1, the two acks), the hook take/drop.
- [ ] Iterations-history entry.
